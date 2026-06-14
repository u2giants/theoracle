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
import { getAuxiliaryModelDef } from './auxiliary';
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

/**
 * Resolve an admin-chosen auxiliary model (e.g. 'vision') from settings.
 *
 * Auxiliary models are not one of the 3 strict pipeline roles, so they're keyed
 * by an entry in the AUXILIARY_MODELS registry rather than by OracleModelRole.
 * This reads the entry's route + (optional) reasoning-effort settings keys and
 * resolves them the same way resolveRouteFromSettings() does for roles.
 *
 * Returns null when the registry id is unknown or the setting is
 * unset/unparseable — callers fall back to the entry's `defaultRouteId`.
 *
 * The value is resolved under the 'extraction' role for synthetic-route
 * labeling only (the role merely tags routes that aren't in the curated
 * catalog). The returned route's `provider` is what the caller uses to format
 * provider-native input (e.g. the image part for a vision model).
 */
export async function resolveAuxiliaryRouteFromSettings(
  db: OracleDb,
  auxiliaryId: string,
): Promise<OracleModelRoute | null> {
  const def = getAuxiliaryModelDef(auxiliaryId);
  if (!def) return null;

  const keys = def.reasoningEffortSettingKey
    ? [def.routeSettingKey, def.reasoningEffortSettingKey]
    : [def.routeSettingKey];

  const rows = await db
    .select({ key: settings.key, value: settings.value })
    .from(settings)
    .where(inArray(settings.key, keys));

  const routeRow = rows.find((r) => r.key === def.routeSettingKey);
  const effortRow = def.reasoningEffortSettingKey
    ? rows.find((r) => r.key === def.reasoningEffortSettingKey)
    : undefined;

  const modelIdOrRouteId =
    typeof routeRow?.value === 'string' ? routeRow.value : null;
  if (!modelIdOrRouteId) return null;

  const effort: ReasoningEffort | undefined = isReasoningEffort(effortRow?.value)
    ? effortRow.value
    : undefined;

  return resolveModelRoute(modelIdOrRouteId, 'extraction', effort);
}
