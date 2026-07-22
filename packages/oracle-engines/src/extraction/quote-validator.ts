/**
 * R5 — Deterministic quote validator.
 *
 * The provenance check from
 * docs/oracle/03-candidate-before-claim-validation.md. Pure function:
 * no DB, no I/O. Workers call this for every proposed evidence row
 * before the row is allowed to influence permanent claims.
 *
 * Verdict ladder (highest precedence first):
 *
 *   exact_match
 *     - The proposed quote appears VERBATIM in the source text exactly once,
 *       OR the model supplied offsets that decode to the exact quote.
 *
 *   normalized_match
 *     - The proposed quote appears verbatim in a *normalized* form of the
 *       source text. Used only when the caller supplied a non-empty
 *       NormalizationPolicy. The result records which normalization was
 *       applied so audits can replay the decision.
 *
 *   ambiguous
 *     - The proposed quote appears in the source MORE THAN ONCE and the
 *       model did NOT supply offsets to disambiguate. We refuse to pick.
 *
 *   failed
 *     - Any other condition (paraphrase, punctuation rewrite, synthesized
 *       quote spanning content the source does not contain, supplied
 *       offsets disagree with the source text, etc).
 *
 * Why no LLM-driven fuzzy match?
 *   Provenance must be deterministic. An LLM-graded "close enough" check
 *   would erase the auditability that makes The Oracle valuable.
 */

import { normalize, methodForApplied } from './normalization';
import type {
  QuoteValidationResult,
  ValidateQuoteInput,
  ValidateSourcePointerInput,
  SourcePointerValidationResult,
} from './types';
import { STRICT_VERBATIM_POLICY } from './types';

// ─────────────────────────────────────────────────────────────────────────
// Quote validation
// ─────────────────────────────────────────────────────────────────────────

