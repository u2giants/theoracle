// D14 — Claim extraction drain task (Batch API path)
//
// Cron: every 10 minutes. Polls in-flight provider_batch_jobs rows for the
// claim_extraction task type. When a batch reaches 'completed' status, walks
// each per-request result and runs the existing R5/R5.5 validation +
// promotion pipeline (processSegmentOutput from claim-extraction.ts) so
// batch-mode candidates land in the DB through the SAME code path as sync.
//
// Cost dashboards: every model_runs row inserted by this task has
// dispatch_mode='batch' so admin /admin/ai pages can distinguish batch from
// sync once the model_runs_with_usage view is updated to expose the column
// (HANDOFF.md Step 0 note).
//
// Per-result error handling:
//   - item.success === false  → extraction_batches.status='failed', messages
//     marked 'failed' with the provider error message
//   - schema parse fails       → same
//   - happy path               → model_runs + model_run_usage_details + batch
//     marked 'model_complete', then processSegmentOutput runs the validators

import { schedules } from '@trigger.dev/sdk/v3';
import { eq, inArray, sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  employees,
  extractionBatches,
  jobRuns,
  messages,
  modelRunUsageDetails,
  modelRuns,
  providerBatchJobs,
  settings,
  type OracleDb,
  type ProviderBatchJob,
} from '@oracle/db';
import {
  buildStandardAdapters,
  ExtractionOutputSchema,
  getOracleRoute,
  supportsBatch,
  type BatchResultItem,
  type BatchStatus,
  type ExtractionOutput,
  type FormattedMessage,
  type OracleModelRoute,
} from '@oracle/ai';
import {
  buildOracleClient,
  loadActiveTopDomainIds,
  loadEntityRegistry,
  processSegmentOutput,
} from './claim-extraction';

export interface BatchDrainTotals {
  ok: boolean;
  batchesPolled: number;
  batchesCompleted: number;
  segmentsProcessed: number;
  claimsPromoted: number;
  duplicatesAppended: number;
  rejections: number;
  errors: number;
}

export async function runClaimExtractionBatchDrainOnce(
  triggerRunId: string,
): Promise<BatchDrainTotals> {
  const db = getDirectDb();
  const startedAt = new Date();
  const totals: Omit<BatchDrainTotals, 'ok'> = {
    batchesPolled: 0,
    batchesCompleted: 0,
    segmentsProcessed: 0,
    claimsPromoted: 0,
    duplicatesAppended: 0,
    rejections: 0,
    errors: 0,
  };

  const [jobRun] = await db
    .insert(jobRuns)
    .values({
      triggerRunId,
      jobType: 'claim-extraction-batch-drain',
      status: 'running',
      startedAt,
    })
    .returning({ id: jobRuns.id });
  if (!jobRun) throw new Error('[claim-extraction-batch-drain] failed to insert job_runs row');

  try {
    const pendingBatches = await db
      .select()
      .from(providerBatchJobs)
      .where(
        sql`${providerBatchJobs.status} IN ('submitted','in_progress') AND ${providerBatchJobs.taskType} = 'message_claim_extraction'`,
      );

    if (pendingBatches.length === 0) {
      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: { ...totals, reason: 'no pending batches' } })
        .where(eq(jobRuns.id, jobRun.id));
      return { ok: true, ...totals };
    }

    const adapters = buildStandardAdapters();
    const activeTopDomainIds = await loadActiveTopDomainIds(db);
    const entityRegistry = await loadEntityRegistry(db);
    // The OracleAIClient is unused by processSegmentOutput (no model calls are
    // made during drain — the model output was produced by the batch already),
    // but we instantiate it so the standard adapter map is initialized once.
    void buildOracleClient();

    for (const batchJob of pendingBatches) {
      totals.batchesPolled += 1;
      try {
        const finalStatus = await drainOneBatch(db, batchJob, adapters, activeTopDomainIds, entityRegistry, totals);
        if (finalStatus === 'completed') totals.batchesCompleted += 1;
      } catch (err) {
        totals.errors += 1;
        console.error('[claim-extraction-batch-drain] batch drain failed', batchJob.id, err);
        // Don't mark the batch as failed on a transient retrieval error —
        // leave it as-is so the next cron tick retries.
        await db
          .update(providerBatchJobs)
          .set({
            pollLastAt: new Date(),
            errorJson: { message: err instanceof Error ? err.message : String(err), transient: true },
          })
          .where(eq(providerBatchJobs.id, batchJob.id));
      }
    }

    await db
      .update(jobRuns)
      .set({ status: 'complete', finishedAt: new Date(), outputJson: totals })
      .where(eq(jobRuns.id, jobRun.id));
    return { ok: true, ...totals };
  } catch (fatalErr) {
    await db
      .update(jobRuns)
      .set({
        status: 'failed',
        finishedAt: new Date(),
        error: fatalErr instanceof Error ? fatalErr.message : String(fatalErr),
      })
      .where(eq(jobRuns.id, jobRun.id));
    throw fatalErr;
  }
}

