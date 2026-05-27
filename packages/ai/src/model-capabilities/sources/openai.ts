// OpenAI model list source.
// Calls OpenAI's /v1/models endpoint and filters down to chat-capable models.
// The full model list includes embeddings, TTS, Whisper, DALL-E, fine-tuned
// variants, etc. — we only want the GPT / o-series chat models.

import OpenAI from 'openai';
import type { RawProviderModel } from './types';

const CHAT_ID_PREFIXES = ['gpt-4', 'gpt-3.5', 'o1', 'o3', 'o4', 'chatgpt-'];

function isChatModel(id: string): boolean {
  return CHAT_ID_PREFIXES.some((p) => id.startsWith(p));
}

export async function fetchOpenAIModels(): Promise<RawProviderModel[]> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY not set');

  const client = new OpenAI({ apiKey });
  const page = await client.models.list();

  return page.data
    .filter((m) => isChatModel(m.id))
    .map((m) => ({
      id: `openai/${m.id}`,
      provider: 'openai' as const,
      displayName: m.id,   // OpenAI's model list doesn't include display names
      contextLength: null,
      maxOutputTokens: null,
      source: 'openai_api' as const,
    }));
}
