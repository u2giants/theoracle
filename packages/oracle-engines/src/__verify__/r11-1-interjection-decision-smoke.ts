/**
 * R11.1 acceptance gate verification script.
 *
 * Run with: pnpm --filter @oracle/engines verify:r11.1
 *
 * Covers both pure decision functions exhaustively across every gate path.
 * The Trigger.dev tasks that compose these with DB I/O (R11.2 lull-
 * interjection, R11.3 contradiction live branch) are NOT exercised here —
 * the pure decision logic IS.
 *
 * For each function we cover:
 *   - Every reasonCode (skip / queue) — exactly one per gate.
 *   - The happy path (decision='ask' / 'live').
 *   - Boundary conditions: zero values, null cooldown, edge of confidence threshold.
 */

import {
  CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD,
  decideContradictionInterjection,
  decideLullInterjection,
  type ContradictionInterjectionInput,
  type LullInterjectionInput,
  type RelevantOpenGap,
} from '../interjection';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

// ─── Fixtures ──────────────────────────────────────────────────────────────

const SAMPLE_GAP: RelevantOpenGap = {
  id: 'gap-0001',
  priority: 'high',
  questionToAsk: 'What does Disney require before tooling for Mickey 100th?',
  whyItMatters: 'Tooling is blocked on licensor sign-off and the deadline is approaching.',
};

function lullBase(): LullInterjectionInput {
  return {
    secondsSinceLastUserMessage: 120,
    lullWindowSeconds: 60,
    isAnyoneTyping: false,
    minutesSinceLastOracleInterjection: 30,
    oracleCooldownMinutes: 10,
    interjectionsInLastHour: 1,
    maxOracleInterjectionsPerHour: 3,
    enableGroupChatLullQuestions: true,
    channelKind: 'group',
    topRelevantOpenGap: SAMPLE_GAP,
  };
}

function contradictionBase(): ContradictionInterjectionInput {
  return {
    detectionConfidence: 90,
    severity: 'high',
    enableLiveContradictionInterjections: true,
    minutesSinceLastOracleInterjection: 30,
    oracleCooldownMinutes: 10,
    interjectionsInLastHour: 1,
    maxOracleInterjectionsPerHour: 3,
    suggestedQuestion: 'You said factory A; the contract says factory B. Which one ships the holiday SKU?',
  };
}

// ═══════════════════════════════════════════════════════════════════════════
// decideLullInterjection — happy path
// ═══════════════════════════════════════════════════════════════════════════

console.log('\n── decideLullInterjection: happy path');
{
  const r = decideLullInterjection(lullBase());
  assert(r.decision === 'ask', 'L1 — all gates pass → ask');
  assert(r.decision === 'ask' && r.gapId === 'gap-0001', 'L1 — returns gap id');
  assert(r.decision === 'ask' && r.reason.includes('asking high-priority gap'), 'L1 — reason names the priority');
}

// ═══════════════════════════════════════════════════════════════════════════
// decideLullInterjection — each gate
// ═══════════════════════════════════════════════════════════════════════════

console.log('\n── decideLullInterjection: gate 1 (group lull disabled)');
{
  const r = decideLullInterjection({
    ...lullBase(),
    enableGroupChatLullQuestions: false,
    channelKind: 'group',
  });
  assert(r.decision === 'skip' && r.reasonCode === 'group_lull_disabled', 'L2 — group + setting off → skip group_lull_disabled');
}
{
  // DM bypasses the group-chat kill switch — even with the setting off, DMs proceed.
  const r = decideLullInterjection({
    ...lullBase(),
    enableGroupChatLullQuestions: false,
    channelKind: 'dm',
  });
  assert(r.decision === 'ask', 'L3 — DM ignores enable_group_chat_lull_questions');
}

console.log('\n── decideLullInterjection: gate 2 (lull window)');
{
  const r = decideLullInterjection({
    ...lullBase(),
    secondsSinceLastUserMessage: 30,
    lullWindowSeconds: 60,
  });
  assert(r.decision === 'skip' && r.reasonCode === 'lull_window_not_elapsed', 'L4 — 30s < 60s → skip lull_window_not_elapsed');
}
{
  // Exact boundary: 60s >= 60s passes
  const r = decideLullInterjection({
    ...lullBase(),
    secondsSinceLastUserMessage: 60,
    lullWindowSeconds: 60,
  });
  assert(r.decision === 'ask', 'L5 — boundary 60s == 60s → ask');
}

