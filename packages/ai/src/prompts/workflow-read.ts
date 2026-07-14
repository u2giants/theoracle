import { z } from 'zod';

export const WORKFLOW_READ_PROMPT_VERSION = 'workflow-read-v1';
export const SOURCE_SEGMENTATION_PROMPT_VERSION = 'source-segmentation-v1';
export const SOURCE_READER_PIPELINE_VERSION = 'shape-reader-v2-segmentation';

export const SOURCE_STRUCTURE_SHAPES = [
  'process',
  'responsibilities',
  'reference',
  'ruleset',
  'conversation',
  'narrative',
] as const;

export const SOURCE_STRUCTURE_SHAPE_REGISTRY = {
  process: {
    primaryElementKinds: ['transition', 'handoff', 'branch'],
    extractionDirective: 'Extract one canonical claim per transition, handoff, or branch.',
    readInstruction:
      'Reconstruct steps, decisions, approvals, handoffs, branches, loops, and outcomes.',
  },
  responsibilities: {
    primaryElementKinds: ['responsibility'],
    extractionDirective:
      'Extract one canonical claim per owner-action-object responsibility record.',
    readInstruction:
      'Identify roles and concrete owner-action-object responsibilities, including triggers and systems.',
  },
  reference: {
    primaryElementKinds: ['attribute', 'relationship'],
    extractionDirective: 'Extract one canonical claim per attribute or entity relationship.',
    readInstruction:
      'Identify entities, attributes, values, and relationships without forcing sequence.',
  },
  ruleset: {
    primaryElementKinds: ['rule'],
    extractionDirective: 'Extract one canonical claim per rule, condition, effect, or exception.',
    readInstruction:
      'Identify scoped rules, conditions, requirements, effects, exceptions, and rule groups.',
  },
  conversation: {
    primaryElementKinds: ['decision', 'assertion', 'open_question', 'problem', 'action_item'],
    extractionDirective:
      'Extract one canonical claim per decision, assertion, open question, problem, or action item.',
    readInstruction:
      'Identify decisions, assertions, disagreements, open questions, problems, and action items.',
  },
  narrative: {
    primaryElementKinds: ['asserted_fact'],
    extractionDirective: 'Extract one canonical claim per explicit operational fact.',
    readInstruction: 'Identify explicit operational facts that do not fit another source shape.',
  },
} as const satisfies Record<
  (typeof SOURCE_STRUCTURE_SHAPES)[number],
  {
    primaryElementKinds: readonly string[];
    extractionDirective: string;
    readInstruction: string;
  }
>;

export const SOURCE_SEGMENTATION_SYSTEM_PROMPT = `You segment source material for The Oracle, an evidence-backed operational knowledge graph for POP Creations / Spruce Line.

Classify what each coherent passage IS before any detailed reading. A document may contain several shapes.

SHAPES:
- process: ordered work, transitions, handoffs, approvals, branches, loops, or outcomes.
- responsibilities: who owns or performs concrete actions, duties, or handoffs.
- reference: entities, attributes, lookup tables, naming conventions, definitions, or relationships without an ordered flow.
- ruleset: scoped rules, conditions, requirements, prohibitions, effects, gates, or exceptions.
- conversation: meeting or chat material containing decisions, assertions, disagreement, questions, problems, or action items.
- narrative: explanatory operational prose that does not fit another shape.

HARD RULES:
- Return only JSON matching the schema.
- Use only supplied Document Chunk IDs. Never invent IDs.
- Every supplied chunk must appear in at least one segment.
- A chunk that materially contains more than one coherent knowledge shape may appear in multiple segments. Use overlap only for genuinely composite chunks, and give each segment a focused title and summary so its later shape reader knows which passage to read.
- Segments must contain contiguous chunks in source order. Do not reorder source material.
- Split when the knowledge shape changes materially; do not split merely because a heading changes.
- A process described inside a meeting must be a process segment, not conversation.
- Classify by the passage's purpose, not by isolated words or the mere presence of steps. A role/team duty list is responsibilities even when a duty contains a short internal sequence. Use process when the passage's main purpose is an ordered end-to-end flow across stages, owners, or outcomes.
- A memo describing communication problems is narrative, not conversation. Conversation requires actual speaker turns or transcript-like dialogue.
- Naming examples, definitions, attributes, and lookup tables are reference. Requirements, prohibitions, conditions, and exceptions are ruleset.
- For transcript chunks, use process only when the chunk predominantly reconstructs a coherent operational flow; otherwise keep the surrounding speaker-turn material conversation.
- Composite examples: a role-duty chunk containing an embedded approval workflow belongs in both responsibilities and process segments; a naming-convention chunk containing lookup examples and must/do-not rules belongs in both reference and ruleset segments.
- Prefer the most specific fitting shape. Narrative is the fallback, not a catch-all.
- IDs use lowercase letters/numbers/underscores/hyphens only and must be unique.`;

