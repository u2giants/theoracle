/**
 * R5 + R5.5 — Extraction pipeline barrel.
 *
 * Workers and Trigger.dev tasks import from here. The promotion executor
 * is wired in R6; R5 + R5.5 export the pure pieces (validator + decision +
 * candidate hash + entity resolver + taxonomy validator) so the executor
 * is just SQL plumbing on top.
 */

// R5 — quote validator + source pointer check + promotion decision
export { validateQuote, validateSourcePointer } from './quote-validator';
export { normalize, methodForApplied } from './normalization';
export { computeCandidateHash, canonicalizeSummary } from './candidate-hash';
export {
  decidePromotion,
  PROMOTION_TRANSACTION_RUNBOOK,
  type CandidateSnapshot,
  type CandidateMetadata,
  type PromotionDecision,
  type EntityAssignment,
} from './promote-candidate';
export type {
  NormalizationPolicy,
  QuoteValidationVerdict,
  QuoteValidationResult,
  ValidationMethod,
  ValidateQuoteInput,
  ValidateSourcePointerInput,
  SourcePointerValidationResult,
  ValidationResultRecord,
} from './types';
export type { NormalizedString } from './normalization';
export {
  STRICT_VERBATIM_POLICY,
  PDF_OCR_NORMALIZATION_POLICY,
  MARKDOWN_DOCUMENT_NORMALIZATION_POLICY,
} from './types';

// R5.5 — taxonomy validation + entity resolution
export {
  resolveEntity,
  type RegistryEntity,
  type ResolveEntityInput,
  type ResolveEntityResult,
} from './entity-resolver';
export {
  validateTaxonomy,
  type ValidateTaxonomyInput,
  type TaxonomyValidationResult,
  type TaxonomyValidationFailure,
  type ProposedEntityReference,
  type ResolvedEntityAssignment,
  type EntityProposalToCreate,
} from './taxonomy-validator';

// R6 — circuit breaker, legacy domain mapping, and Drizzle executor
export {
  decideCircuitBreaker,
  DEFAULT_QUOTE_FAILURE_LIMIT,
  type CircuitBreakerInput,
  type CircuitBreakerDecision,
} from './circuit-breaker';
export { mapLegacyDomainToTopDomain, mapLegacyDomainsToTopDomains } from './domain-mapping';
export {
  executePromotion,
  AdvisoryLockBusyError,
  mapCandidateRowToSnapshotCandidate,
  mapEvidenceRowToValidatedEvidence,
  type ExecutePromotionInput,
  type ExecutePromotionResult,
  type ExtractionCandidateRow,
  type ExtractionCandidateEvidenceRow,
} from './promotion-executor';

// write-time fuzzy-dedup for entity_proposals
export { stageEntityProposal, type StageEntityProposalArgs } from './stage-entity-proposal';

// R7 — cache profitability + provider_cached_content lifecycle
export {
  decideCacheProfitability,
  estimateTokensForCache,
  EXPLICIT_CACHE_MEDIUM_SOURCE_TOKEN_THRESHOLD,
  EXPLICIT_CACHE_MEDIUM_SOURCE_REUSE_THRESHOLD,
  EXPLICIT_CACHE_LARGE_SOURCE_TOKEN_THRESHOLD,
  EXPLICIT_CACHE_LARGE_SOURCE_REUSE_THRESHOLD,
  type CacheProfitabilityInput,
  type CacheProfitabilityDecision,
} from './cache-profitability';
export {
  recordCacheCreation,
  recordCacheReuse,
  recordCacheTermination,
  type RecordCacheCreationInput,
  type RecordCacheTerminationInput,
  type CacheLifecycleHandle,
  type CacheTerminalStatus,
} from './cache-lifecycle';
