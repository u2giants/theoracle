# AGENTS.md — The Oracle Developer Guide

Read this first. It is the canonical operating guide for developers and AI coding sessions working in `D:\repos\oracle`.

## 1. Project summary

The Oracle is an evidence-backed enterprise knowledge graph for POP Creations / Spruce Line. Employees interact with it through chat and document uploads; workers extract operational claims with quote-level evidence; deterministic validators gate promotion into approved claims; synthesis workers maintain traceable Brain sections; admin screens review runs, caches, claims, gaps, contradictions, and taxonomy proposals. The outcome that matters is explainable business knowledge: every important answer or synthesis artifact must be traceable back to messages, document chunks, or approved claims.

## 2. Multi-model AI note

There is no universal ignore-file standard across AI coding tools.

`.claudeignore` works for Claude Code.

When using any other AI tool, paste this file as your first message and follow the instructions in the "What to ignore" section.

## 3. Repository structure

This is a `pnpm` + `turbo` TypeScript monorepo.

Code we own:

- `apps/web/` — Next.js 16 App Router app, API routes, admin UI, employee chat UI
- `apps/workers/` — Trigger.dev tasks and worker config
- `packages/ai/` — `OracleAIClient`, retrieval, prompts, provider adapters, model catalog
- `packages/auth/` — Supabase auth helpers and employee identity linker
- `packages/db/` — Drizzle schema, client, migrate/seed scripts
- `packages/oracle-engines/` — deterministic extraction and synthesis logic
- `packages/shared/` — shared types/constants
- `docs/` — project documentation
- root markdown files — `README.md`, `AGENTS.md`, `CLAUDE.md`, `DECISIONS.md`

Generated code:

- `packages/db/migrations/0*.sql` — Drizzle-generated SQL
- `packages/db/migrations/meta/` — Drizzle metadata

Third-party / framework code:

- `node_modules/`
- `apps/web/components/ui/` — shadcn-generated primitives; treat as framework layer

Build artifacts and caches:

- `apps/web/.next/`
- `dist/`
- `.turbo/`
- `.vercel/`
- `.cache/`
- `coverage/`
- `packages/ai/evals/runs/`

Docs:

- `docs/architecture.md`
- `docs/development.md`
- `docs/configuration.md`
- `docs/deployment.md`
- `docs/oracle/` — deeper AI-retrofit reference material

Scripts:

- `scripts/verify-catalog.ts` — provider/model catalog inspection
- `scripts/refresh-catalog.ts` — model catalog refresh against the real DB
- `packages/db/src/{migrate,seed,verify-identities,inspect-auth-users}.ts`

Migrations:

- `packages/db/src/schema.ts` — source of truth
- `packages/db/migrations/0*.sql` — generated DDL
- `packages/db/migrations/sql/*.sql` — hand-written constraints, views, data migrations, seeds

Deployment files:

- `vercel.json` — repo-level Vercel build contract
- `.github/workflows/pr-check.yml` — current CI gate
- `apps/workers/trigger.config.ts` — Trigger.dev runtime config

## 4. Prime Directive: custom-code boundary

Our custom code lives here:

- `apps/web/app/**`
- `apps/web/lib/**`
- `apps/workers/src/**`
- `packages/**`
- `docs/**`
- `.github/workflows/**`
- root project docs/config files such as `README.md`, `AGENTS.md`, `CLAUDE.md`, `.env.example`, `vercel.json`, `turbo.json`

Everything else requires justification before touching.

Specific boundaries:

- Do not edit `node_modules/`.
- Do not hand-edit generated Drizzle files under `packages/db/migrations/0*.sql`.
- Do not scatter project logic into `apps/web/components/ui/*`; extend behavior from app-owned files instead.
- Do not change `oracle_master_spec.md` casually; if code and spec conflict, record the conflict in `DECISIONS.md`.

## 5. Core modification inventory

| File | Change made | Why it was necessary | Risk during upgrades |
|---|---|---|---|
| _(none)_ | — | No framework/vendor files are intentionally patched in this repo. | — |

## 6. Task-to-file navigation

