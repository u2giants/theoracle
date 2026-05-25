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
