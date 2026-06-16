// Master Drizzle schema for The Oracle — spec Part 6.
// IMPORTANT: do not change column names without coordinating raw SQL migrations
// in `migrations/sql/*` and the RLS policies that reference them.

import {
  boolean,
  date,
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
import { DEPARTMENTS, KNOWLEDGE_DOMAINS, EMBEDDING_DIM } from '@oracle/shared';

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

// Org-unit departments. Source list lives in shared/src/domains.ts. The
// `departments` metadata table (defined below) carries per-row display label,
// description, and optional head_employee_id.
export const departmentEnum = pgEnum('department', DEPARTMENTS);

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
  // DEPRECATED: single-value legacy field. Kept for backward compat during
  // migration. Authoritative source is now `departments` (text[]).
  department: varchar('department', { length: 255 }),
  // Multi-department support. Each value is a free-text department name.
  // The Oracle retrieval layer uses these as soft RRF score hints (not filters).
  departments: text('departments').array().notNull().default([]),
  isAdmin: boolean('is_admin').default(false).notNull(),

  // Preferred content/chat language for this employee. Set manually by an admin
  // to route an employee into the "China group" ('zh-CN'). Drives retrieval
  // rendering, Brain snippet language, answer language, and the source_lang
  // stamped on claims this employee authors. Defaults to English. See china_imp.md.
  locale: varchar('locale', { length: 12 }).notNull().default('en'),

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
// Departments — org units. Enum values in `department_enum`; per-row metadata
// here. `employee_departments` is the many-to-many join (one employee can
// belong to multiple departments).
// ---------------------------------------------------------------------------

export const departments = pgTable('departments', {
  id: departmentEnum('id').primaryKey(),
  // Human-facing label. Editable in /admin/departments without a migration.
  displayLabel: varchar('display_label', { length: 120 }).notNull(),
  description: text('description'),
  // Optional designated head. Used as the prioritized recipient when a
  // clarification request routes to this department; falls back to all
  // members if NULL.
  headEmployeeId: uuid('head_employee_id').references(() => employees.id, {
    onDelete: 'set null',
  }),
  createdAt: timestamp('created_at').defaultNow().notNull(),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

export const employeeDepartments = pgTable(
  'employee_departments',
  {
    employeeId: uuid('employee_id')
      .notNull()
      .references(() => employees.id, { onDelete: 'cascade' }),
    departmentId: departmentEnum('department_id')
      .notNull()
      .references(() => departments.id, { onDelete: 'cascade' }),
    addedAt: timestamp('added_at').defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.employeeId, t.departmentId] })],
);

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

// Typing presence indicators — lightweight heartbeat table so server-side
// workers (e.g. lull-interjection) can check whether anyone is currently
// typing in a channel without subscribing to Supabase Realtime WebSocket.
// The client upserts on typing-start and deletes on typing-stop (or
// lets the row expire via expires_at so stale indicators self-clean).
export const typingIndicators = pgTable(
  'typing_indicators',
  {
    channelId: uuid('channel_id')
      .references(() => channels.id, { onDelete: 'cascade' })
      .notNull(),
    employeeId: uuid('employee_id')
      .references(() => employees.id, { onDelete: 'cascade' })
      .notNull(),
    // Client sets expires_at = now() + 5s on every keystroke, so stale rows
    // mean the client disconnected without sending a stop broadcast.
    expiresAt: timestamp('expires_at', { withTimezone: true }).notNull(),
    updatedAt: timestamp('updated_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.channelId, t.employeeId] }),
    expiresAtIdx: index('typing_indicators_expires_at_idx').on(t.expiresAt),
  }),
);

