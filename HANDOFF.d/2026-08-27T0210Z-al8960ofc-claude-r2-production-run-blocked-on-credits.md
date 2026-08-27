# R2 fresh production gate: worker deployed, the one run is blocked on Trigger.dev credits

Status: **BLOCKED ON OWNER BILLING.** Preflight, all 16 local gates, and the single authorized
production deployment are DONE on `al8960ofc`. The one authorized production run was refused by
Trigger.dev with HTTP 422 `You can't trigger a task because you have run out of credits.` No run id
was issued and no new map exists. Plan of record:
[`../plan_r2_fresh_production_gate.md`](../plan_r2_fresh_production_gate.md).

## 0. Decisions only the owner can make

Blocking: Albert must restore Trigger.dev credits/billing for the account `hello@popcre.com`
(project `proj_wgpzsvhmsopqhvwqaycn`). Nothing else is blocked and no new decision is needed.

Already settled: exactly one fresh run is authorized. No schema, secret, model, route, matcher,
fixture, answer key, threshold, budget, feature-flag, Vercel, second-run, or bake-off change is
authorized. Do not re-ask those questions.

## 1. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. The TypeScript
monorepo is `u2giants/theoracle`; web runs at `https://oracle.designflow.app`; workers run in
Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; production data is Supabase `eqccjfbyrywsqkxxpjvg`.

## 2. What this session set out to do

Continue the approved plan from `42b3404` on the correct host and complete the one production
measurement, without ever triggering more than one run.

## 3. Current state

`main` = `origin/main` = `42b3404`; `52b308b` is an ancestor; CI run `33031355425` is green. The
licensed pinned fixture is reachable on this host. All section-10 gates passed: pinned inventory
28/30 with rows 16 and 26 unsupported; SELECT-only production replay 19 baseline / 21 corrected,
preserved 19, empty `regressedRows` and `recordLevelRegressions`; `git diff --check` clean. Frozen
settings verified in production: workflow-read route `openai/gpt-4.1`, 40 read calls, 500,000 input
tokens, $10, 1 repair attempt, 5 per-source omission retries, 1 quote repair, and all three
`business_model_*_enabled` false. Document `cc005035-2251-4dbe-ba1a-8913ad3ea912` and prior map
`37a8fc62-23e4-46b7-8464-d1c784dc73cd` exist; that document still has exactly one map.

The corrected worker was deployed once to `prod` as version `20260827.1` (deployment `pdgvxo7p`,
25 detected tasks). The trigger call then failed at the API before any run was created.

## 4. What did not work

The Trigger.dev MCP server was dead on this machine: its pinned `trigger.dev@4.4.6` npx cache entry
was corrupt (`Cannot find package .../jiti/index.js`). Clearing
`%LOCALAPPDATA%\npm-cache\_npx\c685fe487f03c925` repaired the CLI; the repo's own `4.5.2` CLI is
authenticated as `hello@popcre.com` and was used for the deployment. The `.mcp.json` entry still
pins `4.4.6`; re-check it before relying on the MCP.

The single trigger attempt returned 422 out-of-credits. No retry was made and none is authorized
until credits exist. Historical dead ends remain binding: replaying the old map cannot reach 27/30;
tuning the matcher or validator would produce dishonest evidence; a stale worker tests the wrong code.

## 5. Root causes and findings

The old map scored 19/30. Current code corrects two stored shapes to 21/30; six further eligible rows
require a fresh pipeline execution. Row 5 may honestly cap the result at 26/30. The fresh run is a
measurement, never a tuning loop.

## 6. Exact next steps

1. Albert restores Trigger.dev credits. Worked when the dashboard shows available credit for
   `proj_wgpzsvhmsopqhvwqaycn`.
2. Re-issue exactly one trigger of task `source-workflow-read` in `prod` with payload
   `{documentId: "cc005035-2251-4dbe-ba1a-8913ad3ea912", force: true}`, options
   `{maxAttempts: 1, idempotencyKey: "plan-r2-fresh-production-gate-2026-08-26-run-1"}`, using
   `TRIGGER_SECRET_KEY` from `vibe_coding` item `Trigger.dev Secret Key - The Oracle`, field
   `Production API key`, injected through `op_run`. Worked when exactly one run id is recorded.
   The deployed worker `20260827.1` is already current; do not redeploy unless Git has moved.
3. Follow that run to a terminal state, then execute plan steps 6-9: audit, score against the frozen
   `licensed-team-responsibilities-v1` key and `field-aware-v3` matcher (threshold 27/30, negative
   controls 16/24/26), re-run section 10, and ship the documentation.

## 7. Constraints and gotchas

One task attempt only; `maxAttempts: 1` is set at trigger time, not in the task file, so the plan's
"no retry change" scope rule stays intact. No second run to chase a better score. Never expose
secrets or licensed source text. Never delete a map or run a migration. Stage only owned files.
Preserve the untracked `.mcp.json.bak-20260826T153207`. Work happened in worktree
`C:\repos\oracle-worktrees\r2-production-plan-2ca7da` on branch `claude/r2-production-plan-2ca7da`;
that worktree needed its own `pnpm install`.

## 8. Access and environment

GitHub, Trigger.dev CLI, Supabase MCP (`eqccjfbyrywsqkxxpjvg`, read-only), and 1Password are
authenticated on `al8960ofc`. Vault `vibe_coding` is id `pimcaogmxxzoafh7lsluj6uxkq`; `op://` refs
must use item IDs, not titles, because the titles contain spaces the resolver rejects. The replay
gate reads `R2_REPLAY_DATABASE_URL` from item `qcuyabwseaptvuzvtjejffi2ou`, field `password`. The
licensed fixture is mounted at the path in plan section 10.

## 9. Open questions and risks

The only execution question remains whether the fresh map reaches 27/30, with row 5 the main risk. A
lower score is an honest failed gate and ends the authorization. Worker rollback to the prior version
is the rollback path; maps are never deleted.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the purpose, live state, failures, findings,
exact next steps, constraints, access, and risks without chat context. Section 0 names the one owner
decision. The linked 13-section plan carries the full executable detail and links back here.
