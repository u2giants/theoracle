# Fix Plan: Remove ALL Silent Fallbacks and Hard-Coded Models

Status: **NOT STARTED.** Self-contained brief for a developer with zero prior context. Written 2026-06-25; revised after codebase review on 2026-06-25.

This is a **core-inference refactor**: every worker and the chat route dispatch through this path. A mistake breaks ALL inference. Implement it as one coherent, verified pass. Do not half-migrate.

---

## 0. Orientation

Read `AGENTS.md` first, then `HANDOFF.md`, then this plan and `fix_resolve_ts.md`.

The Oracle routes every LLM call through:

`OracleAIClient` -> `ModelRouter` -> provider adapter (`packages/ai/src/providers/*-adapter.ts`)

There are 3 frozen pipeline roles:

- `interview`
- `extraction`
- `synthesis`

There are also auxiliary models:

- `vision`
- `general`
- `translation`

The admin picks models in `/admin/settings`. Pipeline stages also have approved pools in `settings.model_pool_<stage>`:

- `model_pool_interview`
- `model_pool_extraction`
- `model_pool_synthesis`

`model_pool_vision` exists as a constant today, but the UI/API do not yet treat auxiliary models as pool-backed. Auxiliary pickers currently draw from the full catalog. This plan must either add real auxiliary pools or explicitly keep aux models as single-pick + loud failure. See section 2.2.

Model metadata lives in the `model_capabilities` table.

## 1. The Problem

Today there are two layers of silent, hard-coded fallback, and they caused real, hours-long incidents this session.

1. **Router dispatch fallback**

   Every route carries `fallbackRouteId`. When the selected model cannot dispatch, for example `No adapter registered for provider qwen`, `ModelRouter` silently switches to the route's fallback. For dynamic routes, `resolve.ts` sets:

   `fallbackRouteId = DEFAULT_ORACLE_ROUTES[role]`

   That is a hard-coded route from `packages/ai/src/routes/defaults.ts`.

2. **Worker unset-setting fallback**

   Several workers have hard-coded `FALLBACK_ROUTE_ID` constants used when `default_<stage>_route` is unset or unresolvable.

Consequences proven this session:

- Selected `qwen/qwen3-vl` for vision and `qwen/qwen3.7-plus` for extraction silently fell back to `gemini-2.5-flash`.
- The fallback model was not approved for that stage's pool.
- The run reported success, so the admin could not tell the selected model was not what ran.
- The `/admin/settings` "General-purpose / utility / fallback model" picker (`default_general_purpose_route`) is currently a dead-end. Taxonomy cluster naming uses a hard-coded Gemini route instead.

## 1.1 Owner Directive

1. No more `fallbackRouteId`.
2. Every failure fails verbosely: loud, durable, surfaced, never silently swapped.
3. On failure, auto-advance only to the next **approved and capability-valid** model in that stage's pool, or surface a clear admin action to pick another approved model.
4. Default to auto-advance where safe, but record every attempt and final failure.
5. Delete the hard-coded default mechanism (`DEFAULT_ORACLE_ROUTES`, `DEFAULT_VISION_ROUTE_ID`, `DEFAULT_TRANSLATION_ROUTE_ID`) except setting-key constants.
6. Delete all `FALLBACK_ROUTE_ID` constants.
7. Delete hard-coded model references, including taxonomy cluster naming.
8. Fix the dead-end `general` picker, or remove the picker.

## 2. Target Architecture

**The approved pool is the only fallback chain. There are no hard-coded model fallbacks.**

For each configured model slot, build an ordered candidate list:

1. Primary candidate: the saved `default_<slot>_route` setting.
2. Remaining candidates: other approved pool members, in pool order.
3. Every candidate must be approved and capability-valid.

Dispatch tries candidates in order. Each failed attempt is:

- logged with stage, route, provider, model, and reason;
- recorded durably in a new attempt table;
- included in the final result metadata or final aggregate error;
- surfaced in the admin alert UI.

If all candidates fail, throw `AllCandidatesFailedError(slot, attempts[])` with every route/model/reason. The caller marks the job/document/message path failed with that full message.

