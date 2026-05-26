/**
 * R11.1 — Proactive interjection decision logic (pure).
 *
 * Two decisions per spec Part 5.1:
 *
 *   1. decideLullInterjection — when the conversation has gone quiet, should
 *      the Oracle pop a high-priority open gap as a question?
 *
 *   2. decideContradictionInterjection — when the contradiction-watcher finds
 *      a real semantic clash between two approved claims, should the Oracle
 *      surface it LIVE in chat, or file it silently for synthesis to digest?
 *
 * Both are pure functions: in → out, no DB, no I/O. The Trigger.dev tasks
 * (R11.2 lull-interjection, R11.3 contradiction-watcher live branch) pass
 * pre-fetched data in; the functions just decide. Smoke gate at
 * `packages/oracle-engines/src/__verify__/r11-1-interjection-decision-smoke.ts`
 * exercises every gate path without spinning up a database.
 *
 * Decision rationale (all calls) is returned as a `reason` string so admin
 * dashboards and `oracle_interventions` audit rows can show exactly why a
 * given interjection did or didn't happen.
 *
 * Per spec Part 5.1 and `docs/oracle/05-ai-retrofit-phase-packet.md` "Phase R11".
 */

// ─── Lull interjection ─────────────────────────────────────────────────────

export type ChannelKind = 'dm' | 'group';

export interface RelevantOpenGap {
  /** `gaps.id` */
  id: string;
  /** `gaps.priority` — `low | medium | high | urgent` per the priority enum. */
  priority: 'low' | 'medium' | 'high' | 'urgent';
  /** `gaps.question_to_ask` — what we'd actually ask the room. */
  questionToAsk: string;
  /** `gaps.why_it_matters` — context for the asker that draft prompts can lean on. */
  whyItMatters: string;
}

export interface LullInterjectionInput {
  /** Time since the last NON-Oracle (`role='user'`) message in the channel. */
  secondsSinceLastUserMessage: number;
  /** `settings.lull_window_seconds` — minimum silence before considering an interjection. */
  lullWindowSeconds: number;
  /** Realtime presence — is anyone currently typing? Skip if so. */
  isAnyoneTyping: boolean;
  /** Time since the most recent oracle_intervention in this channel, or null if none ever. */
  minutesSinceLastOracleInterjection: number | null;
  /** `settings.oracle_cooldown_minutes` — minimum gap between interjections in one channel. */
  oracleCooldownMinutes: number;
  /** Count of oracle_interventions in this channel in the last 60 minutes. */
  interjectionsInLastHour: number;
  /** `settings.max_oracle_interjections_per_hour` — hard cap per channel per hour. */
  maxOracleInterjectionsPerHour: number;
  /** `settings.enable_group_chat_lull_questions` — global kill switch for group chats. */
  enableGroupChatLullQuestions: boolean;
  /** DMs always allow lull questions; group chats require the setting above. */
  channelKind: ChannelKind;
  /**
   * Highest-priority open gap topically relevant to the recent conversation.
   * Null = no relevant gap available, skip.
   */
  topRelevantOpenGap: RelevantOpenGap | null;
}

export type LullInterjectionDecision =
  | {
      decision: 'ask';
      gapId: string;
      reason: string;
    }
  | {
      decision: 'skip';
      reason: string;
      /** Stable code for dashboard grouping. */
      reasonCode:
        | 'group_lull_disabled'
        | 'lull_window_not_elapsed'
        | 'someone_typing'
        | 'cooldown_active'
        | 'rate_cap_reached'
        | 'no_relevant_gap';
    };

/**
 * Decide whether the Oracle should ask a lull question right now.
 *
 * Gates evaluate in this order — first failed gate wins, no further checks:
 *   1. Group-chat lull disabled (setting off + channel is group) → skip
 *   2. Not enough silence yet → skip
 *   3. Someone is typing → skip
 *   4. Cooldown not elapsed → skip
 *   5. Per-channel hourly rate cap reached → skip
 *   6. No relevant open gap to ask about → skip
 *   7. All gates pass → ask
 */
