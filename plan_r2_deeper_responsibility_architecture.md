# R2 Deeper Responsibility Architecture Implementation Plan

Status: **PLAN COMPLETE. IMPLEMENTATION NOT YET AUTHORIZED OR STARTED.**

Created: 2026-07-28
Owner direction: Albert selected the deeper-architecture path by requesting this plan.
Canonical parent plan: `MACRO_FIRST_IMPLEMENTATION_PLAN.md`
Current production handoff: `HANDOFF.md`
Gate evidence: `evals/r2-responsibilities.md`
Independent plan review: GLM 5.2 returned `APPROVE WITH CHANGES`; both P1 and all six P2 changes
were incorporated on 2026-07-28 before implementation.

## STATUS table

| Step | Status | Date | Evidence / next gate |
|---|---|---|---|
| P0. Freeze baseline and prove the starting state | ⬜ open | — | Record commit, current tests, fixture hash, flags, budgets, and table counts before editing |
| P1. Separate inventory validation from field-completeness validation | ⬜ open | — | Complete quoted records survive inventory even when fields need repair |
| P2. Add deterministic multi-destination expansion | ⬜ open | — | Generic list fixtures emit one record per explicit destination |
| P3. Add one bounded combined responsibility-repair call | ⬜ open | — | One repair call fixes fields and/or quotes without exceeding the frozen repair budget |
| P4. Rebuild omission, audit, and merge-eligibility rules around complete records | ⬜ open | — | Inventory is retained, only complete records close omissions or become merge-eligible |
| P5. Complete local regression and invariant verification | ⬜ open | — | All named unit, type, workflow, R0, R1, R2, and ingestion checks pass |
| P6. Independent Grok 4.5 review and same-agent correction loop | ⬜ open | — | Grok returns `APPROVED FOR CI AND LIVE REGATE` with no P0/P1 findings |
| P7. Commit, push, CI, deploy, and run one pinned production gate | ⬜ open | — | CI green, one worker release, one disposable gate, full evidence recorded |
| P8. Apply the score decision and update durable documentation | ⬜ open | — | `>=27` continues R2; `24–26` permits bake-off; `<=23` stops for owner |

Fresh-session starting point after Albert separately asks to implement this plan: begin at **P0**.
Re-read this entire plan, `HANDOFF.md`, and the R2 section of
`evals/r2-responsibilities.md` before touching code. Update this STATUS table as each step
changes. At the marked context cut points, start a clean session and re-read every remaining phase
before continuing.

---

## 1. The ultimate goal

The Oracle must read a company responsibility document and retain the full list of duties while
also keeping each duty's owner, action, target, system, timing, cadence, and direction accurate.
Strict checks must improve weak records instead of deleting most of the useful inventory.

When this work is done:

- the pinned 30-duty responsibility document scores at least 27/30 with the frozen honest scorer;
- the responsibility inventory does not collapse when field checks become stricter;
- incomplete records are repaired only from their exact source spans;
- explicit lists of destinations produce one responsibility per destination without company-
  specific code;
- incomplete or invalid records cannot enter later business-model merge work;
- every decision remains traceable to exact source text and durable audit evidence;
- production merge and apply stay off until the existing R2 gates authorize them.

**If any step in this plan conflicts with this goal, the goal wins. Stop and flag the conflict.**
Do not mechanically follow a step that would improve the fixture score by weakening evidence,
discarding generality, hiding failures, or leaking answer-key knowledge.

---

## 2. What this application is

The Oracle is POP Creations / Spruce Line's evidence-backed company knowledge system. Employees
upload documents and ask questions. Worker jobs read the documents, extract claims and business
structure, validate exact quotes, and build traceable knowledge that admins can review.

Repository and runtime:

- Repository: `u2giants/theoracle`, local checkout `C:\repos\oracle`.
- Branch policy: `main` only. Do not create a feature branch.
- Stack: TypeScript monorepo using `pnpm` and Turbo.
- Web app: Next.js 16 in `apps/web`, deployed by Vercel.
- Workers: Trigger.dev tasks in `apps/workers`.
- AI contracts and prompts: `packages/ai`.
- Deterministic business rules: `packages/oracle-engines`.
- Database: hosted Supabase project `eqccjfbyrywsqkxxpjvg`.
- Trigger.dev project: `proj_wgpzsvhmsopqhvwqaycn`.
- Production web URL: `https://oracle.designflow.app`.

This plan changes the R2 responsibility-reading control plane only. It does not authorize
business-model merge, apply, claim serving, or later macro stages.

---

## 3. What triggered this work

R2 requires the pinned `Licensed Team Responsibilities 2 - tagged.txt` fixture to produce correct
responsibility records for at least 90% of its 30-row answer key. The source SHA-256 is:

`398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`

The frozen answer key is `licensed-team-responsibilities-v1`. The frozen matcher is
`field-aware-v3`. Passing means at least 27/30.

Six live gates established a stable failure:

- Batch E scored 20/30 and kept 179 responsibilities.
- Batch F added strict span-bound field checks, scored 14/30, kept only 92 responsibilities, and
  raised full-map drops from 31 to 170.
- Batch F's grounded quote repair cut its own root quote failures from 10 to 4. Batch E's
  post-repair count was 6, so quote copying was not the main regression.
- Batch F lost seven duties that Batch E had already matched: rows 5, 7, 8, 9, 10, 13, and 25.
- It gained only row 19.

The terminal Batch F production evidence is:

