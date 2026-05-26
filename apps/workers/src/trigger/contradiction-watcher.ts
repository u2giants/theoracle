// Contradiction watcher — spec Part 9.3 + spec 5.1 Rule 1.
//
// R11.0 refactor: all model calls now go through OracleAIClient with direct
// provider adapters (DECISIONS.md D6 + D9). The previous getOpenRouter() +
// Vercel-AI-SDK generateObject() path is retired. R3 observability rows
// (model_run_usage_details + oracle_context_packs) are written for every
// adjudication call, matching the R6 / R7 / R9 workers.
//
// Two modes:
//   1. Per-claim task: triggered after a new claim is approved, compares it
//      against existing approved claims via pgvector ANN, then calls a small
//      LLM to adjudicate whether a semantic match is actually contradictory.
//   2. Sweep cron (every 4 hours): finds recently approved claims that have
//      not yet been checked and triggers the per-claim task for each.
//
// Spec constraints:
//   - Most possible contradictions should NOT cause live interjections (spec 5.1 Rule 1).
//   - The setting `enable_live_contradiction_interjections` gates live interjection.
//   - When a contradiction is found, the default decision is 'queued_gap' or 'admin_review'.
//   - Log oracle_interventions row if any action is taken.
//   - Every LLM call → model_runs + model_run_usage_details + oracle_context_packs.

import { schedules, task, tasks } from '@trigger.dev/sdk/v3';
import { and, desc, eq, gte, inArray, sql } from 'drizzle-orm';
import { z } from 'zod';
import { createHash } from 'node:crypto';
import { getDirectDb } from '@oracle/db/client';
import {
  claimEvidence,
  claimTopDomains,
  claims,
  contradictions,
  gaps,
  messages,
  modelRuns,
  modelRunUsageDetails,
  jobRuns,
  oracleContextPacks,
  oracleInterventions,
  settings,
} from '@oracle/db/schema';
import {
  AnthropicAdapter,
  OpenAIAdapter,
  OracleAIClient,
  VertexGeminiAdapter,
  embedText,
  getOracleRoute,
  resolveModelRoute,
  makeBlock,
  searchWithRetrievalPlan,
  buildDomainScopedPlan,
  buildGlobalRetrievalPlan,
  type OracleModelRoute,
} from '@oracle/ai';
// EMBEDDING_DIM removed: ANN search now goes through searchWithRetrievalPlan
// which handles embedding dimensions internally.
import {
  decideContradictionInterjection,
  CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD,
} from '@oracle/engines';

// Extraction route is the right home for adjudication too — it's a cheap
// structured-output call. Different from R11's live-interjection drafting,
// which uses the interview route for human-facing warmth.
const FALLBACK_ROUTE_ID = 'vertex_gemini_2_5_flash_extraction_primary';
const FALLBACK_INTERVIEW_ROUTE_ID = 'anthropic_claude_haiku_4_5_interview_primary';

// Default settings if the rows are missing — match seed defaults.
const DEFAULT_ORACLE_COOLDOWN_MINUTES = 10;
const DEFAULT_MAX_ORACLE_INTERJECTIONS_PER_HOUR = 3;

const LIVE_INTERJECTION_PROMPT_VERSION = 'contradiction-live-1.0.0';

const LIVE_INTERJECTION_SYSTEM = `You are the Oracle — an evidence-backed knowledge assistant for POP Creations / Spruce Line.

Two approved claims on file appear to contradict each other. The team is mid-conversation, so surface the conflict as one warm, natural, chat-shaped question that helps resolve it. Match the tone of a colleague who quietly noticed something off.

Hard rules:
- Return ONLY the question text — no preface, no explanation, no metadata.
- 240 characters or less.
- One question only.
- Plain text, no markdown.
- If the suggested question is already concrete, you can use it nearly verbatim.
- Do not name the model, the system, or "contradictions" — just ask which one is right today.`;

// Similarity threshold — cosine distance below this may indicate related claims.
// pgvector cosine distance: 0 = identical, 2 = maximally different.
const SIMILARITY_THRESHOLD = 0.35;

