# HANDOFF — The Oracle

Live in-flight state for the next contributor or AI coding session.

**Snapshot date:** 2026-05-27 (end of third session)
**Repo:** https://github.com/u2giants/theoracle
**Live URL:** https://oracle.designflow.app
**Production SHA:** `1d91cd5` (last known READY Vercel deploy)
**Current state:** Admin model-pool overhaul complete. Model catalog now sources from 3 direct provider APIs (Anthropic, OpenAI, Google Gemini) for the model list, with OpenRouter used for pricing + capability enrichment only. Per-stage pools, version badge in the admin header, and a fourth "General-purpose" model picker are live. Vertex/Anthropic/OpenAI all wired through Vercel with full credentials. Session 3 (same date) added multi-department support for employees and a soft department-hint RRF bonus in retrieval. Not yet deployed — `pnpm db:migrate` needed.

---

## TL;DR — what shipped (all sessions, chronological)

| Order | Commit | What | Why |
|---|---|---|---|
| 1 | `3cad3a1` | Bulk: clustering body, taxonomy-reclassification worker, entity fuzzy-dedup, batch-approve UX, typing_indicators table, RetrievalPlan precomputedVector + DOMAIN_KEYWORDS | Closed pre-existing deferred work from prior session |
| 2 | `07aacba` | Build-version badge in admin top bar (SHA + NYC timestamp) | User couldn't tell which build was live |
| 3 | `97438c5` | `/api/chat` — lazy-init OracleAIClient | Every Vercel deploy since `bfc0821` had been ERROR for ~12h because the chat route's module-level `new OracleAIClient({...})` singleton threw at build time when env vars weren't present in the "Collect page data" phase |
| 4 | `fe201e2` | Per-stage model pool (Interview / Extraction / Synthesis) — table UI with 3 checkbox columns, three settings keys (`model_pool_interview` / `_extraction` / `_synthesis`), per-stage filtering in `/api/admin/models` | Original `model_pool` was global; user wanted per-stage curation |
| 5 | `7e1466c` | Dropped `reasoning` cap from Synthesis picker (BAD FIX) | Synthesis dropdown was empty; the wrong reaction was to weaken the requirement |
| 6 | `0e4437b` | Reverted bad fix; extracted MODEL_META to `apps/web/lib/model-metadata.ts`; empty-pool fallback returns ALL hardcoded known models (still bad — hand-typed caps) | User pointed out the system should never make its own determinations |
| 7 | `0e96b15` | Marked Claude 3.7+/4-series and Gemini 2.x as reasoning-capable in catalog + MODEL_META | Correction to Claude/Sonnet's outdated knowledge — but still hand-typed |
| 8 | `e9abe5b` | Replaced hardcoded MODEL_META with a discovery service: Anthropic /v1/models parsed live, OpenAI + Vertex classified by Gemini 2.5 Flash-Lite (FOUNDATION — superseded) | Eliminate hand-typed capability data; first attempt routed through an AI classifier |
| 9 | `65f250e` | **Prior state.** Single source: openrouter.ai/api/v1/models. Persisted to new `model_capabilities` Postgres table. Admin "Refresh from OpenRouter" button. Fourth `/admin/settings` card: "General-purpose model" picker drawing from the full catalog | OpenRouter exposes capability flags AND pricing AND context windows for every provider in one free public endpoint. No AI classification, no per-page-load cost, persists across server restarts |
| 10 | `1d91cd5` | Model catalog: direct provider APIs for model list; OpenRouter enrichment-only | Model list now sources from Anthropic /v1/models, OpenAI /v1/models, Google generativelanguage.googleapis.com/v1beta/models. OpenRouter /v1/models fetched in parallel for pricing + capability enrichment only. ModelCapabilitySource type: 'anthropic_api' \| 'openai_api' \| 'google_api'. Non-fatal per-source errors surfaced in POST /api/admin/model-catalog response. |
| 11 | _(uncommitted)_ | Employee multi-department + retrieval soft hint | `employees.departments text[]` (multi-value, authoritative). `employees.department varchar` kept nullable/deprecated. `RetrievalPlan.departmentHints` threads employee departments into `searchWithRetrievalPlan` as a +0.002 RRF score bonus on matching `claim_metadata.department`. Drizzle migration `0006_magical_revanche.sql` + hand-written `56_employees_departments_array.sql`. Admin `/admin` employees tab now shows multi-department and has an "Add employee" form. |

