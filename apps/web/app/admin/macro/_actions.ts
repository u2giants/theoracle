'use server';

import { revalidatePath } from 'next/cache';
import { and, eq, inArray } from 'drizzle-orm';
import { requireAdmin } from '@/lib/auth-guard';
import { triggerTask } from '@/lib/trigger';
import { getDirectDb } from '@oracle/db/client';
import {
  claims,
  gaps,
  macroRelationshipClaims,
  macroRelationshipReviewEvents,
  macroRelationships,
  sourceCoverageFindings,
} from '@oracle/db/schema';
import { sweepStaleMacroRelationships } from '@oracle/engines';
import { createHash } from 'node:crypto';

function refresh() {
  revalidatePath('/admin/macro');
  revalidatePath('/admin/brain');
}

async function macroSnapshot(id: string) {
  const db = getDirectDb();
  const [relationship] = await db
    .select()
    .from(macroRelationships)
    .where(eq(macroRelationships.id, id))
    .limit(1);
  if (!relationship) throw new Error('Macro relationship not found.');
  const support = await db
    .select({
      claimId: macroRelationshipClaims.claimId,
      supportRole: macroRelationshipClaims.supportRole,
      claimStatus: claims.status,
      summary: claims.summary,
    })
    .from(macroRelationshipClaims)
    .innerJoin(claims, eq(claims.id, macroRelationshipClaims.claimId))
    .where(eq(macroRelationshipClaims.macroRelationshipId, id));
  return { relationship, support };
}

export async function updateMacroRelationshipStatus(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get('id') ?? '');
  const status = String(formData.get('status') ?? '');
  const reviewerNote = String(formData.get('reviewerNote') ?? '').trim() || null;
  if (!id || !['approved', 'rejected', 'needs_review'].includes(status)) return;

  const db = getDirectDb();
  const before = await macroSnapshot(id);
  if (status === 'approved' && before.support.some((row) => row.claimStatus !== 'approved')) {
    throw new Error('Cannot approve a macro relationship until every support claim is approved.');
  }

  await db.transaction(async (tx) => {
    await tx
      .update(macroRelationships)
      .set({ status, updatedAt: new Date(), stalenessReason: null, staleSince: null })
      .where(eq(macroRelationships.id, id));
    await tx.insert(macroRelationshipReviewEvents).values({
      macroRelationshipId: id,
      action: status === 'approved' ? 'approve' : status === 'rejected' ? 'reject' : 'revalidate',
      reviewerNote,
      beforeState: before,
      afterState: { ...before.relationship, status },
    });
  });
  refresh();
}

export async function dropMacroSupportAndRevalidate(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get('id') ?? '');
  const claimIds = formData
    .getAll('claimId')
    .map((value) => String(value))
    .filter(Boolean);
  const reviewerNote = String(formData.get('reviewerNote') ?? '').trim() || null;
  if (!id || claimIds.length === 0) return;

  const db = getDirectDb();
  const before = await macroSnapshot(id);
  await db.transaction(async (tx) => {
    await tx
      .delete(macroRelationshipClaims)
      .where(
        and(
          eq(macroRelationshipClaims.macroRelationshipId, id),
          inArray(macroRelationshipClaims.claimId, claimIds),
        ),
      );
    const remaining = await tx
      .select({ claimId: macroRelationshipClaims.claimId, status: claims.status })
      .from(macroRelationshipClaims)
      .innerJoin(claims, eq(claims.id, macroRelationshipClaims.claimId))
      .where(eq(macroRelationshipClaims.macroRelationshipId, id));
    const nextStatus =
      remaining.length >= 2 && remaining.every((row) => row.status === 'approved')
        ? 'pending_review'
        : 'needs_review';
    await tx
      .update(macroRelationships)
      .set({ status: nextStatus, updatedAt: new Date() })
      .where(eq(macroRelationships.id, id));
    await tx.insert(macroRelationshipReviewEvents).values({
      macroRelationshipId: id,
      action: 'drop_support',
      reviewerNote,
      beforeState: before,
      afterState: { removedClaimIds: claimIds, remainingClaimIds: remaining.map((row) => row.claimId), status: nextStatus },
    });
  });
  refresh();
}

export async function sweepMacroStaleness() {
  await requireAdmin();
  const db = getDirectDb();
  await sweepStaleMacroRelationships(db);
  refresh();
}

