# R2 fresh production gate awaits approval of its written execution contract

Status: **OPEN.** Albert authorized one fresh R2 production run on 2026-08-26. The predecessor requires
the written plan to be approved before deployment or triggering. Plan of record:
[`../plan_r2_fresh_production_gate.md`](../plan_r2_fresh_production_gate.md).

## 0. Decisions only the owner can make

Blocking: approve the exact written plan, including the named licensed document, $10 maximum model
budget, one-attempt limit, 27/30 gate, and abort conditions. Recommendation: approve it; all local work
and independent review are complete. This blocks deployment and the one production run.

Already settled: Albert authorized exactly one fresh run on 2026-08-26. No schema, secret, model,
route, matcher, fixture, threshold, budget, feature-flag, Vercel, second-run, or bake-off change is
authorized. Do not re-ask those questions.

## 1. What this application is

The Oracle turns POP Creations documents into source-grounded business knowledge. The TypeScript
monorepo is `u2giants/theoracle`; web runs at `https://oracle.designflow.app`; workers run in Trigger.dev
project `proj_wgpzsvhmsopqhvwqaycn`; production data is Supabase `eqccjfbyrywsqkxxpjvg`.

## 2. What this session set out to do

Safely resume the completed R2 correction work, pull current `main`, and continue through the one
remaining production measurement. A predecessor handoff correctly stopped the session until Albert
authorized one run and a written run contract existed.

## 3. Current state

`main` and `origin/main` were `aae671c`; the corrected behavior is contained in ancestor `52b308b`.
F0-F6 and all 15 local gates are complete, and both reviewers cleared every P0/P1. No deployment or
production run has occurred in this session. The plan exists but awaits explicit approval. The
untracked `.mcp.json.bak-20260826T153207` is unrelated and must be preserved.

## 4. What did not work

No run was attempted. Historical dead ends remain binding: replaying the old map cannot reach 27/30;
tuning the matcher or validator would produce dishonest evidence; the first F6 record-level replay
fix was a no-op; a stale worker would test the wrong code. Full details are in the predecessor handoff
and the correction plan linked from the new plan.

## 5. Root causes and findings

The old map scored 19/30. Current code corrects two stored shapes to 21/30, but six additional eligible
rows require a fresh pipeline execution. Row 5 may honestly cap the result at 26/30. The new run must
therefore be treated as measurement, never as a tuning loop.

## 6. Exact next steps

1. Obtain Albert's explicit approval of `plan_r2_fresh_production_gate.md`. Worked when he approves
   that file by name.
2. Execute P1-P4 in its STATUS table exactly once. Worked when the deployed version, run id, new map id,
   frozen score, usage, and all regression gates are recorded.
3. Update the plan and eval evidence, push `main`, verify CI, and apply the predecessor successor rule.
   Worked when GitHub, Trigger.dev, the database, and documentation agree.

## 7. Constraints and gotchas

One task attempt only; `maxAttempts: 1`; no second run. Preserve the frozen document, matcher, answer
key, threshold, route/model, budget, and negative controls. Never expose secrets or licensed source
text. Never delete a map or run a migration. Stage only owned files.

## 8. Access and environment

Checkout `C:\repos\oracle`; authenticated GitHub, Trigger.dev MCP, and 1Password. Use `vibe_coding`
item `Supabase DB Direct URL - The Oracle (CURRENT PROD, theoracle, eqccjfbyrywsqkxxpjvg)` only through
protected injection. The licensed fixture path is stated in plan section 10 and must be reachable.

## 9. Open questions and risks

The only execution question is whether the fresh map reaches 27/30; row 5 is the main risk. A lower
score is an honest failed gate and ends the authorization. Worker deployment can be rolled back; maps
remain stored and are not deleted.

## Handoff self-audit

Yes to all four checks. Sections 1-9 give a new developer the complete purpose, live state, failures,
findings, exact next steps, constraints, access, and risks. Section 0 contains the only owner decision
found by rereading sections 1-9: approval of the written contract. The linked 13-section plan carries
the complete executable detail and links back here.
