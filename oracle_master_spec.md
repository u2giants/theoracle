# MASTER DEVELOPMENT SPECIFICATION: “THE ORACLE”

**Project:** POP Creations / Spruce Line Enterprise Knowledge Graph  
**Author:** Albert H. / Lead Architect  
**Status:** V4.1 Enterprise Architecture, Authentication, RLS & Production Readiness  
**Primary Implementation Target:** Claude Code / TypeScript Monorepo

---

# CLAUDE CODE OPERATING INSTRUCTIONS

This document is written as the authoritative development specification for Claude Code.

Follow these rules:

1. **Do not reinterpret the product.** The Oracle is not a project-management system, task tracker, ticket system, or ClickUp clone.
2. **Do not introduce Python, LangChain, LangGraph, Celery, Aegra, Docker, or VPS-managed services.**
3. **Do not store operational knowledge in local files, flat Markdown files, Redis memory, or unstructured AI memory.**
4. **The PostgreSQL database is the source of truth.**
5. **Every operational claim must be traceable to evidence.**
6. **Do not build the full system in one pass. Implement phase-by-phase and stop after each phase for verification.**
7. **If a schema field, policy, or workflow seems underspecified, implement the safest minimal version and document the assumption.**
8. **All generated code must be TypeScript-first, strongly typed, and compatible with the stack defined below.**

---

# PART 1: EXECUTIVE SUMMARY & BUSINESS CONTEXT

## 1.1 Who We Are & The Business Reality

**POP Creations / Spruce Line** is a high-volume home decor company based in Brooklyn, New York.

We design products in-house, manufacture them in China, and sell to major US retail chains including Burlington, TJX, Ross, Hobby Lobby, Walmart, and others.

We currently track approximately **1,500 active SKUs** at any given time.

We employ **18 people** across multiple complex departments:

- Design: US, Brazil, Colombia
- Licensing: US, Colombia
- Production / Logistics: US and China
- Sales: US
- Sourcing: China

We use an ERP system called **Coldlion** to manage operational data.

The company’s operations are a tangled web of global dependencies. A licensed design approval in the US may trigger a physical sample request in China. A sample delay may affect logistics, which may affect customer communication, routing, and delivery expectations.

## 1.2 The Core Problem: “Dark Matter”

The actual operational reality of the company lives mostly in the heads of employees.

We do not have complete manuals, complete standard operating procedures, or a reliable written map of how work actually moves.

We suffer from **Dark Matter**: the invisible forces that actually run the company.

Examples:

- Informal rules
- Undocumented workarounds
- Missing context during inter-departmental handoffs
- Hidden bottlenecks that employees accept as “the way it is”
- Unspoken dependencies between Design, Sourcing, Licensing, Logistics, China, and Coldlion
- Private spreadsheets or side systems created because the official systems do not show what people need
- Contradictory understandings of when work is “ready” for the next department

No one person knows all of these rules, how they evolved, or whether they are still the right way to operate.

## 1.3 The Solution: The Oracle

**Critical directive to developer:** You are **not** building a project-management system. You are **not** building a task tracker, to-do list, ticketing system, or due-date manager.

If you find yourself writing code to assign normal operational tasks, change due dates, or manage project execution, stop and reassess.

You are building an **AI-powered Business Intelligence System**, internally called **The Oracle**.

The Oracle is a living Enterprise Knowledge Graph. It acts like an intensely curious, evidence-driven Chief Operating Officer.

Its purpose is to:

- Observe company conversations
- Interview employees
- Read company documents
- Extract operational claims
- Link every claim to evidence
- Identify contradictions
- Identify gaps in company understanding
- Ask follow-up questions
- Synthesize a versioned “Brain” of how the company actually works
- Let Albert ask high-level operational questions with answers backed by traceable evidence

The end goal is an Oracle that can answer nearly any question about the company’s operations, while showing exactly what evidence supports the answer.

---

# PART 2: STRICT ARCHITECTURAL TENETS

## 2.1 TypeScript Only

Use TypeScript for:

- Frontend
- API routes
- Background workers
- Shared schemas
- Database models
- Validation logic

We are using AI coding agents. A single TypeScript ecosystem reduces context switching and lets us share types across the entire monorepo.

## 2.2 No Python, No LangChain, No Celery

Do not use:

- Python
- LangChain
- LangGraph
- Aegra
- Celery
- Custom agent frameworks unless explicitly approved

LLM calls should be explicit and understandable. Avoid abstractions that hide prompts, schemas, model calls, or retrieval logic.

## 2.3 Database Is the Only Source of Truth

Do not store:

- AI memory in local files
- Brain documents as flat Markdown files
- Chat transcripts in JSON files
- Operational claims in Redis
- Long-term state outside Postgres

Every durable piece of data must live in the relational PostgreSQL database.

Redis-like or memory systems may be used only for ephemeral transport if a managed service requires it, not as source of truth.

## 2.4 Absolute Traceability

An LLM cannot be trusted to rewrite company operations without evidence.

Every operational claim must link to one or more rows in `claim_evidence`.

Evidence must point to:

- A specific message
- A specific document chunk
- A specific external system record
- A manual admin entry

The system must be able to answer:

> Why does the Oracle believe this?

## 2.5 Fully Managed Cloud Architecture

Use a composable managed architecture:

