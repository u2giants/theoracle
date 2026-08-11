# R2 Source-Span Inventory Reader Implementation Plan

Status: **P0 THROUGH P8 COMPLETE. SOLE PRODUCTION GATE FAILED AT 19/30. HARD STOP.**

Created: 2026-08-09

Owner direction: Albert approved proceeding with the deeper reader design.

Canonical parent plan: `MACRO_FIRST_IMPLEMENTATION_PLAN.md`

Predecessor plan: `plan_r2_deeper_responsibility_architecture.md`

Failure evidence: `evals/r2-responsibilities.md` and `evals/bakeoffs/workflow-read.md`

Independent design review: Grok 4.5 session `019fe8db-eef0-7f83-b974-a372bd6330da`
returned `APPROVED FOR IMPLEMENTATION` on 2026-08-09 after two correction rounds. Total review cost
was $1.127844 across 2,510,800 reported tokens, including 2,334,080 cached tokens.

## STATUS table

| Step | Status | Evidence / next gate |
|---|---|---|
| P0. Reconfirm the frozen contract and classify residual failures | ✅ complete | Five baseline checks passed; `evals/r2-responsibilities.md` classifies all 30 rows for all three maps and finds credible non-scorer mechanisms for 30/30. |
| P1. Build a deterministic source-span inventory | ✅ complete | Pure stable inventory seeds, exact raw bindings, inherited owners, locked destination and multi-verb children, audit-only parents, loud integrity checks, and generic tests pass. Grok 4.5 independently returned `APPROVED FOR P2 WITH NON-BLOCKING NOTES`; P2 must preserve seed-aware destination matching, and P5 must close the overlap and direct integrity-test notes below. |
| P2. Add deterministic seed completion and exclusive proposal matching | ✅ complete | Exact source-bound exclusive matching, audit-only unmatched proposals, deterministic clear-list completion, three staged inventory counts/ID lists, split omission classes, overlap hardening, and direct integrity tests pass locally. GLM 5.2 independently found two blockers; both were fixed and its follow-up verdict was `APPROVED FOR P3`. |
| P3. Add exhaustive, budget-proven residual completion | ✅ complete | Shallow strict completion contract, immutable seed canonicalization, stable input/output token packing with the shared 300-record schema ceiling, low/expected/high forecasts, full pre-dispatch read-budget reservation, typed bounded retry rules, strict-improvement validation, ordered per-seed terminal outcomes, and loud missing/duplicate/extra/unscheduled failures pass locally. Grok 4.5 found and verified corrections for retry classification, schema-sized packing, strict improvement, and outcome audit, then returned `APPROVED FOR P4`. |
| P4. Rebuild omission and merge assembly around the inventory | ✅ complete | The production worker now runs budget-packed exhaustive residual completion before detection-only legacy retries and candidate-bound quote repair. Final responsibility elements are source-seed ordered, complete-only, one-to-one asserted, and the inventory, manifests, outcomes, executions, unscheduled IDs, final gaps, and failure facts persist in `validationJson`. Worker typecheck, lint, AI typecheck, the R2 production-seam verifier, and `git diff --check` pass. |
| P5. Complete local verification | ✅ passed locally | The invalid source-prefix fallback remains removed. Two separately authorized, source-grounded corrections raised the unchanged pinned verifier from 16/30 to 26/30 and then 28/30. All prior rows remain supported; only 16 and 26 are unsupported. |
| P6. Independent read-only design and implementation review | ✅ complete | Fresh Codex review found one general actor-reset bug; it was fixed with a regression test. The full suite passed after the fix. Codex and GLM 5.2 follow-ups both returned `APPROVED FOR CI` with no P0/P1. |
| P7. Commit, push, CI, deploy, and run one production gate | ✅ complete | Albert authorized the release on 2026-08-11. Commit `62330bdb0b477abb373fa1d155b104cee45a8b66` and docs commit `9dcfd6072677b9a12e8a320f48e5c316d1099b6b` were already pushed with green CI. Worker `20260811.1`, deployment `725f1ru9`, ran exactly one pinned production gate. Map `37a8fc62-23e4-46b7-8464-d1c784dc73cd` scored 19/30 with unchanged `field-aware-v3`. |
| P8. Apply the frozen score rule and update durable records | ✅ hard-stop decision applied | The 19/30 result is at or below 23. No second gate, reader change, scorer change, budget change, merge, or apply is allowed without a new owner decision. Durable evidence is in `evals/r2-responsibilities.md` and the newest R2 production handoff. |

Fresh-session starting point: **the sole production gate failed at 19/30 and the frozen hard stop is binding**. Do not run another gate or change the reader. The next safe step is a read-only comparison of the 11 live misses against the 28/30 local source-support result, followed by a new owner decision.

Bounded correction plan created 2026-08-11: [`plan_r2_local_owner_context_correction.md`](plan_r2_local_owner_context_correction.md). Read its STATUS table first. It owns the local source-span owner propagation, visible actor-conflict, and split-coherence correction. It does not authorize implementation, deployment, or production.

