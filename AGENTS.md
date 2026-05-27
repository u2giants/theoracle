# AGENTS.md — The Oracle Developer Guide

This is the single source of truth for any developer, AI agent, or AI session working on this project. Read this top-to-bottom before touching anything. The full product specification is in `oracle_master_spec.md`; this file is the operational guide.

---

## 1. What this project is

**The Oracle** is an AI-powered Business Intelligence system — an Enterprise Knowledge Graph — for **POP Creations / Spruce Line**, a high-volume home decor company based in Brooklyn (~1,500 SKUs, ~18 employees across US/China/Brazil/Colombia, retail customers including Burlington, TJX, Ross, Hobby Lobby, Walmart).

The company's real operational reality lives in people's heads ("dark matter"): informal rules, undocumented workarounds, contradictory understandings of when work is "ready" for the next department. The Oracle observes conversations, ingests documents, interviews employees, extracts evidence-backed *claims* about how the business actually works, detects contradictions and gaps, and synthesizes a versioned company "Brain" that the lead architect can query.

**Business outcome:** the lead architect (Albert) can ask "why does the company believe X?" and get an answer backed by traceable evidence — specific messages, specific document chunks, specific employees on specific dates.

**The Oracle is NOT** a project manager, task tracker, to-do list, ticket system, or due-date manager. If any code in this repo looks like that, it is a bug. See `oracle_master_spec.md` Part 1.3.

---

## 1a. Core Architecture

- **Database is Truth:** PostgreSQL (via Supabase) is the sole source of truth. No flat-file Markdown memory.
- **Provider-Native AI:** All AI calls go through `OracleAIClient → ContextCompiler → ModelRouter → direct provider adapter`. The three production adapters use the providers' raw SDKs (`@anthropic-ai/sdk`, `@google/genai`, `openai`). The Vercel AI SDK is forbidden in the production AI path (DECISIONS.md D6 + D9). OpenRouter has been removed entirely (commit `b01e514`).
- **Traceable Intelligence:** Every claim must link to verbatim evidence (`Candidate-Before-Claim` validation) and must declare its `claim_kind` (policy vs. practice) and `corroboration_tier`.
- **No HR Surveillance:** The Oracle maps operational workflows, hidden bottlenecks, and "Dark Matter." It does NOT evaluate employee performance, flag HR violations, or monitor productivity.

---

## 2. Multi-model note

There is no universal ignore-file standard across AI coding tools.

`.claudeignore` works for Claude Code. `.cursorignore` works for Cursor. Other AI tools each have their own conventions.

When using any other AI tool, paste this file as your first message and follow the instructions in the "What to ignore" section.

---

## 3. Repository / package structure

This is a **pnpm + Turborepo** monorepo. TypeScript everywhere. Strict mode.

```
oracle/
├── apps/
│   ├── web/                       # Next.js 16 App Router — the only user-facing app
│   │   ├── app/
│   │   │   ├── page.tsx                       # /  — login landing
│   │   │   ├── auth/callback/route.ts         # OAuth + magic-link callback → linker
│   │   │   ├── auth/signout/route.ts          # POST → clears session, redirects to /
│   │   │   ├── denied/page.tsx                # off-allowlist landing
│   │   │   ├── channels/                      # employee-facing chat (Phase 2)
│   │   │   ├── admin/                         # admin dashboard (Phase 2/5 + R10/R10.5)
│   │   │   │   ├── ai/                        # R10 — AI observability (runs, cache, candidates, evals)
│   │   │   │   ├── taxonomy/                  # R10.5 — taxonomy governance (proposals, entities, change log)
│   │   │   │   ├── settings/                  # P1 #1 — model pool UI (/admin/settings/model-pool)
│   │   │   │   ├── {claims,gaps,contradictions,brain}/   # Phase 5 review dashboards
│   │   │   ├── api/chat/route.ts              # Oracle chat endpoint (Phase 3)
│   │   │   └── _components/                   # local UI: login-form, logout-button
│   │   ├── components/ui/                     # shadcn/ui primitives
│   │   ├── lib/                               # web-only helpers (supabase client, auth-guard)
│   │   ├── next.config.ts                     # loads .env.local from monorepo root
│   │   └── tailwind.config.ts
│   └── workers/                   # Trigger.dev v3 — background workers
│       ├── trigger.config.ts
│       └── src/
│           ├── trigger/{claim-extraction,document-ingestion,brain-synthesis,lull-interjection,contradiction-watcher,taxonomy-reevaluation,taxonomy-reclassification}.ts
│           └── wet-test/run-claim-extraction-once.ts  # local end-to-end runner (bypasses Trigger.dev)
├── packages/
│   ├── shared/                    # framework-agnostic TS types & constants (KNOWLEDGE_DOMAINS, etc.)
│   ├── db/                        # Drizzle ORM — schema, migrations, seed, client
│   │   ├── src/{schema.ts,client.ts,migrate.ts,seed.ts,verify-identities.ts,inspect-auth-users.ts,index.ts}
│   │   ├── migrations/            # Drizzle-generated SQL (auto)
│   │   ├── migrations/sql/        # hand-written SQL — see README in that folder
│   │   └── drizzle.config.ts
│   ├── auth/                      # Supabase auth helpers + multi-identity linker
│   │   └── src/{link.ts,server.ts,client.ts,index.ts}
│   ├── ai/                        # AI provider gateway + prompts + retrieval + embeddings
│   │   └── src/
│   │       ├── client/             # OracleAIClient (R2)
│   │       ├── context/            # ContextCompiler + PromptBlock helpers (R2)
│   │       ├── routing/            # ModelRouter with auto-fallback (R2)
│   │       ├── providers/          # 3 production adapters (R-providers): AnthropicAdapter (raw @anthropic-ai/sdk),
│   │       │                       # VertexGeminiAdapter (raw @google/genai), OpenAIAdapter (raw openai),
│   │       │                       # plus MockProviderAdapter for test mode. NO Vercel AI SDK in this folder.
│   │       ├── usage/              # OracleUsage normalizer (R2)
│   │       ├── validation/         # StructuredOutputValidator + EvidenceValidator (R2)
│   │       ├── routes/             # Curated OracleModelRoute catalog (R1) + `resolveModelRoute()` dynamic resolver (handles catalog routeIds AND OpenRouter-style `provider/model` strings)
│   │       ├── prompts/            # oracle-system.ts (interview), extraction-system.ts
│   │       ├── __verify__/         # r-providers-smoke.ts (real-API smoke) + earlier deterministic smokes
│   │       ├── evals/              # mock-mode extraction eval (fixtures + canned LLM outputs + runner)
│   │       ├── embeddings.ts, retrieval.ts, retrieval-plan.ts
│   │       └── index.ts
│   ├── oracle-engines/            # Pure-logic extraction + synthesis modules + DB-aware executors (R5–R9)
│   │   ├── src/extraction/
│   │   │   ├── types.ts, normalization.ts
│   │   │   ├── quote-validator.ts        # R5 pure provenance check
│   │   │   ├── candidate-hash.ts         # R5 deterministic hash for advisory lock
│   │   │   ├── promote-candidate.ts      # R5 decidePromotion pure decider (extended in R5.5)
│   │   │   ├── entity-resolver.ts        # R5.5 alias → canonical, type-mismatch detection
│   │   │   ├── taxonomy-validator.ts     # R5.5 top-domain + entity validation
│   │   │   ├── circuit-breaker.ts        # R6 3-strike decider
│   │   │   ├── domain-mapping.ts         # R6 legacy KNOWLEDGE_DOMAINS → TOP_LEVEL_DOMAINS
│   │   │   ├── promotion-executor.ts     # R6 Drizzle transaction + advisory lock + race-safe hash lookup (R7)
│   │   │   ├── cache-profitability.ts    # R7 explicit-cache heuristic
│   │   │   ├── cache-lifecycle.ts        # R7 provider_cached_content bookkeeping
│   │   │   └── index.ts
│   │   ├── src/synthesis/         # R9
│   │   │   ├── types.ts                  # SynthesisOutput types
│   │   │   ├── diff-validator.ts         # R9 validateSynthesisDiff — claim ID + unsupported-named-entity check
│   │   │   └── index.ts
│   │   ├── src/__verify__/        # Self-contained smoke gates (R5/R5.5/R6/R7/R9)
│   │   ├── src/interjection.ts    # R11.1 — pure decision functions: decideLullInterjection + decideContradictionInterjection; wired in R11.2 (lull-interjection cron) + R11.3 (contradiction live interjection)
│   │   └── src/index.ts
├── docs/                          # detailed docs — architecture, development, configuration, deployment
├── AGENTS.md                      # this file
├── CLAUDE.md                      # Claude Code-specific notes (points back here)
├── DECISIONS.md                   # every assumption, citation, alternative ruled out
├── HANDOFF.md                     # live in-flight state for a new contributor
├── README.md                      # short orientation
├── oracle_master_spec.md          # authoritative product spec — do not edit casually
├── .env.example                   # variable names only; never real secrets
├── .env.local                     # gitignored; real secrets live here for local dev
├── .claudeignore / .cursorignore  # AI indexer ignore lists
├── .gitignore
├── .prettierrc.json
├── package.json                   # root — workspaces + scripts
├── pnpm-workspace.yaml
├── pnpm-lock.yaml
├── tsconfig.base.json             # shared strict TS config
└── turbo.json
```

**Code we own:** everything under `apps/**`, `packages/**`, `docs/**`, and the markdown files at the root.

