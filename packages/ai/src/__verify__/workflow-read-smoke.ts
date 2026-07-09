import { ExtractionOutputSchema, SourceStructureMapSchema, WorkflowReadSchema } from '..';

const chunkId = '11111111-1111-4111-8111-111111111111';
const mapId = '22222222-2222-4222-8222-222222222222';

const workflow = WorkflowReadSchema.parse({
  summary: 'Licensed product development moves from buyer request through design approval.',
  mapKind: 'workflow',
  lanes: [{ laneId: 'sales', label: 'Sales', ownerName: 'Sales' }],
  nodes: [
    {
      nodeId: 'buyer_request',
      label: 'Buyer request',
      lane: 'Sales',
      ownerName: 'Sales',
      nodeType: 'step',
      systems: ['DFlow'],
      evidenceQuote: '[Sales: "Buyer Request"]',
      chunkId,
    },
    {
      nodeId: 'design_brief',
      label: 'Design brief',
      lane: 'Creative',
      ownerName: 'Creative Direction',
      nodeType: 'artifact',
      systems: [],
      evidenceQuote: '[Creative: "Design Brief"]',
      chunkId,
    },
  ],
  edges: [
    {
      edgeId: 'request_to_brief',
      fromNodeId: 'buyer_request',
      toNodeId: 'design_brief',
      condition: 'After kickoff',
      edgeType: 'handoff',
      evidenceQuote: '[Sales: "Buyer Request"] --(After kickoff)--> [Creative: "Design Brief"]',
      chunkId,
    },
  ],
  paths: [
    {
      pathId: 'main',
      name: 'Main path',
      pathType: 'main',
      nodeIdsOrdered: ['buyer_request', 'design_brief'],
    },
  ],
});

if (workflow.nodes.length !== 2 || workflow.edges.length !== 1) {
  throw new Error('workflow-read schema did not preserve flat graph records');
}

const structureMap = SourceStructureMapSchema.parse({
  documentShape: 'process',
  summary: workflow.summary,
  segments: [
    {
      segmentId: 'process',
      shape: 'process',
      title: 'Licensed product development',
      summary: workflow.summary,
      chunkIds: [chunkId],
    },
  ],
  elements: workflow.nodes.map((node) => ({
    elementId: node.nodeId,
    segmentId: 'process',
    shape: 'process',
    elementKind: node.nodeType,
    label: node.label,
    lane: node.lane,
    ownerName: node.ownerName,
    systems: node.systems?.join('; '),
    evidenceQuote: node.evidenceQuote,
    chunkId: node.chunkId,
  })),
  relations: workflow.edges.map((edge) => ({
    relationId: edge.edgeId,
    segmentId: 'process',
    fromElementId: edge.fromNodeId,
    toElementId: edge.toNodeId,
    shape: 'process',
    relationKind: edge.edgeType,
    condition: edge.condition,
    evidenceQuote: edge.evidenceQuote,
    chunkId: edge.chunkId,
  })),
  lanes: workflow.lanes,
  paths: workflow.paths,
});

if (structureMap.elements.length !== 2 || structureMap.relations.length !== 1) {
  throw new Error('source-structure schema did not preserve process records');
}

ExtractionOutputSchema.parse({
  claims: [
    {
      claimType: 'dependency',
      claimKind: 'policy',
      claimKindConfidence: 8,
      summary: 'The design brief follows the buyer request after kickoff.',
      impactScore: 6,
      confidenceScore: 8,
      domains: ['general', 'design'],
      evidence: {
        exactQuote: '[Sales: "Buyer Request"] --(After kickoff)--> [Creative: "Design Brief"]',
        sourceMessageId: chunkId,
        confidence: 9,
      },
      requiresReview: false,
      mapElementRef: `${mapId}:relation:request_to_brief`,
    },
  ],
});

const invalid = ExtractionOutputSchema.safeParse({
  claims: [
    {
      claimType: 'dependency',
      claimKind: 'policy',
      claimKindConfidence: 8,
      summary: 'The design brief follows the buyer request after kickoff.',
      impactScore: 6,
      confidenceScore: 8,
      domains: ['general'],
      evidence: {
        exactQuote: '[Sales: "Buyer Request"] --(After kickoff)--> [Creative: "Design Brief"]',
        sourceMessageId: chunkId,
        confidence: 9,
      },
      requiresReview: false,
      mapElementRef: 'edge:request_to_brief',
    },
  ],
});

if (invalid.success) {
  throw new Error('invalid mapElementRef was accepted');
}

const legacyRef = ExtractionOutputSchema.safeParse({
  claims: [
    {
      claimType: 'dependency',
      claimKind: 'policy',
      claimKindConfidence: 8,
      summary: 'The design brief follows the buyer request after kickoff.',
      impactScore: 6,
      confidenceScore: 8,
      domains: ['general'],
      evidence: {
        exactQuote: '[Sales: "Buyer Request"] --(After kickoff)--> [Creative: "Design Brief"]',
        sourceMessageId: chunkId,
        confidence: 9,
      },
      requiresReview: false,
      mapElementRef: `${mapId}:edge:request_to_brief`,
    },
  ],
});

if (legacyRef.success) {
  throw new Error('legacy node/edge mapElementRef was accepted');
}

console.log('PASS workflow-read smoke');
