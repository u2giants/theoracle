# Macro Understanding Implementation Plan

Status: planning document. No implementation has landed yet.

## Executive Summary

The current Oracle extraction pipeline is evidence-safe but context-myopic. It
promotes atomic claims only after deterministic quote validation, which is the
right foundation for trust. The weakness is that the system often asks each
model call to reason from a bounded local window:

- Document ingestion parses a source, chunks it into `document_chunks`, then
  runs extraction over one or more 24k-character document windows.
- Message extraction groups pending same-channel messages into 60-minute
  conversation segments, with prior messages passed only as non-quotable
  carry-in.
- Brain synthesis later sees approved claims, but only the claims that already
  survived local extraction.

This creates "contextual myopia": the system can prove local fragments while
missing source-level purpose, process sequence, pronoun/acronym resolution,
cross-chunk relationships, long-running chat threads, and coverage gaps.

The target architecture is macro-first and macro-throughout:

```text
Source
  -> source outline / macro map
  -> meaning-based source groups
  -> lens-guided atomic extraction using macro context
  -> deterministic validation and promotion
  -> relationship pass over validated claims
  -> coverage and contradiction audit
  -> synthesis over claims plus approved macro relationships
```

The central rule is strict: first-pass macro output is guidance, not evidence.
It can help local extraction interpret the source, but it must not become
approved knowledge by itself. Durable macro knowledge must be created only after
the system can cite either quote-validated atomic claims or explicitly validated
source spans.

## Goals

1. Preserve The Oracle's trust contract: every important answer or Brain
   artifact remains traceable to messages, document chunks, or approved claims.
2. Give extraction windows source-level context before they extract atomic
   claims.
3. Add a bounded, auditable macro-claim class whose evidence is a set of
   approved or pending-review atomic claims.
4. Detect when local extraction missed important parts of the source.
5. Improve Brain synthesis so it receives process-aware clusters and macro
   relationships instead of a flat top-200 claim list.
6. Make the new behavior observable and reviewable in admin screens.

## Non-Goals

1. Do not bypass deterministic quote validation for ordinary atomic claims.
2. Do not let an LLM-generated source outline directly write approved claims.
3. Do not remove the existing candidate-before-claim staging pipeline.
4. Do not create a second, competing claim retrieval path.
5. Do not require a new infrastructure service. State stays in Postgres;
   workers stay in Trigger.dev; web stays in Vercel.

## Current-State Constraints

Relevant current surfaces:

- `apps/workers/src/trigger/document-ingestion.ts`
  - parses documents and images
  - runs image vision transcription before extraction
  - persists `document_chunks`
  - builds extraction windows with `buildDocumentChunkWindows`
  - validates document quotes against one chunk
- `apps/workers/src/trigger/claim-extraction.ts`
  - selects pending message segments via `selectPendingConversations`
  - passes carry-in context as non-quotable context
  - runs the candidate-before-claim pipeline
- `packages/ai/src/prompts/extraction-system.ts`
  - strongly favors small, reviewable operational claims
  - requires one source ID and one exact quote per extracted claim
- `packages/oracle-engines/src/extraction/promote-candidate.ts`
  - rejects candidates with no validated evidence
  - inserts permanent `claims`, `claim_top_domains`, `claim_evidence`,
    `claim_entities`, and `claim_metadata`
- `apps/workers/src/trigger/brain-synthesis.ts`
  - reads approved claims by domain
  - hard-limits the main domain read to 200 claims
  - validates generated Brain text against approved claim IDs and the entity
    registry

The first implementation should respect these boundaries rather than replacing
them wholesale.

## Target Concepts

### Source Outline

A source outline is a provisional macro reading of a source. It answers:

- What is this source?
- What business process or situation is it about?
- Which departments, roles, systems, customers, licensors, factories, and
  geographies appear?
- Which acronyms, pronouns, aliases, or shorthand terms need resolution?
- What stages, branches, handoffs, exceptions, or open issues are visible?
- Which source chunks or messages seem to belong together conceptually?
- Which extraction lenses should run against this source?

It is guidance, not truth. It is allowed to be wrong. Downstream validators must
not treat it as evidence.

### Source Group

A source group is a meaning-based subset of source material. Examples:

- chunks that describe the same workflow stage
- transcript messages that are part of the same incident even if hours apart
- all chunks about a specific exception branch
- all messages naming a particular customer, factory, or system

