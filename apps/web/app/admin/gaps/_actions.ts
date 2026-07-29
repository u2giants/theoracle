'use server';

import { and, eq, inArray, isNull, sql } from 'drizzle-orm';
import { revalidatePath } from 'next/cache';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import {
  employees,
  gaps,
  modelCoverageConversionEvents,
  modelCoverageConversions,
} from '@oracle/db/schema';
import {
  assertCoverageFindingEligible,
  modelCoverageSourcesEqual,
} from '@/lib/model-coverage-conversion';

export async function updateGapStatus(formData: FormData) {
  // Defense in depth — see claims/_actions.ts for rationale.
  await requireAdmin();

  const id = formData.get('id') as string;
  const status = formData.get('status') as 'resolved' | 'stale' | 'rejected';
  if (!id || !['resolved', 'stale', 'rejected'].includes(status)) return;

  const db = getDirectDb();
  const [gap] = await db
    .select({ gapType: gaps.gapType })
    .from(gaps)
    .where(eq(gaps.id, id))
    .limit(1);
  if (!gap) throw new Error('Gap not found.');
  if (gap.gapType === 'model_coverage') {
    throw new Error('Model coverage findings can only be resolved through the audited conversion flow.');
  }
  await db.update(gaps).set({ status }).where(eq(gaps.id, id));
  revalidatePath('/admin/gaps');
}

function refreshCoverage() {
  revalidatePath('/admin/gaps');
}

export async function createCoverageConversionDraft(formData: FormData) {
  const me = await requireAdmin();
  const sourceGapId = String(formData.get('sourceGapId') ?? '').trim();
  const questionToAsk = String(formData.get('questionToAsk') ?? '').trim();
  const conversionReason = String(formData.get('conversionReason') ?? '').trim();
  const targetEmployeeIds = [...new Set(formData.getAll('targetEmployeeIds').map(String).filter(Boolean))];
  if (!sourceGapId || !questionToAsk || !conversionReason || targetEmployeeIds.length === 0) {
    throw new Error('Write the question and reason, then choose at least one employee.');
  }

  const db = getDirectDb();
  await db.transaction(async (tx) => {
    const locked = await tx.execute(sql`
      SELECT id, gap_type, status, source_context
      FROM gaps WHERE id = ${sourceGapId}
      FOR UPDATE
    `);
    const finding = [...locked][0] as
      | { id: string; gap_type: string; status: string; source_context: unknown }
      | undefined;
    if (!finding) throw new Error('Model coverage finding not found.');
    const sourceSnapshot = assertCoverageFindingEligible({
      gapType: finding.gap_type,
      status: finding.status,
      sourceContext: finding.source_context,
    });

    const recipients = await tx
      .select({ id: employees.id })
      .from(employees)
      .where(and(inArray(employees.id, targetEmployeeIds), isNull(employees.disabledAt)));
    if (recipients.length !== targetEmployeeIds.length) {
      throw new Error('One or more selected employees are missing or disabled. Refresh and try again.');
    }

    const [draft] = await tx
      .insert(modelCoverageConversions)
      .values({
        sourceGapId,
        questionToAsk,
        conversionReason,
        targetEmployeeIds,
        sourceSnapshot,
        createdByEmployeeId: me.id,
      })
      .onConflictDoNothing()
      .returning({ id: modelCoverageConversions.id });
    if (!draft) throw new Error('This finding already has a conversion. Refresh to review it.');
    await tx.insert(modelCoverageConversionEvents).values({
      conversionId: draft.id,
      sourceGapId,
      action: 'draft_created',
      actedByEmployeeId: me.id,
      sourceSnapshot,
      afterState: { questionToAsk, conversionReason, targetEmployeeIds },
    });
  });
  refreshCoverage();
}