// How many similar claims to retrieve per comparison.
const TOP_K = 8;

const CONTRADICTION_PROMPT_VERSION = 'contradiction-1.0.0';

// ─── Module-singleton OracleAIClient (mirrors R6/R7/R8/R9 workers) ──────────
function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({
    adapters: {
      anthropic: new AnthropicAdapter(),
      vertex: new VertexGeminiAdapter(),
      openai: new OpenAIAdapter(),
    },
    fallbackOnError: true,
  });
}

// ─── LLM adjudication schema: is this a contradiction? ──────────────────────
const ContradictionCheckSchema = z.object({
  isContradiction: z
    .boolean()
    .describe('True if the two claims assert conflicting facts about the same operational reality.'),
  explanation: z
    .string()
    .describe('One-sentence explanation of why this is or is not a contradiction.'),
  severity: z
    .enum(['low', 'medium', 'high'])
    .describe(
      'If a contradiction: how serious the conflict is. low=minor nuance, medium=significant disagreement, high=directly conflicting facts that cannot both be true.',
    ),
  suggestedQuestion: z
    .string()
    .optional()
    .describe(
      'A question that would resolve this contradiction if asked in a conversation.',
    ),
});
type ContradictionCheck = z.infer<typeof ContradictionCheckSchema>;

const CONTRADICTION_ADJUDICATION_SYSTEM = `You are an operational knowledge consistency checker for The Oracle.

Your task: determine whether two operational claims about the same company (POP Creations / Spruce Line) are contradictory.

A CONTRADICTION exists when:
- Both claims address the same process, system, or operational rule, AND
- They assert incompatible facts (both cannot simultaneously be true).

Not a contradiction:
- One claim is a general rule and the other is a recognized exception to that rule.
- The claims describe different aspects of the same process.
- The claims apply to different time periods, departments, or conditions.
- One claim is a refinement or elaboration of the other.

Be precise: "We usually do X" vs "Sometimes we do Y" is NOT a contradiction.
"We always send to China first" vs "China receives it only after US approval" IS a contradiction.

Return only the structured JSON matching the schema.`;

// ─── Payload schema ─────────────────────────────────────────────────────────
const ClaimCheckPayloadSchema = z.object({
  claimId: z.string().uuid(),
});

// ─── Curated route resolver (mirrors claim-extraction.ts) ───────────────────
async function resolveContradictionRoute(
  db: ReturnType<typeof getDirectDb>,
): Promise<OracleModelRoute> {
  const row = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'default_extraction_route'))
    .limit(1);
  const modelIdOrRouteId =
    typeof row[0]?.value === 'string'
      ? (row[0]!.value as string)
      : FALLBACK_ROUTE_ID;
  const resolved =
    resolveModelRoute(modelIdOrRouteId, 'extraction') ?? getOracleRoute(modelIdOrRouteId);
  if (resolved) return resolved;
  const fallback = getOracleRoute(FALLBACK_ROUTE_ID);
  if (!fallback) {
    throw new Error(
      `[contradiction-watcher] settings.default_extraction_route="${modelIdOrRouteId}" not resolvable, and fallback "${FALLBACK_ROUTE_ID}" also missing.`,
    );
  }
  console.warn(
    `[contradiction-watcher] settings.default_extraction_route="${modelIdOrRouteId}" not resolvable; using fallback "${FALLBACK_ROUTE_ID}".`,
  );
  return fallback;
}

