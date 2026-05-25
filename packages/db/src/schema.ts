// Master Drizzle schema for The Oracle — spec Part 6.
// IMPORTANT: do not change column names without coordinating raw SQL migrations
// in `migrations/sql/*` and the RLS policies that reference them.

import {
  boolean,
  index,
  integer,
  jsonb,
  numeric,
  pgEnum,
  pgTable,
  primaryKey,
  text,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
  customType,
} from 'drizzle-orm/pg-core';
import { KNOWLEDGE_DOMAINS, EMBEDDING_DIM } from '@oracle/shared';

// ---------------------------------------------------------------------------
// pgvector column type
// drizzle-orm's `vector` import path varies between versions. Define a small
// custom type so we don't depend on the internal pgvector subpath that some
// versions don't ship.
// ---------------------------------------------------------------------------
const vector = customType<{
  data: number[];
  driverData: string;
  config: { dimensions: number };
}>({
  dataType(config) {
    return `vector(${config?.dimensions ?? EMBEDDING_DIM})`;
  },
  toDriver(value: number[]): string {
    return `[${value.join(',')}]`;
  },
  fromDriver(value: string): number[] {
    // pg returns vectors as strings like "[0.1,0.2,...]"
    if (!value) return [];
    const stripped = value.replace(/^\[|\]$/g, '');
    if (!stripped) return [];
    return stripped.split(',').map((n) => Number(n));
  },
});

// ---------------------------------------------------------------------------
// Enums — spec 6.1
// ---------------------------------------------------------------------------

export const knowledgeDomainEnum = pgEnum('knowledge_domain', KNOWLEDGE_DOMAINS);

// auth_provider includes the dev-only `magic_link_dev` stub (see DECISIONS.md).
// Production providers per spec 4.1 are microsoft / google / authentik.
export const authProviderEnum = pgEnum('auth_provider', [
  'microsoft',
  'google',
  'authentik',
  'magic_link_dev',
]);

export const messageRoleEnum = pgEnum('message_role', ['user', 'assistant', 'system']);

export const channelStatusEnum = pgEnum('channel_status', [
  'active',
  'archived',
  'locked',
]);

export const extractionStatusEnum = pgEnum('extraction_status', [
  'pending',
  'processing',
  'complete',
  'failed',
  'skipped',
]);

export const claimStatusEnum = pgEnum('claim_status', [
  'pending_review',
  'approved',
  'rejected',
  'superseded',
]);

export const evidenceSourceTypeEnum = pgEnum('evidence_source_type', [
  'message',
  'document_chunk',
  'external_system',
  'manual_admin',
]);

export const gapStatusEnum = pgEnum('gap_status', [
  'open',
  'queued',
  'asked',
  'resolved',
  'stale',
  'rejected',
]);

export const gapPriorityEnum = pgEnum('gap_priority', [
  'low',
  'medium',
  'high',
  'urgent',
]);

export const contradictionStatusEnum = pgEnum('contradiction_status', [
  'possible',
  'open',
  'resolved',
  'dismissed',
]);

export const documentStatusEnum = pgEnum('document_status', [
  'pending_processing',
  'processing',
  'complete',
  'failed',
]);

export const oracleInterventionTriggerTypeEnum = pgEnum(
  'oracle_intervention_trigger_type',
  ['direct_mention', 'possible_contradiction', 'lull_gap', 'manual_admin', 'system_test'],
);

export const interventionDecisionEnum = pgEnum('intervention_decision', [
  'no_intervention',
  'queued_gap',
  'live_interjection',
  'admin_review',
]);

export const brainSectionReviewStatusEnum = pgEnum('brain_section_review_status', [
  'draft',
  'approved',
  'needs_review',
  'rejected',
]);

// ---------------------------------------------------------------------------
// 6.2 Settings
// ---------------------------------------------------------------------------

