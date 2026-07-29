/**
 * Read-only, credentialed GAP-2 gate. Requires an explicit production env pull:
 *   vercel env pull .env.gap2.live --environment=production --yes
 */
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { config as loadEnv } from 'dotenv';
import postgres from 'postgres';
import { drizzle } from 'drizzle-orm/postgres-js';
import { asc, eq } from 'drizzle-orm';
import { entities, settings } from '@oracle/db';
import * as schema from '@oracle/db/schema';
import {
  OracleAIClient,
  buildStandardAdapters,
  selectEntitiesWithConfiguredModel,
  type EntityPlannerModelAttempt,
} from '..';
import {
  buildRetrievalPlanFromQuery,
  buildRetrievalPlanWithModel,
  lookupRegistryEntityCandidates,
  type RegistryEntityCandidate,
} from '../retrieval-plan';

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..');
const envPath = resolve(repoRoot, '.env.gap2.live');
assert(existsSync(envPath), 'explicit .env.gap2.live is required; refusing ambient credentials');
loadEnv({ path: envPath, override: true, quiet: true });

const EXPECTED_PROJECT_REF = 'eqccjfbyrywsqkxxpjvg';
const databaseUrlValue = process.env.DATABASE_URL;
assert(databaseUrlValue, 'DATABASE_URL is required in .env.gap2.live');
const databaseUrl: string = databaseUrlValue;
assert(
  databaseUrl.includes(EXPECTED_PROJECT_REF),
  `refusing database target: expected Supabase project ${EXPECTED_PROJECT_REF}`,
);

const MAX_P95_LATENCY_MS = Number(process.env.GAP2_MAX_P95_LATENCY_MS ?? 2_500);
const MAX_AVERAGE_COST_USD = Number(process.env.GAP2_MAX_AVERAGE_COST_USD ?? 0.01);
const MIN_RECALL = Number(process.env.GAP2_MIN_RECALL ?? 0.8);
const MAX_WRONG_ENTITY_RATE = Number(process.env.GAP2_MAX_WRONG_ENTITY_RATE ?? 0.05);
const TARGET_TYPES = [
  'person', 'system', 'customer', 'licensor', 'vendor', 'sku_or_product_line',
  'factory', 'freight_provider', 'testing_lab', 'packaging_supplier',
  'service_provider', 'department', 'geography', 'process_stage', 'document_class',
];

function key(entity: { entityType: string; canonicalValue: string }): string {
  return `${entity.entityType}\u0000${entity.canonicalValue}`;
}

function safeSurface(entity: RegistryEntityCandidate): string | null {
  const values = [entity.displayLabel, ...(entity.aliases ?? [])];
  return values.find((value) =>
    typeof value === 'string' && value.trim().length >= 3 && !/[\r\n]/.test(value),
  )?.trim() ?? null;
}

function percentile95(values: number[]): number {
  return values.slice().sort((a, b) => a - b)[Math.ceil(values.length * 0.95) - 1] ?? 0;
}

