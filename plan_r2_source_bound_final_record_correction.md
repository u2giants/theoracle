# R2 Source-Bound Final Record Correction Plan

Status: **LOCAL IMPLEMENTATION AUTHORIZED BY ALBERT 2026-08-12. PRODUCTION HARD STOP REMAINS.
NO DEPLOY, NO SECOND GATE, NO DB CHANGE, NO LANDING WITHOUT A SEPARATE OWNER DECISION.**

Created: 2026-08-11

## Drift log

- **2026-08-25, after the production-replay gate and F3. The 19/19 preservation gate is now RUN and
  PASSED, from the real stored records.** New SELECT-only harness
  `apps/workers/src/__verify__/r2-production-replay.ts` (`pnpm --filter @oracle/workers
  verify:r2-production-replay`, requires `R2_REPLAY_DATABASE_URL`) reads all **93** stored
  responsibility records for the 2026-08-11 map `37a8fc62-23e4-46b7-8464-d1c784dc73cd`, rebuilds the
  source inventory from the same production chunks, and replays every record through the current
  fidelity validator and `correctResponsibilityFinalRecord`. Results, reproduced twice:
  **93/93 seeds re-resolved (0 unresolved); stored baseline scores exactly 19/30 with exactly the
  eleven documented misses; after correction 21/30; regressed rows: NONE; preserved rows: 19/19;
  recovered rows: 19 and 29; negative controls 16, 24 and 26 still unmatched.** 18 corrections were
  accepted (11 `action_inflection_normalized`, 8 `object_boundary_isolated`; 75 records refused with
  `no_strict_improvement`). This is the first time the 19/30 residual has been proven from the real
  records rather than from the verifier-only distillation in the F0 block — and the two agree.
  Consequence for F5: its residual-replay obligation is met for preservation; the remaining eight-row
  recovery target is still unmet by the deterministic corrector alone (21, not 27), which is expected,
  because rows 5, 14, 15, 17, 20 and 23 depend on F3/F4 seam work rather than on re-correcting an
  already-stored record.
- **2026-08-25, after independent review. The replay gate now checks preservation per RECORD, not
  only per ROW.** `scoreResponsibilityAnswerKey` performs a global best-assignment over all 93
  actuals, so row-level preservation alone can in principle stay green while the record satisfying a
  row changes — one record regressing and another taking its place. Gemini 3.7 Flash (read-only
  review of `b025e65`, verdict APPROVE, no P0/P1/P2) raised the same scenario but dismissed it as
  circumstantially impossible here. Circumstantial is not proof, so the gate now ALSO scores each
  stored record in isolation, where no assignment can substitute one record for another, and fails
  if any record that matched a row on its own no longer matches that same row. Result on the real
  data: `recordLevelRegressions: []`. Do not remove this check in favour of the row check; the row
  check is the weaker of the two.
- **2026-08-25, after F3. The late seam is one optional hook, not a new stage.**
  `executeResponsibilityCompletionBatches` gained an optional `correctRecord` hook applied to each
  canonicalized candidate BEFORE strict-improvement selection, so the record that is judged is the
  record that is kept. Only `runLateResponsibilityCompletion` supplies it, so the change is confined
  to the late path exactly as F3 requires; a caller that omits the hook is byte-for-byte unchanged
  (pinned by test F3c). `runLateResponsibilityCompletion` now also returns a `corrections`
  `FinalRecordCorrection[]` audit for F4 to persist. No new seed queue, completion stage, dispatch,
  budget reservation, model call or retry was added — pinned by dispatch counters in F3a/F3b and by
  the over-budget case F3d, and by F3e which asserts exactly one production call site each for the
  corrector and the late path. Environment note: `verify:r2-pinned-inventory` could NOT be run in
  this session because the licensed pinned fixture path `Z:` is not mounted on this machine; every
  other local gate was run and passed.
- **2026-08-13, after F2b. What was built, and the exact limit of what it proves.** The bounded
  object rule is live in one helper, `boundedSourceObject` in `responsibility-reader.ts`, used by all
  three call sites. Green locally: 16/16 F1 cases with no exemption; F0 still 19/30; pinned support
  still 28/30 with rows 16/26 unsupported; `verify:source-workflow-read`, `verify:r0-reader-validator`,
  `verify:document-ingestion-fallback`, `@oracle/ai verify:r2`, `@oracle/ai verify:workflow-read`, and
  all four `@oracle/engines` suites pass; three typechecks clean; `git diff --check` clean.
  **NOT proven, and nobody may claim otherwise: the 19/19 production-replay preservation gate.** No
  local replay harness for the 93 stored production records exists yet. Suites passing is supporting
  evidence, not that proof. Building that replay is F5's first job and it is a hard gate: if any of
  the 19 regress, stop and report rather than tuning the boundary rule to suit them.
- **2026-08-13, after F2b. A design detail worth keeping.** `cutKind` distinguishes a condition cut
  from a clause cut, and that distinction is load-bearing. A condition belongs to THIS duty and is
  required in `trigger`. A neighbouring duty or new list item belongs to a DIFFERENT seed and must
  never be pushed into this record's `trigger`. Collapsing the two would recreate the junk-drawer
  failure that sank the record-level-completeness alternative. F1 case 16 pins it.