If no usable model is configured, throw `NoConfiguredModelError(slot)`:

`No model configured for <slot>. Set an approved model in Admin -> Settings.`

No hard-coded default route should run in that case.

### 2.1 Capability Enforcement Is Part of This Work

Do `fix_resolve_ts.md` together with this plan, or make this implementation consume its shared capability module.

Pool chaining without runtime capability enforcement is unsafe. Today `makeSyntheticRoute()` in `packages/ai/src/routes/resolve.ts` assumes synthetic routes support vision, tools, and structured output. That is exactly how a wrong-tool model can pass the UI/runtime boundary.

Add shared capability requirements in `packages/ai`, and have both the admin UI and runtime use the same source of truth.

### 2.2 Auxiliary Model Decision

Pipeline stages already have pool settings. Auxiliary models do not, despite `VISION_MODEL_POOL_SETTING_KEY` existing.

Choose one policy and implement it explicitly:

**Preferred policy: make auxiliary models pool-backed too.**

Add real settings, UI, resolver support, and docs for:

- `model_pool_vision`
- `model_pool_general`
- `model_pool_translation`

Then aux candidate lists follow the same rule: primary setting first, then other pool members, all capability-valid where applicable.

**Acceptable narrower policy: aux models are single-pick and fail loud.**

If aux pools are not built in this pass, remove `model_pool_vision` from the plan and docs, delete `defaultRouteId`, and make unset/unresolvable aux settings throw `NoConfiguredModelError`. Do not pretend aux has a pool if the UI/API do not manage one.

Either policy is better than today's hidden hard-coded defaults. Do not leave the current in-between state.

### 2.3 Keep the Router Non-DB-Aware

Do not make `ModelRouter` read settings or the database. Keep DB-aware resolution in `packages/ai/src/routes/from-settings.ts` or a new `packages/ai/src/routes/candidates.ts`.

Recommended shape:

- `resolveRouteCandidates(db, slot): Promise<RouteCandidate[]>`
- `OracleAIClient.runText/runObject` accepts either `routeId` for tests/simple callers or `routeCandidates` for production callers.
- `ModelRouter` receives the ordered candidates and only handles adapter dispatch + attempt metadata.

This keeps routing selection and provider dispatch separated.

### 2.4 Route-ID Normalization

Pools store `provider/modelId` values. Default settings may store curated route IDs such as `anthropic_claude_haiku_4_5_interview_primary`.

Candidate resolution must normalize both forms:

- resolve curated route ID to concrete `provider/modelId`;
- check that concrete id is approved in the pool;
- preserve the saved route ID when it is the actual route identifier needed for observability;
- avoid duplicate attempts when the primary setting and a pool member resolve to the same provider/model.

This is required because the admin picker currently preserves curated route IDs when saving without changing the model.

## 3. Durable Attempt Recording

Do **not** cram per-attempt state into `model_run_usage_details`.

`model_run_usage_details` is currently a 1:1 child of `model_runs` and has a unique `model_run_id`. It is the wrong shape for many candidate attempts.

Add a new table, for example `model_run_attempts`:

- `id uuid primary key`
- `model_run_id uuid null references model_runs(id)`
- `context_pack_id uuid null references oracle_context_packs(id)`
- `task_type varchar`
- `slot varchar` (`interview`, `extraction`, `synthesis`, `vision`, `general`, `translation`)
- `attempt_index integer not null`
- `route_id varchar not null`
- `provider varchar not null`
- `model_id varchar not null`
- `is_primary boolean not null`
- `status varchar not null` (`success`, `failed`, `skipped_capability`, `skipped_unapproved`)
- `error text`
- `latency_ms integer`
- `provider_request_id varchar null`
- `created_at timestamp default now()`

Keep `model_runs` as the final successful run or final failed aggregate run, depending on caller semantics. Link successful attempt rows to the final `model_runs.id` where available. For failures before a provider response, record attempt rows even when token usage is null.

Update `model_runs_with_usage` or add a companion view for alerting:

- recent non-primary successes;
- recent all-candidates-failed events;
- recent skipped capability/unapproved candidates;
- counts by slot and route.

## 4. Hard-Coded Reference Inventory

Delete or replace all of these.

| File | Symbol / behavior | Action |
|---|---|---|
| `packages/ai/src/routes/defaults.ts` | `DEFAULT_ORACLE_ROUTES` | Delete hard-coded route ids. Keep setting-key constants such as `ROUTE_SETTING_KEYS`, `REASONING_EFFORT_SETTING_KEYS`, and pool setting key constants. |
| `packages/ai/src/routes/defaults.ts` | `DEFAULT_VISION_ROUTE_ID`, `DEFAULT_TRANSLATION_ROUTE_ID` | Delete. Aux unset/unresolvable means loud no-config error, or aux pool chain if aux pools are implemented. |
| `packages/ai/src/routes/resolve.ts` | synthetic `fallbackRouteId: DEFAULT_ORACLE_ROUTES[role]` | Remove. Synthetic routes must not carry fallback targets. |
| `packages/ai/src/routes/catalog.ts` | `fallbackRouteId` on curated routes | Remove field from every route. |
| `packages/ai/src/routes/types.ts` | `fallbackRouteId`, `fallbackCondition`, `FallbackCondition` | Remove from `OracleModelRoute`. Update comments that still describe strict primary/fallback pairs. |
| `packages/ai/src/routing/model-router.ts` | `fallbackOnError`, `fallbackRouteId` dispatch, `fallbackReason` | Replace with ordered candidate dispatch and attempt metadata. |
| `packages/ai/src/client/oracle-ai-client.ts` | `fallbackOnError` option | Remove or deprecate during migration; production callers should pass candidates. |
| `packages/ai/src/client/types.ts` | `fellBackFromRouteId`, `fallbackReason` | Replace with `attemptedRoutes[]`, `actualRouteId`, and possibly `nonPrimaryReason`. |
| `packages/ai/src/routes/auxiliary.ts` | `defaultRouteId` | Remove. If aux pools are implemented, add `poolSettingKey`; otherwise single-pick + loud no-config. |
| `apps/workers/src/trigger/document-ingestion.ts` | `FALLBACK_ROUTE_ID`, vision fallback via `VISION_AUXILIARY_MODEL.defaultRouteId` | Delete. Use candidate resolver. |
| `apps/workers/src/trigger/claim-extraction.ts` | `FALLBACK_ROUTE_ID` | Delete. Use candidate resolver. |
| `apps/workers/src/trigger/contradiction-watcher.ts` | `FALLBACK_ROUTE_ID`, any interview fallback constants | Delete. Use candidate resolver for each slot used. |
| `apps/workers/src/trigger/brain-synthesis.ts` | `FALLBACK_ROUTE_ID` | Delete. Use candidate resolver. |
| `apps/workers/src/trigger/teams-live-recall-utterance.ts` | interview fallback behavior | Delete. Use interview candidates or fail loud. |
| `apps/workers/src/trigger/lull-interjection.ts` | interview fallback behavior | Delete. Use interview candidates or fail loud. |
| `apps/workers/src/trigger/claim-translation.ts` | `DEFAULT_TRANSLATION_ROUTE_ID`, `fallbackOnError` | Delete. Use translation candidates or loud single-pick aux behavior. |
| `apps/web/app/admin/claims/_actions.ts` | `DEFAULT_TRANSLATION_ROUTE_ID`, `fallbackOnError` in review-question translation | Delete. Use translation candidates or loud single-pick aux behavior. Decide whether review-question translation failure should fail the assignment or fall back to English with an admin-visible warning. |
| `apps/workers/src/trigger/taxonomy-reevaluation.ts` | `CLUSTER_NAMING_ROUTE_ID` | Replace with `general` candidates. |
| `apps/workers/src/trigger/taxonomy-reevaluation.ts` | generic cluster-name fallback on LLM failure | Do not silently degrade. Either record a warning attempt and surface it, or fail/propose with explicit `name_generation_status='fallback_used'` in payload. |
| `apps/workers/src/trigger/claim-extraction-batch-submit.ts` and drain path | batch route assumptions | Decide explicit behavior. Batch jobs cannot cheaply try a chain synchronously. Either resolve one approved/capable batch route at submit time and fail loud, or model batch fallback as a new batch submission after provider failure. Document it. |
| `packages/db/src/schema.ts` and migrations/views | `fellBackFromRouteId`, `fallbackReason` | Keep legacy columns temporarily if needed for old rows, but add attempts table and update views/UI. Do not use these as the new mechanism. |
| `packages/ai/src/__verify__/oracle-ai-client-smoke.ts` | old fallback assertions | Rewrite for candidate chain. |
| `packages/ai/src/__verify__/r-providers-smoke.ts` | test route objects with `fallbackRouteId` | Update route fixtures. |

