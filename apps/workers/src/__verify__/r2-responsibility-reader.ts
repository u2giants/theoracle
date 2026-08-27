import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import {
  RESPONSIBILITY_READ_PROMPT_VERSION,
  RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
  RESPONSIBILITY_COMBINED_REPAIR_PROMPT_VERSION,
  RESPONSIBILITY_QUOTE_REPAIR_PROMPT_VERSION,
  RESPONSIBILITY_QUOTE_REPAIR_SYSTEM_PROMPT,
  RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT,
  RESPONSIBILITY_READ_SYSTEM_PROMPT,
  AllCandidatesFailedError,
  type ResponsibilityReadOutput,
  type SourceStructureSegment,
} from '@oracle/ai';
import {
  responsibilityCoverage,
  responsibilityMapElementRef,
  findResponsibilityOmissions,
  mergeResponsibilityValidationResults,
  mergeResponsibilityRetryValidation,
  patchResponsibilityQuoteRepairs,
  prefixResponsibilityOutput,
  prefixResponsibilityRetryOutput,
  assertUniqueResponsibilityElementIds,
  assertResponsibilityDutyChunksHaveBaseReads,
  responsibilityParentSegment,
  responsibilityRawAuditArtifact,
  rankResponsibilityOmissionChunks,
  selectFocusedResponsibilityOmissions,
  RESPONSIBILITY_FOCUSED_OMISSION_LIMIT,
  ResponsibilityOmissionRetryScheduler,
  buildResponsibilityOmissionAudit,
  buildResponsibilitySelectedSpanAudit,
  buildGroundedResponsibilityQuoteCandidates,
  buildSyntheticResponsibilitySegments,
  buildResponsibilityBaseReadPlan,
  buildResponsibilitySourceInventory,
  completeAndMatchResponsibilityInventory,
  assertResponsibilityInventorySeeds,
  buildResponsibilityPostPassAudit,
  bindForcedResponsibilitySpans,
  canonicalizeForcedResponsibilityOutput,
  finalizeForcedResponsibilityAudits,
  locateResponsibilityRawSlice,
  responsibilitySpanSha256,
  selectResponsibilityQuoteRepairRead,
  sourceDutySpans,
  validateGroundedResponsibilityQuoteSelections,
  shardResponsibilitySegments,
  validateResponsibilityRead,
  validateResponsibilityFieldFidelity,
  responsibilityMergeEligibleElements,
  expandResponsibilityDestinations,
  patchCombinedResponsibilityRepairs,
  packResponsibilityCompletions,
  canonicalizeResponsibilityCompletionBatch,
  responsibilityCompletionRequest,
  normalizeResponsibilityPriorRejectionReasons,
  RESPONSIBILITY_PRIOR_REJECTION_REASON_LIMIT,
  RESPONSIBILITY_PRIOR_REJECTION_REASON_MAX_LENGTH,
  lateResidualResponsibilitySeeds,
  mergeResponsibilityRecordsByInventoryId,
  resolveEnclosingResponsibilityDutySpan,
  buildResponsibilityFinalRecordCorrectionAudit,
  type ResponsibilityInventorySeed,
} from '../lib/responsibility-reader';
import {
  responsibilityEvidenceCoverage,
  responsibilityShadowLockKey,
  invokeResponsibilityMergeModel,
  assertResponsibilityVersionTarget,
} from '../lib/business-model-merge';
import { shouldDispatchResponsibilityShadowMerge } from '../trigger/document-ingestion';
import {
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  scoreResponsibilityAnswerKey,
} from '../lib/responsibility-answer-key';
import {
  ResponsibilityPostPassBudget,
  SourceReaderBudget,
  SourceReaderBudgetExceededError,
} from '../lib/source-reader-budget';
import {
  buildFocusedResponsibilityEvidenceChunks,
  buildResponsibilityCombinedRepairPlan,
  mergeCombinedResponsibilityRepairOutput,
  buildResponsibilityRequestContent,
  responsibilityReadPromptVersion,
  responsibilityReadTaskType,
  buildResponsibilityCompletionRequestContent,
  reserveResponsibilityCompletionBatches,
  forecastResponsibilityCompletionScenarios,
  responsibilityInventoryRequiresDegradedStatus,
  canonicalResponsibilityInventory,
  finalizeLateResponsibilityCompletion,
  runLateResponsibilityCompletion,
  executeResponsibilityCompletionBatches,
  isRetryableResponsibilityCompletionFailure,
  generateSourceWorkflowMap,
} from '../lib/source-workflow-read';
const answerKey = JSON.parse(
  readFileSync(
    new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
    'utf8',
  ),
) as {
  version: string;
  sourceSha256: string;
  records: Array<{ role: string; action: string; object: string }>;
};

const documentId = '11111111-1111-4111-8111-111111111111';
const chunkId = '22222222-2222-4222-8222-222222222222';
const otherChunkId = '44444444-4444-4444-8444-444444444444';

