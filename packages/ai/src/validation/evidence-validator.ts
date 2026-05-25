/**
 * EvidenceValidator — deterministic verification that a model-proposed
 * `exactQuote` physically exists in its claimed source text.
 *
 * This is the binary provenance check from
 * docs/oracle/03-candidate-before-claim-validation.md "Provenance vs.
 * Corroboration". If this fails, the candidate must be destroyed.
 *
 * R2 ships the core logic (.includes + offsets, single-source). The full
 * spec (normalization policy, edited-message rejection, multi-line
 * boundaries) lands in R5 (claim extraction worker) where the full
 * candidate-before-claim pipeline is wired up.
 */

export type QuoteValidationVerdict =
  | 'exact_match'
  | 'normalized_match'
  | 'failed'
  | 'ambiguous';

export interface QuoteValidationResult {
  verdict: QuoteValidationVerdict;
  validatedExactQuote?: string;
  validatedCharStart?: number;
  validatedCharEnd?: number;
  validationMethod: 'verbatim_includes' | 'verbatim_offset_match' | 'none';
  detail: string;
}

export interface ValidateQuoteArgs {
  /** The source text the model claims to be quoting from. */
  sourceText: string;
  /** The quote the model produced. */
  exactQuoteProvided: string;
  /** Optional char offsets the model provided. */
  charStartProvided?: number;
  charEndProvided?: number;
}

export class EvidenceValidator {
  validateQuote(args: ValidateQuoteArgs): QuoteValidationResult {
    const { sourceText, exactQuoteProvided, charStartProvided, charEndProvided } = args;

    if (!exactQuoteProvided || exactQuoteProvided.length === 0) {
      return {
        verdict: 'failed',
        validationMethod: 'none',
        detail: 'exactQuoteProvided is empty.',
      };
    }

    // If offsets were given, prefer them. They must match exactly.
    if (typeof charStartProvided === 'number' && typeof charEndProvided === 'number') {
      const slice = sourceText.slice(charStartProvided, charEndProvided);
      if (slice === exactQuoteProvided) {
        return {
          verdict: 'exact_match',
          validatedExactQuote: slice,
          validatedCharStart: charStartProvided,
          validatedCharEnd: charEndProvided,
          validationMethod: 'verbatim_offset_match',
          detail: 'Quote matched exactly at provided offsets.',
        };
      }
      return {
        verdict: 'failed',
        validationMethod: 'verbatim_offset_match',
        detail: `Source text at offsets [${charStartProvided}, ${charEndProvided}] does not equal exactQuoteProvided.`,
      };
    }

    // No offsets — scan for the quote.
    const firstIdx = sourceText.indexOf(exactQuoteProvided);
    if (firstIdx === -1) {
      return {
        verdict: 'failed',
        validationMethod: 'verbatim_includes',
        detail: 'exactQuoteProvided was not found in sourceText.',
      };
    }
    // Ambiguity check: if the quote appears more than once we cannot be sure
    // which occurrence is the source. Reject unless the model provides offsets.
    const secondIdx = sourceText.indexOf(exactQuoteProvided, firstIdx + 1);
    if (secondIdx !== -1) {
      return {
        verdict: 'ambiguous',
        validationMethod: 'verbatim_includes',
        detail: 'Quote appears more than once in sourceText. Model must provide explicit offsets.',
      };
    }
    return {
      verdict: 'exact_match',
      validatedExactQuote: exactQuoteProvided,
      validatedCharStart: firstIdx,
      validatedCharEnd: firstIdx + exactQuoteProvided.length,
      validationMethod: 'verbatim_includes',
      detail: 'Quote matched exactly via single-occurrence includes() scan.',
    };
  }
}

let cached: EvidenceValidator | null = null;
export function getEvidenceValidator(): EvidenceValidator {
  if (!cached) cached = new EvidenceValidator();
  return cached;
}
