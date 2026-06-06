# AGENTS.md — The Oracle Developer Guide

Read this first. It is the canonical operating guide for developers and AI coding sessions working in `D:\repos\oracle`.

## 1. Project summary

The Oracle is an evidence-backed enterprise knowledge graph for POP Creations / Spruce Line. Employees interact with it through chat and document uploads; workers extract operational claims with quote-level evidence; deterministic validators gate promotion into approved claims; synthesis workers maintain traceable Brain sections; admin screens review runs, caches, claims, gaps, contradictions, and taxonomy proposals. The outcome that matters is explainable business knowledge: every important answer or synthesis artifact must be traceable back to messages, document chunks, or approved claims.

## 2. Multi-model AI note

There is no universal ignore-file standard across AI coding tools.

`.claudeignore` works for Claude Code.

When using any other AI tool, paste this file as your first message and follow the instructions in the "What to ignore" section.

## Documentation map: what to read for each task

Always start with `AGENTS.md`. Then load additional docs only when relevant — do not bulk-read every `.md` file.

| Task / question | Read these docs | Usually do not need |
|---|---|---|
| Quick repo orientation | `README.md`, `AGENTS.md` | Deep `docs/` unless task requires them |
| Modify app behavior (chat, extraction, synthesis, admin UI) | `AGENTS.md`, `docs/architecture.md` if system design is affected | `docs/deployment.md` unless deploy behavior changes |
| Add or change AI provider adapter or model catalog | `AGENTS.md`, `docs/architecture.md` (adapter table + data flow), provider files under `packages/ai/src/providers/`, `DECISIONS.md` | Worker or webhook code |
| Add or change configuration, env vars, feature flags, secrets | `AGENTS.md` §11, `docs/configuration.md`, `docs/deployment.md` if prod/runtime env is affected | Unrelated architecture docs |
| Change dev scripts, test/lint/debug workflow, or package scripts | `AGENTS.md`, `docs/development.md` | `docs/deployment.md` unless CI/CD changes |
| Change deployment, CI/CD, Vercel release, Trigger.dev deploy, rollback | `AGENTS.md` §12, `docs/deployment.md`, `docs/configuration.md` | Local-only development docs |
| Change database schema, migrations, models, or data flow | `AGENTS.md`, `docs/architecture.md`, `packages/db/src/schema.ts` | Deployment docs unless rollout behavior changes |
| Add or change a worker task | `AGENTS.md` §6 task-to-file, `apps/workers/src/trigger/`, `docs/architecture.md` if data flow changes | Front-end app code unless there is a matching UI/API hook |
| Change Teams transcript ingestion (Graph path) | `AGENTS.md` §6 + §10 quirks, `docs/architecture.md` §"Teams transcript ingestion" | Recall docs unless both paths are affected |
| Change Recall.ai live bot path | `AGENTS.md` §6 + §10 quirks, `docs/architecture.md` §"Teams live participation (Recall.ai)" | Microsoft Graph Teams ingestion docs |
| Investigate a bug or incident | `AGENTS.md` §13 (critical incidents), docs for the affected area, `HANDOFF.md` if present | Unrelated folder-level READMEs |
| Continue unfinished work | `AGENTS.md`, `HANDOFF.md`, docs named inside `HANDOFF.md` | Docs unrelated to the handoff scope |
| Claude Code session | `CLAUDE.md`, then `AGENTS.md` | Other docs unless task requires them |
| Documentation-only cleanup | `AGENTS.md`, `README.md`, affected `docs/`, `HANDOFF.md` if present | Source files except to verify accuracy |

