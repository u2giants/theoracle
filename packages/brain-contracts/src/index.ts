import { z } from 'zod';

const sourceSpan = z.strictObject({
  source_id: z.uuid(),
  source_revision: z.number().int().positive(),
  start: z.number().int().nonnegative(),
  end: z.number().int().positive(),
  quote: z.string().min(1),
}).refine((span) => span.end > span.start);

const candidateAssertion = z.strictObject({
  assertion_id: z.uuid(),
  subject: z.string().min(1),
  predicate: z.string().min(1),
  object: z.string().min(1),
  span: sourceSpan,
  confidence: z.number().min(0).max(1),
});

export const candidateBundle = z.strictObject({
  contract_version: z.literal(1),
  workspace_id: z.uuid(),
  run_id: z.uuid(),
  source_id: z.uuid(),
  source_revision: z.number().int().positive(),
  assertions: z.array(candidateAssertion),
}).refine((bundle) => bundle.assertions.every((assertion) =>
  assertion.span.source_id === bundle.source_id &&
  assertion.span.source_revision === bundle.source_revision));

export const projectionReceipt = z.strictObject({
  contract_version: z.literal(1),
  workspace_id: z.uuid(),
  assertion_id: z.uuid(),
  revision: z.number().int().positive(),
  operation: z.enum(['project', 'withdraw']),
  projector_id: z.string().min(1),
  applied_at: z.iso.datetime({ offset: true }),
  signature: z.string().regex(/^[0-9a-f]{64}$/),
});

export const runRequest = z.strictObject({
  contract_version: z.literal(1),
  run_id: z.uuid(),
  workspace_id: z.uuid(),
  actor_id: z.uuid(),
  source_id: z.uuid(),
  source_revision: z.number().int().positive(),
  mode: z.enum(['synthetic', 'approved_real']),
});

export type CandidateBundle = z.infer<typeof candidateBundle>;
export type ProjectionReceipt = z.infer<typeof projectionReceipt>;
export type RunRequest = z.infer<typeof runRequest>;
