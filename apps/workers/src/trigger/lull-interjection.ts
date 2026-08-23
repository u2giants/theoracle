// R11.2 — Event-driven lull-interjection task.
//
// Per spec Part 5.1 Rule 2 + docs/oracle/05-ai-retrofit-phase-packet.md
// "Phase R11" + HANDOFF.md R11.2.
//
// Sixty seconds after the latest user message in one channel:
//   0. Verify the triggering message is still that channel's latest user
//      message. A newer message makes this delayed run a no-op.
//   1. Compute the inputs to decideLullInterjection (R11.1, pure):
//        - secondsSinceLastUserMessage
//        - minutesSinceLastOracleInterjection
//        - interjectionsInLastHour
//        - top relevant open gap for any channel participant
//   2. Call decideLullInterjection.
//   3. If decision = 'ask':
//        - Draft a natural question via OracleAIClient.runText on the
//          INTERVIEW route (Anthropic Claude Haiku 4.5) so the wording is
//          warm and chat-shaped, not extraction-style.
//        - Insert assistant message into `messages`.
//        - Insert `oracle_interventions` row with was_live_interjection=true,
//          interjection_message_id = the new assistant message id.
//        - Update gap: status='asked', askedInMessageId = the new message.
//
// Per HANDOFF.md the live-message-posting decision is intentional — no
// dry-run gating. Admin reviews via /admin/ai and oracle_interventions.
//
// Typing presence is live through short-lived `typing_indicators` heartbeats.
// Round 1 deferred presence because no durable heartbeat path existed yet.
//
// Gap candidates first pass the existing status, type, assignment, and
// participant filters. Search-only embeddings then choose a gap related to
// the recent channel messages. Claim evidence is untouched.

import { task } from '@trigger.dev/sdk/v3';
import { and, desc, eq, gt, gte, inArray, isNull, ne, or, sql } from 'drizzle-orm';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  channelParticipants,
  channels,
  gaps,
  jobRuns,
  messages,
  modelRuns,
  modelRunUsageDetails,
  oracleContextPacks,
  oracleInterventions,
  settings,
  typingIndicators,
} from '@oracle/db/schema';
import {
  OracleAIClient,
  buildStandardAdapters,
  embedMany,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type OracleModelRoute,
  type RouteCandidate,
} from '@oracle/ai';
import {
  decideLullInterjection,
  assertRealTopicalEmbeddings,
  gapEmbeddingNeedsRefresh,
  isGapEligibleForChannel,
  selectTopicalGap,
  type LullInterjectionInput,
  type RelevantOpenGap,
} from '@oracle/engines';

const LULL_INTERJECTION_PROMPT_VERSION = 'lull-interjection-1.0.0';

// Recent user messages to thread into the drafting prompt for tone/topical context.
const RECENT_MESSAGE_CONTEXT_COUNT = 5;
// Read candidates in bounded keyset pages. We must inspect every eligible gap
// for correctness, but never materialize an unbounded database result at once.
const GAP_CANDIDATE_PAGE_SIZE = 200;

// Default setting values if the row is missing — match the seed in packages/db/src/seed.ts.
const DEFAULT_LULL_WINDOW_SECONDS = 60;
const DEFAULT_ORACLE_COOLDOWN_MINUTES = 10;
const DEFAULT_MAX_ORACLE_INTERJECTIONS_PER_HOUR = 3;
const DEFAULT_ENABLE_GROUP_CHAT_LULL_QUESTIONS = true;
// A conservative positive-similarity floor rejects orthogonal fixture topics.
// The database setting can tune it against measured data without a code or
// model change.
const DEFAULT_LULL_GAP_MINIMUM_RELEVANCE = 0.35;

const LULL_DRAFT_SYSTEM = `You are the Oracle — an evidence-backed knowledge assistant for POP Creations / Spruce Line.

The conversation in this chat has gone quiet. There's an open question the team should answer, and the recent discussion is on a topic where that answer would help.

Your task: rephrase the open question as a warm, natural one-liner fit for chat. Match the tone of the recent messages. Do not introduce yourself, do not preamble, do not use markdown headings, do not say "I" or "the Oracle". Just ask the question.

Hard rules:
- Return ONLY the question text — no preface, no explanation, no metadata.
- 200 characters or less.
- One question only.
- Plain text, no markdown.
- No fabricated specifics. If the open question already has a specific entity (Disney, Coldlion, etc.) keep it; otherwise stay generic.`;

