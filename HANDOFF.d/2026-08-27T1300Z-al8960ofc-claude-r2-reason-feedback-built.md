# R2: rejection-reason feedback is built and green. It has not been measured.

Status: **Third cycle is code-complete and shipped. One owner decision remains.** Two production runs
have been spent (22/30, then 23/30) against a threshold of 27/30. The third cycle changes what the
model is ASKED on a second attempt rather than repeating the first. Nothing about it is measured.
Plan of record: [`../plan_r2_completion_recovery_cycle.md`](../plan_r2_completion_recovery_cycle.md).

## 0. Decisions only the owner can make

Blocking: Albert authorizes exactly one production run to measure the reason-code feedback, or
declines. No run may be triggered without that. Cost of the last run was $0.0054.

Already settled and NOT open: the answer key, the `field-aware-v3` matcher, the 27/30 threshold, the
negative controls, the frozen route and limits, and the business-model flags all stay as they are.
Stored-record COUNT is not the objective — it fell from 102 to 95 while the score rose. Do not re-ask.

## 1. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. Repository
`u2giants/theoracle`, `main`, TypeScript, pnpm, Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`,
production Supabase `eqccjfbyrywsqkxxpjvg`, web at `https://oracle.designflow.app`.

## 2. What this session set out to do

Complete the approved production gate, then run correction cycles against what each measurement
actually showed, never against a guess.

## 3. Current state

`main` is green at `0a1c396`. Three maps exist for document `cc005035-2251-4dbe-ba1a-8913ad3ea912`,
all stored and addressable:

- `37a8fc62-...` (2026-08-11, 19/30) — superseded.
- `aa713247-...` (worker `20260827.1`, run `run_06g423t548pl6pc50ii4e2iv01`, 22/30) — superseded.
- `224ca68d-82c8-4954-ac65-59b02db00546` (worker `20260827.2`, run
  `run_06g45qkld9p9931i6qp4quk501`, **23/30**, 95 records) — current, `degraded`.

Current map matches rows 1-4, 6-13, 17-22, 25, 27-30; misses 5, 14, 15, 16, 23, 24, 26. All 19 rows
the 2026-08-11 run matched are preserved; negative controls 16, 24 and 26 remain unmatched.

Two cycles are shipped. Cycle two: the late completion pass was starved and never ran; `handledIds`
now comes from ACCEPTED outcomes only. Measured worth: one row (19). Cycle three, unmeasured: each
residual seed reaching the late pass now carries `priorRejectionReasons`, and the completion prompt
(`responsibility-completion-v2`) explains each code.

Tooling on `main`: `verify:r2-fresh-map-score` (SELECT-only scorer, takes `R2_FRESH_MAP_ID`) and
`verify:r2-missed-row-diagnosis` (SELECT-only, names one cause per missed row). Both need
`R2_REPLAY_DATABASE_URL`.

All 16 local gates pass and `verify:r2-production-replay` is byte-identical at hash `013e40ca...`.

## 4. What did not work

Both gates failed: 22/30 and 23/30. Neither was retried and nothing was tuned to flatter either.

Binding dead ends: do not relax the fidelity validator to admit rejected candidates; do not weaken the
matcher, key or threshold; do not raise budgets, retries or concurrency (runs used 21 and 23 of 40
authorized model calls); do not add another late pass; and do not re-ask a rejected seed the SAME
question — that was measured and is worth nothing.

Environment repairs: the Trigger.dev MCP server was dead from a corrupt `trigger.dev@4.4.6` npx cache
entry, fixed by clearing the `_npx\c685fe487f03c925` folder under `%LOCALAPPDATA%\npm-cache`; and one
trigger attempt was refused for lack of Trigger.dev credits and created no run.

## 5. Root causes and findings

The reader detects ~139 duty seeds and keeps ~95-102. The losses are not budget, not detection, and
not the retry wiring any more. On the measured run **95 of 148** completion outcomes were rejected by
the deterministic validator, on specific grounds: `condition_not_preserved_in_trigger`,
`object_qualifier_loss:<words>`, `invented_object_content:<words>`, `action_family_mismatch`,
`owner_mismatch`, plus quote-policy failures. Those rejections are correct. The system simply never
told the model why, so the second attempt repeated the first. Cycle three closes that loop.

Still open and separate: rows 5, 14 and 15 each HAVE a record on the right span that passes fidelity
but whose object wording misses the frozen matcher — row 14 carries five of six expected object tokens
with ZERO unexpected ones. Fixing that changes how objects are constructed, the same seam that
protects all 19 preserved rows, so it needs its own plan and review. It is plausible that cycle
three's `object_qualifier_loss` feedback moves some of these on its own; that is a hypothesis to
measure, not a claim.

## 6. Exact next steps

1. Albert authorizes one run, or declines. Nothing proceeds without that.
2. If authorized: deploy `main` once to `prod` via the Trigger.dev CLI from `apps/workers`, then
   trigger `source-workflow-read` in `prod` with
   `{documentId: "cc005035-2251-4dbe-ba1a-8913ad3ea912", force: true}`, `maxAttempts: 1`, and a fresh
   idempotency key. Worked when exactly one run id is recorded.
3. Score with `verify:r2-fresh-map-score` and diagnose with `verify:r2-missed-row-diagnosis`. The
   signal to look for is the validation-rejected count falling on the late batches. Do not predict the
   score. Re-run all 16 gates afterwards.
4. Only then consider rows 5, 14 and 15 under their own plan.

## 7. Constraints and gotchas

Never print licensed source text, secrets, model responses or production rows. Never delete a map.
Never run a migration. Never let a reason code become suggested CONTENT — it is validator output, the
prompt says so, and a source assertion pins that wording. Do not drop the reason caps: feedback rides
in the request payload and is budget-estimated. `apps/workers/src/__verify__/r2-responsibility-reader.ts`
uses CRLF line endings — match them or its source assertions silently stop matching. Work happened in
worktree `C:\repos\oracle-worktrees\r2-production-plan-2ca7da` on branch
`claude/r2-production-plan-2ca7da`, pushed to `main`; that worktree needed its own `pnpm install`.
Preserve the untracked `.mcp.json.bak-20260826T153207`.

## 8. Access and environment

`al8960ofc`. GitHub, Trigger.dev CLI, Supabase MCP (`eqccjfbyrywsqkxxpjvg`, read-only) and 1Password
are authenticated. Vault `vibe_coding` is id `pimcaogmxxzoafh7lsluj6uxkq`; `op://` refs must use item
IDs, not titles, because the titles contain spaces the resolver rejects. SELECT-only verifiers read
`R2_REPLAY_DATABASE_URL` from item `qcuyabwseaptvuzvtjejffi2ou`, field `password`; the trigger key is
item `scugjbpdtbwlmglhv2dmfl4chi`, field `Production API key`. The licensed fixture is mounted at the
path in the production plan's section 10.

## 9. Open questions and risks

The open question is whether reason-code feedback moves a meaningful number of the remaining rows. It
is a well-evidenced hypothesis, not a prediction, and it may be worth nothing. Risk is bounded: the
change sits inside the existing late pass and the frozen budget, every candidate still faces the
unchanged validator, and the caps stop feedback from eating the batch. Rollback is a revert of the
`priorRejectionsBySeedId` wiring and the prompt version.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the purpose, live state, both failed gates,
the two shipped cycles, what is measured versus merely built, exact next steps, constraints, access
and risks without chat context. Section 0 names the one owner decision and closes every settled
question. The linked plan and `evals/r2-responsibilities.md` carry the full evidence and link back.
