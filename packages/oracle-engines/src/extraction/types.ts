/**
 * R5 extraction pipeline types.
 *
 * Shared shapes for the quote validator, source-pointer validator,
 * normalization helpers, and the promotion decision/executor.
 *
 * Per docs/oracle/03-candidate-before-claim-validation.md and
 * docs/oracle/05-ai-retrofit-phase-packet.md Phase R5.
 */

import type {
  EvidenceSourceType,
  EvidenceValidationStatus,
  ValidationCheckName,
  ValidationCheckStatus,
} from '@oracle/shared';

// ─────────────────────────────────────────────────────────────────────────
// Normalization policy
// ─────────────────────────────────────────────────────────────────────────

/**
 * Normalization controls — all OFF by default. Default behavior is
 * strictly verbatim match. Enable an option only when the source type
 * justifies it (e.g. OCR text from PDFs has unreliable whitespace).
 *
 * When normalized matching succeeds, the result records exactly which
 * normalization was applied so audits can replay the decision.
 */
export interface NormalizationPolicy {
  /** Treat CR + LF and LF as equivalent line endings. */
  allowCRLF?: boolean;
  /** Treat curly/smart quotes as straight quotes (and vice versa). */
  allowSmartQuotes?: boolean;
  /**
   * Collapse runs of internal whitespace to a single space before matching.
   * Intended for OCR / PDF text where whitespace is unreliable. NEVER enable
   * for chat messages — message content is exact by construction.
   */
  allowWhitespaceCollapse?: boolean;
  /** Strip leading/trailing whitespace before matching. */
  allowLeadingTrailingTrim?: boolean;
  /**
   * Treat Markdown presentation markers as formatting, not quote content.
   * Intended for uploaded Markdown documents where the source may contain
   * emphasis markers, inline code ticks, links, or table cell separators that
   * a model naturally omits while still copying the same visible words.
   */
  allowMarkdownFormatting?: boolean;
}

export const STRICT_VERBATIM_POLICY: NormalizationPolicy = {};

/** Conservative policy for OCR / PDF document sources. */
export const PDF_OCR_NORMALIZATION_POLICY: NormalizationPolicy = {
  allowCRLF: true,
  allowSmartQuotes: true,
  allowWhitespaceCollapse: true,
  allowLeadingTrailingTrim: true,
};

/** Conservative policy for Markdown/plain-text documents. */
export const MARKDOWN_DOCUMENT_NORMALIZATION_POLICY: NormalizationPolicy = {
  allowCRLF: true,
  allowSmartQuotes: true,
  allowWhitespaceCollapse: true,
  allowLeadingTrailingTrim: true,
  allowMarkdownFormatting: true,
};

// ─────────────────────────────────────────────────────────────────────────
// Quote validation
// ─────────────────────────────────────────────────────────────────────────

export type QuoteValidationVerdict = 'exact_match' | 'normalized_match' | 'failed' | 'ambiguous';

export type ValidationMethod =
  | 'verbatim_offset_match'
  | 'verbatim_includes'
  | 'normalized_crlf'
  | 'normalized_smart_quotes'
  | 'normalized_whitespace'
  | 'normalized_trim'
  | 'normalized_markdown'
  | 'normalized_combined'
  | 'fuzzy_token_overlap'
  | 'none';

export interface ValidateQuoteInput {
  /** The source text the model claims to be quoting. */
  sourceText: string;
  /** The quote the model produced. */
  exactQuoteProvided: string;
  /**
   * Optional offsets the model provided. When present, BOTH are required
   * and they must match exactly — provided offsets cannot disagree with
   * the source text.
   */
  charStartProvided?: number;
  charEndProvided?: number;
  /** Optional normalization controls. Defaults to strict verbatim. */
  normalizationPolicy?: NormalizationPolicy;
  /**
   * Opt-in fuzzy fallback for messy spoken transcripts, where the model
   * paraphrases disfluent speech rather than reproducing it verbatim. When the
   * provided quote's content tokens sufficiently overlap the source utterance,
   * the match is accepted and the evidence is anchored to the REAL source text
   * (the full utterance), NOT the model's paraphrase — so provenance still
   * points at real spoken words. OFF by default; document sources stay strict.
   * See DECISIONS.md D-transcript-fuzzy-quote.
   */
  allowFuzzy?: boolean;
  /** Minimum fraction of quote content-tokens that must appear in the source. Default 0.5. */
  fuzzyMinOverlap?: number;
}

export interface QuoteValidationResult {
  verdict: QuoteValidationVerdict;
  validationStatus: EvidenceValidationStatus;
  validationMethod: ValidationMethod;
  validatedExactQuote?: string;
  validatedCharStart?: number;
  validatedCharEnd?: number;
  /** Which deterministic check failed, if any. Used by callers writing to extraction_validation_results. */
  failedCheckName?: ValidationCheckName;
  /** Free-form human-readable explanation. */
  detail: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Source pointer validation
// ─────────────────────────────────────────────────────────────────────────

/**
 * Mirrors the claim_evidence_source_check / extraction_candidate_evidence_source_check
 * CHECK constraints from spec 6.8 and 13_extraction_constraints.sql. Used to
 * fail fast BEFORE the row is written.
 */
export interface ValidateSourcePointerInput {
  sourceType: EvidenceSourceType;
  sourceMessageId?: string | null;
  sourceDocumentChunkId?: string | null;
  sourceExternalRecordId?: string | null;
  createdByEmployeeId?: string | null;
}

export interface SourcePointerValidationResult {
  ok: boolean;
  failedCheckName?: ValidationCheckName;
  detail: string;
}

// ─────────────────────────────────────────────────────────────────────────
// Validation result records (for extraction_validation_results)
// ─────────────────────────────────────────────────────────────────────────

export interface ValidationResultRecord {
  candidateId?: string;
  candidateEvidenceId?: string;
  checkName: ValidationCheckName;
  status: ValidationCheckStatus;
  detail?: string;
  metadataJson?: unknown;
}
