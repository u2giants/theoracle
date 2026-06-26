/**
 * Oracle Model Route Catalog
 *
 * The complete curated list of production and internal routes.
 *
 * Production routes (admin-selectable historical catalog entries). Runtime
 * model advancement is driven by approved pools, not route-level fallback ids.
 *
 * Internal subroutes (NOT admin-selectable; dispatched by OracleAIClient):
 *   - message_triage     — cheap pre-filter scout
 *   - warmth_escalation  — emotional sensitivity
 *   - schema_repair      — one-shot JSON repair
 *
 * Source of truth for the role / route mapping:
 *   docs/oracle/01-model-roles-and-routes.md
 *   docs/oracle/05-ai-retrofit-phase-packet.md
 */

import type { OracleModelRoute } from './types';

// ============================================================================
// INTERVIEW ROLE
// ============================================================================

export const anthropic_claude_haiku_4_5_interview_primary: OracleModelRoute = {
  routeId: 'anthropic_claude_haiku_4_5_interview_primary',
  role: 'interview',
  tier: 'primary',
  internalPurpose: null,
  provider: 'anthropic',
  modelId: 'claude-haiku-4-5',
  displayName: 'Claude Haiku 4.5 (Interview)',
  recommendedUse:
    'Default conversational chat with employees. Cost-aware primary for routine direct mentions and tactful follow-ups.',
  costTier: 'cheap_default',
  cacheStrategy: 'anthropic_auto_plus_explicit',
  structuredOutputStrategy: 'tool_call',
  supportsVision: true,
  supportsStreaming: true,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: true,
  enabled: true,
};

export const openai_gpt4o_interview_fallback: OracleModelRoute = {
  routeId: 'openai_gpt4o_interview_fallback',
  role: 'interview',
  tier: 'fallback',
  internalPurpose: null,
  provider: 'openai',
  modelId: 'gpt-4o',
  displayName: 'GPT-4o (Interview Fallback)',
  recommendedUse:
    'Activated only when Anthropic experiences outage or rate limiting during a live session.',
  costTier: 'balanced_default',
  cacheStrategy: 'openai_automatic_with_cache_key',
  structuredOutputStrategy: 'tool_call',
  supportsVision: true,
  supportsStreaming: true,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: false,
  enabled: true,
};

// ============================================================================
// EXTRACTION ROLE
// ============================================================================

export const vertex_gemini_2_5_flash_extraction_primary: OracleModelRoute = {
  routeId: 'vertex_gemini_2_5_flash_extraction_primary',
  role: 'extraction',
  tier: 'primary',
  internalPurpose: null,
  provider: 'vertex',
  modelId: 'gemini-2.5-flash',
  displayName: 'Gemini 2.5 Flash (Extraction)',
  recommendedUse:
    'Default high-volume claim extraction from messages and document chunks. Uses Google explicit/implicit caching for repeated stable prefixes.',
  costTier: 'cheap_default',
  cacheStrategy: 'vertex_implicit_or_explicit_by_context_size',
  structuredOutputStrategy: 'native_json_schema',
  supportsVision: true,
  supportsStreaming: false,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: true,
  enabled: true,
};

export const openai_gpt4o_mini_extraction_fallback: OracleModelRoute = {
  routeId: 'openai_gpt4o_mini_extraction_fallback',
  role: 'extraction',
  tier: 'fallback',
  internalPurpose: null,
  provider: 'openai',
  modelId: 'gpt-4o-mini',
  displayName: 'GPT-4o mini (Extraction Fallback)',
  recommendedUse:
    'Activated if Vertex API fails or Gemini repeatedly fails Zod schema validation during extraction.',
  costTier: 'cheap_default',
  cacheStrategy: 'openai_automatic_with_cache_key',
  structuredOutputStrategy: 'native_json_schema',
  supportsVision: true,
  supportsStreaming: false,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: false,
  enabled: true,
};

// ============================================================================
// SYNTHESIS ROLE
// ============================================================================

