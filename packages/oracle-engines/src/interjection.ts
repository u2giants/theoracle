// PHASE 6 STUB — controlled interjection engine (spec 5.1).
//
// =============================================================================
// SPEC RULES (verbatim summary from Part 5.1)
// =============================================================================
//
// Rule 1 — Contradiction Watcher
//   * On new user message, run cheap vector retrieval against approved claims.
//   * If related claims seem misaligned, create contradictions(status='possible').
//   * Only interject LIVE if confidence and operational impact are very high.
//   * Otherwise queue silently for later synthesis or follow-up.
//
// Rule 2 — Lull in Conversation
//   * Only ask a high-priority gap question when:
//       - No human has spoken for `lull_window_seconds` (settings)
//       - No one is currently typing
//       - The room has not received an Oracle interjection recently
//         (within `oracle_cooldown_minutes`)
//       - There is a high-priority gap that is relevant to the recent topic
//   * Respect `max_oracle_interjections_per_hour` per channel.
//
// All proactive interjections must be logged in oracle_interventions with:
//   trigger_type, related_gap_id / related_contradiction_id / related_message_id,
//   was_live_interjection, confidence, impact_score, reason.
//
// =============================================================================
// IMPLEMENTATION NOTES (when Phase 6 fills this in)
// =============================================================================
//
// shouldInterjectOnLull(channelId): consult settings, message timestamps,
//   presence (Realtime), recent oracle_interventions, then pick the highest-
//   priority open gap relevant to the recent topic via embedding similarity.
//
// shouldInterjectOnContradiction(contradictionId): require detection_confidence
//   above threshold AND severity at least 'high' AND settings.enable_live_contradiction_interjections.
//
// recordIntervention(...): wrap the INSERT into oracle_interventions.

export {};
