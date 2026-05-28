# HANDOFF — Batch API worker integration

Status: **foundation landed, worker integration pending**.

## What was built this session (2026-05-28)

Foundation for provider Batch API dispatch (DECISIONS.md D14):

- **Adapter contract** — `OracleProviderAdapter.submitBatch?` and `retrieveBatch?` are now part of the interface. Provider-agnostic types in [packages/ai/src/providers/types.ts](packages/ai/src/providers/types.ts).
- **OpenAI batch** — fully wired in [packages/ai/src/providers/openai-adapter.ts](packages/ai/src/providers/openai-adapter.ts). Uses `client.files.create` + `client.batches.create` against `/v1/chat/completions`. Requires no infrastructure beyond an OpenAI API key.
- **Vertex batch** — fully wired in [packages/ai/src/providers/vertex-gemini-adapter.ts](packages/ai/src/providers/vertex-gemini-adapter.ts). Uses GCS-backed JSONL via `client.batches.create`. Requires `GOOGLE_VERTEX_BATCH_GCS_BUCKET`.
- **DB schema** — migration [packages/db/migrations/sql/60_batch_jobs.sql](packages/db/migrations/sql/60_batch_jobs.sql) creates `provider_batch_jobs`, adds `extraction_batches.provider_batch_job_id`, adds `model_runs.dispatch_mode`. Schema mirror in [packages/db/src/schema.ts](packages/db/src/schema.ts).
- **Docs** — DECISIONS.md D14, docs/architecture.md "Batch API support" section, docs/configuration.md env-var rows and `extraction_dispatch_mode` setting row, .env.example, turbo.json globalEnv.
- **Side improvements** — Tooltip on grayed-out model-pool checkboxes ([apps/web/app/admin/settings/model-pool/_components/model-pool-editor.tsx](apps/web/app/admin/settings/model-pool/_components/model-pool-editor.tsx)) shows missing-capability icons + labels on hover.

Typecheck passes across all 7 workspaces.

## What is NOT done

The two-phase **worker integration** is not wired. The flag `settings.extraction_dispatch_mode` is recognized at the DB level but no code reads it yet.

Specifically:
1. `claim-extraction.ts` still always runs sync, regardless of the flag.
2. There is no `claim-extraction-batch-submit.ts` Trigger.dev task.
3. There is no `claim-extraction-batch-drain.ts` Trigger.dev task.
4. The migration has not been applied to the live DB. Run `pnpm db:migrate` first thing next session.

## Why deferred

Worker integration is a ~400 line refactor of [apps/workers/src/trigger/claim-extraction.ts](apps/workers/src/trigger/claim-extraction.ts) (currently 954 lines). The existing `processSegment` function interleaves prompt-compile + model-call + validate + promote + DB writes; the batch path needs the model-call replaced with submit-now/retrieve-later but the validate + promote logic shared verbatim with the drain task. Doing that refactor cleanly is a focused 2-3 hour piece of work that deserves a dedicated session rather than being squeezed in tonight.

## Exact next-action

### Step 0 — apply migration to live DB

```powershell
pnpm db:migrate
```

This applies `60_batch_jobs.sql` against the production Supabase project. Idempotent.

### Step 1 — extract `processSegmentOutput` from `claim-extraction.ts`

In [apps/workers/src/trigger/claim-extraction.ts](apps/workers/src/trigger/claim-extraction.ts) the function `processSegment` (line 263) does, in order:

1. Compile prompt plan
2. Insert `oracle_context_packs` row
3. Insert `model_runs` row
4. Call `client.runObject(ExtractionOutputSchema, plan, route)`
5. Insert `extraction_batches` row
6. **Process the result**: for each candidate, validate quotes, validate taxonomy, compute hash, insert `extraction_candidates` + `extraction_candidate_evidence`, run executePromotion. Track circuit-breaker counters. Update message extractionStatus.

Refactor target: extract steps 5+6 into a new exported function:

```typescript
export interface ProcessSegmentOutputArgs {
  db: OracleDb;
  client: OracleAIClient;  // for compile helpers
  route: OracleModelRoute;
  activeTopDomainIds: string[];
  entityRegistry: RegistryEntity[];
  jobRunId: string;
  segment: FormattedMessage[];           // original input
  output: ExtractionOutput;              // the structured model output
  usage: OracleUsage;                    // for filling model_run_usage_details
  modelRunId: string;                    // either created here or passed in
  contextPackId: string;
  // For batch mode: the in-flight extraction_batches row already exists
  existingExtractionBatchId?: string;
}
export async function processSegmentOutput(args: ProcessSegmentOutputArgs): Promise<SegmentOutcome>
```

