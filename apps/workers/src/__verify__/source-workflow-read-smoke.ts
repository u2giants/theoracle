import {
  __sourceWorkflowReadTestHooks,
  renderWorkflowMapGuidance,
} from '../lib/source-workflow-read';
import type { WorkflowReadOutput } from '@oracle/ai';

const { isReusableWorkflowMapStatus, prefixWindowIds, workflowToProcessStructureMap } =
  __sourceWorkflowReadTestHooks;

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
