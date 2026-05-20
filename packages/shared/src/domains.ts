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

// Embedding dimension — locked to OpenAI text-embedding-3-small per spec.
// Do NOT change without coordinated migration.
export const EMBEDDING_DIM = 1536 as const;

// Storage bucket names
export const STORAGE_BUCKET_COMPANY_DOCUMENTS = 'company_documents' as const;
