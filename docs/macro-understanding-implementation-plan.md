# Macro Understanding Implementation Plan

Status: planning document. No implementation has landed yet.

## Executive Summary

The Oracle's current extraction pipeline is evidence-safe but context-myopic. It
does a strong job proving small facts with source quotes, but it often fails to
understand the larger source: workflow shape, long-running incidents,
cross-document policy-versus-practice tension, diagram structure, and coverage
gaps. This plan adds a macro understanding layer without weakening the trust
contract.

The target architecture is macro-first and macro-throughout:

```text
Source
  -> source outline / macro map
  -> meaning-based source groups
  -> budgeted lens-guided atomic extraction using macro context
  -> deterministic validation and promotion
  -> relationship pass over validated claims
  -> lifecycle watcher for stale support
  -> coverage and contradiction audit
  -> reviewer triage and measured evals
  -> Brain synthesis over claims plus approved macro relationships
```

The central rule:

First-pass macro output is guidance, not evidence. It can help local extraction
interpret the source, but it must not become approved knowledge by itself.
Durable macro knowledge must cite approved atomic claims or other explicitly
validated source spans. Round 1 macro relationships cite approved claim IDs, not
raw model interpretation.

## Why This Is Needed

Current behavior:

- Document ingestion chunks text and extracts from bounded windows.
- Message extraction splits conversations into time-bounded segments with
  limited carry-in context.
- Brain synthesis runs after claims are approved, so it only sees patterns that
  survived atomized extraction.

Failure modes:

- Page 1 defines "offshore team"; page 15 says "notify them"; local extraction
  misses the referent.
- A Teams incident starts in the morning and resolves in the afternoon; the
  60-minute segment boundary treats the resolution as an orphan fact.
- A diagram's edge or spatial layout is lost when the vision/text pass flattens
  the source.
- Lens fan-out can create many near-duplicate claims.
- A macro relationship can become stale when a supporting claim is later
  revised, superseded, or rejected.

This plan addresses those directly.

## Goals

1. Preserve The Oracle's traceability contract.
2. Give atomic extraction source-level context before it extracts claims.
3. Create a bounded macro relationship layer whose evidence is validated claim
   IDs.
4. Track macro relationship lifecycle when support claims are pending, approved,
   superseded, rejected, or revised.
5. Support cross-source relationships such as "SOP says X; Teams shows Y."
6. Add reviewer triage so the plan does not overwhelm the review queue.
7. Add semantic deduplication for lens fan-out.
8. Add hard model-call, token, and cost ceilings.
9. Use measured A/B evaluation instead of manual vibes.
10. Prepare Brain synthesis to consume approved macro relationships safely.

## Non-Negotiable Trust Requirements

These are not implementation preferences. They are the trust boundary for the
macro layer.

1. Macro relationship retrieval and Brain synthesis must verify support-claim
   approval at read time. They must not trust `macro_relationships.status`
   alone.
2. A watcher and staleness sweep are still required for admin visibility, but
   they are not the only guard against stale evidence.
3. `claim_kind` must be validated or treated as uncertain. A model-generated
   label cannot be used as high-trust policy/practice logic without confidence
   and review semantics.
4. Cross-source candidate selection must be ranked and bounded before the model
   sees it. "Same entity/domain/process stage" is a signal, not a complete
   retrieval plan.
5. New scheduled Trigger.dev tasks must not be added while the project is at
   the 10/10 schedule limit. New sweeps must run through an existing scheduled
   maintenance task, on-demand admin actions, or consolidated cron.
6. Any macro table exposed to browser or employee-facing paths must have an RLS
   story. Server-only service-role access is acceptable only when documented.
7. New vector indexes must follow the existing `ORACLE_RUN_VECTOR_INDEXES=1`
   convention instead of being created in the primary schema migration.

## Non-Goals

1. Do not bypass quote validation for atomic claims.
2. Do not let source outlines write approved claims.
3. Do not replace the candidate-before-claim pipeline.
4. Do not create a second contradiction queue that competes with the existing
   `contradictions` table.
5. Do not require new infrastructure beyond Postgres, Trigger.dev, Vercel, and
   existing providers.
6. Do not run expensive macro passes unbounded across the whole corpus.

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
  - favors small, reviewable operational claims
  - requires one source ID and one exact quote per extracted claim
- `packages/oracle-engines/src/extraction/promote-candidate.ts`
  - rejects candidates with no validated evidence
  - inserts permanent `claims`, `claim_top_domains`, `claim_evidence`,
    `claim_entities`, and `claim_metadata`
- `apps/workers/src/trigger/contradiction-watcher.ts`
  - already writes semantic contradictions to the `contradictions` table
- `apps/workers/src/trigger/brain-synthesis.ts`
  - reads approved claims by domain
  - hard-limits the main domain read to 200 claims
  - validates generated Brain text against approved claim IDs and the entity
    registry

Operational constraints from the repo:

- Trigger.dev is already at the schedule limit. Do not add standalone cron
  tasks for macro staleness, coverage, or cleanup unless a schedule slot is
  explicitly freed or an existing schedule is consolidated.
- RLS is a project principle. Tables that are read with the anon key need
  policies; tables read only through service-role server code need that boundary
  documented in `docs/architecture.md` and `AGENTS.md` if they become durable
  surfaces.
- Expensive vector indexes are gated elsewhere by `ORACLE_RUN_VECTOR_INDEXES`.
  Macro vector columns can be added in the main migration, but HNSW/IVFFlat
  index creation belongs in a gated vector-index migration.

Round 1 should extend these surfaces, not replace them.

## Target Concepts

### Source Outline

A source outline is a provisional macro reading of a source. It answers:

- What is this source?
- What business process or incident is it about?
- Which departments, roles, systems, customers, licensors, factories, and
  geographies appear?
- Which acronyms, pronouns, aliases, or shorthand terms need resolution?
- What stages, branches, handoffs, exceptions, observed practices, and open
  issues are visible?
- Which source chunks/messages belong together conceptually?
- Which extraction lenses should run?

The outline is guidance only. It is not evidence and cannot be quoted.

### Source Group

A source group is a meaning-based subset of source material. Examples:

- chunks that describe the same workflow stage
- transcript messages that are part of the same incident even if hours apart
- chunks about a specific exception branch
- all source rows about one customer, factory, system, or licensor

Source groups improve extraction inputs and reviewer organization.

### Extraction Lens

A lens is a targeted extraction pass. Examples:

- handoffs
- exceptions and workarounds
- ownership and roles
- dependencies and sequence
- systems and data entry
- definitions and acronyms
- customer or licensor risk
- contradictions and tensions

The source outline recommends lenses, but a deterministic budget gate decides
which lens tasks actually run.

### Atomic Claim

An atomic claim is the existing claim shape: a concrete operational statement
with direct quote-validated evidence. Round 1 keeps the current direct evidence
rules unchanged.

### Claim Kind

`claim_kind` is distinct from `claim_type`.

`claim_type` describes the shape of the fact:

- process_rule
- exception_rule
- dependency
- bottleneck
- workaround
- system_limitation
- handoff_gap
- contradiction
- process_ambiguity

`claim_kind` describes the source posture:

- `policy` - official documented rule or SOP
- `observed_practice` - what employees actually do or report doing
- `workaround` - a non-standard method used because the official path is
  insufficient
- `exception` - sanctioned deviation from the standard path
- `historical` - past behavior that may not be current
- `uncertain` - unresolved or contested statement

This vocabulary is essential for macro understanding. It lets the system
distinguish:

- policy versus observed practice
- exception versus contradiction
- workaround versus official process
- old process versus current process

Round 1 can store this in `claim_metadata.metadata_json` if available, but the
recommended durable implementation is:

- nullable `claims.claim_kind`
- nullable `claims.claim_kind_confidence integer`
- nullable `claims.claim_kind_review_status varchar(50)`
  - `model_labeled`
  - `reviewed`
  - `uncertain`

Rules:

- If the model is unsure, it must emit `uncertain`.
- Low-confidence `claim_kind` must not drive automatic policy-vs-practice
  macro relationships.
- Reviewer approve/revise flows must let reviewers correct `claim_kind`.
- Synthesis should prefer reviewed or high-confidence `policy` claims over
  conversational `observed_practice`, but must not treat an unreviewed
  low-confidence `policy` label as authoritative.

### Macro Relationship

A macro relationship is source-level or cross-source knowledge inferred from
validated atomic claims.

Examples:

- "Licensor approval gates the handoff from Design to the China factory lane."
- "The failed-QA branch loops back to sample revision before customer update."
- "The SOP says approvals should happen in Coldlion, but Teams discussions show
  designers still route some approvals through spreadsheets."

Evidence is a list of validated claim IDs, not a free-form quote. Round 1
stores macro relationships in a dedicated table. Later, selected relationship
types may become claim-like artifacts if review proves the lifecycle.

### Coverage Finding

A coverage finding says the source outline expected something that extracted
claims did not cover. It should usually create a gap, not a claim.

Examples:

- "The outline identifies a QA-fail branch, but no claim captures who owns it."
- "The source defines three approval stages; only stages 1 and 3 produced
  claims."
- "Pronoun 'them' appears to refer to the offshore team, but no claim captured
  that definition."

### Relationship Staleness

Macro relationships are only as strong as their support claims. If any support
claim changes status from `approved` to `rejected`, `superseded`, or otherwise
non-current, an approved macro relationship must become stale and leave the
trusted knowledge path until revalidated.

This is a hard provenance rule, not a nice-to-have.

## Data Model Plan

### Phase 1 Tables

Add Drizzle schema entries and hand-written SQL migration:

`packages/db/migrations/sql/79_macro_understanding.sql`

#### `source_outlines`

Purpose: durable, provisional macro context for a source.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_type varchar(50) not null`
  - `document`
  - `channel_thread`
  - `meeting_transcript`
  - `cross_source_set`
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
- `budget_json jsonb`
- `created_at timestamptz default now() not null`
- `updated_at timestamptz default now() not null`

Do not put `document_id` or `channel_id` directly on this table as the only
lineage. Use `source_outline_sources` so the same outline can represent one
document, one channel thread, one meeting, or a cross-source set.

#### `source_outline_sources`

Purpose: source-level lineage for outlines.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_outline_id uuid references source_outlines(id) on delete cascade`
- `source_type varchar(50) not null`
  - `document`
  - `channel`
  - `meeting_transcript`
  - `message_range`
  - `manual_collection`
- `document_id uuid references documents(id)`
- `channel_id uuid references channels(id)`
- `meeting_transcript_id uuid`
- `start_message_id uuid references messages(id)`
- `end_message_id uuid references messages(id)`
- `source_hash varchar(64)`
- `metadata_json jsonb`

Indexes:

- `(source_outline_id)`
- `(document_id)`
- `(channel_id)`

#### `source_outline_source_refs`

Purpose: map outline elements to raw source rows so the outline is inspectable.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_outline_id uuid references source_outlines(id) on delete cascade`
- `outline_element_id varchar(100)`
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
- `embedding vector(1536)`
- `sort_order integer`
- `metadata_json jsonb`

The optional embedding supports semantic deduplication and chat incident
stitching.

#### `source_group_items`

Purpose: ordered membership of chunks/messages in a source group.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_group_id uuid references source_groups(id) on delete cascade`
- `item_type varchar(50) not null`
  - `document_chunk`
  - `message`
- `document_chunk_id uuid references document_chunks(id)`
- `message_id uuid references messages(id)`
- `sort_order integer not null default 0`
- `metadata_json jsonb`

#### `macro_relationships`

Purpose: durable relationships inferred from validated claims.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `relationship_type varchar(100) not null`
  - `dependency`
  - `handoff`
  - `sequence`
  - `exception_path`
  - `policy_vs_practice_tension`
  - `workaround_to_system_limitation`
  - `definition_resolution`
  - `coverage_gap`
- `summary text not null`
- `status varchar(50) not null default 'pending_review'`
  - `pending_review`
  - `blocked_pending_support`
  - `approved`
  - `needs_review`
  - `stale_support`
  - `rejected`
  - `superseded`
- `staleness_reason text`
- `stale_since timestamptz`
- `source_outline_id uuid references source_outlines(id)`
- `confidence_score integer not null`
- `impact_score integer not null`
- `triage_score numeric`
- `embedding vector(1536)`
- `metadata_json jsonb`
- `model_run_id uuid references model_runs(id)`
- `context_pack_id uuid references oracle_context_packs(id)`
- `created_at timestamptz default now() not null`
- `updated_at timestamptz default now() not null`

Do not make `document_id` or `channel_id` the primary lineage. Relationships can
be single-source or cross-source. Source lineage comes from support claims and
`macro_relationship_sources`.

Read-time trust note:

`status='approved'` is an admin workflow state, not sufficient evidence for
trusted serving. Any query that serves macro relationships to Brain, chat, MCP,
or synthesis must also prove every support claim is currently approved.

#### `macro_relationship_sources`

Purpose: explicit cross-source lineage for macro relationships.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `macro_relationship_id uuid references macro_relationships(id) on delete cascade`
- `source_type varchar(50) not null`
- `document_id uuid references documents(id)`
- `channel_id uuid references channels(id)`
- `meeting_transcript_id uuid`
- `metadata_json jsonb`

This table lets a relationship connect Document X and Channel Y without forcing
array columns into `macro_relationships`.

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
  - `policy_anchor`
  - `practice_anchor`
  - `workaround_anchor`
- `claim_status_at_link varchar(50) not null`
- `claim_version_hash varchar(64)`
- `sort_order integer not null default 0`
- `created_at timestamptz default now() not null`
- primary key `(macro_relationship_id, claim_id, support_role)`

Store `claim_status_at_link` so admin can see when a relationship was created
over pending support versus approved support.

#### `macro_relationship_review_events`

Purpose: append-only audit similar to `claim_review_events`.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `macro_relationship_id uuid references macro_relationships(id) on delete cascade`
- `action varchar(50) not null`
  - `approve`
  - `reject`
  - `revise`
  - `mark_stale`
  - `revalidate`
- `reviewed_by_employee_id uuid references employees(id)`
- `reviewer_note text`
- `before_state jsonb not null`
- `after_state jsonb`
- `created_at timestamptz default now() not null`

#### `source_coverage_findings`

Purpose: reviewable audit of missed macro coverage.

Suggested columns:

- `id uuid primary key default gen_random_uuid()`
- `source_outline_id uuid references source_outlines(id)`
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
- `severity integer not null default 5`
- `triage_score numeric`
- `status varchar(50) not null default 'open'`
  - `open`
  - `converted_to_gap`
  - `dismissed`
  - `resolved`
- `created_gap_id uuid references gaps(id)`
- `created_at timestamptz default now() not null`

### Existing Table Extensions

#### `claims.claim_kind`

Recommended durable extension:

- `claim_kind varchar(50)`
- `claim_kind_confidence integer`
- `claim_kind_review_status varchar(50)`

Allowed values:

- `policy`
- `observed_practice`
- `workaround`
- `exception`
- `historical`
- `uncertain`

Add a CHECK constraint in hand-written SQL. If a hard enum is preferred later,
do it in a generated migration after the values settle.

Validation/defaults:

- default `claim_kind` to `uncertain` when absent
- default `claim_kind_review_status` to `model_labeled` for model output
- set `claim_kind_review_status='reviewed'` during human approve/revise when
  the reviewer confirms or changes it
- macro logic that depends on policy/practice distinction must require either
  reviewed kind or confidence above a configured threshold

#### `extraction_batches`

No schema change required for new batch types because `batch_type` is already a
varchar. New values:

- `document_source_group`
- `document_lens_group`
- `source_outline`
- `macro_relationship`
- `coverage_audit`

#### `provider_cached_content`

No schema change required for round 1 if existing lifecycle fields are enough.
If not enough, add:

- `consumer_task_type varchar(100)`
- `consumer_source_id uuid`
- `expected_terminal_signal varchar(100)`

The cleanup worker can still use existing `cleanup_owner`, `status`,
`hard_expiration_at`, and provider metadata.

## Lifecycle Rules

### Macro Relationship State Machine

```text
pending_review
  -> blocked_pending_support
  -> pending_review
  -> approved
  -> needs_review
  -> approved

approved
  -> stale_support
  -> needs_review
  -> approved

pending_review / blocked_pending_support / needs_review
  -> rejected

approved / rejected
  -> superseded
```

Rules:

1. A macro relationship can be created from `pending_review` or `approved`
   support claims.
2. If any support claim is `pending_review`, the macro relationship status is
   `blocked_pending_support` unless manually forced to `pending_review` for
   review visibility.
3. A macro relationship cannot become `approved` unless every support claim is
   `approved`.
4. If any support claim leaves `approved`, an approved macro relationship must
   become `stale_support`.
5. If a support claim is superseded by a replacement, the relationship may be
   revalidated against the replacement only through a worker or reviewer action.
6. Revalidation must write a `macro_relationship_review_events` row.

### Staleness Watcher

Implement a watcher, not just creation-time validation.

Options:

1. Application watcher in claim review actions.
   - When `updateClaimStatus` or `reviseClaim` changes a claim status, call
     `markMacroRelationshipsStaleForClaim(claimId)`.
   - Low migration risk, easy to test.
2. Scheduled worker.
   - Periodically scans for approved macro relationships whose support claims
     are no longer approved.
   - Catches drift from scripts or future code paths.
3. Database trigger.
   - Strongest guard, but more migration complexity.

Recommendation:

- Round 1: implement application watcher plus a sweep that runs through an
  existing scheduled worker or manual admin action. Do not add a new Trigger.dev
  schedule while the project is at 10/10 schedules.
- Round 2: add DB trigger only if drift still appears.

Important:

The watcher is not the read-time trust boundary. Brain/chat/MCP queries must
still join support claims and verify approval at read time.

Sweep query shape:

```sql
SELECT mr.id
FROM macro_relationships mr
JOIN macro_relationship_claims mrc ON mrc.macro_relationship_id = mr.id
JOIN claims c ON c.id = mrc.claim_id
WHERE mr.status = 'approved'
  AND c.status <> 'approved';
```

Then set:

- `status='stale_support'`
- `staleness_reason='support claim left approved status'`
- `stale_since=now()`

Read-time serving query shape:

```sql
SELECT mr.*
FROM macro_relationships mr
WHERE mr.status = 'approved'
  AND NOT EXISTS (
    SELECT 1
    FROM macro_relationship_claims mrc
    JOIN claims c ON c.id = mrc.claim_id
    WHERE mrc.macro_relationship_id = mr.id
      AND c.status <> 'approved'
  );
```

Every retrieval/synthesis/MCP query must use this pattern or a shared helper
that enforces it.

### Approval-Driven Revalidation

When a support claim is approved:

1. Find macro relationships in `blocked_pending_support` or `needs_review` that
   reference it.
2. If all support claims are now approved, move to `pending_review`.
3. Optionally enqueue a revalidation model call if the relationship was created
   before one or more support claims were revised.