- **2026-08-13, after F2b. Anti-invention is unchanged and still measured against the FULL span.**
  Narrowing the expected object cannot let invented words through, because the invention check never
  used the bounded object. Verified by inspection at the `invented_object_content` branch.

- **2026-08-13. OWNER DECISION, unblocks F2. Amends section 11.7.** Albert authorized aligning the
  **expected object** used by `validateResponsibilityFieldFidelity` with the field-boundary rule this
  plan already locked in section 8. This is a **correction, not a weakening**: today the validator
  derives its expected object from `sourceObjectText`, which runs from the first duty verb to the END
  of the span, so it enforces a definition of "object" that contradicts section 8 and contradicts the
  section 1 goal of the smallest complete record. Section 11.7 is amended accordingly: fidelity's
  polarity checks, anti-invention check, owner check and action-family check stay untouched and may
  never be relaxed; only the expected-object boundary is corrected, and only to the section 8 rule.
- **2026-08-13. Rejected after independent review: record-level completeness.** An alternative was
  considered and rejected — replacing "nothing may be missing from `object`" with "object + trigger +
  audit must jointly cover the span". Grok 4.6 refuted it and the refutation is accepted:
  `A ⊆ object` is strictly STRONGER than `A ⊆ (object ∪ trigger ∪ audit)`, so this is a weakening
  described as a broadening. Worse, it is gameable: the frozen matcher never reads `trigger`, so a
  model could emit a short matchable object and dump the remainder into `trigger` and still look
  complete. `packages/ai/src/prompts/workflow-read.ts:97-99` already forbids that shape. Do not
  revive this idea.
- **2026-08-13. Correction to the previous drift entry. Row 5 does NOT share row 17's cause.** An
  earlier session inferred that row 5's failure ("object absorbs unrelated details") was the same
  absorbed-condition mechanism. Independent review refuted it: row 5's stored object carries a
  different duty's nouns entirely and is missing the required `concepts` token, which is a wrong
  object or a wrong surviving seed, not an exception tail. **Row 17 is the only row affected by the
  expected-object conflict.** The other seven eligible rows are inflected action (19, 29), a lost
  named token (14), an over-wide or wrong object (5), or no final record at all (15, 20, 23).
- **2026-08-13. New fact found during review, widens the F2 blast radius.**
  `sourceObjectText` is not only used to CHECK objects. `deterministicInventoryRecord`
  (`responsibility-reader.ts:1139`) copies it straight into `object`, so the no-model path also
  stores the whole span tail. The corrected boundary rule must therefore live in ONE shared helper
  used by the qualifier-loss check, `deterministicInventoryRecord`, and the corrector. That path
  helped produce the 19 rows that currently pass, so F5 must prove all 19 survive.
- **2026-08-13. GLM 5.2's acceptance-rule exemption was removed.** The first F2 draft accepted a
  correction whenever a condition had been moved to `trigger`, even when fidelity regressed. That
  bypass is deleted. The corrector now refuses with the named reason
  `condition_conflicts_with_field_fidelity`, which is honest and visible, until the expected-object
  alignment lands.

- **2026-08-13, after F2. BLOCKING. Needs an owner decision.** The frozen field-fidelity validator
  derives the object it expects from `sourceObjectText(sourceSpan)`, which is everything after the
  first duty verb to the END of the span. When a seed's span holds a duty sentence followed by an
  exception sentence, the exception words are part of the expected object. Measured directly on
  2026-08-13: the ABSORBED record (object still contains the exception) **passes** fidelity, and the
  CORRECTED record (exception moved to `trigger`) **fails** with `object_qualifier_loss`. So the
  repair production row 17 needs makes the unchanged validator go from pass to fail. Row 17 is one of
  the eight rows required to reach 27/30, so at most 7 of 8 are recoverable today, landing at 26/30.
  Three ways out, all owner decisions: (a) change span/inventory so an exception sentence is not part
  of the duty seed's span — out of this plan's scope, touches segmentation; (b) make
  `sourceObjectText` stop at a sentence terminator — a change to the validator, which section 11
  currently forbids; (c) accept 7 of 8 and miss the gate. Per section 13 this is a stop-and-ask.
  Verifier case 14, `KNOWN CONFLICT`, pins it and stays RED until the decision is made.
- **2026-08-13, after F2.** Plan section 9's F2 wording and F1's original case 13 both had this
  polarity inverted: they assumed the absorbed-condition shape is what fidelity rejects today. It is
  not. Case 13 has been rewritten to use the dropped-artifact shape, which fidelity really does
  reject, and the absorbed shape moved to case 14. GLM 5.2 found this error.
- **2026-08-13, after F2. Real bug, fixed.** `core.autocrlf` is true in this repo and there is no
  blanket `text eol=lf` in `.gitattributes`, so a FRESH clone on Windows gets CRLF and every
  multi-line source-text literal in the verifier silently stops matching. This aborted a delegated
  agent's run at the pre-existing frozen-budget guard (verifier line ~2803) before it could reach F0
  or F1 at all. Both that pre-existing guard and the F0 frozen-limits guard now normalize line
  endings before matching. CI on Linux never saw this because Linux checkouts are LF.
