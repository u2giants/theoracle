# R2 fresh production gate awaits approval of its written execution contract

Status: **BLOCKED ON HOST, not on authorization.** Albert approved the written plan on 2026-08-26.
Preflight proved `edge-dev` has no `Z:` drive, so the mandatory licensed pinned-fixture gate cannot run.
No deployment and no production run occurred. Resume P1 on `al8960ofc`. Plan of record:
[`../plan_r2_fresh_production_gate.md`](../plan_r2_fresh_production_gate.md).

## 0. Decisions only the owner can make

Blocking: none for Albert. The approved task must resume on `al8960ofc`, where the predecessor proved
the licensed verification fixture is mounted. This is an execution-host dependency, not a new decision.

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

`main` and `origin/main` are `1ec4a47`; the corrected behavior is contained in ancestor `52b308b`; CI
run `33030360877` passed. Production worker is still `20260823.1`, so it predates the R2 fixes. F0-F6
and both reviews are complete. The approved plan's pre-deploy gates could not run because `edge-dev`
has no `Z:` drive. No deployment or production run occurred. The
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

1. Resume this repository on `al8960ofc`, fetch `origin/main`, and prove the pinned fixture path from
   plan section 10 exists. Worked when the file is reachable and hashes successfully in the pinned gate.
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
findings, exact next steps, constraints, access, and risks. Section 0 confirms there is no remaining
owner decision; the dependency is the execution host. The linked 13-section plan carries
the complete executable detail and links back here.