- Vercel for frontend / route handlers
- Supabase Cloud for Postgres, Storage, Realtime, Auth
- Trigger.dev Cloud for background workers

Do not write Dockerfiles.  
Do not configure VPS reverse proxies.  
Do not introduce self-managed infrastructure.

---

# PART 3: INFRASTRUCTURE & TECHNOLOGY STACK

## 3.1 Frontend

- Framework: **Next.js App Router**
- Styling: **Tailwind CSS**
- Component library: **shadcn/ui**
- Icons: **lucide-react**
- Hosting: **Vercel**

## 3.2 Database, Storage, Realtime

- Database: **Supabase Cloud PostgreSQL**
- Vector search: **pgvector**
- Realtime: **Supabase Realtime**
- Storage: **Supabase Storage**
- ORM: **Drizzle ORM**

## 3.3 AI Layer & Provider Strategy

- **AI Architecture:** Provider-Native Adapter Pattern (`OracleAIClient -> ContextCompiler -> ModelRouter -> Adapters`).
- **Primary SDKs:** Direct APIs (`@anthropic-ai/sdk`, `openai`, `@google/genai`). OpenRouter is deprecated and reserved only for temporary experimental model scouting.
- **Roles:** The system enforces strictly 3 production roles (Interview, Extraction, Synthesis), with exactly one Primary and one Fallback route defined per role.
- **Background workers:** Trigger.dev Cloud v3.

## 3.4 Connection Rules

### Browser Code

Browser code must never use raw Postgres connection strings.

Browser code may use the Supabase client with RLS-protected access.

The browser must never receive:

- Supabase service role key
- Direct Postgres connection string
- Trigger.dev secrets
- OpenRouter API key

### Vercel Route Handlers

Vercel serverless route handlers should use one of:

- Supabase Data API
- Supavisor Transaction Pooler, with prepared statements disabled if applicable

If Drizzle is used from Vercel route handlers through transaction pooling, prepared statements must be disabled or avoided.

If this becomes painful, use Supabase Data API for route handlers and reserve direct Drizzle/Postgres connections for Trigger.dev and migrations.

### Trigger.dev Workers

Trigger.dev workers should use:

- Direct Supabase Postgres connection if IPv6 works
- Session Pooler if direct connection is not available

Trigger.dev workers use privileged backend credentials and may bypass RLS.

### Drizzle Migrations

Drizzle migrations must use the Direct Postgres connection string.

---

# PART 4: AUTHENTICATION & IDENTITY MODEL

## 4.1 Required Login Providers

The Oracle must support these login providers:

1. **Microsoft 365 / Microsoft Entra ID**
2. **Google OAuth**
3. **Authentik OIDC** for internal accounts

## 4.2 Supabase Auth Is the Application Session Layer

Do not build three separate login systems.

Use this identity flow:

```text
Microsoft 365 / Google / Authentik
        ↓
Supabase Auth
        ↓
auth.users.id
        ↓
employees.authUserId
        ↓
RLS policies + application authorization
```

The identity provider proves who the user is.

The `employees` table decides whether that authenticated user is authorized to use Oracle and what they can access.

## 4.3 Employee Authorization Roster

Every human user must map to exactly one row in `employees`.

The `employees` table is the Oracle authorization roster.

Required fields:

- `authUserId`: maps to `auth.users.id`
- `email`: unique email address used for initial linking
- `authProvider`: `microsoft`, `google`, or `authentik`
- `authProviderSubject`: stable provider-side user ID
- `isAdmin`: controls Oracle admin privileges
- `disabledAt`: disables access without deleting history

## 4.4 First Login / Account Linking

Do not let arbitrary Microsoft, Google, or Authentik users create Oracle employee accounts.

First-login rule:

1. Admin creates an `employees` row with approved email address.
2. Employee signs in with Microsoft, Google, or Authentik.
3. Supabase Auth completes login and returns `auth.users.id`.
4. Server-side callback checks the verified provider email.
5. If the verified email matches an existing `employees.email` row and `disabledAt` is null:
   - Set `employees.authUserId` if empty.
   - Store provider metadata.
   - Update `lastLoginAt`.
   - Allow access.
6. If no employee row exists:
   - Deny access.
   - Show: “Your account is not approved for Oracle.”

After first linking, RLS and authorization must rely on `authUserId`, not email.

Email is allowed for first-linking only. Emails can change. `authUserId` is the durable application identity.

## 4.5 Provider Notes

### Microsoft 365

Use Microsoft Entra ID OAuth through Supabase Auth.

Microsoft login must be restricted to the company’s approved Microsoft tenant/domain. Consumer Microsoft accounts must not be accepted unless explicitly approved.

### Google OAuth

Use Google OAuth through Supabase Auth.

Do not assume any Google account is allowed. Access is still controlled by the `employees` table allowlist.

### Authentik OIDC

Use Authentik as an OIDC provider for internal accounts.

Authentik is for:

- Internal accounts not covered by Microsoft or Google
- Contractors if needed
- Service-like human accounts if needed

## 4.6 Employee Invites

Magic-link tokens are not the primary authentication system.

If invitation links are needed, use `employee_invites`. These are onboarding/bootstrap tokens only.

They should direct the user to sign in with Microsoft, Google, or Authentik.

---

# PART 5: CORE ENGINES

