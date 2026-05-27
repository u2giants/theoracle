'use server';

// R10.5 — Taxonomy governance server actions.
//
// Transactional approval/rejection for taxonomy_proposals and entity_proposals.
// Per docs/oracle/05-ai-retrofit-phase-packet.md Phase R10.5 task 4:
//   "Implement the transactional reclassification job, triggered only by
//    approved proposals... writes taxonomy_change_log entries... preserves
//    claim_evidence unchanged."
//
// And docs/oracle/07-knowledge-segmentation.md governance rules:
//   - No auto-mutation. Only an admin approval triggers the mutation.
//   - approved/rejected proposals MUST record the reviewer + timestamp
//     (taxonomy_proposals_reviewed_consistency_check enforces this).
//   - Every accepted change writes a taxonomy_change_log audit row.

import { revalidatePath } from 'next/cache';
import { and, eq, isNull } from 'drizzle-orm';
import {
  entityProposals,
  entities,
  knowledgeTopDomains,
  taxonomyChangeLog,
  taxonomyProposals,
} from '@oracle/db';
import { getDirectDb } from '@oracle/db/client';
import { requireAdmin } from '@/lib/auth-guard';

// ─────────────────────────────────────────────────────────────────────────
// taxonomy_proposals — approve / reject / defer
// ─────────────────────────────────────────────────────────────────────────

export async function rejectTaxonomyProposal(proposalId: string, reason: string) {
  const me = await requireAdmin();
  const db = getDirectDb();

  await db.transaction(async (tx) => {
    const [proposal] = await tx
      .select()
      .from(taxonomyProposals)
      .where(and(eq(taxonomyProposals.id, proposalId), eq(taxonomyProposals.status, 'pending')))
      .limit(1);
    if (!proposal) throw new Error('Proposal not found or already reviewed');

    await tx
      .update(taxonomyProposals)
      .set({
        status: 'rejected',
        reviewedByEmployeeId: me.id,
        reviewedAt: new Date(),
      })
      .where(eq(taxonomyProposals.id, proposalId));

    await tx.insert(taxonomyChangeLog).values({
      changeType: `reject_${proposal.proposalType}`,
      beforeState: { proposalId, proposalType: proposal.proposalType, payload: proposal.payload },
      afterState: null,
      reason,
      approvedByEmployeeId: me.id,
      proposalId,
    });
  });

  revalidatePath('/admin/taxonomy/proposals');
  revalidatePath('/admin/taxonomy/change-log');
}

/**
 * Approve a proposal. The mutation depends on the proposal type:
 *
 *   - create_top_domain → INSERT into knowledge_top_domains using the
 *     proposal payload (boundary rules included). This is the only
 *     mutation currently implemented inline; the reclassification path
 *     for merge_top_domains / split_top_domain / reassign_claims /
 *     create_sub_topic / merge_sub_topics / split_sub_topic / retire_sub_topic
 *     is scaffolded as a TODO — those need targeted reclassification of
 *     claim_top_domains / claim_sub_topics rows + optional Brain
 *     synthesis re-runs (the "transactional reclassification job"
 *     from R10.5 task 4 in the retrofit packet).
 *
 *   For the unimplemented branches, the proposal is marked approved
 *   (recording the reviewer) and the change log row is written, but
 *   the actual reclassification is queued as a TODO note. This
 *   preserves the audit trail without auto-mutating the taxonomy
 *   in ways the reclassifier isn't yet ready to handle.
 */
