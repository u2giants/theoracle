// Anthropic capability source — parses api.anthropic.com /v1/models response.
//
// Anthropic's /v1/models endpoint already returns a structured `capabilities`
// object with explicit booleans for `thinking`, `image_input`, `pdf_input`,
// `structured_outputs`, plus `max_input_tokens` and `max_tokens`. Nothing needs
// to be guessed or AI-classified for this provider.

import type { ModelCapability } from '../types';

type AnthropicModelRaw = {
  id: string;
  display_name?: string;
  max_input_tokens?: number;
  max_tokens?: number;
  capabilities?: {
    image_input?: { supported?: boolean };
    pdf_input?: { supported?: boolean };
    thinking?: { supported?: boolean };
    structured_outputs?: { supported?: boolean };
    // 'effort' (reasoning_effort levels) — currently we only surface the boolean
    // 'thinking' flag in the unified ModelCapability type, but we keep parsing
    // 'effort' here so a future low/medium/high UI can be added without touching
    // the source layer again.
    effort?: { supported?: boolean };
    batch?: { supported?: boolean };
  };
};

async function listAllAnthropicModels(apiKey: string): Promise<AnthropicModelRaw[]> {
  const out: AnthropicModelRaw[] = [];
  let after: string | null = null;
  // Anthropic's list endpoint paginates; loop until has_more is false.
  for (let i = 0; i < 10; i++) {
    const url = new URL('https://api.anthropic.com/v1/models');
    url.searchParams.set('limit', '100');
    if (after) url.searchParams.set('after_id', after);
    const res = await fetch(url.toString(), {
      headers: {
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01',
        Accept: 'application/json',
      },
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) throw new Error(`Anthropic /v1/models: ${res.status} ${await res.text()}`);
    const body = (await res.json()) as {
      data: AnthropicModelRaw[];
      has_more: boolean;
      last_id: string | null;
    };
    out.push(...(body.data ?? []));
    if (!body.has_more || !body.last_id) break;
    after = body.last_id;
  }
  return out;
}

export async function fetchAnthropicCapabilities(): Promise<ModelCapability[]> {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) throw new Error('ANTHROPIC_API_KEY not set');

  const raw = await listAllAnthropicModels(apiKey);
  const now = new Date().toISOString();

  return raw.map((m): ModelCapability => ({
    id: `anthropic/${m.id}`,
    provider: 'anthropic',
    displayName: m.display_name || m.id,
    contextLength: m.max_input_tokens ?? null,
    maxOutputTokens: m.max_tokens ?? null,
    vision: m.capabilities?.image_input?.supported === true,
    pdf: m.capabilities?.pdf_input?.supported === true,
    thinking: m.capabilities?.thinking?.supported === true,
    structuredOutputs: m.capabilities?.structured_outputs?.supported === true,
    // Anthropic /v1/models doesn't separately surface a tool_use boolean;
    // every modern Claude (3.5+) supports tools.  We treat any model returned
    // by the API as tool-capable; if Anthropic ever ships a non-tool model
    // they'll add a flag and we'll wire it in here.
    toolCalling: true,
    promptCaching: true,
    source: 'anthropic_api',
    fetchedAt: now,
  }));
}
