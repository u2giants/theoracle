import type { SourceStructureMap, WorkflowReadOutput } from '@oracle/ai';
import {
  quoteValidationOptionsForSource,
  resolveSourceQuotePolicy,
  validateQuote,
} from '@oracle/engines';
import {
  buildActiveWorkflowMapRefIndex,
  validateMapElementRefMembership,
  type ActiveWorkflowMapContext,
} from '../lib/source-workflow-read';
import {
  listPrimaryMapRefs,
  modelCoverageGapId,
  reconcileMapPrimaryClaims,
} from '../lib/map-coverage';
import {
  SourceReaderBudget,
  SourceReaderBudgetExceededError,
  mapWithConcurrency,
} from '../lib/source-reader-budget';
import { validateWorkflowMap } from '../lib/workflow-map-validator';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

const documentId = '11111111-1111-4111-8111-111111111111';
const foreignDocumentId = '22222222-2222-4222-8222-222222222222';
const chunkA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const chunkB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const chunkUncovered = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';
const chunkForeign = 'dddddddd-dddd-4ddd-8ddd-dddddddddddd';
const mapId = 'eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee';

// Shared source-policy parity.
const markdown = validateQuote({
  sourceText: '**Sales** sends [the proof](https://example.test/proof).',
  exactQuoteProvided: 'Sales sends the proof.',
  ...quoteValidationOptionsForSource('native_text_document'),
});
assert(markdown.verdict === 'normalized_match', 'Markdown policy did not normalize formatting');

const pdf = validateQuote({
  sourceText: 'Sales  sends\n“the proof”.',
  exactQuoteProvided: 'Sales sends "the proof".',
  ...quoteValidationOptionsForSource('pdf_or_word_document'),
});
assert(pdf.verdict === 'normalized_match', 'PDF/OCR policy did not normalize layout artifacts');

const vision = validateQuote({
  sourceText: '[Sales: “Proof”] --> [Licensor: “Review”]',
  exactQuoteProvided: '[Sales: "Proof"] --> [Licensor: "Review"]',
  ...quoteValidationOptionsForSource('vision_transcription'),
});
assert(vision.verdict === 'failed', 'Vision-transcription policy was not strict');
assert(
  resolveSourceQuotePolicy('vision_transcription').name === 'vision_transcription_strict',
  'Vision policy is not named/auditable',
);

const transcript = validateQuote({
  sourceText: 'uh sales sends proof over after the kickoff meeting',
  exactQuoteProvided: 'Sales sends the proof after kickoff',
  ...quoteValidationOptionsForSource('transcript_message'),
});
assert(
  transcript.validationMethod === 'fuzzy_token_overlap' &&
    transcript.validatedExactQuote === 'uh sales sends proof over after the kickoff meeting',
  'Transcript fuzzy policy did not anchor accepted evidence to the real utterance',
);

const validOutput: WorkflowReadOutput = {
  mapKind: 'workflow',
  summary: 'Sales hands the proof to licensing after kickoff.',
  lanes: [{ laneId: 'sales', label: 'Sales' }],
  nodes: [
    {
      nodeId: 'sales_proof',
      label: 'Sales proof',
      nodeType: 'artifact',
      evidenceQuote: '**Sales** creates the proof.',
      chunkId: chunkA,
    },
    {
      nodeId: 'licensor_review',
      label: 'Licensor review',
      nodeType: 'approval_gate',
      evidenceQuote: 'Licensing sends the proof to the licensor.',
      chunkId: chunkB,
    },
  ],
  edges: [
    {
      edgeId: 'proof_to_review',
      fromNodeId: 'sales_proof',
      toNodeId: 'licensor_review',
      edgeType: 'handoff',
      evidenceQuote: 'Licensing sends the proof to the licensor.',
      chunkId: chunkB,
    },
  ],
  paths: [
    {
      pathId: 'main',
      name: 'Main',
      pathType: 'main',
      nodeIdsOrdered: ['sales_proof', 'licensor_review'],
    },
  ],
};

