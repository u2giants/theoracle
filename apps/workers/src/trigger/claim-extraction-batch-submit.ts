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
  employees,
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
  type BatchRequest,
  type FormattedMessage,
} from '@oracle/ai';
import {
  BATCH_SIZE,
  buildContextPackInsert,
  groupIntoSegments,
  resolveExtractionRoute,
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
    const route = await resolveExtractionRoute(db);
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

    // 3. Pull pending messages.
    const pendingMessages = await db
      .select({
        id: messages.id,
        channelId: messages.channelId,
        employeeId: messages.employeeId,
        role: messages.role,
        content: messages.content,
        createdAt: messages.createdAt,
        authorName: employees.name,
      })
      .from(messages)
      .leftJoin(employees, eq(employees.id, messages.employeeId))
      .where(and(eq(messages.extractionStatus, 'pending'), eq(messages.role, 'user')))
      .orderBy(messages.createdAt)
      .limit(BATCH_SIZE);

    if (pendingMessages.length === 0) {
      await finish({ segmentsSubmitted: 0, reason: 'no pending messages' });
      return { ok: true, skipped: false, segmentsSubmitted: 0 };
    }

    // 4. Mark as 'processing' for idempotency.
    const messageIds = pendingMessages.map((m) => m.id);
    await db
      .update(messages)
      .set({ extractionStatus: 'processing' })
      .where(inArray(messages.id, messageIds));

    // 5. Group into segments + 6. Build extraction_batches + context_packs + BatchRequest list.
    const segments = groupIntoSegments(pendingMessages);
    const client = new OracleAIClient({ adapters, fallbackOnError: false });
    const requests: BatchRequest[] = [];
    const stagedBatchIds: string[] = [];
    const allMessageIdsForFailure: string[] = [];

    for (const segment of segments) {
      const segmentIds = segment.map((m) => m.id);
      allMessageIdsForFailure.push(...segmentIds);
      const userMessages = segment.filter((m) => m.role === 'user');
      if (userMessages.length === 0) {
        // Skip empty segments at submit time — mark messages as 'skipped'.
        await db
          .update(messages)
          .set({ extractionStatus: 'skipped', extractedAt: new Date() })
          .where(inArray(messages.id, segmentIds));
        continue;
      }

      const formatted = formatConversationSegment(segment);
      const blocks = [
        makeBlock({
          id: 'extraction-system',
          label: 'Extraction system prompt',
          kind: 'stable_system',
          content: EXTRACTION_SYSTEM_PROMPT,
          reasonIncluded: 'extraction prompt v' + EXTRACTION_PROMPT_VERSION,
        }),
        makeBlock({
          id: 'segment',
          label: 'Conversation segment to extract from',
          kind: 'dynamic_input',
          content: formatted,
          reasonIncluded: `segment of ${segment.length} message(s) in this batch`,
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

      const [contextPack] = await db
        .insert(oracleContextPacks)
        .values(buildContextPackInsert(plan))
        .returning({ id: oracleContextPacks.id });
      if (!contextPack) throw new Error('[batch-submit] failed to insert oracle_context_packs row');

      await db
        .update(extractionBatches)
        .set({ contextPackId: contextPack.id })
        .where(eq(extractionBatches.id, batch.id));

      stagedBatchIds.push(batch.id);
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
    // On any failure during submit, mark the fetched messages back to 'pending'
    // so the next run retries. extraction_batches rows we already inserted
    // stay around but their pending_model state will get reaped by a cron
    // sweeper down the line (or by the drain task noticing no provider job).
    const errMsg = err instanceof Error ? err.message : String(err);
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