export function decideLullInterjection(
  input: LullInterjectionInput,
): LullInterjectionDecision {
  // 1. Group-chat kill switch
  if (input.channelKind === 'group' && !input.enableGroupChatLullQuestions) {
    return {
      decision: 'skip',
      reason: 'enable_group_chat_lull_questions=false; Oracle stays quiet in group chats.',
      reasonCode: 'group_lull_disabled',
    };
  }

  // 2. Lull window
  if (input.secondsSinceLastUserMessage < input.lullWindowSeconds) {
    return {
      decision: 'skip',
      reason: `Conversation has been quiet for only ${input.secondsSinceLastUserMessage}s; lull window is ${input.lullWindowSeconds}s.`,
      reasonCode: 'lull_window_not_elapsed',
    };
  }

  // 3. Presence — don't interrupt typing
  if (input.isAnyoneTyping) {
    return {
      decision: 'skip',
      reason: 'Someone is currently typing; Oracle does not interrupt.',
      reasonCode: 'someone_typing',
    };
  }

  // 4. Cooldown — minutesSinceLastOracleInterjection=null means "never" => not in cooldown
  if (
    input.minutesSinceLastOracleInterjection != null &&
    input.minutesSinceLastOracleInterjection < input.oracleCooldownMinutes
  ) {
    return {
      decision: 'skip',
      reason: `Last Oracle interjection was ${input.minutesSinceLastOracleInterjection}min ago; cooldown is ${input.oracleCooldownMinutes}min.`,
      reasonCode: 'cooldown_active',
    };
  }

  // 5. Per-hour rate cap
  if (input.interjectionsInLastHour >= input.maxOracleInterjectionsPerHour) {
    return {
      decision: 'skip',
      reason: `Channel has already received ${input.interjectionsInLastHour} Oracle interjection(s) this hour; cap is ${input.maxOracleInterjectionsPerHour}.`,
      reasonCode: 'rate_cap_reached',
    };
  }

  // 6. Relevant open gap available?
  if (!input.topRelevantOpenGap) {
    return {
      decision: 'skip',
      reason: 'No open gap topically relevant to recent conversation; nothing to ask.',
      reasonCode: 'no_relevant_gap',
    };
  }

  // 7. All gates pass
  return {
    decision: 'ask',
    gapId: input.topRelevantOpenGap.id,
    reason: `Lull window elapsed (${input.secondsSinceLastUserMessage}s ≥ ${input.lullWindowSeconds}s), cooldown clear, ${input.interjectionsInLastHour}/${input.maxOracleInterjectionsPerHour} interjections this hour, asking ${input.topRelevantOpenGap.priority}-priority gap ${input.topRelevantOpenGap.id}.`,
  };
}

// ─── Contradiction interjection ─────────────────────────────────────────────

export type ContradictionSeverity = 'low' | 'medium' | 'high';

/**
 * Confidence threshold for live interjection. Below this, even a `high`-
 * severity contradiction stays queued. The contradiction-watcher's
 * adjudication LLM reports a 0-100 confidence; 80 is the spec default per
 * the legacy worker. Adjustable per future eval.
 */
export const CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD = 80 as const;

export interface ContradictionInterjectionInput {
  /** 0-100. LLM-reported `detectionConfidence` from the adjudication call. */
  detectionConfidence: number;
  /** `contradictions.severity`. */
  severity: ContradictionSeverity;
  /** `settings.enable_live_contradiction_interjections` — global kill switch. */
  enableLiveContradictionInterjections: boolean;
  /** Time since the most recent oracle_intervention in the channel this contradiction relates to. */
  minutesSinceLastOracleInterjection: number | null;
  /** `settings.oracle_cooldown_minutes`. */
  oracleCooldownMinutes: number;
  /** Count of oracle_interventions in the channel in the last 60 minutes. */
  interjectionsInLastHour: number;
  /** `settings.max_oracle_interjections_per_hour`. */
  maxOracleInterjectionsPerHour: number;
  /** Model-suggested question that would surface the contradiction in chat. Null = nothing to post live. */
  suggestedQuestion: string | null;
}