export function validateQuote(input: ValidateQuoteInput): QuoteValidationResult {
  const { sourceText, exactQuoteProvided, charStartProvided, charEndProvided } = input;
  const policy = input.normalizationPolicy ?? STRICT_VERBATIM_POLICY;

  if (!exactQuoteProvided || exactQuoteProvided.length === 0) {
    return {
      verdict: 'failed',
      validationStatus: 'failed',
      validationMethod: 'none',
      failedCheckName: 'quote_exact_match',
      detail: 'exactQuoteProvided is empty.',
    };
  }

  // ── 1. If the model supplied offsets, they're the ground truth.
  // We REQUIRE both offsets (not just one), they must be in order, and the
  // slice must equal the provided quote exactly.
  const hasStart = typeof charStartProvided === 'number';
  const hasEnd = typeof charEndProvided === 'number';
  if (hasStart !== hasEnd) {
    return {
      verdict: 'failed',
      validationStatus: 'failed',
      validationMethod: 'none',
      failedCheckName: 'quote_offsets_match',
      detail: 'charStartProvided and charEndProvided must be supplied together or not at all.',
    };
  }
  if (hasStart && hasEnd) {
    if (charStartProvided! < 0 || charEndProvided! < 0) {
      return {
        verdict: 'failed',
        validationStatus: 'failed',
        validationMethod: 'verbatim_offset_match',
        failedCheckName: 'quote_offsets_match',
        detail: 'Provided offsets are negative.',
      };
    }
    if (charEndProvided! < charStartProvided!) {
      return {
        verdict: 'failed',
        validationStatus: 'failed',
        validationMethod: 'verbatim_offset_match',
        failedCheckName: 'quote_offsets_match',
        detail: 'Provided charEnd precedes charStart.',
      };
    }
    if (charEndProvided! > sourceText.length) {
      return {
        verdict: 'failed',
        validationStatus: 'failed',
        validationMethod: 'verbatim_offset_match',
        failedCheckName: 'quote_offsets_match',
        detail: 'Provided charEnd extends past the source text.',
      };
    }
    const slice = sourceText.slice(charStartProvided, charEndProvided);
    if (slice === exactQuoteProvided) {
      return {
        verdict: 'exact_match',
        validationStatus: 'exact_match',
        validationMethod: 'verbatim_offset_match',
        validatedExactQuote: slice,
        validatedCharStart: charStartProvided,
        validatedCharEnd: charEndProvided,
        detail: 'Quote matched at provided offsets.',
      };
    }
    return {
      verdict: 'failed',
      validationStatus: 'failed',
      validationMethod: 'verbatim_offset_match',
      failedCheckName: 'quote_offsets_match',
      detail: `Source text at [${charStartProvided}, ${charEndProvided}] does not equal exactQuoteProvided. Got: ${JSON.stringify(
        slice.slice(0, 200),
      )}`,
    };
  }

  // ── 2. No offsets supplied. Try verbatim .indexOf scan.
  const firstIdx = sourceText.indexOf(exactQuoteProvided);
  if (firstIdx !== -1) {
    const secondIdx = sourceText.indexOf(exactQuoteProvided, firstIdx + 1);
    if (secondIdx !== -1) {
      return {
        verdict: 'ambiguous',
        validationStatus: 'ambiguous',
        validationMethod: 'verbatim_includes',
        failedCheckName: 'quote_exact_match',
        detail: 'Quote appears more than once in source. Model must supply explicit offsets.',
      };
    }
    return {
      verdict: 'exact_match',
      validationStatus: 'exact_match',
      validationMethod: 'verbatim_includes',
      validatedExactQuote: exactQuoteProvided,
      validatedCharStart: firstIdx,
      validatedCharEnd: firstIdx + exactQuoteProvided.length,
      detail: 'Quote matched via single-occurrence verbatim scan.',
    };
  }

  // ── 3. Verbatim failed. If the caller enabled any normalization, retry
  // against the normalized form of BOTH the source and the quote.
  const policyEnabled =
    !!policy.allowCRLF ||
    !!policy.allowSmartQuotes ||
    !!policy.allowWhitespaceCollapse ||
    !!policy.allowLeadingTrailingTrim ||
    !!policy.allowMarkdownFormatting;
  if (policyEnabled) {
    const normSource = normalize(sourceText, policy);
    const normQuote = normalize(exactQuoteProvided, policy);
    const normFirstIdx = normSource.text.indexOf(normQuote.text);
    if (normFirstIdx !== -1) {
      const normSecondIdx = normSource.text.indexOf(normQuote.text, normFirstIdx + 1);
      if (normSecondIdx !== -1) {
        return {
          verdict: 'ambiguous',
          validationStatus: 'ambiguous',
          validationMethod: methodForApplied(normSource.applied.concat(normQuote.applied)),
          failedCheckName: 'quote_exact_match',
          detail:
            'Quote appears more than once after normalization. Model must supply explicit offsets.',
        };
      }
      // Normalized match. The validatedExactQuote we report is the substring
      // of the ORIGINAL source covering the same logical span. For a strict
      // implementation we'd need to map normalized offsets back to original
      // offsets — that's nontrivial when whitespace was collapsed. As a
      // conservative compromise we report the normalized quote as validated.
      // Workers that need exact source bytes must use strict verbatim mode.
      return {
        verdict: 'normalized_match',
        validationStatus: 'normalized_match',
        validationMethod: methodForApplied(normSource.applied.concat(normQuote.applied)),
        validatedExactQuote: normQuote.text,
        validatedCharStart: normFirstIdx,
        validatedCharEnd: normFirstIdx + normQuote.text.length,
        detail:
          'Quote matched after normalization. Source/quote offsets are against the normalized form.',
      };
    }
  }

  // ── 4. Fuzzy fallback (opt-in via allowFuzzy). For messy spoken transcripts
  // the model paraphrases disfluent speech, so verbatim/normalized matching
  // fails even when the claim genuinely came from this utterance. We accept the
  // match when the quote's content tokens sufficiently overlap the source, and
  // anchor the evidence to the REAL source text (the full utterance) rather than
  // the model's paraphrase — provenance still points at actual spoken words.
  // This is a deterministic token check (no LLM grader). See
  // DECISIONS.md D-transcript-fuzzy-quote.
  if (input.allowFuzzy) {
    const minOverlap = input.fuzzyMinOverlap ?? 0.5;
    const tokenize = (s: string): string[] => s.toLowerCase().match(/[a-z0-9']+/g) ?? [];
    const quoteTokens = tokenize(exactQuoteProvided);
    const sourceTokens = new Set(tokenize(sourceText));
    if (quoteTokens.length >= 4 && sourceTokens.size > 0) {
      const present = quoteTokens.filter((t) => sourceTokens.has(t)).length;
      const overlap = present / quoteTokens.length;
      if (overlap >= minOverlap) {
        return {
          verdict: 'normalized_match',
          validationStatus: 'normalized_match',
          validationMethod: 'fuzzy_token_overlap',
          validatedExactQuote: sourceText,
          validatedCharStart: 0,
          validatedCharEnd: sourceText.length,
          detail: `Fuzzy match: ${present}/${quoteTokens.length} quote tokens (${Math.round(
            overlap * 100,
          )}%) present in the source utterance; evidence anchored to the full source utterance.`,
        };
      }
    }
  }

  return {
    verdict: 'failed',
    validationStatus: 'failed',
    validationMethod: 'verbatim_includes',
    failedCheckName: 'quote_exact_match',
    detail: 'exactQuoteProvided was not found in sourceText.',
  };
}

// ─────────────────────────────────────────────────────────────────────────
// Source-pointer validation
// Mirrors extraction_candidate_evidence_source_check from
// migrations/sql/13_extraction_constraints.sql.
// ─────────────────────────────────────────────────────────────────────────

export function validateSourcePointer(
  input: ValidateSourcePointerInput,
): SourcePointerValidationResult {
  const {
    sourceType,
    sourceMessageId,
    sourceDocumentChunkId,
    sourceExternalRecordId,
    createdByEmployeeId,
  } = input;

  switch (sourceType) {
    case 'message':
      if (!sourceMessageId) {
        return {
          ok: false,
          failedCheckName: 'source_type_valid',
          detail: 'source_type=message requires non-null source_message_id.',
        };
      }
      return { ok: true, detail: 'message source pointer present.' };

    case 'document_chunk':
      if (!sourceDocumentChunkId) {
        return {
          ok: false,
          failedCheckName: 'source_type_valid',
          detail: 'source_type=document_chunk requires non-null source_document_chunk_id.',
        };
      }
      return { ok: true, detail: 'document_chunk source pointer present.' };

    case 'external_system':
      if (!sourceExternalRecordId) {
        return {
          ok: false,
          failedCheckName: 'source_type_valid',
          detail: 'source_type=external_system requires non-null source_external_record_id.',
        };
      }
      return { ok: true, detail: 'external_system source pointer present.' };

    case 'manual_admin':
      if (!createdByEmployeeId) {
        return {
          ok: false,
          failedCheckName: 'source_type_valid',
          detail: 'source_type=manual_admin requires non-null created_by_employee_id.',
        };
      }
      return { ok: true, detail: 'manual_admin source pointer present.' };

    default:
      return {
        ok: false,
        failedCheckName: 'source_type_valid',
        detail: `unknown source type: ${sourceType}`,
      };
  }
}
