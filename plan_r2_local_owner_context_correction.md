# R2 Local Source-Span Owner Correction Plan

Status: **AUTHORIZED FOLLOW-UP PASSED LOCALLY AT 28/30. PRODUCTION FORBIDDEN.**

Created: 2026-08-11

Parent plan: [`plan_r2_source_span_inventory_reader.md`](plan_r2_source_span_inventory_reader.md)

Session handoff: [`HANDOFF.d/2026-08-11T1306Z-al8960ofc-codex-r2-owner-correction-plan.md`](HANDOFF.d/2026-08-11T1306Z-al8960ofc-codex-r2-owner-correction-plan.md)

## STATUS table

| Step | Status | Evidence / next gate |
|---|---|---|
| Plan review. GLM 5.2 independent challenge | ✅ approved | Initial verdict `CHANGES REQUIRED BEFORE IMPLEMENTATION`; four P1 findings were corrected. Follow-up verdict `APPROVED FOR IMPLEMENTATION`, report `.ai/reviews/glm-r2-inventory-p6-final-20260811T132032Z.md`; no P0/P1 findings remain. |
| C0. Freeze the correction contract and residual matrix | ✅ complete | 2026-08-11: unchanged verifier reproduced 16/30 with unsupported rows 3, 6, 7, 8, 9, 10, 11, 13, 14, 16, 21, 22, 26, and 29. Generic invented regression tests now fail on the known actor-context defect. |
| C1. Correct source-bound owner propagation | ✅ complete | Generic tests prove actor carry-through, inert descriptive bracket/colon labels, prose continuation, unrelated-narrative reset, markdown-section reset, new-actor replacement, and exact quote/offset integrity. |
| C2. Resolve model-visible actor conflicts | ✅ complete | The original correction plus the separately authorized numbered-inner-actor follow-up cover direct subjects, exact list markers, recipient/system safety, and ambiguous no-guess behavior. |
| C3. Preserve owner and coherent assignment through source splitting | ✅ complete | Generic tests prove coherent children retain actor/action/object and exact evidence, incoherent children collapse to one degraded parent, and identical reruns preserve IDs and order. |
| C4. Run the complete local gate and anti-leak audit | ✅ passed by authorized follow-up | The unchanged verifier reached 28/30 from 139 seeds. Every prior supported row remains supported. Only rows 16 and 26 remain unsupported. |
| C5. Independent review and landing decision | ✅ approved for CI | Full suite passed after the fix. Codex and GLM 5.2 follow-ups both returned `APPROVED FOR CI` with no P0/P1. Landing remains; production is forbidden. |

Fresh-session starting point: **finish review and land the honest 28/30 local correction**. Do not deploy, run production, consume the production gate, enable merge/apply, change the verifier, or raise a budget.

Owner authorization: Albert explicitly authorized implementation on 2026-08-11 through the clean-context implementing-agent instruction. This authorization covers C0-C5 only and does not authorize release or production work.

GLM 5.2 review record: the initial full-context turn returned `CHANGES REQUIRED BEFORE IMPLEMENTATION` and found four P1 plan gaps. The corrected follow-up returned `APPROVED FOR IMPLEMENTATION` with no remaining P0/P1 finding. The follow-up reported 204,864 cached input tokens, 668 new input tokens, and 1,312 output tokens. Its only P2 notes are to verify markdown-heading resets against real parser behavior, keep the typed-context representation choice local, ensure standalone actor headings do not conflict with duty-bearing prose paths, and update this status before C0. None changes the frozen contract.

---

## 1. Ultimate goal

The Oracle must understand who owns each real business duty from the same exact source text that its completion model receives. It must not lose duties because a numbered list omitted the actor on later lines, and it must not attach fake actors such as a descriptive heading.

The immediate success measure is the unchanged local pinned verifier: at least 27 of 30 expected responsibility rows must have one unique, source-grounded seed containing enough owner, action, and object evidence. Quality rules remain strict. A higher score is valid only when production architecture makes the needed context part of `responsibilityCompletionRequest(seed).sourceSpan` through a general source rule.

