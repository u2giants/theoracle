# R2: the reason-code prompt regressed production to 13/30. Reverted. One map decision open.

Status: **Regression contained. Two owner decisions remain.** The third cycle was measured and it
broke the completion stage outright: 13/30, and seven rows the 2026-08-11 run had matched were lost —
the first preservation failure ever recorded. The feature is fully reverted and production code is
back to known-good. The map currently SERVED for the document is still the bad one. Plan of record:
[`../plan_r2_completion_recovery_cycle.md`](../plan_r2_completion_recovery_cycle.md).

## 0. Decisions only the owner can make

RESOLVED 2026-08-27: Albert named the map and the action, and it is done. `224ca68d-82c8-4954-ac65-59b02db00546`
is once again the active map for document `cc005035-2251-4dbe-ba1a-8913ad3ea912`, verified at 23/30
with 95 records and all 19 prior rows preserved. The 13/30 map `eadb118c-...` is superseded and still
stored. Nothing about the served data is outstanding.

Blocking, the one decision left: whether to continue at all, and if so it must start with the
live prompt-contract check in section 6 — not with another prompt edit and not with another run.

Also his call: whether to reattempt reason-code feedback at all, and only after the prerequisite in
section 6 exists.

Already settled and NOT open: the answer key, the `field-aware-v3` matcher, the 27/30 threshold, the
negative controls, the frozen route and limits, and the business-model flags. Do not re-ask.

## 1. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. Repository
`u2giants/theoracle`, `main`, TypeScript, pnpm, Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`,
production Supabase `eqccjfbyrywsqkxxpjvg`, web at `https://oracle.designflow.app`.

## 2. What this session set out to do

Complete the approved production gate, then run correction cycles against what each measurement
showed. Three runs were authorized and spent: 22/30, 23/30, then 13/30.

## 3. Current state

`main` is green at `e3f0f23` and carries the revert. Production worker is **`20260827.4`**
(deployment `y0o93f1b`), which is the reverted, known-good `20260827.2` behaviour. All 16 local gates
pass and `verify:r2-production-replay` is byte-identical at hash `013e40ca...`.

Four maps exist for the document, all stored and addressable:

- `37a8fc62-...` (2026-08-11, 19/30) — superseded.
- `aa713247-...` (worker `20260827.1`, 22/30) — superseded.
- `224ca68d-82c8-4954-ac65-59b02db00546` (worker `20260827.2`, **23/30**, 95 records) — **the active
  map**, restored 2026-08-27, and the best result achieved.
- `eadb118c-0635-4ff5-a5fe-26f18865c1ae` (worker `20260827.3`, **13/30**, 46 records) — superseded
  on 2026-08-27 when the good map was restored. Matched only rows 6-11, 13, 17, 21, 22, 25, 27, 30.

## 4. What did not work

Three gates, three failures: 22/30, 23/30, 13/30 against a threshold of 27. Nothing was retried and
nothing was tuned to flatter any number.

The third is a genuine self-inflicted regression, not just a miss. Worker `20260827.3` carried the
reason-code feedback; **all 192 completion outcomes came back `provider_failed` with `Responsibility
completion omitted seeds`**. The model stopped returning exactly one record per requested seed, so the
canonicalizer threw, both attempts of both batches failed, and the completion stage contributed
nothing — the 46 records are the base read alone. This happened on the EXHAUSTIVE batch too, where no
seed carried feedback, which rules out the feedback data and indicts the prompt.

Note for whoever handles the rollback next time: **Trigger.dev refuses to promote an older
deployment.** The rollback had to be a forward deploy of the reverted code.

Binding dead ends: do not relax the fidelity validator; do not weaken the matcher, key or threshold;
do not raise budgets, retries or concurrency; do not re-ask a rejected seed the SAME question (worth
nothing, measured); and do not grow the completion system prompt (worth catastrophically less than
nothing, measured).

## 5. Root causes and findings

Two cycles of findings still stand. The late completion pass had been starved and never ran; fixing it
was worth one row. The remaining losses are validator rejections with specific, already-audited
reasons.

The new finding is about the system itself, and it is the most valuable thing this run bought:
`RESPONSIBILITY_COMPLETION_SYSTEM_PROMPT` is brittle under growth, and its failure mode is **total,
not gradual**. An addition that looked purely additive destroyed the one-record-per-seed contract
across every batch.

**Every deterministic gate passed on the change that caused this.** They test plumbing, not the
model's obedience. There is no check anywhere in this repo that a prompt edit still yields one record
per seed from a live model. That gap is why a broken prompt reached production.

## 6. Exact next steps

1. Albert decides the map question in section 0. Nothing about the served data changes without it.
2. Before ANY further prompt work: build a small live-model contract check — a handful of real seeds
   sent through `runResponsibilityCompletionModel`, asserting one record per requested seed and no
   omissions. It is cheap, it is not a full run, and it would have caught this. Treat it as the
   prerequisite, not an optional extra.
3. Only then reattempt reason-code feedback, in a form that cannot dilute the seed contract —
   ideally per-seed in the request payload with NO system-prompt change, or with a single short line.
4. Rows 5, 14 and 15 remain open under their own plan.

## 7. Constraints and gotchas

Never print licensed source text, secrets, model responses or production rows. Never delete a map.
Never run a migration. Stored-record count is not quality. Trigger.dev cannot promote backwards, so a
worker rollback is a forward deploy of reverted code. A partial unique index
(`source_workflow_maps_active_source_hash_unique`) permits only ONE non-superseded map per document
and content hash: when swapping which map is active, demote the current one FIRST.
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

There is no live risk outstanding: production code is back to known-good on worker `20260827.4`, and
the served map is the 23/30 one again. Everything is preserved and recoverable — no map was deleted
and every version remains addressable by id. The open engineering question is whether reason
feedback can be delivered without touching the system prompt; until the live contract check exists,
that question should not be answered in production.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the purpose, live state, all three failed
gates, the self-inflicted regression and its containment, the root cause, the missing safeguard, exact
next steps, constraints, access and risks without chat context. Section 0 names both owner decisions
and marks which is urgent. The linked plan and `evals/r2-responsibilities.md` carry the full evidence
and link back here.
