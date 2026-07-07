/**
 * Unified model capability shape used by the admin model-pool + picker UIs.
 *
 * Model list: sourced from the 3 direct provider APIs (Anthropic, OpenAI,
 * Google Gemini). Pricing and capability flags are enriched from OpenRouter's
 * /v1/models endpoint and joined onto those models before DB persistence.
 */

export type ModelProvider = 'anthropic' | 'openai' | 'google' | 'deepseek' | 'qwen';

export type ModelCapabilitySource =
  | 'anthropic_api'   // model listed by Anthropic /v1/models
  | 'openai_api'      // model listed by OpenAI /v1/models
  | 'google_api'      // model listed by Google generativelanguage.googleapis.com/v1beta/models
  | 'deepseek_api'    // model listed by DeepSeek /models
  | 'qwen_api';       // model listed by DashScope OpenAI-compatible /models

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
  /** Provider/adapter can enforce a supplied JSON Schema, not just emit JSON text. */
  strictJsonSchema: boolean;
  /** Proven against Oracle's workflow/macro deep nested schemas. */
  deepSchemaAccepted: boolean;
  /** Current adapter request body is accepted by this model. */
  adapterParamsSafe: boolean;
  toolCalling: boolean;
  promptCaching: boolean;
  /** Model supports an output-length cap (max_completion_tokens or max_tokens). */
  outputCap: boolean;
  /** Notes about model-specific adapter/capability caveats. */
  adapterParamNotes: Record<string, unknown>;

  /** ISO date string (YYYY-MM-DD), if the provider published it. */
  knowledgeCutoff: string | null;

  source: ModelCapabilitySource;
}
