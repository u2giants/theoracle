// Public barrel for the model-capabilities module.
//
// The catalog is persisted in the `model_capabilities` Postgres table and
// refreshed from OpenRouter on admin demand (or by a future scheduled job).
// `loadModelCatalog(db)` is the read path — it just reads the table.
// `refreshModelCatalog(db)` is the write path — fetches OpenRouter and
// upserts every row.

import { sql } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';
import { modelCapabilities } from '@oracle/db/schema';
import type { ModelCapability } from './types';
import { fetchOpenRouterCatalog } from './sources/openrouter';

export type { ModelCapability, ModelProvider, ModelCapabilitySource } from './types';

export interface RefreshModelCatalogResult {
  catalog: ModelCapability[];
  written: number;
  refreshedAt: string;
}

/**
 * Refresh the persisted catalog from OpenRouter. Upserts every model row;
 * the previous values are overwritten. Old rows whose ids no longer appear
 * in OpenRouter's response are kept (deprecated upstream but still
 * referenced by existing pool selections); a future cleanup job can prune
 * them once we add usage tracking.
 */
export async function refreshModelCatalog(db: OracleDb): Promise<RefreshModelCatalogResult> {
  const catalog = await fetchOpenRouterCatalog();
  const refreshedAtIso = new Date().toISOString();

  if (catalog.length === 0) return { catalog: [], written: 0, refreshedAt: refreshedAtIso };

  const rows = catalog.map((c) => ({
    id: c.id,
    provider: c.provider,
    displayName: c.displayName,
    contextLength: c.contextLength,
    maxOutputTokens: c.maxOutputTokens,
    promptPer1mUsd: c.promptPer1mUsd != null ? String(c.promptPer1mUsd) : null,
    completionPer1mUsd: c.completionPer1mUsd != null ? String(c.completionPer1mUsd) : null,
    vision: c.vision,
    pdf: c.pdf,
    thinking: c.thinking,
    structuredOutputs: c.structuredOutputs,
    toolCalling: c.toolCalling,
    promptCaching: c.promptCaching,
    knowledgeCutoff: c.knowledgeCutoff,
    source: c.source,
    refreshedAt: new Date(refreshedAtIso),
  }));

  await db
    .insert(modelCapabilities)
    .values(rows)
    .onConflictDoUpdate({
      target: modelCapabilities.id,
      set: {
        provider: sql`excluded.provider`,
        displayName: sql`excluded.display_name`,
        contextLength: sql`excluded.context_length`,
        maxOutputTokens: sql`excluded.max_output_tokens`,
        promptPer1mUsd: sql`excluded.prompt_per_1m_usd`,
        completionPer1mUsd: sql`excluded.completion_per_1m_usd`,
        vision: sql`excluded.vision`,
        pdf: sql`excluded.pdf`,
        thinking: sql`excluded.thinking`,
        structuredOutputs: sql`excluded.structured_outputs`,
        toolCalling: sql`excluded.tool_calling`,
        promptCaching: sql`excluded.prompt_caching`,
        knowledgeCutoff: sql`excluded.knowledge_cutoff`,
        source: sql`excluded.source`,
        refreshedAt: sql`excluded.refreshed_at`,
      },
    });

  return { catalog, written: rows.length, refreshedAt: refreshedAtIso };
}

/** Read the persisted catalog. Empty array means "never refreshed". */
export async function loadModelCatalog(db: OracleDb): Promise<ModelCapability[]> {
  const rows = await db.select().from(modelCapabilities);
  return rows.map((r): ModelCapability => ({
    id: r.id,
    provider: r.provider as ModelCapability['provider'],
    displayName: r.displayName,
    contextLength: r.contextLength,
    maxOutputTokens: r.maxOutputTokens,
    promptPer1mUsd: r.promptPer1mUsd != null ? Number(r.promptPer1mUsd) : null,
    completionPer1mUsd: r.completionPer1mUsd != null ? Number(r.completionPer1mUsd) : null,
    vision: r.vision,
    pdf: r.pdf,
    thinking: r.thinking,
    structuredOutputs: r.structuredOutputs,
    toolCalling: r.toolCalling,
    promptCaching: r.promptCaching,
    knowledgeCutoff: r.knowledgeCutoff,
    source: r.source as ModelCapability['source'],
  }));
}

/** Return the most recent refreshedAt timestamp across all rows, or null. */
export async function getCatalogRefreshedAt(db: OracleDb): Promise<Date | null> {
  const rows = await db
    .select({ refreshedAt: modelCapabilities.refreshedAt })
    .from(modelCapabilities)
    .orderBy(sql`${modelCapabilities.refreshedAt} desc`)
    .limit(1);
  return rows[0]?.refreshedAt ?? null;
}
