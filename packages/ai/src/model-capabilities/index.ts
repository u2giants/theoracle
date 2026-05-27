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
  errors: string[];       // non-fatal per-source errors surfaced to the admin UI
  unenrichedIds: string[]; // model IDs that had no OpenRouter enrichment match
}

/**
 * Look up OpenRouter enrichment for a provider model ID.
 *
 * Direct provider APIs and OpenRouter use different ID conventions:
 *   Anthropic API : claude-opus-4-7, claude-haiku-4-5-20251001
 *   OpenAI API    : gpt-4-0613, gpt-4-turbo-2024-04-09
 *   OpenRouter    : claude-opus-4.7,  claude-haiku-4.5,  gpt-4, gpt-4-turbo
 *
 * We try exact match first, then progressively normalize:
 *   1. Strip date / version suffixes:
 *        -YYYY-MM-DD (e.g. gpt-4-turbo-2024-04-09)
 *        -YYYYMMDD   (e.g. claude-opus-4-20250514)
 *        -\d{4}      (e.g. gpt-4-0613, gpt-3.5-turbo-0125)
 *   2. Convert dash-separated version numbers to dot-separated
 *      (claude-opus-4-7 → claude-opus-4.7, claude-3-5-sonnet → claude-3.5-sonnet)
 *
 * Returns { enrichment, matched } so the caller can track which IDs were found.
 */
function lookupEnrichment(
  map: Map<string, OpenRouterEnrichment>,
  modelId: string,
): { enrichment: OpenRouterEnrichment; matched: boolean } {
  const tryKey = (k: string) => map.get(k);

  // 1. Exact
  const exact = tryKey(modelId);
  if (exact) return { enrichment: exact, matched: true };

  // 2. Strip date / version suffixes
  const stripped = modelId
    .replace(/-\d{4}-\d{2}-\d{2}$/, '')
    .replace(/-\d{8}$/, '')
    .replace(/-\d{4}$/, '');
  if (stripped !== modelId) {
    const v = tryKey(stripped);
    if (v) return { enrichment: v, matched: true };
  }

  // 3. Dash → dot for version numbers (after stripping)
  const dotted = stripped.replace(/-(\d)-(\d)(?=-|$)/g, '-$1.$2');
  if (dotted !== stripped) {
    const v = tryKey(dotted);
    if (v) return { enrichment: v, matched: true };
  }

  // 4. Dash → dot on the original (covers cases where suffix-strip wasn't applicable)
  const origDotted = modelId.replace(/-(\d)-(\d)(?=-|$)/g, '-$1.$2');
  if (origDotted !== modelId && origDotted !== dotted) {
    const v = tryKey(origDotted);
    if (v) return { enrichment: v, matched: true };
  }

  return { enrichment: EMPTY_ENRICHMENT, matched: false };
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
  outputCap: false,
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
  const unenrichedIds: string[] = [];
  const catalog: ModelCapability[] = rawModels.map((raw) => {
    const { enrichment: or, matched } = lookupEnrichment(enrichmentMap, raw.id);
    if (!matched) unenrichedIds.push(raw.id);
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
      outputCap: or.outputCap,
      knowledgeCutoff: or.knowledgeCutoff,
      source: raw.source,
    };
  });

  if (catalog.length === 0) {
    return { catalog: [], written: 0, refreshedAt: refreshedAtIso, errors, unenrichedIds: [] };
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
    outputCap: c.outputCap,
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
        outputCap: sql`excluded.output_cap`,
        knowledgeCutoff: sql`excluded.knowledge_cutoff`,
        source: sql`excluded.source`,
        refreshedAt: sql`excluded.refreshed_at`,
      },
    });

  return { catalog, written: rows.length, refreshedAt: refreshedAtIso, errors, unenrichedIds };
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
    outputCap: r.outputCap,
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
