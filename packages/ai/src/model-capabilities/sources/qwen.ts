// Alibaba Qwen model list source.
// Calls Alibaba DashScope's OpenAI-compatible /models endpoint and tags each
// row as a qwen-provider model. Pricing/caps come from OpenRouter enrichment
// (OpenRouter indexes Qwen models under the "qwen/" slug, which matches).
//
// Auth: DASHSCOPE_API_KEY from DashScope International console.
// Base URL: https://dashscope-intl.aliyuncs.com/compatible-mode/v1

import OpenAI from 'openai';
import type { RawProviderModel } from './types';

const DASHSCOPE_BASE_URL = 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1';

// DashScope returns the full catalog including non-chat models (text-embedding,
// multimodal embedding, etc.). Filter to qwen* chat/VL models.
const QWEN_CHAT_PREFIXES = ['qwen', 'qwq'];

function isQwenChatModel(id: string): boolean {
  const lower = id.toLowerCase();
  return (
    QWEN_CHAT_PREFIXES.some((p) => lower.startsWith(p)) &&
    !lower.includes('embedding') &&
    !lower.includes('rerank') &&
    !lower.includes('-tts') &&
    !lower.includes('-asr')
  );
}

export async function fetchQwenModels(): Promise<RawProviderModel[]> {
  const apiKey = process.env.DASHSCOPE_API_KEY;
  if (!apiKey) throw new Error('DASHSCOPE_API_KEY not set');

  const client = new OpenAI({ apiKey, baseURL: DASHSCOPE_BASE_URL });
  const page = await client.models.list();

  return page.data
    .filter((m) => isQwenChatModel(m.id))
    .map((m) => ({
      id: `qwen/${m.id}`,
      provider: 'qwen' as const,
      displayName: m.id,
      contextLength: null,
      maxOutputTokens: null,
      source: 'qwen_api' as const,
    }));
}