**Generated code:** `packages/db/migrations/0NNN_*.sql` (Drizzle-generated; do not hand-edit — write a new SQL file under `migrations/sql/` instead).

**Build artifacts** (ignored): `node_modules/`, `apps/web/.next/`, `dist/`, `.turbo/`, `.vercel/`.

**Third-party / framework code:** lives in `node_modules/`. Never edit it; if a framework needs a workaround, add a thin wrapper inside our own packages and document it in section 11 below.

---

## 4. The Prime Directive

**Our custom code lives here:**

- `apps/web/app/**` — Oracle's own routes, pages, components
- `apps/web/lib/**` — web-only helpers we own
- `apps/workers/src/**` — Trigger.dev workers
- `packages/**` — all shared logic
- `docs/**`
- `.github/workflows/**` (when added)

**Everything else requires justification before touching.** Specifically:

- Do not modify `apps/web/components/ui/*` beyond what `shadcn/ui` CLI generates. If you need a new variant, extend it in a new file under `apps/web/app/_components/`.
- Do not edit `node_modules/`. Ever.
- Do not edit auto-generated Drizzle migration SQL. Add a new file under `packages/db/migrations/sql/` with the next free numeric prefix.
- Do not edit `oracle_master_spec.md` to make code easier — the spec is the contract. If the spec is wrong, raise it explicitly in `DECISIONS.md` and have Albert decide.

The goal is to prevent AI agents from scattering project-specific logic across framework files where it becomes invisible.

---

## 5. Core modification inventory

Files outside our owned directories that had to be modified.

| File | Change made | Why it was necessary | Risk during upgrades |
|---|---|---|---|
| _(none)_ | — | Greenfield project. No upstream forks. | — |

If this section is ever non-empty, treat it as the upstream-merge conflict checklist.

---

## 6. Decision tree

**If I need to add a new API route:**
1. Add route handler in `apps/web/app/api/<name>/route.ts`.
2. Add Zod schema for the body in the same file (or in a co-located `schema.ts`).
3. If it touches the DB, query through Drizzle from `@oracle/db`. Never hand-write SQL in route handlers.
4. If it uses an LLM, go through the `OracleAIClient` (`packages/ai/src/client`) using direct provider adapters — never call providers directly from a route file, and NEVER use the legacy `openrouter` path.
5. Respect RLS: use the SSR Supabase client from `apps/web/lib/supabase/server.ts`; service-role usage requires a comment justifying it.
6. Update `docs/configuration.md` if a new env var is needed.
7. Do not touch admin views in `packages/db/migrations/sql/30_admin_views.sql` unless the route is admin-only and a new view is required.

**If I need to add a new background job:**
1. Add a task file under `apps/workers/src/trigger/<job>.ts` following the existing scaffolds.
2. Register the task export in `apps/workers/trigger.config.ts` if needed.
3. Every job MUST insert a row in `job_runs`; LLM calls MUST insert rows in `model_runs`. This is non-negotiable per spec Part 9.
4. Add any required env var to `.env.example` and `docs/configuration.md`.
5. Do not touch `apps/web/`.

**If I need to add a new database table or column:**
1. Edit `packages/db/src/schema.ts`.
2. `pnpm db:generate` — creates a new Drizzle migration in `packages/db/migrations/`.
3. If the change needs constraints, RLS, helper functions, or views: add a new `packages/db/migrations/sql/NN_<topic>.sql` file (next free numeric prefix — see the README in that folder for the ordering convention).
4. `pnpm db:migrate` to apply.
5. Update `docs/architecture.md` data-model section.
6. Do not edit prior generated migration files — only the new one.

**If I need to add a new shared type or constant:**
1. Add it to `packages/shared/src/`.
2. Export from `packages/shared/src/index.ts`.
3. Re-run `pnpm typecheck` from the root.

**If I need to change the Oracle's behavior, voice, or system prompt:**
1. Edit `packages/ai/src/prompts/oracle-system.ts`. Treat changes to this file with care — the prompt is verbatim from spec Part 10.
2. If altering the prompt, also update `oracle_master_spec.md` Part 10 in the same commit. The prompt file and spec must never drift.

**If I need to seed or change initial data:**
1. Edit `packages/db/src/seed.ts`.
2. Seeds must be idempotent (upserts, not inserts).
3. Run `pnpm db:seed`.

**If I need to add a login provider:**
1. Configure the provider in Supabase Dashboard → Authentication → Providers.
2. Make sure `packages/auth/src/server.ts` → `resolveAuthProvider()` maps Supabase's provider name to our `auth_provider` enum value. If new, add to the enum in `packages/db/src/schema.ts` and write a small migration.
3. Add a button in `apps/web/app/_components/login-form.tsx` calling `supabase.auth.signInWithOAuth({provider, options: {scopes: '...'}})`. The `email` scope is mandatory for Microsoft Entra (see Idiosyncratic Decisions).

---

## 7. Task-to-file navigation map

| Task | Files to touch | Files NOT to touch |
|---|---|---|
| Add a new claim type or knowledge domain | `packages/shared/src/domains.ts`, `packages/db/src/schema.ts`, new migration SQL | existing applied migration files |
| Tweak the Oracle's chat behavior | `apps/web/app/api/chat/route.ts`, `packages/ai/src/prompts/oracle-system.ts`, `packages/ai/src/retrieval.ts` | `apps/web/components/ui/**`, shadcn primitives |
| Change the login flow | `apps/web/app/page.tsx`, `apps/web/app/_components/login-form.tsx`, `apps/web/app/auth/callback/route.ts`, `packages/auth/src/link.ts` | `apps/web/app/admin/**`, framework files |
| Change the sign-out flow | `apps/web/app/auth/signout/route.ts`, `apps/web/app/_components/logout-button.tsx` | client-side cookie-clearing — let the server route do it |
| Add a new admin dashboard tab | `apps/web/app/admin/<tab>/page.tsx`, `apps/web/app/admin/layout.tsx` (nav link) | RLS policies (admin uses service-role server-side) |
| Add an RLS policy | new `packages/db/migrations/sql/NN_rls_*.sql` file | already-applied `21_rls_policies.sql` |
| Add a new admin view | new `packages/db/migrations/sql/NN_admin_views.sql` file | already-applied `30_admin_views.sql` |
| Add a new worker job | `apps/workers/src/trigger/<job>.ts`, `apps/workers/trigger.config.ts` | `apps/web/**` |
| Change embedding model or dimension | `packages/ai/src/embeddings.ts`, schema `vector(N)` column, migration SQL | _(see Idiosyncratic Decisions — vector dim is locked)_ |
| Add a new env var | `.env.example`, `turbo.json` `globalEnv` array, `docs/configuration.md` | `.env.local` is not in git; never commit it |
| Tweak chat UI | `apps/web/app/channels/[channelId]/_components/channel-chat.tsx` | shadcn primitives, `next.config.ts` |

---

## 8. Data model / custom objects

The full schema lives in `packages/db/src/schema.ts` and is faithful to `oracle_master_spec.md` Part 6. The tables below are the load-bearing ones — every other table joins through these.