export async function runCoverageAudit(formData: FormData) {
  await requireAdmin();
  const sourceOutlineId = String(formData.get('sourceOutlineId') ?? '');
  if (!sourceOutlineId) return;
  const ok = await triggerTask('source-coverage-audit', { sourceOutlineId });
  if (!ok) throw new Error('Could not dispatch coverage audit.');
  refresh();
}

export async function runMacroRelationshipExtraction(formData: FormData) {
  await requireAdmin();
  const sourceOutlineId = String(formData.get('sourceOutlineId') ?? '');
  if (!sourceOutlineId) return;
  const ok = await triggerTask('macro-relationship-extraction', { sourceOutlineId });
  if (!ok) throw new Error('Could not dispatch macro relationship extraction.');
  refresh();
}

export async function convertCoverageFindingToGap(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get('id') ?? '');
  if (!id) return;
  const db = getDirectDb();
  const [finding] = await db
    .select()
    .from(sourceCoverageFindings)
    .where(eq(sourceCoverageFindings.id, id))
    .limit(1);
  if (!finding) throw new Error('Coverage finding not found.');
  const [gap] = await db
    .insert(gaps)
    .values({
      gapType: 'coverage_finding',
      questionToAsk: finding.suggestedQuestion ?? finding.summary,
      whyItMatters: 'A macro coverage audit found that source material is not represented by approved claims or relationships.',
      relatedClaimIds: finding.relatedClaimIds,
      priority: finding.severity >= 8 ? 'high' : 'medium',
      status: 'open',
    })
    .returning({ id: gaps.id });
  await db
    .update(sourceCoverageFindings)
    .set({ status: 'converted_to_gap', createdGapId: gap?.id ?? null })
    .where(eq(sourceCoverageFindings.id, id));
  refresh();
}

export async function dismissCoverageFinding(formData: FormData) {
  await requireAdmin();
  const id = String(formData.get('id') ?? '');
  if (!id) return;
  const db = getDirectDb();
  await db
    .update(sourceCoverageFindings)
    .set({ status: 'dismissed' })
    .where(eq(sourceCoverageFindings.id, id));
  refresh();
}

export async function createManualMacroRelationship(formData: FormData) {
  await requireAdmin();
  const summary = String(formData.get('summary') ?? '').trim();
  const relationshipType = String(formData.get('relationshipType') ?? '').trim();
  const claimIds = String(formData.get('claimIds') ?? '')
    .split(/[\s,]+/)
    .map((value) => value.trim())
    .filter(Boolean);
  if (!summary || !relationshipType || claimIds.length < 2) {
    throw new Error('Manual macro relationships need a type, summary, and at least two support claim IDs.');
  }

  const db = getDirectDb();
  const support = await db
    .select({ id: claims.id, status: claims.status, summary: claims.summary })
    .from(claims)
    .where(inArray(claims.id, claimIds));
  if (support.length < 2) throw new Error('At least two support claims must exist.');
  if (support.some((claim) => claim.status !== 'approved')) {
    throw new Error('Manual macro relationships can only be authored from approved support claims.');
  }

  const dedupeHash = createHash('sha256')
    .update(`${relationshipType}\n${summary.toLowerCase().replace(/\s+/g, ' ').trim()}\n${support.map((claim) => claim.id).sort().join(',')}`)
    .digest('hex');
  const [relationship] = await db
    .insert(macroRelationships)
    .values({
      relationshipType,
      summary,
      status: 'pending_review',
      confidenceScore: 8,
      impactScore: 6,
      triageScore: '68',
      metadataJson: { manual: true, dedupeHash },
    })
    .returning({ id: macroRelationships.id });
  if (!relationship) throw new Error('Macro relationship insert returned no row.');

  await db.insert(macroRelationshipClaims).values(
    support.map((claim, index) => ({
      macroRelationshipId: relationship.id,
      claimId: claim.id,
      supportRole: 'premise',
      claimStatusAtLink: claim.status,
      claimVersionHash: createHash('sha256').update(claim.summary).digest('hex'),
      sortOrder: index,
    })),
  );
  await db.insert(macroRelationshipReviewEvents).values({
    macroRelationshipId: relationship.id,
    action: 'manual_create',
    beforeState: {},
    afterState: { relationshipId: relationship.id, claimIds: support.map((claim) => claim.id) },
  });
  refresh();
}