// Discovered model catalog cache. Refreshed from OpenRouter via the admin
// "Refresh catalog" button. One row per "provider/modelId" id. Pricing is
// stored as USD per 1,000,000 tokens (already multiplied from OpenRouter's
// per-token figures).
export const modelCapabilities = pgTable(
  'model_capabilities',
  {
    id: text('id').primaryKey(),
    provider: text('provider').notNull(),
    displayName: text('display_name').notNull(),
    contextLength: integer('context_length'),
    maxOutputTokens: integer('max_output_tokens'),
    promptPer1mUsd: numeric('prompt_per_1m_usd'),
    completionPer1mUsd: numeric('completion_per_1m_usd'),
    vision: boolean('vision').default(false).notNull(),
    pdf: boolean('pdf').default(false).notNull(),
    thinking: boolean('thinking').default(false).notNull(),
    structuredOutputs: boolean('structured_outputs').default(false).notNull(),
    toolCalling: boolean('tool_calling').default(false).notNull(),
    promptCaching: boolean('prompt_caching').default(false).notNull(),
    outputCap: boolean('output_cap').default(false).notNull(),
    knowledgeCutoff: date('knowledge_cutoff'),
    source: text('source').notNull(),
    refreshedAt: timestamp('refreshed_at', { withTimezone: true }).defaultNow().notNull(),
  },
  (t) => ({
    providerIdx: index('model_capabilities_provider_idx').on(t.provider),
    refreshedIdx: index('model_capabilities_refreshed_idx').on(t.refreshedAt),
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
    // Optional uploader-provided context fed into the extraction (and image
    // vision) prompts to disambiguate the document. Soft signal only.
    context: text('context'),
    // Optional uploader-suggested knowledge_top_domains.id values, used as a
    // prior in the extraction prompt. Per-claim domain validation stays
    // authoritative — these never override it.
    domainHints: jsonb('domain_hints').$type<string[]>(),
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
    // 'sync' (real-time API) | 'batch' (provider Batch API, ~50% off, 24-hour SLA).
    // NULL = legacy row predating the column.
    dispatchMode: varchar('dispatch_mode', { length: 20 }),
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
    // Language the claim was originally created in (language of the source
    // conversation/document). The canonical `summary` + `embedding` are in this
    // language; renderings in other languages live in `claim_translations`.
    // See china_imp.md.
    sourceLang: varchar('source_lang', { length: 12 }).notNull().default('en'),
    embedding: vector('embedding', { dimensions: EMBEDDING_DIM }),
    // R7 — sha256 hex of the canonicalized candidate (see
    // computeCandidateHash in @oracle/engines). The promotion executor
    // looks claims up by this column inside the advisory lock to detect
    // historical duplicates across cron runs. Nullable for backward
    // compatibility with rows promoted before R7; the partial UNIQUE
    // index in migrations/sql/14_claims_candidate_hash_unique.sql
    // enforces uniqueness only when populated.
    candidateHash: varchar('candidate_hash', { length: 64 }),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    statusCreatedIdx: index('claims_status_created_idx').on(t.status, t.createdAt),
    impactIdx: index('claims_impact_idx').on(t.impactScore),
    confidenceIdx: index('claims_confidence_idx').on(t.confidenceScore),
    candidateHashIdx: index('claims_candidate_hash_idx').on(t.candidateHash),
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

// Bilingual claim layer — display-only translations of a claim's summary into
// other languages. The canonical claim (claims.summary + claims.embedding, in
// claims.source_lang) is authoritative; these rows are renderings for readers
// in a different language. NEVER used for quote validation, candidate hashing,
// or promotion — evidence stays in the source language. See china_imp.md.
export const claimTranslations = pgTable(
  'claim_translations',
  {
    claimId: uuid('claim_id')
      .references(() => claims.id)
      .notNull(),
    lang: varchar('lang', { length: 12 }).notNull(), // 'zh-CN' | 'en'
    summary: text('summary').notNull(),
    // Embedding of the translated summary (same model/dimension as claims).
    embedding: vector('embedding', { dimensions: EMBEDDING_DIM }),
    translatedByModelRunId: uuid('translated_by_model_run_id').references(
      () => modelRuns.id,
    ),
    // sha256 hex of the canonical summary at translation time. The translation
    // worker re-translates when this no longer matches the current summary.
    sourceHash: varchar('source_hash', { length: 64 }),
    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.claimId, t.lang] }),
    langIdx: index('claim_translations_lang_idx').on(t.lang),
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

// Bilingual Brain layer — display-only translations of an immutable brain
// section version's markdown into other languages. Keyed to the version id
// (versions are immutable snapshots). See china_imp.md.
export const brainSectionVersionTranslations = pgTable(
  'brain_section_version_translations',
  {
    versionId: uuid('version_id')
      .references(() => brainSectionVersions.id)
      .notNull(),
    lang: varchar('lang', { length: 12 }).notNull(),
    markdown: text('markdown').notNull(),
    structuredContent: jsonb('structured_content'),
    translatedByModelRunId: uuid('translated_by_model_run_id').references(
      () => modelRuns.id,
    ),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.versionId, t.lang] }),
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
    providerMetadataJson: jsonb('provider_metadata_json'),

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

export const providerResponseSessions = pgTable(
  'provider_response_sessions',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    provider: varchar('provider', { length: 50 }).notNull(),
    sessionKey: varchar('session_key', { length: 255 }).notNull(),
    scopeKind: varchar('scope_kind', { length: 50 }).notNull(),
    scopeId: varchar('scope_id', { length: 255 }).notNull(),
    modelId: varchar('model_id', { length: 255 }).notNull(),
    latestResponseId: varchar('latest_response_id', { length: 255 }).notNull(),
    lastContextPackId: uuid('last_context_pack_id').references(() => oracleContextPacks.id),
    lastModelRunId: uuid('last_model_run_id').references(() => modelRuns.id),
    expiresAt: timestamp('expires_at'),
    metadataJson: jsonb('metadata_json'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at').defaultNow().notNull(),
  },
  (t) => ({
    sessionUniqueIdx: uniqueIndex('provider_response_sessions_provider_session_key_unique').on(
      t.provider,
      t.sessionKey,
    ),
    scopeIdx: index('provider_response_sessions_scope_idx').on(t.scopeKind, t.scopeId),
    expiresIdx: index('provider_response_sessions_expires_idx').on(t.expiresAt),
  }),
);

/**
 * Provider Batch API job tracking. One row per submitted batch (1 batch can
 * fan out to N requests / N extraction_batches rows). Batch APIs run async
 * with a 24-hour SLA at ~50% the sync price. A `drain` cron polls in-flight
 * rows by `(provider, provider_batch_id)` and processes results when status
 * becomes 'completed'.
 *
 * status whitelist: 'submitted','in_progress','completed','failed','expired','canceled'.
 * provider whitelist matches the OracleProvider union (anthropic/openai/vertex/...).
 *
 * `provider_metadata_json` stores provider-specific identifiers needed to
 * retrieve results — for OpenAI: { inputFileId, outputFileId, errorFileId }.
 * For Vertex: { inputGcsUri, outputGcsUri }. For Anthropic: nothing
 * additional (batch ID is sufficient via SDK).
 */
export const providerBatchJobs = pgTable(
  'provider_batch_jobs',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    provider: varchar('provider', { length: 50 }).notNull(),
    providerBatchId: varchar('provider_batch_id', { length: 255 }).notNull(),
    status: varchar('status', { length: 50 }).default('submitted').notNull(),
    taskType: varchar('task_type', { length: 100 }).notNull(),
    routeId: varchar('route_id', { length: 255 }).notNull(),
    modelId: varchar('model_id', { length: 255 }).notNull(),
    requestCount: integer('request_count').notNull(),
    completedCount: integer('completed_count').default(0).notNull(),
    failedCount: integer('failed_count').default(0).notNull(),
    providerMetadataJson: jsonb('provider_metadata_json'),
    errorJson: jsonb('error_json'),
    submittedAt: timestamp('submitted_at').defaultNow().notNull(),
    pollLastAt: timestamp('poll_last_at'),
    completedAt: timestamp('completed_at'),
    resultsRetrievedAt: timestamp('results_retrieved_at'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    statusIdx: index('provider_batch_jobs_status_idx').on(t.status),
    providerBatchIdx: uniqueIndex('provider_batch_jobs_provider_batch_unique').on(t.provider, t.providerBatchId),
    taskIdx: index('provider_batch_jobs_task_idx').on(t.taskType),
    submittedIdx: index('provider_batch_jobs_submitted_idx').on(t.submittedAt),
  }),
);

