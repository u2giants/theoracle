/**
 * Oracle Model Route Types
 *
 * Per docs/oracle/01-model-roles-and-routes.md and docs/oracle/05-ai-retrofit-phase-packet.md.
 *
 * The Oracle exposes exactly 3 production roles. Each role has exactly 1 Primary
 * Route and 1 Fallback Route. Internal subroutes (triage, warmth, schema repair)
 * live behind the OracleAIClient and are not exposed as admin-selectable defaults.
 *
 * Do not extend with "balanced alternates" or multiple competing defaults. The
 * strict 1-Primary / 1-Fallback rule is intentional.
 */

export type OracleModelRole = 'interview' | 'extraction' | 'synthesis';

export type OracleProvider = 'anthropic' | 'vertex' | 'openai' | 'deepseek' | 'qwen';

export type RouteTier =
  | 'primary'
  | 'fallback'
  | 'internal_subroute'
  | 'manual_only_frontier';

export type RouteCostTier =
  | 'cheap_default'
  | 'balanced_default'
  | 'expensive_escalation'
  | 'manual_only_frontier';

export type CacheStrategy =
  | 'anthropic_automatic'
  | 'anthropic_explicit_breakpoints'
  | 'anthropic_auto_plus_explicit'
  | 'vertex_implicit'
  | 'vertex_explicit_context_cache'
  | 'vertex_implicit_or_explicit_by_context_size'
  | 'openai_automatic_prefix'
  | 'openai_automatic_with_cache_key'
  | 'openai_automatic_with_retention'
  | 'deepseek_automatic_prefix'
  | 'qwen_explicit_context_cache'
  | 'qwen_none'
  | 'none';

export type StructuredOutputStrategy =
  | 'native_json_schema'
  | 'tool_call'
  | 'schema_prompt_plus_validator';

/**
 * Reasoning effort level — unified across providers. Each adapter translates
 * to its native form:
 *   Anthropic: thinking.budget_tokens (low=2048, medium=8192, high=24000; off omits the thinking param)
 *   OpenAI:    reasoning_effort string ('low'|'medium'|'high'; off omits the param)
 *   Vertex:    thinkingConfig.thinkingBudget (low=1024, medium=8192, high=24576; off=0)
 *   DeepSeek:  no-op (R1 reasoning is automatic and not client-controlled)
 *   Qwen:      enable_thinking + optional budget (low/med/high enable; off disables)
 */
export type ReasoningEffort = 'off' | 'low' | 'medium' | 'high';

export type FallbackCondition =
  | 'provider_outage'
  | 'provider_rate_limit'
  | 'schema_validation_failure'
  | 'quote_validation_failure'
  | 'admin_manual_override'
  | 'not_applicable';

/**
 * Internal subroute purpose tags. These are NOT admin-selectable; they are
 * dispatched by OracleAIClient based on runtime conditions (sentiment, schema
 * repair, cheap triage pre-filter, etc.).
 */
export type InternalSubroutePurpose =
  | 'message_triage'        // Cheap pre-filter scout
  | 'warmth_escalation'     // Emotional-sensitivity route for frustrated/defensive sentiment
  | 'schema_repair';        // One-shot fix for malformed JSON candidates

export interface OracleModelRoute {
  /** Stable identifier used in settings rows and observability. */
  routeId: string;

  /** Which of the 3 production roles this route serves, or null for internal subroutes. */
  role: OracleModelRole | null;

  /** Position in the strict 1-Primary / 1-Fallback / internal taxonomy. */
  tier: RouteTier;

  /**
   * For internal subroutes only. Describes why OracleAIClient may dispatch to
   * this route at runtime. Null for primary/fallback production routes.
   */
  internalPurpose: InternalSubroutePurpose | null;

  provider: OracleProvider;
  modelId: string;
  displayName: string;
  recommendedUse: string;

  costTier: RouteCostTier;
  cacheStrategy: CacheStrategy;
  structuredOutputStrategy: StructuredOutputStrategy;

  supportsVision: boolean;
  supportsStreaming: boolean;
  supportsToolCalling: boolean;
  supportsStructuredOutput: boolean;
  supportsReasoningControls: boolean;

  maxInputTokens?: number;
  maxOutputTokens?: number;

  /**
   * Reasoning effort to request from the model. Optional — when undefined,
   * the adapter omits all thinking/reasoning parameters and the model behaves
   * with its provider default. Set by resolveRouteFromSettings when the admin
   * has saved a per-stage effort preference.
   */
  reasoningEffort?: ReasoningEffort;

  /**
   * For a Primary route, the routeId of its Fallback. Always exactly one.
   * For a Fallback or internal route, null.
   */
  fallbackRouteId: string | null;

  /** Why this fallback may be triggered. Set on Primary routes only. */
  fallbackCondition: FallbackCondition;

  enabled: boolean;
}