- **2026-08-13, after F2.** F0's frozen-budget assertions partly duplicate a pre-existing guard at
  verifier line ~2800 that already froze the reader and post-pass budget literals. The duplication is
  harmless and the two are now consistent, but a future cleanup could merge them.

- **2026-08-12, after F0.** The reader budget defaults (40 / 500,000 / $10 / 1 repair / 4 concurrency
  and post-pass 1 / 5 / 1) and the three fail-safe flags are not exported constants; they are inline
  defaults inside `loadSourceReaderBudgetLimits`, `loadResponsibilityPostPassBudgetLimits`, and
  `packages/db/src/seed.ts`. F0 therefore freezes them by asserting their exact declaration sites in
  source text rather than by importing a constant. No production code was changed to make this
  possible. Later phases must keep that freeze intact.
- **2026-08-12, after F0.** F0's production-shaped records are a verifier-only distillation — one
  representative record per answer-key row — not a copy of the 93 stored production records. They
  reproduce the documented failure shape of each miss and score exactly 19/30. Reading the live map
  was neither needed nor performed.
- **2026-08-12, after F1. Changes what F2 must do.** `validateResponsibilityFieldFidelity` already
  stems the returned action through `dutyVerbsInText`, so an inflected record such as
  `provides / route packets to depot partners` **passes fidelity today**. The inflection is rejected
  only by the frozen `field-aware-v3` matcher. Therefore F2's acceptance rule stated in section 9
  ("re-run existing fidelity validation, accept only strict improvement") cannot mean "fidelity now
  passes" — for rows 19 and 29 fidelity never failed. F2 must accept when fidelity **does not
  regress** AND the named defect (inflected action, absorbed condition, lost artifact token,
  over-wide object) is provably gone. Only the absorbed-condition shape fails fidelity today. F1
  case 13 pins both halves of this rule.
- **2026-08-12, after F1.** F1 resolves the F2 helper dynamically (`await import`) so the suite keeps
  compiling and every pre-existing case stays green while F2 is unwritten. F2 must export
  `correctResponsibilityFinalRecord` from `apps/workers/src/lib/responsibility-reader.ts` with the
  signature and reason codes pinned by F1: `action_inflection_normalized`,
  `object_boundary_isolated`, `condition_moved_to_trigger`, `named_artifact_restored`,
  `ambiguous_object_boundary`, `missing_owner`, `missing_action`, `polarity_reversal`,
  `no_strict_improvement`. Reasons are emitted sorted; the audit carries `seedId`,
  `sourceSpanSha256`, `accepted`, `before`, and `after`. Once F2 exists, F1 may switch to a static
  import. This resolves the plan's "open judgment" on the helper name.
- **2026-08-12, after F0.** The `verify:r2-responsibilities` suite still runs without the licensed
  pinned source. F0 verifies the frozen SHA against the real file only when that path is reachable,
  so CI stays green and the licensed text is never copied into the repo.

Parent: [`plan_r2_source_span_inventory_reader.md`](plan_r2_source_span_inventory_reader.md)
Evidence: [`evals/r2-responsibilities.md`](evals/r2-responsibilities.md)
Handoff: [`HANDOFF.d/2026-08-11T1810Z-al8960ofc-codex-r2-final-record-plan.md`](HANDOFF.d/2026-08-11T1810Z-al8960ofc-codex-r2-final-record-plan.md)

## STATUS table

| Step | Status | Evidence / next gate |
|---|---|---|
| F0. Freeze the 19/30 evidence and correction boundary | ✅ done 2026-08-12 | `verify:r2-responsibilities` reproduces 19/30 under unchanged `field-aware-v3`, pins the eleven misses, the eight eligible rows (5,14,15,17,19,20,23,29) and the three negative controls (16,24,26), and freezes fixture SHA, answer-key version, matcher version, threshold, reader/post-pass budget defaults, and the three fail-safe flags. |
| F1. Add generic failing final-record tests | ✅ done 2026-08-12 | 13 invented-source cases define the F2 contract and are RED for exactly one reason: `correctResponsibilityFinalRecord` does not exist yet. Every pre-existing case in the suite still passes and `pnpm --filter @oracle/workers typecheck` is clean. |
| F2. Add source-bound action and object normalization | ✅ done 2026-08-13 | `correctResponsibilityFinalRecord` (GLM 5.2 draft, reviewed, acceptance-rule exemption removed). All four defect families handled. UNCOMMITTED. |
| F2b. Align the expected object with the locked section 8 boundary | ✅ done 2026-08-13 | One `boundedSourceObject` helper is now the single boundary definition, used by the qualifier-loss check, `deterministicInventoryRecord` and the corrector. A cut condition must appear verbatim in `trigger` or fidelity fails with `condition_not_preserved_in_trigger`; a cut belonging to a different duty is deliberately not demanded. 16/16 F1 cases pass with no exemption, F0 still reproduces 19/30, and every other local suite is green. **Not yet proven: the 19/19 production-replay preservation gate, which belongs to F5.** UNCOMMITTED. |
| F3. Repair the existing late-completion acceptance seam | ✅ done 2026-08-25 | Existing late candidates pass through F2 before existing selection and validation via one optional `correctRecord` hook supplied only by `runLateResponsibilityCompletion`; tests F3a–F3e pin dispatch-once, refusal preserving the existing incomplete outcome, the untouched shared executor, the over-budget case, and one production call site each. `corrections` audit returned for F4. |
| **Production-replay preservation gate (F5 prerequisite)** | ✅ **RUN and PASSED 2026-08-25** | `verify:r2-production-replay` over the real 93 stored records: baseline 19/30 with the eleven documented misses, after correction 21/30, **0 regressed, 19/19 preserved**, rows 19 and 29 recovered, negative controls 16/24/26 still unmatched. |
| F4. Integrate before final validation and assembly | ⬜ open | The production seam stays complete-only, source-ordered, one-to-one, and fully audited. |
| F5. Run unchanged local gates and residual replay | ⬜ open | All suites pass; the pinned source-support verifier stays 28/30 with rows 16/26 unsupported; a separate final-record replay keeps row 24 unsupported and recovers all 8/8 eligible shapes to reach the frozen 27/30 minimum. |
| F6. Independent review and owner decision | ⬜ open | Codex and GLM 5.2 approve with no P0/P1 before Albert decides on local landing. |

