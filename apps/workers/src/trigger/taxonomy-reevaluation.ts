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
import { and, desc, eq, isNotNull, sql } from 'drizzle-orm';
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
  makeBlock,
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
/** Extraction route used for cluster naming. */
const CLUSTER_NAMING_ROUTE_ID = 'vertex_gemini_2_5_flash_extraction_primary';

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
    fallbackOnError: true,
  });
}

// ─────────────────────────────────────────────────────────────────────────
// Cluster naming via cheap LLM call
// ─────────────────────────────────────────────────────────────────────────

type ClusterName = { name: string; purpose: string };

async function nameCluster(
  client: OracleAIClient,
  domainId: string,
  claimSummaries: string[],
): Promise<ClusterName> {
  const topSummaries = claimSummaries.slice(0, 5);
  const listText = topSummaries.map((s, i) => `${i + 1}. ${s}`).join('\n');

  const result = await client.runText({
    taskType: 'admin_explanation',
    routeId: CLUSTER_NAMING_ROUTE_ID,
    promptVersion: CLUSTER_NAMING_PROMPT_VERSION,
    blocks: [
      makeBlock({
        id: 'cluster-naming-system',
        label: 'Cluster naming system prompt',
        kind: 'stable_system',
        content: `You are a taxonomy assistant for a product licensing and manufacturing company.
Given a set of claim summaries that cluster together within a knowledge domain, your job is to assign a short descriptive sub-topic name and one-sentence purpose.

Rules:
- Name: 2–6 words, title case, no punctuation at the end.
- Purpose: one sentence, plain English, describes what claims in this sub-topic have in common.
- Return ONLY valid JSON: {"name": "...", "purpose": "..."}`,
        reasonIncluded: 'cluster naming stable system',
      }),
      makeBlock({
        id: 'cluster-naming-input',
        label: 'Claim summaries for this cluster',
        kind: 'dynamic_input',
        content: `Domain: ${domainId}\n\nClaim summaries:\n${listText}\n\nReturn JSON only.`,
        reasonIncluded: `${topSummaries.length} representative claims`,
      }),
    ],
  });

  try {
    const jsonMatch = /\{[\s\S]*\}/.exec(result.text);
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0]) as unknown;
      if (
        parsed &&
        typeof parsed === 'object' &&
        'name' in parsed &&
        'purpose' in parsed &&
        typeof (parsed as Record<string, unknown>).name === 'string' &&
        typeof (parsed as Record<string, unknown>).purpose === 'string'
      ) {
        return {
          name: String((parsed as Record<string, unknown>).name),
          purpose: String((parsed as Record<string, unknown>).purpose),
        };
      }
    }
  } catch {
    // fall through to fallback
  }

  return {
    name: `${domainId.replace(/_/g, ' ')} cluster`,
    purpose: `A group of related claims within the ${domainId} domain discovered by automated clustering.`,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Per-domain clustering
// ─────────────────────────────────────────────────────────────────────────

type ClaimRow = { id: string; summary: string; embedding: number[] };

async function processReadyDomain(
  db: ReturnType<typeof getDirectDb>,
  client: OracleAIClient,
  domainId: string,
): Promise<number> {
  // Load approved claims with non-null embeddings for this domain.
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
        isNotNull(claims.embedding),
      ),
    )
    .orderBy(desc(claims.impactScore))
    .limit(500);

  const claimRows = rows.filter((r): r is ClaimRow => r.embedding !== null && r.embedding.length > 0);
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

  let proposalsWritten = 0;

  for (const cluster of clusters) {
    if (cluster.memberIndices.length < MIN_CLUSTER_SIZE) continue;

    // Novelty check: skip if too similar to an existing sub-topic.
    const maxExistingSim = existingCentroids.reduce(
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
    const callStart = Date.now();

    try {
      clusterName = await nameCluster(client, domainId, summaries);
      const latencyMs = Date.now() - callStart;

      const [mr] = await db
        .insert(modelRuns)
        .values({
          taskType: 'taxonomy-cluster-naming',
          model: 'gemini-2.5-flash',
          provider: 'vertex',
          promptVersion: CLUSTER_NAMING_PROMPT_VERSION,
          latencyMs,
          success: true,
        })
        .returning({ id: modelRuns.id });
      modelRunId = mr?.id ?? null;
    } catch {
      // Naming failed — use a generic fallback so the cluster isn't lost.
      const latencyMs = Date.now() - callStart;
      clusterName = {
        name: `${domainId.replace(/_/g, ' ')} cluster`,
        purpose: `A group of ${cluster.memberIndices.length} claims within ${domainId} discovered by automated clustering.`,
      };
      await db.insert(modelRuns).values({
        taskType: 'taxonomy-cluster-naming',
        model: 'gemini-2.5-flash',
        provider: 'vertex',
        promptVersion: CLUSTER_NAMING_PROMPT_VERSION,
        latencyMs,
        success: false,
        error: 'cluster naming LLM call failed',
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
                 AND c.embedding IS NOT NULL
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
        ? `No active domain has reached the ${args.activationThreshold}-claim activation threshold (counting only approved claims with embeddings). Sub-topic clustering remains disabled.`
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
