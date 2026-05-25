/**
 * R7 acceptance gate verification script.
 *
 * Run with: pnpm --filter @oracle/engines verify:r7
 *
 * Covers the new pure pieces R7 ships:
 *
 *   - decideCacheProfitability: the 4-case truth table from the
 *     Explicit Cache Heuristic in
 *     docs/oracle/02-provider-native-ai-architecture.md.
 *   - estimateTokensForCache: stable 4-chars-per-token approximation.
 *
 * The promotion-executor extension (race-safe hash lookup) and the
 * document-ingestion worker integration are NOT exercised here — the
 * former requires a live Postgres for the advisory lock + transaction
 * semantics, and the latter is glue. R5 (33/33), R5.5 (45/45), R6
 * (30/30), and the existing R2 (16/16) smokes cover the underlying
 * decision logic.
 */

import {
  decideCacheProfitability,
  estimateTokensForCache,
  EXPLICIT_CACHE_LARGE_SOURCE_REUSE_THRESHOLD,
  EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD,
  EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD,
  EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD,
} from '../extraction';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

function main() {
  console.log('R7 cache profitability + lifecycle smoke test\n');

  // ── Section A — decideCacheProfitability truth table ──────────────────

  // A1: medium source + high reuse → create
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD,
      expectedReuseCount: EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD,
    });
    assert(res.kind === 'create_explicit_cache', 'A1 medium + high reuse → create_explicit_cache');
    if (res.kind === 'create_explicit_cache') {
      assert(res.rule === 'medium_source_high_reuse', 'A1 reports medium_source_high_reuse rule');
    }
  }

  // A2: large source + modest reuse → create
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD,
      expectedReuseCount: EXPLICIT_CACHE_LARGE_SOURCE_REUSE_THRESHOLD,
    });
    assert(res.kind === 'create_explicit_cache', 'A2 large + modest reuse → create_explicit_cache');
    if (res.kind === 'create_explicit_cache') {
      assert(res.rule === 'large_source_modest_reuse', 'A2 reports large_source_modest_reuse rule');
    }
  }

  // A3: small source (always skip regardless of reuse)
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: 8_000,
      expectedReuseCount: 10,
    });
    assert(res.kind === 'skip_explicit_cache', 'A3 small source → skip');
    if (res.kind === 'skip_explicit_cache') {
      assert(res.reason === 'source_too_small', 'A3 reports source_too_small');
    }
  }

  // A4: medium source + only 2 reuses → skip (under medium threshold of 3)
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: 60_000,
      expectedReuseCount: 2,
    });
    assert(res.kind === 'skip_explicit_cache', 'A4 medium + 2 reuses → skip');
    if (res.kind === 'skip_explicit_cache') {
      assert(res.reason === 'reuse_too_low_for_medium', 'A4 reports reuse_too_low_for_medium');
    }
  }

  // A5: large source + only 1 reuse → skip (under large threshold of 2)
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: 150_000,
      expectedReuseCount: 1,
    });
    assert(res.kind === 'skip_explicit_cache', 'A5 large + 1 reuse → skip');
    if (res.kind === 'skip_explicit_cache') {
      assert(res.reason === 'reuse_too_low_for_large', 'A5 reports reuse_too_low_for_large');
    }
  }

  // A6: just-below-medium threshold → skip
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD - 1,
      expectedReuseCount: 100,
    });
    assert(res.kind === 'skip_explicit_cache', 'A6 below medium threshold → skip');
  }

  // A7: just-above-medium token + medium reuse → create
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD + 1,
      expectedReuseCount: EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD,
    });
    assert(res.kind === 'create_explicit_cache', 'A7 just-above-medium + medium reuse → create');
  }

  // A8: large rule takes precedence over medium when both apply
  {
    const res = decideCacheProfitability({
      sourceTokenEstimate: EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD,
      expectedReuseCount: 10, // satisfies both rules
    });
    assert(res.kind === 'create_explicit_cache', 'A8 both rules satisfied → create');
    if (res.kind === 'create_explicit_cache') {
      assert(res.rule === 'large_source_modest_reuse', 'A8 large rule wins precedence');
    }
  }

  // ── Section B — estimateTokensForCache ─────────────────────────────────

  // B1: ceil(length / 4)
  {
    assert(estimateTokensForCache('') === 0, 'B1 empty string → 0 tokens');
    assert(estimateTokensForCache('abcd') === 1, 'B1 4 chars → 1 token');
    assert(estimateTokensForCache('abcde') === 2, 'B1 5 chars → 2 tokens (ceil)');
    assert(estimateTokensForCache('a'.repeat(100_000)) === 25_000, 'B1 100k chars → 25k tokens');
  }

  // B2: deterministic
  {
    const a = estimateTokensForCache('hello world');
    const b = estimateTokensForCache('hello world');
    assert(a === b, 'B2 estimate is deterministic');
  }

  console.log('\nR7 smoke gate: PASS');
}

main();