Source groups are used to build better extraction inputs than arbitrary windows.

### Atomic Claim

An atomic claim is the existing claim shape: a concrete operational statement
with one or more quote-validated evidence rows. Round 1 can keep one evidence
row per candidate. Future rounds can allow multiple direct quote evidence rows
per atomic claim when the summary explicitly combines multiple quoted facts.

### Macro Relationship

A macro relationship is source-level knowledge inferred from already validated
atomic claims. It should be represented as either:

- a new `macro_relationships` table, or
- a controlled claim subtype with claim-to-claim evidence.

Recommended: use a dedicated table first, then optionally promote selected
relationships into `claims` after the review flow is proven.

Examples:

- "Licensor approval gates the handoff from Design to the China factory lane."
- "The failed-QA branch loops back to sample revision before customer update."
- "The morning delay discussion and afternoon resolution refer to the same
  packaging-artwork blocker."

Evidence is a list of validated claim IDs, not a free-form quote.

### Coverage Finding

A coverage finding says the source outline expected something that the extracted
claims did not cover. It should usually create a gap, not a claim.

Examples:

- "The outline identifies a QA-fail branch, but no claim captures who owns it."
- "The source defines three approval stages; only stage 1 and stage 3 produced
  claims."
- "Pronoun 'them' appears to refer to the offshore team, but no claim captured
  that definition."

## Data Model Plan

### Phase 1 Tables

Add hand-written SQL migrations and Drizzle schema for these tables.

#### `source_outlines`

Purpose: durable, provisional macro context for a document or conversation
episode.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_type varchar(50) not null`
  - `document`
  - `channel_thread`
  - `meeting_transcript`
- `document_id uuid references documents(id)`
- `channel_id uuid references channels(id)`
- `meeting_transcript_id uuid`
- `status varchar(50) not null default 'provisional'`
  - `provisional`
  - `superseded`
  - `failed`
- `outline_version varchar(50) not null`
- `model_run_id uuid references model_runs(id)`
- `context_pack_id uuid references oracle_context_packs(id)`
- `source_hash varchar(64) not null`
- `outline_json jsonb not null`
- `summary text`
- `created_at timestamptz default now() not null`
- `updated_at timestamptz default now() not null`

Indexes:

- `(source_type, document_id, created_at desc)`
- `(source_type, channel_id, created_at desc)`
- unique partial latest index is optional; simpler first version can query newest
  non-failed row by `(source_type, source_id, created_at desc)`.

#### `source_outline_source_refs`

Purpose: map outline elements to raw source rows so the outline is inspectable.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_outline_id uuid references source_outlines(id) on delete cascade`
- `ref_type varchar(50) not null`
  - `document_chunk`
  - `message`
  - `claim`
- `document_chunk_id uuid references document_chunks(id)`
- `message_id uuid references messages(id)`
- `claim_id uuid references claims(id)`
- `ref_role varchar(50)`
  - `defines_term`
  - `stage_evidence`
  - `handoff_evidence`
  - `exception_evidence`
  - `open_question_evidence`
- `metadata_json jsonb`

Indexes:

- `(source_outline_id)`
- `(document_chunk_id)`
- `(message_id)`
- `(claim_id)`

#### `source_groups`