const completionSeeds = Array.from({ length: 40 }, (_, index) => ({
  inventorySeedId: `inventory_seed_generic_${String(index + 1).padStart(3, '0')}`,
  parentSeedId: null,
  chunkId,
  spanIndex: index,
  sourceSpan: `[Finance Team] submits report ${index + 1} to the records portal each month`,
  evidenceQuote: `submits report ${index + 1} to the records portal each month`,
  sourceStart: index * 80,
  sourceEnd: index * 80 + 55,
  listStructured: true,
  sourceSpanSha256: `hash_${index}`,
  splitKind: 'none' as const,
  splitValue: null,
  parseDiagnostics: [],
}));
const completionPackArgs = {
  seeds: completionSeeds,
  remainingCalls: 40,
  remainingInputTokens: 500_000,
  remainingCostUsd: 10,
  fixedInputTokensPerCall: 500,
  fixedOutputTokensPerCall: 100,
  maxInputTokensPerCall: 2_400,
  maxOutputTokensPerCall: 2_400,
  inputCostPerMillionTokensUsd: 2,
  outputCostPerMillionTokensUsd: 8,
};
const completionPack = packResponsibilityCompletions(completionPackArgs);
assert.equal(completionPack.unscheduledIds.length, 0);
assert.equal(completionPack.batches.flatMap((batch) => batch.seedIds).length, 40);
assert.deepEqual(completionPack, packResponsibilityCompletions(completionPackArgs));
const forecasts = forecastResponsibilityCompletionScenarios({
  scenarios: {
    low: completionSeeds.slice(0, 20),
    expected: completionSeeds,
    high: [...completionSeeds, ...completionSeeds.map((seed, index) => ({
      ...seed,
      inventorySeedId: `${seed.inventorySeedId}_high_${index}`,
    }))],
  },
  pack: completionPackArgs,
});
assert.equal(forecasts.expected.unscheduledIds.length, 0);
const twoPassCostBudget = new SourceReaderBudget({
  maxReadCalls: 40,
  maxInputTokens: 500_000,
  maxEstimatedCostUsd: 0.01,
  estimatedInputCostPerMillionTokensUsd: 0,
  maxRepairAttempts: 1,
  maxConcurrency: 4,
});
const costedBatch = { ...completionPack.batches[0]!, estimatedCostUsd: 0.006 };
reserveResponsibilityCompletionBatches({ budget: twoPassCostBudget, batches: [costedBatch] });
assert.throws(
  () => reserveResponsibilityCompletionBatches({
    budget: twoPassCostBudget,
    batches: [{ ...costedBatch, batchIndex: costedBatch.batchIndex + 1 }],
  }),
  /max_estimated_cost_usd/,
  'initial and late completion passes share the same full input-plus-output cost ledger',
);
assert.equal(
  responsibilityInventoryRequiresDegradedStatus({
    sourceInventoryCount: 40,
    mergeReadyInventoryCount: 39,
    unscheduledCount: 0,
  }),
  true,
  'one incomplete source seed forces degraded status',
);
assert.equal(
  responsibilityInventoryRequiresDegradedStatus({
    sourceInventoryCount: 40,
    mergeReadyInventoryCount: 40,
    unscheduledCount: 1,
  }),
  true,
  'one unscheduled completion forces degraded status',
);
assert.equal(
  responsibilityInventoryRequiresDegradedStatus({
    sourceInventoryCount: 40,
    mergeReadyInventoryCount: 40,
    unscheduledCount: 0,
  }),
  false,
);
assert.ok(forecasts.low.estimatedCalls <= forecasts.expected.estimatedCalls);
assert.ok(forecasts.high.estimatedCalls >= forecasts.expected.estimatedCalls);
assert.match(buildResponsibilityCompletionRequestContent(completionPack.batches[0]!), /known duty/i);
const completionBudget = new SourceReaderBudget({
  maxReadCalls: 40,
  maxInputTokens: 500_000,
  maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 2,
  maxRepairAttempts: 1,
  maxConcurrency: 4,
});
reserveResponsibilityCompletionBatches({ budget: completionBudget, batches: completionPack.batches });
assert.equal(completionBudget.snapshot().readCalls, completionPack.estimatedCalls);
const firstCompletionBatch = completionPack.batches[0]!;
const validCompletion = canonicalizeResponsibilityCompletionBatch({
  batch: firstCompletionBatch,
  output: {
    completions: firstCompletionBatch.requests.map((request) => ({
      responsibilityId: request.responsibilityId,
      label: 'Submit monthly report',
      role: 'Finance Team',
      action: 'submit',
      object: 'monthly report to the records portal each month',
      trigger: 'each month',
      requiredSystem: 'records portal',
      ownerName: null,
      department: null,
    })),
  },
});
assert.deepEqual(validCompletion.map((item) => item.responsibilityId), firstCompletionBatch.seedIds);
assert.equal(validCompletion[0]!.evidenceQuote, firstCompletionBatch.requests[0]!.evidenceQuote);
assert.throws(() => canonicalizeResponsibilityCompletionBatch({
  batch: firstCompletionBatch,
  output: { completions: [] },
}), /omitted seeds/);
assert.throws(() => canonicalizeResponsibilityCompletionBatch({
  batch: firstCompletionBatch,
  output: { completions: [{
    responsibilityId: 'inventory_seed_extra', label: 'Extra', role: 'Team', action: 'do', object: 'work',
  }] },
}), /extra seed/);
assert.throws(() => canonicalizeResponsibilityCompletionBatch({
  batch: firstCompletionBatch,
  output: { completions: [
    ...firstCompletionBatch.requests.map((request) => ({
      responsibilityId: request.responsibilityId,
      label: 'Submit monthly report', role: 'Finance Team', action: 'submit', object: 'monthly report',
    })),
    {
      responsibilityId: firstCompletionBatch.seedIds[0]!,
      label: 'Duplicate', role: 'Finance Team', action: 'submit', object: 'monthly report',
    },
  ] },
}), /duplicate seed/);
const tinySeeds = Array.from({ length: 601 }, (_, index) => ({
  ...completionSeeds[0]!,
  inventorySeedId: `inventory_seed_tiny_${String(index).padStart(3, '0')}`,
  spanIndex: index,
  sourceSpan: '[Team] files report',
  evidenceQuote: 'files report',
}));
const schemaBoundPack = packResponsibilityCompletions({
  ...completionPackArgs,
  seeds: tinySeeds,
  maxInputTokensPerCall: 1_000_000,
  maxOutputTokensPerCall: 1_000_000,
});
assert.deepEqual(schemaBoundPack.batches.map((batch) => batch.seedIds.length), [300, 300, 1]);
const shortage = packResponsibilityCompletions({
  ...completionPackArgs,
  remainingCalls: 1,
  maxInputTokensPerCall: 900,
});
assert.ok(shortage.unscheduledIds.length > 0);
assert.deepEqual(
  [...shortage.batches.flatMap((batch) => batch.seedIds), ...shortage.unscheduledIds],
  completionSeeds.map((seed) => seed.inventorySeedId),
);
const executionBudget = new SourceReaderBudget({
  maxReadCalls: completionPack.batches.length + 1,
  maxInputTokens: 500_000,
  maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 2,
  maxRepairAttempts: 0,
  maxConcurrency: 4,
});
const execution = await executeResponsibilityCompletionBatches({
  budget: executionBudget,
  batches: completionPack.batches,
  concurrency: 4,
  runBatch: async (batch) => ({
    completions: batch.requests.map((request) => ({
      responsibilityId: request.responsibilityId,
      label: 'Submit monthly report', role: 'Finance Team', action: 'submit',
      object: 'monthly report to the records portal each month',
    })),
  }),
  baselines: completionSeeds.map((seed) => ({ responsibilityId: seed.inventorySeedId, complete: false })),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.deepEqual(execution.flatMap((item) => item.seedIds), completionSeeds.map((seed) => seed.inventorySeedId));
assert.ok(execution.every((item) => item.failure === null && item.attempts === 1));
assert.ok(execution.flatMap((item) => item.outcomes).every((item) => item.status === 'accepted'));
const malformedBudget = new SourceReaderBudget({
  maxReadCalls: 2,
  maxInputTokens: 500_000,
  maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 2,
  maxRepairAttempts: 0,
  maxConcurrency: 1,
});
const malformed = await executeResponsibilityCompletionBatches({
  budget: malformedBudget,
  batches: [firstCompletionBatch],
  concurrency: 1,
  runBatch: async () => ({ completions: [] }),
  baselines: firstCompletionBatch.seedIds.map((responsibilityId) => ({ responsibilityId, complete: false })),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.equal(malformed[0]!.records.length, 0);
assert.equal(malformed[0]!.attempts, 1);
assert.match(malformed[0]!.failure!, /omitted seeds/);
const retryBudget = new SourceReaderBudget({
  maxReadCalls: 2, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 2, maxRepairAttempts: 0, maxConcurrency: 1,
});
let retryCalls = 0;
const retried = await executeResponsibilityCompletionBatches({
  budget: retryBudget,
  batches: [firstCompletionBatch],
  concurrency: 1,
  runBatch: async (batch) => {
    retryCalls += 1;
    if (retryCalls === 1) throw new Error('provider timeout');
    return { completions: batch.requests.map((request) => ({
      responsibilityId: request.responsibilityId,
      label: 'Submit monthly report', role: 'Finance Team', action: 'submit', object: 'monthly report',
    })) };
  },
  baselines: firstCompletionBatch.seedIds.map((responsibilityId) => ({ responsibilityId, complete: false })),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.equal(retried[0]!.attempts, 2);
assert.equal(retried[0]!.failure, null);
const allCandidatesBudget = new SourceReaderBudget({
  maxReadCalls: 2, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 2, maxRepairAttempts: 0, maxConcurrency: 1,
});
let allCandidatesCalls = 0;
const allCandidatesRetried = await executeResponsibilityCompletionBatches({
  budget: allCandidatesBudget,
  batches: [firstCompletionBatch],
  concurrency: 1,
  runBatch: async (batch) => {
    allCandidatesCalls += 1;
    if (allCandidatesCalls === 1) throw new AllCandidatesFailedError('workflow_read', [{
      routeId: 'generic_route', provider: 'generic_provider', modelId: 'generic_model', error: 'temporary',
    }]);
    return { completions: batch.requests.map((request) => ({
      responsibilityId: request.responsibilityId,
      label: 'Submit monthly report', role: 'Finance Team', action: 'submit', object: 'monthly report',
    })) };
  },
  baselines: firstCompletionBatch.seedIds.map((responsibilityId) => ({ responsibilityId, complete: false })),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.equal(allCandidatesRetried[0]!.attempts, 2);
assert.equal(allCandidatesRetried[0]!.failure, null);
const noRetryBudget = new SourceReaderBudget({
  maxReadCalls: 1, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 2, maxRepairAttempts: 0, maxConcurrency: 1,
});
const notBudgeted = await executeResponsibilityCompletionBatches({
  budget: noRetryBudget,
  batches: [firstCompletionBatch],
  concurrency: 1,
  runBatch: async () => {
    throw Object.assign(new Error('All model candidates failed for workflow_read'), {
      name: 'AllCandidatesFailedError',
    });
  },
  baselines: firstCompletionBatch.seedIds.map((responsibilityId) => ({ responsibilityId, complete: false })),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.equal(notBudgeted[0]!.attempts, 1);
assert.ok(notBudgeted[0]!.outcomes.every((item) => item.status === 'retry_not_budgeted'));
assert.match(notBudgeted[0]!.failure!, /retry_not_budgeted/);
const noRetryCostBudget = new SourceReaderBudget({
  maxReadCalls: 2,
  maxInputTokens: 500_000,
  maxEstimatedCostUsd: firstCompletionBatch.estimatedCostUsd * 1.5,
  estimatedInputCostPerMillionTokensUsd: 0,
  maxRepairAttempts: 0,
  maxConcurrency: 1,
});
const costBlockedRetry = await executeResponsibilityCompletionBatches({
  budget: noRetryCostBudget,
  batches: [firstCompletionBatch],
  concurrency: 1,
  runBatch: async () => {
    throw Object.assign(new Error('schema response failed'), { name: 'TimeoutError' });
  },
  baselines: firstCompletionBatch.seedIds.map((responsibilityId) => ({
    responsibilityId,
    complete: false,
  })),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.ok(costBlockedRetry[0]!.outcomes.every((item) => item.status === 'retry_not_budgeted'));
assert.match(costBlockedRetry[0]!.failure!, /max_estimated_cost_usd/);
assert.equal(
  responsibilityInventoryRequiresDegradedStatus({
    sourceInventoryCount: 1,
    mergeReadyInventoryCount: 1,
    unscheduledCount: 0,
    finalGapCount: 1,
  }),
  true,
  'a duty still found after a failed budgeted retry forces degraded status even when known inventory is complete',
);
const acceptedLateFinal = finalizeLateResponsibilityCompletion({
  seedIds: firstCompletionBatch.seedIds,
  results: execution.filter((item) => item.batchIndex === firstCompletionBatch.batchIndex),
  unscheduledIds: [],
  batchOffset: 7,
});
assert.equal(acceptedLateFinal.records.length, firstCompletionBatch.seedIds.length);
assert.equal(new Set(acceptedLateFinal.records.map((item) => item.responsibilityId)).size, acceptedLateFinal.records.length);
assert.ok(acceptedLateFinal.outcomes.every((item) => item.batchIndex === 7));
assert.equal(acceptedLateFinal.degraded, false);
const rejectedLateFinal = finalizeLateResponsibilityCompletion({
  seedIds: firstCompletionBatch.seedIds,
  results: [{
    batchIndex: 0,
    seedIds: firstCompletionBatch.seedIds,
    attempts: 1,
    records: [],
    outcomes: firstCompletionBatch.seedIds.map((responsibilityId) => ({
      responsibilityId,
      status: 'validation_rejected' as const,
      reasons: ['required field missing'],
    })),
    failure: null,
  }],
  unscheduledIds: [],
  batchOffset: 8,
});
assert.equal(rejectedLateFinal.records.length, 0);
assert.equal(rejectedLateFinal.incompleteIds.length, firstCompletionBatch.seedIds.length);
assert.ok(rejectedLateFinal.outcomes.every((item) => item.batchIndex === 8));
assert.equal(rejectedLateFinal.degraded, true);
const blockedLateFinal = finalizeLateResponsibilityCompletion({
  seedIds: firstCompletionBatch.seedIds,
  results: [],
  unscheduledIds: firstCompletionBatch.seedIds,
  batchOffset: 9,
});
assert.equal(blockedLateFinal.records.length, 0);
assert.ok(blockedLateFinal.outcomes.every((item) => item.status === 'budget_exhausted'));
assert.equal(blockedLateFinal.degraded, true);
assert.equal(isRetryableResponsibilityCompletionFailure(Object.assign(new Error('aborted'), { name: 'AbortError' })), true);
const mixedBudget = new SourceReaderBudget({
  maxReadCalls: 1, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 2, maxRepairAttempts: 0, maxConcurrency: 1,
});
const mixed = await executeResponsibilityCompletionBatches({
  budget: mixedBudget,
  batches: [firstCompletionBatch],
  concurrency: 1,
  runBatch: async (batch) => ({ completions: batch.requests.map((request) => ({
    responsibilityId: request.responsibilityId,
    label: 'Submit monthly report', role: 'Finance Team', action: 'submit', object: 'monthly report',
  })) }),
  baselines: firstCompletionBatch.seedIds.map((responsibilityId) => ({ responsibilityId, complete: false })),
  validateCompletion: (record) => record.responsibilityId === firstCompletionBatch.seedIds[0]
    ? { complete: true, reasons: [] }
    : { complete: false, reasons: ['object_missing_required_timing'] },
});
assert.equal(mixed[0]!.records.length, 1);
assert.equal(mixed[0]!.outcomes[0]!.status, 'accepted');
assert.ok(mixed[0]!.outcomes.slice(1).every((item) =>
  item.status === 'validation_rejected' && item.reasons.includes('object_missing_required_timing')
));
const segment: SourceStructureSegment = {
  segmentId: 'licensed_team',
  shape: 'responsibilities',
  title: 'Licensed team',
  chunkIds: [chunkId],
};
const output: ResponsibilityReadOutput = {
  summary: 'Licensed team duties.',
  responsibilities: [
    {
      responsibilityId: 'designer_preflight',
      label: 'Designer checks art files',
      role: 'Licensed Team Designer',
      action: 'checks',
      object: 'art files for completeness before handoff',
      trigger: 'before handoff',
      requiredSystem: 'Designflow',
      evidenceQuote:
        'The Licensed Team Designer checks art files for completeness before handoff.',
      chunkId,
    },
  ],
};
const result = validateResponsibilityRead({
  output,
  documentId,
  segment,
  fileType: 'text/plain',
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText:
        'The Licensed Team Designer checks art files for completeness before handoff.',
    },
  ],
});
assert.equal(result.elements.length, 1);
assert.equal(result.primaryCount, 1);
assert.equal(result.diagnostics.length, 0);
assert.equal(result.elements[0]?.role, 'Licensed Team Designer');

const shardChunks = [
  { id: chunkId },
  { id: otherChunkId },
];
const shards = shardResponsibilitySegments(
  [{ ...segment, chunkIds: [otherChunkId, chunkId] }],
  shardChunks,
);
assert.deepEqual(shards.map((item) => item.chunkIds), [[chunkId], [otherChunkId]]);
assert.deepEqual(
  shardResponsibilitySegments([{ ...segment, chunkIds: [otherChunkId, chunkId] }], shardChunks),
  shards,
  'sharding is idempotent',
);
assert.equal(
  prefixResponsibilityOutput(output, 0).responsibilities[0]?.responsibilityId,
  'shard_001__designer_preflight',
);
const mergedReads = mergeResponsibilityValidationResults([
  { segment: shards[1]!, validation: result },
  { segment: shards[0]!, validation: result },
]);
assert.deepEqual(mergedReads.map((item) => item.segment.segmentId), [
  `${segment.segmentId}__chunk_001`,
  `${segment.segmentId}__chunk_002`,
]);
const parentSegment = responsibilityParentSegment(shards[0]!);
assert.equal(parentSegment.segmentId, segment.segmentId);
const parentJoined = validateResponsibilityRead({
  output: prefixResponsibilityOutput(output, 0),
  documentId,
  segment: parentSegment,
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: output.responsibilities[0]!.evidenceQuote,
    },
  ],
});
assert.equal(parentJoined.elements[0]?.segmentId, segment.segmentId);

const omissionChunks = [
  {
    id: chunkId,
    documentId,
    rawText:
      '- Licensed Team checks art files for completeness.\n' +
      '- Licensed Team emails the approved package to Sales.\n' +
      '- Licensed Team downloads files & uploads files to the archive.\n' +
      'This review summarizes prior work and contains no assigned duty.',
  },
];
const omissionAudit = findResponsibilityOmissions({
  chunks: omissionChunks,
  elements: [
    {
      ...result.elements[0]!,
      role: 'Licensed Team',
      object: 'art files for completeness',
      evidenceQuote: 'Licensed Team checks art files for completeness.',
      chunkId,
    },
  ],
  fileType: 'text/plain',
});
assert.equal(omissionAudit.length, 3);
assert.ok(omissionAudit.some((item) => /emails the approved package/.test(item.sourceSpan)));
assert.ok(omissionAudit.some((item) => /downloads files/.test(item.sourceSpan)));
assert.ok(omissionAudit.some((item) => /uploads files/.test(item.sourceSpan)));
assert.ok(!omissionAudit.some((item) => /review summarizes/.test(item.sourceSpan)));
assert.ok(
  omissionAudit.every((item) => item.listStructured),
  'list structure survives marker stripping for retry ranking',
);
const multiChunkOmissions = findResponsibilityOmissions({
  chunks: [
    { id: chunkId, documentId, rawText: '- Finance authorizes invoices.' },
    { id: otherChunkId, documentId, rawText: '- Sales receives approved files.' },
  ],
  elements: [],
  fileType: 'text/plain',
});
assert.deepEqual(
  multiChunkOmissions.map((item) => item.chunkId),
  [chunkId, otherChunkId],
  'omissions remain bounded and addressable per chunk',
);
const multiDutyFieldCoverage = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText:
        '- Finance Operations approves invoices and then records the decision in the ledger.',
    },
  ],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Finance Operations',
      action: 'approves',
      object: 'invoices',
      evidenceQuote:
        'Finance Operations approves invoices and then records the decision in the ledger.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(
  multiDutyFieldCoverage.length,
  1,
  'a long quote covering two duties leaves the unrepresented duty as an omission',
);
const fieldCoveredThinRao = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: '- Finance Operations approves invoices.',
    },
  ],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Finance Operations',
      action: 'approves',
      object: 'invoices',
      evidenceQuote: 'Finance Operations approves invoices.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(fieldCoveredThinRao.length, 0, 'thin role-action-object coverage closes the omission');
const quoteOverlapWrongFields = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: '- Finance Operations approves invoices in the billing portal.',
    },
  ],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Sales',
      action: 'receives',
      object: 'invoices',
      evidenceQuote: 'Finance Operations approves invoices in the billing portal.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(
  quoteOverlapWrongFields.length,
  1,
  'quote overlap alone cannot hide a field-uncovered duty',
);
const phrasalActionCoverage = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: '[Sales]\n- Reach out to customers in CRM each month.',
    },
  ],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Sales',
      action: 'reach out',
      object: 'customers in CRM each month',
      evidenceQuote: 'Reach out to customers in CRM each month.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(
  phrasalActionCoverage.length,
  0,
  'phrasal action particles are not incorrectly required in object',
);
const structuralFieldsDoNotReplaceObject = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: '[Sales]\n- Reach out to customers in CRM each month.',
    },
  ],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Sales',
      action: 'reach out',
      object: 'customers',
      trigger: 'each month',
      system: 'CRM',
      systems: 'CRM',
      evidenceQuote: 'Reach out to customers in CRM each month.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(
  structuralFieldsDoNotReplaceObject.length,
  1,
  'trigger and system fields cannot hide concrete object omissions',
);
const wrappedObjectCoverage = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText:
        '[Operations]\n- Submit quarterly reports through\nRoyalty Portal before month end.',
    },
  ],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Operations',
      action: 'submit',
      object: 'quarterly reports through Royalty Portal before month end',
      evidenceQuote:
        'Submit quarterly reports through\nRoyalty Portal before month end.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(
  wrappedObjectCoverage.length,
  0,
  'wrapped target, portal, cadence, and timing text remains part of the duty object contract',
);
const nonLicensedOwnerAudit = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: '[Finance Operations]\n- Authorize invoices.\n- Monthly close ownership.',
    },
  ],
  elements: [],
  fileType: 'text/plain',
});
assert.equal(
  nonLicensedOwnerAudit.length,
  1,
  'ownership cues without a concrete duty verb are not omissions',
);
const ownerPersistsAcrossProse = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText:
        '[Finance Operations]\nBackground notes for this section.\n- Authorize invoices in LedgerPro.',
    },
  ],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Sales',
      action: 'authorize',
      object: 'invoices in LedgerPro',
      evidenceQuote: 'Authorize invoices in LedgerPro.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(
  ownerPersistsAcrossProse.length,
  1,
  'an active owner survives prose and wrong-role output never covers its duty',
);
const structuredListFalsePositiveAudit = findResponsibilityOmissions({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: '- Monthly close calendar.\n- General background information.',
    },
  ],
  elements: [],
  fileType: 'text/plain',
});
assert.equal(structuredListFalsePositiveAudit.length, 0);
const rankedOmissions = rankResponsibilityOmissionChunks(
  [
    { chunkId, spanIndex: 0, sourceSpan: 'Finance checks invoice totals.' },
    { chunkId, spanIndex: 1, sourceSpan: 'Finance emails approved invoices.' },
    { chunkId: otherChunkId, spanIndex: 0, sourceSpan: 'Sales receives approved invoices.' },
  ],
  [
    { id: otherChunkId },
    { id: chunkId },
  ],
);
assert.equal(rankedOmissions[0]?.chunkId, chunkId, 'remaining omission count wins ranking');
assert.equal(rankedOmissions[1]?.chunkId, otherChunkId, 'source order breaks equal counts');
const tooManyFocused = Array.from(
  { length: RESPONSIBILITY_FOCUSED_OMISSION_LIMIT + 3 },
  (_, index) => ({
    chunkId,
    spanIndex: index,
    sourceSpan: `Finance checks invoice batch ${index} before close.`,
  }),
);
assert.equal(
  selectFocusedResponsibilityOmissions(tooManyFocused).length,
  RESPONSIBILITY_FOCUSED_OMISSION_LIMIT,
  'focused retries never dump every remaining span',
);
assert.equal(
  selectFocusedResponsibilityOmissions(
    [
      {
        chunkId,
        spanIndex: 0,
        sourceSpan: 'Context before Finance checks a routine item.',
      },
      {
        chunkId,
        spanIndex: 1,
        sourceSpan: '[Finance] Check the urgent invoice total.',
      },
    ],
    1,
  )[0]?.spanIndex,
  1,
  'owner-prefixed verb-start duties keep verb-start priority',
);
assert.equal(
  selectFocusedResponsibilityOmissions(
    [
      {
        chunkId,
        spanIndex: 0,
        sourceSpan:
          'Operations reviews a long explanatory paragraph with many concrete details about records, schedules, folders, and background notes.',
      },
      {
        chunkId,
        spanIndex: 1,
        sourceSpan: '[Operations] Submit access form.',
        listStructured: true,
      },
    ],
    1,
  )[0]?.spanIndex,
  1,
  'a short structured duty outranks a long paragraph',
);
assert.deepEqual(
  sourceDutySpans('[Support]\n- Review requests and then send approvals.'),
  ['[Support] Review requests', '[Support] send approvals.'],
  'adjacent duty verbs become separate span-bound work units',
);
assert.deepEqual(
  sourceDutySpans('- Support reviews requests, sends approvals.'),
  ['Support reviews requests', '[Support] sends approvals.'],
  'an inline owner remains bound to every deterministically split duty',
);
const polarityFailure = validateResponsibilityFieldFidelity(
  '[Support] Provide access codes to Portal X.',
  { role: 'Support', action: 'receive', object: 'access codes to Portal X' },
);
assert.equal(polarityFailure.passed, false);
assert.equal(polarityFailure.polarityFailure, true, 'provide-to-receive reversal is rejected');
assert.equal(
  validateResponsibilityFieldFidelity(
    '[Compliance] Submit quarterly compliance reports.',
    { role: 'Compliance', action: 'submit', object: 'reports' },
  ).passed,
  false,
  'cadence and named qualifiers cannot be thinned out',
);
assert.equal(
  validateResponsibilityFieldFidelity(
    '[Intake] Complete Form A.',
    { role: 'Intake', action: 'complete', object: 'Form B' },
  ).passed,
  false,
  'a named form cannot be replaced',
);
assert.equal(
  validateResponsibilityFieldFidelity(
    '[Records] Upload signed notices to Archive Hub.',
    { role: 'Records', action: 'upload', object: 'signed notices' },
  ).passed,
  false,
  'destination and system qualifiers cannot disappear',
);
assert.equal(
  validateResponsibilityFieldFidelity(
    '[Billing] Review invoices.',
    { role: 'Billing', action: 'review', object: 'invoice' },
  ).passed,
  true,
  'light singular and plural object morphology does not create false failures',
);
assert.equal(
  validateResponsibilityFieldFidelity(
    '[Intake] Complete forms.',
    { role: 'Intake', action: 'complete', object: 'form' },
  ).passed,
  true,
  'generic form and forms morphology is normalized safely',
);
assert.equal(
  validateResponsibilityFieldFidelity(
    '[Intake] Complete Form A.',
    { role: 'Intake', action: 'complete', object: 'Form A' },
  ).passed,
  true,
  'single-letter form markers remain complete when they match',
);
assert.equal(
  validateResponsibilityFieldFidelity(
    'Check status.',
    { role: 'Operator', action: 'check', object: 'status' },
  ).passed,
  true,
  'a short real duty is not rejected for lacking extra qualifiers',
);
const forcedSpans = bindForcedResponsibilitySpans(
  selectFocusedResponsibilityOmissions([
    {
      chunkId,
      spanIndex: 7,
      sourceSpan: '[Support] Send access notice to Portal X.',
      evidenceQuote: '[Support] Send access notice to Portal X.',
      sourceStart: 0,
      sourceEnd: '[Support] Send access notice to Portal X.'.length,
      listStructured: true,
    },
  ]),
);
const missingRawBinding = selectFocusedResponsibilityOmissions([{
  chunkId,
  spanIndex: 8,
  sourceSpan: '[Support] Send a notice.',
  sourceLocationFailure: 'synthetic raw binding failure',
}]);
assert.throws(
  () => bindForcedResponsibilitySpans(missingRawBinding),
  /missing a valid raw evidence binding/,
  'forced retry binding fails loud instead of using semantic text as evidence',
);
const missingRawBindingAudit = buildResponsibilitySelectedSpanAudit({
  selected: missingRawBinding,
  finalOmissions: missingRawBinding,
  preRecordCount: 0,
  postRecordCount: 0,
  skipped: 'raw_source_binding_failed',
  inResponsibilityBaseRead: true,
});
assert.equal(
  missingRawBindingAudit[0]?.sourceLocationFailure,
  'synthetic raw binding failure',
  'an unlocatable duty remains an honest durable uncovered audit row',
);
assert.throws(
  () => locateResponsibilityRawSlice('Check status.', 'Send report.'),
  /could not be bound to raw source/,
  'an unlocatable duty-bearing part fails loud instead of disappearing',
);
const forcedId = forcedSpans[0]!.forcedResponsibilityId;
const forcedResult = canonicalizeForcedResponsibilityOutput({
  selected: forcedSpans,
  output: {
    summary: 'One isolated responsibility span.',
    responsibilities: [{
      responsibilityId: forcedId,
      label: 'Send access notice',
      role: 'Support',
      action: 'send',
      object: 'access notice to Portal X',
      evidenceQuote: 'rewritten quote',
      chunkId,
    }],
  },
});
assert.equal(forcedResult.output.responsibilities.length, 1);
assert.equal(
  forcedResult.output.responsibilities[0]?.evidenceQuote,
  '[Support] Send access notice to Portal X.',
  'a valid forced span always receives its exact offered quote',
);
assert.equal(forcedResult.audits[0]?.accepted, false);
assert.equal(forcedResult.audits[0]?.exactQuoteBinding, false);
assert.equal(forcedResult.audits[0]?.fieldFidelity.passed, true);
assert.equal(forcedResult.audits[0]?.sourceSpanSha256, forcedSpans[0]?.sourceSpanSha256);
const forcedValidation = validateResponsibilityRead({
  output: forcedResult.output,
  documentId,
  segment,
  fileType: 'text/plain',
  chunks: [{
    id: chunkId,
    documentId,
    rawText: '[Support] Send access notice to Portal X.',
  }],
});
const finalForcedAudit = finalizeForcedResponsibilityAudits({
  audits: forcedResult.audits,
  selected: forcedSpans,
  durableAcceptedElementIds: new Set(forcedValidation.elements.map((item) => item.elementId)),
  validation: forcedValidation,
  chunks: [{
    id: chunkId,
    documentId,
    rawText: '[Support] Send access notice to Portal X.',
  }],
  fileType: 'text/plain',
});
assert.equal(finalForcedAudit[0]?.accepted, true);
assert.equal(finalForcedAudit[0]?.exactQuoteBinding, true);
const remappedForcedAudit = finalizeForcedResponsibilityAudits({
  audits: forcedResult.audits,
  selected: forcedSpans,
  durableAcceptedElementIds: new Set(['mapped_inventory_seed']),
  durableIdByForcedId: new Map([[forcedId, 'mapped_inventory_seed']]),
  validation: {
    ...forcedValidation,
    elements: forcedValidation.elements.map((element) => ({
      ...element,
      elementId: 'mapped_inventory_seed',
    })),
    completeElementIds: ['mapped_inventory_seed'],
  },
  chunks: [{
    id: chunkId,
    documentId,
    rawText: '[Support] Send access notice to Portal X.',
  }],
  fileType: 'text/plain',
});
assert.equal(
  remappedForcedAudit[0]?.accepted,
  true,
  'forced retry audit follows the canonical inventory ID assigned after matching',
);
const rejectedRemappedAudit = finalizeForcedResponsibilityAudits({
  audits: forcedResult.audits.map((audit) => ({ ...audit, rejectionReasons: [] })),
  selected: forcedSpans,
  durableAcceptedElementIds: new Set(),
  durableIdByForcedId: new Map([[forcedId, 'mapped_inventory_seed']]),
  validation: {
    ...forcedValidation,
    elements: [],
    completeElementIds: [],
    diagnostics: [{
      responsibilityId: 'mapped_inventory_seed',
      chunkId,
      failureClass: 'invalid_detail',
      detail: 'Mapped field validation failed.',
      boundedQuote: '[Support] Send access notice to Portal X.',
      selectedPolicy: 'strict',
      validationMethod: 'exact',
      alternatePoliciesPassing: [],
      crossSegmentStatus: 'within_segment',
      failureOrigin: 'root',
    }],
  },
  chunks: [{
    id: chunkId,
    documentId,
    rawText: '[Support] Send access notice to Portal X.',
  }],
  fileType: 'text/plain',
});
assert.equal(rejectedRemappedAudit[0]?.accepted, false);
assert.ok(
  rejectedRemappedAudit[0]?.rejectionReasons.some((reason) =>
    reason.includes('Mapped field validation failed.')
  ),
  'remapped retry rejection keeps the durable inventory ID diagnostic',
);
assert.ok(
  !rejectedRemappedAudit[0]?.rejectionReasons.includes('not_durably_accepted'),
);
const realContinuationText = '[Support]\n- Review requests and then send approvals.';
const continuationOmissions = findResponsibilityOmissions({
  chunks: [{ id: chunkId, documentId, rawText: realContinuationText }],
  elements: [],
  fileType: 'text/plain',
});
const continuationSpan = bindForcedResponsibilitySpans(
  selectFocusedResponsibilityOmissions(
    continuationOmissions.filter((item) => /send approvals/.test(item.sourceSpan)),
  ),
)[0]!;
assert.equal(continuationSpan.sourceSpan, '[Support] send approvals.');
assert.equal(continuationSpan.evidenceQuote, 'send approvals.');
assert.equal(
  realContinuationText.slice(continuationSpan.sourceStart, continuationSpan.sourceEnd),
  continuationSpan.evidenceQuote,
  'synthetic inherited owner context is never used as the evidence slice',
);
const continuationCandidate = canonicalizeForcedResponsibilityOutput({
  selected: [continuationSpan],
  output: {
    summary: 'One real continuation duty.',
    responsibilities: [{
      responsibilityId: continuationSpan.forcedResponsibilityId,
      label: 'Send approvals',
      role: 'Support',
      action: 'send',
      object: 'approvals',
      evidenceQuote: '[Support] send approvals.',
      chunkId,
    }],
  },
});
assert.equal(continuationCandidate.output.responsibilities[0]?.evidenceQuote, 'send approvals.');
const continuationValidation = validateResponsibilityRead({
  output: continuationCandidate.output,
  documentId,
  segment,
  fileType: 'text/plain',
  chunks: [{ id: chunkId, documentId, rawText: realContinuationText }],
});
const continuationMerge = mergeResponsibilityRetryValidation(
  {
    elements: [],
    diagnostics: [],
    crossSegmentCitations: [],
    primaryCount: 0,
  },
  continuationValidation,
);
const continuationFinalAudit = finalizeForcedResponsibilityAudits({
  audits: continuationCandidate.audits,
  selected: [continuationSpan],
  durableAcceptedElementIds: new Set(continuationMerge.acceptedElementIds),
  validation: continuationValidation,
  chunks: [{ id: chunkId, documentId, rawText: realContinuationText }],
  fileType: 'text/plain',
});
assert.equal(continuationMerge.acceptedCount, 1);
assert.equal(continuationFinalAudit[0]?.accepted, true);
assert.equal(continuationFinalAudit[0]?.exactQuoteBinding, true);
const continuationSelectedAudit = buildResponsibilitySelectedSpanAudit({
  selected: [continuationSpan],
  finalOmissions: [],
  preRecordCount: 0,
  postRecordCount: 1,
  skipped: null,
  inResponsibilityBaseRead: true,
  fieldAudits: continuationFinalAudit,
});
assert.equal(continuationSelectedAudit[0]?.forcedResponsibilityId, continuationSpan.forcedResponsibilityId);
assert.equal(continuationSelectedAudit[0]?.result.accepted, true);
assert.equal(continuationSelectedAudit[0]?.exactQuoteBinding, true);
assert.equal(continuationSelectedAudit[0]?.fieldFidelity?.passed, true);
const rejectedContinuation = canonicalizeForcedResponsibilityOutput({
  selected: [continuationSpan],
  output: {
    summary: 'A reversed continuation duty.',
    responsibilities: [{
      responsibilityId: continuationSpan.forcedResponsibilityId,
      label: 'Receive approvals',
      role: 'Support',
      action: 'receive',
      object: 'approvals',
      evidenceQuote: 'send approvals.',
      chunkId,
    }],
  },
});
const rejectedContinuationValidation = validateResponsibilityRead({
  output: rejectedContinuation.output,
  documentId,
  segment,
  fileType: 'text/plain',
  chunks: [{ id: chunkId, documentId, rawText: realContinuationText }],
});
const rejectedContinuationAudit = finalizeForcedResponsibilityAudits({
  audits: rejectedContinuation.audits,
  selected: [continuationSpan],
  durableAcceptedElementIds: new Set(),
  validation: rejectedContinuationValidation,
  chunks: [{ id: chunkId, documentId, rawText: realContinuationText }],
  fileType: 'text/plain',
});
assert.equal(rejectedContinuationValidation.elements.length, 0);
assert.equal(rejectedContinuationAudit[0]?.accepted, false);
assert.equal(rejectedContinuationAudit[0]?.exactQuoteBinding, false);
assert.ok(
  rejectedContinuationAudit[0]?.rejectionReasons.some((reason) => /polarity_reversal/.test(reason)),
  'a production-path rejection remains honest in its final audit',
);
const missingForcedResult = canonicalizeForcedResponsibilityOutput({
  selected: forcedSpans,
  output: { summary: 'No returned responsibility for the isolated span.', responsibilities: [] },
});
assert.equal(missingForcedResult.output.responsibilities.length, 0);
assert.deepEqual(missingForcedResult.audits[0]?.rejectionReasons, ['missing_span_record', 'missing_or_duplicate_span_record']);
const focusedOnlyRequest = buildResponsibilityRequestContent({ focusedSpans: forcedSpans });
assert.match(focusedOnlyRequest, /forcedResponsibilityId/);
assert.match(focusedOnlyRequest, /Send access notice to Portal X/);
assert.ok(
  !focusedOnlyRequest.includes('hidden sibling duty'),
  'focused retry input cannot invent a hidden sibling sentence',
);
const focusedEvidence = buildFocusedResponsibilityEvidenceChunks(
  [{
    id: chunkId,
    rawText:
      '[Support] Send access notice to Portal X.\n' +
      '[Support] hidden sibling duty must not be visible.',
  }],
  forcedSpans,
);
assert.equal(
  focusedEvidence[0]?.rawText,
  '[Support] Send access notice to Portal X.',
  'focused retry evidence excludes every unselected sibling sentence',
);
const baseFieldRegression = validateResponsibilityRead({
  output: {
    summary: 'A valid base-read responsibility.',
    responsibilities: [{
      responsibilityId: 'records_archive_notice',
      label: 'Archive signed notice',
      role: 'Records',
      action: 'archive',
      object: 'signed notice in Vault One',
      evidenceQuote: 'Records archive signed notice in Vault One.',
      chunkId,
    }],
  },
  documentId,
  segment,
  fileType: 'text/plain',
  chunks: [{ id: chunkId, documentId, rawText: 'Records archive signed notice in Vault One.' }],
});
assert.equal(baseFieldRegression.elements.length, 1, 'valid existing base RAOs survive field fidelity');
const reversedBaseRegression = validateResponsibilityRead({
  output: {
    summary: 'An invalid reversed base-read responsibility.',
    responsibilities: [{
      responsibilityId: 'support_receive_code',
      label: 'Receive access code',
      role: 'Support',
      action: 'receive',
      object: 'access code to Portal X',
      evidenceQuote: 'Support provide access code to Portal X.',
      chunkId,
    }],
  },
  documentId,
  segment,
  fileType: 'text/plain',
  chunks: [{ id: chunkId, documentId, rawText: 'Support provide access code to Portal X.' }],
});
assert.equal(reversedBaseRegression.elements.length, 0, 'base reads use the same safe field validator');
assert.match(reversedBaseRegression.diagnostics[0]?.detail ?? '', /polarity_reversal/);
const unmappedQuoteFallback = validateResponsibilityRead({
  output: {
    summary: 'A legacy record with a grounded non-duty quote.',
    responsibilities: [{
      responsibilityId: 'legacy_grounded_record',
      label: 'Legacy grounded record',
      role: 'Operations',
      action: 'maintain',
      object: 'legacy record',
      evidenceQuote: 'Operational ownership statement.',
      chunkId,
    }],
  },
  documentId,
  segment,
  fileType: 'text/plain',
  chunks: [{
    id: chunkId,
    documentId,
    rawText: 'Operational ownership statement.',
  }],
});
assert.equal(
  unmappedQuoteFallback.elements.length,
  1,
  'a grounded quote with no resolvable duty span keeps the safe legacy validation path',
);
const scheduler = new ResponsibilityOmissionRetryScheduler();
const schedulerOmissions = [
  { chunkId, spanIndex: 0, sourceSpan: 'Finance checks invoice totals.' },
  { chunkId, spanIndex: 1, sourceSpan: 'Finance emails approved invoices.' },
  { chunkId: otherChunkId, spanIndex: 0, sourceSpan: 'Sales receives approved invoices.' },
];
const firstScheduled = scheduler.next({
  omissions: schedulerOmissions,
  chunks: [{ id: chunkId }, { id: otherChunkId }],
  sourceReadChunkIds: new Set([chunkId, otherChunkId]),
});
assert.equal(firstScheduled.kind, 'attempt');
assert.equal(firstScheduled.kind === 'attempt' && firstScheduled.chunkId, chunkId);
assert.equal(
  firstScheduled.kind === 'attempt' &&
    firstScheduled.omissions[0]?.rankFeatures.chunkOmissionCount,
  2,
);
assert.equal(
  firstScheduled.kind === 'attempt' &&
    firstScheduled.omissions[0]?.rankFeatures.sourceChunkIndex,
  0,
);
scheduler.recordAttempt(chunkId, 'zero_accept');
const afterZeroAccept = scheduler.next({
  omissions: schedulerOmissions,
  chunks: [{ id: chunkId }, { id: otherChunkId }],
  sourceReadChunkIds: new Set([chunkId, otherChunkId]),
});
assert.equal(afterZeroAccept.kind, 'attempt');
assert.equal(
  afterZeroAccept.kind === 'attempt' && afterZeroAccept.chunkId,
  otherChunkId,
  'zero_accept exhausts that chunk and advances to the next ranked chunk',
);
const noSourceScheduler = new ResponsibilityOmissionRetryScheduler();
const noSourceDecision = noSourceScheduler.next({
  omissions: schedulerOmissions,
  chunks: [{ id: chunkId }, { id: otherChunkId }],
  sourceReadChunkIds: new Set([otherChunkId]),
});
assert.equal(noSourceDecision.kind, 'no_source_read', 'missing source read is a loud decision');
const afterNoSource = noSourceScheduler.next({
  omissions: schedulerOmissions,
  chunks: [{ id: chunkId }, { id: otherChunkId }],
  sourceReadChunkIds: new Set([otherChunkId]),
});
assert.equal(afterNoSource.kind, 'attempt');
assert.equal(afterNoSource.kind === 'attempt' && afterNoSource.chunkId, otherChunkId);
const syntheticSegments = buildSyntheticResponsibilitySegments({
  chunks: [
    {
      id: chunkId,
      documentId,
      rawText: '[Finance]\n- Approve invoice totals before close.',
    },
    {
      id: otherChunkId,
      documentId,
      rawText: 'Background narrative without a duty.',
    },
  ],
  existingSegments: [],
});
assert.equal(syntheticSegments.length, 1, 'orphan duty chunks receive a base read');
assert.deepEqual(syntheticSegments[0]?.chunkIds, [chunkId]);
assert.equal(syntheticSegments[0]?.shape, 'responsibilities');
assert.doesNotThrow(() =>
  assertResponsibilityDutyChunksHaveBaseReads({
    chunks: [{
      id: chunkId,
      documentId,
      rawText: '[Finance]\n- Approve invoice totals before close.',
    }],
    baseReadSegments: syntheticSegments,
  }),
);
assert.throws(
  () =>
    assertResponsibilityDutyChunksHaveBaseReads({
      chunks: [{
        id: chunkId,
        documentId,
        rawText: '[Finance]\n- Approve invoice totals before close.',
      }],
      baseReadSegments: [],
    }),
  /missing base reads/,
  'a ranked duty chunk can never reach retry scheduling without a base read',
);
const syntheticCovered = buildSyntheticResponsibilitySegments({
  chunks: [{ id: chunkId, documentId, rawText: '- Finance approves invoices.' }],
  existingSegments: [segment],
});
assert.equal(syntheticCovered.length, 0, 'existing responsibility base reads are never duplicated');
const baseReadPlan = buildResponsibilityBaseReadPlan({
  chunks: [
    { id: chunkId, documentId, rawText: '- Finance approves invoices.' },
    { id: otherChunkId, documentId, rawText: 'Sales must send the approved package.' },
  ],
  responsibilitySegments: [segment],
});
const genericInventoryChunks = [{
  id: 'generic_inventory_chunk',
  documentId,
  rawText:
    '[Service Desk]\n' +
    '- Review intake packets.\n' +
    '2. Upload signed notices into Hub North, Hub South, and Hub West.\n' +
    '- Prepare summaries and then send confirmations.\n' +
    'Service Lead must monitor the shared queue.\n' +
    '- Review intake packets.',
}];
const genericInventoryA = buildResponsibilitySourceInventory(genericInventoryChunks);
const genericInventoryB = buildResponsibilitySourceInventory(genericInventoryChunks);
assert.deepEqual(genericInventoryA, genericInventoryB, 'identical inventory reruns are byte-stable');

const actorContextChunk = {
  id: 'actor_context_chunk',
  documentId,
  rawText:
    '[Fleet Office]\n' +
    '1. Review route packets.\n' +
    '2. Upload signed notices.\n' +
    '[the following notes]\n' +
    '3. Archive delivery records.\n' +
    'Special handling scenarios:\n' +
    '4. Update the dispatch board.',
};
const actorContextInventory = buildResponsibilitySourceInventory([actorContextChunk]);
assert.equal(actorContextInventory.seeds.length, 4);
assert.ok(
  actorContextInventory.seeds.every((seed) => seed.sourceSpan.startsWith('[Fleet Office] ')),
  'a proven actor persists across sibling duties and inert descriptive headings',
);
assert.ok(
  actorContextInventory.seeds.every((seed) =>
    !/\[(?:the following notes|Special handling scenarios)\]/i.test(seed.sourceSpan)
  ),
  'descriptive bracket and colon labels never become owners',
);

const descriptiveOnlyInventory = buildResponsibilitySourceInventory([{
  id: 'descriptive_only_chunk',
  documentId,
  rawText:
    '[These scenarios]\n' +
    '1. Review route packets.\n' +
    '2. Archive delivery records.',
}]);
assert.ok(
  descriptiveOnlyInventory.seeds.every((seed) => !seed.sourceSpan.startsWith('[These scenarios] ')),
  'a descriptive heading cannot invent an actor when no actor was proven',
);

const actorResetInventory = buildResponsibilitySourceInventory([{
  id: 'actor_reset_boundary_chunk',
  documentId,
  rawText:
    '[Fleet Office]\n' +
    '- Review route packets\n' +
    '  before dispatch.\n\n' +
    'This paragraph explains an unrelated policy.\n\n' +
    '- Archive delivery records.\n' +
    '# Returns\n' +
    '- Update the return ledger.',
}]);
assert.match(
  actorResetInventory.seeds[0]!.sourceSpan,
  /^\[Fleet Office\]\s+Review route packets before dispatch\./,
  'ordinary prose continuation inside a duty preserves actor context',
);
assert.ok(
  !actorResetInventory.seeds[1]!.sourceSpan.startsWith('[Fleet Office] '),
  'unrelated narrative followed by a fresh list resets actor context',
);
assert.ok(
  !actorResetInventory.seeds[2]!.sourceSpan.startsWith('[Fleet Office] '),
  'a markdown section heading resets actor context',
);

const resetActorInventory = buildResponsibilitySourceInventory([{
  id: 'reset_actor_chunk',
  documentId,
  rawText:
    '[Fleet Office]\n' +
    '- Review route packets.\n' +
    '[Returns Office]\n' +
    '- Archive return slips.',
}]);
assert.deepEqual(
  resetActorInventory.seeds.map((seed) => seed.sourceSpan.match(/^\[([^\]]+)\]/)?.[1]),
  ['Fleet Office', 'Returns Office'],
  'a new proven actor replaces the prior actor',
);

const resetActorAfterNarrativeInventory = buildResponsibilitySourceInventory([{
  id: 'reset_actor_after_narrative_chunk',
  documentId,
  rawText:
    '[Fleet Office]\n' +
    '- Review route packets.\n\n' +
    'This paragraph closes the old section.\n\n' +
    '[Returns Office]\n' +
    '- Archive return slips.',
}]);
assert.match(
  resetActorAfterNarrativeInventory.seeds[1]!.sourceSpan,
  /^\[Returns Office\]\s+Archive return slips\./,
  'a new proven actor after unrelated narrative clears the pending old-actor reset',
);

