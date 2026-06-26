// Recall.ai live Teams utterance worker.
//
// This processes finalized `transcript.data` events, not partial/provisional
// STT hypotheses. Each finalized utterance is persisted as a `messages` row for
// evidence/backfill, then a tightly gated Oracle pass decides whether a useful
// one-question interjection should be posted back to the Teams meeting chat.

import { task } from '@trigger.dev/sdk/v3';
import { and, desc, eq, gte, inArray, isNull, sql } from 'drizzle-orm';
import { z } from 'zod';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  channelParticipants,
  channels,
  claimEvidence,
  employees,
  jobRuns,
  messages,
  modelRuns,
  modelRunUsageDetails,
  oracleContextPacks,
  oracleInterventions,
  sectionClaims,
  settings,
} from '@oracle/db/schema';
import {
  OracleAIClient,
  buildRetrievalPlanFromQuery,
  buildStandardAdapters,
  getBrainSectionSnippets,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  searchWithRetrievalPlan,
  type RetrievalPlan,
  type OracleModelRoute,
  type RelevantClaim,
  type RouteCandidate,
} from '@oracle/ai';
import { sendRecallChatMessage, RecallTransientSendError } from '../lib/recall';

const LIVE_PROMPT_VERSION = 'teams-live-recall-1.1.0';
const DEFAULT_COOLDOWN_MINUTES = 10;
const DEFAULT_MAX_INTERJECTIONS_PER_HOUR = 3;
const DEFAULT_MIN_CONFIDENCE_TO_POST = 70;
const RECENT_UTTERANCE_LIMIT = 18;
const LIVE_RETRIEVAL_TOP_K = 5;
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
  evidenceClaimIds: z.array(z.string()).default([]),
});
type LiveQuestionDecision = z.infer<typeof LiveQuestionDecisionSchema>;

type LiveRetrievedClaimContext = RelevantClaim & {
  evidenceId: string | null;
  evidenceQuote: string | null;
  sourceMessageId: string | null;
  sourceDocumentChunkId: string | null;
  sourceExternalRecordId: string | null;
};

type LiveRetrievalContext = {
  plan: RetrievalPlan;
  claims: LiveRetrievedClaimContext[];
  brainSections: Array<{ sectionId: string; title: string; markdown: string }>;
  contextText: string;
  includedClaimIds: string[];
  includedEvidenceIds: string[];
  includedBrainSectionIds: string[];
};