| Entity | Identifier | Where defined | Notes |
|---|---|---|---|
| Employee | `employees.id` (uuid) | DB | Authorization roster. `email` is the **primary contact** + first-login bootstrap. Auth identity lives in `employee_identities`, not on this row. `departments text[]` is the authoritative multi-value department list (soft hint for retrieval). `department varchar` is deprecated (nullable, kept for backward compat) — read `departments` in all new code. |
| Employee identity | `employee_identities.id` (uuid) | DB | One row per (employee × auth provider). `auth_user_id` is Supabase's `auth.users.id`. One employee can hold many identities (Google, Microsoft 365, future Authentik). See Idiosyncratic Decisions. |
| Auth user | `auth.users.id` (uuid) | Supabase Auth | Managed by Supabase. Owned by the identity provider. |
| Channel | `channels.id` (uuid) | DB | Group or 1:1 chat. Membership via `channel_participants`. |
| Message | `messages.id` (uuid) | DB | Includes `client_message_id` for client-side dedup, `extraction_status` for the worker pipeline. |
| Document | `documents.id` (uuid) | DB | Lives in Supabase Storage bucket `company_documents`. Storage path is `(storage_bucket, storage_path)` (unique). |
| Document chunk | `document_chunks.id` (uuid) | DB | Always linked to a document. Carries page/sheet/row/bbox metadata. Has `embedding vector(1536)`. |
| Claim | `claims.id` (uuid) | DB | A universal operational assertion. **Intentionally has no direct `employee_id`** — query through `claim_evidence.asserted_by_employee_id`. Has `embedding vector(1536)`. |
| Claim evidence | `claim_evidence.id` (uuid) | DB | The traceability backbone. Every claim must have ≥1 evidence row. `source_type` ∈ {`message`, `document_chunk`, `external_system`, `manual_admin`} and the matching FK column is enforced by `claim_evidence_source_check`. |
| Brain section | `brain_sections.id` (string slug, e.g. `creative_to_technical_handoff`) | DB | Soft-referenced `current_version_id` is filled via two-step transactional insert (see spec 6.7). |
| Gap, Contradiction, Oracle intervention | uuid | DB | All link back to claims/messages/employees for audit. |
| Model run / Job run | uuid | DB | Observability. Every LLM call → `model_runs`. Every Trigger.dev task → `job_runs`. |
| Oracle context pack | `oracle_context_packs.id` (uuid) | DB | **R3.** Full `OraclePromptPlan` per AI call — block list, hashes, retrieval plan, included record IDs. `model_run_id` is nullable so the pack can be created before the run. |
| Model run usage detail | `model_run_usage_details.id` (uuid) | DB | **R3.** 1:1 child of `model_runs` (`UNIQUE(model_run_id)`) with the full `OracleUsage` shape: cached/cache-write/reasoning tokens, raw provider usage JSON, and fallback dispatch tracking. |
| Provider cached content | `provider_cached_content.id` (uuid) | DB | **R3.** Explicit Vertex cache tracking with required `expected_reuse_count`, `latest_planned_reuse_step`, `hard_expiration_at`, `cleanup_owner`, and `status` ∈ `(active, deleted, expired, failed, orphaned)`. CHECK constraint enforces `deleted_at IS NULL iff status='active'`. |
| Knowledge top domain | `knowledge_top_domains.id` (text, e.g. `customer_ops`) | DB | **R3.5.** Layer 1 of the 3-layer taxonomy. Admin-curated; carries boundary rules (`belongs_here`, `does_not_belong_here`, `common_entity_hints`, `default_excluded_document_classes`, `neighboring_domain_ids`). Seeded with 12 domains. |
| Knowledge sub-topic | `knowledge_sub_topics.id` (uuid) | DB | **R3.5.** Layer 2 — auto-discovered, admin-approved. Empty on install. `centroid vector(1536)` with HNSW index. |
| Entity | `entities.id` (uuid) | DB | **R3.5.** Layer 3 canonical registry. UNIQUE `(entity_type, canonical_value)`. `licensor` is a first-class entity type distinct from `vendor`; operating-vendor subtypes (`factory`, `freight_provider`, `testing_lab`, `packaging_supplier`, `service_provider`) are also enumerated. Seeded with 56 entities. |
| Claim top-domain assignment | `claim_top_domains.(claim_id, top_domain_id)` | DB | **R3.5.** Multi-valued join replacing the single `knowledge_domain` enum column. Carries `assignment_confidence` + `assignment_reason`. Mirror tables exist for documents, document chunks, and messages so retrieval can scope BEFORE claims are promoted. |
| Claim metadata | `claim_metadata.claim_id` (uuid) | DB | **R3.5.** Orthogonal axes: `process_stage`, `department`, `geography`, `document_class`, `effective_from`, `effective_until` (`NULL` means "currently in effect"), `superseded_by_claim_id`. |
| Taxonomy proposal | `taxonomy_proposals.id` (uuid) | DB | **R3.5.** Auto-mutation prohibited — admin must approve. CHECK constraint forces `status<>pending` to record reviewer + timestamp. |
| Entity proposal | `entity_proposals.id` (uuid) | DB | **R3.5.** Unknown entity references queued by extraction. CHECK constraint forces `merged_into_existing` to record `merged_into_entity_id`. |
| Extraction batch | `extraction_batches.id` (uuid) | DB | **R4.** One row per extraction job segment. Carries the circuit-breaker fields: `validation_attempt_count`, `consecutive_quote_failure_count`, `model_run_ids_attempted` (jsonb), `route_ids_attempted`. |
| Extraction candidate | `extraction_candidates.id` (uuid) | DB | **R4.** One row per proposed claim. Sensitivity-gate flags (`contains_sensitive_personal_data`, `contains_sensitive_hr_data`, `is_personal_conflict`) are first-class columns; CHECK constraint forces `rejected_sensitive`/`quarantined_sensitive` status to set at least one flag. |
| Extraction candidate evidence | `extraction_candidate_evidence.id` (uuid) | DB | **R4.** Stores both model-provided AND validator-confirmed quote/offsets. CHECK constraint forces validation pass to populate the validated fields — no silent passes. Source-type/pointer consistency mirrors spec 6.8. |
| Extraction validation result | `extraction_validation_results.id` (uuid) | DB | **R4.** One row per deterministic check executed; powers the failure-mode taxonomy in `06-evaluation-framework.md`. |
| Claim candidate hash | `claims.candidate_hash` (varchar(64), nullable) | DB | **R7.** sha256 hex of the canonicalized candidate (see `computeCandidateHash`). Partial UNIQUE index `WHERE candidate_hash IS NOT NULL` enforces "no two distinct claims share the same canonicalized hash" across cron runs. NULL on pre-R7 historical rows. |
| Document → top-domain assignment | `document_top_domains.(document_id, top_domain_id)` | DB | **R3.5.** Multi-valued join; R7's document worker writes these via `executePromotion`'s success path so retrieval can scope at the document level before any claim search runs. |
| Document chunk → top-domain assignment | `document_chunk_top_domains.(document_chunk_id, top_domain_id)` | DB | **R3.5.** Same as above, chunk-level. |
| Document evidence metadata | `extraction_candidate_evidence.documentClass`, `processStage` (varchar(100), nullable) | DB | **R5.5.** Nullable per-evidence metadata that R5.5's extraction prompt can surface inline; the promoter writes these through to `claim_metadata`. |