Rules:
- MUST be task-based.
- MUST NOT become a flat list of every Markdown file.
- Read `HANDOFF.md` whenever it exists — it captures what is in-progress or unfinished.
- `docs/oracle/` — deeper AI-retrofit reference material; only read when the task touches the AI-retrofit spec directly.

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
- `scripts/test-teams-transcript-access.ps1` — no-dep PowerShell probe: does the tenant grant the app Teams transcript access?
- `scripts/diagnose-transcripts.ps1` — tries `getAllTranscripts` variants for an organizer (scheduled meetings only)
- `scripts/create-adhoc-subscription.ps1` — one-off `adhocCalls/getAllTranscripts` subscription creation (webhook must be live first; the `teams-subscription-manager` worker is the production path)

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
| Add a database field or table | `packages/db/src/schema.ts`, new file under `packages/db/migrations/sql/` if hand-written SQL is needed, generated Drizzle migration if schema changed. Ship through `pnpm db:migrate` only — never via Supabase MCP `apply_migration` or `drizzle-kit push`, both bypass the journal. Run `pnpm db:check-drift` if unsure of state. | previously applied migration files; `drizzle.__drizzle_migrations` directly |
| Add a worker | `apps/workers/src/trigger/*.ts`, `apps/workers/trigger.config.ts`, docs if operational behavior changes | `apps/web/**` unless there is a matching UI/API hook |
| Add an admin page | `apps/web/app/admin/**`, possibly `packages/db/migrations/sql/*.sql` for a new admin view | RLS helpers unless policy changes are truly required |
| Change auth/linking behavior | `packages/auth/src/**`, `apps/web/app/auth/**`, `apps/web/app/_components/login-form.tsx` | direct edits to Supabase-managed auth tables |
| Add or change env/config | `.env.example`, `turbo.json`, `docs/configuration.md`, consuming code | `.env.local` in git |
| Add or change model catalog filtering | `packages/ai/src/model-capabilities/sources/<provider>.ts` (per-provider source/blocklist), `packages/ai/src/model-capabilities/index.ts` (write-time post-enrichment filters), **`apps/web/app/api/admin/model-catalog/route.ts` `passesQualityFilter` (mirror filter at read time)**, `scripts/refresh-catalog.ts` to verify, `docs/architecture.md`, `DECISIONS.md` | provider inference adapters, route catalog |
| Reorder or regroup admin nav | `apps/web/app/admin/_components/admin-nav.tsx` (GROUPS array + isActive helper). Layout wrapper stays server-rendered for auth. | `apps/web/app/admin/layout.tsx` other than the AdminNav import — auth still runs there |
| Change deployment behavior | `vercel.json`, `.github/workflows/pr-check.yml`, `apps/workers/trigger.config.ts`, `docs/deployment.md` | ad hoc dashboard-only assumptions without documenting them |
| Change Teams transcript ingestion | webhook: `apps/web/app/api/teams/notifications/route.ts` + `apps/web/lib/graph-notification-crypto.ts` + the subscription helpers in `apps/web/lib/microsoft-graph.ts`; workers: `apps/workers/src/trigger/teams-{subscription-manager,transcript-ingestion}.ts` + `apps/workers/src/lib/graph-transcripts.ts`; env in `docs/configuration.md`. Keep the two Graph helper copies in sync (web is reference). | the candidate-before-claim pipeline (ingestion only writes `messages`; never `claims`) |

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
| Entra app (Graph backend) | `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` | Entra `TheOracle` app | App-only Graph: directory pull + Teams transcripts. Tenant `1caeb1c0-a087-4cb9-b046-a5e22404f971`. |
| Teams transcript subscription | resource `communications/adhocCalls/getAllTranscripts` | `apps/workers/src/lib/graph-transcripts.ts`, Graph **beta** | The only capture path for ad-hoc calls. ~1h max lifetime; renewed by `teams-subscription-manager`. |
| Teams webhook | `https://oracle.designflow.app/api/teams/notifications` | `apps/web/app/api/teams/notifications/route.ts` | Graph `notificationUrl` + `lifecycleNotificationUrl`. Must be live before a subscription can be created. |
| Recall live Teams webhook | `https://oracle.designflow.app/api/teams/live/recall` | `apps/web/app/api/teams/live/recall/route.ts`, `apps/workers/src/trigger/teams-live-recall-utterance.ts` | Optional live meeting path. Recall owns the Teams bot + live STT transport; Oracle receives finalized utterances and can post gated questions back through Recall. |
| Recall.ai workspace | `f2f8cedc-6d28-4fd2-8d06-402b74d65bcc` (POP Creations) | Recall.ai dashboard | US East (N. Virginia), API v1.11, base URL `https://us-east-1.recall.ai`. Do not use the `us-west-2` endpoint — wrong region for this workspace. |
| Graph notification cert id | `oracle-teams-adhoc-1` | `TEAMS_NOTIFICATION_CERT_ID` | Self-signed RSA cert; public half encrypts notifications, private half (`TEAMS_NOTIFICATION_PRIVATE_KEY`) decrypts them. |
| Graph transcript permissions | `OnlineMeetingTranscript.Read.All`, `CallTranscripts.Read.All` | Entra app role assignments | `CallTranscripts.Read.All` (id `4cd61b6d-8692-40bf-9d90-7f38db5e5fce`) is tenant-wide; required for the ad-hoc subscription. Also needs a Teams app access policy. |

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
| Microsoft Graph | Tenant directory pull (admin onboarding) + Teams call-transcript ingestion. App-only `client_credentials`. | Microsoft Entra | app `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` | Raw `fetch` (no SDK) — `apps/web/lib/microsoft-graph.ts`, `apps/workers/src/lib/graph-transcripts.ts` |

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