| Task | Files to touch | Files not to touch |
|---|---|---|
| Change employee chat behavior | `apps/web/app/api/chat/route.ts`, `packages/ai/src/prompts/oracle-system.ts`, `packages/ai/src/retrieval*.ts`, provider adapters as needed | `node_modules/`, `apps/web/components/ui/**` |
| Add or change an AI provider behavior | `packages/ai/src/providers/*.ts`, `packages/ai/src/client/standard-adapters.ts`, `packages/ai/src/routes/{types,resolve}.ts`, relevant docs | route handlers or workers calling SDKs directly |
| Add a database field or table | `packages/db/src/schema.ts`, new file under `packages/db/migrations/sql/` if hand-written SQL is needed, generated Drizzle migration if schema changed | previously applied migration files |
| Add a worker | `apps/workers/src/trigger/*.ts`, `apps/workers/trigger.config.ts`, docs if operational behavior changes | `apps/web/**` unless there is a matching UI/API hook |
| Add an admin page | `apps/web/app/admin/**`, possibly `packages/db/migrations/sql/*.sql` for a new admin view | RLS helpers unless policy changes are truly required |
| Change auth/linking behavior | `packages/auth/src/**`, `apps/web/app/auth/**`, `apps/web/app/_components/login-form.tsx` | direct edits to Supabase-managed auth tables |
| Add or change env/config | `.env.example`, `turbo.json`, `docs/configuration.md`, consuming code | `.env.local` in git |
| Add or change model catalog filtering | `packages/ai/src/model-capabilities/sources/<provider>.ts` (per-provider source/blocklist), `packages/ai/src/model-capabilities/index.ts` (write-time post-enrichment filters), **`apps/web/app/api/admin/model-catalog/route.ts` `passesQualityFilter` (mirror filter at read time)**, `scripts/refresh-catalog.ts` to verify, `docs/architecture.md`, `DECISIONS.md` | provider inference adapters, route catalog |
| Reorder or regroup admin nav | `apps/web/app/admin/_components/admin-nav.tsx` (GROUPS array + isActive helper). Layout wrapper stays server-rendered for auth. | `apps/web/app/admin/layout.tsx` other than the AdminNav import — auth still runs there |
| Change deployment behavior | `vercel.json`, `.github/workflows/pr-check.yml`, `apps/workers/trigger.config.ts`, `docs/deployment.md` | ad hoc dashboard-only assumptions without documenting them |

## 7. Data model and external identifiers

| Entity/System | Identifier | Where defined | Notes |
|---|---|---|---|
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `AGENTS.md`, deployment/config docs | Web app target |
| Trigger.dev project | `proj_wgpzsvhmsopqhvwqaycn` | `apps/workers/trigger.config.ts` | Worker target; env can override |
| Supabase Storage bucket | `company_documents` | schema + worker code + docs | Private document bucket |
| Interview default route | `anthropic_claude_haiku_4_5_interview_primary` | `packages/ai/src/routes/catalog.ts`, settings row | Employee chat default |
| Extraction default route | `vertex_gemini_2_5_flash_extraction_primary` | same | Extraction default |
| Synthesis default route | `anthropic_claude_3_5_sonnet_synthesis_primary` | same | Synthesis default |
| Embedding model | `text-embedding-3-small` | `packages/ai/src/embeddings.ts` | Locked to `vector(1536)` |
| Employee identity table | `employee_identities` | `packages/db/src/schema.ts` | Canonical auth-link table |
| Prompt/context audit table | `oracle_context_packs` | `packages/db/src/schema.ts` | One row per AI call plan |
| Usage detail table | `model_run_usage_details` | `packages/db/src/schema.ts` | Provider token/cache details |
| Provider cache table | `provider_cached_content` | `packages/db/src/schema.ts` | Explicit Vertex cache lifecycle + provider metadata |
| Provider response session table | `provider_response_sessions` | `packages/db/src/schema.ts` | Qwen Responses `previous_response_id` persistence |
| Model catalog table | `model_capabilities` | schema + model-capability refresh code | Populated from direct providers + OpenRouter enrichment |
| Provider Batch jobs table | `provider_batch_jobs` | `packages/db/src/schema.ts`, migration `60_batch_jobs.sql` | One row per submitted provider Batch API job (D14). `extraction_batches.provider_batch_job_id` links per-input rows to their batch. `model_runs.dispatch_mode` ∈ `'sync' \| 'batch' \| NULL`. |

Do not casually rename or regenerate these identifiers. They are wired across code, DB, and deployment surfaces.

## 8. Container and service inventory

There are no Docker containers in this repo. Runtime services are fully managed.

