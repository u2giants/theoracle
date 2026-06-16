'use server';

import { revalidatePath } from 'next/cache';
import { sql } from 'drizzle-orm';
import { requireAdmin } from '@/lib/auth-guard';
import { triggerTask } from '@/lib/trigger';
import { getDirectDb } from '@oracle/db/client';

export type ExtractionAbActionState = {
  status: 'idle' | 'success' | 'error';
  message: string;
};

function normalizeSourceText(text: string | null, quote: string | null): string {
  const trimmed = (text ?? '').trim();
  const trimmedQuote = (quote ?? '').trim();
  if (!trimmed && trimmedQuote) return trimmedQuote;
  if (!trimmed) return '';
  if (!trimmedQuote) return trimmed.slice(0, 12_000);

  const quoteIndex = trimmed.indexOf(trimmedQuote);
  if (quoteIndex < 0) return trimmedQuote;

  const start = Math.max(0, quoteIndex - 4_000);
  const end = Math.min(trimmed.length, quoteIndex + trimmedQuote.length + 4_000);
  return trimmed.slice(start, end);
}

async function loadSourceForReviewEvent(reviewEventId: string) {
  const db = getDirectDb();
  const result = await db.execute(sql`
    SELECT
      cre.id AS review_event_id,
      cre.claim_id AS source_claim_id,
      cre.replacement_claim_id AS revised_claim_id,
      ce.source_type,
      COALESCE(ce.source_message_id, ce.source_document_chunk_id) AS source_id,
      ce.exact_quote,
      COALESCE(m.content, dc.raw_text, ce.exact_quote) AS source_text
    FROM claim_review_events cre
    JOIN LATERAL (
      SELECT *
      FROM (
        SELECT ce.*, 0 AS evidence_priority
        FROM claim_evidence ce
        WHERE ce.claim_id = cre.replacement_claim_id
        UNION ALL
        SELECT ce.*, 1 AS evidence_priority
        FROM claim_evidence ce
        WHERE ce.claim_id = cre.claim_id
      ) ranked_evidence
      ORDER BY evidence_priority, confidence DESC NULLS LAST, created_at ASC
      LIMIT 1
    ) ce ON true
    LEFT JOIN messages m ON m.id = ce.source_message_id
    LEFT JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
    WHERE cre.id = ${reviewEventId}::uuid
      AND cre.action = 'revise'
      AND cre.replacement_claim_id IS NOT NULL
    LIMIT 1
  `);
  const row = [...result][0] as
    | {
        review_event_id: string;
        source_claim_id: string;
        revised_claim_id: string;
        source_type: string;
        source_id: string | null;
        exact_quote: string | null;
        source_text: string | null;
      }
    | undefined;
  if (!row) throw new Error('Could not find source evidence for this revised claim.');
  const sourceExcerpt = normalizeSourceText(row.source_text, row.exact_quote);
  if (!sourceExcerpt) throw new Error('Could not find usable source evidence text for this revised claim.');
  return {
    ...row,
    source_excerpt: sourceExcerpt,
  };
}

export async function runExtractionAbTest(
  _prevState: ExtractionAbActionState,
  formData: FormData,
): Promise<ExtractionAbActionState> {
  try {
    await requireAdmin();
    const reviewEventId = String(formData.get('reviewEventId') ?? '').trim();
    if (!reviewEventId) throw new Error('Missing review event id.');

    const db = getDirectDb();
    const source = await loadSourceForReviewEvent(reviewEventId);

    await db.execute(sql`
      INSERT INTO claim_extraction_ab_tests (
        claim_review_event_id,
        source_claim_id,
        revised_claim_id,
        source_type,
        source_id,
        source_excerpt,
        gemini_3_1_output_json,
        qwen_3_7_output_json,
        gemini_3_1_error,
        qwen_3_7_error,
        best_variant,
        reviewer_note,
        reviewed_by_employee_id,
        reviewed_at,
        run_status,
        run_requested_at,
        run_started_at,
        run_completed_at,
        last_run_error
      )
      VALUES (
        ${source.review_event_id}::uuid,
        ${source.source_claim_id}::uuid,
        ${source.revised_claim_id}::uuid,
        ${source.source_type},
        ${source.source_id}::uuid,
        ${source.source_excerpt},
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        NULL,
        'queued',
        now(),
        NULL,
        NULL,
        NULL
      )
      ON CONFLICT (claim_review_event_id) DO UPDATE
        SET source_excerpt = EXCLUDED.source_excerpt,
            gemini_3_1_output_json = NULL,
            qwen_3_7_output_json = NULL,
            gemini_3_1_error = NULL,
            qwen_3_7_error = NULL,
            best_variant = NULL,
            reviewer_note = NULL,
            reviewed_by_employee_id = NULL,
            reviewed_at = NULL,
            run_status = 'queued',
            run_requested_at = now(),
            run_started_at = NULL,
            run_completed_at = NULL,
            last_run_error = NULL,
            updated_at = now()
    `);

    await triggerTask('extraction-ab-eval', { reviewEventId });
    revalidatePath('/admin/ai/extraction-ab');
    return { status: 'success', message: 'Queued. Results will appear here when the worker finishes.' };
  } catch (error) {
    return {
      status: 'error',
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

export async function scoreExtractionAbTest(formData: FormData) {
  const me = await requireAdmin();
  const reviewEventId = String(formData.get('reviewEventId') ?? '').trim();
  const bestVariant = String(formData.get('bestVariant') ?? '').trim();
  const reviewerNote = String(formData.get('reviewerNote') ?? '').trim();
  const allowed = [
    'existing_gemini_2_5',
    'gemini_3_1_flash_lite',
    'qwen_3_7_max',
  ];
  if (!reviewEventId || !allowed.includes(bestVariant)) {
    throw new Error('Choose the best column before saving.');
  }

  const db = getDirectDb();
  await db.execute(sql`
    UPDATE claim_extraction_ab_tests
    SET best_variant = ${bestVariant},
        reviewer_note = ${reviewerNote || null},
        reviewed_by_employee_id = ${me.id}::uuid,
        reviewed_at = now(),
        updated_at = now()
    WHERE claim_review_event_id = ${reviewEventId}::uuid
  `);

  revalidatePath('/admin/ai/extraction-ab');
}