const directActorConflictInventory = buildResponsibilitySourceInventory([{
  id: 'direct_actor_conflict_chunk',
  documentId,
  rawText: '[Warehouse Team] Compliance Lead reviews audit packets.',
}]);
assert.equal(directActorConflictInventory.seeds.length, 1);
assert.match(
  directActorConflictInventory.seeds[0]!.sourceSpan,
  /^\[Compliance Lead\]\s+reviews audit packets\./,
  'a direct duty subject overrides a conflicting outer formatting tag',
);
assert.ok(
  directActorConflictInventory.seeds[0]!.parseDiagnostics.includes('outer_actor_overridden'),
  'an outer actor override remains visible in the inventory audit',
);

const markedDirectActorCases = [
  ['1.', 'reviews route packets'],
  ['1)', 'downloads delivery records'],
  ['12.', 'updates the dispatch board'],
  ['12)', 'archives approved notices'],
  ['-', 'submits compliance forms'],
  ['*', 'emails approved packets'],
  ['•', 'publishes the final notice'],
] as const;
for (const [marker, duty] of markedDirectActorCases) {
  const rawText = `[Warehouse Team] ${marker} Compliance Lead ${duty}.`;
  const markedInventory = buildResponsibilitySourceInventory([{
    id: `marked_direct_actor_${marker.replace(/[^a-z0-9]/gi, 'marker')}`,
    documentId,
    rawText,
  }]);
  assert.equal(markedInventory.seeds.length, 1);
  assert.match(
    markedInventory.seeds[0]!.sourceSpan,
    new RegExp(`^\\[Compliance Lead\\]\\s+${duty.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.`),
    `one ${marker} source list marker may precede a direct inner actor`,
  );
  assert.equal(markedInventory.seeds[0]!.evidenceQuote, rawText);
  assert.equal(rawText.slice(
    markedInventory.seeds[0]!.sourceStart,
    markedInventory.seeds[0]!.sourceEnd,
  ), rawText, 'marker handling preserves raw quote offsets');
}

for (const rawText of [
  '[Warehouse Team] 2024 records show compliance.',
  '[Warehouse Team] A. Submit compliance forms.',
  '[Warehouse Team] 1. - Compliance Lead submits forms.',
]) {
  const markerNegative = buildResponsibilitySourceInventory([{
    id: `marker_negative_${rawText.length}`,
    documentId,
    rawText,
  }]);
  assert.ok(
    markerNegative.seeds.every((seed) => !/^\[Compliance Lead\]/.test(seed.sourceSpan)),
    'years, alphabetic markers, and multiple markers cannot create an inner actor override',
  );
}

const markedBareVerbInventory = buildResponsibilitySourceInventory([{
  id: 'marked_bare_verb_chunk',
  documentId,
  rawText: '[Warehouse Team] 1. download delivery records.',
}]);
assert.ok(
  markedBareVerbInventory.seeds.every((seed) => !/^\[download\]/i.test(seed.sourceSpan)),
  'a marker followed by a bare duty verb does not invent an inner actor',
);

const markedPrepositionalActorInventory = buildResponsibilitySourceInventory([{
  id: 'marked_prepositional_actor_chunk',
  documentId,
  rawText: '[Warehouse Team] 1. Warehouse Team assists Dispatch Office in downloading route packets.',
}]);
assert.match(
  markedPrepositionalActorInventory.seeds[0]!.sourceSpan,
  /^\[Warehouse Team\]/,
  'a phrase ending in a preposition cannot override the outer actor',
);
assert.ok(
  !/^\[Warehouse Team assists Dispatch Office in\]/.test(
    markedPrepositionalActorInventory.seeds[0]!.sourceSpan,
  ),
  'an intervening helper phrase is not misclassified as a direct actor',
);

const recipientControlInventory = buildResponsibilitySourceInventory([{
  id: 'recipient_control_chunk',
  documentId,
  rawText: '[Warehouse Team] Send audit packets to Compliance Lead.',
}]);
assert.match(
  recipientControlInventory.seeds[0]!.sourceSpan,
  /^\[Warehouse Team\]\s+Send audit packets to Compliance Lead\./,
  'a recipient mention does not override the governing actor',
);

const conditionLabelInventory = buildResponsibilitySourceInventory([{
  id: 'condition_label_chunk',
  documentId,
  rawText: '[When Compliance Lead responds]\n- Submit the audit packet.',
}]);
assert.ok(
  conditionLabelInventory.seeds.every((seed) =>
    !seed.sourceSpan.startsWith('[When Compliance Lead responds] ')
  ),
  'a condition label remains descriptive and cannot become an actor',
);
const conditionLabelCompletion = completeAndMatchResponsibilityInventory({
  inventorySeeds: conditionLabelInventory.seeds,
  proposals: { summary: 'No model discoveries were returned.', responsibilities: [] },
  chunks: [{
    id: 'condition_label_chunk',
    documentId,
    rawText: '[When Compliance Lead responds]\n- Submit the audit packet.',
  }],
});
assert.equal(
  conditionLabelCompletion.audit.mergeReadyInventoryCount,
  0,
  'ambiguous actor syntax remains incomplete instead of guessing an owner',
);

const systemLabelConflictInventory = buildResponsibilitySourceInventory([{
  id: 'system_label_conflict_chunk',
  documentId,
  rawText: '[Dispatch Portal] Fleet Lead reviews route packets.',
}]);
assert.match(
  systemLabelConflictInventory.seeds[0]!.sourceSpan,
  /^\[Fleet Lead\]\s+reviews route packets\./,
  'a system-like outer label does not outrank a direct duty subject',
);

const coordinatedDutyChunk = {
  id: 'coordinated_duty_chunk',
  documentId,
  rawText:
    '[Quality Office]\n' +
    '- Review sample packets and ensure technical requirements match approved standards.',
};
const coordinatedDutyInventory = buildResponsibilitySourceInventory([coordinatedDutyChunk]);
const coordinatedDutyRepeat = buildResponsibilitySourceInventory([coordinatedDutyChunk]);
assert.deepEqual(
  coordinatedDutyInventory,
  coordinatedDutyRepeat,
  'coordinated duty reruns preserve child IDs, source order, and audit order',
);
assert.equal(
  coordinatedDutyInventory.seeds.length,
  2,
  'a coordinated duty splits only when each child has its own action and object',
);
assert.ok(
  coordinatedDutyInventory.seeds.every((seed) =>
    seed.sourceSpan.startsWith('[Quality Office] ') &&
    /\b(?:review\s+sample packets|ensure\s+technical requirements)\b/i.test(seed.sourceSpan)
  ),
  'coherent split children retain the proven actor, action, and source-derived object',
);
assert.ok(
  coordinatedDutyInventory.seeds.every((seed) =>
    coordinatedDutyChunk.rawText.slice(seed.sourceStart, seed.sourceEnd) === seed.evidenceQuote
  ),
  'actor normalization never changes exact evidence quote or offsets',
);

const incoherentSplitInventory = buildResponsibilitySourceInventory([{
  id: 'incoherent_split_chunk',
  documentId,
  rawText: '[Quality Office]\n- Review and ensure technical requirements match approved standards.',
}]);
assert.equal(incoherentSplitInventory.seeds.length, 1);
assert.deepEqual(
  incoherentSplitInventory.seeds[0]!.parseDiagnostics,
  ['ambiguous_multi_verb'],
  'an incoherent split stays as one explicit incomplete parent',
);
assert.equal(
  incoherentSplitInventory.auditParents.length,
  0,
  'an incoherent split never creates misleading active children or an accepted split audit',
);

assert.equal(genericInventoryA.seeds.length, 8, 'all generic duties and destination children are active');
assert.equal(
  genericInventoryA.seeds.filter((seed) => seed.splitKind === 'destination').length,
  3,
  'a source-only destination list creates one child per destination',
);
assert.equal(
  genericInventoryA.seeds.filter((seed) => seed.splitKind === 'multi_verb').length,
  2,
  'a clear compound duty creates one exact child per action and object clause',
);
assert.ok(
  genericInventoryA.seeds.every((seed) =>
    genericInventoryChunks[0]!.rawText.slice(seed.sourceStart, seed.sourceEnd) === seed.evidenceQuote
  ),
  'every active seed keeps an exact raw quote and offset binding',
);
const repeatedInventory = genericInventoryA.seeds.filter((seed) => /Review intake packets/.test(seed.sourceSpan));
assert.equal(repeatedInventory.length, 2);
assert.notEqual(repeatedInventory[0]?.inventorySeedId, repeatedInventory[1]?.inventorySeedId);
assert.notEqual(repeatedInventory[0]?.sourceStart, repeatedInventory[1]?.sourceStart);
assert.equal(
  genericInventoryA.auditParents.filter((parent) => parent.decision === 'split_destination').length,
  1,
);
assert.equal(
  genericInventoryA.auditParents.filter((parent) => parent.decision === 'split_multi_verb').length,
  1,
);
const ambiguousInventory = buildResponsibilitySourceInventory([{
  id: 'ambiguous_inventory_chunk',
  documentId,
  rawText: '- Review and then send confirmations.',
}]);
assert.equal(ambiguousInventory.seeds.length, 1);
assert.deepEqual(ambiguousInventory.seeds[0]?.parseDiagnostics, ['ambiguous_multi_verb']);
const attributeInventory = buildResponsibilitySourceInventory([{
  id: 'attribute_inventory_chunk',
  documentId,
  rawText: '- Review color, size, and material fields.',
}]);
assert.equal(attributeInventory.seeds.length, 1, 'an attribute list is not split as destinations');
assert.equal(attributeInventory.auditParents.length, 0);
const deterministicInventory = completeAndMatchResponsibilityInventory({
  inventorySeeds: genericInventoryA.seeds,
  proposals: { summary: 'No model discoveries were returned.', responsibilities: [] },
  chunks: genericInventoryChunks,
});
assert.equal(deterministicInventory.audit.modelDiscoveredInventoryCount, 0);
assert.ok(
  deterministicInventory.output.responsibilities.some((record) =>
    record.object === 'signed notices into Hub North'
  ),
  'destination completion keeps the shared object head and only its destination',
);
assert.ok(
  deterministicInventory.audit.mergeReadyInventoryCount > 0,
  'clear list duties complete without model output',
);
const deterministicValidation = validateResponsibilityRead({
  output: deterministicInventory.output,
  documentId,
  segment: {
    segmentId: 'generic_inventory_segment',
    title: 'Generic inventory',
    shape: 'responsibilities',
    summary: 'Generic inventory validation segment.',
    chunkIds: ['generic_inventory_chunk'],
  },
  chunks: genericInventoryChunks,
  allCoveredChunkIds: new Set(['generic_inventory_chunk']),
  inventorySeeds: genericInventoryA.seeds,
});
const destinationSeedIds = genericInventoryA.seeds
  .filter((seed) => seed.splitKind === 'destination')
  .map((seed) => seed.inventorySeedId);
assert.equal(
  deterministicValidation.elements.filter((element) => destinationSeedIds.includes(element.elementId)).length,
  3,
  'pre-split destination children validate once each instead of expanding again',
);
assert.equal(
  deterministicValidation.elements.length,
  5,
  'deterministic validation emits only the five clear seeds',
);
assert.ok(
  deterministicValidation.elements.every((element) => !element.elementId.includes('_dst_')),
  'pre-split destination validation creates no hidden expansion artifacts',
);
assert.ok(
  destinationSeedIds.every((id) => deterministicValidation.completeElementIds.includes(id)),
  'destination merge-ready IDs remain inventory seed IDs',
);
assert.equal(
  findResponsibilityOmissions({
    chunks: genericInventoryChunks,
    elements: deterministicValidation.elements,
    inventorySeeds: genericInventoryA.seeds,
  }).filter((item) => /Hub North/.test(item.sourceSpan)).length,
  0,
  'a destination parent is covered when all inventory children are complete',
);
const destinationParent = genericInventoryA.auditParents.find(
  (parent) => parent.decision === 'split_destination',
)!;
const shortenedQuote = destinationParent.evidenceQuote.replace(/\.$/, '');
const partialOverlapProposal = completeAndMatchResponsibilityInventory({
  inventorySeeds: genericInventoryA.seeds,
  proposals: {
    summary: 'A shortened overlapping quote must remain audit only.',
    responsibilities: [{
      responsibilityId: 'partial_overlap_proposal',
      label: 'Upload signed notices',
      role: 'Service Desk',
      action: 'upload',
      object: 'signed notices into Hub North, Hub South, and Hub West',
      trigger: null,
      requiredSystem: null,
      ownerName: null,
      department: null,
      evidenceQuote: shortenedQuote,
      chunkId: 'generic_inventory_chunk',
    }],
  },
  chunks: genericInventoryChunks,
});
assert.deepEqual(
  partialOverlapProposal.audit.unmatchedProposalIds,
  ['partial_overlap_proposal'],
  'partial-overlap proposals are rejected without creating overlapping seeds',
);
const ambiguousCompletion = completeAndMatchResponsibilityInventory({
  inventorySeeds: ambiguousInventory.seeds,
  proposals: { summary: 'No model discoveries were returned.', responsibilities: [] },
  chunks: [{
    id: 'ambiguous_inventory_chunk',
    documentId,
    rawText: '- Review and then send confirmations.',
  }],
});
assert.equal(ambiguousCompletion.output.responsibilities.length, 0);
assert.deepEqual(ambiguousCompletion.audit.incompleteSeedIds, [ambiguousInventory.seeds[0]!.inventorySeedId]);
const unmatchedProposal = completeAndMatchResponsibilityInventory({
  inventorySeeds: attributeInventory.seeds,
  proposals: {
    summary: 'One unmatched proposal is retained only in audit.',
    responsibilities: [{
      responsibilityId: 'proposal_unmatched',
      label: 'Invented duty',
      role: 'Service Desk',
      action: 'send',
      object: 'an invented report',
      trigger: null,
      requiredSystem: null,
      ownerName: null,
      department: null,
      evidenceQuote: 'Invented source text.',
      chunkId: 'attribute_inventory_chunk',
    }],
  },
  chunks: [{
    id: 'attribute_inventory_chunk',
    documentId,
    rawText: '- Review color, size, and material fields.',
  }],
});
assert.deepEqual(unmatchedProposal.audit.unmatchedProposalIds, ['proposal_unmatched']);
assert.ok(!unmatchedProposal.output.responsibilities.some((record) => record.responsibilityId === 'proposal_unmatched'));
const discoveryChunks = [{
  id: 'discovery_inventory_chunk',
  documentId,
  rawText: '- Service Desk reviews intake packets.\n- Service Desk sends notices.',
}];
const discoveryFullInventory = buildResponsibilitySourceInventory(discoveryChunks);
const discoveryInitialSeed = discoveryFullInventory.seeds[0]!;
const discoveryMissingSeed = discoveryFullInventory.seeds[1]!;
const reverseUuidOrderInventory = canonicalResponsibilityInventory({
  seeds: [
    { ...discoveryInitialSeed, inventorySeedId: 'seed_first', chunkId: 'z_uuid' },
    { ...discoveryMissingSeed, inventorySeedId: 'seed_second', chunkId: 'a_uuid' },
  ],
  chunks: [{ id: 'z_uuid' }, { id: 'a_uuid' }],
});
assert.deepEqual(
  reverseUuidOrderInventory.map((seed) => seed.inventorySeedId),
  ['seed_first', 'seed_second'],
  'inventory follows document chunk order rather than UUID order',
);
const orderedDestinationInventory = buildResponsibilitySourceInventory([{
  id: 'ordered_destination_chunk',
  documentId,
  rawText: '- Service Desk uploads packets into Hub Zebra, Hub Alpha, and Hub Middle.',
}]);
assert.deepEqual(
  canonicalResponsibilityInventory({
    seeds: orderedDestinationInventory.seeds,
    chunks: [{ id: 'ordered_destination_chunk' }],
  }).map((seed) => seed.splitValue),
  ['Hub Zebra', 'Hub Alpha', 'Hub Middle'],
  'same-offset destination children preserve their order in the source document',
);
assert.equal(
  canonicalResponsibilityInventory({
    seeds: [discoveryInitialSeed, { ...discoveryInitialSeed }],
    chunks: discoveryChunks,
  }).length,
  1,
  'overlapping segments deduplicate identical inventory seeds',
);
assert.throws(
  () => canonicalResponsibilityInventory({
    seeds: [discoveryInitialSeed, { ...discoveryInitialSeed, sourceEnd: discoveryInitialSeed.sourceEnd + 1 }],
    chunks: discoveryChunks,
  }),
  /Conflicting responsibility inventory seed/,
);
const sourceBoundDiscovery = completeAndMatchResponsibilityInventory({
  inventorySeeds: [discoveryInitialSeed],
  proposals: {
    summary: 'Exact missed duty proposal.',
    responsibilities: [{
      responsibilityId: 'model_proposal_for_missed_duty',
      label: 'Service Desk: send notices',
      role: 'Service Desk',
      action: 'send',
      object: 'notices',
      trigger: null,
      requiredSystem: null,
      ownerName: null,
      department: null,
      evidenceQuote: discoveryMissingSeed.evidenceQuote,
      chunkId: discoveryMissingSeed.chunkId,
    }],
  },
  chunks: discoveryChunks,
});
const inheritedOwnerChunk = {
  id: 'inherited_owner_discovery_chunk',
  documentId,
  rawText: '[Service Desk]\n- Reviews intake packets.',
};
const inheritedOwnerDiscovery = completeAndMatchResponsibilityInventory({
  inventorySeeds: [],
  proposals: {
    summary: 'Inherited owner retry discovery.',
    responsibilities: [{
      responsibilityId: 'inherited_owner_proposal',
      label: 'Review intake packets',
      role: 'Service Desk', action: 'review', object: 'intake packets', trigger: null,
      requiredSystem: null, ownerName: null, department: null,
      evidenceQuote: 'Reviews intake packets.',
      chunkId: inheritedOwnerChunk.id,
    }],
  },
  chunks: [inheritedOwnerChunk],
});
assert.equal(inheritedOwnerDiscovery.inventorySeeds.length, 1);
assert.match(inheritedOwnerDiscovery.inventorySeeds[0]!.sourceSpan, /^\[Service Desk\]/);
assert.match(
  responsibilityCompletionRequest(inheritedOwnerDiscovery.inventorySeeds[0]!).sourceSpan,
  /^\[Service Desk\]/,
  'late completion receives the inherited owner context',
);
const partialQuoteDiscovery = completeAndMatchResponsibilityInventory({
  inventorySeeds: [],
  proposals: {
    summary: 'Partial quote must not claim a full duty.',
    responsibilities: [{
      responsibilityId: 'partial_quote_proposal', label: 'Packets', role: 'Service Desk',
      action: 'review', object: 'packets', trigger: null, requiredSystem: null,
      ownerName: null, department: null, evidenceQuote: 'intake packets',
      chunkId: inheritedOwnerChunk.id,
    }],
  },
  chunks: [inheritedOwnerChunk],
});
assert.equal(partialQuoteDiscovery.output.responsibilities.length, 0);
assert.deepEqual(partialQuoteDiscovery.audit.unmatchedProposalIds, ['partial_quote_proposal']);
const multiChunkFirst = buildResponsibilitySourceInventory([{
  id: 'z_first_chunk', documentId, rawText: '- Service Desk reviews packets.',
}]).seeds[0]!;
const multiChunkSecondChunk = {
  id: 'a_second_chunk', documentId, rawText: '- Service Desk sends notices.',
};
const multiChunkSecond = buildResponsibilitySourceInventory([multiChunkSecondChunk]).seeds[0]!;
const multiChunkRetry = completeAndMatchResponsibilityInventory({
  inventorySeeds: [],
  proposals: {
    summary: 'Second chunk retry.',
    responsibilities: [{
      responsibilityId: 'second_chunk_proposal',
      label: 'Service Desk sends notices',
      role: 'Service Desk', action: 'send', object: 'notices', trigger: null,
      requiredSystem: null, ownerName: null, department: null,
      evidenceQuote: multiChunkSecond.evidenceQuote,
      chunkId: multiChunkSecond.chunkId,
    }],
  },
  chunks: [multiChunkSecondChunk],
});
const multiChunkMerged = canonicalResponsibilityInventory({
  seeds: [multiChunkFirst, ...multiChunkRetry.inventorySeeds],
  chunks: [{ id: 'z_first_chunk' }, { id: 'a_second_chunk' }],
});
assert.deepEqual(
  multiChunkMerged.map((seed) => seed.inventorySeedId),
  [multiChunkFirst.inventorySeedId, multiChunkSecond.inventorySeedId],
  'a one-chunk retry preserves the other chunk and discovers the targeted duty',
);
assert.equal(sourceBoundDiscovery.inventorySeeds.length, 2);
assert.ok(
  sourceBoundDiscovery.inventorySeeds.some(
    (seed) => seed.inventorySeedId === discoveryMissingSeed.inventorySeedId,
  ),
  'an exact missed duty is promoted only through the pure inventory builder',
);
assert.equal(
  sourceBoundDiscovery.output.responsibilities[0]?.responsibilityId,
  discoveryMissingSeed.inventorySeedId,
);
const mergedRetryRecords = mergeResponsibilityRecordsByInventoryId(
  sourceBoundDiscovery.output.responsibilities,
  [{
    ...sourceBoundDiscovery.output.responsibilities.find(
      (record) => record.responsibilityId === discoveryMissingSeed.inventorySeedId,
    )!,
    label: 'Service Desk: send corrected notices',
  }],
);
assert.equal(
  mergedRetryRecords.length,
  sourceBoundDiscovery.output.responsibilities.length,
  'retry merge cannot duplicate an inventory identity',
);
assert.equal(
  mergedRetryRecords.find(
    (record) => record.responsibilityId === discoveryMissingSeed.inventorySeedId,
  )?.label,
  sourceBoundDiscovery.output.responsibilities.find(
    (record) => record.responsibilityId === discoveryMissingSeed.inventorySeedId,
  )?.label,
);
assert.deepEqual(
  lateResidualResponsibilitySeeds({
    seeds: sourceBoundDiscovery.inventorySeeds,
    handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
    completeIds: new Set(),
  }).map((seed) => seed.inventorySeedId),
  [discoveryMissingSeed.inventorySeedId],
  'a late discovered incomplete seed receives a completion pass',
);
assert.deepEqual(
  lateResidualResponsibilitySeeds({
    seeds: sourceBoundDiscovery.inventorySeeds,
    handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
    completeIds: new Set([discoveryMissingSeed.inventorySeedId]),
  }),
  [],
  'a late discovered complete seed skips duplicate completion',
);

// F7. A seed that the exhaustive completion ASKED about but that came back rejected is
// not "handled". The 2026-08-27 production gate lost answer rows 19 and 23 exactly this
// way: every scheduled seed id was passed as `handledIds`, so `lateResidualSeeds` was
// empty, the late pass never ran, and 19 of 40 authorized model calls went unspent.
// `handledIds` must therefore be built from ACCEPTED outcomes, never from scheduled ones.
const f7ScheduledOutcomes = [
  { responsibilityId: discoveryInitialSeed.inventorySeedId, status: 'accepted' as const },
  { responsibilityId: discoveryMissingSeed.inventorySeedId, status: 'validation_rejected' as const },
];
assert.deepEqual(
  lateResidualResponsibilitySeeds({
    seeds: sourceBoundDiscovery.inventorySeeds,
    handledIds: new Set(f7ScheduledOutcomes.map((outcome) => outcome.responsibilityId)),
    completeIds: new Set(),
  }),
  [],
  'the pre-F7 defect: treating every SCHEDULED seed as handled starves the late pass',
);
assert.deepEqual(
  lateResidualResponsibilitySeeds({
    seeds: sourceBoundDiscovery.inventorySeeds,
    handledIds: new Set(
      f7ScheduledOutcomes
        .filter((outcome) => outcome.status === 'accepted')
        .map((outcome) => outcome.responsibilityId),
    ),
    completeIds: new Set(),
  }).map((seed) => seed.inventorySeedId),
  [discoveryMissingSeed.inventorySeedId],
  'a validation-rejected seed reaches the late completion pass',
);

