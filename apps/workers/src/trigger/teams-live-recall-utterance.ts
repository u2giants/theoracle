// Recall.ai live Teams utterance worker.
//
// This processes finalized `transcript.data` events, not partial/provisional
// STT hypotheses. Each finalized utterance is persisted as a `messages` row for
// evidence/backfill, then a tightly gated Oracle pass decides whether a useful
// one-question interjection should be posted back to the Teams meeting chat.

import { task } from '@trigger.dev/sdk/v3';
import { and, desc, eq, gte, isNull, sql } from 'drizzle-orm';
import { z } from 'zod';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  channelParticipants,
  channels,
  employees,
  jobRuns,
  messages,
  modelRuns,
  modelRunUsageDetails,
  oracleContextPacks,
  oracleInterventions,
  settings,
} from '@oracle/db/schema';
import {
  OracleAIClient,
  buildStandardAdapters,
  getOracleRoute,
  makeBlock,
  resolveRouteFromSettings,
  type OracleModelRoute,
} from '@oracle/ai';
import { sendRecallChatMessage } from '../lib/recall';

const FALLBACK_INTERVIEW_ROUTE_ID = 'anthropic_claude_haiku_4_5_interview_primary';
const LIVE_PROMPT_VERSION = 'teams-live-recall-1.0.0';
const DEFAULT_COOLDOWN_MINUTES = 10;
const DEFAULT_MAX_INTERJECTIONS_PER_HOUR = 3;
const DEFAULT_MIN_CONFIDENCE_TO_POST = 70;
const RECENT_UTTERANCE_LIMIT = 18;
const MIN_SECONDS_BETWEEN_LIVE_QUESTIONS = 20;

const RecallWordSchema = z.object({
  text: z.string(),
  start_timestamp: z.object({ relative: z.number().optional() }).optional(),
  end_timestamp: z.object({ relative: z.number().nullable().optional() }).nullable().optional(),
});

const RecallTranscriptDataSchema = z.object({
  words: z.array(RecallWordSchema).optional(),
  language_code: z.string().optional(),
  participant: z
    .object({
      id: z.union([z.string(), z.number()]).optional(),
      name: z.string().nullable().optional(),
      email: z.string().nullable().optional(),
      is_host: z.boolean().optional(),
      platform: z.string().nullable().optional(),
      extra_data: z.unknown().optional(),
    })
    .optional(),
});

const RecallRealtimeEventSchema = z.object({
  event: z.string(),
  data: z.object({
    data: RecallTranscriptDataSchema.optional(),
    transcript: z.object({ id: z.string().optional(), metadata: z.record(z.string(), z.unknown()).optional() }).optional(),
    recording: z.object({ id: z.string().optional(), metadata: z.record(z.string(), z.unknown()).optional() }).optional(),
    bot: z.object({ id: z.string().optional(), metadata: z.record(z.string(), z.unknown()).optional() }).optional(),
  }),
});

const PayloadSchema = z.object({
  receivedAt: z.string().optional(),
  event: RecallRealtimeEventSchema,
});

const LiveQuestionDecisionSchema = z.object({
  shouldAsk: z.boolean(),
  question: z.string().optional(),
  reason: z.string(),
  confidence: z.number().int().min(0).max(100).default(0),
  triggerType: z.enum(['possible_contradiction', 'lull_gap', 'direct_mention', 'none']).default('none'),
});
type LiveQuestionDecision = z.infer<typeof LiveQuestionDecisionSchema>;