export const anthropic_claude_3_5_sonnet_synthesis_primary: OracleModelRoute = {
  routeId: 'anthropic_claude_3_5_sonnet_synthesis_primary',
  role: 'synthesis',
  tier: 'primary',
  internalPurpose: null,
  provider: 'anthropic',
  modelId: 'claude-sonnet-4-6',
  displayName: 'Claude Sonnet 4.6 (Synthesis)',
  recommendedUse:
    'Brain section synthesis. Evidence fidelity, structured diffs, contradiction reasoning. Uses Anthropic explicit cache breakpoints on stable synthesis prompt/schema.',
  costTier: 'expensive_escalation',
  cacheStrategy: 'anthropic_explicit_breakpoints',
  structuredOutputStrategy: 'tool_call',
  supportsVision: true,
  supportsStreaming: true,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: false,
  enabled: true,
};

export const vertex_gemini_2_5_flash_synthesis_fallback: OracleModelRoute = {
  routeId: 'vertex_gemini_2_5_flash_synthesis_fallback',
  role: 'synthesis',
  tier: 'fallback',
  internalPurpose: null,
  provider: 'vertex',
  modelId: 'gemini-2.5-flash',
  displayName: 'Gemini 2.5 Flash (Synthesis Fallback)',
  recommendedUse:
    'Activated if primary fails to generate valid Markdown diffs mapping to approved claim IDs.',
  costTier: 'cheap_default',
  cacheStrategy: 'vertex_implicit',
  structuredOutputStrategy: 'native_json_schema',
  supportsVision: true,
  supportsStreaming: false,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: true,
  enabled: true,
};

// ============================================================================
// INTERNAL SUBROUTES — NOT admin-selectable
// ============================================================================

export const vertex_gemini_2_5_flash_lite_message_triage: OracleModelRoute = {
  routeId: 'vertex_gemini_2_5_flash_lite_message_triage',
  role: null,
  tier: 'internal_subroute',
  internalPurpose: 'message_triage',
  provider: 'vertex',
  modelId: 'gemini-2.5-flash-lite',
  displayName: 'Gemini 2.5 Flash-Lite (Triage)',
  recommendedUse:
    'Cheap pre-filter scout. Determines whether a message warrants full extraction before paying for the primary route.',
  costTier: 'cheap_default',
  cacheStrategy: 'vertex_implicit',
  structuredOutputStrategy: 'native_json_schema',
  supportsVision: false,
  supportsStreaming: false,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: true,
  enabled: true,
};

export const anthropic_claude_haiku_warmth_escalation: OracleModelRoute = {
  routeId: 'anthropic_claude_haiku_warmth_escalation',
  role: null,
  tier: 'internal_subroute',
  internalPurpose: 'warmth_escalation',
  provider: 'anthropic',
  modelId: 'claude-haiku-4-5',
  displayName: 'Claude Haiku 4.5 (Warmth)',
  recommendedUse:
    'Triggered when employee sentiment is frustrated/defensive/confused/worried or topic is personnel-conflict/blame/error-source/customer-issue. Same model, dedicated empathy prompt.',
  costTier: 'cheap_default',
  cacheStrategy: 'anthropic_auto_plus_explicit',
  structuredOutputStrategy: 'tool_call',
  supportsVision: true,
  supportsStreaming: true,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: true,
  enabled: true,
};

export const openai_gpt4o_mini_schema_repair: OracleModelRoute = {
  routeId: 'openai_gpt4o_mini_schema_repair',
  role: null,
  tier: 'internal_subroute',
  internalPurpose: 'schema_repair',
  provider: 'openai',
  modelId: 'gpt-4o-mini',
  displayName: 'GPT-4o mini (Schema Repair)',
  recommendedUse:
    'One-shot fix for malformed JSON candidates produced by another route. Strict structured-output mode.',
  costTier: 'cheap_default',
  cacheStrategy: 'openai_automatic_with_cache_key',
  structuredOutputStrategy: 'native_json_schema',
  supportsVision: false,
  supportsStreaming: false,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: false,
  enabled: true,
};

// ============================================================================
// MANUAL EVAL ROUTES — admin-triggered comparisons, not production defaults
// ============================================================================

export const google_gemini_3_1_flash_lite_extraction_eval: OracleModelRoute = {
  routeId: 'google_gemini_3_1_flash_lite_extraction_eval',
  role: 'extraction',
  tier: 'manual_only_frontier',
  internalPurpose: null,
  provider: 'google',
  modelId: 'gemini-3.1-flash-lite',
  displayName: 'Gemini 3.1 Flash Lite (Extraction Eval)',
  recommendedUse:
    'Manual A/B/C extraction comparison against approved human claim revisions. Not a production default route.',
  costTier: 'cheap_default',
  cacheStrategy: 'none',
  structuredOutputStrategy: 'native_json_schema',
  supportsVision: true,
  supportsStreaming: false,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: true,
  reasoningEffort: 'low',
  enabled: true,
};