console.log('\n── decideLullInterjection: gate 3 (typing)');
{
  const r = decideLullInterjection({ ...lullBase(), isAnyoneTyping: true });
  assert(r.decision === 'skip' && r.reasonCode === 'someone_typing', 'L6 — typing → skip someone_typing');
}

console.log('\n── decideLullInterjection: gate 4 (cooldown)');
{
  const r = decideLullInterjection({
    ...lullBase(),
    minutesSinceLastOracleInterjection: 5,
    oracleCooldownMinutes: 10,
  });
  assert(r.decision === 'skip' && r.reasonCode === 'cooldown_active', 'L7 — 5min < 10min cooldown → skip cooldown_active');
}
{
  // Boundary: 10min == 10min passes (not strictly less than)
  const r = decideLullInterjection({
    ...lullBase(),
    minutesSinceLastOracleInterjection: 10,
    oracleCooldownMinutes: 10,
  });
  assert(r.decision === 'ask', 'L8 — boundary 10min == 10min cooldown → ask');
}
{
  // Never interjected before (null) is NOT in cooldown
  const r = decideLullInterjection({
    ...lullBase(),
    minutesSinceLastOracleInterjection: null,
  });
  assert(r.decision === 'ask', 'L9 — minutesSinceLastOracleInterjection=null → ask (never been quiet)');
}

console.log('\n── decideLullInterjection: gate 5 (rate cap)');
{
  const r = decideLullInterjection({
    ...lullBase(),
    interjectionsInLastHour: 3,
    maxOracleInterjectionsPerHour: 3,
  });
  assert(r.decision === 'skip' && r.reasonCode === 'rate_cap_reached', 'L10 — at cap → skip rate_cap_reached');
}
{
  // Over cap (defensive) — still skip
  const r = decideLullInterjection({
    ...lullBase(),
    interjectionsInLastHour: 4,
    maxOracleInterjectionsPerHour: 3,
  });
  assert(r.decision === 'skip' && r.reasonCode === 'rate_cap_reached', 'L11 — over cap → skip rate_cap_reached');
}
{
  // Just under cap passes
  const r = decideLullInterjection({
    ...lullBase(),
    interjectionsInLastHour: 2,
    maxOracleInterjectionsPerHour: 3,
  });
  assert(r.decision === 'ask', 'L12 — under cap (2/3) → ask');
}

console.log('\n── decideLullInterjection: gate 6 (no gap)');
{
  const r = decideLullInterjection({ ...lullBase(), topRelevantOpenGap: null });
  assert(r.decision === 'skip' && r.reasonCode === 'no_relevant_gap', 'L13 — no gap → skip no_relevant_gap');
}

console.log('\n── decideLullInterjection: gate ordering (first failed gate wins)');
{
  // Multiple gates fail simultaneously. Ordering: group_lull_disabled > lull_window > typing > cooldown > rate_cap > no_relevant_gap.
  const r = decideLullInterjection({
    ...lullBase(),
    channelKind: 'group',
    enableGroupChatLullQuestions: false,   // gate 1 fails
    secondsSinceLastUserMessage: 10,        // gate 2 would fail
    isAnyoneTyping: true,                   // gate 3 would fail
    minutesSinceLastOracleInterjection: 1,  // gate 4 would fail
    interjectionsInLastHour: 10,            // gate 5 would fail
    topRelevantOpenGap: null,               // gate 6 would fail
  });
  assert(r.decision === 'skip' && r.reasonCode === 'group_lull_disabled', 'L14 — gate 1 fires first when many fail');
}
{
  // Skip past gate 1 — gate 2 wins
  const r = decideLullInterjection({
    ...lullBase(),
    secondsSinceLastUserMessage: 10,
    isAnyoneTyping: true,
    topRelevantOpenGap: null,
  });
  assert(r.decision === 'skip' && r.reasonCode === 'lull_window_not_elapsed', 'L15 — gate 2 fires when 1 passes');
}

// ═══════════════════════════════════════════════════════════════════════════
// decideContradictionInterjection — happy path
// ═══════════════════════════════════════════════════════════════════════════

