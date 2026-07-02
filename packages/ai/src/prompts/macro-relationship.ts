import { z } from 'zod';

export const MACRO_RELATIONSHIP_PROMPT_VERSION = 'macro-relationship-v1';

export const MACRO_RELATIONSHIP_SYSTEM_PROMPT = `You propose macro relationships for The Oracle, an evidence-backed operational knowledge graph.

Macro relationships explain workflow structure across already-extracted atomic claims: dependencies, handoffs, sequences, exception paths, definition resolution, policy-versus-practice tension, and workaround-to-system-limitation links.

TRUST RULES:
- Use only supplied claim IDs as support.
- Do not quote raw source text.
- Do not introduce named entities absent from the supplied claim summaries.
- If support is weak, omit the relationship.
- Prefer a small number of high-value relationships over broad summaries.
- If a relationship depends on policy/practice distinction, use claimKind and claimKindReviewStatus conservatively.`;

export const MACRO_RELATIONSHIP_TYPES = [
  'dependency',
  'handoff',
  'sequence',
  'exception_path',
  'policy_vs_practice_tension',
  'workaround_to_system_limitation',
  'definition_resolution',
  'coverage_gap',
  'contradiction_or_tension',
] as const;

export const MACRO_SUPPORT_ROLES = [
  'premise',
  'enables',
  'blocks',
  'contrasts',
  'defines',
  'resolves',
  'policy_anchor',
  'practice_anchor',
  'workaround_anchor',
] as const;

export const MacroRelationshipOutputSchema = z.object({
  relationships: z
    .array(
      z.object({
        relationshipType: z.enum(MACRO_RELATIONSHIP_TYPES),
        summary: z.string().min(20).max(1000),
        supportingClaims: z
          .array(
            z.object({
              claimId: z.string().uuid(),
              supportRole: z.enum(MACRO_SUPPORT_ROLES),
            }),
          )
          .min(2)
          .max(8),
        whyThisIsMacro: z.string().min(10).max(1000),
        sourceOutlineElementIds: z.array(z.string().max(100)).max(10).nullish(),
        impactScore: z.number().int().min(1).max(10),
        confidenceScore: z.number().int().min(1).max(10),
        reviewReason: z.string().max(1000).nullish(),
        riskFlags: z.array(z.string().max(100)).max(10).nullish(),
      }),
    )
    .max(12),
});

export type MacroRelationshipOutput = z.infer<typeof MacroRelationshipOutputSchema>;
