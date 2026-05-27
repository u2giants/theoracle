// Internal types shared across the model-capability source files.
// Not exported from the public barrel.

import type { ModelCapabilitySource } from '../types';

/** A model as returned by a direct provider API, before OpenRouter enrichment. */
export interface RawProviderModel {
  id: string;                        // "provider/modelId" format
  provider: 'anthropic' | 'openai' | 'google';
  displayName: string;
  contextLength: number | null;
  maxOutputTokens: number | null;
  source: ModelCapabilitySource;
}