- Commit `08c2631`.
- CI run `30385119532`.
- Trigger worker `20260728.5`, deployment `f7trr764`.
- Trigger run `run_06fqjpv1ci6sbrh4csk56mvd01`.
- Document `7001cd1e-fd85-45d3-a8d6-bb5141e200d7`.
- Source-workflow job `f145614a-e443-4202-bb6e-026a05a267a9`.
- Map `85fc772b-92c3-4101-8b2a-288ba9ad6d4a`.
- Final model run `88b87385-7ec0-4b8f-b0f9-c7546c291382`.
- Final context pack `ad2a61b9-ce7c-4eb1-88a1-c910d8281d6a`.

The production gate used only 23/40 calls, 59,279/500,000 input tokens, and about $0.296/$10.
The failure was not budget exhaustion. Merge and apply remained false. The three durable
business-model tables remained empty.

Grok 4.5 reviewed the hard stop and found the main regression was control-system behavior:
strict field checks dropped incomplete records, but the pipeline had only quote repair and no
field-completion repair. Albert chose the deeper-architecture planning path on 2026-07-28.

---

## 4. Scope

### In scope

- Preserve exact-quote, structurally valid responsibility inventory before field-completeness
  enforcement.
- Classify field-completeness failures without deleting the inventory record.
- Add one bounded repair call that can:
  - complete responsibility fields from a selected exact source span; and
  - perform candidate-bound quote repair for quote-only failures.
- Deterministically expand one duty with an explicit destination/system list into one thin
  responsibility per destination.
- Make omission coverage depend on field-complete records.
- Make later merge eligibility depend on field-complete records.
- Add durable drop and repair taxonomy.
- Add focused unit and orchestration tests.
- Run one independently reviewed production gate after release.

### Not in this plan

- No Batch G free-form prompt polish.
- No model bake-off before the redesigned path lands.
- No answer-key, company role, PPS, BA, licensor, or fixture strings in runtime logic.
- No scorer, fixture, key, threshold, quote-policy, or budget changes.
- No new database table or migration unless implementation proves existing `validationJson`
  cannot carry the required audit. If that happens, stop and write a separate shared-database
  plan. Do not add an Oracle app-repo migration.
- No R0, R0.1, or R1 redesign.
- No changes to process, narrative, ruleset, reference, or conversation readers.
- No shadow merge enablement, apply, review UI, serving, R3, or later macro stages.
- No manual edit of production maps or answer-key results.
- No multi-model voting or hidden fallback.

---

## 5. Current state of the code

Everything below is committed, pushed to `main`, CI-green, and deployed in worker
`20260728.5`.

### Responsibility discovery and field checking

`apps/workers/src/lib/responsibility-reader.ts` currently contains:

- `validateResponsibilityFieldFidelity` around lines 206–280. It checks owner, action family,
  polarity, object tokens, invention, and multi-verb duties.
- `sourceDutySpanDetails` around lines 494–574. It discovers source duty spans and keeps raw
  source offsets.
- `bindForcedResponsibilitySpans` around lines 601–633.
- `canonicalizeForcedResponsibilityOutput` around lines 634–709.
- `finalizeForcedResponsibilityAudits` around lines 711–764.
- `resolveEnclosingResponsibilityDutySpan` around lines 838–866.
- `findResponsibilityOmissions` around lines 868–934.
- `validateResponsibilityRead` around lines 1310–1477.

The critical current behavior is at `validateResponsibilityRead` lines 1425–1441:
after a record passes strict quote and shape validation, the function resolves an enclosing duty
span and drops the record when field fidelity fails. That is the inventory-thrashing root cause.

### Responsibility orchestration

`apps/workers/src/lib/source-workflow-read.ts` currently:

- runs base responsibility reads around lines 2133–2172;
- immediately calls `validateResponsibilityRead` for each base read;
- computes omissions from only `validation.elements` around lines 2179–2186;
- runs up to five focused omission retries after that;
- reserves one general repair attempt for grounded quote repair;
- persists responsibility omission and repair audit data into the map validation payload.

The current repair path can change quotes only. It cannot fix a correct quoted record whose role,
action, object, trigger, or system is incomplete.

### Prompt and schema

`packages/ai/src/prompts/workflow-read.ts` contains:

- `RESPONSIBILITY_READ_PROMPT_VERSION = responsibility-read-v2.4-span-bound`;
- the base responsibility system prompt;
- the focused span-bound rules;
- `RESPONSIBILITY_QUOTE_REPAIR_PROMPT_VERSION`;
- the quote-only repair schema and prompt.

The base output schema already contains the needed responsibility fields. Prefer a new repair
schema in this file over a database change.

### Existing tests

`apps/workers/src/__verify__/r2-responsibility-reader.ts` already covers:

- answer-key SHA and matcher pins;
- quote and cross-segment validation;
- field fidelity and polarity;
- span discovery, binding, ranking, and audit;
- focused retry isolation;
- quote-repair candidate binding;
- budgets and merge/apply safety guards.

Existing package commands are listed in section 10.

### Production state

- `business_model_merge_enabled=false`.
- `business_model_apply_enabled=false`.
- Post-pass limits are 1 general repair, 5 omission retries, and 1 retry per chunk.
- Reader limits are 40 calls, 500,000 input tokens, $10 estimated input cost, concurrency 4.
- `business_objects=0`.
- `business_object_versions=0`.
- `business_model_changes=0`.

---

## 6. Key findings and root cause

### Root cause 1: validation mixes inventory acceptance with field completeness

Strict quote and structural validation answer: “Is this a real responsibility record supported
by this document?” Field fidelity answers: “Did the model preserve every important field?”
`validateResponsibilityRead` currently treats both as the same gate. A field-thin but real record
is deleted instead of retained for repair.

Evidence:

- Batch E kept 179 responsibilities.
- Batch F kept 92 after applying field checks to base reads.
- Full-map drops rose from 31 to 170.
- The same model and fixture lost seven previously matched answer-key rows.