// ─── Module-singleton OracleAIClient (same pattern as the other workers) ────
function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({
    adapters: buildStandardAdapters(),
  });
}

function hashString(s: string): string {
  return createHash('sha256').update(s).digest('hex');
}

async function resolveInterviewCandidates(
  db: ReturnType<typeof getDirectDb>,
): Promise<RouteCandidate[]> {
  const resolved = await resolveRouteCandidates(db, 'interview');
  for (const skipped of resolved.skipped) {
    console.warn('[lull-interjection] skipped interview route candidate', skipped);
  }
  return resolved.candidates;
}

// ─── Settings loader ────────────────────────────────────────────────────────
interface LullSettings {
  lullWindowSeconds: number;
  oracleCooldownMinutes: number;
  maxOracleInterjectionsPerHour: number;
  enableGroupChatLullQuestions: boolean;
  lullGapMinimumRelevance: number;
}

async function loadLullSettings(db: ReturnType<typeof getDirectDb>): Promise<LullSettings> {
  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(
      inArray(settings.key, [
        'lull_window_seconds',
        'oracle_cooldown_minutes',
        'max_oracle_interjections_per_hour',
        'enable_group_chat_lull_questions',
        'lull_gap_minimum_relevance',
      ]),
    );
  const map = new Map(rows.map((r) => [r.key, r.value]));
  const num = (k: string, fallback: number) => {
    const v = map.get(k);
    return typeof v === 'number' ? v : fallback;
  };
  const bool = (k: string, fallback: boolean) => {
    const v = map.get(k);
    return typeof v === 'boolean' ? v : fallback;
  };
  const lullGapMinimumRelevance = num(
    'lull_gap_minimum_relevance',
    DEFAULT_LULL_GAP_MINIMUM_RELEVANCE,
  );
  if (lullGapMinimumRelevance < 0 || lullGapMinimumRelevance > 1) {
    throw new Error(
      `[lull-interjection] lull_gap_minimum_relevance must be between 0 and 1; received ${lullGapMinimumRelevance}`,
    );
  }
  return {
    lullWindowSeconds: num('lull_window_seconds', DEFAULT_LULL_WINDOW_SECONDS),
    oracleCooldownMinutes: num('oracle_cooldown_minutes', DEFAULT_ORACLE_COOLDOWN_MINUTES),
    maxOracleInterjectionsPerHour: num(
      'max_oracle_interjections_per_hour',
      DEFAULT_MAX_ORACLE_INTERJECTIONS_PER_HOUR,
    ),
    enableGroupChatLullQuestions: bool(
      'enable_group_chat_lull_questions',
      DEFAULT_ENABLE_GROUP_CHAT_LULL_QUESTIONS,
    ),
    lullGapMinimumRelevance,
  };
}

// ─── Per-channel data fetch ─────────────────────────────────────────────────
interface ChannelContext {
  channelId: string;
  isGroupChat: boolean;
  secondsSinceLastUserMessage: number | null; // null = no user messages ever
  minutesSinceLastOracleInterjection: number | null;
  interjectionsInLastHour: number;
  topRelevantOpenGap: RelevantOpenGap | null;
  recentMessageExcerpts: string[];
  isAnyoneTyping: boolean;
}

