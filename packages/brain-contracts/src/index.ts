import { z } from 'zod';

const wireUuid = z.string().regex(
  /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/,
).transform((value) => value.toLowerCase());

const sourceSpan = z.strictObject({
  source_id: wireUuid,
  source_revision: z.number().int().positive(),
  start: z.number().int().nonnegative(),
  end: z.number().int().positive(),
  quote: z.string().min(1),
}).refine((span) => span.end > span.start);

const candidateAssertion = z.strictObject({
  assertion_id: wireUuid,
  subject: z.string().min(1),
  predicate: z.string().min(1),
  object: z.string().min(1),
  span: sourceSpan,
  confidence: z.number().min(0).max(1),
});

export const candidateBundle = z.strictObject({
  contract_version: z.literal(1),
  workspace_id: wireUuid,
  run_id: wireUuid,
  source_id: wireUuid,
  source_revision: z.number().int().positive(),
  assertions: z.array(candidateAssertion),
}).refine((bundle) => bundle.assertions.every((assertion) =>
  assertion.span.source_id === bundle.source_id &&
  assertion.span.source_revision === bundle.source_revision));

export const projectionReceipt = z.strictObject({
  contract_version: z.literal(1),
  workspace_id: wireUuid,
  assertion_id: wireUuid,
  revision: z.number().int().positive(),
  operation: z.enum(['project', 'withdraw']),
  projector_id: z.string().min(1),
  // Same wire rule as Python WIRE_DATETIME: seconds required, colonized offset.
  applied_at: z.iso.datetime({ offset: true })
    .regex(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/),
  signature: z.string().regex(/^[0-9a-f]{64}$/),
});

export const runRequest = z.strictObject({
  contract_version: z.literal(1),
  run_id: wireUuid,
  workspace_id: wireUuid,
  actor_id: wireUuid,
  source_id: wireUuid,
  source_revision: z.number().int().positive(),
  mode: z.enum(['synthetic', 'approved_real']),
});

export type CandidateBundle = z.infer<typeof candidateBundle>;
export type ProjectionReceipt = z.infer<typeof projectionReceipt>;
export type RunRequest = z.infer<typeof runRequest>;
