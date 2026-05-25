/**
 * Core OracleAIClient types.
 *
 * Source of truth for the shapes used by every adapter, the context compiler,
 * and the model router. Per docs/oracle/02-provider-native-ai-architecture.md.
 *
 * Dynamic content (current user message, current chunk, retry suffix) must
 * NEVER be placed before the stable cacheable prefix. PromptBlock.kind is the
 * primary signal that ContextCompiler uses to order blocks correctly.
 */

export type OracleTaskType =
  | 'interview_chat'
  | 'message_claim_extraction'
  | 'document_claim_extraction'
  | 'contradiction_detection'
  | 'brain_synthesis'
  | 'gap_generation'
  | 'admin_explanation'
  | 'validation_repair';

/**
 * The kind tag controls block ordering for provider-native cache friendliness.
 * Stable blocks must appear before semi-stable, which must appear before
 * retrieved, which must appear before dynamic.
 */
export type PromptBlockKind =
  | 'stable_system'
  | 'stable_schema'
  | 'stable_tool_definition'
  | 'semi_stable_domain_context'
  | 'retrieved_context'
  | 'dynamic_input'
  | 'output_contract';

export interface PromptBlock {
  /** Stable identifier, unique within a plan. */
  id: string;
  /** Human-readable label for observability. */
  label: string;
  kind: PromptBlockKind;
  content: string;
  /** Content hash (sha256 over content). Stable per content. */
  hash: string;
  tokenEstimate?: number;
  cacheEligible: boolean;
  /** Free-form reason this block was included; useful for observability. */
  reasonIncluded: string;
}

export interface OutputContract {
  name: string;
  schemaHash: string;
  mode: 'native_json_schema' | 'tool_call' | 'schema_prompt_plus_validator';
}

/**
 * A compiled prompt plan ready to be dispatched to a provider adapter.
 * Includes block-level data + opaque hashes for cache + observability.
 */
export interface OraclePromptPlan {
  taskType: OracleTaskType;
  routeId: string;
  promptVersion: string;
  schemaVersion?: string;
  blocks: PromptBlock[];
  outputContract?: OutputContract;
  metadata: PromptPlanMetadata;
}

export interface PromptPlanMetadata {
  /** Hash over every stable_* block in order. The cache key. */
  stablePrefixHash: string;
  semiStableContextHash?: string;
  retrievedContextHash?: string;
  dynamicInputHash: string;
  toolSchemaHash?: string;
  outputSchemaHash?: string;
  includedMessageIds?: string[];
  includedDocumentChunkIds?: string[];
  includedClaimIds?: string[];
  includedGapIds?: string[];
  includedContradictionIds?: string[];
  retrievalPlanId?: string;
  selectedDomains?: string[];
  selectedSourceTypes?: string[];
  selectedProcessStages?: string[];
  selectedEntityIds?: string[];
}

/**
 * Normalized usage shape — what UsageLogger writes to `model_runs`.
 * Each provider returns slightly different fields; UsageNormalizer maps
 * them all into this shape.
 */
export interface OracleUsage {
  inputTokens?: number;
  /** Tokens read from cache. Provider-native. */
  cachedInputTokens?: number;
  /** Tokens written to cache (Anthropic explicit, Vertex explicit creates). */
  cacheWriteTokens?: number;
  outputTokens?: number;
  /** Reasoning/thinking tokens where the provider exposes them. */
  reasoningTokens?: number;
  totalCostUsd?: string;
  latencyMs: number;
  providerRequestId?: string;
  /** Raw provider usage object preserved for audit and debug. */
  rawUsageJson?: unknown;
}

/** Result of a generateText call. */
export interface OracleTextResult {
  text: string;
  usage: OracleUsage;
  rawResponse: unknown;
}

/** Result of a generateObject call (structured output). */
export interface OracleObjectResult<T> {
  object: T;
  usage: OracleUsage;
  rawResponse: unknown;
}
