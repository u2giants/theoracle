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

// Embedding dimension — locked to OpenAI text-embedding-3-small per spec.
// Do NOT change without coordinated migration.
export const EMBEDDING_DIM = 1536 as const;

// Storage bucket names
export const STORAGE_BUCKET_COMPANY_DOCUMENTS = 'company_documents' as const;
