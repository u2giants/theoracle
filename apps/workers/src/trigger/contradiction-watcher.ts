// PHASE 4 STUB — contradiction watcher (spec 9.3 + 5.1 Rule 1).
//
// Triggered on every new user message (Phase 4 wires a Supabase webhook or
// a poll on messages.extraction_status = 'pending').
//
// Workflow:
//   1. Embed the new message.
//   2. pgvector ANN against approved claims (top 8).
//   3. If any retrieved claim is semantically close but factually
//      contradictory (use a small LLM call with a strict yes/no JSON schema):
//      INSERT contradictions(status='possible', detection_confidence, ...)
//   4. Decide live interjection vs queued (default: queued unless very high
//      confidence + impact + settings.enable_live_contradiction_interjections).
//   5. Log oracle_interventions row if any action was taken.

import { task } from '@trigger.dev/sdk/v3';
import { z } from 'zod';

const PayloadSchema = z.object({ messageId: z.string().uuid() });

export const contradictionWatcherTask = task({
  id: 'contradiction-watcher',
  maxDuration: 60,
  run: async (payload: z.infer<typeof PayloadSchema>, { ctx }) => {
    PayloadSchema.parse(payload);
    return {
      ok: true,
      note: 'phase-4 stub — see comment block at top of file',
      messageId: payload.messageId,
      runId: ctx.run.id,
    };
  },
});