Purpose: meaning-based extraction units produced by the outline pass.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_outline_id uuid references source_outlines(id) on delete cascade`
- `group_type varchar(50) not null`
  - `workflow_stage`
  - `handoff`
  - `exception_branch`
  - `incident_thread`
  - `entity_context`
  - `open_question`
- `title text not null`
- `description text`
- `sort_order integer`
- `metadata_json jsonb`

#### `source_group_items`

Purpose: ordered membership of chunks/messages in a source group.

Suggested columns:

- `source_group_id uuid references source_groups(id) on delete cascade`
- `item_type varchar(50) not null`
- `document_chunk_id uuid references document_chunks(id)`
- `message_id uuid references messages(id)`
- `sort_order integer not null default 0`
- primary key can be `(source_group_id, item_type, document_chunk_id,
  message_id)` if implemented carefully; a surrogate `id` is simpler.

#### `macro_relationships`

Purpose: durable source-level relationships inferred from validated claims.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `relationship_type varchar(100) not null`
  - `dependency`
  - `handoff`
  - `sequence`
  - `exception_path`
  - `contradiction_or_tension`
  - `definition_resolution`
  - `coverage_gap`
- `summary text not null`
- `status varchar(50) not null default 'pending_review'`
  - `pending_review`
  - `approved`
  - `rejected`
  - `superseded`
- `source_outline_id uuid references source_outlines(id)`
- `document_id uuid references documents(id)`
- `channel_id uuid references channels(id)`
- `confidence_score integer not null`
- `impact_score integer not null`
- `metadata_json jsonb`
- `model_run_id uuid references model_runs(id)`
- `context_pack_id uuid references oracle_context_packs(id)`
- `created_at timestamptz default now() not null`
- `updated_at timestamptz default now() not null`

Indexes:

- `(status, created_at desc)`
- `(document_id)`
- `(channel_id)`
- `(relationship_type)`

#### `macro_relationship_claims`

Purpose: claim-level evidence for macro relationships.

Suggested columns:

- `macro_relationship_id uuid references macro_relationships(id) on delete cascade`
- `claim_id uuid references claims(id) on delete restrict`
- `support_role varchar(50) not null`
  - `premise`
  - `enables`
  - `blocks`
  - `contrasts`
  - `defines`
  - `resolves`
- `sort_order integer not null default 0`
- `created_at timestamptz default now() not null`
- primary key `(macro_relationship_id, claim_id, support_role)`

Validator rule: every linked claim must have `status in ('approved',
'pending_review')` when the relationship is created, and only `approved` linked
claims can support an `approved` macro relationship.

#### `source_coverage_findings`

Purpose: reviewable audit of missed macro coverage.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_outline_id uuid references source_outlines(id)`
- `document_id uuid references documents(id)`
- `channel_id uuid references channels(id)`
- `finding_type varchar(100) not null`
  - `missing_stage`
  - `missing_owner`
  - `missing_branch`
  - `unresolved_reference`
  - `unrepresented_exception`
  - `low_claim_density`
  - `conflict_without_contradiction`
- `summary text not null`
- `suggested_question text`
- `related_claim_ids jsonb not null default '[]'::jsonb`
- `related_source_refs jsonb not null default '[]'::jsonb`
- `status varchar(50) not null default 'open'`
  - `open`
  - `converted_to_gap`
  - `dismissed`
  - `resolved`
- `created_gap_id uuid references gaps(id)`
- `created_at timestamptz default now() not null`

### Phase 2 Schema Extensions

After the separate macro table proves useful, decide whether to add
claim-to-claim evidence to the permanent claim model:

- add `sourceType='claim'` to the evidence source enum, or replace the enum with
  a varchar plus CHECK
- add nullable `source_claim_id` to `claim_evidence` and
  `extraction_candidate_evidence`
- allow a candidate evidence row to validate by checking referenced claim IDs,
  not quote text

Do this only after documenting a new decision in `DECISIONS.md`.

Recommended decision name:

`D-macro-relationship-evidence`

Decision boundary:

- Atomic claims still need direct source quotes.
- Macro relationships may cite approved claim IDs as evidence.
- A macro relationship is never evidence for another macro relationship in
  round 1. This prevents unsupported inference chains.

## Prompt and Output Schemas

Create new prompt/schema files under `packages/ai/src/prompts/`:

- `source-outline.ts`
- `macro-relationship.ts`
- `coverage-audit.ts`

### Source Outline Schema

Core fields:

- `sourceSummary`
- `sourceKind`
- `businessPurpose`
- `primaryDomains`
- `actors`
- `systems`
- `customers`
- `licensors`
- `geographies`
- `terms`
  - `term`
  - `meaning`
  - `sourceRefs`
- `processStages`
  - `stageId`
  - `title`
  - `ownerRoleOrDepartment`
  - `inputs`
  - `actions`
  - `outputs`
  - `nextStageIds`
  - `sourceRefs`
- `handoffs`
  - `from`
  - `to`
  - `artifactOrDecision`
  - `condition`
  - `sourceRefs`
- `exceptions`
- `openQuestions`
- `recommendedExtractionLenses`
- `sourceGroups`
  - `groupType`
  - `title`
  - `sourceRefs`
  - `whyGrouped`

Important prompt rule:

The outline must say "unknown" when a source does not define a term or owner.
It must not invent missing process steps.

