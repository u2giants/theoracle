// GET  /api/admin/model-catalog   — read persisted catalog (with pricing/caps)
// POST /api/admin/model-catalog   — refresh from OpenRouter, upsert into DB
//
// Capability and pricing data comes from openrouter.ai/api/v1/models. The
// catalog lives in the model_capabilities Postgres table; this endpoint does
// not call OpenRouter on every request — that only happens on POST (admin
// "Refresh catalog" button or a future cron).

import { NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/auth-guard';
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
  try {
    await requireAdmin();
  } catch {
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
  try {
    await requireAdmin();
  } catch {
    return NextResponse.json({ error: 'Forbidden' }, { status: 403 });
  }

  const db = getDirectDb();
  try {
    const { catalog, written, refreshedAt } = await refreshModelCatalog(db);
    return NextResponse.json({
      models: catalog.map(capabilityToEntry),
      written,
      refreshedAt,
    });
  } catch (err) {
    return NextResponse.json(
      { error: 'refresh_failed', detail: err instanceof Error ? err.message : String(err) },
      { status: 502 },
    );
  }
}