export type ContradictionInterjectionDecision =
  | {
      decision: 'live';
      reason: string;
    }
  | {
      decision: 'queue';
      reason: string;
      /** Stable code for dashboard grouping. */
      reasonCode:
        | 'live_setting_off'
        | 'severity_too_low'
        | 'confidence_too_low'
        | 'cooldown_active'
        | 'rate_cap_reached'
        | 'no_suggested_question';
    };

/**
 * Decide whether a freshly-detected contradiction should be surfaced LIVE in
 * chat or filed silently for later synthesis.
 *
 * Per spec Part 5.1 "Rule 1": most contradictions should NOT cause live
 * interjections. Live is reserved for high-severity + high-confidence cases
 * where the operational impact is real and admin tolerance is high.
 *
 * Gates evaluate in this order — first failed gate wins:
 *   1. Live-interjection setting off → queue
 *   2. Severity below 'high' → queue
 *   3. Confidence below threshold → queue
 *   4. Cooldown not elapsed in the channel → queue
 *   5. Per-channel hourly rate cap reached → queue
 *   6. No model-suggested question to post → queue
 *   7. All gates pass → live
 */
export function decideContradictionInterjection(
  input: ContradictionInterjectionInput,
): ContradictionInterjectionDecision {
  // 1. Setting kill switch
  if (!input.enableLiveContradictionInterjections) {
    return {
      decision: 'queue',
      reason: 'enable_live_contradiction_interjections=false; filing silently for synthesis.',
      reasonCode: 'live_setting_off',
    };
  }

  // 2. Severity threshold (only 'high' is eligible per spec 5.1)
  if (input.severity !== 'high') {
    return {
      decision: 'queue',
      reason: `Severity=${input.severity}; live interjection requires severity=high.`,
      reasonCode: 'severity_too_low',
    };
  }

  // 3. Confidence threshold
  if (input.detectionConfidence < CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD) {
    return {
      decision: 'queue',
      reason: `detectionConfidence=${input.detectionConfidence} below threshold ${CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD}.`,
      reasonCode: 'confidence_too_low',
    };
  }

  // 4. Cooldown
  if (
    input.minutesSinceLastOracleInterjection != null &&
    input.minutesSinceLastOracleInterjection < input.oracleCooldownMinutes
  ) {
    return {
      decision: 'queue',
      reason: `Last Oracle interjection was ${input.minutesSinceLastOracleInterjection}min ago; cooldown is ${input.oracleCooldownMinutes}min.`,
      reasonCode: 'cooldown_active',
    };
  }

  // 5. Per-hour rate cap
  if (input.interjectionsInLastHour >= input.maxOracleInterjectionsPerHour) {
    return {
      decision: 'queue',
      reason: `Channel has already received ${input.interjectionsInLastHour} Oracle interjection(s) this hour; cap is ${input.maxOracleInterjectionsPerHour}.`,
      reasonCode: 'rate_cap_reached',
    };
  }

  // 6. Need a draftable question
  if (!input.suggestedQuestion || input.suggestedQuestion.trim() === '') {
    return {
      decision: 'queue',
      reason: 'Adjudicator did not return a suggested question; cannot draft live message.',
      reasonCode: 'no_suggested_question',
    };
  }

  // 7. All gates pass
  return {
    decision: 'live',
    reason: `severity=high, confidence=${input.detectionConfidence}≥${CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD}, cooldown clear, ${input.interjectionsInLastHour}/${input.maxOracleInterjectionsPerHour} this hour — posting live.`,
  };
}
