/**
 * Auxiliary model registry.
 *
 * Auxiliary models are admin-selectable model choices that are not one of the
 * three strict pipeline roles. They are explicit single-pick slots in this
 * pass: unset or unresolvable settings fail loudly instead of using a shipped
 * hidden default.
 */

import {
  GENERAL_PURPOSE_ROUTE_SETTING_KEY,
  VISION_ROUTE_SETTING_KEY,
  VISION_REASONING_EFFORT_SETTING_KEY,
  TRANSLATION_ROUTE_SETTING_KEY,
  MACRO_ROUTE_SETTING_KEY,
  MODEL_MERGE_ROUTE_SETTING_KEY,
  MODEL_POOL_GENERAL_SETTING_KEY,
  MODEL_POOL_MACRO_SETTING_KEY,
  MODEL_POOL_MODEL_MERGE_SETTING_KEY,
  MODEL_POOL_TRANSLATION_SETTING_KEY,
  MODEL_POOL_VISION_SETTING_KEY,
  MODEL_POOL_WORKFLOW_READ_SETTING_KEY,
  WORKFLOW_READ_ROUTE_SETTING_KEY,
} from './defaults';

/**
 * A single model capability the picker can filter on. These names match the
 * capability columns on model_capabilities and the ModelInfo shape returned by
 * /api/admin/models.
 */
export type AuxiliaryCapabilityFilter =
  | 'vision'
  | 'thinking'
  | 'tools'
  | 'structuredOutputs'
  | 'strictJsonSchema'
  | 'deepSchemaAccepted'
  | 'adapterParamsSafe'
  | 'promptCaching'
  | 'outputCap'
  | 'pdf';

export interface AuxiliaryModelDef {
  /** Stable id used as the GUI `?stage=` param and the resolver lookup key. */
  id: string;
  /** Settings row holding the chosen route/model id. */
  routeSettingKey: string;
  /** Optional ordered fallback pool. */
  poolSettingKey?: string;
  /** Optional settings row for reasoning effort. Omit when effort is irrelevant. */
  reasoningEffortSettingKey?: string;
  /** Capability the picker filters the model list on. Omit for any model. */
  requiredCapability?: AuxiliaryCapabilityFilter;
  /** Short plain-text label. The GUI may render richer copy keyed by id. */
  label: string;
}

export const VISION_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'vision',
  routeSettingKey: VISION_ROUTE_SETTING_KEY,
  poolSettingKey: MODEL_POOL_VISION_SETTING_KEY,
  reasoningEffortSettingKey: VISION_REASONING_EFFORT_SETTING_KEY,
  requiredCapability: 'vision',
  label: 'Vision transcription',
};

export const WORKFLOW_READ_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'workflow_read',
  routeSettingKey: WORKFLOW_READ_ROUTE_SETTING_KEY,
  poolSettingKey: MODEL_POOL_WORKFLOW_READ_SETTING_KEY,
  requiredCapability: 'deepSchemaAccepted',
  label: 'Workflow read',
};

export const MODEL_MERGE_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'model_merge',
  routeSettingKey: MODEL_MERGE_ROUTE_SETTING_KEY,
  poolSettingKey: MODEL_POOL_MODEL_MERGE_SETTING_KEY,
  requiredCapability: 'strictJsonSchema',
  label: 'Model merge',
};

export const GENERAL_PURPOSE_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'general',
  routeSettingKey: GENERAL_PURPOSE_ROUTE_SETTING_KEY,
  poolSettingKey: MODEL_POOL_GENERAL_SETTING_KEY,
  label: 'General utility',
};

export const TRANSLATION_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'translation',
  routeSettingKey: TRANSLATION_ROUTE_SETTING_KEY,
  poolSettingKey: MODEL_POOL_TRANSLATION_SETTING_KEY,
  label: 'Translation',
};

/**
 * Macro-understanding model. Drives the holistic layer: source outlines, macro
 * relationship extraction, and coverage audits. It is a SEPARATE slot from
 * extraction on purpose — extraction mines verbatim-quoted atomic claims, while
 * this model reasons over structure and emits deep nested JSON. The hard
 * capability filter is structured output; the job brief additionally warns that
 * STRICT json-schema (not just json_object) is required.
 */
export const MACRO_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'macro',
  routeSettingKey: MACRO_ROUTE_SETTING_KEY,
  poolSettingKey: MODEL_POOL_MACRO_SETTING_KEY,
  requiredCapability: 'deepSchemaAccepted',
  label: 'Macro understanding model',
};

/** Order here is the order the auxiliary cards render in the admin settings page. */
export const AUXILIARY_MODELS: AuxiliaryModelDef[] = [
  VISION_AUXILIARY_MODEL,
  WORKFLOW_READ_AUXILIARY_MODEL,
  MODEL_MERGE_AUXILIARY_MODEL,
  MACRO_AUXILIARY_MODEL,
  TRANSLATION_AUXILIARY_MODEL,
  GENERAL_PURPOSE_AUXILIARY_MODEL,
];

export function getAuxiliaryModelDef(id: string): AuxiliaryModelDef | undefined {
  return AUXILIARY_MODELS.find((a) => a.id === id);
}

/** Set of auxiliary ids, convenient for membership tests. */
export const AUXILIARY_MODEL_IDS: ReadonlySet<string> = new Set(
  AUXILIARY_MODELS.map((a) => a.id),
);
