// OpenAI model list source.
// Calls OpenAI's /v1/models endpoint and filters out clearly non-chat models.
// The full model list includes embeddings, TTS, audio, image generation,
// realtime, transcription, moderation, video, etc. Blocklists by prefix/
// substring; post-enrichment filters in refreshModelCatalog handle the rest.

import OpenAI from 'openai';
import type { RawProviderModel } from './types';

// Block by id prefix.
const BLOCKED_PREFIXES = [
  'text-embedding', 'text-moderation', 'text-search', 'text-similarity',
  'whisper', 'tts-', 'dall-e',
  'babbage', 'davinci', 'ada', 'curie',
  'gpt-audio', 'gpt-image', 'gpt-realtime',
  'chatgpt-image',
  'omni-moderation',
  'sora',
];

// Block by substring anywhere in the id (catches `-tts`, `-transcribe`, etc.).
const BLOCKED_SUBSTRINGS = ['-tts', '-transcribe', '-diarize', '-translate', '-search-api'];

function isBlockedModel(id: string): boolean {
  if (BLOCKED_PREFIXES.some((p) => id.startsWith(p))) return true;
  if (BLOCKED_SUBSTRINGS.some((s) => id.includes(s))) return true;
  return false;
}

export async function fetchOpenAIModels(): Promise<RawProviderModel[]> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY not set');

  const client = new OpenAI({ apiKey });
  const page = await client.models.list();

  return page.data
    .filter((m) => !isBlockedModel(m.id))
    .map((m) => ({
      id: `openai/${m.id}`,
      provider: 'openai' as const,
      displayName: m.id,   // OpenAI's model list doesn't include display names
      contextLength: null,
      maxOutputTokens: null,
      source: 'openai_api' as const,
    }));
}
