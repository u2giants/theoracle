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
         │  Today (R6–R9 done):                 │
         │    Every model call routed through   │
         │    OracleAIClient via                │
         │    OpenRouterBridgeAdapter (the      │
         │    bridge wears each provider hat    │
         │    while dispatching to OpenRouter). │
         │  Target (post-wet-test):             │
         │    @anthropic-ai/sdk direct          │
         │    @google/genai (Vertex) direct     │
         │    openai direct                     │
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

Cron: weekly (Mondays 06:00). Also admin-triggerable.

1. Reads up to 200 approved claims per brain section (legacy `claim_domains` + `sectionClaims` joins; switch to `claim_top_domains` in a follow-up cleanup).
2. Routes through `OracleAIClient.runObject` using the curated route from `settings.default_synthesis_route` (default `anthropic_claude_3_5_sonnet_synthesis_primary`). Dispatched via `OpenRouterBridgeAdapter` under the hood until the real `@anthropic-ai/sdk` adapter lands.
3. `validateSynthesisDiff` rejects the run if (a) any material paragraph cites a non-approved claim ID, OR (b) the markdown mentions a capitalized proper-noun-shaped name not backed by an approved claim summary or the canonical entity registry. See `packages/oracle-engines/src/synthesis/diff-validator.ts`.
4. On success: inserts a new `brain_section_versions` row (`reviewStatus='draft'` or `'needs_review'`) and updates `brain_sections.current_version_id` (two-step transaction per spec 6.7).
5. On rejection: inserts a `brain_section_versions` row with `reviewStatus='rejected'` carrying the failed markdown + `validationFailures` + `unsupportedNames` in `structuredContent`. `currentVersionId` is NOT updated — the failed output is preserved for admin review without changing the current Brain version.

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

---

## AI architecture retrofit — R1–R4 (landed 2026-05-25)

The AI architecture retrofit is code-complete (R0–R10.5). Every legacy direct `getOpenRouter()` caller has been refactored to dispatch through `OracleAIClient`. The bridge adapter still routes through OpenRouter under the hood pending a wet-test path for real provider SDKs (`@anthropic-ai/sdk`, `@google/genai`, `openai`). See `docs/oracle/05-ai-retrofit-phase-packet.md` for the full phase log and `HANDOFF.md` for the recommended next-step sequence.

### Runtime pipeline (R2, landed)

```
                     Next.js route / Trigger.dev worker
                                  │
                                  ▼
                         ┌──────────────────┐
                         │  OracleAIClient  │  packages/ai/src/client/
                         └────────┬─────────┘
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
        ┌──────────────────┐            ┌────────────────────┐
        │ ContextCompiler  │            │   ModelRouter      │  packages/ai/src/routing/
        │ packages/ai/src/ │            │                    │
        │ context/         │            │  - resolve routeId │
        │                  │            │  - dispatch        │
        │ stable → semi    │            │  - fallback on     │
        │  → retrieved →   │            │    429 / timeout / │
        │  dynamic         │            │    NotImplemented  │
        │                  │            └──────────┬─────────┘
        │ throws if stable │                       │
        │ appears after    │            ┌──────────┴──────────┬──────────────┐
        │ dynamic          │            ▼                     ▼              ▼
        └──────────────────┘    Anthropic adapter    Vertex Gemini      OpenAI adapter
                                    (stub)            adapter (stub)        (stub)
                                                                                │
                                                       (real SDK wiring in R3+)│
                                                                                ▼
                                                                 UsageNormalizer →
                                                                 model_run_usage_details
```

**Test mode** auto-registers `MockProviderAdapter` instances for all three providers, so the full pipeline runs without API keys. The smoke gate (`pnpm --filter @oracle/ai verify:r2`) covers 16 assertions including stable-before-dynamic ordering, generateText across all 3 provider shapes, Zod-validated `generateObject`, ModelRouter fallback dispatch, and `EvidenceValidator` accept/reject behavior.