const LIVE_ORACLE_SYSTEM = `You are the Oracle listening to a live Microsoft Teams meeting for POP Creations / Spruce Line.

Your job is to decide whether to ask ONE short clarification question in the meeting chat.

Ask only when the live discussion reveals one of these:
- a concrete operational rule, exception, handoff, system limitation, or workaround that is unclear;
- a concrete business-process question that the team is actively asking and should not lose in the spoken discussion;
- a possible contradiction with a recent statement in this same meeting;
- a question that would prevent the team from leaving an important process ambiguity unresolved.

You may also be given an "Approved company knowledge" block: already-approved operational claims retrieved for the current utterance. Use it only to judge the live discussion:
- prefer asking when the current utterance conflicts with, updates, or leaves a concrete gap against that approved knowledge;
- when the current utterance is a direct business-process question, the approved knowledge sharpens the clarification question — it never suppresses capturing the question;
- never recite the approved knowledge into the meeting chat and never include claim IDs in the question text;
- list the claim IDs that actually influenced your decision in evidenceClaimIds (empty if none did).

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

async function resolveInterviewCandidates(db: ReturnType<typeof getDirectDb>): Promise<RouteCandidate[]> {
  const resolved = await resolveRouteCandidates(db, 'interview');
  for (const skipped of resolved.skipped) {
    console.warn('[teams-live-recall] skipped interview route candidate', skipped);
  }
  return resolved.candidates;
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

async function channelRateState(
  // Accepts a db or transaction handle so the rate state can be re-read inside
  // the per-channel advisory lock.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  db: any,
  channelId: string,
): Promise<{
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

function truncateForPrompt(text: string, maxChars: number): string {
  const normalized = text.replace(/\s+/g, ' ').trim();
  if (normalized.length <= maxChars) return normalized;
  return `${normalized.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`;
}

async function loadEvidenceForClaims(
  db: ReturnType<typeof getDirectDb>,
  claimIds: string[],
): Promise<Map<string, {
  evidenceId: string;
  exactQuote: string;
  sourceMessageId: string | null;
  sourceDocumentChunkId: string | null;
  sourceExternalRecordId: string | null;
}>> {
  if (claimIds.length === 0) return new Map();

  const rows = await db
    .select({
      evidenceId: claimEvidence.id,
      claimId: claimEvidence.claimId,
      exactQuote: claimEvidence.exactQuote,
      sourceMessageId: claimEvidence.sourceMessageId,
      sourceDocumentChunkId: claimEvidence.sourceDocumentChunkId,
      sourceExternalRecordId: claimEvidence.sourceExternalRecordId,
      createdAt: claimEvidence.createdAt,
    })
    .from(claimEvidence)
    .where(inArray(claimEvidence.claimId, claimIds))
    .orderBy(desc(claimEvidence.createdAt));

  const byClaim = new Map<string, {
    evidenceId: string;
    exactQuote: string;
    sourceMessageId: string | null;
    sourceDocumentChunkId: string | null;
    sourceExternalRecordId: string | null;
  }>();
  for (const row of rows) {
    if (byClaim.has(row.claimId)) continue;
    byClaim.set(row.claimId, {
      evidenceId: row.evidenceId,
      exactQuote: row.exactQuote,
      sourceMessageId: row.sourceMessageId,
      sourceDocumentChunkId: row.sourceDocumentChunkId,
      sourceExternalRecordId: row.sourceExternalRecordId,
    });
  }
  return byClaim;
}

async function buildLiveRetrievalContext(args: {
  db: ReturnType<typeof getDirectDb>;
  currentUtterance: string;
  recentContext: string;
}): Promise<LiveRetrievalContext | null> {
  const retrievalQuery = [
    stripOracleAddress(args.currentUtterance),
    args.recentContext ? `Recent meeting context:\n${args.recentContext}` : '',
  ].filter(Boolean).join('\n\n');
  if (!retrievalQuery) return null;

  try {
    const plan = buildRetrievalPlanFromQuery(retrievalQuery, { topK: LIVE_RETRIEVAL_TOP_K });
    const claims = await searchWithRetrievalPlan(args.db, plan);
    const evidenceByClaim = await loadEvidenceForClaims(args.db, claims.map((c) => c.id));
    const sectionRows = claims.length > 0
      ? await args.db
          .select({ sectionId: sectionClaims.sectionId })
          .from(sectionClaims)
          .where(inArray(sectionClaims.claimId, claims.map((c) => c.id)))
          .limit(2)
      : [];
    const sectionIds = Array.from(new Set(sectionRows.map((r) => r.sectionId))).slice(0, 2);
    const brainSnippets = await getBrainSectionSnippets(args.db, sectionIds);

    const enrichedClaims: LiveRetrievedClaimContext[] = claims.map((claim) => {
      const evidence = evidenceByClaim.get(claim.id);
      return {
        ...claim,
        evidenceId: evidence?.evidenceId ?? null,
        evidenceQuote: evidence?.exactQuote ?? null,
        sourceMessageId: evidence?.sourceMessageId ?? null,
        sourceDocumentChunkId: evidence?.sourceDocumentChunkId ?? null,
        sourceExternalRecordId: evidence?.sourceExternalRecordId ?? null,
      };
    });

    const claimsText = enrichedClaims.length > 0
      ? enrichedClaims.map((claim, i) => {
          const quote = claim.evidenceQuote
            ? ` Evidence: "${truncateForPrompt(claim.evidenceQuote, 220)}"`
            : '';
          return `[C${i + 1}] ${truncateForPrompt(claim.summary, 260)} (impact ${claim.impactScore}, confidence ${claim.confidenceScore}).${quote}`;
        }).join('\n')
      : 'No approved claims matched this live context.';
    const brainText = brainSnippets.length > 0
      ? brainSnippets.map((section, i) =>
          `[B${i + 1}] ${section.title}: ${truncateForPrompt(section.markdown, 420)}`,
        ).join('\n')
      : 'No linked Brain sections found for retrieved claims.';
    const contextText = `Approved claims:\n${claimsText}\n\nLinked Brain sections:\n${brainText}`;

    return {
      plan,
      claims: enrichedClaims,
      brainSections: brainSnippets,
      contextText,
      includedClaimIds: enrichedClaims.map((c) => c.id),
      includedEvidenceIds: enrichedClaims.flatMap((c) => c.evidenceId ? [c.evidenceId] : []),
      includedBrainSectionIds: brainSnippets.map((s) => s.sectionId),
    };
  } catch (err) {
    const cause = err instanceof Error && err.cause instanceof Error ? ` cause: ${err.cause.message}` : '';
    console.warn(
      '[teams-live-recall-utterance] retrieval failed; deciding without approved-knowledge context',
      `${err instanceof Error ? err.message.slice(0, 300) : String(err)}${cause}`,
    );
    return null;
  }
}

async function decideLiveQuestion(args: {
  db: ReturnType<typeof getDirectDb>;
  client: OracleAIClient;
  route: OracleModelRoute;
  routeCandidates: RouteCandidate[];
  channelId: string;
  currentUtterance: string;
  speakerName: string | null;
}): Promise<{
  decision: LiveQuestionDecision;
  modelRunId: string | null;
  retrievalContext: LiveRetrievalContext | null;
}> {
  const recent = await args.db
    .select({ id: messages.id, content: messages.content, metadataJson: messages.metadataJson, createdAt: messages.createdAt })
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
  const retrievalContext = await buildLiveRetrievalContext({
    db: args.db,
    currentUtterance: args.currentUtterance,
    recentContext,
  });
  const retrievalContextText = retrievalContext?.contextText ?? 'Approved-knowledge retrieval was unavailable for this utterance.';
  const userContent = `Recent finalized meeting utterances (oldest first):
${recentContext}

Retrieved approved Oracle knowledge:
${retrievalContextText}

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
    ...(retrievalContext
      ? [
          makeBlock({
            id: 'retrieved-claims',
            label: 'Retrieved approved Oracle knowledge',
            kind: 'retrieved_context' as const,
            content: retrievalContext.contextText,
            cacheEligible: false,
            reasonIncluded: 'approved claims and Brain sections retrieved for live Teams decision',
          }),
        ]
      : []),
    makeBlock({
      id: 'utterances',
      label: 'Recent finalized utterances',
      kind: 'dynamic_input',
      content: userContent,
      cacheEligible: false,
      reasonIncluded: 'rolling live Teams transcript window',
    }),
  ];

  const [contextPack] = await args.db
    .insert(oracleContextPacks)
    .values({
      taskType: 'interview_chat',
      routeId: args.route.routeId,
      promptVersion: LIVE_PROMPT_VERSION,
      stablePrefixHash: hashString(LIVE_ORACLE_SYSTEM),
      retrievedContextHash: retrievalContext ? hashString(retrievalContext.contextText) : null,
      dynamicInputHash: hashString(userContent),
      blocksJson: blocks.map((b) => ({
        id: b.id,
        kind: b.kind,
        hash: b.hash,
        tokenEstimate: b.tokenEstimate,
      })),
      selectedDomains: retrievalContext
        ? retrievalContext.plan.searchScope === 'domain_filtered'
          ? retrievalContext.plan.topDomainHints
          : [retrievalContext.plan.searchScope === 'global_explicit' ? '_global_explicit' : '_global_fallback']
        : [],
      selectedSourceTypes: retrievalContext?.includedBrainSectionIds.length
        ? ['approved_claim', 'brain_section', 'message']
        : retrievalContext ? ['approved_claim', 'message'] : ['message'],
      selectedProcessStages: retrievalContext?.plan.processStageHints ?? [],
      selectedEntityIds: retrievalContext?.plan.requiredEntities.map((e) => `${e.entityType}:${e.canonicalValue}`) ?? [],
      includedMessageIds: recent.map((m) => m.id),
      includedClaimIds: retrievalContext?.includedClaimIds ?? [],
    })
    .returning({ id: oracleContextPacks.id });
  if (!contextPack) throw new Error('failed to insert oracle_context_packs row');

  const callStartedAt = Date.now();
  let modelRunId: string | null = null;
  try {
    const result = await args.client.runObject<LiveQuestionDecision>({
      taskType: 'interview_chat',
      routeId: args.route.routeId,
      promptVersion: LIVE_PROMPT_VERSION,
      blocks,
      schema: LiveQuestionDecisionSchema,
      routeCandidates: args.routeCandidates,
    });
    const latencyMs = Date.now() - callStartedAt;
    const actualRouteId = result.routeId ?? args.route.routeId;
    const actualProvider = result.provider ?? args.route.provider;
    const actualModelId = result.modelId ?? args.route.modelId;

    const [modelRun] = await args.db
      .insert(modelRuns)
      .values({
        taskType: 'teams-live-interjection',
        model: actualModelId,
        provider: actualProvider,
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
      db: args.db,
      metadata: result,
      taskType: 'teams-live-interjection',
      slot: 'interview',
      contextPackId: contextPack.id,
      modelRunId: modelRun.id,
    });
    await args.db.update(oracleContextPacks).set({ modelRunId: modelRun.id }).where(eq(oracleContextPacks.id, contextPack.id));

    if (!result.validation.ok) {
      return {
        decision: { shouldAsk: false, reason: 'Decision output failed schema validation', confidence: 0, triggerType: 'none', evidenceClaimIds: [] },
        modelRunId,
        retrievalContext,
      };
    }
    return { decision: result.object as LiveQuestionDecision, modelRunId, retrievalContext };
  } catch (err) {
    const latencyMs = Date.now() - callStartedAt;
    const message = err instanceof Error ? err.message : String(err);
    await logAllCandidatesFailedAttempts({
      db: args.db,
      error: err,
      taskType: 'teams-live-interjection',
      slot: 'interview',
      contextPackId: contextPack.id,
    });
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
      if (modelRunId) {
        await args.db.insert(modelRunUsageDetails).values({
          modelRunId,
          contextPackId: contextPack.id,
          routeId: args.route.routeId,
        });
        await args.db
          .update(oracleContextPacks)
          .set({ modelRunId })
          .where(eq(oracleContextPacks.id, contextPack.id));
      }
    } catch {
      /* swallow */
    }
    return {
      decision: { shouldAsk: false, reason: `Decision call failed: ${message}`, confidence: 0, triggerType: 'none', evidenceClaimIds: [] },
      modelRunId,
      retrievalContext: null,
    };
  }
}