// G6. Reaching the late pass is not enough. The 2026-08-27 measurement showed an identical
// second attempt returns a candidate that fails the same deterministic rule — 95 of 148
// outcomes were rejected. The second attempt must therefore carry the reason codes the
// first candidate was rejected for, so it is a different question, not a repeat.
const g6Seed = sourceBoundDiscovery.inventorySeeds[0]!;
assert.equal(
  responsibilityCompletionRequest(g6Seed).priorRejectionReasons,
  undefined,
  'a first attempt carries no rejection feedback',
);
const g6Request = responsibilityCompletionRequest(g6Seed, [
  'Field fidelity failed: condition_not_preserved_in_trigger',
  'Field fidelity failed: condition_not_preserved_in_trigger',
  '   ',
]);
assert.deepEqual(
  g6Request.priorRejectionReasons,
  ['Field fidelity failed: condition_not_preserved_in_trigger'],
  'rejection feedback is de-duplicated and blank codes are dropped',
);
assert.ok(
  JSON.stringify(g6Request).length > JSON.stringify(responsibilityCompletionRequest(g6Seed)).length,
  'feedback is part of the request payload, so the packer estimates the tokens it will send',
);
assert.deepEqual(
  normalizeResponsibilityPriorRejectionReasons([]),
  undefined,
  'an empty reason list is absent, not an empty array',
);
assert.equal(
  normalizeResponsibilityPriorRejectionReasons(
    Array.from({ length: 20 }, (_, index) => `reason_${index}`),
  )?.length,
  RESPONSIBILITY_PRIOR_REJECTION_REASON_LIMIT,
  'a pathological reason list cannot dominate the batch budget',
);
assert.ok(
  (normalizeResponsibilityPriorRejectionReasons(['x'.repeat(500)]) ?? [''])[0]!.length ===
    RESPONSIBILITY_PRIOR_REJECTION_REASON_MAX_LENGTH,
  'a single oversized reason code is truncated',
);
// The packer must carry the feedback through to the batch the model actually receives.
const g6Pack = packResponsibilityCompletions({
  seeds: [g6Seed],
  remainingCalls: 4,
  remainingInputTokens: 200_000,
  remainingCostUsd: 5,
  fixedInputTokensPerCall: 64,
  fixedOutputTokensPerCall: 64,
  maxInputTokensPerCall: 50_000,
  maxOutputTokensPerCall: 4_000,
  inputCostPerMillionTokensUsd: 1,
  outputCostPerMillionTokensUsd: 1,
  priorRejectionsBySeedId: new Map([
    [g6Seed.inventorySeedId, ['Field fidelity failed: owner_mismatch']],
  ]),
});
assert.deepEqual(
  g6Pack.batches[0]?.requests[0]?.priorRejectionReasons,
  ['Field fidelity failed: owner_mismatch'],
  'the packed late batch carries each seed rejection feedback',
);
assert.ok(
  buildResponsibilityCompletionRequestContent(g6Pack.batches[0]!).includes('owner_mismatch'),
  'the prompt payload the model receives contains the rejection feedback',
);
const lateDiscoverySeed = sourceBoundDiscovery.inventorySeeds.find(
  (seed) => seed.inventorySeedId === discoveryMissingSeed.inventorySeedId,
)!;
const lateDiscoveryRecord = sourceBoundDiscovery.output.responsibilities.find(
  (record) => record.responsibilityId === discoveryMissingSeed.inventorySeedId,
)!;
const lateOrchestrationPack = {
  remainingCalls: 1,
  remainingInputTokens: 500_000,
  remainingCostUsd: 10,
  fixedInputTokensPerCall: 10,
  fixedOutputTokensPerCall: 10,
  maxInputTokensPerCall: 20_000,
  maxOutputTokensPerCall: 20_000,
  inputCostPerMillionTokensUsd: 1,
  outputCostPerMillionTokensUsd: 1,
};
const acceptedLateOrchestration = await runLateResponsibilityCompletion({
  seeds: sourceBoundDiscovery.inventorySeeds,
  handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
  completeIds: new Set(),
  pack: lateOrchestrationPack,
  budget: new SourceReaderBudget({
    maxReadCalls: 1, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
    estimatedInputCostPerMillionTokensUsd: 1, maxRepairAttempts: 0, maxConcurrency: 1,
  }),
  concurrency: 1,
  batchOffset: 5,
  runBatch: async () => ({ completions: [lateDiscoveryRecord] }),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.deepEqual(acceptedLateOrchestration.residualSeeds, [lateDiscoverySeed]);
assert.deepEqual(acceptedLateOrchestration.final.records.map((record) => record.responsibilityId), [
  discoveryMissingSeed.inventorySeedId,
]);
assert.equal(acceptedLateOrchestration.final.outcomes[0]?.batchIndex, 5);
assert.equal(acceptedLateOrchestration.final.degraded, false);
const rejectedLateOrchestration = await runLateResponsibilityCompletion({
  seeds: sourceBoundDiscovery.inventorySeeds,
  handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
  completeIds: new Set(),
  pack: lateOrchestrationPack,
  budget: new SourceReaderBudget({
    maxReadCalls: 1, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
    estimatedInputCostPerMillionTokensUsd: 1, maxRepairAttempts: 0, maxConcurrency: 1,
  }),
  concurrency: 1,
  batchOffset: 6,
  runBatch: async () => ({ completions: [lateDiscoveryRecord] }),
  validateCompletion: () => ({ complete: false, reasons: ['rejected_by_validator'] }),
});
assert.equal(rejectedLateOrchestration.final.records.length, 0);
assert.equal(rejectedLateOrchestration.final.outcomes[0]?.status, 'validation_rejected');
assert.equal(rejectedLateOrchestration.final.degraded, true);
const blockedLateOrchestration = await runLateResponsibilityCompletion({
  seeds: sourceBoundDiscovery.inventorySeeds,
  handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
  completeIds: new Set(),
  pack: { ...lateOrchestrationPack, remainingCalls: 0 },
  budget: new SourceReaderBudget({
    maxReadCalls: 1, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
    estimatedInputCostPerMillionTokensUsd: 1, maxRepairAttempts: 0, maxConcurrency: 1,
  }),
  concurrency: 1,
  batchOffset: 7,
  runBatch: async () => { throw new Error('unscheduled batch must not run'); },
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.deepEqual(blockedLateOrchestration.pack.unscheduledIds, [discoveryMissingSeed.inventorySeedId]);
assert.equal(blockedLateOrchestration.final.outcomes[0]?.status, 'budget_exhausted');
assert.equal(blockedLateOrchestration.final.degraded, true);

// ---------------------------------------------------------------------------
// F3. The late-completion acceptance seam.
//
// Plan: plan_r2_source_bound_final_record_correction.md, phase F3.
// The existing late path stays the ONLY late path. Each candidate it already
// returns is passed through `correctResponsibilityFinalRecord` BEFORE the
// existing strict-improvement selection and the caller's existing
// `validateResponsibilityRead`, so the record that is judged is the record that
// is kept. No new seed queue, dispatch, budget reservation, model call or retry
// may appear. All source text here is invented.
// ---------------------------------------------------------------------------

const lateBudget = () => new SourceReaderBudget({
  maxReadCalls: 1, maxInputTokens: 500_000, maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 1, maxRepairAttempts: 0, maxConcurrency: 1,
});

// F3a. An inflected late candidate is corrected in place, with exactly one dispatch,
// and the validator sees the CORRECTED record, not the raw one.
let f3DispatchCount = 0;
const f3Validated: Array<{ action: string; object: string }> = [];
const f3CorrectedLate = await runLateResponsibilityCompletion({
  seeds: sourceBoundDiscovery.inventorySeeds,
  handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
  completeIds: new Set(),
  pack: lateOrchestrationPack,
  budget: lateBudget(),
  concurrency: 1,
  batchOffset: 8,
  runBatch: async () => {
    f3DispatchCount += 1;
    return { completions: [{ ...lateDiscoveryRecord, action: 'sends' }] };
  },
  validateCompletion: (record) => {
    f3Validated.push({ action: record.action, object: record.object });
    return { complete: true, reasons: [] };
  },
});
assert.equal(f3DispatchCount, 1, 'F3 adds no second dispatch for a corrected late candidate');
assert.equal(
  f3CorrectedLate.corrections.length,
  1,
  'every late candidate is offered to the corrector exactly once',
);
assert.equal(f3CorrectedLate.corrections[0]?.accepted, true, 'the inflected action is correctable');
assert.deepEqual(
  f3CorrectedLate.corrections[0]?.reasons,
  ['action_inflection_normalized'],
  'the correction reports its own named reason',
);
assert.equal(
  f3CorrectedLate.corrections[0]?.seedId,
  lateDiscoverySeed.inventorySeedId,
  'the correction audit is bound to the seed it corrected',
);
assert.equal(
  f3CorrectedLate.corrections[0]?.sourceSpanSha256,
  lateDiscoverySeed.sourceSpanSha256,
  'the correction audit carries the source span hash',
);
assert.equal(
  f3Validated[0]?.action,
  'send',
  'the existing validator judges the corrected record, not the raw candidate',
);
assert.equal(
  f3CorrectedLate.final.records[0]?.action,
  'send',
  'the corrected record is the record the late path keeps',
);
assert.equal(
  f3CorrectedLate.final.records[0]?.responsibilityId,
  lateDiscoverySeed.inventorySeedId,
  'correction never changes the seed identity a record is bound to',
);
assert.equal(f3CorrectedLate.final.degraded, false);

// F3b. A refused correction leaves the candidate byte-identical and the existing
// incomplete outcome stands. The refusal reason is still recorded.
let f3RefusedDispatchCount = 0;
const f3RefusedLate = await runLateResponsibilityCompletion({
  seeds: sourceBoundDiscovery.inventorySeeds,
  handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
  completeIds: new Set(),
  pack: lateOrchestrationPack,
  budget: lateBudget(),
  concurrency: 1,
  batchOffset: 9,
  runBatch: async () => {
    f3RefusedDispatchCount += 1;
    // An empty action can never be invented, so the corrector must refuse.
    return { completions: [{ ...lateDiscoveryRecord, action: '' }] };
  },
  validateCompletion: (record) => ({
    complete: false,
    reasons: [`late_candidate_incomplete:${record.action === '' ? 'empty_action' : 'other'}`],
  }),
});
assert.equal(f3RefusedDispatchCount, 1, 'a refused correction triggers no extra dispatch or retry');
assert.equal(f3RefusedLate.corrections[0]?.accepted, false);
assert.deepEqual(
  f3RefusedLate.corrections[0]?.reasons,
  ['missing_action'],
  'the refusal is named, never silent',
);
assert.equal(f3RefusedLate.corrections[0]?.after, null, 'a refused correction proposes nothing');
assert.equal(f3RefusedLate.final.records.length, 0, 'a refused candidate is not accepted');
assert.equal(
  f3RefusedLate.final.outcomes[0]?.status,
  'validation_rejected',
  'the existing incomplete outcome is preserved unchanged',
);
assert.ok(
  f3RefusedLate.final.outcomes[0]?.reasons.includes('late_candidate_incomplete:empty_action'),
  'the existing validator still sees the untouched candidate when correction is refused',
);
assert.equal(f3RefusedLate.final.degraded, true);

// F3c. The seam is confined to the late path: the shared batch executor is
// unchanged for any caller that does not supply the correction hook.
const f3UncorrectedExecution = await executeResponsibilityCompletionBatches({
  budget: lateBudget(),
  batches: packResponsibilityCompletions({
    seeds: [lateDiscoverySeed],
    ...lateOrchestrationPack,
  }).batches,
  concurrency: 1,
  baselines: [{ responsibilityId: lateDiscoverySeed.inventorySeedId, complete: false }],
  runBatch: async () => ({ completions: [{ ...lateDiscoveryRecord, action: 'sends' }] }),
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.equal(
  f3UncorrectedExecution[0]?.records[0]?.action,
  'sends',
  'without the F3 hook the shared executor still returns the raw candidate',
);

// F3d. Over-budget seeds stay incomplete: the seam never buys a call the existing
// path refused to make.
const f3OverBudgetLate = await runLateResponsibilityCompletion({
  seeds: sourceBoundDiscovery.inventorySeeds,
  handledIds: new Set([discoveryInitialSeed.inventorySeedId]),
  completeIds: new Set(),
  pack: { ...lateOrchestrationPack, remainingCalls: 0 },
  budget: lateBudget(),
  concurrency: 1,
  batchOffset: 10,
  runBatch: async () => { throw new Error('F3 must not dispatch an unscheduled batch'); },
  validateCompletion: () => ({ complete: true, reasons: [] }),
});
assert.equal(f3OverBudgetLate.corrections.length, 0, 'no candidate means no correction');
assert.equal(f3OverBudgetLate.final.outcomes[0]?.status, 'budget_exhausted');
assert.equal(f3OverBudgetLate.final.degraded, true);

// F3e. The production seam is the existing late path only. Prove by reading the
// production file that the correction is wired through `runLateResponsibilityCompletion`
// and that no new completion stage was introduced alongside it.
const f3WorkflowReadSource = readFileSync(
  new URL('../lib/source-workflow-read.ts', import.meta.url),
  'utf8',
).replace(/\r\n/g, '\n');
const f3ReaderSource = readFileSync(
  new URL('../lib/responsibility-reader.ts', import.meta.url),
  'utf8',
).replace(/\r\n/g, '\n');
// F4 moved the call site into the one shared seam. The corrector must be invoked from
// exactly one place in the whole codebase, and the orchestrator must reach it only
// through that seam — never by calling the corrector itself.
assert.equal(
  (f3ReaderSource.match(/correctResponsibilityFinalRecord\(\{/g) ?? []).length,
  1,
  'exactly one call site applies the final-record correction, inside the shared seam',
);
assert.equal(
  (f3WorkflowReadSource.match(/correctResponsibilityFinalRecord\(/g) ?? []).length,
  0,
  'the orchestrator never calls the corrector directly, only through the shared seam',
);
assert.equal(
  (f3WorkflowReadSource.match(/runLateResponsibilityCompletion\(\{/g) ?? []).length,
  1,
  'the late path still has exactly one production call site',
);
assert.ok(
  f3WorkflowReadSource.indexOf('responsibilityFinalRecordCorrectionSeam({') <
    f3WorkflowReadSource.indexOf('executeResponsibilityCompletionBatches({'),
  'the seam is constructed before the batch executor that consumes it',
);
const splitDiscoveryQuote =
  '[Service Desk] Service Desk reviews packets and then sends notices.';
const splitDiscoveryPrefix = 'Reference introduction.\n';
const splitDiscovery = completeAndMatchResponsibilityInventory({
  inventorySeeds: [],
  proposals: {
    summary: 'Nonzero-offset split discovery.',
    responsibilities: [{
      responsibilityId: 'split_discovery_proposal',
      label: 'Service Desk duties',
      role: 'Service Desk',
      action: 'review',
      object: 'packets and send notices',
      trigger: null,
      requiredSystem: null,
      ownerName: null,
      department: null,
      evidenceQuote: splitDiscoveryQuote,
      chunkId: 'split_discovery_chunk',
    }],
  },
  chunks: [{
    id: 'split_discovery_chunk',
    documentId,
    rawText: `${splitDiscoveryPrefix}${splitDiscoveryQuote}`,
  }],
});
assert.ok(splitDiscovery.inventorySeeds.length >= 2);
assert.equal(splitDiscovery.inventoryAuditParents.length, 1);
const relocatedSplitParent = splitDiscovery.inventoryAuditParents[0]!;
assert.ok(relocatedSplitParent.sourceStart >= splitDiscoveryPrefix.length);
assert.deepEqual(
  new Set(relocatedSplitParent.childSeedIds),
  new Set(splitDiscovery.inventorySeeds.map((seed) => seed.inventorySeedId)),
);
assert.ok(
  splitDiscovery.inventorySeeds.every(
    (seed) => seed.parentSeedId === relocatedSplitParent.inventorySeedId,
  ),
);
const validSeed = attributeInventory.seeds[0]!;
assert.throws(
  () => assertResponsibilityInventorySeeds(
    [{ id: 'attribute_inventory_chunk', documentId, rawText: '- Review color, size, and material fields.' }],
    [{ ...validSeed, evidenceQuote: 'wrong quote' }],
  ),
  /quote\/offset mismatch/,
);
assert.throws(
  () => assertResponsibilityInventorySeeds(
    [{ id: 'attribute_inventory_chunk', documentId, rawText: '- Review color, size, and material fields.' }],
    [{ ...validSeed, sourceStart: -1 }],
  ),
  /invalid offsets/,
);
assert.throws(
  () => assertResponsibilityInventorySeeds([], [validSeed]),
  /has no source chunk/,
);
assert.throws(
  () => assertResponsibilityInventorySeeds(
    [{ id: 'attribute_inventory_chunk', documentId, rawText: '- Review color, size, and material fields.' }],
    [validSeed, {
      ...validSeed,
      inventorySeedId: `${validSeed.inventorySeedId}_overlap`,
      sourceStart: validSeed.sourceStart + 1,
      evidenceQuote: '- Review color, size, and material fields.'.slice(
        validSeed.sourceStart + 1,
        validSeed.sourceEnd,
      ),
    }],
  ),
  /Overlapping responsibility inventory recognition/,
);
assert.throws(
  () => buildResponsibilitySourceInventory([
    { id: 'duplicate_inventory_chunk', documentId, rawText: '- Review open requests.' },
    { id: 'duplicate_inventory_chunk', documentId, rawText: '- Review open requests.' },
  ]),
  /Duplicate responsibility inventory chunk ID/,
  'duplicate stable identities fail loudly',
);
assert.equal(baseReadPlan.syntheticBaseReadCount, 1);
assert.equal(baseReadPlan.inventorySeeds.length, 2, 'the production base-read seam exposes inventory seeds');
assert.deepEqual(
  baseReadPlan.durableSegments.flatMap((item) => item.chunkIds),
  [chunkId, otherChunkId],
  'the production base-read seam keeps synthetic responsibility segments durable',
);
const seamScheduler = new ResponsibilityOmissionRetryScheduler();
const seamSkip = seamScheduler.next({
  omissions: [{
    chunkId: otherChunkId,
    spanIndex: 0,
    sourceSpan: 'Sales must send the approved package.',
  }],
  chunks: [{ id: chunkId }, { id: otherChunkId }],
  sourceReadChunkIds: new Set([chunkId]),
});
assert.equal(seamSkip.kind, 'no_source_read');
assert.equal(
  seamScheduler.next({
    omissions: [{
      chunkId: otherChunkId,
      spanIndex: 0,
      sourceSpan: 'Sales must send the approved package.',
    }],
    chunks: [{ id: chunkId }, { id: otherChunkId }],
    sourceReadChunkIds: new Set([chunkId]),
  }).kind,
  'done',
  'the production retry scheduler cannot loop forever after a skipped source read',
);
const seamQuoteRepair = { attempted: true, accepted: true };
const seamAudit = buildResponsibilityPostPassAudit({
  initialOmissions: [],
  finalOmissions: [],
  retries: [{ preOmissionCount: 1, postOmissionCount: 1 }],
  quoteRepair: seamQuoteRepair,
  postPassBudget: { used: 1 },
  syntheticBaseReadCount: baseReadPlan.syntheticBaseReadCount,
});
assert.equal(seamAudit.syntheticBaseReadCount, 1);
assert.equal(seamAudit.responsibilityQuoteRepair, seamQuoteRepair);
assert.equal(seamAudit.responsibilityOmissionAudit.retries.length, 1);
const seamRepairRead = selectResponsibilityQuoteRepairRead([
  {
    segment,
    validation: {
      diagnostics: [{
        responsibilityId: 'bad_quote',
        chunkId,
        failureClass: 'quote_mismatch' as const,
        detail: 'not exact',
        boundedQuote: 'Finance approve invoices.',
        selectedPolicy: 'plain_text',
        validationMethod: 'none',
        alternatePoliciesPassing: [],
        crossSegmentStatus: 'within_segment' as const,
        failureOrigin: 'root' as const,
      }],
    },
  },
]);
assert.equal(seamRepairRead?.segment.segmentId, segment.segmentId);
const selectedForAudit = selectFocusedResponsibilityOmissions(schedulerOmissions, 1);
const selectedAudit = buildResponsibilitySelectedSpanAudit({
  selected: selectedForAudit,
  finalOmissions: [],
  preRecordCount: 2,
  postRecordCount: 3,
  skipped: null,
  sourceShapes: ['process'],
  sourceSegmentIds: ['invoice_process'],
  inResponsibilityBaseRead: false,
});
assert.equal(selectedAudit.length, 1);
assert.equal(selectedAudit[0]?.sourceSpanSha256.length, 64);
assert.equal(selectedAudit[0]?.rankIndex, 0);
assert.equal(selectedAudit[0]?.preRecordCount, 2);
assert.equal(selectedAudit[0]?.postRecordCount, 3);
assert.equal(selectedAudit[0]?.result.accepted, true);
assert.equal(selectedAudit[0]?.inResponsibilityBaseRead, false);
assert.deepEqual(selectedAudit[0]?.sourceShapes, ['process']);
const boundedFinalAudit = buildResponsibilityOmissionAudit({
  initialOmissions: tooManyFocused,
  finalOmissions: Array.from({ length: 35 }, (_, spanIndex) => ({
    chunkId,
    spanIndex,
    sourceSpan: `Finance reviews invoice ${spanIndex}.`,
  })),
  retries: [],
});
assert.equal(boundedFinalAudit.finalUncoveredSpanSample.length, 30);
assert.equal(boundedFinalAudit.finalUncoveredSpanSample[0]?.sourceSpanSha256.length, 64);
const longSpan = `Finance reviews ${'invoice '.repeat(400)}`;
const longAudit = buildResponsibilityOmissionAudit({
  initialOmissions: [],
  finalOmissions: [{ chunkId, spanIndex: 0, sourceSpan: longSpan }],
  retries: [],
});
assert.equal(
  longAudit.finalUncoveredSpanSample[0]?.sourceSpanSha256,
  responsibilitySpanSha256(longSpan.slice(0, 2000)),
  'the persisted span and its hash describe the same bounded text',
);
const groundedCandidates = buildGroundedResponsibilityQuoteCandidates({
  rawText:
    'Finance reviews invoices.\nFinance approves invoice totals before close.\nSales sends reports.',
  failedQuote: 'Finance approve invoice total before close',
});
assert.equal(
  groundedCandidates[0]?.sourceText,
  'Finance approves invoice totals before close.',
  'grounded candidates rank strongest token overlap first',
);
assert.equal(groundedCandidates[0]?.sourceTextSha256.length, 64);
assert.ok(
  buildGroundedResponsibilityQuoteCandidates({
    rawText: `Long preface ${'context '.repeat(80)} Finance approves invoice totals before close. ${'tail '.repeat(100)}`,
    failedQuote: 'approves invoice totals',
  }).some((item) => item.sourceText.length < 1000),
  'quote repair offers a nearby bounded substring as well as the full logical span',
);
assert.deepEqual(
  validateGroundedResponsibilityQuoteSelections({
    repairs: [{
      responsibilityId: 'invoice_approval',
      evidenceQuote: groundedCandidates[0]!.sourceText,
    }],
    offered: [{ responsibilityId: 'invoice_approval', candidates: groundedCandidates }],
  }),
  { ok: true },
);
assert.deepEqual(
  validateGroundedResponsibilityQuoteSelections({
    repairs: [{
      responsibilityId: 'invoice_approval',
      evidenceQuote: 'A freely rewritten quote.',
    }],
    offered: [{ responsibilityId: 'invoice_approval', candidates: groundedCandidates }],
  }),
  { ok: false, responsibilityId: 'invoice_approval' },
  'grounded repair rejects free rewriting',
);
assert.deepEqual(
  sourceDutySpans('[Finance]\n- Approve invoices.\n- Email approved invoices.'),
  ['[Finance] Approve invoices.', '[Finance] Email approved invoices.'],
  'generic thin duty spans preserve owner and source order',
);
assert.deepEqual(
  sourceDutySpans('Finance must approve invoices.\nSales sends the package.'),
  ['Finance must approve invoices.', 'Sales sends the package.'],
  'modal and direct-owner prose are discovered without list markers',
);
assert.match(RESPONSIBILITY_QUOTE_REPAIR_SYSTEM_PROMPT, /\{"repairs":\[\.\.\.\]\}/);
assert.match(RESPONSIBILITY_QUOTE_REPAIR_SYSTEM_PROMPT, /Never rewrite/);
const budgetScheduler = new ResponsibilityOmissionRetryScheduler();
const budgetDecision = budgetScheduler.next({
  omissions: schedulerOmissions,
  chunks: [{ id: chunkId }, { id: otherChunkId }],
  sourceReadChunkIds: new Set([chunkId, otherChunkId]),
});
assert.equal(budgetDecision.kind, 'attempt');
if (budgetDecision.kind === 'attempt') {
  budgetScheduler.recordAttempt(budgetDecision.chunkId, 'budget_exhausted');
}
assert.deepEqual(
  budgetScheduler.next({
    omissions: schedulerOmissions,
    chunks: [{ id: chunkId }, { id: otherChunkId }],
    sourceReadChunkIds: new Set([chunkId, otherChunkId]),
  }),
  { kind: 'done' },
  'budget exhaustion terminates scheduling without a loop',
);
const reAuditChunk = {
  id: chunkId,
  documentId,
  rawText: '- Finance approves invoices.\n- Finance emails approved invoices.',
};
const beforeAcceptedRetry = findResponsibilityOmissions({
  chunks: [reAuditChunk],
  elements: [],
  fileType: 'text/plain',
});
const afterAcceptedRetry = findResponsibilityOmissions({
  chunks: [reAuditChunk],
  elements: [
    {
      ...result.elements[0]!,
      chunkId,
      role: 'Finance',
      action: 'approves',
      object: 'invoices',
      evidenceQuote: 'Finance approves invoices.',
    },
  ],
  fileType: 'text/plain',
});
assert.equal(beforeAcceptedRetry.length, 2);
assert.equal(afterAcceptedRetry.length, 1, 'accepted retry records force a fresh omission audit');

const sameLocalIdRetryA = prefixResponsibilityRetryOutput(output, 0, 1);
const sameLocalIdRetryB = prefixResponsibilityRetryOutput(output, 1, 1);
const sameLocalIdBase = prefixResponsibilityOutput(output, 0);
const collisionResults = [sameLocalIdBase, sameLocalIdRetryA, sameLocalIdRetryB].map(
  (item, index) =>
    validateResponsibilityRead({
      output: item,
      documentId,
      segment,
      chunks: [
        {
          id: chunkId,
          documentId,
          rawText: output.responsibilities[0]!.evidenceQuote,
        },
      ],
    }).elements[0]!,
);
assert.equal(new Set(collisionResults.map((item) => item.elementId)).size, 3);
assertUniqueResponsibilityElementIds(collisionResults);
const collisionMapRefs = collisionResults.map((item) =>
  responsibilityMapElementRef('map-1', item.elementId),
);
assert.equal(new Set(collisionMapRefs).size, collisionMapRefs.length);
assert.throws(
  () => assertUniqueResponsibilityElementIds([collisionResults[0]!, collisionResults[0]!]),
  /Duplicate responsibility elementId/,
);

const boundedBudget = new SourceReaderBudget({
  maxReadCalls: 2,
  maxInputTokens: 100,
  maxEstimatedCostUsd: 1,
  estimatedInputCostPerMillionTokensUsd: 1,
  maxRepairAttempts: 1,
  maxConcurrency: 1,
});
boundedBudget.reserveRepair('first focused retry');
assert.throws(
  () => boundedBudget.reserveRepair('second focused retry'),
  (error) =>
    error instanceof SourceReaderBudgetExceededError && error.check === 'max_repair_attempts',
);
const postPassBudget = new ResponsibilityPostPassBudget({
  maxQuoteRepairsPerSource: 1,
  maxOmissionRetriesPerSource: 2,
  maxOmissionRetriesPerChunk: 1,
});
postPassBudget.reserveQuoteRepair();
postPassBudget.reserveOmissionRetry(chunkId);
postPassBudget.reserveOmissionRetry(otherChunkId);
assert.deepEqual(postPassBudget.snapshot(), {
  quoteRepairs: 1,
  omissionRetries: 2,
  omissionRetriesByChunk: { [chunkId]: 1, [otherChunkId]: 1 },
  limits: {
    maxQuoteRepairsPerSource: 1,
    maxOmissionRetriesPerSource: 2,
    maxOmissionRetriesPerChunk: 1,
  },
});
assert.equal(boundedBudget.snapshot().repairAttempts, 1, 'process repair budget is isolated');
assert.throws(
  () =>
    new ResponsibilityPostPassBudget({
      maxQuoteRepairsPerSource: 2,
      maxOmissionRetriesPerSource: 1,
      maxOmissionRetriesPerChunk: 1,
    }),
  /quote repair cap may not exceed 1/,
);
const exhaustedPostPassBudget = new ResponsibilityPostPassBudget({
  maxQuoteRepairsPerSource: 1,
  maxOmissionRetriesPerSource: 2,
  maxOmissionRetriesPerChunk: 1,
});
exhaustedPostPassBudget.reserveQuoteRepair();
assert.throws(() => exhaustedPostPassBudget.reserveQuoteRepair(), /quote repair allowance exhausted/);
exhaustedPostPassBudget.reserveOmissionRetry(chunkId);
assert.throws(
  () => exhaustedPostPassBudget.reserveOmissionRetry(chunkId),
  /chunk omission allowance exhausted/,
);

const mismatchOutput: ResponsibilityReadOutput = {
  ...output,
  responsibilities: [
    { ...output.responsibilities[0]!, evidenceQuote: 'A paraphrase that is not in the source.' },
  ],
};
const bad = validateResponsibilityRead({
  output: mismatchOutput,
  documentId,
  segment,
  chunks: [{ id: chunkId, documentId, rawText: 'Original text only.' }],
});
assert.equal(bad.elements.length, 0);
assert.equal(bad.diagnostics[0]?.failureClass, 'quote_mismatch');
assert.equal(bad.diagnostics[0]?.selectedPolicy, 'strict_verbatim');
assert.equal(bad.diagnostics[0]?.failureOrigin, 'root');
const patchedRepair = patchResponsibilityQuoteRepairs({
  original: mismatchOutput,
  diagnostics: bad.diagnostics,
  repaired: output,
});
assert.equal(patchedRepair.ok, true);
if (patchedRepair.ok) {
  assert.equal(
    validateResponsibilityRead({
      output: patchedRepair.output,
      documentId,
      segment,
      chunks: [{ id: chunkId, documentId, rawText: output.responsibilities[0]!.evidenceQuote }],
    }).elements.length,
    1,
  );
}
const partialOriginal: ResponsibilityReadOutput = {
  summary: 'Nine quote mismatches.',
  responsibilities: Array.from({ length: 9 }, (_, index) => ({
    ...output.responsibilities[0]!,
    responsibilityId: `partial_${index}`,
    label: `Partial ${index}`,
    evidenceQuote: `paraphrase ${index}`,
  })),
};
const partialDiagnostics = partialOriginal.responsibilities.map((record) => ({
  responsibilityId: record.responsibilityId,
  chunkId,
  failureClass: 'quote_mismatch' as const,
  detail: 'strict mismatch',
  boundedQuote: record.evidenceQuote,
  selectedPolicy: 'strict_verbatim',
  validationMethod: 'none',
  alternatePoliciesPassing: [],
  crossSegmentStatus: 'within_segment' as const,
  failureOrigin: 'root' as const,
}));
const partialRepair = patchResponsibilityQuoteRepairs({
  original: partialOriginal,
  diagnostics: partialDiagnostics,
  repaired: {
    summary: 'Partial exact repairs.',
    responsibilities: partialOriginal.responsibilities.slice(0, 3).map((record, index) => ({
      ...record,
      evidenceQuote: `Exact duty quote ${index}.`,
    })),
  },
});
assert.equal(partialRepair.ok, true, 'partial 3-of-9 quote repair is patchable');
if (partialRepair.ok) {
  const partialValidation = validateResponsibilityRead({
    output: partialRepair.output,
    documentId,
    segment,
    chunks: [
      {
        id: chunkId,
        documentId,
        rawText: 'Exact duty quote 0. Exact duty quote 1. Exact duty quote 2.',
      },
    ],
  });
  assert.equal(
    partialValidation.diagnostics.filter((item) => item.failureClass === 'quote_mismatch').length,
    6,
    'partial quote-only repair strictly reduces nine root mismatches to six',
  );
}
const auditRepairChunk = {
  id: chunkId,
  documentId,
  rawText: '[Finance]\n- Approve invoices in LedgerPro.',
};
const auditRepairOriginal: ResponsibilityReadOutput = {
  summary: 'Quote repair final audit fixture.',
  responsibilities: [
    {
      responsibilityId: 'audit_repair',
      label: 'Approve invoices',
      role: 'Finance',
      action: 'approve',
      object: 'invoices in LedgerPro',
      evidenceQuote: 'Finance handles invoice approval.',
      chunkId,
    },
  ],
};
const auditRepairBeforeValidation = validateResponsibilityRead({
  output: auditRepairOriginal,
  documentId,
  segment,
  chunks: [auditRepairChunk],
  fileType: 'text/plain',
});
const auditRepairInitialOmissions = findResponsibilityOmissions({
  chunks: [auditRepairChunk],
  elements: auditRepairBeforeValidation.elements,
  fileType: 'text/plain',
});
const auditRepairPatched = patchResponsibilityQuoteRepairs({
  original: auditRepairOriginal,
  diagnostics: auditRepairBeforeValidation.diagnostics,
  repaired: {
    summary: 'Exact quote repair.',
    responsibilities: [
      {
        ...auditRepairOriginal.responsibilities[0]!,
        evidenceQuote: 'Approve invoices in LedgerPro.',
      },
    ],
  },
});
assert.equal(auditRepairPatched.ok, true);
if (auditRepairPatched.ok) {
  const auditRepairAfterValidation = validateResponsibilityRead({
    output: auditRepairPatched.output,
    documentId,
    segment,
    chunks: [auditRepairChunk],
    fileType: 'text/plain',
  });
  const auditRepairFinalOmissions = findResponsibilityOmissions({
    chunks: [auditRepairChunk],
    elements: auditRepairAfterValidation.elements,
    fileType: 'text/plain',
  });
  assert.deepEqual(
    buildResponsibilityOmissionAudit({
      initialOmissions: auditRepairInitialOmissions,
      finalOmissions: auditRepairFinalOmissions,
      retries: [],
    }),
    {
      preOmissionCount: 1,
      postOmissionCount: 0,
      uncoveredSpanCount: 0,
      finalUncoveredSpanSample: [],
      retries: [],
    },
    'accepted quote repair updates the durable final omission audit',
  );
}
assert.deepEqual(
  patchResponsibilityQuoteRepairs({
    original: mismatchOutput,
    diagnostics: bad.diagnostics,
    repaired: {
      ...output,
      responsibilities: [{ ...output.responsibilities[0]!, action: 'invent' }],
    },
  }),
  { ok: false, reason: 'non_quote_field_change' },
);
const duplicateRetryMerge = mergeResponsibilityRetryValidation(result, result);
assert.equal(duplicateRetryMerge.acceptedCount, 0);
assert.equal(duplicateRetryMerge.validation.elements.length, result.elements.length);
assert.equal(duplicateRetryMerge.validation.diagnostics.length, result.diagnostics.length);
assert.ok(responsibilityRawAuditArtifact(output).sha256.length === 64);

const cross = validateResponsibilityRead({
  output: {
    summary: 'Cross-segment citation fixture.',
    responsibilities: [
      {
        ...output.responsibilities[0]!,
        responsibilityId: 'cross_segment',
        chunkId: otherChunkId,
      },
    ],
  },
  documentId,
  segment,
  allCoveredChunkIds: new Set([chunkId, otherChunkId]),
  chunks: [
    {
      id: otherChunkId,
      documentId,
      rawText: output.responsibilities[0]!.evidenceQuote,
    },
  ],
});
assert.equal(cross.elements.length, 1);
assert.deepEqual(cross.crossSegmentCitations, [
  { responsibilityId: 'cross_segment', chunkId: otherChunkId },
]);

const uncovered = validateResponsibilityRead({
  output: {
    ...output,
    responsibilities: [{ ...output.responsibilities[0]!, chunkId: otherChunkId }],
  },
  documentId,
  segment,
  allCoveredChunkIds: new Set([chunkId]),
  chunks: [
    { id: otherChunkId, documentId, rawText: output.responsibilities[0]!.evidenceQuote },
  ],
});
assert.equal(uncovered.diagnostics[0]?.crossSegmentStatus, 'uncovered');

const mapId = '33333333-3333-4333-8333-333333333333';
const coverage = responsibilityCoverage({
  mapId,
  elements: result.elements,
  claimMapRefs: new Set([`${mapId}:element:designer_preflight`]),
});
assert.equal(coverage.ratio, 1);
assert.equal(responsibilityEvidenceCoverage(10, 9), 0.9);
assert.throws(() => responsibilityEvidenceCoverage(10, 8.9), /Invalid responsibility coverage/);
assert.equal(
  shouldDispatchResponsibilityShadowMerge({ mergeEnabled: true, primary: 10, coverage: 0.9 }),
  true,
);
assert.throws(
  () =>
    assertResponsibilityVersionTarget({
      verdict: 'refine_object',
      objectId: '55555555-5555-4555-8555-555555555555',
      baseObjectVersionId: null,
    }),
  /current base version/,
);
assert.doesNotThrow(() =>
  assertResponsibilityVersionTarget({
    verdict: 'refine_object',
    objectId: '55555555-5555-4555-8555-555555555555',
    baseObjectVersionId: '66666666-6666-4666-8666-666666666666',
  }),
);
assert.equal(answerKey.version, 'licensed-team-responsibilities-v1');
assert.equal(answerKey.records.length, 30);
assert.equal(RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION, 'field-aware-v3');
assert.equal(RESPONSIBILITY_READ_PROMPT_VERSION, 'responsibility-read-v2.4-span-bound');
for (const requiredPromptRule of [
  'exact source-owner role label',
  'exactly one duty per record',
  'Never merge adjacent verbs',
  'multi-verb or "and then" sentence',
  'one thin record per destination or system',
  'short verb phrase',
  'target, system, portal, server, form, cadence, and timing qualifier',
  'trigger may repeat timing or cadence, but it must never be their only location',
  'Do not leave a real target only in requiredSystem',
  'Prefer multiple thin',
  'handling chain becomes one record per step',
  'Do not invent duties',
  'nearest explicit owner label',
  'Preserve duty direction and polarity exactly',
  'shortest verbatim quote',
]) {
  assert.ok(
    RESPONSIBILITY_READ_SYSTEM_PROMPT.includes(requiredPromptRule),
    `responsibility prompt is missing hard rule: ${requiredPromptRule}`,
  );
}
// Normalized for the CRLF reason documented at the F0 frozen-limits block below:
// a fresh Windows clone checks this file out with CRLF and the multi-line frozen
// budget literals would silently stop matching.
const workflowReadSource = readFileSync(
  new URL('../lib/source-workflow-read.ts', import.meta.url),
  'utf8',
).replace(/\r\n/g, '\n');
const responsibilityReaderSource = readFileSync(
  new URL('../lib/responsibility-reader.ts', import.meta.url),
  'utf8',
);
const documentIngestionSource = readFileSync(
  new URL('../trigger/document-ingestion.ts', import.meta.url),
  'utf8',
);
const responsibilityPromptSource = readFileSync(
  new URL('../../../../packages/ai/src/prompts/workflow-read.ts', import.meta.url),
  'utf8',
);
for (const frozenBudgetLiteral of [
  "readNumberSetting(db, 'source_reader_max_read_calls_per_source', 40)",
  "readNumberSetting(db, 'source_reader_max_input_tokens_per_source', 500_000)",
  "readNumberSetting(db, 'source_reader_max_estimated_cost_usd_per_source', 10)",
  "'responsibility_postpass_max_quote_repairs_per_source',\n      1",
  "'responsibility_postpass_max_omission_retries_per_source',\n      5",
  "'responsibility_postpass_max_omission_retries_per_chunk',\n      1",
]) {
  assert.ok(
    workflowReadSource.includes(frozenBudgetLiteral),
    `frozen Batch E budget changed: ${frozenBudgetLiteral}`,
  );
}
assert.ok(documentIngestionSource.includes('requiredCoverage: 0.9'));
assert.ok(documentIngestionSource.includes("'business_model_merge_enabled'"));
for (const forbiddenRuntimeLeak of [
  '__fixtures__',
  'responsibility-answer-key',
  'licensed-team-responsibilities',
  'Licensed Team',
  'Lic Manager',
  'Lic Coordinator',
]) {
  assert.ok(
    !workflowReadSource.includes(forbiddenRuntimeLeak) &&
      !responsibilityReaderSource.includes(forbiddenRuntimeLeak) &&
      !responsibilityPromptSource.includes(forbiddenRuntimeLeak),
    `runtime responsibility reader leaked fixture-specific knowledge: ${forbiddenRuntimeLeak}`,
  );
}
for (const requiredRequestRule of [
  'exact source-owner role label',
  'Split adjacent verbs and duties',
  'Split distinct destinations or systems',
  'target, system, destination, portal, server, form, deadline, cadence, and timing qualifier in object',
  'trigger may repeat but never replace them',
  'Do not leave a real target only in requiredSystem',
  'Do not invent duties not present in the source',
  'Prefer multiple thin records',
  'nearest explicit owner',
  'Preserve action direction and polarity exactly',
  'shortest verbatim one-duty quote',
]) {
  assert.ok(
    workflowReadSource.includes(requiredRequestRule),
    `responsibility request block is missing rule: ${requiredRequestRule}`,
  );
}
assert.equal(
  answerKey.sourceSha256,
  '398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be',
);
assert.equal(
  responsibilityReadTaskType(true),
  'source-responsibility-combined-repair',
  'combined model calls have distinct durable task identity',
);
assert.equal(responsibilityReadTaskType(false), 'source-responsibility-read');
assert.equal(
  responsibilityReadPromptVersion(true),
  'responsibility-repair-v3-combined',
);
assert.equal(
  responsibilityReadPromptVersion(false),
  'responsibility-read-v2.4-span-bound',
);
assert.equal(
  RESPONSIBILITY_COMBINED_REPAIR_PROMPT_VERSION,
  'responsibility-repair-v3-combined',
);
for (const persistedPromptVersion of [
  RESPONSIBILITY_READ_PROMPT_VERSION,
  RESPONSIBILITY_QUOTE_REPAIR_PROMPT_VERSION,
]) {
  assert.ok(
    persistedPromptVersion.length <= 50,
    `persisted prompt version exceeds varchar(50): ${persistedPromptVersion}`,
  );
}
const quoteOnlyRequest = buildResponsibilityRequestContent({
  quoteRepairRecords: [output.responsibilities[0]!],
  quoteRepairCandidates: [{
    responsibilityId: output.responsibilities[0]!.responsibilityId,
    failedQuote: 'Designer check art files.',
    immutableFields: {
      responsibilityId: output.responsibilities[0]!.responsibilityId,
      label: output.responsibilities[0]!.label,
      role: output.responsibilities[0]!.role,
      action: output.responsibilities[0]!.action,
      object: output.responsibilities[0]!.object,
      trigger: output.responsibilities[0]!.trigger,
      requiredSystem: output.responsibilities[0]!.requiredSystem,
      ownerName: output.responsibilities[0]!.ownerName,
      department: output.responsibilities[0]!.department,
      chunkId: output.responsibilities[0]!.chunkId,
    },
    candidates: [{
      candidateIndex: 0,
      sourceText: output.responsibilities[0]!.evidenceQuote,
      sourceTextSha256: responsibilitySpanSha256(output.responsibilities[0]!.evidenceQuote),
      tokenOverlap: 3,
    }],
  }],
});
assert.match(quoteOnlyRequest, /Combined responsibility field and quote repair/);
assert.match(quoteOnlyRequest, /Designer check art files/);
assert.match(quoteOnlyRequest, /checks art files for completeness/);
for (const extractionRule of [
  'Split adjacent verbs',
  'Preserve action direction',
  'nearest explicit owner',
  'distinct destinations',
]) {
  assert.ok(
    !quoteOnlyRequest.includes(extractionRule),
    `quote-only request leaked extraction rule: ${extractionRule}`,
  );
}
assert.match(
  buildResponsibilityRequestContent({
    focusedSpans: bindForcedResponsibilitySpans([{
      chunkId,
      spanIndex: 0,
      sourceSpan: 'Finance approves invoices.',
      evidenceQuote: 'Finance approves invoices.',
      sourceStart: 0,
      sourceEnd: 'Finance approves invoices.'.length,
      rankIndex: 0,
      rankFeatures: {
        verbStartsSpan: false,
        explicitOwner: true,
        listStructured: false,
        concreteTokenCount: 3,
        sourceLength: 26,
        chunkOmissionCount: 1,
        sourceChunkIndex: 0,
      },
      sourceSpanSha256: responsibilitySpanSha256('Finance approves invoices.'),
    }]),
  }),
  /Focused omission retry/,
);
assert.equal(
  scoreResponsibilityAnswerKey({
    expected: answerKey.records,
    actual: answerKey.records.slice(0, 27),
  }).recall,
  0.9,
);
const specializedMatch = scoreResponsibilityAnswerKey({
  expected: [{ role: 'Licensed Team', action: 'prioritize', object: 'rush submissions' }],
  actual: [
    {
      role: 'Licensed Team',
      action: 'prioritize and email',
      object: 'rush approval submissions',
    },
  ],
});
assert.equal(specializedMatch.recall, 1);
assert.equal(specializedMatch.evidence[0]?.method, 'field_aware');
for (const adversarial of [
  {
    name: 'role swap',
    actual: { role: 'Lic Manager', action: 'prioritize', object: 'rush submissions' },
  },
  {
    name: 'object substitution',
    actual: { role: 'Licensed Team', action: 'prioritize', object: 'royalty reports' },
  },
  {
    name: 'unrelated overlap',
    actual: { role: 'Licensed Team', action: 'prioritize', object: 'rush' },
  },
  {
    name: 'negation flip',
    actual: { role: 'Licensed Team', action: 'do not prioritize', object: 'rush submissions' },
  },
]) {
  assert.equal(
    scoreResponsibilityAnswerKey({
      expected: [{ role: 'Licensed Team', action: 'prioritize', object: 'rush submissions' }],
      actual: [adversarial.actual],
    }).recall,
    0,
    adversarial.name,
  );
}
const oneActualCannotCreditTwo = scoreResponsibilityAnswerKey({
  expected: [
    { role: 'Licensed Team', action: 'prioritize', object: 'rush submissions' },
    { role: 'Licensed Team', action: 'email', object: 'rush submissions' },
  ],
  actual: [
    {
      role: 'Licensed Team',
      action: 'prioritize and email',
      object: 'rush approval submissions',
    },
  ],
});
assert.equal(oneActualCannotCreditTwo.matched, 1);
const multiSystemBa = {
  role: 'Licensed Team',
  action: 'save',
  object: 'BA number to MasterData DesignFlow and ColdLion',
};
assert.equal(
  scoreResponsibilityAnswerKey({
    expected: [
      { role: 'Licensed Team', action: 'save', object: 'BA number to MasterData' },
      { role: 'Licensed Team', action: 'save', object: 'BA number to DesignFlow' },
      { role: 'Licensed Team', action: 'save', object: 'BA number to ColdLion' },
    ],
    actual: [multiSystemBa],
  }).matched,
  1,
);
assert.equal(
  scoreResponsibilityAnswerKey({
    expected: [
      {
        role: 'Licensed Team',
        action: 'maintain',
        object: '4 Seasons approval status sheet',
      },
    ],
    actual: [
      {
        role: 'Licensed Team',
        action: 'maintain',
        object: 'Status Approvals on a Google Sheet for 4 Seasons',
      },
    ],
  }).recall,
  1,
  'explicit approvals/approval normalization',
);
assert.equal(
  scoreResponsibilityAnswerKey({
    expected: [{ role: 'Licensed Team', action: 'save', object: 'BA number to MasterData' }],
    actual: [{ role: 'Licensed Team', action: 'save', object: 'BA number to Master Data' }],
  }).recall,
  1,
);
assert.equal(
  scoreResponsibilityAnswerKey({
    expected: [{ role: 'Licensed Team', action: 'save', object: 'BA number to MasterData' }],
    actual: [{ role: 'Licensing Team', action: 'save', object: 'BA number to MasterData' }],
  }).recall,
  0,
  'unpinned role aliases must not match',
);
for (const negation of ['not', "don't", 'dont', 'cannot', "can't", 'cant']) {
  assert.equal(
    scoreResponsibilityAnswerKey({
      expected: [{ role: 'Licensed Team', action: 'submit', object: 'product safety tests' }],
      actual: [
        {
          role: 'Licensed Team',
          action: `${negation} submit`,
          object: 'product safety tests',
        },
      ],
    }).recall,
    0,
    `negation ${negation}`,
  );
}
const stableCandidates = [
  { role: 'Licensed Team', action: 'submit', object: 'quarterly royalty reports' },
  { role: 'Licensed Team', action: 'submit and archive', object: 'quarterly royalty reports' },
];
const stabilityExpected = [
  { role: 'Licensed Team', action: 'submit', object: 'quarterly royalty reports' },
];
assert.deepEqual(
  scoreResponsibilityAnswerKey({ expected: stabilityExpected, actual: stableCandidates }).evidence,
  scoreResponsibilityAnswerKey({ expected: stabilityExpected, actual: [...stableCandidates].reverse() })
    .evidence,
);
for (const falseEquivalent of ['insure', 'maintain contact', 'complete removal', 'reach around']) {
  assert.equal(
    scoreResponsibilityAnswerKey({
      expected: [{ role: 'Lic Manager', action: 'request', object: 'factory audits' }],
      actual: [{ role: 'Lic Manager', action: falseEquivalent, object: 'factory audits' }],
    }).recall,
    0,
    `false action equivalent ${falseEquivalent}`,
  );
}
const mergeSource = readFileSync(
  new URL('../lib/business-model-merge.ts', import.meta.url),
  'utf8',
);
for (const required of [
  "resolveRouteCandidates(args.db, 'model_merge')",
  'ResponsibilityMergeOutputSchema',
  '.insert(oracleContextPacks)',
  '.insert(modelRuns)',
  '.insert(modelRunUsageDetails)',
  'logModelRunAttempts',
  'logAllCandidatesFailedAttempts',
  'pg_advisory_xact_lock',
]) {
  assert.ok(mergeSource.includes(required), `real merge/provenance contract missing: ${required}`);
}
const taskSource = readFileSync(
  new URL('../trigger/business-model-merge.ts', import.meta.url),
  'utf8',
);
assert.ok(!taskSource.includes('verdict:'), 'production task must not accept a caller verdict');

const attemptedRoutes: string[] = [];
const provenanceEvents: string[] = [];
const mockedModel = await invokeResponsibilityMergeModel({
  plan: { routeId: 'primary-route' } as never,
  routeCandidates: [
    { route: { routeId: 'primary-route' } },
    { route: { routeId: 'fallback-route' } },
  ] as never,
  runner: async ({ routeCandidates }) => {
    attemptedRoutes.push(...routeCandidates.map((candidate) => candidate.route.routeId));
    return {
      output: {
        verdict: 'create_object',
        proposedName: 'Fixture responsibilities',
        proposedSlug: 'fixture-responsibilities',
        summary: 'Fixture.',
        operations: [],
        omittedSourceElementRefs: [],
      },
      routeId: 'fallback-route',
      provider: 'openai',
      modelId: 'fixture-model',
      usage: { inputTokens: 10, outputTokens: 5 },
    };
  },
  onSuccess: async (result) => {
    provenanceEvents.push(
      `context-pack:model-run:usage:${result.routeId}:${result.usage.inputTokens}`,
    );
  },
  onFailure: async () => {
    provenanceEvents.push('failed-attempt');
  },
});
assert.deepEqual(attemptedRoutes, ['primary-route', 'fallback-route']);
assert.equal(mockedModel.routeId, 'fallback-route');
assert.deepEqual(provenanceEvents, ['context-pack:model-run:usage:fallback-route:10']);
assert.equal(
  shouldDispatchResponsibilityShadowMerge({ mergeEnabled: false, primary: 10, coverage: 1 }),
  false,
);
const lockArgs = {
  sourceMapId: mapId,
};

const genericChunkId = '77777777-7777-4777-8777-777777777777';
const genericDocumentId = '88888888-8888-4888-8888-888888888888';
const genericSegment: SourceStructureSegment = {
  segmentId: 'generic_finance',
  shape: 'responsibilities',
  title: 'Generic finance',
  chunkIds: [genericChunkId],
};
const genericSource = 'The Finance Team submits quarterly compliance reports.';
const thinned = validateResponsibilityRead({
  output: {
    summary: 'Generic responsibility validation.',
    responsibilities: [{
      responsibilityId: 'generic_quarterly_report',
      label: 'Submit reports',
      role: 'Finance Team',
      action: 'submits',
      object: 'reports',
      evidenceQuote: genericSource,
      chunkId: genericChunkId,
    }],
  },
  documentId: genericDocumentId,
  segment: genericSegment,
  chunks: [{ id: genericChunkId, documentId: genericDocumentId, rawText: genericSource }],
});
assert.equal(thinned.inventoryElements.length, 1);
assert.equal(thinned.elements.length, 0);
assert.equal(thinned.incompleteInventoryAudit[0]?.failureCategory, 'field');
assert.deepEqual(responsibilityMergeEligibleElements(thinned), []);

const complete = validateResponsibilityRead({
  output: {
    summary: 'Generic responsibility validation.',
    responsibilities: [{
      responsibilityId: 'generic_quarterly_report_complete',
      label: 'Submit quarterly compliance reports',
      role: 'Finance Team',
      action: 'submits',
      object: 'quarterly compliance reports',
      evidenceQuote: genericSource,
      chunkId: genericChunkId,
    }],
  },
  documentId: genericDocumentId,
  segment: genericSegment,
  chunks: [{ id: genericChunkId, documentId: genericDocumentId, rawText: genericSource }],
});
assert.equal(complete.inventoryElements.length, 1);
assert.equal(complete.elements.length, 1);
assert.equal(responsibilityMergeEligibleElements(complete).length, 1);

const destinationRecord: ResponsibilityReadOutput['responsibilities'][number] = {
  responsibilityId: 'generic_save_approval',
  label: 'Save approval number',
  role: 'Records Team',
  action: 'saves',
  object: 'approval number to LedgerOne, FlowBoard, and ArchiveBox',
  evidenceQuote:
    'The Records Team saves the approval number to LedgerOne, FlowBoard, and ArchiveBox.',
  chunkId: genericChunkId,
};
const expansionA = expandResponsibilityDestinations({
  sourceSpan: destinationRecord.evidenceQuote,
  record: destinationRecord,
});
const expansionB = expandResponsibilityDestinations({
  sourceSpan: destinationRecord.evidenceQuote,
  record: destinationRecord,
});
assert.equal(expansionA.records.length, 3);
assert.deepEqual(
  expansionA.records.map((item) => item.responsibilityId),
  expansionB.records.map((item) => item.responsibilityId),
);
assert.equal(
  expandResponsibilityDestinations({
    sourceSpan: 'The Records Team reviews names, addresses, and dates.',
    record: { ...destinationRecord, object: 'names, addresses, and dates' },
  }).records.length,
  0,
);
for (const ordinaryList of [
  {
    sourceSpan: 'The Review Team reviews changes in names, addresses, and dates.',
    action: 'reviews',
    object: 'changes in names, addresses, and dates',
  },
  {
    sourceSpan: 'The Scheduling Team records coverage on Monday, Tuesday, and Wednesday.',
    action: 'records',
    object: 'coverage on Monday, Tuesday, and Wednesday',
  },
  {
    sourceSpan: 'The Partner Team provides notices to Alice, Bob, and Carol.',
    action: 'provides',
    object: 'notices to Alice, Bob, and Carol',
  },
]) {
  assert.equal(
    expandResponsibilityDestinations({
      sourceSpan: ordinaryList.sourceSpan,
      record: {
        ...destinationRecord,
        action: ordinaryList.action,
        object: ordinaryList.object,
        evidenceQuote: ordinaryList.sourceSpan,
      },
    }).records.length,
    0,
    `ordinary coordinated list was expanded: ${ordinaryList.sourceSpan}`,
  );
}

const combinedPatch = patchCombinedResponsibilityRepairs({
  original: {
    summary: 'Generic repair validation.',
    responsibilities: [{
      responsibilityId: 'generic_repair',
      label: 'Submit reports',
      role: 'Finance Team',
      action: 'submits',
      object: 'reports',
      evidenceQuote: genericSource,
      chunkId: genericChunkId,
    }],
  },
  fieldRequests: [{
    responsibilityId: 'generic_repair',
    chunkId: genericChunkId,
    evidenceQuote: genericSource,
    sourceSpan: genericSource,
    allowedFields: ['object'],
  }],
  quoteRequests: [],
  repaired: {
    fieldRepairs: [{
      responsibilityId: 'generic_repair',
      object: 'quarterly compliance reports',
    }],
    quoteRepairs: [],
  },
});
assert.equal(combinedPatch.ok, true);
assert.equal(
  combinedPatch.ok ? combinedPatch.output.responsibilities[0]?.object : null,
  'quarterly compliance reports',
);

const enclosingSource =
  'The Finance Team submits quarterly compliance reports through the compliance portal.';
const shortQuoteOutput: ResponsibilityReadOutput = {
  summary: 'Short exact quote with a larger enclosing duty.',
  responsibilities: [{
    responsibilityId: 'short_quote_field_repair',
    label: 'Submit reports',
    role: 'Finance Team',
    action: 'submits',
    object: 'reports',
    evidenceQuote: 'submits quarterly compliance reports',
    chunkId: genericChunkId,
  }],
};
const shortQuoteValidation = validateResponsibilityRead({
  output: shortQuoteOutput,
  documentId: genericDocumentId,
  segment: genericSegment,
  chunks: [{ id: genericChunkId, documentId: genericDocumentId, rawText: enclosingSource }],
});
assert.equal(shortQuoteValidation.inventoryElements.length, 1);
assert.equal(shortQuoteValidation.elements.length, 0);
assert.equal(
  shortQuoteValidation.incompleteInventoryAudit[0]?.selectedSourceSpan,
  enclosingSource,
);
const shortQuotePlan = buildResponsibilityCombinedRepairPlan({
  reads: [{
    segment: genericSegment,
    model: { output: shortQuoteOutput },
    validation: shortQuoteValidation,
  }],
  chunks: [{ id: genericChunkId, rawText: enclosingSource }],
});
assert.equal(shortQuotePlan.fieldRepairRequests[0]?.sourceSpan, enclosingSource);
const shortQuotePatch = patchCombinedResponsibilityRepairs({
  original: shortQuoteOutput,
  fieldRequests: shortQuotePlan.fieldRepairRequests,
  quoteRequests: [],
  repaired: {
    fieldRepairs: [{
      responsibilityId: 'short_quote_field_repair',
      object: 'quarterly compliance reports through the compliance portal',
    }],
    quoteRepairs: [],
  },
});
assert.equal(shortQuotePatch.ok, true);
assert.equal(
  shortQuotePatch.ok ? shortQuotePatch.output.responsibilities[0]?.evidenceQuote : null,
  'submits quarterly compliance reports',
);
assert.deepEqual(
  patchCombinedResponsibilityRepairs({
    original: shortQuoteOutput,
    fieldRequests: shortQuotePlan.fieldRepairRequests,
    quoteRequests: [],
    repaired: { fieldRepairs: [], quoteRepairs: [] },
  }),
  { ok: false, reason: 'missing_field_repair' },
);
assert.ok(
  workflowReadSource.includes(": 'repair_failed'"),
  'combined repair failures must persist as repair_failed without partial apply',
);

const repairableRecords: ResponsibilityReadOutput['responsibilities'] = Array.from(
  { length: 7 },
  (_, index) => ({
    responsibilityId: `repairable_base_${index}`,
    label: `Submit report ${index}`,
    role: 'Finance Team',
    action: 'submits',
    object: 'reports',
    evidenceQuote: genericSource,
    chunkId: genericChunkId,
  }),
);
const baseIncompleteAudit = thinned.incompleteInventoryAudit[0]!;
const mixedSlotValidation = {
  ...thinned,
  incompleteInventoryAudit: [
    {
      ...baseIncompleteAudit,
      elementId: 'derived_expansion_a',
      repairStatus: 'rejected' as const,
    },
    {
      ...baseIncompleteAudit,
      elementId: 'derived_expansion_b',
      repairStatus: 'rejected' as const,
    },
    ...repairableRecords.map((record) => ({
      ...baseIncompleteAudit,
      elementId: record.responsibilityId,
      repairStatus: 'not_selected' as const,
    })),
  ],
};
const mixedSlotPlan = buildResponsibilityCombinedRepairPlan({
  reads: [{
    segment: genericSegment,
    model: {
      output: {
        summary: 'Mixed expanded and base repair candidates.',
        responsibilities: repairableRecords,
      },
    },
    validation: mixedSlotValidation,
  }],
  chunks: [{ id: genericChunkId, rawText: genericSource }],
});
assert.equal(mixedSlotPlan.fieldRepairRequests.length, 6);
assert.deepEqual(
  mixedSlotPlan.fieldRepairRequests.map((item) => item.responsibilityId),
  repairableRecords.slice(0, 6).map((item) => item.responsibilityId),
);
assert.deepEqual(
  patchCombinedResponsibilityRepairs({
    original: { summary: 'Generic empty repair.', responsibilities: [] },
    fieldRequests: [],
    quoteRequests: [],
    repaired: { fieldRepairs: [], quoteRepairs: [] },
  }),
  { ok: false, reason: 'empty_repair' },
);
const absentQuote = validateResponsibilityRead({
  output: {
    summary: 'Generic missing quote validation.',
    responsibilities: [{
      responsibilityId: 'generic_absent_quote',
      label: 'Submit reports',
      role: 'Finance Team',
      action: 'submits',
      object: 'quarterly compliance reports',
      evidenceQuote: 'This quote is absent from the source.',
      chunkId: genericChunkId,
    }],
  },
  documentId: genericDocumentId,
  segment: genericSegment,
  chunks: [{ id: genericChunkId, documentId: genericDocumentId, rawText: genericSource }],
});
assert.equal(absentQuote.inventoryElements.length, 0);
assert.equal(absentQuote.diagnostics[0]?.failureClass, 'quote_mismatch');
assert.throws(
  () => expandResponsibilityDestinations({
    sourceSpan: 'The Records Team saves the number to Flow Board, Flow-Board, and Archive Box.',
    record: {
      ...destinationRecord,
      object: 'approval number to Flow Board, Flow-Board, and Archive Box',
    },
  }),
  /Duplicate normalized destination/,
);
const inventedRepair = patchCombinedResponsibilityRepairs({
  original: {
    summary: 'Generic repair validation.',
    responsibilities: [{
      responsibilityId: 'generic_repair',
      label: 'Submit reports',
      role: 'Finance Team',
      action: 'submits',
      object: 'reports',
      evidenceQuote: genericSource,
      chunkId: genericChunkId,
    }],
  },
  fieldRequests: [{
    responsibilityId: 'generic_repair',
    chunkId: genericChunkId,
    evidenceQuote: genericSource,
    sourceSpan: genericSource,
    allowedFields: ['object'],
  }],
  quoteRequests: [],
  repaired: {
    fieldRepairs: [{ responsibilityId: 'generic_repair', object: 'monthly secret reports' }],
    quoteRepairs: [],
  },
});
assert.deepEqual(inventedRepair, { ok: false, reason: 'invented_field_content' });
assert.deepEqual(
  patchCombinedResponsibilityRepairs({
    original: {
      summary: 'Generic quote repair.',
      responsibilities: [{
        responsibilityId: 'generic_quote_repair',
        label: 'Submit reports',
        role: 'Finance Team',
        action: 'submits',
        object: 'quarterly compliance reports',
        evidenceQuote: 'bad quote',
        chunkId: genericChunkId,
      }],
    },
    fieldRequests: [],
    quoteRequests: [{
      responsibilityId: 'generic_quote_repair',
      candidates: [{ candidateId: 'candidate_0', sourceText: genericSource }],
    }],
    repaired: {
      fieldRepairs: [],
      quoteRepairs: [{ responsibilityId: 'generic_quote_repair', candidateId: 'candidate_9' }],
    },
  }),
  { ok: false, reason: 'quote_not_offered' },
);
const inverseReaderBudget = new SourceReaderBudget({
  maxReadCalls: 40,
  maxInputTokens: 500_000,
  maxEstimatedCostUsd: 10,
  estimatedInputCostPerMillionTokensUsd: 5,
  maxRepairAttempts: 1,
  maxConcurrency: 4,
});
const inversePostPassBudget = new ResponsibilityPostPassBudget({
  maxQuoteRepairsPerSource: 1,
  maxOmissionRetriesPerSource: 5,
  maxOmissionRetriesPerChunk: 1,
});
inversePostPassBudget.reserveQuoteRepair();
assert.equal(inversePostPassBudget.snapshot().quoteRepairs, 1);
assert.equal(inverseReaderBudget.snapshot().repairAttempts, 0);
assert.ok(workflowReadSource.includes(
  'read.validation.inventoryElements.length > read.validation.elements.length',
));
assert.ok(workflowReadSource.includes(
  'elements: responsibilityReads.flatMap((read) => read.validation.elements)',
));
assert.ok(workflowReadSource.includes(
  'incompleteInventoryAudit: read.validation.incompleteInventoryAudit',
));
assert.ok(
  workflowReadSource.includes('responsibilityMergeEligibleElements(read.validation)'),
  'production structure-map assembly must use the fail-loud merge eligibility helper',
);
const productionCompletionIndex = workflowReadSource.indexOf(
  'executeResponsibilityCompletionBatches({',
);
const productionDetectionRetryIndex = workflowReadSource.indexOf(
  'const omissionRetryScheduler = new ResponsibilityOmissionRetryScheduler()',
);
const productionQuoteRepairIndex = workflowReadSource.indexOf(
  'const combinedRepairPlan = (args.orchestrationDependencies?.buildCombinedRepairPlan ?? buildResponsibilityCombinedRepairPlan)({',
);
const productionAssemblyIndex = workflowReadSource.indexOf(
  'const mergeReadyInventory = responsibilityReads',
);
assert.ok(
  productionCompletionIndex > 0 &&
    productionCompletionIndex < productionDetectionRetryIndex &&
    productionDetectionRetryIndex < productionQuoteRepairIndex &&
    productionQuoteRepairIndex < productionAssemblyIndex,
  'production orchestration must run exhaustive completion, detection-only retries, quote repair, and merge-ready assembly in order',
);
assert.ok(
  workflowReadSource.includes("omission.omissionClass === 'inventory_detection_gap'"),
  'legacy retry slots must be reserved for inventory detection gaps',
);
assert.ok(
  workflowReadSource.includes('maxFieldRepairs: 0'),
  'candidate-bound quote repair must not repeat residual field completion',
);
assert.ok(
  workflowReadSource.includes('responsibilityCompletion: responsibilityCompletionAudit'),
  'production validationJson must persist completion manifests, outcomes, and execution facts',
);
assert.ok(
  workflowReadSource.includes('const lateResidualSeeds = lateResidualResponsibilitySeeds({') &&
    workflowReadSource.includes('responsibilityCompletionAudit.outcomes.push('),
  'late detection-retry seeds must receive durable completion outcomes',
);
// F7. Lock the production wiring, not just the helper: the late pass must be fed from
// ACCEPTED completion outcomes. `residualSeedIds` there is the defect that cost rows 19
// and 23, so its return is a regression, not a refactor.
assert.ok(
  workflowReadSource.includes("responsibilityCompletionAudit.outcomes") &&
    workflowReadSource.includes(".filter((outcome) => outcome.status === 'accepted')"),
  'late completion handled-ids must be built from accepted outcomes',
);
assert.ok(
  !workflowReadSource.includes(
    'const completionHandledIds = new Set(responsibilityCompletionAudit.residualSeedIds)',
  ),
  'scheduled seed ids must never again be treated as handled completions',
);
// G6. Lock the production wiring for rejection feedback: the late pass must be handed the
// reasons from every non-accepted exhaustive outcome, or it is just an identical retry.
assert.ok(
  workflowReadSource.includes('priorRejectionsBySeedId: latePriorRejections'),
  'the late completion pass must receive prior rejection reasons',
);
assert.ok(
  workflowReadSource.includes("if (outcome.status === 'accepted') continue;"),
  'rejection feedback must be built from non-accepted outcomes',
);
assert.equal(
  RESPONSIBILITY_COMPLETION_PROMPT_VERSION,
  'responsibility-completion-v2',
  'the completion prompt version must move when the completion prompt changes',
);
assert.ok(
  RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT.includes('priorRejectionReasons') &&
    RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT.includes('never a proposed answer'),
  'the prompt must explain the reason codes without turning them into an answer',
);
assert.ok(
  workflowReadSource.includes('auditOnlyParents: [...responsibilityInventoryAuditParents.reduce('),
  'discovered split parents must remain in durable audit',
);
assert.throws(
  () => responsibilityMergeEligibleElements({
    ...complete,
    inventoryElements: [],
  }),
  /absent from inventory/,
);

// Production-used orchestration seam: the plan builder, patcher, validator,
// expansion, omission, retry merge, eligibility, and durable audit are the same
// helpers used by generateSourceWorkflowMap.
const seamChunkA = '99999999-9999-4999-8999-999999999991';
const seamChunkB = '99999999-9999-4999-8999-999999999992';
const seamSourceA =
  'The Finance Team submits quarterly compliance reports to LedgerOne and ArchiveBox.';
const seamSourceB = 'The Operations Team submits signed approval forms.';
const seamSegmentA: SourceStructureSegment = {
  segmentId: 'seam_a',
  shape: 'responsibilities',
  title: 'Seam A',
  chunkIds: [seamChunkA],
};
const seamSegmentB: SourceStructureSegment = {
  segmentId: 'seam_b',
  shape: 'responsibilities',
  title: 'Seam B',
  chunkIds: [seamChunkB],
};
const seamOutputA: ResponsibilityReadOutput = {
  summary: 'Cross-shard seam responsibility A.',
  responsibilities: [{
    responsibilityId: 'seam_submit_reports',
    label: 'Submit reports',
    role: 'Finance Team',
    action: 'submits',
    object: 'reports',
    evidenceQuote: seamSourceA,
    chunkId: seamChunkA,
  }],
};
const seamOutputB: ResponsibilityReadOutput = {
  summary: 'Cross-shard seam responsibility B.',
  responsibilities: [{
    responsibilityId: 'seam_archive_forms',
    label: 'Submit forms',
    role: 'Operations Team',
    action: 'submits',
    object: 'signed approval forms',
    evidenceQuote: 'Operations submit forms.',
    chunkId: seamChunkB,
  }],
};
const seamChunks = [
  { id: seamChunkA, documentId: genericDocumentId, rawText: seamSourceA },
  { id: seamChunkB, documentId: genericDocumentId, rawText: seamSourceB },
];
const seamBaseA = validateResponsibilityRead({
  output: seamOutputA,
  documentId: genericDocumentId,
  segment: seamSegmentA,
  chunks: seamChunks,
  allCoveredChunkIds: new Set([seamChunkA, seamChunkB]),
});
const seamBaseB = validateResponsibilityRead({
  output: seamOutputB,
  documentId: genericDocumentId,
  segment: seamSegmentB,
  chunks: seamChunks,
  allCoveredChunkIds: new Set([seamChunkA, seamChunkB]),
});
const seamInitialOmissions = findResponsibilityOmissions({
  chunks: seamChunks,
  elements: [...seamBaseA.elements, ...seamBaseB.elements],
});
assert.ok(seamInitialOmissions.length >= 2);
const seamRetryOutput: ResponsibilityReadOutput = {
  summary: 'Cross-shard seam retry.',
  responsibilities: [{
    responsibilityId: 'seam_archive_forms_retry',
    label: 'Submit signed approval forms',
    role: 'Operations Team',
    action: 'submits',
    object: 'signed approval forms',
    evidenceQuote: seamSourceB,
    chunkId: seamChunkB,
  }],
};
const seamRetryValidation = validateResponsibilityRead({
  output: seamRetryOutput,
  documentId: genericDocumentId,
  segment: seamSegmentB,
  chunks: seamChunks,
  allCoveredChunkIds: new Set([seamChunkA, seamChunkB]),
});
const seamMergedB = mergeResponsibilityRetryValidation(seamBaseB, seamRetryValidation).validation;
const seamReads = [
  { segment: seamSegmentA, model: { output: seamOutputA }, validation: seamBaseA },
  {
    segment: seamSegmentB,
    model: {
      output: {
        ...seamOutputB,
        responsibilities: [
          ...seamOutputB.responsibilities,
          ...seamRetryOutput.responsibilities,
        ],
      },
    },
    validation: seamMergedB,
  },
];
const seamPlan = buildResponsibilityCombinedRepairPlan({
  reads: seamReads,
  chunks: seamChunks,
});
assert.deepEqual(seamPlan.selectedSegmentIds, ['seam_a', 'seam_b']);
const seamPatched = patchCombinedResponsibilityRepairs({
  original: {
    summary: 'Cross-shard combined repair.',
    responsibilities: seamPlan.records,
  },
  fieldRequests: seamPlan.fieldRepairRequests,
  quoteRequests: seamPlan.quoteRepairCandidates.map((item) => ({
    responsibilityId: item.responsibilityId,
    candidates: item.candidates.map((candidate) => ({
      candidateId: `candidate_${candidate.candidateIndex}`,
      sourceText: candidate.sourceText,
    })),
  })),
  repaired: {
    fieldRepairs: [{
      responsibilityId: 'seam_submit_reports',
      object: 'quarterly compliance reports to LedgerOne and ArchiveBox',
    }],
    quoteRepairs: [{
      responsibilityId: 'seam_archive_forms',
      candidateId: `candidate_${seamPlan.quoteRepairCandidates[0]!.candidates[0]!.candidateIndex}`,
    }],
  },
});
assert.equal(seamPatched.ok, true);
const seamRepairOutput = seamPatched.ok
  ? seamPatched.output
  : { summary: 'unreachable seam repair', responsibilities: [] };
const seamFinalAOutput = mergeCombinedResponsibilityRepairOutput({
  original: seamOutputA,
  repaired: seamRepairOutput,
});
const seamFinalBOutput = mergeCombinedResponsibilityRepairOutput({
  original: seamReads[1]!.model.output,
  repaired: seamRepairOutput,
});
const seamFinalA = validateResponsibilityRead({
  output: seamFinalAOutput,
  documentId: genericDocumentId,
  segment: seamSegmentA,
  chunks: seamChunks,
  allCoveredChunkIds: new Set([seamChunkA, seamChunkB]),
});
const seamFinalB = validateResponsibilityRead({
  output: seamFinalBOutput,
  documentId: genericDocumentId,
  segment: seamSegmentB,
  chunks: seamChunks,
  allCoveredChunkIds: new Set([seamChunkA, seamChunkB]),
});
assert.ok(seamFinalA.expansionAudit.length >= 2);
assert.ok(
  responsibilityMergeEligibleElements(seamFinalA).length >= 2,
  JSON.stringify(seamFinalA),
);
assert.ok(
  responsibilityMergeEligibleElements(seamFinalB).length >= 1,
  JSON.stringify({ seamPlan, seamFinalB }),
);
const seamFinalOmissions = findResponsibilityOmissions({
  chunks: seamChunks,
  elements: [...seamFinalA.elements, ...seamFinalB.elements],
});
assert.ok(seamFinalOmissions.length < seamInitialOmissions.length);
const seamDurableAudit = buildResponsibilityPostPassAudit({
  initialOmissions: seamInitialOmissions,
  finalOmissions: seamFinalOmissions,
  retries: [{
    preOmissionCount: seamInitialOmissions.length,
    postOmissionCount: seamFinalOmissions.length,
  }],
  quoteRepair: { attempted: true, selectedSegmentIds: seamPlan.selectedSegmentIds },
  postPassBudget: inversePostPassBudget.snapshot(),
  syntheticBaseReadCount: 0,
});
assert.deepEqual(
  seamDurableAudit.responsibilityQuoteRepair,
  { attempted: true, selectedSegmentIds: ['seam_a', 'seam_b'] },
);

const fixtureDerivedProperTerms = new Set(
  answerKey.records.flatMap((record) =>
    `${record.role} ${record.object}`.match(/\b[A-Z][A-Za-z0-9]{5,}\b/g) ?? [],
  ),
);
for (const term of fixtureDerivedProperTerms) {
  assert.ok(
    !responsibilityReaderSource.includes(term) &&
      !workflowReadSource.includes(term) &&
      !responsibilityPromptSource.includes(term),
    `runtime responsibility reader leaked fixture-derived term: ${term}`,
  );
}
const inventoryBoundDestinationChunks = [{
  id: 'inventory_bound_destination_chunk',
  documentId,
  rawText: '- Service Desk sends notices via Hub North and Hub South.',
}];
const inventoryBoundDestinationSeed =
  buildResponsibilitySourceInventory(inventoryBoundDestinationChunks).seeds[0]!;
const inventoryBoundValidation = validateResponsibilityRead({
  output: {
    summary: 'Inventory-bound destination validation fixture.',
    responsibilities: [{
      responsibilityId: inventoryBoundDestinationSeed.inventorySeedId,
      label: 'Service Desk: send notices via Hub North and Hub South',
      role: 'Service Desk',
      action: 'send',
      object: 'notices via Hub North and Hub South',
      trigger: null,
      requiredSystem: null,
      ownerName: null,
      department: null,
      evidenceQuote: inventoryBoundDestinationSeed.evidenceQuote,
      chunkId: inventoryBoundDestinationSeed.chunkId,
    }],
  },
  documentId,
  segment: {
    segmentId: 'inventory_bound_destination_segment',
    title: 'Inventory bound destination segment',
    shape: 'responsibilities',
    chunkIds: [inventoryBoundDestinationSeed.chunkId],
  },
  chunks: inventoryBoundDestinationChunks,
  inventorySeeds: [inventoryBoundDestinationSeed],
});
assert.equal(
  inventoryBoundValidation.expansionAudit.length,
  0,
  'validation cannot mint destination child IDs outside the authoritative inventory',
);
const unknownInventoryIdentityValidation = validateResponsibilityRead({
  output: {
    summary: 'Unknown inventory identity fixture.',
    responsibilities: [{
      responsibilityId: 'invented_inventory_identity',
      label: 'Service Desk: send notices',
      role: 'Service Desk',
      action: 'send',
      object: 'notices',
      trigger: null,
      requiredSystem: null,
      ownerName: null,
      department: null,
      evidenceQuote: inventoryBoundDestinationSeed.evidenceQuote,
      chunkId: inventoryBoundDestinationSeed.chunkId,
    }],
  },
  documentId,
  segment: {
    segmentId: 'unknown_inventory_identity_segment',
    title: 'Unknown inventory identity segment',
    shape: 'responsibilities',
    chunkIds: [inventoryBoundDestinationSeed.chunkId],
  },
  chunks: inventoryBoundDestinationChunks,
  inventorySeeds: [inventoryBoundDestinationSeed],
});
assert.equal(unknownInventoryIdentityValidation.elements.length, 0);
assert.match(
  unknownInventoryIdentityValidation.diagnostics[0]?.detail ?? '',
  /no authoritative source inventory seed/,
);
assert.equal(
  responsibilityShadowLockKey(lockArgs),
  responsibilityShadowLockKey(lockArgs),
  'concurrent same-input dispatches must serialize on one advisory lock',
);

// Top-level production orchestration with injected DB/model dependencies. This executes the
// real generateSourceWorkflowMap path without network, production data, or durable writes.
const orchestrationDocumentId = '77777777-7777-4777-8777-777777777777';
const orchestrationChunkId = '88888888-8888-4888-8888-888888888888';
const orchestrationLateDuty = '[Service Desk] When closed, archives requests.';
const orchestrationText =
  `[Service Desk]\n- Reviews intake packets.\n- Sends access notices.\n- ${orchestrationLateDuty}`;
const orchestrationUpdates: Array<Record<string, unknown>> = [];
let orchestrationId = 0;
let orchestrationCompletionCalls = 0;
let orchestrationResponsibilityCalls = 0;
let orchestrationCombinedRepairCalls = 0;
let orchestrationOmissionCalls = 0;
let orchestrationLateSeedId: string | null = null;
let orchestrationRepairSeedId: string | null = null;
const orchestrationInitialInventoryIds = new Set<string>();
const settingsRows = [
  { key: 'default_workflow_read_route', value: 'openai/gpt-4.1' },
  { key: 'model_pool_workflow_read', value: ['openai/gpt-4.1'] },
  { key: 'workflow_read_reasoning_effort', value: 'low' },
  { key: 'enforce_model_capabilities', value: false },
];
const queryBuilder = (result: unknown, capture?: (value: unknown) => void): any => {
  const builder: any = {
    from: () => builder,
    where: () => builder,
    orderBy: () => builder,
    limit: () => builder,
    groupBy: () => builder,
    onConflictDoNothing: () => builder,
    onConflictDoUpdate: () => builder,
    values: (value: unknown) => { capture?.(value); return builder; },
    set: (value: unknown) => { capture?.(value); return builder; },
    returning: () => queryBuilder([{ id: `orchestration_${++orchestrationId}` }]),
    then: (resolve: (value: unknown) => unknown, reject: (error: unknown) => unknown) =>
      Promise.resolve(result).then(resolve, reject),
  };
  return builder;
};
const orchestrationDb: any = {
  execute: async () => [],
  transaction: async (run: (tx: any) => Promise<unknown>) => run(orchestrationDb),
  select: (shape?: Record<string, unknown>) => {
    if (!shape) return queryBuilder([{
      id: 'openai/gpt-4.1', provider: 'openai', displayName: 'Generic test model',
      structuredOutputs: true, strictJsonSchema: true, deepSchemaAccepted: true,
      adapterParamsSafe: true, toolCalling: true, thinking: true, vision: false,
      pdf: false, promptCaching: true, outputCap: true, contextLength: 1_000_000,
      maxOutputTokens: 65_000, promptPer1mUsd: 1, completionPer1mUsd: 1,
      adapterParamNotes: {}, knowledgeCutoff: null, source: 'openai_api',
    }]);
    const keys = Object.keys(shape ?? {});
    if (keys.includes('fileName')) return queryBuilder([{
      id: orchestrationDocumentId,
      fileName: 'generic-responsibilities.txt',
      fileType: 'text/plain',
      context: null,
    }]);
    if (keys.includes('chunkIndex')) return queryBuilder([{
      id: orchestrationChunkId,
      chunkIndex: 0,
      pageNumber: null,
      rawText: orchestrationText,
      contentHash: 'orchestration-content-hash',
    }]);
    if (keys.includes('key') && keys.includes('value')) return queryBuilder(settingsRows);
    if (keys.includes('promptPer1mUsd') || keys.includes('completionPer1mUsd')) {
      return queryBuilder([{
        id: 'openai/gpt-4.1', promptPer1mUsd: 1, completionPer1mUsd: 1,
      }]);
    }
    return queryBuilder([]);
  },
  insert: () => queryBuilder([], () => undefined),
  update: () => queryBuilder([], (value) => {
    if (value && typeof value === 'object') orchestrationUpdates.push(value as Record<string, unknown>);
  }),
  delete: () => queryBuilder([]),
};
const orchestrationClient: any = {
  compile: (args: any) => ({
    blocks: args.blocks,
    metadata: {
      taskType: args.taskType,
      routeId: args.routeId,
      promptVersion: args.promptVersion,
      stablePrefixHash: 'a'.repeat(64),
      dynamicHash: 'b'.repeat(64),
      blockHashes: [],
      totalTokenEstimate: 100,
      observability: args.observability,
    },
  }),
  runObject: async (args: any) => {
    let object: unknown;
    if (args.taskType === 'source_segmentation') {
      object = {
        documentShape: 'reference',
        summary: 'Shared responsibility sections.',
        segments: [
          { segmentId: 'owner_a', shape: 'responsibilities', title: 'Owner A', chunkIds: [orchestrationChunkId] },
          { segmentId: 'owner_b', shape: 'responsibilities', title: 'Owner B', chunkIds: [orchestrationChunkId] },
        ],
      };
    } else if (args.promptVersion === RESPONSIBILITY_COMPLETION_PROMPT_VERSION) {
      orchestrationCompletionCalls += 1;
      const requestBlock = args.blocks.find((block: any) => block.id === 'responsibility-completion-request');
      const parsed = JSON.parse(requestBlock.content) as {
        seeds: Array<{ responsibilityId: string; sourceSpan?: string }>;
      };
      object = {
        completions: parsed.seeds.map((request) => ({
          responsibilityId: request.responsibilityId,
          label: request.sourceSpan?.toLowerCase().includes('archives requests')
            ? 'Archive requests when closed'
            : 'Send access notices',
          role: 'Service Desk',
          // F4: the model returns the INFLECTED source verb here on purpose. The shared
          // correction seam must normalize it before validation and assembly, so the
          // production path — not a test-only copy — is what proves the seam works.
          action: request.sourceSpan?.toLowerCase().includes('archives requests') ? 'archives' : 'sends',
          object: request.sourceSpan?.toLowerCase().includes('archives requests')
            ? 'requests'
            : 'access notices',
          trigger: request.sourceSpan?.toLowerCase().includes('archives requests') ? 'when closed' : null,
          requiredSystem: null,
          ownerName: null,
          department: null,
        })),
      };
    } else if (args.promptVersion === RESPONSIBILITY_COMBINED_REPAIR_PROMPT_VERSION) {
      orchestrationCombinedRepairCalls += 1;
      const repairRequest = args.blocks.find((block: any) => block.id === 'responsibility-request');
      const parsed = JSON.parse(repairRequest.content.split('\n').at(-1)) as {
        quoteRequests: Array<{
          responsibilityId: string;
          candidates: Array<{ candidateId: string }>;
        }>;
      };
      const repair = parsed.quoteRequests[0]!;
      object = {
        fieldRepairs: [],
        quoteRepairs: [{
          responsibilityId: repair.responsibilityId,
          candidateId: repair.candidates.at(-1)!.candidateId,
        }],
      };
    } else {
      orchestrationResponsibilityCalls += 1;
      const retry = orchestrationResponsibilityCalls > 2;
      const retryContent = retry
        ? args.blocks.find((block: any) => block.id === 'responsibility-request').content as string
        : '';
      const retryJsonStart = retryContent.indexOf('[{"forcedResponsibilityId"');
      const retryJsonEnd = retryContent.indexOf('}]', retryJsonStart);
      const retryRequest = retry
        ? JSON.parse(retryContent.slice(retryJsonStart, retryJsonEnd + 2)) as Array<{
            forcedResponsibilityId: string;
          }>
        : [];
      object = {
        summary: retry ? 'Detection retry duty.' : 'One base duty.',
        responsibilities: [{
          responsibilityId: retry ? retryRequest[0]!.forcedResponsibilityId : 'base_review_packets',
          label: retry ? 'Archive requests' : 'Review intake packets',
          role: 'Service Desk',
          action: retry ? 'archive' : 'review',
          object: retry ? 'requests' : 'intake packets',
          trigger: null,
          requiredSystem: null,
          ownerName: null,
          department: null,
          evidenceQuote: retry ? orchestrationLateDuty : 'Reviews intake packets.',
          chunkId: orchestrationChunkId,
        }],
      };
    }
    return {
      object,
      validation: { ok: true },
      usage: { inputTokens: 10, outputTokens: 10, latencyMs: 1, rawUsageJson: {} },
      routeId: 'openai/gpt-4.1',
      provider: 'openai',
      modelId: 'gpt-4.1',
      attempts: [],
    };
  },
};
const orchestrationResult = await generateSourceWorkflowMap({
  documentId: orchestrationDocumentId,
  triggerRunId: 'r2-local-orchestration',
  force: true,
  db: orchestrationDb,
  client: orchestrationClient,
  orchestrationDependencies: {
    buildBaseReadPlan: (planArgs) => {
      const plan = buildResponsibilityBaseReadPlan(planArgs);
      const initialSeeds = plan.inventorySeeds.filter(
        (seed) => !seed.sourceSpan.toLowerCase().includes('archives requests'),
      );
      for (const seed of initialSeeds) orchestrationInitialInventoryIds.add(seed.inventorySeedId);
      return {
        ...plan,
        inventorySeeds: initialSeeds,
      };
    },
    selectResidualSeeds: (seeds) => seeds.slice(-1),
    findOmissions: () => {
      orchestrationOmissionCalls += 1;
      if (orchestrationOmissionCalls > 2) return [];
      const sourceStart = orchestrationText.indexOf(orchestrationLateDuty);
      return [{
        chunkId: orchestrationChunkId,
        spanIndex: 2,
        sourceSpan: orchestrationLateDuty,
        evidenceQuote: orchestrationLateDuty,
        sourceStart,
        sourceEnd: sourceStart + orchestrationLateDuty.length,
        listStructured: false,
        omissionClass: 'inventory_detection_gap' as const,
      }];
    },
    buildCombinedRepairPlan: (repairArgs) => {
      const preparedReads = repairArgs.reads.map((read) => ({
        ...read,
        model: {
          ...read.model,
          output: {
            ...read.model.output,
            responsibilities: read.model.output.responsibilities.map((record) => ({ ...record })),
          },
        },
      })) as any[];
      const read = preparedReads[0] as any;
      const reviewRecord = read.model.output.responsibilities.find(
        (record: any) => record.action === 'review',
      );
      assert.ok(reviewRecord, 'same-document repair fixture has a review duty');
      orchestrationRepairSeedId = reviewRecord.responsibilityId;
      reviewRecord.evidenceQuote = 'Reviews intake packet.';
      read.validation = validateResponsibilityRead({
        output: read.model.output,
        documentId: orchestrationDocumentId,
        segment: read.segment,
        inventorySeeds: read.inventorySeeds,
        chunks: [{
          id: orchestrationChunkId,
          documentId: orchestrationDocumentId,
          rawText: orchestrationText,
        }],
      });
      assert.ok(
        read.validation.diagnostics.some((item: any) =>
          item.responsibilityId === orchestrationRepairSeedId && item.failureClass === 'quote_mismatch'
        ),
        'same-document duty first fails quote validation',
      );
      return {
        ...buildResponsibilityCombinedRepairPlan({ ...repairArgs, reads: preparedReads }),
        preparedReads,
      };
    },
    selectQuoteRepairRead: (reads) => reads[0],
  },
});
assert.equal(orchestrationResult.status, 'validated');
const savedOrchestration = orchestrationUpdates.find((update) => 'validationJson' in update);
assert.ok(savedOrchestration, 'top-level orchestration saves durable validation audit');
const savedValidation = savedOrchestration!.validationJson as any;
assert.equal(savedValidation.responsibilityInventory.mergeReadyInventoryIds.length, 3);
assert.equal(new Set(savedValidation.responsibilityInventory.mergeReadyInventoryIds).size, 3);
assert.ok(savedValidation.responsibilityCompletion, 'top-level path saves completion audit');
assert.ok(orchestrationCompletionCalls > 0, 'top-level path executes residual model completion');
assert.ok(orchestrationResponsibilityCalls > 2, 'top-level path executes detection retry');
assert.ok(orchestrationCombinedRepairCalls > 0, 'top-level path executes combined quote repair');
assert.ok(savedValidation.responsibilityCompletion.outcomes.length > 0);
assert.ok(savedValidation.responsibilityOmissionAudit.retries.length > 0);
assert.equal(savedValidation.responsibilityQuoteRepair.attempted, true);
const savedInventoryIds = savedValidation.responsibilityInventory.sourceInventoryIds as string[];
const lateIds = savedInventoryIds.filter((id) => !orchestrationInitialInventoryIds.has(id));
assert.equal(lateIds.length, 1, 'retry discovers exactly one genuinely new source-bound duty');
orchestrationLateSeedId = lateIds[0]!;
assert.ok(
  savedValidation.responsibilityInventory.sourceInventoryIds.includes(orchestrationLateSeedId),
  'retry-discovered source identity is present in the saved inventory',
);
assert.ok(
  savedValidation.responsibilityCompletion.outcomes.some((outcome: any) =>
    outcome.responsibilityId === orchestrationLateSeedId && outcome.status === 'accepted'
  ),
  'new retry-discovered duty receives an accepted late completion outcome',
);
assert.ok(
  savedValidation.responsibilityInventory.mergeReadyInventoryIds.includes(orchestrationLateSeedId),
  'new retry-discovered duty is saved as merge-ready',
);
assert.equal(savedValidation.responsibilityQuoteRepair.accepted, true);
assert.equal(savedValidation.responsibilityQuoteRepair.rootQuoteFailuresBefore, 1);
assert.equal(savedValidation.responsibilityQuoteRepair.rootQuoteFailuresAfter, 0);
const repairedSegmentAudit = savedValidation.responsibilitySegments.find(
  (segment: any) => segment.mergeReadyInventoryIds.includes(orchestrationRepairSeedId),
);
assert.ok(repairedSegmentAudit, 'accepted repair refreshes its saved segment inventory audit');
assert.equal(repairedSegmentAudit.mergeReadyInventoryCount, repairedSegmentAudit.mergeEligibleCount);
assert.deepEqual(
  repairedSegmentAudit.mergeReadyInventoryIds,
  repairedSegmentAudit.sourceInventoryIds,
  'saved inventory IDs agree after accepted quote repair completes every source seed',
);
assert.deepEqual(repairedSegmentAudit.incompleteSeedIds, []);
assert.ok(
  savedValidation.responsibilityQuoteRepair.groundedCandidates.some((candidate: any) =>
    candidate.responsibilityId === orchestrationRepairSeedId &&
    candidate.failedQuote === 'Reviews intake packet.' &&
    candidate.returnedSelection === 'Reviews intake packets.' &&
    candidate.decisionReason === 'accepted_strict_exact_improvement'
  ),
  'same-document quote failure is repaired, accepted, and saved',
);

// ---------------------------------------------------------------------------
// F4. The production seam and its persisted audit.
//
// Plan: plan_r2_source_bound_final_record_correction.md, phase F4. These assertions
// run against the SAME top-level orchestration above — the real
// generateSourceWorkflowMap path with injected dependencies — so there is no
// test-only copy of the seam. The completion stub returns inflected actions, which
// only the shared seam can normalize before validation and assembly.
// ---------------------------------------------------------------------------

const savedCorrection = savedValidation.responsibilityFinalRecordCorrection;
assert.ok(savedCorrection, 'the production path persists a final-record correction audit');
assert.ok(
  savedCorrection.offeredCount > 0,
  'every candidate reaching the seam is recorded, accepted or not',
);
assert.equal(
  savedCorrection.offeredCount,
  savedCorrection.acceptedCount + savedCorrection.refusedCount,
  'the audit accounts for every offered candidate exactly once',
);
assert.ok(
  savedCorrection.acceptedCount > 0,
  'the inflected completion actions are corrected on the production path',
);
assert.ok(
  savedCorrection.reasonCounts.action_inflection_normalized > 0,
  'the audit names the reason each correction was made',
);
assert.deepEqual(
  savedCorrection.acceptedSeedIds,
  savedCorrection.corrections
    .filter((correction: any) => correction.accepted)
    .map((correction: any) => correction.seedId),
  'accepted seed IDs agree with the per-correction detail',
);
for (const correction of savedCorrection.corrections) {
  assert.ok(
    ['exhaustive', 'late'].includes(correction.stage),
    'every correction names the stage that produced it',
  );
  assert.match(
    correction.sourceSpanSha256,
    /^[0-9a-f]{64}$/,
    'every correction carries its source-span hash',
  );
  assert.ok(
    savedInventoryIds.includes(correction.seedId),
    'a correction can only ever be bound to a real source seed',
  );
}
assert.ok(
  savedCorrection.executionRefs.length > 0 &&
    savedCorrection.executionRefs.every((ref: any) =>
      typeof ref.modelRunId === 'string' && typeof ref.contextPackId === 'string'
    ),
  'the audit carries execution refs for the stages that produced the candidates',
);
// The corrected record — not the raw one — is what reaches assembly.
const assembledElements = savedOrchestration!.elementsJson as Array<Record<string, unknown>>;
const assembledResponsibilities = assembledElements.filter(
  (element) => element.shape === 'responsibilities' && element.elementKind === 'responsibility',
);
assert.ok(
  assembledResponsibilities.every((element) => !/^(sends|archives|reviews)$/i.test(String(element.action))),
  'no inflected action survives into the assembled map',
);
assert.equal(
  new Set(assembledResponsibilities.map((element) => element.elementId)).size,
  assembledResponsibilities.length,
  'correction never introduces a duplicate assembled identity',
);
assert.ok(
  assembledResponsibilities.every((element) => savedInventoryIds.includes(String(element.elementId))),
  'assembly stays one-to-one with the source inventory after correction',
);
// The audit must never carry source text, only identifiers, counts and hashes.
const savedCorrectionJson = JSON.stringify(savedCorrection);
assert.ok(
  !savedCorrectionJson.includes('intake packets') &&
    !savedCorrectionJson.includes('access notices'),
  'the correction audit records hashes and reasons, never source text',
);

console.log('R2 responsibility strict reader, persistence shape, quote, and coverage contract passed');

// ---------------------------------------------------------------------------
// F0. Freeze the 19/30 production residual boundary.
//
// Plan: plan_r2_source_bound_final_record_correction.md, phase F0.
// Evidence: evals/r2-responsibilities.md, "Eighth production gate", map
// 37a8fc62-23e4-46b7-8464-d1c784dc73cd, Trigger run run_06fv3keiq77bp0gpum352rls01.
//
// The production map held 93 responsibility records. The records below are a
// VERIFIER-ONLY distillation: one representative record per answer-key row,
// reproducing the exact documented failure SHAPE of each of the eleven misses.
// They are not a copy of the 93 stored records, and nothing here may be used by
// production code. Their only job is to pin the residual boundary — which rows
// are eligible for source-bound correction and which are honest refusals — so a
// later phase cannot quietly move that line.
// ---------------------------------------------------------------------------

const R2_FROZEN_FIXTURE_SHA256 =
  '398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be';
const R2_FROZEN_ANSWER_KEY_VERSION = 'licensed-team-responsibilities-v1';
const R2_FROZEN_MATCHER_VERSION = 'field-aware-v3';
const R2_FROZEN_PASS_THRESHOLD = 27;
const R2_FROZEN_EXPECTED_ROWS = 30;
const R2_PRODUCTION_RESIDUAL_SCORE = 19;

const r2FrozenAnswerKey = JSON.parse(
  readFileSync(
    new URL('../__fixtures__/licensed-team-responsibilities-v1.json', import.meta.url),
    'utf8',
  ),
) as {
  version: string;
  sourceSha256: string;
  records: Array<{ role: string; action: string; object: string }>;
};

assert.equal(r2FrozenAnswerKey.version, R2_FROZEN_ANSWER_KEY_VERSION, 'answer key version is frozen');
assert.equal(r2FrozenAnswerKey.sourceSha256, R2_FROZEN_FIXTURE_SHA256, 'fixture SHA-256 is frozen');
assert.equal(r2FrozenAnswerKey.records.length, R2_FROZEN_EXPECTED_ROWS, 'answer key still has 30 rows');
assert.equal(
  RESPONSIBILITY_ANSWER_KEY_MATCHER_VERSION,
  R2_FROZEN_MATCHER_VERSION,
  'frozen matcher version is unchanged',
);

// When the licensed pinned source is reachable on this machine, prove the frozen
// SHA still describes the real file. Absence is not a failure: this suite must
// stay runnable in CI, which has no access to the licensed path.
const r2PinnedFixturePath =
  process.env.R2_PINNED_FIXTURE_PATH ??
  'Z:/Documentation/company process - Oracle/Licensed Team Responsibilities 2 - tagged.txt';
let r2PinnedFixtureText: string | null = null;
try {
  r2PinnedFixtureText = readFileSync(r2PinnedFixturePath, 'utf8');
} catch {
  r2PinnedFixtureText = null;
}
if (r2PinnedFixtureText !== null) {
  assert.equal(
    createHash('sha256').update(r2PinnedFixtureText).digest('hex'),
    R2_FROZEN_FIXTURE_SHA256,
    'reachable pinned fixture still hashes to the frozen SHA-256',
  );
}

// One-based answer-key rows that the 2026-08-11 production gate missed.
const R2_PRODUCTION_MISSED_ROWS = [5, 14, 15, 16, 17, 19, 20, 23, 24, 26, 29] as const;
// Misses whose exact model-visible source span DOES support the expected record.
// These eight are the only rows any correction may target: 19 + 8 = 27.
const R2_CORRECTION_ELIGIBLE_ROWS = [5, 14, 15, 17, 19, 20, 23, 29] as const;
// Honest refusals. Their spans do not support the expected owner/action/object
// without borrowing outside context or changing the action family. A correction
// that "recovers" any of these has cheated and must fail this suite.
const R2_NEGATIVE_CONTROL_ROWS = [16, 24, 26] as const;

assert.equal(
  R2_CORRECTION_ELIGIBLE_ROWS.length + R2_NEGATIVE_CONTROL_ROWS.length,
  R2_PRODUCTION_MISSED_ROWS.length,
  'every production miss is classified exactly once as eligible or as a negative control',
);
assert.deepEqual(
  [...R2_CORRECTION_ELIGIBLE_ROWS, ...R2_NEGATIVE_CONTROL_ROWS].sort((a, b) => a - b),
  [...R2_PRODUCTION_MISSED_ROWS],
  'eligible rows and negative controls partition the eleven misses',
);
assert.equal(
  R2_PRODUCTION_RESIDUAL_SCORE + R2_CORRECTION_ELIGIBLE_ROWS.length,
  R2_FROZEN_PASS_THRESHOLD,
  'the eight eligible recoveries are exactly what the frozen 27/30 gate needs',
);
assert.equal(
  R2_PRODUCTION_RESIDUAL_SCORE,
  R2_FROZEN_EXPECTED_ROWS - R2_PRODUCTION_MISSED_ROWS.length,
  'nineteen matches plus eleven misses accounts for all thirty rows',
);

// Verifier-only reproduction of the production residual. Rows not named here are
// reproduced as an exact copy of the expected record, because production matched
// them. Each entry below carries the documented reason it failed.
const r2ProductionShapedOverrides = new Map<
  number,
  { role: string; action: string; object: string } | null
>([
  // Row 5: object drops the required `concepts` token and absorbs unrelated detail.
  [5, {
    role: 'Licensed Team',
    action: 'submit',
    object: 'designs and tech packs into licensor systems for review',
  }],
  // Row 14: object drops the required named artifact token `PPS` (5 of 6 tokens).
  [14, {
    role: 'Lic Coordinator',
    action: 'download',
    object: 'photos from factory sample request email',
  }],
  // Row 15: no usable rename record survived the read.
  [15, null],
  // Row 16 (negative control): completion child names a different owner and only a
  // partial object; the required owner and object are not both source-visible.
  [16, { role: 'Lic Coordinator', action: 'review', object: 'PPS photos' }],
  // Row 17: the correct duty absorbed a following exception sentence, so its
  // `do not` creates a false negation conflict against an affirmative expectation.
  [17, {
    role: 'Licensed Team',
    action: 'submit',
    object: 'PPS photos in licensor portals, but do not submit before comments are resolved',
  }],
  // Row 19: final fields keep the inflected source action instead of the base verb.
  [19, { role: 'Lic Manager', action: 'Fills out', object: 'Letter of Guarantee' }],
  // Row 20: exact span contains the duty, but the seed stayed a final completion_gap.
  [20, null],
  // Row 23: exact span contains role, action, object and timing, but stayed a completion_gap.
  [23, null],
  // Row 24 (negative control): the span says the Licensed Team ASSISTS the Design
  // Team in downloading. Rewriting assistance as direct download changes the
  // action family and would misstate the duty.
  [24, {
    role: 'Licensed Team',
    action: 'assists',
    object: 'the Design Team in downloading style guides to the style guide server',
  }],
  // Row 26 (negative control): the visible span says only that forecast reports are
  // quarterly. It carries no owner and no submit action.
  [26, null],
  // Row 29: the base action is not retained; the record keeps the inflected `provides`.
  [29, { role: 'Licensed Team', action: 'provides', object: 'assets to partners' }],
]);

for (const row of r2ProductionShapedOverrides.keys()) {
  assert.ok(
    (R2_PRODUCTION_MISSED_ROWS as readonly number[]).includes(row),
    `row ${row} is overridden but is not a documented production miss`,
  );
}
assert.equal(
  r2ProductionShapedOverrides.size,
  R2_PRODUCTION_MISSED_ROWS.length,
  'every documented production miss has a reproduced failure shape',
);

const r2ProductionShapedActuals = r2FrozenAnswerKey.records.flatMap((record, index) => {
  const row = index + 1;
  if (!r2ProductionShapedOverrides.has(row)) return [record];
  const override = r2ProductionShapedOverrides.get(row)!;
  return override === null ? [] : [override];
});

const r2ProductionResidualScore = scoreResponsibilityAnswerKey({
  expected: r2FrozenAnswerKey.records,
  actual: r2ProductionShapedActuals,
});

assert.equal(
  r2ProductionResidualScore.matcherVersion,
  R2_FROZEN_MATCHER_VERSION,
  'the residual boundary is measured by the unchanged matcher',
);
assert.equal(
  r2ProductionResidualScore.matched,
  R2_PRODUCTION_RESIDUAL_SCORE,
  'reproduced production shapes score exactly 19/30 under field-aware-v3',
);
assert.ok(
  r2ProductionResidualScore.matched < R2_FROZEN_PASS_THRESHOLD,
  'the frozen 27/30 gate remains unmet by the production residual',
);

const r2ResidualMissedRows = r2ProductionResidualScore.evidence
  .map((item, index) => (item.matched ? null : index + 1))
  .filter((row): row is number => row !== null);
assert.deepEqual(
  r2ResidualMissedRows,
  [...R2_PRODUCTION_MISSED_ROWS],
  'the reproduced misses are exactly the eleven documented production misses',
);

// Each reproduced miss must fail for its OWN documented reason. Scoring the whole
// residual only proves the row is missing; the evidence it reports for a missing
// row is the best of every candidate, which can belong to a different duty. So
// score each expected row against its own reproduced record in isolation.
const r2RowFailureEvidence = (row: number) => {
  const expected = r2FrozenAnswerKey.records[row - 1]!;
  const actual = r2ProductionShapedOverrides.get(row);
  assert.ok(actual, `row ${row} has no reproduced record to explain`);
  const isolated = scoreResponsibilityAnswerKey({ expected: [expected], actual: [actual!] });
  const evidence = isolated.evidence[0]!;
  assert.equal(evidence.matched, false, `row ${row} must not match its own reproduced record`);
  return evidence;
};

// Row 16, negative control: the completion child names a different owner.
assert.equal(
  r2RowFailureEvidence(16).roleExact,
  false,
  'row 16 fails because the required owner is not source-visible',
);
// Row 24, negative control: assistance is a different action family than download.
assert.equal(
  r2RowFailureEvidence(24).actionMatched,
  false,
  'row 24 fails because assistance is a different action family than direct download',
);
// Row 17: absorbed exception text, not missing object tokens.
const r2Row17 = r2RowFailureEvidence(17);
assert.equal(r2Row17.negationConflict, true, 'row 17 fails on absorbed exception text');
assert.equal(r2Row17.objectTokenCoverage, 1, 'row 17 already carries every required object token');
// Row 14: exactly one lost named artifact token.
const r2Row14 = r2RowFailureEvidence(14);
assert.equal(r2Row14.actionMatched, true, 'row 14 has the right action');
assert.ok(
  r2Row14.objectTokenCoverage > 0.8 && r2Row14.objectTokenCoverage < 1,
  'row 14 fails on exactly one lost named artifact token',
);
// Row 5: the object drops a required token and absorbs unrelated detail.
const r2Row5 = r2RowFailureEvidence(5);
assert.equal(r2Row5.actionMatched, true, 'row 5 has the right action');
assert.ok(r2Row5.objectTokenCoverage < 1, 'row 5 fails on an incomplete object');
// Rows 19 and 29: inflected action only; the object is already complete.
for (const row of [19, 29]) {
  const evidence = r2RowFailureEvidence(row);
  assert.equal(evidence.roleExact, true, `row ${row} already has the right owner`);
  assert.equal(evidence.actionMatched, false, `row ${row} fails on the inflected action alone`);
  assert.equal(evidence.objectTokenCoverage, 1, `row ${row} already carries the full expected object`);
  assert.equal(evidence.negationConflict, false, `row ${row} has no polarity problem`);
}
// Rows 15, 20, 23 and 26 produced no usable record at all.
for (const row of [15, 20, 23, 26]) {
  assert.equal(
    r2ProductionShapedOverrides.get(row),
    null,
    `row ${row} is reproduced as a seed that stayed incomplete, with no final record`,
  );
}

// Frozen operating limits. These are the production defaults the correction plan
// forbids changing. They are asserted against the real declaration sites so a
// silent edit to a budget or a fail-safe flag breaks this gate.
// Line endings are normalized before matching. `core.autocrlf` is true in this
// repo and there is no blanket `text eol=lf`, so a FRESH clone on Windows checks
// these files out with CRLF and every multi-line literal below would miss. That
// is not hypothetical: it is exactly what broke a delegated agent working in a
// fresh clone on 2026-08-13. The pre-existing frozen-budget guard earlier in this
// file has the same fragility and is normalized the same way.
const r2SourceWorkflowSource = readFileSync(
  new URL('../lib/source-workflow-read.ts', import.meta.url),
  'utf8',
).replace(/\r\n/g, '\n');
for (const frozenLimit of [
  "readNumberSetting(db, 'source_reader_max_read_calls_per_source', 40)",
  "readNumberSetting(db, 'source_reader_max_input_tokens_per_source', 500_000)",
  "readNumberSetting(db, 'source_reader_max_estimated_cost_usd_per_source', 10)",
  "readNumberSetting(db, 'source_reader_max_repair_attempts_per_source', 1)",
  "readNumberSetting(db, 'source_reader_max_concurrency_per_source', 4)",
  "'responsibility_postpass_max_quote_repairs_per_source',\n      1,",
  "'responsibility_postpass_max_omission_retries_per_source',\n      5,",
  "'responsibility_postpass_max_omission_retries_per_chunk',\n      1,",
]) {
  assert.ok(
    r2SourceWorkflowSource.includes(frozenLimit),
    `frozen reader budget default changed: ${frozenLimit.replace(/\n\s*/g, ' ')}`,
  );
}

const r2SeedSource = readFileSync(new URL('../../../../packages/db/src/seed.ts', import.meta.url), 'utf8');
for (const failSafeFlag of [
  'business_model_merge_enabled',
  'business_model_apply_enabled',
  'business_model_serving_enabled',
]) {
  assert.ok(
    new RegExp(`\\{ key: '${failSafeFlag}', value: false,`).test(r2SeedSource),
    `fail-safe flag ${failSafeFlag} must still default to false`,
  );
}

console.log(
  `R2 frozen residual boundary: ${r2ProductionResidualScore.matched}/${R2_FROZEN_EXPECTED_ROWS} ` +
    `reproduced under ${R2_FROZEN_MATCHER_VERSION}; ` +
    `eligible rows ${R2_CORRECTION_ELIGIBLE_ROWS.join(', ')}; ` +
    `negative controls ${R2_NEGATIVE_CONTROL_ROWS.join(', ')}`,
);

// ---------------------------------------------------------------------------
// F1. Generic failing tests for the source-bound final-record correction.
//
// Plan: plan_r2_source_bound_final_record_correction.md, phase F1.
//
// These cases are RED until F2 lands. That is deliberate: they define the exact
// contract F2 must satisfy before any production line is written. Everything
// here uses INVENTED source text. No licensed wording, no answer-key phrase, and
// no fixture term appears below, so passing these cases can never be achieved by
// tuning to the pinned document.
//
// The helper is resolved dynamically so this file keeps compiling and every case
// above stays green while F2 does not exist yet. Each case then reports its own
// intended failure instead of the whole suite dying at an unresolved import.
// ---------------------------------------------------------------------------

type R2FinalRecordFields = {
  role: string;
  action: string;
  object: string;
  trigger: string | null;
};

type R2FinalRecordCorrection = {
  seedId: string;
  sourceSpanSha256: string;
  accepted: boolean;
  reasons: string[];
  before: R2FinalRecordFields;
  after: R2FinalRecordFields | null;
};

type R2CorrectFinalRecord = (args: {
  seed: ResponsibilityInventorySeed;
  candidate: R2FinalRecordFields;
}) => R2FinalRecordCorrection;

const r2ReaderModule = (await import('../lib/responsibility-reader')) as unknown as Record<
  string,
  unknown
>;
const r2CorrectFinalRecord = r2ReaderModule.correctResponsibilityFinalRecord as
  | R2CorrectFinalRecord
  | undefined;

const r2SeedFrom = (rawText: string, matcher: RegExp): ResponsibilityInventorySeed => {
  const inventory = buildResponsibilitySourceInventory([{
    id: `f1_chunk_${Math.abs(hashF1(rawText))}`,
    documentId: 'f1_generic_document',
    rawText,
  }]);
  const seed = inventory.seeds.find((candidate) => matcher.test(candidate.sourceSpan));
  assert.ok(seed, `F1 fixture did not produce a seed matching ${matcher}`);
  return seed!;
};

function hashF1(value: string): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) | 0;
  }
  return hash;
}

const r2CorrectOrThrow: R2CorrectFinalRecord = (args) => {
  if (!r2CorrectFinalRecord) {
    throw new Error(
      'correctResponsibilityFinalRecord is not exported from responsibility-reader yet (F2 not implemented)',
    );
  }
  return r2CorrectFinalRecord(args);
};

const r2F1Cases: Array<{ name: string; run: () => void }> = [];
const r2F1Case = (name: string, run: () => void) => r2F1Cases.push({ name, run });

// 1. Ordinary verb inflection is reduced to the base duty verb.
r2F1Case('regular verb inflection is normalized to the base duty verb', () => {
  const seed = r2SeedFrom('- Fleet Office provides route packets to depot partners.', /route packets/);
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Fleet Office',
      action: 'provides',
      object: 'route packets to depot partners',
      trigger: null,
    },
  });
  assert.equal(result.accepted, true, 'an inflected action with a complete object is correctable');
  assert.equal(result.after?.action, 'provide');
  assert.equal(result.after?.object, 'route packets to depot partners');
  assert.ok(result.reasons.includes('action_inflection_normalized'));
});

// 2. A multi-word action keeps its particle while the verb is normalized.
r2F1Case('multi-word verb inflection keeps its particle', () => {
  const seed = r2SeedFrom('- Depot Lead fills out the Letter of Compliance.', /Letter of Compliance/);
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Depot Lead',
      action: 'Fills out',
      object: 'Letter of Compliance',
      trigger: null,
    },
  });
  assert.equal(result.accepted, true);
  assert.equal(result.after?.action, 'fill out', 'the particle survives verb normalization');
});

// 3. Nouns are never verb-stemmed. Only the action is normalized.
r2F1Case('object nouns are not stemmed', () => {
  const seed = r2SeedFrom('- Fleet Office records depot readings in the ledger.', /depot readings/);
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Fleet Office',
      action: 'records',
      object: 'depot readings in the ledger',
      trigger: null,
    },
  });
  assert.equal(result.after?.action, 'record');
  assert.ok(
    /readings/.test(result.after?.object ?? ''),
    'a noun that looks like a verb form is left alone in the object',
  );
});

