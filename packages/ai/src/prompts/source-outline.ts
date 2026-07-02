import { z } from 'zod';

export const SOURCE_OUTLINE_PROMPT_VERSION = 'source-outline-v1';

export const SOURCE_OUTLINE_SYSTEM_PROMPT = `You create provisional macro outlines for The Oracle, an evidence-backed operational knowledge graph for POP Creations / Spruce Line.

The outline helps later extraction understand the whole source before extracting quote-backed atomic claims.

TRUST BOUNDARY:
- The outline is guidance only. It is not evidence and cannot create approved claims.
- Do not invent source IDs. Every referenced chunk ID must be one of the document chunk IDs in the prompt.
- Use uncertainty when the source is unclear.
- Prefer concrete process structure: stages, handoffs, dependencies, branches, exceptions, roles, systems, acronyms, aliases, and open questions.
- Recommend only a small number of extraction lenses that are likely to improve recall.`;

export const SOURCE_GROUP_TYPES = [
  'workflow_stage',
  'handoff',
  'exception_branch',
  'incident_thread',
  'entity_context',
  'open_question',
] as const;

export const SOURCE_REF_ROLES = [
  'defines_term',
  'stage_evidence',
  'handoff_evidence',
  'exception_evidence',
  'open_question_evidence',
] as const;

export const EXTRACTION_LENSES = [
  'handoffs',
  'exceptions_and_workarounds',
  'ownership_and_roles',
  'dependencies_and_sequence',
  'systems_and_data_entry',
  'definitions_and_acronyms',
  'customer_or_licensor_risk',
  'contradictions_and_tensions',
] as const;

export const SourceOutlineRefSchema = z.object({
  chunkId: z.string().uuid(),
  role: z.enum(SOURCE_REF_ROLES),
  note: z.string().max(500).nullish(),
});

export const SourceOutlineGroupSchema = z.object({
  elementId: z.string().min(1).max(100),
  groupType: z.enum(SOURCE_GROUP_TYPES),
  title: z.string().min(3).max(200),
  description: z.string().max(1000).nullish(),
  chunkIds: z.array(z.string().uuid()).min(1),
  sortOrder: z.number().int().min(0).max(1000).nullish(),
  recommendedLenses: z.array(z.enum(EXTRACTION_LENSES)).max(4).nullish(),
  uncertainty: z.string().max(500).nullish(),
});

export const SourceOutlineSchema = z.object({
  summary: z.string().min(20).max(2000),
  sourcePurpose: z.string().max(1000).nullish(),
  businessProcess: z.string().max(500).nullish(),
  entities: z
    .array(
      z.object({
        name: z.string().min(1).max(255),
        kind: z.string().min(1).max(100),
        chunkIds: z.array(z.string().uuid()).max(10).nullish(),
      }),
    )
    .max(50),
  terms: z
    .array(
      z.object({
        term: z.string().min(1).max(100),
        meaning: z.string().min(1).max(500),
        chunkIds: z.array(z.string().uuid()).max(10).nullish(),
      }),
    )
    .max(40),
  stages: z
    .array(
      z.object({
        name: z.string().min(1).max(200),
        description: z.string().max(1000).nullish(),
        chunkIds: z.array(z.string().uuid()).max(20).nullish(),
      }),
    )
    .max(40),
  groups: z.array(SourceOutlineGroupSchema).max(30),
  refs: z.array(SourceOutlineRefSchema).max(100),
  recommendedLenses: z.array(z.enum(EXTRACTION_LENSES)).max(6),
  openQuestions: z.array(z.string().min(5).max(500)).max(20),
  budget: z.object({
    recommendedLensCount: z.number().int().min(0).max(6),
    rationale: z.string().max(1000),
  }),
});

export type SourceOutlineOutput = z.infer<typeof SourceOutlineSchema>;
