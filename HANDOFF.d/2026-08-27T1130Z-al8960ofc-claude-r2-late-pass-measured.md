# R2: the late-pass repair is measured at 23/30. Next lever identified, not authorized.

Status: **Cycle complete and measured. One owner decision remains.** Two authorized production runs
have been spent (22/30, then 23/30). The threshold is 27/30, so the business goal is NOT met. The
repair shipped in this cycle did exactly what it was designed to do and was worth one row. Plan of
record: [`../plan_r2_completion_recovery_cycle.md`](../plan_r2_completion_recovery_cycle.md).

## 0. Decisions only the owner can make

Blocking: Albert decides whether to fund a third cycle. The evidence now points at one specific,
different lever (section 5). Nothing may start without his word, and no production run may be
triggered without a fresh explicit authorization.

Already settled and NOT open: the answer key, the `field-aware-v3` matcher, the 27/30 threshold, the
negative controls, the frozen route and limits, and the business-model flags all stay as they are.
Record COUNT is not the objective. Do not re-ask any of this.

## 1. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. Repository
`u2giants/theoracle`, `main`, TypeScript, pnpm, Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`,
production Supabase `eqccjfbyrywsqkxxpjvg`, web at `https://oracle.designflow.app`.

## 2. What this session set out to do

Complete the approved production gate; then, on Albert's authorization, run a correction cycle to
recover the duties it lost; then, on a further authorization, measure that correction.

## 3. Current state

`main` is green and carries everything below. Three maps exist for document
`cc005035-2251-4dbe-ba1a-8913ad3ea912`, all stored and addressable:

- `37a8fc62-...` (2026-08-11, 19/30) — superseded.
- `aa713247-...` (worker `20260827.1`, run `run_06g423t548pl6pc50ii4e2iv01`, 22/30) — superseded.
- `224ca68d-82c8-4954-ac65-59b02db00546` (worker `20260827.2`, run
  `run_06g45qkld9p9931i6qp4quk501`, **23/30**, 95 records) — current, `degraded`.

Matched rows on the current map: 1-4, 6-13, 17, 18, 19, 20, 21, 22, 25, 27-30. Missed: 5, 14, 15, 16,
23, 24, 26. All 19 rows the 2026-08-11 run matched are preserved; negative controls 16, 24 and 26
remain unmatched; all 16 local gates pass and `verify:r2-production-replay` is byte-identical at hash
`013e40ca...`.

Tooling added on `main`: `verify:r2-fresh-map-score` (SELECT-only scorer for a fresh map) and
`verify:r2-missed-row-diagnosis` (SELECT-only, names one cause per missed row). Both need
`R2_REPLAY_DATABASE_URL`; the scorer also takes `R2_FRESH_MAP_ID`.

## 4. What did not work

Both gates failed: 22/30 and 23/30 against a threshold of 27. Neither was retried and nothing was
tuned to flatter either number.

Binding dead ends, unchanged: do not relax the fidelity validator to admit rejected candidates; do not
weaken the matcher, key or threshold; do not raise budgets, retries or concurrency (the runs used 21
and 23 of 40 authorized model calls); do not add another late pass.

Environment repairs made along the way: the Trigger.dev MCP server was dead from a corrupt
`trigger.dev@4.4.6` npx cache entry, fixed by clearing the `_npx\c685fe487f03c925` folder under
`%LOCALAPPDATA%\npm-cache`; and the first trigger attempt was refused for lack of Trigger.dev credits
and created no run.

## 5. Root causes and findings

**Fixed this cycle.** The late completion pass — the one mechanism built to give an unresolved seed
another source-bound attempt — had never run. It was fed every SCHEDULED seed as "handled", so seeds
whose candidates came back `validation_rejected` counted as answered. `handledIds` now comes from
ACCEPTED outcomes only. Measured effect: 2 completion batches instead of 1, 47 rejected seeds
re-attempted, **row 19 recovered**.

**The next lever, not yet attempted.** On the measured run, **95 of 148** completion outcomes were
validation-rejected. Re-asking the same question is therefore spent as a strategy: the model returns a
candidate that fails the same rule. But the rejection reasons are already computed, already audited,
and specific — `condition_not_preserved_in_trigger`, `object_qualifier_loss:<tokens>`,
`action_family_mismatch`, `owner_mismatch`, plus quote-policy failures. Feeding those codes back into
the late-pass prompt is a genuinely different attempt, keeps the validator authoritative, and invents
nothing. This is the recommended third cycle.

**Still open, separately.** Rows 5, 14 and 15 each HAVE a record on the right span that passes
fidelity but whose object wording misses the frozen matcher; row 14 carries five of six expected
object tokens with ZERO unexpected ones. Fixing that changes how objects are constructed — the same
seam that protects all 19 preserved rows — so it needs its own plan and review. Row 23 still produces
no record on its supporting span at all.

## 6. Exact next steps

1. Albert funds a third cycle, or stops here. Nothing proceeds without that.
2. If funded: implement reason-code feedback into the late-pass completion prompt, keeping the
   validator, matcher, key, threshold and budgets untouched. Worked when deterministic cases prove a
   rejected candidate is re-asked WITH its reason codes and the validator still judges the result.
3. Prove locally: all 16 gates plus the replay must stay green and the replay hash unchanged.
4. Only then request one production run, score with `verify:r2-fresh-map-score`, and diagnose with
   `verify:r2-missed-row-diagnosis`.

## 7. Constraints and gotchas

Never print licensed source text, secrets, model responses or production rows. Never delete a map.
Never run a migration. Stored-record count is not quality: it fell from 102 to 95 while the score rose.
`apps/workers/src/__verify__/r2-responsibility-reader.ts` uses CRLF line endings — match them or its
source assertions silently stop matching. Work happened in worktree
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

The open question is whether reason-code feedback closes a meaningful part of the remaining four rows.
It is a hypothesis with good evidence behind it, not a prediction. Risk is low and bounded: the change
would sit inside the existing late pass and the frozen budget, and every candidate would still face
the unchanged validator. Rollback for this cycle's shipped fix is a one-line revert of the
`handledIds` construction.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the purpose, live state, both failed gates,
the fixed cause, the identified next lever, exact next steps, constraints, access and risks without
chat context. Section 0 names the one owner decision and closes every settled question. The linked
plan and `evals/r2-responsibilities.md` carry the full evidence and link back here.