const chunks = new Map([
  [
    chunkA,
    {
      documentId,
      text: '**Sales** creates the proof.',
      coveredBySegmentation: true,
    },
  ],
  [
    chunkB,
    {
      documentId,
      text: 'Licensing sends the proof to the licensor.',
      coveredBySegmentation: true,
    },
  ],
  [chunkUncovered, { documentId, text: 'Uncovered text.', coveredBySegmentation: false }],
  [
    chunkForeign,
    { documentId: foreignDocumentId, text: 'Foreign text.', coveredBySegmentation: true },
  ],
]);

const crossSegment = validateWorkflowMap({
  output: validOutput,
  activeDocumentId: documentId,
  activeSegmentChunkIds: new Set([chunkA]),
  chunksById: chunks,
  sourceKind: 'native_text_document',
  maxDroppedRatio: 0.2,
  maxAuditChars: 10,
});
assert(crossSegment.droppedCount === 0, 'Covered same-document cross-segment citation was dropped');
assert(
  crossSegment.crossSegmentCitationCount === 2,
  'Cross-segment quality signal was not counted',
);
assert(
  typeof (crossSegment.validationJson.readerOutputAudit as { sha256?: string }).sha256 === 'string',
  'Reader-output audit artifact was not retained',
);
assert(
  (crossSegment.validationJson.readerOutputAudit as { truncated?: boolean; boundedJson?: string })
    .truncated === true &&
    (crossSegment.validationJson.readerOutputAudit as { boundedJson?: string }).boundedJson
      ?.length === 10,
  'Reader-output audit artifact was not bounded',
);

const alternatePolicy = validateWorkflowMap({
  output: {
    ...validOutput,
    nodes: [{ ...validOutput.nodes[0]!, evidenceQuote: 'Sales creates the proof.' }],
    edges: [],
    paths: [],
  },
  activeDocumentId: documentId,
  activeSegmentChunkIds: new Set([chunkA]),
  chunksById: chunks,
  sourceKind: 'strict_source',
  maxDroppedRatio: 0.2,
});
assert(
  alternatePolicy.diagnostics[0]?.passesAlternatePolicies.includes('markdown_document'),
  'Rejected quote diagnostic did not record the passing alternate Markdown policy',
);

const rootAndCascadeOutput: WorkflowReadOutput = {
  ...validOutput,
  nodes: [
    { ...validOutput.nodes[0]!, evidenceQuote: 'Hallucinated node quote.' },
    validOutput.nodes[1]!,
  ],
};
const rootAndCascade = validateWorkflowMap({
  output: rootAndCascadeOutput,
  activeDocumentId: documentId,
  activeSegmentChunkIds: new Set([chunkA, chunkB]),
  chunksById: chunks,
  sourceKind: 'native_text_document',
  maxDroppedRatio: 0.2,
});
assert(rootAndCascade.rootDroppedCount === 1, 'Root quote failure was not isolated');
assert(rootAndCascade.cascadeDroppedCount === 2, 'Edge/path endpoint cascades were not isolated');
assert(
  rootAndCascade.diagnostics.some(
    (diagnostic) =>
      diagnostic.failureClass === 'missing_endpoint_cascade' &&
      diagnostic.failureOrigin === 'cascade',
  ),
  'Relation endpoint cascade diagnostic missing',
);

for (const [chunkId, expected] of [
  [chunkForeign, 'foreign_document_citation'],
  [chunkUncovered, 'uncovered_document_citation'],
] as const) {
  const invalidCitation = validateWorkflowMap({
    output: {
      ...validOutput,
      nodes: [{ ...validOutput.nodes[0]!, chunkId, evidenceQuote: chunks.get(chunkId)!.text }],
      edges: [],
      paths: [],
    },
    activeDocumentId: documentId,
    activeSegmentChunkIds: new Set([chunkId]),
    chunksById: chunks,
    sourceKind: 'native_text_document',
    maxDroppedRatio: 0.2,
  });
  assert(
    invalidCitation.diagnostics[0]?.failureClass === expected,
    `${expected} citation was not rejected deterministically`,
  );
}

