// PHASE 4 STUB — claim extraction worker.
//
// Workflow (spec 9.4):
//
//   1. Query messages where extractionStatus = 'pending' AND role = 'user'.
//   2. Group messages by channel / employee / conversation segment.
//   3. Call OpenRouter with the extraction model (settings.default_extraction_model
//      = 'google/gemini-flash') and a structured-output schema (Zod via AI SDK
//      generateObject) to extract operational claims.
//   4. Validate every exact quote against the original message content.
//   5. Insert claims, claim_domains, claim_evidence (source_type='message',
//      source_message_id=<msg.id>, asserted_by_employee_id=<msg.employee_id>).
//   6. Update messages.extraction_status to 'complete' | 'failed' | 'skipped'.
//   7. Triage:
//        - Auto-approve if: exact quote validates, claim_type low-risk, no
//          contradiction, impact <= 6 → claims.status = 'approved'
//        - Pending review if: impact >= 7, contradiction detected, claim affects
//          future PM-system requirements, claim names a person as bottleneck,
//          claim implies customer/licensor risk, OCR confidence low →
//          claims.status = 'pending_review'
//   8. Log a model_runs row with input/output tokens, cost, latency.
//   9. Log a job_runs row tying the Trigger.dev runId to the work done.
//
// Group chat semantics (spec 9.5) — distinguish:
//   - Claim stated
//   - Claim confirmed
//   - Claim challenged
//   - Claim refined
//   - Exception introduced
//   - Process ambiguity revealed
//
// This file is a TODO. The shape below is what Phase 4 will fill in.

import { schedules } from '@trigger.dev/sdk/v3';

export const claimExtractionTask = schedules.task({
  id: 'claim-extraction',
  // Spec 9.4: "Cron schedule, for example every 4 hours or nightly"
  cron: '0 */4 * * *',
  maxDuration: 60 * 5,
  run: async (_payload, { ctx }) => {
    // TODO Phase 4:
    //   const db = getDirectDb();
    //   const pending = await db.select().from(messages).where(...).limit(100);
    //   for (const group of groupByConversationSegment(pending)) {
    //     const extracted = await generateObject({ model, schema, ... });
    //     await validateExactQuotes(extracted, group);
    //     await persistClaimsAndEvidence(extracted, group);
    //   }
    return {
      ok: true,
      note: 'phase-4 stub — see comment block at top of file',
      runId: ctx.run.id,
    };
  },
});
