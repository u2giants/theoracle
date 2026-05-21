// Contradiction watcher — spec Part 9.3 + spec 5.1 Rule 1.
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
//   - Every LLM call → model_runs row. Every job → job_runs row.

import { schedules, task, tasks } from '@trigger.dev/sdk/v3';
import { and, eq, inArray, ne, sql } from 'drizzle-orm';
import { z } from 'zod';
import { generateObject } from 'ai';
import { getDirectDb } from '@oracle/db/client';
import {
  claims,
  contradictions,
  gaps,
  modelRuns,
  jobRuns,
  oracleInterventions,
  settings,
} from '@oracle/db/schema';
import { getOpenRouter, embedText } from '@oracle/ai';
import { EMBEDDING_DIM } from '@oracle/shared';

const FALLBACK_MODEL = 'google/gemini-flash';

// Similarity threshold — cosine distance below this may indicate related claims.
// pgvector cosine distance: 0 = identical, 2 = maximally different.
const SIMILARITY_THRESHOLD = 0.35;

// How many similar claims to retrieve per comparison.
const TOP_K = 8;

// ---------------------------------------------------------------------------
// LLM adjudication schema: is this a contradiction?
// ---------------------------------------------------------------------------
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

// ---------------------------------------------------------------------------
// Payload schema.
// ---------------------------------------------------------------------------
const ClaimCheckPayloadSchema = z.object({
  claimId: z.string().uuid(),
});

