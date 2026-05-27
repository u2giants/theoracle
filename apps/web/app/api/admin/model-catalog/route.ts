// GET /api/admin/model-catalog
//
// Returns all available models from the three direct Oracle providers:
//   • Anthropic — live /v1/models list
//   • OpenAI    — live /v1/models list (filtered to chat/completion models)
//   • Google    — curated static list of Vertex-hosted Gemini models
//
// IDs are returned in "provider/modelId" format so they are compatible with
// resolveModelRoute() in @oracle/ai.  OpenRouter is NOT used.
//
// Requires admin.
// Response: { models: ModelCatalogEntry[], providerErrors: string[] }

import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';
import { MODEL_META } from '@/lib/model-metadata';

export const dynamic = 'force-dynamic';

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

export type ModelCatalogEntry = {
  id: string;               // "provider/modelId", e.g. "anthropic/claude-haiku-4-5"
  name: string;
  provider: 'anthropic' | 'openai' | 'google';
  contextLength: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  tools: boolean;
};

function enrichEntry(
  id: string,
  name: string,
  provider: ModelCatalogEntry['provider'],
): ModelCatalogEntry {
  const meta = MODEL_META[id];
  return {
    id,
    name,
    provider,
    contextLength: meta?.contextLength ?? null,
    promptPer1M: meta?.promptPer1M ?? null,
    completionPer1M: meta?.completionPer1M ?? null,
    vision: meta?.vision ?? true,
    tools: true,
  };
}

// ---------------------------------------------------------------------------
// Provider fetchers
// ---------------------------------------------------------------------------

type AnthropicModel = { id: string; display_name: string };
type OpenAIModel    = { id: string; owned_by: string; object: string };

async function fetchAnthropicModels(): Promise<ModelCatalogEntry[]> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY not set');

  const res = await fetch('https://api.anthropic.com/v1/models', {
    headers: {
      'x-api-key': apiKey,
      'anthropic-version': '2023-06-01',
      Accept: 'application/json',
    },
    signal: AbortSignal.timeout(8_000),
  });
  if (!res.ok) throw new Error(`Anthropic API responded ${res.status}`);
  const body = (await res.json()) as { data?: AnthropicModel[] };
  return (body.data ?? []).map((m) =>
    enrichEntry(`anthropic/${m.id}`, m.display_name || m.id, 'anthropic'),
  );
}

// Models to exclude from the OpenAI list — non-chat capabilities.
const OPENAI_ID_BLOCKLIST = [
  'dall-e', 'whisper', 'tts', 'text-embedding', 'text-moderation',
  'omni-moderation', 'babbage', 'davinci', 'ada', 'curie',
  'text-search', 'code-search', 'codex',
];

async function fetchOpenAIModels(): Promise<ModelCatalogEntry[]> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) throw new Error('OPENAI_API_KEY not set');

  const res = await fetch('https://api.openai.com/v1/models', {
    headers: {
      Authorization: `Bearer ${apiKey}`,
      Accept: 'application/json',
    },
    signal: AbortSignal.timeout(8_000),
  });
  if (!res.ok) throw new Error(`OpenAI API responded ${res.status}`);
  const body = (await res.json()) as { data?: OpenAIModel[] };
  const all: OpenAIModel[] = body.data ?? [];

  const chat = all.filter((m) => {
    if (m.owned_by !== 'openai' && m.owned_by !== 'openai-internal') return false;
    const low = m.id.toLowerCase();
    return !OPENAI_ID_BLOCKLIST.some((block) => low.startsWith(block));
  });

  // Sort: gpt-4o family first, then o-series, then everything else.
  chat.sort((a, b) => {
    const rank = (id: string) => {
      if (id.startsWith('gpt-4o')) return 0;
      if (/^o\d/.test(id)) return 1;
      if (id.startsWith('gpt-4')) return 2;
      return 3;
    };
    const rd = rank(a.id) - rank(b.id);
    if (rd !== 0) return rd;
    return b.id.localeCompare(a.id); // newest snapshots first within group
  });

  return chat.map((m) => enrichEntry(`openai/${m.id}`, m.id, 'openai'));
}

// Static curated list of Vertex-hosted Gemini models.
// Vertex doesn't have a simple REST model-listing endpoint — these are the
// currently available production models (updated manually when new ones ship).
const VERTEX_MODELS: Array<{ id: string; name: string }> = [
  { id: 'google/gemini-2.5-pro',         name: 'Gemini 2.5 Pro'          },
  { id: 'google/gemini-2.5-flash',        name: 'Gemini 2.5 Flash'         },
  { id: 'google/gemini-2.5-flash-lite',   name: 'Gemini 2.5 Flash-Lite'    },
  { id: 'google/gemini-2.0-flash',        name: 'Gemini 2.0 Flash'         },
  { id: 'google/gemini-1.5-pro-002',      name: 'Gemini 1.5 Pro 002'       },
  { id: 'google/gemini-1.5-flash-002',    name: 'Gemini 1.5 Flash 002'     },
];

function getVertexModels(): ModelCatalogEntry[] {
  return VERTEX_MODELS.map((m) => enrichEntry(m.id, m.name, 'google'));
}

// ---------------------------------------------------------------------------
// Route handler
// ---------------------------------------------------------------------------

export async function GET() {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const [anthropicResult, openaiResult] = await Promise.allSettled([
    fetchAnthropicModels(),
    fetchOpenAIModels(),
  ]);

  const providerErrors: string[] = [];
  const models: ModelCatalogEntry[] = [];

  if (anthropicResult.status === 'fulfilled') {
    models.push(...anthropicResult.value);
  } else {
    providerErrors.push(`Anthropic: ${anthropicResult.reason instanceof Error ? anthropicResult.reason.message : String(anthropicResult.reason)}`);
  }

  if (openaiResult.status === 'fulfilled') {
    models.push(...openaiResult.value);
  } else {
    providerErrors.push(`OpenAI: ${openaiResult.reason instanceof Error ? openaiResult.reason.message : String(openaiResult.reason)}`);
  }

  // Vertex is always present (static list).
  models.push(...getVertexModels());

  return NextResponse.json({ models, providerErrors });
}
