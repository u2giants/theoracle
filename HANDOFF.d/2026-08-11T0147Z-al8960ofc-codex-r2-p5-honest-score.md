# HANDOFF: R2 P5 honest-score hard stop

Created 2026-08-11 01:47 UTC on `al8960ofc` by Codex.

## 0. ⚠️ DECISIONS ONLY THE OWNER CAN MAKE

### Blocking

- Choose whether to authorize another bounded, source-grounded local architecture correction after reviewing the honest 16/30 result. Recommendation: stop code churn now and first require a short diagnosis of why 14 answer rows have no owner-visible exact span. This blocks any new R2 implementation phase.

### Recoverable

None.

### Not part of this work and nobody is on it

None discovered during this session.

### Already settled, do NOT re-ask

- 2026-08-10: the pinned verifier must judge only the exact source span the completion model receives. It may not search earlier source text for an owner.
- 2026-08-10: the frozen acceptance line is at least 27/30. A lower honest score forbids deployment and production replay.
- 2026-08-10: merge and apply remain false even if a later score passes.
- 2026-08-10: work stays on `main`; no feature branch is required for Oracle.

The next session must put the single blocking decision above to Albert in one message before starting new implementation work. It may perform read-only diagnosis first, but it must not deploy or run production.

## 1. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees ask business questions and upload documents. Background workers extract duties and process facts, bind every accepted result to exact source evidence, and build reviewable business maps.