Then `processSegment` becomes: steps 1-4 + call `processSegmentOutput(...)` with the inline result.

### Step 2 — write `apps/workers/src/trigger/claim-extraction-batch-submit.ts`

Scheduled task. Same gather + segment + prompt-compile logic as `claim-extraction.ts`, but instead of calling `client.runObject`:

```typescript
// 1. Build BatchRequest[] from segments
const requests: BatchRequest[] = [];
const segmentMap = new Map<string, { extractionBatchId: string, segmentMessageIds: string[] }>();

for (const seg of segments) {
  const plan = compileSegmentPlan(client, seg, route);
  // Insert extraction_batches row in pending_model status BEFORE submitting
  const [extractionBatch] = await db.insert(extractionBatches).values({
    batchType: 'message_segment',
    status: 'pending_model',
    sourceMessageIds: seg.map(m => m.id),
    sourceHash: ...,
  }).returning({ id: extractionBatches.id });
  
  const customId = extractionBatch.id;  // use the batch row id as customId
  requests.push({ customId, plan });
  segmentMap.set(customId, { extractionBatchId: extractionBatch.id, segmentMessageIds: seg.map(m => m.id) });
}

// 2. Submit batch via adapter
const adapter = client.getAdapter(route.provider);
if (!supportsBatch(adapter)) {
  // fall through to sync — or log and exit
  return { batchSubmitted: false, reason: 'adapter does not support batch' };
}
const submitResult = await adapter.submitBatch!({
  route,
  requests,
  jsonSchema: extractionJsonSchemaForRoute(route),
});

// 3. Insert provider_batch_jobs row
const [batchJob] = await db.insert(providerBatchJobs).values({
  provider: route.provider,
  providerBatchId: submitResult.providerBatchId,
  status: 'submitted',
  taskType: 'message_claim_extraction',
  routeId: route.routeId,
  modelId: route.modelId,
  requestCount: requests.length,
  providerMetadataJson: submitResult.providerMetadata,
}).returning({ id: providerBatchJobs.id });

// 4. Link extraction_batches rows to the batch job
await db.update(extractionBatches)
  .set({ providerBatchJobId: batchJob.id })
  .where(inArray(extractionBatches.id, Array.from(segmentMap.keys())));
```

Important: extraction_batches row is created **before** the submit. If the submit call throws, we have an orphan extraction_batches row with no providerBatchJobId — clean it up in an error path or just leave it (eventually a cron sweeper marks stale pending_model rows as failed).

### Step 3 — write `apps/workers/src/trigger/claim-extraction-batch-drain.ts`

Scheduled task, every 10 minutes. Polls in-flight batches and processes completed ones.

```typescript
const pending = await db.select().from(providerBatchJobs)
  .where(inArray(providerBatchJobs.status, ['submitted', 'in_progress']));

for (const job of pending) {
  const adapter = client.getAdapter(job.provider);
  if (!adapter || !supportsBatch(adapter)) continue;
  
  const result = await adapter.retrieveBatch!({
    providerBatchId: job.providerBatchId,
    providerMetadata: job.providerMetadataJson ?? {},
    route: resolveRouteById(job.routeId),
  });
  
  await db.update(providerBatchJobs).set({
    status: result.status,
    pollLastAt: new Date(),
    completedCount: result.completedCount,
    failedCount: result.failedCount,
    completedAt: result.status === 'completed' ? new Date() : undefined,
    errorJson: result.error ? { message: result.error } : undefined,
  }).where(eq(providerBatchJobs.id, job.id));
  
  if (result.status !== 'completed' || !result.results) continue;
  
  // Process each result by customId → extractionBatchId
  for (const item of result.results) {
    const extractionBatchId = item.customId;
    const linkedBatch = await db.select().from(extractionBatches)
      .where(eq(extractionBatches.id, extractionBatchId)).limit(1);
    if (linkedBatch.length === 0) continue;
    
    // The original segment messages — load via sourceMessageIds
    const segmentMessageIds = linkedBatch[0].sourceMessageIds as string[];
    const segment = await loadFormattedSegment(db, segmentMessageIds);
    
    if (!item.success) {
      // Mark extraction_batches as failed
      await db.update(extractionBatches).set({
        status: 'failed',
        error: item.error,
        finishedAt: new Date(),
      }).where(eq(extractionBatches.id, extractionBatchId));
      continue;
    }
    
    // Insert model_runs row for this individual result (with dispatch_mode='batch')
    const [modelRun] = await db.insert(modelRuns).values({
      taskType: 'message_claim_extraction',
      model: job.modelId,
      provider: job.provider,
      inputTokens: item.usage?.inputTokens,
      outputTokens: item.usage?.outputTokens,
      // cost: apply 50% batch discount to the model's per-token rate
      costUsd: computeBatchCost(item.usage, job.modelId),
      latencyMs: item.usage?.latencyMs,
      success: true,
      dispatchMode: 'batch',
    }).returning({ id: modelRuns.id });
    
    // The output is the parsed JSON object — validate against the schema
    const output = ExtractionOutputSchema.parse(item.output);
    
    // CALL THE SHARED FUNCTION — same code path as sync
    await processSegmentOutput({
      db, client, route, activeTopDomainIds, entityRegistry,
      jobRunId: ctx.run.id,
      segment,
      output,
      usage: item.usage ?? {},
      modelRunId: modelRun.id,
      contextPackId: '...',  // need to also create the context_pack at submit time
      existingExtractionBatchId: extractionBatchId,
    });
  }
  
  // Mark resultsRetrievedAt
  await db.update(providerBatchJobs).set({
    resultsRetrievedAt: new Date(),
  }).where(eq(providerBatchJobs.id, job.id));
}
```

