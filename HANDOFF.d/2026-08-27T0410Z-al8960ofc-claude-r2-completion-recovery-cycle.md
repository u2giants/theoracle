# R2 correction cycle: the starved late pass is repaired; production measurement awaits authorization

Status: **Code work for this cycle is DONE and shipped green. One owner decision remains.** The
2026-08-27 production gate measured 22/30. Read-only diagnosis found a concrete structural defect,
it is repaired and locked by deterministic tests, and all 16 gates pass with the preservation replay
byte-identical. Nothing has been measured in production. Plan of record:
[`../plan_r2_completion_recovery_cycle.md`](../plan_r2_completion_recovery_cycle.md).

## 0. Decisions only the owner can make

Blocking: Albert decides whether to authorize exactly one more production run to measure the repair.
Until he does, no run may be triggered.

Also his call, and NOT to be started without it: rows 5, 14 and 15 need a second, riskier change to
how objects are constructed. That seam currently protects all 19 preserved rows, so it needs its own
plan and review.

Already settled and NOT open: the answer key, the `field-aware-v3` matcher, the 27/30 threshold, the
negative controls, the frozen route and limits, and the business-model flags all stay exactly as they
are. Do not re-ask.

## 1. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. Repository
`u2giants/theoracle`, `main`, TypeScript, pnpm, Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`,
production Supabase `eqccjfbyrywsqkxxpjvg`, web at `https://oracle.designflow.app`.

## 2. What this session set out to do

Complete the approved production gate, then — after it failed honestly at 22/30 and Albert authorized
another correction cycle — find and fix the cause of the loss without weakening any evidence rule.

## 3. Current state

The production gate is complete and recorded: worker `20260827.1`, run
`run_06g423t548pl6pc50ii4e2iv01`, map `aa713247-e30f-4b0c-9b93-e02fdefd4048`, 22/30, all 19 prior rows
preserved, rows 17/20/29 recovered, negative controls clean. The prior map
`37a8fc62-23e4-46b7-8464-d1c784dc73cd` is `superseded` and still addressable.

This cycle then added, on `main`:

- `verify:r2-fresh-map-score` — SELECT-only scorer for a fresh map against the frozen key and matcher.
- `verify:r2-missed-row-diagnosis` — SELECT-only diagnostic naming one cause per missed row.
- The production fix in `apps/workers/src/lib/source-workflow-read.ts`: the late completion pass now
  treats a seed as handled only when its completion outcome was ACCEPTED.
- Two deterministic cases plus two source assertions in `verify:r2-responsibilities`.

All 16 local gates pass. `verify:r2-production-replay` is unchanged: 19 baseline / 21 corrected,
19/19 preserved, empty regression lists, hash `013e40ca...`.

## 4. What did not work

The gate itself: 22/30 against a threshold of 27.

Two environment repairs along the way. The Trigger.dev MCP server was dead because its pinned
`trigger.dev@4.4.6` npx cache entry was corrupt; clearing
`%LOCALAPPDATA%\npm-cache\_npx\c685fe487f03c925` fixed it and both `4.4.6` and the repo's `4.5.2` CLI
now authenticate as `hello@popcre.com`. The first trigger attempt was refused for lack of Trigger.dev
credits and created no run; after Albert restored credits the same idempotency key produced the one
run. Exactly one run exists.

Binding dead ends, unchanged: do not relax the fidelity validator to admit the 40 rejected candidates;
do not weaken the matcher, key or threshold; do not raise budgets or concurrency; do not add a second
late pass — the existing one was starved, not missing.

## 5. Root causes and findings

The run detected 139 duty seeds and stored 102. Of 96 seeds sent to completion, 56 were accepted and
**40 were `validation_rejected`** — legitimately, on fidelity and quote-policy grounds. The late
completion pass, which exists to give such a seed one more source-bound attempt, was fed every
SCHEDULED seed as "handled", so its residual list was empty and it never ran. The run finished having
spent 21 of 40 authorized model calls. Answer rows 19 and 23 were lost exactly that way.

Rows 5, 14 and 15 are a different problem: each HAS a record on the right span that passes fidelity,
but its object wording misses the frozen matcher. Row 14 carries five of six expected object tokens
with zero unexpected ones.

## 6. Exact next steps

1. Albert authorizes one production run, or declines. Nothing proceeds without that.
2. If authorized: deploy the current `main` worker once, then trigger `source-workflow-read` in `prod`
   with `{documentId: "cc005035-2251-4dbe-ba1a-8913ad3ea912", force: true}`, `maxAttempts: 1`, and a
   fresh idempotency key. Worked when exactly one run id is recorded.
3. Score with `verify:r2-fresh-map-score` and diagnose with `verify:r2-missed-row-diagnosis`. The
   expected signal is a non-empty late pass and more than 102 stored records. Do not predict the
   score. Re-run all 16 gates afterwards.
4. Only then consider rows 5, 14 and 15, under their own plan.

## 7. Constraints and gotchas

Never print licensed source text, secrets, model responses or production rows. Never delete a map.
Never run a migration. `apps/workers/src/__verify__/r2-responsibility-reader.ts` uses CRLF line
endings — match them or its source assertions silently stop matching. Work happened in worktree
`C:\repos\oracle-worktrees\r2-production-plan-2ca7da` on branch `claude/r2-production-plan-2ca7da`,
pushed to `main`; that worktree needed its own `pnpm install`. Preserve the untracked
`.mcp.json.bak-20260826T153207`.

## 8. Access and environment

`al8960ofc`. GitHub, Trigger.dev CLI, Supabase MCP (`eqccjfbyrywsqkxxpjvg`, read-only) and 1Password
are authenticated. Vault `vibe_coding` is id `pimcaogmxxzoafh7lsluj6uxkq`; `op://` refs must use item
IDs, not titles, because the titles contain spaces the resolver rejects. SELECT-only verifiers read
`R2_REPLAY_DATABASE_URL` from item `qcuyabwseaptvuzvtjejffi2ou`, field `password`; the trigger key is
item `scugjbpdtbwlmglhv2dmfl4chi`, field `Production API key`. The licensed fixture is mounted at the
path in the production plan's section 10.

## 9. Open questions and risks

The open question is what the repaired late pass actually recovers — it removes a proven cause of
loss, but it is not a measured improvement and must not be reported as one. Risk: a future run will
spend more of its authorized model calls, which is intended and stays inside the frozen budget.
Rollback is a one-line revert of the `handledIds` construction.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the purpose, live state, failures, root
cause, exact next steps, constraints, access and risks without chat context. Section 0 names the two
owner decisions and closes every settled question. The linked plan and
`evals/r2-responsibilities.md` carry the full evidence and link back here.