Independent P0/P1 implementation review, 2026-08-10: Grok 4.5 session
`019fe9a5-2324-7601-a7d1-f50f8dd31d8b` returned
`APPROVED FOR P2 WITH NON-BLOCKING NOTES`. It found no blocking P0 or P1 defect. Preserve these four
notes through P2 and close them no later than P5: tighten unrelated-root overlap rejection when both
`parentSeedId` values are null; directly test missing binding, bad offsets/quote mismatch, and true
overlap; match destination children by seed identity and `splitValue` despite shared evidence spans;
and make deterministic destination completion use `splitValue` rather than the full parent
`sourceSpan`. Review cost was $0.5596628 for 945,685 reported tokens, including 819,456 cached.

---

## 1. Ultimate goal

The Oracle must retain every real duty in a responsibility document and accurately represent its
owner, action, object, system, timing, cadence, and direction. The pinned 30-row production fixture
must score at least 27/30 with the unchanged `field-aware-v3` matcher.

The design must generalize beyond the pinned document. It must not weaken quote validation, add
fixture-specific words, silently discard incomplete duties, or let incomplete records reach the
business-model merge path.

If a step conflicts with this goal, stop and record the conflict. The score is evidence of reader
quality, not permission to tailor runtime code to the answer key.

---

## 2. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. Workers read those sources, extract claims and process
structure, validate exact evidence, and prepare reviewable knowledge.

- Repository: `u2giants/theoracle`, local checkout `C:\repos\oracle`.
- Branch: `main` only.
- Stack: TypeScript, `pnpm`, Turbo, Next.js 16, Trigger.dev, Drizzle, and Supabase.
- Web production URL: `https://oracle.designflow.app`.
- Worker project: Trigger.dev `proj_wgpzsvhmsopqhvwqaycn`.
- Database project: Supabase `eqccjfbyrywsqkxxpjvg`.
- Reader orchestration: `apps/workers/src/lib/source-workflow-read.ts`.
- Responsibility rules: `apps/workers/src/lib/responsibility-reader.ts`.
- AI prompts and schemas: `packages/ai/src/prompts/workflow-read.ts`.

This plan changes only the R2 responsibility reader and its audits. It does not authorize a database
schema change, business-model merge, apply, claim serving, or later macro stages.

---

## 3. What triggered this work

The frozen production fixture is `Licensed Team Responsibilities 2 - tagged.txt`, source SHA-256
`398927caaf945cc313429d70836713980a29ae41d8109bc3592fd146dfca90be`. Its answer key is
`licensed-team-responsibilities-v1`; the matcher is `field-aware-v3`; passing is 27/30.

The first deeper architecture added strict field checks, deterministic destination expansion, five
focused omission retries, and one combined repair call. Its one production gate scored 12/30.
Albert then approved a bounded model bake-off. GPT-4.1 scored 11/30 and 12/30, a mean of 11.5.
Claude Sonnet 5 and Gemini 2.5 Pro could not enter that bake-off because the live catalog did not
prove acceptance of the required deep strict schema. The frozen rule now forbids a second bake-off
and requires a new reader architecture.

The deeper design is needed because changing the model did not change the failure shape. The reader
still asks model output to establish which duties exist, then tries to recover only a few losses.

---

## 4. Scope

### In scope

- Make deterministic, exact source spans the first-class duty inventory.
- Give every inventory seed a stable ID and exact raw-source binding.
- Keep model-discovered records as useful proposals, not the authority on whether a duty exists.
- Complete missing fields for all inventory seeds in token-budgeted batches.
- Split source-inventory coverage, model-discovery coverage, and merge-ready coverage in audits.
- Preserve incomplete inventory in `validationJson` only.
- Keep complete, strictly validated records as the only responsibility map elements.
- Add unit, orchestration, audit, and anti-leak tests.
- Run one independently reviewed production gate after CI and worker deployment.

### Out of scope

- Another provider or model bake-off.
- Re-qualifying Claude Sonnet 5 or Gemini 2.5 Pro for deep schemas.
- Raising the frozen 40-call, 500,000-input-token, or $10 reader limits.
- Raising the frozen 1 quote-repair, 5 omission-retry, or 1-per-chunk limits.
- Weakening exact quote or field-fidelity rules.
- Database schema or migration changes.
- UI work.
- Enabling merge or apply.
- Adding company names, roles, systems, or answer-key terms to runtime logic.

---

## 5. Current code and runtime behavior

1. `buildResponsibilityBaseReadPlan` in
   `apps/workers/src/lib/responsibility-reader.ts:375` shards responsibility segments and creates
   synthetic reads for duty-bearing chunks. This guarantees a model call, not a record per duty.
2. `sourceDutySpanDetails` at `apps/workers/src/lib/responsibility-reader.ts:519` already detects and
   binds list and prose duty spans to raw offsets. Today those spans are mainly omission targets.
