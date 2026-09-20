# Why Oracle does not yet understand the business holistically

Audit date: 2026-09-20. Reviewed upstream `u2giants/theoracle` commit
`63cdcaaad90a5efe27f25efff0a51d079d4cac9c` in an isolated worktree.

## Conclusion

The system's implemented center of gravity is **extracting and validating individual
statements**, not maintaining and reasoning over an integrated model of the business.
It has substantial, valuable machinery for trustworthy evidence, but the path from that
evidence to a shared business model and then to employee answers is incomplete.

Changing models or polishing the responsibility reader alone cannot close this gap.
Some information is lost before the model sees it; some is rejected by deterministic
rules; some is stored but never supplied to the answering model. The user-visible result
can look like poor AI comprehension even when the original reading was adequate.

This is an architecture diagnosis, not a recommendation to weaken evidence validation.
Keep faithful source receipts. Build separately reviewable interpretations and relationships
on top of them, with explicit support and uncertainty.

## Scope and evidence limits

- Reviewed document parsing and readers, message/Teams ingestion and extraction,
  claim promotion, responsibility merge, business-model lifecycle, Brain synthesis,
  employee chat, MCP, live meeting context, and evaluation contracts.
- Three independent read-only audit slices were reconciled against the current source.
  The main reviewer rechecked the highest-impact code paths and the latest evaluation
  status. Findings below include concrete source locations and counterexamples.
- No production query, model call, deployment, database mutation, or application-code
  edit was performed. Present production settings, review backlog, data volumes, and
  currently deployed revision were not independently verified.
- The canonical local checkout still contains six unfinished July edits and is behind
  upstream. Those edits were preserved and excluded from this audit. They are not the
  current architecture or an appropriate implementation baseline.
- No new runtime test execution is claimed. Code-grounded failures below are distinguished
  from hypotheses about their frequency in production. Published production results are
  explicitly described as recorded evidence.

## Findings

### H1 — The business-model construction and serving chain is incomplete

Severity: HIGH. Confidence: high. Type: architectural capability gap.

Evidence:

- `apps/workers/src/trigger/business-model-merge.ts:4–16` invokes
  `createResponsibilityShadowProposal`.
- `apps/workers/src/lib/business-model-merge.ts:221` selects only
  `item.shape === 'responsibilities' && item.elementKind === 'responsibility'`.
- That proposal is persisted with `shadow: true` and `applyEligible: false`
  at lines 582–583. `packages/oracle-engines/src/model/lifecycle.ts:55` rejects
  shadow/non-applicable proposals at the application boundary.
- Employee chat context at `apps/web/app/api/chat/route.ts:232–275` contains
  selected claim summaries and legacy macro relationships, not source structures or
  durable business objects.
- `docs/architecture.md:967` records removal of the old automatic macro writer.
  The remaining relationship insertion is manual admin authoring in
  `apps/web/app/admin/macro/_actions.ts:132–159`.

Consequence: a responsibilities document, a licensing policy, and a production meeting
do not automatically become one reviewed account of who acts, when approval is required,
what exceptions apply, and what downstream work depends on it. Improving a source map
does not establish a path for that improvement to reach employee answers.

Qualification: legacy reviewed macro relationships and manual authoring still work.
This is not a claim that the application has no relationships whatsoever. The missing
capability is the complete automated replacement spanning newly ingested information.

### H2 — Source shape is lost or stops at classification

Severity: HIGH. Confidence: high. Type: ingestion/representation gap.

Evidence:

- `apps/workers/src/trigger/document-ingestion.ts:255–285` uses PDF `result.text`,
  spreadsheet `sheet_to_csv`, and Word `extractRawText`.
- `apps/workers/src/lib/source-workflow-read.ts:2694–2696` dispatches detailed
  process and responsibility reading. The six-shape classification vocabulary does
  not mean all six detailed readers exist.
- Teams ingestion writes pending messages (`teams-transcript-ingestion.ts:228–239`);
  their extraction prompt path (`claim-extraction.ts:397–430`) does not invoke the
  document structure reader. Meetings therefore lack an equivalent structured
  conversation model of decisions, disagreements, actions, and described processes.

Consequence: a table's grouping, visual hierarchy, merged-cell meaning, embedded
diagram, or page layout can carry information that text conversion does not preserve.
Rules, reference information, narrative explanations, and conversations can be
classified without becoming the corresponding structured business knowledge.

Qualification: standalone images have a vision path, and text conversion preserves
some content. The finding concerns lost structural/visual signals and missing detailed
shape interpretation, not total loss of every Office/PDF document. Atomic extraction
can still recover explicit text facts.

### H3 — Retrieval can exclude the very cross-department facts a question needs

