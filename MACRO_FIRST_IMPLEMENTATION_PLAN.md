# Macro-First Implementation Plan — Canonical Plan of Record

Status: **CANONICAL. R0 is implemented locally; fresh-database CI and the authorized
post-deploy business-process rerun remain required before R1 begins.**

Created: 2026-07-21
Last reviewed: 2026-07-21
Repository: `u2giants/theoracle`, branch `main`
Production: `https://oracle.designflow.app`
Database: Supabase project `eqccjfbyrywsqkxxpjvg`
Workers: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`

This is the single forward implementation plan for completing the Oracle's macro-first
redesign. It reconciles the original process-centric redesign with the later shape-aware
reader pivot and supersedes their implementation-stage sequences where they conflict.

Supporting documents retain their value but have narrower roles:

- `MACRO_FIRST_REDESIGN.md` — product rationale, original diagnosis, keep/kill inventory,
  state-machine design, and historical stage record.
- `SHAPE_AWARE_READER_DESIGN.md` — six-shape reader rationale, segmentation contract, and
  completed reader Stages 1–2.
- `MODEL_BAKEOFF_SPEC.md` — model-selection and bake-off procedure.
- `evals/shape-aware-stage2.md` and `evals/macro-first-battery.md` — empirical gate log.
- `fix_enhancement.md` §1–§6 — original failure diagnosis and swimlane ground truth.
- `HANDOFF.md` — temporary operational continuation state, not architectural authority.

When another document conflicts with this plan's target architecture, ordering, gates, or
rollback posture, this plan wins. Historical facts and already-recorded production evidence
remain valid unless explicitly corrected here.

---

## 1. Outcome and acceptance standard

The Oracle must understand POP Creations / Spruce Line as a coherent, evolving business,
not as a search index of disconnected sentences.

The primary knowledge layer will be a durable, versioned business model containing:

- processes, stages, owners, systems, gates, branches, exceptions, and handoffs;
- responsibilities and accountability relationships;
- rules, policies, applicability, exceptions, and conflicts;
- reference entities, attributes, and business relationships;
- meeting decisions, action items, open questions, problems, owners, and due dates;
- a deliberately small set of macro-significant goals, constraints, risks, and rationales;
- consultant findings and recommendations derived from the approved model.

Atomic claims remain mandatory, but their role changes. A claim is an **evidence receipt**:
an immutable, reviewable statement tied to a validated quote in a real document chunk or
message. Claims support business-model elements; they are not the primary reasoning unit.

The redesign is complete only when:

1. Chat and Brain reason from the current approved business model first.
2. Every served model element and material answer assertion traces through claim IDs to
   validated source evidence.
3. Rejecting or superseding support evidence changes the served confidence/provisional state
   without rewriting history.
4. Administrators review coherent model-change bundles rather than hundreds of isolated
   claims.
5. The full historical corpus has been backfilled through the new pipeline.
6. The old blind claim-first path and retired macro machinery have been removed only after
   the backfill and rollback gates pass.
7. The macro-first acceptance battery reaches at least 18/20, with the required individual
   gates specified in R7–R9.

---

## 2. Why the redesign is necessary

The prior claim-first architecture preserved provenance but destroyed business structure.
The production evidence is decisive:

- The canonical swimlane diagram produced 241 fragmentary claims from 56 unique quotes and
  no assembled workflow.
- Text documents produced 403 of 469 claims without useful structure; the process-only reader
  was approximately 96% blind to ordinary textual knowledge.
- Lens fan-out, source outlines, and an LLM macro layer attempted to reconstruct structure
  after extraction had already flattened it. They could not reliably recover what the
  pipeline had discarded.
- A shape-aware segmentation pass subsequently proved that real documents are composites of
  processes, responsibilities, reference material, rules, conversation, and narrative.

The correct inversion is therefore:

```text
source evidence
  -> shape-aware source map
  -> evidence claims
  -> reviewed merge proposal
  -> versioned business model
  -> chat / Brain / consultant reasoning

