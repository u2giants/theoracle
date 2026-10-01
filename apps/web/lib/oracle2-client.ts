// Oracle 2 thin pilot client: shared state and helpers for the S03 journey.
// This is an in-process store for the pilot; S04+ replaces it with the Postgres
// authority-backed path already proven in the Python tests.

export interface SourceBlock {
  blockId: string;
  sourceId: string;
  blockIndex: number;
  text: string;
  spanStart: number;
  spanEnd: number;
}

export interface DraftConnection {
  from: number;
  to: number;
}

export interface Draft {
  draftId: string;
  sourceId: string;
  workspaceId: string;
  createdBy: string;
  processName: string;
  connections: DraftConnection[];
  status: 'draft' | 'confirmed' | 'withdrawn';
  updatedAt: string;
}

export interface Citation {
  sourceId: string;
  spanStart: number;
  spanEnd: number;
  quote: string;
}

export interface HypotheticalExperiment {
  label: string;
  description: string;
  measure: string;
  missingInputs: string[];
}

export interface PilotAnswer {
  answerText: string;
  citations: Citation[];
  hypothetical: HypotheticalExperiment | null;
  isEstablishedFact: boolean;
}

export interface Run {
  runId: string;
  workspaceId: string;
  actorId: string;
  sourceId: string;
  draftId: string | null;
  question: string;
  status: 'pending' | 'processing' | 'completed' | 'cancelled' | 'error';
  answer: PilotAnswer | null;
  error: string | null;
  createdAt: string;
}

export interface Review {
  reviewId: string;
  draftId: string;
  workspaceId: string;
  actorId: string;
  action: 'correct' | 'confirm' | 'reject';
  payload: Record<string, unknown>;
  createdAt: string;
}

// Singleton in-memory stores (pilot only; replaced in S04+).
const sources = new Map<string, { sourceId: string; workspaceId: string; filename: string; blocks: SourceBlock[]; status: string }>();
const drafts = new Map<string, Draft>();
const runs = new Map<string, Run>();
const reviews: Review[] = [];
/** Pilot authority grants: actorId → scopes (mirrors S02 has_authority for the thin UI). */
const authorityGrants = new Map<string, Set<string>>();

export function grantAuthority(actorId: string, scope: 'review' | 'confirm'): void {
  const scopes = authorityGrants.get(actorId) ?? new Set<string>();
  scopes.add(scope);
  authorityGrants.set(actorId, scopes);
}

export function revokeAuthority(actorId: string): void {
  authorityGrants.delete(actorId);
}

export function hasAuthority(actorId: string | undefined, scope: 'review' | 'confirm'): boolean {
  if (!actorId) return false;
  return authorityGrants.get(actorId)?.has(scope) ?? false;
}

export function storeSource(sourceId: string, workspaceId: string, filename: string, blocks: SourceBlock[]): void {
  sources.set(sourceId, { sourceId, workspaceId, filename, blocks, status: 'draft' });
}

export function getSource(sourceId: string) {
  return sources.get(sourceId) ?? null;
}

export function storeDraft(draft: Draft): void {
  drafts.set(draft.draftId, draft);
}

export function getDraft(draftId: string): Draft | null {
  return drafts.get(draftId) ?? null;
}

export function storeRun(run: Run): void {
  runs.set(run.runId, run);
}

export function getRun(runId: string): Run | null {
  return runs.get(runId) ?? null;
}

export function storeReview(review: Review): void {
  reviews.push(review);
}

export function getReviewsForDraft(draftId: string): Review[] {
  return reviews.filter((r) => r.draftId === draftId);
}

export function hasActiveConfirm(draftId: string): boolean {
  return reviews.some((r) => r.draftId === draftId && r.action === 'confirm');
}

