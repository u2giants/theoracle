// R11.2 — Lull-interjection scheduled task.
//
// Per spec Part 5.1 Rule 2 + docs/oracle/05-ai-retrofit-phase-packet.md
// "Phase R11" + HANDOFF.md R11.2.
//
// Every minute, for each active channel:
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
// Presence check (isAnyoneTyping): round 1 defaults to false. Wiring real
// Supabase Realtime presence is round 2.
//
// Topical relevance of the chosen gap: round 1 picks highest-priority open
// gap whose targetEmployeeId is null or is a channel participant. Embedding-
// based topical relevance vs recent message embeddings is round 2.

import { schedules } from '@trigger.dev/sdk/v3';
import { and, desc, eq, gte, inArray, isNull, sql } from 'drizzle-orm';
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
  getOracleRoute,
  resolveModelRoute,
  makeBlock,
  type OracleModelRoute,
} from '@oracle/ai';
import {
  decideLullInterjection,
  type LullInterjectionInput,
  type RelevantOpenGap,
} from '@oracle/engines';

const FALLBACK_INTERVIEW_ROUTE_ID = 'anthropic_claude_haiku_4_5_interview_primary';
const LULL_INTERJECTION_PROMPT_VERSION = 'lull-interjection-1.0.0';

// Recent user messages to thread into the drafting prompt for tone/topical context.
const RECENT_MESSAGE_CONTEXT_COUNT = 5;

// Default setting values if the row is missing — match the seed in packages/db/src/seed.ts.
const DEFAULT_LULL_WINDOW_SECONDS = 60;
const DEFAULT_ORACLE_COOLDOWN_MINUTES = 10;
const DEFAULT_MAX_ORACLE_INTERJECTIONS_PER_HOUR = 3;
const DEFAULT_ENABLE_GROUP_CHAT_LULL_QUESTIONS = true;

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
    fallbackOnError: true,
  });
}

function hashString(s: string): string {
  return createHash('sha256').update(s).digest('hex');
}

// ─── Curated route resolver — INTERVIEW route (human-facing drafting) ───────
async function resolveInterviewRoute(
  db: ReturnType<typeof getDirectDb>,
): Promise<OracleModelRoute> {
  const row = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'default_interview_route'))
    .limit(1);
  const modelIdOrRouteId =
    typeof row[0]?.value === 'string'
      ? (row[0]!.value as string)
      : FALLBACK_INTERVIEW_ROUTE_ID;
  const resolved = resolveModelRoute(modelIdOrRouteId, 'interview') ?? getOracleRoute(modelIdOrRouteId);
  if (resolved) return resolved;
  const fallback = getOracleRoute(FALLBACK_INTERVIEW_ROUTE_ID);
  if (!fallback) {
    throw new Error(
      `[lull-interjection] settings.default_interview_route="${modelIdOrRouteId}" not in catalog, and fallback "${FALLBACK_INTERVIEW_ROUTE_ID}" also missing.`,
    );
  }
  console.warn(
    `[lull-interjection] settings.default_interview_route="${modelIdOrRouteId}" not in catalog; using fallback "${FALLBACK_INTERVIEW_ROUTE_ID}".`,
  );
  return fallback;
}

// ─── Settings loader ────────────────────────────────────────────────────────
interface LullSettings {
  lullWindowSeconds: number;
  oracleCooldownMinutes: number;
  maxOracleInterjectionsPerHour: number;
  enableGroupChatLullQuestions: boolean;
}

