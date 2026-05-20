# AGENTS.md — The Oracle Developer Guide

This is the single source of truth for any developer, AI agent, or AI session working on this project. Read this top-to-bottom before touching anything. The full product specification is in `oracle_master_spec.md`; this file is the operational guide.

---

## 1. What this project is

**The Oracle** is an AI-powered Business Intelligence system — an Enterprise Knowledge Graph — for **POP Creations / Spruce Line**, a high-volume home decor company based in Brooklyn (~1,500 SKUs, ~18 employees across US/China/Brazil/Colombia, retail customers including Burlington, TJX, Ross, Hobby Lobby, Walmart).

The company's real operational reality lives in people's heads ("dark matter"): informal rules, undocumented workarounds, contradictory understandings of when work is "ready" for the next department. The Oracle observes conversations, ingests documents, interviews employees, extracts evidence-backed *claims* about how the business actually works, detects contradictions and gaps, and synthesizes a versioned company "Brain" that the lead architect can query.

**Business outcome:** the lead architect (Albert) can ask "why does the company believe X?" and get an answer backed by traceable evidence — specific messages, specific document chunks, specific employees on specific dates.

**The Oracle is NOT** a project manager, task tracker, to-do list, ticket system, or due-date manager. If any code in this repo looks like that, it is a bug. See `oracle_master_spec.md` Part 1.3.

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
│   ├── web/                       # Next.js 15 App Router — the only user-facing app
│   │   ├── app/
│   │   │   ├── page.tsx                       # /  — login landing
│   │   │   ├── auth/callback/route.ts         # Supabase Auth → employees linker
│   │   │   ├── denied/page.tsx                # off-allowlist landing
│   │   │   ├── channels/                      # employee-facing chat (Phase 2)
│   │   │   ├── admin/                         # admin dashboard (Phase 2/5)
│   │   │   ├── api/chat/route.ts              # Oracle chat endpoint (Phase 3)
│   │   │   └── _components/                   # local UI components
│   │   ├── components/ui/                     # shadcn/ui primitives
│   │   ├── lib/                               # web-only helpers (supabase client, auth-guard)
│   │   ├── next.config.ts
│   │   └── tailwind.config.ts
│   └── workers/                   # Trigger.dev v3 — background workers (Phase 4 stubs)
│       ├── trigger.config.ts
│       └── src/trigger/{claim-extraction,document-ingestion,contradiction-watcher,brain-synthesis}.ts
├── packages/
│   ├── shared/                    # framework-agnostic TS types & constants (KNOWLEDGE_DOMAINS, etc.)
│   ├── db/                        # Drizzle ORM — schema, migrations, seed, client
│   │   ├── src/{schema.ts,client.ts,migrate.ts,seed.ts,index.ts}
│   │   ├── migrations/            # Drizzle-generated SQL (auto)
│   │   ├── migrations/sql/        # hand-written SQL — constraints, RLS, views, vector indexes
│   │   └── drizzle.config.ts
│   ├── auth/                      # Supabase auth helpers + first-login linking
│   │   └── src/{link.ts,server.ts,client.ts,index.ts}
│   ├── ai/                        # AI SDK helpers, prompts, retrieval, embeddings
│   │   └── src/{prompts/oracle-system.ts,openrouter.ts,embeddings.ts,retrieval.ts,index.ts}
│   └── oracle-engines/            # interjection / curiosity / synthesis logic (Phase 6 stub)
│       └── src/{interjection.ts,index.ts}
├── docs/                          # detailed docs — architecture, development, configuration, deployment
├── AGENTS.md                      # this file
├── CLAUDE.md                      # Claude Code-specific notes (points back here)
├── DECISIONS.md                   # every assumption, citation, alternative ruled out
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

**Generated code:** `packages/db/migrations/*.sql` (Drizzle-generated; do not hand-edit — write a new SQL file under `migrations/sql/` instead).

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
- Do not edit auto-generated Drizzle migration SQL. Add a new file under `packages/db/migrations/sql/` with a numeric prefix.
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
4. If it uses an LLM, go through `@oracle/ai` (`openrouter`/`retrieval`) — never call providers directly from a route file.
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
3. If the change needs constraints, RLS, helper functions, or views: add a new `packages/db/migrations/sql/NN_<topic>.sql` file (next free numeric prefix).
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