### Lens Extraction

Keep the existing extraction output schema for atomic claims in round 1, but add
a preface block that includes the source outline and the active lens.

Suggested lenses:

- `handoffs`
- `exceptions_and_workarounds`
- `ownership_and_roles`
- `dependencies_and_sequence`
- `systems_and_data_entry`
- `contradictions_and_tensions`
- `definitions_and_acronyms`
- `customer_or_licensor_risk`

Implementation rule:

Each lens pass still emits ordinary atomic candidates with direct exact quotes.
If the active window does not support a claim with one direct quote, the model
should emit a gap or leave it to the relationship pass.

### Macro Relationship Schema

Core fields:

- `relationshipType`
- `summary`
- `supportingClaimIds`
- `supportRoles`
- `whyThisIsMacro`
- `sourceOutlineElementIds`
- `impactScore`
- `confidenceScore`
- `reviewReason`
- `riskFlags`

Hard validation:

- `supportingClaimIds.length >= 2` for most relationship types.
- Every supporting claim ID must be from the supplied list.
- Approved macro relationships require all support claims to be approved.
- The summary may not introduce named entities absent from support claim
  summaries or the canonical entity registry.

### Coverage Audit Schema

Core fields:

- `findingType`
- `summary`
- `sourceOutlineElementId`
- `relatedSourceRefs`
- `relatedClaimIds`
- `suggestedQuestion`
- `severity`
- `recommendedAction`
  - `create_gap`
  - `rerun_lens`
  - `manual_review`
  - `ignore`

## Worker Plan

### New Worker: `source-outline`

Location:

`apps/workers/src/trigger/source-outline.ts`

Inputs:

- `{ documentId }`
- later: `{ channelId, before?, after? }`
- later: `{ meetingTranscriptId }`

Document flow:

1. Load `documents` row.
2. Load all `document_chunks` for the document, ordered by `chunk_index`.
3. Build a full-source prompt. If the source is too large, use the provider
   cache/file-backed path where available; otherwise run a map-reduce outline:
   per-window mini outlines followed by a merge outline.
4. Compile through `OracleAIClient` using the `general` auxiliary route first.
   Do not overload the extraction route with outline work.
5. Insert `oracle_context_packs`, `model_runs`, `model_run_usage_details`, and
   `model_run_attempts`.
6. Insert `source_outlines`, `source_outline_source_refs`, `source_groups`, and
   `source_group_items`.
7. Mark stale prior outlines for the same source as `superseded` if their
   `source_hash` differs.

Why use `general`:

The outline is reading and organizing, not enforcing extraction JSON. Keeping it
as an auxiliary route allows admins to select a strong long-context model
without changing extraction pools.

### Modify Worker: `document-ingestion`

Current order:

```text
parse
  -> chunk
  -> embed
  -> extract windows
  -> validate/promote
```

New order:

```text
parse
  -> chunk
  -> embed
  -> source outline
  -> source groups
  -> lens-guided extraction over groups/windows
  -> validate/promote
  -> macro relationship pass
  -> coverage audit
```

Implementation details:

1. After chunk insertion, call an internal `ensureSourceOutlineForDocument()`.
2. Include the latest non-failed outline as a `semi_stable_domain_context`
   prompt block in each extraction plan.
3. Replace or augment `buildDocumentChunkWindows()` with
   `buildDocumentExtractionUnits()`:
   - prefer `source_groups`
   - preserve the max prompt budget
   - include adjacent chunk context as non-evidentiary context when needed
   - ensure the active evidence chunks are clearly labeled and citeable
4. Add lens scheduling:
   - round 1: one normal extraction pass plus targeted `handoffs` and
     `exceptions_and_workarounds`
   - round 2: add more lenses behind settings
5. Keep quote validation unchanged for atomic claims.
6. After all atomic candidates are processed, trigger
   `macro-relationship-extraction` and `source-coverage-audit` for the
   document.

Idempotency:

- Use `source_hash` over full normalized source text plus outline prompt version.
- Use `extraction_batches.batchType` values such as:
  - `document_source_group`
  - `document_lens_group`
- Do not reprocess groups whose `(source_group_id, lens, source_hash,
  prompt_version)` already completed unless admin requests reevaluation.

### New Worker: `macro-relationship-extraction`

Location:

