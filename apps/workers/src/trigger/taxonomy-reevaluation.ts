// R10.5 — Taxonomy re-evaluation worker.
//
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R10.5 task 1+2.
//
// Goal: periodically scan promoted claims, detect that the current taxonomy
// no longer fits the data, and WRITE PROPOSALS to `taxonomy_proposals` for
// admin review. The worker MUST NEVER auto-mutate the taxonomy — that
// invariant is the whole reason this dashboard + queue exists.
//
// What this worker does (R10.5 full implementation):
//   1. Per-domain density clustering on stored claim embeddings (k-means,
//      cosine distance, k = min(8, max(2, round(sqrt(N/4)))), 30 iterations).
//   2. Cluster naming via a cheap synthesis call (Gemini Flash extraction
//      route). Top-5 claim summaries per cluster are sent as evidence.
//   3. Overlap analysis: clusters whose centroid has cosine similarity >=
//      NOVELTY_COSINE_THRESHOLD to any existing knowledge_sub_topics.centroid
//      row for the same domain are skipped (already represented).
//   4. Proposal writing to `taxonomy_proposals` only (no other tables).
//   5. Proposal payloads match the TaxonomyProposalPayload contract in
//      docs/oracle/07-knowledge-segmentation.md.
//
// Domains below DEFAULT_ACTIVATION_THRESHOLD (30 approved claims with
// non-null embeddings) are skipped — clustering centroids need enough
// mass to be meaningful. See file header comment for rationale on 30 vs
// the spec's conservative 100.
//
// The admin dashboard at `/admin/taxonomy/proposals` is the consumer.

import { schedules, task } from '@trigger.dev/sdk/v3';
import { and, desc, eq, sql } from 'drizzle-orm';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import {
  claims,
  claimTopDomains,
  jobRuns,
  knowledgeSubTopics,
  knowledgeTopDomains,
  modelRuns,
  taxonomyProposals,
} from '@oracle/db';
import {
  OracleAIClient,
  buildStandardAdapters,
  embedMany,
  logAllCandidatesFailedAttempts,
  logModelRunAttempts,
  makeBlock,
  resolveRouteCandidates,
  type OracleObjectResult,
  type RouteCandidate,
} from '@oracle/ai';

// ─────────────────────────────────────────────────────────────────────────
// Constants
// ─────────────────────────────────────────────────────────────────────────

const DEFAULT_ACTIVATION_THRESHOLD = 30;
/** Minimum members a cluster must have to be considered for a proposal. */
const MIN_CLUSTER_SIZE = 3;
/** Cosine similarity above which a new cluster is considered already represented by an existing sub-topic. */
const NOVELTY_COSINE_THRESHOLD = 0.88;
/** Max clusters per domain — prevents proposal flooding on large domains. */
const MAX_K = 8;
/** LLM prompt version for observability. */
const CLUSTER_NAMING_PROMPT_VERSION = '1.0.0';
// ─────────────────────────────────────────────────────────────────────────
// K-means helpers (pure TS, no new deps)
// ─────────────────────────────────────────────────────────────────────────

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += (a[i] ?? 0) * (b[i] ?? 0);
    normA += (a[i] ?? 0) ** 2;
    normB += (b[i] ?? 0) ** 2;
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

function computeCentroid(vectors: number[][]): number[] {
  if (vectors.length === 0) return [];
  const dim = vectors[0]!.length;
  const centroid = new Array<number>(dim).fill(0);
  for (const v of vectors) {
    for (let i = 0; i < dim; i++) centroid[i]! += (v[i] ?? 0) / vectors.length;
  }
  return centroid;
}