4. Do not auto-approve in round 1.

This avoids the lifecycle gap where macro relationships are generated right
after extraction but never rechecked after human claim approval.

## Prompt and Output Schemas

Create new prompt/schema files:

- `packages/ai/src/prompts/source-outline.ts`
- `packages/ai/src/prompts/macro-relationship.ts`
- `packages/ai/src/prompts/coverage-audit.ts`
- update `packages/ai/src/prompts/extraction-system.ts` to include
  `claimKind` in extraction output once the schema supports it

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
- `exceptions`
- `policyPracticeSignals`
  - `policyRefs`
  - `observedPracticeRefs`
  - `workaroundRefs`
- `openQuestions`
- `recommendedExtractionLenses`
- `sourceGroups`
  - `groupType`
  - `title`
  - `sourceRefs`
  - `whyGrouped`

Prompt rules:

- Say "unknown" when the source does not define a term or owner.
- Do not invent missing process steps.
- Use source refs only from the supplied list.
- Mark every outline element as provisional.
- For visual sources, preserve spatial layout and directional edges when
  available.

### Multimodal Source Outline

For images, PDFs with diagrams, spreadsheets, spec sheets, HTS/duty sheets,
factory forms, or visual layouts, the source-outline worker should be
multimodal:

- provide raw image/PDF input where the selected provider supports it
- provide parsed text chunks as a second view
- ask the model to reconcile spatial structure with OCR/text extraction

Do not make multimodal outlining mandatory for plain text or markdown. Use a
document-class heuristic:

- always multimodal for image uploads
- multimodal for PDFs when parser metadata or file context indicates diagram,
  table-heavy spec, schematic, form, or layout
- text-only for normal markdown, txt, and docx unless uploader context requests
  visual reasoning

### Lens Extraction Schema

Keep existing atomic extraction output shape, with additions:

- `claimKind`
- `lens`
- `sourceGroupId`

Every lens output still requires direct evidence quote validation. The model may
use source outline context to resolve meaning, but cannot cite outline text.

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
- `sourcesInvolved`

Hard validation:

- Every supporting claim ID must be from the supplied list.
- Approved macro relationships require all support claims to be approved.
- The summary may not introduce named entities absent from support claim
  summaries or the canonical entity registry.
- The relationship must not duplicate an existing approved or pending macro
  relationship above the near-duplicate threshold.

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

The finding must not assert a new operational fact as true.

## Worker Plan

### New Worker: `source-outline`

Location:

`apps/workers/src/trigger/source-outline.ts`

Inputs:

- `{ documentId }`
- later: `{ channelId, before?, after? }`
- later: `{ meetingTranscriptId }`
- later: `{ sourceSetId }`

Document flow:

1. Load `documents` row.
2. Load all `document_chunks`.
3. Decide text-only versus multimodal outline.
4. Build a full-source prompt.
5. Use provider cache/file-backed path where available.
6. If the source is too large or provider does not support the needed modality,
   run map-reduce outlining:
   - per-window mini outlines
   - merge outline
7. Compile through `OracleAIClient`.
8. Write `oracle_context_packs`, `model_runs`, usage, and attempts.
9. Insert `source_outlines`, `source_outline_sources`,
   `source_outline_source_refs`, `source_groups`, and `source_group_items`.
10. Embed `source_groups` for semantic thread stitching and dedup.
11. Supersede older outlines when `source_hash` differs.

Route:

- start with `default_general_purpose_route`
- add `default_macro_route` only if macro workloads need different model
  economics than taxonomy/general tasks

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
  -> budgeted lens-guided extraction over groups/windows
  -> semantic dedup before promotion/review
  -> validate/promote
  -> macro relationship pass
  -> coverage audit
  -> cache cleanup