Every served model element points downward to claims and validated quotes.
```

---

## 3. Current verified state

### 3.1 Implemented and deployed

- Macro-first schema foundation and state-machine/application scaffolding from migration 86.
- Source workflow/structure maps with immutable superseding semantics.
- Process reader with deterministic quote validation and macro-health reporting.
- Map-directed extraction and document + map-element candidate dedup.
- Removal of lens fan-out and obsolete outline-injection writers.
- Shape-aware reader Stage 1: unified per-source `segments/elements/relations` model while
  preserving process behavior.
- Shape-aware reader Stage 2: two-pass segmentation into six shapes, controlled overlap,
  deterministic source coverage, repair retry, and stale-pipeline hash protection.
- Real-data segmentation gate: five named company sources plus a production Teams transcript.
- Process regression on the swimlane at approximately 96% relation coverage.

### 3.2 Partially implemented

- Only `process` has a detailed pass-2 reader. Other shapes are classified but not read into
  structured elements.
- The process source map feeds map-directed claim extraction, but deterministic omission
  reconciliation is incomplete.
- Lifecycle and transactional-application helpers exist, but there is no production merge
  writer or application caller.
- Business-model and recommendations admin pages are placeholders/read-only shells.

### 3.3 Not implemented

- Durable cross-shape business-model storage.
- Responsibilities, ruleset, reference, conversation, and limited narrative-macro readers.
- Cross-source semantic merge and shadow proposals.
- Bundle review, veto, transactional apply, rebase, and version administration.
- Business-model-first chat, Brain, MCP, and live-meeting consumption.
- Consultant analyzers and recommendations over the new model.
- Historical corpus backfill and final legacy cleanup.

### 3.4 Known blocking quality finding

A production read of `business-process.md` segmented successfully but retained 64 and dropped
101 process graph items during quote validation. The current diagnostics do not preserve enough
information to separate:

- source-kind normalization mismatch;
- valid citations outside the current segment's chunk subset;
- ambiguous repeated quotations;
- true hallucinated/mismatched quotations;
- node failures amplified into incident edge failures.

The code currently validates process-map quotations with the default strict policy while text
claims use `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY`. This is a contract mismatch, not evidence
that the standard should be weakened. R0 resolves it before new pass-2 readers ship.

---

## 4. Non-negotiable invariants

1. **Evidence remains deterministic.** No LLM judges whether a quotation is "close enough."
2. **One evidence pointer resolves to one persisted chunk or message.** Cross-chunk synthesized
   quotations are rejected.
3. **Source maps are guidance, never evidence.** Model-created summaries, maps, and inferred
   relations cannot validate claims.
4. **Claims remain immutable evidence receipts.** Revision creates a replacement/supersession;
   it never overwrites the original model output or source history.
5. **Business-model versions are immutable.** Changes create a new version through the
   transactional application contract.
6. **Serving rechecks evidence at read time.** An element whose required supporting claims are
   no longer approved becomes provisional or unserved according to the serving policy.
7. **Merge suggestions never prove identity.** Semantic keys and embeddings shortlist; the
   merge verdict and review/application contract establish durable identity.
8. **No silent fallback.** Blind extraction, degraded maps, repair, pool fallback, and
   provisional serving must be visible in logs and health state.
9. **No destructive schema shortcut.** Existing production tables are not renamed or dropped
   based on an assumption that they are empty.
10. **No blind-path removal before proof.** The fallback survives until R9 succeeds and is
    removed only in R10.

Relations obey the same evidence boundary without inventing quotations. A relation is supported
by the validated claims on its endpoint elements and may also carry an optional connective claim
whose quote validates inside one chunk. A relation never cites a synthesized cross-chunk sentence.
If the source never states the connection and it cannot be supported through evidenced endpoints
under the shape contract, it remains provisional or is rejected; model inference alone is not
evidence.

---

## 5. Shape-aware source-reading contract

The first iteration contains six extensible shapes:

| Shape | Primary structured output | Extraction unit |
|---|---|---|
| `process` | steps, gates, artifacts, systems, terminals, and flow relations | one claim per primary transition/branch plus necessary element evidence |
| `responsibilities` | roles and responsibility records | one claim per responsibility record |
| `ruleset` | rules, scope, conditions, effects, and exceptions | one claim per rule |
| `reference` | entities, attributes, and relationships | one claim per attribute or relationship |
| `conversation` | decisions, actions, questions, problems, and meeting assertions | one claim per decision/action/problem/assertion |
| `narrative` | claims by default; capped macro elements only | ordinary facts remain claims; only significant goals/constraints/risks/rationales escalate |

The reader remains two-pass:

1. Segment and classify persisted source chunks, allowing controlled overlap for genuinely
   composite chunks.
2. Run shape-specific structured readers over the resulting segments.

Every element contains a source chunk/message pointer and an evidence quotation. Per-shape
coverage measures the shape's primary elements, not decorative/structural helpers.

### 5.1 Narrative boundary

Narrative must not recreate fragment soup as "elements."

- Ordinary narrative assertions, dates, metrics, and facts remain evidence claims.
- At most five macro elements may be proposed per narrative segment.
- Allowed macro kinds are `goal`, `constraint`, `risk`, `rationale`, and `open_question`.
- A macro element must have document-wide or cross-process consequence: being wrong about it
  would materially change a business decision.
- High macro density is a segmentation-quality finding suggesting `ruleset`, `process`, or
  another shape; it does not authorize unlimited narrative elements.
- Narrative macro elements remain provisional until the normal evidence and bundle-review
  contract is satisfied.

Narrative still has an explicit post-cutover extraction path. After segmentation, ordinary
narrative segments run a **shape-directed narrative claim pass**: segment title/summary may guide
the call but is non-quotable, and every output remains an atomic evidence claim backed by a real
chunk. This is not the legacy unsegmented blind-document path. R3 builds and gates this pass along
with the limited narrative-macro reader, and R10 removes only the unsegmented fallback.

---

## 6. Evidence-validation contract

One shared source-policy resolver must be used by both source-map readers and claim extraction.
The resolver selects the deterministic validation policy from the source kind:

| Source | Policy | Required behavior |
|---|---|---|
| Native text / Markdown | markdown document normalization | Formatting syntax may normalize; visible words must occur in order within one chunk. |
| PDF / Word extracted text | PDF/OCR document normalization | OCR/layout artifacts may normalize under the existing policy; no semantic paraphrase. |
| Vision-transcribed image/diagram | strict/topology-preserving | Evidence must match the persisted transcription; diagram edge lines remain load-bearing. |
| Teams transcript/message | transcript-only fuzzy policy | Existing overlap threshold; accepted evidence anchors to the real stored utterance. |

Normalization parity is not a relaxation. These remain hard failures:

- the chunk/message belongs to another source;
- the chunk is not present in the source;
- the quotation fails the selected deterministic policy;
- a quotation is ambiguous within the chunk and no approved offset-disambiguation exists;
- an element ID is missing or duplicated;
- a relation endpoint does not survive element validation.

### 6.1 Cross-segment citations

A structured element may cite a chunk outside its own segment only when:

1. the chunk belongs to the same document; and
2. the segmentation covers that chunk in at least one segment.

The element is accepted if its quote validates, but the mismatch is recorded as
`crossSegmentCitation` in validation diagnostics. A high rate (initial alert threshold: 20%)
marks segmentation quality as degraded for review. A foreign or uncovered chunk is a hard
failure.

Cross-segment citation is a distinct validator outcome, not a renamed `unknown chunkId`. The
validator receives the document-wide covered chunk map plus the citing segment's membership so it
can separately report valid-same-document, foreign-document, and uncovered-document citations.

### 6.2 Required rejection diagnostics

Each dropped element/relation must retain enough bounded information to diagnose the class:

- shape and element/relation type;
- element/relation ID;
- cited chunk/message ID;
- bounded failing quote excerpt;
- deterministic failure class/check name;
- validation method/policy selected;
- whether it would pass the other relevant document normalization policy;
- root failure versus cascade from a missing endpoint;
- cross-segment status.

Raw model output or an equivalent bounded audit artifact must be retained for reader calls so
quality failures can be reproduced without guessing.

---

## 7. Durable cross-shape business model

The durable model uses one shared spine and typed family detail tables. This is a
supertype/subtype design: one versioning, identity, merge, review, evidence, and application
system; several normalized tables for genuinely different fields.

### 7.1 Shared spine

Planned generic tables (final names may be adjusted only before the R1 migration is authored):

- `business_objects`
  - logical container such as a process, responsibility model, rule set, reference dataset,
    decision log, or narrative-macro collection;
  - `object_kind`, `name`, `slug`, `status`, `current_version_id`, embedding and audit fields.
- `business_object_versions`
  - immutable versions with source change, version number, status, summary, and timestamps.
- `business_elements`
  - shared identity and cross-shape fields: `version_id`, stable `element_key`, `shape`,
    `element_kind`, `label`, owner entity/department/raw owner, provisional flag, confidence,
    sort order, and audit fields.
- `business_relations`
  - stable relation key, source and destination element keys, relation kind, condition,
    provisional flag, confidence, and audit fields.
- `business_element_claims`
  - version-scoped element/relation evidence links with `primary` or `corroborating` support.
- `business_element_systems`
  - resolved system/entity links needed across shapes.
- `business_paths`
  - process-only ordered paths and branches, attached to the shared version spine.
- `business_object_top_domains`
  - domain scoping for merge shortlisting and retrieval.

Existing `business_model_changes`, change events, and recommendations remain conceptually shared
but are currently process-scoped. R1 explicitly generalizes them additively:

- add nullable `object_id` references to `business_objects` and a constrained `object_kind` where
  a proposal/recommendation must be understood before an object exists;
- store every create proposal's normalized proposed slug in a dedicated column; namespace locks
  and collision checks derive from this authoritative field, never from `operations_json`;
- retain legacy `process_id` and version references for compatibility through R9;
- backfill generic references only for rows with an unambiguous guarded mapping. At R1 this is
  expected to map zero rows because durable objects are not created before R6 apply and the current
  repo has no legacy proposal/recommendation writers; the exit-gate count of zero is success, not a
  failed backfill;
- update proposal, event, recommendation, lock, admin, and serving reads to prefer generic object
  identity while still understanding legacy rows;
- require exactly one valid target identity for a reviewable new-format row, with explicit
  create-proposal handling before an object ID exists.

This is R1 spine work, not an R5 improvisation. Legacy process references drop only in R10.

### 7.2 Typed detail tables

Each detail table is 1:1 with `business_elements` through `element_id` as PK/FK:

- `business_process_details`: node type, lane, process-specific presentation fields.
- `business_responsibility_details`: role, action, object, trigger, required system.
- `business_rule_details`: scope, condition, effect, exception.
- `business_reference_details`: entity type, constrained attribute key/value, reference kind.
- `business_conversation_details`: decision status, contested flag, speaker, due date, action
  status, meeting reference.
- `business_narrative_macro_details`: macro kind and the limited goal/constraint/risk/rationale
  fields.

Fields belong on the shared spine only when they are genuinely queried across shapes. A new
shape may add one typed detail table and registry entry; it must not clone versioning, merge,
review, or application machinery. Unbounded `attributes_jsonb` and generic EAV escape hatches
are prohibited.

### 7.3 Shape registry as contract source

The shape registry becomes the single code-owned definition of:

- allowed element kinds;
- allowed relation kinds;
- required typed fields;
- reader instructions;
- extraction directive;
- primary-element coverage denominator;
- detail-table serializer/validator;
- merge prompt fragment and deterministic integrity checks.

Registry contract tests must prove every shape has all required behaviors and that a produced
element can be persisted and rendered without shape-specific branching outside the registry
adapter.

---

## 8. Identity, deduplication, and evidence linkage

Four identifiers have separate jobs.

### 8.1 Candidate idempotency key

Before merge, candidate idempotency remains scoped to the exact immutable source-map element:

```text
documentId + mapElementRef
```

This prevents repeat dispatch from duplicating a candidate while preserving distinct evidence.
It must not be replaced by semantic text hashing.

That rule applies to structured map elements and relations. Intentionally element-less claims—
most notably ordinary narrative claims—continue to use the existing evidence-sensitive fallback
hash over normalized summary/domain inputs plus the validated quote and source pointer. The
narrative pass also records its immutable segment reference for lineage. Semantic fallback hashing
is deliberate for map-less evidence; it is never reused as durable-object identity and never
replaces map-element idempotency when an element ref exists.

### 8.2 Source-map reference

`claims.map_element_ref` points to the exact immutable source map and element/relation that
produced the claim. Before accepting the candidate, code must verify that the reference exists
in the active map and is eligible for the current extraction window. A well-formed but unknown
reference is dropped and logged.

### 8.3 Semantic candidate key

Code computes a normalized, shape-specific semantic key from structured content. It is stored
for:

- exact-match merge shortlisting;
- embedding/LLM candidate narrowing;
- reviewer hints;
- coverage and duplicate analytics.

A semantic key never automatically merges, deduplicates, or proves identity. Similar rules and
responsibilities may be legitimately distinct.

### 8.4 Durable element key

`element_key` is assigned when a model change is applied and remains stable across versions of
the same business object. Later source elements attach to it only through the merge verdict and
review/application contract.

When wording changes but identity is preserved, the new version keeps the durable key. When the
business meaning changes, merge proposes refine, contradict, supersede, or create as appropriate.
Old claims remain linked to the old immutable version; new evidence links to the new version.

---

## 9. Merge contract

The merge worker aligns a validated source map with the current durable model and produces a
`business_model_changes` proposal. It never directly mutates the current model.

### 9.1 Deterministic preparation

- Resolve owner, department, system, and referenced entity candidates through the entity
  registry; retain honest raw names when unresolved.
- Shortlist candidate business objects by object kind, top domains, stable keys, and embeddings.
- Shortlist element pairs through semantic keys and embeddings.
- Reject references to non-existent source elements, claims, versions, or durable keys.
- Compile a complete source/evidence pack for the model call and audit it through the existing
  context-pack machinery.

### 9.2 Model verdicts

The model may propose:

- `create_object` — no existing object represents the source structure;
- `confirm` — structure is unchanged; attach corroborating evidence only;
- `refine_object` — add/update/remove a bounded neighborhood of elements/relations;
- `contradict` — evidence materially conflicts with the current model;
- `needs_review` — ambiguity prevents a safe proposal.

The model emits explicit operations, source element refs, target durable keys, and evidence claim
IDs. Deterministic validators enforce referential integrity, operation legality, and complete
evidence before a proposal becomes reviewable.

### 9.3 Create-versus-existing guard

The LLM cannot authorize `create_object` by itself. Before a create proposal becomes reviewable or
applicable, code searches live objects of the same kind using normalized proposed slug, top-domain
scope, exact semantic candidates, resolved owners/entities, and embedding shortlist. An exact
deterministic namespace collision blocks creation. Any plausible existing-object match forces
`needs_review` with the candidate objects; it may not silently create or silently confirm. Only a
reviewed alignment decision establishes identity. This guard runs for both concurrent and
sequential re-reads and is tested independently from the creation advisory lock.

### 9.4 Idempotency

Proposal idempotency is based on the immutable source-map row ID, current base version, merge
prompt/model version, and the deterministic input hash. Re-dispatching the same map cannot create
a duplicate active proposal. A new map created by an identical re-read is a new input and may
produce a new proposal, but the create-versus-existing guard prevents it from silently creating a
duplicate object. Proven equivalence produces `confirm`; ambiguity produces `needs_review`, never
an automatic create. Stage gates distinguish **same-map redispatch idempotency** from **new-map
semantic confirmation**.

---

## 10. Review, transactional apply, and serving authority

### 10.1 Bundle review

Administrators review one coherent model change containing:

- before/after structure;
- operation list;
- source-map elements;
- supporting claims and validated quotes;
- entity-resolution choices;
- confidence and eligibility failures;
- per-operation or per-claim veto controls.

Approval is structural review plus evidence review. Eligible bundled claims are approved through
audited `model_change_bundle` review events. Vetoed or ineligible claims leave their dependent
elements provisional.

### 10.2 Transaction contract

Application reuses and generalizes the existing lifecycle contract:

- acquire the per-object advisory lock;
- reread proposal and current version inside the lock;
- verify base version and optimistic concurrency;
- revalidate every operation and evidence link;
- write the complete new immutable version, details, relations, paths, and evidence links;
- move the object's current-version pointer only after every write succeeds;
- append change and claim-review events;
- on stale base, transition to `needs_rebase`;
- on injected or real error, transition to `failed_apply` with zero partial model state.

`confirm` may auto-apply only when it adds corroborating evidence and makes no structural change.
Auto-apply never silently approves a pending/rejected claim: every linked claim must already be
approved or must pass the same audited bundle-approval eligibility path used by human approval.
If claim eligibility is incomplete, `confirm` remains pending review.

Lock identity is explicit. Existing-object changes lock `business_object:<objectId>`. A create
proposal locks a deterministic creation namespace derived from object kind, normalized proposed
slug, and top-domain scope so competing creates cannot mint duplicate objects before an object ID
exists.

Stored and effective provisional state are distinct. `business_elements.provisional` records the
decision made when that immutable version was applied. Serving derives:

```text
effective_provisional = stored_provisional
  OR missing/invalid current primary support
  OR another serving-time eligibility failure
