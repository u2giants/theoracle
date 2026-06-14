/**
 * Auxiliary model registry.
 *
 * "Auxiliary models" are admin-selectable model choices that are NOT one of the
 * three strict pipeline roles (interview / extraction / synthesis). The pipeline
 * roles have rich structure — a strict primary+fallback catalog pair, stage
 * capability requirements, model pools, reasoning effort, and batch dispatch —
 * enforced by OracleModelRole. Auxiliary models are simpler: a single admin pick
 * of a model for a focused utility job, optionally filtered to one capability.
 *
 * Each entry here is the single source of truth consumed by:
 *   - the runtime resolver (resolveAuxiliaryRouteFromSettings)
 *   - the admin GUI picker (which model list to show + how to filter it)
 *   - the /api/admin/models endpoint (treat the id like a no-pool catalog scope)
 *
 * To add a new auxiliary model (e.g. an audio-transcription model, a cheap OCR
 * fallback), add ONE entry here and one presentation entry in the admin settings
 * page. No new branches in the resolver, picker, or models API are required.
 */

import {
  GENERAL_PURPOSE_ROUTE_SETTING_KEY,
  VISION_ROUTE_SETTING_KEY,
  VISION_REASONING_EFFORT_SETTING_KEY,
  DEFAULT_VISION_ROUTE_ID,
} from './defaults';

/**
 * A single model capability the picker can filter on. These names match the
 * capability columns on model_capabilities and the ModelInfo shape returned by
 * /api/admin/models, so the GUI can filter with `model[requiredCapability]`.
 */
export type AuxiliaryCapabilityFilter =
  | 'vision'
  | 'thinking'
  | 'tools'
  | 'structuredOutputs'
  | 'promptCaching'
  | 'outputCap'
  | 'pdf';

export interface AuxiliaryModelDef {
  /** Stable id — used as the GUI `?stage=` param and the resolver lookup key. */
  id: string;
  /** Settings row holding the chosen route/model id. */
  routeSettingKey: string;
  /** Optional settings row for reasoning effort. Omit when effort is irrelevant. */
  reasoningEffortSettingKey?: string;
  /**
   * Capability the picker filters the model list on. Omit for "any model"
   * (full catalog, like the general-purpose picker).
   */
  requiredCapability?: AuxiliaryCapabilityFilter;
  /** Shipped fallback route id used only when the setting is unset/unparseable. */
  defaultRouteId?: string;
  /** Short plain-text label. The GUI may render richer copy keyed by id. */
  label: string;
}

export const VISION_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'vision',
  routeSettingKey: VISION_ROUTE_SETTING_KEY,
  reasoningEffortSettingKey: VISION_REASONING_EFFORT_SETTING_KEY,
  requiredCapability: 'vision',
  defaultRouteId: DEFAULT_VISION_ROUTE_ID,
  label: 'Image vision model',
};

export const GENERAL_PURPOSE_AUXILIARY_MODEL: AuxiliaryModelDef = {
  id: 'general',
  routeSettingKey: GENERAL_PURPOSE_ROUTE_SETTING_KEY,
  // No capability filter (any model) and no shipped default — general-purpose is
  // an admin convenience with no runtime consumer yet.
  label: 'General-purpose model',
};

/** Order here is the order the auxiliary cards render in the admin settings page. */
export const AUXILIARY_MODELS: AuxiliaryModelDef[] = [
  VISION_AUXILIARY_MODEL,
  GENERAL_PURPOSE_AUXILIARY_MODEL,
];

export function getAuxiliaryModelDef(id: string): AuxiliaryModelDef | undefined {
  return AUXILIARY_MODELS.find((a) => a.id === id);
}

/** Set of auxiliary ids — convenient membership test for the models API. */
export const AUXILIARY_MODEL_IDS: ReadonlySet<string> = new Set(
  AUXILIARY_MODELS.map((a) => a.id),
);
