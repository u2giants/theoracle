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
  provider: 'anthropic' | 'openai' | 'google';
  contextLength: number | null;
  maxOutputTokens: number | null;
  promptPer1M: number | null;
  completionPer1M: number | null;
  vision: boolean;
  pdf: boolean;
  thinking: boolean;
  tools: boolean;
  structuredOutputs: boolean;
  promptCaching: boolean;
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
    promptCaching: cap.promptCaching,
    knowledgeCutoff: cap.knowledgeCutoff,
  };
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

  return NextResponse.json({
    models: catalog.map(capabilityToEntry),
    refreshedAt: refreshedAt ? refreshedAt.toISOString() : null,
    catalogSize: catalog.length,
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
    return NextResponse.json({
      models: catalog.map(capabilityToEntry),
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