export const settings = pgTable('settings', {
  key: varchar('key', { length: 100 }).primaryKey(),
  value: jsonb('value').notNull(),
  description: text('description'),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

// ---------------------------------------------------------------------------
// 6.3 Employees and Invites
// ---------------------------------------------------------------------------

export const employees = pgTable('employees', {
  id: uuid('id').primaryKey().defaultRandom(),

  // Primary contact email. NOT the auth identity — see employee_identities for
  // the (provider, auth_user_id) mappings. Kept here for display, admin contact,
  // and first-login bootstrap (matching a freshly-arrived provider email to an
  // employee row that has not yet been linked to any identity).
  email: varchar('email', { length: 320 }).notNull().unique(),

  // DEPRECATED — kept nullable for transitional reads from old code paths.
  // Authoritative source is now employee_identities. Will be removed once all
  // consumers are migrated. See DECISIONS.md D2.multi-identity.
  authUserId: uuid('auth_user_id').unique(),
  authProvider: authProviderEnum('auth_provider'),
  authProviderSubject: varchar('auth_provider_subject', { length: 255 }),

  name: varchar('name', { length: 255 }).notNull(),
  role: varchar('role', { length: 255 }).notNull(),
  department: varchar('department', { length: 255 }).notNull(),
  isAdmin: boolean('is_admin').default(false).notNull(),

  disabledAt: timestamp('disabled_at'),
  // "Most recent login from any identity" — denormalized convenience column.
  // Per-identity last_login_at lives on employee_identities.
  lastLoginAt: timestamp('last_login_at'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

// One employee can have many identities — a Google account, a Microsoft 365
// account, future Authentik, etc. The linker looks up by
// (auth_provider, auth_user_id) here; if no identity matches, it falls back to
// matching the verified provider email against employees.email and creates a
// new identity row attached to that employee.
export const employeeIdentities = pgTable(
  'employee_identities',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    employeeId: uuid('employee_id')
      .references(() => employees.id, { onDelete: 'cascade' })
      .notNull(),
    authProvider: authProviderEnum('auth_provider').notNull(),
    // Supabase auth.users.id — globally unique across providers in Supabase.
    authUserId: uuid('auth_user_id').notNull().unique(),
    // Stable provider-side user id (Google `sub`, Microsoft `oid`). May be null
    // for the magic-link stub where there is no provider subject.
    authProviderSubject: varchar('auth_provider_subject', { length: 255 }),
    // Verified email captured AT LINK TIME. We denormalize because provider
    // emails can drift; this is the email value we accepted at first link.
    email: varchar('email', { length: 320 }).notNull(),
    linkedAt: timestamp('linked_at').defaultNow().notNull(),
    lastLoginAt: timestamp('last_login_at'),
  },
  (t) => ({
    providerEmployeeIdx: index('employee_identities_provider_employee_idx').on(
      t.authProvider,
      t.employeeId,
    ),
    employeeIdx: index('employee_identities_employee_idx').on(t.employeeId),
    emailIdx: index('employee_identities_email_idx').on(t.email),
    // One employee can have at most one identity per provider — prevents
    // accidentally double-linking the same Google account twice, for example.
    providerEmployeeUnique: uniqueIndex('employee_identities_provider_employee_unique').on(
      t.authProvider,
      t.employeeId,
    ),
  }),
);

export const employeeInvites = pgTable('employee_invites', {
  id: uuid('id').primaryKey().defaultRandom(),
  employeeId: uuid('employee_id')
    .references(() => employees.id)
    .notNull(),
  tokenHash: varchar('token_hash', { length: 255 }).notNull().unique(),
  tokenLastFour: varchar('token_last_four', { length: 4 }).notNull(),
  expiresAt: timestamp('expires_at').notNull(),
  usedAt: timestamp('used_at'),
  revokedAt: timestamp('revoked_at'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

// ---------------------------------------------------------------------------
// 6.4 Channels, Documents, Messages, Attachments
// ---------------------------------------------------------------------------

export const channels = pgTable('channels', {
  id: uuid('id').primaryKey().defaultRandom(),
  name: varchar('name', { length: 255 }),
  isGroupChat: boolean('is_group_chat').default(false).notNull(),
  status: channelStatusEnum('status').default('active').notNull(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

export const channelParticipants = pgTable(
  'channel_participants',
  {
    channelId: uuid('channel_id')
      .references(() => channels.id)
      .notNull(),
    employeeId: uuid('employee_id')
      .references(() => employees.id)
      .notNull(),
    joinedAt: timestamp('joined_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.channelId, t.employeeId] }),
    employeeIdx: index('channel_participants_employee_idx').on(t.employeeId),
  }),
);

export const documents = pgTable(
  'documents',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    uploaderId: uuid('uploader_id')
      .references(() => employees.id)
      .notNull(),
    fileName: varchar('file_name', { length: 255 }).notNull(),
    storageBucket: varchar('storage_bucket', { length: 100 }).notNull(),
    storagePath: varchar('storage_path', { length: 500 }).notNull(),
    fileType: varchar('file_type', { length: 50 }).notNull(),
    status: documentStatusEnum('status').default('pending_processing').notNull(),
    processingError: text('processing_error'),
    processedAt: timestamp('processed_at'),
    parserVersion: varchar('parser_version', { length: 50 }),
    ocrConfidence: integer('ocr_confidence'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    storageUnique: uniqueIndex('documents_storage_unique').on(
      t.storageBucket,
      t.storagePath,
    ),
    uploaderIdx: index('documents_uploader_idx').on(t.uploaderId),
  }),
);

export const documentChunks = pgTable(
  'document_chunks',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    documentId: uuid('document_id')
      .references(() => documents.id)
      .notNull(),
    chunkIndex: integer('chunk_index').notNull(),
    pageNumber: integer('page_number'),
    sheetName: varchar('sheet_name', { length: 255 }),
    rowStart: integer('row_start'),
    rowEnd: integer('row_end'),
    rawText: text('raw_text').notNull(),
    tokenCount: integer('token_count'),
    contentHash: varchar('content_hash', { length: 255 }),
    embedding: vector('embedding', { dimensions: EMBEDDING_DIM }),
    metadataJson: jsonb('metadata_json'),
  },
  (t) => ({
    documentChunkUnique: uniqueIndex('document_chunks_document_chunk_unique').on(
      t.documentId,
      t.chunkIndex,
    ),
    documentIdx: index('document_chunks_document_idx').on(t.documentId),
  }),
);

export const messages = pgTable(
  'messages',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    channelId: uuid('channel_id')
      .references(() => channels.id)
      .notNull(),
    employeeId: uuid('employee_id').references(() => employees.id),
    role: messageRoleEnum('role').notNull(),
    content: text('content').notNull(),

    clientMessageId: varchar('client_message_id', { length: 255 }),
    replyToMessageId: uuid('reply_to_message_id'),
    metadataJson: jsonb('metadata_json'),

    extractionStatus: extractionStatusEnum('extraction_status')
      .default('pending')
      .notNull(),
    extractedAt: timestamp('extracted_at'),
    extractionError: text('extraction_error'),

    editedAt: timestamp('edited_at'),
    deletedAt: timestamp('deleted_at'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    channelCreatedIdx: index('messages_channel_created_idx').on(
      t.channelId,
      t.createdAt,
    ),
    extractionIdx: index('messages_extraction_idx').on(
      t.extractionStatus,
      t.role,
      t.createdAt,
    ),
    clientMessageUnique: uniqueIndex('messages_channel_client_message_unique').on(
      t.channelId,
      t.clientMessageId,
    ),
  }),
);

export const messageAttachments = pgTable('message_attachments', {
  id: uuid('id').primaryKey().defaultRandom(),
  messageId: uuid('message_id')
    .references(() => messages.id)
    .notNull(),
  documentId: uuid('document_id')
    .references(() => documents.id)
    .notNull(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

// ---------------------------------------------------------------------------
// 6.5 Model Runs and Job Runs
// ---------------------------------------------------------------------------

export const modelRuns = pgTable(
  'model_runs',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    taskType: varchar('task_type', { length: 100 }).notNull(),
    model: varchar('model', { length: 100 }).notNull(),
    provider: varchar('provider', { length: 100 }).notNull(),
    promptVersion: varchar('prompt_version', { length: 50 }),
    inputHash: varchar('input_hash', { length: 255 }),
    inputTokens: integer('input_tokens'),
    outputTokens: integer('output_tokens'),
    costUsd: numeric('cost_usd', { precision: 12, scale: 6 }),
    latencyMs: integer('latency_ms'),
    success: boolean('success').notNull(),
    error: text('error'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    taskCreatedIdx: index('model_runs_task_created_idx').on(t.taskType, t.createdAt),
  }),
);

export const jobRuns = pgTable(
  'job_runs',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    triggerRunId: varchar('trigger_run_id', { length: 255 }).notNull(),
    jobType: varchar('job_type', { length: 100 }).notNull(),
    status: varchar('status', { length: 50 }).notNull(),
    startedAt: timestamp('started_at').notNull(),
    finishedAt: timestamp('finished_at'),
    inputJson: jsonb('input_json'),
    outputJson: jsonb('output_json'),
    error: text('error'),
    retryCount: integer('retry_count').default(0).notNull(),
  },
  (t) => ({
    jobStatusStartedIdx: index('job_runs_type_status_started_idx').on(
      t.jobType,
      t.status,
      t.startedAt,
    ),
  }),
);

// ---------------------------------------------------------------------------
// 6.6 Claims, Evidence, Brain, Gaps, Contradictions
// Claims intentionally have no direct employeeId — join through claim_evidence.
// ---------------------------------------------------------------------------

export const claims = pgTable(
  'claims',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    claimType: varchar('claim_type', { length: 100 }).notNull(),
    summary: text('summary').notNull(),
    impactScore: integer('impact_score').notNull(),
    confidenceScore: integer('confidence_score').notNull(),
    status: claimStatusEnum('status').notNull(),
    embedding: vector('embedding', { dimensions: EMBEDDING_DIM }),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    statusCreatedIdx: index('claims_status_created_idx').on(t.status, t.createdAt),
    impactIdx: index('claims_impact_idx').on(t.impactScore),
    confidenceIdx: index('claims_confidence_idx').on(t.confidenceScore),
  }),
);

export const claimDomains = pgTable(
  'claim_domains',
  {
    claimId: uuid('claim_id')
      .references(() => claims.id)
      .notNull(),
    domain: knowledgeDomainEnum('domain').notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.claimId, t.domain] }),
    domainIdx: index('claim_domains_domain_idx').on(t.domain),
  }),
);

export const claimEvidence = pgTable(
  'claim_evidence',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    claimId: uuid('claim_id')
      .references(() => claims.id)
      .notNull(),

    sourceType: evidenceSourceTypeEnum('source_type').notNull(),
    sourceMessageId: uuid('source_message_id').references(() => messages.id),
    sourceDocumentChunkId: uuid('source_document_chunk_id').references(
      () => documentChunks.id,
    ),
    sourceExternalRecordId: varchar('source_external_record_id', { length: 255 }),

    assertedByEmployeeId: uuid('asserted_by_employee_id').references(
      () => employees.id,
    ),
    uploadedByEmployeeId: uuid('uploaded_by_employee_id').references(
      () => employees.id,
    ),
    createdByEmployeeId: uuid('created_by_employee_id').references(
      () => employees.id,
    ),

    exactQuote: text('exact_quote').notNull(),
    charStart: integer('char_start'),
    charEnd: integer('char_end'),
    pageNumber: integer('page_number'),
    confidence: integer('confidence'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    claimIdx: index('claim_evidence_claim_idx').on(t.claimId),
    messageIdx: index('claim_evidence_message_idx').on(t.sourceMessageId),
    documentChunkIdx: index('claim_evidence_document_chunk_idx').on(
      t.sourceDocumentChunkId,
    ),
  }),
);

export const brainSections = pgTable('brain_sections', {
  id: varchar('id', { length: 255 }).primaryKey(),
  knowledgeDomain: knowledgeDomainEnum('knowledge_domain').notNull(),
  relatedDomains: jsonb('related_domains'),
  title: varchar('title', { length: 255 }).notNull(),
  category: varchar('category', { length: 100 }).notNull(),

  // Soft reference to brain_section_versions.id.
  // Must be set via two-step transactional insert (spec 6.7).
  currentVersionId: uuid('current_version_id'),

  createdAt: timestamp('created_at').defaultNow().notNull(),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

export const brainSectionVersions = pgTable(
  'brain_section_versions',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    sectionId: varchar('section_id', { length: 255 })
      .references(() => brainSections.id)
      .notNull(),
    versionNumber: integer('version_number').notNull(),
    markdown: text('markdown').notNull(),
    structuredContent: jsonb('structured_content'),
    changeSummary: text('change_summary').notNull(),
    createdByModelRunId: uuid('created_by_model_run_id').references(() => modelRuns.id),

    reviewStatus: brainSectionReviewStatusEnum('review_status')
      .default('draft')
      .notNull(),
    reviewedByEmployeeId: uuid('reviewed_by_employee_id').references(
      () => employees.id,
    ),
    reviewedAt: timestamp('reviewed_at'),

    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    sectionVersionUnique: uniqueIndex(
      'brain_section_versions_section_version_unique',
    ).on(t.sectionId, t.versionNumber),
    sectionVersionIdx: index('brain_section_versions_section_version_idx').on(
      t.sectionId,
      t.versionNumber,
    ),
  }),
);

export const sectionClaims = pgTable(
  'section_claims',
  {
    sectionId: varchar('section_id', { length: 255 })
      .references(() => brainSections.id)
      .notNull(),
    claimId: uuid('claim_id')
      .references(() => claims.id)
      .notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.sectionId, t.claimId] }),
    claimIdx: index('section_claims_claim_idx').on(t.claimId),
  }),
);

