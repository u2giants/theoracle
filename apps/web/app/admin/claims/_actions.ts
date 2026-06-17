'use server';

import { and, eq, inArray, isNull, sql } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { buildRetrievalPlanFromQuery } from '@oracle/ai';
import {
  claimEntities,
  claimEvidence,
  claimMetadata,
  claimReviewGroupMembers,
  claimReviewGroups,
  claimReviewEvents,
  claims,
  claimTopDomains,
  employees,
  gaps,
  knowledgeTopDomains,
} from '@oracle/db/schema';

type ReviewStatus = 'approved' | 'rejected';

export type AssignClaimQuestionState = {
  status: 'idle' | 'success' | 'error';
  message: string | null;
};

function intFromForm(formData: FormData, key: string, fallback: number): number {
  const raw = String(formData.get(key) ?? '').trim();
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(1, Math.min(10, parsed));
}

function buildAutoRevisionNote(input: {
  beforeSummary: string;
  afterSummary: string;
  beforeClaimType: string;
  afterClaimType: string;
  beforeImpact: number;
  afterImpact: number;
  beforeConfidence: number;
  afterConfidence: number;
  beforeDomains: string[];
  afterDomains: string[];
}): string {
  const changes: string[] = [];
  if (input.beforeSummary !== input.afterSummary) {
    changes.push(`summary changed from "${input.beforeSummary}" to "${input.afterSummary}"`);
  }
  if (input.beforeClaimType !== input.afterClaimType) {
    changes.push(`claim type changed from ${input.beforeClaimType} to ${input.afterClaimType}`);
  }
  if (input.beforeImpact !== input.afterImpact) {
    changes.push(`impact changed from ${input.beforeImpact} to ${input.afterImpact}`);
  }
  if (input.beforeConfidence !== input.afterConfidence) {
    changes.push(`confidence changed from ${input.beforeConfidence} to ${input.afterConfidence}`);
  }
  const beforeDomains = input.beforeDomains.join(', ') || '(none)';
  const afterDomains = input.afterDomains.join(', ') || '(none)';
  if (beforeDomains !== afterDomains) {
    changes.push(`domains changed from ${beforeDomains} to ${afterDomains}`);
  }
  return changes.length > 0
    ? `Reviewer revised the AI claim: ${changes.join('; ')}.`
    : 'Reviewer resubmitted the claim without changing the reviewed fields.';
}

async function recalculateClaimDomainIds(input: {
  summary: string;
  claimType: string;
  fallbackDomainIds: string[];
}): Promise<{ domainIds: string[]; method: 'retrieval_plan_heuristic' | 'fallback_original_domains' }> {
  const db = getDirectDb();
  const plan = buildRetrievalPlanFromQuery(`${input.claimType}\n${input.summary}`);
  const inferredDomainIds = plan.topDomainHints;
  if (inferredDomainIds.length === 0) {
    return { domainIds: input.fallbackDomainIds, method: 'fallback_original_domains' };
  }

  const validDomains = await db
    .select({ id: knowledgeTopDomains.id })
    .from(knowledgeTopDomains)
    .where(inArray(knowledgeTopDomains.id, inferredDomainIds));
  const validDomainIds = inferredDomainIds.filter((id) =>
    validDomains.some((domain) => domain.id === id),
  );

  return validDomainIds.length > 0
    ? { domainIds: validDomainIds, method: 'retrieval_plan_heuristic' }
    : { domainIds: input.fallbackDomainIds, method: 'fallback_original_domains' };
}