async function loadChannelContext(
  db: ReturnType<typeof getDirectDb>,
  channelId: string,
  isGroupChat: boolean,
  now: Date,
  lullSettings: LullSettings,
): Promise<ChannelContext> {
  // Last user message
  const lastUserMsgRows = await db
    .select({ createdAt: messages.createdAt, content: messages.content })
    .from(messages)
    .where(
      and(eq(messages.channelId, channelId), eq(messages.role, 'user'), isNull(messages.deletedAt)),
    )
    .orderBy(desc(messages.createdAt))
    .limit(RECENT_MESSAGE_CONTEXT_COUNT);

  const secondsSinceLastUserMessage =
    lastUserMsgRows.length > 0 && lastUserMsgRows[0]
      ? Math.floor((now.getTime() - lastUserMsgRows[0].createdAt.getTime()) / 1000)
      : null;
  const recentMessageExcerpts = lastUserMsgRows
    .slice()
    .reverse() // oldest-first for prompt readability
    .map((m) => m.content.slice(0, 240));

  // Last oracle intervention in this channel
  const lastInterventionRows = await db
    .select({ createdAt: oracleInterventions.createdAt })
    .from(oracleInterventions)
    .where(eq(oracleInterventions.channelId, channelId))
    .orderBy(desc(oracleInterventions.createdAt))
    .limit(1);
  const minutesSinceLastOracleInterjection =
    lastInterventionRows.length > 0 && lastInterventionRows[0]
      ? Math.floor((now.getTime() - lastInterventionRows[0].createdAt.getTime()) / 60_000)
      : null;

  // Interventions in last hour
  const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
  const countRows = await db
    .select({ c: sql<number>`count(*)::int` })
    .from(oracleInterventions)
    .where(
      and(
        eq(oracleInterventions.channelId, channelId),
        gte(oracleInterventions.createdAt, oneHourAgo),
      ),
    );
  const interjectionsInLastHour = countRows[0]?.c ?? 0;

  // Check live typing before doing embedding work. The decider remains the
  // authority and still returns someone_typing before inspecting a gap.
  const typingRow = await db
    .select({ channelId: typingIndicators.channelId })
    .from(typingIndicators)
    .where(
      and(eq(typingIndicators.channelId, channelId), sql`${typingIndicators.expiresAt} > NOW()`),
    )
    .limit(1);
  const isAnyoneTyping = typingRow.length > 0;

  // Existing eligibility rules run before semantic scoring.
  const participantIds = await db
    .select({ id: channelParticipants.employeeId })
    .from(channelParticipants)
    .where(eq(channelParticipants.channelId, channelId));
  const participantIdList = participantIds.map((p) => p.id);

  type Candidate = {
    id: string;
    priority: RelevantOpenGap['priority'];
    questionToAsk: string;
    whyItMatters: string;
    targetEmployeeId: string | null;
    embedding: number[] | null;
    embeddingModel: string | null;
    embeddingSourceHash: string | null;
    createdAt: Date;
  };
  const eligible: Candidate[] = [];
  let afterGapId: string | null = null;
  do {
    const assignmentFilter =
      participantIdList.length === 0
        ? isNull(gaps.targetEmployeeId)
        : or(isNull(gaps.targetEmployeeId), inArray(gaps.targetEmployeeId, participantIdList));
    const page: Candidate[] = await db
      .select({
        id: gaps.id,
        priority: gaps.priority,
        questionToAsk: gaps.questionToAsk,
        whyItMatters: gaps.whyItMatters,
        targetEmployeeId: gaps.targetEmployeeId,
        embedding: gaps.embedding,
        embeddingModel: gaps.embeddingModel,
        embeddingSourceHash: gaps.embeddingSourceHash,
        createdAt: gaps.createdAt,
      })
      .from(gaps)
      .where(
        and(
          eq(gaps.status, 'open'),
          ne(gaps.gapType, 'model_coverage'),
          assignmentFilter,
          afterGapId === null ? undefined : gt(gaps.id, afterGapId),
        ),
      )
      .orderBy(gaps.id)
      .limit(GAP_CANDIDATE_PAGE_SIZE);
    eligible.push(
      ...page.filter((gap) => isGapEligibleForChannel(gap.targetEmployeeId, participantIdList)),
    );
    afterGapId = page.length === GAP_CANDIDATE_PAGE_SIZE ? page.at(-1)!.id : null;
  } while (afterGapId !== null);

  let topRelevantOpenGap: RelevantOpenGap | null = null;
  const nonGapGatesPass =
    (!isGroupChat || lullSettings.enableGroupChatLullQuestions) &&
    secondsSinceLastUserMessage !== null &&
    secondsSinceLastUserMessage >= lullSettings.lullWindowSeconds &&
    !isAnyoneTyping &&
    (minutesSinceLastOracleInterjection === null ||
      minutesSinceLastOracleInterjection >= lullSettings.oracleCooldownMinutes) &&
    interjectionsInLastHour < lullSettings.maxOracleInterjectionsPerHour;
  if (nonGapGatesPass && recentMessageExcerpts.length > 0 && eligible.length > 0) {
    const recent = await embedMany([recentMessageExcerpts.join('\n')]);
    assertRealTopicalEmbeddings(recent);
    const recentMessageEmbedding = recent.vectors[0];
    if (!recentMessageEmbedding) {
      throw new Error('[lull-interjection] recent-message embedding was not returned');
    }
    const gapText = (gap: (typeof eligible)[number]) =>
      `${gap.questionToAsk}\n${gap.whyItMatters}`;
    const missing = eligible.filter((gap) =>
      gapEmbeddingNeedsRefresh({
        embedding: gap.embedding,
        embeddingModel: gap.embeddingModel,
        embeddingSourceHash: gap.embeddingSourceHash,
        requiredModel: recent.model,
        requiredSourceHash: hashString(gapText(gap)),
      }),
    );
    const embedded =
      missing.length > 0
        ? await embedMany(missing.map(gapText))
        : { vectors: [] as number[][], model: recent.model, fallback: false };
    assertRealTopicalEmbeddings(embedded);
    if (embedded.model !== recent.model) {
      throw new Error('[lull-interjection] gap and recent-message embeddings must use one real model');
    }
    for (let index = 0; index < missing.length; index += 1) {
      const gap = missing[index]!;
      const embedding = embedded.vectors[index];
      if (!embedding) {
        throw new Error(`[lull-interjection] embedding was not returned for gap ${gap.id}`);
      }
      gap.embedding = embedding;
      gap.embeddingModel = embedded.model;
      gap.embeddingSourceHash = hashString(gapText(gap));
      const persisted = await db
        .update(gaps)
        .set({
          embedding,
          embeddingModel: embedded.model,
          embeddingSourceHash: gap.embeddingSourceHash,
        })
        .where(
          and(
            eq(gaps.id, gap.id),
            eq(gaps.questionToAsk, gap.questionToAsk),
            eq(gaps.whyItMatters, gap.whyItMatters),
          ),
        )
        .returning({ id: gaps.id });
      if (persisted.length === 0) {
        throw new Error(`[lull-interjection] gap ${gap.id} changed during topical scoring`);
      }
    }
    topRelevantOpenGap = selectTopicalGap(
      recentMessageEmbedding,
      eligible.map((gap) => ({
        id: gap.id,
        priority: gap.priority as RelevantOpenGap['priority'],
        questionToAsk: gap.questionToAsk,
        whyItMatters: gap.whyItMatters,
        embedding: gap.embedding!,
        createdAtMs: gap.createdAt.getTime(),
      })),
      lullSettings.lullGapMinimumRelevance,
    );
  }

  return {
    channelId,
    isGroupChat,
    secondsSinceLastUserMessage,
    minutesSinceLastOracleInterjection,
    interjectionsInLastHour,
    topRelevantOpenGap,
    recentMessageExcerpts,
    isAnyoneTyping,
  };
}