async function main(): Promise<void> {
  assert(Number.isFinite(MAX_P95_LATENCY_MS) && MAX_P95_LATENCY_MS > 0);
  assert(Number.isFinite(MAX_AVERAGE_COST_USD) && MAX_AVERAGE_COST_USD >= 0);
  const sqlClient = postgres(databaseUrl, { max: 1, prepare: false });
  const db = drizzle(sqlClient, { schema });
  try {
    const [enabledRow] = await db.select({ value: settings.value })
      .from(settings).where(eq(settings.key, 'entity_aware_retrieval_enabled')).limit(1);
    assert(enabledRow?.value !== true, 'production entity-aware retrieval is already enabled; refusing gate');

    const representatives = new Map<string, RegistryEntityCandidate>();
    for (const entityType of TARGET_TYPES) {
      const typeRows = await db.select({
        id: entities.id,
        entityType: entities.entityType,
        canonicalValue: entities.canonicalValue,
        displayLabel: entities.displayLabel,
        aliases: entities.aliases,
      }).from(entities)
        .where(eq(entities.entityType, entityType))
        .orderBy(asc(entities.canonicalValue), asc(entities.id))
        .limit(50);
      const candidates = typeRows.map((row) => ({
        ...row,
        aliases: Array.isArray(row.aliases) ? row.aliases : [],
      }));
      const representative = candidates.find((candidate) => safeSurface(candidate));
      if (representative) representatives.set(entityType, representative);
    }
    assert(representatives.size >= 4, 'live registry needs at least four representative entity types');

    const selected = [...representatives.values()].slice(0, 6);
    const fixtures: Array<{ query: string; expected: RegistryEntityCandidate[] }> = [];
    for (let index = 0; index < selected.length; index += 2) {
      const pair = selected.slice(index, index + 2);
      const surfaces = pair.map(safeSurface);
      if (pair.length > 0 && surfaces.every(Boolean)) {
        fixtures.push({
          query: `Compare the current guidance for ${surfaces.join(' and ')}.`,
          expected: pair,
        });
      }
    }
    fixtures.push({ query: 'What does Unlisted Person Qzxv do in Mystery ERP Qzxv?', expected: [] });

    const client = new OracleAIClient({ adapters: buildStandardAdapters() });
    const attempts: EntityPlannerModelAttempt[] = [];
    let realFallbackCount = 0;
    let successfulFixtureCount = 0;
    let successfulExpectedCount = 0;
    let successfulRecalledCount = 0;
    let successfulWrongCount = 0;
    let successfulInventedCount = 0;

    for (const fixture of fixtures) {
      const expectedKeys = new Set(fixture.expected.map(key));
      const seenRegistryKeys = new Set<string>();
      let validAttempt = fixture.expected.length === 0;
      const plan = await buildRetrievalPlanWithModel(fixture.query, {
        lookupCandidates: async (query) => {
          const candidates = await lookupRegistryEntityCandidates(db, query);
          candidates.forEach((candidate) => seenRegistryKeys.add(key(candidate)));
          return candidates;
        },
        selectWithModel: (query, candidates) =>
          selectEntitiesWithConfiguredModel(db, client, query, candidates, {
            logAttempt: () => {},
            onAttempt: (attempt) => {
              attempts.push(attempt);
              validAttempt = attempt.validationOk;
            },
          }),
        onFallback: () => { realFallbackCount++; },
      });
      if (!validAttempt || (fixture.expected.length > 0 && plan.requiredEntities.length === 0)) continue;
      successfulFixtureCount++;
      successfulExpectedCount += expectedKeys.size;
      const actualKeys = new Set(plan.requiredEntities.map(key));
      successfulRecalledCount += [...expectedKeys].filter((value) => actualKeys.has(value)).length;
      successfulWrongCount += [...actualKeys].filter((value) => !expectedKeys.has(value)).length;
      successfulInventedCount += [...actualKeys].filter((value) => !seenRegistryKeys.has(value)).length;
    }

    const failedModelCalls = attempts.filter((attempt) => !attempt.validationOk).length +
      Math.max(0, realFallbackCount - attempts.filter((attempt) => !attempt.validationOk).length);
    const successfulAttempts = attempts.filter((attempt) => attempt.validationOk);
    const latencies = attempts.map((attempt) => attempt.latencyMs);
    const pricedAttempts = successfulAttempts.filter((attempt) => attempt.totalCostUsd != null);
    const costs = pricedAttempts.map((attempt) => attempt.totalCostUsd!);
    const inputTokens = successfulAttempts.reduce((sum, attempt) => sum + (attempt.inputTokens ?? 0), 0);
    const outputTokens = successfulAttempts.reduce((sum, attempt) => sum + (attempt.outputTokens ?? 0), 0);
    const baselineResolved = fixtures.reduce(
      (sum, fixture) => sum + buildRetrievalPlanFromQuery(fixture.query).requiredEntities.length,
      0,
    );
    const recall = successfulExpectedCount === 0 ? null : successfulRecalledCount / successfulExpectedCount;
    const wrongEntityRate =
      successfulRecalledCount + successfulWrongCount === 0
        ? null
        : successfulWrongCount / (successfulRecalledCount + successfulWrongCount);
    const p95LatencyMs = percentile95(latencies);
    const averageCostUsd = costs.length ? costs.reduce((a, b) => a + b, 0) / costs.length : null;
    const allSuccessfulCallsPriced =
      successfulAttempts.length > 0 && pricedAttempts.length === successfulAttempts.length;
    const defaultSafe =
      failedModelCalls === 0 &&
      realFallbackCount === 0 &&
      successfulFixtureCount === fixtures.length &&
      baselineResolved === 0 &&
      recall != null && recall >= MIN_RECALL &&
      wrongEntityRate != null && wrongEntityRate <= MAX_WRONG_ENTITY_RATE &&
      successfulInventedCount === 0 &&
      p95LatencyMs <= MAX_P95_LATENCY_MS &&
      allSuccessfulCallsPriced &&
      averageCostUsd != null && averageCostUsd <= MAX_AVERAGE_COST_USD;

    console.log(JSON.stringify({
      databaseProjectRefVerified: true,
      productionSettingEnabled: enabledRow?.value === true,
      provider: attempts[0]?.provider ?? null,
      modelId: attempts[0]?.modelId ?? null,
      fixtureCount: fixtures.length,
      successfulFixtureCount,
      modelCallCount: attempts.length,
      failedModelCalls,
      realFixtureFallbackCount: realFallbackCount,
      baselineResolved,
      successfulSelectionMetrics: {
        recall,
        wrongEntityRate,
        unresolvedNameInventedIdCount: successfulInventedCount,
      },
      offlineFixtureRemainsInventedIdAuthority: true,
      latencyMs: { values: latencies, p95: p95LatencyMs, limit: MAX_P95_LATENCY_MS },
      usage: {
        inputTokens,
        outputTokens,
        pricedSuccessfulCalls: pricedAttempts.length,
        averageCostUsd,
        averageCostLimitUsd: MAX_AVERAGE_COST_USD,
      },
      defaultSafe,
    }, null, 2));
    assert(defaultSafe, 'GAP-2 live gate did not pass; keep entity-aware retrieval disabled by default');
  } finally {
    await sqlClient.end({ timeout: 5 });
  }
}

await main();