| Container/service | Purpose | Managed by | App/project ID | Image/source |
|---|---|---|---|---|
| Vercel Functions | Next.js web app and API routes | Vercel | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `apps/web` build via `vercel.json` |
| Trigger.dev Cloud | Background workers | Trigger.dev | `proj_wgpzsvhmsopqhvwqaycn` | `apps/workers` |
| Supabase Postgres | Primary database | Supabase | configured by env | managed Postgres + pgvector |
| Supabase Auth | Login and session identity | Supabase | same project | managed Auth |
| Supabase Storage | Uploaded documents | Supabase | bucket `company_documents` | managed object storage |
| Supabase Realtime | Chat/message live updates | Supabase | same project | managed Realtime |
| Brevo SMTP | Magic-link email delivery through Supabase Auth | Brevo + Supabase | external account | SMTP relay |
| Anthropic API | Interview-model inference | Anthropic | external account | `@anthropic-ai/sdk` |
| Vertex AI | Extraction/synthesis inference and explicit context caches | Google Cloud | `vertex-ai-497120` via env/ADC | `@google/genai` + optional GCS bucket |
| OpenAI API | Fallback inference and embeddings | OpenAI | external account | `openai` SDK |
| DeepSeek API | Optional inference provider | DeepSeek | external account | `openai` SDK against `api.deepseek.com` |
| DashScope | Optional Qwen inference provider | Alibaba | external account | `openai` SDK against `dashscope-us.aliyuncs.com/compatible-mode/v1` |

## 9. What to ignore

Do not load these into AI context unless a task explicitly requires them:

- `node_modules/`
- `apps/web/.next/`
- `dist/`
- `.turbo/`
- `.vercel/`
- `.cache/`
- `coverage/`
- `.claude/`
- `.playwright-mcp/`
- `packages/ai/evals/runs/`
- `pnpm-lock.yaml` unless dependency resolution itself is the task
- `packages/db/migrations/0*.sql`
- `packages/db/migrations/meta/`
- `.env.local`

Read these first when orienting:

- `README.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/development.md`
- `docs/configuration.md`
- `docs/deployment.md`
- `packages/db/src/schema.ts`
- `packages/ai/src/providers/*.ts`

## 10. Intentional quirks and non-obvious decisions

### One employee can have many auth identities

Looks like:
`employees` still has deprecated auth columns, so `employee_identities` looks redundant.

Actually:
`employee_identities` is the real auth-link table. The deprecated columns remain only as transition leftovers.

Why:
One person may log in through Google and Microsoft 365 and still be the same employee.

Do not change because:
Collapsing back to one auth identity per employee breaks real user linkage and RLS helpers.

### All inference must go through `OracleAIClient`

Looks like:
It would be simpler for routes or workers to call provider SDKs directly.

Actually:
The provider adapters are the only supported inference boundary. They own prompt shaping, provider-native caching, reasoning translation, and usage normalization.

Why:
The project depends on provider-specific caching and structured-output behavior that generic wrappers and ad hoc calls hide.

Do not change because:
Direct SDK calls bypass context-pack logging, cache observability, route fallback, and consistent validation.

### OpenRouter is enrichment-only

Looks like:
`openrouter.ts` and OpenRouter-related code mean inference still runs through OpenRouter.

Actually:
OpenRouter is only used to enrich the admin-side model catalog with pricing/capability metadata.

Why:
Inference requires native provider features and exact usage fields; catalog enrichment does not.

Do not change because:
Reintroducing OpenRouter into the inference path would erase provider-native cache and usage behavior that the rest of the system expects.

### Explicit Vertex caches are tracked in Postgres

Looks like:
The adapter could rely only on in-memory cache handles.

Actually:
`provider_cached_content` is the cross-process source of truth for explicit Vertex cache lifecycle, and `provider_metadata_json` now also tracks cleanup metadata for temporary GCS-backed cache sources.

Why:
Workers and web requests run in different processes and time windows. Cache accounting and cleanup have to survive process boundaries.

Do not change because:
Process-local cache tracking leaks money and makes cache reuse/cleanup invisible.

### Qwen chat cache state is persisted separately from run usage

Looks like:
`provider_response_sessions` duplicates data already in `model_runs`.

Actually:
`model_runs` is audit history; `provider_response_sessions` stores the latest reusable `previous_response_id` keyed by logical session.