async function drainOneBatch(
  db: OracleDb,
  batchJob: ProviderBatchJob,
  adapters: ReturnType<typeof buildStandardAdapters>,
  activeTopDomainIds: string[],
  entityRegistry: Awaited<ReturnType<typeof loadEntityRegistry>>,
  totals: Omit<BatchDrainTotals, 'ok'>,
): Promise<BatchStatus> {
  const adapter = adapters[batchJob.provider as keyof typeof adapters];
  if (!adapter || !supportsBatch(adapter)) {
    // Provider unsupported — mark the batch failed so it stops being polled.
    await db
      .update(providerBatchJobs)
      .set({
        status: 'failed',
        completedAt: new Date(),
        pollLastAt: new Date(),
        errorJson: { message: `no batch-capable adapter for provider ${batchJob.provider}` },
      })
      .where(eq(providerBatchJobs.id, batchJob.id));
    return 'failed';
  }

  const route = getOracleRoute(batchJob.routeId);
  if (!route) {
    await db
      .update(providerBatchJobs)
      .set({
        status: 'failed',
        completedAt: new Date(),
        pollLastAt: new Date(),
        errorJson: { message: `route ${batchJob.routeId} no longer in catalog` },
      })
      .where(eq(providerBatchJobs.id, batchJob.id));
    return 'failed';
  }

  const result = await adapter.retrieveBatch!({
    providerBatchId: batchJob.providerBatchId,
    providerMetadata: (batchJob.providerMetadataJson as Record<string, unknown> | null) ?? {},
    route,
  });

  // Always update poll_last_at + status + counts.
  await db
    .update(providerBatchJobs)
    .set({
      status: result.status,
      pollLastAt: new Date(),
      completedCount: result.completedCount ?? batchJob.completedCount,
      failedCount: result.failedCount ?? batchJob.failedCount,
      completedAt: result.status === 'completed' || result.status === 'failed' || result.status === 'expired' || result.status === 'canceled'
        ? new Date()
        : null,
      errorJson: result.error ? { message: result.error } : null,
    })
    .where(eq(providerBatchJobs.id, batchJob.id));

  if (result.status !== 'completed' || !result.results) {
    return result.status;
  }

  // Process each result. customId === extraction_batches.id by submit-task convention.
  for (const item of result.results) {
    await processBatchResultItem(db, batchJob, route, item, activeTopDomainIds, entityRegistry, totals);
  }

  await db
    .update(providerBatchJobs)
    .set({ resultsRetrievedAt: new Date() })
    .where(eq(providerBatchJobs.id, batchJob.id));

  return 'completed';
}

