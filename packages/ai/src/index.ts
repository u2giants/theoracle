export { ORACLE_SYSTEM_PROMPT, ORACLE_SYSTEM_PROMPT_VERSION } from './prompts/oracle-system';
export {
  EXTRACTION_SYSTEM_PROMPT,
  EXTRACTION_PROMPT_VERSION,
  CLAIM_TYPES,
  CLAIM_KINDS,
  SEMANTIC_ROLES,
  ExtractionOutputSchema,
  ExtractionClaimSchema,
  ExtractionEvidenceSchema,
  ExtractionGapSchema,
  formatConversationSegment,
  type ClaimType,
  type ClaimKind,
  type SemanticRole,
  type ExtractionOutput,
  type ExtractionClaim,
  type FormattedMessage,
} from './prompts/extraction-system';
export {
  buildClaimCorrectionLessonPromptBlock,
  loadClaimCorrectionLessonPack,
  type ClaimCorrectionLessonPack,
  type ClaimCorrectionLessonRow,
} from './prompts/claim-correction-lessons';
export {
  WORKFLOW_READ_PROMPT_VERSION,
  WORKFLOW_READ_SYSTEM_PROMPT,
  WORKFLOW_NODE_TYPES,
  WORKFLOW_EDGE_TYPES,
  WORKFLOW_PATH_TYPES,
  SOURCE_STRUCTURE_SHAPES,
  WorkflowReadSchema,
  WorkflowReadNodeSchema,
  WorkflowReadEdgeSchema,
  WorkflowReadLaneSchema,
  WorkflowReadPathSchema,
  SourceStructureMapSchema,
  SourceStructureSegmentSchema,
  SourceStructureElementSchema,
  SourceStructureRelationSchema,
  type WorkflowReadOutput,
  type WorkflowReadNode,
  type WorkflowReadEdge,
  type WorkflowReadLane,
  type WorkflowReadPath,
  type SourceStructureShape,
  type SourceStructureMap,
  type SourceStructureSegment,
  type SourceStructureElement,
  type SourceStructureRelation,
} from './prompts/workflow-read';
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
  type OracleRunRouteMetadata,
  type OracleTextResult,
  type OracleObjectResult,
} from './client/types';
export { getContextCompiler, ContextCompiler, type CompileArgs } from './context/context-compiler';
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
export { releaseVertexExplicitCaches } from './providers/vertex-cache-cleanup';
export { MockProviderAdapter, type MockAdapterOptions } from './providers/mock-adapter';
export { AnthropicAdapter } from './providers/anthropic-adapter';
export { VertexGeminiAdapter } from './providers/vertex-gemini-adapter';
export { GoogleGeminiAdapter } from './providers/google-gemini-adapter';
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
  type InternalSubroutePurpose,
  // Catalog
  ORACLE_MODEL_ROUTES,
  PRODUCTION_ROUTE_IDS,
  INTERNAL_SUBROUTE_IDS,
  getOracleRoute,
  getRoutesForRole,
  // Defaults
  ROUTE_SETTING_KEYS,
  LEGACY_OPENROUTER_SETTING_KEYS,
  MODEL_POOL_SETTING_KEYS,
  MODEL_POOL_MACRO_SETTING_KEY,
  MODEL_POOL_VISION_SETTING_KEY,
  MODEL_POOL_WORKFLOW_READ_SETTING_KEY,
  MODEL_POOL_MODEL_MERGE_SETTING_KEY,
  MODEL_POOL_TRANSLATION_SETTING_KEY,
  MODEL_POOL_TRANSCRIPT_SUMMARY_SETTING_KEY,
  MODEL_POOL_GENERAL_SETTING_KEY,
  GENERAL_PURPOSE_ROUTE_SETTING_KEY,
  REASONING_EFFORT_SETTING_KEYS,
  VISION_ROUTE_SETTING_KEY,
  VISION_REASONING_EFFORT_SETTING_KEY,
  WORKFLOW_READ_ROUTE_SETTING_KEY,
  MODEL_MERGE_ROUTE_SETTING_KEY,
  TRANSLATION_ROUTE_SETTING_KEY,
  TRANSCRIPT_SUMMARY_ROUTE_SETTING_KEY,
  ENFORCE_MODEL_CAPABILITIES_SETTING_KEY,
  type ReasoningEffort,
  resolveRouteCandidates,
  resolvePrimaryRouteFromSettings,
  resolveRouteFromSettings,
  resolveAuxiliaryRouteFromSettings,
  providerModelIdForRoute,
  NoConfiguredModelError,
  ModelCapabilityError,
  AllCandidatesFailedError,
  type ModelSlot,
  type RouteCandidate,
  type RouteCandidateResolution,
  type SkippedRouteCandidate,
  logModelRunAttempts,
  logAllCandidatesFailedAttempts,
  // Auxiliary model registry (non-pipeline-role model selections)
  AUXILIARY_MODELS,
  AUXILIARY_MODEL_IDS,
  VISION_AUXILIARY_MODEL,
  WORKFLOW_READ_AUXILIARY_MODEL,
  MODEL_MERGE_AUXILIARY_MODEL,
  MACRO_AUXILIARY_MODEL,
  GENERAL_PURPOSE_AUXILIARY_MODEL,
  TRANSLATION_AUXILIARY_MODEL,
  TRANSCRIPT_SUMMARY_AUXILIARY_MODEL,
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
export {
  // Settings jsonb encoding helpers (Bug 4 — keep values single-encoded)
  normalizeSettingValue,
  isDoubleEncodedSettingValue,
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
