# R2 fresh production gate is COMPLETE and FAILED at 22/30

Status: **DONE. No work remains and no follow-on session is authorized.** The single authorized
production run was executed on 2026-08-27 and scored 22/30 against a frozen threshold of 27/30. That
is a measured business answer, not an unfinished task. Plan of record:
[`../plan_r2_fresh_production_gate.md`](../plan_r2_fresh_production_gate.md).

## 0. Decisions only the owner can make

Blocking: Albert decides what happens next with the R2 responsibilities reader now that it measured
22/30 — accept the current quality, fund another correction cycle, or shelve it. No AI session may
start that work from this handoff.

Already settled and NOT open: the authorized run is spent. No second run, no retry, no bake-off, and
no change to the answer key, matcher, threshold, validator, prompt, route, model or budget is
authorized. Any future production run requires a new written plan and a new explicit authorization.

## 1. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. The TypeScript
monorepo is `u2giants/theoracle`; web runs at `https://oracle.designflow.app`; workers run in
Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; production data is Supabase `eqccjfbyrywsqkxxpjvg`.

## 2. What this session set out to do

Continue the approved plan from `42b3404` on `al8960ofc` and complete the one production measurement
without ever triggering more than one run.

## 3. Current state

Every step of the plan is DONE. `main` carries the result. The corrected worker is live in `prod` as
version `20260827.1` (deployment `pdgvxo7p`). Run `run_06g423t548pl6pc50ii4e2iv01` completed on the
first attempt for $0.0047 of Trigger compute and produced exactly one new map,
`aa713247-e30f-4b0c-9b93-e02fdefd4048`, with 102 stored responsibility records. The 2026-08-11 map
`37a8fc62-23e4-46b7-8464-d1c784dc73cd` is now `superseded` and remains stored and addressable.

Score under the frozen `licensed-team-responsibilities-v1` key and `field-aware-v3` matcher: **22/30**.
Matched rows 1-4, 6-13, 17, 18, 20-22, 25, 27-30. Missed rows 5, 14, 15, 16, 19, 23, 24, 26. All 19
rows the prior production run matched are preserved. Rows 17, 20 and 29 were newly recovered. Negative
controls 16, 24 and 26 remain unmatched. All 16 local gates were re-run after scoring and all pass,
including the SELECT-only replay at 19 baseline / 21 corrected with empty regression lists and an
unchanged `013e40ca...` hash.

## 4. What did not work

The gate itself did not reach 27/30, and that is the headline. Rows 15, 19 and 23 were predicted
recoveries and did not appear in a fresh execution; row 5 remains the honest unknown.

Two environment problems were repaired along the way. The Trigger.dev MCP server was dead because its
pinned `trigger.dev@4.4.6` npx cache entry was corrupt; clearing
`%LOCALAPPDATA%\npm-cache\_npx\c685fe487f03c925` fixed it and both `4.4.6` and the repo's `4.5.2` CLI
now authenticate as `hello@popcre.com`. The first trigger attempt was refused with HTTP 422 for lack
of Trigger.dev account credits and created no run; Albert restored credits and the same idempotency
key then produced the one run. Only one run exists.

## 5. Root causes and findings

The F2/F2b/F3/F4 correction seams demonstrably work end to end — three rows the old map could never
match were recovered by the fresh pipeline, and nothing regressed. The shortfall is upstream of the
correction seam: for rows 5, 14, 15, 19 and 23 the reader still does not produce a final record whose
role, action and object survive fidelity validation against the row's own source span. Rows 16 and 26
are unsupported by the source, so 28/30 is the honest ceiling under this answer key.

## 6. Exact next steps

None are authorized. If Albert funds another cycle, the first move is diagnostic, not corrective:
compare the 102 stored records of map `aa713247-...` against the pinned inventory seeds for rows 5,
14, 15, 19 and 23 to learn whether each duty produced no candidate at all or produced one that failed
fidelity. That is a SELECT-only investigation and needs no production run.

## 7. Constraints and gotchas

Do not re-run the gate. Do not tune the matcher, answer key, validator or threshold against 22/30 —
that would manufacture a passing number from the same records. Never expose secrets or licensed source
text. Never delete a map or run a migration. Preserve the untracked `.mcp.json.bak-20260826T153207`.
Work happened in worktree `C:\repos\oracle-worktrees\r2-production-plan-2ca7da` on branch
`claude/r2-production-plan-2ca7da`, pushed to `main`; that worktree needed its own `pnpm install`.

## 8. Access and environment

GitHub, Trigger.dev CLI, Supabase MCP (`eqccjfbyrywsqkxxpjvg`, read-only) and 1Password are
authenticated on `al8960ofc`. Vault `vibe_coding` is id `pimcaogmxxzoafh7lsluj6uxkq`; `op://` refs must
use item IDs, not titles, because the titles contain spaces the resolver rejects. The scorer and replay
gates read `R2_REPLAY_DATABASE_URL` from item `qcuyabwseaptvuzvtjejffi2ou`, field `password`; the
trigger key is item `scugjbpdtbwlmglhv2dmfl4chi`, field `Production API key`. The licensed fixture is
mounted at the path in plan section 10.

## 9. Open questions and risks

The measured question is answered: 22/30. The open business question is whether that quality is good
enough to serve, and it belongs to Albert. Operational risk is low — the new map is `degraded` like
its predecessor, the prior map is still addressable, and worker rollback to the previously recorded
version is available if `20260827.1` misbehaves on other tasks.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the purpose, live state, failures, findings,
next steps, constraints, access and risks without chat context. Section 0 names the one owner decision
and closes every settled question. The linked 13-section plan and `evals/r2-responsibilities.md` carry
the full evidence and link back here.
