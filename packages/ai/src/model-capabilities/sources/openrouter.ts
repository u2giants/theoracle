// OpenRouter source — single source of truth for the catalog.
//
// openrouter.ai/api/v1/models returns the complete catalog for every
// provider including capability flags, pricing per token, context length,
// max output tokens, modality info, and supported parameter list. We use
// it as the primary catalog source for all 3 providers (Anthropic, OpenAI,
// Google/Vertex) — no hand-typed tables, no AI classification.
//
// Authentication: optional. The /v1/models endpoint is public; the API key
// is only needed for the catalog if OpenRouter rate-limits unauthenticated
// requests. We send it when present.

import type { ModelCapability } from '../types';

type ORModel = {
  id: string;                           // "anthropic/claude-sonnet-4-6"
  canonical_slug?: string;
  name?: string;
  context_length?: number;
  pricing?: {
    prompt?: string;                    // per-token, USD, stringified
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
    modality?: string;                  // e.g. "text+image+file+audio+video->text"
    input_modalities?: string[];        // ["text", "image", "file", ...]
    output_modalities?: string[];
    tokenizer?: string;
  };
  supported_parameters?: string[];      // ["reasoning", "tools", "structured_outputs", ...]
  knowledge_cutoff?: string | null;     // ISO date or null
};

const PROVIDER_PREFIX_MAP: Record<string, 'anthropic' | 'openai' | 'google'> = {
  anthropic: 'anthropic',
  openai: 'openai',
  google: 'google',
};

function priceToPer1m(perToken?: string): number | null {
  if (perToken == null) return null;
  const n = parseFloat(perToken);
  if (!Number.isFinite(n)) return null;
  return n * 1_000_000;
}

function mapOne(m: ORModel): ModelCapability | null {
  const prefix = m.id.split('/')[0];
  if (!prefix) return null;
  const provider = PROVIDER_PREFIX_MAP[prefix];
  if (!provider) return null; // skip providers we don't run (meta-llama, mistralai, etc.)

  const inputs = m.architecture?.input_modalities ?? [];
  const supportedParams = m.supported_parameters ?? [];

  const vision = inputs.includes('image') || inputs.includes('video');
  const pdf = inputs.includes('file');
  // OpenRouter exposes a reasoning parameter for models that take a
  // reasoning_effort / reasoning_tokens config — that's the same thing as
  // "thinking mode".
  const thinking = supportedParams.includes('reasoning')
    || supportedParams.includes('include_reasoning')
    || supportedParams.includes('thinking');
  const structuredOutputs = supportedParams.includes('structured_outputs')
    || supportedParams.includes('response_format');
  const toolCalling = supportedParams.includes('tools')
    || supportedParams.includes('tool_choice');
  const promptCaching = m.pricing?.input_cache_read != null
    || m.pricing?.input_cache_write != null;

  return {
    id: m.id,
    provider,
    displayName: (m.name ?? m.id).replace(/^[^:]+:\s*/, ''),  // "Google: Gemini..." → "Gemini..."
    contextLength: m.top_provider?.context_length ?? m.context_length ?? null,
    maxOutputTokens: m.top_provider?.max_completion_tokens ?? null,
    promptPer1mUsd: priceToPer1m(m.pricing?.prompt),
    completionPer1mUsd: priceToPer1m(m.pricing?.completion),
    vision,
    pdf,
    thinking,
    structuredOutputs,
    toolCalling,
    promptCaching,
    knowledgeCutoff: m.knowledge_cutoff ?? null,
    source: 'openrouter',
  };
}

export async function fetchOpenRouterCatalog(): Promise<ModelCapability[]> {
  const headers: Record<string, string> = { Accept: 'application/json' };
  const key = process.env.OPENROUTER_API_KEY;
  if (key) headers.Authorization = `Bearer ${key}`;

  const res = await fetch('https://openrouter.ai/api/v1/models', {
    headers,
    signal: AbortSignal.timeout(10_000),
  });
  if (!res.ok) throw new Error(`OpenRouter /v1/models: ${res.status} ${await res.text()}`);
  const body = (await res.json()) as { data?: ORModel[] };
  return (body.data ?? []).map(mapOne).filter((c): c is ModelCapability => c !== null);
}