3. `validateResponsibilityRead` at `apps/workers/src/lib/responsibility-reader.ts:1635` separates
   inventory-valid records from field-complete records, but both begin with model-emitted records.
4. `findResponsibilityOmissions` at `apps/workers/src/lib/responsibility-reader.ts:893` compares
   deterministic duty spans with complete elements after base model reads.
5. The production loop at `apps/workers/src/lib/source-workflow-read.ts:2305` performs model-first
   shard reads. The retry loop at line 2377 can attempt at most five omission calls and one per chunk.
6. `buildResponsibilityCombinedRepairPlan` at
   `apps/workers/src/lib/source-workflow-read.ts:1188` selects a bounded repair set. It cannot ensure
   that every source duty becomes a complete record.
7. Final assembly at `apps/workers/src/lib/source-workflow-read.ts:2808` correctly uses
   `responsibilityMergeEligibleElements`, so incomplete records do not enter the map.
8. Audit output at `apps/workers/src/lib/source-workflow-read.ts:2856` records inventory, complete,
   repair, omission, and budget data in `validationJson`.
9. `RESPONSIBILITY_READ_SYSTEM_PROMPT` in `packages/ai/src/prompts/workflow-read.ts:80` still asks
   one response to discover, split, normalize, and ground all duties from a segment.

No database change is needed. The new inventory and completion audit can remain inside the existing
`validationJson` payload, while `elementsJson` remains complete-only.

---

## 6. Findings and root cause

### Primary root cause

The architecture is model-first. A duty does not become durable inventory unless a base read or one
of a few focused retries emits a usable record. Deterministic span detection happens after the main
read and is used to rank scarcity, rather than establishing the complete work queue up front.

### Why the current repair design cannot close the gap

- Five retries cannot guarantee treatment of every missing span in a long document.
- One combined repair call selects a bounded subset of incomplete records.
- Strict validation correctly rejects thinned objects, reversed direction, missing cadence, and
  unrepresented multi-verb duties. Rejection protects quality but exposes the limited repair queue.
- The production bake-off left substantial token and cost capacity unused. This is not primarily a
  larger-context or more-expensive-model problem.
- GPT-4.1 repeated the same 11 to 12 score band. The reader contract dominated model choice.

### Design conclusion

Invert control. The source defines the duty inventory first. Pure rules complete clear list duties
and split explicit destination or multi-verb structures. Packed model calls fill only the residual
ambiguous seeds. Validation decides whether each seed is complete, but no failed completion can erase
the fact that the duty exists.

---

## 7. Rejected approaches

1. **Run another model bake-off.** Rejected because the owner-approved bake-off already failed and
   the frozen decision explicitly forbids a second one.
2. **Use Claude Sonnet 5 or Gemini 2.5 Pro immediately.** Rejected for this phase because neither had
   `deep_schema_accepted=true` for the required contract. Adapter re-qualification is separate work,
   and model eligibility would not fix the model-first queue.
3. **Raise omission retries or repair slots.** Rejected because it preserves a scarce after-the-fact
   recovery queue and can still omit duties silently as document size grows.
4. **Loosen field fidelity.** Rejected because it would inflate the score with wrong owners, objects,
   direction, systems, or cadence.
5. **Promote incomplete inventory into map elements.** Rejected because later business-model work
   must consume only complete, evidenced records.
6. **Hard-code the 30 expected duties or company vocabulary.** Rejected as answer-key leakage.
7. **Add a new database table.** Rejected because existing `validationJson` can hold the audit and no
   cross-run query requirement has been established.
8. **Prompt-only Batch G.** Rejected because prompt variants already failed to repair the control
   flow. This phase must change scheduling, inventory ownership, and audit semantics.

---

## 8. Decisions

### Locked decisions

1. Deterministic bound source spans are the authoritative inventory for recognized duty-bearing
   text. Model output is not allowed to delete an inventory seed.
2. Each seed identity is derived from document chunk ID, raw start/end offsets, and source-span hash.
   IDs must be stable across identical reruns and must not use answer-key content.
3. Exact evidence quote, chunk ID, and raw offsets are immutable after inventory creation.
4. Field completion may only use the exact enclosing source span plus generic document metadata.
5. Multi-destination splitting is source-only. Parse a terminal conjunction/comma list only after a
   destination preposition (`to`, `into`, `in`, `on`, `within`, or `across`); derive the shared object
   head from source words between the duty verb and preposition; retain the existing ambiguity guards;
   replace the parent with one child per normalized destination and retain the parent in audit.
6. Multi-verb parents never become merge-ready. Inventory-time splitting creates single-verb
   children only when each clause has exactly one duty verb and a non-empty source-derived object.
   Otherwise the parent remains incomplete with `ambiguous_multi_verb`.
7. Every seed still incomplete after validated base proposals and deterministic completion is
   scheduled exactly once for residual field completion.
8. Completion batches are packed by estimated input/output tokens, not by an arbitrary record count.
9. If all batches cannot fit the frozen total budget, stop scheduling and record every unscheduled ID
   as `budget_exhausted`. Never treat it as coverage.
