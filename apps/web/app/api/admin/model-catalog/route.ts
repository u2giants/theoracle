// GET /api/admin/model-catalog
//
// Server-side proxy to OpenRouter's public /api/v1/models endpoint.
// Used by the model-pool editor so it can fetch the full catalog without
// hitting browser CORS restrictions.
//
// Filtered to the Big 3 providers only (anthropic/, openai/, google/).
// The Oracle production AI path only supports Anthropic, Vertex, and OpenAI.
//
// Requires admin.
//
// Response: { models: ModelCatalogEntry[] }

import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';

export const dynamic = 'force-dynamic';

export type ModelCatalogEntry = {
  id: string;
  name: string;
  contextLength: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  tools: boolean;
};

type ORModel = {
  id: string;
  name: string;
  context_length?: number;
  pricing?: { prompt?: string; completion?: string };
  architecture?: {
    modality?: string;
    input_modalities?: string[];
  };
};

export async function GET() {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  let allModels: ORModel[] = [];
  try {
    const res = await fetch('https://openrouter.ai/api/v1/models', {
      headers: { Accept: 'application/json' },
      signal: AbortSignal.timeout(8_000),
    });
    if (!res.ok) {
      return NextResponse.json(
        { error: `OpenRouter responded ${res.status}` },
        { status: 502 },
      );
    }
    const body = (await res.json()) as { data?: ORModel[] };
    allModels = body.data ?? [];
  } catch (err) {
    return NextResponse.json(
      { error: `OpenRouter fetch failed: ${err instanceof Error ? err.message : String(err)}` },
      { status: 502 },
    );
  }

  // Filter to only the Big 3 Oracle-supported providers.
  const supported = allModels.filter(
    (m) =>
      m.id.startsWith('anthropic/') ||
      m.id.startsWith('openai/') ||
      m.id.startsWith('google/'),
  );

  const models: ModelCatalogEntry[] = supported.map((m) => {
    const inputMods = m.architecture?.input_modalities ?? [];
    const modality = m.architecture?.modality ?? '';
    const hasImage = inputMods.includes('image') || modality.includes('image');
    const promptRaw = m.pricing?.prompt;
    const compRaw = m.pricing?.completion;

    return {
      id: m.id,
      name: m.name || m.id,
      contextLength: m.context_length ?? null,
      promptPer1M: promptRaw != null ? parseFloat(promptRaw) * 1_000_000 : null,
      completionPer1M: compRaw != null ? parseFloat(compRaw) * 1_000_000 : null,
      vision: hasImage,
      tools: true,
    };
  });

  // Sort by provider, then cheapest first.
  models.sort((a, b) => {
    const ap = a.id.split('/')[0]!;
    const bp = b.id.split('/')[0]!;
    if (ap !== bp) return ap.localeCompare(bp);
    return (a.promptPer1M ?? Infinity) - (b.promptPer1M ?? Infinity);
  });

  return NextResponse.json({ models });
}