async function canReviewClaim(employeeId: string, isAdmin: boolean, claimId: string): Promise<boolean> {
  if (isAdmin) return true;
  const db = getDirectDb();
  const result = await db.execute(sql`
    SELECT EXISTS (
      SELECT 1
      FROM gaps g
      WHERE g.gap_type = 'claim_review_question'
        AND g.target_employee_id = ${employeeId}::uuid
        AND g.status IN ('open', 'queued', 'asked')
        AND g.related_claim_ids ? ${claimId}
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
  revalidatePath('/admin/gaps');
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
  const reviewerNoteInput = String(formData.get('reviewerNote') ?? '').trim();
  if (!id || !summary || !claimType) return;

  const me = await requireClaimReviewer(id);
  const before = await claimSnapshot(id);
  if (!['pending_review', 'approved'].includes(before.claim.status)) {
    throw new Error('Only pending or approved claims can be revised.');
  }
  const db = getDirectDb();
  const impactScore = intFromForm(formData, 'impactScore', before.claim.impactScore);
  const confidenceScore = intFromForm(formData, 'confidenceScore', before.claim.confidenceScore);
  const domainRecalculation = await recalculateClaimDomainIds({
    summary,
    claimType,
    fallbackDomainIds: before.topDomainIds,
  });
  const validDomainIds = domainRecalculation.domainIds;
  if (validDomainIds.length === 0) {
    throw new Error('The system could not infer a knowledge domain for this revised claim.');
  }
  const reviewerNote =
    reviewerNoteInput ||
    buildAutoRevisionNote({
      beforeSummary: before.claim.summary,
      afterSummary: summary,
      beforeClaimType: before.claim.claimType,
      afterClaimType: claimType,
      beforeImpact: before.claim.impactScore,
      afterImpact: impactScore,
      beforeConfidence: before.claim.confidenceScore,
      afterConfidence: confidenceScore,
      beforeDomains: before.topDomainIds,
      afterDomains: validDomainIds,
    });

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

    await tx.insert(claimTopDomains).values(
      validDomainIds.map((topDomainId) => ({
          claimId: replacementClaimId,
          topDomainId,
          assignmentConfidence: '1',
          assignmentReason: 'manual',
      })),
    );

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
        topDomainIds: validDomainIds,
      },
      aiComparisonJson: {
        originalSummary: before.claim.summary,
        revisedSummary: summary,
        originalTopDomainIds: before.topDomainIds,
        revisedTopDomainIds: validDomainIds,
        domainRecalculationMethod: domainRecalculation.method,
        reviewerNoteWasGenerated: !reviewerNoteInput,
      },
    });
  });

  refreshClaimPages();
}

async function assignClaimQuestionImpl(formData: FormData): Promise<{ targetName: string }> {
  const claimId = String(formData.get('claimId') ?? '').trim();
  const targetEmployeeIds = formData
    .getAll('targetEmployeeIds')
    .map((value) => String(value).trim())
    .filter(Boolean);
  const targetGroupIds = formData
    .getAll('targetGroupIds')
    .map((value) => String(value).trim())
    .filter(Boolean);
  const questionInput = String(formData.get('question') ?? '').trim();
  if (!claimId) throw new Error('Missing claim.');
  if (targetEmployeeIds.length === 0 && targetGroupIds.length === 0) {
    throw new Error('Choose at least one person or group before assigning the question.');
  }

  const me = await requireClaimReviewer(claimId);
  const before = await claimSnapshot(claimId);
  const db = getDirectDb();

  const directTargets =
    targetEmployeeIds.length > 0
      ? await db
          .select({ id: employees.id, name: employees.name })
          .from(employees)
          .where(and(inArray(employees.id, targetEmployeeIds), isNull(employees.disabledAt)))
      : [];

  const groupTargets =
    targetGroupIds.length > 0
      ? await db
          .select({
            employeeId: employees.id,
            employeeName: employees.name,
            groupId: claimReviewGroups.id,
            groupName: claimReviewGroups.name,
          })
          .from(claimReviewGroupMembers)
          .innerJoin(
            claimReviewGroups,
            eq(claimReviewGroups.id, claimReviewGroupMembers.groupId),
          )
          .innerJoin(employees, eq(employees.id, claimReviewGroupMembers.employeeId))
          .where(
            and(
              inArray(claimReviewGroupMembers.groupId, targetGroupIds),
              isNull(claimReviewGroups.archivedAt),
              isNull(employees.disabledAt),
            ),
          )
      : [];

  const recipientsById = new Map<string, { id: string; name: string; groupNames: string[] }>();
  for (const target of directTargets) {
    recipientsById.set(target.id, { id: target.id, name: target.name, groupNames: [] });
  }
  for (const target of groupTargets) {
    const existing = recipientsById.get(target.employeeId);
    if (existing) {
      if (!existing.groupNames.includes(target.groupName)) {
        existing.groupNames.push(target.groupName);
      }
    } else {
      recipientsById.set(target.employeeId, {
        id: target.employeeId,
        name: target.employeeName,
        groupNames: [target.groupName],
      });
    }
  }

  const recipients = [...recipientsById.values()].sort((a, b) => a.name.localeCompare(b.name));
  if (recipients.length === 0) {
    throw new Error('No active employees were found for the selected people or groups.');
  }

  const question =
    questionInput ||
    `Can you help correct or confirm this claim?\n\n${before.claim.summary}`;

  const existingAssignments = await db.execute(sql`
    SELECT target_employee_id
    FROM gaps
    WHERE gap_type = 'claim_review_question'
      AND status IN ('open', 'queued', 'asked')
      AND related_claim_ids ? ${claimId}
      AND target_employee_id IN (
        SELECT value::uuid
        FROM jsonb_array_elements_text(${JSON.stringify(recipients.map((recipient) => recipient.id))}::jsonb)
      )
  `);
  const alreadyAssignedIds = new Set(
    ([...existingAssignments] as Array<{ target_employee_id: string | null }>)
      .map((row) => row.target_employee_id)
      .filter((id): id is string => Boolean(id)),
  );
  const newRecipients = recipients.filter((recipient) => !alreadyAssignedIds.has(recipient.id));

  if (newRecipients.length === 0) {
    throw new Error('All selected recipients already have an open assignment for this claim.');
  }

  await db.transaction(async (tx) => {
    const insertedGaps = await tx
      .insert(gaps)
      .values(newRecipients.map((recipient) => ({
        gapType: 'claim_review_question',
        relatedClaimIds: [claimId],
        questionToAsk: question,
        whyItMatters:
          'A reviewer flagged this claim as needing subject-matter input before it can be approved.',
        targetEmployeeId: recipient.id,
        priority: 'medium' as const,
        status: 'open' as const,
      })))
      .returning({ id: gaps.id });

    await tx.insert(claimReviewEvents).values({
      claimId,
      action: 'assign_question',
      reviewedByEmployeeId: me.id,
      reviewerNote: `Assigned follow-up question to ${newRecipients
        .map((recipient) => recipient.name)
        .join(', ')}.`,
      beforeState: before,
      afterState: {
        assignedGapIds: insertedGaps.map((gap) => gap.id),
        targetEmployeeIds: newRecipients.map((recipient) => recipient.id),
        targetGroupIds,
        skippedAlreadyAssignedEmployeeIds: [...alreadyAssignedIds],
        questionToAsk: question,
      },
    });
  });

  refreshClaimPages();
  const skippedCount = alreadyAssignedIds.size;
  const targetName =
    newRecipients.length === 1
      ? newRecipients[0]!.name
      : `${newRecipients.length} people${skippedCount > 0 ? ` (${skippedCount} already assigned)` : ''}`;
  return { targetName };
}

export async function assignClaimQuestion(formData: FormData) {
  await assignClaimQuestionImpl(formData);
}

export async function assignClaimQuestionWithState(
  _previousState: AssignClaimQuestionState,
  formData: FormData,
): Promise<AssignClaimQuestionState> {
  try {
    const result = await assignClaimQuestionImpl(formData);
    return {
      status: 'success',
      message: `Question assigned to ${result.targetName}.`,
    };
  } catch (error) {
    return {
      status: 'error',
      message: error instanceof Error ? error.message : 'The question could not be assigned.',
    };
  }
}
