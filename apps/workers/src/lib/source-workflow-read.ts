import { and, desc, eq, inArray, ne, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import {
  OracleAIClient,
  AllCandidatesFailedError,
  RESPONSIBILITY_READ_PROMPT_VERSION,
  RESPONSIBILITY_READ_SYSTEM_PROMPT,
  RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
  RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT,
  ResponsibilityCompletionSchema,
  ResponsibilityCombinedRepairSchema,
  RESPONSIBILITY_COMBINED_REPAIR_PROMPT_VERSION,
  RESPONSIBILITY_COMBINED_REPAIR_SYSTEM_PROMPT,
  ResponsibilityReadSchema,
  SOURCE_READER_PIPELINE_VERSION,
  SOURCE_STRUCTURE_SHAPE_REGISTRY,
  SOURCE_SEGMENTATION_PROMPT_VERSION,
  SOURCE_SEGMENTATION_SYSTEM_PROMPT,
  WORKFLOW_READ_PROMPT_VERSION,
  WORKFLOW_READ_SYSTEM_PROMPT,
  WORKFLOW_QUOTE_REPAIR_SYSTEM_PROMPT,
  SourceSegmentationSchema,
  WorkflowReadSchema,
  WorkflowQuoteRepairSchema,
  buildStandardAdapters,
  estimateTokens,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type OraclePromptPlan,
  type ResponsibilityReadOutput,
  type ResponsibilityCompletionOutput,
  type ResponsibilityCombinedRepairOutput,
  type SourceSegmentationOutput,
  type SourceStructureSegment,
  type SourceStructureShape,
  type WorkflowReadEdge,
  type WorkflowReadLane,
  type WorkflowReadNode,
  type WorkflowReadOutput,
  type WorkflowQuoteRepairOutput,
  type WorkflowReadPath,
  type SourceStructureElement,
  type SourceStructureMap,
  type SourceStructureRelation,
} from '@oracle/ai';
import {
  businessProcesses,
  documentChunks,
  documents,
  entities,
  jobRuns,
  modelRunUsageDetails,
  modelRuns,
  modelCapabilities,
  oracleContextPacks,
  settings,
  sourceWorkflowMaps,
  type OracleDb,
} from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import { quoteSourceKindForDocument } from '@oracle/engines';
import {
  markMacroComplete,
  markMacroDegraded,
  markMacroMapFailed,
  markMacroPending,
} from './macro-health';
import {
  validateWorkflowMap,
  type WorkflowMapChunkContext,
  type WorkflowMapStatus,
} from './workflow-map-validator';
import {
  findResponsibilityOmissions,
  buildResponsibilityPostPassAudit,
  buildResponsibilitySelectedSpanAudit,
  buildGroundedResponsibilityQuoteCandidates,
  buildResponsibilityBaseReadPlan,
  bindForcedResponsibilitySpans,
  canonicalizeForcedResponsibilityOutput,
  completeAndMatchResponsibilityInventory,
  responsibilityFinalRecordCorrectionSeam,
  buildResponsibilityFinalRecordCorrectionAudit,
  lateResidualResponsibilitySeeds,
  mergeResponsibilityRecordsByInventoryId,
  canonicalizeResponsibilityCompletionBatch,
  packResponsibilityCompletions,
  selectStrictResponsibilityCompletionImprovements,
  finalizeForcedResponsibilityAudits,
  mergeResponsibilityValidationResults,
  mergeResponsibilityRetryValidation,
  patchCombinedResponsibilityRepairs,
  prefixResponsibilityOutput,
  assertUniqueResponsibilityElementIds,
  responsibilityParentSegment,
  responsibilityFailureTaxonomyCounts,
  responsibilityMergeEligibleElements,
  responsibilityRawAuditArtifact,
  selectResponsibilityQuoteRepairRead,
  ResponsibilityOmissionRetryScheduler,
  type ResponsibilityInventoryMatchAudit,
  shardResponsibilitySegments,
  validateResponsibilityRead,
  type GroundedResponsibilityQuoteCandidate,
  type ForcedResponsibilitySpan,
  type ResponsibilityCompletionBatch,
  type ResponsibilityCompletionPack,
  type ResponsibilityInventorySeed,
  type ResponsibilityCompletionBaseline,
  type FinalRecordCorrection,
} from './responsibility-reader';
import {
  mapWithConcurrency,
  ResponsibilityPostPassBudget,
  SourceReaderBudget,
  SourceReaderBudgetExceededError,
  type SourceReaderBudgetLimits,
  type ResponsibilityPostPassBudgetLimits,
} from './source-reader-budget';
import type {
  WorkflowMapRejectionDiagnostic,
  WorkflowMapValidationResult,
} from './workflow-map-validator';

type ChunkRow = {
  id: string;
  chunkIndex: number;
  pageNumber: number | null;
  rawText: string;
  contentHash: string | null;
};

type ReusableWorkflowMapStatus = 'validated' | 'degraded';

type ResponsibilityCompletionExecution = {
  output: ResponsibilityCompletionOutput;
  modelRunId: string;
  contextPackId: string;
  routeId: string;
  provider: string;
  model: string;
  execution: { outputTokens: number | null; finishReason: string | null; truncated: boolean };
};

async function loadResponsibilityCompletionPackingConfig(args: {
  db: OracleDb;
  budget: SourceReaderBudget;
  reserveQuoteRepair: boolean;
}) {
  const resolved = await resolveRouteCandidates(args.db, 'workflow_read');
  const candidate = resolved.candidates[0]!;
  const route = candidate.route;
  const catalogIds = [
    candidate.approvedModelId,
    `${route.provider}/${route.modelId}`,
    ...(route.provider === 'vertex' ? [`google/${route.modelId}`] : []),
  ];
  const rows = await args.db
    .select({
      id: modelCapabilities.id,
      contextLength: modelCapabilities.contextLength,
      maxOutputTokens: modelCapabilities.maxOutputTokens,
      promptPer1mUsd: modelCapabilities.promptPer1mUsd,
      completionPer1mUsd: modelCapabilities.completionPer1mUsd,
    })
    .from(modelCapabilities)
    .where(inArray(modelCapabilities.id, [...new Set(catalogIds)]));
  const pricing = catalogIds.flatMap((id) => rows.filter((row) => row.id === id))[0];
  const inputPrice = pricing?.promptPer1mUsd == null ? null : Number(pricing.promptPer1mUsd);
  const outputPrice = pricing?.completionPer1mUsd == null ? null : Number(pricing.completionPer1mUsd);
  if (inputPrice === null || outputPrice === null || !Number.isFinite(inputPrice) || !Number.isFinite(outputPrice)) {
    throw new Error(`[source-workflow-read] workflow_read completion pricing is missing for ${catalogIds.join(' / ')}`);
  }
  const snapshot = args.budget.snapshot();
  const reservedCalls = args.reserveQuoteRepair ? 1 : 0;
  return {
    resolved,
    pack: {
      remainingCalls: Math.max(0, snapshot.limits.maxReadCalls - snapshot.readCalls - reservedCalls),
      remainingInputTokens: Math.max(0, snapshot.limits.maxInputTokens - snapshot.inputTokens),
      remainingCostUsd: Math.max(0, snapshot.limits.maxEstimatedCostUsd - snapshot.estimatedCostUsd),
      fixedInputTokensPerCall: estimateTokens(RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT) + 512,
      fixedOutputTokensPerCall: 128,
      maxInputTokensPerCall: Math.max(
        1,
        Math.min(route.maxInputTokens ?? pricing?.contextLength ?? 100_000, 100_000) - 16_000,
      ),
      maxOutputTokensPerCall: Math.min(route.maxOutputTokens ?? pricing?.maxOutputTokens ?? 16_000, 16_000),
      inputCostPerMillionTokensUsd: inputPrice,
      outputCostPerMillionTokensUsd: outputPrice,
    },
  };
}

async function runResponsibilityCompletionModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  mapId: string;
  triggerRunId: string;
  batch: ResponsibilityCompletionBatch;
}): Promise<ResponsibilityCompletionExecution> {
  const resolved = await resolveRouteCandidates(args.db, 'workflow_read');
  for (const skipped of resolved.skipped) {
    console.warn('[source-workflow-read] skipped completion route candidate', skipped);
  }
  const route = resolved.candidates[0]!.route;
  const blocks = [
    makeBlock({
      id: 'responsibility-completion-system',
      label: 'Responsibility completion system prompt',
      kind: 'stable_system',
      content: RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT,
      reasonIncluded: RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
    }),
    makeBlock({
      id: 'responsibility-completion-metadata',
      label: 'Responsibility completion metadata',
      kind: 'semi_stable_domain_context',
      content: [`Document: ${args.doc.fileName}`, `Source map row: ${args.mapId}`].join('\n'),
      reasonIncluded: 'known source and durable audit context',
    }),
    makeBlock({
      id: 'responsibility-completion-request',
      label: 'Known responsibility completion batch',
      kind: 'dynamic_input',
      content: buildResponsibilityCompletionRequestContent(args.batch),
      reasonIncluded: `ordered completion batch ${args.batch.batchIndex + 1}`,
    }),
  ];
  const plan = args.client.compile({
    taskType: 'source_workflow_read',
    routeId: route.routeId,
    promptVersion: RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
    blocks,
    observability: { includedDocumentChunkIds: [...new Set(args.batch.requests.map((item) => item.chunkId))] },
  });
  const [contextPack] = await args.db.insert(oracleContextPacks).values(buildContextPackInsert(plan)).returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[source-workflow-read] failed responsibility completion context pack');
  const started = Date.now();
  const result = await args.client.runObject<ResponsibilityCompletionOutput>({
    taskType: 'source_workflow_read',
    routeId: route.routeId,
    promptVersion: RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
    blocks,
    schema: ResponsibilityCompletionSchema,
    observability: { includedDocumentChunkIds: [...new Set(args.batch.requests.map((item) => item.chunkId))] },
    providerOptions: { maxOutputTokens: Math.min(16_000, args.batch.estimatedOutputTokens) },
    routeCandidates: resolved.candidates,
  });
  const [modelRun] = await args.db.insert(modelRuns).values({
    taskType: 'source_workflow_read_responsibility_completion',
    model: result.modelId ?? route.modelId,
    provider: result.provider ?? route.provider,
    promptVersion: RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
    inputHash: plan.metadata.stablePrefixHash,
    inputTokens: result.usage.inputTokens ?? null,
    outputTokens: result.usage.outputTokens ?? null,
    latencyMs: Date.now() - started,
    success: result.validation.ok,
    error: result.validation.ok ? null : result.validation.error.message,
  }).returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[source-workflow-read] failed responsibility completion model run');
  await args.db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    routeId: result.routeId ?? route.routeId,
    inputTokens: result.usage.inputTokens ?? null,
    cachedInputTokens: result.usage.cachedInputTokens ?? null,
    cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
    outputTokens: result.usage.outputTokens ?? null,
    reasoningTokens: result.usage.reasoningTokens ?? null,
    providerRequestId: result.usage.providerRequestId ?? null,
    rawUsageJson: result.usage.rawUsageJson ?? null,
  });
  await logModelRunAttempts({ db: args.db, metadata: result, taskType: 'source_workflow_read_responsibility_completion', slot: 'workflow_read', contextPackId: contextPack.id, modelRunId: modelRun.id });
  await args.db.update(oracleContextPacks).set({ modelRunId: modelRun.id }).where(eq(oracleContextPacks.id, contextPack.id));
  if (!result.validation.ok) throw new Error(`[source-workflow-read] responsibility completion schema failed: ${result.validation.error.message}`);
  const rawUsage = result.usage.rawUsageJson as Record<string, unknown> | null | undefined;
  const finishReason = typeof rawUsage?.finishReason === 'string' ? rawUsage.finishReason : typeof rawUsage?.finish_reason === 'string' ? rawUsage.finish_reason : null;
  return {
    output: result.object,
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    routeId: result.routeId ?? route.routeId,
    provider: result.provider ?? route.provider,
    model: result.modelId ?? route.modelId,
    execution: { outputTokens: result.usage.outputTokens ?? null, finishReason, truncated: finishReason ? /length|max[_ -]?tokens|trunc/i.test(finishReason) : false },
  };
}

export function buildResponsibilityCompletionRequestContent(
  batch: ResponsibilityCompletionBatch,
): string {
  return JSON.stringify({
    instruction: 'Fill each known duty exactly once. Do not discover duties.',
    seeds: batch.requests,
  });
}

export function reserveResponsibilityCompletionBatches(args: {
  budget: SourceReaderBudget;
  batches: readonly ResponsibilityCompletionBatch[];
}): void {
  for (const batch of args.batches) {
    args.budget.reserveRead({
      estimatedInputTokens: batch.estimatedInputTokens,
      estimatedCostUsd: batch.estimatedCostUsd,
      label: `responsibility completion batch ${batch.batchIndex + 1}`,
    });
  }
}

export function forecastResponsibilityCompletionScenarios(args: {
  scenarios: Record<'low' | 'expected' | 'high', readonly ResponsibilityInventorySeed[]>;
  pack: Omit<Parameters<typeof packResponsibilityCompletions>[0], 'seeds'>;
}): Record<'low' | 'expected' | 'high', ResponsibilityCompletionPack> {
  return {
    low: packResponsibilityCompletions({ ...args.pack, seeds: args.scenarios.low }),
    expected: packResponsibilityCompletions({ ...args.pack, seeds: args.scenarios.expected }),
    high: packResponsibilityCompletions({ ...args.pack, seeds: args.scenarios.high }),
  };
}

export function responsibilityInventoryRequiresDegradedStatus(args: {
  sourceInventoryCount: number;
  mergeReadyInventoryCount: number;
  unscheduledCount: number;
  finalGapCount?: number;
}): boolean {
  return (
    args.sourceInventoryCount > args.mergeReadyInventoryCount ||
    args.unscheduledCount > 0 ||
    (args.finalGapCount ?? 0) > 0
  );
}

export function refreshResponsibilityInventoryMatchAudit(args: {
  audit: ResponsibilityInventoryMatchAudit;
  completeElementIds: readonly string[];
}): ResponsibilityInventoryMatchAudit {
  const completeIds = new Set(args.completeElementIds);
  const mergeReadyInventoryIds = args.audit.sourceInventoryIds.filter((id) => completeIds.has(id));
  return {
    ...args.audit,
    mergeReadyInventoryIds,
    mergeReadyInventoryCount: mergeReadyInventoryIds.length,
    incompleteSeedIds: args.audit.sourceInventoryIds.filter((id) => !completeIds.has(id)),
  };
}

export function canonicalResponsibilityInventory(args: {
  seeds: readonly ResponsibilityInventorySeed[];
  chunks: readonly { id: string }[];
}): ResponsibilityInventorySeed[] {
  const chunkOrder = new Map(args.chunks.map((chunk, index) => [chunk.id, index]));
  const unique = new Map<string, ResponsibilityInventorySeed>();
  const sourceOrder = new Map<string, number>();
  for (const seed of args.seeds) {
    const prior = unique.get(seed.inventorySeedId);
    if (prior && JSON.stringify(prior) !== JSON.stringify(seed)) {
      throw new Error(`Conflicting responsibility inventory seed: ${seed.inventorySeedId}`);
    }
    if (!prior) {
      sourceOrder.set(seed.inventorySeedId, sourceOrder.size);
      unique.set(seed.inventorySeedId, seed);
    }
  }
  return [...unique.values()].sort((a, b) =>
    (chunkOrder.get(a.chunkId) ?? Number.MAX_SAFE_INTEGER) -
      (chunkOrder.get(b.chunkId) ?? Number.MAX_SAFE_INTEGER) ||
    a.sourceStart - b.sourceStart ||
    (sourceOrder.get(a.inventorySeedId) ?? Number.MAX_SAFE_INTEGER) -
      (sourceOrder.get(b.inventorySeedId) ?? Number.MAX_SAFE_INTEGER)
  );
}

export function isRetryableResponsibilityCompletionFailure(error: unknown): boolean {
  if (error instanceof AllCandidatesFailedError) return true;
  const name = error instanceof Error ? error.name : '';
  if (['AllCandidatesFailedError', 'AbortError', 'TimeoutError'].includes(name)) return true;
  const message = error instanceof Error ? error.message : String(error);
  return /timeout|timed out|schema|structured output|all model candidates failed/i.test(message);
}

export type ResponsibilityCompletionTerminalOutcome = {
  responsibilityId: string;
  status: 'accepted' | 'validation_rejected' | 'provider_failed' | 'retry_not_budgeted';
  reasons: string[];
};

type ResponsibilityCompletionBatchResult = {
  batchIndex: number;
  seedIds: string[];
  attempts: number;
  records: ResponsibilityReadOutput['responsibilities'];
  outcomes: ResponsibilityCompletionTerminalOutcome[];
  failure: string | null;
};

export function finalizeLateResponsibilityCompletion(args: {
  seedIds: readonly string[];
  results: readonly ResponsibilityCompletionBatchResult[];
  unscheduledIds: readonly string[];
  batchOffset: number;
}) {
  const seedIds = new Set(args.seedIds);
  const records = new Map<string, ResponsibilityReadOutput['responsibilities'][number]>();
  for (const result of args.results) {
    for (const record of result.records) {
      if (!seedIds.has(record.responsibilityId) || records.has(record.responsibilityId)) continue;
      records.set(record.responsibilityId, record);
    }
  }
  const outcomes = [
    ...args.results.flatMap((result) => result.outcomes.map((outcome) => ({
      ...outcome,
      batchIndex: result.batchIndex + args.batchOffset,
      attempts: result.attempts,
      failure: result.failure,
    }))),
    ...args.unscheduledIds.map((responsibilityId) => ({
      responsibilityId,
      status: 'budget_exhausted' as const,
      reasons: ['late_completion_not_scheduled_within_frozen_budget'],
      batchIndex: null,
      attempts: 0,
      failure: 'budget_exhausted',
    })),
  ];
  const acceptedIds = new Set(records.keys());
  const incompleteIds = args.seedIds.filter((id) => !acceptedIds.has(id));
  return {
    records: [...records.values()],
    outcomes,
    incompleteIds,
    degraded: incompleteIds.length > 0 || args.unscheduledIds.length > 0,
  };
}

export async function runLateResponsibilityCompletion(args: {
  seeds: readonly ResponsibilityInventorySeed[];
  handledIds: ReadonlySet<string>;
  completeIds: ReadonlySet<string>;
  pack: Omit<Parameters<typeof packResponsibilityCompletions>[0], 'seeds'>;
  budget: SourceReaderBudget;
  concurrency: number;
  batchOffset: number;
  runBatch: (
    batch: ResponsibilityCompletionBatch,
    attempt: 1 | 2,
  ) => Promise<ResponsibilityCompletionOutput>;
  validateCompletion: (
    record: ResponsibilityReadOutput['responsibilities'][number],
  ) => { complete: boolean; reasons: readonly string[] };
}) {
  const residualSeeds = lateResidualResponsibilitySeeds({
    seeds: args.seeds,
    handledIds: args.handledIds,
    completeIds: args.completeIds,
  });
  const pack = packResponsibilityCompletions({ seeds: residualSeeds, ...args.pack });
  // F3. The late path is the ONLY late path, and this is its one correction seam: every
  // candidate the existing dispatch returns is passed through the pure source-bound
  // corrector before the existing strict-improvement selection and the caller's existing
  // `validateResponsibilityRead`. No new seed queue, completion stage, dispatch, budget
  // reservation, model call or retry is introduced — a rejected correction simply leaves
  // the candidate exactly as it arrived, and the existing incomplete outcome stands.
  // F4: the late path no longer defines its own correction closure. It uses the ONE shared
  // seam, so both candidate stages correct, refuse and audit identically.
  const seam = responsibilityFinalRecordCorrectionSeam({ seeds: residualSeeds, stage: 'late' });
  const results = await executeResponsibilityCompletionBatches({
    budget: args.budget,
    batches: pack.batches,
    concurrency: args.concurrency,
    baselines: residualSeeds.map((seed) => ({
      responsibilityId: seed.inventorySeedId,
      complete: false,
    })),
    runBatch: args.runBatch,
    validateCompletion: args.validateCompletion,
    correctRecord: seam.correctRecord,
  });
  return {
    residualSeeds,
    pack,
    results,
    corrections: seam.corrections,
    seam,
    final: finalizeLateResponsibilityCompletion({
      seedIds: residualSeeds.map((seed) => seed.inventorySeedId),
      results,
      unscheduledIds: pack.unscheduledIds,
      batchOffset: args.batchOffset,
    }),
  };
}

