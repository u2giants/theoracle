'use server';

import { and, eq, inArray, isNull, sql } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin, requireEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { triggerTask } from '@/lib/trigger';
import {
  buildRetrievalPlanFromQuery,
  OracleAIClient,
  buildStandardAdapters,
  makeBlock,
  resolveRouteCandidates,
} from '@oracle/ai';
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
import {
  markMacroRelationshipsStaleForClaim,
  requeueMacroRelationshipsReadyForReview,
} from '@oracle/engines';

type ReviewStatus = 'approved' | 'rejected';
const CLAIM_KINDS = new Set([
  'policy',
  'observed_practice',
  'workaround',
  'exception',
  'historical',
  'uncertain',
  'proposed_future_state',
]);

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

function claimKindFromForm(formData: FormData, fallback = 'uncertain'): string {
  const raw = String(formData.get('claimKind') ?? fallback).trim();
  return CLAIM_KINDS.has(raw) ? raw : 'uncertain';
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
  const claimKind = claimKindFromForm(formData, before.claim.claimKind ?? 'uncertain');
  const claimKindConfidence = intFromForm(
    formData,
    'claimKindConfidence',
    before.claim.claimKindConfidence ?? 5,
  );

  await db.transaction(async (tx) => {
    await tx
      .update(claims)
      .set({
        status,
        claimKind,
        claimKindConfidence,
        claimKindReviewStatus: status === 'approved' ? 'reviewed' : before.claim.claimKindReviewStatus,
      })
      .where(eq(claims.id, id));
    await tx.insert(claimReviewEvents).values({
      claimId: id,
      action: status === 'approved' ? 'approve' : 'reject',
      reviewedByEmployeeId: me.id,
      reviewerNote: String(formData.get('reviewerNote') ?? '').trim() || null,
      beforeState: before,
      afterState: {
        claim: {
          ...before.claim,
          status,
          claimKind,
          claimKindConfidence,
          claimKindReviewStatus:
            status === 'approved' ? 'reviewed' : before.claim.claimKindReviewStatus,
        },
        topDomainIds: before.topDomainIds,
      },
    });
  });

  if (status === 'approved') {
    await requeueMacroRelationshipsReadyForReview({ db, claimId: id });
  } else if (before.claim.status === 'approved') {
    await markMacroRelationshipsStaleForClaim({
      db,
      claimId: id,
      reason: `support claim was ${status}`,
    });
  }

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
  const claimKind = claimKindFromForm(formData, before.claim.claimKind ?? 'uncertain');
  const claimKindConfidence = intFromForm(
    formData,
    'claimKindConfidence',
    before.claim.claimKindConfidence ?? 5,
  );
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
        claimKind,
        claimKindConfidence,
        claimKindReviewStatus: 'reviewed',
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
          claimKind,
          claimKindConfidence,
          claimKindReviewStatus: 'reviewed',
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

  if (before.claim.status === 'approved') {
    await markMacroRelationshipsStaleForClaim({
      db,
      claimId: id,
      reason: 'support claim was superseded by reviewer revision',
    });
  }

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
  return assignClaimQuestionCore({ claimId, targetEmployeeIds, targetGroupIds, questionInput });
}

/**
 * Core "ask someone to verify/evaluate this claim" logic, keyed to a single
 * claim. Extracted so the per-row form (assignClaimQuestionImpl) and the bulk
 * action (assignClaimQuestionBulkWithState) share the exact same recipient
 * resolution, dedup-against-existing-assignments, per-recipient zh-CN auto
 * translation, gap insertion, and audit trail. `questionInput` empty → each
 * claim falls back to its own summary-based default question.
 */
