import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  RESPONSIBILITY_READ_PROMPT_VERSION,
  RESPONSIBILITY_READ_SYSTEM_PROMPT,
  type ResponsibilityReadOutput,
  type SourceStructureSegment,
} from '@oracle/ai';
import {
  responsibilityCoverage,
  responsibilityRawAuditArtifact,
  validateResponsibilityRead,
} from '../lib/responsibility-reader';
import {
  responsibilityEvidenceCoverage,
  responsibilityShadowLockKey,
  invokeResponsibilityMergeModel,
  assertResponsibilityVersionTarget,
} from '../lib/business-model-merge';
import { shouldDispatchResponsibilityShadowMerge } from '../trigger/document-ingestion';
import { scoreResponsibilityAnswerKey } from '../lib/responsibility-answer-key';
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

const bad = validateResponsibilityRead({
  output: {
    ...output,
    responsibilities: [
      { ...output.responsibilities[0]!, evidenceQuote: 'A paraphrase that is not in the source.' },
    ],
  },
  documentId,
  segment,
  chunks: [{ id: chunkId, documentId, rawText: 'Original text only.' }],
});
assert.equal(bad.elements.length, 0);
assert.equal(bad.diagnostics[0]?.failureClass, 'quote_mismatch');
assert.equal(bad.diagnostics[0]?.selectedPolicy, 'strict_verbatim');
assert.equal(bad.diagnostics[0]?.failureOrigin, 'root');
assert.ok(responsibilityRawAuditArtifact(output).sha256.length === 64);

const otherChunkId = '44444444-4444-4444-8444-444444444444';
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
assert.equal(RESPONSIBILITY_READ_PROMPT_VERSION, 'responsibility-read-v2.1-thin-source-faithful');
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
for (const requiredRequestRule of [
  'exact source-owner role label',
  'Split adjacent verbs and duties',
  'Split distinct destinations or systems',
  'target, system, destination, portal, server, form, deadline, cadence, and timing qualifier in object',
  'trigger may repeat but never replace them',
  'Do not leave a real target only in requiredSystem',
  'Do not invent duties not present in the source',
  'Prefer multiple thin records',
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
