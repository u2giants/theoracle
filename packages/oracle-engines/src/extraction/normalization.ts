/**
 * R5 normalization helpers.
 *
 * Every helper is pure. They produce a normalized form of the input string
 * given the supplied policy, and they signal (via the return shape) exactly
 * which normalizations actually changed the input so the quote validator
 * can report the precise method that succeeded.
 *
 * Default policy is no normalization. Enable options selectively, never
 * blanket-on, because each normalization erodes provenance.
 */

import type { NormalizationPolicy, ValidationMethod } from './types';

export interface NormalizedString {
  text: string;
  /** Which normalizations the policy enabled that actually changed the text. */
  applied: NonNullable<keyof NormalizationPolicy>[];
}

/** Replace CRLF and bare CR with LF. */
function normalizeCRLF(s: string): string {
  return s.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

/**
 * Map common smart-quote variants to their straight equivalents.
 *   ‘ ’ ‚ ‛  → '
 *   “ ” „ ‟  → "
 *   ‹ ›        → '
 *   « »        → "
 *   …          → '...'
 *   – —        → '-'
 */
function normalizeSmartQuotes(s: string): string {
  return s
    .replace(/[‘’‚‛‹›]/g, "'")
    .replace(/[“”„‟«»]/g, '"')
    .replace(/…/g, '...')
    .replace(/[–—]/g, '-');
}

/** Collapse runs of internal whitespace to a single space. */
function normalizeInternalWhitespace(s: string): string {
  return s.replace(/[ \t\f\v]+/g, ' ').replace(/[ \t\f\v]*\n[ \t\f\v]*/g, '\n');
}

/** Strip leading/trailing whitespace. */
function normalizeTrim(s: string): string {
  return s.trim();
}

/**
 * Apply the policy. Returns the normalized text and the list of options
 * that actually changed the input (so callers can report the precise
 * method that succeeded).
 */
export function normalize(input: string, policy: NormalizationPolicy): NormalizedString {
  const applied: NonNullable<keyof NormalizationPolicy>[] = [];
  let out = input;

  if (policy.allowCRLF) {
    const next = normalizeCRLF(out);
    if (next !== out) applied.push('allowCRLF');
    out = next;
  }
  if (policy.allowSmartQuotes) {
    const next = normalizeSmartQuotes(out);
    if (next !== out) applied.push('allowSmartQuotes');
    out = next;
  }
  if (policy.allowWhitespaceCollapse) {
    const next = normalizeInternalWhitespace(out);
    if (next !== out) applied.push('allowWhitespaceCollapse');
    out = next;
  }
  if (policy.allowLeadingTrailingTrim) {
    const next = normalizeTrim(out);
    if (next !== out) applied.push('allowLeadingTrailingTrim');
    out = next;
  }

  return { text: out, applied };
}

/** Pick the most precise ValidationMethod tag given the applied normalizations. */
export function methodForApplied(applied: NonNullable<keyof NormalizationPolicy>[]): ValidationMethod {
  if (applied.length === 0) return 'verbatim_includes';
  if (applied.length > 1) return 'normalized_combined';
  switch (applied[0]) {
    case 'allowCRLF':
      return 'normalized_crlf';
    case 'allowSmartQuotes':
      return 'normalized_smart_quotes';
    case 'allowWhitespaceCollapse':
      return 'normalized_whitespace';
    case 'allowLeadingTrailingTrim':
      return 'normalized_trim';
    default:
      // Unreachable in practice — every NormalizationPolicy key is handled
      // above. The default exists so the compiler can prove exhaustiveness
      // even after new policy keys are added without their case arms.
      return 'normalized_combined';
  }
}