10. Existing five omission retries remain available only for deterministic inventory detection gaps,
    such as ambiguous prose. They are not the normal field-completion mechanism.
11. Existing combined quote repair remains candidate-bound and separate from exhaustive field
    completion. Quote repair cannot change fields; field completion cannot change evidence.
12. Only complete records enter `structureMap.elements`, `elementsJson`, kept counts, coverage
    numerator, claim references, or merge preparation.
13. Incomplete and unscheduled seeds persist only in `validationJson`; any such seed makes map status
    `degraded`.
14. The configured `workflow_read` route remains the model source. No model is hard-coded.
15. Frozen limits, matcher, fixture SHA, merge/apply flags, and one-gate rule remain unchanged.
16. Introduce a dedicated `ResponsibilityInventorySeed` type. Do not reuse retry-only
    `ForcedResponsibilitySpan` fields.
17. Keep pure inventory, splitting, deterministic completion, matching, and token packing in
    `responsibility-reader.ts`; keep provider dispatch and durable writes in `source-workflow-read.ts`.
18. Use a dedicated shallow completion schema. Do not extend the combined quote-repair schema.
19. Unmatched model proposals are audit-only. They become usable only if the pure inventory builder
    creates a seed from the same exact raw span and the exclusive matcher attaches the proposal.
20. A base-model complete record skips residual completion. An incomplete record may be replaced only
    by a strictly better deterministic or residual completion.
21. List-structured, single-verb seeds use deterministic completion first. The model is reserved for
    fields the source grammar cannot determine safely.
22. Destination children keep the exact parent quote as immutable evidence, but field fidelity uses
    the existing destination-specific rewritten span. A child object is exactly the shared source
    object head plus source preposition plus one destination. Set `requiredSystem` only under the
    existing action/preposition rules in `expandResponsibilityDestinations`. After a successful split,
    the parent is audit-only and never merge-ready.
23. For a non-destination seed, deterministic `object` is the complete post-verb source text,
    including destination, system, cadence, and timing tokens required by fidelity. Optional `trigger`
    may repeat explicit timing/cadence, but must never remove those tokens from `object`.

These choices are frozen before implementation. The shallow schema separates duties from quote
repair, but it is not a provider-eligibility claim or the reason the score should improve.

---

## 9. Detailed implementation plan

### Phase A: Freeze and inventory

#### P0. Reconfirm baseline and build the residual matrix

Files:

- no runtime edits
- verifier-only analysis under `apps/workers/src/__verify__/` if needed
- `evals/r2-responsibilities.md` for the durable matrix

Actions:

1. Confirm `main` matches `origin/main` and inspect unrelated local changes.
2. Verify `git var GIT_COMMITTER_IDENT` is Albert's required identity.
3. Run the three typechecks and both current R2 responsibility verifiers from section 10.
4. Record the frozen fixture SHA, matcher, 27/30 threshold, 40/500k/$10 reader budget, 1/5/1
   post-pass budget, and false merge/apply defaults in the test output.
5. Re-score the latest 12/30 production map and both 11/30 and 12/30 GPT-4.1 maps offline from their
   durable artifacts. Give every answer-key row exactly one primary class: `inventory_miss`,
   `multi_destination_miss`, `multi_verb_miss`, `object_thin`, `owner_action_or_direction`,
   `quote_error`, or `scorer_mismatch`. Retain secondary classes separately.
6. Add a mechanism column: source inventory, source-only destination split, source-only multi-verb
   split, deterministic completion, residual model completion, quote repair, or scorer investigation.
7. Stop before P1 if fewer than 27 rows have a credible non-scorer mechanism, or if scorer mismatch
   is suspected. Do not change the frozen scorer without a separate owner decision.

Verification gate: the baseline is clean, frozen assertions pass, all 30 rows in each relevant run
are classified, and at least 27 pinned rows have a credible architecture mechanism.

#### P1. Build the source-span inventory

Files:

- `apps/workers/src/lib/responsibility-reader.ts`
- `apps/workers/src/__verify__/r2-responsibility-reader.ts`

Actions:

1. Export a pure inventory builder next to `sourceDutySpanDetails`.
2. Return one seed per exact recognized duty span with chunk ID, span index, source text, exact quote,
   raw start/end, list/prose classification, hash, stable seed ID, and parse diagnostics.
3. Fail loudly on missing raw binding, duplicate seed ID, overlapping duplicate recognition, invalid
   offsets, or quote/offset mismatch.
4. Preserve owner-heading inheritance in the normalized source span while keeping the evidence quote
   an exact raw slice.
5. Add source-only multi-destination splitting using locked decision 5. Child evidence remains the
   exact parent quote; IDs add the normalized destination hash.
6. Add source-only multi-verb splitting using locked decision 6. Each child binds its exact raw clause;
   inherited owner text may normalize the span but never the quote.
7. Successful split children replace the parent in active inventory while the parent and decision
   remain in audit. A failed split keeps only the incomplete parent.
