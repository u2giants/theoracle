/**
 * UsageNormalizer — maps provider-native usage objects into OracleUsage.
 *
 * Each provider exposes cache + reasoning tokens under a different field
 * name. We normalize once at the adapter boundary so UsageLogger always
 * sees the same shape.
 *
 * The raw provider object is preserved in OracleUsage.rawUsageJson for
 * audit and debugging.
 */

import type { OracleProvider } from '../routes';
import type { OracleUsage } from '../client/types';

export interface AnthropicUsageRaw {
  input_tokens?: number;
  output_tokens?: number;
  cache_creation_input_tokens?: number;
  cache_read_input_tokens?: number;
}

export interface VertexUsageRaw {
  promptTokenCount?: number;
  candidatesTokenCount?: number;
  cachedContentTokenCount?: number;
  thoughtsTokenCount?: number;
  totalTokenCount?: number;
}

export interface OpenAIUsageRaw {
  prompt_tokens?: number;
  completion_tokens?: number;
  prompt_tokens_details?: { cached_tokens?: number };
  completion_tokens_details?: { reasoning_tokens?: number };
  total_tokens?: number;
}

export interface NormalizeArgs {
  provider: OracleProvider;
  raw: unknown;
  latencyMs: number;
  providerRequestId?: string;
}

export function normalizeUsage(args: NormalizeArgs): OracleUsage {
  const { provider, raw, latencyMs, providerRequestId } = args;
  switch (provider) {
    case 'anthropic':
      return normalizeAnthropic(raw as AnthropicUsageRaw, latencyMs, providerRequestId);
    case 'vertex':
      return normalizeVertex(raw as VertexUsageRaw, latencyMs, providerRequestId);
    case 'openai':
      return normalizeOpenAI(raw as OpenAIUsageRaw, latencyMs, providerRequestId);
  }
}

function normalizeAnthropic(
  raw: AnthropicUsageRaw,
  latencyMs: number,
  providerRequestId?: string,
): OracleUsage {
  return {
    inputTokens: raw.input_tokens,
    outputTokens: raw.output_tokens,
    cachedInputTokens: raw.cache_read_input_tokens,
    cacheWriteTokens: raw.cache_creation_input_tokens,
    latencyMs,
    providerRequestId,
    rawUsageJson: raw,
  };
}

function normalizeVertex(
  raw: VertexUsageRaw,
  latencyMs: number,
  providerRequestId?: string,
): OracleUsage {
  return {
    inputTokens: raw.promptTokenCount,
    outputTokens: raw.candidatesTokenCount,
    cachedInputTokens: raw.cachedContentTokenCount,
    reasoningTokens: raw.thoughtsTokenCount,
    latencyMs,
    providerRequestId,
    rawUsageJson: raw,
  };
}

function normalizeOpenAI(
  raw: OpenAIUsageRaw,
  latencyMs: number,
  providerRequestId?: string,
): OracleUsage {
  return {
    inputTokens: raw.prompt_tokens,
    outputTokens: raw.completion_tokens,
    cachedInputTokens: raw.prompt_tokens_details?.cached_tokens,
    reasoningTokens: raw.completion_tokens_details?.reasoning_tokens,
    latencyMs,
    providerRequestId,
    rawUsageJson: raw,
  };
}
