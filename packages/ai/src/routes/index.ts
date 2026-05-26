/**
 * Public barrel for the Oracle route catalog.
 *
 * Importers should use:
 *   import { getOracleRoute, DEFAULT_ORACLE_ROUTES, ROUTE_SETTING_KEYS } from '@oracle/ai/routes';
 *
 * Do not import directly from ./catalog or ./defaults — go through this barrel.
 */

export * from './types';
export * from './catalog';
export * from './defaults';
export { resolveModelRoute } from './resolve';
