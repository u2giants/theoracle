/**
 * Dynamic model route resolver.
 *
 * Handles two ID formats:
 *   1. Catalog routeId, e.g. "anthropic_claude_haiku_4_5_interview_primary"
 *   2. Provider/model id, e.g. "anthropic/claude-haiku-4-5"
 *
 * This resolver is synchronous and cannot read model_capabilities. Production
 * settings should use the DB-aware candidate resolver, which passes verified
 * capability flags into synthetic routes and enforces slot requirements.
 */

import type {
  GeminiThinkingStyle,
  OracleModelRole,
  OracleModelRoute,
  OracleProvider,
  ReasoningEffort,
} from './types';
import { ORACLE_MODEL_ROUTES, getOracleRoute } from './catalog';

/**
 * Derive how a Gemini-family model expresses thinking control, from its model id
 * generation. This is a model-generation FACT, derived here in the catalog/
 * resolve layer (alongside cacheStrategy/structuredOutputStrategy) so the
 * adapter stays free of hard-coded model names.
 *
 *   Gemini 3.x and newer → 'thinking_level' (thinkingConfig.thinkingLevel enum).
 *   Gemini 2.x           → 'thinking_budget' (thinkingConfig.thinkingBudget int);
 *                          2.x REJECTS the thinkingLevel enum with a 400.
 *   Non-Gemini / unknown → undefined (callers gate on supportsReasoningControls).
 *
 * Returns undefined for non-google/vertex providers so the field is only set
 * where it is meaningful.
 */
export function geminiThinkingStyleFor(
  provider: OracleProvider,
  modelId: string,
): GeminiThinkingStyle | undefined {
  if (provider !== 'google' && provider !== 'vertex') return undefined;
  // Extract the leading "gemini-<major>" generation number.
  const match = /gemini-(\d+)\b/i.exec(modelId);
  if (!match) return 'thinking_budget'; // safest default for unrecognized Gemini ids
  const major = Number(match[1]);
  return major >= 3 ? 'thinking_level' : 'thinking_budget';
}

const OR_PROVIDER_MAP: Record<string, OracleProvider> = {
  anthropic: 'anthropic',
  openai: 'openai',
  google: 'google',
  deepseek: 'deepseek',
  qwen: 'qwen',
};

function mapPrefix(prefix: string): OracleProvider | null {
  return (OR_PROVIDER_MAP[prefix] ?? null) as OracleProvider | null;
}

const SYNTHETIC_CAPS: Pick<
  OracleModelRoute,
  | 'supportsVision'
  | 'supportsStreaming'
  | 'supportsToolCalling'
  | 'supportsStructuredOutput'
  | 'supportsReasoningControls'
  | 'costTier'
  | 'enabled'
> = {
  supportsVision: true,
  supportsStreaming: true,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: false,
  costTier: 'balanced_default',
  enabled: true,
};

export type SyntheticRouteCaps = Partial<typeof SYNTHETIC_CAPS>;

function makeSyntheticRoute(
  providerModelId: string,
  provider: OracleProvider,
  modelId: string,
  role: OracleModelRole,
  caps?: SyntheticRouteCaps,
): OracleModelRoute {
  const cacheStrategy =
    provider === 'anthropic'
      ? 'anthropic_auto_plus_explicit'
      : provider === 'vertex'
        ? 'vertex_implicit_or_explicit_by_context_size'
        : provider === 'google'
          ? 'none'
          : provider === 'deepseek'
            ? 'deepseek_automatic_prefix'
            : provider === 'qwen'
              ? 'qwen_explicit_context_cache'
              : 'openai_automatic_with_cache_key';

  const structuredOutputStrategy =
    provider === 'vertex' || provider === 'google'
      ? 'native_json_schema'
      : provider === 'openai'
        ? 'native_json_schema'
        : 'tool_call';

  if (!caps) {
    console.warn(
      `[resolve] using synthetic route for "${providerModelId}" (role=${role}) without DB-verified capabilities. ` +
        `Production settings should use resolveRouteCandidates().`,
    );
  }

  return {
    routeId: providerModelId,
    role,
    tier: 'primary',
    internalPurpose: null,
    provider,
    modelId,
    displayName: providerModelId,
    recommendedUse: `Dynamically resolved from model pool (${providerModelId}).`,
    cacheStrategy,
    structuredOutputStrategy,
    geminiThinkingStyle: geminiThinkingStyleFor(provider, modelId),
    ...SYNTHETIC_CAPS,
    ...(caps ?? {}),
  };
}

export function providerModelIdForRoute(route: OracleModelRoute): string {
  return `${route.provider}/${route.modelId}`;
}

export function resolveModelRoute(
  modelIdOrRouteId: string,
  role: OracleModelRole,
  reasoningEffort?: ReasoningEffort,
  caps?: SyntheticRouteCaps,
): OracleModelRoute | null {
  let base: OracleModelRoute | null = null;

  const byRouteId = getOracleRoute(modelIdOrRouteId);
  if (byRouteId) {
    base = byRouteId;
  } else {
    const slashIdx = modelIdOrRouteId.indexOf('/');
    if (slashIdx === -1) return null;

    const prefix = modelIdOrRouteId.slice(0, slashIdx);
    const modelId = modelIdOrRouteId.slice(slashIdx + 1);
    const provider = mapPrefix(prefix);
    if (!provider) return null;

    const catalogMatch = Object.values(ORACLE_MODEL_ROUTES).find(
      (r) => r.provider === provider && r.modelId === modelId && r.role === role,
    );
    base = catalogMatch ?? makeSyntheticRoute(modelIdOrRouteId, provider, modelId, role, caps);
  }

  // Stamp the Gemini thinking-control style if this is a Gemini-family route and
  // a curated catalog entry didn't already pin it. Model-generation fact, so it
  // belongs here in the resolve layer, never in the adapter.
  if (base.geminiThinkingStyle === undefined) {
    const style = geminiThinkingStyleFor(base.provider, base.modelId);
    if (style) base = { ...base, geminiThinkingStyle: style };
  }

  return reasoningEffort ? { ...base, reasoningEffort } : base;
}
