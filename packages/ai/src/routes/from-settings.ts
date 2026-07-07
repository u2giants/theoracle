/**
 * DB-aware model resolution helpers.
 *
 * Production code should prefer resolveRouteCandidates() so it can try the
 * approved pool chain. The older single-route helpers remain as compatibility
 * wrappers and now return the first valid configured candidate only.
 */

import type { OracleDb } from '@oracle/db';
import { resolvePrimaryRouteFromSettings, resolveRouteCandidates } from './candidates';
import { AUXILIARY_MODEL_IDS } from './auxiliary';
import type { OracleModelRole, OracleModelRoute } from './types';
import type { ModelSlot } from './errors';

export { resolveRouteCandidates, resolvePrimaryRouteFromSettings };
export type { RouteCandidate, RouteCandidateResolution, SkippedRouteCandidate } from './candidates';

export async function resolveRouteFromSettings(
  db: OracleDb,
  role: OracleModelRole,
): Promise<OracleModelRoute | null> {
  return resolvePrimaryRouteFromSettings(db, role);
}

export async function resolveAuxiliaryRouteFromSettings(
  db: OracleDb,
  auxiliaryId: string,
): Promise<OracleModelRoute | null> {
  if (!AUXILIARY_MODEL_IDS.has(auxiliaryId)) {
    return null;
  }
  return resolvePrimaryRouteFromSettings(db, auxiliaryId as ModelSlot);
}