### Claim retrieval has exactly one path, and the two SQL branches must stay in lockstep

Looks like:
`searchWithRetrievalPlan()` in `packages/ai/src/retrieval.ts` contains two near-duplicate SQL queries — a hybrid pgvector+tsvector path and a `_searchFallbackTsvector()` path — and a separate `verify:retrieval-filter-parity` script that seems redundant with typecheck.

Actually:
The fallback runs only when `OPENAI_API_KEY` is unset (dev, no embeddings). Both branches build their WHERE clauses from the same private helper `buildPlanMetadataFilters()`, and the parity guard statically asserts every filter the helper returns is interpolated into BOTH branches. `searchApprovedClaims()` (a weaker, plan-less retrieval) was deleted on 2026-05-28 — there is now exactly one endorsed retrieval entry point.

Why:
The recurring regression here was adding a narrowing filter to the hybrid path and forgetting the fallback, making dev-mode retrieval silently weaker (or vice versa). Typecheck can't catch it — the fragments are SQL strings. The guard runs in CI (`pr-check.yml`) and via `pnpm --filter @oracle/ai verify:retrieval-filter-parity`.

Do not change because:
Adding a second retrieval path (or a filter to only one branch) reintroduces the exact silent-divergence class the guard exists to prevent. New narrowing fields go in `buildPlanMetadataFilters()` and get interpolated into both branches — nowhere else.

### Microsoft Graph Teams transcripts arrive after the call

Looks like:
The Oracle could "sit in" a Teams call and react live, or read the live transcript panel a bot can see on screen.

Actually:
Microsoft Graph exposes **no** live caption/transcript API, and Teams does not pipe spoken words into the meeting text chat. The Graph transcript path is therefore after-the-fact, and only if transcription was turned on. Ad-hoc "Meet Now" calls are reachable **only** through a `communications/adhocCalls/getAllTranscripts` change-notification subscription (beta endpoint; v1.0 rejects it), which is "listen going forward" — a transcript notifies only if the subscription existed before transcription started.

Live spoken participation now exists through the optional Recall.ai path: Recall provides the meeting bot and STT stream; The Oracle receives finalized `transcript.data` utterances via `/api/teams/live/recall`, writes them as `messages`, and posts only gated questions back to Teams chat through Recall.

Why:
Native live spoken awareness would require Microsoft media-bot infrastructure. Recall avoids changing Oracle's infrastructure by externalizing the Teams audio/STT transport while keeping Oracle's durable state in Postgres.

Do not change because:
Do not confuse the two paths. Graph is post-call evidence/backfill; Recall is live optional participation. Both must still write utterances to `messages` and let candidate-before-claim handle durable knowledge. See `docs/architecture.md` § "Teams transcript ingestion" and § "Teams live participation (Recall.ai)".

### The Graph subscription/transcript helper is duplicated on purpose

Looks like:
`apps/web/lib/microsoft-graph.ts` and `apps/workers/src/lib/graph-transcripts.ts` both implement the app-only token + subscription/transcript calls. Looks like copy-paste that should be a shared package.

Actually:
`apps/web` (the webhook) and `apps/workers` (the subscription manager + ingestion) are separate runtime processes, and cross-app imports aren't allowed. Both need the same small Graph surface. The web copy (`microsoft-graph.ts`) is the reference; the worker copy is intentionally self-contained.

Do not change because:
Forcing a shared package for ~150 lines pulls Graph code into a third location and couples the web and worker builds. If they drift, reconcile toward the web copy rather than introducing a shared dependency.

