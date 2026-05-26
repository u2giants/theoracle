/**
 * R9 — Synthesis pipeline barrel.
 *
 * Workers import from here. The pure validator is the only piece R9 ships
 * to `@oracle/engines`; the synthesis worker itself remains in
 * `apps/workers/src/trigger/brain-synthesis.ts` because it's not reusable
 * across other workers (unlike the extraction promotion executor, which
 * R6 + R7 both call).
 */

export {
  validateSynthesisDiff,
  findUnsupportedNamedEntities,
} from './diff-validator';

export type {
  SynthesisOutput,
  SynthesisOutputParagraph,
  SynthesisMaterialChange,
  SynthesisNewGap,
  SynthesisNewContradiction,
  SynthesisValidationInput,
  SynthesisValidationResult,
  SynthesisValidationFailure,
  SynthesisFailureKind,
} from './types';
