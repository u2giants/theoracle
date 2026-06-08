// Single source of truth for knowledge domains across the monorepo.
// Mirrored in packages/db schema as `knowledge_domain` Postgres enum.
// Per spec Part 6.1.

export const KNOWLEDGE_DOMAINS = [
  'design',
  'licensing',
  'production',
  'sourcing',
  'logistics',
  'sales',
  'coldlion',
  'customers',
  'retail_compliance',
  'sampling',
  'costing',
  'artwork_files',
  'factory_communication',
  'quality_control',
  'approvals',
  'shipping_documents',
  'general',
] as const;

export type KnowledgeDomain = (typeof KNOWLEDGE_DOMAINS)[number];

// Org-unit departments. Distinct from KNOWLEDGE_DOMAINS (subject areas the AI
// tags content with). Departments are an org chart concept: who an employee
// reports through, who owns a clarification request, who is paged when a
// claim needs human input. Mirrored in packages/db schema as the `department`
// Postgres enum, with per-row metadata (display label, head) on the
// `departments` table.
//
// Adding/removing a value requires: (1) edit this const, (2) ALTER TYPE
// department ADD VALUE … in a new hand-written SQL migration, (3) INSERT the
// matching row into the `departments` metadata table. Renaming the display
// label or changing the head is a one-click admin action — no code change.
export const DEPARTMENTS = [
  'sales',
  'design',
  'licensing',
  'production',
  'logistics',
  'operations',
  'administrative',
  'management',
  'sourcing',
] as const;

export type Department = (typeof DEPARTMENTS)[number];

export const AUTH_PROVIDERS = [
  'microsoft',
  'google',
  'authentik',
  // Dev-only stub provider (Supabase email magic-link).
  // See DECISIONS.md D1.auth — replace with real provider wiring in production.
  'magic_link_dev',
] as const;

export type AuthProvider = (typeof AUTH_PROVIDERS)[number];

export const MESSAGE_ROLES = ['user', 'assistant', 'system'] as const;
export type MessageRole = (typeof MESSAGE_ROLES)[number];

export const CHANNEL_STATUSES = ['active', 'archived', 'locked'] as const;
export type ChannelStatus = (typeof CHANNEL_STATUSES)[number];

export const EXTRACTION_STATUSES = [
  'pending',
  'processing',
  'complete',
  'failed',
  'skipped',
] as const;
export type ExtractionStatus = (typeof EXTRACTION_STATUSES)[number];

export const CLAIM_STATUSES = [
  'pending_review',
  'approved',
  'rejected',
  'superseded',
] as const;
export type ClaimStatus = (typeof CLAIM_STATUSES)[number];

export const EVIDENCE_SOURCE_TYPES = [
  'message',
  'document_chunk',
  'external_system',
  'manual_admin',
] as const;
export type EvidenceSourceType = (typeof EVIDENCE_SOURCE_TYPES)[number];

export const GAP_STATUSES = [
  'open',
  'queued',
  'asked',
  'resolved',
  'stale',
  'rejected',
] as const;
export type GapStatus = (typeof GAP_STATUSES)[number];

export const GAP_PRIORITIES = ['low', 'medium', 'high', 'urgent'] as const;
export type GapPriority = (typeof GAP_PRIORITIES)[number];

export const CONTRADICTION_STATUSES = [
  'possible',
  'open',
  'resolved',
  'dismissed',
] as const;
export type ContradictionStatus = (typeof CONTRADICTION_STATUSES)[number];

export const DOCUMENT_STATUSES = [
  'pending_processing',
  'processing',
  'complete',
  'failed',
] as const;
export type DocumentStatus = (typeof DOCUMENT_STATUSES)[number];

export const ORACLE_INTERVENTION_TRIGGER_TYPES = [
  'direct_mention',
  'possible_contradiction',
  'lull_gap',
  'manual_admin',
  'system_test',
] as const;
export type OracleInterventionTriggerType =
  (typeof ORACLE_INTERVENTION_TRIGGER_TYPES)[number];

export const INTERVENTION_DECISIONS = [
  'no_intervention',
  'queued_gap',
  'live_interjection',
  'admin_review',
] as const;
export type InterventionDecision = (typeof INTERVENTION_DECISIONS)[number];

export const BRAIN_SECTION_REVIEW_STATUSES = [
  'draft',
  'approved',
  'needs_review',
  'rejected',
] as const;
export type BrainSectionReviewStatus =
  (typeof BRAIN_SECTION_REVIEW_STATUSES)[number];

// ===========================================================================
// R3.5 — Three-layer knowledge taxonomy
//
// Layer 1: top-level domains (text PK in `knowledge_top_domains`; this list is
// the seed source of truth).
// Layer 2: sub-topics (auto-discovered, NOT predeclared here).
// Layer 3: orthogonal entity tags (entity_type values below).
//
// Per docs/oracle/07-knowledge-segmentation.md.
// ===========================================================================

export const TOP_LEVEL_DOMAINS = [
  'customer_ops',
  'licensing_approvals',
  'product_development',
  'creative_design',
  'design_file_operations',
  'supply_chain',
  'it_systems',
  'production_lifecycle',
  'finance_pricing',
  'people_org',
  'vendor_management',
  'logistics_shipping',
  'import_compliance',
] as const;
export type TopLevelDomainId = (typeof TOP_LEVEL_DOMAINS)[number];

/**
 * Entity types in the canonical entity registry.
 *
 * - `licensor` is a first-class type distinct from `vendor` — Disney, Marvel,
 *   Star Wars, NBCUniversal, Warner Bros, etc. govern approvals and brand
 *   rules, not capacity or freight.
 * - Operating vendors are split into specific sub-types so factory questions
 *   don't surface freight material and vice versa. `vendor` itself is the
 *   residual bucket.
 */