export type ProviderBatchJob = typeof providerBatchJobs.$inferSelect;
export type NewProviderBatchJob = typeof providerBatchJobs.$inferInsert;

// ---------------------------------------------------------------------------
// R3.5 — Three-layer knowledge taxonomy
//
// Source of truth for the shapes:
//   docs/oracle/07-knowledge-segmentation.md
//   docs/oracle/05-ai-retrofit-phase-packet.md Phase R3.5
//
// Layer 1: knowledge_top_domains  (admin-curated text PK, includes boundary rules)
// Layer 2: knowledge_sub_topics   (auto-discovered, admin-approved, embedding centroid)
// Layer 3: entities               (canonical registry; licensor is distinct from vendor)
//
// Plus join tables so retrieval can filter:
//   - claims  → claim_top_domains, claim_sub_topics, claim_entities, claim_metadata
//   - documents/chunks/messages → top-domain + entity tags (so retrieval works
//     before any claim has been promoted)
//
// Plus governance:
//   - taxonomy_proposals  (queue; auto-mutation prohibited)
//   - taxonomy_change_log (audit of accepted changes)
//   - entity_proposals    (unknown entities surfaced by extraction)
// ---------------------------------------------------------------------------

export const knowledgeTopDomains = pgTable('knowledge_top_domains', {
  id: varchar('id', { length: 100 }).primaryKey(), // e.g. 'customer_ops'
  name: varchar('name', { length: 255 }).notNull(),
  description: text('description').notNull(),

  // Boundary rules — required per R3.5 task 1.
  // belongsHere / doesNotBelongHere: arrays of short example strings.
  belongsHere: jsonb('belongs_here').default([]).notNull(),
  doesNotBelongHere: jsonb('does_not_belong_here').default([]).notNull(),
  // commonEntityHints: [{ entityType, canonicalValue }, ...].
  commonEntityHints: jsonb('common_entity_hints').default([]).notNull(),
  defaultExcludedDocumentClasses: jsonb('default_excluded_document_classes').default([]).notNull(),
  neighboringDomainIds: jsonb('neighboring_domain_ids').default([]).notNull(),

  displayOrder: integer('display_order').notNull(),
  isActive: boolean('is_active').default(true).notNull(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

export const knowledgeSubTopics = pgTable(
  'knowledge_sub_topics',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    topDomainId: varchar('top_domain_id', { length: 100 })
      .references(() => knowledgeTopDomains.id)
      .notNull(),
    name: varchar('name', { length: 255 }).notNull(),
    description: text('description'),
    centroid: vector('centroid', { dimensions: 1536 }),
    memberCount: integer('member_count').default(0).notNull(),
    reviewStatus: varchar('review_status', { length: 50 }).notNull(),
    approvedByEmployeeId: uuid('approved_by_employee_id').references(() => employees.id),
    approvedAt: timestamp('approved_at'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
    updatedAt: timestamp('updated_at').defaultNow().notNull(),
  },
  (t) => ({
    topDomainNameUnique: uniqueIndex('knowledge_sub_topics_top_domain_name_unique').on(t.topDomainId, t.name),
    topDomainIdx: index('knowledge_sub_topics_top_domain_idx').on(t.topDomainId),
    reviewStatusIdx: index('knowledge_sub_topics_review_status_idx').on(t.reviewStatus),
  }),
);

// Claim → top-level domain (multi-valued; replaces single knowledgeDomainEnum column).
export const claimTopDomains = pgTable(
  'claim_top_domains',
  {
    claimId: uuid('claim_id')
      .references(() => claims.id)
      .notNull(),
    topDomainId: varchar('top_domain_id', { length: 100 })
      .references(() => knowledgeTopDomains.id)
      .notNull(),
    assignmentConfidence: numeric('assignment_confidence', { precision: 4, scale: 3 }),
    assignmentReason: varchar('assignment_reason', { length: 50 }).notNull(),
    assignedAt: timestamp('assigned_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.claimId, t.topDomainId] }),
    topDomainIdx: index('claim_top_domains_top_domain_idx').on(t.topDomainId),
  }),
);

// Document → top-level domain (for pre-claim retrieval / document-level filtering).
export const documentTopDomains = pgTable(
  'document_top_domains',
  {
    documentId: uuid('document_id')
      .references(() => documents.id)
      .notNull(),
    topDomainId: varchar('top_domain_id', { length: 100 })
      .references(() => knowledgeTopDomains.id)
      .notNull(),
    assignmentConfidence: numeric('assignment_confidence', { precision: 4, scale: 3 }),
    assignmentReason: varchar('assignment_reason', { length: 50 }).notNull(),
    assignedAt: timestamp('assigned_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.documentId, t.topDomainId] }),
    topDomainIdx: index('document_top_domains_top_domain_idx').on(t.topDomainId),
  }),
);

// Document chunk → top-level domain (retrieval before claim promotion).
export const documentChunkTopDomains = pgTable(
  'document_chunk_top_domains',
  {
    documentChunkId: uuid('document_chunk_id')
      .references(() => documentChunks.id)
      .notNull(),
    topDomainId: varchar('top_domain_id', { length: 100 })
      .references(() => knowledgeTopDomains.id)
      .notNull(),
    assignmentConfidence: numeric('assignment_confidence', { precision: 4, scale: 3 }),
    assignmentReason: varchar('assignment_reason', { length: 50 }).notNull(),
    assignedAt: timestamp('assigned_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.documentChunkId, t.topDomainId] }),
    topDomainIdx: index('document_chunk_top_domains_top_domain_idx').on(t.topDomainId),
  }),
);

// Message → top-level domain (retrieval before claim promotion).
export const messageTopDomains = pgTable(
  'message_top_domains',
  {
    messageId: uuid('message_id')
      .references(() => messages.id)
      .notNull(),
    topDomainId: varchar('top_domain_id', { length: 100 })
      .references(() => knowledgeTopDomains.id)
      .notNull(),
    assignmentConfidence: numeric('assignment_confidence', { precision: 4, scale: 3 }),
    assignmentReason: varchar('assignment_reason', { length: 50 }).notNull(),
    assignedAt: timestamp('assigned_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.messageId, t.topDomainId] }),
    topDomainIdx: index('message_top_domains_top_domain_idx').on(t.topDomainId),
  }),
);

// Claim → sub-topic (multi-valued).
export const claimSubTopics = pgTable(
  'claim_sub_topics',
  {
    claimId: uuid('claim_id')
      .references(() => claims.id)
      .notNull(),
    subTopicId: uuid('sub_topic_id')
      .references(() => knowledgeSubTopics.id)
      .notNull(),
    assignmentConfidence: numeric('assignment_confidence', { precision: 4, scale: 3 }),
    assignmentReason: varchar('assignment_reason', { length: 50 }).notNull(),
    assignedAt: timestamp('assigned_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.claimId, t.subTopicId] }),
    subTopicIdx: index('claim_sub_topics_sub_topic_idx').on(t.subTopicId),
  }),
);

// Layer 3 — canonical entity registry.
export const entities = pgTable(
  'entities',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    entityType: varchar('entity_type', { length: 50 }).notNull(),
    canonicalValue: varchar('canonical_value', { length: 255 }).notNull(),
    displayLabel: varchar('display_label', { length: 255 }),
    aliases: jsonb('aliases'),
    // Which top-level domains this entity belongs to (text[]).
    domainHints: jsonb('domain_hints').default([]).notNull(),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    typeValueUnique: uniqueIndex('entities_type_value_unique').on(t.entityType, t.canonicalValue),
    typeIdx: index('entities_type_idx').on(t.entityType),
  }),
);

// Claim → entity tags.
export const claimEntities = pgTable(
  'claim_entities',
  {
    claimId: uuid('claim_id')
      .references(() => claims.id)
      .notNull(),
    entityId: uuid('entity_id')
      .references(() => entities.id)
      .notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.claimId, t.entityId] }),
    entityIdx: index('claim_entities_entity_idx').on(t.entityId),
  }),
);

