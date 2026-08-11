# R2 Numbered Inner-Actor Correction Plan

Status: **LOCAL CORRECTION PASSED AT 28/30 AND LANDED. LATER PRODUCTION GATE SCORED 19/30.**

Parent plans: [`plan_r2_local_owner_context_correction.md`](plan_r2_local_owner_context_correction.md) and [`plan_r2_source_span_inventory_reader.md`](plan_r2_source_span_inventory_reader.md)

Handoff: [`HANDOFF.d/2026-08-11T1522Z-al8960ofc-codex-r2-numbered-inner-actor.md`](HANDOFF.d/2026-08-11T1522Z-al8960ofc-codex-r2-numbered-inner-actor.md)

## STATUS table

| Step | Status | Gate |
|---|---|---|
| N0. Freeze the 26/30 baseline | ✅ complete | Unsupported rows were 14, 16, 26, 29. |
| N1. Add generic marker tests | ✅ complete | All allowed marker forms, forbidden forms, exact offsets, actor resets, and false-owner guards are covered. |
| N2. Correct source owner parsing | ✅ complete | One marker is skipped only for direct-actor testing; full-span verb indexes remain unchanged. Review also found and prompted a general stale-reset fix. |
| N3. Run the unchanged score gate | ✅ complete | 28/30 from 139 seeds. Rows 14 and 29 recovered; all prior 26 rows remain supported; only 16 and 26 remain unsupported. |
| N4. Full local suite and fresh review | ✅ complete | All 15 commands pass after the fix. Codex and GLM 5.2 follow-ups both returned `APPROVED FOR CI` with no P0/P1. |
| N5. Land local work | ✅ complete | Commit `62330bdb0b477abb373fa1d155b104cee45a8b66` is pushed to `main`; CI run `31508223778` passed. No deploy or production action occurred. |

Fresh-session start: the local correction is complete. Albert later authorized the parent plan's one production gate. It scored 19/30 on map `37a8fc62-23e4-46b7-8464-d1c784dc73cd`, so the parent plan's hard stop now controls. Do not run another gate.

## 1. Ultimate goal

The Oracle must recognize a directly stated duty owner even when a source line places one normal list marker between an outer formatting label and that owner. If a step conflicts with this goal, the goal wins: stop and flag it. Success must come only from the exact completion-visible seed.

## 2. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed business knowledge system. The TypeScript/pnpm repo is `C:\repos\oracle`, GitHub `u2giants/theoracle`, branch `main`. Web production is `https://oracle.designflow.app`; Trigger.dev project is `proj_wgpzsvhmsopqhvwqaycn`; Supabase is `eqccjfbyrywsqkxxpjvg`. This plan changes local source parsing only.

## 3. What triggered this work

The authorized owner-context correction improved the unchanged pinned verifier from 16/30 to 26/30. Rows 14 and 29 already contain the correct actor, action, and object in their exact spans, but `directDutySubject` fails because `1.` or `2.` appears after the outer bracket. Albert authorized this bounded follow-up on 2026-08-11. GLM 5.2 verdict: `AGREE WITH BOUNDED NEXT CORRECTION`, report `.ai/reviews/glm-r2-inventory-p6-final-20260811T145113Z.md`.

## 4. Scope

In scope: one optional source list marker inside `directDutySubject`, invented tests, unchanged pinned scoring, full local checks, fresh review, commit/push/CI if all gates pass.

Out of scope: rows 16 and 26, other splitting or heading rules, verifier/scorer/answer-key changes, aliases, wider spans, budgets, models, database, UI, merge/apply, deployment, or production.

## 5. Current code state

Pushed `main` is `85dab98`. The combined implementation is local and uncommitted. The unchanged gate now reports 28/30. Rows 16 and 26 remain outside this plan.

## 6. Root cause and findings

Row 14 is `[Licensed Team] 1. Lic Coordinator Download...`; row 29 is `[Lic Coordinator] 2. Licensed team provides...`. After the bracket is removed, the direct-subject regex sees a digit rather than an actor. The general fix is to skip exactly one recognized marker only while testing/extracting the actor. The verb index, evidence, offsets, `listLike`, `span`, `trimmed`, and `listStructured` remain untouched.

## 7. Rejected approaches