export async function executeResponsibilityCompletionBatches(args: {
  budget: SourceReaderBudget;
  batches: readonly ResponsibilityCompletionBatch[];
  concurrency: number;
  runBatch: (
    batch: ResponsibilityCompletionBatch,
    attempt: 1 | 2,
  ) => Promise<ResponsibilityCompletionOutput>;
  baselines: readonly ResponsibilityCompletionBaseline[];
  validateCompletion: (
    record: ResponsibilityReadOutput['responsibilities'][number],
  ) => { complete: boolean; reasons: readonly string[] };
  isRetryableFailure?: (error: unknown) => boolean;
  // F3 seam. A pure, source-bound rewrite applied to each returned candidate BEFORE
  // strict-improvement selection and before the caller's existing validation, so the
  // record that is judged is the record that is kept. It performs no dispatch, model
  // call, budget reservation or retry. Callers that do not supply it are unchanged.
  correctRecord?: (
    record: ResponsibilityReadOutput['responsibilities'][number],
  ) => ResponsibilityReadOutput['responsibilities'][number];
}): Promise<ResponsibilityCompletionBatchResult[]> {
  reserveResponsibilityCompletionBatches({ budget: args.budget, batches: args.batches });
  return mapWithConcurrency({
    inputs: args.batches,
    concurrency: args.concurrency,
    run: async (batch) => {
      let firstFailure: string | null = null;
      for (const attempt of [1, 2] as const) {
        if (attempt === 2) {
          try {
            args.budget.reserveRead({
              estimatedInputTokens: batch.estimatedInputTokens,
              estimatedCostUsd: batch.estimatedCostUsd,
              label: `responsibility completion batch ${batch.batchIndex + 1} retry`,
            });
          } catch (error) {
            return {
              batchIndex: batch.batchIndex,
              seedIds: batch.seedIds,
              attempts: 1,
              records: [],
              outcomes: batch.seedIds.map((responsibilityId) => ({
                responsibilityId,
                status: 'retry_not_budgeted' as const,
                reasons: [firstFailure ?? 'completion_failed', error instanceof Error ? error.message : String(error)],
              })),
              failure: `${firstFailure ?? 'completion_failed'}; retry_not_budgeted: ${error instanceof Error ? error.message : String(error)}`,
            };
          }
        }
        try {
          const output = await args.runBatch(batch, attempt);
          const canonical = canonicalizeResponsibilityCompletionBatch({ batch, output });
          const corrected = args.correctRecord
            ? canonical.map((record) => args.correctRecord!(record))
            : canonical;
          const selection = selectStrictResponsibilityCompletionImprovements({
            records: corrected,
            baselines: args.baselines.filter((item) => batch.seedIds.includes(item.responsibilityId)),
            validate: args.validateCompletion,
          });
          const requestedIds = new Set(batch.seedIds);
          const selectedIds = new Set<string>();
          const rejectedIds = new Set<string>();
          for (const record of selection.acceptedRecords) {
            if (!requestedIds.has(record.responsibilityId) || selectedIds.has(record.responsibilityId)) {
              throw new Error(`Responsibility completion strict-improvement selection returned an invalid seed: ${record.responsibilityId}`);
            }
            selectedIds.add(record.responsibilityId);
          }
          for (const rejection of selection.rejected) {
            if (
              !requestedIds.has(rejection.responsibilityId) ||
              selectedIds.has(rejection.responsibilityId) ||
              rejectedIds.has(rejection.responsibilityId)
            ) {
              throw new Error(`Responsibility completion rejection returned an invalid seed: ${rejection.responsibilityId}`);
            }
            rejectedIds.add(rejection.responsibilityId);
          }
          if (selectedIds.size + rejectedIds.size !== batch.seedIds.length) {
            throw new Error('Responsibility completion selection did not account for every seed.');
          }
          return {
            batchIndex: batch.batchIndex,
            seedIds: batch.seedIds,
            attempts: attempt,
            records: selection.acceptedRecords,
            outcomes: batch.seedIds.map((responsibilityId) => {
              const rejection = selection.rejected.find((item) => item.responsibilityId === responsibilityId);
              return rejection
                ? { responsibilityId, status: 'validation_rejected' as const, reasons: rejection.reasons }
                : { responsibilityId, status: 'accepted' as const, reasons: [] };
            }),
            failure: null,
          };
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          if (attempt === 1) {
            firstFailure = message;
            const retryable = args.isRetryableFailure
              ? args.isRetryableFailure(error)
              : isRetryableResponsibilityCompletionFailure(error);
            if (!retryable) return {
              batchIndex: batch.batchIndex,
              seedIds: batch.seedIds,
              attempts: 1,
              records: [],
              outcomes: batch.seedIds.map((responsibilityId) => ({
                responsibilityId,
                status: 'provider_failed' as const,
                reasons: [message],
              })),
              failure: message,
            };
          }
          else return {
            batchIndex: batch.batchIndex,
            seedIds: batch.seedIds,
            attempts: 2,
            records: [],
            outcomes: batch.seedIds.map((responsibilityId) => ({
              responsibilityId,
              status: 'provider_failed' as const,
              reasons: [firstFailure ?? 'completion_failed', message],
            })),
            failure: `${firstFailure}; retry_failed: ${message}`,
          };
        }
      }
      throw new Error('Unreachable responsibility completion attempt state.');
    },
  });
}

export type WorkflowQuoteRepairMetadata = {
  repairAttempts: number;
  repairSkipped: string | null;
  rootDroppedBefore: number;
  cascadeDroppedBefore: number;
  rootDroppedAfter: number;
  cascadeDroppedAfter: number;
};

export function eligibleWorkflowQuoteRepairs(
  validation: WorkflowMapValidationResult,
): WorkflowMapRejectionDiagnostic[] {
  return validation.diagnostics.filter(
    (item) =>
      item.failureOrigin === 'root' &&
      (item.elementType === 'node' || item.elementType === 'edge') &&
      (item.failureClass === 'quote_mismatch' || item.failureClass === 'quote_ambiguous') &&
      item.citedChunkId !== null,
  );
}

export function patchWorkflowQuoteRepairs(args: {
  original: WorkflowReadOutput;
  requested: readonly WorkflowMapRejectionDiagnostic[];
  response: WorkflowQuoteRepairOutput;
}): { ok: true; output: WorkflowReadOutput } | { ok: false; reason: string } {
  const requested = new Map(
    args.requested.map((item) => [`${item.elementType}:${item.elementId}`, item]),
  );
  const seen = new Set<string>();
  const replacements = new Map<string, string>();
  for (const repair of args.response.repairs) {
    const key = `${repair.elementType}:${repair.elementId}`;
    if (seen.has(key)) return { ok: false, reason: 'duplicate_repair' };
    seen.add(key);
    const target = requested.get(key);
    if (!target) return { ok: false, reason: 'unknown_or_wrong_element_type' };
    if (target.citedChunkId !== repair.chunkId) return { ok: false, reason: 'chunk_move' };
    replacements.set(key, repair.evidenceQuote);
  }
  if (seen.size !== requested.size) return { ok: false, reason: 'missing_repair' };
  return {
    ok: true,
    output: {
      ...args.original,
      nodes: args.original.nodes.map((node) => ({
        ...node,
        evidenceQuote: replacements.get(`node:${node.nodeId}`) ?? node.evidenceQuote,
      })),
      edges: args.original.edges.map((edge) => ({
        ...edge,
        evidenceQuote: replacements.get(`edge:${edge.edgeId}`) ?? edge.evidenceQuote,
      })),
      lanes: args.original.lanes.map((lane) => ({ ...lane })),
      paths: args.original.paths.map((path) => ({
        ...path,
        nodeIdsOrdered: [...path.nodeIdsOrdered],
      })),
    },
  };
}

export function chooseWorkflowQuoteRepair(
  original: WorkflowMapValidationResult,
  repaired: WorkflowMapValidationResult,
): WorkflowMapValidationResult {
  return repaired.rootDroppedCount < original.rootDroppedCount ? repaired : original;
}

export function selectWorkflowQuoteRepairCandidate(
  candidates: readonly WorkflowMapValidationResult[],
): number | null {
  let selected: number | null = null;
  for (let index = 0; index < candidates.length; index += 1) {
    const candidate = candidates[index]!;
    const candidateEligibleRootCount = eligibleWorkflowQuoteRepairs(candidate).length;
    if (candidateEligibleRootCount === 0) continue;
    if (selected === null) {
      selected = index;
      continue;
    }
    const current = candidates[selected]!;
    const currentEligibleRootCount = eligibleWorkflowQuoteRepairs(current).length;
    if (
      candidateEligibleRootCount > currentEligibleRootCount ||
      (candidateEligibleRootCount === currentEligibleRootCount &&
        candidate.cascadeDroppedCount > current.cascadeDroppedCount) ||
      (candidateEligibleRootCount === currentEligibleRootCount &&
        candidate.cascadeDroppedCount === current.cascadeDroppedCount &&
        candidate.rootDroppedCount > current.rootDroppedCount) ||
      (candidateEligibleRootCount === currentEligibleRootCount &&
        candidate.cascadeDroppedCount === current.cascadeDroppedCount &&
        candidate.rootDroppedCount === current.rootDroppedCount &&
        candidate.droppedCount > current.droppedCount)
    ) {
      selected = index;
    }
  }
  return selected;
}

export type SourceWorkflowReadResult = {
  documentId: string;
  status:
    | 'validated'
    | 'degraded'
    | 'failed'
    | 'skipped_existing'
    | 'skipped_no_chunks'
    | 'skipped_not_found';
  mapId?: string;
  existingMapStatus?: 'validated' | 'degraded';
  mapKind?: 'workflow' | 'reference';
  documentShape?: SourceStructureShape;
  droppedCount?: number;
  keptCount?: number;
  segmentCount?: number;
  elementCount?: number;
  relationCount?: number;
  laneCount?: number;
  pathCount?: number;
};

function sha256(text: string): string {
  return createHash('sha256').update(text, 'utf8').digest('hex');
}

function buildContextPackInsert(plan: OraclePromptPlan) {
  return {
    taskType: plan.taskType,
    routeId: plan.routeId,
    promptVersion: plan.promptVersion,
    schemaVersion: plan.schemaVersion ?? null,
    stablePrefixHash: plan.metadata.stablePrefixHash,
    semiStableContextHash: plan.metadata.semiStableContextHash ?? null,
    retrievedContextHash: plan.metadata.retrievedContextHash ?? null,
    dynamicInputHash: plan.metadata.dynamicInputHash,
    toolSchemaHash: plan.metadata.toolSchemaHash ?? null,
    outputSchemaHash: plan.metadata.outputSchemaHash ?? null,
    blocksJson: plan.blocks.map((b) => ({
      id: b.id,
      label: b.label,
      kind: b.kind,
      hash: b.hash,
      tokenEstimate: b.tokenEstimate ?? null,
      cacheEligible: b.cacheEligible,
      reasonIncluded: b.reasonIncluded,
    })),
    includedDocumentChunkIds: plan.metadata.includedDocumentChunkIds ?? null,
  };
}

function buildDocumentCorpus(chunks: ChunkRow[]): string {
  return chunks
    .map((chunk) => {
      const page = chunk.pageNumber ? ` page=${chunk.pageNumber}` : '';
      return `--- Document Chunk ID: ${chunk.id} index=${chunk.chunkIndex}${page} ---\n${chunk.rawText}`;
    })
    .join('\n\n');
}

function sourceHashForDocument(documentId: string, chunks: ChunkRow[]): string {
  return sha256(
    JSON.stringify({
      documentId,
      readerPipelineVersion: SOURCE_READER_PIPELINE_VERSION,
      segmentationPromptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      workflowPromptVersion: WORKFLOW_READ_PROMPT_VERSION,
      chunks: chunks.map((chunk) => [chunk.id, chunk.chunkIndex, chunk.contentHash, chunk.rawText]),
    }),
  );
}

async function readNumberSetting(db: OracleDb, key: string, fallback: number): Promise<number> {
  const [row] = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, key))
    .limit(1);
  const value = row?.value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (typeof value === 'string' && Number.isFinite(Number(value))) return Number(value);
  return fallback;
}

async function readResponsibilityPostPassSetting(
  db: OracleDb,
  key: string,
  fallback: number,
): Promise<number> {
  const [row] = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, key))
    .limit(1);
  if (!row) return fallback;
  const parsed =
    typeof row.value === 'number'
      ? row.value
      : typeof row.value === 'string'
        ? Number(row.value)
        : Number.NaN;
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error(
      `Invalid responsibility post-pass setting ${key}: expected a non-negative integer`,
    );
  }
  return parsed;
}

async function buildReferentPack(db: OracleDb): Promise<string> {
  const [entityRows, processRows] = await Promise.all([
    db
      .select({
        canonicalValue: entities.canonicalValue,
        displayLabel: entities.displayLabel,
        entityType: entities.entityType,
        aliases: entities.aliases,
      })
      .from(entities)
      .orderBy(entities.entityType, entities.canonicalValue)
      .limit(300),
    db
      .select({ name: businessProcesses.name, summary: businessProcesses.summary })
      .from(businessProcesses)
      .orderBy(desc(businessProcesses.updatedAt))
      .limit(80),
  ]);

  const lines = [
    'REFERENT PACK (names and acronyms only; do not copy existing structure):',
    '',
    'Known entities:',
  ];
  for (const entity of entityRows) {
    const aliases =
      Array.isArray(entity.aliases) && entity.aliases.length > 0
        ? ` aliases=${entity.aliases.join(', ')}`
        : '';
    lines.push(`- ${entity.entityType}: ${entity.displayLabel ?? entity.canonicalValue}${aliases}`);
  }
  if (processRows.length > 0) {
    lines.push('', 'Existing process names only:');
    for (const process of processRows) {
      lines.push(`- ${process.name}${process.summary ? `: ${process.summary.slice(0, 180)}` : ''}`);
    }
  }
  return lines.join('\n');
}

function chunkWindows(chunks: ChunkRow[], maxEstimatedInputTokens: number): ChunkRow[][] {
  const maxChars = Math.max(8_000, maxEstimatedInputTokens * 4);
  const windows: ChunkRow[][] = [];
  let current: ChunkRow[] = [];
  for (const chunk of chunks) {
    const next = [...current, chunk];
    if (current.length > 0 && buildDocumentCorpus(next).length > maxChars) {
      windows.push(current);
      current = [chunk];
    } else {
      current = next;
    }
  }
  if (current.length > 0) windows.push(current);
  return windows;
}

function isReusableWorkflowMapStatus(
  status: string | null | undefined,
): status is ReusableWorkflowMapStatus {
  return status === 'validated' || status === 'degraded';
}

function prefixWindowIds(
  output: WorkflowReadOutput,
  windowIndex: number,
  totalWindows: number,
  priorNodeIds: ReadonlySet<string>,
): WorkflowReadOutput {
  if (totalWindows <= 1) return output;
  const prefix = `w${windowIndex + 1}_`;
  const remap = new Map<string, string>();
  for (const node of output.nodes) {
    remap.set(node.nodeId, priorNodeIds.has(node.nodeId) ? node.nodeId : `${prefix}${node.nodeId}`);
  }
  const mapNodeRef = (nodeId: string) => {
    const mapped = remap.get(nodeId);
    if (mapped) return mapped;
    if (priorNodeIds.has(nodeId)) return nodeId;
    return `${prefix}${nodeId}`;
  };
  return {
    ...output,
    nodes: output.nodes.map((node) => ({ ...node, nodeId: mapNodeRef(node.nodeId) })),
    edges: output.edges.map((edge) => ({
      ...edge,
      edgeId: `${prefix}${edge.edgeId}`,
      fromNodeId: mapNodeRef(edge.fromNodeId),
      toNodeId: mapNodeRef(edge.toNodeId),
    })),
    lanes: output.lanes.map((lane) => ({ ...lane, laneId: `${prefix}${lane.laneId}` })),
    paths: output.paths.map((path) => ({
      ...path,
      pathId: `${prefix}${path.pathId}`,
      nodeIdsOrdered: path.nodeIdsOrdered.map(mapNodeRef),
    })),
  };
}

function mergeWorkflowOutputs(outputs: WorkflowReadOutput[]): WorkflowReadOutput {
  if (outputs.length === 1) return outputs[0]!;
  const mapKind = outputs.some((output) => output.mapKind === 'workflow')
    ? 'workflow'
    : 'reference';
  return {
    mapKind,
    summary: outputs.map((output, index) => `Window ${index + 1}: ${output.summary}`).join('\n'),
    nodes: outputs.flatMap((output) => output.nodes),
    edges: outputs.flatMap((output) => output.edges),
    lanes: outputs.flatMap((output) => output.lanes),
    paths: outputs.flatMap((output) => output.paths),
  };
}

function contiguousRuns(
  chunkIds: string[],
  chunkIndexById: ReadonlyMap<string, number>,
): string[][] {
  const sorted = [...chunkIds].sort(
    (a, b) =>
      (chunkIndexById.get(a) ?? Number.MAX_SAFE_INTEGER) -
      (chunkIndexById.get(b) ?? Number.MAX_SAFE_INTEGER),
  );
  const runs: string[][] = [];
  for (const chunkId of sorted) {
    const current = runs.at(-1);
    if (!current) {
      runs.push([chunkId]);
      continue;
    }
    const previousIndex = chunkIndexById.get(current.at(-1)!);
    const nextIndex = chunkIndexById.get(chunkId);
    if (previousIndex !== undefined && nextIndex === previousIndex + 1) current.push(chunkId);
    else runs.push([chunkId]);
  }
  return runs;
}