// Document chunk → entity tags (for pre-claim retrieval).
export const documentChunkEntities = pgTable(
  'document_chunk_entities',
  {
    documentChunkId: uuid('document_chunk_id')
      .references(() => documentChunks.id)
      .notNull(),
    entityId: uuid('entity_id')
      .references(() => entities.id)
      .notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.documentChunkId, t.entityId] }),
    entityIdx: index('document_chunk_entities_entity_idx').on(t.entityId),
  }),
);

// Message → entity tags (for pre-claim retrieval).
export const messageEntities = pgTable(
  'message_entities',
  {
    messageId: uuid('message_id')
      .references(() => messages.id)
      .notNull(),
    entityId: uuid('entity_id')
      .references(() => entities.id)
      .notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.messageId, t.entityId] }),
    entityIdx: index('message_entities_entity_idx').on(t.entityId),
  }),
);

// Claim metadata — orthogonal axes that don't fit into the join tables above.
//
// Note: the spec sketch uses tstzrange for time_validity. To stay Drizzle-
// queryable we split it into effective_from / effective_until columns.
export const claimMetadata = pgTable('claim_metadata', {
  claimId: uuid('claim_id')
    .primaryKey()
    .references(() => claims.id),
  processStage: varchar('process_stage', { length: 100 }),
  department: varchar('department', { length: 100 }),
  geography: varchar('geography', { length: 100 }),
  documentClass: varchar('document_class', { length: 100 }),
  effectiveFrom: timestamp('effective_from'),
  effectiveUntil: timestamp('effective_until'),
  supersededByClaimId: uuid('superseded_by_claim_id').references(() => claims.id),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

// Governance — proposals queue. Auto-mutation is prohibited; an admin must approve.
export const taxonomyProposals = pgTable(
  'taxonomy_proposals',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    proposalType: varchar('proposal_type', { length: 50 }).notNull(),
    // Payload follows the TaxonomyProposalPayload contract in
    // docs/oracle/07-knowledge-segmentation.md.
    payload: jsonb('payload').notNull(),
    proposedByModelRunId: uuid('proposed_by_model_run_id').references(() => modelRuns.id),
    status: varchar('status', { length: 50 }).notNull(),
    reviewedByEmployeeId: uuid('reviewed_by_employee_id').references(() => employees.id),
    reviewedAt: timestamp('reviewed_at'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    statusIdx: index('taxonomy_proposals_status_idx').on(t.status),
    typeStatusIdx: index('taxonomy_proposals_type_status_idx').on(t.proposalType, t.status),
  }),
);

// Audit log of accepted taxonomy changes.
export const taxonomyChangeLog = pgTable(
  'taxonomy_change_log',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    changeType: varchar('change_type', { length: 100 }).notNull(),
    beforeState: jsonb('before_state'),
    afterState: jsonb('after_state'),
    reason: text('reason'),
    approvedByEmployeeId: uuid('approved_by_employee_id').references(() => employees.id),
    proposalId: uuid('proposal_id').references(() => taxonomyProposals.id),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    changeTypeIdx: index('taxonomy_change_log_change_type_idx').on(t.changeType),
    proposalIdx: index('taxonomy_change_log_proposal_idx').on(t.proposalId),
  }),
);

