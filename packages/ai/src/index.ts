export { ORACLE_SYSTEM_PROMPT, ORACLE_SYSTEM_PROMPT_VERSION } from './prompts/oracle-system';
export {
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  CLAIM_TYPES,
  SEMANTIC_ROLES,
  ExtractionOutputSchema,
  ExtractionClaimSchema,
  ExtractionEvidenceSchema,
  ExtractionGapSchema,
  formatConversationSegment,
  type ClaimType,
  type SemanticRole,
  type ExtractionOutput,
  type ExtractionClaim,
  type FormattedMessage,
} from './prompts/extraction-system';
// OpenRouter has been removed from the codebase per R-providers / R11.0.
// Every production model call goes through OracleAIClient with direct
// Anthropic / Vertex / OpenAI adapters. See DECISIONS.md D6, D9.

// R2: OracleAIClient — the production gateway for all Oracle model calls.
export {
  OracleAIClient,
  getOracleAIClient,
  __resetOracleAIClientForTests,
  type OracleAIClientMode,
  type OracleAIClientOptions,
  type RunTextArgs,
  type RunObjectArgs,
  type RunObjectResult,
} from './client/oracle-ai-client';
export {
  type OracleTaskType,
  type PromptBlock,
  type PromptBlockKind,
  type OraclePromptPlan,
  type PromptPlanMetadata,
  type OutputContract,
  type OracleUsage,
  type OracleTextResult,
  type OracleObjectResult,
} from './client/types';
export {
  getContextCompiler,
  ContextCompiler,
  type CompileArgs,
} from './context/context-compiler';
export {
  hashContent,
  hashBlockSequence,
  estimateTokens,
  makeBlock,
  getStablePrefixBlocks,
  compareBlocksByKind,
} from './context/prompt-blocks';
export {
  ModelRouter,
  UnknownRouteError,
  NoAdapterRegisteredError,
  type ProviderAdapterMap,
  type ModelRouterOptions,
} from './routing/model-router';
export {
  ProviderAdapterNotImplementedError,
  supportsBatch,
  type OracleProviderAdapter,
  type GenerateObjectArgs,
  type GenerateTextArgs,
  // Batch API (D14)
  type BatchRequest,
  type BatchResultItem,
  type BatchStatus,
  type SubmitBatchArgs,
  type SubmitBatchResult,
  type RetrieveBatchArgs,
  type RetrieveBatchResult,
} from './providers/types';
// Provider-internal helper exposed for batch submitters that need to convert
// a Zod schema to JSON Schema before passing it to adapter.submitBatch.
export { zodToJsonSchema } from './providers/vertex-gemini-adapter';
export { MockProviderAdapter, type MockAdapterOptions } from './providers/mock-adapter';
export { AnthropicAdapter } from './providers/anthropic-adapter';
export { VertexGeminiAdapter } from './providers/vertex-gemini-adapter';
export { OpenAIAdapter } from './providers/openai-adapter';
export { DeepSeekAdapter } from './providers/deepseek-adapter';
export { QwenAdapter } from './providers/qwen-adapter';
export { buildStandardAdapters } from './client/standard-adapters';
export {
  normalizeUsage,
  type NormalizeArgs,
  type AnthropicUsageRaw,
  type VertexUsageRaw,
  type OpenAIUsageRaw,
} from './usage/usage-normalizer';
export {
  StructuredOutputValidator,
  getStructuredOutputValidator,
  type ValidationResult,
} from './validation/structured-output-validator';
export {
  EvidenceValidator,
  getEvidenceValidator,
  type QuoteValidationResult,
  type QuoteValidationVerdict,
  type ValidateQuoteArgs,
} from './validation/evidence-validator';

// R1: Curated Oracle route catalog. All new production code that needs to
// reference a model route must go through this barrel.
export {
  // Types
  type OracleModelRoute,
  type OracleModelRole,
  type OracleProvider,
  type RouteTier,
  type RouteCostTier,
  type CacheStrategy,
  type StructuredOutputStrategy,
  type FallbackCondition,
  type InternalSubroutePurpose,
  // Catalog
  ORACLE_MODEL_ROUTES,
  PRODUCTION_ROUTE_IDS,
  INTERNAL_SUBROUTE_IDS,
  getOracleRoute,
  getRoutesForRole,
  // Defaults
  DEFAULT_ORACLE_ROUTES,
  ROUTE_SETTING_KEYS,
  LEGACY_OPENROUTER_SETTING_KEYS,
  MODEL_POOL_SETTING_KEYS,
  GENERAL_PURPOSE_ROUTE_SETTING_KEY,
  REASONING_EFFORT_SETTING_KEYS,
  VISION_ROUTE_SETTING_KEY,
  VISION_REASONING_EFFORT_SETTING_KEY,
  VISION_MODEL_POOL_SETTING_KEY,
  DEFAULT_VISION_ROUTE_ID,
  TRANSLATION_ROUTE_SETTING_KEY,
  DEFAULT_TRANSLATION_ROUTE_ID,
  type ReasoningEffort,
  resolveRouteFromSettings,
  resolveAuxiliaryRouteFromSettings,
  // Auxiliary model registry (non-pipeline-role model selections)
  AUXILIARY_MODELS,
  AUXILIARY_MODEL_IDS,
  VISION_AUXILIARY_MODEL,
  GENERAL_PURPOSE_AUXILIARY_MODEL,
  TRANSLATION_AUXILIARY_MODEL,
  getAuxiliaryModelDef,
  type AuxiliaryModelDef,
  type AuxiliaryCapabilityFilter,
} from './routes';

// Model capability discovery — OpenRouter as single source, persisted to DB.
export {
  loadModelCatalog,
  refreshModelCatalog,
  getCatalogRefreshedAt,
  type ModelCapability,
  type ModelProvider,
  type ModelCapabilitySource,
  type RefreshModelCatalogResult,
} from './model-capabilities';

export {
  // Dynamic resolver (handles both catalog routeIds and OpenRouter model IDs)
  resolveModelRoute,
} from './routes';
export { embedText, embedMany } from './embeddings';
export {
  getRecentMessages,
  getRelevantOpenGaps,
  searchWithRetrievalPlan,
  getBrainSectionSnippets,
  getOpenGapsForChannel,
  DEFAULT_RECENT_MESSAGES,
  DEFAULT_GAPS_LIMIT,
  type RecentMessage,
  type RelevantClaim,
} from './retrieval';
export {
  buildRetrievalPlanFromQuery,
  buildDomainScopedPlan,
  buildGlobalRetrievalPlan,
  DEFAULT_TOP_K,
  type RetrievalPlan,
  type RetrievalPlanSearchScope,
} from './retrieval-plan';
