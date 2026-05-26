// GET /api/admin/models
//
// Returns the list of models available in the admin model picker.
//
// Strategy:
//   1. Read `model_pool` setting from DB (JSON array of OpenRouter model IDs).
//   2. If the pool is non-empty, fetch those specific models from OpenRouter's
//      public catalog endpoint (no API key required) to get pricing + capabilities.
//   3. If the pool is empty OR OpenRouter is unreachable, fall back to the
//      curated Oracle catalog routes formatted as Model objects.
//
// Requires admin.
//
// Response: { models: Model[] }
// where Model matches the shape expected by the ModelPicker client component.

import { NextResponse } from 'next/server';
import { eq } from 'drizzle-orm';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import { ORACLE_MODEL_ROUTES, PRODUCTION_ROUTE_IDS } from '@oracle/ai';

export const dynamic = 'force-dynamic';

// ---------------------------------------------------------------------------
// Types (must match ModelPicker's `Model` type)
// ---------------------------------------------------------------------------

export type ModelInfo = {
  id: string;
  name: string;
  contextLength: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  tools: boolean;
  files: boolean;
  reasoning: boolean;
  imageGen: boolean;
};

// ---------------------------------------------------------------------------
// OpenRouter catalog types
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function orModelToInfo(m: ORModel): ModelInfo {
  const inputMods = m.architecture?.input_modalities ?? [];
  const modality = m.architecture?.modality ?? '';
  const hasImage = inputMods.includes('image') || modality.includes('image');
  const hasFile = inputMods.includes('file') || modality.includes('file');

  const promptRaw = m.pricing?.prompt;
  const compRaw = m.pricing?.completion;

  return {
    id: m.id,
    name: m.name || m.id,
    contextLength: m.context_length ?? null,
    promptPer1M: promptRaw != null ? parseFloat(promptRaw) * 1_000_000 : null,
    completionPer1M: compRaw != null ? parseFloat(compRaw) * 1_000_000 : null,
    vision: hasImage,
    tools: true,       // all modern models in the pool support tools
    files: hasFile || hasImage,
    reasoning: m.id.includes('thinking') || m.id.includes('o1') || m.id.includes('o3'),
    imageGen: false,
  };
}

/** Format a curated catalog route as a ModelInfo object (fallback path). */
function catalogRouteToInfo(routeId: string): ModelInfo | null {
  const route = ORACLE_MODEL_ROUTES[routeId];
  if (!route) return null;
  return {
    id: routeId,
    name: route.displayName,
    contextLength: null,        // catalog doesn't store context length
    promptPer1M: null,          // catalog doesn't store pricing
    completionPer1M: null,
    vision: route.supportsVision,
    tools: route.supportsToolCalling,
    files: route.supportsVision, // vision-capable routes handle file attachments too
    reasoning: route.supportsReasoningControls,
    imageGen: false,
  };
}

async function fetchOpenRouterModels(ids: string[]): Promise<ModelInfo[]> {
  const res = await fetch('https://openrouter.ai/api/v1/models', {
    headers: { Accept: 'application/json' },
    // 5-second timeout — if OR is slow, fall back to catalog
    signal: AbortSignal.timeout(5_000),
  });
  if (!res.ok) throw new Error(`OpenRouter responded ${res.status}`);
  const body = (await res.json()) as { data?: ORModel[] };
  const allModels: ORModel[] = body.data ?? [];

  // Filter to only the requested IDs if we have a pool; otherwise return all
  // (filtered to supported providers).
  const idSet = new Set(ids);
  const filtered = idSet.size > 0
    ? allModels.filter((m) => idSet.has(m.id))
    : allModels.filter((m) =>
        m.id.startsWith('anthropic/') ||
        m.id.startsWith('openai/') ||
        m.id.startsWith('google/'),
      );

  return filtered.map(orModelToInfo);
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

  const db = getDirectDb();
  const poolRow = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, 'model_pool'))
    .limit(1);

  const pool: string[] = Array.isArray(poolRow[0]?.value) ? (poolRow[0]!.value as string[]) : [];

  // Try OpenRouter first (enriches with pricing + capabilities).
  try {
    const orModels = await fetchOpenRouterModels(pool);
    if (orModels.length > 0) {
      return NextResponse.json({ models: orModels });
    }
    // OR returned 0 results (empty pool hit — fall through to catalog)
  } catch (err) {
    // OpenRouter is unreachable or timed out — fall through to catalog fallback.
    console.warn('[api/admin/models] OpenRouter fetch failed, using catalog fallback:', err instanceof Error ? err.message : String(err));
  }

  // Catalog fallback — the 6 production routes always work.
  const catalogModels = PRODUCTION_ROUTE_IDS
    .map(catalogRouteToInfo)
    .filter((m): m is ModelInfo => m !== null);

  return NextResponse.json({ models: catalogModels });
}