## 5.1 Interjection Engine

The Oracle observes group chats and intervenes only when tactful and strategically valuable.

### Rule 1: Contradiction Watcher

On new user messages:

1. Run cheap vector retrieval against existing approved claims.
2. If related claims seem misaligned, create a `contradictions` record with status `possible`.
3. Only interject live if confidence and operational impact are very high.
4. Otherwise queue silently for later synthesis or follow-up.

The Oracle should not behave like a referee or police officer. It should behave like a tactful operations consultant.

Safe interjection style:

> “Can I clarify something? Earlier we captured X, but this sounds like Y. Is that an exception, or is the process different in this case?”

### Rule 2: Lull in Conversation

The Oracle may ask a high-priority gap question only when:

- No human has spoken for configured `lull_window_seconds`
- No one is currently typing
- The room has not received an Oracle interjection recently
- The gap is high priority
- The question is relevant to the recent topic

All proactive interjections must be logged in `oracle_interventions`.

## 5.2 Curiosity Engine

If a conversation reveals an unknown workflow, workaround, dependency, system limitation, or exception, the Oracle creates a gap.

A gap is a durable curiosity object.

It includes:

- Question to ask
- Why it matters
- Target employee or department
- Priority
- Related claims or contradictions
- Status

The Oracle may weave open gaps into later conversations.

## 5.3 Ingestion Engine

Uploaded documents must not be ingested as one monolithic text blob.

Documents must be split into `document_chunks`.

Chunks should preserve:

- Page number
- Sheet name
- Row start / end
- Bounding boxes when available
- Raw extracted text
- Content hash
- Token count
- Metadata

Claims extracted from documents must link to specific chunks through `claim_evidence`.

## 5.4 Synthesis Engine

The Oracle Brain is synthesized one section at a time.

The synthesis worker must:

1. Select a brain section.
2. Retrieve approved claims relevant to that section through `claim_domains` and `sectionClaims`.
3. Generate a strict structured diff.
4. Ensure every material statement maps to approved claim IDs.
5. Create a new `brain_section_versions` row.
6. Update `brain_sections.currentVersionId`.
7. Create or resolve gaps and contradictions.
8. Log the model run and job run.

---

# PART 6: MASTER DATABASE SCHEMA

## 6.1 Imports and Enums

```typescript
import {
  pgTable,
  uuid,
  varchar,
  text,
  timestamp,
  integer,
  primaryKey,
  boolean,
  pgEnum,
  jsonb,
  numeric,
  uniqueIndex,
  index,
} from 'drizzle-orm/pg-core';
import { vector } from 'drizzle-orm/pgvector';

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

export type KnowledgeDomain = typeof KNOWLEDGE_DOMAINS[number];
export const knowledgeDomainEnum = pgEnum('knowledge_domain', KNOWLEDGE_DOMAINS);

export const authProviderEnum = pgEnum('auth_provider', [
  'microsoft',
  'google',
  'authentik',
]);

export const messageRoleEnum = pgEnum('message_role', [
  'user',
  'assistant',
  'system',
]);

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

export const oracleInterventionTriggerTypeEnum = pgEnum('oracle_intervention_trigger_type', [
  'direct_mention',
  'possible_contradiction',
  'lull_gap',
  'manual_admin',
  'system_test',
]);

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
```

## 6.2 Settings

```typescript
export const settings = pgTable('settings', {
  key: varchar('key', { length: 100 }).primaryKey(),
  value: jsonb('value').notNull(),
  description: text('description'),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});
```

Required default settings:

```text
lull_window_seconds = 60
oracle_cooldown_minutes = 10
max_oracle_interjections_per_hour = 3
default_interview_model = "anthropic/claude-sonnet-4.6"
default_extraction_model = "google/gemini-flash"
default_synthesis_model = "anthropic/claude-sonnet-4.6"
enable_live_contradiction_interjections = false
enable_group_chat_lull_questions = true
```

## 6.3 Employees and Invites

```typescript
export const employees = pgTable('employees', {
  id: uuid('id').primaryKey().defaultRandom(),

  // Supabase Auth identity mapping
  authUserId: uuid('auth_user_id').unique(),
  email: varchar('email', { length: 320 }).notNull().unique(),
  authProvider: authProviderEnum('auth_provider'),
  authProviderSubject: varchar('auth_provider_subject', { length: 255 }),

  name: varchar('name', { length: 255 }).notNull(),
  role: varchar('role', { length: 255 }).notNull(),
  department: varchar('department', { length: 255 }).notNull(),
  isAdmin: boolean('is_admin').default(false).notNull(),

  disabledAt: timestamp('disabled_at'),
  lastLoginAt: timestamp('last_login_at'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

export const employeeInvites = pgTable('employee_invites', {
  id: uuid('id').primaryKey().defaultRandom(),
  employeeId: uuid('employee_id').references(() => employees.id).notNull(),
  tokenHash: varchar('token_hash', { length: 255 }).notNull().unique(),
  tokenLastFour: varchar('token_last_four', { length: 4 }).notNull(),
  expiresAt: timestamp('expires_at').notNull(),
  usedAt: timestamp('used_at'),
  revokedAt: timestamp('revoked_at'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

## 6.4 Channels, Documents, Messages, Attachments

```typescript
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
    channelId: uuid('channel_id').references(() => channels.id).notNull(),
    employeeId: uuid('employee_id').references(() => employees.id).notNull(),
    joinedAt: timestamp('joined_at').defaultNow().notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.channelId, t.employeeId] }),
    employeeIdx: index('channel_participants_employee_idx').on(t.employeeId),
  })
);

