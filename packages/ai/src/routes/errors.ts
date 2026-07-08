import type { OracleModelRole } from './types';

export type ModelSlot =
  | OracleModelRole
  | 'vision'
  | 'workflow_read'
  | 'model_merge'
  | 'general'
  | 'translation'
  | 'transcript_summary'
  | 'macro';

export class NoConfiguredModelError extends Error {
  constructor(slot: ModelSlot, detail?: string) {
    super(
      `No usable model configured for ${slot}. Set an approved model in Admin -> Settings${
        detail ? ` (${detail})` : ''
      }.`,
    );
    this.name = 'NoConfiguredModelError';
  }
}

export class ModelCapabilityError extends Error {
  constructor(
    readonly slot: ModelSlot,
    readonly modelId: string,
    readonly missing: string[],
  ) {
    super(
      `Model ${modelId} is not valid for ${slot}; missing required capability${
        missing.length === 1 ? '' : 'ies'
      }: ${missing.join(', ')}.`,
    );
    this.name = 'ModelCapabilityError';
  }
}

export interface CandidateFailure {
  routeId: string;
  provider: string;
  modelId: string;
  error: string;
}

export class AllCandidatesFailedError extends Error {
  constructor(readonly slot: ModelSlot, readonly attempts: CandidateFailure[]) {
    super(
      `All model candidates failed for ${slot}: ${attempts
        .map((a) => `${a.routeId} (${a.provider}/${a.modelId}): ${a.error}`)
        .join(' | ')}`,
    );
    this.name = 'AllCandidatesFailedError';
  }
}