export const contradictions = pgTable(
  'contradictions',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    claimAId: uuid('claim_a_id')
      .references(() => claims.id)
      .notNull(),
    claimBId: uuid('claim_b_id')
      .references(() => claims.id)
      .notNull(),
    description: text('description').notNull(),
    severity: varchar('severity', { length: 50 }).notNull(),
    status: contradictionStatusEnum('status').default('possible').notNull(),
    detectionConfidence: integer('detection_confidence'),
    retrievedClaimIds: jsonb('retrieved_claim_ids'),
    newMessageId: uuid('new_message_id').references(() => messages.id),
    interjectionDecision: interventionDecisionEnum('interjection_decision'),
    suggestedQuestion: text('suggested_question'),
    assignedGapId: uuid('assigned_gap_id'),
    resolvedByClaimId: uuid('resolved_by_claim_id').references(() => claims.id),
    createdByModelRunId: uuid('created_by_model_run_id').references(() => modelRuns.id),
    createdAt: timestamp('created_at').defaultNow().notNull(),
    resolvedAt: timestamp('resolved_at'),
  },
  (t) => ({
    statusSeverityIdx: index('contradictions_status_severity_idx').on(
      t.status,
      t.severity,
    ),
  }),
);

export const gaps = pgTable(
  'gaps',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    gapType: varchar('gap_type', { length: 50 }).notNull(),
    sectionId: varchar('section_id', { length: 255 }).references(
      () => brainSections.id,
    ),
    relatedClaimIds: jsonb('related_claim_ids'),
    relatedContradictionId: uuid('related_contradiction_id').references(
      () => contradictions.id,
    ),
    questionToAsk: text('question_to_ask').notNull(),
    whyItMatters: text('why_it_matters').notNull(),
    targetEmployeeId: uuid('target_employee_id').references(() => employees.id),
    targetDepartment: varchar('target_department', { length: 255 }),
    priority: gapPriorityEnum('priority').notNull(),
    status: gapStatusEnum('status').default('open').notNull(),
    askedInMessageId: uuid('asked_in_message_id').references(() => messages.id),
    resolvedByClaimId: uuid('resolved_by_claim_id').references(() => claims.id),
    createdByModelRunId: uuid('created_by_model_run_id').references(() => modelRuns.id),
    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at').defaultNow().notNull(),
    resolvedAt: timestamp('resolved_at'),
  },
  (t) => ({
    statusPriorityIdx: index('gaps_status_priority_idx').on(t.status, t.priority),
    targetStatusIdx: index('gaps_target_status_idx').on(t.targetEmployeeId, t.status),
  }),
);

