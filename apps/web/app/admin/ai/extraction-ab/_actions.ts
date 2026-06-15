'use server';

import { revalidatePath } from 'next/cache';
import { sql } from 'drizzle-orm';
import { z } from 'zod';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import {
  buildStandardAdapters,
  ExtractionClaimSchema,
  EXTRACTION_PROMPT_VERSION,
  EXTRACTION_SYSTEM_PROMPT,
  loadClaimCorrectionLessonPack,
  makeBlock,
  OracleAIClient,
  getOracleRoute,
  type OracleModelRoute,
} from '@oracle/ai';

const EvalOutputSchema = z.object({
  claim: ExtractionClaimSchema.nullable().optional().default(null),
  noClaimReason: z.string().optional(),
});

type EvalOutput = z.infer<typeof EvalOutputSchema>;

export type ExtractionAbActionState = {
  status: 'idle' | 'success' | 'error';
  message: string;
};

const VARIANTS = {
  gemini31: {
    label: 'Gemini 3.1 Flash Lite',
    routeId: 'google_gemini_3_1_flash_lite_extraction_eval',
    column: 'gemini_3_1_output_json',
    errorColumn: 'gemini_3_1_error',
  },
  qwen37: {
    label: 'Qwen 3.7 Max',
    routeId: 'qwen_3_7_max_extraction_eval',
    column: 'qwen_3_7_output_json',
    errorColumn: 'qwen_3_7_error',
  },
} as const;

function normalizeSourceText(text: string, quote: string | null): string {
  const trimmed = text.trim();
  if (trimmed.length <= 12_000) return trimmed;
  if (!quote) return trimmed.slice(0, 12_000);

  const quoteIndex = trimmed.indexOf(quote);
  if (quoteIndex < 0) return trimmed.slice(0, 12_000);

  const start = Math.max(0, quoteIndex - 4_000);
  const end = Math.min(trimmed.length, quoteIndex + quote.length + 4_000);
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
    JOIN claim_evidence ce ON ce.claim_id = cre.claim_id
    LEFT JOIN messages m ON m.id = ce.source_message_id
    LEFT JOIN document_chunks dc ON dc.id = ce.source_document_chunk_id
    WHERE cre.id = ${reviewEventId}::uuid
      AND cre.action = 'revise'
      AND cre.replacement_claim_id IS NOT NULL
    ORDER BY ce.confidence DESC NULLS LAST, ce.created_at ASC
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
        source_text: string;
      }
    | undefined;
  if (!row) throw new Error('Could not find source evidence for this revised claim.');
  return {
    ...row,
    source_excerpt: normalizeSourceText(row.source_text, row.exact_quote),
  };
}

function resolveEvalRoute(routeId: string): OracleModelRoute {
  const route = getOracleRoute(routeId);
  if (!route) throw new Error(`Could not resolve eval route ${routeId}.`);
  return route;
}

async function runVariant(input: {
  client: OracleAIClient;
  route: OracleModelRoute;
  sourceExcerpt: string;
  correctionLessonsPromptBlock: string;
}): Promise<EvalOutput> {
  const blocks = [
    makeBlock({
      id: 'extraction-system',
      label: 'Extraction system prompt',
      kind: 'stable_system',
      content: EXTRACTION_SYSTEM_PROMPT,
      reasonIncluded: 'A/B/C extraction eval prompt v' + EXTRACTION_PROMPT_VERSION,
    }),
    ...(input.correctionLessonsPromptBlock
      ? [
          makeBlock({
            id: 'reviewer-correction-lessons',
            label: 'Approved reviewer correction lessons',
            kind: 'semi_stable_domain_context' as const,
            content: input.correctionLessonsPromptBlock,
            reasonIncluded: 'approved claim revisions teach extraction corrections',
          }),
        ]
      : []),
    makeBlock({
      id: 'eval-source',
      label: 'Source text for one claim extraction eval',
      kind: 'dynamic_input',
      content: `SOURCE TEXT:\n${input.sourceExcerpt}\n\nReturn the single best operational claim supported by this source text. If there is no operational claim, return claim=null and a short noClaimReason. The claim must quote this source text exactly.`,
      reasonIncluded: 'same source text used across extraction A/B/C variants',
    }),
  ];

  const result = await input.client.runObject<EvalOutput>({
    taskType: 'message_claim_extraction',
    routeId: input.route.routeId,
    promptVersion: EXTRACTION_PROMPT_VERSION,
    blocks,
    schema: EvalOutputSchema,
    providerOptions: {
      cache: { disableCache: true },
    },
  });
  if (!result.validation.ok) {
    throw new Error(result.validation.error.message);
  }
  return result.object;
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
    const lessonPack = await loadClaimCorrectionLessonPack(db, { limit: 14 });
    const client = new OracleAIClient({
      adapters: buildStandardAdapters(),
      fallbackOnError: false,
    });

    await db.execute(sql`
      INSERT INTO claim_extraction_ab_tests (
        claim_review_event_id,
        source_claim_id,
        revised_claim_id,
        source_type,
        source_id,
        source_excerpt
      )
      VALUES (
        ${source.review_event_id}::uuid,
        ${source.source_claim_id}::uuid,
        ${source.revised_claim_id}::uuid,
        ${source.source_type},
        ${source.source_id}::uuid,
        ${source.source_excerpt}
      )
      ON CONFLICT (claim_review_event_id) DO UPDATE
        SET source_excerpt = EXCLUDED.source_excerpt,
            updated_at = now()
    `);

    const failedVariants: string[] = [];
    for (const variant of Object.values(VARIANTS)) {
      try {
        const output = await runVariant({
          client,
          route: resolveEvalRoute(variant.routeId),
          sourceExcerpt: source.source_excerpt,
          correctionLessonsPromptBlock: lessonPack.promptBlock,
        });
        await db.execute(sql`
          UPDATE claim_extraction_ab_tests
          SET ${sql.raw(variant.column)} = ${JSON.stringify(output)}::jsonb,
              ${sql.raw(variant.errorColumn)} = NULL,
              updated_at = now()
          WHERE claim_review_event_id = ${reviewEventId}::uuid
        `);
      } catch (error) {
        failedVariants.push(variant.label);
        await db.execute(sql`
          UPDATE claim_extraction_ab_tests
          SET ${sql.raw(variant.errorColumn)} = ${error instanceof Error ? error.message : String(error)},
              updated_at = now()
          WHERE claim_review_event_id = ${reviewEventId}::uuid
        `);
      }
    }

    revalidatePath('/admin/ai/extraction-ab');
    if (failedVariants.length > 0) {
      return {
        status: 'error',
        message: `Finished, but ${failedVariants.join(' and ')} failed. The error is shown in its column.`,
      };
    }
    return { status: 'success', message: 'Models finished. Results refreshed below.' };
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
