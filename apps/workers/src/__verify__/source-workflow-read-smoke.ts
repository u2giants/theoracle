import {
  __sourceWorkflowReadTestHooks,
  renderWorkflowMapGuidance,
} from '../lib/source-workflow-read';
import type { WorkflowReadOutput } from '@oracle/ai';

const {
  isReusableWorkflowMapStatus,
  prefixWindowIds,
  validateSegmentation,
  workflowToProcessStructureMap,
} = __sourceWorkflowReadTestHooks;

const segmentationChunks = [
  {
    id: '11111111-1111-4111-8111-111111111111',
    chunkIndex: 0,
    pageNumber: null,
    rawText: 'First',
    contentHash: 'one',
  },
  {
    id: '22222222-2222-4222-8222-222222222222',
    chunkIndex: 1,
    pageNumber: null,
    rawText: 'Second',
    contentHash: 'two',
  },
  {
    id: '33333333-3333-4333-8333-333333333333',
    chunkIndex: 2,
    pageNumber: null,
    rawText: 'Third',
    contentHash: 'three',
  },
  {
    id: '44444444-4444-4444-8444-444444444444',
    chunkIndex: 3,
    pageNumber: null,
    rawText: 'Fourth',
    contentHash: 'four',
  },
];

const validSegmentation = validateSegmentation(
  {
    documentShape: 'process',
    summary: 'A process followed by a responsibilities section.',
    segments: [
      {
        segmentId: 'process_part',
        shape: 'process',
        title: 'Process',
        chunkIds: segmentationChunks.slice(0, 2).map((chunk) => chunk.id),
      },
      {
        segmentId: 'owners',
        shape: 'responsibilities',
        title: 'Owners',
        chunkIds: segmentationChunks.slice(2).map((chunk) => chunk.id),
      },
    ],
  },
  segmentationChunks,
);

if (validSegmentation.status !== 'validated' || validSegmentation.segments.length !== 2) {
  throw new Error('valid segmentation was not preserved');
}

const repairedSegmentation = validateSegmentation(
  {
    documentShape: 'reference',
    summary: 'Malformed model output used to exercise deterministic repairs.',
    segments: [
      {
        segmentId: 'flow',
        shape: 'process',
        title: 'Flow',
        chunkIds: [segmentationChunks[0]!.id, segmentationChunks[2]!.id],
      },
      {
        segmentId: 'owners',
        shape: 'responsibilities',
        title: 'Owners',
        chunkIds: [
          segmentationChunks[0]!.id,
          segmentationChunks[1]!.id,
          '55555555-5555-4555-8555-555555555555',
        ],
      },
    ],
  },
  segmentationChunks,
);

if (repairedSegmentation.status !== 'degraded') {
  throw new Error('repaired segmentation should be degraded');
}

const repairedChunkIds = repairedSegmentation.segments.flatMap((segment) => segment.chunkIds);
if (new Set(repairedChunkIds).size !== segmentationChunks.length) {
  throw new Error('segmentation repair did not retain every source chunk at least once');
}

if (!repairedSegmentation.segments.some((segment) => segment.segmentId === 'unclassified_1')) {
  throw new Error('missing chunks were not retained in a visible narrative fallback segment');
}

for (const status of ['validated', 'degraded']) {
  if (!isReusableWorkflowMapStatus(status)) {
    throw new Error(`expected ${status} to be reusable`);
  }
}

for (const status of ['failed', 'pending', 'superseded', null, undefined]) {
  if (isReusableWorkflowMapStatus(status)) {
    throw new Error(`expected ${String(status)} not to be reusable`);
  }
}

const secondWindow: WorkflowReadOutput = {
  summary: 'Second window continues the process.',
  mapKind: 'workflow',
  lanes: [{ laneId: 'creative', label: 'Creative' }],
  nodes: [
    {
      nodeId: 'review',
      label: 'Review',
      lane: 'Creative',
      ownerName: 'Creative',
      nodeType: 'step',
      systems: [],
      evidenceQuote: 'Review',
      chunkId: '11111111-1111-4111-8111-111111111111',
    },
  ],
  edges: [
    {
      edgeId: 'handoff_to_review',
      fromNodeId: 'w1_intake',
      toNodeId: 'review',
      condition: 'After intake',
      edgeType: 'handoff',
      evidenceQuote: 'After intake, Review',
      chunkId: '11111111-1111-4111-8111-111111111111',
    },
  ],
  paths: [
    {
      pathId: 'main',
      name: 'Main',
      pathType: 'main',
      nodeIdsOrdered: ['w1_intake', 'review'],
    },
  ],
};

const prefixed = prefixWindowIds(secondWindow, 1, 2, new Set(['w1_intake']));

if (prefixed.edges[0]?.fromNodeId !== 'w1_intake') {
  throw new Error(`prior node endpoint was mangled: ${prefixed.edges[0]?.fromNodeId}`);
}

if (prefixed.edges[0]?.toNodeId !== 'w2_review') {
  throw new Error(`current-window endpoint was not prefixed: ${prefixed.edges[0]?.toNodeId}`);
}

if (prefixed.paths[0]?.nodeIdsOrdered.join(',') !== 'w1_intake,w2_review') {
  throw new Error(
    `path node IDs were not remapped correctly: ${prefixed.paths[0]?.nodeIdsOrdered.join(',')}`,
  );
}

const structureMap = workflowToProcessStructureMap({
  output: prefixed,
  title: 'Fixture',
  chunks: [
    {
      id: '11111111-1111-4111-8111-111111111111',
      chunkIndex: 0,
      pageNumber: null,
      rawText: 'After intake, Review',
      contentHash: 'hash',
    },
  ],
});

if (structureMap.documentShape !== 'process') {
  throw new Error(`expected process document shape, got ${structureMap.documentShape}`);
}

if (structureMap.segments.length !== 1 || structureMap.segments[0]?.chunkIds.length !== 1) {
  throw new Error('process map should have one segment over all chunks');
}

if (
  structureMap.elements[0]?.elementId !== 'w2_review' ||
  structureMap.relations[0]?.relationId !== 'w2_handoff_to_review'
) {
  throw new Error('process nodes/edges were not mapped into elements/relations');
}

const guidance = renderWorkflowMapGuidance('22222222-2222-4222-8222-222222222222', structureMap);
if (
  !guidance.includes('22222222-2222-4222-8222-222222222222:element:w2_review') ||
  !guidance.includes('22222222-2222-4222-8222-222222222222:relation:w2_handoff_to_review')
) {
  throw new Error(`unified map refs missing from guidance:\n${guidance}`);
}

console.log('PASS source workflow read smoke');