### Root cause 2: repair can fix quotes but not fields

Grounded quote repair reduced root failures from 10 to 4 in Batch F. It cannot change any
responsibility field. Records rejected for `object_qualifier_loss`, `action_family_mismatch`,
`polarity_reversal`, or `unrepresented_multi_verb_duty` have no recovery path.

### Root cause 3: one source duty can name several explicit destinations

A source may say one action applies to MasterData, DesignFlow, and ColdLion. A model often returns
one general record. The current field validator treats that as incomplete, while the scorer
expects one thin responsibility per explicit destination. This is a generic list-expansion
problem, not a fixture alias problem.

### Root cause 4: omission and merge eligibility need different evidence sets

Inventory records are useful for audit and repair even when incomplete. They must not close an
omission or enter merge work until field-complete. The current code has one `elements` list and
uses it for all three purposes.

### Root cause 5: the model is not the first experiment

The same model scored 20/30 before the control change and 14/30 after it. A model bake-off on the
thrashing path would measure models through a known control defect. `MODEL_BAKEOFF_SPEC.md` also
warns that model choice is not meaningful when every result is below the quality floor.

---

## 7. Approaches considered and rejected

### Rejected: another free-form prompt and retry batch

Why it seemed reasonable: more explicit prompts increased kept responsibility counts in earlier
batches.

Why it failed: Batches C, D, and E plateaued at 19–20/30 despite 138–190 kept records and repeated
omission retries. Prompt wording did not fix stable field-thinning and direction errors.

### Rejected: keep strict field validation as a hard base-read drop

Why it seemed reasonable: bad records should not enter the map.

Why it failed: Batch F dropped 87 responsibility records and lost seven prior matches. Strictness
improved the surviving records but destroyed recall. Field-incomplete records need a quarantined
inventory state and a repair path, not silent acceptance or deletion.

### Rejected: weaken `field-aware-v3`

Why it seemed reasonable: many misses had 66–80% object overlap.

Why rejected: those were real missing systems, cadence, timing, named forms, or direction.
Weakening the scorer would hide reader errors and violate the evidence contract.

### Rejected: increase calls, tokens, cost, or retry counts

Why it seemed reasonable: more attempts could find more duties.

Why rejected: Batch F used 23/40 calls and about $0.30/$10. Budget was not the limiting factor.
The control path discarded records after they were read.

### Rejected: run a model bake-off first

Why it seemed reasonable: a stronger model may fill more fields.

Why rejected for this phase: the 20→14 regression occurred with the same model after a control
change. Fix the control defect first. A model bake-off becomes allowed only if the redesigned
path scores 24–26.

### Rejected: fixture-specific splitting or aliases

Why it seemed reasonable: hard-coded destination names could recover rows 7–9.

Why rejected: the Oracle must generalize to arbitrary company documents. Runtime code must not
contain fixture roles, systems, answer-key text, or licensing-specific rules.

### Rejected: add a second unbounded repair call

Why it seemed reasonable: one call for fields and another for quotes is simpler.

Why rejected: the reader's one-general-repair budget is frozen. The redesign must use one bounded
combined repair call or deterministically select work within the single reservation.

---

## 8. Design decisions

Decisions dated 2026-07-28.

### Locked decisions

1. **Two validation layers.**
   - Inventory-valid means: known same-document chunk, strict exact/normalized quote, valid
     responsibility shape, unique ID.
   - Field-complete means: enclosing duty span passes owner, action, polarity, object, named
     qualifier, cadence, timing, system, destination, and multi-verb checks.
   - Inventory-valid records survive even when field-incomplete.

2. **Three explicit record sets in memory.**
   - `inventoryElements`: all inventory-valid responsibility elements.
   - `completeElements`: inventory elements that pass field fidelity after deterministic
     expansion and repair.
   - `mergeEligibleElements`: complete elements only. Until the later R2 gate enables shadow
     merge, this set is audit evidence and a guard, not a dispatch authorization.
   - `validation.elements` continues to mean complete elements only. It is the only responsibility
     set allowed into `structureMap.elements`, `elementsJson`, `keptCount`, omission coverage,
     coverage ratios, claim map references, or later merge preparation.
   - Inventory-valid-but-incomplete records stay in memory for retries and repair, then persist only
     as per-record audit inside `validationJson`. They never become authoritative map evidence.

3. **One combined repair call under the existing repair budget.**
   - Reserve one
     `responsibilityPostPassBudget.reserveQuoteRepair()` call total. This is the frozen 1/1
     responsibility post-pass quote-repair allowance, repurposed to carry the combined field and
     quote repair.
   - Do not call `readerBudget.reserveRepair()` for the combined responsibility repair. That is a
     separate general-repair slot shared by segmentation and workflow quote-copy repair.
   - The combined model call still consumes one normal reader call plus its input tokens and
     estimated cost from `readerBudget`.
   - The request uses a discriminated schema with `fieldRepairs[]` and `quoteRepairs[]`.
   - A field repair may change only role, action, object, trigger, and requiredSystem from its
     selected exact span. It may not change record ID, chunk ID, or evidence quote.
   - A quote repair may change only evidence quote and must select an offered candidate.
   - Every returned repair is revalidated. Partial or invented repairs are rejected loudly.

4. **Repair happens after base reads and omission retries.**
   - Base reads preserve inventory.
   - Omission retries target spans not covered by complete records.
   - One combined repair call then receives the highest-value bounded field failures plus eligible
     quote failures from all base and retry reads.
   - Final validation, deterministic expansion, omission audit, and map assembly run after repair.