// Unknown-entity proposals queue. When extraction surfaces an entity reference
// that doesn't resolve to the canonical registry, it's staged here for admin
// review instead of being auto-created.
export const entityProposals = pgTable(
  'entity_proposals',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    proposedEntityType: varchar('proposed_entity_type', { length: 50 }).notNull(),
    proposedCanonicalValue: varchar('proposed_canonical_value', { length: 255 }).notNull(),
    rawStringsObserved: jsonb('raw_strings_observed').default([]).notNull(),
    proposedAliases: jsonb('proposed_aliases'),
    proposedDomainHints: jsonb('proposed_domain_hints'),
    observedInSourceType: varchar('observed_in_source_type', { length: 50 }).notNull(),
    observedInSourceId: uuid('observed_in_source_id'),
    status: varchar('status', { length: 50 }).notNull(),
    mergedIntoEntityId: uuid('merged_into_entity_id').references(() => entities.id),
    proposedByModelRunId: uuid('proposed_by_model_run_id').references(() => modelRuns.id),
    reviewedByEmployeeId: uuid('reviewed_by_employee_id').references(() => employees.id),
    reviewedAt: timestamp('reviewed_at'),
    // How many times this entity surface has been observed. Incremented by
    // stageEntityProposal() when a fuzzy-similar proposal already exists
    // (pg_trgm similarity >= 0.85) instead of inserting a duplicate row.
    proposalCount: integer('proposal_count').default(1).notNull(),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    statusIdx: index('entity_proposals_status_idx').on(t.status),
    typeValueIdx: index('entity_proposals_type_value_idx').on(t.proposedEntityType, t.proposedCanonicalValue),
  }),
);