function validateSegmentation(
  output: SourceSegmentationOutput,
  chunks: ChunkRow[],
): {
  status: 'validated' | 'degraded';
  documentShape: SourceStructureShape;
  summary: string;
  segments: SourceStructureSegment[];
  integrityRepairCount: number;
  validationJson: Record<string, unknown>;
} {
  const chunkIndexById = new Map(chunks.map((chunk) => [chunk.id, chunk.chunkIndex]));
  const covered = new Set<string>();
  const usedSegmentIds = new Set<string>();
  const repairs: Array<Record<string, unknown>> = [];
  let integrityRepairCount = 0;
  const segments: SourceStructureSegment[] = [];

  const uniqueSegmentId = (requested: string) => {
    let candidate = requested;
    let suffix = 2;
    while (usedSegmentIds.has(candidate)) candidate = `${requested}_${suffix++}`;
    usedSegmentIds.add(candidate);
    return candidate;
  };

  for (const proposed of output.segments) {
    const accepted: string[] = [];
    const seenWithinSegment = new Set<string>();
    for (const chunkId of proposed.chunkIds) {
      if (!chunkIndexById.has(chunkId)) {
        repairs.push({ segmentId: proposed.segmentId, chunkId, reason: 'unknown_chunk_id' });
        integrityRepairCount += 1;
        continue;
      }
      if (seenWithinSegment.has(chunkId)) {
        repairs.push({
          segmentId: proposed.segmentId,
          chunkId,
          reason: 'duplicate_chunk_within_segment',
        });
        integrityRepairCount += 1;
        continue;
      }
      seenWithinSegment.add(chunkId);
      covered.add(chunkId);
      accepted.push(chunkId);
    }
    const runs = contiguousRuns(accepted, chunkIndexById);
    if (runs.length > 1) {
      repairs.push({
        segmentId: proposed.segmentId,
        reason: 'non_contiguous_segment_split',
        runCount: runs.length,
      });
    }
    for (let runIndex = 0; runIndex < runs.length; runIndex++) {
      const run = runs[runIndex]!;
      segments.push({
        segmentId: uniqueSegmentId(
          runIndex === 0 ? proposed.segmentId : `${proposed.segmentId}_${runIndex + 1}`,
        ),
        shape: proposed.shape,
        title: runIndex === 0 ? proposed.title : `${proposed.title} (continued)`,
        summary: proposed.summary ?? null,
        chunkIds: run,
      });
    }
    if (accepted.length === 0) {
      repairs.push({ segmentId: proposed.segmentId, reason: 'empty_segment_dropped' });
    }
  }

  const missingIds = chunks.filter((chunk) => !covered.has(chunk.id)).map((chunk) => chunk.id);
  const missingRuns = contiguousRuns(missingIds, chunkIndexById);
  for (let index = 0; index < missingRuns.length; index++) {
    const segmentId = uniqueSegmentId(`unclassified_${index + 1}`);
    segments.push({
      segmentId,
      shape: 'narrative',
      title: 'Unclassified source material',
      summary: 'Chunks omitted by the model and retained as narrative fallback material.',
      chunkIds: missingRuns[index]!,
    });
    repairs.push({ segmentId, reason: 'missing_chunks_recovered', chunkIds: missingRuns[index] });
    integrityRepairCount += 1;
  }

  segments.sort((a, b) => {
    const aIndex = chunkIndexById.get(a.chunkIds[0]!) ?? Number.MAX_SAFE_INTEGER;
    const bIndex = chunkIndexById.get(b.chunkIds[0]!) ?? Number.MAX_SAFE_INTEGER;
    return aIndex - bIndex;
  });

  const shapeCounts = new Map<SourceStructureShape, number>();
  for (const segment of segments) {
    shapeCounts.set(segment.shape, (shapeCounts.get(segment.shape) ?? 0) + segment.chunkIds.length);
  }
  const documentShape = output.documentShape;

  return {
    status: integrityRepairCount === 0 ? 'validated' : 'degraded',
    documentShape,
    summary: output.summary,
    segments,
    integrityRepairCount,
    validationJson: {
      promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      proposedDocumentShape: output.documentShape,
      documentShape,
      segmentChunkAssignmentsByShape: Object.fromEntries(shapeCounts),
      suppliedChunkCount: chunks.length,
      coveredChunkCount: covered.size + missingIds.length,
      segmentChunkAssignmentCount: segments.reduce(
        (sum, segment) => sum + segment.chunkIds.length,
        0,
      ),
      segmentCount: segments.length,
      integrityRepairCount,
      repairs,
    },
  };
}

function nodeSystemsToScalar(systems: string[] | null | undefined): string | null {
  if (!systems || systems.length === 0) return null;
  return (
    systems
      .map((system) => system.trim())
      .filter(Boolean)
      .join('; ') || null
  );
}

function workflowToProcessStructureMap(args: {
  output: WorkflowReadOutput;
  chunks: ChunkRow[];
  title: string;
  segment?: SourceStructureSegment;
  documentShape?: SourceStructureShape;
  prefixIds?: boolean;
}): SourceStructureMap {
  const { output, chunks, title } = args;
  const segment =
    args.segment ??
    ({
      segmentId: 'process',
      shape: 'process',
      title,
      summary: output.summary,
      chunkIds: chunks.map((chunk) => chunk.id),
    } satisfies SourceStructureSegment);
  const prefix = args.prefixIds ? `${segment.segmentId}_` : '';
  const mapElementId = (id: string) => `${prefix}${id}`;
  const elements: SourceStructureElement[] = output.nodes.map((node) => ({
    elementId: mapElementId(node.nodeId),
    segmentId: segment.segmentId,
    shape: 'process',
    elementKind: node.nodeType,
    label: node.label,
    lane: node.lane ?? null,
    ownerName: node.ownerName ?? null,
    systems: nodeSystemsToScalar(node.systems),
    evidenceQuote: node.evidenceQuote,
    chunkId: node.chunkId,
  }));
  const relations: SourceStructureRelation[] = output.edges.map((edge) => ({
    relationId: mapElementId(edge.edgeId),
    segmentId: segment.segmentId,
    fromElementId: mapElementId(edge.fromNodeId),
    toElementId: mapElementId(edge.toNodeId),
    shape: 'process',
    relationKind: edge.edgeType,
    condition: edge.condition ?? null,
    evidenceQuote: edge.evidenceQuote,
    chunkId: edge.chunkId,
  }));

  return {
    documentShape: args.documentShape ?? 'process',
    summary: output.summary,
    segments: [segment],
    elements,
    relations,
    lanes: output.lanes.map((lane) => ({ ...lane, laneId: mapElementId(lane.laneId) })),
    paths: output.paths.map((path) => ({
      ...path,
      pathId: mapElementId(path.pathId),
      nodeIdsOrdered: path.nodeIdsOrdered.map(mapElementId),
    })),
  };
}

async function createPendingMap(args: {
  db: OracleDb;
  documentId: string;
  sourceContentHash: string;
  force: boolean;
}): Promise<{
  mapId: string;
  skippedExisting: boolean;
  existingStatus?: ReusableWorkflowMapStatus;
}> {
  const { db, documentId, sourceContentHash, force } = args;
  if (!force) {
    const [existing] = await db
      .select({ id: sourceWorkflowMaps.id, status: sourceWorkflowMaps.status })
      .from(sourceWorkflowMaps)
      .where(
        and(
          eq(sourceWorkflowMaps.sourceType, 'document'),
          eq(sourceWorkflowMaps.documentId, documentId),
          eq(sourceWorkflowMaps.sourceContentHash, sourceContentHash),
          sql`${sourceWorkflowMaps.status} IN ('validated', 'degraded')`,
        ),
      )
      .orderBy(desc(sourceWorkflowMaps.createdAt))
      .limit(1);
    if (existing) {
      if (!isReusableWorkflowMapStatus(existing.status)) {
        throw new Error(`[source-workflow-read] unexpected reusable map status ${existing.status}`);
      }
      return {
        mapId: existing.id,
        skippedExisting: true,
        existingStatus: existing.status,
      };
    }
  }

  return db.transaction(async (tx) => {
    const oldRows = await tx
      .select({ id: sourceWorkflowMaps.id })
      .from(sourceWorkflowMaps)
      .where(
        and(
          eq(sourceWorkflowMaps.sourceType, 'document'),
          eq(sourceWorkflowMaps.documentId, documentId),
          ne(sourceWorkflowMaps.status, 'superseded'),
        ),
      );
    const oldIds = oldRows.map((row) => row.id);
    if (oldIds.length > 0) {
      await tx
        .update(sourceWorkflowMaps)
        .set({ status: 'superseded', updatedAt: new Date() })
        .where(inArray(sourceWorkflowMaps.id, oldIds));
    }

    const [inserted] = await tx
      .insert(sourceWorkflowMaps)
      .values({
        sourceType: 'document',
        documentId,
        sourceContentHash,
        status: 'pending',
        documentShape: 'process',
        mapKind: 'workflow',
        validationJson: {
          pipelineVersion: SOURCE_READER_PIPELINE_VERSION,
          segmentationPromptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
          workflowPromptVersion: WORKFLOW_READ_PROMPT_VERSION,
          status: 'pending',
        },
      })
      .returning({ id: sourceWorkflowMaps.id });
    if (!inserted)
      throw new Error('[source-workflow-read] failed to insert pending source_workflow_maps row');

    if (oldIds.length > 0) {
      await tx
        .update(sourceWorkflowMaps)
        .set({ supersededByMapId: inserted.id, updatedAt: new Date() })
        .where(inArray(sourceWorkflowMaps.id, oldIds));
    }

    return { mapId: inserted.id, skippedExisting: false };
  });
}

async function runSegmentationModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  chunks: ChunkRow[];
  mapId: string;
  repairFeedback?: string;
  budget: SourceReaderBudget;
}): Promise<{ output: SourceSegmentationOutput; modelRunId: string; contextPackId: string }> {
  const { db, client, doc, chunks, mapId, repairFeedback, budget } = args;
  const resolved = await resolveRouteCandidates(db, 'workflow_read');
  for (const skipped of resolved.skipped) {
    console.warn('[source-workflow-read] skipped segmentation route candidate', skipped);
  }
  const routeCandidates = resolved.candidates;
  const route = routeCandidates[0]!.route;
  const chunkIds = chunks.map((chunk) => chunk.id);
  const blocks = [
    makeBlock({
      id: 'source-segmentation-system',
      label: 'Source segmentation system prompt',
      kind: 'stable_system',
      content: SOURCE_SEGMENTATION_SYSTEM_PROMPT,
      reasonIncluded: `source segmentation prompt ${SOURCE_SEGMENTATION_PROMPT_VERSION}`,
    }),
    makeBlock({
      id: 'document-metadata',
      label: 'Document metadata',
      kind: 'semi_stable_domain_context',
      content: [
        `Document name: ${doc.fileName}`,
        `File type: ${doc.fileType}`,
        doc.context ? `Uploader context:\n${doc.context}` : null,
        `Source structure map row: ${mapId}`,
      ]
        .filter(Boolean)
        .join('\n\n'),
      reasonIncluded: 'document-level context for source segmentation',
    }),
    makeBlock({
      id: 'document-chunks',
      label: 'Document chunks',
      kind: 'retrieved_context',
      content: buildDocumentCorpus(chunks),
      reasonIncluded: 'complete ordered source; every chunk must be assigned exactly once',
    }),
    makeBlock({
      id: 'source-segmentation-request',
      label: 'Source segmentation request',
      kind: 'dynamic_input',
      content:
        'Segment these chunks into the fewest coherent shape-focused passages. Cover every supplied chunk at least once and preserve source order. A genuinely composite chunk may appear in multiple differently shaped segments.' +
        (repairFeedback
          ? `\n\nREPAIR REQUIRED: The prior output failed deterministic validation. Return a complete corrected segmentation, copying chunk IDs exactly from this valid list:\n${chunks.map((chunk) => chunk.id).join('\n')}\n\nValidator feedback:\n${repairFeedback}`
          : ''),
      reasonIncluded: repairFeedback
        ? 'bounded deterministic segmentation repair request'
        : 'current source-segmentation request',
    }),
  ];
  budget.reserveRead({
    estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
    label: repairFeedback ? 'source segmentation repair' : 'source segmentation',
  });
  const plan = client.compile({
    taskType: 'source_segmentation',
    routeId: route.routeId,
    promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
    blocks,
    observability: { includedDocumentChunkIds: chunkIds },
  });
  const [contextPack] = await db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack)
    throw new Error('[source-workflow-read] failed to insert segmentation context pack');

  const started = Date.now();
  const result = await client
    .runObject<SourceSegmentationOutput>({
      taskType: 'source_segmentation',
      routeId: route.routeId,
      promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      blocks,
      schema: SourceSegmentationSchema,
      observability: { includedDocumentChunkIds: chunkIds },
      providerOptions: { maxOutputTokens: 12_000 },
      routeCandidates,
    })
    .catch(async (err) => {
      await logAllCandidatesFailedAttempts({
        db,
        error: err,
        taskType: 'source-segmentation',
        slot: 'workflow_read',
        contextPackId: contextPack.id,
      }).catch((logErr) =>
        console.error(
          '[source-workflow-read] failed to record segmentation model attempts',
          logErr,
        ),
      );
      throw err;
    });

  const actualRouteId = result.routeId ?? route.routeId;
  const actualProvider = result.provider ?? route.provider;
  const actualModelId = result.modelId ?? route.modelId;
  const [modelRun] = await db
    .insert(modelRuns)
    .values({
      taskType: 'source-segmentation',
      model: actualModelId,
      provider: actualProvider,
      promptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[source-workflow-read] failed to insert segmentation model run');

  await db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    routeId: actualRouteId,
    inputTokens: result.usage.inputTokens ?? null,
    cachedInputTokens: result.usage.cachedInputTokens ?? null,
    cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
    outputTokens: result.usage.outputTokens ?? null,
    reasoningTokens: result.usage.reasoningTokens ?? null,
    providerRequestId: result.usage.providerRequestId ?? null,
    rawUsageJson: result.usage.rawUsageJson ?? null,
  });
  await logModelRunAttempts({
    db,
    metadata: result,
    taskType: 'source-segmentation',
    slot: 'workflow_read',
    contextPackId: contextPack.id,
    modelRunId: modelRun.id,
  });
  await db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));

  if (!result.validation.ok) {
    throw new Error(
      '[source-workflow-read] segmentation output failed Zod schema validation: ' +
        result.validation.error.message,
    );
  }
  return { output: result.object, modelRunId: modelRun.id, contextPackId: contextPack.id };
}

async function runWorkflowReadModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  chunks: ChunkRow[];
  referentPack: string;
  triggerRunId: string;
  mapId: string;
  force: boolean;
  segment?: SourceStructureSegment;
  budget: SourceReaderBudget;
}): Promise<{ output: WorkflowReadOutput; modelRunIds: string[]; contextPackIds: string[] }> {
  const { db, client, doc, chunks, referentPack, mapId, segment, budget } = args;
  const maxEstimatedTokens = await readNumberSetting(
    db,
    'workflow_read_max_estimated_input_tokens',
    150_000,
  );
  const windows =
    estimateTokens(buildDocumentCorpus(chunks)) > maxEstimatedTokens
      ? chunkWindows(chunks, maxEstimatedTokens)
      : [chunks];
  const resolved = await resolveRouteCandidates(db, 'workflow_read');
  for (const skipped of resolved.skipped) {
    console.warn('[source-workflow-read] skipped workflow_read route candidate', skipped);
  }
  const routeCandidates = resolved.candidates;
  const route = routeCandidates[0]!.route;
  const outputs: WorkflowReadOutput[] = [];
  const modelRunIds: string[] = [];
  const contextPackIds: string[] = [];
  const carriedRegistry: string[] = [];
  const priorNodeIds = new Set<string>();

  for (let windowIndex = 0; windowIndex < windows.length; windowIndex++) {
    const windowChunks = windows[windowIndex]!;
    const chunkIds = windowChunks.map((chunk) => chunk.id);
    const blocks = [
      makeBlock({
        id: 'workflow-read-system',
        label: 'Workflow read system prompt',
        kind: 'stable_system',
        content: WORKFLOW_READ_SYSTEM_PROMPT,
        reasonIncluded: `workflow read prompt v${WORKFLOW_READ_PROMPT_VERSION}`,
      }),
      makeBlock({
        id: 'document-metadata',
        label: 'Document metadata',
        kind: 'semi_stable_domain_context',
        content: [
          `Document name: ${doc.fileName}`,
          `File type: ${doc.fileType}`,
          doc.context ? `Uploader context:\n${doc.context}` : null,
          `Source workflow map row: ${mapId}`,
          segment
            ? `Process segment: ${segment.segmentId} | ${segment.title}${segment.summary ? ` | ${segment.summary}` : ''}`
            : null,
        ]
          .filter(Boolean)
          .join('\n\n'),
        reasonIncluded: 'document-level context for source workflow read',
      }),
      makeBlock({
        id: 'referent-pack',
        label: 'Referent pack',
        kind: 'semi_stable_domain_context',
        content: referentPack,
        reasonIncluded: 'known names and acronyms only; existing process graphs withheld by design',
      }),
      ...(carriedRegistry.length > 0
        ? [
            makeBlock({
              id: 'carried-node-registry',
              label: 'Prior window node labels',
              kind: 'semi_stable_domain_context' as const,
              content: carriedRegistry.join('\n'),
              reasonIncluded: 'large-source windowing continuity without truncation',
            }),
          ]
        : []),
      makeBlock({
        id: 'document-chunks',
        label: 'Document chunks',
        kind: 'retrieved_context',
        content: buildDocumentCorpus(windowChunks),
        reasonIncluded: `window ${windowIndex + 1}/${windows.length}; map elements must cite these chunk IDs`,
      }),
      makeBlock({
        id: 'workflow-read-request',
        label: 'Workflow read request',
        kind: 'dynamic_input',
        content:
          'Read these process-segment chunks in order and produce the source workflow map. Capture only topology visible in this source, not what you expect from prior knowledge. Every node and edge must cite a verbatim quote from one chunk.',
        reasonIncluded: 'current workflow-read request',
      }),
    ];
    budget.reserveRead({
      estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
      label: `workflow read ${segment?.segmentId ?? 'full-source'} window ${windowIndex + 1}/${windows.length}`,
    });

    const plan = client.compile({
      taskType: 'source_workflow_read',
      routeId: route.routeId,
      promptVersion: WORKFLOW_READ_PROMPT_VERSION,
      blocks,
      observability: { includedDocumentChunkIds: chunkIds },
    });
    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values(buildContextPackInsert(plan))
      .returning({ id: oracleContextPacks.id });
    if (!contextPack)
      throw new Error('[source-workflow-read] failed to insert oracle_context_packs row');
    contextPackIds.push(contextPack.id);

    const started = Date.now();
    const result = await client
      .runObject<WorkflowReadOutput>({
        taskType: 'source_workflow_read',
        routeId: route.routeId,
        promptVersion: WORKFLOW_READ_PROMPT_VERSION,
        blocks,
        schema: WorkflowReadSchema,
        observability: { includedDocumentChunkIds: chunkIds },
        providerOptions: { maxOutputTokens: 32_000 },
        routeCandidates,
      })
      .catch(async (err) => {
        await logAllCandidatesFailedAttempts({
          db,
          error: err,
          taskType: 'source-workflow-read',
          slot: 'workflow_read',
          contextPackId: contextPack.id,
        }).catch((logErr) =>
          console.error('[source-workflow-read] failed to record failed model attempts', logErr),
        );
        throw err;
      });

    const actualRouteId = result.routeId ?? route.routeId;
    const actualProvider = result.provider ?? route.provider;
    const actualModelId = result.modelId ?? route.modelId;
    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'source-workflow-read',
        model: actualModelId,
        provider: actualProvider,
        promptVersion: WORKFLOW_READ_PROMPT_VERSION,
        inputHash: plan.metadata.stablePrefixHash,
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs: Date.now() - started,
        success: result.validation.ok,
        error: result.validation.ok ? null : result.validation.error.message,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('[source-workflow-read] failed to insert model_runs row');
    modelRunIds.push(modelRun.id);

    await db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
      contextPackId: contextPack.id,
      routeId: actualRouteId,
      inputTokens: result.usage.inputTokens ?? null,
      cachedInputTokens: result.usage.cachedInputTokens ?? null,
      cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      reasoningTokens: result.usage.reasoningTokens ?? null,
      providerRequestId: result.usage.providerRequestId ?? null,
      rawUsageJson: result.usage.rawUsageJson ?? null,
    });
    await logModelRunAttempts({
      db,
      metadata: result,
      taskType: 'source-workflow-read',
      slot: 'workflow_read',
      contextPackId: contextPack.id,
      modelRunId: modelRun.id,
    });
    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));

    if (!result.validation.ok) {
      throw new Error(
        '[source-workflow-read] model output failed Zod schema validation: ' +
          result.validation.error.message,
      );
    }
    const output = prefixWindowIds(result.object, windowIndex, windows.length, priorNodeIds);
    outputs.push(output);
    for (const node of output.nodes) priorNodeIds.add(node.nodeId);
    carriedRegistry.push(...output.nodes.map((node) => `- ${node.nodeId}: ${node.label}`));
  }

  return { output: mergeWorkflowOutputs(outputs), modelRunIds, contextPackIds };
}