5. **Deterministic multi-destination expansion is generic and source-bound.**
   - Expand only a single-duty span containing an explicit coordinated list after a destination
     preposition such as `to`, `into`, `in`, `on`, `via`, or `through`.
   - Require at least two clear list members separated by commas, semicolons, bullets, or a final
     conjunction.
   - Preserve the shared object head and create one thin record per explicit member.
   - Use exact source tokens only. Do not maintain a system-name dictionary.
   - Keep the same exact evidence quote for every thin record when that quote supports the full
     list.
   - Generate collision-proof deterministic IDs from the original ID plus destination hash.

6. **Incomplete inventory remains auditable but cannot claim completeness.**
   - It must not close an omission.
   - It must not enter `mergeEligibleElements`.
   - It must not enter `validation.elements`, `structureMap.elements`, `elementsJson`,
     `keptCount`, the responsibility coverage numerator or denominator, or claim map references.
   - It must carry a per-record durable audit in `validationJson`: element ID, chunk ID, stable
     failure category, repair status, selected/rejected reason, and bounded quote hash.
   - Map status is `degraded` whenever `inventoryCount > completeCount`.

7. **No schema migration unless proven necessary.**
   - Store the new audit in the existing map validation JSON.
   - If existing JSON size or contract cannot safely carry it, stop before changing the database.

8. **The scorer and source evidence remain external authority.**
   - Runtime code never reads or imports the answer-key fixture.
   - The key is used only by the verifier and production gate scorer.

### Open implementation judgments

1. Exact TypeScript type names for inventory and repair results. Choose names that make invalid
   state hard to represent.
2. Whether deterministic destination parsing belongs in `responsibility-reader.ts` or a new
   focused module beside it. Prefer a new module only if the reader file becomes harder to audit.
3. The bounded repair selection ranking. It must prioritize:
   - records whose strict quote is already valid;
   - short, single-duty, explicit-owner spans;
   - polarity/action errors before broad object thinning;
   - stable source order as the final tie-break.
4. Maximum repair items inside the one call. Keep it bounded by existing selected-span conventions
   and token budget. Default to six field repairs plus eligible quote repairs only if the request
   stays comfortably inside the frozen input-token budget.

Any open judgment must be documented in the code review and plan STATUS row.

---

## 9. Numbered implementation plan

### Phase A: Baseline and contracts

#### P0. Freeze and record the starting state

Files:

- `plan_r2_deeper_responsibility_architecture.md`
- `HANDOFF.md`
- `evals/r2-responsibilities.md`
- no production code yet

Actions:

1. Confirm branch `main`, clean tracked worktree, and correct Git identity:
   `Albert Hazan <u2giants@users.noreply.github.com>`.
2. Confirm HEAD includes documentation commit `935bab9` or a later known-good main commit.
3. Run the current R2 verifier and typechecks before editing.
4. Record the live frozen settings and zero table counts read-only.
5. Confirm the fixture file hashes to the frozen SHA.
6. Update this STATUS row with the exact baseline commands and results.

Dependencies: none.

Verification gate: baseline tests pass, fixture SHA matches, merge/apply are false, limits are
40/500k/$10 and 1/5/1, and all three business-model tables are zero.

#### P1. Split inventory validation from field-completeness validation

Primary file:

- `apps/workers/src/lib/responsibility-reader.ts`

Functions to change:

- `validateResponsibilityRead`
- `validateResponsibilityFieldFidelity`
- `resolveEnclosingResponsibilityDutySpan`
- validation result types and merge helpers

Actions:

1. Refactor `validateResponsibilityRead` so strict quote, source ownership, chunk coverage,
   unique ID, and `validateBusinessShapeElement` determine inventory acceptance.
2. Do not `continue` and delete an inventory-valid record when field fidelity fails.
3. Return explicit data:
   - inventory elements;
   - complete element IDs or complete elements;
   - field diagnostics keyed by responsibility ID;
   - existing quote/shape diagnostics.
   Keep `validation.elements` as the complete set only. Persist it into map elements, count it as
   kept, and use it for omission and coverage calculations. Keep incomplete inventory in a separate
   audit structure that can persist only inside `validationJson`.
4. Preserve field-fidelity reasons exactly and add a stable category:
   `field`, `quote`, `multi_verb`, `forced_missing`, or `invalid_detail`.
5. Update `mergeResponsibilityValidationResults` and `mergeResponsibilityRetryValidation` so
   inventory and completeness sets merge without ID collisions or audit loss.
6. Keep every strict quote rule unchanged.
7. Add a helper such as `responsibilityMergeEligibleElements(validation)` that returns complete
   elements only and fails loudly if an ID is complete without being inventory-valid.

Dependencies: P0.

Verification gate: a generic exact-quote record with a thinned object appears in inventory,
appears in field diagnostics, does not appear in complete/merge-eligible elements, and is not
reported as a quote failure.

### Context cut point A

Start a fresh session if context is crowded. Re-read sections 1, 6, 8, and all remaining phases.
Do not proceed until P1's inventory/complete contract is green.

### Phase B: Deterministic completion mechanisms

#### P2. Add generic multi-destination expansion

Primary file:

- `apps/workers/src/lib/responsibility-reader.ts`

Optional new file:

- `apps/workers/src/lib/responsibility-destination-expansion.ts`

Actions:

1. Implement a pure parser that receives one exact duty span and one inventory-valid RAO.
2. Detect only explicit coordinated destination/system lists after a supported destination
   preposition.
3. Return zero expansions when syntax is ambiguous.
4. For a valid list, return one thin RAO per destination:
   - same role and action;
   - common object head plus exactly one destination;
   - requiredSystem set only when the source syntax clearly describes a system/destination;
   - same exact evidence quote and chunk;
   - deterministic ID derived from base ID and normalized destination hash.