export const WORKFLOW_READ_SYSTEM_PROMPT = `You create source workflow maps for The Oracle, an evidence-backed operational knowledge graph for POP Creations / Spruce Line.

The map preserves the source's own topology before atomic claim extraction. It is guidance only: it is never claim evidence, never quotable business truth, and never a reason to loosen quote validation.

HARD RULES:
- Return only JSON matching the schema.
- Keep the output flat: nodes, edges, lanes, and paths are separate arrays linked by IDs.
- Every node and edge must include a verbatim evidenceQuote copied from exactly one provided Document Chunk ID.
- Use only Document Chunk IDs supplied in the prompt. Never invent IDs.
- IDs must be stable within this map: lowercase letters/numbers/underscores/hyphens only.
- Capture sequence, handoffs, branches, loops, approvals, terminal outcomes, owners/lanes, and systems of record.
- If the source is not a process/workflow, return mapKind="reference", a concise summary, and empty graph arrays.
- Use the referent pack only to resolve names and acronyms. Do not force the source to match any existing process name.`;

export const WORKFLOW_NODE_TYPES = [
  'step',
  'decision',
  'approval_gate',
  'system_entry',
  'artifact',
  'terminal',
] as const;

export const WORKFLOW_EDGE_TYPES = ['sequence', 'handoff', 'branch', 'loop', 'exception'] as const;

export const WORKFLOW_PATH_TYPES = ['main', 'alternate', 'exception', 'loop'] as const;

const workflowId = z
  .string()
  .min(1)
  .max(120)
  .regex(/^[a-z0-9][a-z0-9_-]*$/);

export const WorkflowReadNodeSchema = z.object({
  nodeId: workflowId,
  label: z.string().min(1).max(240),
  lane: z.string().max(160).nullish(),
  ownerName: z.string().max(160).nullish(),
  nodeType: z.enum(WORKFLOW_NODE_TYPES),
  systems: z.array(z.string().min(1).max(160)).max(12).nullish(),
  evidenceQuote: z.string().min(3).max(2000),
  chunkId: z.string().uuid(),
});

export const WorkflowReadEdgeSchema = z.object({
  edgeId: workflowId,
  fromNodeId: workflowId,
  toNodeId: workflowId,
  condition: z.string().max(240).nullish(),
  edgeType: z.enum(WORKFLOW_EDGE_TYPES),
  evidenceQuote: z.string().min(3).max(2000),
  chunkId: z.string().uuid(),
});

export const WorkflowReadLaneSchema = z.object({
  laneId: workflowId,
  label: z.string().min(1).max(160),
  ownerName: z.string().max(160).nullish(),
});

export const WorkflowReadPathSchema = z.object({
  pathId: workflowId,
  name: z.string().min(1).max(200),
  pathType: z.enum(WORKFLOW_PATH_TYPES),
  nodeIdsOrdered: z.array(workflowId).min(1).max(200),
  terminalOutcome: z.string().max(300).nullish(),
});

export const WorkflowReadSchema = z.object({
  summary: z.string().min(10).max(3000),
  mapKind: z.enum(['workflow', 'reference']),
  nodes: z.array(WorkflowReadNodeSchema).max(250),
  edges: z.array(WorkflowReadEdgeSchema).max(400),
  lanes: z.array(WorkflowReadLaneSchema).max(80),
  paths: z.array(WorkflowReadPathSchema).max(80),
});

