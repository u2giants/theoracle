import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  RESPONSIBILITY_READ_PROMPT_VERSION,
  RESPONSIBILITY_QUOTE_REPAIR_PROMPT_VERSION,
  RESPONSIBILITY_READ_SYSTEM_PROMPT,
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
  responsibilityParentSegment,
  responsibilityRawAuditArtifact,
  rankResponsibilityOmissionChunks,
  selectFocusedResponsibilityOmissions,
  RESPONSIBILITY_FOCUSED_OMISSION_LIMIT,
  ResponsibilityOmissionRetryScheduler,
  buildResponsibilityOmissionAudit,
  shardResponsibilitySegments,
  validateResponsibilityRead,
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
  buildResponsibilityRequestContent,
  responsibilityReadPromptVersion,
  responsibilityReadTaskType,
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
      object: 'art files for completeness',
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
assert.equal(RESPONSIBILITY_READ_PROMPT_VERSION, 'responsibility-read-v2.2-field-faithful');
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
  'source-responsibility-quote-repair',
  'quote-only model calls have distinct durable task identity',
);
assert.equal(responsibilityReadTaskType(false), 'source-responsibility-read');
assert.equal(
  responsibilityReadPromptVersion(true),
  'responsibility-quote-repair-v2.2',
);
assert.equal(
  responsibilityReadPromptVersion(false),
  'responsibility-read-v2.2-field-faithful',
);
assert.equal(
  RESPONSIBILITY_QUOTE_REPAIR_PROMPT_VERSION,
  'responsibility-quote-repair-v2.2',
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
});
assert.match(quoteOnlyRequest, /Quote-copy repair only/);
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
  buildResponsibilityRequestContent({ focusedSpans: ['Finance approves invoices.'] }),
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
assert.equal(
  responsibilityShadowLockKey(lockArgs),
  responsibilityShadowLockKey(lockArgs),
  'concurrent same-input dispatches must serialize on one advisory lock',
);

console.log('R2 responsibility strict reader, persistence shape, quote, and coverage contract passed');