**Validation layer:**

- `packages/ai/src/validation/structured-output-validator.ts` — Zod schema check, returns a discriminated `ValidationResult<T>` so the caller can decide whether to escalate to a repair route.
- `packages/ai/src/validation/evidence-validator.ts` — deterministic `.includes()` + offset verification with ambiguity guard (multi-occurrence quotes without offsets are flagged `ambiguous`, not silently accepted).

### Curated route catalog (R1, landed)

`packages/ai/src/routes/` defines `OracleModelRoute` and the 9 curated routes. Each of the 3 production roles has **exactly 1 Primary + 1 Fallback** — no balanced alternates or competing defaults.

| Role | Primary | Fallback |
|---|---|---|
| Interview | `anthropic_claude_haiku_4_5_interview_primary` | `openai_gpt4o_interview_fallback` |
| Extraction | `vertex_gemini_2_5_flash_extraction_primary` | `openai_gpt4o_mini_extraction_fallback` |
| Synthesis | `anthropic_claude_3_5_sonnet_synthesis_primary` | `vertex_gemini_2_5_flash_synthesis_fallback` |

Internal escalation subroutes (Flash-Lite triage, Haiku warmth escalation, GPT-4o-mini schema repair) live inside `OracleAIClient` and are not exposed in admin settings.

### Observability schema (R3, landed)

Three Drizzle tables (created by migration `0001_hot_johnny_blaze.sql`) feed the future cost/cache dashboards:

| Table | Purpose |
|---|---|
| `oracle_context_packs` | Full `OraclePromptPlan` per AI call. Block list, prompt/schema versions, cache-key hashes (`stable_prefix_hash`, `dynamic_input_hash`, etc.), retrieval plan, included record IDs. `model_run_id` is nullable so the pack can be created BEFORE the model run. |
| `model_run_usage_details` | 1:1 child of `model_runs` (UNIQUE on `model_run_id`). Adds the OracleUsage shape: `cached_input_tokens`, `cache_write_tokens`, `reasoning_tokens`, `provider_request_id`, raw provider usage JSON, plus fallback dispatch tracking (`fell_back_from_route_id`, `fallback_reason`). |
| `provider_cached_content` | Explicit Vertex cache tracking. Required reuse policy fields: `expected_reuse_count`, `latest_planned_reuse_step`, `hard_expiration_at`, `cleanup_owner`. `status` ∈ `(active, deleted, expired, failed, orphaned)`; CHECK constraint enforces `deleted_at IS NULL iff status='active'`. |

The `model_runs_with_usage` view (`migrations/sql/31_observability_views.sql`) joins all three for dashboard queries and computes `cache_hit_ratio = cached_input_tokens / input_tokens`.

### Three-layer knowledge taxonomy (R3.5, landed)

15 tables installing the segmentation from `docs/oracle/07-knowledge-segmentation.md`:

```
Layer 1   knowledge_top_domains            12 domains seeded; admin-curated
            ↑                                each carries boundary rules:
            │                                belongs_here, does_not_belong_here,
            │                                common_entity_hints,
            │                                default_excluded_document_classes,
            │                                neighboring_domain_ids
            │
   ┌────────┴────────────────────────────────────┐
   │                                              │
   ▼                                              ▼
Layer 2   knowledge_sub_topics            (Tagging joins)
            empty on install              claim_top_domains, document_top_domains,
            centroid vector(1536)         document_chunk_top_domains,
            HNSW index                    message_top_domains, claim_sub_topics
                                          → retrieval scopes BEFORE claims exist

Layer 3   entities                        56 entities seeded
            ↑                                customers (5)   licensors (5; first-class)
            │                                systems (10)    departments (8)
            │                                geographies (4) process_stages (14)
            │                                document_classes (10)
            │
   ┌────────┴────────────────────────────────────┐
   │                                              │
   ▼                                              ▼
Tag joins  claim_entities,                claim_metadata
           document_chunk_entities,         process_stage, department, geography,
           message_entities                 document_class, effective_from,
                                            effective_until, superseded_by_claim_id

Governance taxonomy_proposals           Compact admin proposal cards
           taxonomy_change_log          Audit log of accepted changes
           entity_proposals             Unknown-entity queue
                                        Auto-mutation prohibited
```

