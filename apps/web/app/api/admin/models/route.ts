// GET /api/admin/models
//
// Server-side proxy for https://openrouter.ai/api/v1/models/user
// Keeps OPENROUTER_API_KEY out of the browser.
// Restricted to admins.

import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';

export const dynamic = 'force-dynamic';

type OpenRouterModel = {
  id: string;
  name: string;
  context_length: number | null;
  pricing: {
    prompt: string;    // cost per token (string decimal)
    completion: string;
  } | null;
};

type OpenRouterResponse = {
  data: OpenRouterModel[];
};

export async function GET() {
  // Admin-only.
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: 'OPENROUTER_API_KEY not configured' },
      { status: 500 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch('https://openrouter.ai/api/v1/models/user', {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'Content-Type': 'application/json',
      },
      // Don't cache — always reflect the user's actual model access.
      cache: 'no-store',
    });
  } catch (err) {
    console.error('[admin/models] fetch failed', err);
    return NextResponse.json(
      { error: 'Failed to reach OpenRouter' },
      { status: 502 },
    );
  }

  if (!upstream.ok) {
    const body = await upstream.text();
    console.error('[admin/models] OpenRouter error', upstream.status, body);
    return NextResponse.json(
      { error: 'OpenRouter returned an error', detail: body },
      { status: 502 },
    );
  }

  const json = (await upstream.json()) as OpenRouterResponse;

  // Return a trimmed, stable shape — no raw pricing decimals in the client.
  const models = (json.data ?? [])
    .map((m) => ({
      id: m.id,
      name: m.name ?? m.id,
      contextLength: m.context_length ?? null,
      // Convert per-token price to cost per 1M tokens for display.
      promptPer1M:
        m.pricing?.prompt != null
          ? (parseFloat(m.pricing.prompt) * 1_000_000).toFixed(2)
          : null,
      completionPer1M:
        m.pricing?.completion != null
          ? (parseFloat(m.pricing.completion) * 1_000_000).toFixed(2)
          : null,
    }))
    .sort((a, b) => a.id.localeCompare(b.id));

  return NextResponse.json({ models });
}