Fresh-session starting point: **read this file in full, then stop**. Albert must separately authorize
implementation before F0 or any application edit.

End-of-phase rule: after every completed phase, re-read every remaining phase through F6 and report
any new fact, code change, or failed assumption that affects later work. Update this plan or the
current session's own handoff before continuing when drift is found.

## 1. Ultimate goal

The Oracle must turn clear duties in company documents into short, accurate responsibility records
that preserve who does what, to which business object, under which condition, with exact source
proof. It must not lose a key word, attach an exception to the wrong field, or reject a duty because
the source used `provides` instead of `provide`.

The immediate goal is the smallest complete record supported by each exact source span, with an
honest refusal when that span is insufficient. Success is not making the score pass by any means.
If a step conflicts with this goal, the goal wins. Stop and flag the conflict.

## 2. What this application is

The Oracle is POP Creations and Spruce Line's evidence-backed company knowledge system. Employees
upload business documents and ask questions. Trigger.dev workers segment documents, inventory
duties, complete missing fields with a configured model, validate evidence, and save reviewable
source maps. Later business-model merge and apply stages are separately guarded.

- Repo: `u2giants/theoracle`; checkout `C:\repos\oracle`; branch `main` only.
- Stack: TypeScript, pnpm, Turbo, Next.js 16, Trigger.dev, Drizzle, Supabase.
- Web: `https://oracle.designflow.app`; workers: `proj_wgpzsvhmsopqhvwqaycn`.
- Database: Supabase `eqccjfbyrywsqkxxpjvg`.
- Rules: `apps/workers/src/lib/responsibility-reader.ts`.
- Orchestration: `apps/workers/src/lib/source-workflow-read.ts`.
- Model contract: `packages/ai/src/prompts/workflow-read.ts`.
- Verifier: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.
- Frozen matcher: `apps/workers/src/lib/responsibility-answer-key.ts`.

No UI, schema, deployment, or production operation is needed.

## 3. What triggered this work

The source-span reader passed local source support at 28/30. Albert authorized exactly one production
gate. Commit `62330bdb0b477abb373fa1d155b104cee45a8b66` shipped as worker `20260811.1`,
deployment `725f1ru9`. Run `run_06fv3keiq77bp0gpum352rls01` produced map
`37a8fc62-23e4-46b7-8464-d1c784dc73cd`, which scored **19/30** with unchanged
`field-aware-v3`. That is a binding hard stop.

| Row | Short duty | Exact production-visible reason | Status |
|---:|---|---|---|
| 5 | submit concepts into systems | Record exists, but object omits `concepts` and absorbs unrelated details; another exact compact seed was not represented correctly. | eligible |
| 14 | download PPS photos | Record exists but drops `PPS`, leaving 5/6 required object tokens. | eligible |
| 15 | rename PPS files by SKU | Inventory exposes the rename duty, but no usable rename record survives. | eligible |
| 16 | Licensed Team reviews PPS against tech pack | Completion child says `Lic Coordinator` and only `Review PPS photos`; required owner and object are not both visible. | **ineligible** |
| 17 | submit PPS photos in portals | Correct duty absorbs an exception sentence; its `do not` creates a false negation conflict. | eligible |
| 19 | fill out Letter of Guarantee | Correct record is `Fills out LOG...`; final fields keep the inflected action. | eligible |
| 20 | request sample exemption | Exact span contains the duty, but seed remains a final `completion_gap`. | eligible |
| 23 | request audits before expiration | Exact span contains role, action, object, and timing, but remains a `completion_gap`. | eligible |
| 24 | download style guides to server | Exact span says Licensed Team assists Design Team in downloading. Treating assistance as direct download changes the action family and may misstate the duty. | **ineligible** |
| 26 | submit quarterly royalty reports | Visible span says only that forecast reports are quarterly; no owner or submit action. | **ineligible** |
| 29 | provide assets to partners | Correct record uses `provides`; base action is not retained. | eligible |