export async function approveTaxonomyProposal(proposalId: string, reviewNote: string | null) {
  const me = await requireAdmin();
  const db = getDirectDb();

  await db.transaction(async (tx) => {
    const [proposal] = await tx
      .select()
      .from(taxonomyProposals)
      .where(and(eq(taxonomyProposals.id, proposalId), eq(taxonomyProposals.status, 'pending')))
      .limit(1);
    if (!proposal) throw new Error('Proposal not found or already reviewed');

    // Mark approved first (the CHECK constraint enforces reviewer + timestamp).
    await tx
      .update(taxonomyProposals)
      .set({
        status: 'approved',
        reviewedByEmployeeId: me.id,
        reviewedAt: new Date(),
      })
      .where(eq(taxonomyProposals.id, proposalId));

    // Apply the mutation per type.
    type Payload = Record<string, unknown> & {
      proposedId?: string;
      proposedName?: string;
      oneSentencePurpose?: string;
      proposalReason?: string;
      boundaryRules?: {
        belongsHere?: unknown[];
        doesNotBelongHere?: unknown[];
        commonEntityHints?: unknown[];
        defaultExcludedDocumentClasses?: string[];
        neighboringDomainIds?: string[];
      };
      suggestedRetrievalExclusions?: string[];
    };
    const payload = (proposal.payload ?? {}) as Payload;

    let afterState: unknown = null;
    let queuedReclassification = false;

    if (proposal.proposalType === 'create_top_domain') {
      const id = (payload.proposedId ?? '').trim();
      const name = (payload.proposedName ?? '').trim();
      if (!id || !name) {
        throw new Error('create_top_domain proposal is missing proposedId or proposedName');
      }
      // display_order: place at the end of the active list.
      const allDomains = await tx
        .select({ displayOrder: knowledgeTopDomains.displayOrder })
        .from(knowledgeTopDomains);
      const maxOrder = allDomains.reduce((m, r) => (r.displayOrder > m ? r.displayOrder : m), 0);

      const [inserted] = await tx
        .insert(knowledgeTopDomains)
        .values({
          id,
          name,
          description: payload.oneSentencePurpose ?? '(approved from proposal)',
          belongsHere: (payload.boundaryRules?.belongsHere ?? []) as unknown[],
          doesNotBelongHere: (payload.boundaryRules?.doesNotBelongHere ?? []) as unknown[],
          commonEntityHints: (payload.boundaryRules?.commonEntityHints ?? []) as unknown[],
          defaultExcludedDocumentClasses:
            (payload.boundaryRules?.defaultExcludedDocumentClasses ??
              payload.suggestedRetrievalExclusions ??
              []) as string[],
          neighboringDomainIds: (payload.boundaryRules?.neighboringDomainIds ?? []) as string[],
          displayOrder: maxOrder + 10,
          isActive: true,
        })
        .onConflictDoNothing()
        .returning({ id: knowledgeTopDomains.id });
      afterState = { knowledgeTopDomainId: inserted?.id ?? id };
    } else {
      // merge_top_domains / split_top_domain / reassign_claims /
      // create_sub_topic / merge_sub_topics / split_sub_topic / retire_sub_topic
      // are intentionally NOT auto-applied. The proposal stays approved
      // (audit trail intact) but the reclassification work is left for
      // the dedicated reclassification job.
      queuedReclassification = true;
      afterState = {
        queuedFor: 'taxonomy-reclassification-worker',
        proposalType: proposal.proposalType,
        note: 'Mutation deferred — trigger task-id: taxonomy-reclassification.',
      };
    }

    await tx.insert(taxonomyChangeLog).values({
      changeType: queuedReclassification
        ? `approve_pending_reclassification_${proposal.proposalType}`
        : `approve_${proposal.proposalType}`,
      beforeState: { proposalId, proposalType: proposal.proposalType, payload: proposal.payload },
      afterState,
      reason: reviewNote,
      approvedByEmployeeId: me.id,
      proposalId,
    });
  });

  revalidatePath('/admin/taxonomy/proposals');
  revalidatePath('/admin/taxonomy');
  revalidatePath('/admin/taxonomy/change-log');
}

// ─────────────────────────────────────────────────────────────────────────
// taxonomy_proposals — bulk approve / bulk reject
// ─────────────────────────────────────────────────────────────────────────

export async function bulkApproveTaxonomyProposals(
  proposalIds: string[],
  reviewNote: string | null,
) {
  if (proposalIds.length === 0) return { approved: 0, errors: [] };
  const errors: Array<{ proposalId: string; error: string }> = [];
  let approved = 0;
  for (const id of proposalIds) {
    try {
      await approveTaxonomyProposal(id, reviewNote);
      approved++;
    } catch (e) {
      errors.push({ proposalId: id, error: e instanceof Error ? e.message : String(e) });
    }
  }
  return { approved, errors };
}

export async function bulkRejectTaxonomyProposals(proposalIds: string[], reason: string) {
  if (!reason.trim()) throw new Error('A rejection reason is required for bulk reject.');
  if (proposalIds.length === 0) return { rejected: 0, errors: [] };
  const errors: Array<{ proposalId: string; error: string }> = [];
  let rejected = 0;
  for (const id of proposalIds) {
    try {
      await rejectTaxonomyProposal(id, reason);
      rejected++;
    } catch (e) {
      errors.push({ proposalId: id, error: e instanceof Error ? e.message : String(e) });
    }
  }
  return { rejected, errors };
}