8. Make `buildResponsibilityBaseReadPlan` expose inventory seeds for every duty-bearing chunk, not
   merely synthetic segments.

Verification gate: generic list, heading-owned, prose-owned, multi-destination, multi-verb, repeated-
text, and ambiguous examples produce stable, exact, non-duplicated inventory with no model call.

### Context cut point A

Start a fresh session after P1. Re-read this plan and inspect the diff. Confirm runtime code contains
no pinned role, company, system, or answer-key strings.

### Phase B: Validation and completion

#### P2. Add deterministic completion, exclusive matching, and staged coverage

Files:

- `apps/workers/src/lib/responsibility-reader.ts`
- `apps/workers/src/lib/source-workflow-read.ts`
- `apps/workers/src/__verify__/r2-responsibility-reader.ts`

Actions:

1. Add a deterministic matcher using exact chunk/quote binding and raw offset identity before the
   enclosing-span rules. Assignment is exclusive: one proposal to one seed and one seed to at most
   one accepted proposal. Reject partial overlap, one proposal enclosing multiple active children,
   parent/child cross-assignment, and ambiguous repeated-text matches.
2. Preserve unmatched proposals as audit-only. If an exact quote exposes a previously unseeded duty,
   rerun the same pure inventory builder on that raw span; only a newly created seed may enter the
   normal matcher. A proposal alone never creates a merge-ready element.
3. Report three independent counts and ID lists:
   - `sourceInventory`: all deterministic seeds;
   - `modelDiscoveredInventory`: seeds matched by base model output;
   - `mergeReadyInventory`: seeds represented by complete validated records.
4. Replace ambiguous uses of `inventoryCount` so audits clearly state which stage they mean.
5. Keep existing quote, field, polarity, object, system, cadence, direction, and destination checks.
6. Change omission logic to report two classes: `inventory_detection_gap` for duty-like text not
   seeded, and `completion_gap` for seeded duties without a complete element.
7. Add a pure deterministic completer for list-structured, single-verb seeds. Derive owner from the
   recorded inline/heading/modal owner and action from `sourceDutyVerbMatch`. For an ordinary seed,
   object is the full post-verb source text, including destination, system, cadence, and timing. For a
   destination child, object is shared head plus preposition plus that destination and fidelity uses
   `destinationSpecificResponsibilitySpan`, while evidence remains the exact parent quote. Optional
   trigger may repeat explicit timing/cadence; it never removes object tokens. Set `requiredSystem`
   only under the existing action/preposition rules. Ambiguity leaves the seed incomplete.
8. Validate deterministic records through the same `validateResponsibilityRead` and fidelity checks
   as model records. Do not create a privileged validation path.

Verification gate: deleting all model output leaves source inventory intact; clear list-structured
single-verb seeds complete deterministically; ambiguous seeds stay incomplete; discovery coverage is
zero; and no unmatched proposal reaches merge-ready state.

#### P3. Add exhaustive budget-packed field completion

Files:

- `packages/ai/src/prompts/workflow-read.ts`
- `apps/workers/src/lib/responsibility-reader.ts`
- `apps/workers/src/lib/source-workflow-read.ts`
- `apps/workers/src/__verify__/r2-responsibility-reader.ts`
- `packages/ai/src/__verify__/workflow-read-smoke.ts`

Actions:

1. Add a shallow strict completion schema. Each request item contains an immutable seed ID, chunk ID,
   exact evidence quote, normalized enclosing span, and allowed mutable fields. Each response must
   contain exactly one record per requested seed and no extras.
2. Add a completion prompt that says the model is filling known duties, not discovering duties.
   Fields must use only source-span words except harmless grammatical normalization already allowed
   by validators.
3. Add a pure token estimator and stable packer. Inputs are remaining call/token/cost budget after
   segmentation, process reads, base responsibility reads, and one reserved candidate-bound quote
   repair; per-seed prompt estimate; fixed prompt/schema overhead; configured model price; and
   per-call input/output ceilings. Output is an ordered batch manifest plus unscheduled IDs.
4. Before dispatch, produce a pinned-fixture forecast for low, expected, and high inventory counts.
   The expected case must fit the remaining calls, 500,000 input tokens, and $10. Stop before review
   if it does not fit rather than relying on production truncation.
5. Do not impose a six-record or five-chunk selection limit. The residual queue is exhaustive.
6. Reserve completion through `SourceReaderBudget.reserveRead`, not `reserveRepair`, before concurrent
   dispatch. Apply results in original batch and source-seed order regardless of completion timing.
7. Canonicalize returned IDs, quotes, chunk IDs, and offsets from the seed, then validate every field.
8. Accept only strict improvement for each seed. A bad record stays incomplete with its reasons.
9. A missing, duplicate, extra, invented, or cross-seed response fails that batch loudly. Do not
   partially apply a malformed batch.
10. A timeout, schema failure, or `AllCandidatesFailedError` may receive one retry only if the same
    batch fits the remaining frozen read budget. Otherwise retain every seed as incomplete with the
    exact provider failure. Never record successful coverage for a failed batch.
