import { task } from '@trigger.dev/sdk/v3';
import { sql } from 'drizzle-orm';
import { getDirectDb } from '@oracle/db/client';
import {
  buildStandardAdapters,
  CLAIM_TYPES,
  ExtractionClaimSchema,
  EXTRACTION_PROMPT_VERSION,
  EXTRACTION_SYSTEM_PROMPT,
  getOracleRoute,
  loadClaimCorrectionLessonPack,
  makeBlock,
  OracleAIClient,
  type OracleModelRoute,
} from '@oracle/ai';
import { KNOWLEDGE_DOMAINS } from '@oracle/shared';
import { z } from 'zod';

const EvalOutputSchema = z.object({
  claim: ExtractionClaimSchema.nullable().optional().default(null),
  noClaimReason: z.string().optional(),
});

type EvalOutput = z.infer<typeof EvalOutputSchema>;

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

function resolveEvalRoute(routeId: string): OracleModelRoute {
  const route = getOracleRoute(routeId);
  if (!route) throw new Error(`Could not resolve eval route ${routeId}.`);
  return route;
}

function buildVariantBlocks(input: {
  sourceId: string;
  sourceExcerpt: string;
  sourceExactQuote: string | null;
  correctionLessonsPromptBlock: string;
  repairInstruction: string | null;
}) {
  const exactQuote = input.sourceExactQuote?.trim() || null;
  return [
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
      content: `SOURCE ID:\n${input.sourceId}\n\nEXACT QUOTE TO USE:\n${exactQuote ?? '(No separate quote was stored; choose one exact quote from SOURCE TEXT.)'}\n\nSOURCE TEXT:\n${input.sourceExcerpt}\n\nThis source text is from an already-approved human claim revision, so it does contain an operational claim. Return the single best operational claim supported by this source text.\n\nOutput requirements:\n- Return JSON with top-level key "claim"; "claim" must be an object, never null.\n- claim.claimType must be one of: ${CLAIM_TYPES.join(', ')}.\n- claim.impactScore must be an integer from 1 to 10.\n- claim.confidenceScore must be an integer from 1 to 10.\n- claim.domains must contain only these exact IDs: ${KNOWLEDGE_DOMAINS.join(', ')}. Do not invent display names or top-domain labels.\n- claim.evidence must be an object with exactQuote, sourceMessageId, and confidence.\n- claim.evidence.sourceMessageId must be exactly: ${input.sourceId}.\n- claim.evidence.exactQuote must be exactly EXACT QUOTE TO USE when a stored quote is shown; otherwise copy it character-for-character from SOURCE TEXT.`,
      reasonIncluded: 'same source text used across extraction A/B/C variants',
    }),
    ...(input.repairInstruction
      ? [
          makeBlock({
            id: 'eval-repair-instruction',
            label: 'Extraction eval repair instruction',
            kind: 'dynamic_input' as const,
            content: input.repairInstruction,
            reasonIncluded: 'retry malformed extraction eval output',
          }),
        ]
      : []),
  ];
}

async function runVariant(input: {
  client: OracleAIClient;
  route: OracleModelRoute;
  sourceId: string;
  sourceExcerpt: string;
  sourceExactQuote: string | null;
  correctionLessonsPromptBlock: string;
}): Promise<EvalOutput> {
  let lastError: Error | null = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const result = await input.client.runObject<EvalOutput>({
        taskType: 'message_claim_extraction',
        routeId: input.route.routeId,
        promptVersion: EXTRACTION_PROMPT_VERSION,
        blocks: buildVariantBlocks({
          sourceId: input.sourceId,
          sourceExcerpt: input.sourceExcerpt,
          sourceExactQuote: input.sourceExactQuote,
          correctionLessonsPromptBlock: input.correctionLessonsPromptBlock,
          repairInstruction:
            attempt === 1
              ? null
              : `Your previous response did not pass validation: ${lastError?.message ?? 'unknown validation error'}\n\nReturn corrected JSON with a top-level "claim" object that matches the exact extraction schema. Do not return null, {}, display-name domains, or a no-claim response.`,
        }),
        schema: EvalOutputSchema,
        providerOptions: {
          cache: { disableCache: true },
        },
      });
      if (!result.validation.ok) {
        throw new Error(result.validation.error.message);
      }
      if (!result.object.claim) {
        throw new Error('Model returned no claim object.');
      }
      return result.object;
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
    }
  }

  throw lastError ?? new Error('Model did not return a claim object.');
}