export const documents = pgTable(
  'documents',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    uploaderId: uuid('uploader_id').references(() => employees.id).notNull(),
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
    storageUnique: uniqueIndex('documents_storage_unique').on(t.storageBucket, t.storagePath),
    uploaderIdx: index('documents_uploader_idx').on(t.uploaderId),
  })
);

export const documentChunks = pgTable(
  'document_chunks',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    documentId: uuid('document_id').references(() => documents.id).notNull(),
    chunkIndex: integer('chunk_index').notNull(),
    pageNumber: integer('page_number'),
    sheetName: varchar('sheet_name', { length: 255 }),
    rowStart: integer('row_start'),
    rowEnd: integer('row_end'),
    rawText: text('raw_text').notNull(),
    tokenCount: integer('token_count'),
    contentHash: varchar('content_hash', { length: 255 }),
    embedding: vector('embedding', { dimensions: 1536 }),
    metadataJson: jsonb('metadata_json'),
  },
  (t) => ({
    documentChunkUnique: uniqueIndex('document_chunks_document_chunk_unique').on(t.documentId, t.chunkIndex),
    documentIdx: index('document_chunks_document_idx').on(t.documentId),
  })
);

export const messages = pgTable(
  'messages',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    channelId: uuid('channel_id').references(() => channels.id).notNull(),
    employeeId: uuid('employee_id').references(() => employees.id),
    role: messageRoleEnum('role').notNull(),
    content: text('content').notNull(),

    clientMessageId: varchar('client_message_id', { length: 255 }),
    replyToMessageId: uuid('reply_to_message_id'),
    metadataJson: jsonb('metadata_json'),

    extractionStatus: extractionStatusEnum('extraction_status').default('pending').notNull(),
    extractedAt: timestamp('extracted_at'),
    extractionError: text('extraction_error'),

    editedAt: timestamp('edited_at'),
    deletedAt: timestamp('deleted_at'),
    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    channelCreatedIdx: index('messages_channel_created_idx').on(t.channelId, t.createdAt),
    extractionIdx: index('messages_extraction_idx').on(t.extractionStatus, t.role, t.createdAt),
    clientMessageUnique: uniqueIndex('messages_channel_client_message_unique').on(t.channelId, t.clientMessageId),
  })
);