### ESLint config imports eslint-config-next natively, not via FlatCompat

Looks like:
`apps/web/eslint.config.mjs` imports `eslint-config-next/core-web-vitals` and spreads it directly, instead of the `FlatCompat`-based pattern `create-next-app` generates.

Actually:
With `eslint-config-next` v16 + ESLint 9, the `FlatCompat` path throws `TypeError: Converting circular structure to JSON` (the bundled react config has a circular `configs` object). v16 ships a native flat-config array, so importing it directly is the working path. The old `.eslintrc.json` + `next lint` were removed (Next 16 dropped the `next lint` subcommand).

Do not change because:
Reverting to `FlatCompat` reintroduces the circular-structure crash; reverting to `next lint` breaks entirely (`next lint` no longer exists in Next 16).

### Quote validation is fuzzy for transcripts, strict for documents

Looks like:
`validateQuote` has an `allowFuzzy` path that accepts a quote when its tokens merely *overlap* the source — contradicting the "deterministic verbatim provenance / no fuzzy match" principle in `docs/oracle/03` and the comment at the top of `quote-validator.ts`.

Actually:
Spoken Teams transcripts are disfluent and the extraction model paraphrases them, so the polished claim quote never appears verbatim in any utterance — strict matching rejected ~every transcript-derived claim. The fuzzy path (opt-in, enabled only on the message/transcript path in `claim-extraction.ts`; documents stay strict) is a **deterministic** token-overlap check (no LLM grader) and anchors the stored evidence to the **real** utterance text, not the model's paraphrase. See `DECISIONS.md` D-transcript-fuzzy-quote.

Why:
Without it the entire Teams-transcript feature produces zero promotable claims. Provenance is preserved as "this real utterance supports this claim" rather than "the model copied these exact words."

Do not change because:
Reverting to strict-only re-breaks transcript extraction. If tightening is wanted, raise `fuzzyMinOverlap` or restrict `allowFuzzy` to transcript-sourced messages — don't remove it.

### `raw_transcripts` is hand-written SQL, not in schema.ts

Looks like:
`raw_transcripts` (the original VTT per call) is missing from `packages/db/src/schema.ts`, and the ingestion worker reads/writes it with raw `sql` instead of Drizzle.

Actually:
It's defined only in the hand-written `packages/db/migrations/sql/62_raw_transcripts.sql` (idempotent `CREATE TABLE IF NOT EXISTS`), like the observability views. Keeping it out of `schema.ts` avoids a drizzle-kit drift entry for an ancillary raw-storage table the typed query layer never needs.

Why:
The VTT is stored so the whole pipeline stays re-runnable from true source after Microsoft expires the transcript (`messages` are a lossy transform). See `DECISIONS.md` D-raw-transcripts.