// ─────────────────────────────────────────────────────────────────────────
// entity_proposals — approve (creates entity) / reject / merge into existing
// ─────────────────────────────────────────────────────────────────────────

export async function rejectEntityProposal(proposalId: string, reason: string) {
  const me = await requireAdmin();
  const db = getDirectDb();

  await db.transaction(async (tx) => {
    const [proposal] = await tx
      .select()
      .from(entityProposals)
      .where(and(eq(entityProposals.id, proposalId), eq(entityProposals.status, 'pending')))
      .limit(1);
    if (!proposal) throw new Error('Entity proposal not found or already reviewed');

    await tx
      .update(entityProposals)
      .set({
        status: 'rejected',
        reviewedByEmployeeId: me.id,
        reviewedAt: new Date(),
      })
      .where(eq(entityProposals.id, proposalId));

    await tx.insert(taxonomyChangeLog).values({
      changeType: 'reject_entity_proposal',
      beforeState: {
        proposalId,
        proposedEntityType: proposal.proposedEntityType,
        proposedCanonicalValue: proposal.proposedCanonicalValue,
      },
      afterState: null,
      reason,
      approvedByEmployeeId: me.id,
    });
  });

  revalidatePath('/admin/taxonomy/entity-proposals');
  revalidatePath('/admin/taxonomy/change-log');
}

export async function approveEntityProposal(
  proposalId: string,
  // Allow the admin to refine the canonical value at approval time.
  finalCanonicalValue?: string,
  // Optional display label (defaults to canonical value).
  displayLabel?: string,
) {
  const me = await requireAdmin();
  const db = getDirectDb();

  await db.transaction(async (tx) => {
    const [proposal] = await tx
      .select()
      .from(entityProposals)
      .where(and(eq(entityProposals.id, proposalId), eq(entityProposals.status, 'pending')))
      .limit(1);
    if (!proposal) throw new Error('Entity proposal not found or already reviewed');

    const canonicalValue = (finalCanonicalValue ?? proposal.proposedCanonicalValue).trim();
    if (!canonicalValue) {
      throw new Error('canonical value must not be empty');
    }

    const aliases = Array.isArray(proposal.rawStringsObserved)
      ? (proposal.rawStringsObserved as string[]).filter((s) => s && s !== canonicalValue)
      : [];

    const [insertedEntity] = await tx
      .insert(entities)
      .values({
        entityType: proposal.proposedEntityType,
        canonicalValue,
        displayLabel: displayLabel ?? canonicalValue,
        aliases,
        domainHints: proposal.proposedDomainHints ?? [],
      })
      .onConflictDoNothing()
      .returning({ id: entities.id });

    // If onConflictDoNothing returned no row, that means an entity with the
    // same (entity_type, canonical_value) already exists. Look it up so we
    // can merge against it instead of creating a duplicate.
    let entityId = insertedEntity?.id;
    if (!entityId) {
      const [existing] = await tx
        .select({ id: entities.id })
        .from(entities)
        .where(
          and(
            eq(entities.entityType, proposal.proposedEntityType),
            eq(entities.canonicalValue, canonicalValue),
          ),
        )
        .limit(1);
      if (!existing) throw new Error('failed to resolve entity after onConflictDoNothing');
      entityId = existing.id;
    }

    await tx
      .update(entityProposals)
      .set({
        status: insertedEntity ? 'approved' : 'merged_into_existing',
        mergedIntoEntityId: entityId,
        reviewedByEmployeeId: me.id,
        reviewedAt: new Date(),
      })
      .where(eq(entityProposals.id, proposalId));

    await tx.insert(taxonomyChangeLog).values({
      changeType: insertedEntity ? 'create_entity_from_proposal' : 'merge_entity_proposal',
      beforeState: {
        proposalId,
        proposedEntityType: proposal.proposedEntityType,
        proposedCanonicalValue: proposal.proposedCanonicalValue,
      },
      afterState: { entityId, finalCanonicalValue: canonicalValue },
      reason: null,
      approvedByEmployeeId: me.id,
    });
  });

  revalidatePath('/admin/taxonomy/entity-proposals');
  revalidatePath('/admin/taxonomy/entities');
  revalidatePath('/admin/taxonomy/change-log');
}
