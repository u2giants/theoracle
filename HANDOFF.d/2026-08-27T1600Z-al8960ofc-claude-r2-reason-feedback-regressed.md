# R2: the reason-code prompt regressed production to 13/30. Reverted and the good map restored.

Status: **Regression fully contained. One owner decision remains.** The third cycle was measured and
it broke the completion stage outright: 13/30, and seven rows the 2026-08-11 run had matched were lost
— the first preservation failure ever recorded. The feature is reverted, production code is back to
known-good, and the 23/30 map is served again. Plan of record:
[`../plan_r2_completion_recovery_cycle.md`](../plan_r2_completion_recovery_cycle.md).

## 0. Decisions only the owner can make

RESOLVED 2026-08-27: Albert named the map and the action, and it is done. `224ca68d-82c8-4954-ac65-59b02db00546`
is once again the active map for document `cc005035-2251-4dbe-ba1a-8913ad3ea912`, verified at 23/30
with 95 records and all 19 prior rows preserved. The 13/30 map `eadb118c-...` is superseded and still
stored. Nothing about the served data is outstanding.

Blocking, the one thing left: **store `OPENAI_API_KEY` in the `vibe_coding` vault.** The live
prompt-contract probe is built and wired but cannot execute without it — the frozen `workflow_read`
route is `openai/gpt-4.1` and that key exists only in the Trigger.dev production environment. Until
the probe can run, no prompt change should reach production.

Then his call: whether to continue at all. If yes, the order is fixed — run the probe, then reattempt
reason-code feedback per-seed with no system-prompt change, then one run. Never a prompt edit and a
production run in the same step again.


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

`main` is green at `0e19a71` and carries the revert plus the contract probe. Production worker is **`20260827.4`**
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

1. Albert decides whether to continue. Nothing starts without it.
2. DONE, except for one credential: `verify:r2-completion-contract-live` is built and wired. It sends
   8 real seeds through `runResponsibilityCompletionModel` and
   `canonicalizeResponsibilityCompletionBatch` and asserts one record per requested seed. Proven as far
   as the model dispatch — DB connects, route resolves, all 8 seeds pack — then stops because
   `OPENAI_API_KEY` is absent from `vibe_coding`. Store the key, run the probe, confirm it passes on
   the CURRENT prompt so it has a known-good baseline before it is ever used to judge a change.
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
the served map is the 23/30 one again. The one standing exposure is procedural: until the contract
probe can actually run, the repo has no defence against the exact failure that caused the regression. Everything is preserved and recoverable — no map was deleted
and every version remains addressable by id. The open engineering question is whether reason
feedback can be delivered without touching the system prompt; until the live contract check exists,
that question should not be answered in production.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the purpose, live state, all three failed
gates, the self-inflicted regression and its containment, the root cause, the missing safeguard, exact
next steps, constraints, access and risks without chat context. Section 0 names both owner decisions
and marks which is urgent. The linked plan and `evals/r2-responsibilities.md` carry the full evidence
and link back here.