// ---------------------------------------------------------------------------
// R4 — Candidate-before-claim staging
//
// Source of truth for the shapes:
//   docs/oracle/03-candidate-before-claim-validation.md
//   docs/oracle/05-ai-retrofit-phase-packet.md Phase R4
//
// Pipeline:
//   model output
//     → extraction_batches
//     → extraction_candidates
//     → extraction_candidate_evidence
//     → deterministic validation (extraction_validation_results)
//     → transactional promotion
//     → permanent claims / claim_top_domains / claim_evidence
//
// Schema-only phase: no worker behavior changes yet. The existing
// claim-extraction worker continues to insert directly into permanent
// claims until R6 wires it through this staging pipeline.
// ---------------------------------------------------------------------------

export const extractionBatches = pgTable(
  'extraction_batches',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    jobRunId: uuid('job_run_id').references(() => jobRuns.id),
    // Current / latest model run for the batch. Earlier attempts are in
    // modelRunIdsAttempted.
    modelRunId: uuid('model_run_id').references(() => modelRuns.id),
    contextPackId: uuid('context_pack_id').references(() => oracleContextPacks.id),
    // Set only for batch-mode runs — links the per-input extraction_batches row
    // to the provider_batch_jobs row that owns the in-flight provider batch.
    providerBatchJobId: uuid('provider_batch_job_id'),

    // 'message_segment' | 'document_chunk' | 'document_page' | 'transcript_segment'.
    batchType: varchar('batch_type', { length: 50 }).notNull(),

    // EXTRACTION_BATCH_STATUSES.
    status: varchar('status', { length: 50 }).default('pending_model').notNull(),

    // What was processed. Arrays of UUIDs as JSONB so a single batch can
    // span multiple source rows (group-chat segments etc.).
    sourceMessageIds: jsonb('source_message_ids'),
    sourceDocumentChunkIds: jsonb('source_document_chunk_ids'),
    // sha256 hex over the source content fed into the model — used for
    // idempotency and to identify "same batch retried" for the circuit breaker.
    sourceHash: varchar('source_hash', { length: 64 }).notNull(),

    rawModelOutput: jsonb('raw_model_output'),
    validationSummary: jsonb('validation_summary'),

    // Retry safety / circuit breaker.
    validationAttemptCount: integer('validation_attempt_count').default(0).notNull(),
    consecutiveQuoteFailureCount: integer('consecutive_quote_failure_count').default(0).notNull(),
    // History of every model run attempted on this batch (in order).
    modelRunIdsAttempted: jsonb('model_run_ids_attempted').default([]).notNull(),
    // History of every route ID attempted on this batch (in order).
    routeIdsAttempted: jsonb('route_ids_attempted').default([]).notNull(),

    error: text('error'),

    startedAt: timestamp('started_at').defaultNow().notNull(),
    finishedAt: timestamp('finished_at'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    statusIdx: index('extraction_batches_status_idx').on(t.status),
    statusCreatedIdx: index('extraction_batches_status_created_idx').on(t.status, t.createdAt),
    sourceHashIdx: index('extraction_batches_source_hash_idx').on(t.sourceHash),
    batchTypeIdx: index('extraction_batches_batch_type_idx').on(t.batchType),
    modelRunIdx: index('extraction_batches_model_run_idx').on(t.modelRunId),
    contextPackIdx: index('extraction_batches_context_pack_idx').on(t.contextPackId),
  }),
);

