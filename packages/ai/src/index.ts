export { ORACLE_SYSTEM_PROMPT, ORACLE_SYSTEM_PROMPT_VERSION } from './prompts/oracle-system';
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
