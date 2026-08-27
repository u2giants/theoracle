# R2 Fresh Production Gate Plan

## STATUS table

| Step | Status | Evidence |
|---|---|---|
| P0. Owner approval of this exact plan | DONE 2026-08-26 | Albert explicitly approved `plan_r2_fresh_production_gate.md` in Codex. |
| P1. Preflight and deploy corrected worker | DONE 2026-08-27 | Run on `al8960ofc`. `main` = `origin/main` = `42b3404`; `52b308b` is an ancestor; CI run `33031355425` green. Settings verified against section 8 (route `openai/gpt-4.1`, 40 calls, 500,000 tokens, $10, 1 repair, 5 omission retries, 1 quote repair, all three `business_model_*_enabled` false). Document and prior map `37a8fc62-23e4-46b7-8464-d1c784dc73cd` exist. All 16 section-10 gates passed, including pinned fixture 28/30 (16/26 unsupported) and SELECT-only replay 19 baseline / 21 corrected with empty regression lists. Worker deployed once to `prod` as version `20260827.1` (deployment `pdgvxo7p`, 25 tasks). |
| P2. Trigger exactly one fresh production map | BLOCKED 2026-08-27 | Trigger.dev rejected the single authorized trigger with HTTP 422 `You can't trigger a task because you have run out of credits.` No run id was issued and no new map exists; `source_workflow_maps` for the document still holds only `37a8fc62-...`. Deployed worker `20260827.1` is ready. Resume by re-running the one authorized trigger after Trigger.dev billing/credits are restored. |
| P3. Score and audit the new map | OPEN | Frozen `licensed-team-responsibilities-v1` answer key, `field-aware-v3` matcher, threshold 27/30. |
| P4. Re-run preservation and local gates | OPEN | Commands listed in sections 9 and 10; no regression is permitted. |
| P5. Record, ship documentation, and retire predecessor handoff | OPEN | Plan/eval drift entry, commit, push, CI, and handoff successor check. |

Fresh-session start: preflight, local gates, and the one authorized deployment are complete on
`al8960ofc`. The single authorized production run has NOT occurred: Trigger.dev refused it for lack of
account credits. Resume at P2 by re-issuing exactly one trigger for
`{documentId: "cc005035-2251-4dbe-ba1a-8913ad3ea912", force: true}` with `maxAttempts: 1` and
idempotency key `plan-r2-fresh-production-gate-2026-08-26-run-1`, once Albert has restored Trigger.dev
credits. Nothing else in this plan changes.

Plan handoff: [`HANDOFF.d/2026-08-27T0210Z-al8960ofc-claude-r2-production-run-blocked-on-credits.md`](HANDOFF.d/2026-08-27T0210Z-al8960ofc-claude-r2-production-run-blocked-on-credits.md).

## 1. Ultimate goal

Prove whether the corrected Oracle reader can turn the licensed responsibilities document into at
least 27 of the 30 frozen, source-supported business duties without inventing facts or losing any of
the 19 duties the prior production run got right. If a step conflicts with that goal, the goal wins:
stop and flag it rather than changing the evidence rules or score.

## 2. What this application is

The Oracle is POP Creations' evidence-backed business knowledge system. Employees upload documents;
Trigger.dev workers create source-grounded workflow maps; deterministic validators decide what may be
stored. Repository `u2giants/theoracle` uses `main`, TypeScript, pnpm, Trigger.dev, and Supabase. The
web app is `https://oracle.designflow.app`; workers use project `proj_wgpzsvhmsopqhvwqaycn`; production
data is in Supabase project `eqccjfbyrywsqkxxpjvg`.

## 3. What triggered this work

The 2026-08-11 production run `run_06fv3keiq77bp0gpum352rls01` created map
`37a8fc62-23e4-46b7-8464-d1c784dc73cd` for document
`cc005035-2251-4dbe-ba1a-8913ad3ea912` and scored 19/30. F0-F6 then corrected the final-record seam,
proved 19/19 preservation, passed all 15 local gates, and cleared two independent reviews. Albert
authorized exactly one fresh production run on 2026-08-26. The predecessor handoff requires this
written execution contract and Albert's approval before production begins.

## 4. Scope

In scope: verify the exact current code and settings; deploy the corrected worker once; force one new
`source-workflow-read` run for the named document; score its resulting map; re-run all preservation
gates; document and ship the measured result.

