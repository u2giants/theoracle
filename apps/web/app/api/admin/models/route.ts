// GET /api/admin/models?stage=interview|extraction|synthesis
//
// Returns the model list for the ModelPicker on the main /admin/settings page,
// scoped to one stage's pool. Capabilities come from the discovered catalog
// (apps/web → @oracle/ai discoverModelCatalog) — no hand-typed tables.
//
// Strategy:
//   1. Read the per-stage model_pool_${stage} setting.
//   2. Run discovery to get the full capability catalog (cached 1h in memory).
//   3. If pool is non-empty: return only the catalog entries whose id is in
//      the pool. Models in the pool but not in the catalog are dropped
//      silently (the pool may reference IDs that have been removed upstream).
//   4. If pool is empty: return the full catalog as the fallback — the
//      ModelPicker filters client-side by required capabilities.
//
// Requires admin.
// Response: { models: Model[] }

import { NextResponse, type NextRequest } from 'next/server';
import { eq } from 'drizzle-orm';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import {
  AnthropicAdapter,
  OpenAIAdapter,
  OracleAIClient,
  VertexGeminiAdapter,
  MODEL_POOL_SETTING_KEYS,
  discoverModelCatalog,
  type ModelCapability,
} from '@oracle/ai';

export const dynamic = 'force-dynamic';

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

let _client: OracleAIClient | null = null;
function getOracleClient(): OracleAIClient {
  if (!_client) {
    _client = new OracleAIClient({
      adapters: {
        anthropic: new AnthropicAdapter(),
        vertex: new VertexGeminiAdapter(),
        openai: new OpenAIAdapter(),
      },
      fallbackOnError: false,
    });
  }
  return _client;
}

function capabilityToModelInfo(cap: ModelCapability): ModelInfo {
  return {
    id: cap.id,
    name: cap.displayName,
    contextLength: cap.contextLength,
    promptPer1M: null,
    completionPer1M: null,
    vision: cap.vision,
    tools: cap.toolCalling,
    files: cap.pdf,
    reasoning: cap.thinking,
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

  let catalog: ModelCapability[];
  try {
    const result = await discoverModelCatalog(getOracleClient(), { force: false });
    catalog = result.catalog;
  } catch (err) {
    return NextResponse.json(
      { error: 'discovery_failed', detail: err instanceof Error ? err.message : String(err) },
      { status: 500 },
    );
  }

  if (pool.length > 0) {
    const poolSet = new Set(pool);
    const filtered = catalog.filter((c) => poolSet.has(c.id));
    return NextResponse.json({ models: filtered.map(capabilityToModelInfo) });
  }

  // Empty pool — return the full discovered catalog. The ModelPicker filters
  // client-side by the stage's required capabilities (vision / reasoning / etc.).
  return NextResponse.json({ models: catalog.map(capabilityToModelInfo) });
}
