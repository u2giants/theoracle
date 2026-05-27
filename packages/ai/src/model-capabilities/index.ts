// Public barrel for the model-capabilities module.
//
// Hand-typed capability tables are NOT allowed in this codebase. Every entry
// returned by discoverModelCatalog() must come from either a provider /models
// API response or a Gemini Flash-Lite classification of the official provider
// docs.  See sources/*.ts for the provider-specific implementations.

import type { ModelCapability } from './types';
import { fetchAnthropicCapabilities } from './sources/anthropic';
import { fetchOpenAICapabilities } from './sources/openai';
import { fetchVertexCapabilities } from './sources/vertex';
import {
  getCachedCatalog,
  setCachedCatalog,
  invalidateCachedCatalog,
} from './cache';
import { OracleAIClient } from '../client/oracle-ai-client';

export type { ModelCapability, ModelProvider, ModelCapabilitySource } from './types';
export { invalidateCachedCatalog } from './cache';

export interface DiscoverCatalogResult {
  catalog: ModelCapability[];
  providerErrors: string[];
  /** true when this call used the in-memory cache, false when it ran a fresh discovery. */
  cached: boolean;
}

/**
 * Run all three provider discoveries in parallel and return a unified catalog.
 *
 * - Anthropic: parses live /v1/models capability blocks directly (no AI call).
 * - OpenAI:    live /v1/models id list → Gemini Flash-Lite classifies caps.
 * - Vertex:    Gemini Flash-Lite enumerates + classifies the Gemini family.
 *
 * The classifier calls share a single OracleAIClient instance the caller
 * provides (admin route lazy-inits it the same way /api/chat does).
 *
 * When { force: true } is passed the in-memory cache is bypassed.
 */
export async function discoverModelCatalog(
  client: OracleAIClient,
  opts: { force?: boolean } = {},
): Promise<DiscoverCatalogResult> {
  if (!opts.force) {
    const cached = getCachedCatalog();
    if (cached) {
      return { catalog: cached.catalog, providerErrors: cached.providerErrors, cached: true };
    }
  }

  const [anthropic, openai, vertex] = await Promise.allSettled([
    fetchAnthropicCapabilities(),
    fetchOpenAICapabilities(client),
    fetchVertexCapabilities(client),
  ]);

  const catalog: ModelCapability[] = [];
  const providerErrors: string[] = [];

  if (anthropic.status === 'fulfilled') {
    catalog.push(...anthropic.value);
  } else {
    providerErrors.push(`Anthropic: ${anthropic.reason instanceof Error ? anthropic.reason.message : String(anthropic.reason)}`);
  }
  if (openai.status === 'fulfilled') {
    catalog.push(...openai.value);
  } else {
    providerErrors.push(`OpenAI: ${openai.reason instanceof Error ? openai.reason.message : String(openai.reason)}`);
  }
  if (vertex.status === 'fulfilled') {
    catalog.push(...vertex.value);
  } else {
    providerErrors.push(`Vertex: ${vertex.reason instanceof Error ? vertex.reason.message : String(vertex.reason)}`);
  }

  setCachedCatalog(catalog, providerErrors);
  return { catalog, providerErrors, cached: false };
}

void invalidateCachedCatalog; // satisfies isolated-module export check
