import { strict as assert } from 'node:assert';
import { computeCandidateHash } from '@oracle/engines';
import { formatConversationSegment, type FormattedMessage } from '@oracle/ai';
import {
  buildConversationWindows,
  contextBoundedConversationChars,
  ConversationMessageTooLargeError,
} from '../lib/conversation-windowing';
import { decideMessageExtractionStatus } from '../lib/message-extraction-status';

function message(index: number, content = `Operational fact ${index}: save the approved file.`): FormattedMessage {
  return {
    id: `message-${index}`,
    role: 'user',
    content,
    authorName: `Employee ${index % 3}`,
    createdAt: new Date(Date.UTC(2026, 6, 29, 12, index)),
  };
}

const messages = Array.from({ length: 80 }, (_, index) =>
  message(index, `Step ${index}: ${'document the handoff '.repeat(8)}`),
);
const smallestModelChars = contextBoundedConversationChars({
  configuredCharBudget: 4_000,
  contextLengths: [16_000, 8_000, 32_000],
  usableContextRatio: 0.7,
});
assert.equal(smallestModelChars, 4_000, 'configured cap stays below the model-derived cap');
assert.equal(
  contextBoundedConversationChars({
    configuredCharBudget: 24_000,
    contextLengths: [100_000, 8_000, 32_000],
    usableContextRatio: 0.7,
  }),
  16_800,
  'the smallest verified model context can be tighter than extraction_char_budget',
);

const carryIn = [message(-2, 'Earlier context A'), message(-1, 'Earlier context B')];
const windows = buildConversationWindows({
  segment: messages,
  carryIn,
  maxChars: smallestModelChars,
  overlapCount: 2,
});
assert.ok(windows.length > 1, 'oversized fixture must produce multiple windows');
for (const window of windows) {
  assert.ok(window.formattedCharCount <= smallestModelChars, 'every window stays within budget');
  assert.equal(
    window.formattedCharCount,
    formatConversationSegment(window.segment, { carryIn: window.carryIn }).length,
    'budget uses the exact formatted request text',
  );
  assert.match(
    formatConversationSegment(window.segment, { carryIn: window.carryIn }),
    /Do NOT extract claims from this context and do NOT quote these message IDs/,
    'carry-in is clearly non-quotable',
  );
}

const covered = new Set(windows.flatMap((window) => window.segment.map((item) => item.id)));
assert.deepEqual(
  [...covered].sort(),
  messages.map((item) => item.id).sort(),
  'no quotable message is lost',
);
for (const original of messages) {
  for (const repeated of windows.flatMap((window) => window.segment).filter((m) => m.id === original.id)) {
    assert.equal(repeated.createdAt.toISOString(), original.createdAt.toISOString(), 'timestamp preserved');
    assert.equal(repeated.id, original.id, 'evidence identity preserved');
  }
}

const overlapId = windows[0]!.segment.at(-1)!.id;
assert.ok(windows[1]!.segment.some((item) => item.id === overlapId), 'controlled active overlap exists');
const hashInput = {
  summary: 'Approved files must be saved.',
  topDomainIds: ['design_file_operations'],
  validatedQuotes: ['save the approved file'],
  sourcePointers: [`message:${overlapId}`],
};
const overlapCandidateHashes = [
  computeCandidateHash(hashInput),
  computeCandidateHash({ ...hashInput, topDomainIds: [...hashInput.topDomainIds] }),
];
assert.equal(
  new Set(overlapCandidateHashes).size,
  1,
  'the two window results collapse to one existing candidate identity',
);

assert.throws(
  () =>
    buildConversationWindows({
      segment: [message(999, 'x'.repeat(10_000))],
      maxChars: 1_000,
      overlapCount: 2,
    }),
  ConversationMessageTooLargeError,
  'one unfit message fails loudly instead of being truncated',
);

// Overlap owner terminal-state orderings. These arrays stand in for the
// extraction_batches rows visible to the shared DB reconciler.
assert.deepEqual(
  decideMessageExtractionStatus([
    { status: 'validation_complete' },
    { status: 'pending_model' },
  ]),
  { status: 'complete' },
  'success-first is sticky while the later owner is pending',
);
assert.deepEqual(
  decideMessageExtractionStatus([
    { status: 'validation_complete' },
    { status: 'failed', error: 'later failure' },
  ]),
  { status: 'complete' },
  'success-first cannot be demoted by a later failed owner',
);
assert.deepEqual(
  decideMessageExtractionStatus([
    { status: 'failed', error: 'first failure' },
    { status: 'pending_model' },
  ]),
  { status: 'processing' },
  'failure-first waits while another owner can still succeed',
);
assert.deepEqual(
  decideMessageExtractionStatus([
    { status: 'failed', error: 'first failure' },
    { status: 'validation_complete' },
  ]),
  { status: 'complete' },
  'failure-first becomes complete when the later owner succeeds',
);
assert.deepEqual(
  decideMessageExtractionStatus([
    { status: 'failed', error: 'first failure' },
    { status: 'failed', error: 'second failure' },
  ]),
  { status: 'failed', error: 'first failure; second failure' },
  'a multi-owner message fails only when every owner failed',
);
assert.throws(
  () =>
    contextBoundedConversationChars({
      configuredCharBudget: 4_000,
      contextLengths: [8_000, Number.NaN],
      usableContextRatio: 0.7,
    }),
  /verified positive context length/,
  'missing fallback-model context metadata fails loudly',
);

console.log(`conversation-windowing: ${windows.length} windows, ${covered.size} messages, all checks passed`);
