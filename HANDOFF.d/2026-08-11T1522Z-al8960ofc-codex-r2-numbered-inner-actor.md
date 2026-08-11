# HANDOFF: R2 numbered inner-actor correction

## 0. Decisions only the owner can make

None before local implementation. Albert authorized the bounded plan and implementation on 2026-08-11. Already settled: no deployment or production in this workstream.

## 1. What this application is

The Oracle is the evidence-backed business knowledge system in `C:\repos\oracle`, `u2giants/theoracle`, branch `main`. Web is `https://oracle.designflow.app`; workers and data use the project IDs documented in the linked plan.

## 2. What we set out to do

Execute [`../plan_r2_numbered_inner_actor_correction.md`](../plan_r2_numbered_inner_actor_correction.md): recognize one source list marker between an outer label and direct actor, then require the unchanged local gate.

## 3. Current state

Commit `62330bdb0b477abb373fa1d155b104cee45a8b66` is pushed to `main`, and CI run `31508223778` passed. The combined local correction passes the unchanged gate at 28/30 from 139 seeds. Supported rows are 1-15 except 16, plus 17-25, 27-30 except 26. Only rows 16 and 26 remain unsupported. Every full local command passed after the review fix. Codex session `019ff16e-013e-7900-bd0d-bd01e7758e1d` and GLM 5.2 report `.ai/reviews/glm-r2-inventory-p6-final-20260811T153842Z.md` both say `APPROVED FOR CI` with no P0/P1. Nothing is deployed.

## 4. What did not work

The prior helper handled outer label plus direct actor, but not outer label plus `1.`/`2.` plus direct actor. The first marker attempt reached 27/30 but regressed row 24 through a false actor ending in `in`; a general trailing-preposition guard restored it. Review then found a stale reset flag erased a valid new actor after unrelated prose; that is also fixed. Rows 16 and 26 need different designs and are excluded.

## 5. Root cause

`directDutySubject` tests a body that begins with the numeric marker, so its actor regex fails. Exact actor/action/object text is already visible in rows 14 and 29.

## 6. Exact next steps

Do nothing further without Albert's separate decision. Deployment and the frozen production gate remain forbidden in this workstream.

## 7. Constraints

Exact-span only; unchanged verifier/scorer/budgets; no aliases or wider context; preserve offsets and full-span verb index; main only; exact staging.

## 8. Access

Windows repo, pnpm, authenticated GitHub and GLM. No secrets needed.

## 9. Risks

Wrong offset arithmetic or permissive numeric stripping. The plan's locked grammar and negative tests control both.

## Self-audit

Passed. The linked plan and this handoff define all background, failures, code targets, tests, constraints, access, landing gates, and owner decisions for a clean developer.