The legacy `claim_domains` table and `knowledge_domain` Postgres enum are intentionally preserved during transition. `migrations/sql/42_claim_top_domains_backfill.sql` copies existing claim-domain rows into the new `claim_top_domains` join via an explicit mapping (e.g. `coldlion → it_systems`, `sampling → product_development`).

### Candidate-before-claim staging (R4, landed)

The extraction pipeline runs through 4 new tables (`migrations/0003_magenta_lionheart.sql`):

```
model output
  → extraction_batches              circuit-breaker fields:
                                      validation_attempt_count,
                                      consecutive_quote_failure_count,
                                      model_run_ids_attempted,
                                      route_ids_attempted
  → extraction_candidates           sensitivity flags first-class:
                                      contains_sensitive_personal_data,
                                      contains_sensitive_hr_data,
                                      is_personal_conflict
                                    proposed_entities + proposed_metadata
                                    dedup pointers: duplicate_of_candidate_id,
                                      duplicate_of_claim_id
  → extraction_candidate_evidence   stores both model-provided AND validator-
                                    confirmed quote/offsets
  → extraction_validation_results   one row per deterministic check
  → (R5) transactional promotion    advisory-lock → claims +
                                    claim_top_domains + claim_evidence
```

13 CHECK constraints (in `migrations/sql/13_extraction_constraints.sql`) enforce the pipeline invariants that schema alone can't — `promoted-consistency`, `sensitive-consistency`, `validated-fields-required-on-pass`, source-type/pointer consistency, etc.

### Extraction pipeline pure logic (R5 + R5.5, landed)

`packages/oracle-engines/src/extraction/` ships the deterministic logic that workers compose. Every function in this list is pure (no DB, no API keys, no network) and covered by a smoke gate:

| Module | Function | Purpose |
|---|---|---|
| `quote-validator.ts` | `validateQuote` | Verbatim provenance check. Returns `exact_match` / `normalized_match` / `ambiguous` / `failed`. Supplied offsets are ground truth — they must decode to the exact quote or the row fails with `quote_offsets_match`. |
| `quote-validator.ts` | `validateSourcePointer` | Mirrors the `extraction_candidate_evidence_source_check` CHECK constraint. Fails fast before the DB insert. |
| `normalization.ts` | `normalize`, `methodForApplied` | CRLF / smart-quote / whitespace-collapse / trim. All OFF by default. Reports which normalizations actually changed the input so audits can replay the decision. |
| `candidate-hash.ts` | `computeCandidateHash`, `canonicalizeSummary` | Deterministic sha256 over canonicalized candidate (lowercased + collapsed-whitespace summary; sorted top-domain IDs; sorted validated quotes; sorted source pointers). Stable across order, case, and whitespace. |
| `promote-candidate.ts` | `decidePromotion` | Pure decider returning `insert_new_claim` / `append_to_existing_claim` / `reject(reason)`. Extended in R5.5 with `entityAssignments`, `metadata`, `entityProposalsToStage`. |
| `entity-resolver.ts` | `resolveEntity` | Alias → canonical lookup. Returns `resolved` / `unknown` / `type_mismatch` / `ambiguous`. Type-mismatch catches "Disney as vendor" — Disney is a `licensor` in the seed; the resolver refuses to silently create a vendor row. |
| `taxonomy-validator.ts` | `validateTaxonomy` | Validates every proposed top-domain against `knowledge_top_domains` + every proposed entity against the registry. Surfaces `entityProposalsToCreate` for unknown / type-mismatch entities. |
| `circuit-breaker.ts` | `decideCircuitBreaker` | 3-strike rule per `docs/oracle/03-candidate-before-claim-validation.md`. Returns `continue` / `allow_repair_pass` / `trip_breaker`. |
| `domain-mapping.ts` | `mapLegacyDomainsToTopDomains` | Transitional legacy `KNOWLEDGE_DOMAINS` → `TOP_LEVEL_DOMAINS` mapping. Mirrors `migrations/sql/42_claim_top_domains_backfill.sql` exactly. |
| `cache-profitability.ts` | `decideCacheProfitability`, `estimateTokensForCache` | Vertex explicit-cache heuristic. Returns `create_explicit_cache(rule)` / `skip_explicit_cache(reason)`. |

