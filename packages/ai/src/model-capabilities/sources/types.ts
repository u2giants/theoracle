// Internal types shared across the model-capability source files.
// Not exported from the public barrel.

import type { ModelCapabilitySource } from '../types';

import type { ModelProvider } from '../types';

/** A model as returned by a direct provider API, before OpenRouter enrichment. */
export interface RawProviderModel {
  id: string;                        // "provider/modelId" format
  provider: ModelProvider;
  displayName: string;
  contextLength: number | null;
  maxOutputTokens: number | null;
  source: ModelCapabilitySource;
}
