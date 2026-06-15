'use server';

import { eq, sql } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import {
  claimEntities,
  claimEvidence,
  claimMetadata,
  claimReviewEvents,
  claims,
  claimTopDomains,
} from '@oracle/db/schema';

type ReviewStatus = 'approved' | 'rejected';

function intFromForm(formData: FormData, key: string, fallback: number): number {
  const raw = String(formData.get(key) ?? '').trim();
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.min(10, parsed));
}

async function canReviewClaim(employeeId: string, isAdmin: boolean, claimId: string): Promise<boolean> {
  if (isAdmin) return true;
  const db = getDirectDb();
  const result = await db.execute(sql`
    SELECT EXISTS (
      SELECT 1
      FROM claim_top_domains ctd
      JOIN knowledge_domain_review_departments kdrd
        ON kdrd.top_domain_id = ctd.top_domain_id
       AND kdrd.can_review_claims = true
      JOIN employee_departments ed
        ON ed.department_id = kdrd.department_id
      WHERE ctd.claim_id = ${claimId}::uuid
        AND ed.employee_id = ${employeeId}::uuid
    ) AS allowed
  `);
  const row = [...result][0] as { allowed?: boolean } | undefined;
  return row?.allowed === true;
}

async function requireClaimReviewer(claimId: string) {
  const me = await requireEmployee();
  const allowed = await canReviewClaim(me.id, me.isAdmin, claimId);
  if (!allowed) {
    throw new Error('You do not have permission to review this claim.');
  }
  return me;
}

async function claimSnapshot(claimId: string) {
  const db = getDirectDb();
  const [claim] = await db.select().from(claims).where(eq(claims.id, claimId)).limit(1);
  if (!claim) throw new Error('Claim not found.');

  const domains = await db
    .select({ topDomainId: claimTopDomains.topDomainId })
    .from(claimTopDomains)
    .where(eq(claimTopDomains.claimId, claimId));

  return {
    claim,
    topDomainIds: domains.map((d) => d.topDomainId),
  };
}

function refreshClaimPages() {
  revalidatePath('/admin/claims');
  revalidatePath('/claims');
}

export async function updateClaimStatus(formData: FormData) {
  const id = String(formData.get('id') ?? '');
  const status = String(formData.get('status') ?? '') as ReviewStatus;
  if (!id || !['approved', 'rejected'].includes(status)) return;

  const me = await requireClaimReviewer(id);
  const before = await claimSnapshot(id);
  const db = getDirectDb();

  await db.transaction(async (tx) => {
    await tx.update(claims).set({ status }).where(eq(claims.id, id));
    await tx.insert(claimReviewEvents).values({
      claimId: id,
      action: status === 'approved' ? 'approve' : 'reject',
      reviewedByEmployeeId: me.id,
      reviewerNote: String(formData.get('reviewerNote') ?? '').trim() || null,
      beforeState: before,
      afterState: {
        claim: { ...before.claim, status },
        topDomainIds: before.topDomainIds,
      },
    });
  });

  refreshClaimPages();
}

export async function reviseClaim(formData: FormData) {
  const id = String(formData.get('id') ?? '');
  const summary = String(formData.get('summary') ?? '').trim();
  const claimType = String(formData.get('claimType') ?? '').trim();
  const reviewerNote = String(formData.get('reviewerNote') ?? '').trim();
  if (!id || !summary || !claimType) return;

  const me = await requireClaimReviewer(id);
  const before = await claimSnapshot(id);
  const db = getDirectDb();
  const impactScore = intFromForm(formData, 'impactScore', before.claim.impactScore);
  const confidenceScore = intFromForm(formData, 'confidenceScore', before.claim.confidenceScore);

  await db.transaction(async (tx) => {
    const [replacement] = await tx
      .insert(claims)
      .values({
        claimType,
        summary,
        impactScore,
        confidenceScore,
        status: 'pending_review',
      })
      .returning({ id: claims.id });

    if (!replacement) throw new Error('Replacement claim insert returned no row.');
    const replacementClaimId = replacement.id;

    const domains = await tx.select().from(claimTopDomains).where(eq(claimTopDomains.claimId, id));
    if (domains.length > 0) {
      await tx.insert(claimTopDomains).values(
        domains.map((d) => ({
          claimId: replacementClaimId,
          topDomainId: d.topDomainId,
          assignmentConfidence: d.assignmentConfidence,
          assignmentReason: 'manual',
        })),
      );
    }

    const entities = await tx.select().from(claimEntities).where(eq(claimEntities.claimId, id));
    if (entities.length > 0) {
      await tx
        .insert(claimEntities)
        .values(entities.map((e) => ({ claimId: replacementClaimId, entityId: e.entityId })))
        .onConflictDoNothing();
    }

    const [metadata] = await tx.select().from(claimMetadata).where(eq(claimMetadata.claimId, id)).limit(1);
    if (metadata) {
      await tx.insert(claimMetadata).values({
        claimId: replacementClaimId,
        processStage: metadata.processStage,
        department: metadata.department,
        geography: metadata.geography,
        documentClass: metadata.documentClass,
        effectiveFrom: metadata.effectiveFrom,
        effectiveUntil: metadata.effectiveUntil,
      });
    }

    const evidence = await tx.select().from(claimEvidence).where(eq(claimEvidence.claimId, id));
    if (evidence.length > 0) {
      await tx.insert(claimEvidence).values(
        evidence.map((e) => ({
          claimId: replacementClaimId,
          sourceType: e.sourceType,
          sourceMessageId: e.sourceMessageId,
          sourceDocumentChunkId: e.sourceDocumentChunkId,
          sourceExternalRecordId: e.sourceExternalRecordId,
          assertedByEmployeeId: e.assertedByEmployeeId,
          uploadedByEmployeeId: e.uploadedByEmployeeId,
          createdByEmployeeId: e.createdByEmployeeId,
          exactQuote: e.exactQuote,
          charStart: e.charStart,
          charEnd: e.charEnd,
          pageNumber: e.pageNumber,
          confidence: e.confidence,
        })),
      );
    }

    if (reviewerNote) {
      await tx.insert(claimEvidence).values({
        claimId: replacementClaimId,
        sourceType: 'manual_admin',
        createdByEmployeeId: me.id,
        exactQuote: reviewerNote,
        confidence: 100,
      });
    }

    await tx.update(claims).set({ status: 'superseded' }).where(eq(claims.id, id));

    await tx
      .insert(claimMetadata)
      .values({
        claimId: id,
        supersededByClaimId: replacementClaimId,
        updatedAt: new Date(),
      })
      .onConflictDoUpdate({
        target: claimMetadata.claimId,
        set: {
          supersededByClaimId: replacementClaimId,
          updatedAt: new Date(),
        },
      });

    await tx.insert(claimReviewEvents).values({
      claimId: id,
      replacementClaimId,
      action: 'revise',
      reviewedByEmployeeId: me.id,
      reviewerNote: reviewerNote || null,
      beforeState: before,
      afterState: {
        claim: {
          id: replacementClaimId,
          claimType,
          summary,
          impactScore,
          confidenceScore,
          status: 'pending_review',
        },
        topDomainIds: domains.map((d) => d.topDomainId),
      },
      aiComparisonJson: null,
    });
  });

  refreshClaimPages();
}
