/**
 * R7 — Vertex explicit-cache profitability heuristic.
 *
 * Pure function. Encodes the rule from
 * docs/oracle/02-provider-native-ai-architecture.md "Explicit Cache Heuristic":
 *
 *   useExplicitGeminiCache =
 *     (sourceTokenEstimate >= 25_000 && expectedReuseCount >= 3)
 *     OR (sourceTokenEstimate >= 100_000 && expectedReuseCount >= 2)
 *
 * Vertex explicit caches bill while they exist. Creating one for a
 * one-off chunk or for a small reuse window is a net cost loss — the
 * storage fee outpaces the saved input-token spend. The heuristic
 * captures the break-even points conservatively. Workers call this
 * BEFORE creating the cache; if false, they fall back to implicit
 * caching (which is free and provider-managed).
 *
 * Returns a structured decision so the cache-lifecycle bookkeeping
 * (`provider_cached_content` row) can record the reasoning at creation
 * time.
 */

export interface CacheProfitabilityInput {
  /** Estimated token count of the source content the cache would hold. */
  sourceTokenEstimate: number;
  /** How many times the worker plans to call against this cache. */
  expectedReuseCount: number;
}

export type CacheProfitabilityDecision =
  | {
      kind: 'create_explicit_cache';
      rule: 'medium_source_high_reuse' | 'large_source_modest_reuse';
      detail: string;
    }
  | {
      kind: 'skip_explicit_cache';
      reason:
        | 'source_too_small'
        | 'reuse_too_low'
        | 'reuse_too_low_for_medium'
        | 'reuse_too_low_for_large';
      detail: string;
    };

export const EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD = 25_000;
export const EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD = 3;
export const EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD = 100_000;
export const EXPLICIT_CACHE_LARGE_SOURCE_REUSE_THRESHOLD = 2;

/**
 * Cheap, deterministic token estimate for cache-profitability decisions.
 *
 * Uses the well-known 4-chars-per-token approximation. Provider-native
 * adapters will return real token counts after the call; the heuristic
 * here just needs a stable estimate to gate the create-or-skip decision
 * BEFORE the call.
 */
export function estimateTokensForCache(content: string): number {
  return Math.ceil(content.length / 4);
}

export function decideCacheProfitability(input: CacheProfitabilityInput): CacheProfitabilityDecision {
  const { sourceTokenEstimate, expectedReuseCount } = input;

  if (
    sourceTokenEstimate >= EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD &&
    expectedReuseCount >= EXPLICIT_CACHE_LARGE_SOURCE_REUSE_THRESHOLD
  ) {
    return {
      kind: 'create_explicit_cache',
      rule: 'large_source_modest_reuse',
      detail: `Source is large (${sourceTokenEstimate} ≥ ${EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD} tokens) and will be reused ${expectedReuseCount} ≥ ${EXPLICIT_CACHE_LARGE_SOURCE_REUSE_THRESHOLD} times.`,
    };
  }

  if (
    sourceTokenEstimate >= EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD &&
    expectedReuseCount >= EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD
  ) {
    return {
      kind: 'create_explicit_cache',
      rule: 'medium_source_high_reuse',
      detail: `Source is medium (${sourceTokenEstimate} ≥ ${EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD} tokens) and will be reused ${expectedReuseCount} ≥ ${EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD} times.`,
    };
  }

  if (sourceTokenEstimate < EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD) {
    return {
      kind: 'skip_explicit_cache',
      reason: 'source_too_small',
      detail: `Source is below the ${EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD}-token threshold (${sourceTokenEstimate}); explicit cache storage fees would outpace savings. Use implicit caching.`,
    };
  }

  if (sourceTokenEstimate < EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD) {
    return {
      kind: 'skip_explicit_cache',
      reason: 'reuse_too_low_for_medium',
      detail: `Source is medium-sized but reuse count (${expectedReuseCount}) is below the ${EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD}-pass threshold; use implicit caching.`,
    };
  }

  return {
    kind: 'skip_explicit_cache',
    reason: 'reuse_too_low_for_large',
    detail: `Source is large but reuse count (${expectedReuseCount}) is below the ${EXPLICIT_CACHE_LARGE_SOURCE_REUSE_THRESHOLD}-pass threshold; use implicit caching.`,
  };
}