5. Re-run strict shape and field validation on every expansion.
6. Keep the original inventory record for audit, but complete/merge-eligible output should use the
   expanded records when expansion succeeds.
7. Persist expansion origin, base ID, destination text, and accept/reject reason.

Dependencies: P1.

Verification gate: generic source
`The Records Team saves the approval number to LedgerOne, FlowBoard, and ArchiveBox.`
produces three field-complete records with stable unique IDs and exact evidence, while
`The Records Team reviews names, addresses, and dates.` does not falsely create destinations.

#### P3. Add one bounded combined responsibility-repair call

Files:

- `packages/ai/src/prompts/workflow-read.ts`
- `packages/ai/src/index.ts` if new exports are required
- `apps/workers/src/lib/responsibility-reader.ts`
- `apps/workers/src/lib/source-workflow-read.ts`

Actions:

1. Add a versioned combined repair schema and prompt. Keep the version string under database
   column limits.
2. Request shape:
   - `fieldRepairs[]`: immutable responsibility ID, chunk ID, exact evidence quote, selected
     semantic span, current fields, and allowed field names;
   - `quoteRepairs[]`: immutable fields plus deterministic offered quote candidates.
3. Response shape:
   - field repair returns only the immutable ID plus corrected allowed fields;
   - quote repair returns only the immutable ID plus selected offered quote/candidate ID.
4. Add a deterministic patch function:
   - reject ID/chunk/quote changes in field repair;
   - reject non-quote field changes in quote repair;
   - reject any text not present in the selected source span;
   - reject duplicates, missing IDs, extra IDs, and schema-valid but unrequested repairs.
5. Re-run strict quote, shape, field, polarity, and multi-verb validation after patching.
6. Reserve exactly one `responsibilityPostPassBudget.reserveQuoteRepair()` attempt for the combined
   call. Replace only the separate responsibility quote-repair call currently in
   `apps/workers/src/lib/source-workflow-read.ts`; segmentation integrity repair and workflow
   quote-copy repair remain unchanged. Do not use `readerBudget.reserveRepair()` for this combined
   responsibility call. If there is no field or quote work, record `no_eligible_repairs`.
7. Bound repair selection and record why each candidate was selected or skipped.
8. Preserve candidate text, hashes, before/after fields, validation outcomes, and rejection reason
   in durable audit.

Dependencies: P1 and P2.

Verification gate: one mocked combined call can repair a cadence-thinned object and select a
grounded quote candidate in the same response, increments the responsibility post-pass quote-repair
count exactly once, does not increment the reader general-repair count, and rejects invented
content or cross-mode field changes.

#### P4. Rebuild orchestration, omission coverage, and eligibility

Files:

- `apps/workers/src/lib/source-workflow-read.ts`
- `apps/workers/src/lib/responsibility-reader.ts`
- `apps/workers/src/lib/business-model-merge.ts` only for a guard if current shadow preparation
  could consume incomplete map elements
- `apps/workers/src/trigger/document-ingestion.ts` only if an existing dispatch guard must learn
  the new completeness audit; do not enable dispatch

Actions:

1. Base reads produce inventory plus completeness classifications.
2. Run deterministic multi-destination expansion on every completeness pass: after base reads,
   after each omission-retry merge, and after combined repair.
3. Compute omissions from complete elements only.
4. Run the existing maximum five omission retries, one per chunk. Retry results also enter
   inventory first, then deterministic expansion and completeness validation.
5. Build the one combined repair request from bounded field and quote failures across base and
   retry reads.
6. Apply and revalidate the combined repair.
7. Re-run deterministic expansion where repaired fields make it applicable.
8. Compute final complete elements, merge-eligible IDs, and omissions.
9. Persist:
    - inventory count;
    - complete count;
    - merge-eligible count;
    - drop/failure counts by taxonomy;
    - a per-record incomplete-inventory audit containing element ID, chunk ID, failure category,
      repair status, selected/rejected reason, and bounded quote hash;
    - repair candidates, outcomes, and one-call budget evidence;
    - deterministic expansion evidence;
    - before/after omission counts;
    - final uncovered sample capped at 30.
10. Keep `validation.elements`, `structureMap.elements`, `elementsJson`, `keptCount`,
    `findResponsibilityOmissions`, responsibility coverage, claim map references, and later merge
    preparation bound to complete elements only. Persist inventory-valid-but-incomplete records only
    in the `validationJson` audit. Set map status to `degraded` whenever
    `inventoryCount > completeCount`, but do not erase the incomplete inventory audit.
11. Add a fail-loud guard so downstream responsibility shadow merge cannot consume an ID absent
    from `mergeEligibleElements`.
12. Keep merge/apply flags false and do not dispatch shadow merge during this phase.

Dependencies: P1–P3.

Verification gate: an orchestration fixture retains all inventory-valid records, repairs bounded
field failures, expands explicit destinations, closes omissions only with complete records, and
exposes zero incomplete records to the merge-eligibility helper.

### Context cut point B

Start a fresh session. Re-read the entire plan and inspect the actual diff before testing. Confirm
the implementation still matches the locked decisions and has not become a prompt-only Batch G.

### Phase C: Verification and review

#### P5. Complete the required local verification

Files:

- `apps/workers/src/__verify__/r2-responsibility-reader.ts`
- existing verifier files only where a real contract changed

Actions:

1. Add every unit and orchestration test listed in section 10.
2. Run all named commands.
3. Search runtime code for fixture leakage.
4. Run `git diff --check`.
5. Inspect changed exports and ensure every production-used helper is tested through the real
   production seam, not copied into a test-only implementation.

Dependencies: P1–P4.

Verification gate: every command in section 10 passes and the tracked diff contains only
authorized files.

