// R10.5 — Taxonomy re-evaluation worker.
//
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R10.5 task 1+2.
//
// Goal: periodically scan promoted claims, detect that the current taxonomy
// no longer fits the data, and WRITE PROPOSALS to `taxonomy_proposals` for
// admin review. The worker MUST NEVER auto-mutate the taxonomy — that
// invariant is the whole reason this dashboard + queue exists.
//
// What this worker WILL do once implementations land per
// docs/oracle/07-knowledge-segmentation.md:
//   1. Per-domain density clustering on stored claim embeddings.
//   2. Cluster naming via a cheap synthesis call.
//   3. Overlap analysis against current `knowledge_sub_topics.centroid` rows.
//   4. Drift detection per claim (cosine distance to its current sub-topic).
//   5. Cross-domain pattern check (clusters whose membership spans 2+
//      top-domains → suggest reassignment / merge / split).
//   6. Proposal writing to `taxonomy_proposals` only (no other tables).
//   7. Proposal payloads matching the TaxonomyProposalPayload contract in
//      docs/oracle/07-knowledge-segmentation.md.
//
// What this worker DOES today:
//   - Inserts a job_runs row.
//   - Counts how many promoted `claims` exist per top-level domain (via
//     `claim_top_domains`).
//   - Logs activation thresholds — sub-topics shouldn't start activating
//     until each active domain has at least N claims (configurable; default
//     30 — small enough to feel useful in early operation, large enough
//     that density clustering produces meaningful centroids).
//   - Returns a clear "not enough data yet" outcome.
//
// As real claims accumulate, the clustering / drift / proposal-writing
// pipeline becomes a substitution for the current early-exit path. The
// admin dashboard at `/admin/taxonomy/proposals` is the consumer.

import { schedules, task } from '@trigger.dev/sdk/v3';
import { sql } from 'drizzle-orm';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import { jobRuns } from '@oracle/db';

const ManualTriggerPayload = z.object({
  // Optional override: only re-evaluate one domain.
  topDomainId: z.string().optional(),
  // Optional override of the activation threshold.
  activationThreshold: z.number().int().positive().optional(),
});

const DEFAULT_ACTIVATION_THRESHOLD = 30;

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
  proposalsWritten: 0; // intentional — see file header
  note: string;
}> {
  const db = getDirectDb();

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
    // Count promoted-status claims per active top-level domain.
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
    const domainsReady = rows.filter((r) => Number(r.claim_count) >= args.activationThreshold).length;
    const domainsBelowThreshold = rows.length - domainsReady;

    const note =
      domainsReady === 0
        ? `No active domain has reached the ${args.activationThreshold}-claim activation threshold. Sub-topic clustering remains disabled. As approved-claim volume grows, this worker will start writing taxonomy proposals.`
        : `${domainsReady} of ${rows.length} active domains are over the activation threshold. Density clustering / drift detection / proposal writing pipeline lands in a follow-up commit; this scheduled run is a no-op for now.`;

    const output = {
      ok: true as const,
      trigger: args.trigger,
      totalClaims,
      domainsScanned: rows.length,
      domainsReady,
      domainsBelowThreshold,
      proposalsWritten: 0 as const,
      note,
    };

    await db
      .update(jobRuns)
      .set({
        status: 'complete',
        finishedAt: new Date(),
        outputJson: { ...output, perDomainCounts: rows },
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
// brain-synthesis-scheduled task at 6 AM Monday). This is the
// "maturity-based cadence — weekly during early learning" position from
// the retrofit packet.
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