11. If the frozen budget cannot schedule every batch, mark remaining seeds `budget_exhausted`, record
   estimated calls/tokens/cost, and leave the map degraded.
12. Keep model-run IDs, context-pack IDs, route, prompt version, usage, cache data, and execution
    diagnostics in the existing audit.

Verification gate: a generic 40-duty fixture with intentionally empty base output schedules every
seed in stable token-packed batches; valid responses complete all 40; one malformed batch applies
none of its records; a forced budget shortage lists every unscheduled seed.

#### P4. Rebuild orchestration and final assembly

Files:

- `apps/workers/src/lib/source-workflow-read.ts`
- `apps/workers/src/lib/responsibility-reader.ts`
- `apps/workers/src/__verify__/r2-responsibility-reader.ts`

Actions:

1. At the orchestration seam near `source-workflow-read.ts:2159`, build the full inventory before
   responsibility model reads.
2. Keep base reads because they can complete many seeds cheaply and can discover ambiguous prose.
3. Apply deterministic completion, then create the exhaustive residual queue from all still-incomplete
   seeds. Base-complete and deterministic-complete seeds skip model completion.
4. Run completion batches before the legacy five omission retries.
5. Use legacy omission retries only for `inventory_detection_gap`; do not spend them on normal seeded
   completion gaps.
6. Run candidate-bound quote repair only for remaining eligible quote-copy failures.
7. Revalidate the complete combined state once after all passes.
8. Assemble responsibility elements from `mergeReadyInventory` only and assert every complete element
   maps to exactly one seed or a valid deterministic child.
9. Persist source inventory, matching decisions, batch manifests, completion outcomes, unscheduled
   IDs, final gaps, and failure taxonomy in `validationJson`.
10. Calculate status, kept count, dropped count, primary count, and coverage from explicit named
    stages. Incomplete inventory must never inflate map quality.
11. Preserve merge/apply false and do not dispatch shadow merge.
12. On identical reruns, assert stable seed/child IDs, batch order, final element order, and audit
    assignment. Concurrent completion timing must not affect persistence.

Verification gate: one production-used orchestration test executes inventory creation, base model
matching, exhaustive completion, strict validation, optional detection retry, quote repair, final
assembly, and durable audit without duplicating production logic in the test.

### Context cut point B

Start a fresh verification session. Re-read the full plan, inspect the actual diff, and confirm the
implementation is an inventory-first control-flow change, not a prompt-only variation.

### Phase C: Verification and independent review

#### P5. Complete local verification

Files:

- `apps/workers/src/__verify__/r2-responsibility-reader.ts`
- `packages/ai/src/__verify__/workflow-read-smoke.ts`
- existing verifier files only where a real contract changed

Actions:

1. Add all tests in section 10 using invented generic examples.
2. Run every exact command in section 10 in one fail-fast sequence.
3. Search production reader and prompt files for fixture-derived role, system, destination, and object
   terms generated from the verifier fixture.
4. Run the pure inventory builder against the pinned fixture in verifier-only code. Report which of
   the 30 answer-key rows have a supportable seed. Stop before P6 if fewer than 27 do.
5. Compare actual local batch forecasts with P3's low/expected/high model and stop if the expected
   case cannot fit the frozen limits.
6. Run `git diff --check`.
7. Confirm every new pure helper is covered directly and through the production orchestration seam.

Verification gate: all commands pass, anti-leak checks pass, and the diff contains only in-scope
files.

#### P6. Independent review and correction loop

Actions:

1. Use the installed read-only reviewer already established for this repo, with no file edits,
   subagents, memory, or web search.
2. Give it this full plan, the bake-off evidence, and the exact uncommitted diff.
3. Require P0/P1/P2 findings with file and line, a locked-decision audit, and the verdict
   `APPROVED FOR CI AND LIVE REGATE` or `CHANGES REQUIRED`.
4. Correct every actionable finding and repeat the same reviewer until approved.
5. Re-run section 10 after the final correction.

Verification gate: the saved final review says `APPROVED FOR CI AND LIVE REGATE` with no open P0 or
P1 findings, and all local checks still pass.

### Context cut point C

Start a fresh release session. Read sections 11 through 13 and verify the exact approved commit scope.

### Phase D: Landing and one production gate

#### P7. Commit, push, CI, deploy, and run exactly one gate

Actions:

1. State target repo `u2giants/theoracle`, branch `main`.
2. Verify author and committer identity before commit.
3. Stage only reviewed implementation, tests, and required documentation.
4. Commit and push to `main`; wait for the exact GitHub Actions run to pass.
5. Deploy workers with the Trigger.dev PAT from 1Password. Record worker version and deployment ID.
6. Before the gate, record fixture SHA, model route, frozen budgets, false merge/apply flags, and zero
   rows in the three protected business-model tables.
7. Upload exactly one disposable fixture through the normal application path and wait for the
   source-workflow job and map to reach a terminal state.