// 4. A separate exception leaves the affirmative object and is kept in trigger.
r2F1Case('a separate exception moves to trigger and out of the object', () => {
  const seed = r2SeedFrom(
    '- Depot Lead submits inspection photos in partner portals. Do not submit before the depot review closes.',
    /inspection photos/,
  );
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Depot Lead',
      action: 'submit',
      object: 'inspection photos in partner portals. Do not submit before the depot review closes',
      trigger: null,
    },
  });
  assert.equal(result.accepted, true);
  assert.ok(
    !/\bdo not\b/i.test(result.after?.object ?? ''),
    'the affirmative object no longer carries the exception polarity',
  );
  assert.ok(
    /do not submit before the depot review closes/i.test(result.after?.trigger ?? ''),
    'the exception is preserved verbatim in trigger, never discarded',
  );
  assert.ok(result.reasons.includes('condition_moved_to_trigger'));
});

// 5. An over-wide list object is cut back to the one duty clause.
r2F1Case('an over-wide list object is narrowed to its own clause', () => {
  const seed = r2SeedFrom(
    '- Depot Lead submits concept sketches into partner portals.\n- Depot Lead archives depot manifests.',
    /concept sketches/,
  );
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Depot Lead',
      action: 'submit',
      object: 'concept sketches into partner portals and archives depot manifests',
      trigger: null,
    },
  });
  assert.equal(result.accepted, true);
  assert.equal(result.after?.object, 'concept sketches into partner portals');
  assert.ok(
    !/manifest/i.test(result.after?.object ?? ''),
    'a later sibling clause can never leak into an earlier clause object',
  );
  assert.ok(result.reasons.includes('object_boundary_isolated'));
});