- Do not strip arbitrary numbers, alphabetic prefixes, multiple markers, or `Step 1:`.
- Do not change outer span parsing, list classification, source offsets, or completion visibility.
- Do not solve rows 16/26 or add a one-row bridge if the score stays below 27.
- Do not land the 26/30 diff alone.
- The first 27/30 attempt regressed row 24 because an actor candidate ended in `in`. A general trailing-preposition rejection restored row 24 and raised the result to 28/30.
- Independent review found that unrelated prose left a stale reset flag which erased a later valid actor heading. Clearing that flag when a new actor heading is proved fixes the general boundary case.

## 8. Locked decisions

Allowed marker grammar is exactly one `\d+[.)]\s*` or one `[-*•]\s*` immediately after the outer bracket and whitespace. Forbidden: years without `.`/`)`, alphabetic markers, nested/multiple markers, or intervening text. The optional skip is private to `directDutySubject`. `verbIndex` remains from `sourceDutyVerbMatch(sourceSpan)` against the full original span. No open design decision remains.

## 9. Implementation plan

1. Run the pinned verifier and record 26/30. Gate: rows 14,16,26,29 unsupported.
2. Add invented tests in `apps/workers/src/__verify__/r2-responsibility-reader.ts` for `1.`, `1)`, `12.`, and `-` before an inner actor. Add negatives for `2024`, `A.`, no inner actor, condition/recipient/system text, and the already-working no-marker form. Gate: failures isolate only the marker shape.
3. Change only `directDutySubject` in `apps/workers/src/lib/responsibility-reader.ts`. After finding the outer bracket prefix, compute an actor-test start after at most one allowed marker. Test and extract the actor from that position. Keep `verbIndex` from the full span. Gate: generic tests pass and raw quote/offset assertions remain exact.
4. Run the unchanged pinned verifier. Gate: at least 27/30, baseline 26 supported rows remain a subset, rows 16/26 stay unchanged, and no outside text is used. Below 27 stops all work.
5. If passing, run every parent-plan section-10 command, anti-leak search, and `git diff --check`. Gate: all exit zero.
6. Run one fresh independent read-only implementation review. Fix valid findings and rerun gates. Gate: no P0/P1 and explicit approval.
7. Update all three plan status tables and a new handoff. Verify git identity, stage exact files, commit/push `main`, and wait for green CI. Gate: exact SHA and run recorded. Do not deploy.

## 10. Tests required

Positive: outer actor plus `1.`, `1)`, `12.`, or `-` then direct inner actor. Negative: `2024`, `A.`, multiple marker, bare verb, condition, recipient, system, and no-marker regression. Assert full-span verb index behavior indirectly through the final normalized span, exact evidence slice/offsets, unchanged row-16 seed diagnostics, unchanged row-26 span, and no regression of the 26-row supported set. Run every exact command in parent plan section 10.

## 11. Constraints and gotchas

Work on `main`; use `apply_patch`; preserve unrelated untracked files; stage exact paths only; keep Albert's commit identity. Never change fixture/scorer/threshold/budgets/models/request visibility/merge/apply. No production, deployment, database, or secret action.

## 12. Access and environment

Use pnpm from `C:\repos\oracle`. GitHub CLI and GLM harness are authenticated. The local pinned fixture is `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`. No secret is needed; secrets remain in 1Password vault `vibe_coding`.

## 13. Definition of done, risks, and open questions

Done means at least 27/30 unchanged support, no prior-row regression, all local commands green, independent approval, updated docs/handoff, commit/push/green CI, and zero production/deploy/database/model/merge/apply action. Risk: wrong index arithmetic corrupts the normalized span; full-span index tests prevent it. Risk: permissive marker stripping misreads numeric objects; negatives prevent it. Below 27 is a hard stop. No open question remains.

Final review evidence: Codex session `019ff16e-013e-7900-bd0d-bd01e7758e1d` returned `APPROVED FOR CI` after its actor-reset finding was fixed. GLM 5.2 session `r2-inventory-p6-final` independently returned `APPROVED FOR CI`, with no P0/P1 and three non-blocking notes; report `.ai/reviews/glm-r2-inventory-p6-final-20260811T153842Z.md`.

### Self-audit

Passed. Sections 1-4 define goal, app, trigger, and scope; sections 5-8 carry exact state, root cause, rejected paths, and locked grammar; sections 9-12 give file-level steps, tests, constraints, and access; section 13 defines landing and stop conditions. A clean session needs no chat context, and the goal is explicit enough to stop any unsafe score gain.