Run each smoke gate any time: `pnpm --filter @oracle/engines verify:r5` (33/33), `verify:r5.5` (45/45), `verify:r6` (30/30), `verify:r7` (19/19). Combined with R2 (16/16), 143 deterministic assertions cover the business logic.

### DB-aware extraction executor (R6 + R7, landed)

`packages/oracle-engines/src/extraction/promotion-executor.ts` is the only path that inserts into permanent `claims` / `claim_top_domains` / `claim_entities` / `claim_metadata` / `claim_evidence`. The transaction shape:

```
db.transaction(async (tx) => {
  // 1. Advisory lock — refuses to block; throws AdvisoryLockBusyError if taken.
  await tx.execute(sql`SELECT pg_try_advisory_xact_lock(hashtextextended($1, 0))`)

  // 2. RACE-SAFE re-read of candidate row + validated evidence INSIDE the lock.
  //    Caller passes only candidateId — the executor SELECTs the latest
  //    committed state. Pure mappers (mapCandidateRowToSnapshotCandidate,
  //    mapEvidenceRowToValidatedEvidence) convert DB rows into the snapshot
  //    shape decidePromotion consumes. Both mappers are unit-tested under
  //    R5 smoke cases M1–M10.
  const fresh = await loadCandidateSnapshotInLock(tx, candidateId)

  // 3. Missing candidate? Return invalid_state WITHOUT writing
  //    extraction_validation_results (FK target doesn't exist). The only
  //    reject branch that skips the audit row.
  if (!fresh.candidate) return { outcome: 'recorded_rejection', appliedDecision: { kind: 'reject', reason: 'invalid_state', ... } }

  // 4. Race-safe hash lookup INSIDE the lock. Partial UNIQUE on
  //    claims.candidate_hash means at most one row matches.
  const existing = await tx.select(...).from(claims).where(eq(claims.candidateHash, hash))

  // 5. Decide. The decider sees:
  //    - fresh candidate (latest committed status — promoted? validation_failed?)
  //    - fresh validated evidence (includes anything appended since caller's read)
  //    - in-lock existing-claim-by-hash lookup
  //    - caller's auxiliaryInputs.taxonomy + auxiliaryInputs.metadata
  //      (NOT race-protected against registry drift — see scope note below)
  const decision = decidePromotion({
    candidateHash, candidate: fresh.candidate, validatedEvidence: fresh.validatedEvidence,
    taxonomy: input.auxiliaryInputs?.taxonomy, metadata: input.auxiliaryInputs?.metadata,
    existingClaimWithSameHash: existing[0] ?? null
  })

  // 6. Stage entity_proposals (useful regardless of branch).
  // 7. Branch on decision.kind:
  //    insert_new_claim          → claims (with candidate_hash) + claim_top_domains
  //                                + claim_entities + claim_metadata + claim_evidence
  //                                + candidate.status='promoted'
  //                                + extraction_validation_results pass
  //    append_to_existing_claim  → claim_entities + claim_evidence appended
  //                                + candidate.status='duplicate' (current candidate
  //                                  is still validated; some OTHER candidate already
  //                                  committed a claim with the same hash)
  //                                + extraction_validation_results pass
  //    reject                    → candidate.status updated per reason
  //                                + extraction_validation_results fail
  //                                  (EXCEPT: invalid_state with missing candidate
  //                                   skips the audit row — see step 3)
})
```

