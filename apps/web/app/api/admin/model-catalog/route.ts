// GET  /api/admin/model-catalog   — read persisted catalog (with pricing/caps)
// POST /api/admin/model-catalog   — refresh from provider APIs + OpenRouter, upsert into DB
//
// Model list comes from the 3 direct provider APIs (Anthropic, OpenAI, Google Gemini).
// Pricing and capability flags are enriched from openrouter.ai/api/v1/models.
// The catalog lives in the model_capabilities Postgres table; this endpoint does
// not call any external API on GET — that only happens on POST (admin
// "Refresh catalog" button or a future cron).

import { NextResponse } from 'next/server';
import { getCurrentEmployee } from '@/lib/auth-guard';
import { getDirectDb } from '@oracle/db/client';
import {
  loadModelCatalog,
  refreshModelCatalog,
  getCatalogRefreshedAt,
  type ModelCapability,
} from '@oracle/ai';

export const dynamic = 'force-dynamic';

export type ModelCatalogEntry = {
  id: string;
  name: string;
  provider: 'anthropic' | 'openai' | 'google' | 'deepseek' | 'qwen';
  contextLength: number | null;
  maxOutputTokens: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  pdf: boolean;
  thinking: boolean;
  tools: boolean;
  structuredOutputs: boolean;
  strictJsonSchema: boolean;
  deepSchemaAccepted: boolean;
  adapterParamsSafe: boolean;
  promptCaching: boolean;
  outputCap: boolean;
  adapterParamNotes: Record<string, unknown>;
  knowledgeCutoff: string | null;
};

function capabilityToEntry(cap: ModelCapability): ModelCatalogEntry {
  return {
    id: cap.id,
    name: cap.displayName,
    provider: cap.provider,
    contextLength: cap.contextLength,
    maxOutputTokens: cap.maxOutputTokens,
    promptPer1M: cap.promptPer1mUsd,
    completionPer1M: cap.completionPer1mUsd,
    vision: cap.vision,
    pdf: cap.pdf,
    thinking: cap.thinking,
    tools: cap.toolCalling,
    structuredOutputs: cap.structuredOutputs,
    strictJsonSchema: cap.strictJsonSchema,
    deepSchemaAccepted: cap.deepSchemaAccepted,
    adapterParamsSafe: cap.adapterParamsSafe,
    promptCaching: cap.promptCaching,
    outputCap: cap.outputCap,
    adapterParamNotes: cap.adapterParamNotes,
    knowledgeCutoff: cap.knowledgeCutoff,
  };
}

/**
 * Drop models that have NO pricing AND NO capability flags.
 *
 * `refreshModelCatalog` (D13 quality filters) drops these at write time, but
 * old rows from before the filter shipped — or rows written when OpenRouter
 * enrichment was unavailable — can still be in the DB. Apply the same filter
 * at read time so the admin UI never has to render them. Models priced at
 * >= $15.01/1M are also dropped here for the same reason.
 */
function passesQualityFilter(cap: ModelCapability): boolean {
  const hasPrice = cap.promptPer1mUsd != null;
  const hasCaps =
    cap.vision || cap.pdf || cap.thinking ||
    cap.structuredOutputs || cap.strictJsonSchema || cap.deepSchemaAccepted ||
    cap.toolCalling ||
    cap.promptCaching || cap.outputCap;
  if (!hasPrice && !hasCaps) return false;
  if (cap.promptPer1mUsd != null && cap.promptPer1mUsd >= 15.01) return false;
  return true;
}

export async function GET() {
  const employee = await getCurrentEmployee();
  if (!employee?.isAdmin) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const db = getDirectDb();
  const [catalog, refreshedAt] = await Promise.all([
    loadModelCatalog(db),
    getCatalogRefreshedAt(db),
  ]);

  const filtered = catalog.filter(passesQualityFilter);
  return NextResponse.json({
    models: filtered.map(capabilityToEntry),
    refreshedAt: refreshedAt ? refreshedAt.toISOString() : null,
    catalogSize: filtered.length,
  });
}

export async function POST() {
  const employee = await getCurrentEmployee();
  if (!employee?.isAdmin) {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const db = getDirectDb();
  try {
    const { catalog, written, refreshedAt, errors, unenrichedIds } = await refreshModelCatalog(db);
    // The refresh function applies the quality filter at write time, but a
    // belt-and-suspenders pass here keeps the read shape consistent.
    const filtered = catalog.filter(passesQualityFilter);
    return NextResponse.json({
      models: filtered.map(capabilityToEntry),
      written,
      refreshedAt,
      errors,         // non-fatal per-source errors (e.g. one provider API was down)
      unenrichedIds,  // model IDs with no OpenRouter match — shown in admin diagnostics
    });
  } catch (err) {
    return NextResponse.json(
      { error: 'refresh_failed', detail: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
