/**
 * R6 — Validation-loop circuit breaker.
 *
 * Pure decision function. Workers feed in the batch's running counters
 * after each attempt and get back a decision: continue, allow one
 * structured-repair pass, or trip the breaker.
 *
 * Spec: docs/oracle/03-candidate-before-claim-validation.md
 * "Circuit breakers and infinite-loop prevention". A batch whose
 * deterministic quote validation fails 3 times in a row gets:
 *   - status: failed_validation_loop
 *   - extraction_validation_results row with
 *       check_name='validation_loop_circuit_breaker',
 *       status='circuit_breaker'
 *   - the worker moves on to the next batch.
 *
 * Allowed exception: ONE structured-repair attempt before the breaker
 * trips, if the failure is plausibly schema-shape rather than quote
 * hallucination.
 */

import type { ValidationCheckName, ValidationCheckStatus } from '@oracle/shared';

export const DEFAULT_QUOTE_FAILURE_LIMIT = 3;

export interface CircuitBreakerInput {
  /** Total deterministic-validation attempts made so far on this batch. */
  validationAttemptCount: number;
  /** Consecutive QUOTE validation failures specifically. */
  consecutiveQuoteFailureCount: number;
  /**
   * True if the most recent failure looked like a schema-shape issue (e.g.
   * Zod validation failed) rather than a quote hallucination. Workers pass
   * this so we can allow the one-shot repair branch.
   */
  lastFailureLooksLikeSchema?: boolean;
  /**
   * Configurable threshold. Defaults to 3. Override only in tests or with
   * a deliberate spec change.
   */
  failureLimit?: number;
}

export type CircuitBreakerDecision =
  | { kind: 'continue'; detail: string }
  | { kind: 'allow_repair_pass'; detail: string }
  | {
      kind: 'trip_breaker';
      detail: string;
      validationResultToWrite: {
        checkName: ValidationCheckName;
        status: ValidationCheckStatus;
        detail: string;
      };
    };

/**
 * Decide what to do based on the batch counters.
 *
 *  - Under the limit ⇒ continue.
 *  - At limit-1 with a schema-shape failure ⇒ allow_repair_pass (one shot).
 *  - At limit ⇒ trip the breaker.
 */
export function decideCircuitBreaker(input: CircuitBreakerInput): CircuitBreakerDecision {
  const limit = input.failureLimit ?? DEFAULT_QUOTE_FAILURE_LIMIT;

  if (input.consecutiveQuoteFailureCount >= limit) {
    return {
      kind: 'trip_breaker',
      detail:
        `Batch has hit ${input.consecutiveQuoteFailureCount} consecutive quote-validation failures` +
        ` (limit=${limit}). Mark the batch failed_validation_loop and move on.`,
      validationResultToWrite: {
        checkName: 'validation_loop_circuit_breaker',
        status: 'circuit_breaker',
        detail: `Tripped after ${input.consecutiveQuoteFailureCount} consecutive failures.`,
      },
    };
  }

  if (
    input.consecutiveQuoteFailureCount === limit - 1 &&
    input.lastFailureLooksLikeSchema === true
  ) {
    return {
      kind: 'allow_repair_pass',
      detail:
        'One repair attempt allowed because the last failure looked like a schema-shape issue.' +
        ' If it fails too, the next call will trip the breaker.',
    };
  }

  return {
    kind: 'continue',
    detail: `Under threshold (${input.consecutiveQuoteFailureCount} / ${limit}).`,
  };
}