```

Implementation details:

1. After chunk insertion, call `ensureSourceOutlineForDocument()`.
2. Include latest non-failed outline as a `semi_stable_domain_context` block.
3. Replace or augment `buildDocumentChunkWindows()` with
   `buildDocumentExtractionUnits()`:
   - prefer source groups
   - preserve max prompt budget
   - include adjacent context as non-evidentiary context
   - clearly label active evidence chunks
4. Let source outline recommend lenses.
5. Apply deterministic budget gate before triggering lens tasks:
   - max lenses per document
   - max source groups per document
   - max model calls per document
   - max estimated input tokens
   - max estimated USD
6. Run selected lens tasks through Trigger.dev child tasks.
7. Keep quote validation unchanged for atomic claims.
8. Run semantic dedup before sending near-duplicates to review.
9. Trigger macro relationship extraction and coverage audit when atomic passes
   complete or when enough support claims are approved.
10. Release provider caches when all planned consumers finish or the budget is
    exhausted.

### New Worker: `document-lens-extraction`

Location:

`apps/workers/src/trigger/document-lens-extraction.ts`

Inputs:

- `{ documentId, sourceOutlineId, sourceGroupId, lens }`

This makes lens passes independently retryable and budgetable.

Flow:

1. Load source group items.
2. Load source outline summary and relevant outline elements.
3. Build extraction prompt with active lens.
4. Run existing extraction route candidate chain.
5. Stage candidates through the same validation/promotion code.
6. Record lens and source group metadata in `extraction_batches` and
   `raw_candidate_json`.

### New Worker: `macro-relationship-extraction`

Location:

`apps/workers/src/trigger/macro-relationship-extraction.ts`

Inputs:

- `{ documentId }`
- `{ channelId, sourceOutlineId }`
- `{ sourceOutlineId }`
- `{ claimIds, relationshipScope: 'cross_source' }`

Flow:

1. Load source outline when available.
2. Load candidate support claims:
   - same document
   - same channel/thread
   - explicit claim ID set for cross-source runs
   - cross-source related claims selected by entity/domain/process-stage
     overlap
3. Include claim status and `claim_kind`.
4. Group by:
   - source group
   - process stage
   - domain
   - entity
   - claim kind
   - source type
5. Run macro relationship prompt.
6. Validate relationship and support IDs.
7. Run semantic near-duplicate check.
8. Insert `macro_relationships`:
   - `blocked_pending_support` if any support is pending
   - `pending_review` if all support is approved but relationship is not
     reviewed
9. Insert `macro_relationship_claims`.
10. Insert `macro_relationship_sources`.
11. For contradiction/tension relationships, call or enqueue the existing
    contradiction path instead of creating a parallel queue.

### Cross-Source Candidate Selection

Cross-source macro relationships are a retrieval problem. The worker must not
hand the model an unbounded pile of all claims sharing a domain.

Candidate selection should be staged:

1. Pick a seed.
   - changed claim
   - source outline element
   - coverage finding
   - approved policy claim
   - observed-practice/workaround claim
2. Retrieve candidate pools with separate caps:
   - top K by shared entities
   - top K by same or neighboring top domains
   - top K by process stage
   - top K by embedding similarity
   - top K by source recency or source authority
   - top K opposite-kind claims, such as `policy` versus
     `observed_practice`/`workaround`
3. Rerank with a deterministic score:
   - entity overlap
   - domain proximity
   - process-stage match
   - semantic similarity
   - source-type diversity
   - claim kind confidence/review status
   - impact and confidence
4. Diversify:
   - cap claims per source
   - require at least two source types for policy/practice comparisons when
     possible
   - avoid sending many near-duplicates from the same document
5. Hard cap the final model input:
   - max support candidates per relationship run
   - max claims per source
   - max total tokens
   - max estimated cost

Defaults should be conservative, for example:

- 20 to 40 total candidate claims per cross-source macro call
- 8 claims per source maximum
- no more than 3 source documents/channels unless manually requested

If candidate selection cannot build a high-quality bounded set, create a
coverage finding or gap instead of asking the model to infer a relationship from
noise.

### Contradiction Integration

Do not create two contradiction systems.

Rule:

- Macro relationship type `policy_vs_practice_tension` and
  `contradiction_or_tension` should feed the existing `contradictions` table or
  a shared review surface.

Implementation options:

1. Macro worker writes to `contradictions` when it finds two conflicting support
   claims.
2. Macro worker creates a macro relationship with relationship type
   `policy_vs_practice_tension`, then a bridge worker creates/updates a
   `contradictions` row.
3. Existing contradiction watcher reads macro candidates as additional signals.

Recommendation:

- Round 1: macro worker creates a macro relationship and, when the relationship
  is a direct claim-vs-claim conflict, upserts a `contradictions` row with a
  metadata pointer to the macro relationship.
- Admin UI should link between the two instead of duplicating review decisions.

### New Worker Logic: `macro-relationship-staleness-sweep`

Location if implemented as a standalone task:

`apps/workers/src/trigger/macro-relationship-staleness-sweep.ts`

Deployment constraint:

Do not add a new scheduled task for this while Trigger.dev is at the 10/10
schedule limit. Prefer:

- call the sweep from an existing scheduled worker
- add a shared maintenance task if an existing schedule is consolidated
- expose an admin on-demand action
- call targeted stale-marking directly from claim review actions

Flow:

1. Find approved macro relationships with non-approved support claims.
2. Mark them `stale_support`.
3. Write review event.
4. Optionally enqueue revalidation when superseded support has a replacement.

Schedule:

- daily or every few hours depending on volume, but only through an existing or
  consolidated schedule
- also callable from claim review actions

### New Worker: `macro-relationship-revalidation`

Inputs:

- `{ macroRelationshipId }`
- `{ claimId }`

Flow:

1. Load relationship and support claims.
2. If support claims are pending, keep `blocked_pending_support`.
3. If support claims are all approved, validate named entities and support
   status.
4. If support includes superseded claims with replacements, ask model/reviewer
   whether replacement claims preserve the relationship.
5. Move to `pending_review`, `needs_review`, or `stale_support`.

### New Worker: `source-coverage-audit`

Location:

`apps/workers/src/trigger/source-coverage-audit.ts`

Flow:

1. Load outline.
2. Load extracted atomic claims and macro relationships.
3. Ask what outline elements are not represented.
4. Validate references.
5. Insert `source_coverage_findings`.
6. Optionally create gaps.

### Modify Worker: `claim-extraction`

Round 1 for chat:

1. Keep current 60-minute segments for atomic extraction.
2. Add `thread_state_summary` as a source outline variant for channel threads.
3. After each segment, update latest channel outline with:
   - active entities
   - unresolved references
   - open operational problems
   - recent decisions
   - possible continuation markers
4. Pass latest outline into future segment extraction as
   `semi_stable_domain_context`.
5. Do not let prior outline content be quoted.

Round 2 for chat:

1. Build incident threads across time using:
   - channel
   - shared entities
   - shared customer/licensor/system
   - reply metadata
   - vector similarity between new thread summary and active source groups
2. Run macro relationship extraction over completed incident threads.

### Semantic Thread Stitching

When a new segment summary is generated:

1. Embed the `thread_state_summary`.
2. Search active `source_groups` for same channel or related channels.
3. If cosine similarity is above threshold and entity overlap is sufficient,
   attach new messages to the existing incident source group.
4. Otherwise create a new source group.

This prevents same-day incidents from splitting just because time passed.

### Modify Worker: `brain-synthesis`

Round 1:

1. Load approved macro relationships relevant to section top domains.
2. Include:
   - relationship summary
   - relationship type
   - impact score
   - confidence score
   - support claim IDs
   - claim kinds of support claims
3. Prompt synthesis to prioritize:
   - high confidence
   - high impact
   - approved policy relationships over low-confidence conversational
     inferences
   - policy-versus-practice tensions explicitly, without picking a winner
4. Extend validator so paragraphs may cite:
   - approved claim IDs
   - approved macro relationship IDs
5. Validator must expand macro citations to underlying support claims for named
   entity backing.

Round 2:

1. Replace flat top-200 input with staged cluster batches:
   - high-impact claims
   - recently changed claims
   - approved macro relationships
   - taxonomy subtopics
   - explicit section bindings
2. Generate one subsection at a time.
3. Preserve rejected-version behavior on validation failure.

## Cache Lifecycle Orchestration

Macro passes may use large provider caches. At scale, leaving caches to TTL can
waste money and clutter provider state.

Use existing `provider_cached_content` as the source of truth.

### Cache Lease Model

When a source outline or lens pass creates a provider cache:

- record expected consumer count
- record planned consumer tasks
- record hard expiration
- record cleanup owner
- record provider-specific delete handle

When a consumer task completes:

- decrement or record completion in `provider_metadata_json`
- if all planned consumers complete, call explicit provider delete where
  supported
- mark cache row `deleted`

Provider nuance:

- Vertex explicit caches should be deleted when done.
- DeepSeek automatic prefix cache may not expose delete handles; mark lifecycle
  as not user-managed.
- Qwen/OpenAI/Anthropic cache semantics differ by adapter; cleanup should be
  provider-capability driven, not hard-coded to Vertex behavior.

### Cleanup Hooks

Add cleanup calls at:

- successful completion of all lens tasks for a document
- budget exhaustion
- document ingestion failure
- macro pass failure after no retry remains
- scheduled orphan cleanup

Do not depend only on `claim-extraction-batch-drain`; document lens extraction
and macro passes may not flow through that worker.

## Cost and Budget Plan

Add hard settings:

- `enable_source_outline_pass`
- `enable_macro_relationship_pass`
- `enable_source_coverage_audit`
- `macro_outline_max_chars`
- `macro_max_lenses_per_document`
- `macro_max_source_groups_per_document`
- `macro_max_model_calls_per_document`
- `macro_max_input_tokens_per_document`
- `macro_max_estimated_cost_usd_per_document`
- `macro_relationship_max_support_claims`
- `macro_lenses_enabled`

Budget gate behavior:

1. Estimate calls/tokens/cost before dispatch.
2. Sort candidate lenses by outline recommendation confidence and expected
   value.
3. Dispatch until budget is exhausted.
4. Record skipped lenses with reason.
5. Show budget summary in Admin Documents.

Default rollout:

- outline pass enabled manually only
- macro relationship pass manual only
- no automatic coverage audit until reviewer queue impact is known

## Semantic Deduplication Plan

Candidate hash dedup is necessary but insufficient. Lens passes will produce
near-duplicates with different wording or quote choices.

Add a near-duplicate pass before review:

1. Embed candidate summaries.
2. Compare within same source and source group first.
3. Compare against existing pending/approved claims for the same document or
   channel.
4. Flag near-duplicates above threshold.
5. Either:
   - mark lower-confidence candidate as duplicate
   - merge evidence into existing candidate/claim
   - show as duplicate cluster in review UI

Round 1 can be conservative:

- do not auto-delete near-duplicates
- collapse them visually in admin review
- let reviewer choose the best summary

## Reviewer Triage Plan

Reviewer load is the adoption risk. The system already has review bottlenecks;
macro work will add more.

Add `triage_score` to macro relationships and coverage findings.

Suggested scoring:

- impact score
- confidence score
- customer/licensor risk
- number of support claims
- number of distinct sources
- policy-versus-practice tension
- source importance
- recency
- coverage severity
- whether supporting claims are all approved
- whether relationship affects Brain sections or MCP-visible knowledge

Admin UI must default-sort by triage score, not created time.

Review queue categories:

- Needs attention now
- Blocked on claim approval
- Possible duplicates
- Low-risk backlog
- Stale support

Round 1 should not auto-approve macro relationships.

## Admin UI Plan

### Admin Documents

Enhance `apps/web/app/admin/documents`:

- source outline status
- model used for outline
- outline summary
- process stages and source groups
- recommended lenses and skipped-budget reasons
- macro budget summary
- cache lifecycle status
- coverage findings

Actions:

- Generate outline
- Regenerate outline
- Run selected lenses
- Run macro relationship pass
- Run coverage audit
- Reevaluate document with macro context

### Admin Claims

Enhance claim rows:

- claim kind
- source outline used
- source group
- lens
- near-duplicate cluster
- related macro relationships

### New Admin Page: Macro Review

Path:

`apps/web/app/admin/macro-relationships`

Features:

- triage-sorted pending queue
- blocked pending support queue
- stale support queue
- relationship summary
- relationship type
- impact/confidence
- source outline summary
- supporting claim cards with evidence quotes
- support claim statuses
- source lineage across documents/channels
- approve/reject/revise
- revalidate
- convert to gap
- link to contradiction row where applicable

### Admin Contradictions

Show macro relationship links for contradictions created or enriched by macro
passes. Do not make reviewers resolve the same tension in two unrelated places.

### Admin AI Eval

Extend `/admin/ai/extraction-ab` or add a sibling macro eval page:

- compare outline-injected extraction versus baseline
- compare lens selection strategies
- score accept rate, revision rate, duplicate rate, quote failure rate, and
  macro coverage

## Retrieval and Chat Plan

Round 1:

- Do not change `searchWithRetrievalPlan`.
- Chat still retrieves approved atomic claims.
- Brain snippets remain as today.

Round 2:

- Add macro relationship retrieval as a separate retrieved block.
- Include only approved macro relationships whose support claims are verified
  approved at read time.
- Search by:
  - embedded relationship summary
  - linked support claim domains/entities
  - relationship type
  - claim kind mix
- Label distinctly:

```text
APPROVED PROCESS RELATIONSHIPS
These are higher-level relationships supported by approved claim IDs.
```

Do not hide macro relationships inside the atomic claim RRF path in round 1.

### Read-Time Support Verification

All macro relationship read helpers must enforce:

- `macro_relationships.status = 'approved'`
- no linked support claim has `claims.status <> 'approved'`
- relationship is not `stale_support`, `needs_review`,
  `blocked_pending_support`, `pending_review`, `rejected`, or `superseded`

This must happen in SQL or a single shared server helper used by Brain, chat,
MCP, and admin previews. Do not rely on denormalized status alone.

Example helper location:

- `packages/oracle-engines/src/macro/approved-relationships.ts`

The helper should return relationship rows plus support claim summaries so
callers can expand provenance without issuing ad hoc queries.

## Security and RLS Plan

Round 1 macro tables should be server-only:

- `source_outlines`
- `source_outline_sources`
- `source_outline_source_refs`
- `source_groups`
- `source_group_items`
- `macro_relationships`
- `macro_relationship_sources`
- `macro_relationship_claims`
- `macro_relationship_review_events`
- `source_coverage_findings`

Server-only means:

- all admin pages use server components/actions with `getDirectDb()`
- employee chat route reads through server-side service-role code only
- no client component queries these tables directly with the anon key

If any browser path later reads these tables through Supabase anon client, add
RLS policies before exposing it.

Minimum future RLS posture:

- employees may read only approved macro relationships that pass read-time
  support verification and are allowed to appear in chat/MCP context
- admins may read all rows
- writes are service-role only
- review events are append-only via server actions

Document this boundary in `docs/architecture.md` when the implementation lands.

## Validation Plan

### Atomic Claims

No weakening:

- source pointer must exist
- quote must validate against one active source message or one document chunk
- taxonomy must validate
- sensitivity gate still runs
- promotion still goes through `executePromotion`

### Source Outlines

Validate structure only:

- JSON schema valid
- source refs exist and belong to the source
- no invented chunk/message IDs
- maximum sizes respected
- multimodal outline records which raw assets and text chunks were visible

Outlines are allowed to contain uncertainty.

### Macro Relationships

Validate:

- support claim IDs exist
- support claims are not rejected or superseded at creation
- approved relationship support claims are all approved
- source scoping is correct
- summary does not introduce unsupported named entities
- relationship is not a near-duplicate above threshold
- no recursive support from another macro relationship in round 1
- cross-source relationships have explicit source lineage
- `claim_kind`-dependent relationship types require reviewed or high-confidence
  claim kinds, otherwise they become `needs_review` or a coverage finding

### Staleness

Validate continuously:

- claim review actions mark affected macro relationships stale or blocked
- sweep through an existing/consolidated schedule catches drift
- retrieval and synthesis verify support approval at read time
- Brain and chat retrieval exclude `stale_support`, `needs_review`,
  `blocked_pending_support`, `pending_review`, and `rejected`

### Claim Kind

Validate:

- absent kind defaults to `uncertain`
- low-confidence kind cannot be treated as policy/practice truth
- reviewer approve/revise can correct kind
- policy-vs-practice macro relationships include kind confidence/review status
  in the prompt and validator
- synthesis treats unreviewed low-confidence `policy` as weaker than reviewed
  policy

### Coverage Findings

Validate:

- referenced outline element exists
- source refs belong to the source
- suggested gap text is actionable
- finding does not assert new operational truth

## Evaluation Plan

Use the existing extraction A/B machinery instead of manual comparison.

### Extend Existing A/B Harness

Current surfaces:

- `apps/workers/src/trigger/extraction-ab-eval.ts`
- `/admin/ai/extraction-ab`

Add variants:

- baseline extraction
- outline-injected extraction
- outline plus selected lens extraction
- alternate model route if needed

Metrics:

- accepted claim rate
- reviewer revision rate
- quote validation failure rate
- near-duplicate rate
- handoff/dependency/exception recall
- coverage findings resolved by extraction
- macro relationships approved/rejected
- cost per accepted claim
- cost per approved macro relationship

Fixtures:

- diagram with branches
- multi-page SOP with acronym/pronoun dependencies
- Teams incident split across hours
- policy document plus Teams workaround thread
- table-heavy manufacturing/spec sheet

Success threshold:

- outline injection must improve accepted useful claims or reduce revisions
  enough to justify cost
- lens fan-out must not inflate duplicate review load beyond threshold
- macro relationships must have a materially higher approval rate than generic
  model summaries

## Brain Synthesis Protection

The Brain may cite approved macro relationship IDs only when:

- relationship status is `approved`
- relationship is not stale
- all support claims are approved
- support claims are included or expandable in the synthesis validator

Prompt must include:

- relationship `impact_score`
- relationship `confidence_score`
- support claim IDs
- claim kinds
- relationship type

Prompt instruction:

- prioritize high-confidence structural workflow rules
- distinguish policy from observed practice
- explicitly mention unresolved policy/practice tension rather than resolving it
  without evidence
- avoid elevating low-confidence conversational inferences above official policy

Validator:

- rejects unknown macro IDs
- rejects stale/unapproved macro IDs
- expands macro support claims for named-entity backing
- optionally requires paragraphs citing macro IDs to cite at least one
  underlying claim ID in structured support data

## Migration and Backfill Plan

### Migration 1

Add:

- source outline tables
- source group tables
- macro relationship tables
- coverage finding table
- `claims.claim_kind`
- `claims.claim_kind_confidence`
- `claims.claim_kind_review_status`

Files:

- `packages/db/src/schema.ts`
- `packages/db/migrations/sql/79_macro_understanding.sql`

### Migration 2

Add any indexes needed after production query plans are observed:

- macro relationship embedding index
- source group embedding index
- triage/status indexes
- cross-source relationship source indexes

Vector index rule:

- Add vector columns in `79_macro_understanding.sql`.
- Do not create HNSW/IVFFlat indexes in that migration.
- Add vector indexes in a gated vector-index migration following the existing
  `ORACLE_RUN_VECTOR_INDEXES=1` pattern, likely near
  `packages/db/migrations/sql/99_vector_indexes.sql`.
- Document any new vector index names and build commands in
  `docs/deployment.md` or the migration README when implemented.

### Backfill

Do not backfill all documents at once.

Priority:

1. known workflow documents
2. known diagram/image ingestion incidents
3. documents with many approved claims
4. documents feeding active Brain sections
5. Teams transcripts tied to known operational incidents

Script:

- `scripts/backfill-source-outlines.mjs`
- dry-run by default
- filters by document ID, status, created date, minimum approved claims
- triggers tasks rather than doing provider work inline
- respects per-document and global budget caps

## Implementation Phases

### Phase 0: Decision and Guardrails

Deliverables:

- `DECISIONS.md` entry for macro understanding
- define evidence rule:
  - source outlines are guidance
  - atomic claims require direct quotes
  - macro relationships cite validated claim IDs
  - approved macro relationships require approved support claims
  - stale support removes relationships from trusted retrieval/synthesis
- trusted retrieval/synthesis must verify support approval at read time
- record schedule constraint: no new Trigger.dev cron until the 10/10 schedule
  limit is resolved or schedules are consolidated
- record RLS/service-role boundary for new macro tables
- record vector-index gate for source group and macro relationship embeddings
- update docs map

Acceptance:

- provenance boundary is explicit
- no runtime behavior changes

### Phase 1: Source Outline Storage and Worker

Deliverables:

- schema/migration for outlines, sources, refs, groups, group items
- source outline prompt/schema
- `source-outline` worker for documents
- admin action to generate outline
- context pack/model run logging

Acceptance:

- document can produce an outline
- outline refs validate
- admin can inspect outline
- no claims are created

### Phase 2: Outline Injection Into Extraction

Deliverables:

- `ensureSourceOutlineForDocument()`
- extraction context block includes outline
- feature flag
- quote validation regression test that outline text cannot be cited

Acceptance:

- document ingestion still works if outline generation fails in non-blocking
  mode
- claims still require direct quotes
- context packs show outline block

### Phase 3: Claim Kind

Deliverables:

- `claims.claim_kind`
- `claims.claim_kind_confidence`
- `claims.claim_kind_review_status`
- extraction schema emits claim kind
- admin displays claim kind
- reviewer approve/revise can correct claim kind
- retrieval/synthesis can use claim kind as context

Acceptance:

- policy versus observed practice can be represented
- low-confidence kind defaults to uncertain behavior
- revision flow preserves/updates claim kind

### Phase 4: Budgeted Source Groups and Lens Extraction

Deliverables:

- source groups drive extraction units
- outline-recommended lenses become child tasks after budget gate
- semantic dedup before review
- admin displays skipped lens reasons

Acceptance:

- lenses improve recall on fixtures
- duplicate queue is controlled
- budget limits are enforced

### Phase 5: Macro Relationship Extraction and Lifecycle

Deliverables:

- macro relationship schema
- macro relationship worker
- validators
- review events
- staleness watcher
- read-time support approval helper
- approval-driven revalidation
- admin macro review page

Acceptance:

- pending support blocks approval
- approved relationship goes stale when support claim dies
- stale relationships are excluded from Brain/chat by both status and read-time
  support verification
- support approval can move relationship back to review
- no new scheduled Trigger.dev task is added unless a schedule slot exists or
  schedules are consolidated

### Phase 6: Coverage Audit and Gap Creation

Deliverables:

- coverage finding table
- coverage audit worker
- admin coverage surface
- gap creation from findings

Acceptance:

- missing stages/owners can be detected
- findings do not become claims automatically

### Phase 7: Cross-Source Macro Relationships

Deliverables:

- cross-source support claim selection
- bounded/ranked candidate retrieval
- macro relationship sources
- policy-versus-practice tension detection
- contradiction integration

Acceptance:

- relationship can connect Document X and Channel Y
- candidate set is capped, ranked, and source-diversified
- contradiction queue is not duplicated
- claim kind improves relationship classification

### Phase 8: Chat Thread State

Deliverables:

- channel/thread source outlines
- semantic incident stitching
- source group embeddings
- future segment context injection

Acceptance:

- long-running incident is grouped across time
- thread state cannot be cited as evidence

### Phase 9: Brain Synthesis Integration

Deliverables:

- synthesis loads approved macro relationships
- prompt includes impact/confidence/support claims/claim kinds
- validator accepts safe macro citations
- stale macro IDs reject
- synthesis query verifies all support claims are still approved at read time

Acceptance:

- Brain can cite approved macro relationships
- stale or support-invalid relationships are excluded
- named-entity validation still works

### Phase 10: Retrieval and Chat Use

Deliverables:

- macro relationship retrieval helper
- chat prompt includes approved macro relationships separately
- context packs record included macro IDs

Acceptance:

- chat can use approved macro relationships
- no macro leakage when disabled
- atomic claim retrieval path remains endorsed and unchanged

## Rollout Plan

1. Ship schema and source outline worker behind flags.
2. Generate outlines manually for 3 to 5 known workflow documents.
3. Run A/B eval: baseline versus outline-injected extraction.
4. Enable outline injection for admin document uploads only.
5. Add claim kind.
6. Add budgeted source groups and one or two lenses.
7. Add semantic dedup and reviewer triage before broad lens rollout.
8. Add macro relationship proposals with no auto-approval.
9. Add read-time support verification and staleness watcher before any macro
   relationship can be used by Brain.
10. Add coverage audit.
11. Add cross-source macro relationships.
12. Integrate approved macro relationships into Brain.
13. Integrate approved macro relationships into chat retrieval.

## Quality Metrics

Track:

- accepted claim rate
- quote validation failure rate
- reviewer revision rate
- rejected claim rate by reason
- near-duplicate rate
- claims per source by claim type and claim kind
- handoff/dependency/exception recall
- coverage findings per source
- macro relationships proposed/approved/rejected/stale
- blocked macro relationships waiting on support approval
- staleness events
- reviewer queue size and age
- cost per source
- cost per approved claim
- cost per approved macro relationship
- Brain synthesis validation failures
- broad process answer quality

## Risks and Mitigations

Risk: source outline pollutes atomic claims with unsupported assumptions.

Mitigation:

- outline is context only
- outline source IDs are not valid evidence IDs
- quote validation unchanged
- tests where model tries to quote outline text

Risk: macro relationships become stale.

Mitigation:

- lifecycle states
- application watcher
- sweep through an existing/consolidated schedule or admin action
- retrieval/synthesis verifies support claims at read time and excludes
  stale/unapproved relationships

Risk: macro relationships weaken provenance.

Mitigation:

- separate table first
- support claim IDs required
- approval requires approved support
- no recursive macro support in round 1

Risk: reviewer queue explodes.

Mitigation:

- triage score
- duplicate clustering
- budgeted lens fan-out
- no automatic broad backfill

Risk: cost cliff.

Mitigation:

- per-document budget settings
- deterministic lens cap
- cache leases and cleanup
- manual rollout first

Risk: contradiction duplication.

Mitigation:

- macro contradiction/tension feeds existing contradiction path
- admin UI links relationship and contradiction

Risk: vision/text outline misses spatial meaning.

Mitigation:

- multimodal source outline for images, diagrams, forms, spec sheets, and
  spatial PDFs

## Open Questions

1. Should macro relationships remain separate forever, or eventually become a
   claim subtype with claim-to-claim evidence?
2. Should `claim_kind` be a checked varchar first or a Postgres enum?
3. Which macro relationship types should feed `contradictions` automatically?
4. What default budget is acceptable per document?
5. Which model should own macro passes: general, synthesis, or a new macro
   auxiliary route?
6. What near-duplicate threshold is safe enough to collapse review UI without
   hiding distinct facts?
7. Should source group embeddings use the same embedding model as claims?
8. When a support claim is superseded, can replacement mapping be automatic, or
   must it always be reviewer-approved?

## First Slice Recommendation

The first shippable slice should be conservative:

1. Add source outline and source group tables.
2. Add document-only `source-outline` worker.
3. Add manual "Generate outline" on Admin Documents.
4. Show outline and groups in Admin Documents.
5. Inject outline into document extraction behind a feature flag.
6. Add A/B eval comparing baseline versus outline-injected extraction.
7. Prove outline text cannot be cited as evidence.

Second slice:

1. Add `claim_kind`.
2. Add budgeted handoff and exception lenses.
3. Add semantic dedup in review UI.

Third slice:

1. Add macro relationships.
2. Add support-claim lifecycle states.
3. Add staleness watcher before Brain or chat can consume them.

This sequence moves the system toward macro-first understanding without taking
a risky shortcut around provenance.