// ---------------------------------------------------------------------------
// Check a single claim for contradictions with existing approved claims.
// ---------------------------------------------------------------------------
async function checkClaimForContradictions(
  claimId: string,
  triggerRunId: string,
): Promise<{ contradictionsFound: number }> {
  const db = getDirectDb();

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

  // Read settings.
  const [enableLiveSetting, modelSetting] = await Promise.all([
    db
      .select({ value: settings.value })
      .from(settings)
      .where(eq(settings.key, 'enable_live_contradiction_interjections'))
      .limit(1),
    db
      .select({ value: settings.value })
      .from(settings)
      .where(eq(settings.key, 'default_extraction_model'))
      .limit(1),
  ]);

  const enableLiveInterjection = enableLiveSetting[0]?.value === true;
  const modelName =
    (typeof modelSetting[0]?.value === 'string' ? modelSetting[0].value : null) ??
    FALLBACK_MODEL;

  // Ensure the claim has an embedding; compute one if absent.
  let claimEmbedding = claim.embedding;
  if (!claimEmbedding) {
    try {
      const { vector } = await embedText(claim.summary);
      claimEmbedding = vector;
      // Persist the embedding so future comparisons skip this step.
      await db
        .update(claims)
        .set({ embedding: vector })
        .where(eq(claims.id, claimId));
    } catch (embedErr) {
      console.warn('[contradiction-watcher] embedding failed — skipping ANN search', embedErr);
      return { contradictionsFound: 0 };
    }
  }

  // ANN search: top-K approved claims by cosine similarity.
  const vec = `[${claimEmbedding.join(',')}]`;
  const similar = await db.execute<{
    id: string;
    summary: string;
    claim_type: string;
    distance: number;
  }>(
    sql`
      SELECT c.id, c.summary, c.claim_type,
             (c.embedding <=> ${vec}::vector(${EMBEDDING_DIM})) AS distance
      FROM claims c
      WHERE c.status = 'approved'
        AND c.embedding IS NOT NULL
        AND c.id <> ${claimId}
      ORDER BY distance ASC
      LIMIT ${TOP_K};
    `,
  );

  // Filter to semantically close claims only.
  const candidates = similar.filter((r) => r.distance < SIMILARITY_THRESHOLD);
  if (candidates.length === 0) return { contradictionsFound: 0 };

  let contradictionsFound = 0;
  const openrouter = getOpenRouter();
  const model = openrouter(modelName);

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

    if (existing.length > 0) continue; // already recorded

    const userContent = `CLAIM A:\n${claim.summary}\n\nCLAIM B:\n${candidate.summary}`;
    const callStartMs = Date.now();

    try {
      const { object, usage } = await generateObject({
        model,
        schema: ContradictionCheckSchema,
        system: CONTRADICTION_ADJUDICATION_SYSTEM,
        messages: [{ role: 'user', content: userContent }],
        temperature: 0,
      });

      const latencyMs = Date.now() - callStartMs;

      const [modelRun] = await db
        .insert(modelRuns)
        .values({
          taskType: 'contradiction-check',
          model: modelName,
          provider: 'openrouter',
          promptVersion: '1.0.0',
          inputTokens: usage?.inputTokens ?? null,
          outputTokens: usage?.outputTokens ?? null,
          latencyMs,
          success: true,
        })
        .returning({ id: modelRuns.id });

      if (!object.isContradiction) continue;

      contradictionsFound++;

      // Decide: live interjection vs queued (spec 5.1 Rule 1).
      // Most contradictions → queued. Live only if setting is on + severity=high.
      const isLive = enableLiveInterjection && object.severity === 'high';
      const decision = isLive ? 'live_interjection' : 'queued_gap';

      // Insert contradictions row.
      const [contradiction] = await db
        .insert(contradictions)
        .values({
          claimAId: claimId,
          claimBId: candidate.id,
          description: object.explanation,
          severity: object.severity,
          status: 'possible',
          detectionConfidence: 80, // LLM confirmed contradiction
          retrievedClaimIds: candidates.map((c) => c.id),
          interjectionDecision: decision,
          suggestedQuestion: object.suggestedQuestion ?? null,
          createdByModelRunId: modelRun?.id ?? null,
        })
        .returning({ id: contradictions.id });

      // If queued_gap, create a gap asking for clarification.
      if (decision === 'queued_gap' && object.suggestedQuestion) {
        await db.insert(gaps).values({
          gapType: 'contradiction_gap',
          relatedClaimIds: [claimId, candidate.id],
          relatedContradictionId: contradiction?.id,
          questionToAsk: object.suggestedQuestion,
          whyItMatters: `Two approved claims appear to contradict: "${claim.summary}" vs "${candidate.summary}"`,
          priority: object.severity === 'high' ? 'high' : 'medium',
          status: 'open',
          createdByModelRunId: modelRun?.id ?? null,
        });
      }

      // Log oracle_interventions row.
      await db.insert(oracleInterventions).values({
        // No channel context at this point (batch job, not live chat).
        // Use a placeholder — Phase 6 will wire this to the right channel.
        channelId: '00000000-0000-0000-0000-000000000000',
        triggerType: 'possible_contradiction',
        relatedContradictionId: contradiction?.id,
        confidence: 80,
        impactScore: object.severity === 'high' ? 9 : object.severity === 'medium' ? 6 : 3,
        wasLiveInterjection: isLive,
        reason: object.explanation,
      });
    } catch (llmErr) {
      console.error('[contradiction-watcher] LLM adjudication failed:', llmErr);
      await db.insert(modelRuns).values({
        taskType: 'contradiction-check',
        model: modelName,
        provider: 'openrouter',
        promptVersion: '1.0.0',
        latencyMs: Date.now() - callStartMs,
        success: false,
        error: llmErr instanceof Error ? llmErr.message : String(llmErr),
      });
    }
  }

  return { contradictionsFound };
}

// ---------------------------------------------------------------------------
// Per-claim task (triggered after new claim is approved).
// ---------------------------------------------------------------------------
export const contradictionWatcherTask = task({
  id: 'contradiction-watcher',
  maxDuration: 60, // 1 minute per claim (multiple LLM calls)
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

// ---------------------------------------------------------------------------
// Sweep cron: find recently approved claims not yet checked for contradictions
// and trigger individual watcher tasks for each.
// ---------------------------------------------------------------------------
export const contradictionWatcherSweepTask = schedules.task({
  id: 'contradiction-watcher-sweep',
  cron: '0 */4 * * *', // every 4 hours, same as claim-extraction
  maxDuration: 60 * 2,
  run: async (_payload, { ctx }) => {
    const db = getDirectDb();

    // Find approved claims that have no contradiction rows yet.
    // Uses a NOT EXISTS subquery.
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