Out of scope: any schema, migration, secret, model, route, prompt, matcher, answer key, fixture,
threshold, budget, retry, concurrency, Vercel, merge/apply/serving, or business-model flag change;
any second production run or bake-off; cleanup of unrelated files or branches.

## 5. Current state of the code

`main` and `origin/main` were both `aae671c` on 2026-08-26. The behavior under test landed in
`52b308b` after F5/F6 commits `aab134e`, `41f775b`, and `58642ed`. The shared correction seam and
validators are in `apps/workers/src/lib/responsibility-reader.ts` and
`apps/workers/src/lib/source-workflow-read.ts`; the production task wrapper is
`apps/workers/src/trigger/source-workflow-read.ts`. Local gates are green, but the current production
worker must be inspected: no claim is made yet that it contains `52b308b`.

## 6. Key findings and root cause

The old map cannot exceed 21/30 under replay because rows 15, 20, and 23 lack usable stored records;
six recoveries require the corrected seam during a fresh pipeline execution. Row 5 remains the honest
unknown and may cap the result at 26/30. The prior 19 matches are protected by the SELECT-only replay
gate in `apps/workers/src/__verify__/r2-production-replay.ts`. The new run supersedes the old map for
the same document, but the old map remains recoverable by id and Git preserves every plan/handoff.

## 7. Rejected approaches

- Do not tune the old replay to 27/30; it cannot create records that were never stored.
- Do not weaken field fidelity, polarity, owner/action checks, the condition-to-trigger rule, or the
  frozen matcher. That can manufacture a passing number from bad records.
- Do not raise the model budget, retries, or concurrency; the prior run had unused capacity.
- Do not enable the dormant second field-rewrite path or business-model merge/apply/serving flags.
- Do not run from a stale worker or trigger more than once to select the best outcome.

## 8. Locked and open decisions

Locked on 2026-08-26: one run only; document id above; frozen route/model and limits of 40 model calls,
500,000 tokens, $10, one repair, five completion attempts, and one late pass; answer key
`licensed-team-responsibilities-v1`; matcher `field-aware-v3`; threshold 27/30; negative controls rows
16, 24, and 26; all three `business_model_*_enabled` settings remain false.

Open only as measured outcomes: whether the fresh map reaches 27/30 and whether row 5 is honestly
recoverable. No implementation judgment may move a locked decision.

## 9. Execution plan

1. **Approve this contract.** Albert reviews the named document, maximum budget, expected score, and
   abort rules. Gate: Albert explicitly approves `plan_r2_fresh_production_gate.md`.
2. **Preflight the immutable inputs.** Fetch GitHub; prove local `main` equals `origin/main`; prove
   `52b308b` is an ancestor; inspect GitHub CI; verify the document and old map exist; record the
   current settings and confirm the frozen model/route/limits and all business-model flags. Read-only
   queries use the existing production credential through 1Password `vibe_coding`, never plaintext.
   Gate: every identifier and setting matches section 8; otherwise stop without deployment.
3. **Run the local release gates before deployment.** Execute the full command list in section 10,
   including the licensed pinned fixture and SELECT-only production replay. Gate: all commands exit 0,
   pinned support remains 28/30 with rows 16/26 unsupported, replay remains 19 baseline / 21 corrected,
   and both regression lists are empty.
4. **Deploy the current worker once.** Use the authenticated Trigger.dev deployment tool with config
   `apps/workers/trigger.config.ts`, project `proj_wgpzsvhmsopqhvwqaycn`, environment `prod`. Record
   deployment/version and confirm `source-workflow-read` is registered. Gate: promoted production
   worker is healthy and corresponds to current Git code. If deployment fails, stop; do not trigger.
5. **Trigger exactly one run.** Use the Trigger.dev task `source-workflow-read` in `prod` with payload
   `{documentId: "cc005035-2251-4dbe-ba1a-8913ad3ea912", force: true}` and an idempotency key tied to
   this plan. Gate: record exactly one run id. Do not retry a failed or low-scoring run without new
   owner authorization.
6. **Wait and audit.** Follow the one run to a terminal state. On completion, identify its one new map,
   source-workflow job, model run, context pack, status, usage, and correction audit. Gate: no task
   error/retry ambiguity, no unproven field-fidelity elements, and no unexpected second map/run.
