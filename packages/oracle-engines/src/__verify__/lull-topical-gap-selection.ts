import {
  decideLullInterjection,
  assertRealTopicalEmbeddings,
  gapEmbeddingNeedsRefresh,
  isGapEligibleForChannel,
  selectTopicalGap,
  type LullInterjectionInput,
  type TopicalGapCandidate,
} from '../interjection';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
  console.log(`✓ ${message}`);
}

// Small deterministic vectors stand in for network embeddings. The channel is
// discussing factory tooling. One eligible gap matches; one urgent gap is
// unrelated. A targeted gap for a non-participant has already been removed by
// the worker's assignment/participant filter and is intentionally absent here.
const recentFactoryMessages = [1, 0, 0];
assert(
  isGapEligibleForChannel('employee-in-room', ['employee-in-room']),
  'gap assigned to a participant remains eligible',
);
assert(
  !isGapEligibleForChannel('employee-elsewhere', ['employee-in-room']),
  'gap assigned outside the channel is filtered before scoring',
);
const eligibleOpenGaps: TopicalGapCandidate[] = [
  {
    id: 'urgent-unrelated-benefits',
    priority: 'urgent',
    questionToAsk: 'When does open enrollment close?',
    whyItMatters: 'Employees need benefit elections.',
    embedding: [0, 1, 0],
    createdAtMs: 3,
  },
  {
    id: 'high-matching-tooling',
    priority: 'high',
    questionToAsk: 'Which factory approves the tooling sample?',
    whyItMatters: 'The tooling handoff is blocked.',
    embedding: [0.92, 0.08, 0],
    createdAtMs: 2,
  },
];

const selected = selectTopicalGap(recentFactoryMessages, eligibleOpenGaps, 0.35);
assert(selected?.id === 'high-matching-tooling', 'matching gap wins over unrelated urgent gap');
assert((selected.relevanceScore ?? 0) >= 0.35, 'selected gap records its relevance score');

const unrelatedOnly = selectTopicalGap(
  recentFactoryMessages,
  [eligibleOpenGaps[0]!],
  0.35,
);
assert(unrelatedOnly === null, 'unrelated gaps below the threshold produce no question');

const crowded = Array.from({ length: 75 }, (_, index): TopicalGapCandidate => ({
  ...eligibleOpenGaps[0]!,
  id: `urgent-unrelated-${index}`,
  createdAtMs: 100 + index,
}));
crowded.push({
  ...eligibleOpenGaps[1]!,
  id: 'low-matching-after-seventy-five',
  priority: 'low',
});
assert(
  selectTopicalGap(recentFactoryMessages, crowded, 0.35)?.id ===
    'low-matching-after-seventy-five',
  'more than 50 unrelated urgent gaps cannot hide one topical lower-priority gap',
);

const equalScore = selectTopicalGap(
  recentFactoryMessages,
  [
    { ...eligibleOpenGaps[1]!, id: 'medium', priority: 'medium', embedding: [1, 0, 0] },
    { ...eligibleOpenGaps[1]!, id: 'urgent', priority: 'urgent', embedding: [1, 0, 0] },
  ],
  0.35,
);
assert(equalScore?.id === 'urgent', 'existing priority order breaks equal-relevance ties');

assert(
  gapEmbeddingNeedsRefresh({
    embedding: [1, 0, 0],
    embeddingModel: 'old-model',
    embeddingSourceHash: 'current-hash',
    requiredModel: 'current-model',
    requiredSourceHash: 'current-hash',
  }),
  'a changed embedding model forces refresh',
);
assert(
  gapEmbeddingNeedsRefresh({
    embedding: [1, 0, 0],
    embeddingModel: 'current-model',
    embeddingSourceHash: 'old-hash',
    requiredModel: 'current-model',
    requiredSourceHash: 'current-hash',
  }),
  'changed gap text forces refresh through its source hash',
);
let rejectedZeroStub = false;
try {
  assertRealTopicalEmbeddings({ fallback: true, model: 'zero-stub', vectors: [[0, 0, 0]] });
} catch {
  rejectedZeroStub = true;
}
assert(rejectedZeroStub, 'zero-stub embeddings fail closed');

const lullInput: LullInterjectionInput = {
  secondsSinceLastUserMessage: 120,
  lullWindowSeconds: 60,
  isAnyoneTyping: true,
  minutesSinceLastOracleInterjection: null,
  oracleCooldownMinutes: 10,
  interjectionsInLastHour: 0,
  maxOracleInterjectionsPerHour: 3,
  enableGroupChatLullQuestions: true,
  channelKind: 'group',
  topRelevantOpenGap: selected,
};
const typingDecision = decideLullInterjection(lullInput);
assert(
  typingDecision.decision === 'skip' && typingDecision.reasonCode === 'someone_typing',
  'live typing still prevents a topical question',
);

const workerSource = readFileSync(
  resolve(process.cwd(), '../../apps/workers/src/trigger/lull-interjection.ts'),
  'utf8',
);
const filterPosition = workerSource.indexOf('const eligible: Candidate[] = []');
const embeddingPosition = workerSource.indexOf('const recent = await embedMany');
assert(
  filterPosition >= 0 && embeddingPosition > filterPosition,
  'worker filters eligible gaps before any topical embedding request',
);
assert(
  workerSource.includes('.orderBy(gaps.id)') &&
    workerSource.includes('.limit(GAP_CANDIDATE_PAGE_SIZE)') &&
    !workerSource.includes('.limit(50)'),
  'worker scans all eligible gaps through bounded keyset pages',
);
const lockPosition = workerSource.indexOf('pg_try_advisory_xact_lock');
const finalTypingPosition = workerSource.indexOf('const liveTyping = await tx');
const claimPosition = workerSource.indexOf('// Claim the gap atomically');
assert(
  lockPosition >= 0 &&
    finalTypingPosition > lockPosition &&
    claimPosition > finalTypingPosition,
  'advisory lock and final typing check both precede the atomic gap claim',
);

console.log('Topical lull-gap fixture passed.');