Production used 21/40 calls, 63,015/500,000 input tokens, 1/1 general repair, and
$0.350742/$10. This was not budget exhaustion. Merge, apply, and serving stayed false; all protected
business-model tables remained empty.

## 4. Scope

### In scope

- Reduce ordinary source duty-verb inflections to the existing base duty verb.
- Select the smallest complete object supported by the exact completion-visible span.
- Keep explicit conditions and exceptions in `trigger` or audit, not in the affirmative object.
- Preserve a required named artifact token when present in the exact span.
- Route candidates already produced by the existing late-completion path through the same source-bound
  canonicalizer before its existing validation. Do not add another opportunity or dispatch.
- Persist before/after fields, reasons, accepted/rejected status, seed ID, and source-span hash.
- Add generic tests and verifier-only replay of the production failure shapes.

### Out of scope

- Recovering rows 16, 24, or 26 under the current source-span contract.
- Earlier headings, nearby duties, source prefixes, answer-key aliases, or fixture terms as context.
- Matcher, key, threshold, model, route, pool, cache, concurrency, or budget changes.
- New call or retry allowances; segmentation/owner redesign; DB; UI; chat; merge/apply/serving.
- Deployment, production, bake-off, or another live gate.
- Arbitrary noun stemming or broad language rewriting.

## 5. Current state of the code

- `responsibilityCompletionRequest` at `responsibility-reader.ts:201` exposes only the exact seed span,
  quote, offsets, and mutable fields. Keep it unchanged.
- `validateResponsibilityFieldFidelity` at `responsibility-reader.ts:573` checks exact-span field
  support but does not create a compact final record.
- Existing `stemDutyVerb` use near `responsibility-reader.ts:1145` and `:1352` already supplies a
  narrow verb-family mechanism. Do not add a second general stemmer.
- `canonicalizeForcedResponsibilityOutput` at `responsibility-reader.ts:1602` protects IDs and source
  binding for omission work. It is not a general final-field normalizer.
- `validateResponsibilityRead` at `responsibility-reader.ts:2603` owns final validation and complete
  element selection.
- Orchestration builds inventory near `source-workflow-read.ts:2930`, exhaustive completion near
  `:3055`, late completion near `:3401`, and complete-only assembly near `:3774`.
- Audit persistence is near `source-workflow-read.ts:3899`.
- The matcher at `responsibility-answer-key.ts:49-178` stays unchanged.
- Existing code is committed, pushed, deployed, and tested. This plan has no implementation.

## 6. Key findings and root cause

0. **Added 2026-08-13, the deepest finding so far.** The span is doing two different jobs, and they
   conflict. It is the correct unit of EVIDENCE, but `sourceObjectText` also makes it the definition
   of the ANSWER: the expected `object` is everything from the first duty verb to the end of the
   span. So the code enforces "copy the tail" while section 1 and section 8 ask for the smallest
   complete object with conditions in `trigger`. Independent review confirmed the mechanism and
   confirmed it affects exactly one eligible row, row 17 — it is not the cause of the other seven.
   F2b corrects it. Note the same helper also BUILDS objects at `deterministicInventoryRecord`
   (`responsibility-reader.ts:1139`), so the wrong definition is stored as well as enforced.

1. Source discovery is not the only problem. Several misses already have complete or near-complete
   records; their final fields cause rejection.
2. A model object may copy a whole sentence or list. Fidelity can accept source words even when a
   separate exception changes the object's apparent polarity.
3. Verb handling differs by stage. Deterministic parsing stems verbs; accepted model fields may keep
   `provides` or `Fills out`.
4. Exact seeds can remain incomplete despite ample total budget. The current late completion already
   reaches those seeds; its candidates need the same final-field correction before existing validation.
5. Object minimality differs from evidence minimality. Evidence remains verbatim; normalized fields
   should isolate the duty while retaining conditions in structured audit/trigger data.
6. Rows 16, 24, and 26 are honest refusals and required negative controls.
7. This plan's honest target is 27/30. Eight eligible recoveries plus 19 current matches equals the
   frozen passing minimum. The broader source-support ceiling remains 28/30.

## 7. Approaches considered and rejected

1. Restore hidden source-prefix owner lookup. Rejected because it exposes text outside the request.
2. Borrow headings or nearby duties. Rejected for the same honesty reason.
3. Add matcher aliases or weaken negation checks. Rejected because this hides bad stored fields.
4. Raise budgets, retries, or model cost. Rejected because production left large capacity unused.
5. Prompt-only cleanup. Rejected because prior prompt/model changes stayed near 11-19/30 and cannot
   own deterministic acceptance.
6. General English lemmatizer. Rejected because it adds broad behavior and may change business nouns.
7. Delete all extra object words. Rejected because qualifiers can be essential.
8. Recover rows 16/24/26. Rejected because their visible spans do not support the expected action,
   owner, and object combination without changing meaning or borrowing context.
9. Run another gate. Rejected because the parent plan consumed its one gate and hard-stopped.

## 8. Design decisions

### Locked, 2026-08-11

