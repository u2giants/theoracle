# Fix Plan: Remove ALL silent fallbacks & hard-coded models → pool-as-chain + fail-verbose

Status: **NOT STARTED.** Self-contained brief for a developer with zero prior context. Written 2026-06-25.

This is a **core-inference refactor**: every worker and the chat route dispatch through this path. A mistake breaks ALL inference. Implement it as one coherent, verified pass — do NOT half-migrate.

---

## 0. Orientation (read first)

Read `AGENTS.md`. The Oracle routes every LLM call through `OracleAIClient` → `ModelRouter` → a provider adapter (`packages/ai/src/providers/*-adapter.ts`). There are 3 frozen pipeline roles — `interview`, `extraction`, `synthesis` — plus auxiliary models (`vision`, `general`, `translation`). The admin picks a model per role/aux at `/admin/settings`; each stage also has an **approved pool** (`model_pool_<stage>` settings row, e.g. `model_pool_extraction = ["google/gemini-3.1-flash-lite","qwen/qwen3.7-plus","qwen/qwen3.7-max"]`). Model metadata lives in the `model_capabilities` Postgres table.

## 1. The problem (why this exists)

Today there are **two layers of silent, hard-coded fallback**, and they caused real, hours-long incidents this session:

- **Router dispatch fallback:** every route carries a `fallbackRouteId`. When the selected model can't dispatch (e.g. `"No adapter registered for provider qwen"` because a key was missing), `ModelRouter` silently switches to it. For dynamic routes, `resolve.ts` sets `fallbackRouteId = DEFAULT_ORACLE_ROUTES[role]` — a **hard-coded** route in `packages/ai/src/routes/defaults.ts`.
- **Worker "unset setting" fallback:** each worker has a hard-coded `FALLBACK_ROUTE_ID` used when `default_<stage>_route` is unset/unresolvable.

Consequences proven this session: the selected `qwen/qwen3-vl` (vision) and `qwen/qwen3.7-plus` (extraction) **both silently fell back to `gemini-2.5-flash`** — an *unapproved* model that isn't even in the pool — and reported success. Nobody was alerted. The admin's selected model was not what ran. Separately, the `/admin/settings` "General-purpose / utility / fallback model" picker (`default_general_purpose_route`) is a **dead-end** — nothing consumes it; the job it was meant for (taxonomy cluster-naming) uses a hard-coded route instead.

### Owner's directive (the target behavior)
1. **No more `fallbackRouteId`. Every failure fails VERBOSELY** (loud, surfaced — never a silent swap).
2. On failure, the system either (a) **auto-advances to the next APPROVED model in that stage's pool**, logging each attempt verbosely, or (b) surfaces to the admin to pick another approved model from the dropdown. Default to auto-advance, but make every attempt + the final failure visible.
3. **Delete `DEFAULT_ORACLE_ROUTES.extraction`** (and the whole hard-coded-default mechanism).
4. **Delete all `FALLBACK_ROUTE_ID` constants** in workers — replace with the pool-chain path.
5. **Delete all hard-coded model references** (see the full inventory in §3).
6. **Fix the dead-end "general/utility" picker.**

## 2. The new architecture

**The approved pool IS the fallback chain. There are no hard-coded models.**