export const oracleInterventions = pgTable('oracle_interventions', {
  id: uuid('id').primaryKey().defaultRandom(),
  channelId: uuid('channel_id')
    .references(() => channels.id)
    .notNull(),
  triggerType: oracleInterventionTriggerTypeEnum('trigger_type').notNull(),
  relatedGapId: uuid('related_gap_id').references(() => gaps.id),
  relatedContradictionId: uuid('related_contradiction_id').references(
    () => contradictions.id,
  ),
  relatedMessageId: uuid('related_message_id').references(() => messages.id),
  interjectionMessageId: uuid('interjection_message_id').references(() => messages.id),
  confidence: integer('confidence'),
  impactScore: integer('impact_score'),
  wasLiveInterjection: boolean('was_live_interjection').notNull(),
  reason: text('reason'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

// ---------------------------------------------------------------------------
// R3 — AI observability: context packs, usage details, provider cache tracking
//
// Source of truth for the shapes:
//   docs/oracle/02-provider-native-ai-architecture.md
//   docs/oracle/04-context-packs-observability.md
//   docs/oracle/05-ai-retrofit-phase-packet.md Phase R3
//
// Design notes:
// - `model_runs` (above) keeps its existing minimal shape so legacy callers
//   are not broken. The new R3 tables hang off `model_runs.id`.
// - `oracle_context_packs` may be created *before* the model run (so the
//   context-pack ID can be threaded through the OracleAIClient call); the FK
//   to `model_runs` is therefore nullable.
// - `model_run_usage_details` is a 1:1 child of `model_runs` carrying the
//   richer OracleUsage shape (cached/write/reasoning tokens, raw provider
//   usage JSON, fallback tracking).
// - `provider_cached_content` tracks explicit Vertex caches (and any future
//   provider-managed caches) so the cache-lifecycle teardown rule from
//   `02-provider-native-ai-architecture.md` can be enforced and audited.
// ---------------------------------------------------------------------------

export const oracleContextPacks = pgTable(
  'oracle_context_packs',
  {
    id: uuid('id').primaryKey().defaultRandom(),

    // Created-before-or-after-the-run: nullable until the model run is logged.
    modelRunId: uuid('model_run_id').references(() => modelRuns.id),

    taskType: varchar('task_type', { length: 100 }).notNull(),
    routeId: varchar('route_id', { length: 100 }).notNull(),
    promptVersion: varchar('prompt_version', { length: 50 }),
    schemaVersion: varchar('schema_version', { length: 50 }),

    // Cache-key hashes (sha256 hex = 64 chars).
    stablePrefixHash: varchar('stable_prefix_hash', { length: 64 }).notNull(),
    semiStableContextHash: varchar('semi_stable_context_hash', { length: 64 }),
    retrievedContextHash: varchar('retrieved_context_hash', { length: 64 }),
    dynamicInputHash: varchar('dynamic_input_hash', { length: 64 }).notNull(),
    toolSchemaHash: varchar('tool_schema_hash', { length: 64 }),
    outputSchemaHash: varchar('output_schema_hash', { length: 64 }),

    // Full block list for audit (id, label, kind, hash, tokenEstimate,
    // cacheEligible, reasonIncluded). Mirrors PromptBlock[] from @oracle/ai.
    blocksJson: jsonb('blocks_json'),

    // Retrieval-plan observability.
    retrievalPlanId: varchar('retrieval_plan_id', { length: 100 }),
    selectedDomains: jsonb('selected_domains'),
    selectedSourceTypes: jsonb('selected_source_types'),
    selectedProcessStages: jsonb('selected_process_stages'),
    selectedEntityIds: jsonb('selected_entity_ids'),

    // Which records were included in the prompt.
    includedMessageIds: jsonb('included_message_ids'),
    includedDocumentChunkIds: jsonb('included_document_chunk_ids'),
    includedClaimIds: jsonb('included_claim_ids'),
    includedGapIds: jsonb('included_gap_ids'),
    includedContradictionIds: jsonb('included_contradiction_ids'),

    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    taskCreatedIdx: index('oracle_context_packs_task_created_idx').on(t.taskType, t.createdAt),
    routeIdx: index('oracle_context_packs_route_idx').on(t.routeId),
    modelRunIdx: index('oracle_context_packs_model_run_idx').on(t.modelRunId),
    stablePrefixHashIdx: index('oracle_context_packs_stable_prefix_hash_idx').on(t.stablePrefixHash),
  }),
);

export const modelRunUsageDetails = pgTable(
  'model_run_usage_details',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    modelRunId: uuid('model_run_id')
      .references(() => modelRuns.id)
      .notNull()
      .unique(),
    contextPackId: uuid('context_pack_id').references(() => oracleContextPacks.id),

    // Route used. May differ from the originally-requested route if fallback fired.
    routeId: varchar('route_id', { length: 100 }).notNull(),

    // Token breakdown per OracleUsage.
    inputTokens: integer('input_tokens'),
    cachedInputTokens: integer('cached_input_tokens'),
    cacheWriteTokens: integer('cache_write_tokens'),
    outputTokens: integer('output_tokens'),
    reasoningTokens: integer('reasoning_tokens'),

    // Provider audit trail.
    providerRequestId: varchar('provider_request_id', { length: 255 }),
    rawUsageJson: jsonb('raw_usage_json'),

    // Fallback dispatch tracking.
    fellBackFromRouteId: varchar('fell_back_from_route_id', { length: 100 }),
    fallbackReason: varchar('fallback_reason', { length: 100 }),

    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    routeIdx: index('model_run_usage_details_route_idx').on(t.routeId),
    contextPackIdx: index('model_run_usage_details_context_pack_idx').on(t.contextPackId),
    fellBackFromIdx: index('model_run_usage_details_fellback_idx').on(t.fellBackFromRouteId),
  }),
);