Severity: HIGH. Confidence: high. Type: concrete retrieval defect.

Evidence:

- `packages/ai/src/retrieval-plan.ts:899–915` recognizes PLM/Designflow wording
  and returns excluded domains `customer_ops`, `licensing_approvals`, and
  `creative_design` without checking whether the question explicitly requests them.
- `packages/ai/src/retrieval.ts:102–108` rejects a claim carrying **any** excluded
  domain through `NOT EXISTS`.
- The analogous file-operations rule at `retrieval-plan.ts:953` excludes product
  development and production lifecycle.

Counterexample: “How does PLM support our licensing approvals across the overall
workflow?” requests both sides of a business connection, but the PLM rule removes
licensing evidence before similarity ranking can consider it. Multi-domain claims
can be especially vulnerable because any excluded tag is sufficient.

The original noise-control intent is sensible. Applying it as an unconditional veto
is incompatible with cross-functional understanding.

### H4 — Conversation extraction drops context needed to interpret answers

Severity: HIGH. Confidence: high. Type: concrete context assembly defects.

Evidence:

- `apps/workers/src/trigger/claim-extraction.ts:1205–1224` selects pending user
  messages only. The carry-in context at lines 1168–1176 is earlier than the first
  selected message; it does not restore questions interleaved among selected answers.
- `packages/ai/src/prompts/extraction-system.ts:373–375` can format assistant
  messages as non-evidence context, so the selection path is narrower than the
  formatter's supported contract.
- `apps/workers/src/trigger/teams-transcript-ingestion.ts:228–246` preserves an
  unmatched speaker name in metadata while leaving employee ID null. Extraction
  selects `employees.name` at `claim-extraction.ts:1213`; the formatter falls back
  to `Unknown Employee` rather than the preserved speaker name.

Counterexample: “yes,” “every Friday,” and “Design handles that” cannot be reliably
interpreted if the questions between those answers disappear. Similarly, “I approve
this” loses useful attribution when a known transcript speaker becomes unknown.

The right boundary is to retain questions and speaker context for interpretation while
continuing to require evidence receipts from eligible source statements.

### H5 — The responsibility validator mistakes a narrow vocabulary for meaning

Severity: HIGH. Confidence: high. Type: deterministic semantic bottleneck.

Evidence:

- `apps/workers/src/lib/responsibility-reader.ts:452–459` builds duty recognition
  from a fixed English verb list.
- `:735–743` returns `passed: false` with `source_has_no_duty_verb` if no listed
  verb occurs.
- The list omits common business verbs such as negotiate, reconcile, manufacture,
  inspect, pay, purchase, and ship.

Counterexample: a standalone duty “Finance pays suppliers” has a clear owner, action,
and object, but no recognized duty verb in this rule. A better model cannot make that
unchanged source pass the vocabulary gate. Non-English sources are exposed too.

Qualification: this blocks a responsibility-map admission, not necessarily every
atomic claim about the same duty. Incomplete inventory can preserve the rejected
candidate for audit. Extending the list alone would continue the same structural
limitation; quote fidelity and semantic role interpretation need separate contracts.

### H6 — Synthesis omits supporting facts that its own validator accepts

Severity: HIGH. Confidence: high. Type: concrete data-flow bug.

Evidence in `apps/workers/src/trigger/brain-synthesis.ts`:

- Line 337 snapshots `approvedClaims` from `allClaimsMap`.
- Lines 344–357 subsequently add macro relationship supporting claims to the map.
- Line 360 creates the expanded validation set.
- Line 383 still builds the model corpus from the earlier `approvedClaims` snapshot.
- Line 219 renders macro support IDs and kinds, not the missing support summaries.

Consequence: an out-of-domain or otherwise unselected supporting fact can be recorded
as available evidence for validation without ever being shown to the synthesizer.
This specifically undermines cross-department reasoning. It also overstates context
in observability, which uses the expanded claim list.

### H7 — Answer construction starts with a small fact slice and does not investigate gaps

Severity: HIGH. Confidence: high. Type: retrieval/context design gap.

Evidence:

- Chat retrieval uses only `latestUserMessage.content`
  (`apps/web/app/api/chat/route.ts:183`) with `topK: 8` (198/205).
- Legacy relationships are selected through those initial claim IDs (214–222).
- The answer context renders claim summaries (264) and relationship summaries with
  supporting IDs (257), omitting source neighborhoods and supporting claim text.
- Brain selects up to 200 high-impact domain claims
  (`apps/workers/src/trigger/brain-synthesis.ts:315–317`) and synthesizes summaries.
  Existing section-linked claims supplement that set, so 200 is not a universal cap.