If a step conflicts with this goal, the goal wins. Stop and flag it. Never improve the score by giving the verifier text the completion model cannot see.

## 2. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees upload documents and ask business questions. TypeScript workers discover duties and process facts, bind accepted records to exact source evidence, and prepare reviewable business maps.

- Repository: `u2giants/theoracle` at `C:\repos\oracle`.
- Branch: `main` only.
- Stack: TypeScript, pnpm, Turbo, Next.js 16, Trigger.dev, Drizzle, and Supabase.
- Web production URL: `https://oracle.designflow.app`.
- Worker project: Trigger.dev `proj_wgpzsvhmsopqhvwqaycn`.
- Database project: Supabase `eqccjfbyrywsqkxxpjvg`.
- Source-span and inventory code: `apps/workers/src/lib/responsibility-reader.ts`.
- Production orchestration: `apps/workers/src/lib/source-workflow-read.ts`.
- Pinned verifier: `apps/workers/src/__verify__/r2-pinned-inventory.ts`.
- General R2 verifier: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.
- Parent contract: `plan_r2_source_span_inventory_reader.md`.

This correction is local reader architecture only. It does not authorize production or cloud work.

## 3. What triggered this work

Commit `0ea1180c073b854e1a5826cd7dd06f264b739e21` is pushed to `main`, and GitHub Actions run `31450496620` passed. R2 phases P0 through P4 and the P6 code-quality fixes are complete.

P5 originally appeared to score 27/30 because verifier code searched source text before a seed for an owner heading. Production completion never receives that prefix. Removing the invalid fallback exposed the honest score: 16/30 from 144 source-bound seeds. The frozen acceptance line is 27/30.

The unsupported one-based rows are 3, 6, 7, 8, 9, 10, 11, 13, 14, 16, 21, 22, 26, and 29. The read-only diagnosis used only `responsibilityCompletionRequest(seed).sourceSpan` and found:

| Row | Expected duty | Exact model-visible failure |
|---:|---|---|
| 3 | Lic Manager requests order value and units from Sales | Owner and object are visible, but the span says “reach out” and “get”; the verifier has no source-grounded action-family match for normalized `request`. |
| 6 | Licensed Team saves BA form to SharedLic | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 7 | Licensed Team saves BA number to MasterData | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 8 | Licensed Team saves BA number to DesignFlow | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 9 | Licensed Team saves BA number to ColdLion | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 10 | Licensed Team assigns revision to SKU designer | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 11 | Licensed Team updates Microsoft Loop status | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 13 | Licensed Team resubmits revised tech pack | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 14 | Lic Coordinator downloads PPS photos | Exact span contains outer `[Licensed Team]` and inner `Lic Coordinator`; current owner selection chooses the conflicting outer tag. |
| 16 | Licensed Team reviews PPS photos against tech-pack specifications | Split children divide `review` from the object details, and both children inherit `the following scenarios`; there is no one coherent unique assignment. |
| 21 | Lic Manager submits factory audits | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 22 | Lic Manager enters factory information in MasterData | Action and object are visible; owner is falsely rendered as `the following scenarios`. |
| 26 | Licensed Team submits quarterly royalty reports | Seed is only `[the following scenarios] Submit the Reports`; it lacks both the owner and the heading-derived `quarterly royalty` object words. |
| 29 | Licensed Team provides assets to partners | Exact span contains outer `[Lic Coordinator]` and inner `Licensed team`; current owner selection chooses the conflicting outer tag. |

Reproduction is local only:

```powershell
pnpm --filter @oracle/workers run verify:r2-pinned-inventory
```

Expected pre-fix outcome: exit 1, 16/30, with exactly the unsupported rows above.

### C4 measured result, 2026-08-11

The unchanged verifier reached **26/30** from 139 source-bound seeds. All sixteen rows supported at
baseline remained supported. Newly supported rows were 3, 6, 7, 8, 9, 10, 11, 13, 21, and 22.
The four residuals are:

| Row | Exact model-visible residual after C1-C3 |
|---:|---|
| 14 | The seed remains `[Licensed Team] 1. Lic Coordinator Download the photos from the Factory Sample Request email.` The direct-actor helper handles an inner actor after an outer tag, but not the intervening numbered-list marker. |
| 16 | The source still becomes two children: `[Lic Coordinator] Review PPS photos` and `[Lic Coordinator] ensure that the photos match the tech pack specifications & can be submitted to the licensors.` No one unique seed contains the expected review action plus all required object anchors. |
| 26 | The exact request remains `[Licensed Team] Submit the Reports`; it still lacks source-bound `quarterly royalty` object words. |
| 29 | The seed remains `[Lic Coordinator] 2. Licensed team provides assets to partners so they can create their concepts.` The direct-actor helper again does not pass the numbered-list marker between the outer tag and inner actor. |

Per C4 step 17, no additional parser bridge, alias, wider span, heading rule, or extra context was
added. C5 was not started.

Albert later authorized the separate bounded plan `plan_r2_numbered_inner_actor_correction.md`.
That exact-span correction recovered rows 14 and 29. The unchanged verifier now reports **28/30**
from 139 seeds, with only rows 16 and 26 unsupported and no loss from the prior 26-row set.

## 4. Scope

### In scope

- Correct how `sourceDutySpanDetails` recognizes a real owner heading.
- Carry a legitimate list owner across sibling numbered or bulleted duties inside the same source section.
- Prevent descriptive text such as `the following scenarios` from becoming an owner.
- Resolve conflicts using actor text already inside the exact raw duty span.
- Preserve a legitimate owner when a raw duty becomes deterministic source children.
- Keep one coherent seed when splitting would separate the expected action from its required object anchors.
- Add generic, invented tests that prove each rule without pinned-company vocabulary.
- Re-run the unchanged pinned inventory verifier and all parent-plan section 10 checks.

### Not in this plan

- No verifier, answer key, threshold, matcher, fixture SHA, tokenization, or object-overlap change.
- No production prompt change unless a failing generic test proves the request contract itself is wrong. If that happens, stop for owner review.
- No answer-key aliases or fixture-derived terms in production code.
- No source-prefix, earlier-heading, nearby-duty, or answer-key-only context at verification time.
- No larger completion span assembled from neighboring duties.
- No budget increase, extra retries, model change, model bake-off, database change, UI work, deployment, production run, merge, or apply.
- Row 3 action normalization and row 26 heading-derived object enrichment are not automatic implementation targets. They require a generic rule proven safe after C1-C3. The plan may pass at 27/30 without solving both.

## 5. Current state of the code

`apps/workers/src/lib/responsibility-reader.ts:820-929` contains `sourceDutySpanDetails`. It walks `logicalSourceSpans(rawText)`, stores `ownerHeading`, recognizes list-like spans, and creates the normalized `sourceSpan` sent to completion.

The current heading rule at lines 870-873 treats any bracketed text or short colon-ended text as an owner. This allows descriptive bracket text such as `[the following scenarios]` to replace a real actor.

The owner precedence at lines 877-885 is:

1. outer bracket tag,
2. prose owner before the first duty verb,
3. remembered heading.

That order causes rows 14 and 29 to choose the outer bracket even when the visible duty body names the actual actor.

Lines 887-926 split one logical span on `DUTY_SPLIT_PATTERN`. Owner decoration occurs separately on each part. `buildResponsibilitySourceInventory` at lines 1290-1382 then may turn those parts into source children. Row 16 shows that a split can separate the action `review` from the required `tech pack specifications` object and attach the same false heading to both.

`responsibilityCompletionRequest` at lines 201-213 correctly passes only the seed's immutable `sourceSpan`, quote, chunk, and offsets. Do not expand that request from unrelated source text.

`apps/workers/src/__verify__/r2-pinned-inventory.ts` correctly uses only `responsibilityCompletionRequest(seed).sourceSpan`. Its `ownerAt` helper recognizes only model-visible owners. It must remain unchanged during C1-C4 except for a test-only diagnostic that does not affect scoring, and even that should be avoided unless needed.

Current release state:

- HEAD: `0ea1180c073b854e1a5826cd7dd06f264b739e21` on `main`, pushed.
- CI: GitHub Actions run `31450496620`, passed.
- Production: no R2 inventory correction deployed; no production gate consumed.
- Working tree contains many unrelated untracked `.ai`, browser, and screenshot files. They belong to other sessions and must remain untouched.

## 6. Key findings and root cause

The primary root cause is not model quality. The pure source-span builder writes the wrong owner into the exact request contract.

`ownerHeading` is semantically untyped. Any bracketed phrase can become an owner and remain active for later numbered list items. The phrase `the following scenarios` entered this state earlier in the document and then contaminated many unrelated seeds. This accounts for nine direct failed rows and contributes to row 16.

The second root cause is actor precedence. A formatting tag is treated as stronger than a direct actor phrase in the duty body. Rows 14 and 29 contain enough exact text to select the correct actor, but current code selects the outer tag.

The third root cause is split coherence. The source splitter can divide a coordinated duty into children that do not each contain enough action and object text to express the intended responsibility. Strict validation then correctly refuses to combine them.

Two residuals are different:

- Row 3 needs a generic action-normalization rule from “reach out…get” to `request`, or it may remain unsupported.
- Row 26 needs legitimate section context for `quarterly royalty`, but its exact duty is only “Submit the Reports.” Importing a heading into the seed is valid only if a generic typed section-label rule is designed and tested. It must not be added merely to gain this row.

The likely bounded path can recover at least 11 rows through owner correction alone, taking the score from 16 to 27 without relying on rows 3, 16, or 26. The exact result must be measured, not assumed.

## 7. Approaches considered and rejected

1. **Restore the source-prefix owner fallback.** Rejected because it let verification inspect text the completion model never receives. It produced a false 27/30.
2. **Borrow the nearest earlier heading or nearby duty during scoring.** Rejected for the same reason. The fix must change the production seed contract itself.
3. **Add role, system, action, or object aliases from the answer key.** Rejected as fixture leakage. Production vocabulary must remain general.
4. **Treat any bracketed phrase as an owner.** This is the present bug. Descriptive labels are not actors.
5. **Always trust an outer bracket over an inner subject.** Rejected by rows 14 and 29. The exact body explicitly names the actor performing the duty.
6. **Always trust the inner subject.** Also unsafe. A body can mention another person as an object or recipient. The rule must require a direct subject immediately governing a duty verb.
7. **Join adjacent duties into a larger completion span.** Rejected because it can mix actions and objects across duties and defeat unique assignment.
8. **Disable multi-verb splitting.** Rejected as too broad. Existing valid source-child behavior and audit identity must remain. Only incoherent splits should stay as one incomplete or safely parsed unit.
9. **Solve row 26 by copying its heading unconditionally.** Rejected until a generic distinction exists between an actor heading and a semantic section label. Owner context and topic context are different data.
10. **Deploy and see whether the model fixes it.** Forbidden. The unchanged local gate must reach 27/30 first.

## 8. Design decisions

### Locked decisions

1. The completion model sees only `responsibilityCompletionRequest(seed).sourceSpan`.
2. Evidence quote, offsets, chunk ID, and seed identity remain source-bound and immutable.
3. The pinned verifier, answer key, `field-aware-v3`, 27/30 line, fixture SHA, budgets, and merge/apply false state do not change.
4. Production code must use generic syntax and actor rules, never company or fixture vocabulary.
5. A normalized owner added to `sourceSpan` must be derived from the same logical source structure that owns that duty, not a free search over earlier text.
6. A direct grammatical actor governing the duty verb outranks a conflicting formatting tag. A mentioned recipient or object does not.
7. If ownership remains ambiguous, keep the seed incomplete and degraded. Never guess.
8. No production or deployment action occurs below 27/30.

### Open implementation judgments

1. Whether to represent source parsing state as one typed context object or separate `actorHeading` and `sectionHeading` fields. Prefer the smallest clear change, but descriptive headings must never occupy the actor slot.
2. Whether row 16 should remain a single seed or create one coherent child. The chosen result must preserve exact quote/offset integrity and one unique action/object assignment.
3. Whether to attempt row 3 or row 26 after C1-C3. Attempt only through a separately written, generic design approved by Albert. The implementing session may diagnose them but may not add a bridge rule on its own.