// 6. A named artifact token dropped by the candidate is restored from the span.
r2F1Case('a dropped named artifact token is restored from the exact span', () => {
  const seed = r2SeedFrom(
    '- Depot Lead downloads QA1 photos from the depot intake email.',
    /QA1 photos/,
  );
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Depot Lead',
      action: 'download',
      object: 'photos from the depot intake email',
      trigger: null,
    },
  });
  assert.equal(result.accepted, true);
  assert.ok(
    /QA1/.test(result.after?.object ?? ''),
    'a required named artifact present in the exact span cannot be silently lost',
  );
  assert.ok(result.reasons.includes('named_artifact_restored'));
});

// 7. An ambiguous object boundary is refused, not guessed.
r2F1Case('an ambiguous object boundary is refused', () => {
  const seed = r2SeedFrom(
    '- Depot Lead reviews and updates depot manifests and route packets.',
    /depot manifests/,
  );
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Depot Lead',
      action: 'review',
      object: 'depot manifests and route packets',
      trigger: null,
    },
  });
  assert.equal(result.accepted, false, 'an ambiguous boundary fails loudly rather than guessing');
  assert.equal(result.after, null);
  assert.ok(result.reasons.includes('ambiguous_object_boundary'));
});

// 8. A missing owner or action is refused, never invented.
r2F1Case('a missing owner or action is refused', () => {
  const seed = r2SeedFrom('- Fleet Office provides route packets to depot partners.', /route packets/);
  for (const [field, candidate] of [
    ['owner', { role: '', action: 'provide', object: 'route packets to depot partners', trigger: null }],
    ['action', { role: 'Fleet Office', action: '', object: 'route packets to depot partners', trigger: null }],
  ] as const) {
    const result = r2CorrectOrThrow({ seed, candidate });
    assert.equal(result.accepted, false, `a missing ${field} is not correctable`);
    assert.equal(result.after, null);
    assert.ok(
      result.reasons.some((reason) => /^missing_(?:owner|action)$/.test(reason)),
      `a missing ${field} reports its own reason`,
    );
  }
});