function kMeans(
  vectors: number[][],
  k: number,
  maxIter = 30,
): Array<{ centroid: number[]; memberIndices: number[] }> {
  if (vectors.length === 0 || k <= 0) return [];
  k = Math.min(k, vectors.length);

  // k-means++ initialisation
  const centroids: number[][] = [vectors[Math.floor(Math.random() * vectors.length)]!];
  while (centroids.length < k) {
    const dists = vectors.map((v) => {
      const bestSim = centroids.reduce((m, c) => Math.max(m, cosineSimilarity(v, c)), -Infinity);
      return Math.max(0, 1 - bestSim);
    });
    const totalDist = dists.reduce((s, d) => s + d, 0);
    let rand = Math.random() * totalDist;
    let chosen = 0;
    for (let i = 0; i < dists.length; i++) {
      rand -= dists[i]!;
      if (rand <= 0) { chosen = i; break; }
    }
    centroids.push(vectors[chosen]!);
  }

  let assignments = new Array<number>(vectors.length).fill(0);

  for (let iter = 0; iter < maxIter; iter++) {
    const newAssignments = vectors.map((v) => {
      let bestIdx = 0, bestSim = -Infinity;
      for (let c = 0; c < centroids.length; c++) {
        const sim = cosineSimilarity(v, centroids[c]!);
        if (sim > bestSim) { bestSim = sim; bestIdx = c; }
      }
      return bestIdx;
    });

    for (let c = 0; c < k; c++) {
      const members = vectors.filter((_, i) => newAssignments[i] === c);
      if (members.length > 0) centroids[c] = computeCentroid(members);
    }

    if (newAssignments.every((a, i) => a === assignments[i])) break;
    assignments = newAssignments;
  }

  return Array.from({ length: k }, (_, c) => ({
    centroid: centroids[c]!,
    memberIndices: assignments.reduce<number[]>((acc, a, i) => { if (a === c) acc.push(i); return acc; }, []),
  }));
}

// ─────────────────────────────────────────────────────────────────────────
// OracleAIClient factory
// ─────────────────────────────────────────────────────────────────────────