The repository is `C:\repos\oracle`, GitHub repository `u2giants/theoracle`, branch `main`. It is a TypeScript monorepo using pnpm and Turbo. The web app runs at `https://oracle.designflow.app`. Workers run in Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`. Production data lives in Supabase project `eqccjfbyrywsqkxxpjvg`.

This handoff concerns the R2 source-span inventory reader in `plan_r2_source_span_inventory_reader.md`. The reader must discover every responsibility from exact source spans, complete missing fields, validate quotes and field fidelity, and save explicit audit results.

## 2. What we set out to do this session, and why

The session resumed P5 and P6 after Codex review `C:\repos\oracle\.ai\reviews\20260810-183652-diff-review.md` found three proof problems. The goals were:

1. Remove a verifier fallback that borrowed owner text from before the model-visible span.
2. Prove a quote repair begins with a real bad quote from the same local document, then accepts and saves the corrected quote.
3. Prove a retry discovers a genuinely new duty, late completion processes it, and the result is saved.
4. Run all P5 checks and one P6 review without deploying or touching production unless the honest score stayed at least 27/30.

The fallback removal exposed the real result: 16/30. That is the correct business outcome even though it blocks release. The session then fixed three additional correctness findings from the one Codex P6 review and obtained a GLM 5.2 second opinion.

## 3. Current state

- P0 through P4 remain complete.
- The invalid owner-prefix fallback is removed from `apps/workers/src/__verify__/r2-pinned-inventory.ts`. `ownerAt` now uses only the seed/request span.
- The honest verifier reports 16/30 supported rows from 144 source-bound seeds. Supported one-based rows: 1, 2, 4, 5, 12, 15, 17, 18, 19, 20, 23, 24, 25, 27, 28, 30. Unsupported rows: 3, 6, 7, 8, 9, 10, 11, 13, 14, 16, 21, 22, 26, 29.
- The full top-level orchestration test in `apps/workers/src/__verify__/r2-responsibility-reader.ts` uses one coherent Service Desk document. It proves same-document quote failure and repair, a retry-only newly discovered duty, late completion, accepted outcome, and saved merge-ready identity.
- Codex P6 review `C:\repos\oracle\.ai\reviews\20260810-190539-diff-review.md` found three further issues. They are fixed: final gaps force degraded status; accepted quote repair refreshes saved inventory audit counts and IDs; same-offset destination children retain source order.
- GLM 5.2 report `C:\repos\oracle\.ai\reviews\glm-r2-inventory-p6-final-20260811T012646Z.md` verified all three fixes and found no P0/P1 defects. It found three P2 cleanup items. They are fixed: the shadowed `discovered` variable was renamed; the anti-leak check includes the prompt source; the quote-repair test uses cloned prepared reads rather than mutating its input.
- Focused verifier, worker typecheck, and `git diff --check` pass after the GLM cleanup.
- Full P5 result: fourteen checks pass and only `verify:r2-pinned-inventory` fails, by design, at 16/30.
- No production run, deployment, database change, secret change, or model-setting change occurred.
- At handoff-writing time the implementation, plan update, and this handoff are local changes awaiting the closeout commit and push. The closing report must supply the final commit SHA and CI state.

Changed project files in this batch:

- `apps/workers/package.json`
- `apps/workers/src/__verify__/r2-pinned-inventory.ts`
- `apps/workers/src/__verify__/r2-responsibility-reader.ts`
- `apps/workers/src/lib/responsibility-reader.ts`
- `apps/workers/src/lib/source-reader-budget.ts`
- `apps/workers/src/lib/source-workflow-read.ts`
- `packages/ai/src/prompts/workflow-read.ts`
- `plan_r2_source_span_inventory_reader.md`
- this handoff file

## 4. Everything we tried that did NOT work

1. The old pinned verifier searched `source.slice(0, sourceStart)` for the last owner heading. It produced 27/30 but observed text the real completion model cannot see. Removing it dropped the honest score to 16/30. Do not restore this fallback.
2. The first orchestration proof used Service Desk source text but injected unrelated Finance and Operations quote-repair records. It proved only that a repair call happened. It did not prove a failed quote from the tested document was repaired and saved.
3. The first retry proof selected a seed already present in the initial inventory. It did not prove a newly discovered retry duty received late completion.
4. Several test-fixture drafts failed locally while making the new retry duty incomplete. A thinned object stopped discovery; invented trigger/system data still validated as complete; a wrong owner stopped matching. The successful fixture uses a source-bound duty with omitted trigger context, then supplies the complete trigger during late completion.
5. The first GLM 5.2 call failed before review because its permission endpoint returned HTTP 000. The session was aborted, `ai-glm doctor` and server health passed, and the same persistent session was retried successfully. Do not create a replacement GLM session for this workstream.
6. GLM's formal verdict was `CHANGES REQUIRED` despite finding no P0/P1 defect because it listed three P2 cleanups. All three were corrected after the report. No additional GLM turn was run after those mechanical cleanups.

## 5. Root causes and key findings

- The 27/30 result was not an architecture result. It depended on hidden owner context outside the completion request. The honest exact-span architecture presently supports only 16/30.
- A known missing duty can exist without an inventory seed. Therefore final omission gaps, not only incomplete inventory counts, must force degraded status. This is implemented through `responsibilityInventoryRequiresDegradedStatus` in `apps/workers/src/lib/source-workflow-read.ts`.
- Accepted quote repair changes final validation. Its saved `inventoryMatchAudit` must be recalculated from the repaired complete IDs or one audit can call the same duty both incomplete and complete. `refreshResponsibilityInventoryMatchAudit` now does this.
- Destination children share their parent's offsets. Hash-based ID order is not source order. `canonicalResponsibilityInventory` now retains insertion order for same-offset children, and a three-destination test pins it.
- A valid recovery proof must follow one document and one identity through failure, repair or late completion, validation, and durable saved audit. Call counters alone are insufficient.
- GLM 5.2 used the existing persistent session `r2-inventory-p6-final`. Its report recorded 154,752 cached input tokens and found no P0/P1 correctness, evidence, data-leak, or test-proof blocker beyond the frozen score gate.

## 6. Exact next steps

1. Read `AGENTS.md`, this handoff, and all of `plan_r2_source_span_inventory_reader.md`. You will know the starting point is correct when the plan says P5 failed honestly at 16/30 and production is forbidden.
2. Verify the closeout commit and CI result recorded in the final chat report. If CI is not green, inspect only that exact run and fix genuine failures without changing the scorer. You will know it worked when the pushed SHA's GitHub Actions run is green.
3. Re-run `pnpm --filter @oracle/workers run verify:r2-pinned-inventory` only if you need to reproduce the local result. Expect exit 1 and 16/30. You will know the guard is honest when the unsupported row list remains 3, 6, 7, 8, 9, 10, 11, 13, 14, 16, 21, 22, 26, 29.
4. Perform a read-only residual diagnosis for those 14 rows. For each row, record whether the exact model-visible seed lacks an owner, action anchor, object anchors, or unique assignment. Do not use earlier source headings or answer-key-only aliases. You will know it worked when every unsupported row has one source-grounded failure reason.
5. Put the single owner decision from section 0 to Albert: authorize or reject another bounded local architecture correction. Recommend diagnosis first and no production work. You will know the decision is complete when it is dated in the plan.
6. If Albert authorizes another correction, change only production architecture that makes owner context legitimately part of the exact seed/request contract. Do not loosen the verifier to match unavailable context. You will know it worked when the honest local verifier reaches at least 27/30 and every section 10 check passes.
7. Run a fresh independent read-only review after any correction. You will know P6 is reopened successfully only when there are no P0/P1 findings and the honest score remains at least 27/30.
8. Only after steps 6 and 7 pass may a future session consider P7 commit/deploy/one-production-gate instructions. Merge and apply remain false. You will know the release gate is open only when the plan explicitly records the passing local score and approving review.

## 7. Constraints and gotchas in force

- Work on `main`. Preserve Albert's commit identity: `Albert Hazan <u2giants@users.noreply.github.com>`.
- Do not deploy, run production, or consume the single frozen production gate while the honest score is 16/30.
- Never restore the source-prefix owner fallback, add fixture-specific production terms, weaken exact quote checks, loosen unique assignment, change the frozen 27/30 line, raise budgets, or enable merge/apply.
- The completion model sees only each seed's exact `sourceSpan`. If owner context is required, architecture must put it inside that seed through a legitimate source-bound rule.
- Preserve unrelated untracked `.ai` files, `.playwright-cli`, `detail-current.png`, and `rfq-before.png`. Do not use `git add -A`.
- No database change is authorized. Shared database changes require the separate `u2giants/shared-db` branch-and-PR workflow.
- Root `HANDOFF.md` is a static pointer. Never rewrite it or edit/delete another session's `HANDOFF.d` file.
- After adding this handoff there are six open handoff files. The next closeout must not delete any without proof that its workstream is complete.

## 8. Access and environment

- Checkout: `C:\repos\oracle`, branch `main`, Windows PowerShell, machine `al8960ofc`.
- GitHub CLI is authenticated. Repository: `u2giants/theoracle`.
- Package manager: pnpm. Run checks from the repository root.
- Pinned local fixture: `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`. Its SHA is frozen in the verifier fixture JSON.
- GLM harness is installed and healthy. Reuse Codex caller session `r2-inventory-p6-final`; do not create a new Oracle R2 P6 session.
- Trigger.dev project: `proj_wgpzsvhmsopqhvwqaycn`. Vercel project: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`. Supabase project: `eqccjfbyrywsqkxxpjvg`. None were mutated.
- Secrets live only in 1Password vault `vibe_coding`. No secret value was read or changed in this session.