export const providerCachedContent = pgTable(
  'provider_cached_content',
  {
    id: uuid('id').primaryKey().defaultRandom(),

    // 'anthropic' | 'vertex' | 'openai'.
    provider: varchar('provider', { length: 50 }).notNull(),
    // 'explicit' (we requested an explicit cache resource) | 'implicit'
    // (provider-managed prefix cache; we just record observed cache hits).
    cacheKind: varchar('cache_kind', { length: 50 }).notNull(),

    // Provider-side handle (e.g., Vertex cachedContent resource name).
    providerResourceName: varchar('provider_resource_name', { length: 500 }),

    // What's cached.
    sourceHash: varchar('source_hash', { length: 64 }).notNull(),
    sourceTokenEstimate: integer('source_token_estimate'),
    sourceDescription: text('source_description'),

    // Reuse policy — required up front per the cache-lifecycle teardown rule
    // in 02-provider-native-ai-architecture.md.
    expectedReuseCount: integer('expected_reuse_count').notNull(),
    actualReuseCount: integer('actual_reuse_count').default(0).notNull(),
    latestPlannedReuseStep: varchar('latest_planned_reuse_step', { length: 100 }),
    hardExpirationAt: timestamp('hard_expiration_at').notNull(),
    cleanupOwner: varchar('cleanup_owner', { length: 100 }),

    // Lifecycle status — every path that ends use of a cache must update this.
    // 'active' | 'deleted' | 'expired' | 'failed' | 'orphaned'.
    status: varchar('status', { length: 50 }).default('active').notNull(),
    deletedAt: timestamp('deleted_at'),
    statusReason: text('status_reason'),

    // Audit.
    createdByJobRunId: uuid('created_by_job_run_id').references(() => jobRuns.id),
    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at').defaultNow().notNull(),
  },
  (t) => ({
    statusIdx: index('provider_cached_content_status_idx').on(t.status),
    providerStatusIdx: index('provider_cached_content_provider_status_idx').on(t.provider, t.status),
    sourceHashIdx: index('provider_cached_content_source_hash_idx').on(t.sourceHash),
    expirationIdx: index('provider_cached_content_expiration_idx').on(t.hardExpirationAt),
    cleanupOwnerIdx: index('provider_cached_content_cleanup_owner_idx').on(t.cleanupOwner),
  }),
);

