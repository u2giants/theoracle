import { __sourceWorkflowReadTestHooks } from '../lib/source-workflow-read';
import type { WorkflowReadOutput } from '@oracle/ai';

const { isReusableWorkflowMapStatus, prefixWindowIds } = __sourceWorkflowReadTestHooks;

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
  throw new Error(`path node IDs were not remapped correctly: ${prefixed.paths[0]?.nodeIdsOrdered.join(',')}`);
}

console.log('PASS source workflow read smoke');
