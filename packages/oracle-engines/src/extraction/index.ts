/**
 * R5 — Extraction pipeline barrel.
 *
 * Workers and Trigger.dev tasks import from here. The promotion executor
 * is wired in R6; R5 exports the pure pieces (validator + decision +
 * candidate hash) so the executor is just SQL plumbing on top.
 */

export { validateQuote, validateSourcePointer } from './quote-validator';
export { normalize, methodForApplied } from './normalization';
export { computeCandidateHash, canonicalizeSummary } from './candidate-hash';
export {
  decidePromotion,
  PROMOTION_TRANSACTION_RUNBOOK,
  type CandidateSnapshot,
  type PromotionDecision,
} from './promote-candidate';
export type {
  NormalizationPolicy,
  QuoteValidationVerdict,
  QuoteValidationResult,
  ValidationMethod,
  ValidateQuoteInput,
  ValidateSourcePointerInput,
  SourcePointerValidationResult,
  ValidationResultRecord,
} from './types';
export type { NormalizedString } from './normalization';
export { STRICT_VERBATIM_POLICY, PDF_OCR_NORMALIZATION_POLICY } from './types';