8. Score all 30 rows with the frozen key and matcher.
9. Collect seed count, discovery count, completion count, unmatched proposals, batch manifests,
   unscheduled IDs, field failures, quote failures, destination expansions, multi-verb splits,
   omissions, model usage, all run/context/map IDs, flags, and protected table counts.
10. Do not run a second gate for the same release.

Verification gate: exactly one terminal production map exists for the pinned source and released
worker, with a complete 30-row score and unchanged safety state.

#### P8. Apply the result rule

Files:

- `evals/r2-responsibilities.md`
- `evals/bakeoffs/workflow-read.md` only if a cross-reference is needed
- `MACRO_FIRST_IMPLEMENTATION_PLAN.md`
- `plan_r2_deeper_responsibility_architecture.md`
- this plan's STATUS table
- a new write-once file under `HANDOFF.d/`
- `docs/architecture.md` if the shipped control contract needs durable architecture text

Decision:

- `>=27/30`: mark the deeper-reader gate passed and proceed only to the remaining R2 shadow-merge,
  idempotency, refine, namespace, and UI gates.
- `24–26/30`: stop production runs and code churn. Write a bounded residual-gap diagnosis for owner
  review. Do not reopen the completed model bake-off.
- `<=23/30`: hard stop. Require a new owner decision before further reader work.

Actions:

1. Record all evidence, including failures and unused budget.
2. Update every affected status table and fresh-session starting point.
3. Create and self-audit a complete handoff.
4. Commit, push, and wait for CI.

Verification gate: durable documentation matches the sole production result and leaves one
unambiguous next action.

---

## 10. Tests required

### New unit and orchestration cases

1. Stable source inventory from bullets, numbers, headings, modal prose, and direct-owner prose.
2. Exact offset and quote binding when identical duty text repeats in one chunk.
3. Loud failure for missing binding, overlap duplicate, bad offsets, and duplicate seed ID.
4. Empty model output preserves inventory but yields zero discovery and completion coverage.
5. Model proposal matches exactly one seed and cannot claim two unrelated spans.
6. Unmatched proposal cannot become merge-ready without a real source-span binding.
7. Thinned object remains inventory but incomplete.
8. Owner mismatch, polarity reversal, invented object, missing system, missing cadence, and wrong
   direction remain incomplete with distinct reasons.
9. Generic multi-destination source produces stable child IDs and no false split for attribute lists.
10. Multi-verb source produces grounded children only when each action/object is independently clear.
11. Token packer is stable, source ordered, exhaustive, and respects per-call and total limits.
12. Forty incomplete seeds all receive completion work without a fixed six-record cap.
13. Missing, duplicate, extra, invented, or cross-seed completion response rejects the entire batch.
14. One bad completion does not erase its seed or another successfully completed batch.
15. Budget exhaustion lists every unscheduled seed and forces degraded status.
16. Legacy omission retry targets only inventory-detection gaps, not normal completion gaps.
17. Quote repair stays candidate-bound and cannot change normalized fields.
18. Complete-only final assembly, counts, coverage, claim references, and merge eligibility.
19. Validation audit contains source inventory, proposal matching, batch manifests, outcomes, gaps,
   budgets, and prompt/model execution IDs.
20. Frozen SHA, answer-key version, matcher, threshold, budgets, and false merge/apply defaults.
21. Runtime anti-leak guard derives fixture terms at test time and proves none occur in production
   reader or prompt code.
22. Production-used seam covers the whole pipeline without a test-only copy.
23. Pure multi-destination expansion derives its object head and destinations without model fields.
24. Pinned fixture inventory coverage is reported in verifier-only code and supports at least 27 rows.
25. Deterministic completion handles clear list-structured single-verb duties without a model.
26. Exclusive proposal matching rejects repeated-text ambiguity, partial overlap, and parent/child
    cross-assignment.
27. Timeout/provider/schema failure follows the one-budgeted-retry contract and never partially
    applies a batch.
28. Concurrent completion produces stable applied and persisted order.

### Exact commands

Run from `C:\repos\oracle`:

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

Production replay is allowed only in P7 after independent approval, green CI, and worker deployment.

---

## 11. Constraints and gotchas

1. Work on `main`; do not create a branch unless Albert changes the repo rule.
2. Commits must be authored and committed as
   `Albert Hazan <u2giants@users.noreply.github.com>`.
3. Preserve unrelated work and stage only this workstream's files.
4. Use `apply_patch` for edits and do not edit generated Drizzle migrations.
5. No database change is authorized. If one becomes necessary, stop and use the separate shared-db
   process before app code.
6. Never weaken exact evidence or field-fidelity validation.
7. No silent fallback. Binding, identity, schema, batch, budget, or audit failures must be durable and
   visible.
8. Keep the model configurable through `workflow_read`; do not hard-code a provider or model.
9. Do not change model pools during this phase.
10. Frozen 40/500k/$10 and 1/5/1 limits remain unchanged.
11. A completion call is ordinary reader work under the total reader budget, not a way to increase
    the one candidate-bound quote-repair allowance.
