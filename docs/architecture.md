# Architecture

System design for The Oracle. For business context and the operating philosophy, read `oracle_master_spec.md` Parts 1–2. For the developer-facing map, read `AGENTS.md`.

## Components

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              Identity providers                             │
│   Microsoft Entra (popcre tenant)      Google OAuth                         │
│   Supabase email magic-link  ← Brevo SMTP    Authentik OIDC (TODO)          │
└──────────────────────────────────┬─────────────────────────────────────────┘
                                   ↓
                            Supabase Auth
                            (auth.users)
                                   ↓
                  packages/auth/src/link.ts (linker)
                                   ↓
            ┌──────────────────────┴──────────────────────┐
            ↓                                             ↓
   employee_identities                              employees
   (one row per employee × provider)               (authorization roster)
            │                                             │
            └─────────── joined via employee_id ──────────┘

┌──────────────────┐    ┌────────────────────────┐    ┌──────────────────────┐
│   apps/web       │    │   Supabase Postgres    │    │   apps/workers       │
│   Next.js 16     │◄──►│  + pgvector + RLS      │◄──►│   Trigger.dev v3     │
│   App Router     │    │                        │    │                      │
│   Vercel Fluid   │    │  Schema in             │    │  - claim extraction  │
│   Compute        │    │  packages/db/src/      │    │  - doc ingestion     │
│                  │    │  schema.ts             │    │  - contradiction     │
│  /channels/...   │    │                        │    │    watcher           │
│  /admin/...      │    │  RLS, constraints,     │    │  - brain synthesis   │
│  /api/chat       │    │  views, data migs in   │    │                      │
│  /auth/...       │    │  migrations/sql/*.sql  │    │  Each task writes    │
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
         │  Current (legacy):                   │
         │    OpenRouter (chat / extraction /   │
         │    synthesis) — default models in    │
         │    settings table                    │
         │  Target (AI retrofit, R1+):          │
         │    Anthropic direct                  │
         │    Google Vertex / Gemini direct     │
         │    OpenAI direct                     │
         │  Embeddings (unchanged):             │
         │    OpenAI text-embedding-3-small     │
         └──────────────────────────────────────┘
                             ▲
                             │
                   packages/ai
                   Current files: openrouter.ts,
                   embeddings.ts, retrieval.ts,
                   prompts/oracle-system.ts.
                   Target files (R1–R2, not yet
                   present): routes/, oracle-ai-
                   client.ts, model-router.ts,
                   providers/{anthropic,vertex-gemini,
                   openai}-adapter.ts.
```

The "current" path is what production actually runs today. The "target" path is what `docs/oracle/02-provider-native-ai-architecture.md` mandates and what R1+ will build. Until R8 lands, `apps/web/app/api/chat/route.ts` still goes through OpenRouter via the Vercel AI SDK — that is current technical debt, not the intended architecture.

## Identity model

One human → one `employees` row → many `employee_identities` rows.

- `employees.email` is the **primary contact** for the human (used for display, admin contact, and first-login bootstrap).
- `employee_identities` is the authoritative source for `(auth_provider, auth_user_id)`. Supabase Auth identifies the user; the linker maps that Supabase user to the employee row through this table.
- The linker resolves a session by `(auth_provider, auth_user_id)` first. On miss it bootstraps by matching the verified provider email against `employees.email` OR any existing `employee_identities.email` row, then creates a new identity. See `packages/auth/src/link.ts`.
- The RLS helper `current_employee_id()` joins `employees` with `employee_identities` on `auth.uid()` — RLS does not read `employees.auth_user_id` directly.
- Deprecated columns `employees.auth_user_id`, `employees.auth_provider`, `employees.auth_provider_subject` remain on the schema as NULL placeholders during the multi-identity transition. They will be dropped in a follow-up migration. See `DECISIONS.md` D2.multi-identity.

## Data flow — the load-bearing paths

### 1. Employee sends a message

1. Browser inserts into `messages` via the Supabase client (RLS enforced — must be a participant of the channel).
2. Supabase Realtime fan-outs `postgres_changes` to other participants.
3. If the message starts with `@oracle` (or `oracle,`), the client calls `POST /api/chat` (see flow 2).
4. The message row sits with `extraction_status='pending'`. The claim extraction worker (Phase 4) picks it up later.

### 2. `@oracle` mention → chat response

1. `POST /api/chat` receives `{ channelId }`. The employee is resolved server-side from the Supabase session cookie — the client does not pass an employee ID.
2. The route resolves the requester's `employees` row through `employee_identities` (matches `auth.uid()` from the Supabase session). Verifies the requester is a participant of `channelId`.
3. Assembles a minimal retrieval bundle: recent N messages, employee profile, top open gaps for this employee/department, top semantically-relevant approved claims (pgvector cosine).
4. Calls the Vercel AI SDK with the spec Part 10 system prompt + the retrieval bundle. Model is `settings.default_interview_model` (default `deepseek/deepseek-v4-pro`) via OpenRouter. Image/file parts are stripped for text-only models before the LLM call.
5. Tools exposed: `search_company_knowledge`, `check_open_gaps` — both Zod-validated, both backed by `packages/ai/src/retrieval.ts`.
6. On completion: inserts the assistant message into `messages` and writes a `model_runs` row with cost/latency/tokens.

### 3. Document upload

1. Browser uploads file to Supabase Storage bucket `company_documents`.
2. Creates a `documents` row (`status='pending_processing'`).
3. Creates a `message_attachments` row linking the document to the message that referenced it.
4. After the upload completes, the client triggers `POST /api/chat` — same Oracle reply flow as flow 2. In DMs this always fires; in group chats it fires only when the upload caption starts with `@oracle`.
5. The document ingestion worker (Phase 4) picks up `status='pending_processing'`, chunks the file into `document_chunks`, embeds them, then runs claim extraction over the chunks.

### 4. Claim extraction (worker — deployed, Phase 4)

Cron: every 4 hours (`0 */4 * * *`). Also triggered by document ingestion.

1. Queries `messages WHERE extraction_status='pending' AND role='user'`. Batches up to 100 messages per run.
2. Groups by channel, then splits into 60-minute conversation segments.
3. Calls the extraction model (`settings.default_extraction_model`, default `google/gemini-2.5-flash`) via `generateObject` with a structured Zod schema.
4. Validates exact quotes against the source text verbatim — invalid quotes are rejected without inserting.
5. Inserts `claims` + `claim_domains` + `claim_evidence` rows. Auto-approves low-risk claim types with impact ≤ 6; others go to `pending_review`.
6. Suggests `gaps` rows for unanswered questions.
7. Marks source messages `extraction_status = 'complete'`, `'failed'`, or `'skipped'`. Writes `job_runs` + `model_runs` rows.

### 5. Synthesis (worker — deployed, Phase 4)

Cron: weekly. Also admin-triggerable.

1. Reads up to 200 approved claims per brain section.
2. Calls the synthesis model (`settings.default_synthesis_model`, default `anthropic/claude-sonnet-4.6`) via `generateObject`.
3. Validator rejects the run if any material paragraph doesn't map to approved claim IDs — hallucinated claim IDs cause the run to fail.
4. On success: inserts a new `brain_section_versions` row and updates `brain_sections.current_version_id` (two-step transaction per spec 6.7).

### 6. Admin review (Phase 5 — done)

Four server-component dashboards under `/admin/`:

- `/admin/claims` — pending-review queue with lateral join to primary evidence and asserting employee. Status-filter tabs. Approve/Reject server actions (`_actions.ts`) update `claims.status` and `revalidatePath`.
- `/admin/gaps` — Drizzle query joined with employees. Priority + status badges. Resolve/Stale server actions.
- `/admin/contradictions` — raw SQL via the `contradictions` table joined with both claim summaries (mirrors `contradictions_with_claim_summaries` view). Card-per-row layout. Confirm (possible→open) / Dismiss server actions.
- `/admin/brain` — `brain_sections` LEFT JOIN `brain_section_versions` on `current_version_id`. Scrollable markdown preview, review-status badge. Read-only; re-synthesis trigger is post-retrofit.

All four read via `getDirectDb()` (service role) and use `'use server'` actions with `revalidatePath` rather than client-side state.

### 7. Interjection engine (Phase 6 — paused)

Lull detection and contradiction-watcher rules are scaffolded as JSDoc in `packages/oracle-engines/src/interjection.ts`. Resumption is gated on the AI retrofit (R0–R10.5). See spec Part 5.1 and `docs/oracle/05-ai-retrofit-phase-packet.md` "Phase R11".

### 7. Sign-out

`POST /auth/signout` clears the Supabase session cookies server-side (via the same `@supabase/ssr` cookie adapter the callback uses) and redirects to `/`. The button is a `<form action="/auth/signout" method="post">` — POST avoids accidental sign-outs from URL prefetchers, and clearing cookies server-side avoids the "client says signed out but SSR pages still think they're signed in" gap.

## Major constraints

- **Postgres is the only source of truth.** No Redis, no file-based memory, no in-process AI memory. Every durable bit of state lives in a row.
- **Traceability is the product.** Every claim links to ≥1 `claim_evidence` row. Worker validators enforce exact-quote integrity.
- **No containers, no VPS.** Vercel + Supabase + Trigger.dev. Spec Part 2.5.
- **RLS first, application authorization second.** Browser code uses the anon key + RLS. Server routes use the service-role key only where it's documented and necessary.
- **Identity is durable through `employee_identities`** — emails on `employees` can change, but the `(provider, auth_user_id)` tuples in `employee_identities` are the stable identifiers.
- **Embeddings dimension is 1536** and locked. Changing it requires re-embedding everything. See AGENTS.md §11.
- **Supabase Postgres connection is via the poolers**, never the direct `db.*.supabase.co` hostname (IPv6-only on new projects). See AGENTS.md §11 + `docs/configuration.md`.

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
| Part 4 (auth) | `packages/auth/`, `apps/web/app/auth/callback/route.ts`, `apps/web/app/auth/signout/route.ts`, `apps/web/app/denied/` |
| Part 4 (multi-identity extension) | `packages/db/src/schema.ts` (employee_identities), `packages/db/migrations/sql/15_employee_identities.sql`, `packages/auth/src/link.ts` |
| Part 5.1 (interjection) | `packages/oracle-engines/src/interjection.ts` (scaffold) |
| Part 5.2 (curiosity / gaps) | `packages/db/src/schema.ts` (`gaps` table) + `apps/workers/src/trigger/claim-extraction.ts` (inserts gap suggestions) |
| Part 5.3 (ingestion) | `apps/workers/src/trigger/document-ingestion.ts` (deployed) |
| Part 5.4 (synthesis) | `apps/workers/src/trigger/brain-synthesis.ts` (deployed) |
| Part 6 (schema) | `packages/db/src/schema.ts` |
| Part 6.8 (CHECK constraints) | `packages/db/migrations/sql/10_check_constraints.sql` |
| Part 6.9 (vector indexes) | `packages/db/migrations/sql/99_vector_indexes.sql` |
| Part 7 (RLS) | `packages/db/migrations/sql/20_rls_helpers.sql`, `21_rls_policies.sql` |
| Part 8 (admin views) | `packages/db/migrations/sql/30_admin_views.sql` |
| Part 9.1 (chat route) | `apps/web/app/api/chat/route.ts` + `packages/ai/src/retrieval.ts` |
| Part 9.2 (tools) | `apps/web/app/api/chat/route.ts` |
| Part 9.4 (claim extraction) | `apps/workers/src/trigger/claim-extraction.ts` (deployed) |
| Part 10 (system prompt) | `packages/ai/src/prompts/oracle-system.ts` (verbatim) |
| Settings / model config | `apps/web/app/admin/settings/` — three model-role pickers (interview, extraction, synthesis) backed by `GET /api/admin/models` (OpenRouter) + `POST /api/admin/settings`. R1 will replace the OpenRouter-catalog picker with a curated `OracleModelRoute.routeId` picker. |
| Phase 5 admin review dashboards | `apps/web/app/admin/{claims,gaps,contradictions,brain}/page.tsx` + `_actions.ts`. Server actions; no client-state library. |

### Intentionally awkward — flag these before assuming they're bugs

- **`brain_sections.current_version_id` has no FK to `brain_section_versions`.** Looks like a missing constraint; it's a soft reference because the two tables reference each other circularly. Inserts happen as a two-step transaction (insert section with null, insert first version, update section). Documented in AGENTS.md §11 and `oracle_master_spec.md` Part 6.7.
- **`claims` has no `employee_id` column.** Looks like a schema oversight; it's intentional. A claim can be supported by multiple employees, documents, or external systems across time. Attribution lives on `claim_evidence.asserted_by_employee_id` per row.
- **Deprecated columns on `employees` (`auth_user_id`, `auth_provider`, `auth_provider_subject`) are NULL-filled and still present.** Looks like dead columns; they're kept during the multi-identity transition because dropping them mid-session would force a column-drop migration. Removal is in AGENTS.md §15 pending work. New code must read identities through `employee_identities`, not these columns.
- **Workers and chat still call OpenRouter via the Vercel AI SDK.** Looks like the docs/oracle architecture is half-implemented; it is — that's the AI retrofit's whole reason for being. Do not extend the OpenRouter path. R1–R9 replace it.
- **Embeddings fall back to a deterministic zero vector when `OPENAI_API_KEY` is unset.** Looks like a silent bug. It is intentional so local dev works without a real key; vector similarity is meaningless in that state but the schema and shape are preserved. AGENTS.md §11.
