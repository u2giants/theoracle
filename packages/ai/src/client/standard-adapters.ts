/**
 * buildStandardAdapters() — single source of truth for the production adapter
 * map. Used by /api/chat and every Trigger.dev worker so that adding a new
 * provider only touches this file (plus the route catalog).
 *
 * Tolerant of missing env vars: if any adapter's constructor throws (e.g.
 * DEEPSEEK_API_KEY isn't set yet), that adapter is omitted instead of taking
 * down the whole map. Dispatch to an unregistered adapter still fails fast
 * inside ModelRouter — this only prevents one missing key from breaking
 * every endpoint at boot.
 */

import { AnthropicAdapter } from '../providers/anthropic-adapter';
import { VertexGeminiAdapter } from '../providers/vertex-gemini-adapter';
import { GoogleGeminiAdapter } from '../providers/google-gemini-adapter';
import { OpenAIAdapter } from '../providers/openai-adapter';
import { DeepSeekAdapter } from '../providers/deepseek-adapter';
import { QwenAdapter } from '../providers/qwen-adapter';
import type { ProviderAdapterMap } from '../routing/model-router';
import type { OracleProvider } from '../routes';
import type { OracleProviderAdapter } from '../providers/types';

const IS_PROD = process.env.NODE_ENV === 'production';

function tryAdd(
  map: ProviderAdapterMap,
  key: OracleProvider,
  factory: () => OracleProviderAdapter,
): void {
  try {
    map[key] = factory();
  } catch (err) {
    if (!IS_PROD) {
      // eslint-disable-next-line no-console
      console.warn(
        `[buildStandardAdapters] skipped ${key}: ${err instanceof Error ? err.message : String(err)}`,
      );
    }
  }
}

export function buildStandardAdapters(): ProviderAdapterMap {
  const map: ProviderAdapterMap = {};
  tryAdd(map, 'anthropic', () => new AnthropicAdapter());
  tryAdd(map, 'vertex',    () => new VertexGeminiAdapter());
  tryAdd(map, 'google',    () => new GoogleGeminiAdapter());
  tryAdd(map, 'openai',    () => new OpenAIAdapter());
  tryAdd(map, 'deepseek',  () => new DeepSeekAdapter());
  tryAdd(map, 'qwen',      () => new QwenAdapter());
  return map;
}