// ─── Single adjudication call: one (claimA, claimB) pair via OracleAIClient.
//     Writes all three observability rows on success or failure.
// ─────────────────────────────────────────────────────────────────────────
async function adjudicateOnePair(
  db: ReturnType<typeof getDirectDb>,
  client: OracleAIClient,
  route: OracleModelRoute,
  claimASummary: string,
  claimBSummary: string,
): Promise<{ object: ContradictionCheck | null; modelRunId: string | null; error: string | null }> {
  const userContent = `CLAIM A:\n${claimASummary}\n\nCLAIM B:\n${claimBSummary}`;

  const blocks = [
    makeBlock({
      id: 'sys',
      label: 'Contradiction adjudication system',
      kind: 'stable_system',
      content: CONTRADICTION_ADJUDICATION_SYSTEM,
      cacheEligible: true,
      reasonIncluded: 'spec 5.1 Rule 1 — contradiction adjudication',
    }),
    makeBlock({
      id: 'pair',
      label: 'Claim pair',
      kind: 'dynamic_input',
      content: userContent,
      cacheEligible: false,
      reasonIncluded: 'current claim pair under adjudication',
    }),
  ];

  const callStartedAt = Date.now();
  let modelRunId: string | null = null;
  try {
    const result = await client.runObject<ContradictionCheck>({
      taskType: 'contradiction_detection',
      routeId: route.routeId,
      promptVersion: CONTRADICTION_PROMPT_VERSION,
      blocks,
      schema: ContradictionCheckSchema,
    });
    const latencyMs = Date.now() - callStartedAt;

    // Observability — three rows like every other R6+ worker.
    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values({
        taskType: 'contradiction_detection',
        routeId: route.routeId,
        promptVersion: CONTRADICTION_PROMPT_VERSION,
        stablePrefixHash: hashString(CONTRADICTION_ADJUDICATION_SYSTEM),
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

    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'contradiction-check',
        model: route.modelId,
        provider: route.provider,
        promptVersion: CONTRADICTION_PROMPT_VERSION,
        inputHash: hashString(CONTRADICTION_ADJUDICATION_SYSTEM),
        inputTokens: result.usage.inputTokens ?? null,
        outputTokens: result.usage.outputTokens ?? null,
        latencyMs,
        success: result.validation.ok,
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

    if (!result.validation.ok) {
      return { object: null, modelRunId, error: result.validation.error?.message ?? 'schema validation failed' };
    }
    return { object: result.object as ContradictionCheck, modelRunId, error: null };
  } catch (err) {
    const latencyMs = Date.now() - callStartedAt;
    const message = err instanceof Error ? err.message : String(err);
    // Best-effort failure row so admin dashboards see the attempt.
    try {
      const [modelRun] = await db
        .insert(modelRuns)
        .values({
          taskType: 'contradiction-check',
          model: route.modelId,
          provider: route.provider,
          promptVersion: CONTRADICTION_PROMPT_VERSION,
          latencyMs,
          success: false,
          error: message,
        })
        .returning({ id: modelRuns.id });
      modelRunId = modelRun?.id ?? null;
    } catch {
      /* observability write itself failed — swallow to surface the real error */
    }
    return { object: null, modelRunId, error: message };
  }
}

function hashString(s: string): string {
  return createHash('sha256').update(s).digest('hex');
}

// ─── Check a single claim for contradictions with existing approved claims.
// ─────────────────────────────────────────────────────────────────────────
async function checkClaimForContradictions(
  claimId: string,
  _triggerRunId: string,
): Promise<{ contradictionsFound: number }> {
  const db = getDirectDb();
  const client = buildOracleClient();

  // Load the claim.
  const [claim] = await db
    .select()
    .from(claims)
    .where(and(eq(claims.id, claimId), eq(claims.status, 'approved')))
    .limit(1);

  if (!claim) {
    console.log(`[contradiction-watcher] claim ${claimId} not found or not approved — skipping`);
    return { contradictionsFound: 0 };
  }

  // Read settings + resolve routes.
  const [
    enableLiveSetting,
    cooldownSetting,
    rateCapSetting,
    extractionRoute,
    interviewRoute,
  ] = await Promise.all([
    db
      .select({ value: settings.value })
      .from(settings)
      .where(eq(settings.key, 'enable_live_contradiction_interjections'))
      .limit(1),
    db
      .select({ value: settings.value })
      .from(settings)
      .where(eq(settings.key, 'oracle_cooldown_minutes'))
      .limit(1),
    db
      .select({ value: settings.value })
      .from(settings)
      .where(eq(settings.key, 'max_oracle_interjections_per_hour'))
      .limit(1),
    resolveContradictionRoute(db),
    resolveInterviewRoute(db),
  ]);

  const enableLiveInterjection = enableLiveSetting[0]?.value === true;
  const oracleCooldownMinutes =
    typeof cooldownSetting[0]?.value === 'number'
      ? (cooldownSetting[0]!.value as number)
      : DEFAULT_ORACLE_COOLDOWN_MINUTES;
  const maxOracleInterjectionsPerHour =
    typeof rateCapSetting[0]?.value === 'number'
      ? (rateCapSetting[0]!.value as number)
      : DEFAULT_MAX_ORACLE_INTERJECTIONS_PER_HOUR;
  // Use extractionRoute for adjudication; interviewRoute for live drafting.
  const route = extractionRoute;

  // Ensure the claim has an embedding; compute one if absent.
  let claimEmbedding = claim.embedding;
  if (!claimEmbedding) {
    try {
      const { vector } = await embedText(claim.summary);
      claimEmbedding = vector;
      await db.update(claims).set({ embedding: vector }).where(eq(claims.id, claimId));
    } catch (embedErr) {
      console.warn('[contradiction-watcher] embedding failed — skipping ANN search', embedErr);
      return { contradictionsFound: 0 };
    }
  }

  // ANN search via searchWithRetrievalPlan — enforces the RetrievalPlan
  // metadata pre-filter contract (no silent global search).
  //
  // Domain hints come from the target claim's claim_top_domains rows so that
  // vendor-manual noise and unrelated licensor claims are suppressed.
  // If the claim has no taxonomy tags yet (pre-backfill), we fall back to
  // buildGlobalRetrievalPlan (searchScope='global_explicit') and log a warning.
  //
  // Note: searchWithRetrievalPlan calls embedText(claim.summary) internally.
  // The embedding computed/stored above is kept for DB persistence; the slight
  // redundancy is acceptable for a background worker.
  // TODO: add precomputedVector support to RetrievalPlan to avoid the double-embed.
  const domainRows = await db
    .select({ topDomainId: claimTopDomains.topDomainId })
    .from(claimTopDomains)
    .where(eq(claimTopDomains.claimId, claimId));
  const domainHints = domainRows.map((r) => r.topDomainId);

  const annPlan =
    domainHints.length > 0
      ? buildDomainScopedPlan(claim.summary, domainHints, { topK: TOP_K })
      : (() => {
          console.warn('[contradiction-watcher] claim has no domain tags — falling back to global ANN', {
            claimId,
            hint: 'Run the taxonomy re-evaluation worker to assign claim_top_domains.',
          });
          return buildGlobalRetrievalPlan(claim.summary, { topK: TOP_K });
        })();

  const annResults = await searchWithRetrievalPlan(db, annPlan);
  // Exclude the target claim itself (searchWithRetrievalPlan doesn't know about it).
  const candidates = annResults.filter(
    (r) => r.id !== claimId && r.distance < SIMILARITY_THRESHOLD,
  );
  if (candidates.length === 0) return { contradictionsFound: 0 };

  let contradictionsFound = 0;

  for (const candidate of candidates) {
    // Skip if this pair already has a contradictions row.
    const existing = await db
      .select({ id: contradictions.id })
      .from(contradictions)
      .where(
        and(
          inArray(contradictions.claimAId, [claimId, candidate.id]),
          inArray(contradictions.claimBId, [claimId, candidate.id]),
        ),
      )
      .limit(1);
    if (existing.length > 0) continue;

    const { object, modelRunId, error } = await adjudicateOnePair(
      db,
      client,
      route,
      claim.summary,
      candidate.summary,
    );
    if (error || !object) {
      if (error) console.error('[contradiction-watcher] adjudication failed:', error);
      continue;
    }
    if (!object.isContradiction) continue;

    contradictionsFound++;

    // Resolve channel context — pick the channel containing the most recent
    // claim_evidence row for either claim. If neither claim has any
    // claim_evidence with a source_message_id (document-only evidence),
    // the contradiction stays as a contradictions row but cannot be live-
    // posted — there's nowhere to post.
    const channelCtx = await findChannelForClaimPair(db, claimId, candidate.id);

    // Compute the inputs to decideContradictionInterjection.
    let cooldownMin: number | null = null;
    let interjectionsInLastHour = 0;
    if (channelCtx) {
      const lastInt = await db
        .select({ createdAt: oracleInterventions.createdAt })
        .from(oracleInterventions)
        .where(eq(oracleInterventions.channelId, channelCtx.channelId))
        .orderBy(desc(oracleInterventions.createdAt))
        .limit(1);
      cooldownMin =
        lastInt.length > 0 && lastInt[0]
          ? Math.floor((Date.now() - lastInt[0].createdAt.getTime()) / 60_000)
          : null;
      const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000);
      const countRows = await db
        .select({ c: sql<number>`count(*)::int` })
        .from(oracleInterventions)
        .where(
          and(
            eq(oracleInterventions.channelId, channelCtx.channelId),
            gte(oracleInterventions.createdAt, oneHourAgo),
          ),
        );
      interjectionsInLastHour = countRows[0]?.c ?? 0;
    }

    const interjectionDecisionResult = decideContradictionInterjection({
      detectionConfidence: CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD,
      severity: object.severity,
      enableLiveContradictionInterjections: enableLiveInterjection,
      minutesSinceLastOracleInterjection: cooldownMin,
      oracleCooldownMinutes,
      interjectionsInLastHour,
      maxOracleInterjectionsPerHour,
      suggestedQuestion: object.suggestedQuestion ?? null,
    });

    // If we have no channel to post in, force the decision to queue.
    const willLive =
      interjectionDecisionResult.decision === 'live' && channelCtx !== null;
    const decisionLabel = willLive ? 'live_interjection' : 'queued_gap';

    const [contradiction] = await db
      .insert(contradictions)
      .values({
        claimAId: claimId,
        claimBId: candidate.id,
        description: object.explanation,
        severity: object.severity,
        status: 'possible',
        detectionConfidence: CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD,
        retrievedClaimIds: candidates.map((c) => c.id),
        interjectionDecision: decisionLabel,
        suggestedQuestion: object.suggestedQuestion ?? null,
        createdByModelRunId: modelRunId,
      })
      .returning({ id: contradictions.id });

    // Live branch: draft a one-liner via the interview route and post.
    let interjectionMessageId: string | null = null;
    if (willLive && channelCtx && object.suggestedQuestion) {
      try {
        const drafted = await draftContradictionInterjection(
          db,
          client,
          interviewRoute,
          {
            suggestedQuestion: object.suggestedQuestion,
            claimASummary: claim.summary,
            claimBSummary: candidate.summary,
            explanation: object.explanation,
          },
        );
        const [postedMessage] = await db
          .insert(messages)
          .values({
            channelId: channelCtx.channelId,
            employeeId: null,
            role: 'assistant',
            content: drafted.text,
            metadataJson: {
              source: 'contradiction-interjection',
              contradictionId: contradiction?.id,
              modelRunId: drafted.modelRunId,
              decisionReason: interjectionDecisionResult.reason,
            },
          })
          .returning({ id: messages.id });
        interjectionMessageId = postedMessage?.id ?? null;
      } catch (drafterr) {
        console.error('[contradiction-watcher] live drafting failed:', drafterr);
        // Fall through — record the intervention as not-live; the gap still gets queued below.
      }
    }

    // If queued (decision wasn't live, or live drafting failed), create a gap.
    if (!interjectionMessageId && object.suggestedQuestion) {
      await db.insert(gaps).values({
        gapType: 'contradiction_gap',
        relatedClaimIds: [claimId, candidate.id],
        relatedContradictionId: contradiction?.id,
        questionToAsk: object.suggestedQuestion,
        whyItMatters: `Two approved claims appear to contradict: "${claim.summary}" vs "${candidate.summary}"`,
        priority: object.severity === 'high' ? 'high' : 'medium',
        status: 'open',
        createdByModelRunId: modelRunId,
      });
    }

    // Log oracle_interventions row. channelId is the real channel if we found
    // one, or the all-zero placeholder if the contradiction is between
    // claims sourced only from documents (no chat channel).
    await db.insert(oracleInterventions).values({
      channelId: channelCtx?.channelId ?? '00000000-0000-0000-0000-000000000000',
      triggerType: 'possible_contradiction',
      relatedContradictionId: contradiction?.id,
      interjectionMessageId,
      confidence: CONTRADICTION_LIVE_CONFIDENCE_THRESHOLD,
      impactScore: object.severity === 'high' ? 9 : object.severity === 'medium' ? 6 : 3,
      wasLiveInterjection: interjectionMessageId !== null,
      reason: interjectionDecisionResult.decision === 'live'
        ? interjectionDecisionResult.reason
        : `${interjectionDecisionResult.reason} [details: ${object.explanation}]`,
    });
  }

  return { contradictionsFound };
}

// ─── Per-claim task ─────────────────────────────────────────────────────────
export const contradictionWatcherTask = task({
  id: 'contradiction-watcher',
  maxDuration: 60,
  run: async (payload: z.infer<typeof ClaimCheckPayloadSchema>, { ctx }) => {
    ClaimCheckPayloadSchema.parse(payload);
    const db = getDirectDb();

    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'contradiction-watcher',
        status: 'running',
        startedAt: new Date(),
        inputJson: { claimId: payload.claimId },
      })
      .returning({ id: jobRuns.id });

    if (!jobRun) throw new Error('[contradiction-watcher] failed to insert job_runs row');

    try {
      const result = await checkClaimForContradictions(payload.claimId, ctx.run.id);
      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: result })
        .where(eq(jobRuns.id, jobRun.id));
      return { ok: true, claimId: payload.claimId, ...result };
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

// ─── Sweep cron ─────────────────────────────────────────────────────────────
export const contradictionWatcherSweepTask = schedules.task({
  id: 'contradiction-watcher-sweep',
  cron: '0 */4 * * *',
  maxDuration: 60 * 2,
  run: async (_payload, { ctx: _ctx }) => {
    const db = getDirectDb();

    const unchecked = await db.execute<{ id: string }>(
      sql`
        SELECT c.id
        FROM claims c
        WHERE c.status = 'approved'
          AND c.embedding IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM contradictions ct
            WHERE ct.claim_a_id = c.id OR ct.claim_b_id = c.id
          )
        ORDER BY c.created_at DESC
        LIMIT 50;
      `,
    );

    if (unchecked.length === 0) {
      return { ok: true, triggered: 0 };
    }

    let triggered = 0;
    for (const row of unchecked) {
      try {
        await tasks.trigger('contradiction-watcher', { claimId: row.id });
        triggered++;
      } catch (err) {
        console.error(`[contradiction-watcher-sweep] failed to trigger for claim ${row.id}:`, err);
      }
    }

    return { ok: true, triggered, total: unchecked.length };
  },
});

// ─── R11.3 helpers ──────────────────────────────────────────────────────────

/**
 * Resolve the curated INTERVIEW route (Anthropic Claude Haiku 4.5 by default).
 * Used for human-facing contradiction interjection drafting.
 */
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
  const resolved =
    resolveModelRoute(modelIdOrRouteId, 'interview') ?? getOracleRoute(modelIdOrRouteId);
  if (resolved) return resolved;
  const fallback = getOracleRoute(FALLBACK_INTERVIEW_ROUTE_ID);
  if (!fallback) {
    throw new Error(
      `[contradiction-watcher] settings.default_interview_route="${modelIdOrRouteId}" not resolvable, and fallback "${FALLBACK_INTERVIEW_ROUTE_ID}" also missing.`,
    );
  }
  console.warn(
    `[contradiction-watcher] settings.default_interview_route="${modelIdOrRouteId}" not in catalog; using fallback "${FALLBACK_INTERVIEW_ROUTE_ID}".`,
  );
  return fallback;
}