const structureMap: SourceStructureMap = {
  documentShape: 'process',
  summary: validOutput.summary,
  segments: [
    {
      segmentId: 'process',
      shape: 'process',
      title: 'Process',
      chunkIds: [chunkA, chunkB],
    },
  ],
  elements: validOutput.nodes.map((node) => ({
    elementId: node.nodeId,
    segmentId: 'process',
    shape: 'process',
    elementKind: node.nodeType,
    label: node.label,
    evidenceQuote: node.evidenceQuote,
    chunkId: node.chunkId,
  })),
  relations: validOutput.edges.map((edge) => ({
    relationId: edge.edgeId,
    segmentId: 'process',
    shape: 'process',
    fromElementId: edge.fromNodeId,
    toElementId: edge.toNodeId,
    relationKind: edge.edgeType,
    evidenceQuote: edge.evidenceQuote,
    chunkId: edge.chunkId,
  })),
  lanes: validOutput.lanes,
  paths: validOutput.paths,
};
const activeMap: ActiveWorkflowMapContext = {
  mapId,
  map: structureMap,
  guidance: 'test',
  refs: buildActiveWorkflowMapRefIndex(mapId, structureMap),
};
const validRelationRef = `${mapId}:relation:proof_to_review`;
assert(
  validateMapElementRefMembership({
    mapElementRef: validRelationRef,
    activeMap,
    eligibleChunkIds: new Set([chunkB]),
  }).ok,
  'Valid active-map ref was rejected',
);
const hallucinatedRef = validateMapElementRefMembership({
  mapElementRef: `${mapId}:relation:hallucinated_but_well_formed`,
  activeMap,
  eligibleChunkIds: new Set([chunkB]),
});
assert(
  !hallucinatedRef.ok && hallucinatedRef.failureClass === 'unknown_map_ref',
  'Hallucinated-but-well-formed map ref was accepted',
);
const outsideWindow = validateMapElementRefMembership({
  mapElementRef: validRelationRef,
  activeMap,
  eligibleChunkIds: new Set([chunkA]),
});
assert(
  !outsideWindow.ok && outsideWindow.failureClass === 'outside_extraction_window',
  'Map ref outside the extraction window was accepted',
);

const primaryRefs = listPrimaryMapRefs(mapId, structureMap);
assert(
  primaryRefs.length === 1 && primaryRefs[0]?.kind === 'relation',
  'Process coverage denominator drifted',
);
const reconciliationA = reconcileMapPrimaryClaims({
  mapId,
  map: structureMap,
  claimMapElementRefs: [],
});
const reconciliationB = reconcileMapPrimaryClaims({
  mapId,
  map: structureMap,
  claimMapElementRefs: [],
});
assert(
  JSON.stringify(reconciliationA) === JSON.stringify(reconciliationB) &&
    reconciliationA.omissions.length === 1,
  'Map-to-claim omission reconciliation is not deterministic',
);
const gapIdA = modelCoverageGapId({
  sourceType: 'document',
  sourceId: documentId,
  mapId,
  mapElementRef: validRelationRef,
});
const gapIdB = modelCoverageGapId({
  sourceType: 'document',
  sourceId: documentId,
  mapId,
  mapElementRef: validRelationRef,
});
assert(gapIdA === gapIdB, 'model_coverage gap identity is not idempotent');

const budget = new SourceReaderBudget({
  maxReadCalls: 1,
  maxInputTokens: 10,
  maxEstimatedCostUsd: 1,
  estimatedInputCostPerMillionTokensUsd: 1,
  maxRepairAttempts: 0,
  maxConcurrency: 1,
});
budget.reserveRead({ estimatedInputTokens: 10, label: 'bounded synthetic source' });
let budgetFailedLoud = false;
try {
  budget.reserveRead({ estimatedInputTokens: 1, label: 'over-budget synthetic source' });
} catch (error) {
  budgetFailedLoud =
    error instanceof SourceReaderBudgetExceededError && error.check === 'max_read_calls';
}
assert(budgetFailedLoud, 'Reader read-call budget did not fail loudly');

const concurrencyResult = await mapWithConcurrency({
  inputs: [1, 2, 3],
  concurrency: 2,
  run: async (value) => value * 2,
});
assert(concurrencyResult.join(',') === '2,4,6', 'Bounded reader concurrency lost stable ordering');

console.log('PASS R0 reader/validator contract');