export const ENTITY_TYPES = [
  'system',
  'customer',
  'licensor',
  'factory',
  'freight_provider',
  'testing_lab',
  'packaging_supplier',
  'service_provider',
  'vendor',
  'person',
  'sku_or_product_line',
  'process_stage',
  'department',
  'geography',
  'document_class',
] as const;
export type EntityType = (typeof ENTITY_TYPES)[number];

export const SUB_TOPIC_REVIEW_STATUSES = [
  'proposed',
  'approved',
  'merged',
  'split',
  'retired',
] as const;
export type SubTopicReviewStatus = (typeof SUB_TOPIC_REVIEW_STATUSES)[number];

export const TAXONOMY_PROPOSAL_TYPES = [
  'create_top_domain',
  'merge_top_domains',
  'split_top_domain',
  'create_sub_topic',
  'merge_sub_topics',
  'split_sub_topic',
  'reassign_claims',
  'retire_sub_topic',
] as const;
export type TaxonomyProposalType = (typeof TAXONOMY_PROPOSAL_TYPES)[number];

export const TAXONOMY_PROPOSAL_STATUSES = ['pending', 'approved', 'rejected'] as const;
export type TaxonomyProposalStatus = (typeof TAXONOMY_PROPOSAL_STATUSES)[number];

export const ENTITY_PROPOSAL_STATUSES = [
  'pending',
  'approved',
  'rejected',
  'merged_into_existing',
] as const;
export type EntityProposalStatus = (typeof ENTITY_PROPOSAL_STATUSES)[number];

export const ENTITY_PROPOSAL_SOURCE_TYPES = [
  'claim_candidate',
  'document_chunk',
  'message',
] as const;
export type EntityProposalSourceType = (typeof ENTITY_PROPOSAL_SOURCE_TYPES)[number];

/** Why a top-domain or sub-topic assignment row exists. */
export const ASSIGNMENT_REASONS = [
  'extraction',         // produced inline with the claim/message
  'ingestion',          // produced when a document was first ingested
  'reclassification',   // re-evaluation worker moved it
  'manual',             // admin set it directly
  'backfill',           // one-shot migration from legacy claim_domains
] as const;
export type AssignmentReason = (typeof ASSIGNMENT_REASONS)[number];

// ===========================================================================
// R4 — Candidate-before-claim staging pipeline statuses
//
// All claim extraction output flows through extraction_batches →
// extraction_candidates → extraction_candidate_evidence → deterministic
// validation → transactional promotion. These status / type values are
// the closed sets used at every step.
//
// Per docs/oracle/03-candidate-before-claim-validation.md.
// ===========================================================================

export const EXTRACTION_BATCH_TYPES = [
  'message_segment',
  'document_chunk',
  'document_page',
  'transcript_segment',
] as const;
export type ExtractionBatchType = (typeof EXTRACTION_BATCH_TYPES)[number];

export const EXTRACTION_BATCH_STATUSES = [
  'pending_model',
  'model_complete',
  'validation_complete',
  'promoted',
  'failed',
  'skipped',
  'failed_validation_loop',
] as const;
export type ExtractionBatchStatus = (typeof EXTRACTION_BATCH_STATUSES)[number];

export const EXTRACTION_CANDIDATE_STATUSES = [
  'pending_validation',
  'validation_failed',
  'failed_validation_loop',
  'validated',
  'duplicate',
  'promoted',
  'rejected',
  'rejected_sensitive',
  'quarantined_sensitive',
] as const;
export type ExtractionCandidateStatus = (typeof EXTRACTION_CANDIDATE_STATUSES)[number];

/**
 * Group-chat stance per docs/oracle/03... "Group-chat semantics". Distinguishes
 * stated/confirmed/challenged/refined/exception_introduced/ambiguity_revealed
 * so the synthesis step can preserve operational nuance instead of flattening
 * a conversation into isolated single-speaker facts.
 */
export const CANDIDATE_STANCES = [
  'stated',
  'confirmed',
  'challenged',
  'refined',
  'exception_introduced',
  'ambiguity_revealed',
] as const;
export type CandidateStance = (typeof CANDIDATE_STANCES)[number];

export const EVIDENCE_VALIDATION_STATUSES = [
  'pending',
  'exact_match',
  'normalized_match',
  'failed',
  'ambiguous',
  'failed_validation_loop',
] as const;
export type EvidenceValidationStatus = (typeof EVIDENCE_VALIDATION_STATUSES)[number];

export const VALIDATION_CHECK_NAMES = [
  'source_exists',
  'quote_exact_match',
  'quote_offsets_match',
  'source_type_valid',
  'not_duplicate',
  'domain_valid',
  'score_range_valid',
  'sensitivity_gate',
  'promotion_transaction',
  'duplicate_promotion_lock',
  'validation_loop_circuit_breaker',
] as const;
export type ValidationCheckName = (typeof VALIDATION_CHECK_NAMES)[number];

export const VALIDATION_CHECK_STATUSES = [
  'pass',
  'fail',
  'warning',
  'skipped',
  'circuit_breaker',
] as const;
export type ValidationCheckStatus = (typeof VALIDATION_CHECK_STATUSES)[number];

// Embedding dimension — locked to OpenAI text-embedding-3-small per spec.
// Do NOT change without coordinated migration.
export const EMBEDDING_DIM = 1536 as const;

// Storage bucket names
export const STORAGE_BUCKET_COMPANY_DOCUMENTS = 'company_documents' as const;