export function responsibilityReadTaskType(quoteRepair: boolean): string {
  return quoteRepair
    ? 'source-responsibility-combined-repair'
    : 'source-responsibility-read';
}

export function responsibilityReadPromptVersion(quoteRepair: boolean): string {
  return quoteRepair
    ? RESPONSIBILITY_COMBINED_REPAIR_PROMPT_VERSION
    : RESPONSIBILITY_READ_PROMPT_VERSION;
}

export function buildResponsibilityRequestContent(args: {
  focusedSpans?: ForcedResponsibilitySpan[];
  quoteRepairRecords?: ResponsibilityReadOutput['responsibilities'];
  fieldRepairRequests?: Array<{
    responsibilityId: string;
    chunkId: string;
    evidenceQuote: string;
    sourceSpan: string;
    allowedFields: Array<'role' | 'action' | 'object' | 'trigger' | 'requiredSystem'>;
  }>;
  quoteRepairCandidates?: Array<{
    responsibilityId: string;
    failedQuote: string;
    immutableFields: Omit<
      ResponsibilityReadOutput['responsibilities'][number],
      'evidenceQuote'
    >;
    candidates: GroundedResponsibilityQuoteCandidate[];
  }>;
}): string {
  if (args.quoteRepairRecords?.length || args.fieldRepairRequests?.length) {
    return [
      'Combined responsibility field and quote repair.',
      'Field repairs may change only offered fields using exact text from the selected source span.',
      'Quote repairs must select only an offered candidateId.',
      'Never change IDs, chunks, or evidence in field mode. Never change fields in quote mode.',
      JSON.stringify({
        fieldRequests: args.fieldRepairRequests ?? [],
        quoteRequests: (args.quoteRepairCandidates ?? []).map((item) => ({
          responsibilityId: item.responsibilityId,
          failedQuote: item.failedQuote,
          candidates: item.candidates.map((candidate) => ({
            candidateId: `candidate_${candidate.candidateIndex}`,
            sourceText: candidate.sourceText,
          })),
        })),
      }),
    ].join('\n');
  }
  return [
    args.focusedSpans?.length
      ? [
          'Focused omission retry. Each JSON item is one isolated source span.',
          'Return exactly one record per item using its forcedResponsibilityId and chunkId.',
          'Copy evidenceQuote exactly. Use semanticSourceSpan only for owner/action/object fields.',
          'Never copy or quote semanticSourceSpan. Do not use facts outside that item.',
          JSON.stringify(args.focusedSpans.map((span) => ({
            forcedResponsibilityId: span.forcedResponsibilityId,
            chunkId: span.chunkId,
            spanIndex: span.spanIndex,
            sourceSpanSha256: span.sourceSpanSha256,
            semanticSourceSpan: span.sourceSpan,
            evidenceQuote: span.evidenceQuote,
            sourceStart: span.sourceStart,
            sourceEnd: span.sourceEnd,
          }))),
        ].join('\n')
      : 'Extract every distinct responsibility record from this segment.',
    'Use the exact source-owner role label and one short action verb phrase per record.',
    'Use the nearest explicit owner in the same span or active list heading. Never substitute a nearby owner.',
    'Preserve action direction and polarity exactly.',
    'Split adjacent verbs and duties. Split distinct destinations or systems into separate records.',
    'Keep every stated target, system, destination, portal, server, form, deadline, cadence, and timing qualifier in object; trigger may repeat but never replace them.',
    'If one duty names several targets, systems, forms, portals, cadences, or timing details, split per target or preserve all named details in object.',
    'Do not leave a real target only in requiredSystem. Do not invent duties not present in the source.',
    'Prefer multiple thin records. Use the shortest verbatim one-duty quote copied exactly from one chunk.',
  ].join(' ');
}

export function buildResponsibilityCombinedRepairPlan(args: {
  reads: readonly {
    segment: SourceStructureSegment;
    model: { output: ResponsibilityReadOutput };
    validation: ReturnType<typeof validateResponsibilityRead>;
  }[];
  chunks: readonly { id: string; rawText: string }[];
  maxFieldRepairs?: number;
  maxQuoteRepairs?: number;
}) {
  const chunkById = new Map(args.chunks.map((chunk) => [chunk.id, chunk]));
  const orderedReads = [...args.reads].sort((a, b) =>
    a.segment.segmentId.localeCompare(b.segment.segmentId),
  );
  const allModelRecords = new Map(
    orderedReads
      .flatMap((read) => read.model.output.responsibilities)
      .map((record) => [record.responsibilityId, record] as const),
  );
  const fieldSelections = orderedReads
    .flatMap((read) =>
      read.validation.incompleteInventoryAudit.map((audit) => ({ read, audit })),
    )
    .filter(({ audit }) =>
      (audit.failureCategory === 'field' || audit.failureCategory === 'multi_verb') &&
      audit.repairStatus !== 'repaired' &&
      allModelRecords.has(audit.elementId),
    )
    .sort(
      (a, b) =>
        Number(a.audit.failureCategory === 'multi_verb') -
          Number(b.audit.failureCategory === 'multi_verb') ||
        a.audit.chunkId.localeCompare(b.audit.chunkId) ||
        a.audit.elementId.localeCompare(b.audit.elementId),
    )
    .slice(0, args.maxFieldRepairs ?? 6);
  const quoteSelections = orderedReads
    .flatMap((read) =>
      read.validation.diagnostics
        .filter((diagnostic) => diagnostic.failureClass === 'quote_mismatch')
        .map((diagnostic) => ({ read, diagnostic })),
    )
    .sort(
      (a, b) =>
        a.diagnostic.chunkId.localeCompare(b.diagnostic.chunkId) ||
        a.diagnostic.responsibilityId.localeCompare(b.diagnostic.responsibilityId),
    )
    .slice(0, args.maxQuoteRepairs ?? 12);
  const selectedIds = new Set([
    ...fieldSelections.map(({ audit }) => audit.elementId),
    ...quoteSelections.map(({ diagnostic }) => diagnostic.responsibilityId),
  ]);
  const records = orderedReads.flatMap((read) =>
    read.model.output.responsibilities.filter((record) =>
      selectedIds.has(record.responsibilityId),
    ),
  );
  const uniqueRecords = [
    ...new Map(records.map((record) => [record.responsibilityId, record])).values(),
  ];
  const byRecordId = new Map(uniqueRecords.map((record) => [record.responsibilityId, record]));
  const fieldRepairRequests = fieldSelections.flatMap(({ audit }) => {
    const record = byRecordId.get(audit.elementId);
    return record
      ? [{
          responsibilityId: record.responsibilityId,
          chunkId: record.chunkId,
          evidenceQuote: record.evidenceQuote,
          sourceSpan: audit.selectedSourceSpan,
          allowedFields: [
            'role',
            'action',
            'object',
            'trigger',
            'requiredSystem',
          ] as Array<'role' | 'action' | 'object' | 'trigger' | 'requiredSystem'>,
        }]
      : [];
  });
  const quoteRepairCandidates = quoteSelections.flatMap(({ diagnostic }) => {
    const record = byRecordId.get(diagnostic.responsibilityId);
    const chunk = chunkById.get(diagnostic.chunkId);
    if (!record || !chunk) return [];
    const { evidenceQuote: _evidenceQuote, ...immutableFields } = record;
    return [{
      responsibilityId: record.responsibilityId,
      failedQuote: record.evidenceQuote,
      immutableFields,
      candidates: buildGroundedResponsibilityQuoteCandidates({
        rawText: chunk.rawText,
        failedQuote: record.evidenceQuote,
      }),
    }];
  });
  return {
    records: uniqueRecords,
    fieldRepairRequests,
    quoteRepairCandidates,
    selectedSegmentIds: orderedReads
      .filter((read) =>
        read.model.output.responsibilities.some((record) =>
          selectedIds.has(record.responsibilityId),
        ),
      )
      .map((read) => read.segment.segmentId),
    chunkIds: [...new Set(uniqueRecords.map((record) => record.chunkId))],
  };
}

export function mergeCombinedResponsibilityRepairOutput(args: {
  original: ResponsibilityReadOutput;
  repaired: ResponsibilityReadOutput;
}): ResponsibilityReadOutput {
  const repairedById = new Map(
    args.repaired.responsibilities.map((record) => [record.responsibilityId, record]),
  );
  return {
    ...args.original,
    responsibilities: args.original.responsibilities.map(
      (record) => repairedById.get(record.responsibilityId) ?? record,
    ),
  };
}

export function buildFocusedResponsibilityEvidenceChunks<T extends {
  id: string;
  rawText: string;
}>(chunks: readonly T[], focusedSpans: readonly ForcedResponsibilitySpan[]): T[] {
  return chunks.map((chunk) => ({
    ...chunk,
    rawText: focusedSpans
      .filter((span) => span.chunkId === chunk.id)
      .sort((a, b) => a.spanIndex - b.spanIndex)
      .map((span) => span.evidenceQuote)
      .join('\n'),
  }));
}

async function runResponsibilityReadModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  chunks: ChunkRow[];
  triggerRunId: string;
  mapId: string;
  segment: SourceStructureSegment;
  budget: SourceReaderBudget;
  focusedSpans?: ForcedResponsibilitySpan[];
  quoteRepairRecords?: ResponsibilityReadOutput['responsibilities'];
  fieldRepairRequests?: Array<{
    responsibilityId: string;
    chunkId: string;
    evidenceQuote: string;
    sourceSpan: string;
    allowedFields: Array<'role' | 'action' | 'object' | 'trigger' | 'requiredSystem'>;
  }>;
  quoteRepairCandidates?: Array<{
    responsibilityId: string;
    failedQuote: string;
    immutableFields: Omit<
      ResponsibilityReadOutput['responsibilities'][number],
      'evidenceQuote'
    >;
    candidates: GroundedResponsibilityQuoteCandidate[];
  }>;
}): Promise<{
  output: ResponsibilityReadOutput;
  modelRunId: string;
  contextPackId: string;
  execution: { outputTokens: number | null; finishReason: string | null; truncated: boolean };
  forcedSpanAudits: ReturnType<typeof canonicalizeForcedResponsibilityOutput>['audits'];
}> {
  const quoteRepairMode = Boolean(
    args.quoteRepairRecords?.length || args.fieldRepairRequests?.length,
  );
  const responsibilityTaskType = responsibilityReadTaskType(quoteRepairMode);
  const responsibilityPromptVersion = responsibilityReadPromptVersion(quoteRepairMode);
  const resolved = await resolveRouteCandidates(args.db, 'workflow_read');
  for (const skipped of resolved.skipped) {
    console.warn('[source-workflow-read] skipped responsibility route candidate', skipped);
  }
  const route = resolved.candidates[0]!.route;
  const evidenceChunks = args.focusedSpans?.length
    ? buildFocusedResponsibilityEvidenceChunks(args.chunks, args.focusedSpans)
    : args.chunks;
  const blocks = [
    makeBlock({
      id: 'responsibility-read-system',
      label: 'Responsibility read system prompt',
      kind: 'stable_system',
      content: quoteRepairMode
        ? RESPONSIBILITY_COMBINED_REPAIR_SYSTEM_PROMPT
        : RESPONSIBILITY_READ_SYSTEM_PROMPT,
      reasonIncluded: quoteRepairMode
        ? `${RESPONSIBILITY_COMBINED_REPAIR_PROMPT_VERSION}:combined`
        : RESPONSIBILITY_READ_PROMPT_VERSION,
    }),
    makeBlock({
      id: 'responsibility-metadata',
      label: 'Responsibility segment metadata',
      kind: 'semi_stable_domain_context',
      content: [
        `Document: ${args.doc.fileName}`,
        `Segment: ${args.segment.segmentId} | ${args.segment.title}`,
        !args.focusedSpans?.length && args.segment.summary
          ? `Non-quotable segment summary: ${args.segment.summary}`
          : null,
        !args.focusedSpans?.length && args.doc.context
          ? `Uploader context: ${args.doc.context}`
          : null,
        `Source map row: ${args.mapId}`,
      ]
        .filter(Boolean)
        .join('\n'),
      reasonIncluded: 'responsibility segment routing and audit context',
    }),
    makeBlock({
      id: 'responsibility-chunks',
      label: 'Document chunks',
      kind: 'retrieved_context',
      content: buildDocumentCorpus(evidenceChunks),
      reasonIncluded: 'only valid evidence source for this responsibility segment',
    }),
    makeBlock({
      id: 'responsibility-request',
      label: 'Responsibility read request',
      kind: 'dynamic_input',
      content: buildResponsibilityRequestContent({
        focusedSpans: args.focusedSpans,
        quoteRepairRecords: args.quoteRepairRecords,
        fieldRepairRequests: args.fieldRepairRequests,
        quoteRepairCandidates: args.quoteRepairCandidates,
      }),
      reasonIncluded: 'current responsibilities pass-2 request',
    }),
  ];
  args.budget.reserveRead({
    estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
    label: `responsibility read ${args.segment.segmentId}`,
  });
  const plan = args.client.compile({
    taskType: 'source_workflow_read',
    routeId: route.routeId,
    promptVersion: responsibilityPromptVersion,
    blocks,
    observability: { includedDocumentChunkIds: args.chunks.map((chunk) => chunk.id) },
  });
  const [contextPack] = await args.db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[source-workflow-read] failed responsibility context pack');
  const started = Date.now();
  const result = quoteRepairMode
    ? await args.client.runObject<ResponsibilityCombinedRepairOutput>({
        taskType: 'source_workflow_read',
        routeId: route.routeId,
        promptVersion: responsibilityPromptVersion,
        blocks,
        schema: ResponsibilityCombinedRepairSchema,
        observability: { includedDocumentChunkIds: args.chunks.map((chunk) => chunk.id) },
        providerOptions: { maxOutputTokens: 8_000 },
        routeCandidates: resolved.candidates,
      })
    : await args.client.runObject<ResponsibilityReadOutput>({
        taskType: 'source_workflow_read',
        routeId: route.routeId,
        promptVersion: responsibilityPromptVersion,
        blocks,
        schema: ResponsibilityReadSchema,
        observability: { includedDocumentChunkIds: args.chunks.map((chunk) => chunk.id) },
        providerOptions: { maxOutputTokens: 32_000 },
        routeCandidates: resolved.candidates,
      });
  const [modelRun] = await args.db
    .insert(modelRuns)
    .values({
      taskType: responsibilityTaskType,
      model: result.modelId ?? route.modelId,
      provider: result.provider ?? route.provider,
      promptVersion: responsibilityPromptVersion,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[source-workflow-read] failed responsibility model run');
  await args.db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    routeId: result.routeId ?? route.routeId,
    inputTokens: result.usage.inputTokens ?? null,
    cachedInputTokens: result.usage.cachedInputTokens ?? null,
    cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
    outputTokens: result.usage.outputTokens ?? null,
    reasoningTokens: result.usage.reasoningTokens ?? null,
    providerRequestId: result.usage.providerRequestId ?? null,
    rawUsageJson: result.usage.rawUsageJson ?? null,
  });
  await logModelRunAttempts({
    db: args.db,
    metadata: result,
    taskType: responsibilityTaskType,
    slot: 'workflow_read',
    contextPackId: contextPack.id,
    modelRunId: modelRun.id,
  });
  await args.db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));
  if (!result.validation.ok) {
    throw new Error(
      `[source-workflow-read] responsibility schema failed: ${result.validation.error.message}`,
    );
  }
  if (quoteRepairMode) {
    const knownRepairIds = new Set([
      ...(args.quoteRepairRecords ?? []).map((record) => record.responsibilityId),
      ...(args.fieldRepairRequests ?? []).map((request) => request.responsibilityId),
    ]);
    const unknownRepair = (result.object as ResponsibilityCombinedRepairOutput).quoteRepairs.find(
      (repair) => !knownRepairIds.has(repair.responsibilityId),
    );
    if (unknownRepair) {
      throw new Error(
        `[source-workflow-read] quote repair returned unknown responsibility ${unknownRepair.responsibilityId}`,
      );
    }
    for (const repair of (result.object as ResponsibilityCombinedRepairOutput).quoteRepairs) {
      const offered = args.quoteRepairCandidates?.find(
        (item) => item.responsibilityId === repair.responsibilityId,
      );
      const index = Number(repair.candidateId.replace(/^candidate_/, ''));
      if (!offered?.candidates.some((candidate) => candidate.candidateIndex === index)) {
        throw new Error(
          `[source-workflow-read] combined repair returned a quote outside grounded candidates for ${repair.responsibilityId}`,
        );
      }
    }
  }
  let output: ResponsibilityReadOutput = quoteRepairMode
    ? (() => {
        const originals = [
          ...(args.quoteRepairRecords ?? []),
          ...(args.fieldRepairRequests ?? []).flatMap((request) => {
            const original = args.quoteRepairRecords?.find(
              (record) => record.responsibilityId === request.responsibilityId,
            );
            return original ? [original] : [];
          }),
        ];
        const patched = patchCombinedResponsibilityRepairs({
          original: {
            summary: 'Combined responsibility repairs.',
            responsibilities: [...new Map(originals.map((item) => [item.responsibilityId, item])).values()],
          },
          fieldRequests: args.fieldRepairRequests ?? [],
          quoteRequests: (args.quoteRepairCandidates ?? []).map((item) => ({
            responsibilityId: item.responsibilityId,
            candidates: item.candidates.map((candidate) => ({
              candidateId: `candidate_${candidate.candidateIndex}`,
              sourceText: candidate.sourceText,
            })),
          })),
          repaired: result.object as ResponsibilityCombinedRepairOutput,
        });
        if (!patched.ok) {
          throw new Error(`[source-workflow-read] combined repair rejected: ${patched.reason}`);
        }
        return patched.output;
      })()
    : (result.object as ResponsibilityReadOutput);
  const forcedResult = args.focusedSpans?.length
    ? canonicalizeForcedResponsibilityOutput({
        output,
        selected: args.focusedSpans,
      })
    : null;
  if (forcedResult) output = forcedResult.output;
  const rawUsage = result.usage.rawUsageJson as Record<string, unknown> | null | undefined;
  const finishReason =
    typeof rawUsage?.finishReason === 'string'
      ? rawUsage.finishReason
      : typeof rawUsage?.finish_reason === 'string'
        ? rawUsage.finish_reason
        : null;
  return {
    output,
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    execution: {
      outputTokens: result.usage.outputTokens ?? null,
      finishReason,
      truncated: finishReason ? /length|max[_ -]?tokens|trunc/i.test(finishReason) : false,
    },
    forcedSpanAudits: forcedResult?.audits ?? [],
  };
}

