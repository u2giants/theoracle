import { z } from 'zod';

export const COVERAGE_AUDIT_PROMPT_VERSION = 'coverage-audit-v1';

export const COVERAGE_AUDIT_SYSTEM_PROMPT = `You audit coverage for The Oracle.

Compare a provisional source outline against extracted atomic claims and macro relationships. Identify important outline elements that are missing, unresolved, or poorly represented.

RULES:
- Findings are review prompts, not operational truth.
- Do not assert a new business fact as true.
- Reference only supplied claim IDs and outline/source refs.
- Prefer actionable gaps: missing owner, missing branch, unresolved reference, missing stage, or macro-only source.`;

export const COVERAGE_FINDING_TYPES = [
  'missing_stage',
  'missing_owner',
  'missing_branch',
  'unresolved_reference',
  'unrepresented_exception',
  'low_claim_density',
  'macro_only_source',
  'conflict_without_contradiction',
] as const;

export const CoverageAuditOutputSchema = z.object({
  findings: z
    .array(
      z.object({
        findingType: z.enum(COVERAGE_FINDING_TYPES),
        summary: z.string().min(10).max(1000),
        sourceOutlineElementId: z.string().max(100).nullish(),
        relatedSourceRefs: z.array(z.string().max(150)).max(20).default([]),
        relatedClaimIds: z.array(z.string().uuid()).max(20).default([]),
        suggestedQuestion: z.string().max(1000).nullish(),
        severity: z.number().int().min(1).max(10).default(5),
        recommendedAction: z.enum(['create_gap', 'rerun_lens', 'manual_review', 'ignore']),
      }),
    )
    .max(20),
});

export type CoverageAuditOutput = z.infer<typeof CoverageAuditOutputSchema>;
