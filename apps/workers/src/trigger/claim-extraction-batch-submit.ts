// D14 — Claim extraction submit task (Batch API path)
//
// Cron: every 4 hours, same as the sync claim-extraction worker. Bails when
// settings.extraction_dispatch_mode !== 'batch'. The sync worker has a
// mirror-image bail when the flag IS 'batch', so the two paths never both
// process the same messages.
//
// Flow:
//   1. Read the flag — bail if not 'batch'
//   2. Resolve the extraction route + check its adapter supports batch
//   3. Pull pending user messages (BATCH_SIZE), mark them 'processing'
//   4. Group into 60-minute conversation segments
//   5. For each segment: compile the prompt plan, insert extraction_batches
//      and oracle_context_packs rows
//   6. Build BatchRequest[] (customId = extraction_batches.id)
//   7. Call adapter.submitBatch — submits the JSONL to OpenAI / GCS for Vertex
//   8. Insert provider_batch_jobs row with the providerBatchId + metadata
//   9. Link all extraction_batches rows to the provider_batch_jobs row
//
// The drain task (claim-extraction-batch-drain.ts) is what runs validation +
// promotion when the batch completes. This task only submits.

import { schedules } from '@trigger.dev/sdk/v3';
import { and, eq, inArray } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  extractionBatches,
  jobRuns,
  messages,
  oracleContextPacks,
  providerBatchJobs,
  settings,
} from '@oracle/db';
import {
  buildStandardAdapters,
  OracleAIClient,
  supportsBatch,
  zodToJsonSchema,
  makeBlock,
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  ExtractionOutputSchema,
  formatConversationSegment,
  loadClaimCorrectionLessonPack,
  type BatchRequest,
  type FormattedMessage,
} from '@oracle/ai';
import {
  BATCH_SIZE,
  buildContextPackInsert,
  loadExtractionSelectionSettings,
  resolveExtractionCandidates,
  selectPendingConversations,
} from './claim-extraction';

export interface BatchSubmitTotals {
  ok: boolean;
  skipped: boolean;
  reason?: string;
  segmentsSubmitted: number;
  providerBatchId?: string;
}