async function runWorkflowQuoteRepairModel(args: {
  db: OracleDb;
  client: OracleAIClient;
  doc: { fileName: string; fileType: string; context: string | null };
  mapId: string;
  chunks: ChunkRow[];
  failures: readonly WorkflowMapRejectionDiagnostic[];
  budget: SourceReaderBudget;
}): Promise<{ output: WorkflowQuoteRepairOutput; modelRunId: string; contextPackId: string }> {
  const resolved = await resolveRouteCandidates(args.db, 'workflow_read');
  const route = resolved.candidates[0]!.route;
  const neededChunkIds = new Set(args.failures.map((failure) => failure.citedChunkId!));
  const repairChunks = args.chunks.filter((chunk) => neededChunkIds.has(chunk.id));
  const blocks = [
    makeBlock({
      id: 'workflow-quote-repair-system',
      label: 'Workflow quote-copy repair system prompt',
      kind: 'stable_system',
      content: WORKFLOW_QUOTE_REPAIR_SYSTEM_PROMPT,
      reasonIncluded: `bounded quote-copy repair ${WORKFLOW_READ_PROMPT_VERSION}`,
    }),
    makeBlock({
      id: 'workflow-quote-repair-document',
      label: 'Document metadata and source chunks',
      kind: 'retrieved_context',
      content: `Document: ${args.doc.fileName}\nMap: ${args.mapId}\n\n${buildDocumentCorpus(repairChunks)}`,
      reasonIncluded: 'exact source text for failed quotes only',
    }),
    makeBlock({
      id: 'workflow-quote-repair-request',
      label: 'Failed quote-copy records',
      kind: 'dynamic_input',
      content: JSON.stringify(
        args.failures.map((failure) => ({
          elementId: failure.elementId,
          elementType: failure.elementType,
          chunkId: failure.citedChunkId,
          rejectedEvidenceQuote: failure.failingQuoteExcerpt,
          failureClass: failure.failureClass,
        })),
      ),
      reasonIncluded: 'repair only eligible root quote-copy failures',
    }),
  ];
  args.budget.reserveRead({
    estimatedInputTokens: blocks.reduce((sum, block) => sum + (block.tokenEstimate ?? 0), 0),
    label: 'workflow quote-copy repair',
  });
  const plan = args.client.compile({
    taskType: 'source_workflow_read',
    routeId: route.routeId,
    promptVersion: WORKFLOW_READ_PROMPT_VERSION,
    blocks,
    observability: { includedDocumentChunkIds: [...neededChunkIds] },
  });
  const [contextPack] = await args.db
    .insert(oracleContextPacks)
    .values(buildContextPackInsert(plan))
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('[source-workflow-read] failed to insert repair context pack');
  const started = Date.now();
  const result = await args.client
    .runObject<WorkflowQuoteRepairOutput>({
      taskType: 'source_workflow_read',
      routeId: route.routeId,
      promptVersion: WORKFLOW_READ_PROMPT_VERSION,
      blocks,
      schema: WorkflowQuoteRepairSchema,
      observability: { includedDocumentChunkIds: [...neededChunkIds] },
      providerOptions: { maxOutputTokens: 8_000 },
      routeCandidates: resolved.candidates,
    })
    .catch(async (error) => {
      await logAllCandidatesFailedAttempts({
        db: args.db,
        error,
        taskType: 'source-workflow-read',
        slot: 'workflow_read',
        contextPackId: contextPack.id,
      }).catch((logError) =>
        console.error('[source-workflow-read] failed to log quote repair attempts', logError),
      );
      throw error;
    });
  const [modelRun] = await args.db
    .insert(modelRuns)
    .values({
      taskType: 'source-workflow-read-quote-repair',
      model: result.modelId ?? route.modelId,
      provider: result.provider ?? route.provider,
      promptVersion: WORKFLOW_READ_PROMPT_VERSION,
      inputHash: plan.metadata.stablePrefixHash,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      latencyMs: Date.now() - started,
      success: result.validation.ok,
      error: result.validation.ok ? null : result.validation.error.message,
    })
    .returning({ id: modelRuns.id });
  if (!modelRun) throw new Error('[source-workflow-read] failed to insert repair model run');
  await args.db.insert(modelRunUsageDetails).values({
    modelRunId: modelRun.id,
    contextPackId: contextPack.id,
    routeId: result.routeId ?? route.routeId,
    inputTokens: result.usage.inputTokens ?? null,
    cachedInputTokens: result.usage.cachedInputTokens ?? null,
    cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
    outputTokens: result.usage.outputTokens ?? null,
    reasoningTokens: result.usage.reasoningTokens ?? null,
    providerRequestId: result.usage.providerRequestId ?? null,
    rawUsageJson: result.usage.rawUsageJson ?? null,
  });
  await logModelRunAttempts({
    db: args.db,
    metadata: result,
    taskType: 'source-workflow-read',
    slot: 'workflow_read',
    contextPackId: contextPack.id,
    modelRunId: modelRun.id,
  });
  await args.db
    .update(oracleContextPacks)
    .set({ modelRunId: modelRun.id })
    .where(eq(oracleContextPacks.id, contextPack.id));
  if (!result.validation.ok) {
    throw new Error(
      `[source-workflow-read] quote repair failed schema validation: ${result.validation.error.message}`,
    );
  }
  return { output: result.object, modelRunId: modelRun.id, contextPackId: contextPack.id };
}

export function renderWorkflowMapGuidance(mapId: string, map: SourceStructureMap): string {
  const lines = [
    'SOURCE STRUCTURE MAP (GUIDANCE ONLY - NEVER QUOTE THIS BLOCK)',
    `Map ID: ${mapId}`,
    `Document shape: ${map.documentShape}`,
    `Summary: ${map.summary}`,
  ];
  if (map.segments.length > 0) {
    lines.push('', 'Segments:');
    for (const segment of map.segments) {
      lines.push(
        `- ${segment.segmentId} [${segment.shape}] ${segment.title}${segment.summary ? ` | ${segment.summary}` : ''}`,
      );
    }
  }
  if (map.lanes.length > 0) {
    lines.push('', 'Lanes:');
    for (const lane of map.lanes)
      lines.push(
        `- ${lane.laneId}: ${lane.label}${lane.ownerName ? ` (owner: ${lane.ownerName})` : ''}`,
      );
  }
  if (map.elements.length > 0) {
    lines.push('', 'Elements:');
    for (const element of map.elements) {
      const ref = `${mapId}:element:${element.elementId}`;
      lines.push(
        `- ${ref} [${element.elementKind}] ${element.label}${element.lane ? ` | lane=${element.lane}` : ''}${element.ownerName ? ` | owner=${element.ownerName}` : ''}${element.systems ? ` | systems=${element.systems}` : ''}`,
      );
    }
  }
  if (map.relations.length > 0) {
    lines.push('', 'Relations:');
    for (const relation of map.relations) {
      const ref = `${mapId}:relation:${relation.relationId}`;
      lines.push(
        `- ${ref} [${relation.relationKind}] ${relation.fromElementId} -> ${relation.toElementId}${relation.condition ? ` | condition=${relation.condition}` : ''}`,
      );
    }
  }
  if (map.paths.length > 0) {
    lines.push('', 'Paths:');
    for (const path of map.paths)
      lines.push(
        `- ${path.pathId} [${path.pathType}] ${path.name}: ${path.nodeIdsOrdered.join(' -> ')}`,
      );
  }
  lines.push(
    '',
    'Shape-directed extraction:',
    ...[...new Set(map.segments.map((segment) => segment.shape))].map(
      (shape) => `- ${shape}: ${SOURCE_STRUCTURE_SHAPE_REGISTRY[shape].extractionDirective}`,
    ),
    '',
    'Extraction instruction: when a claim supports a listed element or relation, set mapElementRef to the exact ref shown above. Claims still require a verbatim exactQuote from a Document Chunk ID.',
  );
  return lines.join('\n');
}

export type ActiveWorkflowMapRef = {
  ref: string;
  kind: 'element' | 'relation';
  localId: string;
  segmentId: string;
  shape: SourceStructureShape;
  chunkId: string;
};

export type ActiveWorkflowMapContext = {
  mapId: string;
  map: SourceStructureMap;
  guidance: string;
  refs: ReadonlyMap<string, ActiveWorkflowMapRef>;
};

export type MapElementRefMembershipResult =
  | { ok: true; target: ActiveWorkflowMapRef }
  | {
      ok: false;
      failureClass: 'no_active_map' | 'wrong_map' | 'unknown_map_ref' | 'outside_extraction_window';
      detail: string;
    };

export function buildActiveWorkflowMapRefIndex(
  mapId: string,
  map: SourceStructureMap,
): Map<string, ActiveWorkflowMapRef> {
  const refs = new Map<string, ActiveWorkflowMapRef>();
  for (const element of map.elements) {
    const ref = `${mapId}:element:${element.elementId}`;
    refs.set(ref, {
      ref,
      kind: 'element',
      localId: element.elementId,
      segmentId: element.segmentId,
      shape: element.shape,
      chunkId: element.chunkId,
    });
  }
  for (const relation of map.relations) {
    const ref = `${mapId}:relation:${relation.relationId}`;
    refs.set(ref, {
      ref,
      kind: 'relation',
      localId: relation.relationId,
      segmentId: relation.segmentId,
      shape: relation.shape,
      chunkId: relation.chunkId,
    });
  }
  return refs;
}

async function loadSourceReaderBudgetLimits(db: OracleDb): Promise<SourceReaderBudgetLimits> {
  const [
    maxReadCalls,
    maxInputTokens,
    maxEstimatedCostUsd,
    estimatedInputCostPerMillionTokensUsd,
    maxRepairAttempts,
    maxConcurrency,
  ] = await Promise.all([
    readNumberSetting(db, 'source_reader_max_read_calls_per_source', 40),
    readNumberSetting(db, 'source_reader_max_input_tokens_per_source', 500_000),
    readNumberSetting(db, 'source_reader_max_estimated_cost_usd_per_source', 10),
    readNumberSetting(db, 'source_reader_estimated_input_cost_per_million_tokens_usd', 5),
    readNumberSetting(db, 'source_reader_max_repair_attempts_per_source', 1),
    readNumberSetting(db, 'source_reader_max_concurrency_per_source', 4),
  ]);
  return {
    maxReadCalls: Math.trunc(maxReadCalls),
    maxInputTokens: Math.trunc(maxInputTokens),
    maxEstimatedCostUsd,
    estimatedInputCostPerMillionTokensUsd,
    maxRepairAttempts: Math.trunc(maxRepairAttempts),
    maxConcurrency: Math.trunc(maxConcurrency),
  };
}

async function loadResponsibilityPostPassBudgetLimits(
  db: OracleDb,
): Promise<ResponsibilityPostPassBudgetLimits> {
  const [maxQuoteRepairs, maxOmissionRetries, maxOmissionRetriesPerChunk] = await Promise.all([
    readResponsibilityPostPassSetting(
      db,
      'responsibility_postpass_max_quote_repairs_per_source',
      1,
    ),
    readResponsibilityPostPassSetting(
      db,
      'responsibility_postpass_max_omission_retries_per_source',
      5,
    ),
    readResponsibilityPostPassSetting(
      db,
      'responsibility_postpass_max_omission_retries_per_chunk',
      1,
    ),
  ]);
  return {
    maxQuoteRepairsPerSource: Math.trunc(maxQuoteRepairs),
    maxOmissionRetriesPerSource: Math.trunc(maxOmissionRetries),
    maxOmissionRetriesPerChunk: Math.trunc(maxOmissionRetriesPerChunk),
  };
}

export function validateMapElementRefMembership(args: {
  mapElementRef: string;
  activeMap: ActiveWorkflowMapContext | null;
  eligibleChunkIds: ReadonlySet<string>;
}): MapElementRefMembershipResult {
  if (!args.activeMap) {
    return {
      ok: false,
      failureClass: 'no_active_map',
      detail: 'Candidate supplied mapElementRef but no active validated/degraded map exists.',
    };
  }
  if (!args.mapElementRef.startsWith(`${args.activeMap.mapId}:`)) {
    return {
      ok: false,
      failureClass: 'wrong_map',
      detail: `mapElementRef does not belong to active map ${args.activeMap.mapId}.`,
    };
  }
  const target = args.activeMap.refs.get(args.mapElementRef);
  if (!target) {
    return {
      ok: false,
      failureClass: 'unknown_map_ref',
      detail: `mapElementRef is well-formed but is not a member of active map ${args.activeMap.mapId}.`,
    };
  }
  if (!args.eligibleChunkIds.has(target.chunkId)) {
    return {
      ok: false,
      failureClass: 'outside_extraction_window',
      detail: `mapElementRef cites chunk ${target.chunkId}, which is outside the active extraction window.`,
    };
  }
  return { ok: true, target };
}

export async function loadLatestWorkflowMapContext(
  db: OracleDb,
  documentId: string,
): Promise<ActiveWorkflowMapContext | null> {
  const [row] = await db
    .select({
      id: sourceWorkflowMaps.id,
      status: sourceWorkflowMaps.status,
      summary: sourceWorkflowMaps.summary,
      documentShape: sourceWorkflowMaps.documentShape,
      segmentsJson: sourceWorkflowMaps.segmentsJson,
      elementsJson: sourceWorkflowMaps.elementsJson,
      relationsJson: sourceWorkflowMaps.relationsJson,
      nodesJson: sourceWorkflowMaps.nodesJson,
      edgesJson: sourceWorkflowMaps.edgesJson,
      lanesJson: sourceWorkflowMaps.lanesJson,
      pathsJson: sourceWorkflowMaps.pathsJson,
    })
    .from(sourceWorkflowMaps)
    .where(
      and(
        eq(sourceWorkflowMaps.sourceType, 'document'),
        eq(sourceWorkflowMaps.documentId, documentId),
        sql`${sourceWorkflowMaps.status} IN ('validated', 'degraded')`,
      ),
    )
    .orderBy(desc(sourceWorkflowMaps.createdAt))
    .limit(1);
  if (!row) return null;
  const elements = row.elementsJson as SourceStructureElement[];
  const relations = row.relationsJson as SourceStructureRelation[];
  const segments = row.segmentsJson as SourceStructureMap['segments'];
  const map =
    segments.length > 0
      ? ({
          documentShape: row.documentShape as SourceStructureShape,
          summary: row.summary ?? 'No summary.',
          segments,
          elements,
          relations,
          lanes: row.lanesJson as WorkflowReadLane[],
          paths: row.pathsJson as WorkflowReadPath[],
        } satisfies SourceStructureMap)
      : workflowToProcessStructureMap({
          output: {
            summary: row.summary ?? 'No summary.',
            mapKind: 'workflow',
            nodes: row.nodesJson as WorkflowReadNode[],
            edges: row.edgesJson as WorkflowReadEdge[],
            lanes: row.lanesJson as WorkflowReadLane[],
            paths: row.pathsJson as WorkflowReadPath[],
          },
          chunks: [
            {
              id: '00000000-0000-4000-8000-000000000000',
              chunkIndex: 0,
              pageNumber: null,
              rawText: '',
              contentHash: null,
            },
          ],
          title: 'Full process',
        });
  return {
    mapId: row.id,
    map,
    guidance: renderWorkflowMapGuidance(row.id, map),
    refs: buildActiveWorkflowMapRefIndex(row.id, map),
  };
}

export async function loadLatestWorkflowMapGuidance(
  db: OracleDb,
  documentId: string,
): Promise<string | null> {
  return (await loadLatestWorkflowMapContext(db, documentId))?.guidance ?? null;
}

async function buildWorkflowValidationChunkContexts(args: {
  db: OracleDb;
  documentId: string;
  output: WorkflowReadOutput;
  documentChunks: ChunkRow[];
  coveredChunkIds: ReadonlySet<string>;
}): Promise<Map<string, WorkflowMapChunkContext>> {
  const contexts = new Map<string, WorkflowMapChunkContext>(
    args.documentChunks.map((chunk) => [
      chunk.id,
      {
        documentId: args.documentId,
        text: chunk.rawText,
        coveredBySegmentation: args.coveredChunkIds.has(chunk.id),
      },
    ]),
  );
  const citedIds = new Set([
    ...args.output.nodes.map((node) => node.chunkId),
    ...args.output.edges.map((edge) => edge.chunkId),
  ]);
  const unresolvedIds = [...citedIds].filter((chunkId) => !contexts.has(chunkId));
  if (unresolvedIds.length === 0) return contexts;

  const referencedRows = await args.db
    .select({
      id: documentChunks.id,
      documentId: documentChunks.documentId,
      rawText: documentChunks.rawText,
    })
    .from(documentChunks)
    .where(inArray(documentChunks.id, unresolvedIds));
  for (const row of referencedRows) {
    contexts.set(row.id, {
      documentId: row.documentId,
      text: row.rawText,
      coveredBySegmentation: false,
    });
  }
  return contexts;
}

