# Legacy worker production release — exact dispatch for review

Status: **awaiting independent review** (revision 5). Not executed. Result goes in
§Result below and on tracking issue https://github.com/u2giants/theoracle/issues/50.

Owner request (Albert, Claude chat, 2026-09-28), verbatim: "release the workers";
and "let's put z.ai on hold for now and use the others."

Revision 5 re-pins to the new `origin/main` (`1ab6d0c`, which adds the #51 adapter
fix) and reflects that the separately reviewed provider-key dispatch
(`docs/operations/2026-09-28-provider-keys-dispatch.md`, #49) has already written
`META_MUSE_API_KEY` and `STEPFUN_API_KEY` into Trigger prod. This release is what makes
those keys take effect in background jobs.

## 1. Target and pinned artifact

- Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`, environment `prod`, config
  `apps/workers/trigger.config.ts`, CLI pinned `trigger.dev@4.5.15`.
- Deploy exactly commit **`1ab6d0cd1abbba8fb17791364a28e7237c88880f`** (`1ab6d0c`,
  `origin/main` at review time).
  This dispatch file lives on branch `claude/worker-release-dispatch-2` (a docs-only
  commit on top of it) and is NOT the deployed tree.
- Stop and re-request review if `origin/main` has moved in `apps/workers/**` or
  `packages/**` beyond the pinned commit (step 1), or prod is no longer `20260909.1`
  (step 0).

## 2. Live prod state read (read-only, 2026-09-28, 3:25–4:30 PM EDT)

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
  teams-transcript-summary. Current deployment `hfnvqrvg` (`28e8eb7`).
- Prod env var **names** (Trigger management API `GET
  /api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod`, names only), re-read
  ~4:25 PM EDT: 25 names; includes `META_MUSE_API_KEY` and `STEPFUN_API_KEY`
  (written by #49); **`ZAI_API_KEY` absent** (Z.ai on hold); no `*_BASE_URL` for the
  three vendors.
- Prod DB (SELECT-only, ~4:25 PM EDT): 27 model-selection `settings` rows
  (`model_pool_%`, `default_%`, `%route%`), **0** whose value mentions
  `meta_muse|stepfun|zai|mimo`, so no stage routes to a new provider after release;
  `map_directed_extraction_enabled = true`, `require_workflow_map_for_ingestion =
  false`; 0 documents created in the last 7 days; `source_workflow_maps` in 30 days:
  1 degraded, 1 superseded.
- 24 h run baseline (TRQL on `runs`, ending ~19:25 UTC): all Completed except
  `contradiction-watcher` — 5 Failed (`Failed query: insert into "job_runs"`, one burst
  at ~00:02 UTC) and 2 Timed out (`MAX_DURATION_EXCEEDED`, 60 s); 293 Completed. 7-day
  non-completed runs: only those two classes. Last `model-catalog-refresh-nightly`
  run `run_06gednh8s80p9uohsqk5i88r01`: `ok: true, written: 223, errors: []`.

## 3. What ships beyond 20260909.1 (`28e8eb7..1ab6d0c`, exact runtime files)

- **Providers (PRs #48, #51):** `packages/ai/src/providers/openai-compatible-adapter.ts`
  (new; #51 adds lenient JSON parsing and one retry for off-schema replies),
  `client/standard-adapters.ts` (+3 `tryAdd`), `model-capabilities/index.ts` and
  `sources/openai-compatible.ts` (3 catalog sources), `routes/catalog.ts` (new routes
  at tier `manual_only_frontier`; six production routes unchanged), `routes/resolve.ts`,
  `routes/types.ts`, `usage/usage-normalizer.ts`, `model-capabilities/types.ts`,
  `index.ts`.
- **Retrieval (PRs #16, #17):** `packages/ai/src/retrieval-plan.ts`,
  `packages/ai/src/retrieval.ts`. Worker consumers: `teams-live-recall-utterance` and
  `contradiction-watcher` (imports `searchWithRetrievalPlan`,
  `buildGlobalRetrievalPlan`). The same range bumps `prompts/oracle-system.ts` to
  1.1.0 (DECISIONS.md "2026-09-20 — Connected explanations from approved evidence"),
  but no file in `apps/workers/src` imports `ORACLE_SYSTEM_PROMPT` or its version, so
  that prompt is web-only. Vercel has run this retrieval since 2026-09-20.
- **Responsibility reader (PR #12):** `apps/workers/src/lib/responsibility-reader.ts` —
  the deterministic inventory record (`buildResponsibilitySourceSupportRecord`) must
  now also pass `validateResponsibilityFieldFidelity`, so a record failing fidelity is
  no longer emitted as a deterministic fallback; that seed stays unclaimed (it can only
  be covered by an accepted model record). Net effect: fewer, but fidelity-valid,
  deterministic rows.
  Reached by task `source-workflow-read` **and by every `document-ingestion`** because
  `map_directed_extraction_enabled` is true in prod (`document-ingestion.ts` →
  `generateSourceWorkflowMap` → `completeAndMatchResponsibilityInventory`).
- `apps/workers/trigger.config.ts` excludes `oracle2-run.ts` and `oracle2-project.ts`;
  new deps `@trigger.dev/python` and `@oracle/brain-contracts` are imported only by
  those files. `apps/workers/src/__verify__/**` is outside `dirs: ['./src/trigger']`.

**Unchanged** (`git diff --quiet 28e8eb7 1ab6d0c -- <path>` exits 0):
`packages/ai/src/prompts/workflow-read.ts` (`RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT`),
`apps/workers/src/lib/source-workflow-read.ts`, `apps/workers/src/trigger/**` except
the two excluded oracle2 files, and all of `packages/db` (no migration in range).

## 4. Expected production side effects

- **Meta Muse and StepFun adapters register** in every worker (keys present). No
  stage uses them (0 settings rows name them, §2); they become selectable in admin
  pools. `buildStandardAdapters()` logs `PROVIDER UNAVAILABLE: "zai" ...` via
  `console.error` — expected, not a failure.
- **Nightly catalog refresh** (07:15 UTC) will call the Meta Muse and StepFun
  `/models` endpoints and write their chat models into `model_capabilities`
  (production data; rows are selectable, not used). `errors` will contain
  `Z.ai: Error: ZAI_API_KEY not set`; the run still returns `ok: true`.
- **"Use the others":** after this release Meta Muse and StepFun are available to
  background jobs once an admin selects them in a pool; that selection is Albert's
  call and is not made here (asked on #50). Z.ai stays on hold.
- **Reader change exposure:** each new document ingestion runs the changed reader. A
  deterministic fallback record failing fidelity is now dropped instead of emitted. The completion request itself is unchanged (§3).

## 5. Gate evidence (2026-09-28, edge-dev3)

Pinned commit `1ab6d0cd1abbba8fb17791364a28e7237c88880f`; CI on it: PR check run `36478923230` success, Oracle 2 contracts
run `36478923547` success (self-hosted; workers typecheck + legacy worker-bundle
guard), task gates run `36478923228` success.

Local on tree `1ab6d0c`, `corepack pnpm@9.5.0 install --frozen-lockfile`, no
`.env.local`, no `DATABASE_URL` (all pass, ~4:10–4:25 PM EDT): workers `typecheck`,
`verify:source-workflow-read`, `verify:document-ingestion-fallback`,
`verify:r0-reader-validator`, `verify:r2-responsibilities`,
`verify:taxonomy-reclassification`, `verify:conversation-windowing`,
`verify:lull-event-dispatch`; ai `typecheck`, `verify:adapter-request-shapes`,
`verify:retrieval-plan-domain-boundaries`, `verify:retrieval-filter-parity`;
`npx trigger.dev@4.5.15 deploy --env prod --dry-run` (bundle `environment: prod`,
`cliPackageVersion 4.5.15`, 20 entry files all under `src/trigger/`, none `oracle2-*`).

**Reader guard against production data:** `verify:r2-production-replay` (SELECT-only;
replays the 93 stored production responsibility records of map
`37a8fc62-23e4-46b7-8464-d1c784dc73cd` through the current reader) **passed** on
`1ab6d0c`: `preservedRows 19`, `regressedRows []`, `recordLevelRegressions []`,
`recoveredRows [17, 19, 29]`, `replayMatched 22`, replay sha256
`d0e18a997753f116d07b8e0c5ea56f94ea24d8b5818ff6fd3a5e4c26050c7c85`.

Not run, with reason (all remaining `verify:*` / `audit:*` scripts in
`apps/workers/package.json`): `verify:r2-pinned-inventory`, `verify:r2-support-contract`,
`verify:shape-segmentation-real` need the licensed source file on the Windows `Z:`
share, absent on this machine; `verify:r2-contract-v2-score`,
`verify:r2-first-divergence`, `verify:r2-fresh-map-score`,
`verify:r2-missed-row-diagnosis` need a freshly produced map id (a production map
write); `verify:r0-production-replay`, `verify:taxonomy-reclassification-db`,
`audit:taxonomy-reclassification-production` cover code this range does not change.
`verify:r2-completion-contract-live` is required by its own header and by gate G9 in
`plan_r2_completion_recovery_cycle.md` for changes to the completion request, which
§3 proves unchanged; it also writes production audit rows, so it is not run.

§4's predictions are verified by code read (`standard-adapters.ts`,
`model-capabilities/index.ts`, `sources/openai-compatible.ts`) plus the §2 env-name
read, not by a gate.

## 6. Actions (operator)

Credentials (never printed, pasted, logged or committed; values only in the shell
environment):
`export TRIGGER_ACCESS_TOKEN="$(op read 'op://vibe_coding/ylzcsfbhmjyzjy65mnu6uxw67e/Personal Access Token - admin level')"`
and, for the DB read,
`export U="$(op read 'op://vibe_coding/qcuyabwseaptvuzvtjejffi2ou/oracle_session_pooler')"`.

0. **Approval and prod re-read (read-only).** First write into §Result the reviewer
   verdict line, review run id and the dispatch commit it reviewed; the dispatch at
   that commit must equal the one being executed; no APPROVE → stop. Trigger reads in
   steps 0/4/5/6 use the Trigger MCP (`get_current_worker`, `list_deploys`,
   `list_runs`, `query`) for reads only; its 4.4.6 CLI is never used to deploy. Env
   names come from the management API with the PAT:
   `GET https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod`
   (print names only). Then require:
   - worker `20260909.1` with the 25 ids in §2;
   - env names include `META_MUSE_API_KEY`, `STEPFUN_API_KEY`, and not `ZAI_API_KEY`;
   - inside `BEGIN TRANSACTION READ ONLY` (the pooler ignores the
     `default_transaction_read_only` connection option — observed), `SELECT key FROM
     settings WHERE (key LIKE 'model_pool_%' OR key LIKE 'default_%' OR key LIKE
     '%route%') AND value::text ~ 'meta_muse|stepfun|zai|mimo'` returns 0 rows.
   Any mismatch → stop, record, re-request review.
1. `git fetch origin`; `git diff --quiet 1ab6d0c origin/main -- apps/workers packages`
   exits 0, else stop. `ai-task-gates check --before deploy` passes. Fresh clean
   worktree at `1ab6d0c` (`git status --porcelain` empty, no `.env.local`, no `.env`),
   `corepack pnpm install --frozen-lockfile`; record the full SHA.
2. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod --dry-run` succeeds
   and its `build.json` shows `environment: prod`, `cliPackageVersion 4.5.15`, 20
   entry files all under `src/trigger/`, none `oracle2-*`. Else stop; prod unchanged.
3. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod`, one attempt (the
   repo `deploy` script with `--env prod` explicit).
4. **Failure branches.** Build failure, or built-then-failed-before-promotion (gate
   G12 in `plan_r2_completion_recovery_cycle.md`): prod stays `20260909.1` (confirm);
   record and stop. No retry, no code change, no CLI change.
5. **Verify.** `get_current_worker` prod: new version `YYYYMMDD.N` for the deploy's
   UTC date, not `20260909.1`; SDK `4.5.15`; exactly the 25 ids in §2. Missing, extra,
   or `oracle2-*` id → rollback (§7). Runs already queued or retrying finish on the
   version they started; judge each run by its own version and final status.
6. **Checkpoints** (owner: the executing session, then the session named in its
   `HANDOFF.d` file; each recorded with run ids in §Result and on #50):
   - T+30 min: `claim-extraction-batch-drain` and `teams-subscription-renew`
     Completed on the new version.
   - First 4-hour cycle: `claim-extraction`, `claim-extraction-batch-submit`,
     `contradiction-watcher-sweep`, `document-ingestion-sweep` Completed.
     `macro-relationship-staleness-sweep` has no cron; its absence is "investigate".
   - First 24 h, `contradiction-watcher` (retrieval consumer) on the new version:
     Timed out ≤ 4 (baseline 2) and no Failed run whose stack names `retrieval.ts` or
     `retrieval-plan.ts`. `job_runs` insert failures are recorded, not judged: they are
     a database-side burst unrelated to this code.
   - First 07:15 UTC `model-catalog-refresh-nightly`: Completed, `ok: true`, `errors`
     includes the Z.ai string; record `written` and any Meta Muse / StepFun rows.
   - **Document ingestion:** for the first `document-ingestion` run on the new
     version (whenever a document arrives; none in the last 7 days), record the map
     status and whether `[document-ingestion] SOURCE WORKFLOW READ FAILED` was logged.
   - After watch close-out, informational: 2026-10-05 `brain-synthesis-scheduled`
     (06:00 UTC) and `taxonomy-reevaluation` (07:00 UTC) recorded on #50.
   - **Rollback trigger (release-attributable only):** a final Failed / Crashed /
     System failure / Timed out run on the new version whose error is not a §2
     baseline class and whose stack or message points into a §3 file or a missing
     task/module; `contradiction-watcher` breaking its 24 h bound; the catalog
     refresh run itself not Completed; the first document ingestion Failing or
     logging `SOURCE WORKFLOW READ FAILED` with a stack in `responsibility-reader.ts`.
   - **Investigate, not rollback:** anything else new (e.g. a transient vendor string
     in catalog `errors`, a Muse/StepFun `/models` error, a `written` dip, a degraded
     map without a reader stack) — recorded on #50 with run ids.
   - **Watch close-out** when T+30 min, first 4-hour cycle, 24 h `contradiction-watcher`
     and first 07:15 UTC checkpoints pass. §Result then states verbatim: "Retrieval in
     `teams-live-recall-utterance` and the reader in `document-ingestion` /
     `source-workflow-read` are unproven in production until natural traffic; the
     first natural run of each is recorded on #50."
   - **#50 and the handoff stay open** until the first document-ingestion checkpoint
     and the 2026-10-05 checks are recorded, the "use the others" pool question has an
     answer or its own issue, and the release row is added to
     `plan_repo_reliability_and_release_gaps.md` STATUS. Then tick #50 and delete the
     handoff (AGENTS.md §3a).
7. Record the result in §Result and #50 (version, deployment id, 25 tasks), replace
   the stale "Worker deploy state verified … `20260629.1` with 21 tasks" row in
   `docs/agents/15-pending-work.md`, and land this file's §Result on `main` in a
   docs-only PR (squash-merged per repository policy) so the record is on `main`.

## 7. Rollback (forward deploy of the old tree)

`trigger.dev promote 20260909.1` and dashboard "Promote" are **refused** for an older
deployment (`docs/deployment.md` §Rollback/Workers). The rollback is a forward deploy:

1. `git fetch origin`; `git diff --quiet 1ab6d0c origin/main -- apps/workers packages`
   must exit 0 (else a new review is required). Clean worktree at `28e8eb7` (the exact
   tree of `20260909.1`), `corepack pnpm install --frozen-lockfile`.
2. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod --dry-run`, then
   `npx trigger.dev@4.5.15 deploy --env prod`.
3. Verify a new version with the 25 ids in §2; watch the next 4-hour cycle as in 6.

Pre-authorized only when a §6 rollback trigger fires before watch close-out and no
later than 48 hours after the release deploy; otherwise a new review. Env vars are not
touched. After rollback the old worker ignores the two new keys (it has no adapters
for them), which is the pre-release state.

**Web/worker skew on rollback.** Vercel keeps `1ab6d0c`+ while workers return to
`28e8eb7` — exactly today's pre-release state (web has run #16/#17 retrieval and
prompt 1.1.0 since 2026-09-20). Workers never stamp `ORACLE_SYSTEM_PROMPT_VERSION`,
so the audit trail is unaffected and web needs no revert.

## Result

_Not executed._ Fields: reviewer verdict line, review run id, reviewed dispatch
commit; pinned full SHA; step 0 reads; dry run; deploy result, version, deployment
id; each checkpoint with run ids; residual-risk statement; owner answer on selecting
Meta Muse / StepFun in a pool (asked on #50).