### Locked actor-context state machine

1. `sourceDutySpanDetails` must track `provenActor` separately from non-actor section or descriptive text.
2. A duty-bearing span proves an actor when either:
   - a direct grammatical subject immediately governs the duty verb; or
   - an inline bracket label is attached to that same duty-bearing span and no conflicting direct grammatical subject exists.
3. A standalone bracket or colon heading may prove an actor only when a generic `looksLikeActorLabel` helper accepts it. The candidate rule is deliberately syntax-based: a short noun label, not a sentence; no condition opener such as `if`, `when`, `after`, `before`, or `unless`; no descriptive determiner such as `the following`, `these`, `those`, `this section`, `note`, `overview`, `purpose`, or `scenario`; and no duty verb. Capitalization alone is insufficient. The helper must be direct-tested with invented positive and negative labels before it is used.
4. A bracket or colon heading rejected by `looksLikeActorLabel` is descriptive context. It does **not** replace or reset `provenActor`.
5. `provenActor` resets only when:
   - a new proven actor replaces it;
   - a real markdown section heading (`#` through `######`) begins a new section and no direct actor is attached to the next duty; or
   - an unrelated narrative paragraph is followed by a fresh list sequence rather than a continuation of the current numbered/bulleted list.
6. A descriptive bracket/colon label inside an active list does not count as a real section reset. This exact rule is required for the nine `[the following scenarios]` failures.
7. An ordinary prose continuation inside the same numbered/bulleted list does not reset the actor. Unrelated prose outside the list does. The state machine must use list continuity and section structure, not elapsed characters or arbitrary prefix searching.
8. If syntax cannot classify an actor or reset boundary safely, do not add an owner. Keep the seed incomplete and degraded.

## 9. Implementation plan

### Phase C0: Freeze and prove the baseline

1. Re-read `AGENTS.md`, this plan, the parent plan, and the newest R2 handoff. Confirm `main` and commit identity. Preserve unrelated files.
2. Run the pinned verifier once. Record 16/30 and the exact 14 unsupported rows in the test output or plan status. Do not edit the verifier.
3. Add or extend generic tests in `apps/workers/src/__verify__/r2-responsibility-reader.ts` that reproduce these syntax classes using invented departments and systems. These tests may fail locally during C0, but they must not be committed or pushed in a failing state. C1-C3 must make them pass before any landing step:
   - one explicit actor followed by three untagged numbered duties;
   - a descriptive bracket label before duties;
   - one proven actor, then a descriptive bracket label, then numbered duties that must retain the proven actor;
   - one proven actor, then a descriptive colon label, then numbered duties that must retain the proven actor;
   - an outer tag conflicting with a direct inner actor;
   - an outer tag plus a recipient mention that must not become the actor;
   - a coordinated review-and-ensure sentence where object details must remain usable.

Verification gate: the new tests fail for the same architectural reasons as the diagnosis, while existing tests still compile. You will know the fixture is generic when no pinned role, system, destination, or object term appears in the new test strings.

### Phase C1: Type and bound owner context

4. Refactor `sourceDutySpanDetails` in `apps/workers/src/lib/responsibility-reader.ts:820-929` so remembered context distinguishes an actor from descriptive or topic text.
5. Implement the locked actor-context state machine from section 8. Accept a remembered actor only when the generic syntax rule proves an actor. Do not promote arbitrary bracket text or colon headings into the actor slot.
6. Carry that actor across directly following sibling list items. A rejected descriptive bracket or colon heading does not replace or reset it. Reset only at the exact boundaries locked in section 8. The implementation must not search arbitrary earlier source text.
7. Preserve current raw quote and offset binding. Only the normalized `sourceSpan` may add `[owner]`; `evidenceQuote` must remain the exact raw slice.

Verification gate: generic list tests show every sibling request contains the legitimate actor, descriptive labels never appear as owners, unrelated sections do not inherit the old actor, and quote/offset integrity tests pass.

