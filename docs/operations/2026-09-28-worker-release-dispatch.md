# Legacy worker production release — exact dispatch for review

Status: **awaiting independent review** (revision 7). Not executed. Tracking issue:
https://github.com/u2giants/theoracle/issues/50. Nothing here runs before a
approving review (a `## Verdict` heading followed by `APPROVE`) whose record names the reviewed commit of this file. The approval
record and every execution result are posted on #50; this file is never edited
during execution, so the executed text is exactly the reviewed text.

Owner request (Albert, Claude chat, 2026-09-28), verbatim: "release the workers";
and "let's put z.ai on hold for now and use the others."

Context: the reviewed provider-key dispatch
(`docs/operations/2026-09-28-provider-keys-dispatch.md`, #49) already wrote
`META_MUSE_API_KEY` and `STEPFUN_API_KEY` into Trigger prod, and #54 widened the
`model_capabilities` provider CHECK in prod. This release is what makes Meta Muse and
StepFun available to background jobs. Which model each stage uses stays Albert's
choice on the admin settings page; this release does not depend on it.

## 1. Target and pinned artifact

- Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`, environment `prod`, config
  `apps/workers/trigger.config.ts`, CLI pinned `trigger.dev@4.5.15`.
- Deploy exactly commit **`5a441199925d0ddb5a76374f44b8c3243a303214`** (`5a44119`,
  `origin/main` at review time). This dispatch lives in docs-only commits on branch
  `claude/worker-release-dispatch-2` above that commit and is NOT the deployed tree.
- Stop and re-request review if `origin/main` has moved in `apps/workers/**` or
  `packages/**` beyond the pinned commit (§6 step 2), or prod is no longer `20260909.1`
  (§6 step 1).

## 2. Live prod state read (read-only, 2026-09-28, 3:25–5:15 PM EDT)

- `get_current_worker` prod (re-read ~5:10 PM EDT): version **`20260909.1`**, SDK
  `4.5.15`, **25 tasks**: brain-synthesis, brain-synthesis-scheduled,
  business-model-merge, claim-extraction, claim-extraction-batch-drain,
  claim-extraction-batch-submit, claim-translation, contradiction-watcher,
  contradiction-watcher-sweep, document-ingestion, document-ingestion-sweep,
  extraction-ab-eval, lull-interjection, macro-relationship-staleness-sweep,
  model-catalog-refresh-nightly, source-workflow-read, taxonomy-reclassification,
  taxonomy-reevaluation, taxonomy-reevaluation-manual, teams-live-recall-utterance,
  teams-subscription-manager, teams-subscription-renew,
  teams-transcript-discovery-scan, teams-transcript-ingestion,
  teams-transcript-summary. Current deployment `hfnvqrvg` (`28e8eb7`).
- Env var **names** (Trigger management API, names only, ~5:10 PM EDT): 25 names,
  including `META_MUSE_API_KEY` and `STEPFUN_API_KEY`; **`ZAI_API_KEY` absent** (on
  hold); no `*_BASE_URL` for the three vendors.
- Prod DB, inside a `READ ONLY` transaction (`transaction_read_only = on` confirmed),
  ~5:10 PM EDT:
  - `model_capabilities_provider_check` = `CHECK (provider = ANY (ARRAY['anthropic',
    'openai','google','deepseek','qwen','meta_muse','zai','stepfun']))` — #54 applied.
  - `model_capabilities` rows by provider: anthropic 15, deepseek 4, google 42,
    openai 77, qwen 145 (no Muse/StepFun rows yet).
  - Model-selection `settings` rows (`model_pool_%`, `default_%`, `%route%`): 27; rows
    whose value matches `meta_muse|stepfun|zai|mimo|muse-spark|step-5|glm-`: **0**.
  - Earlier read (~4:25 PM EDT): `map_directed_extraction_enabled = true`,
    `require_workflow_map_for_ingestion = false`; 0 documents created in 7 days.
- 24 h run baseline (TRQL on `runs`, ending ~19:25 UTC): all Completed except
  `contradiction-watcher` — 5 Failed (`Failed query: insert into "job_runs"`, one burst
  at ~00:02 UTC) and 2 Timed out (`MAX_DURATION_EXCEEDED`, 60 s); 293 Completed. 7-day
  non-completed runs: only those two classes. Last `model-catalog-refresh-nightly`
  run `run_06gednh8s80p9uohsqk5i88r01`: `ok: true, written: 223, errors: []`.

## 3. What ships beyond 20260909.1 (`28e8eb7..5a44119`, exact runtime files)

- **Providers (PRs #48, #51, #53):** `packages/ai/src/providers/openai-compatible-adapter.ts`
  (new; #51 lenient JSON + one retry), `client/standard-adapters.ts` (+3 `tryAdd`),
  `model-capabilities/index.ts` (3 sources; #53 fixes infinite recursion in
  `lookupEnrichment` for the self-aliased `stepfun` prefix),
  `model-capabilities/sources/openai-compatible.ts`, `routes/catalog.ts` (new routes at
  tier `manual_only_frontier`, including two Z.ai eval routes `zai_glm_5_3_synthesis_eval`
  and `zai_glm_5_3_flash_extraction_eval`; six production routes unchanged), `routes/resolve.ts`,
  `routes/types.ts`, `usage/usage-normalizer.ts`, `model-capabilities/types.ts`,
  `index.ts`.
- **Retrieval (PRs #16, #17):** `packages/ai/src/retrieval-plan.ts`,
  `packages/ai/src/retrieval.ts`. Worker consumers: `teams-live-recall-utterance` and
  `contradiction-watcher` (`searchWithRetrievalPlan`, `buildGlobalRetrievalPlan`). The
  range also bumps `prompts/oracle-system.ts` to 1.1.0 (DECISIONS.md "2026-09-20 —
  Connected explanations from approved evidence"); no file in `apps/workers/src`
  imports it, so it is web-only. Vercel has run this retrieval since 2026-09-20.
- **Responsibility reader (PR #12):** `apps/workers/src/lib/responsibility-reader.ts` —
  a deterministic fallback record (`buildResponsibilitySourceSupportRecord`) must now
  also pass `validateResponsibilityFieldFidelity`; one that fails is dropped instead of
  emitted. Reached by `source-workflow-read` **and every `document-ingestion`**
  (map-directed extraction is on: `document-ingestion.ts` → `generateSourceWorkflowMap`
  → `completeAndMatchResponsibilityInventory`).
- **Database:** only `packages/db/migrations/sql/56_model_capabilities_more_providers.sql`
  (the #54 CHECK widening) and its README row; already applied in prod (§2). No other
  migration in range; no migration step in this dispatch.
- `apps/workers/trigger.config.ts` excludes `oracle2-run.ts` and `oracle2-project.ts`;
  new deps `@trigger.dev/python` and `@oracle/brain-contracts` are imported only by
  them. `apps/workers/src/__verify__/**` is outside `dirs: ['./src/trigger']`.

**Unchanged** (`git diff --quiet 28e8eb7 5a44119 -- <path>` exits 0):
`packages/ai/src/prompts/workflow-read.ts` (`RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT`),
`apps/workers/src/lib/source-workflow-read.ts`, and `apps/workers/src/trigger/**`
except the two excluded oracle2 files.

## 4. Expected production side effects

- **Meta Muse and StepFun adapters register** in every worker. No stage selects them
  (§2), so no job changes model until someone selects them on the settings page.
  `buildStandardAdapters()` logs `PROVIDER UNAVAILABLE: "zai" ...` via `console.error`
  — expected.
- **Z.ai hold:** the two Z.ai eval routes and `zai/*` ids become visible in code but
  cannot dispatch (no `ZAI_API_KEY`, so no adapter; a stage pointed at one falls back
  with the `PROVIDER UNAVAILABLE` log). The hold is kept by the key's absence, checked
  at §6 step 1 and re-checked in the watch (§6 step 7).
- **Nightly catalog refresh** (07:15 UTC) will list Meta Muse and StepFun `/models`
  and upsert their chat models into `model_capabilities` (now allowed by the CHECK);
  `errors` will contain `Z.ai: Error: ZAI_API_KEY not set`; the run returns `ok: true`.
- **Reader change:** each new document ingestion runs the changed reader; a
  deterministic fallback record failing fidelity is dropped. The completion request is
  unchanged (§3).

## 5. Gate evidence (2026-09-28, 4:55–5:15 PM EDT, edge-dev3, tree `5a44119`)

CI on `5a441199925d0ddb5a76374f44b8c3243a303214`: PR check run `36484270691` success,
Oracle 2 contracts run `36484270622` success (self-hosted; workers typecheck + legacy
worker-bundle guard), task gates run `36484270628` success.

Local, `corepack pnpm@9.5.0 install --frozen-lockfile`, no `.env.local`, no
`DATABASE_URL`, all pass: workers `typecheck`, `verify:source-workflow-read`,
`verify:document-ingestion-fallback`, `verify:r0-reader-validator`,
`verify:r2-responsibilities`, `verify:taxonomy-reclassification`,
`verify:conversation-windowing`, `verify:lull-event-dispatch`; ai `typecheck`,
`verify:adapter-request-shapes`, `verify:retrieval-plan-domain-boundaries`,
`verify:retrieval-filter-parity`; `npx trigger.dev@4.5.15 deploy --env prod --dry-run`
(bundle `environment: prod`, `cliPackageVersion 4.5.15`, 20 entry files all under
`src/trigger/`, none `oracle2-*`).

**Reader guard on production data:** `verify:r2-production-replay` (SELECT-only; the 93
stored production records of map `37a8fc62-23e4-46b7-8464-d1c784dc73cd` through the
current reader) passed on `5a44119`: `preservedRows 19`, `regressedRows []`,
`recordLevelRegressions []`, `replayMatched 22`, replay sha256
`d0e18a997753f116d07b8e0c5ea56f94ea24d8b5818ff6fd3a5e4c26050c7c85`.

Not run, with reason (every other `verify:*` / `audit:*` script in
`apps/workers/package.json`): `verify:r2-pinned-inventory`, `verify:r2-support-contract`,
`verify:shape-segmentation-real` need the licensed file on the Windows `Z:` share, not
on this machine; `verify:r2-contract-v2-score`, `verify:r2-first-divergence`,
`verify:r2-fresh-map-score`, `verify:r2-missed-row-diagnosis` need a freshly produced
map (a production write); `verify:r0-production-replay`,
`verify:taxonomy-reclassification-db`, `audit:taxonomy-reclassification-production`
cover unchanged code. `verify:r2-completion-contract-live` applies (its header; gate
G9 in `plan_r2_completion_recovery_cycle.md`) to completion-request changes, which §3
proves absent, and writes production audit rows, so it is not run.

§4's predictions are verified by code read plus the §2 reads, not by a gate.

## 6. Actions (operator)

Rules: run each command separately and check its exit status; secrets only in the
shell environment, never printed, pasted, logged or committed:
`export TRIGGER_ACCESS_TOKEN="$(op read 'op://vibe_coding/ylzcsfbhmjyzjy65mnu6uxw67e/Personal Access Token - admin level')"`;
for DB reads `export U="$(op read 'op://vibe_coding/qcuyabwseaptvuzvtjejffi2ou/oracle_session_pooler')"`,
consumed by a short Node script run from `packages/db` (which has the `postgres`
package): `postgres(process.env.U, { max: 1, prepare: false })` and every query inside
`sql.begin('read only', ...)`, printing only keys, counts and the constraint text.
Trigger reads use the Trigger MCP (`get_current_worker`, `list_deploys`, `list_runs`,
`query`) for reads only; its 4.4.6 CLI never deploys. Every result below is posted on
#50 with run ids.

0. **Gates and approval record.**
   `ai-task-gates start --class deployment --base origin/main`, then
   `ai-task-gates check --before deploy`; stop on anything but pass. Post on #50 the
   reviewed commit of this file, the approving review record's file name and its
   `## Verdict` / `APPROVE` lines; `git show <reviewed commit>:docs/operations/2026-09-28-worker-release-dispatch.md`
   must equal the operator's copy. No APPROVE → stop.
1. **Prod re-read (read-only).**
   - `get_current_worker` prod: `20260909.1`, the 25 ids in §2.
   - Env names (management API `GET
     https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod`,
     print names only): include `META_MUSE_API_KEY`, `STEPFUN_API_KEY`; exclude
     `ZAI_API_KEY`.
   - In `BEGIN TRANSACTION READ ONLY` (the pooler ignores a
     `default_transaction_read_only` connection option): the CHECK in §2 includes
     `meta_muse` and `stepfun`; and `SELECT key FROM settings WHERE (key LIKE
     'model_pool_%' OR key LIKE 'default_%' OR key LIKE '%route%') AND value::text ~
     'meta_muse|stepfun|zai|mimo|muse-spark|step-5|glm-'` returns 0 rows. (If it
     returns rows because Albert has since selected Muse/StepFun, record them on #50
     and continue only for `meta_muse`/`stepfun` rows; any `zai`/`glm-` row → stop.)
   Any other mismatch → stop, post, re-request review.
2. `git fetch origin`; `git diff --quiet 5a441199925d0ddb5a76374f44b8c3243a303214 origin/main -- apps/workers packages`
   exits 0, else stop. Fresh clean worktree at the pinned commit (`git status
   --porcelain` empty, no `.env.local`, no `.env`), `corepack pnpm install
   --frozen-lockfile`.
3. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod --dry-run` succeeds
   and `.trigger/tmp/*/build.json` shows `environment: prod`, `cliPackageVersion
   4.5.15`, 20 entry files all under `src/trigger/`, none `oracle2-*`. Else stop.
4. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod`, one attempt (the
   repo `deploy` script with `--env prod` explicit).
5. **Failure branches.** Build failure, or built-then-failed-before-promotion (gate
   G12 in `plan_r2_completion_recovery_cycle.md`): prod stays `20260909.1` (confirm);
   post and stop. No retry, no code change, no CLI change.
6. **Verify.** `get_current_worker` prod: new version `YYYYMMDD.N` for the deploy's
   UTC date, not `20260909.1`; SDK `4.5.15`; exactly the 25 ids in §2. Missing, extra
   or `oracle2-*` id → rollback (§7). Runs already queued or retrying finish on the
   version they started; judge each run by its own version and final status.
7. **Checkpoints** (owner: the executing session, then the session named in its
   `HANDOFF.d` file):
   - T+30 min: `claim-extraction-batch-drain`, `teams-subscription-renew` Completed on
     the new version.
   - First 4-hour cycle: `claim-extraction`, `claim-extraction-batch-submit`,
     `contradiction-watcher-sweep`, `document-ingestion-sweep` Completed.
     `macro-relationship-staleness-sweep` has no cron; its absence is "investigate".
   - First 24 h `contradiction-watcher` (retrieval consumer): Timed out ≤ 4 (baseline
     2) and no Failed run whose stack names `retrieval.ts` / `retrieval-plan.ts`.
     `job_runs` insert failures are recorded, not judged (database-side burst).
   - First 07:15 UTC `model-catalog-refresh-nightly`: Completed, `ok: true`, `errors`
     includes the Z.ai string; record `written` and the Muse/StepFun row counts.
   - First `document-ingestion` run on the new version (whenever a document arrives):
     map status and whether `[document-ingestion] SOURCE WORKFLOW READ FAILED` was
     logged.
   - At the 24 h and 07:15 UTC checkpoints, repeat the §6 step 1 env-name and settings
     reads: still no `ZAI_API_KEY` and no `zai`/`glm-` settings row (else post on #50
     for Albert; not a rollback trigger).
   - Informational: 2026-10-05 `brain-synthesis-scheduled` (06:00 UTC) and
     `taxonomy-reevaluation` (07:00 UTC).
   - **Rollback trigger (release-attributable only):** a final Failed / Crashed /
     System failure / Timed out run on the new version whose error is not a §2
     baseline class and whose stack or message points into a §3 file or a missing
     task/module; `contradiction-watcher` breaking its 24 h bound; the catalog refresh
     run itself not Completed; the first document ingestion Failing, or logging
     `SOURCE WORKFLOW READ FAILED` with a stack in `responsibility-reader.ts`.
   - **Investigate, not rollback:** anything else new (a transient vendor string in
     catalog `errors`, a Muse/StepFun `/models` error, a `written` dip, a degraded map
     without a reader stack).
   - **Watch ownership:** the executing session owns the watch. If it ends before the
     #50 conditions below are met, it writes its own `HANDOFF.d` file naming #50 and the
     remaining checkpoints, and any session that then claims #50 (by comment) owns the
     watch and the rollback decision.
   - **Watch close-out** when the T+30 min, first 4-hour, 24 h `contradiction-watcher`
     and first 07:15 UTC checkpoints pass. The #50 close-out comment states verbatim:
     "Retrieval in `teams-live-recall-utterance` and the reader in `document-ingestion` /
     `source-workflow-read` are unproven in production until natural traffic; the first
     natural run of each is recorded on #50."
   - **#50 and the handoff stay open** until the first document-ingestion checkpoint
     and the 2026-10-05 checks are recorded and the release row is added to
     `plan_repo_reliability_and_release_gaps.md` STATUS; then tick #50 and delete the
     handoff (AGENTS.md §3a).
8. **Records.** In a docs-only PR after execution (squash-merged under Albert's
   standing instruction for prose-only PRs, as recorded in
   `plan_oracle_consultant_overhaul.md` §Git): set this file's `Status:` line to executed with a pointer to the #50
   result comment (the only edit ever made to this file), and replace the stale
   "Worker deploy state verified … `20260629.1` with 21 tasks" row in
   `docs/agents/15-pending-work.md` with the new version and 25 tasks.

## 7. Rollback (forward deploy of the old tree)

`trigger.dev promote 20260909.1` and dashboard "Promote" are **refused** for an older
deployment (`docs/deployment.md` §Rollback/Workers). The rollback is a forward deploy:

1. `get_current_worker` prod must show the version this release created (posted on #50
   at §6 step 6) — i.e. no later worker deploy has happened, so deploying `28e8eb7`
   un-ships exactly this release whatever `origin/main` contains by then. Any other
   version → a new review is required. Clean worktree at `28e8eb7` (the exact
   tree of `20260909.1`), `corepack pnpm install --frozen-lockfile`.
2. From `apps/workers`: `npx trigger.dev@4.5.15 deploy --env prod --dry-run`, then
   `npx trigger.dev@4.5.15 deploy --env prod`.
3. Verify a new version with the 25 ids in §2. Post-rollback watch: the next T+30 min
   and 4-hour-cycle checkpoints of §6 step 7, judged against the §2 baseline only (no
   §3 attribution applies to the old tree); any new failure → post on #50 and stop for
   a new review.

**Authorization window.** This one rollback deploy is pre-authorized when a §6 step 7
rollback trigger fires: within 48 hours of the release deploy for the run-based
triggers, and for the document-ingestion trigger at the first document-ingestion run
on the new version provided it occurs within 14 days of the release deploy. Outside
those windows, for a second deploy, or for any other reason, a new review is required.
Env vars and the CHECK are not touched: the old worker has no Muse/StepFun adapters
and ignores the keys; the wider CHECK only permits extra values.

**Web/worker skew on rollback.** Vercel keeps `5a44119`+ while workers return to
`28e8eb7` — today's pre-release state (web has run #16/#17 retrieval and prompt 1.1.0
since 2026-09-20). Workers never stamp `ORACLE_SYSTEM_PROMPT_VERSION`, so the audit
trail is unaffected and web needs no revert.