// ─── Rate-state re-read (used inside the advisory lock) ─────────────────────
// Re-reads ONLY the cooldown + hourly-count inputs to decideLullInterjection
// so the post decision can be re-validated under the per-channel lock. Accepts
// a db or tx handle.
async function reloadInterjectionRateState(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  dbOrTx: any,
  channelId: string,
  now: Date,
): Promise<{ minutesSinceLastOracleInterjection: number | null; interjectionsInLastHour: number }> {
  const lastInterventionRows = await dbOrTx
    .select({ createdAt: oracleInterventions.createdAt })
    .from(oracleInterventions)
    .where(eq(oracleInterventions.channelId, channelId))
    .orderBy(desc(oracleInterventions.createdAt))
    .limit(1);
  const minutesSinceLastOracleInterjection =
    lastInterventionRows.length > 0 && lastInterventionRows[0]
      ? Math.floor((now.getTime() - lastInterventionRows[0].createdAt.getTime()) / 60_000)
      : null;
  const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000);
  const countRows = await dbOrTx
    .select({ c: sql<number>`count(*)::int` })
    .from(oracleInterventions)
    .where(
      and(
        eq(oracleInterventions.channelId, channelId),
        gte(oracleInterventions.createdAt, oneHourAgo),
      ),
    );
  return {
    minutesSinceLastOracleInterjection,
    interjectionsInLastHour: countRows[0]?.c ?? 0,
  };
}