Consequence: “And what does that mean for China?” is retrieved independently of the
process established earlier in the conversation. A broad workflow question receives
one small selection without checking whether owners, gates, exceptions, or downstream
dependencies are missing. The model receives conversation history for generation,
but that does not repair retrieval's missing context.

Eight is not inherently wrong for a narrow fact question. One fixed retrieval pass
is insufficient as a general mechanism for company-wide explanation.

### M1 — Extraction completion and usable knowledge are different milestones

Severity: MEDIUM. Confidence: high for code; runtime impact unmeasured.

`packages/oracle-engines/src/extraction/promote-candidate.ts:290` inserts promoted
claims as `pending_review`; Brain requires `approved` at `brain-synthesis.ts:315`.
This is a valid safety boundary. If approval lags, uploaded material can look processed
while providing no usable knowledge to employees. Current backlog size was not measured.
Measure and display readiness through reading, review, integration, and serving separately.
Do not auto-approve merely to increase apparent recall.

### M2 — The evidence is stronger for local extraction than for holistic understanding

Severity: MEDIUM. Confidence: high. Type: evaluation coverage gap.

The latest recorded R2 result is **23/25, passing**, not the older 19/30 or 23/30
failure repeated in earlier plans. `plan_r2_completion_recovery_cycle.md:26` and
`evals/r2-responsibilities.md:1142–1160` record the September 10 owner-approved
contract and rescore of the same persisted map. The versioned contract explicitly
requires one evidence span, controlled action paraphrases, and no object paraphrases
(`apps/workers/src/__fixtures__/licensed-team-responsibilities-contract-v2.json:7–10`).

That is a useful fidelity result. It does not prove multi-source understanding.
The general extraction runner explicitly uses canned outputs and states that it does
not test live model behavior (`packages/ai/evals/runners/eval-extraction.ts:18–21`).
Separate live reader tests exist; the mock runner should not be mistaken for them.

No end-to-end business-answer acceptance suite was found in the reviewed evaluation
paths. A green local suite cannot establish that an employee receives the right
complete explanation with the right applicability and exceptions.

### M3 — The user-facing behavior is optimized for interviewing

Severity: MEDIUM. Confidence: high. Type: product-contract mismatch.

`packages/ai/src/prompts/oracle-system.ts:18,53` instructs “Ask one tightly scoped
question at a time” and “Prefer sharp operational questions over summaries.” The
live meeting prompt explicitly says not to summarize or answer the meeting
(`apps/workers/src/trigger/teams-live-recall-utterance.ts:135–136`).

These instructions are reasonable for knowledge collection. They do not define an
analysis mode that explains a business process, compares official rules with practice,
traces consequences, and clearly distinguishes facts from supported interpretations.
Even a complete knowledge layer would need an explicit answer/analysis contract.

## What I recommend

Start with one demonstrable business outcome: explain one end-to-end licensed-product
journey using a process document, a responsibility document, and a meeting transcript.
Judge the final answer on ownership, handoffs, approval conditions, exceptions, reasons,
source conflicts, and consequences for the business. Use a held-out example too.

For that outcome, close the complete chain rather than adding another isolated reader:

1. Preserve the source structures and dialogue needed for interpretation. Include
   exact spans plus their headings, table context, speaker identities, and questions.
2. Separate evidence receipts from interpreted business relationships. An individual
   receipt can stay bound to one source span; a supported business conclusion can cite
   several receipts without pretending they were one verbatim sentence.
3. Make one reviewed cross-source business model usable by answers. Connect equivalent
   roles/processes across sources and retain scope, exceptions, time, disagreements,
   and uncertainty. Department labels and name resolution alone are not this model.
4. Retrieve around the business question and its conversation context. Preserve
   explicitly requested domains, expand relevant dependencies, and check coverage
   before concluding. Show the answering model the actual supporting premises.
5. Prove the employee-facing answer end to end. Keep the existing fidelity checks,
   but distinguish parsing, faithful facts, integration, retrieval completeness,
   and answer quality so one passing stage cannot stand in for the whole result.

The immediately repairable defects are H3, H4, H5's overly narrow admission contract,
and H6. They will improve fidelity and recall, but H1 and H7 are the essential work
for the requested holistic capability. Do not present those bug fixes alone as solving
business understanding.

## Decision and completion

The requested diagnostic audit is complete. Application behavior has not been changed.
The recommendation above is a proposed next workstream, not an implementation claim
or authorization to deploy. The older July patch was not resumed or merged.

Severity tally: 7 HIGH findings, 3 MEDIUM findings. HIGH includes missing architecture
as well as defects; it does not mean seven independently reproduced production incidents.