1. `responsibilityCompletionRequest(seed).sourceSpan` is the only semantic source.
2. Quote, chunk, offsets, seed ID, and source hash are immutable.
3. Correction occurs before final validation and complete-only assembly.
4. Action normalization reuses the existing duty-verb parser and cannot change action family.
5. A separate condition may leave `object` only when retained in `trigger` and durable audit. This is
   safe for the frozen score because `field-aware-v3` checks negation only in `action + object` at
   `responsibility-answer-key.ts:62-73`; a generic test must prove the condition remains visible in
   `trigger` while the affirmative object no longer carries its negation.
6. Required named source tokens cannot be silently lost.
7. Rows 16, 24, and 26 remain unsupported negative controls.
8. Matcher, key, threshold, route, model, budgets, DB, merge/apply/serving, deployment, and production
   stay untouched.
9. Ambiguity fails loudly and leaves the seed incomplete.

### Open judgments

- Exact helper name.
- Exact helper and audit field names, provided the locked field rules below remain unchanged.
- Whether the existing `trigger` needs an additional audit-only condition field. `trigger` retention
  itself is mandatory.

### Locked field-boundary rule

1. Find the one source duty verb whose family matches the candidate action. Start the normalized
   object immediately after that verb, excluding a grammatical subject or helper verb.
2. End the object at the first explicit boundary after a complete object: terminal punctuation;
   newline/list marker starting a new clause; a coordinating conjunction followed by a different
   duty verb; or a separate exception/condition cue such as `except`, `unless`, `only if`, `if`,
   `does not`, or `do not` after the affirmative duty is complete.
3. Before ending, retain named artifacts, acronyms, destinations, systems, timing, cadence, and
   direction attached to that duty. Never copy a token from another seed or clause.
4. Put a separated condition or exception into `trigger` verbatim and record its source offsets/hash
   in the correction audit. If the boundary is ambiguous, reject the correction.
5. For compound list text, isolate only a clause that contains its own actor or inherited seed owner,
   duty verb, and object. A later sibling clause cannot complete an earlier clause.

## 9. Implementation plan

### Phase A: Freeze evidence and tests

#### F0. Freeze the residual boundary

Files: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.

Actions: add verifier-only production-shaped actual records; assert 19/30 with unchanged matcher;
freeze eligible rows 5,14,15,17,19,20,23,29 and negative controls 16/24/26; assert fixture SHA,
matcher version, threshold, budgets, and false safety defaults. Do not put fixture terms in production.

Dependency: none.

Verification gate: `pnpm --filter @oracle/workers run verify:r2-responsibilities` reproduces 19/30
and refuses rows 16/26 as targets.

#### F1. Add generic failing tests

File: `apps/workers/src/__verify__/r2-responsibility-reader.ts`.

Add invented cases for regular and multi-word verb inflection; noun non-stemming; negative exception
separation; over-wide list object; omitted named artifact; final incomplete seed retry; atomic bad
batch rejection; ambiguous object refusal; missing owner/action refusal; polarity; immutable source
binding; stable order and audit.

Dependency: F0.

Verification gate: new cases fail for intended current-code reasons before production edits and all
existing cases stay green.

### Context cut point A

Start a fresh implementation session. Re-read sections 6-11 and confirm the diff has tests only.

### Phase B: Pure correction and incomplete-seed handling

#### F2. Add one pure source-bound canonicalizer

Files: `apps/workers/src/lib/responsibility-reader.ts` and its verifier.

Actions:

1. Accept one immutable seed and one candidate, with no surrounding source.
2. Canonicalize action only when exactly one compatible source verb family explains it.
3. Isolate an object using explicit clause boundaries while preserving artifact, destination, timing,
   cadence, and direction.
4. Move a separate condition to trigger/audit; never discard or hide polarity.
5. Re-run existing fidelity validation. Accept only strict improvement.
6. Return typed audit with seed/hash, original/proposed fields, accepted flag, and reason codes.
7. Keep source binding and non-mutable fields immutable.

Dependency: F1.

Verification gate: all F1 tests pass and the production file contains no answer-key terms.

Status 2026-08-13: defects 1, 3 and 4 are done and 13/14 cases pass. Defect 2, the absorbed
condition, is deferred to F2b below because it cannot be accepted honestly until the expected object
is corrected. The acceptance rule carries NO exemption; the corrector refuses defect 2 with the named
reason `condition_conflicts_with_field_fidelity`.

#### F2b. Align the expected object with the locked section 8 boundary

Files: `apps/workers/src/lib/responsibility-reader.ts` and its verifier.

Why: `sourceObjectText` (`responsibility-reader.ts:558-563`) returns everything from the first duty
verb to the END of the span, and `validateResponsibilityFieldFidelity` (`:573-647`, qualifier-loss at
`:621-631`) treats that whole tail as the required object. That contradicts section 1 and section 8.
It is also copied into `object` by `deterministicInventoryRecord` (`:1139`), so the wrong definition
is both enforced and stored. Row 17 cannot be recovered until this is corrected, and 19 + 7 = 26
misses the frozen gate.

Actions:

1. Add ONE shared pure helper that computes the section 8 bounded object from a span: start after the
   matching duty verb; end at the first real boundary after a complete object (terminal punctuation;
   a newline or list marker starting a new clause; a coordinating conjunction followed by a different
   duty verb; or an exception cue such as `except`, `unless`, `only if`, `if`, `does not`, `do not`);
   retain named artifacts, acronyms, destinations, systems, timing, cadence and direction; refuse on
   an ambiguous cut. It must also return the CUT TAIL so callers can preserve it verbatim.
2. Use that one helper in all three places: the qualifier-loss check, `deterministicInventoryRecord`,
   and `correctResponsibilityFinalRecord`. There must be exactly one definition of an object boundary
   in the codebase when this phase ends.
3. Add the paired rule that makes this a correction rather than a loosening: **if a tail was cut, the
   record must carry that tail verbatim in `trigger`.** A cut tail that appears nowhere is a failure,
   not a pass. This is what stops `trigger` becoming a junk drawer.
4. Keep every other part of fidelity untouched: anti-invention, polarity, owner match, action family,
   multi-verb rejection. Do not touch the frozen matcher, the answer key, or the threshold.
5. Delete nothing from F1. Case 4 must go green on merit and case 14 must stay honest.

Dependency: F2.

Verification gate: `verify:r2-responsibilities` reports 14/14 with no exemption in the acceptance
rule; the F0 block still reproduces 19/30; a new regression test proves an in-sentence exception cue
is cut, not only a sentence boundary; a new test proves a cut tail missing from `trigger` is
REJECTED; and the deterministic no-model path is shown to still produce the objects behind all 19
currently-passing rows.

Risk to watch: this changes a path that helped produce the 19 passing rows. F5 must prove 19/19 are
preserved. If any of the 19 regress, stop and report rather than tuning the boundary rule to suit
them.

#### F3. Repair the existing late-completion acceptance seam

Files: `apps/workers/src/lib/source-workflow-read.ts`, optionally a pure queue helper in
`responsibility-reader.ts`, and verifier.

Actions: keep `lateResidualResponsibilitySeeds` and `runLateResponsibilityCompletion` at
`source-workflow-read.ts:3401-3540` as the only late path. Insert F2 between each returned late
candidate and the existing `validateResponsibilityRead` call at `:3449-3470`. Do not add a new seed
queue, completion stage, dispatch, budget reservation, call, or retry. If a candidate still fails,
persist the existing incomplete outcome and new F2 reasons. Preserve existing atomic batch rejection,
strict-improvement selection, execution audit, budget accounting, and stable order.

Dependency: F2.

Verification gate: a generic 40-seed stub proves each residual seed is dispatched by the existing late
path at most once; F2 can make an existing returned candidate pass without any new call; malformed,
ambiguous, or over-budget seeds remain incomplete; reversed async timing does not change order.

### Phase C: Production seam and audit

#### F4. Integrate before final assembly

Files: `apps/workers/src/lib/source-workflow-read.ts`, `responsibility-reader.ts`, verifier.

Actions: use one shared F2 seam for candidate stages before final validation; revalidate combined
state once; preserve source order and one-to-one assembly; persist a
`responsibilityFinalRecordCorrection` audit with counts, IDs, reasons, hashes, and execution refs;
keep incomplete status degraded and all safety flags off.

Dependency: F2/F3.

Verification gate: production-used orchestration test covers base, deterministic, exhaustive, final
correction, rejection, audit, assembly, and degraded status without a test-only copy.

### Context cut point B

Start a fresh verification session. Re-read the plan and audit every production hunk for hidden
context, matcher bypass, or fixture leakage.

### Phase D: Local gates and reviews

#### F5. Run unchanged local gates

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

Also require unchanged pinned support 28/30 with rows 16/26 unsupported; require the separate
final-record replay to keep row 24 unsupported and recover all 8/8 eligible shapes, because 19 + 8
= the frozen 27/30 minimum;
preservation of 19/19 prior matches; anti-leak pass; and no changes to
limits, model, matcher, answer key, threshold, flags, schema, migrations, or deploy files.

Added 2026-08-13, because F2b changes a path that produced the passing rows: the 19/19 preservation
check is now a HARD gate, not a formality. It must be run and reported explicitly. If any of the 19
regress, stop and report; do not tune the boundary rule until they pass again.

Stop on fewer than 8 recoveries, any regression, hidden support for 16/26, or any failed command.

Verification gate: all commands and added gates pass in one fail-fast run.

#### F6. Independent review and owner decision

Added 2026-08-13: F6 must specifically audit the F2b change. A reviewer is to confirm that only the
expected-object boundary moved, that anti-invention, polarity, owner and action-family checks are
byte-for-byte unchanged, that exactly one boundary helper exists, that a cut tail missing from
`trigger` is rejected, and that no acceptance-rule exemption was reintroduced.

Run fresh read-only Codex review; continue the existing GLM 5.2 R2 session; require row-by-row honesty,
locked-decision audit, and `APPROVED FOR LOCAL LANDING REVIEW` or `CHANGES REQUIRED`; fix findings;
rerun F5; then ask Albert only whether to authorize local landing. Deployment and production are a
separate future decision.

Dependency: F5.

Verification gate: both reviews have no P0/P1, F5 remains green, and Albert receives measured results.

## 10. Tests required

