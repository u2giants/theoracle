/**
 * Unified model capability shape used by the admin model-pool + picker UIs.
 *
 * Filled from OpenRouter's /v1/models endpoint — capability flags, pricing,
 * and context windows all live there. No hand-typed capability tables.
 */

export type ModelProvider = 'anthropic' | 'openai' | 'google';

export type ModelCapabilitySource =
  | 'openrouter'              // openrouter.ai/api/v1/models — primary source
  | 'anthropic_api'           // optional supplemental source (reserved for follow-up)
  | 'classifier';             // Gemini Flash-Lite last-resort fallback (reserved)

export interface ModelCapability {
  /** "provider/modelId" — same id format used in settings.model_pool_*. */
  id: string;
  provider: ModelProvider;
  displayName: string;

  contextLength: number | null;       // max input tokens
  maxOutputTokens: number | null;     // max output tokens per request

  /** USD per 1,000,000 input tokens. */
  promptPer1mUsd: number | null;
  /** USD per 1,000,000 output tokens. */
  completionPer1mUsd: number | null;

  vision: boolean;
  pdf: boolean;
  thinking: boolean;
  structuredOutputs: boolean;
  toolCalling: boolean;
  promptCaching: boolean;

  /** ISO date string (YYYY-MM-DD), if the provider published it. */
  knowledgeCutoff: string | null;

  source: ModelCapabilitySource;
}