function buildOracleClient(): OracleAIClient {
  return new OracleAIClient({
    adapters: buildStandardAdapters(),
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Cluster naming via cheap LLM call
// ─────────────────────────────────────────────────────────────────────────

type ClusterName = { name: string; purpose: string };

const ClusterNameSchema = z.object({
  name: z.string(),
  purpose: z.string(),
});

async function nameCluster(
  client: OracleAIClient,
  routeCandidates: RouteCandidate[],
  domainId: string,
  claimSummaries: string[],
): Promise<ClusterName & { result: OracleObjectResult<ClusterName> }> {
  const topSummaries = claimSummaries.slice(0, 5);
  const listText = topSummaries.map((s, i) => `${i + 1}. ${s}`).join('\n');
  const route = routeCandidates[0]!.route;

  const result = await client.runObject<ClusterName>({
    taskType: 'admin_explanation',
    routeId: route.routeId,
    promptVersion: CLUSTER_NAMING_PROMPT_VERSION,
    schema: ClusterNameSchema,
    routeCandidates,
    blocks: [
      makeBlock({
        id: 'cluster-naming-system',
        label: 'Cluster naming system prompt',
        kind: 'stable_system',
        content: `You are a taxonomy assistant for a product licensing and manufacturing company.
Given a set of claim summaries that cluster together within a knowledge domain, your job is to assign a short descriptive sub-topic name and one-sentence purpose.

Rules:
- Name: 2–6 words, title case, no punctuation at the end.
- Purpose: one sentence, plain English, describes what claims in this sub-topic have in common.`,
        // Stable system instructions are identical across every cluster/domain
        // naming call, so this prefix is cache-eligible.
        cacheEligible: true,
        reasonIncluded: 'cluster naming stable system',
      }),
      makeBlock({
        id: 'cluster-naming-input',
        label: 'Claim summaries for this cluster',
        kind: 'dynamic_input',
        content: `Domain: ${domainId}\n\nClaim summaries:\n${listText}`,
        reasonIncluded: `${topSummaries.length} representative claims`,
      }),
    ],
  });

  if (result.validation.ok) {
    const obj = result.object;
    if (obj.name.trim() && obj.purpose.trim()) {
      return { name: obj.name, purpose: obj.purpose, result };
    }
  }

  const validationMessage = result.validation.ok
    ? 'cluster naming output was empty'
    : result.validation.error.message;
  throw new Error(validationMessage);
}

// ─────────────────────────────────────────────────────────────────────────
// Per-domain clustering
// ─────────────────────────────────────────────────────────────────────────

type ClaimRow = { id: string; summary: string; embedding: number[] };

async function ensureClaimEmbeddings(
  db: ReturnType<typeof getDirectDb>,
  rows: Array<{ id: string; summary: string; embedding: number[] | null }>,
): Promise<Array<{ id: string; summary: string; embedding: number[] | null }>> {
  const missing = rows.filter((r) => r.embedding === null || r.embedding.length === 0);
  if (missing.length === 0) return rows;

  const embedded = await embedMany(missing.map((r) => r.summary));
  if (embedded.fallback) {
    throw new Error(
      '[taxonomy-reevaluation] OPENAI_API_KEY is unavailable; refusing to cluster zero-vector fallback embeddings',
    );
  }

  const byId = new Map<string, number[]>();
  for (const [index, row] of missing.entries()) {
    const vector = embedded.vectors[index];
    if (!vector) throw new Error(`[taxonomy-reevaluation] missing embedding result for claim ${row.id}`);
    byId.set(row.id, vector);
    await db.update(claims).set({ embedding: vector }).where(eq(claims.id, row.id));
  }

  return rows.map((row) => ({
    ...row,
    embedding: row.embedding && row.embedding.length > 0 ? row.embedding : byId.get(row.id) ?? null,
  }));
}

async function processReadyDomain(
  db: ReturnType<typeof getDirectDb>,
  client: OracleAIClient,
  domainId: string,
): Promise<number> {
  // Load approved claims for this domain and backfill missing embeddings
  // before clustering. Freshly-approved historical claims often predate claim
  // embeddings; treating those as "not ready" made the general-purpose picker
  // path impossible to exercise.
  const rows = await db
    .select({
      id: claims.id,
      summary: claims.summary,
      embedding: claims.embedding,
    })
    .from(claims)
    .innerJoin(claimTopDomains, eq(claimTopDomains.claimId, claims.id))
    .where(
      and(
        eq(claimTopDomains.topDomainId, domainId),
        eq(claims.status, 'approved'),
      ),
    )
    .orderBy(desc(claims.impactScore))
    .limit(500);

  const rowsWithEmbeddings = await ensureClaimEmbeddings(db, rows);
  const claimRows = rowsWithEmbeddings.filter(
    (r): r is ClaimRow => r.embedding !== null && r.embedding.length > 0,
  );
  if (claimRows.length < MIN_CLUSTER_SIZE) return 0;

  const k = Math.min(MAX_K, Math.max(2, Math.round(Math.sqrt(claimRows.length / 4))));
  const vectors = claimRows.map((r) => r.embedding);
  const clusters = kMeans(vectors, k);

  // Load existing approved/pending sub-topic centroids for this domain to
  // detect novelty. Skip clusters that are already represented.
  const existingSubTopics = await db
    .select({ centroid: knowledgeSubTopics.centroid })
    .from(knowledgeSubTopics)
    .where(eq(knowledgeSubTopics.topDomainId, domainId));

  const existingCentroids = existingSubTopics
    .map((st) => st.centroid)
    .filter((c): c is number[] => c !== null && c.length > 0);

  // Also dedupe against still-PENDING create_sub_topic proposals for this
  // domain. Without this, repeated re-evaluation runs (before an admin acts on
  // the queue) flood the queue with duplicate proposals for the same cluster.
  const pendingProposalRows = await db
    .select({ payload: taxonomyProposals.payload })
    .from(taxonomyProposals)
    .where(
      and(
        eq(taxonomyProposals.proposalType, 'create_sub_topic'),
        eq(taxonomyProposals.status, 'pending'),
      ),
    );
  const pendingCentroids = pendingProposalRows
    .map((r) => {
      const p = (r.payload ?? {}) as { topDomainId?: unknown; clusterCentroid?: unknown };
      if (p.topDomainId !== domainId) return null;
      const centroid = p.clusterCentroid;
      return Array.isArray(centroid) && centroid.every((n) => typeof n === 'number')
        ? (centroid as number[])
        : null;
    })
    .filter((c): c is number[] => c !== null && c.length > 0);
  const noveltyCentroids = [...existingCentroids, ...pendingCentroids];

  let proposalsWritten = 0;
  const routeResolution = await resolveRouteCandidates(db, 'general');
  for (const skipped of routeResolution.skipped) {
    console.warn('[taxonomy-reevaluation] skipped general route candidate', skipped);
  }
  const routeCandidates = routeResolution.candidates;
  const primaryRoute = routeCandidates[0]!.route;

  for (const cluster of clusters) {
    if (cluster.memberIndices.length < MIN_CLUSTER_SIZE) continue;

    // Novelty check: skip if too similar to an existing sub-topic OR an
    // already-pending create_sub_topic proposal for this domain.
    const maxExistingSim = noveltyCentroids.reduce(
      (max, existing) => Math.max(max, cosineSimilarity(cluster.centroid, existing)),
      -Infinity,
    );
    if (maxExistingSim >= NOVELTY_COSINE_THRESHOLD) continue;

    // Build evidence list (top members by original claim order, already
    // sorted desc by impact_score above).
    const memberClaims = cluster.memberIndices
      .sort((a, b) => a - b)
      .slice(0, 5)
      .map((i) => claimRows[i]!)
      .filter(Boolean);

    const summaries = memberClaims.map((c) => c.summary);
    let clusterName: ClusterName;
    let modelRunId: string | null = null;
    let namingStatus: 'model_named' | 'model_failed_generic_name' = 'model_named';
    const callStart = Date.now();

    try {
      const named = await nameCluster(client, routeCandidates, domainId, summaries);
      clusterName = { name: named.name, purpose: named.purpose };
      const latencyMs = Date.now() - callStart;
      const actualProvider = named.result.provider ?? primaryRoute.provider;
      const actualModelId = named.result.modelId ?? primaryRoute.modelId;

      const [mr] = await db
        .insert(modelRuns)
        .values({
          taskType: 'taxonomy-cluster-naming',
          model: actualModelId,
          provider: actualProvider,
          promptVersion: CLUSTER_NAMING_PROMPT_VERSION,
          latencyMs,
          success: true,
        })
        .returning({ id: modelRuns.id });
      modelRunId = mr?.id ?? null;
      if (modelRunId) {
        await logModelRunAttempts({
          db,
          metadata: named.result,
          taskType: 'taxonomy-cluster-naming',
          slot: 'general',
          modelRunId,
        });
      }
    } catch (err) {
      // Naming failed. Keep the proposal, but mark the generic name explicitly
      // in payload so reviewers know the LLM label did not succeed.
      const latencyMs = Date.now() - callStart;
      const message = err instanceof Error ? err.message : String(err);
      namingStatus = 'model_failed_generic_name';
      clusterName = {
        name: `${domainId.replace(/_/g, ' ')} cluster`,
        purpose: `A group of ${cluster.memberIndices.length} claims within ${domainId} discovered by automated clustering.`,
      };
      await logAllCandidatesFailedAttempts({
        db,
        error: err,
        taskType: 'taxonomy-cluster-naming',
        slot: 'general',
      });
      await db.insert(modelRuns).values({
        taskType: 'taxonomy-cluster-naming',
        model: primaryRoute.modelId,
        provider: primaryRoute.provider,
        promptVersion: CLUSTER_NAMING_PROMPT_VERSION,
        latencyMs,
        success: false,
        error: message,
      });
    }

    // Build proposal payload per TaxonomyProposalPayload contract in
    // docs/oracle/07-knowledge-segmentation.md.
    // Extra fields (topDomainId, clusterCentroid, representativeClaimIds) are
    // not part of the base contract but are consumed by the
    // taxonomy-reclassification worker to create the sub-topic row.
    const payload = {
      proposedName: clusterName.name,
      oneSentencePurpose: clusterName.purpose,
      proposalReason: `Automated k-means clustering (k=${k}) on ${claimRows.length} approved claim embeddings in domain "${domainId}" identified a cluster of ${cluster.memberIndices.length} claims with no sufficiently similar existing sub-topic (max existing centroid similarity: ${maxExistingSim === -Infinity ? 'none' : maxExistingSim.toFixed(3)}).`,
      topDomainId: domainId,
      namingStatus,
      clusterCentroid: cluster.centroid,
      representativeEvidence: memberClaims.map((c) => ({
        sourceType: 'claim' as const,
        sourceId: c.id,
        shortSnippet: c.summary.slice(0, 200),
        whyRepresentative: 'Selected as top member of this cluster by claim order (impact score desc)',
      })),
      representativeClaimIds: memberClaims.map((c) => c.id),
      commonEntities: [],
      affectedCounts: { claims: cluster.memberIndices.length },
      suggestedRetrievalExclusions: [],
      recommendedAction: 'approve' as const,
      recommendedActionReason: `Cluster has ${cluster.memberIndices.length} members and appears meaningfully distinct from existing sub-topics.`,
      confidence: Math.min(0.95, 0.5 + cluster.memberIndices.length / 50),
    };

    await db.insert(taxonomyProposals).values({
      proposalType: 'create_sub_topic',
      payload,
      proposedByModelRunId: modelRunId ?? undefined,
      status: 'pending',
    });

    proposalsWritten++;
  }

  return proposalsWritten;
}

// ─────────────────────────────────────────────────────────────────────────
// Main logic
// ─────────────────────────────────────────────────────────────────────────

const ManualTriggerPayload = z.object({
  topDomainId: z.string().optional(),
  activationThreshold: z.number().int().positive().optional(),
});

type DomainCountRow = {
  top_domain_id: string;
  claim_count: number;
};

async function runReevaluation(args: {
  triggerRunId: string;
  trigger: 'scheduled' | 'manual';
  topDomainFilter?: string;
  activationThreshold: number;
}): Promise<{
  ok: true;
  trigger: 'scheduled' | 'manual';
  totalClaims: number;
  domainsScanned: number;
  domainsReady: number;
  domainsBelowThreshold: number;
  proposalsWritten: number;
  note: string;
}> {
  const db = getDirectDb();
  const client = buildOracleClient();

  const [jobRun] = await db
    .insert(jobRuns)
    .values({
      triggerRunId: args.triggerRunId,
      jobType: 'taxonomy-reevaluation',
      status: 'running',
      startedAt: new Date(),
      inputJson: {
        trigger: args.trigger,
        topDomainFilter: args.topDomainFilter ?? null,
        activationThreshold: args.activationThreshold,
      },
    })
    .returning({ id: jobRuns.id });
  if (!jobRun) throw new Error('[taxonomy-reevaluation] failed to insert job_runs row');

  try {
    const domainFilter = args.topDomainFilter ? sql`AND d.id = ${args.topDomainFilter}` : sql``;
    const result = await db.execute(sql`
      SELECT d.id AS top_domain_id,
             COALESCE((
               SELECT COUNT(DISTINCT ctd.claim_id)
               FROM claim_top_domains ctd
               JOIN claims c ON c.id = ctd.claim_id
               WHERE ctd.top_domain_id = d.id
                 AND c.status = 'approved'
             ), 0) AS claim_count
      FROM knowledge_top_domains d
      WHERE d.is_active = true
      ${domainFilter}
      ORDER BY d.display_order
    `);
    const rows = [...result] as unknown as DomainCountRow[];

    const totalClaims = rows.reduce((sum, r) => sum + Number(r.claim_count), 0);
    const readyRows = rows.filter((r) => Number(r.claim_count) >= args.activationThreshold);
    const domainsReady = readyRows.length;
    const domainsBelowThreshold = rows.length - domainsReady;

    let proposalsWritten = 0;
    const perDomainResults: Record<string, { claimsWithEmbeddings: number; proposals: number }> = {};

    for (const row of readyRows) {
      const written = await processReadyDomain(db, client, row.top_domain_id);
      proposalsWritten += written;
      perDomainResults[row.top_domain_id] = {
        claimsWithEmbeddings: Number(row.claim_count),
        proposals: written,
      };
    }

    const note =
      domainsReady === 0
        ? `No active domain has reached the ${args.activationThreshold}-claim activation threshold. Sub-topic clustering remains disabled.`
        : `Clustered ${domainsReady} of ${rows.length} active domains. Wrote ${proposalsWritten} create_sub_topic proposal(s) for admin review.`;

    const output = {
      ok: true as const,
      trigger: args.trigger,
      totalClaims,
      domainsScanned: rows.length,
      domainsReady,
      domainsBelowThreshold,
      proposalsWritten,
      note,
    };

    await db
      .update(jobRuns)
      .set({
        status: 'complete',
        finishedAt: new Date(),
        outputJson: { ...output, perDomainCounts: rows, perDomainResults },
      })
      .where(sql`id = ${jobRun.id}`);

    return output;
  } catch (err) {
    await db
      .update(jobRuns)
      .set({
        status: 'failed',
        finishedAt: new Date(),
        error: err instanceof Error ? err.message : String(err),
      })
      .where(sql`id = ${jobRun.id}`);
    throw err;
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Tasks
// ─────────────────────────────────────────────────────────────────────────

// Scheduled cadence: weekly, every Monday at 7 AM (one hour after the
// brain-synthesis-scheduled task at 6 AM Monday).
export const taxonomyReevaluationScheduledTask = schedules.task({
  id: 'taxonomy-reevaluation',
  cron: '0 7 * * 1',
  maxDuration: 60 * 10,
  // Retries disabled: scheduled cron; a retry would re-cluster and could write
  // duplicate proposals. The next weekly run is the natural retry.
  retry: { maxAttempts: 1 },
  run: async (_payload, { ctx }) => {
    return runReevaluation({
      triggerRunId: ctx.run.id,
      trigger: 'scheduled',
      activationThreshold: DEFAULT_ACTIVATION_THRESHOLD,
    });
  },
});

// Manual trigger from admin / API.
export const taxonomyReevaluationManualTask = task({
  id: 'taxonomy-reevaluation-manual',
  maxDuration: 60 * 10,
  run: async (payload: z.infer<typeof ManualTriggerPayload>, { ctx }) => {
    const parsed = ManualTriggerPayload.parse(payload);
    return runReevaluation({
      triggerRunId: ctx.run.id,
      trigger: 'manual',
      topDomainFilter: parsed.topDomainId,
      activationThreshold: parsed.activationThreshold ?? DEFAULT_ACTIVATION_THRESHOLD,
    });
  },
});
