// GET /api/admin/models
//
// Returns the list of models available in the admin model picker.
//
// Strategy:
//   1. Read `model_pool` setting from DB (JSON array of "provider/modelId" strings).
//   2. If the pool is non-empty, return those models enriched with static metadata.
//   3. If the pool is empty, fall back to the 6 curated Oracle catalog routes.
//
// Model IDs are in "provider/modelId" format (compatible with resolveModelRoute).
// OpenRouter is NOT used.
//
// Requires admin.
// Response: { models: Model[] }

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
// Static metadata — same table as model-catalog/route.ts
// ---------------------------------------------------------------------------

type ModelMeta = {
  contextLength: number;
  promptPer1M: number;
  completionPer1M: number;
  vision: boolean;
  reasoning?: boolean;
};

const MODEL_META: Record<string, ModelMeta> = {
  // ── Anthropic ──────────────────────────────────────────────────────────────
  'anthropic/claude-opus-4-7':            { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 75,  vision: true  },
  'anthropic/claude-opus-4-7-20250514':   { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 75,  vision: true  },
  'anthropic/claude-sonnet-4-6':          { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true  },
  'anthropic/claude-sonnet-4-6-20250514': { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true  },
  'anthropic/claude-haiku-4-5':           { contextLength: 200_000, promptPer1M: 0.8,   completionPer1M: 4,   vision: true  },
  'anthropic/claude-haiku-4-5-20251001':  { contextLength: 200_000, promptPer1M: 0.8,   completionPer1M: 4,   vision: true  },
  'anthropic/claude-3-7-sonnet-20250219': { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true  },
  'anthropic/claude-3-5-sonnet-20241022': { contextLength: 200_000, promptPer1M: 3,     completionPer1M: 15,  vision: true  },
  'anthropic/claude-3-5-haiku-20241022':  { contextLength: 200_000, promptPer1M: 0.8,   completionPer1M: 4,   vision: true  },
  'anthropic/claude-3-opus-20240229':     { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 75,  vision: true  },

  // ── OpenAI ────────────────────────────────────────────────────────────────
  'openai/gpt-4o':                        { contextLength: 128_000, promptPer1M: 2.5,   completionPer1M: 10,  vision: true  },
  'openai/gpt-4o-2024-11-20':             { contextLength: 128_000, promptPer1M: 2.5,   completionPer1M: 10,  vision: true  },
  'openai/gpt-4o-mini':                   { contextLength: 128_000, promptPer1M: 0.15,  completionPer1M: 0.6, vision: true  },
  'openai/gpt-4o-mini-2024-07-18':        { contextLength: 128_000, promptPer1M: 0.15,  completionPer1M: 0.6, vision: true  },
  'openai/gpt-4-turbo':                   { contextLength: 128_000, promptPer1M: 10,    completionPer1M: 30,  vision: true  },
  'openai/o4-mini':                       { contextLength: 200_000, promptPer1M: 1.1,   completionPer1M: 4.4, vision: true,  reasoning: true },
  'openai/o3':                            { contextLength: 200_000, promptPer1M: 10,    completionPer1M: 40,  vision: true,  reasoning: true },
  'openai/o3-mini':                       { contextLength: 200_000, promptPer1M: 1.1,   completionPer1M: 4.4, vision: false, reasoning: true },
  'openai/o1':                            { contextLength: 200_000, promptPer1M: 15,    completionPer1M: 60,  vision: true,  reasoning: true },
  'openai/o1-mini':                       { contextLength: 128_000, promptPer1M: 1.1,   completionPer1M: 4.4, vision: false, reasoning: true },

  // ── Google / Vertex AI ────────────────────────────────────────────────────
  'google/gemini-2.5-pro':                { contextLength: 1_000_000, promptPer1M: 1.25, completionPer1M: 10,  vision: true },
  'google/gemini-2.5-flash':              { contextLength: 1_000_000, promptPer1M: 0.15, completionPer1M: 0.6, vision: true },
  'google/gemini-2.5-flash-lite':         { contextLength: 1_000_000, promptPer1M: 0.1,  completionPer1M: 0.4, vision: true },
  'google/gemini-2.0-flash':              { contextLength: 1_000_000, promptPer1M: 0.1,  completionPer1M: 0.4, vision: true },
  'google/gemini-1.5-pro-002':            { contextLength: 2_000_000, promptPer1M: 1.25, completionPer1M: 5,   vision: true },
  'google/gemini-1.5-flash-002':          { contextLength: 1_000_000, promptPer1M: 0.075,completionPer1M: 0.3, vision: true },
};

function poolModelToInfo(id: string): ModelInfo {
  const meta = MODEL_META[id];
  const slug = id.split('/')[1] ?? id;
  return {
    id,
    name: meta ? id : id,   // use the ID as display name; pool editor shows friendly names separately
    contextLength: meta?.contextLength ?? null,
    promptPer1M: meta?.promptPer1M ?? null,
    completionPer1M: meta?.completionPer1M ?? null,
    vision: meta?.vision ?? true,
    tools: true,
    files: meta?.vision ?? true,
    reasoning: meta?.reasoning ?? (slug.startsWith('o') && /^o\d/.test(slug)),
    imageGen: false,
  };
}

/** Format a curated catalog route as a ModelInfo object (empty-pool fallback). */
function catalogRouteToInfo(routeId: string): ModelInfo | null {
  const route = ORACLE_MODEL_ROUTES[routeId];
  if (!route) return null;
  // Use "provider/modelId" as the ID so resolveModelRoute can parse it if needed.
  const id = `${route.provider === 'vertex' ? 'google' : route.provider}/${route.modelId}`;
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

  if (pool.length > 0) {
    const models = pool.map(poolModelToInfo);
    return NextResponse.json({ models });
  }

  // Empty pool — fall back to the 6 curated Oracle catalog routes.
  const catalogModels = PRODUCTION_ROUTE_IDS
    .map(catalogRouteToInfo)
    .filter((m): m is ModelInfo => m !== null);

  return NextResponse.json({ models: catalogModels });
}