**Two race scenarios — distinct branches:**

- *Same candidate, re-read inside the lock, status no longer `validated`* → `reject(already_promoted)` (if another worker promoted *this* candidate) or `reject(not_validated)` (if a sensitivity gate fired between reads).
- *Different candidate, same canonicalized hash* → `append_to_existing_claim`. The current candidate is still `validated`; a parallel extraction of the same operational fact already committed a claim with the same hash. Our validated evidence is appended to their claim and our candidate is marked `duplicate`.

**Scope of what's race-protected:** the candidate row + validated evidence + same-hash claim lookup. The caller-provided `auxiliaryInputs.taxonomy` and `auxiliaryInputs.metadata` are NOT — registry drift between caller-side `validateTaxonomy()` and executor promotion is tolerated. Taxonomy mutations happen via admin approval at `/admin/taxonomy` (minutes/hours scale), not worker activity (ms scale). See `DECISIONS.md` D8.taxonomy-stays-caller-provided for the rationale.

Cache lifecycle (`packages/oracle-engines/src/extraction/cache-lifecycle.ts`):
- `recordCacheCreation` inserts a `provider_cached_content` row with `status='active'` and the required reuse policy fields (`expected_reuse_count`, `latest_planned_reuse_step`, `hard_expiration_at`, `cleanup_owner`).
- `recordCacheReuse(handle)` bumps `actual_reuse_count`.
- `recordCacheTermination({ handle, status, reason })` marks the row `deleted | expired | failed | orphaned` and stamps `deleted_at`. The CHECK constraint on `provider_cached_content` enforces `deleted_at IS NOT NULL` whenever status is non-active.

### Worker and chat-route integration (R6 + R7 + R8, landed)

After R6 / R7 / R8 / R9, every legacy `getOpenRouter()` caller in the production AI surface has been refactored:

| Caller | Phase | Status |
|---|---|---|
| `apps/workers/src/trigger/claim-extraction.ts` | R6 | ✅ via `OpenRouterBridgeAdapter` |
| `apps/workers/src/trigger/document-ingestion.ts` | R7 | ✅ via `OpenRouterBridgeAdapter` |
| `apps/web/app/api/chat/route.ts` | R8 | ✅ via `OpenRouterBridgeAdapter` + `providerOptions` escape hatch for tools/multi-turn |
| `apps/workers/src/trigger/brain-synthesis.ts` | R9 | ✅ via `OpenRouterBridgeAdapter` + `validateSynthesisDiff` (claim ID + unsupported-named-entity check) + rejected-version preservation |
| `apps/workers/src/trigger/contradiction-watcher.ts` | R11 | ⬜ Phase 6 / interjection territory |
| `apps/workers/src/trigger/taxonomy-reevaluation.ts` | R10.5 | ⬜ scaffold only — clustering body deferred until claim density justifies it |

Each refactored caller follows the same pattern:
1. Build `OracleAIClient` with `OpenRouterBridgeAdapter` for all 3 provider tags.
2. Resolve the curated route from `settings.default_*_route` (R1 keys).
3. Compile a prompt plan with `ContextCompiler` (stable_system + dynamic content).
4. Insert `oracle_context_packs` row BEFORE the model call so its ID can thread through.
5. Call `OracleAIClient.runText` (chat) or `runObject` (workers).
6. Insert `model_runs` + `model_run_usage_details` + back-link the context pack.
7. Workers: stage `extraction_batches` + `extraction_candidates` + `extraction_candidate_evidence`, run validators, call `executePromotion`. Chat: persist the assistant message.

### Transitional bridge adapter (R6 onward, still active through R9)

