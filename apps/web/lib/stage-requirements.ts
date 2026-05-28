/**
 * Single source of truth for per-stage capability requirements.
 *
 * Both the model-pool page (where admins build the per-stage shortlists) and
 * the model-picker page (where admins pick the active model) import from here
 * so their requirement icons + filtering logic stay in lockstep.
 *
 * If you change a stage's requirements, both pages and the runtime filtering
 * update together.
 */

import { Braces, Eye, Maximize2, Sparkles, Type, Wrench, Zap, FileText } from 'lucide-react';

type IconComponent = React.ComponentType<{ className?: string }>;

// ---------------------------------------------------------------------------
// Capability metadata — matches the DB column names on model_capabilities.
// ---------------------------------------------------------------------------

export type CapKey =
  | 'vision'
  | 'thinking'
  | 'tools'
  | 'structuredOutputs'
  | 'promptCaching'
  | 'outputCap'
  | 'pdf';

export interface CapMeta {
  field: CapKey;
  short: string;
  long: string;
  icon: IconComponent;
  color: string;
}

export const CAPS: ReadonlyArray<CapMeta> = [
  { field: 'vision',            short: 'Vision',     long: 'Vision (image input)',                              icon: Eye,      color: 'text-sky-600 dark:text-sky-400' },
  { field: 'thinking',          short: 'Reasoning',  long: 'Reasoning / include_reasoning',                     icon: Sparkles, color: 'text-violet-600 dark:text-violet-400' },
  { field: 'tools',             short: 'Tools',      long: 'Tools / tool_choice',                               icon: Wrench,   color: 'text-emerald-600 dark:text-emerald-400' },
  { field: 'structuredOutputs', short: 'Structured', long: 'Structured outputs / response_format',              icon: Braces,   color: 'text-orange-600 dark:text-orange-400' },
  { field: 'promptCaching',     short: 'Caching',    long: 'Prompt caching',                                    icon: Zap,      color: 'text-amber-600 dark:text-amber-400' },
  { field: 'outputCap',         short: 'OutCap',     long: 'Output cap (max_completion_tokens or max_tokens)',  icon: Type,     color: 'text-teal-600 dark:text-teal-400' },
  { field: 'pdf',               short: 'PDF',        long: 'PDF input',                                         icon: FileText, color: 'text-slate-600 dark:text-slate-400' },
];

export const CAP_BY_FIELD = Object.fromEntries(CAPS.map((c) => [c.field, c])) as Record<CapKey, CapMeta>;

// ---------------------------------------------------------------------------
// Stages
// ---------------------------------------------------------------------------

export const STAGES = ['interview', 'extraction', 'synthesis'] as const;
export type Stage = (typeof STAGES)[number];

export const STAGE_LABELS: Record<Stage, string> = {
  interview: 'Interview',
  extraction: 'Extraction',
  synthesis: 'Synthesis',
};

// ---------------------------------------------------------------------------
// Stage requirements — generic over any object with the canonical cap fields.
// ---------------------------------------------------------------------------

/** Minimal shape needed to evaluate stage requirements against a model. */
export interface ReqEvaluable {
  contextLength: number | null;
  vision: boolean;
  thinking: boolean;
  tools: boolean;
  structuredOutputs: boolean;
  promptCaching: boolean;
  outputCap: boolean;
  pdf: boolean;
  // Pricing fields used by "hasEnrichment" check (nullable)
  promptPer1M?: number | null;
}

export interface StageRequirement {
  /** Predicate against the model entry. */
  check: (m: ReqEvaluable) => boolean;
  /** Header label / tooltip text. */
  label: string;
  /** Icon shown in the stage's requirement display. */
  icon: IconComponent;
  /** Tailwind text-color class for the icon. */
  color: string;
}

const CTX_REQ = (threshold: number): StageRequirement => ({
  check: (m) => m.contextLength != null && m.contextLength > threshold,
  label: `Context > ${threshold >= 1_000_000 ? `${threshold / 1_000_000}M` : `${threshold / 1_000}K`}`,
  icon: Maximize2,
  color: 'text-indigo-600 dark:text-indigo-400',
});

const CAP_REQ = (field: CapKey): StageRequirement => {
  const meta = CAP_BY_FIELD[field];
  return {
    check: (m) => !!m[field],
    label: meta.long,
    icon: meta.icon,
    color: meta.color,
  };
};

/**
 * Per-stage requirements. A model is "eligible" for a stage when all
 * predicates return true. Order matters only for the icon display.
 *
 *   Interview:  tools, structured, vision, ctx > 100K
 *   Extraction: structured, vision, ctx > 100K
 *   Synthesis:  ctx > 400K, structured, thinking (reasoning), outputCap
 *
 * `thinking` was moved from Extraction → Synthesis 2026-05-28: extraction
 * benefits more from speed and verbatim quote fidelity than from extended
 * reasoning; synthesis benefits from reasoning when consolidating large
 * approved-claim corpora into Brain sections.
 */
export const STAGE_REQUIREMENTS: Record<Stage, StageRequirement[]> = {
  interview: [
    CAP_REQ('tools'),
    CAP_REQ('structuredOutputs'),
    CAP_REQ('vision'),
    CTX_REQ(100_000),
  ],
  extraction: [
    CAP_REQ('structuredOutputs'),
    CAP_REQ('vision'),
    CTX_REQ(100_000),
  ],
  synthesis: [
    CTX_REQ(400_000),
    CAP_REQ('structuredOutputs'),
    CAP_REQ('thinking'),
    CAP_REQ('outputCap'),
  ],
};

// ---------------------------------------------------------------------------
// Helpers — used by both model-pool and model-picker pages
// ---------------------------------------------------------------------------

/** True when we have enrichment data for this model (context OR pricing populated). */
export function hasEnrichment(m: ReqEvaluable): boolean {
  return m.contextLength != null || m.promptPer1M != null;
}

/** Returns the missing requirements for a stage, or [] if eligible (or unknown). */
export function missingReqs(m: ReqEvaluable, stage: Stage): StageRequirement[] {
  if (!hasEnrichment(m)) return []; // unknown — allow
  return STAGE_REQUIREMENTS[stage].filter((r) => !r.check(m));
}

/** True iff every stage requirement is satisfied (or enrichment is unknown). */
export function meetsStageReq(m: ReqEvaluable, stage: Stage): boolean {
  return missingReqs(m, stage).length === 0;
}