**External system identifiers** (do not change casually; recorded so a future migration doesn't break references):

| Item | Identifier | Source | Notes |
|---|---|---|---|
| GitHub repo | `u2giants/theoracle` | GitHub | **Public**. Never commit secrets. |
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Vercel | The web app deploys here. |
| Supabase project | _(see Vercel env)_ | Supabase | Database, Auth, Storage, Realtime. |
| Trigger.dev project | _(see Vercel env)_ | Trigger.dev | Background workers. |
| Supabase Storage bucket | `company_documents` | Supabase | Private. Holds uploaded employee documents. |
| Brevo (SMTP) | account on file | Brevo | Used by Supabase Auth to deliver magic-link emails. Configured in Supabase → Authentication → SMTP Settings. |
| Interview route ID (target) | `anthropic_claude_haiku_4_5_interview_primary` | `settings.default_interview_route` row | Set by Admin → Settings model picker. Target route IDs per `docs/oracle/01-model-roles-and-routes.md`. |
| Extraction route ID (target) | `vertex_gemini_2_5_flash_extraction_primary` | `settings.default_extraction_route` row | Set by Admin → Settings. |
| Synthesis route ID (target) | `anthropic_claude_3_5_sonnet_synthesis_primary` | `settings.default_synthesis_route` row | Set by Admin → Settings. |
| Embedding model | `text-embedding-3-small` (OpenAI, 1536-dim) | hardcoded in `packages/ai/src/embeddings.ts` | Vector column is `vector(1536)` — see Idiosyncratic Decisions. |

---

## 9. Container / runtime inventory

This project does not use containers. Everything is fully managed cloud per spec Part 2.5 — no Dockerfiles, no VPS, no reverse proxies.

| Runtime | Purpose | Managed by | Identifier | Notes |
|---|---|---|---|---|
| Vercel Functions | `apps/web` — Next.js App Router + API routes | Vercel | project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Fluid Compute, Node.js 24 runtime |
| Trigger.dev v3 | `apps/workers` — claim extraction, ingestion, contradiction watcher, synthesis | Trigger.dev Cloud | project key in `TRIGGER_SECRET_KEY` | Background workers. May bypass RLS (service-role). |
| Supabase Postgres | Source of truth — all durable data | Supabase Cloud | URL in `NEXT_PUBLIC_SUPABASE_URL` | pgvector for embeddings, RLS enforced. Connection through **pooler** URLs only — direct connections are IPv6-only on new Supabase projects. |
| Supabase Storage | Uploaded documents | Supabase Cloud | bucket `company_documents` | Private bucket. |
| Supabase Auth | Identity | Supabase Cloud | — | Google OAuth + Microsoft 365 SSO (live); email magic-link (fallback). OAuth providers are configured in the Supabase Dashboard. |
| Supabase Realtime | Chat / presence | Supabase Cloud | — | `postgres_changes` for messages; presence channel for typing. |
| Brevo | SMTP for magic-link emails | Brevo | account on file | Configured in Supabase Auth → SMTP Settings; replaces Supabase's built-in throttled SMTP. |
| OpenAI | Embeddings only (`text-embedding-3-small`) | OpenAI | account on file | Optional — falls back to deterministic zero vector if `OPENAI_API_KEY` is unset; **vector dimension does not change**. |

---

## 10. What to ignore

Directories/files an AI agent should not index, scan, or read into context:

```gitignore
node_modules/
.next/
dist/
.turbo/
.vercel/
coverage/
*.log
pnpm-lock.yaml      # giant, low signal; trust package.json
apps/web/.next/
packages/db/migrations/0NNN_*.sql   # generated Drizzle output; the source of truth is schema.ts
```

Files you SHOULD read when getting oriented:

1. `AGENTS.md` (this file)
2. `oracle_master_spec.md` (product spec)
3. `DECISIONS.md` (assumptions log)
4. `HANDOFF.md` (live state — what's done, what's next)
5. `packages/db/src/schema.ts` (data model)
6. `packages/db/migrations/sql/*.sql` (RLS, constraints, views — hand-written, all signal)
7. `packages/ai/src/prompts/oracle-system.ts` (Oracle's voice)

---

## 11. Idiosyncratic decisions

The most important section. **Do not undo these without reading the cited spec section and updating `DECISIONS.md`.**

### Claims have no `employee_id` column

**Looks like:** an obvious schema bug — every "who said it" lookup requires a join.

**Actually:** spec Part 6.6 explicitly forbids it. A claim is a universal operational assertion that can be supported by multiple employees, documents, or external systems over time.

**Why:** if a claim is asserted by Employee A in a Slack message, then re-confirmed by Employee B in an interview, then contradicted in a document chunk uploaded by Employee C, attaching the claim to a single `employee_id` would erase that history. The `claim_evidence` table carries `asserted_by_employee_id`, `uploaded_by_employee_id`, and `created_by_employee_id` per evidence row.

**Do not change because:** breaks traceability. The whole product collapses if "why does the Oracle believe this" can't be answered with multiple evidence rows.

### One employee, many auth identities — `employee_identities` table

**Looks like:** an extra table for what could be a single (provider, auth_user_id, email) tuple on `employees`.

**Actually:** spec Part 4.3 calls for `auth_provider` and `auth_provider_subject` fields on employees, but the same human can legitimately authenticate via multiple providers (Google + Microsoft 365 + future Authentik) with different verified emails. Forcing one identity per employees row created a second Albert when he signed in via M365 after Google.

**Why:** see DECISIONS.md D2.multi-identity. The linker in `packages/auth/src/link.ts` resolves a session by `(auth_provider, auth_user_id)` first; on miss it falls back to matching the verified provider email against `employees.email` OR any `employee_identities.email` and creates a new identity row attached to the existing employee.

**Do not change because:** reverting to a single-row-per-identity layout will re-introduce the duplication bug. The `auth_user_id`, `auth_provider`, and `auth_provider_subject` columns on `employees` are flagged deprecated (nullable, NULL-filled) only because removing them mid-session would force a column-drop migration; a follow-up commit will fully remove them.

### `brain_sections.current_version_id` is a soft reference

**Looks like:** a missing foreign-key constraint between `brain_sections` and `brain_section_versions`.

**Actually:** spec Part 6.7. The two tables reference each other circularly (section → current version → section). A hard FK would make initial insertion impossible without `DEFERRABLE INITIALLY DEFERRED`, which Drizzle doesn't model cleanly.

**Why:** brain sections are created in a documented two-step transaction: insert section with `current_version_id = NULL`, insert first version, update section's `current_version_id`. The seed and the synthesis worker both follow this pattern.

**Do not change because:** adding a hard FK breaks the synthesis worker. If you ever want one, model it as `DEFERRABLE` in a hand-written SQL migration.

### Embedding dimension is locked to 1536

**Looks like:** an opinionated choice that ties us to OpenAI's `text-embedding-3-small`.

**Actually:** spec Part 6.4 declares `vector('embedding', { dimensions: 1536 })`. The Drizzle schema, the HNSW indexes (`packages/db/migrations/sql/99_vector_indexes.sql`), and any prior embeddings already in the table all assume 1536.

**Why:** changing the dimension means re-embedding every chunk and claim — expensive and destructive. If `OPENAI_API_KEY` is unset we fall back to a **deterministic zero vector of the same dimension**, never a different dimension.

**Do not change because:** silently changing the dim corrupts vector similarity and renders all existing claims/chunks un-searchable.

### Microsoft 365 OAuth requires the `email` scope explicitly

**Looks like:** the default scopes from Supabase should be enough.

**Actually:** Microsoft Entra accounts without an Exchange mailbox return an empty `mail` field from Microsoft Graph. Supabase reads `mail` and bails with "Error getting user email from external provider" if it's empty. The `email` OIDC scope forces an email claim into the ID token regardless of mailbox state.

**Why:** the login form (`apps/web/app/_components/login-form.tsx`) passes `scopes: 'openid profile email User.Read'` for Azure. Symmetric `openid profile email` for Google.

**Do not change because:** removing the scope re-introduces the "Error getting user email from external provider" denial on first M365 login. The Azure App registration must also have `email`, `openid`, `profile`, `User.Read` as delegated Microsoft Graph permissions with admin consent granted.

### `claim_evidence_source_check` CHECK constraint over JSON schemas

**Looks like:** belt-and-suspenders — Zod could enforce this.

**Actually:** the constraint runs at the DB level so background workers, admin SQL, manual inserts, and future non-TypeScript integrations all get the same guarantee.

**Why:** spec Part 6.8 mandates it. Different `source_type` values require different FK columns to be non-null. Application-level validation is bypassed by workers, by SQL migrations, and by any future Coldlion sync.

**Do not change because:** removes a critical invariant; allows orphaned claims with no evidence pointer.

### Supabase Postgres connection uses the pooler, not the direct hostname

**Looks like:** the most obvious URL on Supabase's "Connection string" page is the Direct connection. Use that.

**Actually:** the `db.<project-ref>.supabase.co` direct hostname is **IPv6-only** on new Supabase projects. IPv4-only networks (most consumer ISPs, most CI) get `getaddrinfo ENOENT` and fail. Use the **Session pooler** (port 5432) for `DIRECT_URL` and the **Transaction pooler** (port 6543) for `DATABASE_URL`. Both run on `aws-0-<region>.pooler.supabase.com` over IPv4 once you toggle "Use IPv4 connection (Shared Pooler)" on the Supabase connection page.

**Why:** the migration runner (`packages/db/src/migrate.ts`) and the application client both read from `.env.local`. If either gets a `db.*.supabase.co` URL on IPv4, the connection fails opaquely.

**Do not change because:** changing back to the direct hostname requires the paid IPv4 add-on from Supabase. The poolers are the recommended path.

### Drizzle migrations applied via a custom `migrate.ts` rather than `drizzle-kit push`

**Looks like:** reinventing the wheel.

**Actually:** the runner in `packages/db/src/migrate.ts` applies Drizzle-generated migrations **and** every file in `packages/db/migrations/sql/` in lex order (extensions → identities → constraints → RLS helpers → policies → views → data migrations → vector indexes).

**Why:** Drizzle doesn't model raw SQL migrations cleanly. We need extensions, RLS, CHECK constraints, and views applied in a specific order, idempotently.

**Do not change because:** `drizzle-kit push` will skip the `migrations/sql/` files entirely and leave the database without RLS or constraints. See `packages/db/migrations/sql/README.md` for the ordering convention.

### `.env.local` lives at the monorepo root; `next.config.ts` loads it explicitly

**Looks like:** Next.js's built-in dotenv should find `.env.local` automatically.

**Actually:** Next only reads `.env.local` from the app's own directory (`apps/web/`). The monorepo keeps secrets at the repo root because the migration runner, seed scripts, and worker scaffolds need them too. `apps/web/next.config.ts` calls `dotenv.config({ path: resolve(__dirname, '..', '..', '.env.local') })` to load them.

**Why:** one source of truth for secrets. Duplicating `.env.local` into each workspace would invite drift.

**Do not change because:** removing the explicit load makes the web app see `<EMPTY>` for `NEXT_PUBLIC_SUPABASE_URL` and friends. Same logic applies to `packages/db/src/{migrate,seed}.ts` which also load from the monorepo root.

### `employees.department` is deprecated — use `departments text[]`

**Looks like:** two fields for the same concept.

**Actually:** `department varchar(255)` was the original single-value field. It is kept nullable for backward compat during migration. `departments text[]` (added in session 3) is the authoritative source — supports employees who belong to multiple departments.

**Why:** most POP Creations employees span multiple departments (e.g. Production + Creative). A single string forces an arbitrary choice and discards the rest. The multi-value array passes all departments as `departmentHints` to `searchWithRetrievalPlan`, which applies a small RRF score bonus (+0.002) to claims whose `claim_metadata.department` matches any of the employee's departments. This is a soft signal — it nudges ranking without filtering results.

**Do not change because:** reverting to a single value breaks the RRF multi-department weighting. The data migration (`packages/db/migrations/sql/56_employees_departments_array.sql`) copies the old single value into the new array for existing rows, so both fields are populated after `pnpm db:migrate`.

### Test employee in seed (`test-employee@oracle.local`)

**Looks like:** leaked test data.

**Actually:** required to test the Phase 2 RLS gate (channel isolation needs two employees).

**Why:** the spec's acceptance gate for Phase 2 requires proving employee A can't read a channel where they aren't a participant — impossible with only the admin row.

**Do not change because:** removing it breaks the RLS verification. Note that `.local` is not a real TLD — to actually wet-test Phase 2 you need to either update this row's email to a real mailbox (e.g. a Gmail `+`-alias) or seed a second real employee. **DO delete this row before production rollout** (tracked in Pending Work below).

### `vercel.json` at the repo root is required — don't delete it

**Looks like:** "Vercel auto-detects Next.js — we don't need a config file."

**Actually:** the auto-detection assumes the Next app is at the repo root. Ours lives at `apps/web/`, so Turbo writes `.next` to `apps/web/.next`. Without `vercel.json` telling Vercel where to look, the build itself succeeds and then the finalize step errors with `The Next.js output directory ".next" was not found at "/vercel/path0/.next"`. Every production deploy fails silently this way until you check Vercel's deployment list.

**Why:** `vercel.json` declares `framework: "nextjs"`, `buildCommand: "pnpm --filter @oracle/web build"` (Turbo-aware), `installCommand: "pnpm install --frozen-lockfile=false"`, and `outputDirectory: "apps/web/.next"` (the actual location). Committing this keeps the deploy contract in the repo so it survives a future Vercel project recreation.

**Do not change because:** removing or breaking `vercel.json` will silently fail every production deploy. The dev server (`pnpm --filter @oracle/web dev`) is unaffected because it has nothing to do with Vercel's build pipeline — so a broken `vercel.json` is invisible from local dev. See `docs/deployment.md` → "vercel.json — required for this monorepo".

### Production `next build` runs TypeScript; `next dev` (Turbopack) does not

**Looks like:** "Local dev works, so the types are fine — push it."

**Actually:** `next dev` with Turbopack skips the tsc pass entirely for speed. `next build` runs full strict tsc. A type error that the dev server ignores will fail the Vercel production build. This bit us hard on 2026-05-20 — the `OracleDb` vs `Db` mismatch in retrieval helpers and the implicit-any cookie adapter params in `packages/auth/src/server.ts` were both runtime-safe but production-build-fatal. ~an hour of failed deploys before we caught it.

**Why:** there's no equivalent of `tsc --noEmit` baked into the dev loop. The safety net is `pnpm --filter @oracle/web build` — run that **before pushing changes that touch types** and you'll see exactly what Vercel will see. `pnpm typecheck` alone is not enough; it skips Next-specific type generation.

**Do not change because:** turning the type check off in `next.config.ts` (`typescript.ignoreBuildErrors: true`) would unblock builds but ship runtime time-bombs. Keep the gate. The right place to enforce it long-term is a GitHub Action that runs `pnpm --filter @oracle/web build` on every PR — that's in pending work.

### `licensor` is a first-class entity type, distinct from `vendor`

**Looks like:** an over-segmentation. Why not just have `vendor` and let the model figure it out?

**Actually:** POP Creations sells licensed entertainment products (Disney, Marvel, Star Wars, NBCUniversal, Warner Bros — see master spec Part 1.1). Licensors govern approvals, art/brand rules, legal permissions, and style-guide constraints. Operating vendors (factories, freight providers, testing labs) govern capacity, lead times, customs paperwork, and cost. These two categories almost never share answers.

**Why:** if `licensor` and `vendor` are collapsed, a query like *"when do Disney approvals need to happen before production"* will retrieve generic factory manuals and freight invoices, which is operationally wrong. Boundary rules on `knowledge_top_domains` reinforce this — the `licensing_approvals` domain explicitly lists `vendor_manual` and `freight_invoice` as default-excluded document classes. The CHECK constraint on `entities.entity_type` and `entity_proposals.proposed_entity_type` includes both `licensor` and `vendor` (plus the operating-vendor subtypes `factory`, `freight_provider`, `testing_lab`, `packaging_supplier`, `service_provider`) so the schema enforces the split at write time.

**Do not change because:** collapsing the types re-introduces the cross-contamination at retrieval time. The taxonomy needs the discrimination, not the LLM.

### `claim_metadata.time_validity` is two timestamp columns, not `tstzrange`

**Looks like:** an unnecessary deviation from the schema sketch in `docs/oracle/07-knowledge-segmentation.md`, which uses `tstzrange`.

**Actually:** Drizzle ORM doesn't model `tstzrange` cleanly, and using `WHERE effective_until IS NULL` to mean "currently in effect" is far more obvious in app code than range overlap operators. The sketch was illustrative; the final schema picks the form that survives application contact. Doc 07 has been updated to call this out (half-open `[effective_from, effective_until)` semantics).

**Do not change because:** rewriting to `tstzrange` would force a custom Drizzle type plus all consumers would have to learn `@>` and other range operators. The two-column form covers every case the spec needs.

### Stable prefix MUST precede dynamic content in `ContextCompiler`

**Looks like:** a strict, almost legalistic invariant that throws an error if violated.

**Actually:** the entire `cache_hit_ratio` metric depends on this. Anthropic prefix caching, Vertex implicit caching, and OpenAI automatic prefix caching ALL identify the cacheable prefix by exact byte-identical content at the start of the prompt. If a dynamic block (current user message, timestamp, retry suffix) appears anywhere before a stable block, the prefix hashes differently on every call and the cache is permanently busted.

**Why:** `packages/ai/src/context/context-compiler.ts` throws if a stable block appears after a dynamic block. The compiler also sorts by `KIND_ORDER` automatically, so most callers don't have to think about it — but the throw catches anyone who tries to bypass the sort by inserting blocks in a `dynamic_input` slot that should be `semi_stable_domain_context`.

**Do not change because:** silently allowing the bypass means the cache hit ratio in dashboards looks healthy while every call is actually paying full input-token price. That regression is invisible without provider-native usage tracking, which we now have but which would only show the problem after a bill arrives.

### Direct provider adapters use raw SDKs — Vercel AI SDK is forbidden in this folder

**Looks like:** the adapter code in `packages/ai/src/providers/` imports `@anthropic-ai/sdk`, `@google/genai`, and `openai` directly, hand-flattens prompt blocks into provider-specific message shapes, hand-converts Zod schemas to JSON Schema, and hand-normalizes usage. There's a `Vercel AI SDK` (`ai` package, `@ai-sdk/*` providers) that would be cleaner.

**Actually:** the project tried that path during R-providers (commit `cf8f087`) and reverted (commit `bfc0821`). `docs/oracle/02-provider-native-ai-architecture.md` §"Shared architecture" forbids the Vercel AI SDK by name. `DECISIONS.md` D6 + D9 record why: the `@ai-sdk/*` wrappers normalize provider-specific cache fields (`cache_read_input_tokens` vs `cachedContentTokenCount` vs `prompt_tokens_details.cached_tokens`) through a uniform-but-lossy abstraction, and they collapse three distinct structured-output strategies (tool call / `responseJsonSchema` / `response_format` strict) into one `generateObject` signature that takes away per-provider tuning. The R7 cache lifecycle and the wet-test JSON-schema enforcement both depend on having native access.

**Do not change because:** re-introducing `@ai-sdk/*` violates D6 + D9 directly. If a future provider's structured-output mode is too complex to hand-wire, add a tightly-scoped helper inside the relevant adapter rather than reaching for the SDK.

### OpenRouter is enrichment-only — the inference routing wrapper is gone on purpose

**Looks like:** The `sources/openrouter.ts` file references OpenRouter, and `OPENROUTER_API_KEY` is still read in production code. Looks like OpenRouter is still in the production AI path.

**Actually:** `packages/ai/src/model-capabilities/sources/openrouter.ts` calls OpenRouter's `/v1/models` endpoint to fetch pricing and capability flags (vision, thinking, tool-calling, etc.) for enrichment of the model catalog. It is never in the inference path. The inference routing wrapper that was `packages/ai/src/openrouter.ts` (deleted in commit `b01e514`) and its deps (`@openrouter/ai-sdk-provider`, `getOpenRouter()`) are gone. OpenRouter does not handle any LLM calls.

**Why:** OpenRouter's `/v1/models` is the best public source for pricing per token, capability flags, and context windows across all three providers. The model list itself comes from each provider's own API (Anthropic `/v1/models`, OpenAI `/v1/models`, Google Gemini `/v1beta/models`); OpenRouter enriches each model after the list is built.

**Do not change because:** Re-routing inference through OpenRouter would violate DECISIONS.md D6 + D9. Removing the OpenRouter enrichment source would leave pricing and capability flags as null/unknown for all models in the catalog.

### Pure-function-first design in `packages/oracle-engines/src/extraction/`

**Looks like:** R5 / R5.5 / R6 / R7 ship a lot of pure functions (`validateQuote`, `decidePromotion`, `resolveEntity`, `validateTaxonomy`, `decideCircuitBreaker`, `decideCacheProfitability`, `computeCandidateHash`, `mapLegacyDomainsToTopDomains`, `estimateTokensForCache`) that take inputs and return decisions — without touching the database directly.

**Actually:** the workers compose them with DB I/O explicitly. The DB-touching helpers (`executePromotion`, `recordCacheCreation`, `recordCacheTermination`, `recordCacheReuse`) are thin wrappers around Drizzle inserts. The split is intentional so:

1. **Smoke gates run without API keys, DB, or network.** 127 assertions across R2/R5/R5.5/R6/R7 verify business logic in milliseconds, in CI, on any machine.
2. **Decision logic is auditable.** A reviewer can read `decidePromotion` in 60 lines and know exactly when an `insert_new_claim` becomes an `append_to_existing_claim` becomes a `reject`.
3. **Tests don't have to mock Drizzle.** The R5 smoke test verifies "duplicate promotion retry safety" by calling `decidePromotion` with a snapshot where `candidate.status === 'promoted'` — no mock DB, no fake transaction.

**Do not change because:** moving business logic into the DB-touching helpers would re-couple decision and execution, force smoke tests to spin up a Postgres, and bury invariants that should be one function lookup away.

### Synthesis rejection inserts a `reviewStatus='rejected'` version row

**Looks like:** the synthesis worker (`apps/workers/src/trigger/brain-synthesis.ts`) inserts a `brain_section_versions` row even when validation fails, but doesn't update `brain_sections.currentVersionId`. That seems wasteful — why insert anything?

**Actually:** the row IS the audit trail. Per the R9 spec, "store failed synthesis output for review." The existing `brainSectionReviewStatusEnum` already had `'rejected'` as a value, so R9 just uses it. The rejected version preserves the full `updatedMarkdown` the model produced, plus the structured `validationFailures` + `unsupportedNames` in `structuredContent`, so an admin can inspect exactly what the model produced and which checks fired — without changing the current Brain version anyone reads.

**Why:** the `currentVersionId` pointer is the ONLY way the live Brain is read. Leaving it unchanged on rejection means production traffic doesn't see the broken output. The version row is queryable via the existing admin pages (`/admin/brain`), and its `changeSummary` field records the failure summary inline.

**Do not change because:** dropping the row entirely loses the audit trail. Auto-applying the failed output to `currentVersionId` exposes broken synthesis to the user.

### `/admin/ai/candidates` deliberately hides sensitive material

**Looks like:** the candidate dashboard's `"all"` filter doesn't actually show all candidates. It excludes `rejected_sensitive` and `quarantined_sensitive` rows.

**Actually:** that's the only filter that should never accidentally show those rows. Per `docs/oracle/03-candidate-before-claim-validation.md`: "Sensitive rejected/quarantined candidates must not appear in this standard queue." The R10 candidates page enforces this at the SQL level — the `"all"` tab's SQL query explicitly `WHERE status NOT IN ('rejected_sensitive','quarantined_sensitive')`. Sensitive rows are reachable ONLY via the explicit "Sensitive (hidden by default)" tab.

**Why:** PII, HR conflict, and disciplinary material that the extractor flags as sensitive must NEVER leak into the standard admin queue. A simple `WHERE status = ?` filter on the candidates page would let them slip through any time the admin clicked "all". The structural exclusion in the SQL means no UI toggle accident can change that.

**Do not change because:** the exclusion is a privacy guarantee that the candidate-before-claim spec mandates. If you need to inspect a specific sensitive case, the explicit "Sensitive" tab is the only path; flipping the SQL would weaken the guarantee for all queries.

### Race-safe promotion: candidate snapshot + hash lookup inside the advisory lock

**Looks like:** the executor (`packages/oracle-engines/src/extraction/promotion-executor.ts`) does an `existingClaimWithSameHash` lookup AND re-reads the candidate row + validated evidence INSIDE the Drizzle transaction, after `pg_try_advisory_xact_lock(hashtextextended($1, 0))` returns. The caller seemingly does the same SELECTs minutes earlier; doing them again inside the lock looks wasteful.

**Actually:** the caller's reads happen BEFORE the advisory lock is held. Between the caller's reads and the executor's lock acquisition, another worker can mutate the staging tables — promote the same candidate, mark it `validation_failed`, append additional evidence rows, or trip the sensitivity gate. The in-lock re-read closes that race window. The two race-relevant lookups are distinct branches of the decision:

- **Same candidate, re-read inside the lock, status no longer `validated`** (e.g. promoted by another worker, sensitivity quarantined) → `decidePromotion` returns `reject(already_promoted)` or `reject(not_validated)`. The candidate row itself is in a terminal state.
- **Different candidate, same hash** (the in-lock `claims WHERE candidate_hash = $hash` SELECT finds a row) → `decidePromotion` returns `append_to_existing_claim`. The current candidate is still `validated`; some other candidate (a parallel extraction of the same fact) already committed a claim with the same canonicalized hash. Our validated evidence is appended to their claim and our candidate is marked `duplicate`.

**Why:** the advisory lock + in-transaction candidate re-read + in-transaction hash lookup + partial UNIQUE on `claims.candidate_hash` together form the cord that makes promotion idempotent across worker restarts and cron retries. Pulling any of those reads outside the lock re-introduces a race.

**Scope of what's protected:** the candidate row + validated evidence + same-hash claim lookup. The caller-provided `auxiliaryInputs.taxonomy` and `auxiliaryInputs.metadata` are NOT race-protected — taxonomy mutations (`/admin/taxonomy` approvals) are admin-paced (minutes/hours), not worker-paced (ms), so registry drift between the caller's `validateTaxonomy()` and executor promotion is tolerated until production traffic shows it actually fires.

**Special case — missing candidate inside the lock:** if the candidate row is gone (extremely rare, would indicate either a bug or a manual delete), the executor returns `reject(invalid_state)` WITHOUT writing to `extraction_validation_results`. The FK target would be missing. This is the ONLY `reject` branch that skips the audit row; the caller logs the anomaly via `job_runs.error`.

**Do not change because:** moving any of these reads out of the lock re-introduces real races we've observed in design review. The mappers in `promotion-executor.ts` (`mapCandidateRowToSnapshotCandidate`, `mapEvidenceRowToValidatedEvidence`) are exported for testability — they're covered by 23 assertions in the R5 smoke gate (cases M1–M10).

### Logout uses a POST form to a server route, not client-side `signOut()`

**Looks like:** "just call `supabase.auth.signOut()` from a client button — simpler."

**Actually:** the SSR-Auth pattern requires server-side cookie clearing. `apps/web/app/auth/signout/route.ts` accepts POST, runs `supabase.auth.signOut()` with the cookie adapter, then redirects. The button (`apps/web/app/_components/logout-button.tsx`) is a `<form action="/auth/signout" method="post">`.

**Why:** client-only `signOut()` leaves server-rendered pages thinking the user is still signed in for the duration of the cached session JWT. POST also avoids accidental sign-outs from URL prefetchers / preview crawlers that fire GETs.

**Do not change because:** moving the signout to a client `useEffect` re-introduces the cached-session bug. If you need progress UI on sign-out, the form-action redirect already handles that without JavaScript.

### `resolveModelRoute()` accepts both catalog routeIds AND OpenRouter-style `provider/model` strings

**Looks like:** an overly permissive API that could silently accept any arbitrary string.

**Actually:** `packages/ai/src/routes/resolve.ts` (`resolveModelRoute(modelIdOrRouteId, role)`) first tries the curated catalog; if no catalog match, it parses a `provider/model` slash string and builds a synthetic `OracleModelRoute` pointing at the matching direct adapter. Workers read `settings.default_*_route`, which can hold either a catalog ID (the default) or a model ID from the admin's model-pool picker. The resolver bridges the two.

**Why:** the model pool UI at `/admin/settings/model-pool` lets the admin select models by OpenRouter ID (e.g. `anthropic/claude-haiku-4-5`) which the curated catalog doesn't know about. Without the resolver, any non-catalog model ID selected in the UI would cause all workers to fail at startup. The synthetic route picks the right adapter via `OR_PROVIDER_MAP` (`google/` → `vertex`, `anthropic/` → `anthropic`, `openai/` → `openai`).

**Do not change because:** removing the fallback parsing means only catalog routeIds work, breaking the model-pool UI for any model the admin selects that isn't already in the curated catalog.

### `RetrievalPlan.searchScope` is mandatory — every plan must declare its search intent

**Looks like:** a nullable or optional field you can skip when you "just want everything."

**Actually:** `packages/ai/src/retrieval-plan.ts` exports three factory functions: `buildRetrievalPlanFromQuery` (heuristic keyword classifier → `'domain_filtered'` or `'global_fallback'`), `buildDomainScopedPlan` (explicit domain list → `'domain_filtered'`), and `buildGlobalRetrievalPlan` (intentional all-corpus → `'global_explicit'`). Every caller picks one of these. There is no path that constructs a plan without a `searchScope`.

**Why:** without explicit scope tagging, global vector searches silently contaminate ERP answers with vendor-manual noise — exactly the failure mode the taxonomy and segmentation layers exist to prevent. `global_fallback` plans emit a `console.warn` with a structured object (query slice, hint about which keywords to add, impact label) and write `['_global_fallback']` to `oracle_context_packs.selected_domains` so admin can audit miss rates at `WHERE selected_domains @> ARRAY['_global_fallback']`. `global_explicit` (reserved for intentional all-corpus analysis) does the same but with `'_global_explicit'` and no warning.

**Do not change because:** adding a `searchScope`-free path re-opens the contamination problem. If a query keeps landing on `global_fallback`, the right fix is to expand `DOMAIN_KEYWORDS` in `retrieval-plan.ts`, not to make `searchScope` optional.

---

## 12. Credentials and environment

Never commit real values. `.env.local` is git-ignored. Reference values are in the Vercel project's Environment Variables tab (Production and Preview); local dev pulls them in via `npx vercel env pull` or manual paste.

| Variable | Purpose | Stored where | Required in dev | Required in prod |
|---|---|---|---|---|
| `DATABASE_URL` | Supabase Postgres — Transaction pooler URL (port 6543) | Vercel env, `.env.local` | yes | yes |
| `DIRECT_URL` | Supabase Postgres — Session pooler URL (port 5432) for Drizzle migrations | Vercel env, `.env.local` | yes | yes |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Vercel env, `.env.local` | yes | yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key for browser client | Vercel env, `.env.local` | yes | yes |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key (newer alias of anon) | Vercel env, `.env.local` | yes | yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Bypasses RLS — server-side only | Vercel env, `.env.local` | yes | yes |
| `ANTHROPIC_API_KEY` | Direct Anthropic API — `AnthropicAdapter` for interview chat (Claude Haiku 4.5) | `.env.local`, Vercel env, Trigger.dev (workers) | yes | yes |
| `GOOGLE_CLOUD_PROJECT` | GCP project for Vertex AI — `VertexGeminiAdapter` for extraction + synthesis (Gemini 2.5 Flash). Current value: `vertex-ai-497120`. | `.env.local`, Vercel env, Trigger.dev (workers) | yes | yes |
| `GOOGLE_CLOUD_LOCATION` | Vertex region (`us-central1`) | `.env.local`, Vercel env, Trigger.dev (workers) | yes | yes |
| Vertex auth | Application Default Credentials. Locally: `gcloud auth application-default login`. Cloud: service-account JSON mounted via `GOOGLE_APPLICATION_CREDENTIALS`. | `~/.config/gcloud/application_default_credentials.json` locally; secret-mounted JSON in cloud | yes | yes |
| `OPENAI_API_KEY` | Direct OpenAI API — `OpenAIAdapter` for fallback / schema-repair AND `text-embedding-3-small` embeddings (1536-dim) | `.env.local`, Vercel env, Trigger.dev (workers) | yes | yes |
| `TRIGGER_SECRET_KEY` | Trigger.dev server-side key | Vercel env (web), Trigger.dev (workers), `.env.local` | yes | yes |
| `TRIGGER_PROJECT_REF` | Trigger.dev project (`proj_wgpzsvhmsopqhvwqaycn`) | Vercel env, Trigger.dev, `.env.local` | yes | yes |

`OPENROUTER_API_KEY` is optional — `packages/ai/src/model-capabilities/sources/openrouter.ts` reads it when present to avoid rate limits on the public `/v1/models` endpoint. It is not required; the endpoint works unauthenticated. It is NOT used in any inference path.

For full details including the Sensitive-vs-Encrypted Vercel quirk, see [`docs/configuration.md`](docs/configuration.md).

---

## 13. Deployment

The deploy story is fully managed (no Docker, no VPS, per spec Part 2.5):

- **`apps/web` → Vercel.**
  - Vercel project ID: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`.
  - Auto-deploys on push to `main` (production) and on every PR (preview).
  - Build command: `pnpm install && pnpm --filter @oracle/web build`.
  - Output: Next.js 16 App Router on Fluid Compute (Node 24 runtime).
  - Runtime env vars: managed in Vercel → Settings → Environment Variables.
  - **Rollback:** Vercel dashboard → Deployments → promote the previous production deployment.

- **`apps/workers` → Trigger.dev Cloud.**
  - Project: `proj_wgpzsvhmsopqhvwqaycn`. Tasks across 7 files (claim-extraction, document-ingestion, contradiction-watcher, brain-synthesis, lull-interjection, taxonomy-reevaluation, taxonomy-reclassification); 11 exported tasks total.
  - Deploy manually: `pnpm --filter @oracle/workers deploy` (invokes `npx trigger.dev@latest deploy`).
  - Runtime env vars: managed in Trigger.dev project dashboard (not Vercel). Must include all the direct-provider keys + Vertex service-account JSON.
  - **Rollback:** redeploy from a prior commit, or disable the task in Trigger.dev's UI.

- **Database migrations** are run manually before deploying changes that need them: `pnpm db:migrate`. The runner is idempotent. There is currently no CI-driven migration step — adding one is a Pending Work item.

- **GitHub Actions:** `.github/workflows/pr-check.yml` is live (runs `pnpm --filter @oracle/web build` on PRs + pushes to `main`). `migrate.yml` and `workers-deploy.yml` are planned.

For step-by-step deploy operations and rollback procedures, see [`docs/deployment.md`](docs/deployment.md).

---

## 14. Critical incident log

| Date | Incident | What we learned |
|---|---|---|
| 2026-05-26 | R-providers wired with `@ai-sdk/*` wrappers (commit `cf8f087`) instead of raw SDKs | The Vercel AI SDK normalizes provider-specific cache fields and structured-output strategies through a uniform-but-lossy abstraction. `docs/oracle/02-provider-native-ai-architecture.md` §"Shared architecture" and DECISIONS.md D6 had already ruled this out by name. **Lesson:** read the relevant `docs/oracle/0N-*.md` BEFORE picking a dep. Reverted in commit `bfc0821`. Rule added: any new dep that lives in `packages/ai/src/providers/` must justify why it isn't a raw provider SDK. |
| 2026-05-26 | OpenRouter API key surfaced in tool output (`.env.local` line dump during R11.0) | Tool output containing file content is logged in the transcript. `.env.local` contained `OPENROUTER_API_KEY=sk-or-v1-...` at the time. **Lesson:** when dumping `.env.local`, always pipe through a `sed` redaction. Rule added: scripts that touch `.env.local` redact secret-shaped values before printing. The leaked key is being rotated as part of the pre-production checklist. |

When something goes wrong, append a section here using the format:

```markdown
### YYYY-MM-DD — Short title

What happened:
Impact:
Root cause:
Recovery:
Rule added to prevent recurrence:
```

---

## 15. Pending work

| Status | Item | Owner / next action |
|---|---|---|
| open | Delete the deprecated `auth_user_id` / `auth_provider` / `auth_provider_subject` columns from `employees` once all consumers are confirmed migrated | follow-up migration after a week of soak |
| open | Apply Drizzle migration `0006_magical_revanche.sql` + data migration `56_employees_departments_array.sql` to live Supabase: run `pnpm db:migrate` | before deploying session-3 code |
| open | Drop deprecated `employees.department` column once all code reads only `departments` | follow-up migration |
| done | **Session 3 — Employee multi-department + retrieval soft hint.** `employees.departments text[]` added. `departmentHints` RRF bonus in `searchWithRetrievalPlan`. Admin `/admin` employees page + "Add employee" form. SQL migration 56 + Drizzle migration 0006. | 2026-05-27 |
| open | Replace `test-employee@oracle.local` with a real mailbox (e.g. `u2giants+test@gmail.com`) so the Phase 2 RLS gate can be wet-tested with two real logins | Albert |
| open | Wet-test Phase 2 RLS (cross-channel isolation between two real employees) | after the test mailbox is set up |
| done | Wet-test Phase 3 chat route — `@oracle` posted, response received, `model_runs` row confirmed (6.3 s, 2001/98 tokens). Oracle also triggered after document uploads. | 2026-05-21 |
| open | Create the `company_documents` Storage bucket in Supabase if not already done | Albert (Supabase dashboard) |
| open | Wire Authentik OIDC as a third login provider for internal-only accounts | future build session |
| done | Deploy Phase 4 to Trigger.dev — version `20260521.1` with 7 tasks running in production (`proj_wgpzsvhmsopqhvwqaycn`). `TRIGGER_PROJECT_REF` set in `.env.local` + Vercel. | 2026-05-21 |
| done | **P1 #1 — Admin → Settings model pool UI** (`/admin/settings/model-pool`). `resolveModelRoute()` wired to all workers; correct `ROUTE_SETTING_KEYS`; `/api/admin/model-catalog` for OpenRouter Big-3 browsing. | commit `a6affc6` |
| done | Implement Phase 5 — Admin review dashboards (claims, gaps, contradictions, brain) | all four dashboards + server actions live; typecheck clean |
| done | **R1 — Curated Oracle model route catalog** | `packages/ai/src/routes/` (commit `91e44ea`) |
| done | **R2 — OracleAIClient + ContextCompiler + ModelRouter + provider adapter stubs** | commit `3c51c9b`; 16/16 smoke assertions pass via `pnpm --filter @oracle/ai verify:r2` |
| done | **R3 — Observability schema** (`oracle_context_packs`, `model_run_usage_details`, `provider_cached_content` + CHECK constraints + `model_runs_with_usage` view) | commit `1e345d3`; Drizzle migration `0001_hot_johnny_blaze.sql` + hand-written `11_observability_constraints.sql`, `31_observability_views.sql` |
| done | **R3.5 — Three-layer knowledge taxonomy schema** (15 tables; 12 top-domains with boundary rules seeded; 56 entities seeded; `licensor` first-class) | commit `c529594`; Drizzle migration `0002_demonic_kid_colt.sql` + hand-written `12_taxonomy_constraints.sql`, `16_knowledge_top_domains_seed.sql`, `17_entities_seed.sql`, `42_claim_top_domains_backfill.sql`, `48_taxonomy_vector_indexes.sql` |
| done | **R4 — Candidate-before-claim staging schema** (4 staging tables; 13 CHECK constraints incl. promoted-consistency, sensitive-consistency, validated-fields-required-on-pass) | commit `fe60304`; Drizzle migration `0003_magenta_lionheart.sql` + hand-written `13_extraction_constraints.sql` |
| done | **R5 — Quote validator + promotion decision** (pure functions in `packages/oracle-engines/src/extraction/{quote-validator,candidate-hash,promote-candidate}.ts`; 33/33 assertions via `pnpm --filter @oracle/engines verify:r5`) | commit `70339c6` |
| done | **R5.5 — Entity resolver + taxonomy validator** (`entity-resolver.ts` + `taxonomy-validator.ts`; `decidePromotion` extended with `entityAssignments` + `metadata` + `entityProposalsToStage`; 45/45 assertions via `verify:r5.5`) | commit `8cad256`; Drizzle migration `0004_simple_tomas.sql`. Wiring completed in P1 #2 + P2 #1 (commit `191b791`): `ExtractionClaimSchema` now includes `sensitivityFlags` + entity proposal fields; workers emit real sensitivity flags and entity proposals via `EXTRACTION_PROMPT_VERSION=2.0.0`. Licensor-vs-vendor resolver now fires in production. |
| done | **R6 — Refactor `apps/workers/src/trigger/claim-extraction.ts` through staging tables** (circuit breaker + promotion executor; smoke assertions via `verify:r6`) | commit `b46131d` (later swapped to direct adapters in R-providers) |
| done | **R7 — Refactor `apps/workers/src/trigger/document-ingestion.ts` through staging** (cache profitability heuristic + `provider_cached_content` lifecycle + race-safe executor + `claims.candidate_hash`; 19/19 assertions via `verify:r7`) | commit `a8a8586`; Drizzle migration `0005_kind_nekra.sql` + hand-written `14_claims_candidate_hash_unique.sql` |
| done | **R8 — Refactor `apps/web/app/api/chat/route.ts` through `OracleAIClient`** with `providerOptions` escape hatch for tools, multi-turn messages, `stopWhen`, `temperature` | commit `8a38fbd` |
| done | **R9 — Synthesis worker refactor + diff validator** (`brain-synthesis.ts` through `OracleAIClient`; `validateSynthesisDiff` in `packages/oracle-engines/src/synthesis/` with claim-ID + unsupported-named-entity checks; rejected-version preservation via `reviewStatus='rejected'`; 21-assertion smoke `verify:r9`) | commit `8343c2d` |
| done | **R10 — Admin AI observability dashboards** (6 pages under `/admin/ai`: dashboard, runs list, run detail / context pack viewer with retrieval diagnostics, cache, candidates with sensitive-hidden-by-default, evals placeholder) | commit `ea33d66` |
| done | **R10.5 — Taxonomy governance dashboard + re-evaluation worker** (5 pages under `/admin/taxonomy`; 4 transactional approve/reject server actions; scheduled `taxonomy-reevaluation` worker with k-means clustering body; companion `taxonomy-reclassification` worker that applies approved mutations idempotently) | commit `533f39b` for scaffold; `3cad3a1` (2026-05-27 session) for clustering body + reclassification job. The "continually re-evaluate domains for the first year" requirement is now fully automated end-to-end. Bulk-approve UX added to `/admin/taxonomy/proposals` in the same session. |
| done | Apply the new migrations to live Supabase DB | 2026-05-26 — applied via Supabase MCP this session. 6 Drizzle (0000–0005) + 18 hand-written SQL files. 51 public tables. Supabase advisor: 36 → 2. |
| done | **R-providers — Direct provider adapters** (`AnthropicAdapter` via `@anthropic-ai/sdk`, `VertexGeminiAdapter` via `@google/genai`, `OpenAIAdapter` via `openai`; all 4 production callers switched off the bridge) | commits `bfc0821` + `51a33ff`; 6/6 real-API smoke green |
| done | Wet-test the candidate-before-claim pipeline end-to-end | 2026-05-26 — 1 synthetic message → 2 promoted claims, 0 errors, 8.3s. Real Vertex Gemini Flash via direct adapter. commit `51a33ff` |
| done | **R11.0 — Refactor `contradiction-watcher` through `OracleAIClient`**; OpenRouter completely removed from codebase | commit `b01e514` |
| done | **R11.1 — Pure decision functions** in `packages/oracle-engines/src/interjection.ts` (`decideLullInterjection` + `decideContradictionInterjection`) + 33-assertion smoke gate `verify:r11.1` | commit `c9d0efe` |
| done | **R11.2 — Lull-interjection Trigger.dev task** | commit `bf7cad7`. `apps/workers/src/trigger/lull-interjection.ts` — cron `* * * * *`, drafts via Anthropic Haiku 4.5 interview route, posts live message, records intervention. |
| done | **R11.3 — Live contradiction interjection** | commit `bf7cad7`. `contradiction-watcher` extended: resolves channel from claim_evidence → messages, calls `decideContradictionInterjection`, drafts + posts live on 'live' / queues gap on 'queue'. Migration `50_enable_live_contradiction_interjections.sql` flips the setting ON. |
| done | **R11.4 — Final docs cleanup** | (this commit). HANDOFF / DECISIONS (D10 + D11) / docs/architecture / retrofit packet updated. |
| done | **Trigger.dev redeploy** | `20260527.1` deployed (11 tasks — adds `taxonomy-reclassification`). `OPENROUTER_API_KEY` was already absent from the project env. |
| done | **Model catalog discovery (2026-05-27 session)** | `packages/ai/src/model-capabilities/` sources from OpenRouter; persisted to `model_capabilities` table (migration 54). Admin "Refresh from OpenRouter" button on `/admin/settings/model-pool`. Per-stage pools (`model_pool_interview` / `_extraction` / `_synthesis`). Fourth `/admin/settings` card: "General-purpose model". |
| done | Model catalog source refactored: model list from 3 direct provider APIs (Anthropic, OpenAI, Google Gemini); OpenRouter demoted to enrichment-only (pricing + caps). ModelCapabilitySource type updated. | commit 1d91cd5 |
| done | **Vercel env vars set (2026-05-27 session)** | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` all uploaded to all three Vercel targets. |
| done | **Build-version badge** | `apps/web/next.config.ts` bakes `NEXT_PUBLIC_GIT_SHA` / `NEXT_PUBLIC_GIT_TIMESTAMP` at build. `apps/web/app/admin/layout.tsx` shows them in the top-right of every admin page. |
| done | **Lazy `OracleAIClient` in `/api/chat`** | Module-level `new OracleAIClient({adapters:{new AnthropicAdapter(),...}})` was throwing during Next.js "Collect page data" build phase. Replaced with `getOracleClient()` lazy helper. Build had been ERROR for ~12h. |
| done | **Vertex production credentials** | `GOOGLE_APPLICATION_CREDENTIALS_JSON` for `oracle-trigger-worker@vertex-ai-497120.iam.gserviceaccount.com` was already set in the Trigger.dev project env. |
| done | **`precomputedVector` support in `RetrievalPlan`** | Added `precomputedVector?: number[]` to `RetrievalPlan` + all builder opts. `searchWithRetrievalPlan` skips `embedText` when provided. Contradiction-watcher passes the stored claim embedding, eliminating the double-embed. TODO comment in `contradiction-watcher.ts` removed. |
| done | **DOMAIN_KEYWORDS tuning (round 1)** | Added ~50 keywords across all 10 domains (IT tooling, logistics trade terms, product materials, finance payment, customer compliance). Extend further via production `global_fallback` audit. |
| done | **Typing presence in lull-interjection** | `typing_indicators` table (schema + `52_typing_indicators.sql`). `channel-chat.tsx` upserts on typing-start, deletes on stop. Lull worker queries live instead of hardcoding `false`. |
| open | **Round-2 interjection improvement (b)** | Add `gaps.embedding` column + score topical relevance of the chosen gap against mean embedding of recent channel messages instead of participant-filter. See DECISIONS.md D11. |
| open | **Entity proposal write-time fuzzy-dedup** | As claim volume grows, the same unknown entity (e.g. "Microsoft", "MSFT", "Microsoft Corp") may accumulate many `entity_proposals` rows before an admin reviews. At insert time, run a pg_trgm similarity check against open proposals of the same `proposed_entity_type` and collapse into an existing row (increment a counter or append the source candidate ID) if similarity ≥ threshold. Cleaner than a cron and prevents queue noise. Requires pg_trgm extension (already available on Supabase Postgres) + a `proposal_count` or `source_candidate_ids` jsonb column on `entity_proposals`. Defer until `entity_proposals` queue shows actual noise in production. |
| done | Retrofit reference docs sweep | This commit. `docs/oracle/02-provider-native-ai-architecture.md` and `docs/oracle/05-ai-retrofit-phase-packet.md` updated to reflect the completed retrofit. Status tables show what shipped vs what's deferred to round 2. |
| done | Wet-test walkthrough conversion | This commit. `docs/wet-test-walkthrough.md` rewritten as a "how to repeat the wet-test against a new transcript" guide (3 steps + failure shapes + cleanup). |
| done | CI: `.github/workflows/pr-check.yml` runs `pnpm --filter @oracle/web build` on PRs + pushes to `main`. Catches production-only typecheck errors (the 2026-05-20 class of failure). Uses placeholder env vars; App Router dynamic-rendering means real secrets aren't needed at build. | 2026-05-21 |
| open | CI: add migration job (`pnpm db:migrate`) gated on manual approval | — |
| open | Vector indexes (`packages/db/migrations/sql/99_vector_indexes.sql`) — apply once enough embedding data exists to justify HNSW | run the SQL when ready |
| open | Rotate the Vercel token that was pasted into the build transcript during overnight setup | https://vercel.com/account/tokens |
| open | Rotate `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and the unused OpenRouter key before going live (all three were exposed in chat transcripts during the R-providers and R11.0 sessions for dev convenience) | https://console.anthropic.com/settings/keys, https://platform.openai.com/api-keys, https://openrouter.ai/keys |
| done | Delete `OpenRouter`-tagged tasks from the Trigger.dev project's env vars on the next workers deploy (`OPENROUTER_API_KEY` is no longer used) | Confirmed absent from Trigger.dev project env on 2026-05-26. |
| open | Add an admin UI to link / unlink employee identities (e.g. "this gmail is also Albert") | future Phase 5 task |
| open | Wet-test the Microsoft 365 + Google login flows on a fresh employee (one with no prior session state) before broader rollout | Albert |
| done | Phase 1 — Foundation (schema, migrations, RLS, auth callback, admin seed) | **wet-tested** |
| done | Phase 2 — Realtime chat UI + document upload + admin skeleton | code complete, partial wet-test |
| done | Phase 3 — Oracle chat route + tools + system prompt | code complete |
| done | Phase 4–6 stub scaffolds | committed |
| done | Multi-identity refactor (DECISIONS.md D2) | wet-tested with Google + M365 on the same Albert |
| done | Google OAuth provider live | `u2giants@gmail.com` |
| done | Microsoft 365 SSO live (popcre tenant only) | `albert@popcre.com` |
| done | Brevo SMTP integrated for magic-link delivery | configured in Supabase Auth |
| done | Logout flow | POST `/auth/signout` + form button in admin and channels layouts |
| done | Next.js bumped 15 → 16 (resolves CVE-2025-66478) | `apps/web/package.json` |
| done | `next.config.ts` updated for Next 16 (`serverExternalPackages`, eslint block removed) | |
| done | Fixed `OracleDb` vs `Db` typecheck failure in retrieval helpers (production build was failing every deploy) | `packages/db/src/client.ts` (exported the type) + `packages/ai/src/retrieval.ts` |
| done | Fixed implicit-any cookie adapter params in `packages/auth/src/server.ts` | typed against `@supabase/ssr`'s `CookieMethodsServer` |
| done | Added `vercel.json` so Vercel finds `apps/web/.next` in this monorepo | repo root |

**Keep this section current.** A stale pending-work list is worse than no list.