Do not change because:
Adding it to `schema.ts` would make drizzle-kit want to generate a migration for an already-applied hand-written table (drift). Leave it as hand-written SQL.

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
| `PROD_DIRECT_URL` | Used by the CI drift-check step to reach production Postgres | GitHub Actions repo secret (`gh secret list`) | no | yes (CI) |
| `TRIGGER_PROJECT_REF` | Trigger.dev project selector | `.env.local`, Vercel | optional | optional |
| `AZURE_TENANT_ID` | Entra ID tenant GUID for the Graph backend tenant directory pull | `.env.local`, Vercel | optional | optional |
| `AZURE_GRAPH_CLIENT_ID` | Entra app (Application) ID — same `TheOracle` app as SSO | `.env.local`, Vercel | optional | optional |
| `AZURE_GRAPH_CLIENT_SECRET` | Client secret for app-only Graph client_credentials calls. Distinct from the SSO secret (which lives in Supabase). | `.env.local`, Vercel | optional | optional |
| `TEAMS_NOTIFICATION_PRIVATE_KEY` | PEM key the webhook uses to decrypt Graph transcript notifications | Vercel (webhook) | optional | yes for Teams ingestion |
| `TEAMS_WEBHOOK_CLIENT_STATE` | Shared secret on every notification (webhook verifies, worker sets) | Vercel + Trigger.dev | optional | yes for Teams ingestion |
| `TEAMS_NOTIFICATION_URL` | Public webhook URL the worker registers as the subscription target | Trigger.dev | optional | yes for Teams ingestion |
| `TEAMS_NOTIFICATION_PUBLIC_CERT` | Base64 DER public cert Graph encrypts notifications with | Trigger.dev | optional | yes for Teams ingestion |
| `TEAMS_NOTIFICATION_CERT_ID` | Identifier for the cert above (`oracle-teams-adhoc-1`) | Trigger.dev | optional | yes for Teams ingestion |
| `RECALL_API_KEY` | Recall.ai API key — creates Teams meeting bots and sends bot chat messages | Vercel + Trigger.dev | optional | yes for live Teams participation |
| `RECALL_WEBHOOK_SECRET` | `whsec_…` signature secret — verifies real-time `transcript.data` webhooks from Recall | Vercel | optional | yes for live Teams participation |
| `RECALL_BASE_URL` | Recall.ai region endpoint. POP Creations workspace is `https://us-east-1.recall.ai` | Vercel + Trigger.dev | optional | yes for live Teams participation |
| `RECALL_REALTIME_WEBHOOK_URL` | Public URL Recall calls for `transcript.data` events (set per-bot at create time) | Vercel | optional | yes for live Teams participation |
| `MICROSOFT_BOT_APP_ID` | Azure Bot Framework app ID — enables `@The Oracle join` command from inside Teams | Vercel | optional | required for Teams-native bot |
| `MICROSOFT_BOT_APP_PASSWORD` | Bot Framework client secret | Vercel | optional | required for Teams-native bot |
| `MICROSOFT_BOT_TENANT_ID` | Tenant ID for single-tenant Bot Framework auth; omit for multi-tenant | Vercel | optional | optional |

The Teams transcript app also needs the Graph **Application** permissions `OnlineMeetingTranscript.Read.All` + `CallTranscripts.Read.All` (tenant admin consent) and a Teams application access policy. For exact sources and setup notes, read `docs/configuration.md`.

## 12. Deployment

Current deployment path:

- GitHub repo: `u2giants/theoracle`
- CI workflow: `.github/workflows/pr-check.yml`
- Web deploy target: Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`
- Worker deploy target: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`
- Database/auth/storage target: Supabase project configured through env

How deployment works today:

1. Merge or push to `main`.
2. GitHub Actions runs `pr-check.yml`: installs dependencies, builds `@oracle/web`, runs the static DB-free verify guards (`verify:retrieval-filter-parity`, `verify:vertex-file-cache`), then runs `pnpm db:check-drift` against production (requires the `PROD_DIRECT_URL` repo secret; skips gracefully if absent). Drift in the Drizzle migration journal fails the build.
3. Vercel auto-deploys the web app from GitHub using `vercel.json`.
4. Trigger.dev workers are deployed manually with `pnpm --filter @oracle/workers run deploy` (the `run` keyword is required — `pnpm` reserves the bare `deploy` form for its own subcommand).
5. Database migrations are applied manually with `pnpm db:migrate` before shipping code that depends on them. Hand-written `migrations/sql/*.sql` files MAY be applied via Supabase MCP `apply_migration`; generated `0NNN_*.sql` files MUST go through `pnpm db:migrate` (otherwise the journal drifts — see incident 2026-05-28).

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

### Release & CI/CD policy (the rules that actually apply here)

This repo is a **managed-platform** deployment — Vercel (web) + Trigger.dev (workers) + Supabase (DB/auth/storage). There are **no containers, no Dockerfiles, no container registry, no Coolify, no production VPS, and no SSH deploy**. Generic container/registry/Coolify/SSH CI-CD rules are therefore **Not Applicable** unless this repo ever adopts a self-hosted containerized model. The rules that DO apply:

- **Single-branch model: work on `main` only.** Do **not** create feature, staging, or release branches, and do not open PRs as a routine workflow — this repo has no promotion model. Commit straight to `main`. (Push to `main` only when Albert says push — see CLAUDE.md.)
- **One release path, repo-driven:** push to `main` → Vercel builds/deploys the web app from `vercel.json`; workers ship via `pnpm --filter @oracle/workers run deploy`; DB via `pnpm db:migrate`. No alternate routine deploy method.
- **CI verifies, never deploys.** `pr-check.yml` only builds + runs the static verify guards + checks migration drift. It must not deploy, SSH, mutate production, or publish artifacts.
- **The deploy gate is native to Vercel's build.** `vercel.json` `buildCommand` runs the static verify guards (`verify:retrieval-filter-parity`, `verify:vertex-file-cache`) **before** `@oracle/web build`. If a guard or the build fails, Vercel's production build fails and the previous deployment stays live — so a guard-breaking or build-breaking commit cannot reach production. This is the "hard blocker": enforcement lives in the platform's own build, not in a separate CI deploy step.
- **Repo is authoritative; the platform owns runtime.** Runtime env vars / secrets / domains live in Vercel / Trigger.dev / Supabase — never baked into CI shell commands, images, or committed `.env*` (except `.env.example`).
- **Schema changes only through the approved migration path** (`pnpm db:migrate` for generated `0NNN_*.sql`; Supabase MCP `apply_migration` for hand-written `sql/*.sql`). Never ad-hoc production schema edits as the normal path.
- **Traceability:** every production change is auditable from repo commit history + Vercel / Trigger.dev / Supabase deployment history.
- **Drift check is advisory.** The Drizzle migration-drift check needs prod DB creds and runs only in `pr-check.yml`, not in the Vercel build (the build has no prod DB access, by design). Migrations are applied manually via `pnpm db:migrate` anyway, so drift is a bookkeeping signal, not a runtime-breakage gate. Everything else (build + verify guards) is hard-gated in the Vercel build per the bullet above.

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

### 2026-05-28 Drizzle migration journal drifted from production

What happened:
`pnpm db:migrate` failed at Step 2 with `relation "model_capabilities" already exists`. Migration `0006_magical_revanche` had been applied to production at some earlier point — all four objects it creates (tables `model_capabilities` + `typing_indicators`, columns `employees.departments` + `entity_proposals.proposal_count`) existed in the live DB — but its sha256 was never written to `drizzle.__drizzle_migrations`. The runner therefore tried to replay it on every invocation.

Impact:
Database migrations could not ship through the canonical runner. Hand-written `migrations/sql/*.sql` files were unreachable because Step 2 failed before Step 3 ran them.

Root cause:
At least one Drizzle-generated migration was applied through a side channel that does not write to `drizzle.__drizzle_migrations` — most likely Supabase MCP `apply_migration` (which writes to `supabase_migrations.schema_migrations` instead), the Supabase dashboard SQL editor, or `drizzle-kit push`.

Recovery:
Inserted the correct sha256 (`d273fe37e62858c4e0e0b7e76fb6baa794889e2ed6efbf5f265f83c70d6941db`) into `drizzle.__drizzle_migrations` for `0006_magical_revanche`. `pnpm db:migrate` then completed cleanly. Commit `b108821`.

Rules added to prevent recurrence:
1. Generated `packages/db/migrations/0NNN_*.sql` files ship ONLY through `pnpm db:migrate`. Hand-written `packages/db/migrations/sql/*.sql` files (idempotent views/constraints) MAY ship via Supabase MCP `apply_migration` — those aren't journaled. Documented in CLAUDE.md → "Drizzle journal hygiene".
2. Added `pnpm db:check-drift` (`packages/db/src/check-migration-drift.ts`) that compares on-disk migration hashes against the journal. Wired into `.github/workflows/pr-check.yml` so every PR / push to main fails the build on drift. Requires repo secret `PROD_DIRECT_URL`. Commit `35439b2`.

### 2026-05-28 Batch-submit rollback left staging orphans

What happened:
The initial 2026-05-28 retry-safety fix in `claim-extraction-batch-submit.ts` (commit `830713c`) reverted messages from `processing` back to `pending` on submit failure but left the `extraction_batches` + `oracle_context_packs` rows it had already inserted in place. An inline comment falsely claimed the drain task would reap them later.

Impact:
There is no reaper in `claim-extraction-batch-drain.ts` for `extraction_batches WHERE provider_batch_job_id IS NULL`. Every failed submit accumulated dead `pending_model` staging rows + orphan context packs that admin observability would surface indefinitely as never-drained batches.

Root cause:
The fix's inline comment described an invariant that didn't exist in the codebase; the comment was never cross-checked against the drain task it referenced.

