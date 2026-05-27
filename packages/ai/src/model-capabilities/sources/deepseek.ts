// DeepSeek model list source.
// Calls DeepSeek's /models endpoint (OpenAI-compatible) and tags each row
// as a deepseek-provider model. Capabilities and pricing come separately
// from OpenRouter enrichment (matched by canonical-slug fallback in index.ts).

import OpenAI from 'openai';
import type { RawProviderModel } from './types';

const DEEPSEEK_BASE_URL = 'https://api.deepseek.com';

export async function fetchDeepSeekModels(): Promise<RawProviderModel[]> {
  const apiKey = process.env.DEEPSEEK_API_KEY;
  if (!apiKey) throw new Error('DEEPSEEK_API_KEY not set');

  const client = new OpenAI({ apiKey, baseURL: DEEPSEEK_BASE_URL });
  const page = await client.models.list();

  return page.data.map((m) => ({
    id: `deepseek/${m.id}`,
    provider: 'deepseek' as const,
    displayName: m.id,                  // DeepSeek doesn't return a display name
    contextLength: null,                // not exposed by /models — OpenRouter fills this
    maxOutputTokens: null,
    source: 'deepseek_api' as const,
  }));
}
