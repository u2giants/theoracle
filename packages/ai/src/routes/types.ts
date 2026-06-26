/**
 * Oracle Model Route Types
 *
 * Per docs/oracle/01-model-roles-and-routes.md and docs/oracle/05-ai-retrofit-phase-packet.md.
 *
 * The Oracle exposes exactly 3 production roles. Runtime selection is driven by
 * admin settings and approved model pools; routes do not carry hidden fallback
 * targets.
 */

export type OracleModelRole = 'interview' | 'extraction' | 'synthesis';

export type OracleProvider = 'anthropic' | 'vertex' | 'google' | 'openai' | 'deepseek' | 'qwen';

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
 * How a Gemini-family model expresses reasoning control on the Google Developer
 * API (`generativelanguage`). This is a model-generation fact, not an adapter
 * decision, so it lives on the route (derived in the catalog/resolve layer):
 *
 *   - 'thinking_budget' — Gemini 2.x: `thinkingConfig.thinkingBudget` (integer
 *     token budget). The 2.x generation REJECTS the `thinkingLevel` enum with a
 *     400 "Thinking level is not supported for this model" (this 400 is what
 *     broke gemini-2.5-flash vision when any reasoning effort was set).
 *   - 'thinking_level' — Gemini 3.x+: `thinkingConfig.thinkingLevel` enum
 *     (LOW/MEDIUM/HIGH). The 3.x generation does not accept a raw thinkingBudget.
 *   - 'none' — model does not support client-controlled thinking; omit entirely.
 *
 * The Vertex adapter has always used thinkingBudget and is unaffected; this flag
 * exists for the Google Developer-API adapter, which previously hard-coded the
 * thinkingLevel enum for every model.
 */
export type GeminiThinkingStyle = 'thinking_budget' | 'thinking_level' | 'none';

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

  /**
   * For Gemini-family routes only: how this model's generation expresses
   * thinking control on the Google Developer API. Derived in the catalog/resolve
   * layer from the model id (a model-generation fact), consumed by
   * GoogleGeminiAdapter so the adapter never hard-codes a model name. Undefined
   * for non-Gemini providers (and harmless if present — only the Google adapter
   * reads it).
   */
  geminiThinkingStyle?: GeminiThinkingStyle;

  maxInputTokens?: number;
  maxOutputTokens?: number;

  /**
   * Reasoning effort to request from the model. Optional — when undefined,
   * the adapter omits all thinking/reasoning parameters and the model behaves
   * with its provider default. Set by resolveRouteFromSettings when the admin
   * has saved a per-stage effort preference.
   */
  reasoningEffort?: ReasoningEffort;

  enabled: boolean;
}