Recovery / fix:
Made the rollback symmetric and timing-aware. The submit task now tracks `stagedBatchIds`, `stagedContextPackIds`, and a `providerAccepted` flag (flipped the instant `adapter.submitBatch` returns). On failure:
- `providerAccepted === false` (no live provider state): revert messages + DELETE both staging tables, scoped to ids this run created. Drain finds nothing because nothing existed.
- `providerAccepted === true` (batch live at provider): leave everything in place — drain finds rows by `customId` from the batch result, not by the back-link — and log loudly including the `providerBatchId` so an operator can manually recover if the post-submit DB writes failed.

Rule added to prevent recurrence:
Any "this gets cleaned up downstream" comment must point at the specific code path doing the cleanup. If no such code exists, do the cleanup inline.

### 2026-06-04 Webhook dispatched to the wrong Trigger.dev environment (near-miss)

What happened:
The Teams transcript webhook called `tasks.trigger('teams-transcript-ingestion')`, but the run landed in the **dev** Trigger.dev environment and **expired** (TTL 10m, never executed) — while the workers are deployed to **prod**. The first real call was silently lost.

Impact:
Transcript ingestion appeared to work (subscription fired, webhook received + decrypted the notification correctly — confirmed by the decrypted payload on the expired dev run) but produced no messages. Unlike document-ingestion (saved by its 4h sweep cron), transcripts have no sweep, so the call was unrecoverable.

Root cause:
Vercel's `TRIGGER_SECRET_KEY` was a **dev** environment key. The Trigger.dev SDK routes a trigger to whatever environment the key belongs to. Dev tasks only run when a local `trigger.dev dev` session is connected — none was — so the run sat for its TTL and expired.

Recovery:
Set Vercel Production `TRIGGER_SECRET_KEY` to the **prod** secret key + redeployed `apps/web`; re-triggered the same transcript in prod via the Trigger MCP → resolved 2/2.

Rule added to prevent recurrence:
Vercel's `TRIGGER_SECRET_KEY` MUST be the prod-environment secret key. Any `tasks.trigger()` from the web app dispatches to the key's environment; a dev key silently drops production work.

## 14. Pending work

