/**
 * R5 — Deterministic candidate hash.
 *
 * Used for:
 *  - Postgres advisory locking during promotion (`pg_try_advisory_xact_lock`
 *    takes a bigint; we feed `hashtextextended($1, 0)` the hex string this
 *    function returns).
 *  - In-transaction duplicate detection (two workers racing to promote the
 *    same logical claim hash to the same id).
 *
 * The hash MUST be stable across:
 *   - process restarts
 *   - worker re-tries
 *   - machine boundaries
 * so we use deterministic JSON canonicalization (sorted keys, no
 * insignificant whitespace) and sha256.
 */

import { createHash } from 'node:crypto';

export interface CandidateHashInputs {
  /** Normalized claim summary, lowercased + collapsed whitespace. */
  summary: string;
  /** Sorted list of top-domain IDs. */
  topDomainIds: string[];
  /**
   * Sorted, validated quote substrings — NOT the model's proposed quotes.
   * Using the validated form means two workers that extract the same fact
   * with slightly different model wording but the same validated source
   * span will collide and dedup correctly.
   */
  validatedQuotes: string[];
  /** Sorted source pointers — each one is `${sourceType}:${sourceId}`. */
  sourcePointers: string[];
}

export interface MapElementCandidateHashInputs {
  documentId: string;
  mapElementRef: string;
}

/**
 * Produce a deterministic sha256 hex hash for the candidate.
 *
 * Two candidates with the same logical content (same summary modulo case
 * and whitespace, same domains, same evidence spans) MUST produce the
 * same hash. That equality is what the advisory lock and duplicate
 * detection rely on.
 */
export function computeCandidateHash(inputs: CandidateHashInputs): string {
  const canonical = {
    summary: canonicalizeSummary(inputs.summary),
    topDomainIds: [...inputs.topDomainIds].map((d) => d.trim().toLowerCase()).sort(),
    validatedQuotes: [...inputs.validatedQuotes].map((q) => q.trim()).sort(),
    sourcePointers: [...inputs.sourcePointers].map((s) => s.trim()).sort(),
  };
  const json = JSON.stringify(canonical);
  return createHash('sha256').update(json, 'utf8').digest('hex');
}

/**
 * Produce the Stage-3 macro-first dedup key for map-referenced document claims.
 *
 * Map claims intentionally ignore summary wording and quote span: if two valid
 * candidates refer to the same map node/edge in the same document, they are the
 * same within-source fact and the first promoted claim wins.
 */
export function computeMapElementCandidateHash(inputs: MapElementCandidateHashInputs): string {
  const canonical = {
    kind: 'document_map_element',
    documentId: inputs.documentId.trim().toLowerCase(),
    mapElementRef: inputs.mapElementRef.trim(),
  };
  const json = JSON.stringify(canonical);
  return createHash('sha256').update(json, 'utf8').digest('hex');
}

/**
 * Canonicalize a claim summary so trivially-different wording collides.
 * Lowercase, collapse internal whitespace, strip leading/trailing
 * whitespace. We deliberately don't strip punctuation — a claim "X must
 * happen before Y" vs "X must happen, before Y" can genuinely be different
 * statements and should NOT be deduped.
 */
export function canonicalizeSummary(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, ' ');
}
