# HANDOFF: R2 local owner-context correction plan

Created 2026-08-11 13:06 UTC on `al8960ofc` by Codex.

## 0. Decisions only the owner can make

The owner authorized planning and GLM 5.2 review, not implementation. After the reviewed plan is presented, Albert decides whether to authorize implementation. Recommendation: authorize only if the plan remains bounded to general source-owner architecture and GLM finds no blocking design flaw.

Already settled: no deployment, production run, frozen-gate consumption, verifier weakening, source-prefix lookup, budget increase, model change, merge, or apply while the honest local score is below 27/30.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees upload documents and ask questions. Workers turn exact source spans into validated duties and business maps. The repo is `C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main`. The web app is `https://oracle.designflow.app`; workers use Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; data uses Supabase project `eqccjfbyrywsqkxxpjvg`.

## 2. What we set out to do, and why

Write a fresh-session implementation plan for the honest R2 P5 residual failure and run it by GLM 5.2 with full background. The plan is [`../plan_r2_local_owner_context_correction.md`](../plan_r2_local_owner_context_correction.md). GLM's initial verdict was `CHANGES REQUIRED BEFORE IMPLEMENTATION`; its four P1 findings were incorporated. The follow-up verdict is `APPROVED FOR IMPLEMENTATION` with no remaining P0/P1 finding.

## 3. Current state

Commit `0ea1180c073b854e1a5826cd7dd06f264b739e21` is pushed to `main`; GitHub Actions run `31450496620` passed. P0-P4 and P6 code-quality fixes are complete. The unchanged local pinned verifier scores 16/30. Unsupported rows are 3, 6, 7, 8, 9, 10, 11, 13, 14, 16, 21, 22, 26, and 29. No implementation, deployment, production run, database change, setting change, or secret use occurred in this planning session.

## 4. Everything tried that did not work

The earlier verifier searched source text before a seed for an owner and falsely scored 27/30. It is removed and must not return. Nearby duties, earlier headings, answer-key aliases, fixture terms, larger budgets, model changes, and wider completion spans are rejected. The residual diagnosis found the production seed builder itself writes false owner `the following scenarios`, mishandles outer-tag versus inner-actor conflicts, and can split one duty into incoherent children.

## 5. Root causes and key findings

`sourceDutySpanDetails` in `apps/workers/src/lib/responsibility-reader.ts:820-929` stores arbitrary bracket or short heading text in one untyped `ownerHeading`. That false state contaminates later list items. Its owner precedence chooses an outer tag before a direct duty subject. Split logic can separate action and object anchors. At least eleven failed rows appear recoverable through a general owner correction, enough to reach 27/30 without solving the two special residuals.

## 6. Exact next steps

1. Read the linked plan in full and the parent `plan_r2_source_span_inventory_reader.md` before implementation. Success: both frozen contracts agree.
2. Read the saved GLM review and apply only agreed plan corrections. Success: no unresolved blocking finding remains.
3. Ask Albert for implementation authorization. Success: an explicit yes is dated in the plan.
4. If authorized, execute C0-C5 exactly. Success: unchanged verifier reaches at least 27/30, all local checks pass, and fresh review approves.
5. Stop before deployment or production. A later release session owns parent P7. Success: no cloud state changed.

## 7. Constraints and gotchas

Work on `main`; preserve Albert's git identity; use `apply_patch`; stage exact files only; preserve unrelated untracked `.ai`, browser, and screenshot files. Do not change the verifier, answer key, threshold, fixture SHA, budgets, model, prompt visibility, merge/apply, database, or production state. Root `HANDOFF.md` remains untouched.

## 8. Access and environment

Windows checkout `C:\repos\oracle`; pnpm from repo root; GitHub CLI authenticated. GLM uses `ai-glm` with caller `codex` and the existing Oracle session when applicable. Pinned local fixture is on `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`. Secrets remain in 1Password vault `vibe_coding`; none are needed.

## 9. Open questions and risks

Implementation is not yet authorized. GLM confirmed the diagnosis and approved the corrected plan after it gained an explicit actor-context state machine, a rule that descriptive headings do not reset a proven actor, combined-pattern tests, and a zero-margin stop. The score may remain below 27. Any such outcome is a hard stop, not permission for more rules. A passing local seed score still does not authorize production.

## Mandatory self-audit

Passed. A street-new developer can find the application, plan, exact state, failed paths, root cause, ordered next steps, constraints, access, decision boundary, and verification gates without this chat. The handoff and plan link to each other, and no secret value appears.
