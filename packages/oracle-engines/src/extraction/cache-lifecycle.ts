/**
 * R7 — provider_cached_content lifecycle helpers.
 *
 * Records every explicit Vertex cache in `provider_cached_content` with
 * the required reuse policy fields at creation time, then drives the
 * lifecycle:
 *
 *   active  →  deleted (clean shutdown after final reuse)
 *            →  expired (TTL exceeded before final reuse)
 *            →  failed (deletion attempted and failed)
 *            →  orphaned (lifecycle could not be tracked)
 *
 * Per docs/oracle/02-provider-native-ai-architecture.md
 * "Explicit Cache Lifecycle Rule":
 *
 *   "Because explicit caches bill while they exist, workers must attach
 *    every cache to a short-lived reuse policy BEFORE creating it."
 *
 * R7 ships the bookkeeping helpers. R7 itself does NOT yet create real
 * Vertex caches — that requires the @google/genai SDK wired in. The
 * helpers are designed so the worker can call them around any cache
 * creator (real or stub) and the lifecycle audit trail is identical.
 */

import { and, eq, sql } from 'drizzle-orm';
import { providerCachedContent, type OracleDb } from '@oracle/db';

export interface RecordCacheCreationInput {
  db: OracleDb;
  provider: 'anthropic' | 'vertex' | 'openai';
  cacheKind: 'explicit' | 'implicit';
  /** sha256 of the cached source content. */
  sourceHash: string;
  sourceTokenEstimate?: number;
  sourceDescription?: string;
  /** Provider-side resource handle (Vertex cachedContent resource name). */
  providerResourceName?: string;
  /** Required: how many times the worker plans to use this cache. */
  expectedReuseCount: number;
  /** Identifier of the latest planned reuse step (for cleanup gating). */
  latestPlannedReuseStep?: string;
  /** Hard expiration — caches must NOT outlive this. */
  hardExpirationAt: Date;
  /** Worker/job responsible for cleanup. */
  cleanupOwner?: string;
  createdByJobRunId?: string;
}

export interface CacheLifecycleHandle {
  /** provider_cached_content.id. */
  id: string;
}

/**
 * Insert a `provider_cached_content` row with `status='active'`. Returns
 * the handle the worker uses to update the row later (bump reuse count,
 * mark deleted, etc.).
 */
export async function recordCacheCreation(input: RecordCacheCreationInput): Promise<CacheLifecycleHandle> {
  const [row] = await input.db
    .insert(providerCachedContent)
    .values({
      provider: input.provider,
      cacheKind: input.cacheKind,
      providerResourceName: input.providerResourceName ?? null,
      sourceHash: input.sourceHash,
      sourceTokenEstimate: input.sourceTokenEstimate ?? null,
      sourceDescription: input.sourceDescription ?? null,
      expectedReuseCount: input.expectedReuseCount,
      latestPlannedReuseStep: input.latestPlannedReuseStep ?? null,
      hardExpirationAt: input.hardExpirationAt,
      cleanupOwner: input.cleanupOwner ?? null,
      status: 'active',
      createdByJobRunId: input.createdByJobRunId ?? null,
    })
    .returning({ id: providerCachedContent.id });
  if (!row) throw new Error('provider_cached_content insert returned no row');
  return { id: row.id };
}

/** Increment actual_reuse_count after each successful use of the cache. */
export async function recordCacheReuse(db: OracleDb, handle: CacheLifecycleHandle): Promise<void> {
  await db
    .update(providerCachedContent)
    .set({
      actualReuseCount: sql`${providerCachedContent.actualReuseCount} + 1`,
      updatedAt: new Date(),
    })
    .where(eq(providerCachedContent.id, handle.id));
}

export type CacheTerminalStatus = 'deleted' | 'expired' | 'failed' | 'orphaned';

export interface RecordCacheTerminationInput {
  db: OracleDb;
  handle: CacheLifecycleHandle;
  status: CacheTerminalStatus;
  reason: string;
}

/**
 * Mark a cache deleted / expired / failed / orphaned. The CHECK constraint
 * on provider_cached_content enforces that `deleted_at IS NOT NULL` whenever
 * status is non-active.
 */
export async function recordCacheTermination(input: RecordCacheTerminationInput): Promise<void> {
  await input.db
    .update(providerCachedContent)
    .set({
      status: input.status,
      deletedAt: new Date(),
      statusReason: input.reason,
      updatedAt: new Date(),
    })
    .where(
      and(
        eq(providerCachedContent.id, input.handle.id),
        // Defensive: don't double-write a termination.
        eq(providerCachedContent.status, 'active'),
      ),
    );
}