```

Serving never mutates an old version merely because evidence status changes. It computes effective
state and labels or excludes the element according to the serving setting.

### 10.3 Serving authority

The current approved business-object version is the primary reasoning source. At read time:

- required support claims are rechecked;
- missing/rejected primary support makes the element provisional;
- provisional elements are either clearly labeled or excluded according to the approved setting;
- every cited assertion resolves to claim IDs and real source evidence;
- source maps and merge prose never become citations.

---

## 11. Canonical implementation sequence

Every stage is completed, verified, documented, committed, pushed, CI-green, and deployed where
runtime behavior changes before the next stage begins. Each stage appends its results, failures,
run IDs, metrics, and decision to the appropriate eval log. The swimlane regression runs at every
reader/model stage.

Before a real-data gate runs, its fixture manifest must record the source name, immutable source
ID or approved local path, content hash, expected shape(s), and answer-key version. The initial
manifest uses the six sources already named in `evals/shape-aware-stage2.md`: `business-process.md`,
`Licensed Team Responsibilities 2 - tagged.txt`, `transcript-Book report overview.txt`,
`Team Communication and Product Details 2.docx`, `SKU descriptions naming convention.pdf`, and a
completed production `teams_transcript` channel pinned by channel/source ID. A fixture content
change requires a new manifest version; it must not silently move a gate's answer key.

### R0 — Validator contract, reference integrity, and coverage instrumentation

**Purpose:** remove the shared reader-quality uncertainty before multiplying pass-2 readers.

Entry:

- Shape-aware segmentation Stage 2 remains green.
- Existing process reader and map-directed extraction remain deployed.

Build:

1. Add one source-kind quote-policy resolver shared by map and claim validation. It creates named
   vision-transcription and transcript-fuzzy policies around the existing strict/markdown/PDF
   constants and fuzzy parameters so call sites cannot drift. Bump the reader pipeline version in
   the source hash so unchanged documents cannot silently reuse pre-R0 maps.
2. Pass source kind/parse kind into map validation.
3. Add bounded structured rejection diagnostics and reader-output audit retention.
4. Separate root element failures from relation endpoint cascades.
5. Validate `mapElementRef` membership against the active map.
6. Allow same-document, covered cross-segment citations and record them as quality signals.
7. Export and directly unit-test the map validator.
8. Add deterministic map-primary-element to claim reconciliation per shape.
9. Write actionable coverage omissions to `gaps` idempotently; do not use an LLM grader. `gaps`
   uses a free-text `gap_type`, so R0 adds no enum migration; the writer must define a stable
   `model_coverage` type and deterministic source/map/element idempotency key.
   Every employee-facing gap consumer explicitly excludes `model_coverage`; an administrator may
   convert a finding into a human question only through a separate audited action.
10. Add DB-free deterministic reader/validator verifies to CI.
11. Add configurable per-source limits for segment reads, input tokens, estimated cost, repair
    attempts, and concurrency before the first additional pass-2 reader ships.
12. Resolve the duplicate hand-written `86_*` trap before any new settings or schema migration is
    attempted. Mark `86_source_workflow_maps.sql` as superseded/dead without changing already
    applied production behavior, document the lexicographic double-run, and add a fresh-database
    test that asserts the surviving `source_workflow_maps` shape from
    `86_macro_first_schema.sql` plus later migrations.

Exit gate:

- Every one of the existing 101 drops is grouped into a reproducible class and receives a decided
  disposition: contract defect fixed, correct hard rejection, prompt under-production,
  segmentation defect, cascade, or separately scheduled work. No unresolved bucket remains.
- `business-process.md` drop ratio and important-relation evidence coverage are reported outcomes,
  not pass thresholds. The intended healthy range remains below 20% drops and approximately
  90–95% relation coverage, but those figures must never be reached by weakening validation.
- Any prompt under-production preventing the intended range becomes its own explicit reader gate;
  it is not relabeled as validator success.
- Swimlane regression remains approximately 96% relation coverage with no duplication regression.
- Hallucinated-but-well-formed map refs fail a deterministic test.
- Foreign-document and uncovered-chunk citations fail deterministic tests.
- Markdown/PDF/vision/transcript policy parity fixtures pass.
- Omission reconciliation is repeatable and creates no duplicate gaps.
- Reader budgets fail loudly on a bounded synthetic over-budget source.

Rollback:

- Diagnostics and tests are additive.
- Policy resolver can revert to the prior call-site behavior without schema rollback.
- Already persisted maps/claims are immutable; rollback changes future validation only. Any rows
  produced under the R0 policy remain auditable and are superseded through normal re-read behavior,
  never rewritten.
- No durable business-model writes exist yet.

### R1 — Durable cross-shape model contract

**Purpose:** give every structured shape a safe, versioned destination before more readers depend
on it.

Entry:

- R0 green.
- No schema migration is authored until the production-data audit is recorded.

Production-data audit:

- Count every existing macro-first/process table.
- Inspect FKs into those tables through `pg_constraint`.
- Inspect RLS enablement and policies.
- Record any manual/test rows and decide their guarded copy behavior.
- Run drift check and confirm migration journal state, including the historical duplicate `86_*`
  filenames.
- Confirm the generated Drizzle snapshot and the hand-written SQL migration sequence describe the
  same target schema; record the exact snapshot-only/generated reconciliation step required by
  the current migration runner before authoring R1 DDL.

Build:

1. Create the generic spine and typed detail tables additively through the normal migration runner.
2. Leave legacy process tables in place through R9.
3. Do **not** copy legacy process content into the new spine during R1. New objects are created only
   by the R2–R6 reviewed fixture pipeline and R9 corpus backfill. Guarded copy is limited to
   compatibility/reference columns and aborts when counts or references do not match.
4. Generalize `business_model_changes`, change events, and recommendations from process-scoped to
   object-scoped as specified in §7.1: add `object_id`/required create-time kind, retain legacy
   process references through R9, and update every read/write/lock/admin path.
5. Generalize lifecycle and transaction helpers against the new spine.
6. Add RLS and deny anonymous access; service-role worker access only until admin APIs are built.
7. Add per-shape persistence/constraint tests and a fresh-database migration test.
8. Update the read-only admin shell to show generic objects/versions without applying changes.
9. Seed fail-safe settings, default off: `business_model_merge_enabled`,
   `business_model_apply_enabled`, and `business_model_serving_enabled`. Preserve the existing
   blind/map-directed extraction setting until R10. Provisional serving remains a separate setting.

Exit gate:

- Production audit recorded before migration.
- Migration applies idempotently through `pnpm db:migrate` and the journal.
- Any compatibility-column guarded backfill counts match exactly; no process-content rows are
  duplicated into the new spine.
- Anonymous access denied; authorized service/admin reads pass.
- All shape detail contracts reject invalid required-field combinations.
- Existing process reader and swimlane gate are unchanged.
- Old code can roll back while legacy tables remain intact.

Rollback:

- Stop new-table readers/writers and restore prior code.
- New tables are additive and may remain unused.
- Do not drop legacy tables or columns.

### R2 — Responsibilities vertical slice

**Purpose:** prove the entire reader-to-shadow-merge contract on the simplest high-value shape.

Entry: R0 and R1 green; narrative/responsibility business decisions confirmed; merge and apply
settings remain off until this stage explicitly enables merge in shadow mode only.

Build:

1. Responsibilities pass-2 reader and flat strict schema.
2. Typed persistence into per-source structure maps.
3. Responsibility-specific semantic keys, extraction directive, and coverage denominator.
4. Map-directed claims for each responsibility record.
5. Entity resolution for roles, owners, departments, and systems.
6. `business-model-merge` worker in shadow mode for responsibility objects.
7. Read-only admin proposal rendering with evidence quotes and operations.

Exit gate:

- The pinned `Licensed Team Responsibilities 2 - tagged.txt` fixture produces responsibility
  elements for at least 90% of its answer-key responsibility records.
- At least 90% of primary responsibility elements have valid evidence claims.
- First ingest produces one `create_object` proposal.
- Same-map redispatch is idempotent. A sequential identical-source reread produces a new map but
  resolves to `confirm`; a near-match is forced to `needs_review`; neither can fork a duplicate
  object through `create_object`.
- A doctored single responsibility produces one bounded `refine_object` operation.
- Re-dispatch produces no duplicate active proposal.
- A deterministic namespace-collision fixture proves that an LLM `create_object` verdict is
  blocked when a live object already occupies that namespace.
- No proposal can apply.
- Swimlane regression green.

Rollback: disable the responsibility reader/merge dispatch; shadow rows are inert and auditable.

### R3 — Ruleset, reference, and narrative vertical slices

**Purpose:** reuse the shared machinery for conditional policy, structured lookup knowledge, and
the post-cutover narrative path.

Entry: R2 shadow-merge gates green; R3 fixture manifest and narrative-macro approval recorded.

Build:

- Ruleset reader, typed rule details, applicability/exception relations, extraction directive,
  coverage, and shadow merge.
- Reference reader, typed entity/attribute/relationship details, extraction directive, coverage,
  and shadow merge.
- Shape-directed narrative atomic-claim extraction that does not depend on the legacy unsegmented
  fallback.
- Limited narrative-macro reader for approved goal/constraint/risk/rationale/open-question kinds,
  with the five-element cap and misclassification finding.
- Shape-specific deterministic contract tests and semantic-shortlist tests.

Exit gate:

- SKU naming source produces structured rules with scope, condition/effect, and exceptions.
- Business-process reference tables produce entities/attributes without treating each cell as an
  unrelated generic fact.
- The pinned `Team Communication and Product Details 2.docx` narrative portions retain their
  evidence claims after the legacy blind path is disabled in a test, while macro output stays
  within the approved cap.
- Each shape reaches at least 90% primary-element claim coverage on its real fixture.
- Create/confirm/single-refine/idempotency gates pass separately for both shapes.
- Responsibilities and swimlane regressions remain green.

Rollback: disable each new shape independently; existing shadow proposals remain inert.

### R4 — Conversation vertical slice

**Purpose:** convert meetings into durable decisions and accountable follow-up while preserving
spoken-source evidence rules.

Entry: R3 gates green; a completed production transcript is pinned in the fixture manifest;
conversation source identity and repeated-ingestion rules are documented.

Build:

- Conversation pass-2 reader over persisted Teams/message sources.
- Decisions, actions, questions, problems, assertions, speakers, owners, and due dates.
- Transcript fuzzy-validation parity with real-utterance anchoring.
- Separate process segments continue through the process reader.
- Shadow merge into decision-log/business objects.

Exit gate:

- Book Report transcript yields conversation structure plus its separate reconstructed process.
- A production Teams transcript passes with no document-style normalization leakage.
- At least 90% of primary decision/action elements have evidence receipts.
- Repeated meeting discovery/ingestion does not duplicate decision objects or proposals.
- Create/confirm/refine/idempotency gates pass.
- Prior shape regressions green.

Rollback: disable conversation map/merge dispatch; transcript ingestion itself remains intact.

### R5 — Process shadow merge

**Purpose:** prove the hardest graph-alignment behavior only after shared merge machinery works on
flat structures.

Entry: R2–R4 shadow merge is green for every non-process family; no proposal can apply; the
canonical swimlane fixture and its answer key are pinned.

Build:

- Process-specific merge prompt fragment and deterministic graph operation validation.
- Node, relation, lane, path, branch-neighborhood, entity, and system alignment.
- Read-only before/after graph rendering.
- No apply path.

Exit gate:

- Canonical first ingest produces one process `create_object` proposal reproducing the validated
  source map.
- Identical re-ingest produces `confirm`.
- One doctored edge produces a bounded `refine_object` touching only its neighborhood.
- A disjoint workflow produces a new object, not a destructive refinement.
- Re-dispatch is idempotent.
- Unsupported claims/elements are visibly provisional.
- All earlier real-corpus shape gates remain green.

Rollback: stop process merge dispatch; shadow proposals never affect serving.

### R6 — Bundle review, apply, versioning, and rebase

**Purpose:** activate the transactionally safe human-control layer.

Entry: all shape readers and process shadow merge are green; Albert has accepted the shadow
proposal backlog and review presentation; `business_model_apply_enabled` remains false until the
concurrency and injected-failure gates pass.

Build:

- Complete admin proposal queue and before/after rendering for every implemented shape.
- Evidence quote inspection, eligibility failures, per-operation/claim veto, approve/reject.
- Build the production application callback against the shared spine and every typed detail table;
  the existing lifecycle helper supplies the transaction/lock/state skeleton but has no production
  mutation body or caller.
- Build `confirm` corroborating-evidence auto-apply eligibility and the object/create-namespace
  locks; neither exists in production merely because its lifecycle state/helper is scaffolded.
- Stale-base `needs_rebase` workflow.
- Application audit events and claim bundle-review events.

Exit gate:

- Approving a fixture proposal creates version 1 and all expected evidence links.
- Veto creates provisional output without silently approving the rejected evidence.
- Rejection leaves the durable model unchanged and returns claims to the documented state.
- Two proposals on one base: first applies, second becomes `needs_rebase`; rebase is correct.
- Injected mid-apply failure produces `failed_apply` with zero partial new version/state.
- Repeated approve/apply calls are idempotent.
- Two competing `create_object` proposals for the same normalized namespace serialize under the
  creation lock and cannot mint duplicate durable objects.
- Auto-applied `confirm` cannot approve or link an ineligible claim.
- A sequential reread cannot bypass the deterministic create-versus-existing guard even when the
  merge model proposes `create_object`.
- Visual UI verification passes at desktop and narrow widths.

Rollback: stop application and serving flags; retain applied immutable versions for audit. Never
delete applied history as rollback.

### R7 — Answering inversion

**Purpose:** make the business model the primary reasoning layer in actual employee experiences.

Entry: R6 has approved fixture objects/versions for every implemented shape; provisional-serving
policy is approved; existing Brain sections and their claim citations are inventoried before the
new synthesis path is enabled.

Build:

- Business-model retrieval by domain, object, owner, entity, and semantic relevance.
- Chat context ordered around model objects/elements/relations; claims supplied as evidence.
- Oracle system prompt updated to distinguish model assertions, provisional state, and evidence.
- Brain synthesis re-anchored to business objects/versions while citing claims downward.
- MCP knowledge endpoint and live-meeting context use the same serving authority.
- Read-time support-claim revalidation and provisional demotion.

Exit gate:

- Macro-first battery B1–B7 and B10 each score 2.
- Answers name coherent processes/responsibilities/rules and cite resolvable claim IDs.
- Rejecting a primary support claim demotes or removes the dependent element immediately.
- A fabricated claim/element ID canary is rejected.
- Claim-only fallback is visible and used only when no eligible model context exists.
- Existing approved Brain versions remain immutable history; the first model-anchored synthesis
  creates a new version rather than rewriting legacy sections.
- R7 battery scoring is explicitly limited to the approved R2–R6 fixture objects. Full-corpus
  product scoring and the 18/20 acceptance bar remain R9 gates.

Rollback: disable business-model serving and fall back loudly to the legacy claim path while
retaining all new model data.

### R8 — Consultant layer

**Purpose:** derive evidence-backed business insights from the approved model.

Entry: R7 serving and support-demotion gates green; sufficient approved objects exist for B8/B9;
consultant model route and cost budget are selected through the bake-off procedure.

Build:

- Deterministic analyzers first: missing owner/system, uncovered stage, conflicting rules,
  unowned action, unmitigated risk, stale decision/action, process bottleneck candidates.
- LLM synthesis only after deterministic candidate creation.
- Wire consultant analyzers to emit object/element-scoped recommendations through the table
  generalized in R1.
- Admin review and status workflow.

Exit gate:

- Battery B8 and B9 score 2.
- Every recommendation resolves to current model elements and supporting claims.
- Fabricated references fail deterministic validation.
- Changing/rejecting support marks recommendations stale or provisional.

Rollback: disable recommendation generation/serving; model and evidence remain unchanged.

### R9 — Controlled historical backfill

**Purpose:** prove the architecture against the full corpus before legacy removal.

Entry: R6–R8 green; all source shapes have a post-cutover extraction path; review capacity and
priority order are approved from the dry-run report; serving rollback has been rehearsed.

Build/run:

1. Dry-run report across the corpus: maps, shadow proposals, predicted review load, cost, failures,
   and coverage by document/domain/shape.
2. Albert-approved priority order by business value.
3. Human-sized review batches, targeting no more than 10 structural proposals per sitting.
4. Bulk accept limited to true `confirm` proposals with unchanged structure.
5. Reruns after early approvals so later merges use the improved current model.
6. Legacy-claim reconciliation report before writes: classify existing claims as reused evidence,
   new corroborating evidence, superseded evidence, or still-unmapped evidence. Do not delete or
   automatically supersede an approved legacy claim merely because a new map exists.
7. Preserve existing claim IDs and Brain citations. New versions link approved legacy claims when
   their evidence and meaning remain valid; changed facts create new claims/versions and retain the
   old claim on historical versions.
8. Coverage omissions remain administrative model-quality work. Every employee-facing gap/query
   consumer explicitly excludes `gap_type='model_coverage'`; those rows become employee questions
   only through a separate, deliberate, audited conversion action.

Exit gate:

- Full corpus processed; no stale pending maps/proposals outside the approved window.
- Macro-first battery at least 18/20.
- BO-0 reaches at least 80% of the selected ceiling on all fixtures.
- Coverage, drop, proposal, cost, and review-load report accepted.
- No unexplained duplicate durable objects/elements.
- No unexplained duplicate claims from new-map re-reads; every duplicate-looking pair is resolved
  as distinct evidence, corroboration, or supersession without rewriting history.
- Rollback drill succeeds by disabling new serving without losing audit history.

Rollback: pause batches and disable business-model serving. Do not erase applied versions.

### R10 — Cleanup and final cutover

**Purpose:** remove the old architecture only after the new one survives real production data.

Entry: R9 accepted; legacy-claim reconciliation complete; the shape-directed narrative pass has
been proven with the unsegmented fallback disabled; database restore/compatibility procedure has
been rehearsed against a production-shaped copy.

Build:

- Delete the legacy **unsegmented** blind-document default/fallback after Albert approves the
  backfill result. Retain the evidence-only, shape-directed narrative claim pass.
- Remove dead source-outline/lens/macro writers, settings, model slots, and admin remnants.
- Drop legacy process-only tables/columns only through a separately reviewed cleanup migration.
- Remove dead `stableGraphKey` and superseded code/docs.
- Delete `HANDOFF.md` only when no unfinished work remains.

Exit gate:

- Typecheck, tests, build, drift, and migration journal clean.
- Grep proves no references to retired modules/settings/tables.
- Production web, workers, and database operate only on the new model.
- Live acceptance battery remains green after cleanup.
- Final documentation accurately describes the resulting code, not this implementation plan.

Rollback: cleanup migration requires a rehearsed restore path and explicit approval. Do not enter
R10 while rollback still depends on a legacy table scheduled for deletion.

---

## 12. Verification matrix

| Concern | Deterministic/local | Real-data/production | Required continuously |
|---|---|---|---|
| Quote policies | source-kind fixtures; strict/normalized/fuzzy boundary tests | instrumented rerun per source kind | CI guard + stage gates |
| Segmentation | registry/coverage/repair tests | five company files + Teams transcript | every reader stage |
| Map validation | direct unit tests, cascade and cross-segment fixtures | business-process and swimlane runs | CI + R0 onward |
| Map refs | membership and malformed-ref tests | no dangling accepted refs | CI + every extraction stage |
| Coverage | deterministic primary-element reconciliation | per-shape real fixture ≥90% | every vertical slice |
| Persistence | per-family constraints and serializers | guarded production copy/counts | R1 and schema changes |
| Merge | create/confirm/refine/disjoint/idempotency fixtures | real shadow proposals | R2–R5 |
| Apply | lock, stale base, injected failure, repeat call | controlled reviewed fixture | R6 onward |
| Serving | rejected-support demotion, fabricated-ID canary | B1–B10 | R7 onward |
| UI | component/integration tests | Playwright screenshots and keyboard path | every UI stage |
| Backfill | dry-run summarizer/idempotency | complete corpus report | R9 |

Deterministic DB-free guards belong in GitHub Actions. Live-model/production-corpus gates remain
explicit recorded release gates; they must not silently become optional because they are too
expensive or require approved data access.

---

## 13. Model routing and bake-offs

- No model ID is hard-coded into reader, merge, or consultant logic.
- Existing auxiliary slots remain: `workflow_read`, `model_merge`, and the appropriate later
  consultant/deep-synthesis route.
- Every new/materially changed model task follows `MODEL_BAKEOFF_SPEC.md`.
- Pools must preserve a capable fallback and record the actual provider/model attempt.
- Strict-schema eligibility is checked before dispatch; failing candidates fall back loudly.
- Each vertical slice records quality, latency, input/output tokens, cache behavior, and cost.
- A model change does not bypass deterministic output validation or stage gates.

Required bake-off timing:

- R0: no model bake-off unless the reader prompt changes materially.
- R2: responsibilities read + merge.
- R3: ruleset/reference reads and merge fragments.
- R4: conversation read + merge.
- R5: process merge.
- R7: answering/conversation ladder.
- R8: consultant synthesis.

---

## 14. Observability, performance, and cost

Every reader and merge run must expose:

- source/map/object/version/proposal IDs;
- prompt/model/route/pool attempts;
- segmentation and element counts by shape;
- validation pass/drop counts by reason;
- root failures versus cascade failures;
- cross-segment citation count;
- primary-element evidence coverage;
- proposal operation counts by type;
- tokens, cache use, latency, and cost;
- final health/status and loud degraded reason.

Controlled overlap and per-segment reads multiply model calls. Before R9, measure and enforce
configurable budgets for:

- maximum segments/read calls per source;
- maximum input tokens and estimated cost;
- concurrency per document;
- end-to-end ingestion duration;
- retry/repair limits.

Large sources must not remain inside an unbounded inline document-ingestion critical path. When
real metrics show the current task budget is unsafe, split orchestration into idempotent child
tasks using existing Trigger patterns; do not raise timeouts as the primary fix.

Budget instrumentation and fail-loud caps ship in R0. Calibration continues in every vertical
slice; R9 may tune the configurable values from the dry-run report but may not introduce the first
budget enforcement.

---

## 15. Security and migration discipline

- Schema changes use `packages/db/src/schema.ts` plus new hand-written migration files where
  required; previously applied migrations are never edited.
- Apply through `pnpm db:migrate` only. Never use `drizzle-kit push` or direct Supabase migration
  application that bypasses the journal.
- Run `pnpm db:check-drift` before and after R1/R10.
- New model tables start with RLS enabled and no broad client policies.
- Worker writes use service-role access; admin reads/actions go through existing authenticated
  server-side authorization.
- Proposal operations and evidence IDs are treated as untrusted model output until deterministic
  validation succeeds.
- No source excerpts, employee data, or secrets are added to logs beyond bounded diagnostics
  already authorized for the application.

---

## 16. Risks and responses

| Risk | Response |
|---|---|
| Business model becomes a second truth store that drifts from claims | Version-scoped evidence links, read-time claim revalidation, provisional demotion, immutable history. |
| Cross-shape schema becomes a sparse mega-table | Shared spine plus typed 1:1 family detail tables. |
| Detail tables become six separate systems | One registry, merge worker, lifecycle, review UI, transaction, and serving path. |
| Semantic normalization collapses distinct knowledge | Semantic keys shortlist only; identity established at reviewed merge. |
| Reader coverage looks green by redefining the denominator | Shape registry declares primary elements; omission audit reports both structural and claim coverage. |
| Quote-normalization fix weakens evidence | One deterministic source-policy helper; no semantic matching for documents; existing transcript exception only. |
| Segment overlap drives cost/timeouts | Configurable budgets, metrics, parallel child tasks when justified, bounded repair. |
| Process-only assumptions leak into shared machinery | Responsibilities first, then two other flat shapes, then process shadow merge before apply. |
| Shadow proposal backlog overwhelms review | Read-only backlog metrics and human-sized R9 batches; no apply until R6 UI is complete. |
| Production schema contains unexpected rows/dependencies | Blocking pre-migration audit, guarded copy, legacy tables retained through R9. |
| Claim-first runtime becomes permanent | R7 is an explicit acceptance stage; R10 cannot complete until claim-only serving is removed. |
| Sequential re-reads fork duplicate durable objects | Deterministic create-versus-existing guard forces review before create; semantic candidates never auto-merge. |
| Coverage goals incentivize weaker validation | R0 gates complete classification/disposition; numeric coverage remains reported and prompt under-production stays visible. |

---

## 17. Decisions and open business approvals

### 17.1 Resolved technical decisions

- Macro-first with claims as evidence receipts is the target architecture.
- Six-shape, two-pass source reading remains the reader architecture.
- The durable model is cross-shape, not process-only.
- Storage uses one shared spine plus typed family detail tables.
- The build proceeds through vertical slices, beginning with responsibilities.
- The process quote-validation investigation is R0 and blocks additional pass-2 reader release.
- Semantic keys shortlist but never automatically merge or deduplicate.
- Migrations are additive; legacy process tables survive until R10.
- Process shadow merge must pass before transactional apply.

### 17.2 Business approvals to confirm before their consuming stage

1. **Narrative macro lane:** recommended approval — allow at most five significant
   goal/constraint/risk/rationale/open-question elements per narrative segment.
2. **Provisional employee answers:** recommended approval — allow clearly labeled provisional
   elements only when they still have valid evidence and the response explains uncertainty.
3. **Shadow backlog R2–R5:** recommended approval — permit read-only proposals to accumulate
   before the complete R6 review UI; no structural writes occur.
4. **Responsibilities first:** recommended approval — lowest-risk vertical slice for proving
   merge identity and reuse.
5. **Backfill priority:** decide at R9 from the dry-run report, not now.

Decisions 1, 3, and 4 must be recorded before R2 begins because R1 creates their storage/flags and
R2/R3 consume them. Decision 2 must be recorded before R6 review behavior is finalized, not deferred
until R7 UI work.

---

## 18. Immediate next action

R0 is complete as of 2026-07-22. Both release gates and the complete production result are recorded
in `evals/shape-aware-stage2.md`: fresh-database CI is green, migration 94 and worker version
`20260722.1` are deployed, and forced `business-process.md` run
`run_06fof96hugnkrumk86vi8f0d01` achieved a 3.6% whole-map drop ratio and 95.2% important-relation
evidence coverage without weakening document quote validation.

Begin R1 with its mandatory read-only production-data audit: count the existing macro/process
tables, inspect inbound FKs and RLS/policies, record manual/test-row disposition, run migration
drift/journal checks, and reconcile the generated Drizzle snapshot with the hand-written SQL target.
Record that audit before authoring any R1 DDL. Do not begin the R2 responsibilities reader until the
R1 durable cross-shape contract and all R1 exit gates are complete.

---

## 19. Plan maintenance

- Update this file after every stage gate, architectural decision, or approved deviation.
- Append empirical run results to the eval logs; do not turn this plan into a raw run diary.
- Keep `HANDOFF.md` focused on exact unfinished state and continuation instructions.
- Record durable architectural decisions in `DECISIONS.md` once implemented/approved.
- Update `AGENTS.md` routing whenever this file, a stage, or its source-of-truth files change.
- A deviation that changes evidence, identity, transaction, serving authority, or stage order
  requires explicit rationale and an updated rollback/gate here before implementation proceeds.

---

## 20. Independent review record

- **Kimi K3, 2026-07-21:** reviewed the repository and original plans, debated the architecture
  with Codex through three rounds, and agreed on the cross-shape spine, typed family details,
  validation-first sequence, four identity roles, and vertical slices. After its billing-cycle
  quota reset, it reconciled all ten Claude corrections against the code: nine were accepted as
  written and the duplicate-`86_*` repair was moved from R1 to R0 because it can block any fresh
  migration before R1. It also clarified the expected-zero R1 compatibility backfill and required
  a dedicated proposed-slug column. Its final verdict was implementation-ready at R0.
- **Claude Opus, 2026-07-21:** completed an authenticated, read-only adversarial repository review
  of the revised plan. Verdict: proceed after mandatory edits, not redesign or reject. Its required
  findings—object-generalizing existing proposal/recommendation tables, deterministic
  create-versus-existing guard, relation-evidence semantics, classify-first R0 gate, explicit new
  apply work, no R1 process-content copy, coverage-gap isolation, duplicate-86 disposition,
  effective provisional state, and map-less candidate identity—are incorporated here.