// ─── Drafting via OracleAIClient.runText (interview route) ──────────────────
async function draftLullQuestion(
  db: ReturnType<typeof getDirectDb>,
  client: OracleAIClient,
  route: OracleModelRoute,
  routeCandidates: RouteCandidate[],
  gap: RelevantOpenGap,
  recentMessageExcerpts: string[],
): Promise<{ text: string; modelRunId: string | null }> {
  const recentContext =
    recentMessageExcerpts.length === 0
      ? '(no recent messages)'
      : recentMessageExcerpts.map((m, i) => `[${i + 1}] ${m}`).join('\n');

  const userMessage = `Open question to ask: ${gap.questionToAsk}
Why it matters: ${gap.whyItMatters}

Recent messages in this channel (oldest first, for tone reference — do not directly quote):
${recentContext}`;

  const blocks = [
    makeBlock({
      id: 'sys',
      label: 'Lull-interjection system prompt',
      kind: 'stable_system',
      content: LULL_DRAFT_SYSTEM,
      cacheEligible: true,
      reasonIncluded: 'spec 5.1 Rule 2 — lull interjection drafting',
    }),
    makeBlock({
      id: 'gap-input',
      label: 'Gap + recent context',
      kind: 'dynamic_input',
      content: userMessage,
      cacheEligible: false,
      reasonIncluded: 'current gap and recent messages',
    }),
  ];

  const callStartedAt = Date.now();
  let modelRunId: string | null = null;
  try {
    const result = await client.runText({
      taskType: 'gap_generation',
      routeId: route.routeId,
      promptVersion: LULL_INTERJECTION_PROMPT_VERSION,
      blocks,
      providerOptions: { temperature: 0.4 },
      routeCandidates,
    });
    const latencyMs = Date.now() - callStartedAt;
    const actualRouteId = result.routeId ?? route.routeId;
    const actualProvider = result.provider ?? route.provider;
    const actualModelId = result.modelId ?? route.modelId;

    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values({
        taskType: 'gap_generation',
        routeId: route.routeId,
        promptVersion: LULL_INTERJECTION_PROMPT_VERSION,
        stablePrefixHash: hashString(LULL_DRAFT_SYSTEM),
        dynamicInputHash: hashString(userMessage),
        blocksJson: blocks.map((b) => ({
          id: b.id,
          kind: b.kind,
          hash: b.hash,
          tokenEstimate: b.tokenEstimate,
        })),
        includedGapIds: [gap.id],
      })
      .returning({ id: oracleContextPacks.id });
    if (!contextPack) throw new Error('failed to insert oracle_context_packs row');

    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'lull-interjection',
        model: actualModelId,
        provider: actualProvider,
        promptVersion: LULL_INTERJECTION_PROMPT_VERSION,
        inputHash: hashString(LULL_DRAFT_SYSTEM),
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs,
        success: true,
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('failed to insert model_runs row');
    modelRunId = modelRun.id;

    await db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
      contextPackId: contextPack.id,
      routeId: actualRouteId,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      cachedInputTokens: result.usage.cachedInputTokens ?? null,
      cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
      reasoningTokens: result.usage.reasoningTokens ?? null,
      providerRequestId: result.usage.providerRequestId ?? null,
      rawUsageJson: (result.usage.rawUsageJson ?? null) as Record<string, unknown> | null,
    });

    await logModelRunAttempts({
      db,
      metadata: result,
      taskType: 'lull-interjection',
      slot: 'interview',
      contextPackId: contextPack.id,
      modelRunId: modelRun.id,
    });

    await db
      .update(oracleContextPacks)
      .set({ modelRunId: modelRun.id })
      .where(eq(oracleContextPacks.id, contextPack.id));

    const text = (result.text ?? '').trim();
    if (text.length === 0) {
      throw new Error('drafting returned empty text');
    }
    return { text, modelRunId };
  } catch (err) {
    const latencyMs = Date.now() - callStartedAt;
    const message = err instanceof Error ? err.message : String(err);
    await logAllCandidatesFailedAttempts({
      db,
      error: err,
      taskType: 'lull-interjection',
      slot: 'interview',
    });
    try {
      const [modelRun] = await db
        .insert(modelRuns)
        .values({
          taskType: 'lull-interjection',
          model: route.modelId,
          provider: route.provider,
          promptVersion: LULL_INTERJECTION_PROMPT_VERSION,
          latencyMs,
          success: false,
          error: message,
        })
        .returning({ id: modelRuns.id });
      modelRunId = modelRun?.id ?? null;
    } catch {
      /* swallow */
    }
    throw err;
  }
}