---

## 7. Task-to-file navigation map

| Task | Files to touch | Files NOT to touch |
|---|---|---|
| Add a new claim type or knowledge domain | `packages/shared/src/domains.ts`, `packages/db/src/schema.ts`, migration SQL | existing applied migration files |
| Tweak the Oracle's chat behavior | `apps/web/app/api/chat/route.ts`, `packages/ai/src/prompts/oracle-system.ts`, `packages/ai/src/retrieval.ts` | `apps/web/components/ui/**`, shadcn primitives |
| Change the login flow | `apps/web/app/page.tsx` (form), `apps/web/app/auth/callback/route.ts`, `packages/auth/src/link.ts` | `apps/web/app/admin/**`, framework files |
| Add a new admin dashboard tab | `apps/web/app/admin/<tab>/page.tsx`, `apps/web/app/admin/layout.tsx` (nav link) | RLS policies (admin uses service-role server-side) |
| Add an RLS policy | `packages/db/migrations/sql/NN_rls_*.sql` (new file) | `packages/db/migrations/sql/21_rls_policies.sql` (already applied) |
| Add a new admin view | `packages/db/migrations/sql/NN_admin_views.sql` (new file) | `packages/db/migrations/sql/30_admin_views.sql` (already applied) |
| Add a new worker job | `apps/workers/src/trigger/<job>.ts`, `apps/workers/trigger.config.ts` | `apps/web/**` |
| Change embedding model or dimension | `packages/ai/src/embeddings.ts`, schema `vector(N)` column, migration SQL | _(see Idiosyncratic Decisions — vector dim is locked)_ |
| Add a new env var | `.env.example`, `turbo.json` `globalEnv` array, `docs/configuration.md` | `.env.local` is not in git; never commit it |
| Tweak chat UI | `apps/web/app/channels/[channelId]/_components/channel-chat.tsx` | shadcn primitives, `next.config.ts` |

---

## 8. Data model / custom objects

The full schema lives in `packages/db/src/schema.ts` and is faithful to `oracle_master_spec.md` Part 6. The tables below are the load-bearing ones — every other table joins through these.

| Entity | Identifier | Where defined | Notes |
|---|---|---|---|
| Employee | `employees.id` (uuid) | DB | Authorization roster. `auth_user_id` links to `auth.users.id` from Supabase Auth. Identity by `auth_user_id`, not email, after first login. |
| Auth user | `auth.users.id` (uuid) | Supabase Auth | Managed by Supabase. Owned by the identity provider. |
| Channel | `channels.id` (uuid) | DB | Group or 1:1 chat. Membership via `channel_participants`. |
| Message | `messages.id` (uuid) | DB | Includes `client_message_id` for client-side dedup, `extraction_status` for worker pipeline. |
| Document | `documents.id` (uuid) | DB | Lives in Supabase Storage bucket `company_documents`. Storage path is `storageBucket`/`storagePath` (unique). |
| Document chunk | `document_chunks.id` (uuid) | DB | Always linked to a document. Carries page/sheet/row/bbox metadata. Has `embedding vector(1536)`. |
| Claim | `claims.id` (uuid) | DB | A universal operational assertion. **Intentionally has no direct `employee_id`** — query through `claim_evidence.asserted_by_employee_id`. Has `embedding vector(1536)`. |
| Claim evidence | `claim_evidence.id` (uuid) | DB | The traceability backbone. Every claim must have ≥1 evidence row. `source_type` ∈ {`message`, `document_chunk`, `external_system`, `manual_admin`} and the matching FK column is enforced by `claim_evidence_source_check`. |
| Brain section | `brain_sections.id` (string slug, e.g. `creative_to_technical_handoff`) | DB | Soft-referenced `current_version_id` is filled via two-step transactional insert (see spec 6.7). |
| Gap, Contradiction, Oracle intervention | uuid | DB | All link back to claims/messages/employees for audit. |
| Model run / Job run | uuid | DB | Observability. Every LLM call → `model_runs`. Every Trigger.dev task → `job_runs`. |