export function parseTextToBlocks(text: string, sourceId: string): SourceBlock[] {
  // Process tables and numbered process steps are line-oriented; blank-line
  // paragraphs alone would collapse an entire table into one uncorrectable block.
  const lines = text.split('\n');
  const blocks: SourceBlock[] = [];
  let offset = 0;
  let current: string[] = [];
  let currentStart = 0;
  const flush = () => {
    const raw = current.join('\n');
    const stripped = raw.trim();
    if (stripped) {
      const start = text.indexOf(stripped, currentStart);
      const end = start + stripped.length;
      blocks.push({
        blockId: `${sourceId}-${blocks.length}`,
        sourceId,
        blockIndex: blocks.length,
        text: stripped,
        spanStart: start,
        spanEnd: end,
      });
    }
    current = [];
  };
  for (const line of lines) {
    const trimmed = line.trim();
    const isRow =
      line.includes('|') ||
      /^\s*(step\s+)?\d+\s*[.)|:\-]/i.test(trimmed) ||
      /^step[_ ]id/i.test(trimmed);
    if (current.length === 0) {
      currentStart = offset;
    }
    if (trimmed === '') {
      flush();
    } else if (isRow) {
      flush();
      currentStart = offset;
      current = [line];
    } else {
      current.push(line);
    }
    offset += line.length + 1;
  }
  flush();
  return blocks;
}

export function retrieveSpans(
  question: string,
  blocks: SourceBlock[],
  limit = 5,
  processConnections: DraftConnection[] = [],
): Array<{ block: SourceBlock; score: number }> {
  const stopWords = new Set(['the', 'a', 'an', 'is', 'are', 'can', 'where', 'how', 'what', 'when', 'does', 'do', 'in', 'on', 'to', 'of', 'for', 'and', 'or', 'be', 'will', 'would', 'could', 'should']);
  const questionWords = new Set(
    question
      .split(/\s+/)
      .map((w) => w.toLowerCase().replace(/[.,;:!?]/g, ''))
      .filter((w) => w && !stopWords.has(w)),
  );
  const connectedIndexes = new Set<number>();
  for (const connection of processConnections) {
    connectedIndexes.add(connection.from);
    connectedIndexes.add(connection.to);
  }
  const connectionBoost = connectedIndexes.size > 0 ? 0.15 : 0;
  const scored = blocks
    .map((block) => {
      const textLower = block.text.toLowerCase();
      let overlap = 0;
      for (const word of questionWords) {
        if (textLower.includes(word)) overlap++;
      }
      let score = overlap / Math.max(questionWords.size, 1);
      if (connectedIndexes.has(block.blockIndex)) score += connectionBoost;
      return { block, score };
    })
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score);
  return scored.slice(0, limit);
}

export function answerQuestion(
  question: string,
  spans: Array<{ block: SourceBlock; score: number }>,
  processConnections: DraftConnection[] = [],
  connectedBlocks: SourceBlock[] = [],
): PilotAnswer {
  if (spans.length === 0) {
    return {
      answerText: 'No source evidence was found for this question.',
      citations: [],
      hypothetical: null,
      isEstablishedFact: false,
    };
  }
  const citations: Citation[] = spans.map((s) => ({
    sourceId: s.block.sourceId,
    spanStart: s.block.spanStart,
    spanEnd: s.block.spanEnd,
    quote: s.block.text,
  }));
  for (const block of connectedBlocks) {
    if (!citations.some((c) => c.spanStart === block.spanStart && c.spanEnd === block.spanEnd)) {
      citations.push({
        sourceId: block.sourceId,
        spanStart: block.spanStart,
        spanEnd: block.spanEnd,
        quote: block.text,
      });
    }
  }
  const factLines = spans.slice(0, 3).map((s) => `According to the source: ${s.block.text}`);
  if (processConnections.length > 0) {
    const edges = processConnections.slice(0, 5).map((c) => `${c.from}→${c.to}`).join(', ');
    factLines.push(
      `Process-map connections in scope: ${edges}. The answer follows those corrected process links with the cited spans.`,
    );
    for (const block of connectedBlocks.slice(0, 4)) {
      factLines.push(`Connected process step (${block.blockIndex}): ${block.text}`);
    }
  }
  return {
    answerText: factLines.join('\n'),
    citations,
    hypothetical: {
      label: 'Hypothetical improvement experiment (not established fact)',
      description:
        'Consider testing whether consolidating sequential handoffs into a single checkpoint reduces cycle time.',
      measure: 'Measure cycle time before and after the change over two sprints.',
      missingInputs: ['current cycle-time baseline', 'team capacity data'],
    },
    isEstablishedFact: true,
  };
}