export async function runClaimExtractionBatchSubmitOnce(
  triggerRunId: string,
): Promise<BatchSubmitTotals> {
  const db = getDirectDb();
  const startedAt = new Date();

  const [jobRun] = await db
    .insert(jobRuns)
    .values({
      triggerRunId,
      jobType: 'claim-extraction-batch-submit',
      status: 'running',
      startedAt,
      inputJson: { batchSize: BATCH_SIZE },
    })
    .returning({ id: jobRuns.id });
  if (!jobRun) throw new Error('[claim-extraction-batch-submit] failed to insert job_runs row');

  const finish = async (output: Record<string, unknown>) => {
    await db
      .update(jobRuns)
      .set({ status: 'complete', finishedAt: new Date(), outputJson: output })
      .where(eq(jobRuns.id, jobRun.id));
  };

  // Hoisted so the catch can roll back the state this run created.
  // - claimedMessageIds: messages we flipped 'pending' → 'processing'.
  // - stagedBatchIds / stagedContextPackIds: extraction_batches +
  //   oracle_context_packs rows we inserted as part of staging segments.
  // - providerAccepted: flipped to true the moment adapter.submitBatch returns
  //   successfully. If a failure happens after that, the batch is live at the
  //   provider and the staging rows are still needed (drain finds them by
  //   customId from the batch result, not by provider_batch_job_id), so we
  //   leave them in place and log loudly instead of cleaning up.
  let claimedMessageIds: string[] = [];
  const stagedBatchIds: string[] = [];
  const stagedContextPackIds: string[] = [];
  let providerAccepted = false;
  let providerBatchIdForRecovery: string | null = null;
  let providerBatchJobInserted = false;

  try {
    // 1. Dispatch-mode gate — mirror image of the sync worker.
    const dispatchModeRow = await db
      .select({ value: settings.value })
      .from(settings)
      .where(eq(settings.key, 'extraction_dispatch_mode'))
      .limit(1);
    const dispatchMode = (dispatchModeRow[0]?.value as string | undefined) ?? 'sync';
    if (dispatchMode !== 'batch') {
      await finish({ skipped: true, reason: `extraction_dispatch_mode=${dispatchMode}` });
      return { ok: true, skipped: true, reason: `extraction_dispatch_mode=${dispatchMode}`, segmentsSubmitted: 0 };
    }

    // 2. Resolve route + check adapter capability.
    const routeCandidates = await resolveExtractionCandidates(db);
    const route = routeCandidates[0]!.route;
    const correctionLessons = await loadClaimCorrectionLessonPack(db);
    const adapters = buildStandardAdapters();
    const adapter = adapters[route.provider];
    if (!adapter) {
      await finish({ skipped: true, reason: `no adapter registered for provider ${route.provider}` });
      return { ok: true, skipped: true, reason: `no adapter for ${route.provider}`, segmentsSubmitted: 0 };
    }
    if (!supportsBatch(adapter)) {
      await finish({ skipped: true, reason: `adapter ${route.provider} does not implement Batch API` });
      return { ok: true, skipped: true, reason: `adapter ${route.provider} does not support batch`, segmentsSubmitted: 0 };
    }

    // 3. Pull whole pending conversations. Never split a conversation just
    // because the per-tick budget is reached.
    const selectionSettings = await loadExtractionSelectionSettings(db);
    const conversations = await selectPendingConversations(db, {
      charBudget: selectionSettings.charBudget,
      maxMessages: BATCH_SIZE,
      carryInCount: selectionSettings.carryInCount,
    });

    if (conversations.length === 0) {
      await finish({ segmentsSubmitted: 0, reason: 'no pending messages' });
      return { ok: true, skipped: false, segmentsSubmitted: 0 };
    }

    // 4. Mark selected segment messages as 'processing' for idempotency.
    // Carry-in context is not claimed or re-extracted.
    const messageIds = conversations.flatMap((conversation) =>
      conversation.segment.map((m) => m.id),
    );
    claimedMessageIds = messageIds;
    await db
      .update(messages)
      .set({ extractionStatus: 'processing' })
      .where(inArray(messages.id, messageIds));

    // 5. Build extraction_batches + context_packs + BatchRequest list.
    const client = new OracleAIClient({ adapters });
    const requests: BatchRequest[] = [];
    const allMessageIdsForFailure: string[] = [];

    for (const conversation of conversations) {
      const segment = conversation.segment;
      const segmentIds = segment.map((m) => m.id);
      allMessageIdsForFailure.push(...segmentIds);
      if (conversation.isOversized) {
        console.warn('[claim-extraction-batch-submit] submitting oversized conversation without truncation', {
          channelId: conversation.channelId,
          messages: segment.length,
          charCount: conversation.charCount,
          charBudget: selectionSettings.charBudget,
        });
      }
      const userMessages = segment.filter((m) => m.role === 'user');
      if (userMessages.length === 0) {
        // Skip empty segments at submit time — mark messages as 'skipped'.
        await db
          .update(messages)
          .set({ extractionStatus: 'skipped', extractedAt: new Date() })
          .where(inArray(messages.id, segmentIds));
        continue;
      }

      const formatted = formatConversationSegment(segment, { carryIn: conversation.carryIn });
      const blocks = [
        makeBlock({
          id: 'extraction-system',
          label: 'Extraction system prompt',
          kind: 'stable_system',
          content: EXTRACTION_SYSTEM_PROMPT,
          reasonIncluded: 'extraction prompt v' + EXTRACTION_PROMPT_VERSION,
        }),
        ...(correctionLessons.promptBlock
          ? [
              makeBlock({
                id: 'reviewer-correction-lessons',
                label: 'Approved reviewer correction lessons',
                kind: 'semi_stable_domain_context' as const,
                content: correctionLessons.promptBlock,
                reasonIncluded: 'approved claim revisions teach extraction corrections',
              }),
            ]
          : []),
        makeBlock({
          id: 'segment',
          label: 'Conversation segment to extract from',
          kind: 'dynamic_input',
          content: formatted,
          reasonIncluded: `segment of ${segment.length} message(s) with ${conversation.carryIn.length} non-quotable carry-in context message(s)`,
        }),
      ];
      const plan = client.compile({
        taskType: 'message_claim_extraction',
        routeId: route.routeId,
        promptVersion: EXTRACTION_PROMPT_VERSION,
        blocks,
        observability: { includedMessageIds: segmentIds },
      });
      const sourceHash = createHash('sha256').update(formatted, 'utf8').digest('hex');

      // Stage extraction_batches row in pending_model status (no model_run_id
      // yet — that gets filled in at drain time when results come back).
      const [batch] = await db
        .insert(extractionBatches)
        .values({
          jobRunId: jobRun.id,
          batchType: 'message_segment',
          status: 'pending_model',
          sourceMessageIds: segmentIds,
          sourceHash,
          modelRunIdsAttempted: [],
          routeIdsAttempted: [route.routeId],
        })
        .returning({ id: extractionBatches.id });
      if (!batch) throw new Error('[batch-submit] failed to insert extraction_batches row');
      // Track for rollback immediately — if the context_pack insert below
      // throws, this row is already orphaned and the catch needs to delete it.
      stagedBatchIds.push(batch.id);

      const [contextPack] = await db
        .insert(oracleContextPacks)
        .values(buildContextPackInsert(plan))
        .returning({ id: oracleContextPacks.id });
      if (!contextPack) throw new Error('[batch-submit] failed to insert oracle_context_packs row');
      stagedContextPackIds.push(contextPack.id);

      await db
        .update(extractionBatches)
        .set({ contextPackId: contextPack.id })
        .where(eq(extractionBatches.id, batch.id));

      requests.push({
        customId: batch.id, // extraction_batches.id IS the customId so drain can map results
        plan,
      });
    }

    if (requests.length === 0) {
      await finish({ segmentsSubmitted: 0, reason: 'all segments were user-message-free; no batch submitted' });
      return { ok: true, skipped: false, segmentsSubmitted: 0 };
    }

    // 7. Submit batch via adapter.
    const jsonSchema = zodToJsonSchema(ExtractionOutputSchema);
    const submitResult = await adapter.submitBatch!({
      route,
      requests,
      jsonSchema,
    });
    // The provider has accepted the batch — from here on, staging rows MUST
    // survive any catch path because the drain task will need them to map
    // results back via customId.
    providerAccepted = true;
    providerBatchIdForRecovery = submitResult.providerBatchId;

    // 8. Insert provider_batch_jobs row.
    const [batchJob] = await db
      .insert(providerBatchJobs)
      .values({
        provider: route.provider,
        providerBatchId: submitResult.providerBatchId,
        status: 'submitted',
        taskType: 'message_claim_extraction',
        routeId: route.routeId,
        modelId: route.modelId,
        requestCount: requests.length,
        providerMetadataJson: submitResult.providerMetadata,
      })
      .returning({ id: providerBatchJobs.id });
    if (!batchJob) throw new Error('[batch-submit] failed to insert provider_batch_jobs row');
    providerBatchJobInserted = true;

    // 9. Link extraction_batches rows to the batch job.
    await db
      .update(extractionBatches)
      .set({ providerBatchJobId: batchJob.id })
      .where(inArray(extractionBatches.id, stagedBatchIds));

    await finish({
      segmentsSubmitted: requests.length,
      providerBatchId: submitResult.providerBatchId,
      providerBatchJobId: batchJob.id,
    });
    return {
      ok: true,
      skipped: false,
      segmentsSubmitted: requests.length,
      providerBatchId: submitResult.providerBatchId,
    };
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);

    // Two failure regimes:
    //
    //  (a) providerAccepted === false: the failure happened before the
    //      provider accepted the batch. Nothing is live upstream. Roll back
    //      everything this run created — messages back to pending, staged
    //      extraction_batches + oracle_context_packs deleted — so the next
    //      cron tick gets a clean retry and the admin observability surface
    //      isn't littered with stale pending_model rows that will never get
    //      drained.
    //
    //  (b) providerAccepted === true but providerBatchJobInserted === false:
    //      the provider has an upstream batch, but Oracle has no durable row
    //      for the drain task to poll. That upstream batch is intentionally
    //      abandoned; reset local state so the next cron can submit a tracked
    //      retry instead of leaving messages stuck as 'processing'.
    //
    //  (c) providerBatchJobInserted === true: the provider batch is tracked.
    //      A failure after that point means messages stay 'processing' and
    //      staging rows MUST be kept — drain can recover by polling the job.
    if (!providerAccepted || !providerBatchJobInserted) {
      if (providerAccepted) {
        console.error(
          '[claim-extraction-batch-submit] provider accepted a batch but local provider_batch_jobs insert failed; abandoning upstream batch and resetting local state',
          { providerBatchId: providerBatchIdForRecovery, error: errMsg },
        );
      }
      if (claimedMessageIds.length > 0) {
        try {
          await db
            .update(messages)
            .set({ extractionStatus: 'pending' })
            .where(
              and(
                inArray(messages.id, claimedMessageIds),
                eq(messages.extractionStatus, 'processing'),
              ),
            );
        } catch (revertErr) {
          console.error(
            '[claim-extraction-batch-submit] failed to revert messages to pending',
            revertErr,
          );
        }
      }
      // Delete the FK child first (oracle_context_packs is referenced from
      // extraction_batches.context_pack_id), then the parent staging rows.
      // Both deletes are scoped to ids this run created, so they cannot
      // touch any other batch's state.
      if (stagedBatchIds.length > 0) {
        try {
          await db
            .delete(extractionBatches)
            .where(inArray(extractionBatches.id, stagedBatchIds));
        } catch (cleanupErr) {
          console.error(
            '[claim-extraction-batch-submit] failed to delete staged extraction_batches rows',
            cleanupErr,
          );
        }
      }
      if (stagedContextPackIds.length > 0) {
        try {
          await db
            .delete(oracleContextPacks)
            .where(inArray(oracleContextPacks.id, stagedContextPackIds));
        } catch (cleanupErr) {
          console.error(
            '[claim-extraction-batch-submit] failed to delete staged oracle_context_packs rows',
            cleanupErr,
          );
        }
      }
    } else {
      console.error(
        '[claim-extraction-batch-submit] failure after tracked provider batch creation — staging rows + messages left as-is for drain or manual recovery',
        {
          providerBatchId: providerBatchIdForRecovery,
          stagedBatchIds,
          stagedContextPackIds,
          claimedMessageCount: claimedMessageIds.length,
          error: errMsg,
        },
      );
    }

    await db
      .update(jobRuns)
      .set({ status: 'failed', finishedAt: new Date(), error: errMsg })
      .where(eq(jobRuns.id, jobRun.id));
    throw err;
  }
}

export const claimExtractionBatchSubmitTask = schedules.task({
  id: 'claim-extraction-batch-submit',
  cron: '0 */4 * * *',
  maxDuration: 60 * 5,
  run: async (_payload, { ctx }) => {
    return runClaimExtractionBatchSubmitOnce(ctx.run.id);
  },
});

// Suppress the unused-warning for FormattedMessage which is imported solely
// to satisfy the implicit-any check on groupIntoSegments callers in some
// downstream callers. Keep the import — re-importing it elsewhere is noisier.
export type { FormattedMessage };
