// GET /api/admin/models?stage=interview|extraction|synthesis|general
//
// Returns the model list for the ModelPicker on /admin/settings, scoped to
// the requested stage's pool. Reads the persisted model_capabilities table
// for capability + pricing data — no provider API calls per request.
//
// Strategy:
//   1. Read the per-stage model_pool_${stage} setting (or, for the special
//      "general" picker, ignore the pool — the general-purpose picker shows
//      the full catalog so the admin can pick any model).
//   2. Load the persisted catalog from model_capabilities.
//   3. Pool non-empty → return only catalog rows in the pool.
//      Pool empty → return the full catalog (client filters by required caps).
//
// Requires admin.

import { NextResponse, type NextRequest } from 'next/server';
import { eq } from 'drizzle-orm';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import {
  MODEL_POOL_SETTING_KEYS,
  loadModelCatalog,
  type ModelCapability,
} from '@oracle/ai';

export const dynamic = 'force-dynamic';

export type ModelInfo = {
  id: string;
  name: string;
  provider: string;
  contextLength: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  // Canonical capability fields (matches model_capabilities DB columns and
  // the shared stage-requirements module in apps/web/lib/stage-requirements.ts).
  vision: boolean;
  thinking: boolean;
  tools: boolean;
  structuredOutputs: boolean;
  promptCaching: boolean;
  outputCap: boolean;
  pdf: boolean;
  // Legacy aliases kept for older client code (channel chat, document upload)
  // that still uses the friendly names. Remove after those callers migrate.
  files: boolean;       // alias for pdf
  reasoning: boolean;   // alias for thinking
  imageGen: boolean;    // not currently sourced; always false
};

function capabilityToModelInfo(cap: ModelCapability): ModelInfo {
  return {
    id: cap.id,
    name: cap.displayName,
    provider: cap.provider,
    contextLength: cap.contextLength,
    promptPer1M: cap.promptPer1mUsd,
    completionPer1M: cap.completionPer1mUsd,
    vision: cap.vision,
    thinking: cap.thinking,
    tools: cap.toolCalling,
    structuredOutputs: cap.structuredOutputs,
    promptCaching: cap.promptCaching,
    outputCap: cap.outputCap,
    pdf: cap.pdf,
    files: cap.pdf,
    reasoning: cap.thinking,
    imageGen: false,
  };
}

type StageOrGeneral = 'interview' | 'extraction' | 'synthesis' | 'general';

function parseStage(req: NextRequest): StageOrGeneral {
  const raw = req.nextUrl.searchParams.get('stage');
  if (raw === 'interview' || raw === 'extraction' || raw === 'synthesis' || raw === 'general') return raw;
  return 'interview';
}

export async function GET(req: NextRequest) {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const stage = parseStage(req);
  const db = getDirectDb();
  const catalog = await loadModelCatalog(db);

  // The general-purpose picker draws from the full catalog (no pool).
  if (stage === 'general') {
    return NextResponse.json({ models: catalog.map(capabilityToModelInfo) });
  }

  const poolKey = MODEL_POOL_SETTING_KEYS[stage];
  const poolRow = await db
    .select({ value: settings.value })
    .from(settings)
    .where(eq(settings.key, poolKey))
    .limit(1);

  const pool: string[] = Array.isArray(poolRow[0]?.value) ? (poolRow[0]!.value as string[]) : [];

  if (pool.length > 0) {
    const poolSet = new Set(pool);
    return NextResponse.json({
      models: catalog.filter((c) => poolSet.has(c.id)).map(capabilityToModelInfo),
    });
  }

  return NextResponse.json({ models: catalog.map(capabilityToModelInfo) });
}