### Phase C2: Resolve exact-span actor conflicts

8. Add a pure helper near `sourceDutySpanDetails` that identifies a direct subject immediately governing a duty verb inside the raw duty span. Reuse `sourceDutyVerbMatch`, `MODAL_OR_DIRECT_OWNER_PATTERN`, and existing normalization where safe.
9. Change owner precedence so a proven direct duty subject can override a conflicting outer formatting tag. Do not let recipients after prepositions, systems, or names inside objects override the owner.
10. Record a generic parse diagnostic when an outer tag was overridden by a direct actor. Do not add a new database field; the diagnostic stays in existing inventory audit JSON.

Verification gate: the direct-actor conflict test selects the inner actor; the recipient-control test keeps the outer actor; ambiguous syntax produces no guessed owner and remains incomplete.

### Phase C3: Preserve coherent source assignments

11. Review the split logic at `responsibility-reader.ts:887-926` and child construction at lines 1312-1382. For a coordinated source duty, require each child to retain a legitimate owner plus one action and a non-empty source-derived object.
12. When splitting would strand required object anchors in a sibling, do not emit a misleading complete child. Prefer one coherent source-bound seed or an `ambiguous_multi_verb` parent that remains degraded. Never stitch words from a neighboring duty.
13. Preserve stable source offsets, source order, parent/child IDs, audit-only parent behavior, destination splits, and deterministic rerun identity.

Verification gate: the generic review-and-ensure case yields one unique usable assignment if syntax supports it, or one explicit incomplete parent if it does not. Existing destination and multi-verb tests remain byte-stable.

### Phase C4: Measure before considering residual rules

14. Run `pnpm --filter @oracle/workers run verify:r2-pinned-inventory` unchanged.
15. Before counting recovered rows, verify that every previously supported row remains supported. Record any regression and its exact request span.
16. If the result is at least 27/30, stop architecture changes. Do not pursue rows 3, 16, or 26 for a higher score.
17. If the result is below 27, produce a new exact-span residual matrix and stop. The 16 + 11 estimate has zero margin, so 24-26 is a credible outcome. The implementing session may not add another alias, heading rule, wider span, or other bridge correction to gain one or two rows. Rows 3 and 26 require a new written design and Albert's authorization; row 16 requires the same if C3's already-bounded generic split work did not recover it.

Verification gate: either the unchanged verifier reaches at least 27/30, or the phase ends with an honest lower score and no production action.

### Phase C5: Full local verification and independent review

18. Run every exact command in parent-plan section 10, followed by `git diff --check` and an anti-leak search over production reader and prompt files.
19. Run one fresh read-only independent review with this plan, the parent plan, the 14-row diagnosis, the exact diff, and all test results. Require file-and-line findings, locked-decision audit, and a clear `APPROVED FOR CI AND LIVE REGATE` or `CHANGES REQUIRED` verdict.
20. Correct only valid findings and repeat local verification. Any correction that changes the score contract, budgets, or request visibility requires new owner approval.
21. Update this STATUS table and the parent plan with the exact score and review result. Create a new write-once handoff for the implementing session.

Verification gate: all local checks pass, honest support is at least 27/30, the final review has no P0/P1 issue, and docs match the actual state.

### Context cut point

Stop after C5. A different release session must re-read this plan plus parent-plan sections 11-13 before any P7 action. This plan itself does not authorize deployment or production.

## 10. Tests required

Add or preserve these direct tests in `apps/workers/src/__verify__/r2-responsibility-reader.ts`:

1. `explicit actor carries through sibling numbered duties`.
2. `descriptive bracket labels never become owners`.
3. `actor inheritance resets at a new section or explicit actor`.
4. `direct duty subject overrides a conflicting outer formatting tag`.
5. `recipient or object name does not override the governing actor`.
6. `ambiguous actor conflict remains incomplete`.
7. `split children retain legitimate owner and exact evidence`.
8. `incoherent multi-verb split does not create a false complete child`.
9. `identical reruns preserve seed IDs, source order, and audit order`.
10. `raw evidence quote equals source slice at recorded offsets`.
11. `no source-prefix or nearby-duty context enters completion requests`.
12. `generic negative list does not inherit an actor across unrelated prose`.
13. `actor persists through a non-actor descriptive bracket heading inside the same list or section`.
14. `actor persists through a non-actor descriptive colon heading inside the same list or section`.
15. `new proven actor replaces the prior actor for later duties`.
16. `lowercase or capitalized descriptive bracket labels are never actors`.
17. `system label before a direct duty subject does not become the actor`.
18. `condition label before a direct duty subject does not become the actor`.
19. `ordinary prose continuation inside one list preserves actor context`.
20. `unrelated narrative followed by a fresh list resets actor context`.
21. `all sixteen previously supported pinned rows remain supported before recovered rows are counted`.

Keep every parent-plan section 10 test. Run these exact commands from `C:\repos\oracle`:

```powershell
pnpm --filter @oracle/workers typecheck
pnpm --filter @oracle/ai typecheck
pnpm --filter @oracle/engines typecheck
pnpm --filter @oracle/workers run verify:r2-responsibilities
pnpm --filter @oracle/workers run verify:r2-pinned-inventory
pnpm --filter @oracle/workers run verify:source-workflow-read
pnpm --filter @oracle/workers run verify:r0-reader-validator
pnpm --filter @oracle/workers run verify:document-ingestion-fallback
pnpm --filter @oracle/ai run verify:r2
pnpm --filter @oracle/ai run verify:workflow-read
pnpm --filter @oracle/engines run verify:macro
pnpm --filter @oracle/engines run verify:macro-first
pnpm --filter @oracle/engines run verify:r1-cross-shape
pnpm --filter @oracle/engines run verify:r2-responsibilities
git diff --check
```

Anti-leak gate: derive fixture terms in verifier-only code and prove none occur in `apps/workers/src/lib/responsibility-reader.ts`, `apps/workers/src/lib/source-workflow-read.ts`, or `packages/ai/src/prompts/workflow-read.ts`.

## 11. Constraints, standing rules, and gotchas

- Work on `main`. Do not create a branch.
- Commit identity must be `Albert Hazan <u2giants@users.noreply.github.com>`.
- Use `apply_patch` for edits. Do not edit generated migrations.
- Stage only deliberate plan or implementation files. Never use `git add -A`.
- Preserve all unrelated untracked `.ai`, `.playwright-cli`, screenshot, and image files.
- No database change is authorized. This plan should need none.
- Never restore source-prefix owner lookup or let scoring inspect adjacent source.
- Never hard-code POP roles, systems, headings, partners, or answer-key phrases.
- Owner context and semantic topic context are different. Do not overload one string for both.
- A formatting label is not automatically a person or team.
- A mentioned person can be a recipient. Require grammatical control of the duty verb before treating it as owner.
- Exact evidence, field fidelity, unique assignment, stable identity, budgets, retry counts, and degraded status remain strict.
- Frozen limits remain 40 reads, 500,000 input tokens, $10 estimated cost, one quote repair, five detection retries, and one completion retry.
- Merge and apply stay false even after a passing local score.
- No UI work is in scope, so no screenshot gate is needed.
- No deployment or production run is allowed under this plan.

## 12. Access and environment

- Checkout: `C:\repos\oracle` on Windows machine `al8960ofc`.
- Repository: `u2giants/theoracle`; branch `main`; remote `origin/main`.
- Package manager: pnpm. Run commands from the repository root.
- GitHub CLI is authenticated for later CI inspection, but this planning phase needs no GitHub mutation until the plan is approved and intentionally committed.
- Pinned local fixture: `Z:\Documentation\company process - Oracle\Licensed Team Responsibilities 2 - tagged.txt`. It is verifier input only; production code may not contain its vocabulary.
- GLM review uses the installed `ai-glm` harness with `AI_GLM_CALLER=codex` and the existing Oracle session `r2-inventory-p6-final` when it remains the best topic match.
- Production services are Trigger.dev `proj_wgpzsvhmsopqhvwqaycn`, Vercel `prj_rP6Jlima7iK1paffEPhLqxlswGsC`, and Supabase `eqccjfbyrywsqkxxpjvg`. They are out of scope here.
- Secrets live only in 1Password vault `vibe_coding`. No secret is needed for local planning, implementation, or verification.