`packages/ai/src/providers/openrouter-bridge-adapter.ts` is a deliberate transitional layer. It implements `OracleProviderAdapter` for all 3 provider tags (`anthropic`, `vertex`, `openai`) but the underlying network call goes to OpenRouter via the Vercel AI SDK. The bridge maps the route's `modelId` to OpenRouter's namespace (`vertex_gemini_2_5_flash` → `google/gemini-2.5-flash`, etc.).

**The bridge is not part of the target architecture.** Real `@anthropic-ai/sdk` / `@google/genai` / `openai` SDKs land one at a time as each phase that needs a specific provider's native features (Anthropic cache breakpoints, Vertex explicit caching, OpenAI structured outputs) reaches a wet-test path. After the last replacement, the bridge can be deleted entirely.

### Synthesis pipeline (R9, landed)

`packages/oracle-engines/src/synthesis/` ships the deterministic synthesis-diff validator. The synthesis worker composes it with the OracleAIClient bridge pattern:

```
brain_sections + approved claims + entity registry
  ↓
ContextCompiler.compile()
  ├── stable_system block: ORACLE_SYSTEM_PROMPT + approved claim corpus
  └── dynamic_input block: per-trigger request
  ↓
oracle_context_packs row (modelRunId nullable, set after the call)
  ↓
OracleAIClient.runObject(SynthesisOutputSchema)
  via OpenRouterBridgeAdapter for vertex_* or anthropic_* routes
  ↓
model_runs + model_run_usage_details + back-link to context pack
  ↓
validateSynthesisDiff({
  output, approvedClaimIds, approvedClaimSummariesLower,
  registryEntityCanonicalsLower, expectedSectionId
})
  ↓
  ok=true  → brain_section_versions row (status='draft' or 'needs_review')
              + UPDATE brain_sections.currentVersionId
              + sectionClaims membership
              + newGaps insert + resolvedGaps update
  ok=false → brain_section_versions row (reviewStatus='rejected')
              with validationFailures + unsupportedNames in
              structuredContent. currentVersionId is NOT updated.
```

The seven failure kinds `validateSynthesisDiff` distinguishes:

| Failure kind | Trigger |
|---|---|
| `wrong_section_id` | `output.sectionId` doesn't match the requested section |
| `paragraph_cites_non_approved_claim` | `paragraphs[].supportingClaimIds` contains an ID not in the approved set |
| `material_change_cites_non_approved_claim` | `materialChanges[].claimId` not approved |
| `claim_ref_not_approved` | `claimsAdded` / `claimsStrengthened` / `claimsWeakened` references not approved (`claimsRemoved` is NOT checked — removed claims may no longer be approved by design) |
| `contradiction_cites_non_approved_claim` | `newContradictions[]` references claims not approved |
| `gap_missing_required_fields` | `newGaps[]` has empty `questionToAsk` or `whyItMatters` |
| `unsupported_named_entity` | A capitalized proper-noun-shaped name in `updatedMarkdown` is not backed by an approved claim summary OR the canonical entity registry |

The unsupported-named-entity check is the R9-new addition. It strips Markdown structure (code blocks, inline code, image refs, markdown links, ENTIRE heading lines) before regex-matching for capitalized proper-noun phrases, then checks each candidate against the lowercase approved-summary corpus and the lowercase registry canonical set. Heuristic, not a parser; false positives hold for admin review (acceptable), false negatives let fabricated names through (worse), so the stopword list is curated tight.

### Admin observability surface (R10, landed)

Six read-only Next.js App Router pages under `/admin/ai`. Server-rendered Drizzle queries against existing R3 / R4 / R7 tables and the `model_runs_with_usage` view. No new schema, no new server actions, no new dependencies.

