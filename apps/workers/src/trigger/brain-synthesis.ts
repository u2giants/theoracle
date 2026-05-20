// PHASE 4 STUB — brain synthesis worker (spec 9.7, 9.8, 5.4).
//
// Workflow:
//   1. Pick a brain_sections row to synthesize (scheduled, or admin-triggered).
//   2. Retrieve approved claims via claim_domains.domain == section.knowledge_domain
//      OR claim_id IN (section_claims for this section).
//   3. Generate structured output (spec 9.8 schema — paragraphs[], supportingClaimIds,
//      updatedMarkdown, materialChanges[], claimsAdded[], etc.).
//   4. Validate (spec 9.8): every paragraph maps to approved claim IDs; no
//      unsupported names/systems/customers/stages/departments/process rules in
//      the markdown; new gaps include whyItMatters; contradictions point to real
//      claim IDs.
//   5. Two-step insert (spec 6.7):
//        a. INSERT brain_sections row (if new) with current_version_id = NULL.
//        b. INSERT brain_section_versions row.
//        c. UPDATE brain_sections.current_version_id = <new version>.
//   6. Emit gaps / contradictions / resolved gaps as side-effects.
//   7. Log model_runs and job_runs rows.

import { task } from '@trigger.dev/sdk/v3';
import { z } from 'zod';

const PayloadSchema = z.object({
  sectionId: z.string().min(1),
  trigger: z.enum(['scheduled', 'admin', 'new_claims']),
});

export const brainSynthesisTask = task({
  id: 'brain-synthesis',
  maxDuration: 60 * 10,
  run: async (payload: z.infer<typeof PayloadSchema>, { ctx }) => {
    PayloadSchema.parse(payload);
    return {
      ok: true,
      note: 'phase-4 stub — see comment block at top of file',
      sectionId: payload.sectionId,
      trigger: payload.trigger,
      runId: ctx.run.id,
    };
  },
});