export const extractionCandidates = pgTable(
  'extraction_candidates',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    extractionBatchId: uuid('extraction_batch_id')
      .references(() => extractionBatches.id)
      .notNull(),

    // EXTRACTION_CANDIDATE_STATUSES.
    status: varchar('status', { length: 50 }).default('pending_validation').notNull(),

    claimType: varchar('claim_type', { length: 100 }).notNull(),
    summary: text('summary').notNull(),
    impactScore: integer('impact_score').notNull(),
    confidenceScore: integer('confidence_score'),

    // Proposed top-domain IDs (text[] of knowledge_top_domains.id).
    domains: jsonb('domains').notNull(),
    // Proposed entity references the model surfaced — array of
    // { entityType, canonicalValue, resolvedEntityId? }. Unresolved entries
    // become entity_proposals when promotion is attempted.
    proposedEntities: jsonb('proposed_entities').default([]).notNull(),
    // Optional metadata the model surfaced (process_stage, department, etc.).
    proposedMetadata: jsonb('proposed_metadata'),

    // CANDIDATE_STANCES.
    stance: varchar('stance', { length: 50 }),

    // Privacy / sensitivity gate per docs/oracle/03 "Privacy and sensitivity gate".
    containsSensitivePersonalData: boolean('contains_sensitive_personal_data').default(false).notNull(),
    containsSensitiveHRData: boolean('contains_sensitive_hr_data').default(false).notNull(),
    isPersonalConflict: boolean('is_personal_conflict').default(false).notNull(),
    sensitivityReason: text('sensitivity_reason'),

    riskFlags: jsonb('risk_flags'),
    requiresReview: boolean('requires_review').default(true).notNull(),
    reviewReason: text('review_reason'),

    // Dedup — within the staging pipeline and against already-promoted claims.
    duplicateOfCandidateId: uuid('duplicate_of_candidate_id'),
    duplicateOfClaimId: uuid('duplicate_of_claim_id').references(() => claims.id),

    // After successful promotion, points at the resulting permanent claim.
    promotedToClaimId: uuid('promoted_to_claim_id').references(() => claims.id),

    rawCandidateJson: jsonb('raw_candidate_json').notNull(),
    validationError: text('validation_error'),

    createdAt: timestamp('created_at').defaultNow().notNull(),
    validatedAt: timestamp('validated_at'),
    promotedAt: timestamp('promoted_at'),
  },
  (t) => ({
    statusIdx: index('extraction_candidates_status_idx').on(t.status),
    batchIdx: index('extraction_candidates_batch_idx').on(t.extractionBatchId),
    promotedClaimIdx: index('extraction_candidates_promoted_claim_idx').on(t.promotedToClaimId),
    duplicateClaimIdx: index('extraction_candidates_duplicate_claim_idx').on(t.duplicateOfClaimId),
    sensitivityIdx: index('extraction_candidates_sensitivity_idx').on(
      t.containsSensitiveHRData,
      t.isPersonalConflict,
    ),
    createdAtIdx: index('extraction_candidates_created_at_idx').on(t.createdAt),
  }),
);

export const extractionCandidateEvidence = pgTable(
  'extraction_candidate_evidence',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    candidateId: uuid('candidate_id')
      .references(() => extractionCandidates.id)
      .notNull(),

    sourceType: evidenceSourceTypeEnum('source_type').notNull(),
    sourceMessageId: uuid('source_message_id').references(() => messages.id),
    sourceDocumentChunkId: uuid('source_document_chunk_id').references(() => documentChunks.id),
    sourceExternalRecordId: varchar('source_external_record_id', { length: 255 }),

    assertedByEmployeeId: uuid('asserted_by_employee_id').references(() => employees.id),
    uploadedByEmployeeId: uuid('uploaded_by_employee_id').references(() => employees.id),
    createdByEmployeeId: uuid('created_by_employee_id').references(() => employees.id),

    exactQuoteProvided: text('exact_quote_provided').notNull(),
    normalizedQuote: text('normalized_quote'),
    charStartProvided: integer('char_start_provided'),
    charEndProvided: integer('char_end_provided'),

    // Filled in by the deterministic validator (R5).
    validatedExactQuote: text('validated_exact_quote'),
    validatedCharStart: integer('validated_char_start'),
    validatedCharEnd: integer('validated_char_end'),
    pageNumber: integer('page_number'),

    // EVIDENCE_VALIDATION_STATUSES.
    validationStatus: varchar('validation_status', { length: 50 }).default('pending').notNull(),

    // 'verbatim_includes' | 'verbatim_offset_match' | 'normalized_*' | 'none'.
    validationMethod: varchar('validation_method', { length: 100 }),
    validationError: text('validation_error'),
    confidence: integer('confidence'),

    // R5.5 — taxonomy metadata surfaced inline by the extractor when the
    // model can infer it from the surrounding context. Nullable; the
    // promoter writes these through to claim_metadata.
    documentClass: varchar('document_class', { length: 100 }),
    processStage: varchar('process_stage', { length: 100 }),

    createdAt: timestamp('created_at').defaultNow().notNull(),
    validatedAt: timestamp('validated_at'),
  },
  (t) => ({
    candidateIdx: index('extraction_candidate_evidence_candidate_idx').on(t.candidateId),
    sourceMessageIdx: index('extraction_candidate_evidence_source_message_idx').on(t.sourceMessageId),
    sourceChunkIdx: index('extraction_candidate_evidence_source_chunk_idx').on(t.sourceDocumentChunkId),
    validationStatusIdx: index('extraction_candidate_evidence_validation_status_idx').on(t.validationStatus),
  }),
);