**External system identifiers** (do not change casually; recorded so a future migration doesn't break references):

| Item | Identifier | Source | Notes |
|---|---|---|---|
| GitHub repo | `u2giants/theoracle` | GitHub | **Public**. Never commit secrets. |
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Vercel | The web app deploys here. |
| Supabase project | _(see Vercel env)_ | Supabase | Database, Auth, Storage, Realtime. |
| Trigger.dev project | _(see Vercel env)_ | Trigger.dev | Background workers. |
| Supabase Storage bucket | `company_documents` | Supabase | Private. Holds uploaded employee documents. |
| OpenRouter model id (default interview) | `anthropic/claude-sonnet-4.6` | `settings.default_interview_model` row | Configurable at runtime via the settings table. |
| OpenRouter model id (default extraction) | `google/gemini-flash` | `settings.default_extraction_model` row | Configurable. |
| OpenRouter model id (default synthesis) | `anthropic/claude-sonnet-4.6` | `settings.default_synthesis_model` row | Configurable. |
| Embedding model | `text-embedding-3-small` (OpenAI, 1536-dim) | hardcoded in `packages/ai/src/embeddings.ts` | Vector column is `vector(1536)` — see Idiosyncratic Decisions. |

---

## 9. Container / runtime inventory

This project does not use containers. Everything is fully managed cloud per spec Part 2.5 — no Dockerfiles, no VPS, no reverse proxies.

| Runtime | Purpose | Managed by | Identifier | Notes |
|---|---|---|---|---|
| Vercel Functions | `apps/web` — Next.js App Router + API routes | Vercel | project `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | Fluid Compute, Node.js 24 runtime by default |
| Trigger.dev v3 | `apps/workers` — claim extraction, ingestion, contradiction watcher, synthesis | Trigger.dev Cloud | project ID in `TRIGGER_SECRET_KEY` | Background workers. May bypass RLS (service-role). |
| Supabase Postgres | Source of truth — all durable data | Supabase Cloud | URL in `NEXT_PUBLIC_SUPABASE_URL` | pgvector for embeddings, RLS enforced. |
| Supabase Storage | Uploaded documents | Supabase Cloud | bucket `company_documents` | Private bucket. |
| Supabase Auth | Identity | Supabase Cloud | — | Currently magic-link only (dev stub). OAuth providers (Microsoft / Google / Authentik) are a deferred TODO. |
| Supabase Realtime | Chat / presence | Supabase Cloud | — | `postgres_changes` for messages; presence channel for typing. |
| OpenRouter | LLM provider | OpenRouter | account on file | Used via Vercel AI SDK. |
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
packages/db/migrations/*.sql   # generated Drizzle output; the source of truth is schema.ts
```

Files you SHOULD read when getting oriented:

1. `AGENTS.md` (this file)
2. `oracle_master_spec.md` (product spec)
3. `DECISIONS.md` (assumptions log)
4. `packages/db/src/schema.ts` (data model)
5. `packages/db/migrations/sql/*.sql` (RLS, constraints, views — hand-written, all signal)
6. `packages/ai/src/prompts/oracle-system.ts` (Oracle's voice)

---

## 11. Idiosyncratic decisions

The most important section. **Do not undo these without reading the cited spec section and updating `DECISIONS.md`.**

### Claims have no `employee_id` column

**Looks like:** an obvious schema bug — every "who said it" lookup requires a join.

**Actually:** spec Part 6.6 explicitly forbids it. A claim is a universal operational assertion that can be supported by multiple employees, documents, or external systems over time.

**Why:** if a claim is asserted by Employee A in a Slack message, then re-confirmed by Employee B in an interview, then contradicted in a document chunk uploaded by Employee C, attaching the claim to a single `employee_id` would erase that history. The `claim_evidence` table carries `asserted_by_employee_id`, `uploaded_by_employee_id`, and `created_by_employee_id` per evidence row.

**Do not change because:** breaks traceability. The whole product collapses if "why does the Oracle believe this" can't be answered with multiple evidence rows.

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

### Magic-link auth (not Microsoft / Google / Authentik) — dev stub

**Looks like:** "OAuth was never wired up — let me add it."

**Actually:** intentional dev stub per the overnight build user decision. Spec Part 4.1 requires Microsoft / Google / Authentik. We're using Supabase email magic-link as a stub provider while the OAuth provider configuration is deferred. The `auth_provider` enum has a `magic_link_dev` value for this. The **employee allowlist + `auth_user_id` linking is the real spec-compliant flow** — only the upstream provider is stubbed.

**Why:** see `DECISIONS.md` D1.auth-provider-stub. Avoids blocking on tenant-restriction policy decisions for Microsoft Entra and Authentik issuer config.

**Do not change because:** the linker code in `packages/auth/src/link.ts` is correct; the change needed is in Supabase Auth provider config, not in our code. Removing magic-link before OAuth is wired will break local dev.

### `claim_evidence_source_check` CHECK constraint over JSON schemas

**Looks like:** belt-and-suspenders — Zod could enforce this.

**Actually:** the constraint runs at the DB level so background workers, admin SQL, manual inserts, and future non-TypeScript integrations all get the same guarantee.

**Why:** spec Part 6.8 mandates it. Different `source_type` values require different FK columns to be non-null. Application-level validation is bypassed by workers, by SQL migrations, and by any future Coldlion sync.

**Do not change because:** removes a critical invariant; allows orphaned claims with no evidence pointer.

### Windows install gotcha — no `.npmrc` workaround checked in (deliberately)

**Looks like:** "Windows install is fragile, why isn't there an `.npmrc` with `node-linker=hoisted` committed?"

**Actually:** we tried that workaround. It doesn't fix the real Windows issues — workspace packages get symlinked regardless of `node-linker`. The real fixes are environmental: Developer Mode on, sign out/in after enabling, install once from an Administrator PowerShell, add Defender exclusions for the repo and pnpm store. See `docs/development.md` → "Windows-specific setup".

**Why:** `node-linker=hoisted` makes pnpm flatten external deps but does nothing for the `@oracle/*` workspace packages, which are what was actually failing. Keeping `.npmrc` out of the repo avoids future devs misattributing fixes to it.

**Do not change because:** if a future install issue tempts you to add `.npmrc`, first verify Developer Mode is actually active (`Get-ItemProperty HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\AppModelUnlock`), verify Defender exclusions are in place, and try an Admin-shell install. The `.npmrc` workaround is a last resort and should land in DECISIONS.md if added.

### Test employee in seed (`test-employee@oracle.local`)

**Looks like:** leaked test data.

**Actually:** required to test the Phase 2 RLS gate (channel isolation needs two employees).

**Why:** the spec's acceptance gate for Phase 2 requires proving employee A can't read a channel where they aren't a participant — impossible with only the admin row.

**Do not change because:** removing it breaks the RLS verification. **DO delete it before production rollout** (tracked in Pending Work below).

### Drizzle migrations applied via a custom `migrate.ts` rather than `drizzle-kit push`

**Looks like:** reinventing the wheel.

**Actually:** the runner in `packages/db/src/migrate.ts` applies Drizzle-generated migrations **and** every file in `packages/db/migrations/sql/` in order (extensions → constraints → RLS helpers → policies → views → vector indexes).

**Why:** Drizzle doesn't model raw SQL migrations cleanly. We need extensions, RLS, CHECK constraints, and views applied in a specific order, idempotently.

**Do not change because:** `drizzle-kit push` will skip the `migrations/sql/` files entirely and leave the database without RLS or constraints.

---

## 12. Credentials and environment

Never commit real values. `.env.local` is git-ignored. Reference values are in the Vercel project's Environment Variables tab (Production and Preview); local dev pulls them in via `npx vercel env pull` or manual paste.

| Variable | Purpose | Stored where | Required in dev | Required in prod |
|---|---|---|---|---|
| `DATABASE_URL` | Supabase Postgres connection (transaction pooler, port 6543) | Vercel env, `.env.local` | yes | yes |
| `DIRECT_URL` | Supabase Postgres direct connection (port 5432) — used by Drizzle migrations | Vercel env, `.env.local` | yes | yes |
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project URL | Vercel env, `.env.local` | yes | yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anon key for browser client | Vercel env, `.env.local` | yes | yes |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key (newer alias of anon) | Vercel env, `.env.local` | yes | yes |
| `SUPABASE_SERVICE_ROLE_KEY` | Bypasses RLS — server-side only | Vercel env, `.env.local` | yes | yes |
| `OPENROUTER_API_KEY` | LLM provider for chat + extraction + synthesis | Vercel env, `.env.local` | yes | yes |
| `OPENAI_API_KEY` | Embeddings (`text-embedding-3-small`) | Vercel env, `.env.local` | optional (falls back to zero vector) | yes |
| `TRIGGER_SECRET_KEY` | Trigger.dev server-side key | Vercel env (web), Trigger.dev (workers), `.env.local` | yes | yes |

Sensitive env vars in Vercel **cannot** be set on the Development environment — set them on Production+Preview and either copy into `.env.local` manually, or convert them to "Encrypted" type so `vercel env pull --environment=development` works.

---

## 13. Deployment

The deploy story is fully managed (no Docker, no VPS, per spec Part 2.5):

- **`apps/web` → Vercel.**
  - Vercel project ID: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`.
  - Auto-deploys on push to `main` (production) and on every PR (preview).
  - Build command: `pnpm install && pnpm --filter @oracle/web build`.
  - Output: Next.js 15 App Router on Fluid Compute (Node 24 runtime).
  - Runtime env vars: managed in Vercel → Settings → Environment Variables.
  - **Rollback:** Vercel dashboard → Deployments → promote the previous production deployment. No CLI/runbook step beyond that.

- **`apps/workers` → Trigger.dev Cloud.**
  - Deploy from CI or manually: `pnpm --filter @oracle/workers deploy`.
  - Runtime env vars: managed in Trigger.dev project dashboard.
  - **Rollback:** redeploy from a prior commit, or disable the task in Trigger.dev's UI.

- **Database migrations** are run manually before deploying changes that need them: `pnpm db:migrate`. The runner is idempotent. There is currently no CI-driven migration step — adding one is a Pending Work item.

- **GitHub Actions:** none yet. Once added they'll live under `.github/workflows/`.

There is no SSH path. There is no Coolify, no VPS, no Docker image. Anything that says otherwise is wrong.

---

## 14. Critical incident log

| Date | Incident | What we learned |
|---|---|---|
| _(none yet)_ | — | Greenfield. |

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
| open | Set Vercel env var values for Development environment (or convert Sensitive → Encrypted and re-pull) | Albert |
| open | Wire real OAuth providers (Microsoft Entra / Google / Authentik) — remove `magic_link_dev` from `auth_provider` enum once done | Albert + a future build session |
| open | Create the `company_documents` Storage bucket in Supabase if it isn't there yet | Albert |
| open | Bump Next.js 15.1.4 → ≥15.1.7 to fix CVE-2025-66478 | `pnpm --filter @oracle/web up next@latest` |
| open | Bump `tsx` to v4+ to drop deprecated `@esbuild-kit/*` subdeps | `pnpm -r up tsx@latest` |
| open | Delete `test-employee@oracle.local` from `employees` seed and DB before production rollout | trivial SQL or admin UI |
| open | Implement Phase 4 — Trigger.dev workers (claim extraction, document ingestion, contradiction watcher, brain synthesis) | scaffolds exist in `apps/workers/src/trigger/` |
| open | Implement Phase 5 — Admin review/brain dashboard pages | placeholders exist under `apps/web/app/admin/*` |
| open | Implement Phase 6 — Interjection engine (lull detection, cooldown, contradiction live-interjection) | scaffold at `packages/oracle-engines/src/interjection.ts` |
| open | CI: add `pnpm typecheck && pnpm build` on PRs (GitHub Actions) | — |
| open | Vector indexes (`packages/db/migrations/sql/99_vector_indexes.sql`) — apply once there's enough embedding data to justify HNSW | run the SQL when ready |
| open | Rotate the Vercel token that was pasted into the chat transcript during overnight setup | https://vercel.com/account/tokens |
| done | Phase 1 — Foundation (schema, migrations, RLS, auth callback, admin seed) | commit `d832f5f` |
| done | Phase 2 — Realtime chat UI + document upload + admin skeleton | commit `9efd3e1` |
| done | Phase 3 — Oracle chat route + tools + system prompt | commit `eec3d58` |
| done | Phase 4–6 stub scaffolds | commit `4940327` |

**Keep this section current.** A stale pending-work list is worse than no list.