export const teamsLiveRecallUtteranceTask = task({
  id: 'teams-live-recall-utterance',
  maxDuration: 60 * 2,
  // Retries disabled: a retry re-runs the task, but the persisted utterance
  // makes the dedup short-circuit the retry, silently dropping any interjection
  // (and a successful post would otherwise risk duplication). Transient send
  // failures are swallowed in-run so the task completes. (Override of default=3.)
  retry: { maxAttempts: 1 },
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
      let retrievedClaimIds: string[] = [];
      let evidenceClaimIds: string[] = [];
      let retrievalContext: LiveRetrievalContext | null = null;
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
          const routeCandidates = await resolveInterviewCandidates(db);
          const route = routeCandidates[0]!.route;
          const decisionResult = await decideLiveQuestion({
            db,
            client,
            route,
            routeCandidates,
            channelId,
            currentUtterance: text,
            speakerName,
          });
          modelRunId = decisionResult.modelRunId;
          retrievalContext = decisionResult.retrievalContext;
          retrievedClaimIds = retrievalContext?.includedClaimIds ?? [];
          decisionReason = decisionResult.decision.reason;
          // Only trust evidence IDs the model could actually have seen.
          const retrievedIdSet = new Set(retrievedClaimIds);
          evidenceClaimIds = decisionResult.decision.evidenceClaimIds.filter((id) => retrievedIdSet.has(id));
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
            // Commit under a per-channel advisory lock with a re-read of the
            // rate/cooldown state so two concurrent utterance runs can't both
            // blow past the per-hour interjection cap for the same channel.
            await db.transaction(async (tx) => {
              const lockRes = await tx.execute<{ locked: boolean }>(
                sql`SELECT pg_try_advisory_xact_lock(hashtext(${channelId})) AS locked`,
              );
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              const lockRows: Array<{ locked: boolean }> = (lockRes as any).rows ?? (lockRes as any);
              if (lockRows[0]?.locked !== true) {
                decisionReason = `skipped: lock_contended (${decisionReason})`;
                return;
              }

              // Re-read rate/cooldown state inside the lock and re-check the
              // limits (unless posting limits are disabled).
              if (!liveSettings.disablePostingLimits) {
                const fresh = await channelRateState(tx, channelId);
                const freshCooldownSeconds =
                  fresh.minutesSinceLast == null ? null : fresh.minutesSinceLast * 60;
                const freshCooldownClear =
                  freshCooldownSeconds == null ||
                  freshCooldownSeconds >=
                    Math.max(MIN_SECONDS_BETWEEN_LIVE_QUESTIONS, liveSettings.cooldownMinutes * 60);
                const freshRateCapClear = fresh.inLastHour < liveSettings.maxInterjectionsPerHour;
                if (!freshCooldownClear || !freshRateCapClear) {
                  decisionReason = freshRateCapClear ? 'cooldown_active' : 'rate_cap_reached';
                  return;
                }
              }

              // Post to Recall. A TRANSIENT send failure is logged and
              // swallowed so the task COMPLETES — re-throwing would let Trigger
              // retry the task, and the utterance dedup would then short-circuit
              // the retry, silently dropping the interjection. Non-transient
              // errors still throw.
              try {
                await sendRecallChatMessage({ botId, message: questionToSend });
              } catch (sendErr) {
                if (sendErr instanceof RecallTransientSendError) {
                  decisionReason = `send_failed_transient: ${sendErr.message.slice(0, 200)}`;
                  console.warn(
                    `[teams-live-recall-utterance] transient Recall send failure; completing without retry: ${sendErr.message}`,
                  );
                  return;
                }
                throw sendErr;
              }
              postedQuestion = questionToSend;

              const [assistantMessage] = await tx
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
                    retrievedClaimIds,
                    evidenceClaimIds,
                    retrievalContext: retrievalContext
                      ? {
                          searchScope: retrievalContext.plan.searchScope,
                          topDomainHints: retrievalContext.plan.topDomainHints,
                          excludedTopDomains: retrievalContext.plan.excludedTopDomains ?? [],
                          excludedDocumentClasses: retrievalContext.plan.excludedDocumentClasses ?? [],
                          includedClaimIds: retrievalContext.includedClaimIds,
                          includedEvidenceIds: retrievalContext.includedEvidenceIds,
                          includedBrainSectionIds: retrievalContext.includedBrainSectionIds,
                        }
                      : null,
                  },
                })
                .returning({ id: messages.id });
              await tx.insert(oracleInterventions).values({
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
        retrievedClaimIds,
        evidenceClaimIds,
        retrieval: retrievalContext
          ? {
              searchScope: retrievalContext.plan.searchScope,
              topDomainHints: retrievalContext.plan.topDomainHints,
              claimCount: retrievalContext.claims.length,
              evidenceCount: retrievalContext.includedEvidenceIds.length,
              brainSectionCount: retrievalContext.includedBrainSectionIds.length,
            }
          : null,
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
