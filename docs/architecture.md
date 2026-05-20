# Architecture

System design for The Oracle. For business context and the operating philosophy, read `oracle_master_spec.md` Parts 1–2. For the developer-facing map, read `AGENTS.md`.

## Components

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              Identity providers                             │
│  Microsoft Entra (TODO)     Google OAuth (TODO)     Authentik OIDC (TODO)   │
│  Supabase email magic-link (current dev stub, auth_provider='magic_link_dev')│
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   ↓
                            Supabase Auth
                            (auth.users)
                                   ↓
                       employees.auth_user_id linker
                       (packages/auth/src/link.ts)
                                   ↓
┌──────────────────┐    ┌────────────────────────┐    ┌──────────────────────┐
│   apps/web       │    │   Supabase Postgres    │    │   apps/workers       │
│   Next.js 15     │◄──►│  + pgvector + RLS      │◄──►│   Trigger.dev v3     │
│   App Router     │    │                        │    │                      │
│   Vercel Fluid   │    │  Schema in             │    │  - claim extraction  │
│   Compute        │    │  packages/db/src/      │    │  - doc ingestion     │
│                  │    │  schema.ts             │    │  - contradiction     │
│  /channels/...   │    │                        │    │    watcher           │
│  /admin/...      │    │  RLS, constraints,     │    │  - brain synthesis   │
│  /api/chat       │    │  views in              │    │                      │
│                  │    │  migrations/sql/*.sql  │    │  Each task writes    │
│                  │    │                        │    │  job_runs +          │
│                  │    │                        │    │  model_runs rows.    │
└────────┬─────────┘    └────────────────────────┘    └──────┬───────────────┘
         │                          ▲                        │
         │                          │                        │
         │                  ┌───────┴────────┐               │
         │                  │  Supabase      │               │
         │                  │  Storage       │               │
         │                  │  bucket:       │               │
         │                  │  company_documents             │
         │                  └────────────────┘               │
         │                                                   │
         │      ┌──────────────────────────────┐             │
         └─────►│  Supabase Realtime           │◄────────────┘
                │  - postgres_changes(messages)│
                │  - presence (typing)         │
                └──────────────────────────────┘
                            ↓
                  Browser chat UI
                  (channel-chat.tsx)

         ┌──────────────────────────────────────┐
         │           LLM providers              │
         │  OpenRouter (chat / extraction /     │
         │  synthesis) — default models in      │
         │  settings table                      │
         │  OpenAI text-embedding-3-small       │
         │  (embeddings only)                   │
         └──────────────────────────────────────┘
                             ▲
                             │
                   packages/ai wrappers
                   (openrouter.ts, embeddings.ts,
                    retrieval.ts, prompts/)
```

## Data flow — the load-bearing paths

### 1. Employee sends a message

1. Browser inserts into `messages` via the Supabase client (RLS enforced — must be participant of the channel).
2. Supabase Realtime fan-outs `postgres_changes` to other participants.
3. If the message starts with `@oracle` (or `oracle,`), the client calls `POST /api/chat` (see flow 2).
4. The message row sits with `extraction_status='pending'`. The claim extraction worker (Phase 4) picks it up later.

### 2. `@oracle` mention → chat response

1. `POST /api/chat` receives `{channelId, employeeId, message}`.
2. The route assembles a minimal retrieval bundle: recent N messages from the channel, employee profile, top open gaps for this employee/department, top semantically-relevant approved claims (pgvector cosine).
3. Calls Vercel AI SDK `streamText` with the Part 10 system prompt + the retrieval bundle. Model is `settings.default_interview_model` (default `anthropic/claude-sonnet-4.6`) via OpenRouter.
4. Tools exposed: `search_company_knowledge`, `check_open_gaps` — both Zod-validated, both backed by `packages/ai/src/retrieval.ts`.
5. On completion: inserts the assistant message into `messages` and writes a `model_runs` row with cost/latency/tokens.

### 3. Document upload

1. Browser uploads file to Supabase Storage bucket `company_documents`.
2. Creates a `documents` row (`status='pending_processing'`).
3. Creates a `message_attachments` row linking the document to the message that referenced it.
4. The document ingestion worker (Phase 4) picks up `status='pending_processing'`, chunks the file into `document_chunks`, embeds them, then runs claim extraction over the chunks.

### 4. Claim extraction (worker — Phase 4 scaffold)

1. Cron-scheduled. Queries `messages where extraction_status='pending' AND role='user'`.
2. Groups by channel/employee/conversation segment.
3. Calls the LLM with extraction prompt.
4. Validates exact quotes against the source text — invalid quotes are rejected.
5. Inserts `claims` + `claim_domains` + `claim_evidence` rows. Status either `pending_review` or `approved` based on triage (spec 9.4).
6. Marks source messages `complete`, `failed`, or `skipped`.

### 5. Synthesis (worker — Phase 4 scaffold)

1. Triggered by new approved claims OR scheduled maintenance OR manual admin trigger.
2. Selects one brain section. Retrieves approved claims via `claim_domains` and `section_claims`.
3. Generates the structured output specified in spec 9.8 (paragraphs with `supportingClaimIds`, lists of changes, etc.).
4. Validator rejects the run if any material paragraph doesn't map to approved claim IDs.
5. On success: inserts a new `brain_section_versions` row and updates `brain_sections.current_version_id` (two-step transaction per spec 6.7).

### 6. Interjection engine (Phase 6 — not yet implemented)

Lull detection and contradiction-watcher rules are scaffolded as JSDoc in `packages/oracle-engines/src/interjection.ts`. See spec Part 5.1.

## Major constraints

- **Postgres is the only source of truth.** No Redis, no file-based memory, no in-process AI memory. Every durable bit of state lives in a row.
- **Traceability is the product.** Every claim links to ≥1 `claim_evidence` row. Worker validators enforce exact-quote integrity.
- **No containers, no VPS.** Vercel + Supabase + Trigger.dev. Spec Part 2.5.
- **RLS first, application authorization second.** Browser code uses the anon key + RLS. Server routes use the service-role key only where it's documented and necessary.
- **`auth_user_id` is the durable identity** after first login. Email is the linker only; emails can change.
- **Embeddings dimension is 1536** and locked. Changing it requires re-embedding everything. See AGENTS.md §11.

## Module dependency graph

```
packages/shared
   ↑   ↑       ↑
   │   │       │
packages/db ──→ packages/auth
   ↑   ↑           ↑
   │   │           │
packages/ai ───────┘
   ↑
   │
packages/oracle-engines
   ↑
   │
apps/web ───────────────→ apps/workers
   (no app-to-app deps; both depend on packages)
```

- `packages/shared` has zero internal deps.
- `packages/db` depends on `shared`.
- `packages/auth` depends on `db` + `shared`.
- `packages/ai` depends on `db` + `shared`.
- `packages/oracle-engines` depends on `db` + `shared`.
- `apps/web` depends on all packages.
- `apps/workers` depends on `db`, `shared`, `ai`.

Workers must not import from `apps/web`, and vice versa.

## Where each spec part is implemented

| Spec part | Implemented in |
|---|---|
| Part 4 (auth) | `packages/auth/`, `apps/web/app/auth/callback/route.ts`, `apps/web/app/denied/` |
| Part 5.1 (interjection) | `packages/oracle-engines/src/interjection.ts` (scaffold) |
| Part 5.2 (curiosity / gaps) | `packages/db/src/schema.ts` (`gaps` table) + worker (Phase 4 scaffold) |
| Part 5.3 (ingestion) | `apps/workers/src/trigger/document-ingestion.ts` (scaffold) |
| Part 5.4 (synthesis) | `apps/workers/src/trigger/brain-synthesis.ts` (scaffold) |
| Part 6 (schema) | `packages/db/src/schema.ts` |
| Part 6.8 (CHECK constraints) | `packages/db/migrations/sql/10_check_constraints.sql` |
| Part 6.9 (vector indexes) | `packages/db/migrations/sql/99_vector_indexes.sql` |
| Part 7 (RLS) | `packages/db/migrations/sql/20_rls_helpers.sql`, `21_rls_policies.sql` |
| Part 8 (admin views) | `packages/db/migrations/sql/30_admin_views.sql` |
| Part 9.1 (chat route) | `apps/web/app/api/chat/route.ts` + `packages/ai/src/retrieval.ts` |
| Part 9.2 (tools) | `apps/web/app/api/chat/route.ts` |
| Part 10 (system prompt) | `packages/ai/src/prompts/oracle-system.ts` (verbatim) |
