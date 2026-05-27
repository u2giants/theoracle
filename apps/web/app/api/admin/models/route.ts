// GET /api/admin/models?stage=interview|extraction|synthesis
//
// Returns the list of models available in the admin model picker for the
// given stage. Each stage has its own pool stored in settings as
// `model_pool_${stage}`.
//
// Strategy:
//   1. Read the per-stage `model_pool_${stage}` setting from DB
//      (JSON array of "provider/modelId" strings).
//   2. If the pool is non-empty, return those models enriched with static metadata.
//   3. If the pool is empty, fall back to EVERY model in MODEL_META plus the
//      6 curated catalog routes. The ModelPicker then filters client-side by
//      requiredCaps, so reasoning-required stages (Synthesis) surface
//      o-series models, vision-required stages surface vision models, etc.
//
// Model IDs are in "provider/modelId" format (compatible with resolveModelRoute).
// OpenRouter is NOT used.
//
// Requires admin.
// Response: { models: Model[] }

import { NextResponse, type NextRequest } from 'next/server';
import { eq } from 'drizzle-orm';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import { ORACLE_MODEL_ROUTES, PRODUCTION_ROUTE_IDS, MODEL_POOL_SETTING_KEYS } from '@oracle/ai';
import { MODEL_META } from '@/lib/model-metadata';

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

function metaToInfo(id: string): ModelInfo {
  const meta = MODEL_META[id];
  const slug = id.split('/')[1] ?? id;
  // Heuristic reasoning flag: o-series OpenAI models always count, beyond
  // whatever the static table says.
  const reasoning = meta?.reasoning ?? (slug.startsWith('o') && /^o\d/.test(slug));
  return {
    id,
    name: id,
    contextLength: meta?.contextLength ?? null,
    promptPer1M: meta?.promptPer1M ?? null,
    completionPer1M: meta?.completionPer1M ?? null,
    vision: meta?.vision ?? true,
    tools: true,
    files: meta?.vision ?? true,
    reasoning,
    imageGen: false,
  };
}

/** Format a curated catalog route as a ModelInfo (empty-pool fallback augment). */
function catalogRouteToInfo(routeId: string): ModelInfo | null {
  const route = ORACLE_MODEL_ROUTES[routeId];
  if (!route) return null;
  const id = `${route.provider === 'vertex' ? 'google' : route.provider}/${route.modelId}`;
  // If we already have static metadata for this id, prefer it — it has prices
  // and context.  Otherwise build a minimal ModelInfo from the route record.
  if (MODEL_META[id]) return metaToInfo(id);
  return {
    id,
    name: route.displayName,
    contextLength: null,
    promptPer1M: null,
    completionPer1M: null,
    vision: route.supportsVision,
    tools: route.supportsToolCalling,
    files: route.supportsVision,
    reasoning: route.supportsReasoningControls,
    imageGen: false,
  };
}

type Stage = 'interview' | 'extraction' | 'synthesis';

function parseStage(req: NextRequest): Stage {
  const raw = req.nextUrl.searchParams.get('stage');
  if (raw === 'interview' || raw === 'extraction' || raw === 'synthesis') return raw;
  return 'interview';
}

export async function GET(req: NextRequest) {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const stage = parseStage(req);
  const poolKey = MODEL_POOL_SETTING_KEYS[stage];

  const db = getDirectDb();
  const poolRow = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, poolKey))
    .limit(1);

  const pool: string[] = Array.isArray(poolRow[0]?.value) ? (poolRow[0]!.value as string[]) : [];

  if (pool.length > 0) {
    return NextResponse.json({ models: pool.map(metaToInfo) });
  }

  // Empty pool — fall back to ALL known models so the dropdown is sensible
  // for every stage including reasoning-required ones. Merge MODEL_META
  // entries with the 6 curated catalog routes (dedupe by id).
  const byId = new Map<string, ModelInfo>();
  for (const id of Object.keys(MODEL_META)) {
    byId.set(id, metaToInfo(id));
  }
  for (const routeId of PRODUCTION_ROUTE_IDS) {
    const info = catalogRouteToInfo(routeId);
    if (info && !byId.has(info.id)) byId.set(info.id, info);
  }

  return NextResponse.json({ models: Array.from(byId.values()) });
}