Pure tests: verb inflection; no noun stemming; source-token provenance; minimal object with named
artifact; separate positive duty/negative condition; ambiguous boundary refusal; missing required
fields; immutable binding; strict improvement; stable audit reasons.

Orchestration tests: each eligible seed queued once; unchanged budget/concurrency/order; no new retry;
atomic batch rejection; full revalidation; rejected seed remains visible; complete-only one-to-one
assembly; audit persistence; rows 16/24/26 analogues stay rejected; residual replay recovers all 8/8
eligible shapes and preserves 19/19 with unchanged matcher.

Run every F5 suite. None may be skipped. The unchanged pinned verifier continues to measure source
support only and must remain 28/30 with rows 16/26 unsupported. The separate final-record replay is
the check that must keep row 24 unsupported while proving the eight eligible final records.

## 11. Constraints and gotchas

1. `main` only. Implementation is not authorized by plan creation.
2. Use `apply_patch`; preserve unrelated untracked/concurrent work.
3. Before commit, identity must be `Albert Hazan <u2giants@users.noreply.github.com>`.
4. No DB change or app-repo migration.
5. No production read is needed; saved evidence is sufficient.
6. No second gate, bake-off, deployment, or Vercel action.
7. Do not weaken evidence, field fidelity, polarity, matcher, key, or threshold.
   **Amended 2026-08-13 by owner decision.** One narrow exception, and only this one: the
   **expected-object boundary** inside `validateResponsibilityFieldFidelity` may be corrected to the
   section 8 rule, because today it enforces a definition of "object" that contradicts sections 1 and
   8. Everything else in fidelity is still frozen: anti-invention, polarity, owner match, action
   family and multi-verb rejection may not be relaxed. The correction must be paired with the rule
   that any cut tail appears verbatim in `trigger`, so nothing is lost. The matcher, the answer key
   and the 27/30 threshold remain untouchable. Record-level or union completeness is explicitly
   forbidden; see the drift log.
8. Use only `responsibilityCompletionRequest(seed).sourceSpan`.
9. No headings, prefixes, siblings, nearby duties, aliases, or fixture terms.
10. Frozen limits stay 40/500k/$10 and 1/5/1; no new allowance.
11. Merge, apply, serving remain false; incomplete inventory is audit-only.
12. No silent fallback; no hard-coded model/provider; no UI work.

## 12. Access and environment

- Windows 11 `al8960ofc`; PowerShell; `C:\repos\oracle`; branch `main`.
- pnpm/Node are installed. `gh` is authenticated only for later landing.
- GLM uses `ai-glm` with `AI_GLM_CALLER=codex`; continue an existing R2 session.
- Production credentials are not needed. Any later secrets remain in 1Password vault `vibe_coding`
  and values must never be printed or committed.
- Supabase and Trigger.dev stay unused under this plan.

## 13. Definition of done, risks, rollback, and open questions

Done means: pure helper and tests; one shared production seam; existing-budget incomplete handling;
all 8/8 eligible recoveries; 19/19 prior matches; rows 16/24/26 still unsupported; all F5 gates and
reviews green; docs/handoff current; exact diff committed/pushed with green CI only after separate
owner approval; and zero deploy/production/merge/apply/serving action.

Risks: over-normalization, hidden negation, lost qualifiers, budget exhaustion, fixture tuning, and
mistaking local replay for live proof. Mitigate with exact-span tokens, strict improvement, condition
audit, qualifier tests, existing budget refusal, invented fixtures, and honest local-only reporting.

Rollback: before landing, remove only reviewed hunks. After a later approved landing, revert the
single correction commit. No data rollback exists. Never use `git reset --hard`.

Open questions, updated 2026-08-13: row 14 is covered (case 13 green) and row 17 is now understood
and scheduled as F2b. The live open question is **row 5**, whose stored object carries a different
duty's nouns and misses the required token. Independent review found no evidence it shares row 17's
cause, and a boundary fix will not invent a missing token, so row 5 may need a different remedy or
may not be honestly recoverable at all. If it is not, the ceiling is 26/30 and that is a stop-and-ask,
not a reason to loosen anything. Also still open: whether larger
documents fit the remaining frozen budget. Tests decide. Row 24 is no longer an open target. If any
of the eight eligible shapes fails, stop and ask Albert. Do not lower the eight-row gate.

## Implementation-plan self-audit

1. A new session can execute without questions. Sections 1-4 define goal, app, evidence, rows, and
   scope. Sections 5-8 give exact code state, root cause, dead ends, and locked/open decisions,
   including the exact object/condition boundary rule and existing late-completion seam.
   Sections 9-13 give files, dependencies, gates, commands, access, stop rules, landing, and rollback.
2. All current nuance is carried. Sections 3, 6, and 7 distinguish 28/30 local support from 19/30
   production, record all 11 reasons, unused budget, hidden-context failure, and rejected shortcuts.
3. The goal is decisive. Section 1 requires the smallest complete exact-source record and honest
   refusal, and makes that goal override any conflicting step.

All 13 required sections, explicit scope, rejected approaches, locked/open decisions, named tests,
file/function targets, per-step gates, secret locations, commit/push/CI boundary, explicit no-deploy
rule, and plan/handoff links are present. The implementation-plan-writer self-audit passes.