Vercel deploys: 9 successful (5 of those were the iterative model-pool/discovery work). 1 ERROR fixed in commit 3.

### Vercel env vars added this session (via REST API in this session)

| Variable | Value source | Targets |
|---|---|---|
| `ANTHROPIC_API_KEY` | Copied from local `.env.local` | production, preview, development |
| `OPENAI_API_KEY` | Copied from local `.env.local` | production, preview, development |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | New SA key for `oracle-trigger-worker@vertex-ai-497120` (created and uploaded in this session via `gcloud iam service-accounts keys create`; local copy deleted) | production, preview, development |
| `GOOGLE_CLOUD_PROJECT` | `vertex-ai-497120` | production, preview, development |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | production, preview, development |

The Vercel project also still has a stale `OPENROUTER_API_KEY` env var. The user said leave it; nothing reads it from production code anymore (we use OpenRouter's public catalog endpoint without auth).

### Supabase migration applied this session

`packages/db/migrations/sql/54_model_capabilities.sql` — applied to live DB via Supabase MCP (`apply_migration`) before commit `65f250e`. The migration file is in the repo for reproducibility from a fresh checkout.

### Files added / changed this session (high level)

**New files:**
- `apps/web/app/admin/taxonomy/proposals/_components/proposal-list-bulk.tsx` — batch-approve UX
- `apps/workers/src/trigger/taxonomy-reclassification.ts` — 11th Trigger.dev task
- `packages/db/migrations/sql/52_typing_indicators.sql`
- `packages/db/migrations/sql/53_entity_proposals_dedup.sql`
- `packages/db/migrations/sql/54_model_capabilities.sql`
- `packages/oracle-engines/src/extraction/stage-entity-proposal.ts`
- `packages/ai/src/model-capabilities/{types,index}.ts` + `sources/openrouter.ts`

**Removed files:**
- `apps/web/lib/model-metadata.ts` (the hardcoded MODEL_META; replaced by live OpenRouter catalog)
- `packages/ai/src/model-capabilities/sources/{anthropic,openai,vertex}.ts` (the Gemini-classifier-based sources; replaced by OpenRouter)
- `packages/ai/src/model-capabilities/cache.ts` (in-memory cache; replaced by DB persistence)

**Notable edits:**
- `apps/web/next.config.ts` — git SHA + commit timestamp baked in as `NEXT_PUBLIC_GIT_SHA` / `NEXT_PUBLIC_GIT_TIMESTAMP`
- `apps/web/app/admin/layout.tsx` — top-right version badge
- `apps/web/app/admin/settings/{page.tsx,_components/model-picker.tsx,model-pool/page.tsx,model-pool/_components/model-pool-editor.tsx}` — 4-stage settings page (Interview / Extraction / Synthesis / General-purpose), per-stage pool table, refresh-from-OpenRouter button
- `apps/web/app/api/admin/{model-catalog,models}/route.ts` — completely rewritten around `loadModelCatalog`/`refreshModelCatalog`
- `apps/web/app/api/chat/route.ts` — lazy `getOracleClient()` helper
- `apps/web/app/admin/taxonomy/_actions.ts` + `proposals/page.tsx` — bulk approve/reject server actions
- `apps/workers/src/trigger/{claim-extraction,document-ingestion,contradiction-watcher,lull-interjection,taxonomy-reevaluation}.ts` — entity proposal staging now uses pg_trgm dedup; reclassification handles approved proposals; clustering uses k-means
- `packages/ai/src/{index.ts,routes/defaults.ts,client/types.ts,routes/catalog.ts}` — `MODEL_POOL_SETTING_KEYS`, `GENERAL_PURPOSE_ROUTE_SETTING_KEY`, new exports
- `packages/db/src/schema.ts` — `typingIndicators` + `modelCapabilities` tables, `proposalCount` column on `entityProposals`

---

## Pre-production security reminders (CARRIED OVER)

The session that landed R-providers and the wet-test required pasting API keys into chat for dev convenience. The keys live in `.env.local` (gitignored) AND in Vercel project env (uploaded via REST API this session). Before the app ships to real users:

- **Rotate `ANTHROPIC_API_KEY`** at https://console.anthropic.com/settings/keys — paste the new value into `.env.local` AND upload to Vercel (Settings → Environment Variables, or `POST /v10/projects/{id}/env` with `upsert=true`).
- **Rotate `OPENAI_API_KEY`** at https://platform.openai.com/api-keys — same dual-update.
- **Rotate the Vercel service account key** for `oracle-trigger-worker@vertex-ai-497120` (the one this session created — there's a comment trail in the gcloud audit log). Generate a new key via `gcloud iam service-accounts keys create … --iam-account=oracle-trigger-worker@vertex-ai-497120.iam.gserviceaccount.com`, upload the JSON content as `GOOGLE_APPLICATION_CREDENTIALS_JSON` in Vercel, then revoke the old key (`gcloud iam service-accounts keys delete <KEY_ID> --iam-account=…`).
- The stale `OPENROUTER_API_KEY` in Vercel env is harmless (no code path reads it) but can be deleted for tidiness.

---

## Read this in order

1. `HANDOFF.md` — this file.
2. `AGENTS.md` — developer guide and repo conventions.
3. `CLAUDE.md` — Claude Code-specific notes (short; points to AGENTS).
4. `oracle_master_spec.md` — product/business contract.
5. `DECISIONS.md` — assumptions and historical decisions (D6 + D9 explain why no Vercel AI SDK, no OpenRouter in the AI path; OpenRouter's `/v1/models` is used ONLY as a public catalog source, never for inference).
6. `docs/architecture.md` for code structure, `docs/configuration.md` for env vars, `docs/deployment.md` for Vercel + Trigger.dev workflow.
7. `docs/oracle/00-buildout-index.md` — index for the AI retrofit spec docs.

---

## Architecture state — current truth

### AI inference path (production)

```
employee message
   ↓
/api/chat (Vercel, lazy OracleAIClient)
   ↓
OracleAIClient
   → compile() → OraclePromptPlan (stable blocks, dynamic blocks, output contract)
   → router resolves settings.default_interview_route to an OracleModelRoute
   → routeId may be either a curated catalog routeId (e.g. anthropic_claude_haiku_4_5_interview_primary)
     OR a "provider/modelId" string (e.g. "anthropic/claude-opus-4-7") — resolveModelRoute() handles both
   → direct provider adapter (AnthropicAdapter | VertexGeminiAdapter | OpenAIAdapter)
   → raw provider SDK (@anthropic-ai/sdk | @google/genai | openai)
   → observability rows in oracle_context_packs + model_runs + model_run_usage_details
```

No Vercel AI SDK in this path. No OpenRouter in this path. (OpenRouter is used ONLY for the admin-side model catalog metadata, never for inference.)

### Background workers (Trigger.dev v3, 11 tasks)

| Task | File | Schedule | Purpose |
|---|---|---|---|
| `claim-extraction` | `apps/workers/src/trigger/claim-extraction.ts` | Cron every 4h + message-channel triggered | Run Gemini Flash extraction over recent unprocessed messages, stage entity proposals via pg_trgm dedup, write candidates |
| `document-ingestion` | `apps/workers/src/trigger/document-ingestion.ts` | On document upload | Chunk, embed, extract claims from doc chunks |
| `brain-synthesis` | `apps/workers/src/trigger/brain-synthesis.ts` | Weekly cron + admin-triggered | Synthesize brain sections from approved claims; validate diff |
| `contradiction-watcher` | `apps/workers/src/trigger/contradiction-watcher.ts` | Cron every 30 min + on-promotion | Detect contradictions between approved claims; on high-confidence live → post chat interjection |
| `lull-interjection` | `apps/workers/src/trigger/lull-interjection.ts` | Cron every 1 min | When a channel has gone quiet and a relevant open gap exists, draft + post a warm chat question |
| `taxonomy-reevaluation` | `apps/workers/src/trigger/taxonomy-reevaluation.ts` | Cron every 6h | Per top-domain: k-means cluster claim embeddings, name clusters via Gemini Flash, write `create_sub_topic` proposals when novel |
| `taxonomy-reclassification` | `apps/workers/src/trigger/taxonomy-reclassification.ts` | Cron every 15 min | Find approved taxonomy proposals with `approve_pending_reclassification_*` change-log row but no `reclassification_applied_*`; apply the mutation (create_sub_topic, reassign_claims, merge_sub_topics, retire_sub_topic, merge_top_domains) and write the applied sentinel row |
| _(other infra tasks)_ | — | — | — |

Production Trigger.dev project ref: `proj_wgpzsvhmsopqhvwqaycn`. **Trigger.dev deploy was last done at version `20260527.1` with 11 tasks (prior to this session's commits 3-9).** The new code added in 3cad3a1 is included, but the chat-route lazy-init, per-stage pools, and OpenRouter discovery service are web-app only — they don't affect Trigger.dev workers. No Trigger.dev redeploy is needed for this session's work.

### Model catalog (NEW this session)

- **Source:** Anthropic /v1/models, OpenAI /v1/models, Google generativelanguage.googleapis.com/v1beta/models (direct provider APIs) — model list. openrouter.ai/api/v1/models — enrichment (pricing + capability flags).
- **Storage:** `model_capabilities` Postgres table (migration `54_model_capabilities.sql`)
- **Refresh:** Admin clicks "Refresh catalog" on `/admin/settings/model-pool`. Fetches all 3 provider APIs + OpenRouter in parallel; non-fatal per-source errors returned in response. No automatic refresh; no expiry.
- **Read path:** `/api/admin/model-catalog` (GET) → returns persisted rows. `/api/admin/models?stage=<stage>` → filters by per-stage pool from `settings.model_pool_<stage>`, or returns full catalog if pool is empty.
- **Write path:** `/api/admin/model-catalog` (POST) → calls `refreshModelCatalog(db)` which fetches all 3 provider APIs + OpenRouter enrichment and upserts every row by id.

### Stage routes & general-purpose model

| Setting key | Used by | UI card |
|---|---|---|
| `default_interview_route` | `/api/chat`, lull-interjection, contradiction-watcher (interjection draft) | Interview |
| `default_extraction_route` | claim-extraction, document-ingestion, contradiction-watcher (adjudication) | Extraction |
| `default_synthesis_route` | brain-synthesis | Synthesis |
| `default_general_purpose_route` | (reserved for taxonomy cluster naming + future classifier fallbacks; not yet wired into workers) | General-purpose |
| `model_pool_interview` / `_extraction` / `_synthesis` | `/api/admin/models` filters per-stage dropdown candidates | (controlled from `/admin/settings/model-pool`) |

Workers use `resolveModelRoute(settingValue, role)` to translate either a curated catalog routeId or a `provider/modelId` string into an `OracleModelRoute` object. If the settings value isn't recognised, the worker logs a warning and falls back to the hardcoded `FALLBACK_ROUTE_ID` for that role.

---

## What's done in session 3 (on `main`, NOT yet deployed — `pnpm db:migrate` pending)

- [x] `employees.departments text[]` column — schema, Drizzle migration `0006_magical_revanche.sql`, data migration `56_employees_departments_array.sql`
- [x] `employees.department varchar` made nullable/deprecated (backward compat only)
- [x] `RetrievalPlan.departmentHints?: string[]` — new soft signal, threaded through `buildRetrievalPlanFromQuery`
- [x] `searchWithRetrievalPlan` — department RRF bonus (+0.002 to claims whose `claim_metadata.department` ∈ `departmentHints`). Never filters; only nudges.
- [x] `getRelevantOpenGaps` — updated to use `departments` array (with fallback to legacy `department`)
- [x] `getOpenGapsForChannel` — updated to flatMap all participant departments
- [x] `/api/chat` — passes employee `departments` as `departmentHints` to retrieval plan
- [x] Admin `/admin` employees page — `AddEmployeeForm` card + updated table showing multi-department
- [x] `apps/web/app/admin/_actions.ts` — `addEmployee` server action (comma-separated departments → `text[]`)
- [x] `apps/web/app/admin/_components/add-employee-form.tsx` — client form component
- [x] Seed updated — both `ADMIN_EMPLOYEE` and `TEST_EMPLOYEE` now include `departments` array
- [x] `packages/ai/src/index.ts` — removed stale `getDomainHintsForDepartment` / `DEPARTMENT_DOMAIN_HINTS` exports (those were the first wrong implementation, reverted before commit)
- [x] `pnpm -r typecheck` — clean across all 7 packages + web + workers

**To deploy:** run `pnpm db:migrate` to apply migration 0006 + SQL file 56. Then push / let Vercel auto-deploy.

---

## What's done in session 2 (already on `main`, already deployed)

- [x] R10.5 clustering body (k-means with cosine distance, k-means++ init) — `taxonomy-reevaluation`
- [x] `taxonomy-reclassification` Trigger.dev task (idempotent via change-log sentinel rows)
- [x] Entity-proposal write-time fuzzy-dedup via `pg_trgm` similarity ≥ 0.85
- [x] Batch-approve UX on `/admin/taxonomy/proposals` (checkbox multi-select + sticky action bar)
- [x] `typing_indicators` table for server-readable typing presence (used by lull-interjection)
- [x] RetrievalPlan additions — `precomputedVector` field, expanded `DOMAIN_KEYWORDS` heuristic
- [x] Build-version badge in admin header (commit SHA + NYC timestamp)
- [x] Per-stage model pool (Interview / Extraction / Synthesis), 3 independent settings rows
- [x] Lazy `OracleAIClient` init in `/api/chat` (the build-was-broken-for-12h fix)
- [x] Live model-capability discovery via OpenRouter, persisted to `model_capabilities`
- [x] Model catalog refactored: model list from 3 direct provider APIs; OpenRouter demoted to enrichment-only
- [x] "General-purpose model" picker on `/admin/settings`
- [x] Vercel env vars uploaded for all 3 providers (Anthropic, OpenAI, Vertex) via REST API
- [x] Migration `54_model_capabilities.sql` applied to live DB

---

## What's NOT done / what's deferred

### Session-3 items still pending

- [ ] **Run `pnpm db:migrate`** to apply Drizzle migration `0006_magical_revanche.sql` (adds `departments text[]`, makes `department` nullable) and hand-written `56_employees_departments_array.sql` (copies existing `department` values into the new array for pre-existing employees). Required before deploying session-3 code.
- [ ] **Drop deprecated `employees.department`** once all readers are confirmed using `departments`. Write a follow-up migration (`packages/db/migrations/sql/57_drop_employees_department.sql`).

### Easy follow-ups that match what was just built

- [ ] **Wire `GENERAL_PURPOSE_ROUTE_SETTING_KEY` into `taxonomy-reevaluation` cluster naming.** Currently `apps/workers/src/trigger/taxonomy-reevaluation.ts:309,326` has `model: 'gemini-2.5-flash'` hardcoded. Should read `settings.default_general_purpose_route` via `resolveModelRoute(..., 'extraction')` and fall back to the current hardcoded id if unset.
- [ ] **Replace the vision-detection regex in `/api/chat`** (`apps/web/app/api/chat/route.ts:535` — `/claude|gpt-4o|gemini|llava|pixtral|qwen.*vl|minicpm/i`) with a lookup against the resolved route's `vision` flag from the `model_capabilities` table. Right now this hardcoded regex decides whether to download user-uploaded image attachments before the chat call. If Anthropic or OpenAI ship a vision model whose name doesn't match the regex, attachments would be silently dropped.
- [ ] **Periodic refresh cron for `model_capabilities`.** Right now the catalog only refreshes when the admin clicks the button. A weekly Trigger.dev task `refresh-model-catalog` would keep it current automatically.
- [ ] **Pricing source.** OpenRouter exposes pricing in `pricing.prompt` / `pricing.completion` per-token; we already store it in `model_capabilities.prompt_per_1m_usd` / `completion_per_1m_usd` (multiplied to per-million). The model-pool UI already shows pricing badges. No follow-up needed unless OpenRouter ever stops publishing it.
- [ ] **Default selected model in `ModelPicker`** falls back to literal `'anthropic/claude-sonnet-4.6'` (`apps/web/app/admin/settings/_components/model-picker.tsx:120`) when `currentModel` is null. That's the only remaining hardcoded model id in user-facing code. Should fall back to whichever model in the discovered catalog is cheapest+vision-capable, or just leave the picker empty until the admin chooses.

### Bigger architectural follow-ups

- [ ] **Wire the model_pool to actually constrain the model picker dropdown.** Right now the pool DOES filter the dropdown when non-empty, but it's a soft filter — workers will still successfully execute any `provider/modelId` saved to `settings.default_*_route` even if it's not in the pool. If you want hard enforcement, validate-on-save in `/api/admin/settings` POST.
- [ ] **`r-providers-smoke` and other `__verify__` files** still hardcode model IDs (`gemini-2.5-flash-lite`, `claude-haiku-4-5`, `gpt-4o-mini`). They're test code, run manually, low risk — but they'd go stale the same way other hand-typed IDs do.
- [ ] **Live-chat fallback when chosen Gemini model has no Vertex credentials** doesn't have a clean error path yet. Today if the admin picks a Gemini model and `GOOGLE_APPLICATION_CREDENTIALS_JSON` isn't set on Vercel (now it IS set, so this doesn't bite us), the chat call fails. There's no graceful "this model needs Vertex creds, please switch" UI.
- [ ] **Stale `OPENROUTER_API_KEY` in Vercel env** — harmless but tidy to delete.

### Operational items (no code change needed)

- [ ] Rotate the three dev API keys before going live (see "Pre-production security reminders" above).
- [ ] Click "Refresh from OpenRouter" on `/admin/settings/model-pool` the first time you visit after the deploy — the `model_capabilities` table is empty until then.
- [ ] Re-curate per-stage pools (the old global `model_pool` setting still exists in the DB but is ignored by the new per-stage code).

---

## Where hardcoded data could be wrong (knowledge cutoff audit)

The user explicitly asked for this audit. Anywhere the code embeds a model id, capability flag, pricing number, or provider behaviour assumption that came from Claude's training data has a risk of being stale.

**Resolved this session:**
- ✅ Model capability tables in `apps/web/lib/model-metadata.ts` — DELETED, replaced by `model_capabilities` table populated from OpenRouter.
- ✅ `supportsReasoningControls: false` on every Claude/Gemini curated route — was wrong; corrected, then made moot by switching to OpenRouter as the source.

**Remaining hand-typed model data (intentional today but at risk):**

| Location | What's hardcoded | Risk | Mitigation if it goes stale |
|---|---|---|---|
| `packages/ai/src/routes/catalog.ts` | The 6 production-route model IDs + 3 internal subroute IDs (e.g. `claude-haiku-4-5`, `gemini-2.5-flash`, `gpt-4o`, `claude-3-5-sonnet-latest`) | Provider deprecates one of these model IDs → workers return errors until admin updates `default_*_route` settings | `resolveModelRoute()` already supports admin override via settings. Admin sets `default_extraction_route` to a new id from the discovered catalog. |
| `packages/ai/src/routes/catalog.ts` | `supportsVision`, `supportsStreaming`, `supportsToolCalling`, `supportsStructuredOutput`, `supportsReasoningControls`, `costTier`, `cacheStrategy`, `structuredOutputStrategy` on each curated route | These describe THE CURATED ROUTE's intent (e.g. "this route is meant for vision-heavy interview chat") rather than the model's actual capabilities. Less risky than a global capability table because they're tied to specific routes the admin chose. Still hand-typed. | If a curated route's underlying model loses a capability, edit the route or pick a different model id |
| `packages/ai/src/routes/defaults.ts` | `DEFAULT_ORACLE_ROUTES` map keyed by role — references 3 curated routeIds | Same as catalog above | Same |
| `apps/workers/src/trigger/taxonomy-reevaluation.ts:309,326` | `model: 'gemini-2.5-flash'` hardcoded for cluster naming via direct `@google/genai` call | Bypasses the discovery service entirely. If 2.5 Flash is deprecated, cluster naming fails | See "Easy follow-ups" — wire `GENERAL_PURPOSE_ROUTE_SETTING_KEY` here |
| `apps/web/app/api/chat/route.ts:535` | Vision-detection regex `/claude|gpt-4o|gemini|llava|pixtral|qwen.*vl|minicpm/i` | If a new vision-capable model ships whose name doesn't match these patterns, image attachments get silently dropped before being sent | Replace with `model_capabilities.vision` lookup. The capability data is already in the DB. |
| `apps/web/app/admin/settings/_components/model-picker.tsx:120` | Default selected model literal `'anthropic/claude-sonnet-4.6'` | If that id is renamed, the picker shows that text as the placeholder selection but functions correctly once admin picks anything | Cosmetic; could pick the first vision-capable cheapest model from the discovered catalog instead |
| `packages/ai/src/providers/anthropic-adapter.ts` | `'anthropic-version': '2023-06-01'` header | Anthropic deliberately keeps this stable across years; documented as the current API version | Update if Anthropic publishes a breaking new version |
| `packages/ai/src/__verify__/r-providers-smoke.ts` | Hardcoded model IDs for smoke tests | Test code, manually run, low blast radius | Edit when running smokes if a model ID is dead |
| `packages/db/src/seed.ts:36-37` | `default_extraction_model` + `default_synthesis_model` rows with deprecated OpenRouter-style ids | Explicitly marked DEPRECATED; superseded by `default_*_route` keys; no code reads these | Leave; they're documentation of the migration path |

**Other dated assumptions in code/docs:**
- DECISIONS.md and the `docs/oracle/*` retrofit packets are dated by nature — they record what we believed at a point in time. They should NOT be retrofitted to current reality; they're history.
- `oracle_master_spec.md` and `oracle_ai_architecture_prompt caching.md` are product spec snapshots. Keep accurate when product intent changes; otherwise leave.

---

## Next exact action (for the next session)

### Session-3 deployment (do this first)

1. **Apply the DB migrations.** `pnpm db:migrate` from the repo root. This applies `0006_magical_revanche.sql` (adds `departments text[]`, makes `department` nullable) and `56_employees_departments_array.sql` (copies existing department values into the new array). Idempotent — safe to run multiple times.
2. **Commit + push session-3 changes** (if not already committed). Let Vercel auto-deploy.
3. **Verify admin employees page.** Open `/admin`. Existing employees should show their `department` value under "Department(s)". The "Add employee" form should accept a comma-separated departments list.
4. **Test add employee.** Add a test employee via the form. Confirm the row appears with the correct `departments` values.

### Session-2 follow-ups (still open)

5. **First-load smoke check.** Open https://oracle.designflow.app/admin → confirm the top-right shows a commit SHA newer than `1d91cd5`. Hard-refresh if you see anything older.
6. **Refresh the model catalog** if `model_capabilities` table is empty: open `/admin/settings/model-pool` → click "Refresh catalog".
7. **Curate the per-stage pools** and pick the active model per stage on `/admin/settings`.
8. **Live chat sanity check.** Send a message in a channel. Confirm the Oracle responds.

If anything is broken after the session-3 deploy, most likely:
- a. Migration not run — `pnpm db:migrate` was skipped.
- b. Browser cache — hard-refresh.
- c. `model_capabilities` table empty — click the catalog refresh button.

---

## Decisions made this session (recorded here, also worth promoting to DECISIONS.md if they become load-bearing)

1. **Model capability source = OpenRouter, not direct provider APIs + AI classifier.** Anthropic's `/v1/models` returns a rich `capabilities` block; OpenAI's returns nothing useful; Vertex's `publishers/google/models` is the entire Model Garden with no clean capability schema. Going through the discovered catalog for all 3 providers via OpenRouter is simpler, free, and avoids any AI-classifier cost or hallucination risk. The classifier path was built (commits `e9abe5b`) and then replaced (`65f250e`).
6. **Model list from direct provider APIs, not OpenRouter.** OpenRouter's catalog includes every third-party model and uses OpenRouter-specific routing identifiers. The 3 direct provider APIs return only that provider's own models with authoritative IDs. OpenRouter remains the best source for pricing and capability flags (it parses provider docs and exposes a unified schema), so it's retained as an enrichment step after the model list is built.
2. **DB persistence over in-memory cache.** Originally cached the discovered catalog in memory with a 1h TTL. Replaced with the `model_capabilities` table; refresh is an explicit admin action, no TTL.
3. **Reasoning capability on synthesis is required, not optional.** When the picker emptied because no catalog route had `reasoning: true`, the first fix was to drop the requirement. That was wrong (weakens the system). Correct fix: fix the underlying capability data, which led to the entire OpenRouter migration.
4. **Per-stage pools, not one global pool.** `settings.model_pool` is gone, replaced by `settings.model_pool_interview` / `_extraction` / `_synthesis`. The old key is left in the DB (ignored) — don't delete it manually.
5. **Lazy `OracleAIClient` init.** Module-level `new AnthropicAdapter()` etc. broke Vercel's "Collect page data" build phase because env vars aren't in scope then. All web-app callers now use a `getOracleClient()` helper that constructs on first request.

---

## Dead ends / abandoned approaches

- **In-memory catalog cache with TTL** (commit `e9abe5b`) — wiped on server restart, paid for AI classification on each cold instance. Replaced with DB.
- **Direct Vertex `publishers/google/models` REST endpoint for Gemini discovery** — returned the entire Vertex Model Garden (TFVision, MedLM, etc.) without a clean capability schema. Abandoned in favor of OpenRouter.
- **Gemini Flash-Lite as a capability classifier for OpenAI/Vertex** — built and working but user objected on principle (API metadata should be the source, AI classification should be a last resort only). Replaced with OpenRouter.
- **Dropping the `reasoning` capability requirement from Synthesis** (commit `7e1466c`) — masked the actual bug (no reasoning-capable routes in the catalog). Reverted within the same session.

---

## Known risks / blockers / unknowns

- **OpenRouter availability.** If openrouter.ai goes down, admin can't refresh the catalog. The previously refreshed `model_capabilities` rows stay readable; only `POST /api/admin/model-catalog` fails. There's no programmatic alarm yet.
- **OpenRouter's view of provider capabilities may lag.** OpenRouter parses each provider's docs and surfaces capability flags. If Anthropic ships a new Claude version that OpenRouter hasn't catalogued yet, that model won't appear in our catalog until OpenRouter updates. This is acceptable; the alternative was AI classification or hand-typed lists, both worse.
- **Trigger.dev workers are not aware of OpenRouter.** They resolve routes via `resolveModelRoute()` against the curated catalog OR a `provider/modelId` string. If the admin picks a model in the picker that workers don't recognise, `resolveModelRoute` will fall back to the synthetic route shape (handles auth, defaults reasonable values) — but if the model id is wholly invented, the provider call will 4xx.
- **The Vercel SA key for `oracle-trigger-worker@vertex-ai-497120` is now multi-key.** Trigger.dev has its own SA key for this account (set previously); Vercel got a new key generated in this session. Both work. Rotate both during pre-production cleanup. There's a record in GCP IAM of who created each.

---

## When is this HANDOFF.md eligible for deletion?

Per the user's rule: HANDOFF.md exists when there's unfinished or in-progress work that the next session needs. The list under "What's NOT done / what's deferred" above is the gating criteria — when those follow-ups are either landed or explicitly deprioritised, this file should be deleted (its history lives in git anyway).

Until then, keep it.