async function loadLullSettings(
  db: ReturnType<typeof getDirectDb>,
): Promise<LullSettings> {
  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(
      inArray(settings.key, [
        'lull_window_seconds',
        'oracle_cooldown_minutes',
        'max_oracle_interjections_per_hour',
        'enable_group_chat_lull_questions',
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
  return {
    lullWindowSeconds: num('lull_window_seconds', DEFAULT_LULL_WINDOW_SECONDS),
    oracleCooldownMinutes: num(
      'oracle_cooldown_minutes',
      DEFAULT_ORACLE_COOLDOWN_MINUTES,
    ),
    maxOracleInterjectionsPerHour: num(
      'max_oracle_interjections_per_hour',
      DEFAULT_MAX_ORACLE_INTERJECTIONS_PER_HOUR,
    ),
    enableGroupChatLullQuestions: bool(
      'enable_group_chat_lull_questions',
      DEFAULT_ENABLE_GROUP_CHAT_LULL_QUESTIONS,
    ),
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
): Promise<ChannelContext> {
  // Last user message
  const lastUserMsgRows = await db
    .select({ createdAt: messages.createdAt, content: messages.content })
    .from(messages)
    .where(and(eq(messages.channelId, channelId), eq(messages.role, 'user'), isNull(messages.deletedAt)))
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

  // Top relevant open gap. Round 1: prioritize urgent > high > medium > low,
  // then prefer gaps whose targetEmployeeId is a channel participant (more
  // likely to land on someone present), then prefer most-recently-created.
  // No embedding-based topical relevance yet.
  const participantIds = await db
    .select({ id: channelParticipants.employeeId })
    .from(channelParticipants)
    .where(eq(channelParticipants.channelId, channelId));
  const participantIdList = participantIds.map((p) => p.id);

  // Priority ordering: gap_priority enum is ('low','medium','high','urgent').
  // We need urgent first → use CASE.
  const candidates = await db
    .select({
      id: gaps.id,
      priority: gaps.priority,
      questionToAsk: gaps.questionToAsk,
      whyItMatters: gaps.whyItMatters,
      targetEmployeeId: gaps.targetEmployeeId,
      createdAt: gaps.createdAt,
    })
    .from(gaps)
    .where(eq(gaps.status, 'open'))
    .orderBy(
      sql`CASE ${gaps.priority}
            WHEN 'urgent' THEN 1
            WHEN 'high'   THEN 2
            WHEN 'medium' THEN 3
            WHEN 'low'    THEN 4
            ELSE 5
          END`,
      desc(gaps.createdAt),
    )
    .limit(50);

  // Filter: targetEmployeeId is null (channel-agnostic) OR a participant.
  const eligible = candidates.find((g) => {
    if (g.targetEmployeeId === null) return true;
    return participantIdList.includes(g.targetEmployeeId);
  });

  const topRelevantOpenGap: RelevantOpenGap | null = eligible
    ? {
        id: eligible.id,
        priority: eligible.priority as RelevantOpenGap['priority'],
        questionToAsk: eligible.questionToAsk,
        whyItMatters: eligible.whyItMatters,
      }
    : null;

  // Check whether any employee is currently typing in this channel.
  // The client upserts a typing_indicators row on keystrokes with expires_at = now+5s;
  // stale rows (disconnected clients) are excluded by the expires_at filter.
  const typingRow = await db
    .select({ channelId: typingIndicators.channelId })
    .from(typingIndicators)
    .where(
      and(
        eq(typingIndicators.channelId, channelId),
        sql`${typingIndicators.expiresAt} > NOW()`,
      ),
    )
    .limit(1);
  const isAnyoneTyping = typingRow.length > 0;

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

// ─── Drafting via OracleAIClient.runText (interview route) ──────────────────
async function draftLullQuestion(
  db: ReturnType<typeof getDirectDb>,
  client: OracleAIClient,
  route: OracleModelRoute,
  gap: RelevantOpenGap,
  recentMessageExcerpts: string[],
): Promise<{ text: string; modelRunId: string | null }> {
  const recentContext = recentMessageExcerpts.length === 0
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
    });
    const latencyMs = Date.now() - callStartedAt;

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
        model: route.modelId,
        provider: route.provider,
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
      routeId: route.routeId,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      cachedInputTokens: result.usage.cachedInputTokens ?? null,
      cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
      reasoningTokens: result.usage.reasoningTokens ?? null,
      providerRequestId: result.usage.providerRequestId ?? null,
      rawUsageJson: (result.usage.rawUsageJson ?? null) as Record<string, unknown> | null,
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
  channel: { id: string; isGroupChat: boolean },
  settings: LullSettings,
  now: Date,
): Promise<ChannelOutcome> {
  const ctx = await loadChannelContext(db, channel.id, channel.isGroupChat, now);

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
    const drafted = await draftLullQuestion(db, client, route, ctx.topRelevantOpenGap, ctx.recentMessageExcerpts);

    // Insert the assistant message (no employeeId — Oracle messages are
    // employeeId=null per the schema; role='assistant').
    const [interjectionMessage] = await db
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
          gapId: ctx.topRelevantOpenGap.id,
          modelRunId: drafted.modelRunId,
          decisionReason: decision.reason,
        },
      })
      .returning({ id: messages.id });
    if (!interjectionMessage) throw new Error('failed to insert assistant message');

    // Record the intervention.
    await db.insert(oracleInterventions).values({
      channelId: channel.id,
      triggerType: 'lull_gap',
      relatedGapId: ctx.topRelevantOpenGap.id,
      interjectionMessageId: interjectionMessage.id,
      confidence: null,
      impactScore: null,
      wasLiveInterjection: true,
      reason: decision.reason,
    });

    // Mark the gap as asked.
    await db
      .update(gaps)
      .set({
        status: 'asked',
        askedInMessageId: interjectionMessage.id,
        updatedAt: new Date(),
      })
      .where(eq(gaps.id, ctx.topRelevantOpenGap.id));

    return {
      channelId: channel.id,
      decision: 'ask',
      interjectionMessageId: interjectionMessage.id,
      gapId: ctx.topRelevantOpenGap.id,
    };
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : String(err);
    console.error(`[lull-interjection] channel ${channel.id} drafting/posting failed:`, errorMessage);
    return {
      channelId: channel.id,
      decision: 'skip',
      reasonCode: 'drafting_failed',
      errorMessage,
    };
  }
}

// ─── Top-level scheduled task ───────────────────────────────────────────────
export const lullInterjectionTask = schedules.task({
  id: 'lull-interjection',
  // Every minute. The cooldown + rate-cap gates inside decideLullInterjection
  // handle the actual interjection frequency; this just makes sure we check
  // often enough that a 60s lull window can fire promptly.
  cron: '* * * * *',
  maxDuration: 60 * 2,
  run: async (_payload, { ctx }) => {
    const db = getDirectDb();
    const client = buildOracleClient();
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
      channelsConsidered: 0,
      interjectionsAsked: 0,
      skipsByReason: {} as Record<string, number>,
      errors: 0,
    };

    try {
      const lullSettings = await loadLullSettings(db);
      const route = await resolveInterviewRoute(db);

      const activeChannels = await db
        .select({ id: channels.id, isGroupChat: channels.isGroupChat })
        .from(channels)
        .where(eq(channels.status, 'active'));

      for (const channel of activeChannels) {
        totals.channelsConsidered += 1;
        try {
          const outcome = await processChannel(db, client, route, channel, lullSettings, new Date());
          if (outcome.decision === 'ask') {
            totals.interjectionsAsked += 1;
          } else {
            const code = outcome.reasonCode ?? 'unknown';
            totals.skipsByReason[code] = (totals.skipsByReason[code] ?? 0) + 1;
            if (outcome.errorMessage) totals.errors += 1;
          }
        } catch (chanErr) {
          totals.errors += 1;
          console.error(`[lull-interjection] channel ${channel.id} failed:`, chanErr);
        }
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
