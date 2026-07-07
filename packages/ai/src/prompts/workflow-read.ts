import { z } from 'zod';

export const WORKFLOW_READ_PROMPT_VERSION = 'workflow-read-v1';

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

export const WORKFLOW_EDGE_TYPES = [
  'sequence',
  'handoff',
  'branch',
  'loop',
  'exception',
] as const;

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

export type WorkflowReadOutput = z.infer<typeof WorkflowReadSchema>;
export type WorkflowReadNode = z.infer<typeof WorkflowReadNodeSchema>;
export type WorkflowReadEdge = z.infer<typeof WorkflowReadEdgeSchema>;
export type WorkflowReadLane = z.infer<typeof WorkflowReadLaneSchema>;
export type WorkflowReadPath = z.infer<typeof WorkflowReadPathSchema>;
