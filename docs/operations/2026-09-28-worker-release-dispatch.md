# Legacy worker production release — exact dispatch for review

Status: **awaiting independent review** (revision 4). Not executed. Result goes in
§Result below and on tracking issue https://github.com/u2giants/theoracle/issues/50.

Owner request (Albert, Claude chat, 2026-09-28), verbatim: "release the workers";
and "let's put z.ai on hold for now and use the others."

## 1. Target and pinned artifact

- Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`, environment `prod`, config
  `apps/workers/trigger.config.ts`, CLI pinned `trigger.dev@4.5.15`
  (`apps/workers/package.json` `deploy` script).
- Deploy exactly commit **`a12e25e2db6090776f3c2494bcdd36cc77cbcaac`** (`origin/main`
  at review time). This dispatch file lives in a later docs-only commit and is
  deliberately NOT the deployed tree; do not deploy the dispatch commit.
- Operator stops and re-requests review if `origin/main` has moved in
  `apps/workers/**` or `packages/**` beyond `a12e25e`, or if prod is no longer
  `20260909.1` (step 0).

## 2. Live prod state read (read-only, 2026-09-28 ~3:25 PM EDT)

- `get_current_worker` prod: version **`20260909.1`**, SDK `4.5.15`, **25 tasks**:
  brain-synthesis, brain-synthesis-scheduled, business-model-merge, claim-extraction,
  claim-extraction-batch-drain, claim-extraction-batch-submit, claim-translation,
  contradiction-watcher, contradiction-watcher-sweep, document-ingestion,
  document-ingestion-sweep, extraction-ab-eval, lull-interjection,
  macro-relationship-staleness-sweep, model-catalog-refresh-nightly,
  source-workflow-read, taxonomy-reclassification, taxonomy-reevaluation,
  taxonomy-reevaluation-manual, teams-live-recall-utterance,
  teams-subscription-manager, teams-subscription-renew,
  teams-transcript-discovery-scan, teams-transcript-ingestion,
  teams-transcript-summary.
- `list_deploys` prod: current deployment `hfnvqrvg` = `v20260909.1` (commit
  message "chore: add Phase 3 task gates (#9)", i.e. `28e8eb7`).
- Prod env var **names** (management API `GET .../envvars/prod`, 23 names; values
  not read): provider keys present are `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`,
  `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`/`DASHSCOPE_BASE_URL`. **`META_MUSE_API_KEY`,
  `ZAI_API_KEY` and `STEPFUN_API_KEY` are all absent.**
- 24-hour baseline (TRQL on `runs`, prod, ending ~19:25 UTC): all Completed except
  `contradiction-watcher` — 5 Failed (`Failed query: insert into "job_runs"` burst at
  ~00:02 UTC) and 2 Timed out (`MAX_DURATION_EXCEEDED` 60 s); 293 Completed. 7-day
  non-completed runs: only those same two classes. Last
  `model-catalog-refresh-nightly` run `run_06gednh8s80p9uohsqk5i88r01`
  (2026-09-28 07:15 UTC): `ok: true, written: 223, errors: [], unenrichedCount: 110`.
  Last `brain-synthesis-scheduled` and `taxonomy-reevaluation`: Completed today.

## 3. What ships beyond 20260909.1 (`28e8eb7..a12e25e`, exact files)

Worker bundle changes only in these runtime files (full list:
`git diff --stat 28e8eb7 a12e25e -- apps/workers packages`):

- Providers (PR #48): `packages/ai/src/providers/openai-compatible-adapter.ts` (new),
  `packages/ai/src/client/standard-adapters.ts` (+3 `tryAdd`),
  `packages/ai/src/model-capabilities/index.ts` and
  `.../sources/openai-compatible.ts` (3 new catalog sources),
  `packages/ai/src/routes/catalog.ts` (new routes, tier `manual_only_frontier`;
  six production routes unchanged), `routes/resolve.ts`, `routes/types.ts`,
  `usage/usage-normalizer.ts`, `model-capabilities/types.ts`, `index.ts`.
- Retrieval used by worker tasks `teams-live-recall-utterance` and
  `contradiction-watcher` (`apps/workers/src/trigger/contradiction-watcher.ts` imports
  `searchWithRetrievalPlan` and `buildGlobalRetrievalPlan`) (PRs #16, #17):
  `packages/ai/src/retrieval-plan.ts`, `packages/ai/src/retrieval.ts`
  (`buildRetrievalPlanFromQuery`, `searchWithRetrievalPlan`). The same range bumps
  `packages/ai/src/prompts/oracle-system.ts` to `ORACLE_SYSTEM_PROMPT_VERSION` 1.1.0,
  but no worker file imports `ORACLE_SYSTEM_PROMPT` or its version (grep of
  `apps/workers/src`), so that prompt is web-only; its DECISIONS.md record is
  "2026-09-20 — Connected explanations from approved evidence" (prompt v1.1). The Vercel chat has run these modules since
  2026-09-20 (#17), so web is already ahead of workers today.
- Responsibility reader (PR #12): `apps/workers/src/lib/responsibility-reader.ts` —
  the deterministic inventory record is extracted into
  `buildResponsibilitySourceSupportRecord` and now must also pass
  `validateResponsibilityFieldFidelity`. Reached only by task `source-workflow-read`
  (manual; zero runs in the 24 h baseline).
- `apps/workers/trigger.config.ts` excludes `oracle2-run.ts` and `oracle2-project.ts`;
  `@trigger.dev/python` and `@oracle/brain-contracts` added as dependencies, imported
  only by those excluded files. `trigger.oracle2-*.config.ts` are not used here.
- `apps/workers/src/__verify__/**` scripts are outside `dirs: ['./src/trigger']`.

**Unchanged (proved by `git diff --quiet 28e8eb7 a12e25e -- <path>` returning 0):**
`packages/ai/src/prompts/workflow-read.ts` (holds
`RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT`), `apps/workers/src/lib/source-workflow-read.ts`,
`apps/workers/src/trigger/source-workflow-read.ts`, and all of `packages/db` (no
migration in range; highest migrations remain `102_conversation_window_settings.sql`
and `0011_pink_titanium_man.sql`, applied in July). No completion-request or
DB-schema change ships, so no migration step applies.

## 4. Expected production side effects

- **No new provider becomes active.** The three new adapters need keys that prod
  lacks (§2), so `buildStandardAdapters()` skips them and logs
  `[buildStandardAdapters] PROVIDER UNAVAILABLE: "meta_muse" | "zai" | "stepfun" was
  NOT registered ...` via `console.error` wherever adapters are built. That log line
  is expected, not a failure. Z.ai stays on hold as Albert asked. Activating Meta Muse
  or StepFun later is a separate env-var write that Albert must name; this dispatch
  writes no env var.
- **Nightly catalog refresh** (`model-catalog-refresh-nightly`, 07:15 UTC) will
  report exactly three new strings in `errors` and still return `ok: true` (the run
  itself Completes): `Meta Muse: Error: META_MUSE_API_KEY not set`,
  `Z.ai: Error: ZAI_API_KEY not set`, `StepFun: Error: STEPFUN_API_KEY not set`.
  With no key, no rows from those vendors are written; existing providers' rows are
  written as before. Decision: no code guard is added in this release — the strings
  are deterministic, classified here, and fixing them would add a code PR to a
  deploy whose purpose is to ship already-merged code. (Follow-up on #50.)
- **"Use the others" (owner context, not done by this release):** Meta Muse's key
  exists in 1Password ("Meta ai Muse Spark API Key", live-smoked 2026-09-28) but not
  in Trigger prod; StepFun has no key anywhere; Z.ai is on hold (and its stored key has
  no general-endpoint balance). So after this release no new provider is usable by
  background jobs. Enabling Meta Muse needs Albert to name one env-var write
  (`META_MUSE_API_KEY` in Trigger prod) plus a pool selection; StepFun needs a key
  first. Tracked on #50 and reported to Albert.
- **Runtime model selection gate.** Runtime model choice comes from production
  `settings` rows (keys like `model_pool_%`, `default_%`, `%route%`). Read-only check
  at ~3:40 PM EDT 2026-09-28 (session `default_transaction_read_only=on`): 27 rows,
  zero whose primary/fallback names `meta_muse`, `stepfun`, `zai` or `mimo`. Re-run
  at execution (step 0).
- DeepSeek catalog routes ship at tier `manual_only_frontier`; production default
  routes unchanged (asserted locally by `verify:adapter-request-shapes`, §5).

## 5. Gate evidence (recorded 2026-09-28, 3:00–3:30 PM EDT, edge-dev3, tree `a12e25e`)

CI on `a12e25e` (all `success`): PR check run `36466644641`, Oracle 2 contracts
run `36466644750` (self-hosted edge-dev3; runs workers typecheck and
`scripts/oracle2/verify_worker_bundle.mjs`, which asserts the legacy bundle excludes
Oracle 2 tasks), task gates run `36466644723`. `verify:adapter-request-shapes` is
**local-only** (in no workflow).

Local, `corepack pnpm@9.5.0 install --frozen-lockfile`, no `.env.local`, no
`DATABASE_URL`:

| Gate | Result |
|---|---|
| `@oracle/workers typecheck` | pass |
| `verify:source-workflow-read` | pass |
| `verify:document-ingestion-fallback` | pass |
| `verify:r0-reader-validator` | pass |
| `verify:r2-responsibilities` | pass |
| `verify:taxonomy-reclassification` | pass |
| `verify:conversation-windowing` | pass |
| `verify:lull-event-dispatch` | pass |
| `@oracle/ai typecheck` | pass |
| `@oracle/ai verify:adapter-request-shapes` | pass |
| `@oracle/ai verify:retrieval-plan-domain-boundaries` | pass |
| `npx trigger.dev@4.5.15 deploy --env prod --dry-run` | pass; built bundle `environment: prod`, `cliPackageVersion 4.5.15`, 20 entry files all under `src/trigger/`, none `oracle2-*` |

`@oracle/ai verify:retrieval-filter-parity` (the static guard over
`searchWithRetrievalPlan`) also passed locally and in the cited PR check run.

Not run, with reason (this is every remaining worker script in
`apps/workers/package.json`): `verify:r2-pinned-inventory`, `verify:r2-support-contract`,
`verify:shape-segmentation-real` (need the licensed fixture / real documents on `Z:`);
`verify:r2-production-replay`, `verify:r0-production-replay`,
`verify:r2-contract-v2-score`, `verify:r2-first-divergence`,
`verify:r2-fresh-map-score`, `verify:r2-missed-row-diagnosis`,
`verify:taxonomy-reclassification-db`, `audit:taxonomy-reclassification-production`
(need a production DB URL and/or a fresh map id; none of their code paths changed
except the reader, covered below).

§4's predictions (adapters omitted when keys are absent; the three exact catalog
strings; `ok: true`) are verified by code read of `standard-adapters.ts`,
`model-capabilities/index.ts` and `sources/openai-compatible.ts`, not by a gate —
`adapter-request-shapes` sets all three keys before building adapters. **Live probe `verify:r2-completion-contract-live` not run:** it
requires the production database and writes model-run audit rows, and its own rule
(file header; gate G9 in `plan_r2_completion_recovery_cycle.md`) applies to changes in the completion request — which §3 proves
unchanged (`workflow-read.ts`, `source-workflow-read.ts` untouched). The reader change
that does ship (PR #12) is covered by the passing deterministic
`verify:r2-responsibilities` and only runs on a manual `source-workflow-read`, which
this dispatch forbids triggering during the watch.

## 6. Actions (operator)

Credentials: the PAT is read with
`op read 'op://vibe_coding/ylzcsfbhmjyzjy65mnu6uxw67e/Personal Access Token - admin level'`
into `TRIGGER_ACCESS_TOKEN` in the command environment only; never printed, pasted,
logged or committed.

0. **Approval and prod re-read (read-only).** First write into §Result the reviewer
   verdict line, the review run id, and the exact dispatch commit it reviewed (the
   head of branch `claude/worker-release-dispatch-2` passed to `--assert-head`); the
   dispatch file at that commit must equal the one being executed. No APPROVE → stop.
   Trigger reads in steps 0/4/5/6 use the Trigger MCP (`get_current_worker`,
   `list_deploys`, `list_runs`, `query`) for reads only; its pinned CLI version
   (4.4.6 in `.mcp.json`) is never used to deploy.
   Then: `get_current_worker` prod must show `20260909.1` with
   the 25 ids in §2; env names must still lack the three new keys; and the read-only
   settings query
   `SELECT key FROM settings WHERE (key LIKE 'model_pool_%' OR key LIKE 'default_%' OR key LIKE '%route%') AND value::text ~ 'meta_muse|stepfun|zai|mimo'`
   (prod DB via `op read "op://vibe_coding/ntr5ln6tnmsmzxzpyv4q6ohxgy/oracle_session_pooler"`
   as in `docs/deployment.md`, connection option `default_transaction_read_only=on`)
   must return zero rows. Any mismatch → stop, record, re-request review.
1. `git fetch origin` then
   `git diff --quiet a12e25e2db6090776f3c2494bcdd36cc77cbcaac origin/main -- apps/workers packages`
   must exit 0; otherwise stop and re-request review (§1).
   `ai-task-gates check --before deploy` passes. Fresh clean worktree at `a12e25e`
   (`git rev-parse HEAD` = `a12e25e2db6090776f3c2494bcdd36cc77cbcaac`,
   `git status --porcelain` empty, no `.env.local`), `corepack pnpm install
   --frozen-lockfile`.
2. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod --dry-run` must
   succeed. Failure → stop; prod unchanged.
3. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod` (one attempt). This is
   the repo's `pnpm --filter @oracle/workers run deploy` script (`npx trigger.dev@4.5.15
   deploy`) with `--env prod` made explicit.
4. **Failure branches.** Build failure, or built-then-failed-before-promotion (e.g.
   gate G12 in `plan_r2_completion_recovery_cycle.md`, `The "data" argument must be of type string ... Received undefined`):
   prod stays on `20260909.1` (confirm with `get_current_worker`); record and stop.
   No retry, no changed code, no CLI version change.
5. **Verify.** `get_current_worker` prod shows a new version of the form
   `YYYYMMDD.N` dated the deploy day in UTC and not
   `20260909.1`, SDK `4.5.15`, and
   exactly the 25 task ids in §2. Any id missing, any extra id, or any `oracle2-*`
   id → rollback (§7).
6. **Checkpoints** (operator: the executing session; results written to §Result and
   #50 with run ids). Compare each against the §2 baseline:
   - T+30 min: `claim-extraction-batch-drain` (every 10 min) and
     `teams-subscription-renew` (every 30 min) Completed on the new version.
   - Next 4-hour cycle (`0 */4` / `30 */4` UTC): `claim-extraction`,
     `claim-extraction-batch-submit`, `contradiction-watcher-sweep`,
     `document-ingestion-sweep` Completed. `contradiction-watcher` (a consumer of the
     changed retrieval code, 60 s `maxDuration`) is judged by rate against §2 over the
     first 24 h: Timed out ≤ 4 (baseline 2) and `job_runs` insert failures ≤ 10
     (baseline 5), both with no Failed run whose stack names `retrieval.ts` or
     `retrieval-plan.ts`. `macro-relationship-staleness-sweep` has no cron (it
     is dispatched by the sweep and its dispatch failure is only logged), so its
     absence is recorded as "investigate", never a rollback trigger.
   - Next 07:15 UTC `model-catalog-refresh-nightly`: Completed, `ok: true`, and
     `errors` contains the three strings in §4.
   - After close-out, informational only: next `brain-synthesis-scheduled`
     (Mon 06:00 UTC, 2026-10-05) and `taxonomy-reevaluation` (Mon 07:00 UTC) are
     checked and recorded on #50; a failure there opens an investigation and any
     rollback then needs a new review.
   - Run status means the **final** run status; a failed attempt later retried to
     Completed is not a failure.
   - **Rollback trigger (release-attributable only):** `contradiction-watcher`
     exceeding either 24 h rate bound above, or any of its Failed runs with a stack in
     `retrieval.ts` / `retrieval-plan.ts`; a final Failed / Crashed /
     System failure / Timed out run on the new version whose error is not one of the
     §2 baseline classes AND whose stack or message points into a §3 changed file or
     a missing/renamed task or module; or the catalog refresh run itself ending
     Failed / Crashed / Timed out (not `ok: true`).
   - **Investigate, not rollback:** a catalog refresh whose `errors` lacks one of the
     three §4 strings (a key appeared without a reviewed env write), any other new error (e.g. a transient
     `Anthropic:` / `OpenAI:` / `OpenRouter enrichment:` string, a `written` dip
     from a vendor outage), recorded on #50 with run ids.
   - **Watch close-out:** the watch closes when the T+30 min, first 4-hour-cycle,
     first 07:15 UTC and 24 h `contradiction-watcher` rate checkpoints pass. §Result
     must then state the residual risk verbatim: "`teams-live-recall-utterance` and
     `source-workflow-read` (the reader change) are unproven in production until natural
     traffic; no smoke run was authorized." The executing session records the first
     natural run of each on #50 when it occurs.
   - **Issue and handoff stay open** after watch close-out until: the 2026-10-05
     `brain-synthesis-scheduled` / `taxonomy-reevaluation` checks are recorded; the
     catalog error-string guard follow-up and the "use the others" owner ask (§4) each
     have their own open issue; and the release row is recorded in
     `plan_repo_reliability_and_release_gaps.md` STATUS. Only then tick #50 and delete
     the handoff (AGENTS.md §3a).
7. Record result in §Result and #50 (version, deployment id, task count 25), and
   replace the stale "Worker deploy state verified … `20260629.1` with 21 tasks" row in
   `docs/agents/15-pending-work.md` with the new version and 25 tasks.

## 7. Rollback (forward deploy of the old tree)

`trigger.dev promote 20260909.1` and dashboard "Promote" are **refused** by Trigger.dev
for an older deployment (`docs/deployment.md` §Rollback/Workers; verified
2026-08-27). The rollback is a forward deploy of the known-good tree:

1. `git fetch origin`; `git diff --quiet a12e25e2db6090776f3c2494bcdd36cc77cbcaac origin/main -- apps/workers packages`
   must exit 0 (no newer worker code landed, so the old tree un-ships only this
   release); otherwise a new review is required. Then a clean worktree at `28e8eb7`
   (the exact tree of `20260909.1`), `corepack pnpm install --frozen-lockfile`.
2. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod --dry-run`, then
   `npx trigger.dev@4.5.15 deploy --env prod`.
3. Verify `get_current_worker` shows a new version with the 25 ids in §2, then
   watch the next 4-hour cycle as in step 6.

This one rollback deploy is pre-authorized by this dispatch only when a §6 rollback
trigger fires before close-out, and in any case no later than 48 hours after the
release deploy; afterwards, or for a second deploy, or for any other reason, a new
review is required. Owner of the watch and of that decision: the executing session,
then the session named in its `HANDOFF.d` file. Env vars are untouched by release and
rollback alike.

**Web/worker skew on rollback.** Rolling workers back to `28e8eb7` while Vercel
keeps `a12e25e`+ restores exactly today's pre-release state: web has run the #16/#17
retrieval and the 1.1.0 system prompt since 2026-09-20 while workers ran `28e8eb7`.
Workers never stamp `ORACLE_SYSTEM_PROMPT_VERSION` (no import in `apps/workers/src`),
so the database audit trail is unaffected; web stays as is and needs no revert.

## Result

_Not executed._ Fields to fill: reviewer verdict line + review run id + reviewed
dispatch commit; step 0 reads; dry run; deploy result, version, deployment id; each
checkpoint with run ids; residual-risk statement; owner answer on "use the others"
(activate Meta Muse in Trigger prod: yes/no, asked on #50).