## 13. Definition of done, risks, and open questions

### Definition of done for the local correction

1. Generic tests prove correct bounded actor inheritance, direct-actor precedence, reset behavior, and split coherence.
2. Every completion request still contains only its own source-bound seed span.
3. Raw quote and offset integrity remains exact.
4. No fixture vocabulary or answer-key alias enters production code.
5. The unchanged pinned verifier reaches at least 27/30.
6. Every parent-plan section 10 command and `git diff --check` passes.
7. A fresh independent review has no P0/P1 issue and explicitly approves CI/live-regate readiness.
8. This plan, the parent plan, and a new handoff record the exact final score and residual rows.
9. Implementation is committed and pushed to `main` with green CI only after review approval.
10. Deployment and production remain separate, still blocked until a later release session follows the parent P7 rules.

### Risks and rollback

- **Owner bleed across sections.** A remembered actor could contaminate unrelated duties. Tests must pin reset boundaries. Roll back the parser change if generic negative cases fail.
- **Inner-subject false positives.** A recipient could be mistaken for the actor. Require direct control of the duty verb and keep negative recipient tests.
- **Seed identity churn.** Adding normalized owner text changes span hashes and IDs. Stable identical reruns are required, but a corrected normalized span may intentionally create new IDs relative to the broken version. Record this explicitly in audit/review; never change raw offsets or quotes.
- **Split regressions.** Owner fixes could disturb destination or multi-verb children. Existing deterministic split tests must stay green.
- **Score still below 27.** Stop. Do not deploy, add fixture rules, or raise limits.
- **Zero-margin estimate.** The owner correction predicts exactly 27/30 with no safety margin. A result of 24-26 is credible. Stop at C4 and do not add a bridge rule, alias, or extra context to gain the missing rows.
- **Score rises for the wrong reason.** Inspect each newly supported row against the exact request span. Any row relying on unavailable context is invalid even if the total passes.
- **Previously supported row regresses.** Record it before counting recoveries. A corrected total that hides a lost prior row is not acceptable evidence.

### Open questions

- The minimal safe reset boundary for actor inheritance must be chosen from generic source structure during C1.
- Row 16 may require a separate coherent-split correction after owner repair. Let the generic test decide.
- Rows 3 and 26 may remain unsupported. They are not required if the honest score reaches 27/30 through the general owner correction.
- A passing local inventory score predicts supportable seeds, not the final production score. The single frozen production gate remains a later, separately controlled action.

### Mandatory implementation-plan self-audit

1. **Could a brand-new AI session execute this plan without asking the planning session anything?** Yes. Sections 1-4 define the goal, application, trigger, complete 14-row diagnosis, scope, and exclusions. Sections 5-8 give exact code locations, root causes, rejected approaches, and locked versus open decisions. Sections 9-12 provide ordered file-level actions, verification gates, commands, constraints, access, and a context cut point.
2. **Does the plan carry every relevant background, nuance, and rejected path?** Yes. Sections 3, 6, and 7 preserve the false 27/30 fallback, honest 16/30 result, every unsupported row, the owner contamination mechanism, actor conflicts, split damage, and the bans on nearby context, fixture aliases, unconditional heading copying, broader spans, and production experimentation.
3. **Is the ultimate goal clear enough for a correct judgment call if a step is wrong?** Yes. Section 1 says the business outcome is correct source-visible duty ownership and makes the goal override the steps. Sections 8 and 13 require ambiguity to remain degraded and require stopping if an apparent score gain uses unavailable context.

Checklist result: **passed**. All 13 sections exist; the goal leads; scope and rejected work are explicit; every step names files/functions and a verification gate; tests are behavior-specific; decisions are labeled; secrets are location-only; landing includes commit, push, CI, and the separate deployment boundary; and the plan and session handoff link to each other.