// ─── Per-channel processing ─────────────────────────────────────────────────
interface ChannelOutcome {
  channelId: string;
  decision: 'ask' | 'skip';
  reasonCode?: string;
  interjectionMessageId?: string;
  gapId?: string;
  errorMessage?: string;
}

async function processChannel(
  db: ReturnType<typeof getDirectDb>,
  client: OracleAIClient,
  route: OracleModelRoute,
  routeCandidates: RouteCandidate[],
  channel: { id: string; isGroupChat: boolean },
  settings: LullSettings,
  now: Date,
  expectedLatestUserMessageId: string,
): Promise<ChannelOutcome> {
  const ctx = await loadChannelContext(
    db,
    channel.id,
    channel.isGroupChat,
    now,
    settings,
  );

  // No user messages ever → nothing to interrupt; treat as long lull but skip
  // because the channel hasn't started a conversation yet.
  if (ctx.secondsSinceLastUserMessage === null) {
    return {
      channelId: channel.id,
      decision: 'skip',
      reasonCode: 'no_user_messages_yet',
    };
  }

  const decisionInput: LullInterjectionInput = {
    secondsSinceLastUserMessage: ctx.secondsSinceLastUserMessage,
    lullWindowSeconds: settings.lullWindowSeconds,
    isAnyoneTyping: ctx.isAnyoneTyping,
    minutesSinceLastOracleInterjection: ctx.minutesSinceLastOracleInterjection,
    oracleCooldownMinutes: settings.oracleCooldownMinutes,
    interjectionsInLastHour: ctx.interjectionsInLastHour,
    maxOracleInterjectionsPerHour: settings.maxOracleInterjectionsPerHour,
    enableGroupChatLullQuestions: settings.enableGroupChatLullQuestions,
    channelKind: channel.isGroupChat ? 'group' : 'dm',
    topRelevantOpenGap: ctx.topRelevantOpenGap,
  };

  const decision = decideLullInterjection(decisionInput);

  if (decision.decision === 'skip') {
    return {
      channelId: channel.id,
      decision: 'skip',
      reasonCode: decision.reasonCode,
    };
  }

  // decision === 'ask' — draft + post.
  try {
    if (!ctx.topRelevantOpenGap) {
      // The decider already enforces this, but TS doesn't know.
      return { channelId: channel.id, decision: 'skip', reasonCode: 'no_relevant_gap' };
    }
    const gap = ctx.topRelevantOpenGap;

    // Draft OUTSIDE the lock (don't hold the advisory lock across the LLM call).
    const drafted = await draftLullQuestion(
      db,
      client,
      route,
      routeCandidates,
      gap,
      ctx.recentMessageExcerpts,
    );

    // Commit inside a transaction guarded by a per-channel advisory lock so two
    // concurrent runs can't both blow past the per-hour interjection cap on the
    // same channel. Re-read the rate/cooldown state inside the lock and re-run
    // the decider; also claim the gap atomically so two workers can't ask the
    // same gap. If the lock is contended or the re-check/gap-claim fails, skip.
    return await db.transaction(async (tx) => {
      const lockRes = await tx.execute<{ locked: boolean }>(
        sql`SELECT pg_try_advisory_xact_lock(hashtext(${channel.id})) AS locked`,
      );
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const lockRows: Array<{ locked: boolean }> = (lockRes as any).rows ?? (lockRes as any);
      if (lockRows[0]?.locked !== true) {
        return {
          channelId: channel.id,
          decision: 'skip' as const,
          reasonCode: 'skipped: lock_contended',
        };
      }

      // Re-read cooldown + rate-cap state inside the lock and re-decide.
      const recheck = await reloadInterjectionRateState(tx, channel.id, new Date());
      const recheckDecision = decideLullInterjection({
        ...decisionInput,
        minutesSinceLastOracleInterjection: recheck.minutesSinceLastOracleInterjection,
        interjectionsInLastHour: recheck.interjectionsInLastHour,
      });
      if (recheckDecision.decision === 'skip') {
        return {
          channelId: channel.id,
          decision: 'skip' as const,
          reasonCode: recheckDecision.reasonCode,
        };
      }

      // Presence can change while the question is being drafted. Re-read it
      // under the same channel lock so a fresh heartbeat still prevents a post.
      const liveTyping = await tx
        .select({ channelId: typingIndicators.channelId })
        .from(typingIndicators)
        .where(
          and(
            eq(typingIndicators.channelId, channel.id),
            sql`${typingIndicators.expiresAt} > NOW()`,
          ),
        )
        .limit(1);
      if (liveTyping.length > 0) {
        return {
          channelId: channel.id,
          decision: 'skip' as const,
          reasonCode: 'someone_typing',
        };
      }

      // A message can arrive while the model is drafting. Re-check immediately
      // before claiming the gap and posting so an old delayed run never
      // interrupts a conversation that has resumed.
      const [latestUserMessage] = await tx
        .select({ id: messages.id })
        .from(messages)
        .where(
          and(
            eq(messages.channelId, channel.id),
            eq(messages.role, 'user'),
            isNull(messages.deletedAt),
          ),
        )
        .orderBy(desc(messages.createdAt), desc(messages.id))
        .limit(1);
      if (latestUserMessage?.id !== expectedLatestUserMessageId) {
        return {
          channelId: channel.id,
          decision: 'skip' as const,
          reasonCode: 'newer_user_message',
        };
      }

      // Claim the gap atomically — only if it is still open.
      const claimed = await tx
        .update(gaps)
        .set({ status: 'asked', updatedAt: new Date() })
        .where(and(eq(gaps.id, gap.id), eq(gaps.status, 'open')))
        .returning({ id: gaps.id });
      if (claimed.length === 0) {
        return {
          channelId: channel.id,
          decision: 'skip' as const,
          reasonCode: 'gap_already_claimed',
        };
      }

      // Insert the assistant message (no employeeId — Oracle messages are
      // employeeId=null per the schema; role='assistant').
      const [interjectionMessage] = await tx
        .insert(messages)
        .values({
          channelId: channel.id,
          employeeId: null,
          role: 'assistant',
          content: drafted.text,
          // extractionStatus stays 'pending' default per schema; the extraction
          // worker queries role='user' so it'll naturally skip Oracle messages.
          metadataJson: {
            source: 'lull-interjection',
            gapId: gap.id,
            modelRunId: drafted.modelRunId,
            decisionReason: decision.reason,
          },
        })
        .returning({ id: messages.id });
      if (!interjectionMessage) throw new Error('failed to insert assistant message');

      // Record the intervention.
      await tx.insert(oracleInterventions).values({
        channelId: channel.id,
        triggerType: 'lull_gap',
        relatedGapId: gap.id,
        interjectionMessageId: interjectionMessage.id,
        confidence: null,
        impactScore: null,
        wasLiveInterjection: true,
        reason: decision.reason,
      });

      // Back-fill askedInMessageId now that the message exists.
      await tx
        .update(gaps)
        .set({ askedInMessageId: interjectionMessage.id })
        .where(eq(gaps.id, gap.id));

      return {
        channelId: channel.id,
        decision: 'ask' as const,
        interjectionMessageId: interjectionMessage.id,
        gapId: gap.id,
      };
    });
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : String(err);
    console.error(
      `[lull-interjection] channel ${channel.id} drafting/posting failed:`,
      errorMessage,
    );
    return {
      channelId: channel.id,
      decision: 'skip',
      reasonCode: 'drafting_failed',
      errorMessage,
    };
  }
}