// 9. A reversed direction is refused. Correction may not change the action family.
r2F1Case('a polarity reversal is refused', () => {
  const seed = r2SeedFrom('- Fleet Office provides route packets to depot partners.', /route packets/);
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Fleet Office',
      action: 'downloads',
      object: 'route packets to depot partners',
      trigger: null,
    },
  });
  assert.equal(result.accepted, false, 'an inbound action cannot be normalized onto an outbound duty');
  assert.ok(result.reasons.includes('polarity_reversal'));
});

// 10. Correction is accepted only as a strict improvement.
r2F1Case('an already-faithful record is not rewritten', () => {
  const seed = r2SeedFrom('- Fleet Office provides route packets to depot partners.', /route packets/);
  const candidate = {
    role: 'Fleet Office',
    action: 'provide',
    object: 'route packets to depot partners',
    trigger: null,
  };
  const result = r2CorrectOrThrow({ seed, candidate });
  assert.equal(result.accepted, false, 'a record that already passes is left untouched');
  assert.ok(result.reasons.includes('no_strict_improvement'));
});

// 11. Source binding is immutable through correction.
r2F1Case('source binding is immutable', () => {
  const seed = r2SeedFrom('- Fleet Office provides route packets to depot partners.', /route packets/);
  const frozenSeed = JSON.parse(JSON.stringify(seed)) as ResponsibilityInventorySeed;
  const result = r2CorrectOrThrow({
    seed,
    candidate: {
      role: 'Fleet Office',
      action: 'provides',
      object: 'route packets to depot partners',
      trigger: null,
    },
  });
  assert.deepEqual(seed, frozenSeed, 'correction never mutates the seed it was given');
  assert.equal(result.seedId, seed.inventorySeedId);
  assert.equal(result.sourceSpanSha256, seed.sourceSpanSha256);
});

