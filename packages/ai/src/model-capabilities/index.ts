// Public barrel for the model-capabilities module.
//
// Model list is sourced from 3 direct provider APIs (Anthropic, OpenAI,
// Google Gemini). OpenRouter is called separately to enrich each model with
// pricing and capability flags.
//
// `loadModelCatalog(db)` — read path, reads the persisted table.
// `refreshModelCatalog(db)` — write path, fetches all sources and upserts.

import { sql } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';
import { modelCapabilities } from '@oracle/db/schema';
import type { ModelCapability } from './types';
import type { OpenRouterEnrichment } from './sources/openrouter';
import { fetchAnthropicModels } from './sources/anthropic';
import { fetchOpenAIModels } from './sources/openai';
import { fetchGoogleModels } from './sources/google';
import { fetchOpenRouterEnrichment } from './sources/openrouter';

export type { ModelCapability, ModelProvider, ModelCapabilitySource } from './types';

export interface RefreshModelCatalogResult {
  catalog: ModelCapability[];
  written: number;
  refreshedAt: string;
  errors: string[];   // non-fatal per-source errors surfaced to the admin UI
}

const EMPTY_ENRICHMENT: OpenRouterEnrichment = {
  contextLength: null,
  maxOutputTokens: null,
  promptPer1mUsd: null,
  completionPer1mUsd: null,
  vision: false,
  pdf: false,
  thinking: false,
  structuredOutputs: false,
  toolCalling: false,
  promptCaching: false,
  knowledgeCutoff: null,
};

/**
 * Refresh the persisted catalog by fetching from all 3 provider APIs and
 * enriching with OpenRouter pricing + capability data. Each provider source
 * is fetched concurrently; a single source failure is non-fatal (the admin
 * UI receives the error list so they know which provider was skipped).
 *
 * Old rows whose ids no longer appear in any source are kept (deprecated
 * models still referenced by pool selections); a future cleanup pass can
 * prune them once usage tracking confirms they're unused.
 */
export async function refreshModelCatalog(db: OracleDb): Promise<RefreshModelCatalogResult> {
  const refreshedAtIso = new Date().toISOString();
  const errors: string[] = [];

  // Fetch model lists and enrichment in parallel.
  const [anthropicResult, openaiResult, googleResult, enrichmentResult] =
    await Promise.allSettled([
      fetchAnthropicModels(),
      fetchOpenAIModels(),
      fetchGoogleModels(),
      fetchOpenRouterEnrichment(),
    ]);

  const rawModels = [
    ...(anthropicResult.status === 'fulfilled'
      ? anthropicResult.value
      : (errors.push(`Anthropic: ${anthropicResult.reason}`), [])),
    ...(openaiResult.status === 'fulfilled'
      ? openaiResult.value
      : (errors.push(`OpenAI: ${openaiResult.reason}`), [])),
    ...(googleResult.status === 'fulfilled'
      ? googleResult.value
      : (errors.push(`Google: ${googleResult.reason}`), [])),
  ];

  const enrichmentMap: Map<string, OpenRouterEnrichment> =
    enrichmentResult.status === 'fulfilled'
      ? enrichmentResult.value
      : (errors.push(`OpenRouter enrichment: ${enrichmentResult.reason}`),
         new Map());

  // Merge: provider model + OpenRouter enrichment.
  const catalog: ModelCapability[] = rawModels.map((raw) => {
    const or = enrichmentMap.get(raw.id) ?? EMPTY_ENRICHMENT;
    return {
      id: raw.id,
      provider: raw.provider,
      displayName: raw.displayName,
      // Prefer the provider API's own context/output limits when available;
      // fall back to OpenRouter's values.
      contextLength: raw.contextLength ?? or.contextLength,
      maxOutputTokens: raw.maxOutputTokens ?? or.maxOutputTokens,
      promptPer1mUsd: or.promptPer1mUsd,
      completionPer1mUsd: or.completionPer1mUsd,
      vision: or.vision,
      pdf: or.pdf,
      thinking: or.thinking,
      structuredOutputs: or.structuredOutputs,
      toolCalling: or.toolCalling,
      promptCaching: or.promptCaching,
      knowledgeCutoff: or.knowledgeCutoff,
      source: raw.source,
    };
  });

  if (catalog.length === 0) {
    return { catalog: [], written: 0, refreshedAt: refreshedAtIso, errors };
  }

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

  return { catalog, written: rows.length, refreshedAt: refreshedAtIso, errors };
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
