// GET /api/admin/models?stage=interview|extraction|synthesis|<auxiliary id>
//
// Returns the model list for the ModelPicker on /admin/settings. Reads the
// persisted model_capabilities table for capability + pricing data — no
// provider API calls per request.
//
// Strategy:
//   1. Pipeline stages (interview/extraction/synthesis) read the per-stage
//      model_pool_${stage} setting: non-empty pool → only those rows; empty →
//      full catalog (the client filters by the stage's required caps).
//   2. Any auxiliary-model id (general-purpose, vision, …) draws from the full
//      catalog; the client filters by that aux model's single required
//      capability (or not at all).
//
// Requires admin.

import { NextResponse, type NextRequest } from 'next/server';
import { eq } from 'drizzle-orm';
import { requireAdmin } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import { settings } from '@oracle/db/schema';
import {
  MODEL_POOL_SETTING_KEYS,
  AUXILIARY_MODEL_IDS,
  getAuxiliaryModelDef,
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

type PipelineStage = 'interview' | 'extraction' | 'synthesis';
type ModelScope =
  | { kind: 'stage'; stage: PipelineStage }
  | { kind: 'auxiliary'; auxiliaryId: string; poolKey?: string }
  | { kind: 'full' };

function parseScope(req: NextRequest): ModelScope {
  const raw = req.nextUrl.searchParams.get('stage');
  if (raw === 'interview' || raw === 'extraction' || raw === 'synthesis') {
    return { kind: 'stage', stage: raw };
  }
  // Any auxiliary-model id (general-purpose, vision, …) → full catalog; the
  // client filters by that model's required capability. If that auxiliary has
  // an ordered pool, return only pool members so fallbacks and pickers stay in
  // the same approved set.
  if (raw && AUXILIARY_MODEL_IDS.has(raw)) {
    return { kind: 'auxiliary', auxiliaryId: raw, poolKey: getAuxiliaryModelDef(raw)?.poolSettingKey };
  }
  return { kind: 'stage', stage: 'interview' };
}

export async function GET(req: NextRequest) {
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const scope = parseScope(req);
  const db = getDirectDb();
  const catalog = await loadModelCatalog(db);

  // Auxiliary-model pickers draw from the configured auxiliary pool when one
  // exists, otherwise from the full catalog.
  if (scope.kind === 'auxiliary') {
    if (!scope.poolKey) {
      return NextResponse.json({ models: catalog.map(capabilityToModelInfo) });
    }
    const poolRow = await db
      .select({ value: settings.value })
      .from(settings)
      .where(eq(settings.key, scope.poolKey))
      .limit(1);
    const pool: string[] = Array.isArray(poolRow[0]?.value) ? (poolRow[0]!.value as string[]) : [];
    if (pool.length === 0) {
      return NextResponse.json({ models: catalog.map(capabilityToModelInfo) });
    }
    const poolSet = new Set(pool);
    return NextResponse.json({
      models: catalog.filter((c) => poolSet.has(c.id)).map(capabilityToModelInfo),
    });
  }

  if (scope.kind === 'full') {
    return NextResponse.json({ models: catalog.map(capabilityToModelInfo) });
  }

  const poolKey = MODEL_POOL_SETTING_KEYS[scope.stage];
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
