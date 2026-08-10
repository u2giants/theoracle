import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  RESPONSIBILITY_READ_PROMPT_VERSION,
  RESPONSIBILITY_COMBINED_REPAIR_PROMPT_VERSION,
  RESPONSIBILITY_QUOTE_REPAIR_PROMPT_VERSION,
  RESPONSIBILITY_QUOTE_REPAIR_SYSTEM_PROMPT,
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
  executeResponsibilityCompletionBatches,
  isRetryableResponsibilityCompletionFailure,
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
const workflowReadSource = readFileSync(
  new URL('../lib/source-workflow-read.ts', import.meta.url),
  'utf8',
);
const responsibilityReaderSource = readFileSync(
  new URL('../lib/responsibility-reader.ts', import.meta.url),
  'utf8',
);
const documentIngestionSource = readFileSync(
  new URL('../trigger/document-ingestion.ts', import.meta.url),
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
      !responsibilityReaderSource.includes(forbiddenRuntimeLeak),
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
  'const combinedRepairPlan = buildResponsibilityCombinedRepairPlan({',
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
    !responsibilityReaderSource.includes(term),
    `runtime responsibility reader leaked fixture-derived term: ${term}`,
  );
}
assert.equal(
  responsibilityShadowLockKey(lockArgs),
  responsibilityShadowLockKey(lockArgs),
  'concurrent same-input dispatches must serialize on one advisory lock',
);

console.log('R2 responsibility strict reader, persistence shape, quote, and coverage contract passed');
