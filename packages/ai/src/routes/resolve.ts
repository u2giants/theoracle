/**
 * Dynamic model route resolver — P1 #1 (Settings overhaul).
 *
 * Handles two ID formats:
 *   1. Catalog routeId  — e.g. "anthropic_claude_haiku_4_5_interview_primary"
 *      → direct lookup in the curated catalog.
 *   2. OpenRouter model ID — e.g. "anthropic/claude-haiku-4-5"
 *      → find the best-matching catalog route for the requested role,
 *        or synthesise a minimal route so the OracleAIClient can dispatch.
 *
 * Workers and routes that previously called getOracleRoute() should call
 * resolveModelRoute() instead so that settings saved via the model-pool
 * picker continue to work even when the saved value is an OpenRouter model ID.
 */

import type { OracleModelRole, OracleModelRoute, OracleProvider } from './types';
import { ORACLE_MODEL_ROUTES } from './catalog';
import { getOracleRoute } from './catalog';

// ---------------------------------------------------------------------------
// Provider-prefix mapping (OpenRouter prefix → Oracle provider name).
// ---------------------------------------------------------------------------

const OR_PROVIDER_MAP: Record<string, OracleProvider> = {
  anthropic: 'anthropic',
  openai: 'openai',
  google: 'vertex',   // OpenRouter uses google/ for Gemini models
  // others (meta-llama, mistralai, etc.) are not supported — return null
};

/** Map an OpenRouter provider prefix to the internal OracleProvider enum value. */
function mapPrefix(prefix: string): OracleProvider | null {
  return (OR_PROVIDER_MAP[prefix] ?? null) as OracleProvider | null;
}

// ---------------------------------------------------------------------------
// Default capabilities for synthetic routes — conservative but broad.
// ---------------------------------------------------------------------------

const SYNTHETIC_CAPS: Pick<
  OracleModelRoute,
  | 'supportsVision'
  | 'supportsStreaming'
  | 'supportsToolCalling'
  | 'supportsStructuredOutput'
  | 'supportsReasoningControls'
  | 'costTier'
  | 'fallbackRouteId'
  | 'fallbackCondition'
  | 'enabled'
> = {
  supportsVision: true,
  supportsStreaming: true,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: false,
  costTier: 'balanced_default',
  fallbackRouteId: null,
  fallbackCondition: 'not_applicable',
  enabled: true,
};

/** Build a synthetic OracleModelRoute for a model not in the curated catalog. */
function makeSyntheticRoute(
  openRouterId: string,    // e.g. "anthropic/claude-haiku-4-5"
  provider: OracleProvider,
  modelId: string,         // e.g. "claude-haiku-4-5"
  role: OracleModelRole,
): OracleModelRoute {
  const cacheStrategy =
    provider === 'anthropic'
      ? 'anthropic_auto_plus_explicit'
      : provider === 'vertex'
      ? 'vertex_implicit_or_explicit_by_context_size'
      : 'openai_automatic_with_cache_key';

  const structuredOutputStrategy =
    provider === 'vertex' ? 'native_json_schema' : 'tool_call';

  return {
    routeId: openRouterId,  // use the OpenRouter ID as the routeId
    role,
    tier: 'primary',
    internalPurpose: null,
    provider,
    modelId,
    displayName: openRouterId,
    recommendedUse: `Dynamically resolved from model pool (${openRouterId}).`,
    cacheStrategy,
    structuredOutputStrategy,
    ...SYNTHETIC_CAPS,
  };
}

// ---------------------------------------------------------------------------
// Public resolver
// ---------------------------------------------------------------------------

/**
 * Resolve a model setting value to an OracleModelRoute.
 *
 * Accepts either:
 *   - A catalog routeId      ("anthropic_claude_haiku_4_5_interview_primary")
 *   - An OpenRouter model ID ("anthropic/claude-haiku-4-5")
 *
 * Returns null when the value cannot be resolved to a supported provider.
 * Callers should log a warning and fall back to the default route for the role.
 *
 * @param modelIdOrRouteId  The value stored in the settings table.
 * @param role              The model role being resolved (used when creating
 *                          synthetic routes and for catalog matching).
 */
export function resolveModelRoute(
  modelIdOrRouteId: string,
  role: OracleModelRole,
): OracleModelRoute | null {
  // ── 1. Try direct catalog routeId lookup ─────────────────────────────────
  const byRouteId = getOracleRoute(modelIdOrRouteId);
  if (byRouteId) return byRouteId;

  // ── 2. Parse as OpenRouter-style "provider/model" ─────────────────────────
  const slashIdx = modelIdOrRouteId.indexOf('/');
  if (slashIdx === -1) return null; // unknown format

  const prefix = modelIdOrRouteId.slice(0, slashIdx);
  const modelId = modelIdOrRouteId.slice(slashIdx + 1);
  const provider = mapPrefix(prefix);
  if (!provider) return null; // unsupported provider prefix

  // ── 3. Try catalog lookup by provider + modelId + role ───────────────────
  const catalogMatch = Object.values(ORACLE_MODEL_ROUTES).find(
    (r) => r.provider === provider && r.modelId === modelId && r.role === role,
  );
  if (catalogMatch) return catalogMatch;

  // ── 4. Synthesise a minimal route ─────────────────────────────────────────
  return makeSyntheticRoute(modelIdOrRouteId, provider, modelId, role);
}