// ---------------------------------------------------------------------------
// Type exports for app code
// ---------------------------------------------------------------------------

export type Employee = typeof employees.$inferSelect;
export type NewEmployee = typeof employees.$inferInsert;
export type Channel = typeof channels.$inferSelect;
export type Message = typeof messages.$inferSelect;
export type NewMessage = typeof messages.$inferInsert;
export type Document = typeof documents.$inferSelect;
export type Claim = typeof claims.$inferSelect;
export type Gap = typeof gaps.$inferSelect;
export type Contradiction = typeof contradictions.$inferSelect;
export type BrainSection = typeof brainSections.$inferSelect;
export type BrainSectionVersion = typeof brainSectionVersions.$inferSelect;
// R3 observability
export type ModelRun = typeof modelRuns.$inferSelect;
export type NewModelRun = typeof modelRuns.$inferInsert;
export type OracleContextPack = typeof oracleContextPacks.$inferSelect;
export type NewOracleContextPack = typeof oracleContextPacks.$inferInsert;
export type ModelRunUsageDetail = typeof modelRunUsageDetails.$inferSelect;
export type NewModelRunUsageDetail = typeof modelRunUsageDetails.$inferInsert;
export type ProviderCachedContent = typeof providerCachedContent.$inferSelect;
export type NewProviderCachedContent = typeof providerCachedContent.$inferInsert;