`apps/workers/src/trigger/macro-relationship-extraction.ts`

Inputs:

- `{ documentId }`
- `{ channelId, sourceOutlineId }`
- optional `{ sourceOutlineId }`

Flow:

1. Load the latest source outline.
2. Load claims created from this source:
   - document: `claim_evidence -> document_chunks -> documents`
   - chat: `claim_evidence -> messages -> channel_id`
3. Prefer `status in ('approved', 'pending_review')`.
4. Group by source group, process stage, domain, entity, and claim type.
5. Run `OracleAIClient.runObject` with the macro relationship schema.
6. Validate:
   - all support claim IDs exist
   - support claims belong to the source or allowed adjacent thread context
   - no support claim is rejected or superseded
   - if relationship status is `approved`, all support claims must be approved
   - summary named entities are backed by support claims or entity registry
7. Insert `macro_relationships` as `pending_review`.
8. Insert `macro_relationship_claims`.
9. Optionally auto-approve low-risk relationships only after there is admin
   review experience. Round 1 should not auto-approve.

### New Worker: `source-coverage-audit`

Location:

`apps/workers/src/trigger/source-coverage-audit.ts`

Inputs:

- `{ documentId }`
- `{ sourceOutlineId }`

Flow:

1. Load outline.
2. Load extracted atomic claims and macro relationships for the source.
3. Ask the model what outline elements are not represented.
4. Validate output references:
   - outline element IDs must exist
   - claim IDs must exist
   - source refs must belong to the source
5. Insert `source_coverage_findings`.
6. For `recommendedAction='create_gap'`, create `gaps` rows with a new
   `gap_type` such as `source_coverage_gap`, or reuse an existing operational
   gap type if it fits.

### Modify Worker: `claim-extraction`

Round 1 for chat:

1. Keep current 60-minute segments for atomic extraction.
2. Add `thread_state_summary` as a source outline variant for channel threads.
3. After each segment, update the latest channel outline with:
   - active entities
   - unresolved references
   - open operational problems
   - recent decisions
   - possible continuation markers
4. Pass the latest outline into future segment extraction as
   `semi_stable_domain_context`.
5. Do not let prior outline content be quoted or claimed directly.

Round 2 for chat:

1. Build long-running incident threads by clustering messages across time using:
   - same channel
   - shared entities
   - shared customer/licensor/system
   - reply metadata if available
   - semantic similarity over message embeddings if later added
2. Run macro relationship extraction over completed incident threads.

### Modify Worker: `brain-synthesis`

Round 1:

1. Load approved macro relationships relevant to the section's top domains.
2. Include them in the synthesis corpus after atomic claims:

```text
APPROVED MACRO RELATIONSHIPS:
- ID: ...
  Type: dependency
  Relationship: ...
  Supporting claims: ...
```

3. Extend synthesis validation so a paragraph may cite:
   - approved claim IDs, and/or
   - approved macro relationship IDs
4. Require macro relationship IDs to resolve to approved rows.
5. The validator should still inspect the underlying support claim summaries for
   named-entity backing.

Round 2:

1. Replace the flat top-200 read with staged subtopic/cluster batches:
   - high-impact claims
   - recently changed claims
   - approved macro relationships
   - taxonomy subtopics
   - explicit section bindings
2. Generate or refresh one subsection at a time.
3. Preserve existing rejected-version behavior on validation failure.

## Admin UI Plan

### Admin Documents

Enhance `apps/web/app/admin/documents`:

- show source outline status
- show model used for outline
- show outline summary
- show process stages and source groups
- add actions:
  - "Generate outline"
  - "Regenerate outline"
  - "Run macro relationship pass"
  - "Run coverage audit"
  - "Reevaluate document with macro context"

### Admin Claims

Round 1:

- show whether a claim was extracted with a source outline
- show source group/lens metadata if available

Round 2:

- add filter by source group, lens, or process stage
- show related macro relationships for each claim

### New Admin Page: Macro Review

Path:

`apps/web/app/admin/macro-relationships`

Features:

- pending review queue
- relationship summary
- source outline summary
- supporting claim cards with evidence quotes
- approve/reject/revise
- convert to gap
- links back to document/chunks/messages

Actions:

- approve macro relationship
- reject macro relationship
- revise summary
- create gap from relationship/finding

Audit:

- add `macro_relationship_review_events`, or use a generic review event table.
  Prefer a dedicated table if the UI needs before/after snapshots similar to
  `claim_review_events`.

### Admin Gaps

Show coverage findings that created gaps and link back to source outline.

## Retrieval and Chat Plan

Round 1:

- Do not change `searchWithRetrievalPlan`.
- Chat still retrieves approved atomic claims.
- Brain snippets remain as today.

Round 2:

- Add macro relationships to retrieval context as a separate retrieved block,
  not mixed into atomic claim RRF at first.
- Search macro relationships by:
  - embedded summary
  - linked support claim domains/entities
  - relationship type
- Include only approved macro relationships.
- In chat prompt, label them distinctly:

```text
APPROVED PROCESS RELATIONSHIPS
These are higher-level relationships supported by approved claim IDs.
```

This avoids contaminating the single endorsed claim retrieval path while adding
a second, explicitly typed retrieval stream.

## Validation Plan

### Atomic Claims

No weakening:

- source pointer must exist
- quote must validate against one active source message or one document chunk
- taxonomy must validate
- sensitivity gate still runs
- promotion still goes through `executePromotion`

### Source Outlines

Validation should check structure only:

- JSON schema valid
- source refs exist and belong to the source
- no invented chunk/message IDs
- maximum sizes respected

Outlines are allowed to contain uncertain language.

### Macro Relationships

Validation should check:

- all supporting claim IDs exist
- support claims are not rejected or superseded
- source scoping is correct
- relationship summary does not introduce unsupported named entities
- if status is `approved`, every support claim is approved
- no recursive support from another macro relationship in round 1
- no relationship with fewer than two support claims unless type is
  `definition_resolution` and it has a clear source outline ref

### Coverage Findings

Validation should check:

- referenced outline element exists
- source refs belong to the source
- suggested gap text is actionable
- finding does not assert a new operational fact as true

## Settings Plan

Add settings:

- `enable_source_outline_pass`
- `enable_macro_relationship_pass`
- `enable_source_coverage_audit`
- `macro_outline_max_chars`
- `macro_relationship_max_support_claims`
- `macro_lenses_enabled`
- `default_macro_route`

`default_macro_route` should be implemented as a new auxiliary model:

- add to `packages/ai/src/routes/auxiliary.ts`
- expose in Admin Settings
- seed with `ON CONFLICT DO NOTHING`

Alternative:

- reuse `default_general_purpose_route` initially.

Recommendation:

- Start by reusing `general` to keep migration small.
- Add `macro` auxiliary slot only if outline/relationship calls need different
  model economics than taxonomy naming and other general work.

## Observability Plan

Every new model call must write:

- `oracle_context_packs`
- `model_runs`
- `model_run_usage_details`
- `model_run_attempts`

Use task types:

- `source_outline`
- `macro_relationship_extraction`
- `source_coverage_audit`

Context pack observability:

- `includedDocumentChunkIds`
- `includedMessageIds`
- `includedClaimIds`
- `selectedDomains`
- source outline ID in `blocksJson` metadata or a future
  `includedSourceOutlineIds` field

Admin run summaries should show:

- outline generated or skipped
- groups created
- extraction units run
- candidates staged
- claims promoted
- macro relationships proposed
- coverage findings created
- failures by validation check

## Migration and Backfill Plan

### Migration 1

Add source outline tables and macro relationship tables.

Files:

- `packages/db/src/schema.ts`
- `packages/db/migrations/sql/79_macro_understanding.sql`

If generated Drizzle migration is desired later, keep the hand-written SQL
idempotent and reconcile drift intentionally.

### Migration 2

Add optional metadata fields to existing tables:

- `extraction_batches.batch_type` values are varchar already, so no schema
  change needed for new batch types.
- `documents` can remain unchanged if outlines live in `source_outlines`.
  Avoid adding `documents.global_context_json` because it will become cramped
  and hides version history.

### Backfill

1. Generate source outlines for the most important existing documents first.
2. Run macro relationship extraction on documents with:
   - many approved claims
   - known workflow/process content
   - known diagram/image ingestion issues
3. Do not backfill every document immediately. Cost and reviewer load will be
   high.

Backfill script:

- `scripts/backfill-source-outlines.mjs`
- dry-run by default
- filters by document ID, status, created date, minimum approved claims
- triggers tasks rather than doing provider work inline