export const messageAttachments = pgTable('message_attachments', {
  id: uuid('id').primaryKey().defaultRandom(),
  messageId: uuid('message_id').references(() => messages.id).notNull(),
  documentId: uuid('document_id').references(() => documents.id).notNull(),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

## 6.5 Model Runs and Job Runs

`modelRuns` is defined before intelligence tables so other tables can reference it.

```typescript
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
  })
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
    jobStatusStartedIdx: index('job_runs_type_status_started_idx').on(t.jobType, t.status, t.startedAt),
  })
);
```

## 6.6 Claims, Evidence, Brain, Gaps, Contradictions

Developer note: claims intentionally do **not** have a direct `employeeId`.

A claim is a universal operational assertion that may be supported by multiple employees, documents, or external systems.

To query claims by employee, join through `claim_evidence.assertedByEmployeeId`.

```typescript
export const claims = pgTable('claims', {
  id: uuid('id').primaryKey().defaultRandom(),

  // Claim Taxonomy
  claimKind: varchar('claim_kind', { length: 50 }).notNull(), // 'policy', 'observed_practice', 'exception', 'workaround', 'proposed_future_state'
  summary: text('summary').notNull(),
  knowledgeDomain: varchar('knowledge_domain', { length: 100 }).notNull(),
  appliesWhen: text('applies_when'), // Contextual scope for exceptions/workarounds

  // Trust & Provenance
  corroborationTier: varchar('corroboration_tier', { length: 50 }).default('single_source_observed').notNull(),
  impactScore: integer('impact_score').notNull(),
  status: varchar('status', { length: 50 }).notNull(), // pending_review, approved, rejected, archived

  // Freshness & Recertification
  currentAsOf: timestamp('current_as_of').defaultNow().notNull(),
  lastReassertedAt: timestamp('last_reasserted_at'),
  staleAfter: timestamp('stale_after'), // Nullable expiration (e.g., seasonal policy)
  recertificationTrigger: varchar('recertification_trigger', { length: 100 }), // Event that demands review
  recertificationStatus: varchar('recertification_status', { length: 50 }).default('fresh'), // fresh, review_due, stale

  // Lineage
  exceptionOfClaimId: uuid('exception_of_claim_id').references(() => claims.id),
  supersededByClaimId: uuid('superseded_by_claim_id').references(() => claims.id),

  embedding: vector('embedding', { dimensions: 1536 }),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

export const claimDomains = pgTable(
  'claim_domains',
  {
    claimId: uuid('claim_id').references(() => claims.id).notNull(),
    domain: knowledgeDomainEnum('domain').notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.claimId, t.domain] }),
    domainIdx: index('claim_domains_domain_idx').on(t.domain),
  })
);

export const claimEvidence = pgTable(
  'claim_evidence',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    claimId: uuid('claim_id').references(() => claims.id).notNull(),

    sourceType: evidenceSourceTypeEnum('source_type').notNull(),
    sourceMessageId: uuid('source_message_id').references(() => messages.id),
    sourceDocumentChunkId: uuid('source_document_chunk_id').references(() => documentChunks.id),
    sourceExternalRecordId: varchar('source_external_record_id', { length: 255 }),

    assertedByEmployeeId: uuid('asserted_by_employee_id').references(() => employees.id),
    uploadedByEmployeeId: uuid('uploaded_by_employee_id').references(() => employees.id),
    createdByEmployeeId: uuid('created_by_employee_id').references(() => employees.id),

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
    documentChunkIdx: index('claim_evidence_document_chunk_idx').on(t.sourceDocumentChunkId),
  })
);

export const brainSections = pgTable('brain_sections', {
  id: varchar('id', { length: 255 }).primaryKey(),
  knowledgeDomain: knowledgeDomainEnum('knowledge_domain').notNull(),
  relatedDomains: jsonb('related_domains'),
  title: varchar('title', { length: 255 }).notNull(),
  category: varchar('category', { length: 100 }).notNull(),

  // Soft reference to brain_section_versions.id.
  // Must be set via two-step transactional insert.
  currentVersionId: uuid('current_version_id'),

  createdAt: timestamp('created_at').defaultNow().notNull(),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

export const brainSectionVersions = pgTable(
  'brain_section_versions',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    sectionId: varchar('section_id', { length: 255 }).references(() => brainSections.id).notNull(),
    versionNumber: integer('version_number').notNull(),
    markdown: text('markdown').notNull(),
    structuredContent: jsonb('structured_content'),
    changeSummary: text('change_summary').notNull(),
    createdByModelRunId: uuid('created_by_model_run_id').references(() => modelRuns.id),

    reviewStatus: brainSectionReviewStatusEnum('review_status').default('draft').notNull(),
    reviewedByEmployeeId: uuid('reviewed_by_employee_id').references(() => employees.id),
    reviewedAt: timestamp('reviewed_at'),

    createdAt: timestamp('created_at').defaultNow().notNull(),
  },
  (t) => ({
    sectionVersionUnique: uniqueIndex('brain_section_versions_section_version_unique').on(t.sectionId, t.versionNumber),
    sectionVersionIdx: index('brain_section_versions_section_version_idx').on(t.sectionId, t.versionNumber),
  })
);

export const sectionClaims = pgTable(
  'section_claims',
  {
    sectionId: varchar('section_id', { length: 255 }).references(() => brainSections.id).notNull(),
    claimId: uuid('claim_id').references(() => claims.id).notNull(),
  },
  (t) => ({
    pk: primaryKey({ columns: [t.sectionId, t.claimId] }),
    claimIdx: index('section_claims_claim_idx').on(t.claimId),
  })
);

export const contradictions = pgTable(
  'contradictions',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    claimAId: uuid('claim_a_id').references(() => claims.id).notNull(),
    claimBId: uuid('claim_b_id').references(() => claims.id).notNull(),
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
    statusSeverityIdx: index('contradictions_status_severity_idx').on(t.status, t.severity),
  })
);

export const gaps = pgTable(
  'gaps',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    gapType: varchar('gap_type', { length: 50 }).notNull(),
    sectionId: varchar('section_id', { length: 255 }).references(() => brainSections.id),
    relatedClaimIds: jsonb('related_claim_ids'),
    relatedContradictionId: uuid('related_contradiction_id').references(() => contradictions.id),
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
  })
);

export const oracleInterventions = pgTable('oracle_interventions', {
  id: uuid('id').primaryKey().defaultRandom(),
  channelId: uuid('channel_id').references(() => channels.id).notNull(),
  triggerType: oracleInterventionTriggerTypeEnum('trigger_type').notNull(),
  relatedGapId: uuid('related_gap_id').references(() => gaps.id),
  relatedContradictionId: uuid('related_contradiction_id').references(() => contradictions.id),
  relatedMessageId: uuid('related_message_id').references(() => messages.id),
  interjectionMessageId: uuid('interjection_message_id').references(() => messages.id),
  confidence: integer('confidence'),
  impactScore: integer('impact_score'),
  wasLiveInterjection: boolean('was_live_interjection').notNull(),
  reason: text('reason'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});
```

## 6.7 Brain Section Creation Note

Brain section creation must be a two-step transactional operation:

1. Insert `brain_sections` row with `currentVersionId = null`.
2. Insert first `brain_section_versions` row referencing the section.
3. Update `brain_sections.currentVersionId` to the version row.

Do not attempt to insert both sides of the circular relationship in one naive insert.

## 6.8 Required SQL Check Constraints

Drizzle may not express every constraint cleanly. Add raw SQL migrations where needed.

### Claim Evidence Source Constraint

Enforce:

- If `sourceType = 'message'`, `sourceMessageId` must be non-null.
- If `sourceType = 'document_chunk'`, `sourceDocumentChunkId` must be non-null.
- If `sourceType = 'external_system'`, `sourceExternalRecordId` must be non-null.
- If `sourceType = 'manual_admin'`, `createdByEmployeeId` must be non-null.

Pseudo-SQL:

```sql
ALTER TABLE claim_evidence
ADD CONSTRAINT claim_evidence_source_check
CHECK (
  (source_type = 'message' AND source_message_id IS NOT NULL)
  OR
  (source_type = 'document_chunk' AND source_document_chunk_id IS NOT NULL)
  OR
  (source_type = 'external_system' AND source_external_record_id IS NOT NULL)
  OR
  (source_type = 'manual_admin' AND created_by_employee_id IS NOT NULL)
);
```

## 6.9 Vector Indexes

Apply once there is enough data to justify vector indexing:

```sql
CREATE INDEX claims_embedding_hnsw_idx
ON claims
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX document_chunks_embedding_hnsw_idx
ON document_chunks
USING hnsw (embedding vector_cosine_ops);
```

---

# PART 7: ROW LEVEL SECURITY

## 7.1 RLS Identity Helpers

Create helper functions.

```sql
CREATE OR REPLACE FUNCTION public.current_employee_id()
RETURNS uuid
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT id
  FROM employees
  WHERE auth_user_id = auth.uid()
    AND disabled_at IS NULL
  LIMIT 1
$$;

CREATE OR REPLACE FUNCTION public.current_employee_is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT COALESCE(is_admin, false)
  FROM employees
  WHERE auth_user_id = auth.uid()
    AND disabled_at IS NULL
  LIMIT 1
$$;
```

## 7.2 RLS Policy Requirements

Enable RLS before employee rollout.

### Employees

- Employee can read self.
- Admin can read all.
- Service role can read/write all.

### Channels

- Employee can read a channel if they are in `channel_participants`.
- Admin can read all.

### Channel Participants

- Employee can read participant rows for channels they belong to.
- Admin can read all.

### Messages

- Employee can read messages if participant in channel.
- Employee can insert user messages only as themselves.
- Employee cannot insert assistant/system messages.
- Employee cannot modify other users’ messages.
- Admin can read all.

### Documents

- Uploader can read own uploaded document metadata.
- Participants can read documents attached to messages in their channels.
- Admin can read all.

### Intelligence Tables

The following are admin/service only:

- `claims`
- `claim_evidence`
- `brain_sections`
- `brain_section_versions`
- `section_claims`
- `gaps`
- `contradictions`
- `model_runs`
- `job_runs`
- `oracle_interventions`

Employee chat UI receives relevant context only through server-side Oracle route handlers.

## 7.3 Admin View Security

Admin dashboard views must not accidentally bypass RLS.

Use one of:

1. Keep admin views in a non-exposed schema and access only through privileged server routes.
2. Create views with `security_invoker = true` where appropriate and lock grants down carefully.

Default recommendation: access admin views only through privileged server routes.

---

# PART 8: REQUIRED ADMIN VIEWS

Create these Postgres views to simplify Admin Dashboard queries:

- `employee_claims`
- `section_claims_with_evidence`
- `open_gaps_by_employee`
- `claims_pending_review_with_evidence`
- `latest_brain_sections`
- `contradictions_with_claim_summaries`
- `claims_with_primary_evidence`

Critical view:

```sql
CREATE VIEW claims_with_primary_evidence AS
SELECT
  c.id,
  c.summary,
  c.claim_type,
  c.status,
  c.impact_score,
  c.confidence_score,
  ce.exact_quote,
  ce.asserted_by_employee_id,
  ce.source_message_id,
  ce.source_document_chunk_id
FROM claims c
LEFT JOIN LATERAL (
  SELECT *
  FROM claim_evidence ce
  WHERE ce.claim_id = c.id
  ORDER BY ce.confidence DESC NULLS LAST, ce.created_at ASC
  LIMIT 1
) ce ON true;
```

---

# PART 9: APPLICATION WORKFLOWS

## 9.1 Live Chat / Interview Route

Route:

```text
app/api/chat/route.ts
```

Use:

- Next.js Route Handler
- `OracleAIClient` (interview role) for streaming chat responses
- Provider-native adapter (target); legacy OpenRouter path while retrofit is in progress

Retrieval constraint:

Fetch only:

- Recent conversation context
- Employee profile
- Highest-priority open gaps
- Small number of strictly relevant claims
- System prompt

Do not load giant sections of the company Brain into every chat turn.

## 9.2 Tool Calling

Provide tools:

### `search_company_knowledge`

Searches approved claims and relevant brain sections.

Must filter by:

- `claim_domains`
- `brain_sections.knowledgeDomain`
- `brain_sections.relatedDomains`
- semantic similarity
- relevance to current channel / employee context

### `check_open_gaps`

Returns open gaps targeted to:

- current employee
- current department
- current channel context

The Oracle may weave these questions into conversation naturally.

## 9.3 Contradiction Watcher

Trigger:

- New message where `role = 'user'`

Workflow:

1. Run cheap vector retrieval against approved claims.
2. If possible misalignment exists, create `contradictions` row with status `possible`.
3. Decide whether to:
   - silently queue
   - create a gap
   - request admin review
   - live interject
4. Log decision in `oracle_interventions` if any intervention occurs.

Most possible contradictions should **not** cause live interjections.

## 9.4 Claim Extraction Worker

Trigger:

- Cron schedule, for example every 4 hours or nightly

Query:

```text
messages where extractionStatus = 'pending' and role = 'user'
```

Workflow:

1. Group messages by channel / employee / conversation segment.
2. Extract operational claims.
3. Populate `claims`, `claim_domains`, and `claim_evidence`.
4. Validate exact quotes.
5. Mark messages `complete`, `failed`, or `skipped`.

Triage:

Auto-approve only if:

- Exact quote is validated
- Claim type is low-risk
- No contradiction found
- Impact score <= 6

Pending review if:

- Impact >= 7
- Contradiction detected
- Claim affects future PM-system requirements
- Claim names a person as a bottleneck
- Claim implies customer/licensor risk
- OCR/document confidence is low

## 9.5 Group Chat Extraction Semantics

Group chat extraction must distinguish:

- Claim stated
- Claim confirmed
- Claim challenged
- Claim refined
- Exception introduced
- Process ambiguity revealed

Example:

```text
Employee A: We always send that to China after licensor approval.
Employee B: Not always. For Walmart seasonal, sourcing sees it earlier.
```

This should produce:

- General process claim
- Exception claim
- Possible contradiction or refinement
- Gap asking when the exception applies

Do not flatten group conversation into isolated single-speaker facts.

## 9.6 Document Ingestion Worker

Trigger:

- New document row / upload event

Workflow:

1. Upload document and create row.
2. Parse document into chunks.
3. Store `document_chunks`.
4. Use `contentHash` for deduplication.
5. Embed chunks.
6. Extract claims from chunks.
7. Link claims to chunk-level `claim_evidence`.
8. Mark document complete or failed.

## 9.7 Brain Synthesis Worker

Trigger:

- Approved claims
- Scheduled maintenance
- Manual admin trigger

Workflow:

1. Select one brain section.
2. Retrieve relevant approved claims through `claim_domains` and `sectionClaims`.
3. Generate structured synthesis output.
4. Validate all IDs.
5. Validate traceability.
6. Create new `brain_section_versions` row.
7. Update `brain_sections.currentVersionId`.
8. Emit gaps and contradictions.
9. Log model run and job run.

## 9.8 Synthesis Output Format

The synthesis model must produce structured output. Do not rely only on freeform Markdown.

Required shape:

```json
{
  "sectionId": "creative_to_technical_handoff",
  "paragraphs": [
    {
      "text": "Technical design often receives artwork without complete production context.",
      "supportingClaimIds": ["claim_uuid_1", "claim_uuid_2"]
    }
  ],
  "updatedMarkdown": "...",
  "materialChanges": [
    {
      "type": "added_claim",
      "claimId": "claim_uuid_1",
      "reason": "New evidence from technical design described missing context in art files."
    }
  ],
  "claimsAdded": [],
  "claimsRemoved": [],
  "claimsStrengthened": [],
  "claimsWeakened": [],
  "newContradictions": [],
  "resolvedContradictions": [],
  "newGaps": [],
  "resolvedGaps": [],
  "confidenceChange": "increased",
  "requiresHumanReview": true
}
```

Validation constraint:

A synthesis job may not update a brain section unless every material paragraph or bullet maps to approved claim IDs.

Backend validator must check:

- Section ID exists.
- All claim IDs exist.
- All claim IDs are approved.
- New gaps include `whyItMatters`.
- Contradictions point to real claim IDs.
- Markdown contains no unsupported named people, systems, customers, stages, departments, or process rules.
- If validation fails, do not update current brain section. Save job failure details.

---

# PART 10: MASTER SYSTEM PROMPT

Use this prompt when initializing the Oracle conversation.

```text
You are the “Operations Oracle” for POP Creations / Spruce Line, a high-volume home decor company.

Your ultimate goal is to map the “dark matter” of this company: informal rules, hidden bottlenecks, missing context in handoffs, undocumented workarounds, system limitations, and operational dependencies across all departments.

You are not a task manager. You are not here to assign blame. You are here to understand how the company actually works.

PERSONALITY:
- You are a highly intelligent, intensely curious, clinical-when-analyzing Chief Operating Officer.
- You are warm and friendly without being long-winded.
- You are empathetic but focused on operational reality.
- Your tone is concise.
- Ask one tightly scoped question at a time.

INVESTIGATIVE TACTICS:

1. ROOT CAUSE RULE:
If an employee mentions a problem, pull the thread to find the systemic root cause.
Example: If a handoff fails, ask what specific system field, document, meeting, person, or approval was supposed to facilitate it.

2. SYSTEM VS. REALITY RULE:
Always look for the delta between the official process and the real process.
If someone uses a personal spreadsheet, ask why they had to build it and what exact data the official system fails to show.

3. DEPENDENCY RULE:
If the conversation touches another department, follow it.
Ask how the handoff occurs, what system mediates it, and what information tends to get lost.

4. PSYCHOLOGICAL SAFETY RULE:
Do not make employees feel blamed.
Investigate systems, handoffs, unclear ownership, missing context, and system limitations — not personal failure.
When employees disagree, treat disagreement as evidence of process ambiguity, not as someone being wrong.
If a question could sound accusatory, rephrase it around missing information, unclear ownership, or system limitations.
When discussing something another employee said, anonymize it unless explicitly permitted.
Use neutral process language.

5. GROUP CHAT RULES:
Do not interrupt human-to-human conversation unnecessarily.
Only interject proactively if:
- A major contradiction is detected, or
- There is a natural lull, no one is typing, and there is a high-priority knowledge gap relevant to the recent topic.
If directly mentioned, respond immediately using your tools.

OUTPUT CONSTRAINTS:
- Never ask more than one question in a single message.
- Validate valuable answers briefly before moving on.
- Do not write essays to employees.
- Prefer sharp operational questions over summaries.
```

---

# PART 11: PHASED IMPLEMENTATION PLAN

Implement sequentially. Stop after each phase for verification.

## Phase 1: Foundation

Tasks:

1. Initialize Turborepo / Next.js App Router.
2. Install Tailwind, shadcn/ui, lucide-react.
3. Configure Supabase project.
4. Configure Supabase Auth providers:
   - Microsoft 365 / Entra ID
   - Google OAuth
   - Authentik OIDC
5. Create Supabase Storage bucket:
   - `company_documents`
6. Implement Drizzle schema.
7. Generate migrations.
8. Add raw SQL constraints and helper functions.
9. Enable RLS.
10. Add RLS policies.
11. Seed settings.
12. Seed employees.

Acceptance gate:

- Employee can authenticate through at least one provider.
- Unknown user is denied.
- Known employee links to `employees.authUserId`.
- RLS prevents employees from seeing channels they do not belong to.
- Admin can access admin-only data through server route.

## Phase 2: Multi-Player UI and Realtime

Tasks:

1. Build chat UI.
2. Build group room UI.
3. Build 1:1 room UI.
4. Build document upload component.
5. Implement Supabase Realtime subscriptions.
6. Implement typing/presence tracking.
7. Build initial Admin Dashboard:
   - employees
   - channels
   - messages
   - documents
   - claims placeholder
   - gaps placeholder
   - contradictions placeholder

Acceptance gate:

- Two employees can chat in same room.
- Employee cannot see a room they are not in.
- Document upload creates document row and storage object.
- Message attachments preserve upload context.
- Admin can view transcripts.

## Phase 3: Basic Oracle Chat

Tasks:

1. Implement `app/api/chat/route.ts`.
2. Use `OracleAIClient` interview role (streaming via provider-native adapter).
3. Add master system prompt.
5. Implement direct mention response.
6. Implement basic tools:
   - `search_company_knowledge`
   - `check_open_gaps`

Acceptance gate:

- Oracle responds when directly addressed.
- Oracle asks one question at a time.
- Oracle does not load large brain context.
- Oracle respects psychological safety prompt.

## Phase 4: Trigger.dev Intelligence Workers

Tasks:

1. Initialize Trigger.dev.
2. Implement `jobRuns`.
3. Implement `modelRuns`.
4. Implement claim extraction worker.
5. Implement exact quote validation.
6. Implement document ingestion worker.
7. Implement chunking and embeddings.
8. Implement contradiction watcher.
9. Implement synthesis worker.

Acceptance gate:

- Messages become claims with evidence.
- Invalid quotes are rejected.
- Documents produce chunks.
- Claims link to document chunks.
- Possible contradictions are created but do not automatically interrupt.
- Synthesis creates a versioned brain section.

## Phase 5: Admin Review and Brain Dashboard

Tasks:

1. Build claims review queue.
2. Build evidence viewer.
3. Build gaps dashboard.
4. Build contradictions dashboard.
5. Build brain sections viewer.
6. Build model/job run observability dashboard.
7. Build settings editor.

Acceptance gate:

- Albert can approve/reject claims.
- Albert can see supporting evidence.
- Albert can view open gaps by employee.
- Albert can inspect model cost and errors.
- Albert can review brain section versions.

## Phase 6: Controlled Interjection Engine

Tasks:

1. Implement lull detection.
2. Implement cooldown rules.
3. Implement high-priority gap interjections.
4. Implement contradiction interjection only for very high confidence/high impact.
5. Log all interventions.

Acceptance gate:

- Oracle does not interrupt too often.
- All interventions are logged.
- Live interjections can be disabled from settings.
- Admin can audit why each intervention happened.

---

# PART 12: EVALUATION GATES

Before broad employee rollout, create a gold-standard evaluation set from 3–5 known transcripts.

Manually define:

- Expected claims
- Expected evidence quotes
- Expected gaps
- Expected contradictions
- Expected brain-section updates

Track:

- Claim extraction precision
- Claim extraction recall
- Evidence quote validity
- Wrong-domain rate
- Duplicate-claim rate
- False contradiction rate
- Brain section usefulness
- Albert usefulness rating

Initial pre-rollout targets:

```text
Evidence quote validity: 98%+
Wrong-domain rate: under 10%
Duplicate claim rate: under 15%
False contradiction rate: under 20% initially
Albert usefulness rating for brain sections: 4/5 or better
```

Do not broaden rollout until the Oracle produces useful, evidence-backed output on known transcripts.

---

# PART 13: FINAL IMPLEMENTATION PRINCIPLE

The Oracle should feel like a living company brain.

Internally, it must be:

```text
versioned
evidence-backed
claim-based
section-synthesized
traceable
auditable
secure
measurable
```

The system succeeds only if Albert can ask:

> “Why does the Oracle believe this?”

And the system can answer:

> “Because these specific employees said these specific things, in these specific messages or documents, and these claims were later synthesized into this brain section.”
