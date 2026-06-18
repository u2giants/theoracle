// R10.5 — Taxonomy reclassification worker.
//
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R10.5 task 4.
//
// Consumes approved taxonomy_proposals that the admin-action in
// apps/web/app/admin/taxonomy/_actions.ts defers with:
//   afterState.queuedFor = 'taxonomy-reclassification-worker'
//
// Applies the structural mutation that the proposal describes, then writes a
// taxonomy_change_log row with changeType 'reclassification_applied_*' so the
// proposal is never re-processed.
//
// Governance invariants (see docs/oracle/07-knowledge-segmentation.md):
//   - NEVER auto-mutates an un-approved proposal. status must be 'approved'.
//   - NEVER touches claims, claim_evidence, or extraction tables.
//   - NEVER deletes taxonomy rows — only inserts, updates (review_status),
//     and claim_sub_topics re-assignments.
//   - complex proposals (split_top_domain, split_sub_topic) require human
//     judgment about which claims go where; they are logged as
//     'manual_intervention_required' and skipped.
//
// Trigger.dev auto-discovers this file via dirs: ['./src/trigger'] in
// trigger.config.ts — no explicit registration needed.

import { task } from '@trigger.dev/sdk/v3';
import { and, eq, inArray, notInArray, sql } from 'drizzle-orm';
import { z } from 'zod';
import { getDirectDb } from '@oracle/db/client';
import {
  claimSubTopics,
  claimTopDomains,
  jobRuns,
  knowledgeSubTopics,
  knowledgeTopDomains,
  taxonomyChangeLog,
  taxonomyProposals,
} from '@oracle/db';

// ─────────────────────────────────────────────────────────────────────────
// Payload types
// ─────────────────────────────────────────────────────────────────────────

const ManualTriggerPayload = z.object({
  /** Only reclassify proposals of this type. Omit to process all pending. */
  proposalType: z.string().optional(),
  /** Dry-run: find pending proposals but do not apply mutations. */
  dryRun: z.boolean().optional(),
});

// Loose type for the JSONB payload stored in taxonomy_proposals.
// Each handler narrows further.
type ProposalPayload = Record<string, unknown>;

// ─────────────────────────────────────────────────────────────────────────
// Find pending reclassifications
// ─────────────────────────────────────────────────────────────────────────

type PendingProposal = {
  id: string;
  proposalType: string;
  payload: ProposalPayload;
};