Why:
Responses API session cache needs a stable conversation handle across requests and processes.

Do not change because:
Without it, Qwen session cache resets every turn and the savings disappear.

### Batch API methods on the adapter contract are optional

Looks like:
`OracleProviderAdapter.submitBatch` and `retrieveBatch` are marked `?` (optional). Existing adapters (Anthropic, DeepSeek, Qwen) don't implement them. The interface looks half-finished.

Actually:
The methods are optional on purpose. DeepSeek has no public Batch API. Qwen's batch surface is non-OpenAI-compatible (DECISIONS.md D12 deferred the native DashScope SDK swap). OpenAI, Vertex, and Anthropic implement both methods today; future adapters opt in by implementing both.

Why:
Forcing every adapter to implement batch would either block adding new providers behind a 50%-discount feature, or paper over it with stub `submitBatch` methods that throw — both worse than the optional pattern. The runtime helper `supportsBatch(adapter)` is the feature-detection contract. See DECISIONS.md D14.

Do not change because:
Making `submitBatch` / `retrieveBatch` required on the interface would force the DeepSeek and Qwen adapters to throw at construction, which would break the per-provider `tryAdd()` boot in `buildStandardAdapters()` and silently disable both providers.

Anthropic batch specifics: each request is a `messages.batches.create` entry with `custom_id` + `params` (same shape as a sync `messages.create`); when `jsonSchema` is provided we attach the forced single-tool input_schema per-request (mirrors `generateObject`). Status maps `processing_status: ended` → `'completed'` and we stream `messages.batches.results(id)` to produce `BatchResultItem`s. Per-item `result.type` → success (`succeeded` — tool_use input or text), or failure (`errored` / `canceled` / `expired`). `providerMetadata` is `{}` — the batch ID alone is sufficient for retrieve.

### Two-phase batch worker — submit and drain are independent tasks

Looks like:
`claim-extraction.ts`, `claim-extraction-batch-submit.ts`, and `claim-extraction-batch-drain.ts` look redundant. The flag `extraction_dispatch_mode` toggles them, but all three are scheduled.

Actually:
Each task reads `settings.extraction_dispatch_mode` at the top and bails when it doesn't match its dispatch mode. So at any given time only ONE of (sync) or (submit + drain) is active. The drain task is always scheduled because it always needs to poll outstanding `provider_batch_jobs` rows even after the flag flips back to `'sync'` (any in-flight batches should still be drained, not orphaned).

Why:
The flag is read every cron tick — flipping it doesn't require a redeploy. The drain task running unconditionally ensures no orphaned batches when admin flips back to sync. Per-task short-circuit at the top is the cleanest gate.

Do not change because:
Removing the always-on drain task would orphan any in-flight Vertex/OpenAI batches if the flag flipped back to sync mid-stream. Removing the gate from the sync task would double-process in batch mode.

### Model catalog quality filter runs at BOTH write and read time

Looks like:
The same filter logic appears in `packages/ai/src/model-capabilities/index.ts` (`refreshModelCatalog`) AND `apps/web/app/api/admin/model-catalog/route.ts` (`passesQualityFilter`). Looks duplicated.

Actually:
Intentional defense in depth. The write-time filter prevents new junk from landing in the DB. The read-time filter handles the legacy case: rows written BEFORE the write-time filter shipped (or when OpenRouter enrichment was unavailable) sit in the DB with no pricing and no capability flags. Deleting them would break pool selections that still reference deprecated model IDs. Filtering at read time hides them from admins without losing the FK target.

Why:
The write-time-only filter let junk creep back into the admin UI whenever an old OpenRouter outage produced unenriched rows. The read-time filter is the catch-all.

Do not change because:
Removing the read-time filter resurrects the original "junky models reappear" bug. Removing the write-time filter floods the DB with no-data rows that build up over time. Keep both.

### Ineligible models are SELECTABLE (red checkbox), not disabled

Looks like:
Models that don't meet a stage's required capabilities still have an active checkbox in the model-pool grid, just colored red.