## 9. Open questions and risks

- 2026-08-11: the next technical path is intentionally undecided because 16/30 is far below the frozen gate. Another code change needs Albert's authorization after the residual diagnosis.
- Risk: restoring contextual owner headings would make the score rise while violating the exact request contract. Treat any score improvement that uses text outside `responsibilityCompletionRequest(seed).sourceSpan` as invalid.
- Risk: the large implementation diff accumulated through P5/P6 corrections. Future changes should be narrow and independently reviewed rather than reopening broad architecture without a diagnosis.
- Risk: six open handoffs can bury the resume point. Do not delete them blindly; Albert should decide which older workstreams are truly finished.

## Sub-agent record: `fix_new_p6_findings` (Banach)

- Asked to fix exactly the three findings from Codex review `20260810-190539`: final gaps must degrade status, quote repair must refresh audit data, and same-offset destination children must preserve source order.
- Changed `apps/workers/src/lib/source-workflow-read.ts` and `apps/workers/src/__verify__/r2-responsibility-reader.ts` in the shared checkout.
- Added focused proof tests and reported passing worker verifier, worker typecheck, and `git diff --check`. The coordinator reran and confirmed all three.
- Did not deploy, run production, commit, push, change the score, or touch secrets.
- The agent finished normally. No separate branch, worktree, or PR exists.

## Mandatory self-audit

1. Yes. Sections 1–3 define the product, repositories, runtimes, goal, exact files, score, review evidence, and release state, so a street-new developer can resume without this chat.
2. Yes. Sections 4–5 preserve the failed verifier design, incoherent repair proof, false retry proof, failed fixture variants, GLM permission failure, and the non-obvious architectural findings needed to continue as effectively as this session.
3. Yes. Sections 0–9 and the sub-agent record cover background, purpose, current state, failures, decisions, constraints, risks, access, verification, and ordered next actions with success gates.
4. Yes. A line-by-line sweep of sections 1–9 and the sub-agent record found one owner judgment: whether to authorize another bounded local correction after diagnosis. It appears in section 0 with a recommendation and what it blocks. All other owner references are dated settled decisions or instructions not to re-ask.

Self-audit result: passed. Every required section is present, the owner-decision sweep is complete, secrets are location-only, commit/push/deploy state is explicit, and every next step has a verification gate.