- Per stage/aux, build an **ordered candidate list** from settings: primary = `default_<stage>_route`; remaining = the other members of `model_pool_<stage>`, in pool order. Every candidate must be **approved (in the pool) and capability-valid** for the role (reuse the capability check from `fix_resolve_ts.md` — these two efforts share the invariant).
- Dispatch tries candidates **in order**. Each failure is logged **verbosely** (provider/model/reason) AND recorded (`model_runs` + `model_run_usage_details.attempted_route_id` / failure reason) AND surfaced (see §5 alerting). It advances to the next candidate.
- If **all** candidates fail → throw a clear aggregate error naming every model tried and why. The caller marks the job/document `failed` with that message (workers already do this after this session's anti-masking work).
- If the stage has **no configured model / empty pool** → fail verbosely with "no model configured for <stage> — set one in Admin → Settings." NO hard-coded default.
- The concept of a single `fallbackRouteId` is removed entirely. "Fallback" = "next approved model in the pool."

## 3. Hard-coded model reference inventory (delete/replace ALL of these)

| File | Symbol | Action |
|---|---|---|
| `packages/ai/src/routes/defaults.ts` | `DEFAULT_ORACLE_ROUTES` (interview/extraction/synthesis) | DELETE. Resolution comes from settings + pool; unset = verbose error. |
| `packages/ai/src/routes/defaults.ts` | `DEFAULT_VISION_ROUTE_ID`, `DEFAULT_TRANSLATION_ROUTE_ID` | DELETE the hard-coded route ids; aux resolution uses the aux pool (`model_pool_vision`) / setting; unset = verbose error. |
| `packages/ai/src/routes/resolve.ts` | synthetic route `fallbackRouteId: DEFAULT_ORACLE_ROUTES[role]` | REMOVE the `fallbackRouteId` field from routes entirely. |
| `packages/ai/src/routes/catalog.ts` | `fallbackRouteId:` on curated routes (`openai_gpt4o_interview_fallback`, `openai_gpt4o_mini_extraction_fallback`, `vertex_gemini_2_5_flash_synthesis_fallback`, …) | REMOVE the field from the route type + all routes. |
| `packages/ai/src/routes/types.ts` | `fallbackRouteId`, `fallbackCondition` on `OracleModelRoute` | REMOVE from the type. |
| `packages/ai/src/routing/model-router.ts` | `fallbackOnError`, `fallbackRouteId` dispatch path, `fallbackReason` | REPLACE with the ordered-candidate-list logic (§2). |
| `packages/ai/src/routes/auxiliary.ts` | `defaultRouteId` on aux entries | REMOVE; aux resolution uses the aux pool/setting; unset = verbose. |
| `apps/workers/src/trigger/document-ingestion.ts` | `FALLBACK_ROUTE_ID` | DELETE; use the pool-chain resolver. |
| `apps/workers/src/trigger/claim-extraction.ts` | `FALLBACK_ROUTE_ID` | DELETE; pool-chain. |
| `apps/workers/src/trigger/contradiction-watcher.ts` | `FALLBACK_ROUTE_ID`, `FALLBACK_INTERVIEW_ROUTE_ID` | DELETE; pool-chain. |
| `apps/workers/src/trigger/brain-synthesis.ts` | `FALLBACK_ROUTE_ID` | DELETE; pool-chain. |
| `apps/workers/src/trigger/teams-live-recall-utterance.ts` | `FALLBACK_INTERVIEW_ROUTE_ID` | DELETE; pool-chain. |
| `apps/workers/src/trigger/lull-interjection.ts` | `FALLBACK_INTERVIEW_ROUTE_ID` | DELETE; pool-chain. |
| `apps/workers/src/trigger/taxonomy-reevaluation.ts` | `CLUSTER_NAMING_ROUTE_ID` (hard-coded gemini) | REPLACE with the `general`/utility aux model (this is the dead-end fix, §6). |

Search command to confirm none remain after the work:
`rg -n "FALLBACK_ROUTE_ID|fallbackRouteId|DEFAULT_ORACLE_ROUTES|DEFAULT_VISION_ROUTE_ID|DEFAULT_TRANSLATION_ROUTE_ID|CLUSTER_NAMING_ROUTE_ID|fallbackOnError" packages apps` → should return only the new pool-chain code + tests.

## 4. Step-by-step implementation (order matters — build the replacement BEFORE deleting)

1. **Capability check shared module** (coordinate with `fix_resolve_ts.md`): `requiredCapabilitiesFor(roleOrAux)` + a `model_capabilities` lookup. A candidate is eligible only if approved (in pool) AND capability-valid.
2. **`resolveRouteCandidates(db, stageOrAux): OracleModelRoute[]`** (new, in `from-settings.ts` or a new `candidates.ts`): primary `default_<stage>_route` first, then the rest of `model_pool_<stage>`, each validated; throws `NoConfiguredModelError(stage)` (verbose) if the primary is unset/empty.
3. **`ModelRouter`**: new `dispatchText`/`dispatchObject` that take the ordered candidate list, try each, and on each failure: `console.error` verbosely, record the attempt, advance. After the last: throw `AllCandidatesFailedError(stage, attempts[])` listing every model + reason. Remove `fallbackOnError`/`fallbackRouteId`.
4. **`OracleAIClient` `runText`/`runObject`**: accept a stage (or candidate list) and pass it to the router. Result metadata carries `attemptedRoutes[]` + `actualRouteId` (replacing `fellBackFromRouteId`).
5. **Usage logging**: extend `model_run_usage_details` (or a new `model_run_attempts` table) to record each attempt + reason. Migration in `packages/db/migrations/sql/`.
6. **Update every worker + the chat route** to use `resolveRouteCandidates` and surface the verbose failure (mark job/doc `failed` with the aggregate message — most workers already mark failed after this session's changes).
7. **Delete** everything in §3.
8. **Remove the route `fallbackRouteId`/`fallbackCondition` fields** from the type + catalog.
9. **Alerting** (§5).
10. **Dead-end picker** (§6).
11. **Docs**: `AGENTS.md` §10 (new quirk: "no silent fallback; pool is the chain; unset = verbose error"), `docs/architecture.md` (routing section), `docs/configuration.md` (pool settings drive fallback), `DECISIONS.md` (record the removal of `fallbackRouteId`).

## 5. Verbose failure + ALERTING (owner: "I NEED TO BE ALERTED")

- **Verbose at the source:** every attempt failure → `console.error` with stage, model, reason; the final failure → job/document `failed` with the full aggregate message.
- **Durable record:** each attempt (incl. which model, success/fail, reason) in `model_run_usage_details`/`model_run_attempts`.
- **Active admin alert:** add an admin surface that reads recent fallbacks/attempt-failures and shows a **red banner + count on `/admin` and `/admin/settings`** whenever a stage ran on a non-primary model or exhausted its pool in the last N days. (A true push/email alert can come later; the banner is the v1 "you will not miss it" signal.) Files: a small query + a banner component in `apps/web/app/admin/_components/`.
- Distinguish "advanced to next approved model" (warning) from "all candidates failed" (error).

## 6. Fix the dead-end "general / utility" picker

`default_general_purpose_route` (set in `/admin/settings`, currently your `qwen3.7-max`) is consumed by **nothing**. The job it was meant for — taxonomy **cluster-naming** in `apps/workers/src/trigger/taxonomy-reevaluation.ts` — uses the hard-coded `CLUSTER_NAMING_ROUTE_ID` instead. Fix = **wire cluster-naming (and any other "internal one-off" jobs) to resolve the `general` aux model via `resolveAuxiliaryRouteFromSettings(db, 'general')`** (with the same pool-chain + verbose-fail rules), and delete `CLUSTER_NAMING_ROUTE_ID`. If you decide the general model has no real consumer, REMOVE the picker + setting instead — do not leave a control wired to nothing.

## 7. Edge cases / gotchas

- **Build the replacement before deleting** — deleting `FALLBACK_ROUTE_ID` without the pool-chain resolver breaks every worker's unset-setting path.
- **Boot resilience is separate:** `buildStandardAdapters` still skips providers whose key is absent (and now logs loudly, fixed 2026-06-25). A missing-adapter dispatch must now FAIL VERBOSELY for that candidate and advance to the next APPROVED candidate (not a hard-coded one) — that is exactly the qwen incident, fixed correctly.
- **Pool of one:** if a stage's pool has a single model and it fails, that's a verbose all-candidates-failed error. Correct.
- **Capability validity:** don't advance to a pool member that lacks the required capability (e.g. a non-vision model for the vision aux) — skip it with a logged reason, or the same wrong-tool incident recurs. Ties to `fix_resolve_ts.md`.
- **Chat route latency:** chat is user-facing; auto-advancing through a long pool adds latency. Consider capping chat to primary + 1 candidate, or failing fast with a clear UI error. Decide + document.
- **Trigger schedule slots are 10/10** — don't add a cron.
- **The smoke `verify:r2`** currently asserts the OLD `fallbackOnError`/`fallbackRouteId` behavior (`packages/ai/src/__verify__/oracle-ai-client-smoke.ts`). Rewrite those assertions for the new candidate-chain behavior — don't just delete them.

## 8. Testing / acceptance

- Rewrite `verify:r2` (`oracle-ai-client-smoke.ts`) for candidate-chain: primary fails → next approved candidate runs (and is recorded as the actual route); all fail → `AllCandidatesFailedError` naming each; unset stage → `NoConfiguredModelError`.
- New test: a candidate that lacks the required capability is skipped (logged), not used.
- `rg` search (§3) returns no hard-coded refs.
- `corepack pnpm -r typecheck` and the full `verify:*` suite green.
- Manual: set extraction primary to a model whose provider key is missing; confirm it (a) does NOT silently run gemini, (b) advances to the next approved pool model OR fails verbosely, (c) shows the admin banner.

**Acceptance:** no `fallbackRouteId`/`DEFAULT_ORACLE_ROUTES`/`FALLBACK_ROUTE_ID`/hard-coded model id remains; a failed primary auto-advances only through approved+capable pool models, each attempt visible; total failure is loud and surfaced; an unset stage fails verbosely; the general/utility picker drives a real job or is removed.

## 9. Logistics

- Deploy workers: `corepack pnpm --filter @oracle/workers run deploy` (or Trigger MCP `deploy`). Web deploys via Vercel on push to `main`.
- Prod DB: session pooler string in 1Password (`Supabase DB Direct URL - The Oracle (CURRENT PROD …)` → `oracle_session_pooler`); direct host is IPv6-only. `.env.local` may point at the old project. See `AGENTS.md` §10.
- **Related plan:** `fix_resolve_ts.md` (capability enforcement) shares the capability-check + approved-model invariant — do them together or make this one consume that module.

## 10. Concrete anchors (so you don't have to rediscover them)

- **Settings keys** (table `settings`, JSON values): per-stage selection `default_interview_route` / `default_extraction_route` / `default_synthesis_route` (constants `ROUTE_SETTING_KEYS` in `routes/defaults.ts`); approved pools `model_pool_interview` / `model_pool_extraction` / `model_pool_synthesis` / `model_pool_vision`; aux selections `default_vision_route`, `default_translation_route`, `default_general_purpose_route`; reasoning effort `default_<stage>_reasoning_effort`. The router/region env: `DASHSCOPE_BASE_URL` (set to the intl endpoint in prod), provider keys `DASHSCOPE_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GOOGLE_APPLICATION_CREDENTIALS_JSON`.
- **Where routes resolve today:** `packages/ai/src/routes/from-settings.ts` (`resolveRouteFromSettings`, `resolveAuxiliaryRouteFromSettings`) -> `resolve.ts` (`resolveModelRoute`, `makeSyntheticRoute`). Provider→strategy map is in `resolve.ts` (qwen/deepseek = `tool_call` = LOOSE; vertex/google/openai = `native_json_schema` = STRICT). The pool-chain resolver replaces the single-route return here.
- **The validation-throws fact (critical for verbose-fail AND for any per-claim salvage):** structured output currently THROWS on a schema-invalid response — `vertex-gemini-adapter.ts` `generateObject` calls `tryZodParse(schema, parsed)` which throws (`tryZodParse` in the same file, ~line 1065), so `client.runObject` (`oracle-ai-client.ts` ~line 113) never reaches its `validator.validate(...)`/`receivedJson` path on a hard failure. As part of this refactor, make the dispatch loop catch that, record it verbosely, and advance to the next candidate. Making it **return raw + a failure result instead of throwing** is also the precondition for the per-claim salvage described in `HANDOFF.md` (which was reverted this session precisely because it was unreachable behind the throw). The `verify:r2` smoke (`packages/ai/src/__verify__/oracle-ai-client-smoke.ts`) encodes the current throw/fallback behavior — rewrite it for the new behavior.
- **Full session context:** see `HANDOFF.md` "SESSION-END STATE" — it explains how this was discovered (Qwen vision + extraction both silently fell back to the hard-coded `vertex_gemini_2_5_flash_extraction_primary`), what was committed vs reverted, and the fast interim fix (switch extraction to the strict-JSON `google/gemini-3.1-flash-lite`).