#### P6. Run the Grok 4.5 correction loop

Actions:

1. Use the installed Grok CLI with model `grok-4.5`.
2. Review read-only:
   - `--allow Read --allow Grep`
   - `--deny Edit --deny Bash`
   - `--no-subagents --no-memory --disable-web-search`
3. Give Grok this entire plan, the hard-stop evidence, and the exact uncommitted diff.
4. Require:
   - P0/P1/P2 findings with file and line;
   - locked-decision audit;
   - explicit verdict `APPROVED FOR CI AND LIVE REGATE` or `CHANGES REQUIRED`.
5. Send every actionable final-text finding back to the same implementation agent.
6. Repeat until approved. Ignore discarded internal `thought` drafts; use the final review text.
7. Do not commit or deploy before approval.

Dependencies: P5.

Verification gate: saved Grok final review says `APPROVED FOR CI AND LIVE REGATE`, with no open
P0 or P1.

### Context cut point C

Start a fresh release session. Re-read sections 11–13 and verify the exact approved commit scope.

### Phase D: Landing and one production gate

#### P7. Commit, push, CI, deploy, and run exactly one gate

Actions:

1. State target: repo `u2giants/theoracle`, branch `main`.
2. Verify Git identity before commit.
3. Stage only the approved implementation and test files.
4. Commit and push to `main`.
5. Wait for the exact GitHub Actions run to pass.
6. Deploy workers with the Trigger PAT from 1Password using `op_run`.
7. Record worker version and deployment ID.
8. Before the gate, read and record:
   - fixture SHA;
   - model route;
   - 40/500k/$10 limits;
   - 1/5/1 post-pass limits;
   - merge/apply false;
   - all three business-model table counts zero.
9. Upload exactly one disposable fixture through the normal application path. If browser file
   upload is blocked, use the previously proven Supabase CLI + normal Storage REST/document
   insert/Trigger dispatch path with the service key kept in child memory only. Never print or
   persist it.
10. Wait for the source-workflow job and map to reach terminal state.
11. Score all 30 rows with the frozen key and matcher.
12. Collect all IDs, counts, field repair evidence, expansion evidence, drop taxonomy, budgets,
    truncation, flags, and table counts.
13. Do not run a second gate for the same release.

Dependencies: P6.

Verification gate: one terminal production map exists for the exact fixture and released worker,
with a complete 30-row score and unchanged safety state.

#### P8. Apply the score rule and update documentation

Files:

- `evals/r2-responsibilities.md`
- `HANDOFF.md`
- `MACRO_FIRST_IMPLEMENTATION_PLAN.md`
- this plan's STATUS table
- `docs/architecture.md` if the implemented control contract changed durable architecture

Decision:

- `>=27/30`: mark the deeper-reader gate passed. Proceed to the remaining R2 shadow-merge,
  idempotency, refine, namespace, and UI gates. Do not skip them.
- `24–26/30`: stop code churn. Authorize only the bounded workflow-read model bake-off on the
  redesigned path under `MODEL_BAKEOFF_SPEC.md`.
- `<=23/30`: hard stop again. Do not create another completeness batch. Require a new owner
  decision.

Actions:

1. Record all evidence and failed approaches.
2. Update every plan status row that changed.
3. Run the mandatory HANDOFF self-audit.
4. Commit, push, and wait for CI.

Dependencies: P7.

Verification gate: documentation matches production evidence, the correct next decision is
unambiguous, and a fresh developer can continue without chat context.

---

## 10. Tests required

### New unit tests in `apps/workers/src/__verify__/r2-responsibility-reader.ts`

Add tests with invented generic examples only:

1. **Inventory survives field thinning**
   - Exact quote: `The Finance Team submits quarterly compliance reports.`
   - Returned object: `reports`.
   - Expect inventory accepted, field incomplete, merge-ineligible, omission still open.

2. **Complete base record remains complete**
   - Same quote, returned object includes `quarterly compliance reports`.
   - Expect inventory accepted, field complete, merge-eligible.

3. **Strict quote failure is not inventory**
   - Quote absent from source.
   - Expect quote diagnostic and no inventory record.

4. **Polarity reversal remains incomplete**
   - Source says `provides assets to vendors`; output says `receives assets from vendors`.
   - Expect inventory only, polarity diagnostic, merge-ineligible.

5. **Named form/system/cadence remains strict**
   - Form A vs Form B, Route A vs Route B, quarterly vs reports-only.
   - Expect repair-required diagnostics, never silent completion.

6. **Generic multi-destination expansion**
   - `saves the approval number to LedgerOne, FlowBoard, and ArchiveBox`.
   - Expect three stable complete elements with exact quotes and no fixture strings.

7. **No false destination expansion**
   - `reviews names, addresses, and dates`.
   - Expect zero deterministic destination clones.

8. **Expansion ID stability and collision guard**
   - Same input twice produces same IDs.
   - Duplicate normalized destination fails loudly.

9. **Combined field repair accepts bounded correction**
   - Current object `reports`; exact span has `quarterly compliance reports`.
   - Repair returns complete object and passes all validators.

10. **Combined field repair rejects invention**
    - Repair adds a system or cadence absent from the span.
    - Expect explicit reject and unchanged inventory.

11. **Combined quote repair remains candidate-bound**
    - Returned quote not in offered candidates is rejected.

12. **Cross-mode mutation rejection**
    - Field repair changes quote or chunk.
    - Quote repair changes action or object.
    - Both fail loudly.

13. **Correct repair-budget wiring**
    - Mixed field and quote work uses one responsibility post-pass quote-repair reservation,
      never two.
    - `responsibilityPostPassBudget.snapshot().quoteRepairs` becomes 1.
    - `readerBudget.snapshot().repairAttempts` does not increase.

