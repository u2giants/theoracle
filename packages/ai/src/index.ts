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
/**
 * @deprecated Use the OracleAIClient (R2) once available. OpenRouter is the
 * legacy AI path and must not be used by new production code. See
 * docs/oracle/05-ai-retrofit-phase-packet.md.
 */
export { getOpenRouter } from './openrouter';

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
  type OracleProviderAdapter,
  type GenerateObjectArgs,
  type GenerateTextArgs,
} from './providers/types';
export { MockProviderAdapter, type MockAdapterOptions } from './providers/mock-adapter';
export { AnthropicAdapter } from './providers/anthropic-adapter';
export { VertexGeminiAdapter } from './providers/vertex-gemini-adapter';
export { OpenAIAdapter } from './providers/openai-adapter';
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
} from './routes';
export { embedText, embedMany } from './embeddings';
export {
  getRecentMessages,
  getRelevantOpenGaps,
  searchApprovedClaims,
  getBrainSectionSnippets,
  getOpenGapsForChannel,
  DEFAULT_RECENT_MESSAGES,
  DEFAULT_GAPS_LIMIT,
  DEFAULT_CLAIMS_LIMIT,
  type RecentMessage,
  type RelevantClaim,
} from './retrieval';