async function processBatchResultItem(
  db: OracleDb,
  batchJob: ProviderBatchJob,
  route: OracleModelRoute,
  item: BatchResultItem,
  activeTopDomainIds: string[],
  entityRegistry: Awaited<ReturnType<typeof loadEntityRegistry>>,
  totals: Omit<BatchDrainTotals, 'ok'>,
): Promise<void> {
  const extractionBatchId = item.customId;

  // Load the extraction_batches row + its segment messages.
  const [batchRow] = await db
    .select()
    .from(extractionBatches)
    .where(eq(extractionBatches.id, extractionBatchId))
    .limit(1);
  if (!batchRow) {
    console.warn('[claim-extraction-batch-drain] no extraction_batches row for customId', extractionBatchId);
    totals.errors += 1;
    return;
  }

  const segmentMessageIds = (batchRow.sourceMessageIds as string[] | null) ?? [];
  if (segmentMessageIds.length === 0) {
    totals.errors += 1;
    return;
  }

  // Load FormattedMessage[] for the segment. The shape mirrors the sync
  // worker's pending-messages SELECT.
  const segmentRows = await db
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
    .where(inArray(messages.id, segmentMessageIds))
    .orderBy(messages.createdAt);
  const segment = segmentRows as unknown as FormattedMessage[];

  // Per-request failure path (provider returned non-success for this customId).
  if (!item.success) {
    await markBatchFailed(db, extractionBatchId, segmentMessageIds, item.error ?? 'batch result error');
    totals.errors += 1;
    return;
  }

  // Parse / validate the output against the extraction schema.
  let modelOutput: ExtractionOutput;
  try {
    modelOutput = ExtractionOutputSchema.parse(item.output);
  } catch (parseErr) {
    await markBatchFailed(
      db,
      extractionBatchId,
      segmentMessageIds,
      `output failed schema validation: ${parseErr instanceof Error ? parseErr.message : String(parseErr)}`,
    );
    totals.errors += 1;
    return;
  }

  // Insert model_runs row (the batch path lacks a per-request latency, so
  // dispatch_mode + provider_request_id are the main signals).
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'claim-extraction',
      model: route.modelId,
      provider: route.provider,
      promptVersion: undefined,
      inputTokens: item.usage?.inputTokens ?? null,
      outputTokens: item.usage?.outputTokens ?? null,
      latencyMs: null,
      success: true,
      dispatchMode: 'batch',
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[batch-drain] failed to insert model_runs row');

  await db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
    contextPackId: batchRow.contextPackId,
    routeId: route.routeId,
    inputTokens: item.usage?.inputTokens ?? null,
    cachedInputTokens: item.usage?.cachedInputTokens ?? null,
    cacheWriteTokens: item.usage?.cacheWriteTokens ?? null,
    outputTokens: item.usage?.outputTokens ?? null,
    reasoningTokens: item.usage?.reasoningTokens ?? null,
    providerRequestId: item.usage?.providerRequestId ?? null,
    rawUsageJson: (item.usage?.rawUsageJson as Record<string, unknown> | undefined) ?? null,
  });

  await db
    .update(extractionBatches)
    .set({
      modelRunId: modelRun.id,
      modelRunIdsAttempted: [modelRun.id],
      rawModelOutput: modelOutput as unknown as Record<string, unknown>,
      status: 'model_complete',
    })
    .where(eq(extractionBatches.id, extractionBatchId));

  // Hand off to the shared per-segment processor.
  const outcome = await processSegmentOutput({
    db,
    route,
    activeTopDomainIds,
    entityRegistry,
    segment,
    extractionBatchId,
    modelRunId: modelRun.id,
    sourceHash: batchRow.sourceHash,
    modelOutput,
  });

  totals.segmentsProcessed += 1;
  totals.claimsPromoted += outcome.claimsPromoted;
  totals.duplicatesAppended += outcome.duplicatesAppended;
  totals.rejections += outcome.rejections;
}

async function markBatchFailed(
  db: OracleDb,
  extractionBatchId: string,
  segmentMessageIds: string[],
  errorMsg: string,
): Promise<void> {
  await db
    .update(extractionBatches)
    .set({ status: 'failed', error: errorMsg, finishedAt: new Date() })
    .where(eq(extractionBatches.id, extractionBatchId));
  if (segmentMessageIds.length > 0) {
    await db
      .update(messages)
      .set({ extractionStatus: 'failed', extractionError: errorMsg })
      .where(inArray(messages.id, segmentMessageIds));
  }
}

export const claimExtractionBatchDrainTask = schedules.task({
  id: 'claim-extraction-batch-drain',
  cron: '*/10 * * * *',
  maxDuration: 60 * 10,
  run: async (_payload, { ctx }) => {
    return runClaimExtractionBatchDrainOnce(ctx.run.id);
  },
});

// Settings import is unused at runtime — pulled in only to satisfy the
// Drizzle types when the file is consumed by the Trigger.dev build.
export const _settingsTableRef = settings;
