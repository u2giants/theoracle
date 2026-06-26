/**
 * Public barrel for the Oracle route catalog.
 *
 * Importers should use:
 *   import { getOracleRoute, ROUTE_SETTING_KEYS } from '@oracle/ai/routes';
 *
 * Do not import directly from ./catalog or ./defaults — go through this barrel.
 */

export * from './types';
export * from './catalog';
export * from './defaults';
export * from './auxiliary';
export { resolveModelRoute } from './resolve';
export { providerModelIdForRoute } from './resolve';
export * from './errors';
export * from './capability-requirements';
export * from './attempt-logging';
export {
  resolveRouteCandidates,
  resolvePrimaryRouteFromSettings,
  resolveRouteFromSettings,
  resolveAuxiliaryRouteFromSettings,
  type RouteCandidate,
  type RouteCandidateResolution,
  type SkippedRouteCandidate,
} from './from-settings';