Confirm with:

```powershell
rg -n "FALLBACK_ROUTE_ID|fallbackRouteId|DEFAULT_ORACLE_ROUTES|DEFAULT_VISION_ROUTE_ID|DEFAULT_TRANSLATION_ROUTE_ID|CLUSTER_NAMING_ROUTE_ID|fallbackOnError|fellBackFromRouteId|fallbackReason" packages apps
```

Expected after migration:

- no production fallback mechanism hits;
- only legacy DB column references, migration comments, compatibility reads, or renamed test expectations remain;
- ideally even legacy references are isolated and clearly marked.

## 5. Implementation Order

Build the replacement before deleting old constants.

1. **Shared capability module**

   Implement the core of `fix_resolve_ts.md` first:

   - `requiredCapabilitiesFor(slot)`
   - DB lookup from `model_capabilities`
   - typed `ModelCapabilityError`
   - shared UI/runtime requirement source

2. **Candidate resolver**

   Add `resolveRouteCandidates(db, slot)` in `packages/ai/src/routes/candidates.ts` or `from-settings.ts`.

   Responsibilities:

   - read primary setting and reasoning effort;
   - read the slot pool when pool-backed;
   - normalize route IDs and `provider/modelId`;
   - require primary to be approved in pool for pool-backed slots;
   - de-duplicate candidates;
   - attach real capability metadata where available;
   - skip or reject capability-invalid models with recorded reasons;
   - throw `NoConfiguredModelError` when no usable candidate exists.

3. **Auxiliary policy**

   Implement section 2.2. If choosing aux pools, add settings/UI/API support before wiring runtime to aux pools.

4. **Attempt table migration**

   Add `model_run_attempts` in `packages/db/src/schema.ts` and a hand-written SQL migration under `packages/db/migrations/sql/`. Update the SQL README.

5. **Router candidate dispatch**

   Replace `fallbackOnError` with a dispatch loop over ordered candidates.

   Each attempt should catch:

   - missing adapter;
   - provider/network/rate limit errors;
   - schema/Zod errors thrown by adapters;
   - provider refusal/empty response errors.

   On failure, record the attempt and advance only if another approved/capable candidate exists. After the final failure, throw `AllCandidatesFailedError`.

6. **Structured output failure semantics**

   Today adapters call `tryZodParse(schema, parsed)` and throw on schema-invalid output. The dispatch loop must catch that and record it. Prefer a later cleanup where adapters return raw parsed output plus validation failure instead of throwing, but this refactor must at least make thrown validation failures visible and chainable.

7. **OracleAIClient metadata**

   Return metadata like:

   - `actualRouteId`
   - `actualProvider`
   - `actualModelId`
   - `attemptedRoutes[]`
   - `usedNonPrimary: boolean`

   Remove `fellBackFromRouteId` and `fallbackReason` from new code.

8. **Call-site migration**

   Update every worker and the chat route to resolve candidates before calling `OracleAIClient`.

   Production callers to cover:

   - `apps/web/app/api/chat/route.ts`
   - `apps/workers/src/trigger/claim-extraction.ts`
   - `apps/workers/src/trigger/document-ingestion.ts`
   - `apps/workers/src/trigger/brain-synthesis.ts`
   - `apps/workers/src/trigger/contradiction-watcher.ts`
   - `apps/workers/src/trigger/teams-live-recall-utterance.ts`
   - `apps/workers/src/trigger/lull-interjection.ts`
   - `apps/workers/src/trigger/claim-translation.ts`
   - `apps/web/app/admin/claims/_actions.ts`
   - `apps/workers/src/trigger/taxonomy-reevaluation.ts`
   - batch submit/drain paths, with explicit batch-specific behavior

