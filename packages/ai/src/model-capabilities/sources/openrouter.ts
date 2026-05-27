// OpenRouter enrichment source — pricing and capability flags only.
//
// The authoritative model list comes from the 3 direct provider APIs
// (Anthropic, OpenAI, Google Gemini). This module calls OpenRouter's
// /v1/models endpoint and returns a Map keyed by "provider/modelId" so
// the caller can join on our already-fetched model list.
//
// OpenRouter exposes capability flags (vision, thinking, tool-calling, etc.),
// pricing per token, context windows, and knowledge cutoff dates for every
// provider. We use it purely as an enrichment layer — no model is added to
// the catalog solely because it appears in OpenRouter.
//
// Authentication: optional. The /v1/models endpoint is public; the API key
// only matters if OpenRouter rate-limits unauthenticated requests.

type ORModel = {
  id: string;
  canonical_slug?: string;
  name?: string;
  context_length?: number;
  pricing?: {
    prompt?: string;
    completion?: string;
    image?: string;
    audio?: string;
    web_search?: string;
    internal_reasoning?: string;
    input_cache_read?: string;
    input_cache_write?: string;
  };
  top_provider?: {
    context_length?: number;
    max_completion_tokens?: number;
    is_moderated?: boolean;
  };
  architecture?: {
    modality?: string;
    input_modalities?: string[];
    output_modalities?: string[];
    tokenizer?: string;
  };
  supported_parameters?: string[];
  knowledge_cutoff?: string | null;
};

export interface OpenRouterEnrichment {
  contextLength: number | null;
  maxOutputTokens: number | null;
  promptPer1mUsd: number | null;
  completionPer1mUsd: number | null;
  vision: boolean;
  pdf: boolean;
  thinking: boolean;
  structuredOutputs: boolean;
  toolCalling: boolean;
  promptCaching: boolean;
  outputCap: boolean;            // supports max_completion_tokens OR max_tokens
  knowledgeCutoff: string | null;
}

function priceToPer1m(perToken?: string): number | null {
  if (perToken == null) return null;
  const n = parseFloat(perToken);
  return Number.isFinite(n) ? n * 1_000_000 : null;
}

function toEnrichment(m: ORModel): OpenRouterEnrichment {
  const inputs = m.architecture?.input_modalities ?? [];
  const params = m.supported_parameters ?? [];

  return {
    contextLength: m.top_provider?.context_length ?? m.context_length ?? null,
    maxOutputTokens: m.top_provider?.max_completion_tokens ?? null,
    promptPer1mUsd: priceToPer1m(m.pricing?.prompt),
    completionPer1mUsd: priceToPer1m(m.pricing?.completion),
    vision: inputs.includes('image') || inputs.includes('video'),
    pdf: inputs.includes('file'),
    thinking:
      params.includes('reasoning') ||
      params.includes('include_reasoning') ||
      params.includes('thinking'),
    structuredOutputs:
      params.includes('structured_outputs') || params.includes('response_format'),
    toolCalling: params.includes('tools') || params.includes('tool_choice'),
    promptCaching:
      m.pricing?.input_cache_read != null || m.pricing?.input_cache_write != null,
    outputCap: params.includes('max_completion_tokens') || params.includes('max_tokens'),
    knowledgeCutoff: m.knowledge_cutoff ?? null,
  };
}

/**
 * Fetch OpenRouter's model catalog and return a Map keyed by the OpenRouter
 * model id ("provider/modelId"). Use this to enrich models fetched from
 * direct provider APIs with pricing and capability flags.
 */
export async function fetchOpenRouterEnrichment(): Promise<Map<string, OpenRouterEnrichment>> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const key = process.env.OPENROUTER_API_KEY;
  if (key) headers.Authorization = `Bearer ${key}`;

  const res = await fetch('https://openrouter.ai/api/v1/models', {
    headers,
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) {
    throw new Error(`OpenRouter /v1/models: ${res.status} ${await res.text()}`);
  }

  const body = (await res.json()) as { data?: ORModel[] };
  const map = new Map<string, OpenRouterEnrichment>();
  for (const m of body.data ?? []) {
    const enrichment = toEnrichment(m);
    map.set(m.id, enrichment);
    // Index by canonical_slug too — versioned model IDs (e.g. "anthropic/claude-opus-4-20250514")
    // can fall back to the canonical form ("anthropic/claude-opus-4") stored here.
    if (m.canonical_slug && m.canonical_slug !== m.id) {
      map.set(m.canonical_slug, enrichment);
    }
  }
  return map;
}