7. **Score without changing the frozen scorer.** Run a SELECT-only scorer against the new map using
   the frozen answer key and matcher. Report matched and missed row numbers, prior-row preservation,
   eligible recoveries, negative controls, and usage. Gate: at least 27/30, all 19 prior rows retained,
   and rows 16/24/26 remain unmatched. Below 27, any regression, or any negative-control match is a
   hard stop and an honest failed gate.
8. **Re-run preservation.** Execute section 10 again plus `verify:r2-production-replay` against the
   historical map. Gate: all commands exit 0 and both regression lists remain empty. No tuning is
   allowed after seeing the production result.
9. **Close the record.** Add the result and identifiers to this STATUS table, the drift log in
   `plan_r2_source_bound_final_record_correction.md`, and `evals/r2-responsibilities.md`; retire the
   predecessor handoff only after its successor conditions are met; commit owned docs, push `main`,
   and verify CI. Gate: GitHub `main`, CI, deployed worker, run, map, score, and docs all agree.

## 10. Tests required

Run before deployment and after scoring:

- `pnpm --filter @oracle/workers typecheck`
- `pnpm --filter @oracle/ai typecheck`
- `pnpm --filter @oracle/engines typecheck`
- `pnpm --filter @oracle/workers verify:r2-responsibilities`
- `pnpm --filter @oracle/workers verify:source-workflow-read`
- `pnpm --filter @oracle/workers verify:r0-reader-validator`
- `pnpm --filter @oracle/workers verify:document-ingestion-fallback`
- `pnpm --filter @oracle/workers verify:lull-event-dispatch`
- `pnpm --filter @oracle/workers verify:conversation-windowing`
- `pnpm --filter @oracle/ai verify:r2`
- `pnpm --filter @oracle/ai verify:workflow-read`
- `pnpm --filter @oracle/engines verify:macro`
- `pnpm --filter @oracle/engines verify:macro-first`
- `pnpm --filter @oracle/engines verify:r1-cross-shape`
- `pnpm --filter @oracle/workers verify:r2-pinned-inventory` with
  `R2_PINNED_FIXTURE_PATH=Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`
- `pnpm --filter @oracle/workers verify:r2-production-replay` with the existing production database
  URL injected through 1Password
- `git diff --check`

No new test code is planned. A missing licensed fixture on the current machine blocks deployment; it
does not authorize skipping the gate.

## 11. Constraints and gotchas

Preserve unrelated `.mcp.json.bak-20260826T153207`. Stage only owned docs. Never print licensed text,
secrets, model responses, or production rows. The run is a recoverable write: `force: true` creates a
new map and supersedes the prior active map, while the prior map remains stored by id. Do not delete
maps. Never run migrations. A Trigger task retry can spend budget; set `maxAttempts: 1` and treat any
terminal failure as the one authorized attempt. Do not confuse the old replay score of 21/30 with the
fresh-map gate of 27/30.

## 12. Access and environment

Primary checkout: `C:\repos\oracle`. GitHub, Trigger.dev MCP, and 1Password are authenticated. Trigger
project: `proj_wgpzsvhmsopqhvwqaycn`; worker config: `apps/workers/trigger.config.ts`; production
Supabase ref: `eqccjfbyrywsqkxxpjvg`. Database access uses 1Password vault `vibe_coding`, item
`Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)`, through
`op_run`; no secret value enters commands, logs, chat, or files. The licensed fixture must be reachable
at the path in section 10.

## 13. Definition of done, risks, rollback, and open questions

Done means: written plan approved; exact preflight passed; local gates passed; corrected worker
deployed and identified; exactly one run completed; new map scored honestly; historical preservation
and local gates re-passed; result documented, committed, pushed, and green in CI; predecessor handoff
retired under the successor rule.

Success is 27/30 or better with all 19 prior matches preserved and negative controls still rejected.
A result below 27/30 is a completed but failed production gate, not unfinished work and not permission
for another run. Rollback is worker rollback to the previously recorded deployment if the new worker
is unhealthy; maps are not deleted, and the previous map remains addressable. The only genuine open
question is the measured result, especially row 5.

## Self-audit

1. Yes. Sections 2-13 define every identifier, environment, ordered action, gate, and rollback a new
   session needs without chat context.
2. Yes. Sections 3, 5-8, and 11 preserve the prior run, root cause, dead ends, locked decisions, and
   operational traps.
3. Yes. Section 1 states the business goal and explicitly makes it win over a conflicting step.

All 13 sections, the STATUS table, handoff backlink, explicit scope, named tests, secret references,
deployment proof, and stop conditions are present.