const LIVE_ORACLE_SYSTEM = `You are the Oracle listening to a live Microsoft Teams meeting for POP Creations / Spruce Line.

Your job is to decide whether to ask ONE short clarification question in the meeting chat.

Ask only when the live discussion reveals one of these:
- a concrete operational rule, exception, handoff, system limitation, or workaround that is unclear;
- a concrete business-process question that the team is actively asking and should not lose in the spoken discussion;
- a possible contradiction with a recent statement in this same meeting;
- a question that would prevent the team from leaving an important process ambiguity unresolved.

Do not ask because of small talk, greetings, filler, status updates, or incomplete thoughts.
Do not ask if the current utterance is too vague.
If the current utterance is already a useful business-process question, it is acceptable to restate that question concisely so it is captured in the meeting chat.
Do not summarize.
Do not answer the meeting.
Do not ask more than one question.
Keep the question under 220 characters, warm, plain text, and psychologically safe.`;

function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({
    adapters: buildStandardAdapters(),
    fallbackOnError: true,
  });
}

function hashString(s: string): string {
  return createHash('sha256').update(s).digest('hex');
}

function normalizeWords(words: z.infer<typeof RecallWordSchema>[]): string {
  return words
    .map((w) => w.text)
    .join(' ')
    .replace(/\s+([,.;:!?])/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

function firstOffsetMs(words: z.infer<typeof RecallWordSchema>[]): number {
  const start = words[0]?.start_timestamp?.relative;
  return typeof start === 'number' ? Math.round(start * 1000) : 0;
}

function clientMessageId(args: {
  botId: string;
  transcriptId: string;
  participantId: string;
  offsetMs: number;
  text: string;
}): string {
  const digest = createHash('sha256').update(args.text).digest('hex').slice(0, 12);
  return `recall-live:${args.botId}:${args.transcriptId}:${args.participantId}:${args.offsetMs}:${digest}`;
}

async function resolveInterviewRoute(db: ReturnType<typeof getDirectDb>): Promise<OracleModelRoute> {
  const resolved = await resolveRouteFromSettings(db, 'interview');
  if (resolved) return resolved;
  const fallback = getOracleRoute(FALLBACK_INTERVIEW_ROUTE_ID);
  if (!fallback) throw new Error(`Fallback interview route ${FALLBACK_INTERVIEW_ROUTE_ID} missing`);
  return fallback;
}

async function findOrCreateLiveChannel(db: ReturnType<typeof getDirectDb>, botId: string): Promise<string> {
  const existing = await db
    .select({ id: channels.id })
    .from(channels)
    .where(sql`${channels.name} = ${`Teams live meeting ${botId}`}`)
    .limit(1);
  if (existing[0]) return existing[0].id;

  const [channel] = await db
    .insert(channels)
    .values({
      name: `Teams live meeting ${botId}`,
      isGroupChat: true,
      status: 'active',
    })
    .returning({ id: channels.id });
  if (!channel) throw new Error('failed to create live Teams channel');
  return channel.id;
}

async function resolveEmployeeId(
  db: ReturnType<typeof getDirectDb>,
  speaker: { name: string | null; email: string | null },
): Promise<string | null> {
  if (speaker.email) {
    const byEmail = await db
      .select({ id: employees.id })
      .from(employees)
      .where(sql`lower(${employees.email}) = ${speaker.email.toLowerCase()}`)
      .limit(1);
    if (byEmail[0]) return byEmail[0].id;
  }
  if (speaker.name) {
    const byName = await db
      .select({ id: employees.id })
      .from(employees)
      .where(sql`lower(${employees.name}) = ${speaker.name.trim().toLowerCase()}`)
      .limit(1);
    if (byName[0]) return byName[0].id;
  }
  return null;
}

async function loadLiveSettings(db: ReturnType<typeof getDirectDb>): Promise<{
  cooldownMinutes: number;
  maxInterjectionsPerHour: number;
  forceModelPass: boolean;
  forcePost: boolean;
  disablePostingLimits: boolean;
  minConfidenceToPost: number;
}> {
  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(sql`${settings.key} in (
      'oracle_cooldown_minutes',
      'max_oracle_interjections_per_hour',
      'teams_live_recall_force_model_pass',
      'teams_live_recall_force_post',
      'teams_live_recall_disable_posting_limits',
      'teams_live_recall_min_confidence_to_post'
    )`);
  const map = new Map(rows.map((r) => [r.key, r.value]));
  return {
    cooldownMinutes:
      typeof map.get('oracle_cooldown_minutes') === 'number'
        ? (map.get('oracle_cooldown_minutes') as number)
        : DEFAULT_COOLDOWN_MINUTES,
    maxInterjectionsPerHour:
      typeof map.get('max_oracle_interjections_per_hour') === 'number'
        ? (map.get('max_oracle_interjections_per_hour') as number)
        : DEFAULT_MAX_INTERJECTIONS_PER_HOUR,
    forceModelPass: map.get('teams_live_recall_force_model_pass') === true,
    forcePost: map.get('teams_live_recall_force_post') === true,
    disablePostingLimits: map.get('teams_live_recall_disable_posting_limits') === true,
    minConfidenceToPost:
      typeof map.get('teams_live_recall_min_confidence_to_post') === 'number'
        ? (map.get('teams_live_recall_min_confidence_to_post') as number)
        : DEFAULT_MIN_CONFIDENCE_TO_POST,
  };
}

async function channelRateState(db: ReturnType<typeof getDirectDb>, channelId: string): Promise<{
  minutesSinceLast: number | null;
  inLastHour: number;
}> {
  const last = await db
    .select({ createdAt: oracleInterventions.createdAt })
    .from(oracleInterventions)
    .where(eq(oracleInterventions.channelId, channelId))
    .orderBy(desc(oracleInterventions.createdAt))
    .limit(1);
  const minutesSinceLast = last[0]
    ? Math.floor((Date.now() - last[0].createdAt.getTime()) / 60_000)
    : null;
  const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
  const countRows = await db
    .select({ c: sql<number>`count(*)::int` })
    .from(oracleInterventions)
    .where(and(eq(oracleInterventions.channelId, channelId), gte(oracleInterventions.createdAt, oneHourAgo)));
  return { minutesSinceLast, inLastHour: countRows[0]?.c ?? 0 };
}

function isWorthModelPass(text: string): boolean {
  if (text.length < 40) return false;
  return /\b(always|never|usually|not always|exception|approval|approved|send|handoff|handover|Coldlion|ERP|China|factory|routing|Burlington|TJX|Ross|Walmart|Disney|Marvel|licensor|customer|sample|production|shipping|cost|workaround|spreadsheet|process)\b/i.test(text);
}

function forcedTestQuestion(text: string): string {
  const cleaned = stripOracleAddress(text).replace(/^test[:,]?\s*/i, '').replace(/\s+/g, ' ').trim();
  if (!cleaned) return 'Quick Oracle test: what should we clarify from the current discussion?';
  return cleaned.endsWith('?') ? cleaned : `${cleaned}?`;
}

function stripOracleAddress(text: string): string {
  return text
    .replace(/^\s*(hey\s+)?oracle[:,]?\s*/i, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function isMetaOracleQuestion(text: string): boolean {
  return /\b(oracle|ai|transcription|transcript|record|recording|listen|listening|eavesdropping|bot)\b/i.test(text);
}

function isDirectBusinessQuestion(text: string): boolean {
  const content = stripOracleAddress(text);
  if (!content.includes('?')) return false;
  if (isMetaOracleQuestion(content)) return false;
  return isWorthModelPass(content);
}

function fallbackClarificationQuestion(text: string): string {
  const content = stripOracleAddress(text).replace(/\s+/g, ' ').trim();
  if (!content) return 'Can we clarify the business-process question that was just raised?';
  return `Can we clarify this process question: ${content}`;
}

async function decideLiveQuestion(args: {
  db: ReturnType<typeof getDirectDb>;
  client: OracleAIClient;
  route: OracleModelRoute;
  channelId: string;
  currentUtterance: string;
  speakerName: string | null;
}): Promise<{ decision: LiveQuestionDecision; modelRunId: string | null }> {
  const recent = await args.db
    .select({ content: messages.content, metadataJson: messages.metadataJson, createdAt: messages.createdAt })
    .from(messages)
    .where(and(eq(messages.channelId, args.channelId), eq(messages.role, 'user'), isNull(messages.deletedAt)))
    .orderBy(desc(messages.createdAt))
    .limit(RECENT_UTTERANCE_LIMIT);

  const recentContext = recent
    .slice()
    .reverse()
    .map((m, i) => {
      const meta = (m.metadataJson ?? {}) as { speaker?: string };
      return `[${i + 1}] ${meta.speaker ? `${meta.speaker}: ` : ''}${m.content}`;
    })
    .join('\n');
  const userContent = `Recent finalized meeting utterances (oldest first):
${recentContext}

Current utterance to evaluate:
${args.speakerName ? `${args.speakerName}: ` : ''}${args.currentUtterance}`;

  const blocks = [
    makeBlock({
      id: 'sys',
      label: 'Teams live Oracle decision system',
      kind: 'stable_system',
      content: LIVE_ORACLE_SYSTEM,
      cacheEligible: true,
      reasonIncluded: 'live Teams meeting interjection decision',
    }),
    makeBlock({
      id: 'utterances',
      label: 'Recent finalized utterances',
      kind: 'dynamic_input',
      content: userContent,
      cacheEligible: false,
      reasonIncluded: 'rolling live Teams transcript window',
    }),
  ];

  const callStartedAt = Date.now();
  let modelRunId: string | null = null;
  try {
    const result = await args.client.runObject<LiveQuestionDecision>({
      taskType: 'interview_chat',
      routeId: args.route.routeId,
      promptVersion: LIVE_PROMPT_VERSION,
      blocks,
      schema: LiveQuestionDecisionSchema,
    });
    const latencyMs = Date.now() - callStartedAt;

    const [contextPack] = await args.db
      .insert(oracleContextPacks)
      .values({
        taskType: 'interview_chat',
        routeId: args.route.routeId,
        promptVersion: LIVE_PROMPT_VERSION,
        stablePrefixHash: hashString(LIVE_ORACLE_SYSTEM),
        dynamicInputHash: hashString(userContent),
        blocksJson: blocks.map((b) => ({
          id: b.id,
          kind: b.kind,
          hash: b.hash,
          tokenEstimate: b.tokenEstimate,
        })),
      })
      .returning({ id: oracleContextPacks.id });
    if (!contextPack) throw new Error('failed to insert oracle_context_packs row');

    const [modelRun] = await args.db
      .insert(modelRuns)
      .values({
        taskType: 'teams-live-interjection',
        model: args.route.modelId,
        provider: args.route.provider,
        promptVersion: LIVE_PROMPT_VERSION,
        inputHash: hashString(LIVE_ORACLE_SYSTEM),
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs,
        success: result.validation.ok,
        error: result.validation.ok ? null : (result.validation.error?.message ?? 'schema validation failed'),
      })
      .returning({ id: modelRuns.id });
    if (!modelRun) throw new Error('failed to insert model_runs row');
    modelRunId = modelRun.id;

    await args.db.insert(modelRunUsageDetails).values({
      modelRunId: modelRun.id,
      contextPackId: contextPack.id,
      routeId: args.route.routeId,
      inputTokens: result.usage.inputTokens ?? null,
      outputTokens: result.usage.outputTokens ?? null,
      cachedInputTokens: result.usage.cachedInputTokens ?? null,
      cacheWriteTokens: result.usage.cacheWriteTokens ?? null,
      reasoningTokens: result.usage.reasoningTokens ?? null,
      providerRequestId: result.usage.providerRequestId ?? null,
      rawUsageJson: (result.usage.rawUsageJson ?? null) as Record<string, unknown> | null,
    });
    await args.db.update(oracleContextPacks).set({ modelRunId: modelRun.id }).where(eq(oracleContextPacks.id, contextPack.id));

    if (!result.validation.ok) {
      return {
        decision: { shouldAsk: false, reason: 'Decision output failed schema validation', confidence: 0, triggerType: 'none' },
        modelRunId,
      };
    }
    return { decision: result.object as LiveQuestionDecision, modelRunId };
  } catch (err) {
    const latencyMs = Date.now() - callStartedAt;
    const message = err instanceof Error ? err.message : String(err);
    try {
      const [modelRun] = await args.db
        .insert(modelRuns)
        .values({
          taskType: 'teams-live-interjection',
          model: args.route.modelId,
          provider: args.route.provider,
          promptVersion: LIVE_PROMPT_VERSION,
          latencyMs,
          success: false,
          error: message,
        })
        .returning({ id: modelRuns.id });
      modelRunId = modelRun?.id ?? null;
    } catch {
      /* swallow */
    }
    return {
      decision: { shouldAsk: false, reason: `Decision call failed: ${message}`, confidence: 0, triggerType: 'none' },
      modelRunId,
    };
  }
}

export const teamsLiveRecallUtteranceTask = task({
  id: 'teams-live-recall-utterance',
  maxDuration: 60 * 2,
  run: async (rawPayload: unknown, { ctx }) => {
    const payload = PayloadSchema.parse(rawPayload);
    if (payload.event.event !== 'transcript.data') {
      return { ok: true, skipped: 'unsupported_event', event: payload.event.event };
    }

    const data = payload.event.data.data;
    const words = data?.words ?? [];
    const text = normalizeWords(words);
    if (!text) return { ok: true, skipped: 'empty_utterance' };

    const botId = payload.event.data.bot?.id ?? 'unknown-bot';
    const transcriptId = payload.event.data.transcript?.id ?? 'unknown-transcript';
    const recordingId = payload.event.data.recording?.id ?? null;
    const participant = data?.participant;
    const participantId = String(participant?.id ?? 'unknown-speaker');
    const speakerName = participant?.name ?? null;
    const speakerEmail = participant?.email ?? null;
    const offsetMs = firstOffsetMs(words);
    const clientId = clientMessageId({ botId, transcriptId, participantId, offsetMs, text });

    const db = getDirectDb();
    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'teams-live-recall-utterance',
        status: 'running',
        startedAt: new Date(),
        inputJson: { botId, transcriptId, recordingId, participantId, text },
      })
      .returning({ id: jobRuns.id });
    if (!jobRun) throw new Error('[teams-live-recall-utterance] failed to insert job_runs row');

    try {
      const channelId = await findOrCreateLiveChannel(db, botId);
      const existing = await db
        .select({ id: messages.id })
        .from(messages)
        .where(and(eq(messages.channelId, channelId), eq(messages.clientMessageId, clientId)))
        .limit(1);
      if (existing[0]) {
        const out = { skipped: 'duplicate', channelId, messageId: existing[0].id };
        await db.update(jobRuns).set({ status: 'complete', finishedAt: new Date(), outputJson: out }).where(eq(jobRuns.id, jobRun.id));
        return { ok: true, ...out };
      }

      const employeeId = await resolveEmployeeId(db, { name: speakerName, email: speakerEmail });
      if (employeeId) {
        await db.insert(channelParticipants).values({ channelId, employeeId }).onConflictDoNothing();
      }

      const [message] = await db
        .insert(messages)
        .values({
          channelId,
          employeeId,
          role: 'user',
          content: text,
          clientMessageId: clientId,
          extractionStatus: 'pending',
          metadataJson: {
            source: 'teams_live_recall',
            botId,
            transcriptId,
            recordingId,
            participantId,
            speaker: speakerName,
            speakerEmail,
            languageCode: data?.language_code ?? null,
            offsetMs,
            resolvedEmployeeId: employeeId,
          },
        })
        .returning({ id: messages.id });

      let postedQuestion: string | null = null;
      let decisionReason = 'heuristic_skip';
      let modelRunId: string | null = null;
      const liveSettings = await loadLiveSettings(db);
      if (liveSettings.forceModelPass || isWorthModelPass(text)) {
        const rateState = await channelRateState(db, channelId);
        const cooldownSeconds =
          rateState.minutesSinceLast == null ? null : rateState.minutesSinceLast * 60;
        const cooldownClear =
          liveSettings.disablePostingLimits ||
          cooldownSeconds == null ||
          cooldownSeconds >= Math.max(MIN_SECONDS_BETWEEN_LIVE_QUESTIONS, liveSettings.cooldownMinutes * 60);
        const rateCapClear =
          liveSettings.disablePostingLimits || rateState.inLastHour < liveSettings.maxInterjectionsPerHour;
        if (cooldownClear && rateCapClear) {
          const client = buildOracleClient();
          const route = await resolveInterviewRoute(db);
          const decisionResult = await decideLiveQuestion({
            db,
            client,
            route,
            channelId,
            currentUtterance: text,
            speakerName,
          });
          modelRunId = decisionResult.modelRunId;
          decisionReason = decisionResult.decision.reason;
          const isForcePostTest = liveSettings.forcePost && /^oracle\s+test[:,]?/i.test(text);
          const shouldPost =
            isForcePostTest ||
            (decisionResult.decision.shouldAsk &&
              decisionResult.decision.confidence >= liveSettings.minConfidenceToPost);
          const questionToPost = isForcePostTest
            ? forcedTestQuestion(text)
            : decisionResult.decision.question?.trim();
          const fallbackQuestion =
            !questionToPost && isDirectBusinessQuestion(text) ? fallbackClarificationQuestion(text) : null;
          const questionToSend = shouldPost ? (questionToPost ?? fallbackQuestion) : fallbackQuestion;
          if (questionToSend) {
            postedQuestion = questionToSend;
            await sendRecallChatMessage({ botId, message: postedQuestion });
            const [assistantMessage] = await db
              .insert(messages)
              .values({
                channelId,
                employeeId: null,
                role: 'assistant',
                content: postedQuestion,
                extractionStatus: 'skipped',
                metadataJson: {
                  source: 'teams_live_recall_interjection',
                  botId,
                  triggerMessageId: message?.id ?? null,
                  modelRunId,
                  decisionReason,
                },
              })
              .returning({ id: messages.id });
            await db.insert(oracleInterventions).values({
              channelId,
              triggerType:
                decisionResult.decision.triggerType === 'possible_contradiction'
                  ? 'possible_contradiction'
                  : 'lull_gap',
              relatedMessageId: message?.id ?? null,
              interjectionMessageId: assistantMessage?.id ?? null,
              confidence: decisionResult.decision.confidence,
              impactScore: null,
              wasLiveInterjection: true,
              reason: fallbackQuestion
                ? `direct_business_question_fallback: ${decisionReason}`
                : isForcePostTest ? `force_post_test: ${decisionReason}` : decisionReason,
            });
          }
        } else {
          decisionReason = cooldownClear ? 'rate_cap_reached' : 'cooldown_active';
        }
      }

      const out = {
        channelId,
        messageId: message?.id ?? null,
        employeeId,
        modelRunId,
        postedQuestion,
        decisionReason,
      };
      await db.update(jobRuns).set({ status: 'complete', finishedAt: new Date(), outputJson: out }).where(eq(jobRuns.id, jobRun.id));
      return { ok: true, ...out };
    } catch (err) {
      await db
        .update(jobRuns)
        .set({
          status: 'failed',
          finishedAt: new Date(),
          error: err instanceof Error ? err.message : String(err),
        })
        .where(eq(jobRuns.id, jobRun.id));
      throw err;
    }
  },
});