## Implementation Phases

### Phase 0: Decision and Guardrails

Deliverables:

- add `DECISIONS.md` entry for macro understanding
- confirm evidence rule:
  - source outlines are guidance
  - atomic claims require direct quotes
  - macro relationships cite validated claim IDs
- add this plan to docs map

Acceptance criteria:

- future sessions can name the provenance boundary in one paragraph
- no code change yet mutates production behavior

### Phase 1: Source Outline Storage and Worker

Deliverables:

- schema and migration for `source_outlines`, refs, groups, group items
- `packages/ai/src/prompts/source-outline.ts`
- `apps/workers/src/trigger/source-outline.ts`
- admin action to generate outline for a document
- context pack/model run logging

Acceptance criteria:

- a document can produce one source outline
- outline source refs all validate against existing chunks
- admin can inspect the outline
- no claims are created by this pass

Suggested tests:

- schema typecheck
- prompt schema parse smoke
- source ref validator smoke
- local fixture document outline smoke with mock adapter if available

### Phase 2: Inject Outline into Document Extraction

Deliverables:

- `ensureSourceOutlineForDocument()` in document ingestion
- extraction prompt includes outline as `semi_stable_domain_context`
- extraction batches record outline ID in context metadata
- feature flag `enable_source_outline_pass`

Acceptance criteria:

- document ingestion still succeeds when outline generation fails if feature is
  configured as non-blocking
- extracted claims still validate exact quotes
- context packs show the outline block
- disabling the feature returns to current behavior

Suggested tests:

- document ingestion typecheck
- a fixture where pronoun/acronym resolution improves
- quote validation regression: outline text cannot be cited as evidence

### Phase 3: Meaning-Based Source Groups and Lens Extraction

Deliverables:

- `buildDocumentExtractionUnits()` prefers source groups
- lens prompt addendum
- batch metadata includes lens and source group ID
- settings for enabled lenses

Acceptance criteria:

- the system can run handoff and exception lens passes
- every lens output still enters the same candidate validation path
- duplicate detection prevents obvious repeated claims across lenses

Suggested tests:

- fixture with handoff hidden across sections
- fixture with exception branch in later chunk
- duplicate candidate hash regression

### Phase 4: Macro Relationship Extraction

Deliverables:

- schema for `macro_relationships` and `macro_relationship_claims`
- prompt/schema for macro relationships
- worker
- validators
- admin review page

Acceptance criteria:

- model can propose relationships over validated document claims
- invalid claim IDs are rejected
- rejected/superseded support claims are rejected
- pending macro relationships are visible in admin
- approving a macro relationship requires all support claims to be approved

Suggested tests:

- validator unit tests
- macro relationship prompt schema smoke
- admin action typecheck
- fixture where two atomic claims produce one dependency relationship

### Phase 5: Coverage Audit and Gap Creation

Deliverables:

- `source_coverage_findings`
- coverage audit prompt/schema
- worker
- admin document coverage tab
- optional gap creation action

Acceptance criteria:

- the system identifies at least one missing stage/owner in a fixture
- findings never become claims automatically
- created gaps link back to coverage finding/source outline

Suggested tests:

- fixture with outline stage not represented by claims
- validator rejects invented refs

### Phase 6: Chat Thread State

Deliverables:

- source outline support for channel threads
- rolling thread summary after message segment extraction
- injection into future message extraction
- feature flag

Acceptance criteria:

- follow-up segments receive prior thread state
- prior thread state cannot be cited as evidence
- no segment extraction is blocked by a failed summary update

Suggested tests:

- two-segment fixture where "them" resolves from earlier segment
- quote validation rejects thread summary text

### Phase 7: Brain Synthesis Integration

Deliverables:

- synthesis loads approved macro relationships
- synthesis corpus includes macro relationships and supporting claim IDs
- diff validator accepts approved macro relationship citations
- Brain section UI can display macro relationship citations

Acceptance criteria:

- Brain synthesis can cite macro relationship IDs
- unsupported macro IDs reject the synthesis
- named-entity validation still works through support claims
- sections with more than 200 claims are not silently limited to a flat top-200
  input in the final design

Suggested tests:

- synthesis validator test with macro relationship citation
- rejection test for unapproved relationship
- regression: atomic-claim-only synthesis still works