interface LullInterjectionPayload {
  channelId: string;
  messageId: string;
}

// ─── Top-level event-driven task ───────────────────────────────────────────
export const lullInterjectionTask = task({
  id: 'lull-interjection',
  maxDuration: 60 * 2,
  // Retries remain disabled because the task can post a live interjection.
  // Trigger dispatch is debounced by channel and delayed 60 seconds in the web
  // app; a retry could re-evaluate stale state and risk a duplicate post.
  retry: { maxAttempts: 1 },
  run: async (payload: LullInterjectionPayload, { ctx }) => {
    const db = getDirectDb();
    const startedAt = new Date();

    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'lull-interjection',
        status: 'running',
        startedAt,
      })
      .returning({ id: jobRuns.id });
    if (!jobRun) throw new Error('[lull-interjection] failed to insert job_runs row');

    const totals = {
      channelsConsidered: 1,
      interjectionsAsked: 0,
      skipsByReason: {} as Record<string, number>,
      errors: 0,
    };

    try {
      if (
        typeof payload?.channelId !== 'string' ||
        typeof payload?.messageId !== 'string'
      ) {
        totals.channelsConsidered = 0;
        totals.skipsByReason.invalid_event_payload = 1;
        await db
          .update(jobRuns)
          .set({ status: 'complete', finishedAt: new Date(), outputJson: totals })
          .where(eq(jobRuns.id, jobRun.id));
        return { ok: true, ...totals };
      }

      const [channel] = await db
        .select({ id: channels.id, isGroupChat: channels.isGroupChat })
        .from(channels)
        .where(and(eq(channels.id, payload.channelId), eq(channels.status, 'active')))
        .limit(1);

      const [latestUserMessage] = await db
        .select({ id: messages.id })
        .from(messages)
        .where(
          and(
            eq(messages.channelId, payload.channelId),
            eq(messages.role, 'user'),
            isNull(messages.deletedAt),
          ),
        )
        .orderBy(desc(messages.createdAt), desc(messages.id))
        .limit(1);

      if (!channel || latestUserMessage?.id !== payload.messageId) {
        const reason = !channel ? 'channel_not_active' : 'newer_user_message';
        totals.skipsByReason[reason] = 1;
        await db
          .update(jobRuns)
          .set({ status: 'complete', finishedAt: new Date(), outputJson: totals })
          .where(eq(jobRuns.id, jobRun.id));
        return { ok: true, ...totals };
      }

      const lullSettings = await loadLullSettings(db);
      const routeCandidates = await resolveInterviewCandidates(db);
      const route = routeCandidates[0]!.route;
      const outcome = await processChannel(
        db,
        buildOracleClient(),
        route,
        routeCandidates,
        channel,
        lullSettings,
        new Date(),
        payload.messageId,
      );
      if (outcome.decision === 'ask') {
        totals.interjectionsAsked += 1;
      } else {
        const code = outcome.reasonCode ?? 'unknown';
        totals.skipsByReason[code] = 1;
        if (outcome.errorMessage) totals.errors += 1;
      }

      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: totals })
        .where(eq(jobRuns.id, jobRun.id));

      return { ok: true, ...totals };
    } catch (fatalErr) {
      await db
        .update(jobRuns)
        .set({
          status: 'failed',
          finishedAt: new Date(),
          error: fatalErr instanceof Error ? fatalErr.message : String(fatalErr),
        })
        .where(eq(jobRuns.id, jobRun.id));
      throw fatalErr;
    }
  },
});