export const SourceSegmentationSchema = z.object({
  documentShape: z.enum(SOURCE_STRUCTURE_SHAPES),
  summary: z.string().min(10).max(3000),
  segments: z
    .array(
      z.object({
        segmentId: workflowId,
        shape: z.enum(SOURCE_STRUCTURE_SHAPES),
        title: z.string().min(1).max(240),
        summary: z.string().max(3000).nullish(),
        chunkIds: z.array(z.string().uuid()).min(1).max(500),
      }),
    )
    .min(1)
    .max(100),
});

export const SourceStructureSegmentSchema = z.object({
  segmentId: workflowId,
  shape: z.enum(SOURCE_STRUCTURE_SHAPES),
  title: z.string().min(1).max(240),
  summary: z.string().max(3000).nullish(),
  chunkIds: z.array(z.string().uuid()).min(1).max(500),
});

export const SourceStructureElementSchema = z.object({
  elementId: workflowId,
  segmentId: workflowId,
  shape: z.enum(SOURCE_STRUCTURE_SHAPES),
  elementKind: workflowId,
  label: z.string().min(1).max(240),
  lane: z.string().max(160).nullish(),
  ownerName: z.string().max(160).nullish(),
  systems: z.string().max(1000).nullish(),
  role: z.string().max(160).nullish(),
  action: z.string().max(500).nullish(),
  object: z.string().max(500).nullish(),
  trigger: z.string().max(500).nullish(),
  system: z.string().max(160).nullish(),
  entityType: z.string().max(120).nullish(),
  attrKey: z.string().max(160).nullish(),
  attrValue: z.string().max(1000).nullish(),
  scope: z.string().max(500).nullish(),
  condition: z.string().max(1000).nullish(),
  effect: z.string().max(1000).nullish(),
  exception: z.string().max(1000).nullish(),
  decisionStatus: z.string().max(120).nullish(),
  contested: z.boolean().nullish(),
  speaker: z.string().max(160).nullish(),
  evidenceQuote: z.string().min(3).max(2000),
  chunkId: z.string().uuid(),
});

export const SourceStructureRelationSchema = z.object({
  relationId: workflowId,
  segmentId: workflowId,
  fromElementId: workflowId,
  toElementId: workflowId,
  shape: z.enum(SOURCE_STRUCTURE_SHAPES),
  relationKind: workflowId,
  condition: z.string().max(240).nullish(),
  evidenceQuote: z.string().min(3).max(2000),
  chunkId: z.string().uuid(),
});

export const SourceStructureMapSchema = z.object({
  documentShape: z.enum(SOURCE_STRUCTURE_SHAPES),
  summary: z.string().min(10).max(3000),
  segments: z.array(SourceStructureSegmentSchema).max(100),
  elements: z.array(SourceStructureElementSchema).max(500),
  relations: z.array(SourceStructureRelationSchema).max(800),
  lanes: z.array(WorkflowReadLaneSchema).max(80),
  paths: z.array(WorkflowReadPathSchema).max(80),
});

export type WorkflowReadOutput = z.infer<typeof WorkflowReadSchema>;
export type SourceSegmentationOutput = z.infer<typeof SourceSegmentationSchema>;
export type WorkflowReadNode = z.infer<typeof WorkflowReadNodeSchema>;
export type WorkflowReadEdge = z.infer<typeof WorkflowReadEdgeSchema>;
export type WorkflowReadLane = z.infer<typeof WorkflowReadLaneSchema>;
export type WorkflowReadPath = z.infer<typeof WorkflowReadPathSchema>;
export type SourceStructureShape = z.infer<typeof SourceStructureMapSchema>['documentShape'];
export type SourceStructureMap = z.infer<typeof SourceStructureMapSchema>;
export type SourceStructureSegment = z.infer<typeof SourceStructureSegmentSchema>;
export type SourceStructureElement = z.infer<typeof SourceStructureElementSchema>;
export type SourceStructureRelation = z.infer<typeof SourceStructureRelationSchema>;