14. **Omission closes only on complete records**
    - Inventory-only record leaves span uncovered.
    - It remains targeted by an omission retry.
    - Repaired complete record closes it.

15. **Merge eligibility guard**
    - Incomplete ID cannot be returned or consumed as merge-eligible.

16. **Drop taxonomy**
    - Produce one each: quote, field, multi_verb, forced_missing, invalid_detail.
    - Durable counts and record IDs match.

17. **Runtime leak guard**
    - Continue the existing search/assertions that forbid fixture role names and pinned
      business-specific strings in production reader/prompt code.
    - Derive destination, system, and object terms from the verifier fixture at test time and assert
      that none appear in the production reader, prompt, or expansion source. Do not copy those
      answer-key terms into the runtime code or hard-code a second answer key in the leak test.

18. **Frozen invariants**
    - Answer-key SHA and matcher remain frozen.
    - Budgets remain 40/500k/$10 and 1/5/1.
    - Merge/apply remain false by default.

19. **Incomplete inventory never persists as map evidence**
    - An inventory-valid but field-incomplete record appears in the per-record `validationJson`
      audit.
    - It does not appear in `structureMap.elements`, `elementsJson`, `keptCount`, claim map
      references, or merge preparation.

20. **Incomplete inventory forces degraded status**
    - When `inventoryCount > completeCount`, map status is `degraded` even if no legacy diagnostic
      remains.

21. **Post-repair expansion**
    - A successful field repair that exposes an explicit destination list is expanded before final
      completeness and persistence.

22. **Complete-only coverage denominator**
    - Responsibility coverage and `primaryCount` use complete elements only.
    - Inventory-only elements cannot inflate either side of the ratio.

### Production-used orchestration test

Add or extend a production-used seam so one test executes:

base output → inventory validation → destination expansion → omission calculation → retry merge →
combined repair patch → final validation → complete/merge-eligible selection → durable audit.

The test must call the same helpers production uses. It must not duplicate the algorithm.

### Existing commands that must stay green

Run from `C:\repos\oracle`:

```powershell
pnpm --filter @oracle/workers typecheck
pnpm --filter @oracle/ai typecheck
pnpm --filter @oracle/engines typecheck
pnpm --filter @oracle/workers run verify:r2-responsibilities
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

Run the production replay only during the authorized release gate with protected production DB
access. Do not make a local test depend on production.

---

## 11. Constraints, standing rules, and gotchas

1. Main-only repo. No branch or PR unless Albert changes the rule.
2. Before committing, `git var GIT_COMMITTER_IDENT` must show
   `Albert Hazan <u2giants@users.noreply.github.com>`.
3. Preserve unrelated untracked `.ai/reviews`, `.playwright-cli`, and image files.
4. Do not commit `.ai/reviews` scratch output.
5. No database schema change in this repo. Shared DB work belongs in `u2giants/shared-db` after a
   separate preview-first plan.
6. Never weaken exact evidence validation for document sources.
7. No silent fallback. Missing repair binding, unknown ID, extra response item, budget failure,
   duplicate destination, or audit mismatch must be loud and durable.
8. No hard-coded model. Continue using the configured `workflow_read` route.
9. No model pool manipulation during this architecture phase.
10. The responsibility post-pass quote-repair allowance remains 1/1 even when its one combined
    call contains both repair modes. The separate reader general-repair allowance remains unchanged.
11. Five omission retries and one per chunk remain frozen.
12. The answer-key fixture may appear in verifier/eval code only, never runtime reader logic.
13. Merge and apply remain false. Do not enable them even if the score passes; later R2 gates own
    that action.
14. Keep the quote-repair path candidate-bound.
15. Inventory preservation does not mean incomplete records become authoritative. They are audit
    and repair inputs only, persist only in `validationJson`, and never enter `elementsJson`.
16. Map status must honestly show degradation when incomplete inventory remains.
17. Trigger CLI deploy requires the PAT from 1Password. Do not put secrets in command text, files,
    process arguments, or logs.
18. Serialize 1Password reads.
19. The production direct Supabase hostname may be IPv6-only from this Windows machine. Use the
    session pooler reference documented below for read-only database checks.
20. No UI work is in scope, so no screenshot gate is required for this plan.

---

## 12. Access and environment

Authenticated tools expected on this Windows machine:

- `gh` for GitHub Actions and repository checks.
- `supabase` CLI for project metadata and the proven protected upload path.
- `vercel` CLI for web deployment inspection if needed.
- Trigger.dev CLI through the workers package.
- 1Password connector / `op_run`.
- Grok CLI for independent review.

Secrets live in 1Password vault `vibe_coding`. Reference locations only:

- Production Supabase session pooler:
  item `Supabase DB Direct URL - The Oracle (CURRENT PROD …)`,
  field `oracle_session_pooler`.
- Trigger.dev management PAT:
  item `Trigger.dev Personal Access Token (management)`.
- Trigger.dev production API key:
  existing Oracle Trigger production item documented in `HANDOFF.md`.

Do not reveal secret values.

Local commands:

```powershell
cd C:\repos\oracle
pnpm install
pnpm --filter @oracle/workers typecheck
pnpm --filter @oracle/workers run verify:r2-responsibilities
```

Production identifiers:

- Supabase project `eqccjfbyrywsqkxxpjvg`.
- Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`.
- Vercel project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`.
- Web URL `https://oracle.designflow.app`.

Review command safety:

- Grok model must be `grok-4.5`.
- Read-only permissions only.
- No Grok subagents or memory.

---

## 13. Definition of done, risks, rollback, and open questions

### Definition of done

This deeper-architecture implementation is complete only when all are true:

- [ ] Inventory and field-completeness validation are separate in production code.
- [ ] Field-incomplete exact-quote records survive as inventory but are merge-ineligible.
- [ ] Explicit multi-destination lists expand generically and deterministically.
- [ ] One combined repair call handles bounded field and quote repair within the existing budget.
- [ ] Every repair and expansion is strictly revalidated.
- [ ] Omissions close only on field-complete records.
- [ ] Incomplete records cannot enter responsibility merge preparation.
- [ ] Durable audit reports inventory, complete, eligible, repair, expansion, drop taxonomy, and
      final omissions honestly.
- [ ] Every new unit and production-seam test passes.
- [ ] All existing commands in section 10 pass.
- [ ] Grok 4.5 approves the exact diff with no P0/P1.
- [ ] Code is committed to `main` with Albert's correct identity and pushed.
- [ ] Exact GitHub Actions run is green.
- [ ] Trigger worker deployment succeeds and its version/deployment ID are recorded.
- [ ] Exactly one fresh pinned production gate runs.
- [ ] Fixture SHA, scorer, threshold, budgets, flags, and table zeros are verified before/after.
- [ ] All 30 rows and full operational evidence are recorded.
- [ ] Score decision is applied exactly.
- [ ] This plan, `HANDOFF.md`, `MACRO_FIRST_IMPLEMENTATION_PLAN.md`,
      `evals/r2-responsibilities.md`, and `docs/architecture.md` are current.
- [ ] Documentation commit is pushed and CI-green.

### Main risks and controls

1. **Risk: preserving inventory accidentally makes weak records authoritative.**
   - Control: separate complete and merge-eligible sets; fail-loud merge guard.

2. **Risk: field repair invents details.**
   - Control: exact selected span only, immutable evidence, token/source validation, strict
     post-repair validation.

3. **Risk: destination parsing over-splits ordinary noun lists.**
   - Control: require destination preposition plus explicit coordinated list; ambiguous syntax
     returns no expansion.

4. **Risk: combined repair schema becomes too complex for a provider.**
   - Control: adapter request-shape review if schema behavior changes; keep union shallow; fail
     loud. Do not silently fall back to free JSON.

5. **Risk: repair candidate volume exceeds token budget.**
   - Control: deterministic bounded ranking and one repair reservation; record skipped items.

6. **Risk: retained inventory increases map size.**
   - Control: audit serialized size in local tests and live gate. If JSON storage becomes unsafe,
     stop for a separate schema plan.

7. **Risk: the redesigned path still scores below 24.**
   - Control: binding hard stop. No additional completeness batch.

### Rollback

If the release fails before a production gate:

1. Do not run the gate.
2. Fix forward on `main` with reviewed code.
3. Keep merge/apply false.

If the released worker causes unexpected runtime failures:

1. Stop new fixture dispatch.
2. Redeploy the last known worker `20260728.5` only if Trigger.dev supports an exact safe rollback,
   otherwise revert the implementation commit on `main`, pass CI, and deploy forward.
3. Do not edit production code or maps directly.
4. Record the failure in `HANDOFF.md` and this plan.

If the gate scores below the decision threshold:

- follow P8 exactly;
- never hide the result by rerunning the same release.

### Open questions

The following are intentionally deferred to implementation evidence:

1. Whether the combined repair request can safely include six field repairs plus all eligible
   quote repairs inside model/schema limits. Decide using request-shape tests and token estimates.
2. Whether multi-destination expansion should set `requiredSystem` for every destination or only
   when source grammar identifies a system. Default to source grammar, never capitalization alone.
3. Whether retained incomplete inventory needs a future typed durable status. Existing JSON audit
   is the required first implementation; schema work needs a separate plan.

None of these questions permit scorer, evidence, budget, or fixture changes.

---

## Mandatory plan self-audit

### 1. Could a brand-new AI session execute this plan perfectly without asking Albert anything?

**Yes.** Sections 2–5 define the application, repository, runtime, trigger, scope, exact current
code, production evidence, and frozen state. Section 8 locks the architecture and labels the few
implementation judgments. Section 9 gives ordered file/function-level steps with a verification
gate for every step. Sections 10–12 provide exact tests, commands, rules, access, secret locations,
and environments.

### 2. Does the plan carry all current background, nuance, failed attempts, and reasoning?

**Yes.** Sections 3, 6, and 7 record the six-gate history, Batch E→F regression, quote-repair
result, inventory collapse, why model choice is not the first experiment, and every rejected
shortcut. Section 8 records the chosen two-layer architecture, correct responsibility post-pass
repair budget, generic destination expansion, and authority boundaries.

### 3. Is the ultimate goal clear enough for a correct judgment call if a step is wrong?

**Yes.** Section 1 states the business result first and explicitly says the goal wins over any
conflicting step. Sections 4, 8, and 11 make the safety and evidence boundaries unambiguous.
Section 13 gives objective success, rollback, risk, and score-decision rules.

### Objective checklist

- [x] All 13 sections are present.
- [x] The ultimate goal is in plain business English at the top.
- [x] A fresh session needs no planning-chat context.
- [x] Failed and rejected approaches are preserved with reasons.
- [x] Every implementation step names files/functions and has a verification gate.
- [x] Locked and open decisions are labeled.
- [x] Out-of-scope work is explicit.
- [x] Tests are named by behavior and command.
- [x] Important paths, URLs, IDs, SHAs, and services are defined.
- [x] Secrets are referenced by location only.
- [x] Definition of done includes commit, push, CI, worker deploy, production gate, and docs.
- [x] GLM 5.2's two major findings and six smaller findings are resolved in the plan.

**Self-audit result after GLM 5.2 review: PASS.**