export async function generateSourceWorkflowMap(args: {
  documentId: string;
  triggerRunId: string;
  force?: boolean;
  db?: OracleDb;
  client?: OracleAIClient;
  orchestrationDependencies?: {
    selectResidualSeeds?: (
      seeds: readonly ResponsibilityInventorySeed[],
      completeIds: ReadonlySet<string>,
    ) => ResponsibilityInventorySeed[];
    findOmissions?: typeof findResponsibilityOmissions;
    buildBaseReadPlan?: typeof buildResponsibilityBaseReadPlan;
    buildCombinedRepairPlan?: typeof buildResponsibilityCombinedRepairPlan;
    selectQuoteRepairRead?: typeof selectResponsibilityQuoteRepairRead;
  };
}): Promise<SourceWorkflowReadResult> {
  const db = args.db ?? getDirectDb();
  const client = args.client ?? new OracleAIClient({ adapters: buildStandardAdapters() });
  const force = args.force ?? false;

  const [doc] = await db
    .select({
      id: documents.id,
      fileName: documents.fileName,
      fileType: documents.fileType,
      context: documents.context,
    })
    .from(documents)
    .where(eq(documents.id, args.documentId))
    .limit(1);
  if (!doc) return { documentId: args.documentId, status: 'skipped_not_found' };

  const chunks = await db
    .select({
      id: documentChunks.id,
      chunkIndex: documentChunks.chunkIndex,
      pageNumber: documentChunks.pageNumber,
      rawText: documentChunks.rawText,
      contentHash: documentChunks.contentHash,
    })
    .from(documentChunks)
    .where(eq(documentChunks.documentId, args.documentId))
    .orderBy(documentChunks.chunkIndex);
  if (chunks.length === 0) return { documentId: args.documentId, status: 'skipped_no_chunks' };

  await markMacroPending(db, args.documentId);
  const sourceContentHash = sourceHashForDocument(args.documentId, chunks);
  const pending = await createPendingMap({
    db,
    documentId: args.documentId,
    sourceContentHash,
    force,
  });
  if (pending.skippedExisting) {
    if (pending.existingStatus === 'degraded') await markMacroDegraded(db, args.documentId);
    else await markMacroComplete(db, args.documentId);
    return {
      documentId: args.documentId,
      status: 'skipped_existing',
      mapId: pending.mapId,
      existingMapStatus: pending.existingStatus,
    };
  }

  const [jobRun] = await db
    .insert(jobRuns)
    .values({
      triggerRunId: args.triggerRunId,
      jobType: 'source-workflow-read',
      status: 'running',
      startedAt: new Date(),
      inputJson: { documentId: args.documentId, force, mapId: pending.mapId },
    })
    .returning({ id: jobRuns.id });
  if (!jobRun) throw new Error('[source-workflow-read] failed to insert job_runs row');

  let readerBudget: SourceReaderBudget | null = null;
  try {
    readerBudget = new SourceReaderBudget(await loadSourceReaderBudgetLimits(db));
    const responsibilityPostPassBudget = new ResponsibilityPostPassBudget(
      await loadResponsibilityPostPassBudgetLimits(db),
    );
    const referentPack = await buildReferentPack(db);
    const firstSegmentationModel = await runSegmentationModel({
      db,
      client,
      doc,
      chunks,
      mapId: pending.mapId,
      budget: readerBudget,
    });
    const segmentationModels = [firstSegmentationModel];
    const segmentationValidations = [validateSegmentation(firstSegmentationModel.output, chunks)];
    let segmentation = segmentationValidations[0]!;
    while (
      segmentation.integrityRepairCount > 0 &&
      segmentationModels.length - 1 < readerBudget.limits.maxRepairAttempts
    ) {
      readerBudget.reserveRepair('source segmentation integrity repair');
      const retryModel = await runSegmentationModel({
        db,
        client,
        doc,
        chunks,
        mapId: pending.mapId,
        repairFeedback: JSON.stringify(segmentation.validationJson),
        budget: readerBudget,
      });
      const retryValidation = validateSegmentation(retryModel.output, chunks);
      segmentationModels.push(retryModel);
      segmentationValidations.push(retryValidation);
      if (retryValidation.integrityRepairCount >= segmentation.integrityRepairCount) break;
      segmentation = retryValidation;
    }
    const chunkById = new Map(chunks.map((chunk) => [chunk.id, chunk]));
    const coveredChunkIds = new Set(segmentation.segments.flatMap((segment) => segment.chunkIds));
    const quoteSourceKind = quoteSourceKindForDocument(doc);
    const maxDroppedRatio = await readNumberSetting(db, 'workflow_map_max_dropped_ratio', 0.2);
    const processSegments = segmentation.segments.filter((segment) => segment.shape === 'process');
    const responsibilitySegments = segmentation.segments.filter(
      (segment) => segment.shape === 'responsibilities',
    );
    const responsibilityBaseReadPlan = (
      args.orchestrationDependencies?.buildBaseReadPlan ?? buildResponsibilityBaseReadPlan
    )({
      responsibilitySegments,
      chunks: chunks.map((chunk) => ({
        id: chunk.id,
        documentId: args.documentId,
        rawText: chunk.rawText,
      })),
    });
    const responsibilityShards = responsibilityBaseReadPlan.responsibilityShards;
    const processReads = await mapWithConcurrency<
      SourceStructureSegment,
      {
        segment: SourceStructureSegment;
        validation: ReturnType<typeof validateWorkflowMap>;
        output: WorkflowReadOutput;
        segmentChunks: ChunkRow[];
        validationChunks: Map<string, WorkflowMapChunkContext>;
        eligibleFailures: WorkflowMapRejectionDiagnostic[];
        modelRunIds: string[];
        contextPackIds: string[];
        repair: WorkflowQuoteRepairMetadata;
      }
    >({
      inputs: processSegments,
      concurrency: readerBudget.limits.maxConcurrency,
      run: async (segment) => {
        const segmentChunks = segment.chunkIds
          .map((chunkId) => chunkById.get(chunkId))
          .filter((chunk): chunk is ChunkRow => Boolean(chunk));
        const modelResult = await runWorkflowReadModel({
          db,
          client,
          doc,
          chunks: segmentChunks,
          referentPack,
          triggerRunId: args.triggerRunId,
          mapId: pending.mapId,
          force,
          segment,
          budget: readerBudget!,
        });
        const validationChunks = await buildWorkflowValidationChunkContexts({
          db,
          documentId: args.documentId,
          output: modelResult.output,
          documentChunks: chunks,
          coveredChunkIds,
        });
        const originalValidation = validateWorkflowMap({
          output: modelResult.output,
          activeDocumentId: args.documentId,
          activeSegmentChunkIds: new Set(segment.chunkIds),
          chunksById: validationChunks,
          sourceKind: quoteSourceKind,
          maxDroppedRatio,
        });
        const eligibleFailures = eligibleWorkflowQuoteRepairs(originalValidation);
        const repair: WorkflowQuoteRepairMetadata = {
          repairAttempts: 0,
          repairSkipped:
            eligibleFailures.length === 0
              ? 'no_eligible_root_quote_failure'
              : 'not_selected_lower_impact',
          rootDroppedBefore: originalValidation.rootDroppedCount,
          cascadeDroppedBefore: originalValidation.cascadeDroppedCount,
          rootDroppedAfter: originalValidation.rootDroppedCount,
          cascadeDroppedAfter: originalValidation.cascadeDroppedCount,
        };
        return {
          segment,
          validation: originalValidation,
          output: modelResult.output,
          segmentChunks,
          validationChunks,
          eligibleFailures,
          modelRunIds: modelResult.modelRunIds,
          contextPackIds: modelResult.contextPackIds,
          repair,
        };
      },
    });

    const repairCandidateIndex = selectWorkflowQuoteRepairCandidate(
      processReads.map((read) => read.validation),
    );
    if (repairCandidateIndex !== null) {
      const read = processReads[repairCandidateIndex]!;
      read.repair.repairSkipped = null;
      try {
        readerBudget.reserveRepair('workflow quote-copy repair');
        read.repair.repairAttempts = 1;
        const repairResult = await runWorkflowQuoteRepairModel({
          db,
          client,
          doc,
          mapId: pending.mapId,
          chunks,
          failures: read.eligibleFailures,
          budget: readerBudget,
        });
        read.modelRunIds.push(repairResult.modelRunId);
        read.contextPackIds.push(repairResult.contextPackId);
        const patched = patchWorkflowQuoteRepairs({
          original: read.output,
          requested: read.eligibleFailures,
          response: repairResult.output,
        });
        if (!patched.ok) {
          read.repair.repairSkipped = patched.reason;
        } else {
          const repairedValidation = validateWorkflowMap({
            output: patched.output,
            activeDocumentId: args.documentId,
            activeSegmentChunkIds: new Set(read.segment.chunkIds),
            chunksById: read.validationChunks,
            sourceKind: quoteSourceKind,
            maxDroppedRatio,
          });
          read.repair.rootDroppedAfter = repairedValidation.rootDroppedCount;
          read.repair.cascadeDroppedAfter = repairedValidation.cascadeDroppedCount;
          const selectedValidation = chooseWorkflowQuoteRepair(
            read.validation,
            repairedValidation,
          );
          if (selectedValidation === read.validation) {
            read.repair.repairSkipped = 'no_root_improvement';
          } else {
            read.validation = selectedValidation;
          }
        }
      } catch (error) {
        if (
          error instanceof SourceReaderBudgetExceededError &&
          (error.check === 'max_repair_attempts' ||
            error.check === 'max_read_calls' ||
            error.check === 'max_input_tokens' ||
            error.check === 'max_estimated_cost_usd')
        ) {
          read.repair.repairSkipped = 'budget_exhausted';
        } else {
          read.repair.repairSkipped = 'repair_call_failed';
          console.error('[source-workflow-read] optional quote-copy repair failed', error);
        }
      }
    }

    let responsibilityReads = mergeResponsibilityValidationResults(await mapWithConcurrency({
      inputs: responsibilityShards,
      concurrency: readerBudget.limits.maxConcurrency,
      run: async (segment, shardIndex) => {
        const segmentChunkIds = new Set(segment.chunkIds);
        const segmentChunks = chunks.filter((chunk) => segmentChunkIds.has(chunk.id));
        const model = await runResponsibilityReadModel({
          db,
          client,
          doc,
          chunks: segmentChunks,
          triggerRunId: args.triggerRunId,
          mapId: pending.mapId,
          segment,
          budget: readerBudget!,
        });
        model.output = prefixResponsibilityOutput(model.output, shardIndex);
        const inventoryMatch = completeAndMatchResponsibilityInventory({
          inventorySeeds: responsibilityBaseReadPlan.inventorySeeds.filter((seed) =>
            segmentChunkIds.has(seed.chunkId),
          ),
          proposals: model.output,
          chunks: segmentChunks.map((chunk) => ({
            id: chunk.id,
            documentId: args.documentId,
            rawText: chunk.rawText,
          })),
        });
        model.output = inventoryMatch.output;
        const validation = validateResponsibilityRead({
          output: model.output,
          documentId: args.documentId,
          segment: responsibilityParentSegment(segment),
          fileType: doc.fileType,
          fileName: doc.fileName,
          allCoveredChunkIds: new Set(segmentation.segments.flatMap((item) => item.chunkIds)),
          inventorySeeds: inventoryMatch.inventorySeeds,
          chunks: chunks.map((chunk) => ({
            id: chunk.id,
            documentId: args.documentId,
            rawText: chunk.rawText,
          })),
        });
        return {
          segment,
          model,
          validation,
          modelRunIds: [model.modelRunId],
          contextPackIds: [model.contextPackId],
          executions: [model.execution],
          inventoryMatchAudit: {
            ...inventoryMatch.audit,
            mergeReadyInventoryIds: validation.completeElementIds,
            mergeReadyInventoryCount: validation.completeElementIds.length,
            incompleteSeedIds: inventoryMatch.audit.sourceInventoryIds.filter(
              (id) => !validation.completeElementIds.includes(id),
            ),
          },
          inventorySeeds: inventoryMatch.inventorySeeds,
          inventoryAuditParents: inventoryMatch.inventoryAuditParents,
        };
      },
    }));

    const ownedResponsibilitySeedIds = new Set<string>();
    responsibilityReads = responsibilityReads.map((read) => {
      const ownedSeeds = read.inventorySeeds.filter((seed) => {
        if (ownedResponsibilitySeedIds.has(seed.inventorySeedId)) return false;
        ownedResponsibilitySeedIds.add(seed.inventorySeedId);
        return true;
      });
      if (ownedSeeds.length === read.inventorySeeds.length) return read;
      const ownedIds = new Set(ownedSeeds.map((seed) => seed.inventorySeedId));
      const ownedDiscoveredIds = read.inventoryMatchAudit.modelDiscoveredInventoryIds.filter((id) =>
        ownedIds.has(id)
      );
      const output = {
        ...read.model.output,
        responsibilities: read.model.output.responsibilities.filter((record) =>
          ownedIds.has(record.responsibilityId)
        ),
      };
      const validation = validateResponsibilityRead({
        output,
        documentId: args.documentId,
        segment: responsibilityParentSegment(read.segment),
        fileType: doc.fileType,
        fileName: doc.fileName,
        allCoveredChunkIds: coveredChunkIds,
        inventorySeeds: ownedSeeds,
        chunks: chunks.map((chunk) => ({
          id: chunk.id, documentId: args.documentId, rawText: chunk.rawText,
        })),
      });
      return {
        ...read,
        model: { ...read.model, output },
        validation,
        inventorySeeds: ownedSeeds,
        inventoryMatchAudit: {
          ...read.inventoryMatchAudit,
          sourceInventoryIds: ownedSeeds.map((seed) => seed.inventorySeedId),
          sourceInventoryCount: ownedSeeds.length,
          modelDiscoveredInventoryIds: ownedDiscoveredIds,
          modelDiscoveredInventoryCount: ownedDiscoveredIds.length,
          matchedProposalInventoryIds: Object.fromEntries(
            Object.entries(read.inventoryMatchAudit.matchedProposalInventoryIds).filter(([, id]) =>
              ownedIds.has(id)
            ),
          ),
          mergeReadyInventoryIds: validation.completeElementIds,
          mergeReadyInventoryCount: validation.completeElementIds.length,
          incompleteSeedIds: ownedSeeds
            .map((seed) => seed.inventorySeedId)
            .filter((id) => !validation.completeElementIds.includes(id)),
        },
      };
    });

    let responsibilityInventorySeeds = canonicalResponsibilityInventory({
      seeds: responsibilityReads.flatMap((read) => read.inventorySeeds),
      chunks,
    });
    const responsibilityInventoryAuditParents = [
      ...responsibilityBaseReadPlan.inventoryAuditParents,
      ...responsibilityReads.flatMap((read) => read.inventoryAuditParents),
    ];

    const completeBeforeResidual = new Set(
      responsibilityReads.flatMap((read) => read.validation.completeElementIds),
    );
    const residualSeeds = args.orchestrationDependencies?.selectResidualSeeds
      ? args.orchestrationDependencies.selectResidualSeeds(
          responsibilityInventorySeeds,
          completeBeforeResidual,
        )
      : responsibilityInventorySeeds.filter(
          (seed) => !completeBeforeResidual.has(seed.inventorySeedId),
        );
    const completionPacking = await loadResponsibilityCompletionPackingConfig({
      db,
      budget: readerBudget,
      reserveQuoteRepair: responsibilityPostPassBudget.limits.maxQuoteRepairsPerSource > 0,
    });
    const completionPack = packResponsibilityCompletions({
      seeds: residualSeeds,
      ...completionPacking.pack,
    });
    // The exhaustive stage owns batch indices [0, exhaustiveBatchCount); the late path is
    // offset past them, which makes this the exact stage boundary in the execution audit.
    const exhaustiveBatchCount = completionPack.batches.length;
    const completionExecutions = new Map<number, ResponsibilityCompletionExecution[]>();
    // F4: the exhaustive completion stage uses the SAME shared seam as the late path, so a
    // candidate is corrected before the strict-improvement selection and before the
    // `validateResponsibilityRead` call below — the record that is judged is the record that
    // is assembled. No new stage, dispatch, reservation, model call or retry is introduced.
    const exhaustiveCorrectionSeam = responsibilityFinalRecordCorrectionSeam({
      seeds: residualSeeds,
      stage: 'exhaustive',
    });
    const completionResults = await executeResponsibilityCompletionBatches({
      correctRecord: exhaustiveCorrectionSeam.correctRecord,
      budget: readerBudget,
      batches: completionPack.batches,
      concurrency: readerBudget.limits.maxConcurrency,
      baselines: residualSeeds.map((seed) => ({
        responsibilityId: seed.inventorySeedId,
        complete: false,
      })),
      runBatch: async (batch) => {
        const execution = await runResponsibilityCompletionModel({
          db,
          client,
          doc,
          mapId: pending.mapId,
          triggerRunId: args.triggerRunId,
          batch,
        });
        const list = completionExecutions.get(batch.batchIndex) ?? [];
        list.push(execution);
        completionExecutions.set(batch.batchIndex, list);
        return execution.output;
      },
      validateCompletion: (record) => {
        const seed = responsibilityInventorySeeds.find(
          (item) => item.inventorySeedId === record.responsibilityId,
        );
        const read = seed
          ? responsibilityReads.find((item) => item.segment.chunkIds.includes(seed.chunkId))
          : undefined;
        if (!seed || !read) return { complete: false, reasons: ['seed_or_source_read_missing'] };
        const validation = validateResponsibilityRead({
          output: { summary: 'Residual responsibility completion.', responsibilities: [record] },
          documentId: args.documentId,
          segment: responsibilityParentSegment(read.segment),
          fileType: doc.fileType,
          fileName: doc.fileName,
          allCoveredChunkIds: coveredChunkIds,
          inventorySeeds: [seed],
          chunks: chunks.map((chunk) => ({
            id: chunk.id,
            documentId: args.documentId,
            rawText: chunk.rawText,
          })),
        });
        return {
          complete: validation.completeElementIds.includes(record.responsibilityId),
          reasons: [
            ...validation.diagnostics.map((item) => item.detail),
            ...validation.incompleteInventoryAudit.map((item) => item.decisionReason),
          ],
        };
      },
    });
    const acceptedCompletionRecords = completionResults.flatMap((result) => result.records);
    const acceptedCompletionById = new Map(
      acceptedCompletionRecords.map((record) => [record.responsibilityId, record]),
    );
    responsibilityReads = responsibilityReads.map((read) => {
      const readSeedIds = new Set(read.inventorySeeds.map((seed) => seed.inventorySeedId));
      const existingIds = new Set(read.model.output.responsibilities.map((item) => item.responsibilityId));
      const responsibilities = read.model.output.responsibilities.map(
        (item) => acceptedCompletionById.get(item.responsibilityId) ?? item,
      );
      for (const [id, record] of acceptedCompletionById) {
        if (readSeedIds.has(id) && !existingIds.has(id)) responsibilities.push(record);
      }
      const output = { ...read.model.output, responsibilities };
      const validation = validateResponsibilityRead({
        output,
        documentId: args.documentId,
        segment: responsibilityParentSegment(read.segment),
        fileType: doc.fileType,
        fileName: doc.fileName,
        allCoveredChunkIds: coveredChunkIds,
        inventorySeeds: read.inventorySeeds,
        chunks: chunks.map((chunk) => ({ id: chunk.id, documentId: args.documentId, rawText: chunk.rawText })),
      });
      const relevantExecutions = completionResults
        .filter((result) => result.seedIds.some((id) => readSeedIds.has(id)))
        .flatMap((result) => completionExecutions.get(result.batchIndex) ?? []);
      return {
        ...read,
        model: { ...read.model, output },
        validation,
        modelRunIds: [...read.modelRunIds, ...relevantExecutions.map((item) => item.modelRunId)],
        contextPackIds: [...read.contextPackIds, ...relevantExecutions.map((item) => item.contextPackId)],
        executions: [...read.executions, ...relevantExecutions.map((item) => item.execution)],
        inventoryMatchAudit: {
          ...read.inventoryMatchAudit,
          mergeReadyInventoryIds: validation.completeElementIds,
          mergeReadyInventoryCount: validation.completeElementIds.length,
          incompleteSeedIds: [...readSeedIds].filter((id) => !validation.completeElementIds.includes(id)),
        },
      };
    });
    const responsibilityCompletionAudit = {
      promptVersion: RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
      residualSeedIds: residualSeeds.map((seed) => seed.inventorySeedId),
      residualSeedCount: residualSeeds.length,
      batchManifest: completionPack.batches.map((batch) => ({
        batchIndex: batch.batchIndex,
        seedIds: batch.seedIds,
        estimatedInputTokens: batch.estimatedInputTokens,
        estimatedOutputTokens: batch.estimatedOutputTokens,
        estimatedCostUsd: batch.estimatedCostUsd,
      })),
      estimatedCalls: completionPack.estimatedCalls,
      estimatedInputTokens: completionPack.estimatedInputTokens,
      estimatedOutputTokens: completionPack.estimatedOutputTokens,
      estimatedCostUsd: completionPack.estimatedCostUsd,
      unscheduledIds: completionPack.unscheduledIds,
      outcomes: [
        ...completionResults.flatMap((result) => result.outcomes.map((outcome) => ({
          ...outcome,
          batchIndex: result.batchIndex,
          attempts: result.attempts,
          failure: result.failure,
        }))),
        ...completionPack.unscheduledIds.map((responsibilityId) => ({
          responsibilityId,
          status: 'budget_exhausted' as const,
          reasons: ['completion_not_scheduled_within_frozen_budget'],
          batchIndex: null,
          attempts: 0,
          failure: 'budget_exhausted',
        })),
      ],
      executions: [...completionExecutions.entries()]
        .sort(([a], [b]) => a - b)
        .flatMap(([batchIndex, executions]) => executions.map((execution, attemptIndex) => ({
          batchIndex,
          attempt: attemptIndex + 1,
          modelRunId: execution.modelRunId,
          contextPackId: execution.contextPackId,
          routeId: execution.routeId,
          provider: execution.provider,
          model: execution.model,
          ...execution.execution,
        }))),
    };

    const responsibilityAuditChunks = chunks.map((chunk) => ({
      id: chunk.id,
      documentId: args.documentId,
      rawText: chunk.rawText,
    }));
    const auditResponsibilityOmissions = () =>
      (args.orchestrationDependencies?.findOmissions ?? findResponsibilityOmissions)({
        chunks: responsibilityAuditChunks,
        elements: responsibilityReads.flatMap((read) => read.validation.elements),
        inventorySeeds: responsibilityInventorySeeds,
        fileType: doc.fileType,
        fileName: doc.fileName,
      });
    const initialOmissions = auditResponsibilityOmissions();
    const omissionRetries: Array<{
      chunkId: string;
      selectedSpanCount: number;
      selectedSpans: ReturnType<typeof buildResponsibilitySelectedSpanAudit>;
      acceptedCount: number;
      skipped: string | null;
      preOmissionCount: number;
      postOmissionCount: number;
      fieldAudits: ReturnType<typeof canonicalizeForcedResponsibilityOutput>['audits'];
    }> = [];
    const sourceMetadataForChunk = (chunkId: string) => {
      const segments = segmentation.segments.filter((segment) => segment.chunkIds.includes(chunkId));
      return {
        sourceShapes: [...new Set(segments.map((segment) => segment.shape))],
        sourceSegmentIds: segments.map((segment) => segment.segmentId),
      };
    };
    const omissionRetryScheduler = new ResponsibilityOmissionRetryScheduler();
    while (true) {
      const currentOmissions = auditResponsibilityOmissions().filter(
        (omission) => omission.omissionClass === 'inventory_detection_gap',
      );
      const decision = omissionRetryScheduler.next({
        omissions: currentOmissions,
        chunks: responsibilityAuditChunks,
        sourceReadChunkIds: new Set(
          responsibilityReads.flatMap((read) => read.segment.chunkIds),
        ),
      });
      if (decision.kind === 'done') break;
      const { chunkId } = decision;
      const focusedOmissions = decision.omissions;
      let forcedSpans: ForcedResponsibilitySpan[];
      try {
        forcedSpans = bindForcedResponsibilitySpans(
          [...focusedOmissions].sort((a, b) => a.spanIndex - b.spanIndex),
        );
      } catch {
        omissionRetries.push({
          chunkId,
          selectedSpanCount: focusedOmissions.length,
          selectedSpans: buildResponsibilitySelectedSpanAudit({
            selected: focusedOmissions,
            finalOmissions: currentOmissions,
            preRecordCount: responsibilityReads.reduce(
              (sum, read) => sum + read.validation.elements.length,
              0,
            ),
            postRecordCount: responsibilityReads.reduce(
              (sum, read) => sum + read.validation.elements.length,
              0,
            ),
            skipped: 'raw_source_binding_failed',
            ...sourceMetadataForChunk(chunkId),
            inResponsibilityBaseRead: true,
          }),
          acceptedCount: 0,
          skipped: 'raw_source_binding_failed',
          preOmissionCount: currentOmissions.length,
          postOmissionCount: currentOmissions.length,
          fieldAudits: [],
        });
        omissionRetryScheduler.recordAttempt(chunkId, 'retry_failed');
        continue;
      }
      const sourceRead = responsibilityReads.find((read) => read.segment.chunkIds.includes(chunkId));
      const chunk = chunkById.get(chunkId);
      if (decision.kind === 'no_source_read' || !sourceRead || !chunk) {
        const sourceMetadata = sourceMetadataForChunk(chunkId);
        omissionRetries.push({
          chunkId,
          selectedSpanCount: focusedOmissions.length,
          selectedSpans: buildResponsibilitySelectedSpanAudit({
            selected: forcedSpans,
            finalOmissions: currentOmissions,
            preRecordCount: responsibilityReads.reduce(
              (sum, read) => sum + read.validation.elements.length,
              0,
            ),
            postRecordCount: responsibilityReads.reduce(
              (sum, read) => sum + read.validation.elements.length,
              0,
            ),
            skipped: 'no_source_read',
            ...sourceMetadata,
            inResponsibilityBaseRead: false,
          }),
          acceptedCount: 0,
          skipped: 'no_source_read',
          preOmissionCount: decision.preOmissionCount,
          postOmissionCount: decision.preOmissionCount,
          fieldAudits: [],
        });
        omissionRetryScheduler.recordAttempt(chunkId, 'retry_failed');
        continue;
      }
      try {
        responsibilityPostPassBudget.reserveOmissionRetry(chunkId);
        const shardIndex = responsibilityShards.findIndex(
          (segment) => segment.segmentId === sourceRead.segment.segmentId,
        );
        if (shardIndex < 0) {
          throw new Error(`Responsibility retry shard is not registered: ${sourceRead.segment.segmentId}`);
        }
        const retryModel = await runResponsibilityReadModel({
          db,
          client,
          doc,
          chunks: [chunk],
          triggerRunId: args.triggerRunId,
          mapId: pending.mapId,
          segment: sourceRead.segment,
          budget: readerBudget,
          focusedSpans: forcedSpans,
        });
        const retryInventoryMatch = completeAndMatchResponsibilityInventory({
          inventorySeeds: sourceRead.inventorySeeds.filter((seed) => seed.chunkId === chunk.id),
          proposals: retryModel.output,
          chunks: [{ id: chunk.id, documentId: args.documentId, rawText: chunk.rawText }],
        });
        retryModel.output = retryInventoryMatch.output;
        sourceRead.inventorySeeds = canonicalResponsibilityInventory({
          seeds: [
            ...sourceRead.inventorySeeds.filter((seed) => seed.chunkId !== chunk.id),
            ...retryInventoryMatch.inventorySeeds,
          ],
          chunks: sourceRead.segment.chunkIds.map((id) => ({ id })),
        });
        sourceRead.inventoryAuditParents.push(...retryInventoryMatch.inventoryAuditParents);
        responsibilityInventoryAuditParents.push(...retryInventoryMatch.inventoryAuditParents);
        responsibilityInventorySeeds = canonicalResponsibilityInventory({
          seeds: responsibilityReads.flatMap((read) => read.inventorySeeds),
          chunks,
        });
        const retryValidation = validateResponsibilityRead({
          output: retryModel.output,
          documentId: args.documentId,
          segment: responsibilityParentSegment(sourceRead.segment),
          fileType: doc.fileType,
          fileName: doc.fileName,
          allCoveredChunkIds: coveredChunkIds,
          inventorySeeds: sourceRead.inventorySeeds.filter((seed) => seed.chunkId === chunk.id),
          chunks: [{ id: chunk.id, documentId: args.documentId, rawText: chunk.rawText }],
        });
        const mergedRetryOutput = {
          ...sourceRead.model.output,
          responsibilities: mergeResponsibilityRecordsByInventoryId(
            sourceRead.model.output.responsibilities,
            retryModel.output.responsibilities,
          ),
        };
        const baseCompleteIds = new Set(sourceRead.validation.completeElementIds);
        const mergedRetryValidation = validateResponsibilityRead({
          output: mergedRetryOutput,
          documentId: args.documentId,
          segment: responsibilityParentSegment(sourceRead.segment),
          fileType: doc.fileType,
          fileName: doc.fileName,
          allCoveredChunkIds: coveredChunkIds,
          inventorySeeds: sourceRead.inventorySeeds,
          chunks: responsibilityAuditChunks,
        });
        const mergedRetry = {
          validation: mergedRetryValidation,
          acceptedElementIds: mergedRetryValidation.completeElementIds.filter(
            (id) => !baseCompleteIds.has(id),
          ),
          acceptedCount: mergedRetryValidation.completeElementIds.filter(
            (id) => !baseCompleteIds.has(id),
          ).length,
        };
        const finalFieldAudits = finalizeForcedResponsibilityAudits({
          audits: retryModel.forcedSpanAudits,
          selected: forcedSpans,
          durableAcceptedElementIds: new Set(mergedRetry.acceptedElementIds),
          durableIdByForcedId: new Map(
            Object.entries(retryInventoryMatch.audit.matchedProposalInventoryIds),
          ),
          validation: retryValidation,
          chunks: [{ id: chunk.id, documentId: args.documentId, rawText: chunk.rawText }],
          fileType: doc.fileType,
          fileName: doc.fileName,
        });
        sourceRead.model.output = mergedRetryOutput;
        sourceRead.validation = mergedRetry.validation;
        sourceRead.inventoryMatchAudit = {
          ...sourceRead.inventoryMatchAudit,
          sourceInventoryIds: sourceRead.inventorySeeds.map((seed) => seed.inventorySeedId),
          sourceInventoryCount: sourceRead.inventorySeeds.length,
          modelDiscoveredInventoryIds: [
            ...new Set([
              ...sourceRead.inventoryMatchAudit.modelDiscoveredInventoryIds,
              ...retryInventoryMatch.audit.modelDiscoveredInventoryIds,
            ]),
          ],
          modelDiscoveredInventoryCount: new Set([
            ...sourceRead.inventoryMatchAudit.modelDiscoveredInventoryIds,
            ...retryInventoryMatch.audit.modelDiscoveredInventoryIds,
          ]).size,
          unmatchedProposalIds: [
            ...new Set([
              ...sourceRead.inventoryMatchAudit.unmatchedProposalIds,
              ...retryInventoryMatch.audit.unmatchedProposalIds,
            ]),
          ],
          matchedProposalInventoryIds: {
            ...sourceRead.inventoryMatchAudit.matchedProposalInventoryIds,
            ...retryInventoryMatch.audit.matchedProposalInventoryIds,
          },
          mergeReadyInventoryIds: mergedRetry.validation.completeElementIds,
          mergeReadyInventoryCount: mergedRetry.validation.completeElementIds.length,
          incompleteSeedIds: sourceRead.inventorySeeds
            .map((seed) => seed.inventorySeedId)
            .filter((id) => !mergedRetry.validation.completeElementIds.includes(id)),
        };
        sourceRead.modelRunIds.push(retryModel.modelRunId);
        sourceRead.contextPackIds.push(retryModel.contextPackId);
        sourceRead.executions.push(retryModel.execution);
        const postOmissions = auditResponsibilityOmissions();
        const preRecordCount =
          responsibilityReads.reduce((sum, read) => sum + read.validation.elements.length, 0) -
          mergedRetry.acceptedCount;
        const postRecordCount = responsibilityReads.reduce(
          (sum, read) => sum + read.validation.elements.length,
          0,
        );
        const skipped = mergedRetry.acceptedCount === 0 ? 'zero_accept' : null;
        omissionRetries.push({
          chunkId,
          selectedSpanCount: focusedOmissions.length,
          selectedSpans: buildResponsibilitySelectedSpanAudit({
            selected: forcedSpans,
            finalOmissions: postOmissions,
            preRecordCount,
            postRecordCount,
            skipped,
            ...sourceMetadataForChunk(chunkId),
            inResponsibilityBaseRead: true,
            fieldAudits: finalFieldAudits,
          }),
          acceptedCount: mergedRetry.acceptedCount,
          skipped,
          preOmissionCount: currentOmissions.length,
          postOmissionCount: postOmissions.length,
          fieldAudits: finalFieldAudits,
        });
        omissionRetryScheduler.recordAttempt(
          chunkId,
          mergedRetry.acceptedCount === 0 ? 'zero_accept' : 'accepted',
        );
      } catch (error) {
        const budgetExhausted =
          error instanceof SourceReaderBudgetExceededError ||
          (error instanceof Error && error.message.includes('responsibility-post-pass-budget'));
        omissionRetries.push({
          chunkId,
          selectedSpanCount: focusedOmissions.length,
          selectedSpans: buildResponsibilitySelectedSpanAudit({
            selected: forcedSpans,
            finalOmissions: currentOmissions,
            preRecordCount: responsibilityReads.reduce(
              (sum, read) => sum + read.validation.elements.length,
              0,
            ),
            postRecordCount: responsibilityReads.reduce(
              (sum, read) => sum + read.validation.elements.length,
              0,
            ),
            skipped: budgetExhausted ? 'budget_exhausted' : 'retry_failed',
            ...sourceMetadataForChunk(chunkId),
            inResponsibilityBaseRead: true,
          }),
          acceptedCount: 0,
          skipped: budgetExhausted ? 'budget_exhausted' : 'retry_failed',
          preOmissionCount: currentOmissions.length,
          postOmissionCount: currentOmissions.length,
          fieldAudits: [],
        });
        omissionRetryScheduler.recordAttempt(
          chunkId,
          budgetExhausted ? 'budget_exhausted' : 'retry_failed',
        );
        if (budgetExhausted) continue;
      }
    }

    // F4: every stage's correction seam is collected here so exactly one audit is persisted.
    const responsibilityCorrectionSeams: Array<{
      stage: 'exhaustive' | 'late';
      corrections: readonly FinalRecordCorrection[];
    }> = [exhaustiveCorrectionSeam];
    const completionHandledIds = new Set(responsibilityCompletionAudit.residualSeedIds);
    const lateResidualSeeds = lateResidualResponsibilitySeeds({
      seeds: responsibilityInventorySeeds,
      handledIds: completionHandledIds,
      completeIds: new Set(
        responsibilityReads.flatMap((read) => read.validation.completeElementIds),
      ),
    });
    if (lateResidualSeeds.length > 0) {
      const latePackingConfig = await loadResponsibilityCompletionPackingConfig({
        db,
        budget: readerBudget,
        reserveQuoteRepair: responsibilityPostPassBudget.limits.maxQuoteRepairsPerSource > 0,
      });
      const batchOffset = responsibilityCompletionAudit.batchManifest.length;
      const lateExecutions = new Map<number, ResponsibilityCompletionExecution[]>();
      const lateRun = await runLateResponsibilityCompletion({
        seeds: responsibilityInventorySeeds,
        handledIds: completionHandledIds,
        completeIds: new Set(
          responsibilityReads.flatMap((read) => read.validation.completeElementIds),
        ),
        pack: latePackingConfig.pack,
        budget: readerBudget,
        concurrency: readerBudget.limits.maxConcurrency,
        batchOffset,
        runBatch: async (batch) => {
          const execution = await runResponsibilityCompletionModel({
            db,
            client,
            doc,
            mapId: pending.mapId,
            triggerRunId: args.triggerRunId,
            batch,
          });
          const list = lateExecutions.get(batch.batchIndex) ?? [];
          list.push(execution);
          lateExecutions.set(batch.batchIndex, list);
          return execution.output;
        },
        validateCompletion: (record) => {
          const seed = lateResidualSeeds.find(
            (item) => item.inventorySeedId === record.responsibilityId,
          );
          const read = seed
            ? responsibilityReads.find((item) => item.segment.chunkIds.includes(seed.chunkId))
            : undefined;
          if (!seed || !read) return { complete: false, reasons: ['seed_or_source_read_missing'] };
          const validation = validateResponsibilityRead({
            output: { summary: 'Late detected responsibility completion.', responsibilities: [record] },
            documentId: args.documentId,
            segment: responsibilityParentSegment(read.segment),
            fileType: doc.fileType,
            fileName: doc.fileName,
            allCoveredChunkIds: coveredChunkIds,
            inventorySeeds: [seed],
            chunks: responsibilityAuditChunks,
          });
          return {
            complete: validation.completeElementIds.includes(record.responsibilityId),
            reasons: [
              ...validation.diagnostics.map((item) => item.detail),
              ...validation.incompleteInventoryAudit.map((item) => item.decisionReason),
            ],
          };
        },
      });
      const { pack: latePack, results: lateResults, final: lateFinal } = lateRun;
      responsibilityCorrectionSeams.push(lateRun.seam);
      const lateAcceptedById = new Map(
        lateFinal.records.map((record) => [record.responsibilityId, record]),
      );
      responsibilityReads = responsibilityReads.map((read) => {
        const readSeedIds = new Set(read.inventorySeeds.map((seed) => seed.inventorySeedId));
        const byId = new Map(
          read.model.output.responsibilities.map((record) => [record.responsibilityId, record]),
        );
        for (const [id, record] of lateAcceptedById) {
          if (readSeedIds.has(id)) byId.set(id, record);
        }
        const output = { ...read.model.output, responsibilities: [...byId.values()] };
        const validation = validateResponsibilityRead({
          output,
          documentId: args.documentId,
          segment: responsibilityParentSegment(read.segment),
          fileType: doc.fileType,
          fileName: doc.fileName,
          allCoveredChunkIds: coveredChunkIds,
          inventorySeeds: read.inventorySeeds,
          chunks: responsibilityAuditChunks,
        });
        const executions = lateResults
          .filter((result) => result.seedIds.some((id) => readSeedIds.has(id)))
          .flatMap((result) => lateExecutions.get(result.batchIndex) ?? []);
        return {
          ...read,
          model: { ...read.model, output },
          validation,
          modelRunIds: [...read.modelRunIds, ...executions.map((item) => item.modelRunId)],
          contextPackIds: [...read.contextPackIds, ...executions.map((item) => item.contextPackId)],
          executions: [...read.executions, ...executions.map((item) => item.execution)],
          inventoryMatchAudit: {
            ...read.inventoryMatchAudit,
            mergeReadyInventoryIds: validation.completeElementIds,
            mergeReadyInventoryCount: validation.completeElementIds.length,
            incompleteSeedIds: [...readSeedIds].filter(
              (id) => !validation.completeElementIds.includes(id),
            ),
          },
        };
      });
      responsibilityCompletionAudit.residualSeedIds.push(
        ...lateResidualSeeds.map((seed) => seed.inventorySeedId),
      );
      responsibilityCompletionAudit.residualSeedCount += lateResidualSeeds.length;
      responsibilityCompletionAudit.batchManifest.push(
        ...latePack.batches.map((batch) => ({
          batchIndex: batch.batchIndex + batchOffset,
          seedIds: batch.seedIds,
          estimatedInputTokens: batch.estimatedInputTokens,
          estimatedOutputTokens: batch.estimatedOutputTokens,
          estimatedCostUsd: batch.estimatedCostUsd,
        })),
      );
      responsibilityCompletionAudit.estimatedCalls += latePack.estimatedCalls;
      responsibilityCompletionAudit.estimatedInputTokens += latePack.estimatedInputTokens;
      responsibilityCompletionAudit.estimatedOutputTokens += latePack.estimatedOutputTokens;
      responsibilityCompletionAudit.estimatedCostUsd += latePack.estimatedCostUsd;
      responsibilityCompletionAudit.unscheduledIds.push(...latePack.unscheduledIds);
      responsibilityCompletionAudit.outcomes.push(...lateFinal.outcomes);
      responsibilityCompletionAudit.executions.push(
        ...[...lateExecutions.entries()]
          .sort(([a], [b]) => a - b)
          .flatMap(([batchIndex, executions]) => executions.map((execution, attemptIndex) => ({
            batchIndex: batchIndex + batchOffset,
            attempt: attemptIndex + 1,
            modelRunId: execution.modelRunId,
            contextPackId: execution.contextPackId,
            routeId: execution.routeId,
            provider: execution.provider,
            model: execution.model,
            ...execution.execution,
          }))),
      );
    }

    const responsibilityQuoteRepair = {
      attempted: false,
      selectedSegmentId: null as string | null,
      selectedSegmentIds: [] as string[],
      eligibleCount: 0,
      accepted: false,
      skipped: 'no_eligible_root_quote_failure' as string | null,
      rootQuoteFailuresBefore: 0,
      rootQuoteFailuresAfter: 0,
      fieldFailuresBefore: 0,
      fieldFailuresAfter: 0,
      fieldRepairs: [] as Array<{
        responsibilityId: string;
        chunkId: string;
        quoteSha256: string;
        repairStatus: 'selected' | 'repaired' | 'rejected';
        decisionReason: string;
      }>,
      groundedCandidates: [] as Array<{
        responsibilityId: string;
        failedQuote: string;
        immutableFields: Record<string, unknown>;
        candidates: GroundedResponsibilityQuoteCandidate[];
        returnedSelection: string | null;
        returnedSelectionSha256: string | null;
        decisionReason: string | null;
      }>,
    };
    const combinedRepairPlan = (args.orchestrationDependencies?.buildCombinedRepairPlan ?? buildResponsibilityCombinedRepairPlan)({
      reads: responsibilityReads,
      chunks,
      maxFieldRepairs: 0,
    });
    if ('preparedReads' in combinedRepairPlan && Array.isArray(combinedRepairPlan.preparedReads)) {
      responsibilityReads = combinedRepairPlan.preparedReads as typeof responsibilityReads;
    }
    const quoteRepairRead = (args.orchestrationDependencies?.selectQuoteRepairRead ?? selectResponsibilityQuoteRepairRead)(responsibilityReads);
    if (quoteRepairRead && combinedRepairPlan.records.length > 0) {
      const eligibleDiagnostics = responsibilityReads.flatMap((read) =>
        read.validation.diagnostics.filter((item) => item.failureClass === 'quote_mismatch'),
      );
      responsibilityQuoteRepair.selectedSegmentId =
        combinedRepairPlan.selectedSegmentIds[0] ?? null;
      responsibilityQuoteRepair.selectedSegmentIds =
        combinedRepairPlan.selectedSegmentIds;
      responsibilityQuoteRepair.eligibleCount = eligibleDiagnostics.length;
      const fieldRepairIds = combinedRepairPlan.fieldRepairRequests.map(
        (item) => item.responsibilityId,
      );
      responsibilityQuoteRepair.fieldFailuresBefore = fieldRepairIds.length;
      responsibilityQuoteRepair.fieldFailuresAfter = fieldRepairIds.length;
      responsibilityQuoteRepair.fieldRepairs = responsibilityReads
        .flatMap((read) => read.validation.incompleteInventoryAudit)
        .filter((item) => fieldRepairIds.includes(item.elementId))
        .map((item) => ({
          responsibilityId: item.elementId,
          chunkId: item.chunkId,
          quoteSha256: item.quoteSha256,
          repairStatus: 'selected' as const,
          decisionReason: item.decisionReason,
        }));
      responsibilityQuoteRepair.rootQuoteFailuresBefore = eligibleDiagnostics.length;
      responsibilityQuoteRepair.rootQuoteFailuresAfter = eligibleDiagnostics.length;
      try {
        responsibilityPostPassBudget.reserveQuoteRepair();
        responsibilityQuoteRepair.attempted = true;
        const quoteRepairRecords = combinedRepairPlan.records;
        const quoteRepairCandidates = combinedRepairPlan.quoteRepairCandidates;
        const fieldRepairRequests = combinedRepairPlan.fieldRepairRequests;
        responsibilityQuoteRepair.groundedCandidates = quoteRepairCandidates.map((item) => ({
          ...item,
          immutableFields: item.immutableFields as Record<string, unknown>,
          returnedSelection: null,
          returnedSelectionSha256: null,
          decisionReason: null,
        }));
        const repairModel = await runResponsibilityReadModel({
          db,
          client,
          doc,
          chunks: combinedRepairPlan.chunkIds.flatMap((chunkId) => {
            const chunk = chunkById.get(chunkId);
            return chunk ? [chunk] : [];
          }),
          triggerRunId: args.triggerRunId,
          mapId: pending.mapId,
          segment: {
            ...responsibilityParentSegment(quoteRepairRead.segment),
            segmentId: 'responsibility_combined_repair',
            title: 'Combined responsibility repair',
            chunkIds: combinedRepairPlan.chunkIds,
          },
          budget: readerBudget,
          quoteRepairRecords,
          quoteRepairCandidates,
          fieldRepairRequests,
        });
        for (const repaired of repairModel.output.responsibilities) {
          const audit = responsibilityQuoteRepair.groundedCandidates.find(
            (item) => item.responsibilityId === repaired.responsibilityId,
          );
          if (audit) {
            audit.returnedSelection = repaired.evidenceQuote;
            audit.returnedSelectionSha256 = createHash('sha256')
              .update(repaired.evidenceQuote)
              .digest('hex');
          }
        }
        for (const read of responsibilityReads) {
          if (!combinedRepairPlan.selectedSegmentIds.includes(read.segment.segmentId)) continue;
          read.modelRunIds.push(repairModel.modelRunId);
          read.contextPackIds.push(repairModel.contextPackId);
          read.executions.push(repairModel.execution);
        }
        {
          const repairedReads = responsibilityReads.map((read) => {
            const output = mergeCombinedResponsibilityRepairOutput({
              original: read.model.output,
              repaired: repairModel.output,
            });
            return {
              read,
              output,
              validation: validateResponsibilityRead({
                output,
                documentId: args.documentId,
                segment: responsibilityParentSegment(read.segment),
                fileType: doc.fileType,
                fileName: doc.fileName,
                allCoveredChunkIds: coveredChunkIds,
                inventorySeeds: read.inventorySeeds,
                chunks: chunks.map((chunk) => ({
                  id: chunk.id,
                  documentId: args.documentId,
                  rawText: chunk.rawText,
                })),
              }),
            };
          });
          const failuresAfter = repairedReads.reduce(
            (sum, item) =>
              sum +
              item.validation.diagnostics.filter(
                (diagnostic) => diagnostic.failureClass === 'quote_mismatch',
              ).length,
            0,
          );
          responsibilityQuoteRepair.rootQuoteFailuresAfter = failuresAfter;
          responsibilityQuoteRepair.fieldFailuresAfter =
            repairedReads.reduce(
              (sum, item) => sum + item.validation.incompleteInventoryAudit.length,
              0,
            );
          const remainingIncomplete = new Set(
            repairedReads.flatMap((item) =>
              item.validation.incompleteInventoryAudit.map((audit) => audit.elementId),
            ),
          );
          responsibilityQuoteRepair.fieldRepairs = responsibilityQuoteRepair.fieldRepairs.map(
            (item) => ({
              ...item,
              repairStatus: remainingIncomplete.has(item.responsibilityId)
                ? 'rejected'
                : 'repaired',
              decisionReason: remainingIncomplete.has(item.responsibilityId)
                ? 'combined_repair_remained_incomplete'
                : 'combined_repair_completed',
            }),
          );
          if (
            failuresAfter < eligibleDiagnostics.length ||
            repairedReads.reduce((sum, item) => sum + item.validation.elements.length, 0) >
              responsibilityReads.reduce(
                (sum, read) => sum + read.validation.elements.length,
                0,
              )
          ) {
            for (const repairedRead of repairedReads) {
              repairedRead.read.model.output = repairedRead.output;
              repairedRead.read.validation = repairedRead.validation;
              repairedRead.read.inventoryMatchAudit = refreshResponsibilityInventoryMatchAudit({
                audit: repairedRead.read.inventoryMatchAudit,
                completeElementIds: repairedRead.validation.completeElementIds,
              });
            }
            responsibilityQuoteRepair.accepted = true;
            responsibilityQuoteRepair.skipped = null;
            for (const audit of responsibilityQuoteRepair.groundedCandidates) {
              audit.decisionReason = audit.returnedSelection
                ? 'accepted_strict_exact_improvement'
                : 'not_returned';
            }
          } else {
            responsibilityQuoteRepair.skipped = 'no_strict_exact_improvement';
            for (const audit of responsibilityQuoteRepair.groundedCandidates) {
              audit.decisionReason = audit.returnedSelection
                ? 'rejected_no_strict_exact_improvement'
                : 'not_returned';
            }
          }
        }
      } catch (error) {
        responsibilityQuoteRepair.skipped = /budget|allowance/i.test(
          error instanceof Error ? error.message : '',
        )
          ? 'budget_exhausted'
          : 'repair_failed';
        for (const audit of responsibilityQuoteRepair.groundedCandidates) {
          audit.decisionReason = responsibilityQuoteRepair.skipped;
        }
      }
    }
    const omissions = auditResponsibilityOmissions();

    const finalizedProcessReads = processReads.map((read) => ({
      ...read,
      map: workflowToProcessStructureMap({
        output: read.validation.map,
        chunks: read.segmentChunks,
        title: read.segment.title,
        segment: read.segment,
        documentShape: segmentation.documentShape,
        prefixIds: processSegments.length > 1,
      }),
    }));
    const sourceInventoryOrder = new Map(
      responsibilityInventorySeeds.map((seed, index) => [seed.inventorySeedId, index]),
    );
    const mergeReadyInventory = responsibilityReads
      .flatMap((read) => responsibilityMergeEligibleElements(read.validation))
      .sort(
        (a, b) =>
          (sourceInventoryOrder.get(a.elementId) ?? Number.MAX_SAFE_INTEGER) -
            (sourceInventoryOrder.get(b.elementId) ?? Number.MAX_SAFE_INTEGER) ||
          a.elementId.localeCompare(b.elementId),
      );
    const mergeReadySeen = new Set<string>();
    for (const element of mergeReadyInventory) {
      if (!sourceInventoryOrder.has(element.elementId)) {
        throw new Error(`Merge-ready responsibility has no source inventory seed: ${element.elementId}`);
      }
      if (mergeReadySeen.has(element.elementId)) {
        throw new Error(`Merge-ready responsibility maps to its seed more than once: ${element.elementId}`);
      }
      mergeReadySeen.add(element.elementId);
    }

    const structureMap: SourceStructureMap = {
      documentShape: segmentation.documentShape,
      summary: segmentation.summary,
      segments: [
        ...new Map(
          [...segmentation.segments, ...responsibilityBaseReadPlan.syntheticSegments].map(
            (segment) => [segment.segmentId, segment] as const,
          ),
        ).values(),
      ].sort((a, b) => {
        const firstChunkIndex = (segment: SourceStructureSegment) =>
          Math.min(
            ...segment.chunkIds.map((chunkId) =>
              chunks.findIndex((chunk) => chunk.id === chunkId),
            ),
          );
        return firstChunkIndex(a) - firstChunkIndex(b) || a.segmentId.localeCompare(b.segmentId);
      }),
      elements: [
        ...finalizedProcessReads.flatMap((read) => read.map.elements),
        ...mergeReadyInventory,
      ],
      relations: finalizedProcessReads.flatMap((read) => read.map.relations),
      lanes: finalizedProcessReads.flatMap((read) => read.map.lanes),
      paths: finalizedProcessReads.flatMap((read) => read.map.paths),
    };
    assertUniqueResponsibilityElementIds(structureMap.elements);
    const workflowOutputs = processReads.map((read) => read.validation.map);
    const droppedCount =
      processReads.reduce((sum, read) => sum + read.validation.droppedCount, 0) +
      Math.max(0, responsibilityInventorySeeds.length - mergeReadyInventory.length);
    const keptCount =
      processReads.reduce((sum, read) => sum + read.validation.keptCount, 0) +
      mergeReadyInventory.length;
    const status: WorkflowMapStatus =
      segmentation.status === 'degraded' ||
      processReads.some((read) => read.validation.status === 'degraded') ||
      responsibilityInventoryRequiresDegradedStatus({
        sourceInventoryCount: responsibilityInventorySeeds.length,
        mergeReadyInventoryCount: mergeReadyInventory.length,
        unscheduledCount: responsibilityCompletionAudit.unscheduledIds.length,
        finalGapCount: omissions.length,
      }) ||
      responsibilityReads.some(
        (read) =>
          read.validation.inventoryElements.length > read.validation.elements.length ||
          read.validation.diagnostics.length > 0 ||
          read.validation.crossSegmentCitations.length /
            Math.max(1, read.validation.elements.length) >
            0.2,
      )
        ? 'degraded'
        : 'validated';
    const mapKind: WorkflowReadOutput['mapKind'] = processReads.some(
      (read) => read.validation.map.mapKind === 'workflow',
    )
      ? 'workflow'
      : 'reference';
    const modelRunIds = [
      ...segmentationModels.map((model) => model.modelRunId),
      ...processReads.flatMap((read) => read.modelRunIds),
      ...responsibilityReads.flatMap((read) => read.modelRunIds),
    ];
    const contextPackIds = [
      ...segmentationModels.map((model) => model.contextPackId),
      ...processReads.flatMap((read) => read.contextPackIds),
      ...responsibilityReads.flatMap((read) => read.contextPackIds),
    ];
    const lastModelRunId = modelRunIds.at(-1) ?? null;
    const lastContextPackId = contextPackIds.at(-1) ?? null;
    const validationJson = {
      pipelineVersion: SOURCE_READER_PIPELINE_VERSION,
      segmentation: segmentation.validationJson,
      segmentationAttempts: segmentationValidations.map((validation) => validation.validationJson),
      processSegments: processReads.map((read) => ({
        segmentId: read.segment.segmentId,
        promptVersion: WORKFLOW_READ_PROMPT_VERSION,
        ...read.validation.validationJson,
        quoteRepair: read.repair,
      })),
      responsibilitySegments: responsibilityReads.map((read) => ({
        segmentId: responsibilityParentSegment(read.segment).segmentId,
        executionShardId: read.segment.segmentId,
        promptVersion: RESPONSIBILITY_READ_PROMPT_VERSION,
        keptCount: read.validation.elements.length,
        sourceInventoryCount: read.inventoryMatchAudit.sourceInventoryCount,
        sourceInventoryIds: read.inventoryMatchAudit.sourceInventoryIds,
        modelDiscoveredInventoryCount: read.inventoryMatchAudit.modelDiscoveredInventoryCount,
        modelDiscoveredInventoryIds: read.inventoryMatchAudit.modelDiscoveredInventoryIds,
        mergeReadyInventoryCount: read.inventoryMatchAudit.mergeReadyInventoryCount,
        mergeReadyInventoryIds: read.inventoryMatchAudit.mergeReadyInventoryIds,
        unmatchedProposalIds: read.inventoryMatchAudit.unmatchedProposalIds,
        matchedProposalInventoryIds: read.inventoryMatchAudit.matchedProposalInventoryIds,
        incompleteSeedIds: read.inventoryMatchAudit.incompleteSeedIds,
        completeCount: read.validation.elements.length,
        mergeEligibleCount: read.validation.completeElementIds.length,
        droppedCount: read.validation.diagnostics.length,
        primaryCount: read.validation.primaryCount,
        crossSegmentCitations: read.validation.crossSegmentCitations,
        rawOutputAudit: responsibilityRawAuditArtifact(read.model.output),
        executions: read.executions,
        diagnostics: read.validation.diagnostics,
        incompleteInventoryAudit: read.validation.incompleteInventoryAudit,
        deterministicExpansionAudit: read.validation.expansionAudit,
        failureTaxonomyCounts: responsibilityFailureTaxonomyCounts(read.validation),
      })),
      responsibilityInventory: {
        sourceInventoryCount: responsibilityInventorySeeds.length,
        sourceInventoryIds: responsibilityInventorySeeds.map((seed) => seed.inventorySeedId),
        auditOnlyParents: [...responsibilityInventoryAuditParents.reduce((byId, parent) => {
          const prior = byId.get(parent.inventorySeedId);
          if (prior && JSON.stringify(prior) !== JSON.stringify(parent)) {
            throw new Error(`Conflicting responsibility audit parent: ${parent.inventorySeedId}`);
          }
          if (!prior) byId.set(parent.inventorySeedId, parent);
          return byId;
        }, new Map<string, (typeof responsibilityInventoryAuditParents)[number]>()).values()],
        mergeReadyInventoryCount: mergeReadyInventory.length,
        mergeReadyInventoryIds: mergeReadyInventory.map((element) => element.elementId),
        incompleteSeedIds: responsibilityInventorySeeds
          .map((seed) => seed.inventorySeedId)
          .filter((id) => !mergeReadySeen.has(id)),
        finalGaps: omissions.map((omission) => ({
          chunkId: omission.chunkId,
          spanIndex: omission.spanIndex,
          omissionClass: omission.omissionClass,
          sourceSpanSha256: createHash('sha256').update(omission.sourceSpan).digest('hex'),
        })),
      },
      responsibilityCompletion: responsibilityCompletionAudit,
      // F4. One audit for the whole final-record correction seam: counts, seed IDs, reason
      // codes, source-span hashes and the execution refs of the stages that produced the
      // corrected candidates. Never source text.
      responsibilityFinalRecordCorrection: buildResponsibilityFinalRecordCorrectionAudit({
        seams: responsibilityCorrectionSeams,
        executionRefs: responsibilityCompletionAudit.executions.map((execution) => ({
          // Late batches are appended after the exhaustive ones using exactly this offset,
          // so the batch index is an exact, not heuristic, stage boundary.
          stage: (execution.batchIndex < exhaustiveBatchCount ? 'exhaustive' : 'late') as
            | 'exhaustive'
            | 'late',
          modelRunId: execution.modelRunId,
          contextPackId: execution.contextPackId,
        })),
      }),
      ...buildResponsibilityPostPassAudit({
        initialOmissions,
        finalOmissions: omissions,
        retries: omissionRetries,
        quoteRepair: responsibilityQuoteRepair,
        postPassBudget: responsibilityPostPassBudget.snapshot(),
        syntheticBaseReadCount: responsibilityBaseReadPlan.syntheticBaseReadCount,
      }),
      droppedCount,
      keptCount,
      readerBudget: readerBudget.snapshot(),
    };

    await db
      .update(sourceWorkflowMaps)
      .set({
        status,
        documentShape: structureMap.documentShape,
        mapKind,
        summary: structureMap.summary,
        segmentsJson: structureMap.segments,
        elementsJson: structureMap.elements,
        relationsJson: structureMap.relations,
        nodesJson: workflowOutputs.flatMap((output) => output.nodes),
        edgesJson: workflowOutputs.flatMap((output) => output.edges),
        lanesJson: workflowOutputs.flatMap((output) => output.lanes),
        pathsJson: workflowOutputs.flatMap((output) => output.paths),
        validationJson,
        modelRunId: lastModelRunId,
        contextPackId: lastContextPackId,
        updatedAt: new Date(),
        finalizedAt: new Date(),
      })
      .where(eq(sourceWorkflowMaps.id, pending.mapId));

    await db
      .update(jobRuns)
      .set({
        status: 'complete',
        finishedAt: new Date(),
        outputJson: {
          documentId: args.documentId,
          mapId: pending.mapId,
          status,
          mapKind,
          documentShape: structureMap.documentShape,
          droppedCount,
          keptCount,
          elementCount: structureMap.elements.length,
          relationCount: structureMap.relations.length,
          segmentCount: structureMap.segments.length,
          segmentShapeCounts: Object.fromEntries(
            structureMap.segments.map((segment) => [
              segment.shape,
              structureMap.segments.filter((candidate) => candidate.shape === segment.shape).length,
            ]),
          ),
          modelRunIds,
          readerBudget: readerBudget.snapshot(),
        },
      })
      .where(eq(jobRuns.id, jobRun.id));

    if (status === 'degraded') await markMacroDegraded(db, args.documentId);
    else await markMacroComplete(db, args.documentId);

    return {
      documentId: args.documentId,
      status,
      mapId: pending.mapId,
      mapKind,
      documentShape: structureMap.documentShape,
      droppedCount,
      keptCount,
      segmentCount: structureMap.segments.length,
      elementCount: structureMap.elements.length,
      relationCount: structureMap.relations.length,
      laneCount: structureMap.lanes.length,
      pathCount: structureMap.paths.length,
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    await db
      .update(sourceWorkflowMaps)
      .set({
        status: 'failed',
        validationJson: {
          pipelineVersion: SOURCE_READER_PIPELINE_VERSION,
          segmentationPromptVersion: SOURCE_SEGMENTATION_PROMPT_VERSION,
          workflowPromptVersion: WORKFLOW_READ_PROMPT_VERSION,
          readerBudget: readerBudget?.snapshot() ?? null,
          error: message,
        },
        updatedAt: new Date(),
        finalizedAt: new Date(),
      })
      .where(eq(sourceWorkflowMaps.id, pending.mapId));
    await db
      .update(jobRuns)
      .set({
        status: 'failed',
        finishedAt: new Date(),
        error: message,
        outputJson: { readerBudget: readerBudget?.snapshot() ?? null },
      })
      .where(eq(jobRuns.id, jobRun.id));
    await markMacroMapFailed(db, args.documentId);
    throw err;
  }
}

export const __sourceWorkflowReadTestHooks = {
  validateSegmentation,
  validateWorkflowMap,
  isReusableWorkflowMapStatus,
  prefixWindowIds,
  workflowToProcessStructureMap,
};
