/**
 * R6 acceptance gate verification script.
 *
 * Run with: pnpm --filter @oracle/engines verify:r6
 *
 * Covers the new pure pieces R6 ships:
 *
 *   - decideCircuitBreaker: continue / allow_repair_pass / trip_breaker
 *     across the 3-strike threshold.
 *   - mapLegacyDomainsToTopDomains: the transitional KNOWLEDGE_DOMAINS →
 *     TOP_LEVEL_DOMAINS mapping used by the refactored worker, kept in
 *     sync with migrations/sql/42_claim_top_domains_backfill.sql.
 *
 * The promotion-executor + worker integration are NOT exercised here —
 * they require a live Postgres for the advisory lock + transaction
 * semantics. R5 (33/33) and R5.5 (45/45) already cover the pure decision
 * logic the executor is plumbing for.
 */

import {
  decideCircuitBreaker,
  mapLegacyDomainToTopDomain,
  mapLegacyDomainsToTopDomains,
} from '../extraction';

function assert(cond: unknown, msg: string): asserts cond {
  if (!cond) {
    console.error(`✗ ${msg}`);
    process.exit(1);
  }
  console.log(`✓ ${msg}`);
}

function main() {
  console.log('R6 circuit breaker + domain mapping smoke test\n');

  // ── Section A — circuit breaker ────────────────────────────────────────

  // A1: no failures → continue
  {
    const res = decideCircuitBreaker({
      validationAttemptCount: 1,
      consecutiveQuoteFailureCount: 0,
    });
    assert(res.kind === 'continue', 'A1 no failures → continue');
  }

  // A2: one failure under the threshold → continue
  {
    const res = decideCircuitBreaker({
      validationAttemptCount: 2,
      consecutiveQuoteFailureCount: 1,
    });
    assert(res.kind === 'continue', 'A2 one failure → continue');
  }

  // A3: two failures under threshold → continue (no schema-shape signal)
  {
    const res = decideCircuitBreaker({
      validationAttemptCount: 3,
      consecutiveQuoteFailureCount: 2,
    });
    assert(res.kind === 'continue', 'A3 two failures, no repair signal → continue');
  }

  // A4: two failures + schema-shape signal → allow_repair_pass (one shot)
  {
    const res = decideCircuitBreaker({
      validationAttemptCount: 3,
      consecutiveQuoteFailureCount: 2,
      lastFailureLooksLikeSchema: true,
    });
    assert(res.kind === 'allow_repair_pass', 'A4 N-1 + schema signal → allow_repair_pass');
  }

  // A5: three failures → trip_breaker
  {
    const res = decideCircuitBreaker({
      validationAttemptCount: 4,
      consecutiveQuoteFailureCount: 3,
    });
    assert(res.kind === 'trip_breaker', 'A5 three failures → trip_breaker');
    if (res.kind === 'trip_breaker') {
      assert(
        res.validationResultToWrite.checkName === 'validation_loop_circuit_breaker',
        'A5 records the validation_loop_circuit_breaker check',
      );
      assert(
        res.validationResultToWrite.status === 'circuit_breaker',
        'A5 status is circuit_breaker',
      );
    }
  }

  // A6: beyond the threshold still trips (no recovery)
  {
    const res = decideCircuitBreaker({
      validationAttemptCount: 7,
      consecutiveQuoteFailureCount: 5,
    });
    assert(res.kind === 'trip_breaker', 'A6 5 consecutive failures → trip_breaker');
  }

  // A7: custom failureLimit honored
  {
    const tighter = decideCircuitBreaker({
      validationAttemptCount: 2,
      consecutiveQuoteFailureCount: 2,
      failureLimit: 2,
    });
    assert(tighter.kind === 'trip_breaker', 'A7 custom limit=2 trips at 2 failures');
  }

  // A8: schema-shape signal does NOT cause a repair pass on the very first failure
  {
    const res = decideCircuitBreaker({
      validationAttemptCount: 1,
      consecutiveQuoteFailureCount: 1,
      lastFailureLooksLikeSchema: true,
    });
    assert(
      res.kind === 'continue',
      'A8 1 failure + schema signal still continues (not at N-1 yet)',
    );
  }

  // ── Section B — legacy domain mapping ──────────────────────────────────

  // B1: every legacy enum value maps to an active top-domain
  {
    const cases: Array<[string, string]> = [
      ['licensing', 'licensing_approvals'],
      ['approvals', 'licensing_approvals'],
      ['sourcing', 'supply_chain'],
      ['factory_communication', 'supply_chain'],
      ['logistics', 'logistics_shipping'],
      ['shipping_documents', 'logistics_shipping'],
      ['coldlion', 'it_systems'],
      ['design', 'creative_design'],
      ['artwork_files', 'creative_design'],
      ['sampling', 'product_development'],
      ['production', 'production_lifecycle'],
      ['quality_control', 'production_lifecycle'],
      ['customers', 'customer_ops'],
      ['sales', 'customer_ops'],
      ['retail_compliance', 'customer_ops'],
      ['costing', 'finance_pricing'],
      ['general', 'customer_ops'],
    ];
    for (const [legacy, expected] of cases) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const got = mapLegacyDomainToTopDomain(legacy as any);
      assert(got === expected, `B1 legacy "${legacy}" → "${expected}"`);
    }
  }

  // B2: array mapping preserves order + deduplicates
  {
    const got = mapLegacyDomainsToTopDomains([
      'design',
      'artwork_files', // collides with design → creative_design
      'sales',
      'customers', // collides with sales → customer_ops
      'production',
    ] as never);
    assert(got.length === 3, 'B2 deduplicates collisions');
    assert(got[0] === 'creative_design', 'B2 keeps insertion order: creative_design first');
    assert(got[1] === 'customer_ops', 'B2 customer_ops second');
    assert(got[2] === 'production_lifecycle', 'B2 production_lifecycle third');
  }

  // B3: empty input → empty output
  {
    const got = mapLegacyDomainsToTopDomains([]);
    assert(got.length === 0, 'B3 empty input → empty output');
  }

  // B4: residual fallback for unknown values (defensive — shouldn't happen
  // because the type is closed, but the mapping handles it gracefully)
  {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const got = mapLegacyDomainToTopDomain('not_a_real_domain' as any);
    assert(got === 'customer_ops', 'B4 unknown legacy value → customer_ops residual');
  }

  console.log('\nR6 smoke gate: PASS');
}

main();