| Status | Item | Owner/next action |
|---|---|---|
| open | `apps/web/app/admin/taxonomy/_actions.ts` approves some proposal types by queueing reclassification work rather than applying it inline. | Keep the actions as-is until the reclassification path is expanded further. |
| open | Only `.github/workflows/pr-check.yml` exists (build + two verify guards + Drizzle drift check). There is no automated DB migration workflow and no automated Trigger.dev deploy workflow. | Keep manual `pnpm db:migrate` and `pnpm --filter @oracle/workers run deploy` (note: `run` keyword required — `pnpm` reserves the bare `deploy` form for its own subcommand) in the release process until workflows are added. |
| resolved | `RetrievalPlan.requiredEntities` semantics: **disjunctive (any-of) — decided 2026-05-28, keep as-is.** A claim matches if it carries ANY of the listed entities. Conjunctive (all-of) was rejected because it would require a single claim to mention every listed entity, collapsing recall for multi-entity queries (claims are typically single-entity). Filter lives in `buildPlanMetadataFilters()` in `packages/ai/src/retrieval.ts`. | No action. If a future "facts connecting X and Y" feature is ever wanted, add it as a separate explicit mode — do not flip the default. |
| open | `RetrievalPlan.requiredEntities` is declared and enforced (any-of) but **no production code populates it**. `buildRetrievalPlanFromQuery()` is a keyword matcher that routes to broad domains; it does not do named-entity recognition + registry resolution to pin specific entities. This is a deferred feature, not a bug — the field is the socket a future model-backed plan builder (`buildRetrievalPlanWithModel`, noted in `retrieval-plan.ts` header) would fill. | Build entity recognition + resolution into plan construction when per-query latency budget allows the extra structured-output call. Until then the field stays empty and inert. |
| open | Authentik is mentioned in schema/docs but no Authentik login flow is wired in the app. | Treat Authentik as not implemented. |
| open | Oversized Vertex file-backed caches require `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` in the runtime env. Without it, the adapter falls back to text-prefix caching only. Used by both the extraction worker and (since the chat-attachment file-cache v1) the interview chat route for large attached PDFs. | Provision the bucket/env in environments that need large-document cache optimization. |
| open | Chat-attachment file-cache (v1) limitations: (1) only ONE PDF per turn is cached; other attachments are not separately inlined while the file cache is active; (2) a cross-provider fallback (Vertex→Anthropic on a transient error) loses the cached document — degraded answer, not an error, logged as a warning. | Acceptable for v1. Hardening = fix Vertex multimodal `buildContents` then keep the attachment inline + dedupe the cached copy in the adapter, and/or constrain a Vertex interview route's fallback to also be Vertex. |
| open | Vertex `buildContents` collapses each chat turn to a single text part, so inline image/file parts are not translated to `inlineData`/`fileData`. Vertex chat vision is effectively unwired. | Translate AI-SDK parts → Gemini parts. Prerequisite for general Vertex vision and for caching a doc alongside other inline attachments. |
| open | Vertex Batch Prediction requires `GOOGLE_VERTEX_BATCH_GCS_BUCKET` to be provisioned + the worker SA granted `roles/storage.objectAdmin` on it. | One-time admin task before batch mode can be enabled for Vertex routes. OpenAI batch needs no infrastructure setup. Flip extraction to batch via `/admin/settings` → "Extraction dispatch mode" card. |
| done | **Teams transcript ingestion — LIVE + validated end-to-end (2026-06-04/05).** Real Meet-Now call → subscription → webhook → ingestion → 95 messages, `speakersResolved 2/2`. Workers `20260605.1`. Speaker resolution now email-based (`fbb82cd`) + bootstrap-by-email for `@popcre.com` (`e73868b`); 38 employees seeded. | No action — feature works. Fuzzy quote matching (`89d2fd9`) + raw_transcripts persistence added. |
| open | **Extraction gates hold most claims on a fresh system** (not a bug): entity registry is empty → new entities (people, systems, RFQ…) are unresolved → claim **held** + entity queued as `entity_proposals`; `domain_valid` fails when proposed domains don't map to active top-domains; impact≥7 claims → `pending_review`. | Seed the entity registry + active `knowledge_top_domains` to let claims flow. Touches the review/safety model — get owner sign-off before loosening. See HANDOFF.md. |
| open | **Synthesis never demonstrated** — needs ≥1 approved claim; 4 sit in `pending_review`. | Approve a claim (SQL or admin) → trigger `brain-synthesis` → confirm Brain narrative. |
| open | **Recall.ai live Teams bot path — wired but not end-to-end tested.** Code committed (`bfd6612`); region bug fixed (`4219c66`, default now `us-east-1`); env vars set in Vercel (`RECALL_API_KEY`, `RECALL_WEBHOOK_SECRET`, `RECALL_BASE_URL`, `RECALL_REALTIME_WEBHOOK_URL`) and Trigger.dev (`RECALL_API_KEY`, `RECALL_BASE_URL`); workers deployed v20260606.1; webhook responding at production URL (signature verification confirmed). | End-to-end test: `POST https://oracle.designflow.app/api/teams/live/start` with a real Teams meeting URL → admit bot → speak → confirm `messages` row with `source='teams_live_recall'` and optional Oracle question posted to meeting chat. See `docs/deployment.md` § "Teams live participation" and DECISIONS.md before changing behavior. |
| open | **Secret rotation — CRITICAL.** Three secrets exposed in chat sessions: (1) Azure app client secret (prior session); (2) Vercel API token (prior session); (3) `RECALL_API_KEY` + `RECALL_WEBHOOK_SECRET` (2026-06-06 session). | Rotate in Recall dashboard → update `RECALL_API_KEY` + `RECALL_WEBHOOK_SECRET` in Vercel + Trigger.dev. Rotate Azure client secret in Entra → update `AZURE_GRAPH_CLIENT_SECRET` in Vercel + Trigger.dev. Revoke Vercel API token in Vercel account settings. |
| open | `pnpm lint` migration surfaced ~10 pre-existing `apps/web` violations the broken script had masked: 2× `react/no-unescaped-entities` (`proposals/_components/proposal-card.tsx`), 2× `react-hooks/set-state-in-effect` (`channel-chat.tsx`, `document-upload.tsx`), ~6 stale `eslint-disable` directives (`api/chat/route.ts`). | Fix in a focused lint-cleanup pass; not blocking (lint isn't in the Vercel build gate). |

If work is incomplete in a future session, create `HANDOFF.md` at the repo root and delete it once the work is finished.
