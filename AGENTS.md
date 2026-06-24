# AGENTS.md — The Oracle Developer Guide

Read this first. It is the canonical operating guide for developers and AI coding sessions working in `C:\repos\oracle`.

## 1. Project summary

The Oracle is an evidence-backed enterprise knowledge graph for POP Creations / Spruce Line. Employees interact with it through chat and document uploads; workers extract operational claims with quote-level evidence; deterministic validators gate promotion into approved claims; synthesis workers maintain traceable Brain sections; admin screens review runs, caches, claims, gaps, contradictions, and taxonomy proposals. The outcome that matters is explainable business knowledge: every important answer or synthesis artifact must be traceable back to messages, document chunks, or approved claims.

## 2. Multi-model AI note

There is no universal ignore-file standard across AI coding tools.

`.claudeignore` works for Claude Code.

When using any other AI tool, paste this file as your first message and follow the instructions in the "What to ignore" section.

## Documentation map: what to read for each task

Always start with:

- `AGENTS.md`

Then load additional docs only when relevant — do not bulk-read every `.md` file.

| Task / question | Read these docs | Usually do not need |
|---|---|---|
| Quick repo orientation | `README.md`, `AGENTS.md` | Deep docs under `docs/` unless task requires them |
| Modify app behavior or project-owned code | `AGENTS.md`, relevant folder-level `README.md` if present, `docs/architecture.md` if system design is affected | `docs/deployment.md` unless deploy behavior changes |
| Add or change AI provider adapter or model catalog | `AGENTS.md`, `docs/architecture.md` (adapter table + data flow), provider files under `packages/ai/src/providers/`, `DECISIONS.md` | Worker or webhook code |
| Add or change configuration, env vars, feature flags, secrets | `AGENTS.md` §11, `docs/configuration.md`, `docs/deployment.md` if prod/runtime env is affected | Unrelated architecture docs |
| Pull secrets from 1Password via the MCP server or `op` CLI | `AGENTS.md`, `docs/1password.md` | Unrelated architecture docs |
| Change local setup, dev scripts, test/lint/debug workflow, package scripts, or tooling | `AGENTS.md`, `docs/development.md`, relevant package/config files | `docs/deployment.md` unless CI/CD changes |
| Change deployment, Docker, CI/CD, hosting, release flow, rollback, or runtime environment | `AGENTS.md` §12, `docs/deployment.md`, `docs/configuration.md`, relevant workflow/deployment files | Local-only development docs unless needed |
| Change database schema, migrations, models, external IDs, or data flow | `AGENTS.md`, `docs/architecture.md`, `docs/configuration.md` if env/config is affected, `packages/db/src/schema.ts`, relevant migration/model docs | Deployment docs unless rollout/deploy behavior changes |
| Add or change a worker task | `AGENTS.md` §6 task-to-file, `apps/workers/src/trigger/`, `docs/architecture.md` if data flow changes | Front-end app code unless there is a matching UI/API hook |
| Change Teams transcript ingestion (Graph path) | `AGENTS.md` §6 + §10 quirks, `docs/architecture.md` §"Teams transcript ingestion" | Recall docs unless both paths are affected |
| Change Recall.ai live bot path | `AGENTS.md` §6 + §10 quirks, `docs/architecture.md` §"Teams live participation (Recall.ai)" | Microsoft Graph Teams ingestion docs |
| Investigate a bug or incident | `AGENTS.md` §13 (critical incidents), docs for the affected area, `HANDOFF.md` if present | Unrelated folder-level READMEs |
| Continue unfinished work | `AGENTS.md`, `HANDOFF.md`, docs named inside `HANDOFF.md` | Docs unrelated to the handoff scope |
| Work in a subfolder with its own README | `AGENTS.md`, that folder-level `README.md`, and only broader docs referenced there | Other folder-level READMEs |
| Change the remote MCP knowledge endpoint (tools agents query) | `AGENTS.md` §10 MCP quirk, `apps/web/lib/mcp/README.md`, `apps/web/lib/mcp/*`, `apps/web/app/api/mcp/[transport]/route.ts` | Unrelated chat/worker code |
| China bilingual claim layer / claim translation / asking China-team members to verify a claim | `AGENTS.md` §7–§10, `china_imp.md` (design + resolved decisions), `packages/ai/src/retrieval.ts`, `apps/workers/src/trigger/claim-translation.ts`, `apps/web/app/admin/claims/*` (verification reuses main's `claim_review_question` + review-groups) | Teams/Recall docs; provider-adapter internals |
| Claude Code session | `CLAUDE.md`, then `AGENTS.md` | Other docs unless task requires them |
| Documentation-only cleanup | `AGENTS.md`, `README.md`, affected docs under `docs/`, folder-level READMEs only where relevant, `HANDOFF.md` if present | Source files except as needed to verify accuracy |
| Product/spec contract or AI-retrofit provenance | `AGENTS.md`, `oracle_master_spec.md`, relevant `docs/oracle/*` file, `oracle_ai_architecture_prompt caching.md` only if prompt-cache retrofit history is directly relevant | Current deployment/config docs unless operations are affected |

Rules:
- MUST be task-based.
- MUST NOT become a flat list of every Markdown file.
- Read `HANDOFF.md` whenever it exists — it captures what is in-progress or unfinished.
- Update this documentation map when documentation files are added, removed, renamed, or repurposed.
- `docs/oracle/` — deeper AI-retrofit reference material; only read when the task touches the AI-retrofit spec directly.
- `oracle_master_spec.md` and `oracle_ai_architecture_prompt caching.md` are historical/spec reference files, not default orientation docs.

## Five-minute orientation

If you are new to this repo, read only this path first:

1. `README.md` for the repo shape.
2. This file through §9 for operating rules, what to touch, external IDs, services, and ignore rules.
3. `HANDOFF.md` if it exists.
4. The single topic doc named by the table above.

Do not open every Markdown file. Most tasks need `AGENTS.md` plus one topic doc and the affected source files.

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
- root markdown files — `README.md`, `AGENTS.md`, `CLAUDE.md`, `DECISIONS.md`, `china_imp.md`

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
- `docs/wet-test-walkthrough.md`
- `docs/oracle/` — deeper AI-retrofit reference material
- `oracle_master_spec.md` — product/spec contract
- `oracle_ai_architecture_prompt caching.md` — historical AI architecture/prompt-cache reference
- `china_imp.md` — design + resolved decisions for the China bilingual claim layer (Phase 1 implemented; the code is the source of truth, this doc captures rationale). Read only for China bilingual / translation / recertification work.

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

## 6. Task-to-file navigation: what to edit for common changes

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
| Add or change model picker stage requirements / job briefs | `apps/web/lib/stage-requirements.ts` (shared requirement predicates), `apps/web/app/admin/settings/page.tsx` (role descriptions + Copy job brief text), `docs/configuration.md`, `docs/architecture.md` if behavior changes | provider inference adapters unless runtime dispatch changes |
| Reorder or regroup admin nav | `apps/web/app/admin/_components/admin-nav.tsx` (GROUPS array + isActive helper). Layout wrapper stays server-rendered for auth. | `apps/web/app/admin/layout.tsx` other than the AdminNav import — auth still runs there |
| Change deployment behavior | `vercel.json`, `.github/workflows/pr-check.yml`, `apps/workers/trigger.config.ts`, `docs/deployment.md` | ad hoc dashboard-only assumptions without documenting them |
| Change Teams transcript ingestion | webhook: `apps/web/app/api/teams/notifications/route.ts` + `apps/web/lib/graph-notification-crypto.ts` + the subscription helpers in `apps/web/lib/microsoft-graph.ts`; workers: `apps/workers/src/trigger/teams-{subscription-manager,transcript-ingestion,transcript-backfill}.ts` + `apps/workers/src/lib/graph-transcripts.ts`; env in `docs/configuration.md`. Keep the two Graph helper copies in sync (web is reference). Capture spans BOTH ad-hoc and scheduled meetings (two subscriptions via `ensureAllSubscriptions`); recover already-completed scheduled transcripts with the on-demand `teams-transcript-backfill` task (pulls `getAllTranscripts` per organizer → triggers ingestion, idempotent). Ingested utterances are HELD (`extraction_status='awaiting_approval'`) until an admin approves the transcript — see the transcript-approval-gate row. | the candidate-before-claim pipeline (ingestion only writes `messages`; never `claims`) |
| Change the meeting-transcript approval gate | `apps/web/app/admin/transcripts/page.tsx` + `_actions.ts` (`approveTranscript`/`rejectTranscript`, admin-only); nav in `apps/web/app/admin/_components/admin-nav.tsx` (Activity group); `apps/workers/src/trigger/teams-transcript-ingestion.ts` writes `extraction_status='awaiting_approval'`; gate state on `raw_transcripts.approval_status` (migration `76_transcript_approval.sql`) + enum value `awaiting_approval` (`packages/db/src/schema.ts` + `75_extraction_status_awaiting_approval.sql`). Approve flips the channel's held messages → `pending`; reject → `skipped`. The extraction cron only ever selects `pending`, so it needs NO change. | the extraction worker queries; the live Recall path (`teams-live-recall-utterance.ts`) is intentionally NOT gated |
| Change document ingestion (formats / image vision / prompts) | `apps/workers/src/trigger/document-ingestion.ts` (`resolveParseKind`, `extractTextFrom*`, `transcribeImageToText`, `IMAGE_TRANSCRIPTION_SYSTEM`, `buildUploaderContextNote`); image inline support in `packages/ai/src/providers/vertex-gemini-adapter.ts` (`toVertexParts`); admin upload UI `apps/web/app/admin/documents/**` + `apps/web/app/api/admin/documents/route.ts`. Redeploy the worker for parse/prompt changes. | the candidate-before-claim pipeline; the channel-based `POST /api/documents` (separate, chat path) |
| Add/change an auxiliary model (vision, general-purpose, translation, …) | `packages/ai/src/routes/auxiliary.ts` (registry entry), `apps/web/app/admin/settings/page.tsx` (`AUX_PRESENTATION` entry + optional `AUX_CLIPBOARD_BRIEFS` brief). Resolver, picker, and `/api/admin/models` already iterate the registry — no new branches needed. | `OracleModelRole` (stays the 3 pipeline roles); the pipeline route catalog |
| Change China bilingual claim rendering / locale-aware retrieval | `packages/db/src/schema.ts` (`claims.source_lang`, `claim_translations`), `packages/ai/src/retrieval.ts` (`buildPlanMetadataFilters` localization fragments — interpolate into BOTH branches; parity guard enforces), `packages/shared/src/domains.ts` (`SUPPORTED_LOCALES`), `apps/workers/src/trigger/claim-translation.ts`, `apps/web/app/api/chat/route.ts` | `getBrainSectionSnippets` (Brain is English-only by decision); the candidate-before-claim pipeline |
| Change claim translation / China review-question flow | `apps/web/app/admin/claims/page.tsx` + `apps/web/app/admin/claims/_actions.ts` (`translateClaimsForChina`; `assignClaimQuestion` + bulk `assignClaimQuestionBulkWithState` share `assignClaimQuestionCore`, which translates the question per `zh-CN` recipient via `translateReviewQuestionToChinese`), `apps/workers/src/trigger/claim-translation.ts` | the auto gap-generation path; `gaps` schema (no change needed) |
| Set an employee's reader language (China group) | `apps/web/app/admin/employees/page.tsx` ("Language" column) + `_components/employee-locale-form.tsx` + `_actions.ts` (`updateEmployeeLocale`). Writes `employees.locale` (`en`/`zh-CN`, validated vs `SUPPORTED_LOCALES`). This is the single switch the whole bilingual layer keys off — editable in the UI now, not SQL-only. Forward-looking (no retroactive translation). | the auth/identity tables |
| Show which claims are out for review / to whom | `apps/web/app/admin/claims/page.tsx` — derived live from open `claim_review_question` gaps (`gaps.related_claim_ids ? claim.id`, status in `open/queued/asked`), NOT a column on `claims`. The bulk "Ask selected to evaluate" checkboxes are UI-gated to `pending_review` rows, but `assignClaimQuestionCore` has no status gate. | adding a denormalized column on `claims` (the gap rows are the source of truth) |
| Change claims grouping / checkbox range-select | `apps/web/app/admin/claims/page.tsx` — claims are grouped by specific source (channel/meeting, document, external, or manual), derived in the evidence `LATERAL` (`source_group_key/label/kind`); rows arrive newest-first so first-seen key orders groups. Shift-click range select is a pure-DOM client enhancer `_components/shift-select.tsx` keyed off `data-select-form`/`data-select-index` (ranges never cross the `bulk-evaluate`/`translate-claims` form boundary). | the form-based submission model (checkboxes stay server-rendered + `form=`-associated) |

## 7. Data model and external identifiers

| Entity/System | Identifier | Where defined | Notes |
|---|---|---|---|
| Vercel project | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `AGENTS.md`, deployment/config docs | Web app target |
| Trigger.dev project | `proj_wgpzsvhmsopqhvwqaycn` | `apps/workers/trigger.config.ts` | Worker target; env can override |
| Current Supabase project | `eqccjfbyrywsqkxxpjvg` (`theoracle`, N. Virginia / `us-east-1`) | Supabase dashboard + runtime env | Primary DB/Auth/Storage/Realtime after 2026-06-20 cutover. Previous Ohio project `vokucjpanhvqunimlvsp` is `oracle.old`. |
| Supabase Storage bucket | `company_documents` | schema + worker code + docs | Private document bucket |
| Interview default route | `anthropic_claude_haiku_4_5_interview_primary` | `packages/ai/src/routes/catalog.ts`, settings row | Employee chat default |
| Extraction default route | `vertex_gemini_2_5_flash_extraction_primary` | same | Extraction default |
| Synthesis default route | `anthropic_claude_3_5_sonnet_synthesis_primary` | same | Synthesis default. **Name is legacy** — resolves at runtime to `anthropic/claude-sonnet-4-6`. Do NOT rename the route to match; live `settings` rows reference this exact string. Route IDs are the canonical shape for `default_*_route` (a bare `provider/modelId` resolves to the same route); the `/admin/settings` picker resolves route IDs to their concrete model rather than warning. See `docs/configuration.md`. |
| Embedding model | `text-embedding-3-small` | `packages/ai/src/embeddings.ts` | Locked to `vector(1536)` |
| Employee identity table | `employee_identities` | `packages/db/src/schema.ts` | Canonical auth-link table |
| Prompt/context audit table | `oracle_context_packs` | `packages/db/src/schema.ts` | One row per AI call plan |
| Usage detail table | `model_run_usage_details` | `packages/db/src/schema.ts` | Provider token/cache details |
| Provider cache table | `provider_cached_content` | `packages/db/src/schema.ts` | Explicit Vertex cache lifecycle + provider metadata |
| Provider response session table | `provider_response_sessions` | `packages/db/src/schema.ts` | Qwen Responses `previous_response_id` persistence |
| Model catalog table | `model_capabilities` | schema + model-capability refresh code | Populated from direct providers + OpenRouter enrichment |
| Auxiliary-model registry | `AUXILIARY_MODELS` | `packages/ai/src/routes/auxiliary.ts` | Admin-selectable models that are NOT one of the 3 strict `OracleModelRole`s (which stay frozen): currently `vision` and `general`. Each entry = `{ id, routeSettingKey, reasoningEffortSettingKey?, requiredCapability?, defaultRouteId? }`. Resolved at runtime by `resolveAuxiliaryRouteFromSettings(db, id)`. The picker, `/api/admin/models`, and the settings page all iterate it. |
| Image-vision route setting | `default_vision_route` | `settings` row + `auxiliary.ts` (`VISION_AUXILIARY_MODEL`) | Vision model used by `document-ingestion` to transcribe uploaded images to text (Pass 1) before extraction. Shipped fallback `vertex_gemini_2_5_flash_extraction_primary`. Chosen at Admin → Settings → "Image vision model" (no redeploy). Seeded with `ON CONFLICT DO NOTHING`. |
| Document context/hints | `documents.context`, `documents.domain_hints` | `packages/db/src/schema.ts`, migration `65_document_context_and_domain_hints.sql` | Optional uploader-provided free-text context (fed into extraction + image-vision prompts) and suggested top-domain ids (a non-binding prior). Per-claim `domain_valid` stays authoritative. |
| Admin document upload | `POST /api/admin/documents` | `apps/web/app/api/admin/documents/route.ts` | Admin-only, multi-file, **no channel** — stores the file, inserts a `documents` row, triggers `document-ingestion`. The channel-based `POST /api/documents` still exists for chat attachments. There is no UI to create a channel, so this is the path for company/process docs. |
| Design file operations domain | `design_file_operations` | `knowledge_top_domains`, `packages/ai/src/retrieval-plan.ts` | Separate from product/design workflow. Covers designer file naming, invalid characters, server folders, file-size reduction, linked assets, packaging, versioning, archive, and handoff file hygiene. |
| Operations systems domain | `operations_systems` | `knowledge_top_domains`, `packages/ai/src/retrieval-plan.ts` | Separate from generic IT support. Covers ERP/CRM/PLM workflows, Google Sheets to Designflow PLM integration, OrderList, MasterData, TaskList, field mapping, validation, and source-of-truth rules. |
| Business process domain | `business_process` | `knowledge_top_domains`, `packages/ai/src/retrieval-plan.ts`, `packages/oracle-engines/src/extraction/domain-mapping.ts` | Cross-functional company workflows and operating-model overviews. Use with narrower department/process domains for end-to-end flows; do not use as a generic dumping ground. |
| Training enablement domain | `training_enablement` | `knowledge_top_domains`, `packages/ai/src/retrieval-plan.ts` | Separate from `people_org` and sensitive HR records. Covers onboarding, role training, SOP learning paths, shadowing, cross-training, skill checks, and refresher guidance. |
| Provider Batch jobs table | `provider_batch_jobs` | `packages/db/src/schema.ts`, migration `60_batch_jobs.sql` | One row per submitted provider Batch API job (D14). `extraction_batches.provider_batch_job_id` links per-input rows to their batch. `model_runs.dispatch_mode` ∈ `'sync' \| 'batch' \| NULL`. |
| Claim review events | `claim_review_events` | `packages/db/src/schema.ts`, migration `68_claim_review_workflow.sql` | Append-only audit for approve/reject/revise/assign decisions. Revise creates a replacement claim and supersedes the original; do not overwrite original AI output in place. |
| Claim review groups | `claim_review_groups`, `claim_review_group_members` | `packages/db/src/schema.ts`, migration `73_claim_review_groups.sql` | Admin-managed recipient lists for sending a claim-review question to multiple employees. Sending to a group expands into one `gaps` assignment per active employee. |
| Domain review permissions | `knowledge_domain_review_departments` | same | Department-to-domain authorization map retained for future claim-review routing. It is currently not exposed in `/claims`; non-admin claim review is direct-assignment only. |
| Entra app (Graph backend) | `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` | Entra `TheOracle` app | App-only Graph: directory pull + Teams transcripts. Tenant `1caeb1c0-a087-4cb9-b046-a5e22404f971`. |
| Azure Bot resource | `theoracle-popcre-teams-bot` | Azure subscription `37077c95-ea53-4a19-8380-f3f48f0cc75d`, resource group `rg-oracle-teams-bot` | Free `F0` Bot Service resource. Display name `The Oracle`, endpoint `https://oracle.designflow.app/api/teams/bot/messages`, `msaAppType=SingleTenant`, Teams channel enabled. |
| Teams org app | Teams app id `17ccd7a1-b90b-428c-9966-33e7fb832923`; external id `850b2963-3583-4af9-bf18-84985ecbcf03` | Teams tenant app store, package generated from `apps/web/teams-app/oracle/manifest.template.json` | Organization/private-catalog app named `The Oracle`. Available to everyone; installed for Albert on 2026-06-09. |
| Teams transcript subscriptions | resources `communications/adhocCalls/getAllTranscripts` (ad-hoc "Meet Now") **and** `communications/onlineMeetings/getAllTranscripts` (scheduled meetings) | `apps/workers/src/lib/graph-transcripts.ts` (`TRANSCRIPT_RESOURCES`, `ensureAllSubscriptions`), Graph **beta** | Two standing subscriptions, one per resource (the "limit of 1" is per resource). ~1h max lifetime; both renewed by the single `teams-subscription-renew` cron (no new schedule — slots are 10/10). Subscriptions only "listen going forward"; recover already-completed scheduled transcripts with the on-demand `teams-transcript-backfill` task. |
| Teams webhook | `https://oracle.designflow.app/api/teams/notifications` | `apps/web/app/api/teams/notifications/route.ts` | Graph `notificationUrl` + `lifecycleNotificationUrl`. Must be live before a subscription can be created. |
| Recall live Teams webhook | `https://oracle.designflow.app/api/teams/live/recall` | `apps/web/app/api/teams/live/recall/route.ts`, `apps/workers/src/trigger/teams-live-recall-utterance.ts` | Optional live meeting path. Recall owns the Teams bot + live STT transport; Oracle receives finalized utterances and can post gated questions back through Recall. |
| Recall.ai workspace | `f2f8cedc-6d28-4fd2-8d06-402b74d65bcc` (POP Creations) | Recall.ai dashboard | US East (N. Virginia), API v1.11, base URL `https://us-east-1.recall.ai`. Do not use the `us-west-2` endpoint — wrong region for this workspace. |
| Graph notification cert id | `oracle-teams-adhoc-1` | `TEAMS_NOTIFICATION_CERT_ID` | Self-signed RSA cert; public half encrypts notifications, private half (`TEAMS_NOTIFICATION_PRIVATE_KEY`) decrypts them. |
| Graph transcript permissions | `OnlineMeetingTranscript.Read.All`, `CallTranscripts.Read.All` | Entra app role assignments | `CallTranscripts.Read.All` (id `4cd61b6d-8692-40bf-9d90-7f38db5e5fce`) is tenant-wide; required for the ad-hoc subscription. Also needs a Teams app access policy. |

| Bilingual claim translations table | `claim_translations` | `packages/db/src/schema.ts`, migration `0007_tricky_charles_xavier.sql` | Display-only per-language renderings of a claim summary (`(claim_id, lang)` PK, own `embedding`, `source_hash`). Canonical claim stays in `claims.source_lang`. NEVER used for quote validation/hashing/promotion. Retrieval `COALESCE`s it in by reader locale. China bilingual layer (`china_imp.md`). |
| Claim source language | `claims.source_lang` | `packages/db/src/schema.ts` | Language the claim was authored in (`varchar(12)`, default `'en'`). Stamped at promotion from the authoring employee's `locale`. |
| Employee locale | `employees.locale` | `packages/db/src/schema.ts` | Reader/content language (`varchar(12)`, default `'en'`). Admin sets `'zh-CN'` to put an employee on the "China team". Drives retrieval rendering, answer language, and the language a `claim_review_question` is asked in. |
| Supported locales | `SUPPORTED_LOCALES` (`['en','zh-CN']`) | `packages/shared/src/domains.ts` | Source of truth for the bilingual layer; add variants here (varchar(12) columns, no migration). |
| Translation route setting | `default_translation_route` | `settings` row + `auxiliary.ts` (`TRANSLATION_AUXILIARY_MODEL`) | Admin-selectable model for claim translation (Admin → Settings → "Translation model"). No capability filter (any catalog model, e.g. Qwen). Shipped fallback `DEFAULT_TRANSLATION_ROUTE_ID` = the Sonnet synthesis route. Not seeded — resolver falls back to the default when unset. |
| Claim translation worker | task `claim-translation` | `apps/workers/src/trigger/claim-translation.ts` | Translates an approved claim summary into other supported langs, embeds each, upserts `claim_translations` (idempotent on `source_hash`). Triggered by `translateClaimsForChina`. |
| China review-question translation | `gap_type='claim_review_question'` | `apps/web/app/admin/claims/_actions.ts` (`assignClaimQuestion` → `translateReviewQuestionToChinese`) | "Ask to verify" reuses main's claim-review-question + review-groups mechanism. A question sent to a `zh-CN` recipient (direct or via a group containing them) is translated to Chinese per-recipient via the `translation` route; English recipients get English. (There is no separate recertification worker — folded into review questions.) |

Do not casually rename or regenerate these identifiers. They are wired across code, DB, and deployment surfaces.

## 8. Container and service inventory

There are no Docker containers in this repo. Runtime services are fully managed.

| Container/service | Purpose | Managed by | App/project ID | Image/source |
|---|---|---|---|---|
| Vercel Functions | Next.js web app and API routes | Vercel | `prj_rP6Jlima7iK1paffEPhLqxlswGsC` | `apps/web` build via `vercel.json` |
| Oracle MCP server | Read-only MCP endpoint exposing approved business knowledge (claims, Brain sections, domain taxonomy) to external AI agents. Streamable HTTP at `/api/mcp/mcp`, bearer-token auth (`ORACLE_MCP_TOKEN`). | Vercel (in-app route) | same web project | `apps/web/app/api/mcp/[transport]/route.ts` + `apps/web/lib/mcp/` |
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
| Azure Bot Service | Teams Bot Framework message ingress for `@The Oracle join`. | Azure | subscription `37077c95-ea53-4a19-8380-f3f48f0cc75d`; resource `theoracle-popcre-teams-bot` | Free `F0` Bot Service registration; Teams channel routes signed Bot Framework turns to `/api/teams/bot/messages`. |
| Teams tenant app store | Makes The Oracle addable/searchable inside Teams. | Microsoft Teams Admin Center / Teams PowerShell | Teams app id `17ccd7a1-b90b-428c-9966-33e7fb832923` | Organization/private-catalog app package built from `apps/web/teams-app/oracle/manifest.template.json`. |

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
- `oracle_master_spec.md` unless product/spec alignment is the task
- `oracle_ai_architecture_prompt caching.md` unless AI architecture or prompt-cache retrofit history is the task
- `china_imp.md` unless the task is the China bilingual claim layer / claim translation / recertification
- `docs/oracle/` unless the task touches the AI-retrofit spec directly

For orientation, follow the documentation map near the top of this file. Do not load broad source files such as `packages/db/src/schema.ts` or `packages/ai/src/providers/*.ts` unless the task needs that subsystem.

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

### Employee removal is soft-disable, not hard delete

What changed:
Admin -> Employees exposes Disable/Re-enable controls backed by `employees.disabled_at`.

Why:
Employee rows are referenced by identities, messages, claims/evidence, documents, assignments, review events, and audit history. Hard-deleting a person can break provenance and historical records, while `disabled_at` already blocks login/linking and active RLS helpers.

Future sessions should:
Use `apps/web/app/admin/employees/_components/employee-access-form.tsx` and `updateEmployeeAccess()` for GUI access changes. Do not add hard-delete employee buttons unless you first design archival/reference cleanup across all employee FKs.

### All inference must go through `OracleAIClient`

Looks like:
It would be simpler for routes or workers to call provider SDKs directly.

Actually:
The provider adapters are the only supported inference boundary. They own prompt shaping, provider-native caching, reasoning translation, and usage normalization.

Why:
The project depends on provider-specific caching and structured-output behavior that generic wrappers and ad hoc calls hide.

Do not change because:
Direct SDK calls bypass context-pack logging, cache observability, route fallback, and consistent validation.

### Log the actual AI result route, not only the planned route

Looks like:
The caller already resolved a route before calling `OracleAIClient`, so it can log that route in `model_runs` and `model_run_usage_details`.

Actually:
`ModelRouter` may dispatch to a fallback route. `OracleTextResult` and `OracleObjectResult` carry `routeId`, `provider`, `modelId`, `fellBackFromRouteId`, and `fallbackReason` after dispatch.

Why:
Cost/cache dashboards and fallback debugging need the route that actually ran, while still preserving the original route when fallback happened.

Do not change because:
Logging the pre-dispatch route hides provider fallback and makes cache-hit/cost accounting wrong. New AI callers should use the result metadata when writing usage rows, with the pre-resolved route only as a fallback if metadata is absent.

### Chat retrieval is deterministic, not AI-SDK tool calling

Looks like:
The chat route used to define `search_company_knowledge` and `check_open_gaps` tools, so re-adding `tools` to `providerOptions` might seem like restoring agentic retrieval.

Actually:
The native provider adapters do not execute Vercel AI SDK tool definitions from `providerOptions`. The chat route now performs retrieval deterministically before the model call and injects recent messages, open gaps, approved claims, and Brain snippets into prompt blocks.

Why:
All inference goes through raw provider adapters to preserve provider-native cache/usage fields. Passing AI SDK tools through this boundary looked useful but was decorative unless every native adapter learned tool orchestration.

Do not change because:
Reintroducing AI SDK tools in the chat route can create a false sense that the model is searching live. Add retrieval through `searchWithRetrievalPlan()` and prompt blocks, or implement tool orchestration explicitly inside the native adapter boundary.

### OpenRouter is enrichment-only

Looks like:
`openrouter.ts` and OpenRouter-related code mean inference still runs through OpenRouter.

Actually:
OpenRouter is only used to enrich the admin-side model catalog with pricing/capability metadata.

Why:
Inference requires native provider features and exact usage fields; catalog enrichment does not.

Do not change because:
Reintroducing OpenRouter into the inference path would erase provider-native cache and usage behavior that the rest of the system expects.

### `google/*` model settings are real Gemini API routes, not Vertex aliases

What changed:
`google/*` model IDs now resolve to the `GoogleGeminiAdapter`, while curated `vertex_*` routes continue to use `VertexGeminiAdapter`.

Why:
Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`) returned `NOT_FOUND` through the configured Vertex project/region, but worked through the Gemini API using the deployed service-account OAuth path. The extraction A/B/C eval route `google_gemini_3_1_flash_lite_extraction_eval` depends on this split.

Future sessions should:
Do not map `google/*` back to `vertex` in `packages/ai/src/routes/resolve.ts` unless the exact model has been verified in the configured Vertex region. `GEMINI_API_KEY` is optional; `GoogleGeminiAdapter` can also mint Gemini API OAuth tokens from `GOOGLE_APPLICATION_CREDENTIALS_JSON`.

### Trigger.dev schedule slots are currently full

What changed:
The `extraction-ab-eval` worker is an immediate Trigger.dev task with no cron sweep. A cron fallback was attempted on 2026-06-16, but Trigger.dev deploy failed because the project already had 10/10 schedules.

Why:
Adding another `schedules.task()` currently blocks worker deployment. The A/B eval page queues rows and dispatches `extraction-ab-eval` immediately from Vercel through `TRIGGER_SECRET_KEY`.

Future sessions should:
Do not add new Trigger schedules casually. Reuse/consolidate an existing schedule or increase the Trigger.dev schedule limit before adding another `schedules.task()`. Deploy workers with `corepack pnpm --filter @oracle/workers run deploy`.

### Supabase project cutovers have platform integration surfaces

What changed:
The production Supabase project moved from Ohio (`vokucjpanhvqunimlvsp`, now `oracle.old`) to N. Virginia (`eqccjfbyrywsqkxxpjvg`, `theoracle`) on 2026-06-20.

Why:
A Supabase project cutover is not just `DATABASE_URL` / `DIRECT_URL` / browser key rotation. Vercel, GitHub, Trigger.dev, Supabase Auth providers, Microsoft Entra redirect URIs/client secrets, Supabase.com project integrations, and Recall live-bot envs can all hold project-specific URLs or secrets.

Future sessions should:
Use `docs/deployment.md` "Supabase project cutover checklist" before declaring a cutover done. Vercel's Supabase integration may inject `SUPABASE_*` / `POSTGRES_*` env vars that this app does not read; the runtime still depends on `NEXT_PUBLIC_SUPABASE_*`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`, and `DIRECT_URL`.

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

### Design file operations are not product/design workflow

Looks like:
Design-file naming, server organization, invalid filename characters, Photoshop/Illustrator file bloat, linked assets, packaging, and archive cleanup could live under `creative_design`, `product_development`, or `it_systems` because the design team and design tools are involved.

Actually:
They live in the dedicated top-level domain `design_file_operations`. That domain is for technical creative-file hygiene: keeping design files valid, lightweight, findable, compatible, packaged, versioned, and safe to share. Product/design workflow remains separate: concept intake, design assignment, proofs, approvals, revisions, production handoff, and product lifecycle state belong in `product_development`, `creative_design`, `licensing_approvals`, or `production_lifecycle`.

Why:
The same employees participate in both knowledge bases, but the user intent is different. "How should I name/save/store this file?" should not retrieve product approval/status claims. "Where is this product in design approval?" should not retrieve filename/server-folder rules.

Do not change because:
Collapsing these domains causes retrieval bleed between computer/file-management practices and the business workflow of designs/products moving through the company. Keep `design_file_operations` as its own retrieval target and preserve its negative boundary against product workflow domains.

### Operations systems are not generic IT support

Looks like:
ERP, CRM, PLM, Google Sheets, and integration work could all live under `it_systems`.

Actually:
Business-system data-flow knowledge lives in `operations_systems`. That domain covers ERP/CRM/PLM workflows, field mapping, source-of-truth rules, validation, and integrations such as moving OrderList, MasterData, and TaskList from Google Sheets into Designflow PLM. Generic account access, password resets, permission troubleshooting, and system administration remain in `it_systems`.

Why:
The Oracle needs to guide operational integration decisions, not just answer technical support questions. "How do I log into Designflow?" and "Which MasterData fields become Designflow PLM item fields?" should retrieve different evidence.

Do not change because:
Collapsing `operations_systems` back into generic `it_systems` makes business-process integration knowledge compete with IT support noise and weakens retrieval for ERP/CRM/PLM data migration work.

### Business Process is for cross-functional workflow overviews

Looks like:
`business_process` could become a vague "company process" bucket for anything operational.

Actually:
It is only for end-to-end workflows, operating-model explanations, and handoffs that span multiple departments. A claim can and should carry `business_process` plus narrower domains like `licensing_approvals`, `product_development`, `production_lifecycle`, `customer_ops`, `logistics_shipping`, or `finance_pricing` when those areas are materially involved.

Why:
Broad questions such as "how does the overall company process work?" need to retrieve overview claims without losing department-specific facts.

Do not change because:
Mapping cross-functional extraction output back to `customer_ops` buries companywide workflow knowledge under a single department and makes broad process queries unreliable.

### Training enablement is not people/org ownership or HR records

Looks like:
Training people to do their jobs could live under `people_org` because it involves employees, departments, roles, and onboarding.

Actually:
Job-training knowledge lives in the dedicated top-level domain `training_enablement`. That domain covers onboarding plans, role-specific training checklists, SOP learning paths, work instructions, shadowing, cross-training, skill checks, and refresher training after workflow changes.

Why:
The retrieval intent is different. "Who owns onboarding for the design team?" is an ownership/org question. "What checklist should a new design hire follow to learn proof setup?" is training enablement.

Do not change because:
Collapsing `training_enablement` into `people_org` makes procedural learning material compete with org charts, escalation paths, and ownership facts. Keep sensitive HR/personnel records — compensation, discipline, performance evaluation, and personal conflicts — out of this domain.

### Claim revision is supersede-and-replace, not overwrite

Looks like:
If a pending or approved claim is 80% correct, the admin/reviewer could simply edit `claims.summary` and approve it.

Actually:
Claim revision creates a replacement claim, copies the supporting evidence/domain/entity metadata, marks the original claim `superseded`, links `claim_metadata.superseded_by_claim_id`, and writes an append-only `claim_review_events` row with before/after state and reviewer note. Admins can edit approved claims from `/admin/claims`; that edit creates a replacement claim in `pending_review`, so the replacement must be approved before it becomes active Brain/retrieval knowledge.

Why:
The original row is the AI's first interpretation of the evidence. Keeping it makes review quality auditable and gives future AI comparison tools a clean before/after pair to analyze.

Do not change because:
Overwriting claims in place destroys the evidence of what the model got wrong and weakens the provenance chain that makes Oracle answers explainable.

### Non-admin claim review is direct-assignment only for now

Looks like:
`knowledge_domain_review_departments` means department members should see every claim in their mapped domains.

Actually:
The table remains in the schema as a future routing/authorization map, but the current `/claims` page only shows claims that were directly assigned through a `claim_review_question` gap. The old "My review domains" queue is intentionally hidden, and the server action permission check only allows admins or the employee directly assigned to that claim.

Why:
The team wants explicit review sends, including multi-person and review-group assignment, before reopening broad domain queues.

Do not change because:
Re-enabling domain queues can expose large pending-review surfaces to non-admin employees. If domain review is restored later, update `/claims`, `canReviewClaim()`, and this guide together.

### Claim corrections become prompt lessons, not training or evidence

Looks like:
Reviewer notes and revised claims should make the model "learn" automatically or become Brain evidence.

Actually:
Approved replacement claims feed a semi-stable extraction prompt block through `packages/ai/src/prompts/claim-correction-lessons.ts`. The sync extraction worker, batch-submit worker, and document-ingestion worker include that block in future extraction calls; `/admin/ai/claim-lessons` shows the exact block.

Why:
The project needs an immediate auditable feedback loop from human corrections without pretending to fine-tune the model or treating review commentary as source evidence.

Do not change because:
Reviewer notes are not evidence. Keep correction lessons as prompt guidance only; the candidate-before-claim validators still decide whether new model output can become a claim.

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

### The Drizzle snapshot was baselined at migration 0007 — some tables exist only via hand SQL

Looks like:
`drizzle-kit generate` wants to CREATE tables that already exist in production —
`departments`, `employee_departments`, `provider_batch_jobs`,
`provider_response_sessions` — plus columns like `documents.context`,
`model_runs.dispatch_mode`, `provider_cached_content.provider_metadata_json`.
It looks like a fresh, legitimate migration.

Actually:
Those objects were added to `schema.ts` and materialized via **hand-written
`migrations/sql/*.sql`** files (56–65), but were never captured in a *generated*
Drizzle migration, so the Drizzle snapshot drifted behind `schema.ts`. Migration
`0007` re-syncs the snapshot to the true full schema (so future `generate` runs
are clean), but its **SQL was trimmed by hand** to only the genuinely-new objects
(`claim_translations`, `claims.source_lang`, `employees.locale`). Applying the
un-trimmed generate output would fail on the live DB with `type "department"
already exists`.

Why:
A fresh DB still gets those tables — the hand-written `sql/` files create them in
the migrate runner's step 3 (after generated migrations in step 2). So both paths
work: existing DBs already have them; fresh DBs get them from hand SQL.

Do not change because:
Do NOT "fix" a future `generate` by committing its full output if it re-emits
`departments`/`provider_*`/etc. — trim those statements (they already exist) and
keep only your new objects, exactly as `0007` does. Re-emitting them breaks
`pnpm db:migrate` on every already-migrated database.

### Claim retrieval has exactly one path, and the two SQL branches must stay in lockstep

Looks like:
`searchWithRetrievalPlan()` in `packages/ai/src/retrieval.ts` contains two near-duplicate SQL queries — a hybrid pgvector+tsvector path and a `_searchFallbackTsvector()` path — and a separate `verify:retrieval-filter-parity` script that seems redundant with typecheck.

Actually:
The fallback runs only when `OPENAI_API_KEY` is unset (dev, no embeddings). Both branches build their WHERE clauses from the same private helper `buildPlanMetadataFilters()`, and the parity guard statically asserts every filter the helper returns is interpolated into BOTH branches. `searchApprovedClaims()` (a weaker, plan-less retrieval) was deleted on 2026-05-28 — there is now exactly one endorsed retrieval entry point.

Why:
The recurring regression here was adding a narrowing filter to the hybrid path and forgetting the fallback, making dev-mode retrieval silently weaker (or vice versa). Typecheck can't catch it — the fragments are SQL strings. The guard runs in CI (`pr-check.yml`) and via `pnpm --filter @oracle/ai verify:retrieval-filter-parity`.

Do not change because:
Adding a second retrieval path (or a filter to only one branch) reintroduces the exact silent-divergence class the guard exists to prevent. New narrowing fields go in `buildPlanMetadataFilters()` and get interpolated into both branches — nowhere else.

### Raw-SQL list parameters are bound as JSON strings, not JS arrays

Looks like:
`buildPlanMetadataFilters()` in `packages/ai/src/retrieval.ts` could use the simpler `= ANY(${arr}::text[])` form instead of `IN (SELECT jsonb_array_elements_text(${JSON.stringify(arr)}::jsonb))`.

Actually:
Two driver pitfalls make the obvious forms fail at runtime (found 2026-06-10, the first day a hinted retrieval ran against an approved+embedded claim): a bare JS array in a drizzle ``sql`` template expands to a placeholder list `($1, $2)`, making `ANY((...)::text[])` a syntax error; and binding the array as one param (`sql.param`) relies on postgres-js serialization of unknown-typed params, which is unreliable. Also, a type modifier such as `vector(1536)` cannot be a bind parameter — `EMBEDDING_DIM` is inlined with `sql.raw`. The static verify guards and typecheck cannot catch any of this; it only fails when the query executes.

Do not change because:
Reverting to `ANY(${arr}::text[])` reintroduces a runtime-only failure that stays invisible until real data exercises the filter. New list filters in raw SQL should follow the JSON-string + `jsonb_array_elements_text` / `jsonb_to_recordset` pattern.

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

### The Oracle MCP server is lazy-loaded on purpose — `tools/list` stays at five tools

Looks like:
`apps/web/lib/mcp/capabilities.ts` defines real operations (search claims, list domains, read Brain sections) but none are registered as MCP tools. Only five generic tools appear in `tools/list` (`health`, `list_capabilities`, `tool_search`, `get_capability_details`, `invoke_tool`). It looks like indirection that could be simplified by registering each operation directly as its own MCP tool.

Actually:
This is a deliberate lazy-loaded capability registry. Real operations live in a hidden registry and are reached via `invoke_tool` after discovery through `tool_search` / `get_capability_details`. Keeping `tools/list` tiny means MCP clients that cache the initial list never miss capabilities — we intentionally do **not** rely on `tools/list_changed`. The `verify:mcp` guard (`apps/web/lib/mcp/__verify__/mcp-registry.ts`, wired into the Vercel build gate + `pr-check.yml`) asserts `tools/list` is exactly those five.

Why:
The endpoint is for external AI agents building software for us; the design follows the house lazy-registry standard (same shape as the `devops-mcp` / `synology-monitor` servers). It is read-only and only surfaces approved knowledge (`searchWithRetrievalPlan` filters `status = 'approved'`; Brain tools require `review_status = 'approved'`).

Do not change because:
- Registering capabilities directly as MCP tools reintroduces the exact anti-pattern the design avoids and breaks `verify:mcp` (build fails).
- The live endpoint is `/api/mcp/mcp`. The doubled segment is correct, not a typo: `mcp-handler` requires a `[transport]` route segment and `basePath: '/api/mcp'` derives the Streamable-HTTP endpoint as `<basePath>/mcp`.
- New write (tier-2+) capabilities MUST go through the `invoke_tool` preview/confirm gate; never let a write run without `args.confirmed === true`.
- Full design + "how to add a capability" lives in `apps/web/lib/mcp/README.md` — read it before changing the MCP surface.

### Uploaded images become knowledge via a two-pass vision→text→extract flow

Looks like:
`document-ingestion` could just send an uploaded image straight to a vision model and ask it for claims. Instead it runs a vision model first to produce a text transcription, then runs the normal extraction model over that text.

Actually:
This is deliberate and load-bearing for provenance. Pass 1 (`transcribeImageToText`) renders the image to faithful text (a structured text topology for diagrams — nodes/edges/swimlane headers, verbatim labels kept inside the nodes). Pass 2 is the unchanged chunk → extract → quote-validate → promote pipeline. Every claim's `exactQuote` is validated against a `document_chunk`, and an image has no text to validate against — so the transcription IS the chunk text, and the verbatim-label rule keeps quotes matchable. The transcription is persisted, so the whole thing stays re-runnable and auditable.

Why:
A single-pass "image → claims" call would force bypassing quote validation, breaking the candidate-before-claim provenance guarantee. Keep the two passes separate.

Do not change because:
Inline image input is implemented only in the Vertex adapter (`toVertexParts` → Gemini `inlineData`); the worker formats the part per provider. The vision route is pinned via the auxiliary registry, not the extraction route, so flipping the extraction model to a non-vision provider does not silently break image ingestion.

### Document extraction quotes must stay inside persisted chunks

Looks like:
The extractor could read a whole uploaded document and return any true statement with a quote from anywhere in the document.

Actually:
`document-ingestion` persists `document_chunks`, formats extraction input as labeled chunk blocks, and expects document-derived candidates to use the exact chunk id as `sourceMessageId`. The promotion executor validates every `exactQuote` against one persisted chunk. Existing uploaded rows keep their old chunks until re-uploaded or deliberately reprocessed with chunk recreation.

Why:
Document claims need quote-level provenance that can be re-run and audited. A quote spanning two chunks, even if semantically correct, cannot be promoted because there is no single chunk evidence row that contains it verbatim.

Do not change because:
Letting document extraction use document-level source ids, paraphrased quotes, or cross-chunk quotes breaks the candidate-before-claim evidence contract and can make valid-looking claims impossible to trace.

Large uploads are processed by `buildDocumentChunkWindows()` in bounded extraction windows. There should be no document-level "first N characters only" cap; each window covers whole persisted chunks and produces its own extraction batch/model run. Reintroducing a silent whole-document cap will make long company docs appear to process successfully while losing most of the knowledge.

### Markdown document quotes normalize formatting, not meaning

Looks like:
A Markdown upload should require the model to reproduce every `**`, table pipe, heading marker, and link exactly.

Actually:
Document quote validation uses `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY` for text/markdown uploads. It deterministically strips or normalizes Markdown syntax such as emphasis markers, heading/list prefixes, inline code ticks, links/images to display text, and table separators before matching. It does not rewrite meaning, do fuzzy matching, or allow cross-chunk quotes.

Why:
Business-process docs commonly contain tables and formatted labels. Models often quote the visible text instead of the raw Markdown punctuation, so strict raw matching rejected true claims even when the source chunk contained the visible statement.

Do not change because:
Documents still need deterministic quote-level provenance. If a new format needs looser matching, add an explicit normalization policy for that format rather than enabling transcript-style fuzzy matching on documents.

### Extraction picker intentionally does not require vision

Looks like:
The Extraction stage handles uploaded-image knowledge, so the model picker should require vision.

Actually:
Images are transcribed by the separate auxiliary Image Vision model before Extraction sees them. `claim-extraction` and the extraction pass inside `document-ingestion` call `OracleAIClient.runObject<ExtractionOutput>()` over text blocks and expect structured JSON. The hard picker requirements for Extraction are therefore structured output plus context window, not image input.

Why:
Requiring vision on Extraction filters out strong text/JSON extraction models for a capability the runtime does not use. The provenance-critical image path remains protected by `default_vision_route`.

Do not change because:
Adding `vision` back to `STAGE_REQUIREMENTS.extraction` in `apps/web/lib/stage-requirements.ts` should only happen if a runtime path starts sending raw image parts directly into the extraction route again. Verify with `document-ingestion.ts` first.

### Auxiliary models are a registry, not a 4th pipeline role

Looks like:
The image-vision model selection looks like it should be a 4th `OracleModelRole` next to interview/extraction/synthesis.

Actually:
`OracleModelRole` is intentionally frozen at exactly 3 pipeline stages (each with a strict primary+fallback catalog pair, stage requirements, pools, batch dispatch). Vision and general-purpose are "auxiliary models" — single-pick selections with at most one capability filter and a default route — defined in `AUXILIARY_MODELS` (`packages/ai/src/routes/auxiliary.ts`) and resolved by `resolveAuxiliaryRouteFromSettings`. The settings page, picker, and `/api/admin/models` iterate the registry; none of them special-case `'vision'` or `'general'` by string.

Why:
Auxiliary models have none of a pipeline role's structure, and folding them into `OracleModelRole` would ripple through every `Record<OracleModelRole, …>` map and the strict 1-primary/1-fallback invariant. The registry adds new utility-model selections with zero new branches.

Do not change because:
Adding `'vision'` to `OracleModelRole` to "unify" things reintroduces exactly the ripple the registry avoids. Add a registry entry instead.

### One brain, but claims render per-reader-language; evidence and Brain never translate

Looks like:
`claim_translations` plus locale-aware retrieval looks like it could fragment into a separate Chinese knowledge graph, or like the whole claim (including its evidence quote) gets translated for China readers.

Actually:
There is exactly ONE knowledge graph. A claim stays canonical in `claims.source_lang` with its verbatim `claim_evidence.exactQuote` intact; `claim_translations` holds display-only summary renderings per language. `searchWithRetrievalPlan(db, plan, locale)` renders `COALESCE(translation, canonical)` for the reader's locale (and `'simple'` tsvector config for `zh-CN`, since Postgres can't tokenize spaceless Chinese). Three deliberate boundaries: (1) **evidence quotes are never translated** — they must stay byte-for-byte for the quote validator; (2) **Brain synthesis is English-only** — `getBrainSectionSnippets` has no locale path; (3) **translation is opt-in per claim** (admin selects claims to send to the China team) and **claim-review questions (`claim_review_question`) are translated per-recipient** so a question is translated to Chinese only when a recipient is a `zh-CN` employee (the verify path reuses main's review-question + review-groups mechanism, not a separate recertification worker).

Why:
Translating evidence would break verbatim provenance; auto-translating every claim or the Brain would burn tokens on knowledge no China employee needs. Per-recipient/opt-in keeps cost proportional to what's actually directed to China while keeping one shared brain. See `china_imp.md`.

Do not change because:
Feeding a translated quote into validation, or adding a locale branch to `getBrainSectionSnippets`, or auto-translating on approval, each reverses a deliberate decision. The locale-rendering SQL fragments live in `buildPlanMetadataFilters()` precisely so the parity guard forces both retrieval branches to stay in lockstep — add new locale logic there, not in one branch.

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
| `OPENAI_ORG_ID` | Optional OpenAI organization passed to the OpenAI SDK | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `GOOGLE_CLOUD_PROJECT` | Vertex adapter project | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `GOOGLE_CLOUD_LOCATION` | Vertex region | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | service-account JSON content for Vertex ADC bootstrapping | Vercel/Trigger.dev secret, optional local | no | yes |
| `GEMINI_API_KEY` | Optional direct Gemini API key for `google/*` routes; `GoogleGeminiAdapter` falls back to `GOOGLE_APPLICATION_CREDENTIALS_JSON` OAuth when unset | `.env.local`, Vercel/Trigger.dev secret if used | no | no |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` | temp GCS bucket for oversized file-backed Vertex caches | env/secret | optional | recommended |
| `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_PREFIX` | temp GCS prefix for those uploads | env/secret | optional | optional |
| `GOOGLE_VERTEX_BATCH_GCS_BUCKET` | GCS bucket for Vertex Batch Prediction JSONL I/O (D14) | env/secret | optional | required if batch mode + Vertex |
| `GOOGLE_VERTEX_BATCH_GCS_PREFIX` | Object prefix inside the batch bucket | env/secret | optional | optional |
| `DEEPSEEK_API_KEY` | DeepSeek adapter | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `DASHSCOPE_API_KEY` | Qwen adapter | `.env.local`, Vercel, Trigger.dev | optional | optional |
| `OPENROUTER_API_KEY` | model catalog enrichment only | `.env.local`, Vercel if desired | optional | optional |
| `ORACLE_MCP_TOKEN` | Static bearer token for the remote MCP knowledge endpoint (`/api/mcp/mcp`). External AI agents present it to query approved business knowledge. If unset, the endpoint rejects all requests. | `.env.local`, Vercel | optional | yes for MCP access |
| `TRIGGER_SECRET_KEY` | Trigger.dev auth | `.env.local`, Vercel, Trigger.dev | yes | yes |
| `PROD_DIRECT_URL` | Used by the CI drift-check step to reach production Postgres | GitHub Actions repo secret (`gh secret list`) | no | yes (CI) |
| `TRIGGER_PROJECT_REF` | Trigger.dev project selector | `.env.local`, Vercel | optional | optional |
| `ORACLE_RUN_VECTOR_INDEXES` | Opt-in switch for expensive `99_vector_indexes.sql` migration step | shell/env when intentionally running vector index creation | optional | optional |
| `NEXT_PUBLIC_GIT_SHA` | Build metadata injected by `apps/web/next.config.ts` for admin display | generated at build time | no | no |
| `NEXT_PUBLIC_GIT_TIMESTAMP` | Build timestamp injected by `apps/web/next.config.ts` for admin display | generated at build time | no | no |
| `NODE_ENV`, `VERCEL`, `VERCEL_ENV` | Runtime/build environment metadata used by frameworks/tooling and Turbo cache keys | platform/tooling | no | yes |
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
2. GitHub Actions runs `pr-check.yml`: installs dependencies, builds `@oracle/web`, runs the static DB-free verify guards (`verify:retrieval-filter-parity`, `verify:vertex-file-cache`, `verify:mcp`), then runs `pnpm db:check-drift` against production (requires the `PROD_DIRECT_URL` repo secret; skips gracefully if absent). Drift in the Drizzle migration journal fails the build.
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
- **The deploy gate is native to Vercel's build.** `vercel.json` `buildCommand` runs the static verify guards (`verify:retrieval-filter-parity`, `verify:vertex-file-cache`, `verify:mcp`) **before** `@oracle/web build`. If a guard or the build fails, Vercel's production build fails and the previous deployment stays live — so a guard-breaking or build-breaking commit cannot reach production. This is the "hard blocker": enforcement lives in the platform's own build, not in a separate CI deploy step.
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
Made the rollback symmetric and timing-aware. The submit task now tracks `stagedBatchIds`, `stagedContextPackIds`, `providerAccepted` (flipped the instant `adapter.submitBatch` returns), and `providerBatchJobInserted` (flipped after the durable `provider_batch_jobs` row exists). On failure:
- `providerAccepted === false` (no live provider state): revert messages + DELETE both staging tables, scoped to ids this run created. Drain finds nothing because nothing existed.
- `providerAccepted === true` but `providerBatchJobInserted === false`: the provider accepted work, but Oracle has no durable job row for the drain task to poll. Abandon that upstream batch, reset local messages/staging for a clean tracked retry, and log the provider batch id for operator awareness.
- `providerBatchJobInserted === true`: leave messages/staging in place. The provider batch is durably tracked, and the drain task can recover by polling `provider_batch_jobs`.

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

### 2026-06-09 Entra secret rotation broke Supabase Microsoft login

What happened:
While wiring the Teams-native Azure Bot, `az ad app credential reset` was run without `--append` against the shared Entra app `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`. That removed existing client secrets, including the Supabase Azure provider secret and the Graph backend secret. Microsoft sign-in then redirected to `/auth/callback?error=server_error&error_code=unexpected_failure...`; Oracle showed `/denied?reason=no_code`.

Impact:
Microsoft SSO was temporarily broken. Graph-backed directory/transcript paths also needed fresh secrets in Vercel and Trigger.dev before they could safely run.

Root cause:
The same Entra app carries three separate client-secret consumers: Supabase Auth Azure provider, app-only Microsoft Graph backend, and Bot Framework authentication. Rotating one without `--append` invalidated the others.

Recovery:
Created fresh appended Entra secrets. Updated Supabase Auth's Azure provider client secret manually in the Supabase dashboard, updated Vercel `AZURE_GRAPH_CLIENT_SECRET` / `MICROSOFT_BOT_*`, updated Trigger.dev prod `AZURE_GRAPH_CLIENT_SECRET` via `POST https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod/import`, and redeployed Vercel production. Supabase Azure provider URL was corrected to `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971` (no `/v2.0`; Supabase appends `/oauth2/v2.0/authorize`).

Rule added to prevent recurrence:
When creating or rotating a client secret on the shared Entra app, use `az ad app credential reset --append --display-name <purpose> ...` unless intentionally replacing every consumer. Keep separate display names for `supabase-prod-*`, `oracle-graph-*`, and `oracle-teams-bot-*`. Never put `/v2.0` in the Supabase Azure provider URL.

## 14. Pending work

| Status | Item | Owner/next action |
|---|---|---|
| open | `apps/web/app/admin/taxonomy/_actions.ts` approves some proposal types by queueing reclassification work rather than applying it inline. | Keep the actions as-is until the reclassification path is expanded further. |
| open | Only `.github/workflows/pr-check.yml` exists (build + two verify guards + Drizzle drift check). There is no automated DB migration workflow and no automated Trigger.dev deploy workflow. | Keep manual `pnpm db:migrate` and `pnpm --filter @oracle/workers run deploy` (note: `run` keyword required — `pnpm` reserves the bare `deploy` form for its own subcommand) in the release process until workflows are added. |
| resolved | `RetrievalPlan.requiredEntities` semantics: **disjunctive (any-of) — decided 2026-05-28, keep as-is.** A claim matches if it carries ANY of the listed entities. Conjunctive (all-of) was rejected because it would require a single claim to mention every listed entity, collapsing recall for multi-entity queries (claims are typically single-entity). Filter lives in `buildPlanMetadataFilters()` in `packages/ai/src/retrieval.ts`. | No action. If a future "facts connecting X and Y" feature is ever wanted, add it as a separate explicit mode — do not flip the default. |
| done | China bilingual claim layer (schema, locale-aware retrieval, `claim-translation` worker, translate-for-China bulk action, per-`zh-CN`-recipient translation of `claim_review_question`s) is **merged to `main`**, migration `0007` is **applied to prod**, and `claim-translation` is deployed in Trigger.dev worker `20260620.1`. | Set a China employee's `locale='zh-CN'` and pick a translation model at Admin → Settings → "Translation model" when the owner wants to use it. |
| open | China bilingual follow-ups discussed but not built: backfill of existing approved claims (moot — translation is opt-in), and admin side-by-side translation review. | Build on request. |
| open | `RetrievalPlan.requiredEntities` is declared and enforced (any-of) but **no production code populates it**. `buildRetrievalPlanFromQuery()` is a keyword matcher that routes to broad domains; it does not do named-entity recognition + registry resolution to pin specific entities. This is a deferred feature, not a bug — the field is the socket a future model-backed plan builder (`buildRetrievalPlanWithModel`, noted in `retrieval-plan.ts` header) would fill. | Build entity recognition + resolution into plan construction when per-query latency budget allows the extra structured-output call. Until then the field stays empty and inert. |
| open | Authentik is mentioned in schema/docs but no Authentik login flow is wired in the app. | Treat Authentik as not implemented. |
| open | Oversized Vertex file-backed caches require `GOOGLE_VERTEX_CONTEXT_CACHE_GCS_BUCKET` in the runtime env. Without it, the adapter falls back to text-prefix caching only. Used by both the extraction worker and (since the chat-attachment file-cache v1) the interview chat route for large attached PDFs. | Provision the bucket/env in environments that need large-document cache optimization. |
| open | Chat-attachment file-cache (v1) limitations: (1) only ONE PDF per turn is cached; other attachments are not separately inlined while the file cache is active; (2) a cross-provider fallback (Vertex→Anthropic on a transient error) loses the cached document — degraded answer, not an error, logged as a warning. | Acceptable for v1. Hardening = fix Vertex multimodal `buildContents` then keep the attachment inline + dedupe the cached copy in the adapter, and/or constrain a Vertex interview route's fallback to also be Vertex. |
| partial | Vertex `buildContents` now translates inline image message parts (`{type:'image',mimeType,data}`) into Gemini `inlineData` via `toVertexParts` (2026-06-14, guard `verify:vertex-inline-image`). Used by `document-ingestion`'s image vision pass. **`fileData`** parts (e.g. caching a PDF alongside other inline attachments in the interview chat route) are still not generalized. | Done for inline images. For chat attachments, extend `toVertexParts` to also emit `fileData` parts and dedupe against the file-backed cache. |
| open | Vertex Batch Prediction requires `GOOGLE_VERTEX_BATCH_GCS_BUCKET` to be provisioned + the worker SA granted `roles/storage.objectAdmin` on it. | One-time admin task before batch mode can be enabled for Vertex routes. OpenAI batch needs no infrastructure setup. Flip extraction to batch via `/admin/settings` → "Extraction dispatch mode" card. |
| done | **Teams transcript ingestion — LIVE + validated end-to-end (2026-06-04/05).** Real Meet-Now call → subscription → webhook → ingestion → 95 messages, `speakersResolved 2/2`. Workers `20260605.1`. Speaker resolution now email-based (`fbb82cd`) + bootstrap-by-email for `@popcre.com` (`e73868b`); 38 employees seeded. | No action — feature works. Fuzzy quote matching (`89d2fd9`) + raw_transcripts persistence added. |
| done | **Teams-native Oracle app wrapper is wired (2026-06-09).** Azure Bot resource `theoracle-popcre-teams-bot` (`F0`) points at `/api/teams/bot/messages`, Teams channel is enabled, the organization Teams app `The Oracle` is uploaded, and Albert's user has the app installed. | No repo action. If users cannot see the app, check Teams app propagation/policies and `Get-M365TeamsApp -Id 17ccd7a1-b90b-428c-9966-33e7fb832923`. |
| open | **Extraction gates hold most claims on a fresh system** (not a bug): entity registry is empty → new entities (people, systems, RFQ…) are unresolved → claim **held** + entity queued as `entity_proposals`; `domain_valid` fails when proposed domains don't map to active top-domains; impact≥7 claims → `pending_review`. | Seed the entity registry + active `knowledge_top_domains` to let claims flow. Touches the review/safety model — get owner sign-off before loosening. See HANDOFF.md. |
| open | **Synthesis never demonstrated** — needs ≥1 approved claim; 4 sit in `pending_review`. | Approve a claim (SQL or admin) → trigger `brain-synthesis` → confirm Brain narrative. |
| done | **Recall.ai live Teams bot path — LIVE + validated end-to-end (2026-06-08/09).** Admin start path, Recall bot join, ElevenLabs/AssemblyAI streaming, signed `/api/teams/live/recall` webhook, Trigger worker, message persistence, Recall `send_chat_message`, and visible Teams chat post were all verified. Current deployed worker version after cleanup: `20260609.6` with 17 tasks. | No action for mechanical live path. Safety/test settings are clamped off after testing (`max_oracle_interjections_per_hour=0`, `teams_live_recall_min_confidence_to_post=101`, force flags false). See `HANDOFF.md` for bot IDs, verification evidence, and the next open item: retrieval-backed live context. |
| deferred | **Secret rotation.** Earlier sessions exposed several credentials in chat. The user explicitly deferred rotation until the system is up and running. | Do not treat rotation as the first blocker for current live testing. When the owner is ready, rotate Recall API/webhook secrets, any exposed Vercel token, and any Google service-account JSON that appeared in tool output. Azure Graph/Bot/Supabase Entra client secrets were refreshed on 2026-06-09; keep them distinct by display name and use `--append` for future rotations. Never write secret values into docs. |
| done | **Live Oracle has retrieval-backed context.** The Recall path now retrieves approved claims plus linked Brain snippets with `searchWithRetrievalPlan()` before the live decision, stores the context pack/model run linkage, and records `retrievedClaimIds` / validated `evidenceClaimIds` in job/interjection metadata. | Keep the bot as a clarification asker, not a meeting-answering assistant. Retrieval failures must degrade to the no-context prompt and must not block utterance persistence. See `HANDOFF.md`. |
| done | **Repository documentation audit from pasted charter.** User supplied a comprehensive Markdown-maintenance spec on 2026-06-09. | Completed in the docs commit from this session: verified canonical docs against repo state, kept `AGENTS.md` canonical, kept `CLAUDE.md` Claude-only, aligned ignore files, and updated `HANDOFF.md` status. |
| done | `pnpm lint` migration surfaced pre-existing `apps/web` violations the broken script had masked; the 2026-06-11 cleanup fixed the taxonomy quote escaping, initial state-sync effects, stale `eslint-disable` directives, and PostCSS config warning. | No action. `pnpm lint`, `pnpm typecheck`, and `pnpm build` pass locally as of the cleanup session. |

| done | **Remote MCP knowledge endpoint LIVE + verified (2026-06-14)** — `/api/mcp/mcp` (lazy registry: `search_business_knowledge`, `list_knowledge_domains`, `list/get_brain_section`). `ORACLE_MCP_TOKEN` is set in Vercel Production (encrypted, via `vercel env add`) and the endpoint was verified end-to-end against prod: 401 without the token; with it, `initialize` + `tools/list` (the 5 always-on tools) + `invoke_tool list_knowledge_domains` (14 domains). The token value also lives in the gitignored root `.env.local` — retrieve via `vercel env pull` or read `.env.local`. | No action for the mechanical endpoint. Caveat: `search_business_knowledge` only returns substance once claims are **approved** — most still sit in `pending_review` (see the extraction-gates row above); `list_knowledge_domains` already returns all 14 domains. If the token is rotated, set it in Vercel Production and **redeploy** (env vars apply to new deployments only). |
| done | **Word (.docx) + image (vision) document ingestion (2026-06-14).** `mammoth` for `.docx`; PNG/JPEG/WebP/HEIC images run a two-pass vision→text→extract flow with structured text-topology transcription. Provider-agnostic image input (Gemini inlineData / Anthropic / OpenAI). Worker `20260614.3`. | No action. Live image upload→`complete`→claims test still pending a human. GIF/BMP/TIFF unsupported; `.doc` (binary) unsupported. |
| done | **GUI-configurable vision model via the auxiliary-model registry (2026-06-14).** `default_vision_route` chosen at Admin → Settings → "Image vision model"; `OracleModelRole` stays at 3. Seeded to the Gemini route in prod. | No action. To add another auxiliary model: one `AUXILIARY_MODELS` entry + one `AUX_PRESENTATION` entry. |
| done | **Admin company-document uploader, no channel (2026-06-14).** `POST /api/admin/documents` on Admin → Documents. Decouples company-doc upload from chat (no create-channel UI exists). | No action. |
| open | **Per-document `context` / `domain_hints` added via hand-written SQL only (2026-06-14, migration `65`).** Columns are in `schema.ts` + applied to prod, but there is no Drizzle-generated migration, so `pnpm db:check-drift` may flag them and a fresh-DB `pnpm db:migrate` won't recreate them. | If drift matters, fold the two nullable columns into a generated Drizzle migration; otherwise keep the hand-written `sql/65` as authoritative (consistent with the `raw_transcripts` precedent). |

If work is incomplete in a future session, create `HANDOFF.md` at the repo root and delete it once the work is finished.
<!-- ansible-host-policy: managed rollout from u2giants/ansible -->
## Host / server changes — do NOT make them here

The `hetz` server's host/OS layer is managed by **Ansible** in **[`u2giants/ansible`](https://github.com/u2giants/ansible)**.
To change the server (packages, users, firewall, DNS, Docker *engine* config, system cron,
systemd units, Cloudflare Tunnel 1, the backup watchdog), **open a PR there** and let CI apply
it — **never** SSH into the box and hand-edit it. Manual changes are drift and get reverted by
the next apply. See [`u2giants/ansible/AGENTS.md`](https://github.com/u2giants/ansible/blob/main/AGENTS.md).

This repo is **not** the host layer. Its own changes belong here and deploy through their normal
pipeline (e.g. Coolify). Don't put host-level changes here, and don't manage this service's
container with Ansible. Scope boundary: **Ansible owns the host; Coolify owns the apps.**