### Phase 8: Retrieval and Chat Use of Macro Relationships

Deliverables:

- macro relationship retrieval helper
- chat route includes approved macro relationship context in a separate block
- context packs record included macro IDs

Acceptance criteria:

- chat answers can use approved macro relationships
- answers cite or reference underlying approved claims where needed
- existing `searchWithRetrievalPlan` remains the endorsed atomic claim path

Suggested tests:

- retrieval helper unit smoke
- chat context pack smoke
- no macro relationship leakage when feature disabled

## Rollout Plan

1. Ship tables and source outline worker behind feature flags.
2. Generate outlines manually for 3 to 5 known workflow documents.
3. Compare extraction quality with and without outline injection.
4. Enable outline injection for admin document uploads only.
5. Add macro relationship proposals, review manually, no auto-approval.
6. Add coverage audit, create gaps manually at first.
7. Integrate approved macro relationships into synthesis.
8. Only after reviewer trust is established, consider limited auto-approval for
   low-risk macro relationships.

## Quality Metrics

Track before/after:

- claim acceptance rate
- quote validation failure rate
- rejected claim rate by reason
- number of handoff/dependency/exception claims per source
- reviewer revisions per 100 claims
- coverage findings per source
- macro relationships approved/rejected
- Brain synthesis validation failures
- admin-reported "missed big picture" incidents
- answer quality for broad process questions

Useful evaluation fixtures:

- a flowchart/diagram with branches
- a multi-page SOP with acronyms and pronouns
- a Teams transcript where problem and resolution are separated by hours
- a business-process document with cross-department handoffs
- a document where one section defines a term and later sections use shorthand

## Risks and Mitigations

Risk: first-pass outline pollutes atomic claims with unsupported assumptions.

Mitigation:

- label outline as context only
- prohibit outline source IDs as evidence
- keep exact quote validation unchanged
- add tests where model tries to quote outline text

Risk: macro relationships weaken provenance.

Mitigation:

- keep them in a separate table first
- require support claim IDs
- require support claims to be approved before macro approval
- document the exception in `DECISIONS.md`

Risk: cost and latency increase significantly.

Mitigation:

- feature flags
- manual admin triggers first
- use provider caching for long sources
- run lens passes selectively
- avoid immediate full backfill

Risk: reviewer UI becomes overwhelming.

Mitigation:

- start with documents page outline display
- separate macro review queue
- group by source and relationship type
- convert weak relationships into gaps instead of claims

Risk: synthesis trusts macro relationships too much.

Mitigation:

- synthesis validator resolves macro relationship support claims
- require paragraphs citing macro IDs to cite underlying claim IDs in structured
  output or store the expansion server-side
- keep rejection behavior unchanged

Risk: duplicate claims increase because lens passes overlap.

Mitigation:

- candidate hash dedup remains active
- lens metadata helps inspect overlap
- add per-source duplicate reports

## Open Questions

1. Should macro relationships be a separate first-class artifact permanently,
   or eventually become a claim type with claim-to-claim evidence?
2. Should source outlines be generated automatically for every upload, or only
   for documents above a size/complexity threshold?
3. Which model should own macro passes: `general`, `synthesis`, or a new
   `macro` auxiliary route?
4. Should pending-review atomic claims be allowed as support for pending macro
   relationships? Recommended: yes. For approved macro relationships:
   approved support only.
5. Should macro relationships be visible to employee chat before Brain
   synthesis uses them? Recommended: no until admin approval is established.
6. How should source groups interact with batch extraction mode?
7. Do we need embeddings for source outlines and macro relationships in round 1?
   Recommended: macro relationship embeddings yes before chat retrieval;
   source outline embeddings optional.

## First Slice Recommendation

The first shippable slice should be deliberately small:

1. Add `source_outlines`, `source_outline_source_refs`, `source_groups`, and
   `source_group_items`.
2. Add `source-outline` worker for documents only.
3. Add a manual "Generate outline" action on Admin Documents.
4. Show the outline in Admin Documents.
5. Inject the outline into document extraction behind
   `enable_source_outline_pass`.
6. Prove with one fixture that outline text cannot be cited as evidence and
   direct quote validation remains unchanged.

Then add macro relationships as the second slice.

This avoids changing the evidence model in the first release while still moving
the pipeline from bottom-up only to macro-first local extraction.