export async function processExtractionAbEval(reviewEventId: string) {
  const db = getDirectDb();
  const claimed = await db.execute(sql`
    UPDATE claim_extraction_ab_tests
    SET run_status = 'running',
        run_started_at = now(),
        run_completed_at = NULL,
        last_run_error = NULL,
        updated_at = now()
    WHERE claim_review_event_id = ${reviewEventId}::uuid
      AND (
        run_status IN ('queued', 'idle', 'failed')
        OR (run_status = 'running' AND run_started_at < now() - interval '15 minutes')
      )
    RETURNING id
  `);
  if ([...claimed].length === 0) {
    return { ok: true, skipped: true, reason: 'not queued or already running' };
  }

  try {
    const source = await loadSourceForReviewEvent(reviewEventId);
    await db.execute(sql`
      UPDATE claim_extraction_ab_tests
      SET source_excerpt = ${source.source_excerpt},
          updated_at = now()
      WHERE claim_review_event_id = ${reviewEventId}::uuid
    `);

    const lessonPack = await loadClaimCorrectionLessonPack(db, { limit: 14 });
    const client = new OracleAIClient({
      adapters: buildStandardAdapters(),
    });

    const variantResults = await Promise.all(
      Object.values(VARIANTS).map(async (variant) => {
        try {
          const output = await runVariant({
            client,
            route: resolveEvalRoute(variant.routeId),
            sourceId: source.source_id ?? source.review_event_id,
            sourceExcerpt: source.source_excerpt,
            sourceExactQuote: source.exact_quote,
            correctionLessonsPromptBlock: lessonPack.promptBlock,
          });
          await db.execute(sql`
            UPDATE claim_extraction_ab_tests
            SET ${sql.raw(variant.column)} = ${JSON.stringify(output)}::jsonb,
                ${sql.raw(variant.errorColumn)} = NULL,
                updated_at = now()
            WHERE claim_review_event_id = ${reviewEventId}::uuid
          `);
          return { label: variant.label, ok: true };
        } catch (error) {
          const message = error instanceof Error ? error.message : String(error);
          await db.execute(sql`
            UPDATE claim_extraction_ab_tests
            SET ${sql.raw(variant.errorColumn)} = ${message},
                updated_at = now()
            WHERE claim_review_event_id = ${reviewEventId}::uuid
          `);
          return { label: variant.label, ok: false, error: message };
        }
      }),
    );

    const failures = variantResults.filter((result) => !result.ok);
    await db.execute(sql`
      UPDATE claim_extraction_ab_tests
      SET run_status = ${failures.length > 0 ? 'failed' : 'complete'},
          run_completed_at = now(),
          last_run_error = ${failures.length > 0
            ? `Failed variants: ${failures.map((failure) => failure.label).join(', ')}`
            : null},
          updated_at = now()
      WHERE claim_review_event_id = ${reviewEventId}::uuid
    `);

    return { ok: failures.length === 0, failures };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    await db.execute(sql`
      UPDATE claim_extraction_ab_tests
      SET run_status = 'failed',
          run_completed_at = now(),
          last_run_error = ${message},
          updated_at = now()
      WHERE claim_review_event_id = ${reviewEventId}::uuid
    `);
    throw error;
  }
}

export const extractionAbEvalTask = task({
  id: 'extraction-ab-eval',
  run: async (payload: { reviewEventId: string }) => {
    return processExtractionAbEval(payload.reviewEventId);
  },
});