export const extractionValidationResults = pgTable(
  'extraction_validation_results',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    candidateId: uuid('candidate_id').references(() => extractionCandidates.id),
    candidateEvidenceId: uuid('candidate_evidence_id').references(() => extractionCandidateEvidence.id),

    // VALIDATION_CHECK_NAMES.
    checkName: varchar('check_name', { length: 100 }).notNull(),

    // VALIDATION_CHECK_STATUSES.
    status: varchar('status', { length: 50 }).notNull(),

    detail: text('detail'),
    metadataJson: jsonb('metadata_json'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    candidateIdx: index('extraction_validation_results_candidate_idx').on(t.candidateId),
    candidateEvidenceIdx: index('extraction_validation_results_candidate_evidence_idx').on(t.candidateEvidenceId),
    checkNameStatusIdx: index('extraction_validation_results_check_name_status_idx').on(t.checkName, t.status),
    createdAtIdx: index('extraction_validation_results_created_at_idx').on(t.createdAt),
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
export type ClaimTranslation = typeof claimTranslations.$inferSelect;
export type NewClaimTranslation = typeof claimTranslations.$inferInsert;
export type BrainSectionVersionTranslation =
  typeof brainSectionVersionTranslations.$inferSelect;
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
// R3.5 knowledge taxonomy
export type KnowledgeTopDomain = typeof knowledgeTopDomains.$inferSelect;
export type NewKnowledgeTopDomain = typeof knowledgeTopDomains.$inferInsert;
export type KnowledgeSubTopic = typeof knowledgeSubTopics.$inferSelect;
export type NewKnowledgeSubTopic = typeof knowledgeSubTopics.$inferInsert;
export type ClaimTopDomain = typeof claimTopDomains.$inferSelect;
export type NewClaimTopDomain = typeof claimTopDomains.$inferInsert;
export type DocumentTopDomain = typeof documentTopDomains.$inferSelect;
export type NewDocumentTopDomain = typeof documentTopDomains.$inferInsert;
export type DocumentChunkTopDomain = typeof documentChunkTopDomains.$inferSelect;
export type NewDocumentChunkTopDomain = typeof documentChunkTopDomains.$inferInsert;
export type MessageTopDomain = typeof messageTopDomains.$inferSelect;
export type NewMessageTopDomain = typeof messageTopDomains.$inferInsert;
export type ClaimSubTopic = typeof claimSubTopics.$inferSelect;
export type NewClaimSubTopic = typeof claimSubTopics.$inferInsert;
export type Entity = typeof entities.$inferSelect;
export type NewEntity = typeof entities.$inferInsert;
export type ClaimEntity = typeof claimEntities.$inferSelect;
export type NewClaimEntity = typeof claimEntities.$inferInsert;
export type DocumentChunkEntity = typeof documentChunkEntities.$inferSelect;
export type NewDocumentChunkEntity = typeof documentChunkEntities.$inferInsert;
export type MessageEntity = typeof messageEntities.$inferSelect;
export type NewMessageEntity = typeof messageEntities.$inferInsert;
export type ClaimMetadata = typeof claimMetadata.$inferSelect;
export type NewClaimMetadata = typeof claimMetadata.$inferInsert;
export type TaxonomyProposal = typeof taxonomyProposals.$inferSelect;
export type NewTaxonomyProposal = typeof taxonomyProposals.$inferInsert;
export type TaxonomyChangeLog = typeof taxonomyChangeLog.$inferSelect;
export type NewTaxonomyChangeLog = typeof taxonomyChangeLog.$inferInsert;
export type EntityProposal = typeof entityProposals.$inferSelect;
export type NewEntityProposal = typeof entityProposals.$inferInsert;
// Typing presence
export type TypingIndicator = typeof typingIndicators.$inferSelect;
export type NewTypingIndicator = typeof typingIndicators.$inferInsert;
export type ModelCapabilityRow = typeof modelCapabilities.$inferSelect;
export type NewModelCapabilityRow = typeof modelCapabilities.$inferInsert;
// R4 candidate-before-claim staging
export type ExtractionBatch = typeof extractionBatches.$inferSelect;
export type NewExtractionBatch = typeof extractionBatches.$inferInsert;
export type ExtractionCandidate = typeof extractionCandidates.$inferSelect;
export type NewExtractionCandidate = typeof extractionCandidates.$inferInsert;
export type ExtractionCandidateEvidence = typeof extractionCandidateEvidence.$inferSelect;
export type NewExtractionCandidateEvidence = typeof extractionCandidateEvidence.$inferInsert;
export type ExtractionValidationResult = typeof extractionValidationResults.$inferSelect;
export type NewExtractionValidationResult = typeof extractionValidationResults.$inferInsert;