| Route | Purpose | Reads from |
|---|---|---|
| `/admin/ai` | Top-level dashboard: 12 metric cards + route usage breakdown + recent runs | `model_runs_with_usage`, `provider_cached_content`, `extraction_candidates` |
| `/admin/ai/runs` | Paginated runs list (50/page, 4 filters + task-type chips) | `model_runs_with_usage` |
| `/admin/ai/runs/[id]` | One-run detail: summary, usage breakdown, full prompt-plan block list, retrieval diagnostics, linked extraction batches, linked provider caches | `model_runs_with_usage`, `oracle_context_packs`, `extraction_batches`, `provider_cached_content` |
| `/admin/ai/cache` | Cache rows filterable by status + provider hit-ratio table | `provider_cached_content`, `model_runs_with_usage` |
| `/admin/ai/candidates` | Extraction candidate review with 8 filter tabs. Sensitive rows are excluded at the SQL level from every tab except the explicit "Sensitive" tab. | `extraction_candidates`, `extraction_validation_results` |
| `/admin/ai/evals` | Placeholder. Documents the CLI smoke gates. | — |

The sensitive-candidate exclusion is structural: the SQL `WHERE` clause prevents any UI toggle from leaking sensitive material into the standard queue.

### Taxonomy governance surface (R10.5, landed)

Five admin pages under `/admin/taxonomy` plus four transactional server actions plus a scheduled re-evaluation worker scaffold.

| Route | Purpose |
|---|---|
| `/admin/taxonomy` | Top-level domains list with full boundary rules + usage counts |
| `/admin/taxonomy/proposals` | Taxonomy proposals review queue with approve/reject |
| `/admin/taxonomy/entities` | Entity registry grouped by type (licensor split from vendor explicitly) |
| `/admin/taxonomy/entity-proposals` | Unknown-entity review queue. Approval can refine canonical + auto-merges on conflict |
| `/admin/taxonomy/change-log` | Append-only audit (latest 200 events) |

Server actions in `apps/web/app/admin/taxonomy/_actions.ts`:

- `approveTaxonomyProposal(id, reviewNote?)` — transactional. Applies the mutation INLINE for `create_top_domain` proposals (INSERT into `knowledge_top_domains` with full boundary rules). For `merge_top_domains` / `split_top_domain` / `reassign_claims` / `create_sub_topic` / `merge_sub_topics` / `split_sub_topic` / `retire_sub_topic` the proposal is marked approved with a `taxonomy_change_log` entry of `changeType='approve_pending_reclassification_<type>'`; the actual reclassification work is queued for the dedicated reclassification job (R10.5 task 4) which lands when those proposal types start arriving.
- `rejectTaxonomyProposal(id, reason)` — transactional reject + change-log audit.
- `approveEntityProposal(id, finalCanonicalValue?, displayLabel?)` — transactional. INSERTs the `entities` row; auto-merges if the (entity_type, canonical_value) pair already exists. Status becomes `approved` or `merged_into_existing`.
- `rejectEntityProposal(id, reason)` — transactional reject + change-log audit.

The scheduled `taxonomy-reevaluation` worker (`apps/workers/src/trigger/taxonomy-reevaluation.ts`) is currently a scaffold: it counts approved claims per active top-domain and reports a configurable activation threshold (default 30 claims). The clustering / drift detection / proposal writing body is documented inline as the substitution for the early-exit path; it lands when approved-claim density justifies it.

### Architectural state after R0–R10.5

```
Every legacy getOpenRouter() worker has been refactored.
Every model call has a context pack + usage detail row.
Every promotion is advisory-locked and race-safe.
Every claim insertion is hash-deduped.
Every taxonomy mutation is admin-gated.
Every synthesis output is validated; rejected versions preserved.
Every operationally-sensitive observability dashboard is read-only.
Every refactored worker still dispatches through OpenRouterBridgeAdapter
  pending the wet-test that swaps in real provider SDKs one at a time.
```

R11 (interjection engine) is the remaining phase. Architectural prerequisites met; empirical prerequisites (test transcript processed + claims reviewed and approved) need real data flowing through the pipeline first.