/**
 * Find a chat channel to post a live interjection in for a pair of contradicting
 * claims. Picks the channel containing the most-recent claim_evidence
 * source_message for either claim. Returns null if neither claim has
 * message-sourced evidence (e.g. both came purely from document chunks).
 */
async function findChannelForClaimPair(
  db: ReturnType<typeof getDirectDb>,
  claimAId: string,
  claimBId: string,
): Promise<{ channelId: string } | null> {
  const rows = await db
    .select({
      channelId: messages.channelId,
      createdAt: messages.createdAt,
    })
    .from(claimEvidence)
    .innerJoin(messages, eq(claimEvidence.sourceMessageId, messages.id))
    .where(inArray(claimEvidence.claimId, [claimAId, claimBId]))
    .orderBy(desc(messages.createdAt))
    .limit(1);
  return rows.length > 0 && rows[0] ? { channelId: rows[0].channelId } : null;
}

/**
 * Draft the live interjection message via the interview route (Anthropic
 * Claude Haiku 4.5). Writes the standard observability triple (context pack,
 * model_runs, model_run_usage_details).
 */
async function draftContradictionInterjection(
  db: ReturnType<typeof getDirectDb>,
  client: OracleAIClient,
  route: OracleModelRoute,
  input: {
    suggestedQuestion: string;
    claimASummary: string;
    claimBSummary: string;
    explanation: string;
  },
): Promise<{ text: string; modelRunId: string | null }> {
  const userMessage = `Suggested question (use this as-is or tighten if needed): ${input.suggestedQuestion}

Why it matters (context for tone — do NOT include in the output):
Two claims on file appear to contradict:
- Claim A: ${input.claimASummary}
- Claim B: ${input.claimBSummary}
Explanation: ${input.explanation}`;

  const blocks = [
    makeBlock({
      id: 'sys',
      label: 'Contradiction live interjection system prompt',
      kind: 'stable_system',
      content: LIVE_INTERJECTION_SYSTEM,
      cacheEligible: true,
      reasonIncluded: 'spec 5.1 Rule 1 — live contradiction interjection drafting',
    }),
    makeBlock({
      id: 'input',
      label: 'Contradiction input',
      kind: 'dynamic_input',
      content: userMessage,
      cacheEligible: false,
      reasonIncluded: 'current contradiction pair under live drafting',
    }),
  ];

  const callStartedAt = Date.now();
  let modelRunId: string | null = null;
  try {
    const result = await client.runText({
      taskType: 'interview_chat',
      routeId: route.routeId,
      promptVersion: LIVE_INTERJECTION_PROMPT_VERSION,
      blocks,
      providerOptions: { temperature: 0.4 },
    });
    const latencyMs = Date.now() - callStartedAt;

    const [contextPack] = await db
      .insert(oracleContextPacks)
      .values({
        taskType: 'interview_chat',
        routeId: route.routeId,
        promptVersion: LIVE_INTERJECTION_PROMPT_VERSION,
        stablePrefixHash: hashString(LIVE_INTERJECTION_SYSTEM),
        dynamicInputHash: hashString(userMessage),
        blocksJson: blocks.map((b) => ({
          id: b.id,
          kind: b.kind,
          hash: b.hash,
          tokenEstimate: b.tokenEstimate,
        })),
      })
      .returning({ id: oracleContextPacks.id });
    if (!contextPack) throw new Error('failed to insert oracle_context_packs row');

    const [modelRun] = await db
      .insert(modelRuns)
      .values({
        taskType: 'contradiction-live-interjection',
        model: route.modelId,
        provider: route.provider,
        promptVersion: LIVE_INTERJECTION_PROMPT_VERSION,
        inputHash: hashString(LIVE_INTERJECTION_SYSTEM),
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
          taskType: 'contradiction-live-interjection',
          model: route.modelId,
          provider: route.provider,
          promptVersion: LIVE_INTERJECTION_PROMPT_VERSION,
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