export async function sendCoverageConversion(formData: FormData) {
  const me = await requireAdmin();
  const conversionId = String(formData.get('conversionId') ?? '').trim();
  if (!conversionId) throw new Error('Conversion draft is missing.');
  const db = getDirectDb();
  await db.transaction(async (tx) => {
    const locked = await tx.execute(sql`
      SELECT * FROM model_coverage_conversions
      WHERE id = ${conversionId}
      FOR UPDATE
    `);
    const draft = [...locked][0] as
      | {
          id: string;
          source_gap_id: string;
          question_to_ask: string;
          conversion_reason: string;
          target_employee_ids: string[];
          source_snapshot: unknown;
          status: string;
          created_gap_ids: string[];
        }
      | undefined;
    if (!draft) throw new Error('Conversion draft not found.');
    if (draft.status === 'sent') return;
    if (draft.status !== 'draft') throw new Error('Only a draft conversion can be sent.');

    const sourceRows = await tx.execute(sql`
      SELECT id, gap_type, status, source_context
      FROM gaps WHERE id = ${draft.source_gap_id}
      FOR UPDATE
    `);
    const finding = [...sourceRows][0] as
      | { gap_type: string; status: string; source_context: unknown }
      | undefined;
    if (!finding) throw new Error('The source model coverage finding no longer exists.');
    const currentSource = assertCoverageFindingEligible({
      gapType: finding.gap_type,
      status: finding.status,
      sourceContext: finding.source_context,
    });
    if (!modelCoverageSourcesEqual(currentSource, draft.source_snapshot)) {
      throw new Error('The source finding changed. Cancel this draft and review a new one.');
    }

    const recipients = await tx
      .select({ id: employees.id })
      .from(employees)
      .where(and(inArray(employees.id, draft.target_employee_ids), isNull(employees.disabledAt)));
    if (recipients.length !== draft.target_employee_ids.length) {
      throw new Error('A selected employee is now missing or disabled. Cancel this draft and create a new one.');
    }
    const created = await tx
      .insert(gaps)
      .values(recipients.map((recipient) => ({
        gapType: 'coverage_question',
        questionToAsk: draft.question_to_ask,
        whyItMatters: draft.conversion_reason,
        targetEmployeeId: recipient.id,
        priority: 'medium' as const,
        status: 'open' as const,
        sourceContext: {
          modelCoverageSourceGapId: draft.source_gap_id,
          ...draft.source_snapshot as object,
        },
      })))
      .returning({ id: gaps.id });
    const createdGapIds = created.map((row) => row.id);
    await tx
      .update(modelCoverageConversions)
      .set({ status: 'sent', createdGapIds, updatedAt: new Date() })
      .where(and(eq(modelCoverageConversions.id, conversionId), eq(modelCoverageConversions.status, 'draft')));
    await tx
      .update(gaps)
      .set({ status: 'resolved', updatedAt: new Date() })
      .where(eq(gaps.id, draft.source_gap_id));
    await tx.insert(modelCoverageConversionEvents).values({
      conversionId,
      sourceGapId: draft.source_gap_id,
      action: 'sent',
      actedByEmployeeId: me.id,
      sourceSnapshot: draft.source_snapshot,
      afterState: { createdGapIds, targetEmployeeIds: draft.target_employee_ids },
    });
  });
  refreshCoverage();
}

export async function cancelCoverageConversion(formData: FormData) {
  const me = await requireAdmin();
  const conversionId = String(formData.get('conversionId') ?? '').trim();
  if (!conversionId) throw new Error('Conversion draft is missing.');
  const db = getDirectDb();
  await db.transaction(async (tx) => {
    const locked = await tx.execute(sql`
      SELECT * FROM model_coverage_conversions
      WHERE id = ${conversionId}
      FOR UPDATE
    `);
    const draft = [...locked][0] as
      | { source_gap_id: string; source_snapshot: unknown; status: string }
      | undefined;
    if (!draft) throw new Error('Conversion draft not found.');
    if (draft.status === 'cancelled') return;
    if (draft.status !== 'draft') throw new Error('A sent conversion cannot be cancelled.');
    await tx
      .update(modelCoverageConversions)
      .set({ status: 'cancelled', updatedAt: new Date() })
      .where(and(eq(modelCoverageConversions.id, conversionId), eq(modelCoverageConversions.status, 'draft')));
    await tx.insert(modelCoverageConversionEvents).values({
      conversionId,
      sourceGapId: draft.source_gap_id,
      action: 'cancelled',
      actedByEmployeeId: me.id,
      sourceSnapshot: draft.source_snapshot,
      afterState: { cancelled: true },
    });
  });
  refreshCoverage();
}