// 12. The audit is deterministic and carries the before state on every outcome.
r2F1Case('the correction audit is deterministic and complete', () => {
  const seed = r2SeedFrom('- Fleet Office provides route packets to depot partners.', /route packets/);
  const candidate = {
    role: 'Fleet Office',
    action: 'provides',
    object: 'route packets to depot partners',
    trigger: null,
  };
  const first = r2CorrectOrThrow({ seed, candidate });
  const second = r2CorrectOrThrow({ seed, candidate });
  assert.deepEqual(first, second, 'the same seed and candidate always produce the same audit');
  assert.deepEqual(first.before, candidate, 'the audit records the untouched original fields');
  assert.deepEqual(
    [...first.reasons].sort(),
    first.reasons,
    'reason codes are emitted in a stable sorted order',
  );
});

// 13. Correction may never regress the unchanged field-fidelity validator.
//
// Note the boundary this case pins. `validateResponsibilityFieldFidelity` already
// stems the returned action, so an inflected `provides` passes fidelity today —
// the inflection only breaks the frozen answer-key matcher. So F2's acceptance
// test cannot be "fidelity now passes"; it must be "fidelity does not regress AND
// the named defect is gone". The absorbed-condition case is the one that fails
// fidelity today, and it must pass afterwards.
r2F1Case('correction never regresses unchanged field fidelity', () => {
  const inflectedSeed = r2SeedFrom(
    '- Fleet Office provides route packets to depot partners.',
    /route packets/,
  );
  const inflected = {
    role: 'Fleet Office',
    action: 'provides',
    object: 'route packets to depot partners',
    trigger: null,
  };
  assert.equal(
    validateResponsibilityFieldFidelity(inflectedSeed.sourceSpan, inflected).passed,
    true,
    'fidelity already tolerates an inflected action; only the frozen matcher rejects it',
  );
  const inflectedResult = r2CorrectOrThrow({ seed: inflectedSeed, candidate: inflected });
  assert.equal(inflectedResult.accepted, true);
  assert.equal(
    validateResponsibilityFieldFidelity(inflectedSeed.sourceSpan, inflectedResult.after!).passed,
    true,
    'a correction may never turn a fidelity-passing record into a failing one',
  );

  const artifactSeed = r2SeedFrom(
    '- Depot Lead downloads QA1 photos from the depot intake email.',
    /QA1 photos/,
  );
  const droppedArtifact = {
    role: 'Depot Lead',
    action: 'download',
    object: 'photos from the depot intake email',
    trigger: null,
  };
  assert.equal(
    validateResponsibilityFieldFidelity(artifactSeed.sourceSpan, droppedArtifact).passed,
    false,
    'a dropped artifact token is a shape fidelity really does reject today',
  );
  const artifactResult = r2CorrectOrThrow({ seed: artifactSeed, candidate: droppedArtifact });
  assert.equal(artifactResult.accepted, true);
  assert.equal(
    validateResponsibilityFieldFidelity(artifactSeed.sourceSpan, artifactResult.after!).passed,
    true,
    'correction is judged by the unchanged validator, which is never weakened',
  );
});

// 14. F2b invariant: a cut condition must be preserved, never silently dropped.
//
// This case used to pin an unresolved conflict. It was resolved on 2026-08-13 by
// aligning the expected object with the locked field-boundary rule, and it now pins
// the guarantee that makes that alignment a correction rather than a loosening.
//
// Narrowing the expected object, on its own, WOULD be a loosening: the exception
// words would simply stop being required anywhere. The paired rule is what closes
// that hole. If the boundary cut a condition off the object, the record must carry
// that condition verbatim in `trigger`, or fidelity fails with
// `condition_not_preserved_in_trigger`.
r2F1Case('F2b: a cut condition must be preserved verbatim in trigger', () => {
  const seed = r2SeedFrom(
    '- Depot Lead submits inspection photos in partner portals. Do not submit before the depot review closes.',
    /inspection photos/,
  );

  // The shape production actually stored: the exception is still inside the object.
  const absorbed = {
    role: 'Depot Lead',
    action: 'submit',
    object: 'inspection photos in partner portals. Do not submit before the depot review closes',
    trigger: null,
  };
  assert.equal(
    validateResponsibilityFieldFidelity(seed.sourceSpan, absorbed).passed,
    false,
    'the absorbed shape is now rejected: the condition is not in trigger',
  );

  // The dangerous shape: condition cut out of the object and preserved NOWHERE.
  // This is the silent loss the paired rule exists to prevent.
  const droppedCondition = {
    role: 'Depot Lead',
    action: 'submit',
    object: 'inspection photos in partner portals',
    trigger: null,
  };
  const droppedResult = validateResponsibilityFieldFidelity(seed.sourceSpan, droppedCondition);
  assert.equal(droppedResult.passed, false, 'dropping a condition entirely must never pass');
  assert.ok(
    droppedResult.reasons.includes('condition_not_preserved_in_trigger'),
    'and it must fail for that exact named reason, not by accident',
  );

  // The correct shape: minimal object, condition preserved verbatim in trigger.
  const corrected = {
    role: 'Depot Lead',
    action: 'submit',
    object: 'inspection photos in partner portals',
    trigger: 'Do not submit before the depot review closes',
  };
  assert.equal(
    validateResponsibilityFieldFidelity(seed.sourceSpan, corrected).passed,
    true,
    'the corrected shape passes the unchanged validator with no exemption',
  );

  // And the corrector must produce exactly that shape, on merit.
  const result = r2CorrectOrThrow({ seed, candidate: absorbed });
  assert.equal(result.accepted, true, 'the repair is accepted without any bypass');
  assert.equal(
    validateResponsibilityFieldFidelity(seed.sourceSpan, result.after!).passed,
    true,
    'an accepted repair always satisfies the validator; no acceptance-rule exemption exists',
  );
});

// 15. The boundary must cut an in-sentence exception, not only a sentence end.
// This is the case the rejected sentence-boundary-only patch would have missed, and
// it is the common shape in real documents.
r2F1Case('F2b: an in-sentence exception cue is a boundary', () => {
  const seed = r2SeedFrom(
    '- Depot Lead submits inspection photos in partner portals unless the depot review is open.',
    /inspection photos/,
  );
  const wide = {
    role: 'Depot Lead',
    action: 'submit',
    object: 'inspection photos in partner portals unless the depot review is open',
    trigger: null,
  };
  assert.equal(
    validateResponsibilityFieldFidelity(seed.sourceSpan, wide).passed,
    false,
    'an in-sentence condition left inside the object is rejected',
  );
  const corrected = {
    role: 'Depot Lead',
    action: 'submit',
    object: 'inspection photos in partner portals',
    trigger: 'unless the depot review is open',
  };
  assert.equal(
    validateResponsibilityFieldFidelity(seed.sourceSpan, corrected).passed,
    true,
    'the same repair works mid-sentence, which a period-only rule could never do',
  );
});

// 16. A tail cut because it belongs to ANOTHER duty must not be demanded in trigger.
// Collapsing this distinction is what would turn `trigger` into a junk drawer.
r2F1Case('F2b: a neighbouring duty is not forced into this record trigger', () => {
  const seed = r2SeedFrom(
    '- Depot Lead reviews depot manifests. Fleet Office archives route packets.',
    /depot manifests/,
  );
  const record = {
    role: 'Depot Lead',
    action: 'review',
    object: 'depot manifests',
    trigger: null,
  };
  const result = validateResponsibilityFieldFidelity(seed.sourceSpan, record);
  assert.ok(
    !result.reasons.includes('condition_not_preserved_in_trigger'),
    'text belonging to a different duty is never demanded in this record trigger',
  );
});

const r2F1Failures: Array<{ name: string; message: string }> = [];
for (const testCase of r2F1Cases) {
  try {
    testCase.run();
  } catch (error) {
    r2F1Failures.push({
      name: testCase.name,
      message: error instanceof Error ? error.message : String(error),
    });
  }
}

if (r2F1Failures.length > 0) {
  console.error(`\nF1 red gate: ${r2F1Failures.length}/${r2F1Cases.length} correction cases failing:`);
  for (const failure of r2F1Failures) {
    console.error(`  - ${failure.name}\n      ${failure.message.split('\n')[0]}`);
  }
  assert.fail(
    `F1 correction contract is not satisfied: ${r2F1Failures.length}/${r2F1Cases.length} cases failing. ` +
      'This is the expected state until F2 lands.',
  );
}

console.log(`R2 final-record correction contract: ${r2F1Cases.length}/${r2F1Cases.length} cases passed`);

// ---------------------------------------------------------------------------
// F6. The persisted correction audit may not overstate what actually happened.
//
// The corrector's own `accepted` flag means only "something changed and fidelity did
// not get worse". The seam applies the correction WITHOUT re-validating; the caller's
// validateResponsibilityRead judges it afterwards, and the batch can still fail or be
// retried. Reporting that raw flag as `accepted` in a persisted audit therefore claims
// more than was proven — raised as P1 by the F6 reviewer (Codex, 2026-08-26).
//
// The builder now reconciles every row against the seeds that actually reached the map.
// These cases pin that reconciliation directly, so a future session cannot quietly drop
// the `persistedSeedIds` argument and restore the overstating audit.
// ---------------------------------------------------------------------------

const f6CorrectionRow = (seedId: string, accepted: boolean) => ({
  seedId,
  sourceSpanSha256: createHash('sha256').update(`f6-span-${seedId}`).digest('hex'),
  accepted,
  reasons: accepted ? ['action_inflection_normalized'] : ['no_strict_improvement'],
  before: { role: 'Depot Lead', action: 'files', object: 'route packets', trigger: null },
  after: accepted
    ? { role: 'Depot Lead', action: 'file', object: 'route packets', trigger: null }
    : null,
});

const f6Audit = buildResponsibilityFinalRecordCorrectionAudit({
  seams: [
    {
      stage: 'exhaustive' as const,
      corrections: [
        f6CorrectionRow('f6-seed-kept', true),
        f6CorrectionRow('f6-seed-dropped', true),
        f6CorrectionRow('f6-seed-refused', false),
      ] as any,
    },
  ],
  executionRefs: [
    { stage: 'exhaustive' as const, modelRunId: 'f6-run', contextPackId: 'f6-pack' },
  ],
  persistedSeedIds: new Set(['f6-seed-kept']),
});

assert.deepEqual(
  f6Audit.acceptedSeedIds,
  ['f6-seed-kept'],
  'F6: only a correction that actually reached the persisted map may be reported as accepted',
);
assert.ok(
  f6Audit.refusedSeedIds.includes('f6-seed-dropped'),
  'F6: a correction the corrector took but that did not survive is reported as refused',
);
assert.equal(
  f6Audit.acceptedCount,
  1,
  'F6: acceptedCount counts persisted corrections, not corrections merely taken',
);
assert.equal(
  f6Audit.offeredCount,
  f6Audit.acceptedCount + f6Audit.refusedCount,
  'F6: reconciliation still accounts for every offered candidate exactly once',
);
const f6Dropped = f6Audit.corrections.find((item) => item.seedId === 'f6-seed-dropped');
assert.ok(
  f6Dropped && f6Dropped.reasons.includes('correction_not_persisted'),
  'F6: a downgraded row names why it was downgraded, so it stays distinguishable from a plain refusal',
);
const f6Refused = f6Audit.corrections.find((item) => item.seedId === 'f6-seed-refused');
assert.ok(
  f6Refused && !f6Refused.reasons.includes('correction_not_persisted'),
  'F6: a correction the corrector itself refused is not relabelled as a persistence loss',
);

// The production path must agree: every seed the persisted audit calls accepted is a seed
// that is actually present in the persisted elements. This is the assertion that would
// have failed before the F6 fix.
for (const seedId of savedCorrection.acceptedSeedIds) {
  assert.ok(
    savedInventoryIds.includes(seedId),
    'F6: an accepted correction on the production path names a seed that reached the map',
  );
}

// ---------------------------------------------------------------------------
// F6. The scorer masks multi-row matches when it is given a single actual.
//
// This is the trap that made the first attempt at the replay gate's record-level
// fix a no-op. `scoreResponsibilityAnswerKey` assigns greedily and guards with
// `assignedActual.has(actualIndex)`, so ONE actual can only ever be assigned to ONE
// expected row: its greedy-best. Every other row that same record satisfies is
// forced to `matched: false` in the returned evidence.
//
// Consequence, and the reason this is pinned rather than commented: any code that
// asks "which rows does this record satisfy on its own?" by scoring the record
// against ALL rows in one call gets a silently truncated answer, and a count built
// that way reads as a clean zero no matter what the data holds. The only correct
// way to ask is one expected row per call.
//
// Invented source wording only — Fleet Office / Depot Lead house style.
// ---------------------------------------------------------------------------

const f6RowA = {
  role: 'Depot Lead',
  action: 'file',
  object: 'route packets',
} as const;
const f6RowB = {
  role: 'Depot Lead',
  action: 'file',
  object: 'route packets and QA1 photos',
} as const;
const f6RecordBoth = {
  role: 'Depot Lead',
  action: 'file',
  object: 'route packets and QA1 photos',
};

const f6MatchesAlone = (expected: { role: string; action: string; object: string }) =>
  scoreResponsibilityAnswerKey({ expected: [expected], actual: [f6RecordBoth] }).evidence[0]
    ?.matched === true;

assert.ok(
  f6MatchesAlone(f6RowA) && f6MatchesAlone(f6RowB),
  'F6: the invented record must genuinely satisfy BOTH rows on its own, or this case proves nothing',
);

const f6CombinedEvidence = scoreResponsibilityAnswerKey({
  expected: [f6RowA, f6RowB],
  actual: [f6RecordBoth],
}).evidence;
assert.equal(
  f6CombinedEvidence.filter((item) => item.matched).length,
  1,
  'F6: scoring one actual against many rows reports at most one match — this is the masking trap',
);

// And the per-row form, which is what the replay gate must use, recovers both.
const f6IsolatedRows = [f6RowA, f6RowB].filter((row) => f6MatchesAlone(row));
assert.equal(
  f6IsolatedRows.length,
  2,
  'F6: asking one expected row per call is the only way to recover the full isolated match set',
);

// ---------------------------------------------------------------------------
// F6. A record with no resolvable enclosing duty span must still be proved.
//
// `resolveEnclosingResponsibilityDutySpan` returns null when no duty span encloses the
// evidence quote AND the quote itself carries no duty verb. Before this fix that produced
// `fieldFidelity = null`, and because the rejection branch only fires when fidelity EXISTS
// and fails, the record was accepted and persisted having passed NO field check at all —
// not owner match, not polarity, not anti-invention, not multi-verb, and not the condition
// rule. Both F6 reviewers found it independently.
//
// The record below carries an INVENTED object token ('QA1 photos') that does not appear in
// its source at all, so it must be rejected by anti-invention. Its quote is an exact,
// verb-less fragment of the chunk, which is what defeats the span resolver. It has a
// matched inventory seed, so the seed's own immutable source span is available as the
// fidelity source and is now used.
//
// Invented source wording only.
// ---------------------------------------------------------------------------

const f6SpanlessChunkId = 'f6_spanless_chunk';
const f6SpanlessChunks = [{
  id: f6SpanlessChunkId,
  documentId,
  rawText: '[Depot Lead]\n- Upload route packets into Hub North.\nHub North is open on weekdays.',
}];
const f6SpanlessInventory = buildResponsibilitySourceInventory(f6SpanlessChunks);
assert.equal(f6SpanlessInventory.seeds.length, 1, 'F6: the spanless case needs exactly one seed');
const f6SpanlessSeed = f6SpanlessInventory.seeds[0]!;

// Verb-less exact fragment: no duty verb, so the enclosing-span resolver returns null.
const f6VerblessQuote = 'Hub North is open on weekdays';
assert.ok(
  f6SpanlessChunks[0]!.rawText.includes(f6VerblessQuote),
  'F6: the evidence quote must be an exact substring or the quote gate rejects it first',
);
assert.equal(
  resolveEnclosingResponsibilityDutySpan({
    rawText: f6SpanlessChunks[0]!.rawText,
    evidenceQuote: f6VerblessQuote,
    fileType: 'text/plain',
    fileName: 'f6.txt',
  }),
  null,
  'F6: this quote must genuinely defeat the span resolver, or the case proves nothing',
);

const f6SpanlessValidation = validateResponsibilityRead({
  output: {
    summary: 'F6 spanless fidelity case.',
    responsibilities: [{
      responsibilityId: f6SpanlessSeed.inventorySeedId,
      chunkId: f6SpanlessChunkId,
      label: 'Depot Lead: file QA1 photos',
      role: 'Depot Lead',
      action: 'file',
      // Invented: 'QA1 photos' appears nowhere in the source span.
      object: 'QA1 photos',
      trigger: null,
      evidenceQuote: f6VerblessQuote,
    }],
  } as any,
  documentId,
  segment: {
    segmentId: 'f6_spanless_segment',
    title: 'F6 spanless',
    shape: 'responsibilities',
    summary: 'F6 spanless validation segment.',
    chunkIds: [f6SpanlessChunkId],
  },
  chunks: f6SpanlessChunks,
  allCoveredChunkIds: new Set([f6SpanlessChunkId]),
  inventorySeeds: f6SpanlessInventory.seeds,
  fileType: 'text/plain',
  fileName: 'f6.txt',
} as any);

assert.ok(
  !f6SpanlessValidation.completeElementIds.includes(f6SpanlessSeed.inventorySeedId),
  'F6: a record whose enclosing span does not resolve is still proved against its seed span, and an invented object is rejected',
);
assert.deepEqual(
  f6SpanlessValidation.unprovenFieldFidelityElementIds,
  [],
  'F6: with a matched seed available, nothing is accepted without a fidelity check',
);
