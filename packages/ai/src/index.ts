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
export { getOpenRouter } from './openrouter';
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