Actually:
Admin override is intentional. Sometimes a model is fine for a stage even when one of the canonical capability flags is missing (e.g. OpenRouter hasn't enriched the model yet, but the admin knows it supports tools). Disabling the checkbox would force admins to wait for enrichment or edit settings via SQL.

Why:
The stage-requirements predicates are a heuristic, not ground truth. Red styling + the missing-caps hover tooltip make the override state obvious; no silent risk of accidental selection.

Do not change because:
Disabling the checkbox blocks valid admin overrides and forces SQL editing.

### Stage `thinking` requirement is on Synthesis, not Extraction

Looks like:
The Extraction model card has no reasoning-effort row visible, while Synthesis does — even though extraction is the more "thinking-heavy" task by feel.

Actually:
`thinking` was moved from `STAGE_REQUIREMENTS.extraction` → `STAGE_REQUIREMENTS.synthesis` on 2026-05-28 (`apps/web/lib/stage-requirements.ts`). Extraction benefits more from speed + verbatim quote fidelity; synthesis benefits from extended reasoning when consolidating a large approved-claim corpus into a single Brain section.

Why:
Earlier requirement set forced extraction into reasoning models that produced slower, more elaborate JSON for no provable accuracy win. Moving `thinking` to synthesis matches actual cost/quality observations.

Do not change because:
Putting `thinking` back on extraction excludes Gemini Flash and the cheap GPT-4o-mini path from the extraction pool — both proven good for extraction in our wet-tests.

### OpenAI model catalog uses a blocklist, not an allowlist

Looks like:
A new GPT or o-series model is missing from the admin catalog even though it appears in the OpenAI API response.

Actually:
The source in `packages/ai/src/model-capabilities/sources/openai.ts` uses a blocklist of non-chat categories. A model whose name hits a blocked prefix or substring (`-tts`, `-transcribe`, `-search-api`, etc.) is excluded. Otherwise it passes through automatically.

Why:
An allowlist required a code change for every new OpenAI model generation. GPT-5.x was invisible until `gpt-5` was manually added to the prefix list. The blocklist lets new chat models appear without a code change; only genuinely non-chat categories are excluded. See `DECISIONS.md` D13.

Do not change because:
Reverting to an allowlist means future GPT-6/o-series models will be silently missing from the catalog until someone notices and edits the list. Post-enrichment quality filters (no-data models, ≥$15.01/1M input) provide a second layer of junk removal in `index.ts`.

### Hand-written SQL migrations are authoritative for constraints, views, and data fixes

Looks like:
Drizzle-generated SQL should be enough, so editing old generated files might be acceptable.

Actually:
Generated files cover schema DDL only. Constraints, RLS, views, and data migrations live in `packages/db/migrations/sql/*.sql`.

Why:
The migration runner applies generated DDL plus hand-written SQL in deterministic order.

Do not change because:
Editing old generated files breaks replay expectations and production drift recovery.

## 11. Credentials and environment

| Variable | Purpose | Stored where | Required in dev | Required in prod |
|---|---|---|---|---|
| `DATABASE_URL` | app DB access via Supabase transaction pooler | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `DIRECT_URL` | migrations/admin DB access via session pooler | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `NEXT_PUBLIC_SUPABASE_URL` | browser Supabase URL | `.env.local`, Vercel | yes | yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | browser anon key | `.env.local`, Vercel | yes | yes |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | browser publishable key | `.env.local`, Vercel | yes | yes |
| `SUPABASE_SERVICE_ROLE_KEY` | server-side privileged Supabase access | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `ANTHROPIC_API_KEY` | Anthropic adapter | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `OPENAI_API_KEY` | OpenAI adapter + embeddings | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `GOOGLE_CLOUD_PROJECT` | Vertex adapter project | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `GOOGLE_CLOUD_LOCATION` | Vertex region | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | service-account JSON content for Vertex ADC bootstrapping | Vercel/Trigger.dev secret, optional local | no | yes |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` | temp GCS bucket for oversized file-backed Vertex caches | env/secret | optional | recommended |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_PREFIX` | temp GCS prefix for those uploads | env/secret | optional | optional |
| `GOOGLE_VERTEX_BATCH_GCS_BUCKET` | GCS bucket for Vertex Batch Prediction JSONL I/O (D14) | env/secret | optional | required if batch mode + Vertex |
| `GOOGLE_VERTEX_BATCH_GCS_PREFIX` | Object prefix inside the batch bucket | env/secret | optional | optional |
| `DEEPSEEK_API_KEY` | DeepSeek adapter | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `DASHSCOPE_API_KEY` | Qwen adapter | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `OPENROUTER_API_KEY` | model catalog enrichment only | `.env.local`, Vercel if desired | optional | optional |
| `TRIGGER_SECRET_KEY` | Trigger.dev auth | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `TRIGGER_PROJECT_REF` | Trigger.dev project selector | `.env.local`, Vercel | optional | optional |

For exact sources and setup notes, read `docs/configuration.md`.

## 12. Deployment

Current deployment path:

- GitHub repo: `u2giants/theoracle`
- CI workflow: `.github/workflows/pr-check.yml`
- Web deploy target: Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`
- Worker deploy target: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`
- Database/auth/storage target: Supabase project configured through env

How deployment works today:

1. Merge or push to `main`.
2. GitHub Actions runs `pr-check.yml`, which installs dependencies and builds `@oracle/web`.
3. Vercel auto-deploys the web app from GitHub using `vercel.json`.
4. Trigger.dev workers are deployed manually with `pnpm --filter @oracle/workers deploy`.
5. Database migrations are applied manually with `pnpm db:migrate` before shipping code that depends on them.

Rollback:

- Web: promote a previous Vercel deployment.
- Workers: redeploy from a previous commit or roll back in Trigger.dev.
- DB: ship a compensating SQL migration; there is no automatic rollback layer.

Runtime env vars live in:

- Vercel project environment settings
- Trigger.dev project secrets/env
- local `.env.local`

SSH:

- SSH is not part of the normal deployment path.
- No VPS/container SSH workflow exists in this repo.

## 13. Critical incidents

### 2026-05-26 Provider-layer regression through a generic SDK abstraction

What happened:
A provider-adapter implementation briefly used generic AI SDK wrappers instead of raw provider SDKs.

Impact:
Provider-native cache and structured-output behavior would have been obscured.

Root cause:
The implementation ignored the documented provider-native boundary.

Recovery:
The adapters were rewritten to use raw provider SDKs directly.

Rule added to prevent recurrence:
Do not introduce generic inference wrappers into `packages/ai/src/providers/`.

### 2026-05-27 Missing migration caused auth callback failures

What happened:
Code referencing `employees.departments` reached production before the corresponding live DB column existed.

Impact:
OAuth callback queries failed and users hit 500s during sign-in.

Root cause:
A schema-affecting change was shipped without first applying the migration to the live DB.

Recovery:
A catch-up migration added and backfilled the missing column.

Rule added to prevent recurrence:
Apply migrations before pushing code that requires them, and stage git changes explicitly instead of sweeping unrelated files with `git add -A`.

## 14. Pending work

| Status | Item | Owner/next action |
|---|---|---|
| open | `pnpm db:migrate` fails at Step 2 with `relation "model_capabilities" already exists` — the Drizzle `__drizzle_migrations` journal in production is out of sync with the on-disk `packages/db/migrations/0*.sql` files. Hand-written SQL changes still ship via Supabase MCP `apply_migration` in the meantime. | Reconcile the journal: identify which generated migrations actually ran in prod, INSERT their hashes into `__drizzle_migrations` so the runner skips them. See `HANDOFF.md`. |
| open | `apps/web/app/admin/taxonomy/_actions.ts` approves some proposal types by queueing reclassification work rather than applying it inline. | Keep the actions as-is until the reclassification path is expanded further. |
| open | Only `.github/workflows/pr-check.yml` exists. There is no automated DB migration workflow and no automated Trigger.dev deploy workflow. | Keep manual `pnpm db:migrate` and `pnpm --filter @oracle/workers deploy` in the release process until workflows are added. |
| open | Authentik is mentioned in schema/docs but no Authentik login flow is wired in the app. | Treat Authentik as not implemented. |
| open | Oversized Vertex file-backed caches require `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` in the runtime env. Without it, the adapter falls back to text-prefix caching only. | Provision the bucket/env in environments that need large-document cache optimization. |
| open | Vertex Batch Prediction requires `GOOGLE_VERTEX_BATCH_GCS_BUCKET` to be provisioned + the worker SA granted `roles/storage.objectAdmin` on it. | One-time admin task before batch mode can be enabled for Vertex routes. OpenAI batch needs no infrastructure setup. Flip extraction to batch via `/admin/settings` → "Extraction dispatch mode" card. |

If work is incomplete in a future session, create `HANDOFF.md` at the repo root and delete it once the work is finished.
