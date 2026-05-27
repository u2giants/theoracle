/**
 * resolveRouteFromSettings() — DRY helper for workers and the chat route.
 *
 * Reads both the role's model setting (default_${role}_route) AND the role's
 * reasoning-effort setting (default_${role}_reasoning_effort) in one query,
 * then hands the pair to resolveModelRoute() so the returned OracleModelRoute
 * already has `reasoningEffort` attached.
 *
 * Returns null when the model setting is unset or unparseable — callers should
 * fall back to a hardcoded route (typically the curated catalog primary for
 * the role).
 */

import { inArray } from 'drizzle-orm';
import type { OracleDb } from '@oracle/db';
import { settings } from '@oracle/db/schema';
import { ROUTE_SETTING_KEYS, REASONING_EFFORT_SETTING_KEYS } from './defaults';
import { resolveModelRoute } from './resolve';
import type { OracleModelRole, OracleModelRoute, ReasoningEffort } from './types';

function isReasoningEffort(v: unknown): v is ReasoningEffort {
  return v === 'off' || v === 'low' || v === 'medium' || v === 'high';
}

export async function resolveRouteFromSettings(
  db: OracleDb,
  role: OracleModelRole,
): Promise<OracleModelRoute | null> {
  const routeKey = ROUTE_SETTING_KEYS[role];
  const effortKey = REASONING_EFFORT_SETTING_KEYS[role];

  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(inArray(settings.key, [routeKey, effortKey]));

  const routeRow = rows.find((r) => r.key === routeKey);
  const effortRow = rows.find((r) => r.key === effortKey);

  const modelIdOrRouteId =
    typeof routeRow?.value === 'string' ? routeRow.value : null;
  if (!modelIdOrRouteId) return null;

  const effort: ReasoningEffort | undefined = isReasoningEffort(effortRow?.value)
    ? effortRow.value
    : undefined;

  return resolveModelRoute(modelIdOrRouteId, role, effort);
}