12. Incomplete inventory is audit and work-queue state only. It is never authoritative evidence.
13. Any incomplete or unscheduled seed forces `degraded` status.
14. Merge and apply stay false even if the production score passes.
15. The answer-key fixture may appear in verifier/eval code only.
16. Do not run a second production gate for the same release.
17. Trigger deployment credentials stay in 1Password and must never appear in files, arguments, or
    logs. Serialize secret reads.
18. No UI work is in scope, so no screenshot gate is required.

---

## 12. Access and environment

Expected authenticated tools on the Windows `t16` machine:

- `gh` for GitHub push and Actions evidence.
- Trigger.dev CLI or management API for worker deployment.
- `supabase` CLI and protected database access for read-only safety checks and the proven upload path.
- 1Password CLI/connector for credential injection.
- The installed independent reviewer used by this repository.

Secrets live in 1Password vault `vibe_coding`. Relevant items:

- `Trigger.dev Personal Access Token (management)` for deployment.
- `Supabase DB Direct URL - The Oracle (CURRENT PROD …)`, field
  `oracle_session_pooler`, for protected production checks.
- Current Supabase service credential only for the established disposable upload path if the normal
  browser upload cannot be used.

Do not print, persist, commit, or copy secret values into process arguments. Production cloud and
database access is read-only except for the one normal-path disposable fixture upload and Trigger
worker deployment explicitly authorized in P7.

---

## 13. Definition of done, risks, and open questions

### Definition of done

This plan is complete only when:

1. Source spans establish a stable duty inventory before model output.
2. Every incomplete seed is completed or has a durable, explicit failure reason.
3. Complete-only assembly and all evidence rules remain intact.
4. All section 10 checks pass.
5. Independent review approves the implementation with no open P0/P1 findings.
6. One production gate is committed to durable evidence.
7. The score rule is applied exactly.
8. Merge/apply remain false and protected table counts remain unchanged.
9. Code, tests, plan status, eval evidence, and handoff are committed and pushed; GitHub CI is green.
10. Worker deployment SHA/version is recorded when code is shipped.

### Risks

- The deterministic parser may miss free-form prose. Mitigation: keep model proposals and the five
  detection retries for genuine inventory-detection gaps, with separate audit counts.
- A source span may contain several duties. Mitigation: stable parent/child inventory and strict
  independent grounding for each child.
- Exhaustive completion may approach the frozen call/token budget. Mitigation: token-packed batches,
  base-output reuse, and loud unscheduled IDs rather than hidden truncation.
- A shallower completion schema may still be unsupported by some providers. Mitigation: use only the
  currently eligible configured route; provider re-qualification remains separate.
- Inventory count can rise while quality stays low. Mitigation: publish discovery and merge-ready
  coverage separately and score only complete records.

### Open questions

- Whether deterministic prose recognition is broad enough on non-list documents. This must be
  measured with invented local fixtures before the one production gate, not guessed from the pinned
  answer key.

No owner decision is required before P0. The next implementing session should begin there.

### Implementation-plan self-audit

1. **Could a brand-new AI session execute this plan without asking the planning session anything?**
   Yes. Sections 1 through 4 define the business goal, application, trigger, frozen production gate,
   and exact scope. Sections 5 through 8 provide line-level current state, root cause, failed paths,
   and locked design decisions. Section 9 gives ordered file/function actions, dependencies, context
   cut points, and a verification gate for every phase. Sections 10 through 13 provide exact tests,
   operating constraints, access locations, landing steps, stop rules, and completion evidence.
2. **Does the plan carry the full background, nuance, and reasoning, including rejected work?**
   Yes. Section 3 records the 12/30 production gate, 11.5/30 GPT-4.1 bake-off mean, deep-schema model
   exclusions, frozen fixture/hash/matcher, and ban on a second bake-off. Sections 6 and 7 explain why
   model-first reads, scarce retries, prompt-only work, weaker validation, incomplete persistence,
   model substitution, and a new database table are rejected. Section 8 freezes source inventory,
   deterministic completion/splitting, exclusive matching, budget handling, evidence, and merge rules.
3. **Is the goal clear enough to make the right decision if a step proves wrong?**
   Yes. Section 1 says the business outcome is retaining every real duty with accurate owner, action,
   object, system, timing, cadence, direction, and exact evidence, measured by the unchanged 27/30
   gate. It explicitly says the goal wins over any conflicting step and forbids score gains through
   answer-key leakage, weaker evidence, silent deletion, or incomplete downstream records.

All implementation-plan-writer checklist items pass: all 13 sections exist; the goal and conflict
rule lead; scope and rejected approaches are explicit; current code has file/line evidence; locked
decisions are labeled; each P0-P8 step names files/functions and a verification gate; tests are named
by behavior and exact command; secrets are location-only; and done includes commit, push, CI, worker
deployment, the one production gate, durable evidence, and the next score decision.
