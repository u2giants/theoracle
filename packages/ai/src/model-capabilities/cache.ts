// In-memory cache for the discovered capability catalog.
//
// Vercel function instances live long enough that one discovery call serves
// many subsequent admin requests within the TTL window. Cold instances pay
// the cost once.
//
// Followup: persist the cache to the `model_capabilities` Postgres table so
// the discovery cost is amortised across instances and survives restarts.

import type { ModelCapability } from './types';

type CacheEntry = {
  catalog: ModelCapability[];
  providerErrors: string[];
  expiresAt: number;
};

const TTL_MS = 60 * 60 * 1_000; // 1 hour

let entry: CacheEntry | null = null;

export function getCachedCatalog(): CacheEntry | null {
  if (!entry) return null;
  if (Date.now() > entry.expiresAt) {
    entry = null;
    return null;
  }
  return entry;
}

export function setCachedCatalog(catalog: ModelCapability[], providerErrors: string[]): void {
  entry = { catalog, providerErrors, expiresAt: Date.now() + TTL_MS };
}

export function invalidateCachedCatalog(): void {
  entry = null;
}
