/**
 * Default Oracle Model Routes
 *
 * Strictly one Primary route per role. There are NO "balanced alternates" or
 * multiple competing defaults. Per docs/oracle/05-ai-retrofit-phase-packet.md
 * Phase R1: "Remove any existing code referencing 'balanced alternate routes'
 * or multiple defaults."
 *
 * The admin selects a route by routeId via Admin → Settings. The settings rows
 * keyed `default_interview_route`, `default_extraction_route`, and
 * `default_synthesis_route` hold the current production selections. The values
 * below are the seeded defaults shipped with the codebase.
 */

import {
  anthropic_claude_haiku_4_5_interview_primary,
  vertex_gemini_2_5_flash_extraction_primary,
  anthropic_claude_3_5_sonnet_synthesis_primary,
} from './catalog';
import type { OracleModelRole } from './types';

export const DEFAULT_ORACLE_ROUTES: Record<OracleModelRole, string> = {
  interview: anthropic_claude_haiku_4_5_interview_primary.routeId,
  extraction: vertex_gemini_2_5_flash_extraction_primary.routeId,
  synthesis: anthropic_claude_3_5_sonnet_synthesis_primary.routeId,
};

/** Settings row keys for the three production route selections. */
export const ROUTE_SETTING_KEYS = {
  interview: 'default_interview_route',
  extraction: 'default_extraction_route',
  synthesis: 'default_synthesis_route',
} as const satisfies Record<OracleModelRole, string>;

/**
 * Settings key for the general-purpose / utility model — used for internal
 * one-off jobs that don't fit one of the three primary stages (e.g. taxonomy
 * cluster naming, future classifier fallbacks). Admin chooses any model from
 * the discovered catalog.
 */
export const GENERAL_PURPOSE_ROUTE_SETTING_KEY = 'default_general_purpose_route';

/**
 * Image-vision model — used by the document-ingestion worker to transcribe an
 * uploaded image to text before claim extraction runs over that text.
 *
 * Like the general-purpose key, this is NOT one of the three strict pipeline
 * roles (interview / extraction / synthesis), so it lives as a standalone
 * setting rather than extending OracleModelRole. The admin picker filters it to
 * vision-capable models from any provider; whatever model is saved is read at
 * runtime via resolveVisionRouteFromSettings() with no redeploy.
 *
 * DEFAULT_VISION_ROUTE_ID is the shipped fallback used only when the setting is
 * unset/unparseable — it points at the Gemini extraction route, which is
 * vision-capable and already credentialed in production.
 */
export const VISION_ROUTE_SETTING_KEY = 'default_vision_route';
export const VISION_REASONING_EFFORT_SETTING_KEY = 'default_vision_reasoning_effort';
export const VISION_MODEL_POOL_SETTING_KEY = 'model_pool_vision';
export const DEFAULT_VISION_ROUTE_ID = vertex_gemini_2_5_flash_extraction_primary.routeId;

/**
 * Reasoning effort settings keys, one per stage. Values are 'off' | 'low' |
 * 'medium' | 'high' (unified across providers; adapters translate).
 *
 * Each stage's effort setting is independent of the model setting — choosing
 * a non-reasoning model just means the saved effort is ignored at inference
 * time. The picker UI hides the dropdown when the selected model lacks
 * reasoning capability.
 */
export const REASONING_EFFORT_SETTING_KEYS = {
  interview: 'default_interview_reasoning_effort',
  extraction: 'default_extraction_reasoning_effort',
  synthesis: 'default_synthesis_reasoning_effort',
} as const satisfies Record<OracleModelRole, string>;

/** Legacy settings keys kept temporarily during R1 migration. Read-only. */
export const LEGACY_OPENROUTER_SETTING_KEYS = {
  interview: 'default_interview_model',
  extraction: 'default_extraction_model',
  synthesis: 'default_synthesis_model',
} as const satisfies Record<OracleModelRole, string>;

/**
 * Per-stage admin model pools. Each row is a JSON string[] of "provider/modelId"
 * IDs that should appear in that stage's dropdown on /admin/settings. Empty
 * array means "fall back to the 6 curated Oracle catalog routes".
 */
export const MODEL_POOL_SETTING_KEYS = {
  interview: 'model_pool_interview',
  extraction: 'model_pool_extraction',
  synthesis: 'model_pool_synthesis',
} as const satisfies Record<OracleModelRole, string>;
