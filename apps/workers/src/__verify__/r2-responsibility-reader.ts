import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import type { ResponsibilityReadOutput, SourceStructureSegment } from '@oracle/ai';
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