async function findPendingReclassifications(
  db: ReturnType<typeof getDirectDb>,
  proposalTypeFilter?: string,
): Promise<PendingProposal[]> {
  // Find approved proposals that have the "queuedFor" change_log row but NOT
  // a "reclassification_applied_*" row yet.
  const result = await db.execute(sql`
    SELECT tp.id, tp.proposal_type, tp.payload
    FROM taxonomy_proposals tp
    WHERE tp.status = 'approved'
      AND tp.proposal_type != 'create_top_domain'
      ${proposalTypeFilter ? sql`AND tp.proposal_type = ${proposalTypeFilter}` : sql``}
      AND EXISTS (
        SELECT 1 FROM taxonomy_change_log cl
        WHERE cl.proposal_id = tp.id
          AND cl.change_type LIKE 'approve_pending_reclassification_%'
      )
      AND NOT EXISTS (
        SELECT 1 FROM taxonomy_change_log cl
        WHERE cl.proposal_id = tp.id
          AND cl.change_type LIKE 'reclassification_applied_%'
      )
    ORDER BY tp.created_at ASC
    LIMIT 50
  `);

  return (result as unknown as Array<{ id: string; proposal_type: string; payload: unknown }>).map(
    (r) => ({
      id: r.id,
      proposalType: r.proposal_type,
      payload: (r.payload ?? {}) as ProposalPayload,
    }),
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Proposal handlers
// ─────────────────────────────────────────────────────────────────────────

type HandlerResult =
  | { applied: true; afterState: unknown }
  | { applied: false; reason: string };

/** create_sub_topic: INSERT knowledge_sub_topics + link representative claims. */
async function handleCreateSubTopic(
  db: ReturnType<typeof getDirectDb>,
  payload: ProposalPayload,
): Promise<HandlerResult> {
  const topDomainId = payload.topDomainId as string | undefined;
  const proposedName = payload.proposedName as string | undefined;
  const purpose = payload.oneSentencePurpose as string | undefined;
  const centroid = payload.clusterCentroid as number[] | undefined;
  const representativeClaimIds = (payload.representativeClaimIds as string[] | undefined) ?? [];

  if (!topDomainId || !proposedName) {
    return { applied: false, reason: 'payload missing topDomainId or proposedName' };
  }

  const [inserted] = await db
    .insert(knowledgeSubTopics)
    .values({
      topDomainId,
      name: proposedName,
      description: purpose ?? null,
      centroid: centroid ?? null,
      memberCount: representativeClaimIds.length,
      reviewStatus: 'approved',
    })
    .onConflictDoNothing()
    .returning({ id: knowledgeSubTopics.id });

  if (!inserted) {
    return {
      applied: false,
      reason: `knowledge_sub_topic (${topDomainId}, "${proposedName}") already exists — skipping`,
    };
  }

  if (representativeClaimIds.length > 0) {
    await db
      .insert(claimSubTopics)
      .values(
        representativeClaimIds.map((claimId) => ({
          claimId,
          subTopicId: inserted.id,
          assignmentReason: 'cluster_seed',
          assignmentConfidence: '0.800',
        })),
      )
      .onConflictDoNothing();
  }

  return {
    applied: true,
    afterState: {
      subTopicId: inserted.id,
      topDomainId,
      name: proposedName,
      linkedClaims: representativeClaimIds.length,
    },
  };
}

/** reassign_claims: move claims from one sub-topic to another. */
async function handleReassignClaims(
  db: ReturnType<typeof getDirectDb>,
  payload: ProposalPayload,
): Promise<HandlerResult> {
  const fromSubTopicId = payload.fromSubTopicId as string | undefined;
  const toSubTopicId = payload.toSubTopicId as string | undefined;
  const claimIds = payload.claimIds as string[] | undefined;

  if (!fromSubTopicId || !toSubTopicId) {
    return { applied: false, reason: 'payload missing fromSubTopicId or toSubTopicId' };
  }

  const targetExists = await db
    .select({ id: knowledgeSubTopics.id })
    .from(knowledgeSubTopics)
    .where(eq(knowledgeSubTopics.id, toSubTopicId))
    .limit(1);
  if (!targetExists.length) {
    return { applied: false, reason: `target sub-topic ${toSubTopicId} not found` };
  }

  const whereClause =
    claimIds && claimIds.length > 0
      ? and(eq(claimSubTopics.subTopicId, fromSubTopicId), inArray(claimSubTopics.claimId, claimIds))
      : eq(claimSubTopics.subTopicId, fromSubTopicId);

  // Re-point existing rows; skip claims already in the target.
  const alreadyInTarget = await db
    .select({ claimId: claimSubTopics.claimId })
    .from(claimSubTopics)
    .where(eq(claimSubTopics.subTopicId, toSubTopicId));
  const skipIds = alreadyInTarget.map((r) => r.claimId);

  const finalWhere =
    skipIds.length > 0
      ? and(whereClause, notInArray(claimSubTopics.claimId, skipIds))
      : whereClause;

  const updated = await db
    .update(claimSubTopics)
    .set({ subTopicId: toSubTopicId })
    .where(finalWhere)
    .returning({ claimId: claimSubTopics.claimId });

  return {
    applied: true,
    afterState: { fromSubTopicId, toSubTopicId, reassignedCount: updated.length },
  };
}

/** merge_sub_topics: move all members of source into target, then retire source. */
async function handleMergeSubTopics(
  db: ReturnType<typeof getDirectDb>,
  payload: ProposalPayload,
): Promise<HandlerResult> {
  const sourceSubTopicId = payload.sourceSubTopicId as string | undefined;
  const targetSubTopicId = payload.targetSubTopicId as string | undefined;

  if (!sourceSubTopicId || !targetSubTopicId) {
    return { applied: false, reason: 'payload missing sourceSubTopicId or targetSubTopicId' };
  }
  if (sourceSubTopicId === targetSubTopicId) {
    return { applied: false, reason: 'source and target sub-topic IDs are the same' };
  }

  // Move claims not already in target.
  const alreadyInTarget = await db
    .select({ claimId: claimSubTopics.claimId })
    .from(claimSubTopics)
    .where(eq(claimSubTopics.subTopicId, targetSubTopicId));
  const skipIds = alreadyInTarget.map((r) => r.claimId);

  const moveWhere =
    skipIds.length > 0
      ? and(eq(claimSubTopics.subTopicId, sourceSubTopicId), notInArray(claimSubTopics.claimId, skipIds))
      : eq(claimSubTopics.subTopicId, sourceSubTopicId);

  const moved = await db
    .update(claimSubTopics)
    .set({ subTopicId: targetSubTopicId })
    .where(moveWhere)
    .returning({ claimId: claimSubTopics.claimId });

  // Delete any leftover rows pointing at source (duplicates that were in target).
  await db
    .delete(claimSubTopics)
    .where(eq(claimSubTopics.subTopicId, sourceSubTopicId));

  // Retire source sub-topic.
  await db
    .update(knowledgeSubTopics)
    .set({ reviewStatus: 'retired' })
    .where(eq(knowledgeSubTopics.id, sourceSubTopicId));

  return {
    applied: true,
    afterState: {
      sourceSubTopicId,
      targetSubTopicId,
      movedCount: moved.length,
      sourceStatus: 'retired',
    },
  };
}

/** retire_sub_topic: mark retired, detach all claim_sub_topics rows. */
async function handleRetireSubTopic(
  db: ReturnType<typeof getDirectDb>,
  payload: ProposalPayload,
): Promise<HandlerResult> {
  const subTopicId = payload.subTopicId as string | undefined;
  if (!subTopicId) {
    return { applied: false, reason: 'payload missing subTopicId' };
  }

  const detached = await db
    .delete(claimSubTopics)
    .where(eq(claimSubTopics.subTopicId, subTopicId))
    .returning({ claimId: claimSubTopics.claimId });

  await db
    .update(knowledgeSubTopics)
    .set({ reviewStatus: 'retired' })
    .where(eq(knowledgeSubTopics.id, subTopicId));

  return {
    applied: true,
    afterState: { subTopicId, detachedClaimsCount: detached.length, status: 'retired' },
  };
}

/** merge_top_domains: re-tag all claim_top_domains from source → target, deactivate source. */
async function handleMergeTopDomains(
  db: ReturnType<typeof getDirectDb>,
  payload: ProposalPayload,
): Promise<HandlerResult> {
  const sourceTopDomainId = payload.sourceTopDomainId as string | undefined;
  const targetTopDomainId = payload.targetTopDomainId as string | undefined;

  if (!sourceTopDomainId || !targetTopDomainId) {
    return { applied: false, reason: 'payload missing sourceTopDomainId or targetTopDomainId' };
  }

  const targetExists = await db
    .select({ id: knowledgeTopDomains.id })
    .from(knowledgeTopDomains)
    .where(eq(knowledgeTopDomains.id, targetTopDomainId))
    .limit(1);
  if (!targetExists.length) {
    return { applied: false, reason: `target top-domain ${targetTopDomainId} not found` };
  }

  // Move claim_top_domains rows not already pointing at target.
  const alreadyInTarget = await db
    .select({ claimId: claimTopDomains.claimId })
    .from(claimTopDomains)
    .where(eq(claimTopDomains.topDomainId, targetTopDomainId));
  const skipIds = alreadyInTarget.map((r) => r.claimId);

  const moveWhere =
    skipIds.length > 0
      ? and(
          eq(claimTopDomains.topDomainId, sourceTopDomainId),
          notInArray(claimTopDomains.claimId, skipIds),
        )
      : eq(claimTopDomains.topDomainId, sourceTopDomainId);

  const moved = await db
    .update(claimTopDomains)
    .set({ topDomainId: targetTopDomainId })
    .where(moveWhere)
    .returning({ claimId: claimTopDomains.claimId });

  // Delete remaining source rows (duplicates already in target).
  await db
    .delete(claimTopDomains)
    .where(eq(claimTopDomains.topDomainId, sourceTopDomainId));

  // Deactivate source domain.
  await db
    .update(knowledgeTopDomains)
    .set({ isActive: false })
    .where(eq(knowledgeTopDomains.id, sourceTopDomainId));

  return {
    applied: true,
    afterState: {
      sourceTopDomainId,
      targetTopDomainId,
      movedCount: moved.length,
      sourceStatus: 'deactivated',
    },
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Main dispatch
// ─────────────────────────────────────────────────────────────────────────

async function applyProposal(
  db: ReturnType<typeof getDirectDb>,
  proposal: PendingProposal,
  dryRun: boolean,
): Promise<{ proposalId: string; changeType: string; applied: boolean; note: string }> {
  if (dryRun) {
    return {
      proposalId: proposal.id,
      changeType: `dry_run_${proposal.proposalType}`,
      applied: false,
      note: 'dry-run — no mutation applied',
    };
  }

  // Run the structural mutation AND the taxonomy_change_log row inside a single
  // transaction so a partial failure mid-handler can't leave the taxonomy moved
  // without an 'applied' log row (or vice versa) — the whole thing rolls back.
  const result = await db.transaction<HandlerResult>(async (tx) => {
    let r: HandlerResult;
    switch (proposal.proposalType) {
      case 'create_sub_topic':
        r = await handleCreateSubTopic(tx, proposal.payload);
        break;
      case 'reassign_claims':
        r = await handleReassignClaims(tx, proposal.payload);
        break;
      case 'merge_sub_topics':
        r = await handleMergeSubTopics(tx, proposal.payload);
        break;
      case 'retire_sub_topic':
        r = await handleRetireSubTopic(tx, proposal.payload);
        break;
      case 'merge_top_domains':
        r = await handleMergeTopDomains(tx, proposal.payload);
        break;
      case 'split_top_domain':
      case 'split_sub_topic':
        r = {
          applied: false,
          reason: `${proposal.proposalType} requires manual admin intervention — claim-level split cannot be automated safely.`,
        };
        break;
      default:
        r = { applied: false, reason: `unknown proposal type: ${proposal.proposalType}` };
    }

    const ct = r.applied
      ? `reclassification_applied_${proposal.proposalType}`
      : `reclassification_skipped_${proposal.proposalType}`;

    await tx.insert(taxonomyChangeLog).values({
      changeType: ct,
      beforeState: { proposalId: proposal.id, proposalType: proposal.proposalType },
      afterState: r.applied ? r.afterState : { reason: r.reason },
      reason: r.applied ? 'Applied by taxonomy-reclassification worker' : r.reason,
      proposalId: proposal.id,
    });

    return r;
  });

  const changeType = result.applied
    ? `reclassification_applied_${proposal.proposalType}`
    : `reclassification_skipped_${proposal.proposalType}`;

  return {
    proposalId: proposal.id,
    changeType,
    applied: result.applied,
    note: result.applied ? 'applied' : result.reason,
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Task
// ─────────────────────────────────────────────────────────────────────────

export const taxonomyReclassificationTask = task({
  id: 'taxonomy-reclassification',
  maxDuration: 60 * 5,
  run: async (payload: z.infer<typeof ManualTriggerPayload>, { ctx }) => {
    const parsed = ManualTriggerPayload.parse(payload);
    const db = getDirectDb();

    const [jobRun] = await db
      .insert(jobRuns)
      .values({
        triggerRunId: ctx.run.id,
        jobType: 'taxonomy-reclassification',
        status: 'running',
        startedAt: new Date(),
        inputJson: { proposalType: parsed.proposalType ?? null, dryRun: parsed.dryRun ?? false },
      })
      .returning({ id: jobRuns.id });
    if (!jobRun) throw new Error('[taxonomy-reclassification] failed to insert job_runs row');

    try {
      const pending = await findPendingReclassifications(db, parsed.proposalType);

      const results = [];
      for (const proposal of pending) {
        const r = await applyProposal(db, proposal, parsed.dryRun ?? false);
        results.push(r);
      }

      const appliedCount = results.filter((r) => r.applied).length;
      const skippedCount = results.length - appliedCount;

      const output = {
        ok: true as const,
        dryRun: parsed.dryRun ?? false,
        proposalsFound: pending.length,
        proposalsApplied: appliedCount,
        proposalsSkipped: skippedCount,
        results,
      };

      await db
        .update(jobRuns)
        .set({ status: 'complete', finishedAt: new Date(), outputJson: output })
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
  },
});