console.log('\n── decideContradictionInterjection: happy path');
{
  const r = decideContradictionInterjection(contradictionBase());
  assert(r.decision === 'live', 'C1 — all gates pass → live');
  assert(r.decision === 'live' && r.reason.includes('severity=high'), 'C1 — reason names severity');
}

// ═══════════════════════════════════════════════════════════════════════════
// decideContradictionInterjection — each gate
// ═══════════════════════════════════════════════════════════════════════════

console.log('\n── decideContradictionInterjection: gate 1 (setting off)');
{
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    enableLiveContradictionInterjections: false,
  });
  assert(r.decision === 'queue' && r.reasonCode === 'live_setting_off', 'C2 — setting off → queue live_setting_off');
}

console.log('\n── decideContradictionInterjection: gate 2 (severity)');
{
  const r = decideContradictionInterjection({ ...contradictionBase(), severity: 'low' });
  assert(r.decision === 'queue' && r.reasonCode === 'severity_too_low', 'C3 — severity=low → queue severity_too_low');
}
{
  const r = decideContradictionInterjection({ ...contradictionBase(), severity: 'medium' });
  assert(r.decision === 'queue' && r.reasonCode === 'severity_too_low', 'C4 — severity=medium → queue severity_too_low');
}

console.log('\n── decideContradictionInterjection: gate 3 (confidence)');
{
  // Just under threshold
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    detectionConfidence: CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD - 1,
  });
  assert(r.decision === 'queue' && r.reasonCode === 'confidence_too_low', 'C5 — confidence=79 < 80 → queue confidence_too_low');
}
{
  // Exact threshold passes
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    detectionConfidence: CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD,
  });
  assert(r.decision === 'live', 'C6 — boundary confidence=80 == 80 → live');
}
{
  // Way over threshold passes
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    detectionConfidence: 100,
  });
  assert(r.decision === 'live', 'C7 — confidence=100 → live');
}

console.log('\n── decideContradictionInterjection: gate 4 (cooldown)');
{
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    minutesSinceLastOracleInterjection: 3,
    oracleCooldownMinutes: 10,
  });
  assert(r.decision === 'queue' && r.reasonCode === 'cooldown_active', 'C8 — cooldown not elapsed → queue cooldown_active');
}
{
  // Never interjected before (null) is NOT in cooldown
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    minutesSinceLastOracleInterjection: null,
  });
  assert(r.decision === 'live', 'C9 — minutesSinceLastOracleInterjection=null → live');
}

console.log('\n── decideContradictionInterjection: gate 5 (rate cap)');
{
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    interjectionsInLastHour: 3,
    maxOracleInterjectionsPerHour: 3,
  });
  assert(r.decision === 'queue' && r.reasonCode === 'rate_cap_reached', 'C10 — at cap → queue rate_cap_reached');
}

console.log('\n── decideContradictionInterjection: gate 6 (no question)');
{
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    suggestedQuestion: null,
  });
  assert(r.decision === 'queue' && r.reasonCode === 'no_suggested_question', 'C11 — null question → queue no_suggested_question');
}
{
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    suggestedQuestion: '   ',
  });
  assert(r.decision === 'queue' && r.reasonCode === 'no_suggested_question', 'C12 — whitespace-only question → queue no_suggested_question');
}

console.log('\n── decideContradictionInterjection: gate ordering');
{
  // Multiple gates fail. Order: live_setting_off > severity_too_low > confidence_too_low > cooldown_active > rate_cap_reached > no_suggested_question
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    enableLiveContradictionInterjections: false, // gate 1 fails
    severity: 'low',                               // gate 2 would fail
    detectionConfidence: 10,                       // gate 3 would fail
    minutesSinceLastOracleInterjection: 1,         // gate 4 would fail
    interjectionsInLastHour: 99,                   // gate 5 would fail
    suggestedQuestion: null,                       // gate 6 would fail
  });
  assert(r.decision === 'queue' && r.reasonCode === 'live_setting_off', 'C13 — gate 1 fires first when many fail');
}
{
  const r = decideContradictionInterjection({
    ...contradictionBase(),
    severity: 'low',
    detectionConfidence: 10,
    suggestedQuestion: null,
  });
  assert(r.decision === 'queue' && r.reasonCode === 'severity_too_low', 'C14 — gate 2 fires when 1 passes');
}

console.log('\nAll R11.1 interjection-decision smoke assertions passed.');
