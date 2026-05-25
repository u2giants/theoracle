/**
 * StructuredOutputValidator — runs a Zod schema check over a model's
 * structured output. Returns a discriminated result so the caller can
 * decide whether to escalate to a repair route.
 *
 * This validator is deterministic. It must not call an LLM.
 */

import type { ZodType, ZodError } from 'zod';

export type ValidationResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: ZodError; receivedJson: unknown };

export class StructuredOutputValidator {
  validate<T>(schema: ZodType<T>, candidate: unknown): ValidationResult<T> {
    const parsed = schema.safeParse(candidate);
    if (parsed.success) return { ok: true, value: parsed.data };
    return { ok: false, error: parsed.error, receivedJson: candidate };
  }
}

let cached: StructuredOutputValidator | null = null;
export function getStructuredOutputValidator(): StructuredOutputValidator {
  if (!cached) cached = new StructuredOutputValidator();
  return cached;
}