async function assignClaimQuestionCore({
  claimId,
  targetEmployeeIds,
  targetGroupIds,
  questionInput,
}: {
  claimId: string;
  targetEmployeeIds: string[];
  targetGroupIds: string[];
  questionInput: string;
}): Promise<{ targetName: string }> {
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
          .select({ id: employees.id, name: employees.name, locale: employees.locale })
          .from(employees)
          .where(and(inArray(employees.id, targetEmployeeIds), isNull(employees.disabledAt)))
      : [];

  const groupTargets =
    targetGroupIds.length > 0
      ? await db
          .select({
            employeeId: employees.id,
            employeeName: employees.name,
            employeeLocale: employees.locale,
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

  const recipientsById = new Map<
    string,
    { id: string; name: string; locale: string; groupNames: string[] }
  >();
  for (const target of directTargets) {
    recipientsById.set(target.id, {
      id: target.id,
      name: target.name,
      locale: target.locale,
      groupNames: [],
    });
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
        locale: target.employeeLocale,
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

  // Bilingual (china_imp.md): each recipient is asked in their own language, so a
  // China-team (zh-CN) recipient — direct or via a group containing them — gets a
  // Chinese question while everyone else gets the original English. Only zh-CN
  // recipients trigger a translation; failure falls back to the original text.
  const needsChinese = newRecipients.some((recipient) => recipient.locale === 'zh-CN');
  let zhQuestion = question;
  if (needsChinese) {
    try {
      zhQuestion = await translateReviewQuestionToChinese(db, question);
    } catch (err) {
      console.warn('[claims] zh-CN question translation failed; using original text', err);
      zhQuestion = question;
    }
  }
  const zhWhyItMatters =
    '复核请求：审核人员标记此条目，需相关同事确认或更正后方可批准。';
  const enWhyItMatters =
    'A reviewer flagged this claim as needing subject-matter input before it can be approved.';

  await db.transaction(async (tx) => {
    const insertedGaps = await tx
      .insert(gaps)
      .values(newRecipients.map((recipient) => ({
        gapType: 'claim_review_question',
        relatedClaimIds: [claimId],
        questionToAsk: recipient.locale === 'zh-CN' ? zhQuestion : question,
        whyItMatters: recipient.locale === 'zh-CN' ? zhWhyItMatters : enWhyItMatters,
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

/**
 * Bulk "ask selected to evaluate" — the reviewer ticks several (typically
 * pending_review) claims, picks one shared set of people/groups, and each claim
 * is routed to those recipients for evaluation. Each claim reuses
 * assignClaimQuestionCore with an empty question so it gets its own
 * summary-based default; zh-CN recipients are asked in Chinese automatically.
 *
 * Per-claim failures (e.g. every chosen recipient already has an open
 * assignment for that claim) are non-fatal and reported as a skipped count, so
 * one already-assigned claim doesn't abort the whole batch.
 */
export async function assignClaimQuestionBulkWithState(
  _previousState: AssignClaimQuestionState,
  formData: FormData,
): Promise<AssignClaimQuestionState> {
  const claimIds = [
    ...new Set(
      formData.getAll('claimId').map((value) => String(value).trim()).filter(Boolean),
    ),
  ];
  const targetEmployeeIds = formData
    .getAll('targetEmployeeIds')
    .map((value) => String(value).trim())
    .filter(Boolean);
  const targetGroupIds = formData
    .getAll('targetGroupIds')
    .map((value) => String(value).trim())
    .filter(Boolean);

  if (claimIds.length === 0) {
    return { status: 'error', message: 'Tick at least one claim first.' };
  }
  if (targetEmployeeIds.length === 0 && targetGroupIds.length === 0) {
    return { status: 'error', message: 'Choose at least one person or group.' };
  }

  let sent = 0;
  const failures: string[] = [];
  for (const claimId of claimIds) {
    try {
      await assignClaimQuestionCore({
        claimId,
        targetEmployeeIds,
        targetGroupIds,
        questionInput: '',
      });
      sent += 1;
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
    }
  }

  if (sent === 0) {
    return {
      status: 'error',
      message: failures[0] ?? 'Nothing was sent.',
    };
  }
  const skipped = failures.length;
  return {
    status: 'success',
    message: `Sent ${sent} claim${sent === 1 ? '' : 's'} for evaluation${
      skipped > 0 ? ` (${skipped} skipped — already assigned or ineligible)` : ''
    }.`,
  };
}

// ---------------------------------------------------------------------------
// China bilingual claim layer (china_imp.md)
// ---------------------------------------------------------------------------

/**
 * Translate a claim-review question into Simplified Chinese via the admin-chosen
 * translation model (`default_translation_route`). Used so a `claim_review_question` directed at a
 * China-team (`zh-CN`) recipient is asked in Chinese. All inference goes through
 * OracleAIClient.
 */
async function translateReviewQuestionToChinese(
  db: ReturnType<typeof getDirectDb>,
  question: string,
): Promise<string> {
  const routeResolution = await resolveRouteCandidates(db, 'translation');
  for (const skipped of routeResolution.skipped) {
    console.warn('[claims-admin] skipped translation route candidate', skipped);
  }
  const routeCandidates = routeResolution.candidates;
  const route = routeCandidates[0]!.route;

  const client = new OracleAIClient({ adapters: buildStandardAdapters() });
  const result = await client.runText({
    taskType: 'claim_translation',
    routeId: route.routeId,
    promptVersion: 'claim-review-question-zh-v1',
    blocks: [
      makeBlock({
        id: 'review-question-translate-system',
        label: 'Translate review question to Chinese',
        kind: 'stable_system',
        content:
          'Translate the user message into Simplified Chinese (简体中文). Output ONLY the translation — no preamble, no quotes. Preserve meaning, proper nouns, numbers, and codes.',
        reasonIncluded: 'Translate a claim-review question for a China-team recipient',
      }),
      makeBlock({
        id: 'review-question-translate-input',
        label: 'Question text',
        kind: 'dynamic_input',
        content: question,
        reasonIncluded: 'The English question to translate',
      }),
    ],
    routeCandidates,
  });
  const translated = result.text.trim();
  if (!translated) {
    throw new Error('Translation model returned an empty review question.');
  }
  return translated;
}

/**
 * Bilingual claim layer: translate the SELECTED approved claims into the other
 * supported language(s) for the China team. Opt-in per claim (admin selects
 * them); the `claim-translation` worker is idempotent and skips non-approved
 * claims. Untranslated claims are still visible to China readers, in English.
 */
export async function translateClaimsForChina(formData: FormData) {
  await requireAdmin();

  const ids = Array.from(
    new Set(
      formData
        .getAll('claimId')
        .filter((v): v is string => typeof v === 'string' && v.length > 0),
    ),
  );
  if (ids.length === 0) return;

  let failed = 0;
  for (const id of ids) {
    const dispatched = await triggerTask('claim-translation', { claimId: id });
    if (!dispatched) failed += 1;
  }

  refreshClaimPages();

  // claim-translation has NO cron sweep — a failed dispatch never runs. Surface
  // it instead of silently claiming the translations were queued.
  if (failed > 0) {
    throw new Error(
      `${failed}/${ids.length} claim-translation dispatch(es) failed — those claims were NOT queued ` +
        `and no sweep will retry them. Check TRIGGER_SECRET_KEY, then re-run.`,
    );
  }
}