### Step 4 — gate sync path on the flag

In `claim-extraction.ts` near the top of `runClaimExtractionOnce`:

```typescript
const mode = await db.select().from(settings).where(eq(settings.key, 'extraction_dispatch_mode')).limit(1);
const dispatchMode = (mode[0]?.value as string | undefined) ?? 'sync';
if (dispatchMode === 'batch') {
  return { skipped: true, reason: 'batch mode — handled by claim-extraction-batch-submit' };
}
// ... existing sync code ...
```

### Step 5 — seed the new setting

Add to [packages/db/src/seed.ts](packages/db/src/seed.ts) settings seeds:

```typescript
{ key: 'extraction_dispatch_mode', value: 'sync', description: '"sync" (default) or "batch". When "batch", claim extraction submits via provider Batch API for ~50% off pricing.' },
```

### Step 6 — provision the Vertex GCS bucket (one-time admin task, only if using Vertex batch)

```powershell
$gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd"
& $gcloud storage buckets create gs://oracle-vertex-batch-vertex-ai-497120 `
  --project=vertex-ai-497120 --location=us-central1 --uniform-bucket-level-access
& $gcloud storage buckets add-iam-policy-binding gs://oracle-vertex-batch-vertex-ai-497120 `
  --member="serviceAccount:oracle-trigger-worker@vertex-ai-497120.iam.gserviceaccount.com" `
  --role="roles/storage.objectAdmin"
# Set GOOGLE_VERTEX_BATCH_GCS_BUCKET=oracle-vertex-batch-vertex-ai-497120 in Vercel + Trigger.dev env
```

OpenAI batch requires no infrastructure — only `OPENAI_API_KEY`.

## How to verify when done

1. `pnpm db:migrate` against prod (or test against a branch DB first).
2. `UPDATE settings SET value = '"batch"'::jsonb WHERE key = 'extraction_dispatch_mode';`
3. Send a test message to a channel.
4. Wait for the next claim-extraction-batch-submit cron tick (or trigger manually from Trigger.dev dashboard).
5. Verify a `provider_batch_jobs` row exists with `status='submitted'`.
6. Wait up to 24 hours (typically much less for small batches — usually 10-30 min).
7. Verify the drain task marks status='completed' and `claims` rows appear with `model_run.dispatch_mode='batch'`.
8. Flip the flag back to 'sync' if anything looks off.

## Rollback

If the new tasks misbehave: `UPDATE settings SET value = '"sync"'::jsonb WHERE key = 'extraction_dispatch_mode';` — the worker reads the flag every tick, no redeploy needed.

If the new tasks misbehave AND have already submitted batches that are in flight: let them drain on their own (24-hour SLA, then expire); the drain task will mark them as expired and the `extraction_batches` rows can be cleaned up manually with `UPDATE extraction_batches SET status='failed', error='abandoned during rollback' WHERE provider_batch_job_id IN (...)`.

## Delete this file when work is complete.