export const qwen_3_7_max_extraction_eval: OracleModelRoute = {
  routeId: 'qwen_3_7_max_extraction_eval',
  role: 'extraction',
  tier: 'manual_only_frontier',
  internalPurpose: null,
  provider: 'qwen',
  modelId: 'qwen3.7-max',
  displayName: 'Qwen 3.7 Max (Extraction Eval)',
  recommendedUse:
    'Manual A/B/C extraction comparison against approved human claim revisions. Not a production default route.',
  costTier: 'balanced_default',
  cacheStrategy: 'qwen_explicit_context_cache',
  structuredOutputStrategy: 'tool_call',
  supportsVision: true,
  supportsStreaming: false,
  supportsToolCalling: true,
  supportsStructuredOutput: true,
  supportsReasoningControls: true,
  reasoningEffort: 'low',
  enabled: true,
};

// ============================================================================
// CATALOG
// ============================================================================

/**
 * Every curated route, keyed by routeId. This is the only place a routeId
 * lookup is allowed. Never accept an arbitrary model string as a route.
 */
export const ORACLE_MODEL_ROUTES: Record<string, OracleModelRoute> = {
  // Production
  [anthropic_claude_haiku_4_5_interview_primary.routeId]: anthropic_claude_haiku_4_5_interview_primary,
  [openai_gpt4o_interview_fallback.routeId]: openai_gpt4o_interview_fallback,
  [vertex_gemini_2_5_flash_extraction_primary.routeId]: vertex_gemini_2_5_flash_extraction_primary,
  [openai_gpt4o_mini_extraction_fallback.routeId]: openai_gpt4o_mini_extraction_fallback,
  [anthropic_claude_3_5_sonnet_synthesis_primary.routeId]: anthropic_claude_3_5_sonnet_synthesis_primary,
  [vertex_gemini_2_5_flash_synthesis_fallback.routeId]: vertex_gemini_2_5_flash_synthesis_fallback,

  // Internal subroutes
  [vertex_gemini_2_5_flash_lite_message_triage.routeId]: vertex_gemini_2_5_flash_lite_message_triage,
  [anthropic_claude_haiku_warmth_escalation.routeId]: anthropic_claude_haiku_warmth_escalation,
  [openai_gpt4o_mini_schema_repair.routeId]: openai_gpt4o_mini_schema_repair,

  // Manual eval routes
  [google_gemini_3_1_flash_lite_extraction_eval.routeId]: google_gemini_3_1_flash_lite_extraction_eval,
  [qwen_3_7_max_extraction_eval.routeId]: qwen_3_7_max_extraction_eval,
};

/** Production routes (admin-selectable). */
export const PRODUCTION_ROUTE_IDS = [
  anthropic_claude_haiku_4_5_interview_primary.routeId,
  openai_gpt4o_interview_fallback.routeId,
  vertex_gemini_2_5_flash_extraction_primary.routeId,
  openai_gpt4o_mini_extraction_fallback.routeId,
  anthropic_claude_3_5_sonnet_synthesis_primary.routeId,
  vertex_gemini_2_5_flash_synthesis_fallback.routeId,
] as const;

/** Internal subroutes (NOT admin-selectable). */
export const INTERNAL_SUBROUTE_IDS = [
  vertex_gemini_2_5_flash_lite_message_triage.routeId,
  anthropic_claude_haiku_warmth_escalation.routeId,
  openai_gpt4o_mini_schema_repair.routeId,
] as const;

/**
 * Lookup a route by routeId. Returns null if the routeId is not in the curated
 * catalog. Never returns an arbitrary string-based route.
 */
export function getOracleRoute(routeId: string): OracleModelRoute | null {
  return ORACLE_MODEL_ROUTES[routeId] ?? null;
}

/** All production routes for a given role. */
export function getRoutesForRole(role: 'interview' | 'extraction' | 'synthesis'): OracleModelRoute[] {
  return Object.values(ORACLE_MODEL_ROUTES).filter((r) => r.role === role);
}
