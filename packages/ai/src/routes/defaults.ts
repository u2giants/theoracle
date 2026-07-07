/**
 * Oracle model setting keys.
 *
 * Runtime model selection comes from settings rows and approved model pools.
 * This file intentionally does not export hard-coded model defaults.
 */

import type { OracleModelRole } from './types';

/** Settings row keys for the three production route selections. */
export const ROUTE_SETTING_KEYS = {
  interview: 'default_interview_route',
  extraction: 'default_extraction_route',
  synthesis: 'default_synthesis_route',
} as const satisfies Record<OracleModelRole, string>;

/**
 * Settings key for the general-purpose / utility model used for internal
 * one-off jobs that do not fit one of the three primary stages.
 */
export const GENERAL_PURPOSE_ROUTE_SETTING_KEY = 'default_general_purpose_route';

/** Image-vision model used by document ingestion to transcribe image uploads. */
export const VISION_ROUTE_SETTING_KEY = 'default_vision_route';
export const VISION_REASONING_EFFORT_SETTING_KEY = 'default_vision_reasoning_effort';

/** Translation model used by the bilingual claim layer. */
export const TRANSLATION_ROUTE_SETTING_KEY = 'default_translation_route';

/** Macro-first source workflow reader. Runs before extraction. */
export const WORKFLOW_READ_ROUTE_SETTING_KEY = 'default_workflow_read_route';

/** Macro-first business-model merge alignment. */
export const MODEL_MERGE_ROUTE_SETTING_KEY = 'default_model_merge_route';

/**
 * Macro-understanding model used by the source-outline, macro-relationship, and
 * source-coverage-audit workers. Distinct from the general-purpose slot on
 * purpose: these workers emit deep nested JSON and MUST use a model with real
 * (strict) structured-output support. See AGENT_ERROR_LOG.md for why Qwen
 * (json_object only) hard-failed here.
 */
export const MACRO_ROUTE_SETTING_KEY = 'default_macro_route';

/**
 * Reasoning effort settings keys, one per stage. Values are 'off' | 'low' |
 * 'medium' | 'high' (unified across providers; adapters translate).
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
 * IDs that are approved candidates for that stage. Empty is now a configuration
 * error at runtime.
 */
export const MODEL_POOL_SETTING_KEYS = {
  interview: 'model_pool_interview',
  extraction: 'model_pool_extraction',
  synthesis: 'model_pool_synthesis',
} as const satisfies Record<OracleModelRole, string>;

export const MODEL_POOL_VISION_SETTING_KEY = 'model_pool_vision';
export const MODEL_POOL_WORKFLOW_READ_SETTING_KEY = 'model_pool_workflow_read';
export const MODEL_POOL_MODEL_MERGE_SETTING_KEY = 'model_pool_model_merge';
export const MODEL_POOL_TRANSLATION_SETTING_KEY = 'model_pool_translation';
export const MODEL_POOL_GENERAL_SETTING_KEY = 'model_pool_general';

/**
 * Fallback pool for the macro slot. Unlike the other auxiliary slots (which are
 * single-pick), the macro layer gets an ordered approved chain so one malformed
 * structured-output response can't zero the whole holistic layer. Must be
 * non-empty and must contain the `default_macro_route` primary. See
 * AGENT_ERROR_LOG.md ERR-001.
 */
export const MODEL_POOL_MACRO_SETTING_KEY = 'model_pool_macro';

/** Emergency capability-enforcement override. Defaults to true when unset. */
export const ENFORCE_MODEL_CAPABILITIES_SETTING_KEY = 'enforce_model_capabilities';
