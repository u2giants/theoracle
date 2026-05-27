/**
 * Unified model capability shape used by the admin model-pool + picker UIs.
 *
 * Hand-typed capability tables are explicitly NOT allowed in this module —
 * every field below must come from either a provider /models API response
 * (Anthropic) or a Gemini Flash-Lite classification of the official
 * provider docs (OpenAI, Vertex). See sources/*.ts.
 */

export type ModelProvider = 'anthropic' | 'openai' | 'google';

export type ModelCapabilitySource =
  | 'anthropic_api'         // Parsed from api.anthropic.com /v1/models capabilities object
  | 'openai_classified'     // OpenAI /v1/models id, capabilities inferred by Gemini Flash-Lite
  | 'vertex_classified';    // Vertex Gemini model id, capabilities inferred by Gemini Flash-Lite

export interface ModelCapability {
  /** "provider/modelId" — same id format used in settings.model_pool_*. */
  id: string;
  provider: ModelProvider;
  displayName: string;

  contextLength: number | null;       // max input tokens
  maxOutputTokens: number | null;     // max output tokens per request

  /** Accepts image inputs (image_url, base64 image, etc.) */
  vision: boolean;
  /** Accepts PDF/document file inputs directly. */
  pdf: boolean;
  /** Has a first-class reasoning / extended-thinking mode the API exposes. */
  thinking: boolean;
  /** Supports server-side structured output (json_schema response_format / native_json_schema). */
  structuredOutputs: boolean;
  /** Supports the tools / function-calling parameter. */
  toolCalling: boolean;
  /** Supports provider-native prompt caching. */
  promptCaching: boolean;

  source: ModelCapabilitySource;
  fetchedAt: string;                  // ISO timestamp of the discovery run
}