9. **Delete old fields/constants**

   Remove route fallback fields from types/catalog/resolver and worker fallback constants.

10. **Admin alerting**

   Add section 6 banner/query.

11. **Docs and decisions**

   Update:

   - `AGENTS.md`
   - `docs/architecture.md`
   - `docs/configuration.md`
   - `DECISIONS.md`
   - `packages/db/migrations/sql/README.md`

## 6. Verbose Failure and Alerting

Owner requirement: "I NEED TO BE ALERTED."

### Source Logging

Every attempt failure logs:

- slot;
- candidate index;
- route id;
- provider;
- model id;
- primary vs non-primary;
- error name/message;
- whether the system will advance or stop.

### Durable Record

Use `model_run_attempts`. Do not rely on console logs.

### Admin Alert V1

Add a red admin banner plus count on:

- `/admin`
- `/admin/settings`

Trigger conditions for last N days:

- a run used a non-primary candidate;
- all candidates failed;
- a candidate was skipped because it was unapproved or capability-invalid;
- an aux slot is unset but has consumers.

Distinguish:

- **warning:** advanced to next approved model;
- **error:** all candidates failed;
- **configuration error:** no model configured or primary not in pool.

A true push/email alert can come later. The banner is the v1 "you will not miss it" signal.

## 7. General / Utility Picker

`default_general_purpose_route` is currently consumed by nothing. Taxonomy cluster naming uses hard-coded `CLUSTER_NAMING_ROUTE_ID`.

Fix:

- wire taxonomy cluster naming to the `general` aux model;
- use the same candidate-chain or loud single-pick aux behavior chosen in section 2.2;
- delete `CLUSTER_NAMING_ROUTE_ID`;
- record model attempts for taxonomy naming.

Also fix the second silent fallback in taxonomy naming:

- today, if naming fails, it silently creates a generic cluster name;
- after this refactor, either fail the proposal or write an explicit degraded proposal payload field and raise an admin alert.

If the team decides the general model has no real consumer, remove the picker and setting instead. Do not leave a control wired to nothing.

## 8. Edge Cases and Gotchas

- **Build replacement first.** Deleting `FALLBACK_ROUTE_ID` without candidate resolution breaks unset-setting paths.
- **Boot resilience is separate.** `buildStandardAdapters` may still skip providers whose key is absent. A missing adapter for a candidate is an attempt failure, not a reason to jump to a hard-coded model.
- **Pool of one.** If it fails, throw all-candidates-failed. Correct.
- **Primary not in pool.** For pool-backed slots, this is a configuration error. Do not run an unapproved primary just because it is saved.
- **Capability-invalid pool member.** Skip and record, or fail configuration depending on policy. Do not dispatch.
- **Unknown model capabilities.** Follow `fix_resolve_ts.md`: fail closed for capability-sensitive slots unless an emergency flag explicitly disables enforcement.
- **Chat latency.** Chat is user-facing. Consider limiting interview chain to primary + one candidate, or fail fast after provider errors likely to be slow. Decide and document.
- **Batch mode.** Batch dispatch cannot use the same synchronous loop without submitting multiple jobs. Decide explicit semantics before changing batch submit/drain.
- **Translation UX.** For review-question translation, decide whether translation failure blocks assignment or sends English with a loud warning. Do not silently send English as if translation worked.
- **Trigger schedule slots are 10/10.** Do not add a cron.
- **Legacy observability columns.** Keep old `fell_back_from_route_id` columns only as legacy data until a later cleanup. New logic uses attempts.

## 9. Testing and Acceptance

Rewrite `verify:r2` for candidate-chain behavior:

- primary fails -> next approved candidate runs;
- actual route metadata records the non-primary route;
- attempts array/table has both attempts;
- all fail -> `AllCandidatesFailedError` names each candidate and reason;
- unset stage -> `NoConfiguredModelError`;
- candidate lacks required capability -> skipped/blocked and recorded, not used;
- dynamic route `qwen/qwen3.7-plus` still resolves when catalog capabilities allow it.

Add or update tests for:

- route ID vs `provider/modelId` normalization;
- primary not in pool;
- duplicate primary/pool candidate de-duplication;
- aux policy chosen in section 2.2;
- taxonomy naming uses general aux and records degraded/failure state;
- translation callers no longer use `DEFAULT_TRANSLATION_ROUTE_ID`;
- batch-mode behavior is explicit.

Acceptance:

- no production code uses `fallbackRouteId`, `DEFAULT_ORACLE_ROUTES`, `DEFAULT_VISION_ROUTE_ID`, `DEFAULT_TRANSLATION_ROUTE_ID`, `FALLBACK_ROUTE_ID`, `CLUSTER_NAMING_ROUTE_ID`, `fallbackOnError`, `fellBackFromRouteId`, or `fallbackReason`;
- every production model call uses either ordered approved/capable candidates or intentionally loud single-pick aux behavior;
- failed primary can only advance to approved/capable pool candidates;
- every attempt is visible in durable data;
- total failure is loud and surfaced;
- unset model config fails verbosely;
- `general` drives taxonomy cluster naming or is removed;
- admin banner surfaces non-primary use and exhausted pools;
- `corepack pnpm -r typecheck` passes;
- relevant `verify:*` suite passes.

Manual acceptance:

1. Set extraction primary to a model whose provider key is missing.
2. Confirm it does not silently run Gemini.
3. Confirm it advances only to the next approved/capable pool model, or fails loudly.
4. Confirm attempts are in DB.
5. Confirm `/admin` and `/admin/settings` show the banner.

## 10. Logistics

- Deploy workers: `corepack pnpm --filter @oracle/workers run deploy` or Trigger MCP deploy.
- Web deploys via Vercel on push to `main`.
- Prod DB: use the session pooler string in 1Password (`Supabase DB Direct URL - The Oracle (CURRENT PROD ...)` -> `oracle_session_pooler`). Direct host is IPv6-only. `.env.local` may point at the old project. See `AGENTS.md`.
- Do not use Supabase MCP `apply_migration` or `drizzle-kit push`; ship through the repo migration path.

## 11. Concrete Anchors

Current settings keys:

- stage selections: `default_interview_route`, `default_extraction_route`, `default_synthesis_route`
- stage pools: `model_pool_interview`, `model_pool_extraction`, `model_pool_synthesis`
- aux selections: `default_vision_route`, `default_translation_route`, `default_general_purpose_route`
- existing aux pool-ish constant: `model_pool_vision` exists, but is not fully wired
- reasoning effort: `default_<stage>_reasoning_effort`, plus `default_vision_reasoning_effort`

Current route path:

- `packages/ai/src/routes/from-settings.ts`
- `packages/ai/src/routes/resolve.ts`
- `packages/ai/src/routing/model-router.ts`
- `packages/ai/src/client/oracle-ai-client.ts`

Current validation throw:

- `packages/ai/src/providers/vertex-gemini-adapter.ts` exports `tryZodParse`
- adapters call `tryZodParse(schema, parsed)`
- invalid Zod output throws before `OracleAIClient.runObject` can build its `validation` result

Current observability:

- `model_runs`
- `model_run_usage_details` (1:1 with `model_runs`)
- `model_runs_with_usage`
- `extraction_batches.modelRunIdsAttempted` and `routeIdsAttempted` exist but are not a general attempt log

Full session context:

- See `HANDOFF.md` "SESSION-END STATE".
- This explains how Qwen vision and extraction silently fell back to the hard-coded `vertex_gemini_2_5_flash_extraction_primary`, what was committed vs reverted, and why the fast interim fix was to switch extraction to strict JSON (`google/gemini-3.1-flash-lite`).
