# MACRO-FIRST REDESIGN — The Oracle as a business consultant

Status: **approved direction, not yet started**. Written 2026-07-06.
Author: Claude (Fable 5), commissioned by Albert.
Audience: the implementing developer. This document assumes you are competent but have
NOT internalized this codebase or the reasoning behind these decisions. Where a judgment
call could arise, this document makes the call for you (§10 "Forks in the road"). Follow
the calls unless you can prove one wrong with evidence from the code or a live run — in
which case record the deviation and its proof in this file's changelog (§14).

Read order before you write any code:
1. This document, fully.
2. `AGENTS.md` (repo operating guide — conventions, deploy paths, secrets rules).
3. `fix_enhancement.md` §0, §5, §6 only (product intent, verified bugs, onboarding,
   invariants). Do NOT execute its fix plan — this document supersedes it (§2.3 below
   says exactly what survives from it).
4. `HANDOFF.md` current-state sections (what is already deployed vs. local-only).

---

## 0. Prime directives

These override everything else in this document if a conflict ever appears.

- **D1 — Provenance is the product.** Every durable atomic claim must cite an exact
  verbatim quote from one persisted `document_chunks` row (or one source message),
  enforced by the deterministic quote validator. Nothing in this redesign weakens that.
  Model-generated structure (outlines, maps, process narratives) is NEVER quotable
  evidence and NEVER becomes a claim by itself.
- **D2 — The business model is the primary understanding object.** Claims are evidence
  (footnotes), not understanding. Chat, Brain, and recommendations reason from the
  business model layer and cite claims downward.
- **D3 — Humans review coherent objects.** Admins approve process maps and model
  changes — things a human can actually judge — not thousands of atomic near-duplicate
  claims one at a time. Claim approval is bundled into model-change approval (§4.5).
- **D4 — Failures are loud.** Every new worker writes `job_runs` (running →
  complete/failed) and updates document/model health fields. A silent zero is a bug.
  This was learned the hard way (see `AGENT_ERROR_LOG.md` ERR-001: the macro layer
  hard-failed on every run for weeks and nothing surfaced it).
- **D5 — No sentimentality.** §3 lists what dies. Delete it — do not keep dead code
  paths "just in case," do not leave feature flags that resurrect them. Git history is
  the archive.
- **D6 — Structured-output schemas stay FLAT.** Every new LLM output schema in this
  redesign is a flat list of records, max 2 levels of nesting, with cross-references by
  string ID. Graphs are ASSEMBLED IN CODE from flat lists, with deterministic
  referential-integrity validation. If you find yourself writing a Zod schema with an
  array inside an object inside an array, stop and flatten it.
  Why: this is a MODEL-AGNOSTICISM rule, not a concession to weak models. Nested
  schemas add zero expressive power (any graph is fully representable as flat lists
  with ID references) while shrinking the pool of models eligible to compete for a
  slot — verified in production (ERR-001: Qwen cannot do strict json_schema at all,
  and even Gemini 2.5 flash/pro rejected the nested macro schemas with
  `400 too-complex`). Flat schemas keep the interface portable so the best model can
  always be chosen per slot (§8), and they make validation deterministic and testable.

---

## 1. Product goal and acceptance test

The Oracle must understand POP Creations the way a top-tier consultant would after a
month of interviews and document review: the whole operating model, every process
end-to-end, who owns what, which systems record what, where the gates and branches and
loops are — and then answer questions and make recommendations from that understanding,
with every assertion traceable to quoted evidence.

**The acceptance battery.** The redesign is DONE when the chat endpoint answers all of
these as coherent narratives with claim citations (not ranked lists of fragments), using
the Pop Creations corpus (canonical test document `9d09fa89-3a46-465e-a98b-837287c9e22a`,
"Pop Creations Flow 12112025 (1).png", plus whatever else is ingested):

- B1. "What is the full path of an Edge Home licensed product from buyer concept to
  shipment to the US?"
- B2. "What changes for new products versus existing products?"
- B3. "Where does licensor approval happen and what loops can occur?"
- B4. "What has to happen before mass production can start?"
- B5. "Which teams own each stage of the product lifecycle?"
- B6. "Which systems of record are updated, and at which stage?"
- B7. "Where can the process branch, fail, or loop back?"
- B8 (consultant tier). "Where are the bottlenecks or single points of failure in our
  product development process?"
- B9 (consultant tier). "What process stages have no clear owner or no system of
  record, and what would you recommend?"
- B10 (context tier). Ask a question about ONE stage (e.g., "how does costing work?")
  and the answer must situate it in the surrounding flow (what feeds it, what it gates).

Score each answer 0–2 (0 = fragments/wrong, 1 = partially assembled, 2 = coherent +
cited). Stage gates in §9 specify minimum scores. Record every scoring run in
`evals/macro-first-battery.md` (create it; append-only log).

---

## 2. The core inversion

### 2.1 Today (claim-first)

```
source → chunk → extract atomic claims (blind, per window) → validate quotes →
promote → [afterthought: outline → lens fan-out → LLM tries to rediscover
relationships from a bag of ≤40 prose summaries] → chat does hybrid search over
individual claims
```

Understanding is supposed to EMERGE bottom-up from fragments. It never does: the
extraction prompt mandates fragments (`packages/ai/src/prompts/extraction-system.ts:318`),
the outline arrives after extraction already ran
(`apps/workers/src/trigger/document-ingestion.ts:1328`), the macro layer rediscovers
instead of preserves, and its output is gated invisible
(`packages/oracle-engines/src/macro/lifecycle.ts:16`,
`packages/oracle-engines/src/macro/approved-relationships.ts:64`).

### 2.2 Target (macro-first)

```
source → chunk →
  (1) READ: one holistic model pass produces a source workflow map
      (nodes/edges/lanes/paths, flat lists, evidence-anchored to chunks)
  (2) VALIDATE the map deterministically (graph integrity, evidence anchoring)
  (3) MERGE: propose updates to the durable BUSINESS MODEL
      (new process / stage refinement / contradiction with existing model)
  (4) EXTRACT: map-DIRECTED atomic claims — one canonical claim per map element,
      exact-quote validated, edge-level dedup keys
  (5) REVIEW: admin approves model changes as bundles (claims ride along)
  (6) SERVE: chat/Brain reason from the business model, cite claims
  (7) ANALYZE: deterministic graph analytics + LLM synthesis → recommendations
```

Every layer above claims is new or restructured. The claims layer itself — the quote
validator, promotion pipeline, evidence tables — survives nearly intact as the evidence
substrate. That is deliberate: it is A+ logic (§3.1).

### 2.3 Relationship to `fix_enhancement.md`

That document is the repair plan for the OLD architecture. From it, this redesign keeps:
- The invariants (its §6.5) — restated and extended in §11 here.
- The per-source workflow-map concept and node/edge/path shapes (its §7) — adopted and
  extended in §4.2/§6 here.
- The already-shipped fixes (macro model slot + fallback pool, `macro_health`,
  `job_runs` observability, coverage-first lens budgeting) — the observability and
  routing work carries forward; the lens budgeting is deleted along with lens fan-out
  (§3.2) because map-directed extraction supersedes the problem it patched.
- The eval-fixture idea (its §7 "Evaluation change") — expanded into the battery in §1.

Everything else in `fix_enhancement.md` — outline injection flags, lens budget tuning,
feeding more claims to the LLM macro pass, softening Bug D — is superseded. Do not
implement it.

---

## 3. Keep / Kill / Repurpose — the no-sentimentality inventory

Judge every component by one question: *is this A+ logic for the macro-first
architecture?* Time and money already spent are irrelevant.

### 3.1 KEEP (A+ logic — do not rewrite these)

| Component | Where | Why it stays |
|---|---|---|
| Quote validator + candidate→validation→promotion pipeline | `apps/workers/src/trigger/document-ingestion.ts`, `claim-extraction.ts`, `extraction_batches` / `extraction_candidates` / `extraction_validation_results` / `claim_evidence` tables | The provenance contract (D1). Deterministic, battle-tested, and the audit trail is the product's moat. Map-directed extraction (§5.4) funnels THROUGH this machinery unchanged. |
| Structure-aware chunking | `document-ingestion.ts:93–270` | Respects paragraph/heading/edge-line boundaries so quotes stay matchable. Correct as-is. |
| Vision transcription Pass 1 (`IMAGE_TRANSCRIPTION_SYSTEM`, one-line-per-edge topology) | `document-ingestion.ts` | Verified excellent — on the test diagram it captured every branch/loop/terminal. The map reader consumes its output. Keep the one-line-per-edge rule; it is load-bearing for quote validation. |
| Model routing: slots, admin pickers, fallback pools, capability enforcement, `model_run_attempts` logging | `packages/ai/src/routes/*`, `packages/ai/src/client/oracle-ai-client.ts` | Hard-won (four adapter bugs + ERR-001 all live here). The auxiliary-slot registry mechanism (which added `vision` and `macro` as one registry entry + one settings entry each) is exactly how the three new slots in §8 are added. |
| Observability: `job_runs`, `documents.macro_health`, `apps/workers/src/lib/macro-health.ts` | workers + db | D4. Extend `macro_health` semantics to the new pipeline (§5.7); don't rebuild. |
| Hybrid retrieval (pgvector + tsvector + RRF) | `packages/ai/src/retrieval.ts` | Stays as the EVIDENCE lookup — finding supporting claims for a model element or a chat answer. It stops being the primary answering path (§4.6). |
| Entity registry + taxonomy (top domains, sub-topics, entity proposals) | `entities`, `knowledge_top_domains`, etc. | The business model references entities (systems, roles) instead of inventing parallel tables (§6.2). |
| Admin claim review UI + review groups + review events | `/admin/claims`, `claim_review_*` tables | Adapted, not rebuilt: it gains a "bundle" context (§4.5) but per-claim veto and audit events survive. |
| Brain synthesis worker + sections/versions | `brain-synthesis.ts`, `brain_sections`, `brain_section_versions` | Re-anchored to consume the business model (§5.6, Stage 6). The versioned-draft + validator pattern is good. |
| Translation layer, Teams/Recall/meeting ingestion transports, settings system, seed conventions | various | Orthogonal to the inversion. Untouched except where §5.5 taps conversations into the merge pipeline. |
| Conversation segmenting + non-quotable carry-in | `claim-extraction.ts:1095–1252` | Correct provenance behavior. The macro layer, not quotability changes, is how earlier context becomes durable. |

### 3.2 KILL (delete the code, the settings, and the dead flags)

| Component | Where | Why it dies | Replaced by |
|---|---|---|---|
| Document lens fan-out (whole subsystem) | `apps/workers/src/trigger/document-lens-extraction.ts`, `apps/workers/src/lib/document-lens-budget.ts`, settings `macro_lenses_enabled`, `macro_max_lens_*` (4 keys), migration-81 seeds | It exists to compensate for blind extraction by re-running extraction through themed "lenses," and it produced the 4× duplication disaster (241 claims / 56 quotes). Map-directed extraction makes it redundant: the map already tells us exactly what to extract. Budget machinery, lens-major sort fixes, idempotency guard — all of it goes. | §5.4 map-directed extraction |
| LLM macro rediscovery | `macro-relationship-extraction.ts` model call + `MACRO_RELATIONSHIP_SYSTEM_PROMPT` (`packages/ai/src/prompts/macro-relationship.ts`) + `loadSupportClaims` LIMIT/impact-sort machinery | Asks an LLM to rebuild a graph from ≤40 impact-sorted prose summaries after the pipeline destroyed the graph. Structurally cannot work and empirically never has. | §5.3 deterministic derivation from the map/model + §4.7 for the genuinely inferential relationship types |
| `macro_outline_injection_enabled` flag + prior-outline injection path | `document-ingestion.ts:1424–…` (`loadDocumentOutlineContext`), setting seeded false in migration 79 | Superseded: the map is generated BEFORE extraction and injected unconditionally (§5.2). A flag that gates the architecture's core step is a bug. | awaited pre-read |
| LLM-first coverage audit | `source-coverage-audit.ts` model call + `packages/ai/src/prompts/coverage-audit.ts` | Coverage of a known graph is a deterministic computation, not an LLM opinion. | §5.7 deterministic coverage checks (an optional LLM "anything qualitative missing?" pass may be re-added LAST, Stage 7, if deterministic checks prove insufficient) |
| Summary-text candidate dedup for map-derived claims | candidate-hash logic in promotion path | Same edge phrased 3 ways = 3 claims. | edge-level dedup keys (§5.4) |
| Bug D birth-status semantics for generated structure | `packages/oracle-engines/src/macro/lifecycle.ts` `statusForGeneratedMacroRelationship` | Gating generated structure behind prior mass claim-approval inverts D3 and made the macro layer permanently invisible. | bundle review (§4.5) + read-time verification kept (§11) |
| `source-outline` as a fire-and-forget afterthought | trigger at `document-ingestion.ts:1328–1332` | The read must happen BEFORE extraction, awaited, inline (§5.2). The outline worker's group/lens-recommendation output is superseded by the map. | `source-workflow-read` (§5.2) |

Killing rules: remove task registrations from the Trigger.dev worker bundle; write a
cleanup migration deleting the dead settings keys; grep for every import of deleted
modules (`corepack pnpm -r typecheck` must pass with the files GONE, not stubbed).
`macro-relationship-staleness-sweep.ts` survives only if `macro_relationships` retains
rows (§3.3) — re-point it at the new support-status transitions; otherwise delete it too.

### 3.3 REPURPOSE

| Component | Disposition |
|---|---|
| `source_outlines`, `source_groups`, `source_group_items`, `source_outline_sources/_refs` tables | Retire from the pipeline (no new writers after Stage 3). Do NOT drop the tables until Stage 9 cleanup — historical rows aid the backfill comparison. The new `source_workflow_maps` table (§6.1) is the successor. |
| `macro_relationships` (+ `_claims`, `_sources`, `_review_events`) | KEEP the tables, change the producer and the meaning. Sequence/handoff/branch/loop relationships now live NATIVELY in the process graph (edges) — never as `macro_relationships` rows. `macro_relationships` becomes the home of genuinely inferential cross-claim insights only: `policy_vs_practice_tension`, `contradiction_or_tension`, `workaround_to_system_limitation`, `coverage_gap`, `definition_resolution` — produced by the Stage 7 consultant pass and by contradiction tooling. Rows of type `dependency`/`handoff`/`sequence`/`exception_path` get no new writers. `/admin/macro` UI survives, re-scoped to these types. |
| `/admin/macro` page | Becomes the review surface for model changes (§4.5) + inferential relationships. |
| `gaps` table | Gains a writer: deterministic coverage findings (§5.7) file gaps referencing model elements. |
| Chat's existing macro-relationship injection (`apps/web/app/api/chat/route.ts:192–275`) | Pattern survives; the primary context block becomes the process narrative (§4.6). |

---

## 4. Target architecture

### 4.1 The business model layer (the new spine)

A durable, versioned, cross-source representation of how the company operates. It is
NOT per-document. Sources update it; it outlives them.

Concepts (schema in §6):

- **Business process** — a named end-to-end flow ("Licensed product development",
  "Meeting transcript → knowledge"). Has a summary narrative, a status, a current
  version, and an embedding (for chat matching).
- **Process node** — a stage/step/decision/approval-gate/terminal within a process
  version. Carries: label, node type (`step | decision | approval_gate | system_entry |
  artifact | terminal`), owner (FK → `departments` or `entities`), systems touched
  (FKs → `entities`), and sort/lane info.
- **Process edge** — directed transition between nodes: condition label, edge type
  (`sequence | handoff | branch | loop | exception`), from/to owner.
- **Process path** — a named walk through the graph (`main | alternate | exception |
  loop`): "new-product path", "audit-fail loop". Stored as ordered node/edge ID arrays.
- **Evidence links** — every node and edge links to ≥1 claim
  (`process_element_claims`). Elements without an approved supporting claim are
  `provisional` and are served with that label or not at all (§4.6, §11).
- **Versioning** — mirrors the proven `brain_sections`/`brain_section_versions`
  pattern: `business_processes.current_version_id` → `business_process_versions`;
  nodes/edges/paths hang off a version. Approving a change creates a new version;
  history is never mutated.

### 4.2 The source reading layer

Per source (document, meeting, conversation segment): ONE holistic read producing a
`source_workflow_maps` row — the source's own topology (flat node/edge/lane/path lists,
each anchored to a chunk ID + line-level evidence quote), validated deterministically
before anything downstream consumes it. This is `fix_enhancement.md` §7's artifact,
adopted. It is per-source and immutable once validated; the MERGE step (§4.3) is what
touches the durable model. For prose/SOP sources the same reader runs with a
process-shaped prompt; for non-process sources (price lists, reference sheets) it
returns `map_kind='reference'` with an empty graph and the pipeline degrades gracefully
to plain claim extraction (fork F6).

### 4.3 The merge layer (source map → business model)

The step that makes the system cumulative instead of amnesiac. For each validated source
map, a worker (`business-model-merge`) matches the map against existing process
versions and emits a **model change proposal** (`business_model_changes` row).

**Candidate shortlisting is DOMAIN-SCOPED (Albert's requirement — a licensing
responsibility list must never be analyzed against logistics flow data):** the source's
knowledge top-domains (already classified by the existing taxonomy pipeline on the
document/chunks) filter the candidate processes FIRST via `process_top_domains`
(§6.2); embedding similarity on process/node labels + entity overlap ranks WITHIN the
domain-filtered set. Shortlist width: `merge_candidate_top_k` (seed 5) candidates are
considered INTERNALLY, then narrowed to the highest-confidence 1–2 before the LLM
alignment pass sees them — a hard top-2 cutoff fails on overlapping processes, while
showing the LLM five graphs invites over-matching; shortlist wide, align narrow. Only
the narrowed processes enter the merge context window. A source whose domains match no
existing process goes straight to `create_process`. The proposal is one of:

- `create_process` — nothing matches; propose a new process built from the map. (This
  is the "add a whole process" case.)
- `refine_process` — the map covers an existing process (or part); propose a flat
  operations list (§6.4) of specific changes. **"Add" lives here**: `add_node`,
  `add_edge`, `add_path` operations extend the known process with stages/branches/
  paths the model had never seen (e.g., a new source reveals an extra approval step).
  There is deliberately no separate `add` proposal type — additions and edits ride the
  same review flow, since both change the structure and need the same human judgment.
- `confirm` — the map is consistent with the current version; record corroboration
  (bump element confidence; link new evidence claims) — auto-appliable, no human gate.
- `contradict` — the map disagrees with the current version on specific elements;
  propose the change AND file a `contradictions` row. Never auto-apply.

Matching is LLM-assisted (the `model_merge` slot, §8; flat schema: list of
`{mapNodeId, modelNodeId|null, verdict}` alignments) but the resulting diff is computed
in code. The proposal stores the full operations list, the source map ID, and the
supporting claim IDs per operation.

### 4.4 The evidence layer (claims, demoted but intact)

Claims keep their exact shape, tables, quote validation, translations, taxonomy, and
review events. Two changes only:

1. **Origin**: for mapped sources, extraction is map-directed (§5.4) — each candidate
   carries the map element it evidences (`extraction_candidates.map_element_ref`), and
   dedup keys on the element, not on summary prose.
2. **Approval flow**: claims bundled in a model change are approved/rejected with the
   bundle (§4.5). Direct per-claim review still exists (conversations, unmapped
   sources, vetoes).

The extraction prompt keeps its atomicity rules — they are correct for evidence — but
gains the map as injected context and an explicit instruction that its job is to
evidence the map, not to summarize the document.

### 4.5 The review model (inverted)

The admin's unit of work is a **model change proposal**, rendered as: the process graph
before/after (diff-highlighted), the operations list, the source, and the supporting
claims per operation with their quotes inline.

Rules (implement exactly):

- Approving a proposal executes the TRANSACTIONAL APPLY defined in §4.8 (optimistic
  lock on the process's `current_version_id`; all-or-nothing). Within that
  transaction it: creates the new process version, applies the operations, approves
  the bundled claims that pass the eligibility checks below (writing a
  `claim_review_events` row with `review_source='model_change_bundle'` and the
  proposal ID), and links `process_element_claims`.
- **Claim eligibility checks — bundle approval is NOT blanket approval.** "The
  structure is right" and "every quoted sentence is right" are related but not
  identical judgments. A bundled claim auto-approves only if ALL of: (a) it passed
  quote validation; (b) its content matches the element/support-role it is linked to
  (an ownership claim linked to an edge-transition op fails this); (c) no open
  `contradictions` row touches it; (d) it is not a duplicate of an existing canonical
  claim for the same business-model element (§4.8 canonical dedup — the newcomer
  links as `corroborating` instead of approving as a second canonical). Claims
  failing any check stay `pending_review` individually and are listed on the
  proposal so the reviewer sees what did NOT ride along.
- The reviewer can veto individual claims within the bundle before approving. A vetoed
  claim is rejected normally. If a veto (or eligibility failure) leaves an operation's
  element with zero supporting claims, that element is created/updated as
  `provisional`.
- Rejecting a proposal: no version change; bundled claims fall back to ordinary
  `pending_review` (they may still be true facts even if the structural read was wrong).
- `confirm` proposals auto-apply without human review (they add evidence, never change
  structure) — through the same §4.8 transaction and the same claim eligibility
  checks.
- Every transition writes an audit event (`business_model_change_events`, mirroring
  `claim_review_events`).

This deletes the Bug D deadlock: structure no longer waits for mass claim approval —
claim approval rides on structure approval, which is one human decision per source.

### 4.6 The answering path (inverted)

`apps/web/app/api/chat/route.ts` context assembly becomes, in order:

1. **Process match**: embed the query; retrieve top matching business processes
   (approved current versions). If matched, render each as a **process context block**:
   narrative summary, ordered stages with owners/systems, branches/loops, and the gate
   list — each element tagged with its supporting claim IDs. Serving verifies at read
   time that cited claims are still `approved`; elements whose support is not approved
   render as `provisional` with an explicit label, or are dropped if
   `serve_provisional_process_elements=false` (setting, seed `true` — see fork F4).
2. **Evidence claims**: today's hybrid claim retrieval, now used to (a) attach quotes
   for cited elements and (b) catch facts outside any process.
3. **Inferential relationships**: approved `macro_relationships` (repurposed types),
   as today.
4. **Gaps/contradictions** touching matched processes.

The system prompt (`packages/ai/src/prompts/oracle-system.ts`) is updated to instruct:
answer from the process model, cite claims, state provisional/gap status honestly.
Brain synthesis (Stage 6) anchors sections to processes the same way.

### 4.7 The consultant layer

Runs over the approved business model. Two halves:

- **Deterministic analyzers** (pure code, no LLM, `packages/oracle-engines/src/analysis/`):
  unreachable/orphan nodes; stages with no owner; stages with no system of record;
  approval gates with no failure path; loops with no exit condition; single-owner
  bottlenecks (one department on the critical path N times); cross-source contradiction
  surfacing; coverage gaps (provisional elements, paths with thin evidence). Each
  finding → `recommendations` row (§6.6) citing element IDs.
- **LLM synthesis pass** (the `synthesis` slot — shared with Brain synthesis, §8 row 5): given a process version + analyzer
  findings + supporting claims, write consultant-grade narrative recommendations
  (flat output schema: list of `{title, severity, elementIds[], claimIds[], narrative,
  suggestedAction}`). LLM recommendations must reference only supplied element/claim
  IDs — same trust rule as today's macro prompt, which got this right.

Recommendations are served in chat (B8/B9) and in a new `/admin/recommendations` view,
with statuses (`open | accepted | dismissed | done`).

### 4.8 The state machine and transaction contract (implement this BEFORE any worker code)

This section is the concurrency/idempotency spec for the whole redesign. Stage 1
lands it as schema + a short `docs/`-adjacent contract check; every worker built later
must conform. The failure modes it prevents are not hypothetical: two documents CAN
propose changes to the same process concurrently, and re-dispatched Trigger runs CAN
double-fire.

**States (exhaustive — no other values may be written):**

- `source_workflow_maps.status`: `pending → validated | degraded | failed`;
  `validated/degraded → superseded` (only by a newer validated map for the same
  source, §6.1). Maps are immutable after leaving `pending`.
- `business_model_changes.status`: `pending_review → approved | rejected |
  needs_rebase | superseded`; `pending_review → auto_applied` (confirm only);
  any apply attempt that errors mid-transaction → `failed_apply` (terminal until
  manually re-dispatched). `needs_rebase → superseded` when the rebased replacement
  proposal is created.
- `business_process_versions.status`: `pending_review → approved → superseded`;
  `pending_review → rejected`. Versions are immutable after creation; "editing" a
  version is always creating a new one.

**Transactional apply (approval and confirm auto-apply both use this):**

One database transaction that (1) takes a per-process advisory lock (reuse the
existing promotion-path advisory-lock helper); (2) re-checks
`business_processes.current_version_id == proposal.base_version_id` — if stale, the
transaction aborts and the proposal flips to `needs_rebase` (nothing else changes);
(3) creates the new version + nodes/edges/paths (carrying stable `node_key`/
`edge_key` forward per §6.2); (4) runs the §4.5 claim eligibility checks and approves
eligible claims; (5) runs canonical dedup (below) and writes
`process_element_claims`; (6) writes the audit event; (7) flips
`current_version_id`. Any error → full rollback, proposal `failed_apply`,
`job_runs` failed, `macro_health` degraded. NO partial state, ever.

**Rebase:** a `needs_rebase` proposal is not hand-edited — re-dispatch
`business-model-merge` with the same `source_workflow_map_id` against the NEW current
version; the old proposal is marked `superseded` by the new one. This is safe because
maps are immutable.

**Canonical dedup (cross-source — per-document dedup alone is not enough):** at
link time, if the target element (`version lineage` + `element_key`) already has a
`primary` claim in `process_element_claims`, a new claim asserting the same fact
links as `corroborating` — it never becomes a second canonical claim. Per-document
`(documentId, mapElementRef)` dedup (§5.4) handles within-source duplication; this
rule handles across-source duplication.

**Idempotency keys (every worker; re-dispatch with the same key must be a no-op that
returns the existing artifact):**

- `source-workflow-read`: `(source id, source content hash)` — the §6.1 uniqueness.
- `business-model-merge`: `(source_workflow_map_id, base_version_id)` — a second
  dispatch finds the existing proposal and exits.
- apply: proposal ID + status guard — only a `pending_review` proposal can apply;
  double-click/double-dispatch hits the status check and no-ops.
- extraction: the existing batch machinery + `(documentId, mapElementRef)` dedup.
- recommendations: `(version_id, analyzer_key, hash(element_keys))`.

**Retries and poison jobs:** bounded retries via Trigger.dev task config (max 3, as
today); a run that exhausts retries writes `job_runs` failed + the appropriate
terminal status (`map_failed` / `failed_apply` / `macro_health='failed'`) — never an
infinite retry loop, never a silently vanished job (D4). A stuck document (any
`pending` state older than 24h) is surfaced in Admin → Documents.

---

## 5. The new pipeline, end to end

### 5.1 Document ingestion (rewrite of `processDocument` control flow)

```
parse → chunk → embed                       (unchanged, KEEP §3.1)
→ AWAIT source-workflow-read  (§5.2)         (new, inline — not fire-and-forget)
→ map validation (deterministic)  (§5.2)
→ map-directed claim extraction  (§5.4)      (through existing candidate/validation/promotion)
→ AWAIT business-model-merge  (§5.3)         (proposal written; confirm auto-applies)
→ deterministic coverage check  (§5.7)
→ set documents.macro_health + status
```

Ordering is sequential with barriers — no `.trigger().catch(warn)` for pipeline-critical
steps. Trigger.dev `triggerAndWait` (or direct function composition inside
`document-ingestion`) is the mechanism; fire-and-forget remains acceptable only for
truly optional afterthoughts (translations, notifications).

**Reader-failure fallback (required — do not make the reader a hard dependency of
ingestion).** The 3-model `workflow_read` pool makes total reader failure rare, but
"rare" is not "never": if all candidates fail, a document must still ingest as claims,
not fail outright — otherwise a workflow-read outage halts ALL document ingestion,
which is a worse regression than the blind-extraction it replaced. Behavior on a
reader that exhausts its pool:
- Gate it on a setting `require_workflow_map_for_ingestion` (seed **`false`**). When
  `false` (default): log the failure loudly, set the map row `failed` and
  `macro_health='map_failed'` (so the miss is VISIBLE, per D4), and CONTINUE to
  map-directed extraction with no map block — extraction falls back to the pre-map
  blind path for this one document. The document completes as `degraded`, never
  silently `complete`. When `true`: the document fails (the §5.1 hard-stop), for
  deployments that would rather block than ingest un-mapped.
- This composes with the Stage-3 old-extraction-path retention (§9): the blind path
  stays reachable as this fallback even after Stage 5 deletes it as the *default*.
- ⚠️ Deviation note (2026-07-07): Stage 2 as first shipped made the reader a HARD
  dependency (total failure fails the document). This fallback is the correct target;
  implement it before the Stage 2 gate is declared green.

### 5.2 `source-workflow-read` (new worker; successor to `source-outline`)

Input: document ID (or meeting/segment ref). Loads all chunks IN ORDER (never a
truncated/impact-sorted subset). Token/cost guardrail: estimated input above
`workflow_read_max_estimated_input_tokens` (setting, seed `150000`) switches to
sequential windows in chunk order, each producing partial flat lists with a
carried-forward node-label registry, merged + re-validated in code (fork F5) — the
budget triggers windowing, never truncation or failure. Model: the `workflow_read`
slot (§8). Output (FLAT, D6):

```
nodes:   [{ nodeId, label, lane, ownerName?, nodeType, systems?, evidenceQuote, chunkId }]
edges:   [{ edgeId, fromNodeId, toNodeId, condition?, edgeType, evidenceQuote, chunkId }]
lanes:   [{ laneId, label, ownerName? }]
paths:   [{ pathId, name, pathType, nodeIdsOrdered, terminalOutcome? }]
summary: string
mapKind: 'workflow' | 'reference'
```

Deterministic validation before persisting `status='validated'`:
every edge endpoint exists; every node/edge `evidenceQuote` is a verbatim substring of
its `chunkId`'s text (reuse the quote validator); no orphan lanes; path node IDs exist.
Failures: drop the offending element, log it into the map's `validation_json`, and mark
the map `degraded` if >20% of elements dropped (threshold as setting
`workflow_map_max_dropped_ratio`, seed `0.2`). A degraded map still proceeds (partial
understanding beats none) but sets `macro_health='degraded'`.

`ownerName`/`systems` are resolved against the `entities` registry in code
(exact/alias match); unresolved names become `entity_proposals`, and the element keeps
the raw string until resolution — never invent entity rows silently.

**Entity resolution — where it happens (resolved 2026-07-07).** Stage 2 as first
shipped stored `ownerName`/`systems` as raw strings and did NOT resolve them against
the `entities` registry or file `entity_proposals`. That is an acceptable DEFERRAL,
not a permanent skip, on one condition: resolution MUST happen no later than the merge
step (§5.3), because the durable `process_nodes.owner_department_id`/`owner_entity_id`
FKs and `process_node_systems` rows cannot be written from raw strings. The rule:
- The reader keeps emitting raw `ownerName`/`systems` strings (correct — the reader
  should not be gated on registry lookups).
- The **merge worker** (§5.3), when it turns an approved map element into a durable
  `process_node`, resolves each raw owner/system against `entities` (exact/alias),
  writes the FK when matched, keeps `owner_raw` and files an `entity_proposal` when
  not — never inventing an entity row silently.
This keeps the invariant (no silent entity invention) while letting the reader stay a
pure topology pass. If merge is not yet built when this is read, the raw strings sit
harmlessly on the map until it is; nothing downstream consumes the unresolved FKs yet.

**Reader context rule — referents, NOT structure (deliberate anti-bias decision).**
The reader prompt is enriched with a compact "referent pack": known entity names and
aliases (systems like DFlow/ColdLion/PPS, people, departments), the NAMES of existing
business processes, and domain vocabulary — so it resolves acronyms, pronouns, and
lane labels correctly against what the company already knows. It must NOT receive the
existing process graphs (nodes/edges/sequences). Why: an LLM primed with the current
model's structure will harmonize the new source toward it and quietly miss
contradictions — and contradictions are the most valuable signal a new source can
carry. Fresh eyes at read time; full model context at MERGE time (§5.3). Do not
"improve" the reader by injecting the business model into it.

### 5.3 `business-model-merge` (new worker)

As §4.3. Determinism rules: the LLM only produces the alignment verdicts; the
operations diff, confidence math, and contradiction detection are code. A `confirm`
outcome auto-applies. Anything structural waits for review (§4.5). If NO process exists
yet (first ever mapped source), `create_process` proposals are still human-gated — the
first version of the model is the most important thing an admin will ever review.

### 5.4 Map-directed claim extraction

Replace the blind per-window prompt assembly in `document-ingestion.ts` (and delete lens
fan-out) with:

- Inject the validated map (rendered compactly: lanes, node list, edge list) into the
  extraction prompt as a `SOURCE WORKFLOW MAP (GUIDANCE ONLY — NEVER QUOTE)` block, for
  EVERY window, unconditionally (no flag).
- Instruct: "For each map node and edge visible in this window's chunks, extract exactly
  ONE canonical claim stating that fact, quoting the chunk verbatim. Additionally
  extract claims for operational facts NOT captured by the map." Claim candidates carry
  `mapElementRef` (`nodeId`/`edgeId` or null).
- Dedup key for map-referenced candidates: `(documentId, mapElementRef)` — first valid
  candidate wins, later phrasings are dropped as duplicates (not promoted as variants).
  Non-map candidates keep the existing summary-hash dedup. This handles WITHIN-source
  duplication only; ACROSS-source duplication (a second document evidencing the same
  business-model element) is handled at link time by §4.8 canonical dedup — the new
  claim links as `corroborating`, never as a second canonical.
- Everything downstream (quote validation, taxonomy, entity checks, promotion) is the
  EXISTING pipeline, untouched.

Expected result on the test diagram: ~60–90 claims (one per unique element + genuine
extras), not 241. That number is a Stage-3 gate (§9).

### 5.5 Conversations and meetings

Stage-5+ scope (do documents first — segments need the apply path to exist). Same
shape, lighter weight: after a conversation segment's claim extraction completes, a
`segment-model-merge` pass runs the §5.3 matcher over the segment's promoted claims +
segment summary against the business model. It emits `confirm`/`contradict`/`refine` proposals only (segments rarely
justify `create_process`). This is what makes a meeting utterance mean something in
context: "they described a workaround at the PPS audit stage" becomes a linked model
change, not fragment #4,012. Live Recall interjections may later consult the process
match (fork F8) — NOT in initial scope.

### 5.6 Brain synthesis re-anchoring (Stage 6)

`brain-synthesis.ts` currently synthesizes per knowledge domain from approved claims.
Change: for domains that intersect business processes, the synthesis prompt receives
the relevant approved process versions as primary structure and claims as evidence.
Validator and versioning machinery unchanged.

### 5.7 Health + coverage (deterministic)

Extend `documents.macro_health` states: `not_applicable | pending | map_failed |
map_degraded | merge_pending_review | complete | failed`. Coverage findings (map
elements with no promoted claim; paths with unevidenced steps; unresolved owners) are
computed in code post-extraction and written as `gaps` rows (`gap_type='model_coverage'`)
+ surfaced in Admin → Documents. No LLM required for any of this.

---

## 6. Schema (hand-written SQL migrations)

Conventions (from AGENTS.md + established macro-table precedent — follow exactly):
hand-written idempotent SQL in `packages/db/migrations/sql/NN_*.sql` (take the next free
number; 85 was the last as of writing); mirror in `packages/db/src/schema.ts` but never
let Drizzle re-emit these tables; RLS ENABLED with NO anon policies (server/service-role
only); vector indexes gated behind `ORACLE_RUN_VECTOR_INDEXES=1`; seeds use
`ON CONFLICT DO NOTHING`.

### 6.1 `source_workflow_maps`

`id`, `source_type` (`document|meeting|conversation_segment`), `document_id` FK null,
`channel_id` FK null, `segment_ref` null, `status`
(`pending|validated|degraded|failed`), `map_kind` (`workflow|reference`), `summary`,
`nodes_json`, `edges_json`, `lanes_json`, `paths_json`, `validation_json`,
`model_run_id` FK, `context_pack_id` FK, `superseded_by_map_id` FK null, timestamps.
Maps are IMMUTABLE once out of `pending` and are never deleted or overwritten:
re-ingesting a source creates a NEW map row and marks the old one
`status='superseded'` (+ `superseded_by_map_id`). Rationale: maps influence claims
and model changes, so replacing one destructively would orphan the audit trail of
everything derived from it. Uniqueness: at most one non-superseded map per
(source, source content hash).

### 6.2 Business model tables

- `business_processes`: `id`, `name`, `slug` unique, `status`
  (`draft|active|archived`), `current_version_id` FK, `summary`, `embedding`
  vector(1536), timestamps.
- `business_process_versions`: `id`, `process_id` FK, `version_number`, `status`
  (`pending_review|approved|superseded|rejected`), `narrative` text,
  `created_from_change_id` FK, `model_run_id` null, timestamps.
- `process_nodes`: `id`, `version_id` FK, `node_key` (stable across versions — carry
  forward on refine so evidence links survive), `label`, `node_type` (§4.1 enum),
  `lane_label`, `owner_department_id` FK null, `owner_entity_id` FK null,
  `owner_raw` text null (unresolved), `sort_order`, `provisional` bool,
  `confidence_score` int.
- `process_edges`: `id`, `version_id` FK, `edge_key` stable, `from_node_key`,
  `to_node_key`, `condition` null, `edge_type` enum, `provisional` bool,
  `confidence_score`.
- `process_node_systems`: (`node_id`, `entity_id`) — systems of record.
- `process_paths`: `id`, `version_id`, `path_key`, `name`, `path_type` enum,
  `node_keys_ordered` jsonb, `terminal_outcome` null.
- `process_element_claims`: `id`, `version_id`, `element_kind` (`node|edge`),
  `element_key`, `claim_id` FK, `support_role` (`primary|corroborating`),
  `claim_status_at_link`. ⚠️ `claim_status_at_link` is AUDIT METADATA ONLY — it
  records history and goes stale by design. Serving and verification must ALWAYS
  join the live `claims.status` (read-time verification, §11.2); no code path may
  branch on `claim_status_at_link` for anything except audit display.
- `process_top_domains`: (`process_id`, `top_domain_id` FK →
  `knowledge_top_domains`) — links every business process to the existing knowledge
  taxonomy. Written at process creation (from the founding source's domains) and
  updated on refine. This is what makes merge shortlisting (§4.3) and chat process
  matching domain-scoped instead of embedding-only.

### 6.3 Extraction linkage

`ALTER TABLE extraction_candidates ADD COLUMN map_element_ref text;` and
`ALTER TABLE claims ADD COLUMN map_element_ref text;` (nullable; format
`<source_workflow_map_id>:<node|edge>:<key>`). Backfill: none (old claims stay null).

### 6.4 `business_model_changes`

`id`, `process_id` FK null (null for `create_process`), `base_version_id` FK
(REQUIRED for `refine_process`/`contradict`/`confirm` — the optimistic-lock anchor,
§4.8), `change_type` (`create_process|refine_process|confirm|contradict`), `status`
(`pending_review|approved|rejected|auto_applied|needs_rebase|superseded|failed_apply`
— full transition rules in §4.8), `superseded_by_change_id` FK null,
`source_workflow_map_id` FK, `operations_json` (flat list:
`{op: add_node|update_node|remove_node|add_edge|update_edge|remove_edge|add_path|
update_narrative, payload, supportClaimIds[]}`), `summary`, `contradiction_id` FK
null, `reviewed_by` FK null, `model_run_id`, timestamps. Unique partial index on
`(source_workflow_map_id, base_version_id)` for non-superseded rows — the §4.8 merge
idempotency key. Plus `business_model_change_events` audit table (mirror
`claim_review_events` columns).

### 6.5 Settings (seed in the same migration)

`serve_provisional_process_elements=true`, `workflow_map_max_dropped_ratio=0.2`,
`model_merge_min_alignment_confidence=70`, `merge_candidate_top_k=5` (internal merge
shortlist, §4.3), `process_match_top_k=2` (chat process matching, §4.6),
`workflow_read_max_estimated_input_tokens=150000` (§5.2 windowing trigger),
plus DELETE of the dead lens keys in the Stage-9 cleanup migration.

### 6.6 `recommendations` (Stage 7)

`id`, `process_id` FK, `version_id` FK, `origin` (`deterministic|llm`), `analyzer_key`
null, `title`, `severity` (`info|warning|critical`), `narrative`, `element_keys` jsonb,
`support_claim_ids` jsonb, `status` (`open|accepted|dismissed|done`), `model_run_id`
null, timestamps.

---

## 7. Prompts

New prompt files under `packages/ai/src/prompts/` (replacing the killed ones):

- `workflow-read.ts` — the §5.2 reader. Reuse the topology vocabulary of
  `IMAGE_TRANSCRIPTION_SYSTEM` (nodes/edges/lanes) so vision output and reader input
  speak the same language. Hard rules in-prompt: every element carries a verbatim
  `evidenceQuote` + `chunkId`; never invent nodes; unknown owner → omit `ownerName`,
  never guess.
- `model-merge-alignment.ts` — the §5.3 matcher. Flat verdicts only.
- `extraction-system.ts` — EDIT, don't replace: keep all provenance/atomicity rules;
  add the map-guidance block contract and the one-canonical-claim-per-element rule
  (§5.4); delete rule text that tells the model nothing exists beyond the window.
- `process-recommendations.ts` — §4.7 synthesis; adopt the trust-rules paragraph from
  the old `macro-relationship.ts` verbatim (only supplied IDs; omit weak findings) —
  that paragraph is A+ and survives its file's deletion.
- `oracle-system.ts` — EDIT: answer-from-model instructions (§4.6).

All new output schemas: flat (D6), optionals as `.nullish()` (OpenAI strict-mode lesson,
see HANDOFF 2026-06-26 bug #1).

---

## 8. Model routing

Model-agnosticism rules first (these are architecture, not preference):

- The CODE never depends on a specific model. Models are picked in admin settings per
  slot, with fallback pools and `model_run_attempts` logging. Never hard-code a model
  ID (F7). D6 (flat schemas) exists to keep the interface portable — it maximizes the
  pool of models eligible for each slot; it is not a concession to any model.
- Hard provider constraint to remember: Qwen/DashScope cannot do strict `json_schema`
  (provider API limitation, see DECISIONS.md D12) — Qwen is therefore ineligible for
  any strict-structured-output slot regardless of quality. It remains eligible for
  chat/prose slots.
- Model names below are SEEDED DEFAULTS + bake-off candidate lists, not dependencies.
  The repo's proven convention (2026-06-26 extraction bake-off) applies: isolate each
  candidate in a one-element pool so fail-over can't mask failures, run the fixture,
  pick the winner empirically. The §9 stage gates include these bake-offs (§8.3).
- Cost policy (Albert): no premium-tier models (Claude Opus/Fable, GPT-5.5,
  Gemini 3.1 Pro Preview). Mid-tier (e.g., Claude Sonnet, Gemini 2.5 Pro) is allowed
  and is worth it for the low-volume, high-reasoning passes: workflow-read and
  consultant run once per source / per process version, not per chunk, so a stronger
  model there costs pennies per document.

### The Model Passes table (Admin → Settings) — Albert's requirement

Admin → Settings exposes ONE consolidated "Model passes" table: every LLM pass is a
row; each row has a **Primary** picker and **two ordered Fallback** pickers (the three
together are written as `default_<slot>_route` + `model_pool_<slot> = [primary,
fallback1, fallback2]`, dispatched by the existing pool machinery), plus a
**Copy job brief** button (same mechanism as today's auxiliary briefs — §8.1 defines
each brief's content). Passes with identical needs SHARE a row (Albert's simplification
decision): consultant synthesis + Brain synthesis are one row; chat + claim-review
questions + live interjections are one row.

Implementation rules:
- Reuse the auxiliary-registry / `AUX_PRESENTATION` mechanism (one registry entry +
  one settings-page entry per row) and the existing model-pool editor. Do not build a
  parallel UI system.
- All defaults below are SEEDED via migration with `ON CONFLICT (key) DO NOTHING` —
  never hard-coded in code paths, never clobbering an admin's existing choice. Runtime
  always reads settings.
- Capability enforcement (`enforce_model_capabilities=true`) filters each row's
  pickers: the vision row lists only vision-capable models; strict-schema rows list
  only `structuredOutputs`-capable models (which automatically excludes Qwen there).
- Verified consolidation facts (do not re-derive): chat ALREADY resolves via
  `default_interview_route` (`apps/web/app/api/chat/route.ts:9`, taskType
  `interview_chat`), and Brain synthesis ALREADY resolves slot `synthesis` via
  `default_synthesis_route` (`brain-synthesis.ts:759`). So the consultant pass (§4.7)
  routes through the EXISTING `synthesis` slot (there is no `default_consultant_route`),
  and the conversation row is a UI relabel of the interview slot — do NOT rename
  settings keys; renames are churn with zero function. Confirm live Recall
  interjections resolve the interview slot too; if they don't, re-point them to it.
- The entire Model Passes table (all 8 rows, relabels, new pools, empty-state
  pickers) ships in Stage 1 with the rest of the schema/settings work (§9) — the rows
  exist before their workers do. The old `macro` slot (`default_macro_route`,
  `model_pool_macro`) is superseded and its keys retire in the Stage-9 cleanup
  migration.

The eight rows:

| # | Row (UI label) | Settings keys | Passes served | Seeded primary | Seeded fallback 1 | Seeded fallback 2 |
|---|---|---|---|---|---|---|
| 1 | Vision transcription | `default_vision_route` + NEW `model_pool_vision` | image → text topology (Pass 1) | `qwen/qwen3-vl-235b-a22b-thinking` (incumbent until the Test 2 bake-off decides) | `google/gemini-2.5-flash` | `claude-sonnet-5` |
| 2 | Workflow read | NEW `default_workflow_read_route` + `model_pool_workflow_read` | §5.2 source workflow read; §5.5 segment read | `openai/gpt-4.1` | `claude-sonnet-5` | `google/gemini-2.5-pro` |
| 3 | Model merge | NEW `default_model_merge_route` + `model_pool_model_merge` | §5.3 merge-alignment verdicts | `openai/gpt-4.1-mini` | `google/gemini-2.5-flash` | `claude-haiku-4-5` |
| 4 | Claim extraction | `default_extraction_route` + `model_pool_extraction` | §5.4 map-directed extraction | `google/gemini-2.5-flash` (2026-06-26 bake-off winner) | `vertex_gemini_2_5_flash_extraction_primary` | `openai/gpt-4.1-mini` |
| 5 | Deep synthesis | EXISTING `default_synthesis_route` + `model_pool_synthesis` (create pool if missing) | §4.7 consultant recommendations + Brain synthesis (combined: same needs) | `claude-sonnet-5` | `google/gemini-2.5-pro` | `openai/gpt-4.1` |
| 6 | Conversation | EXISTING `default_interview_route` + `model_pool_interview` (UI relabel only) | chat/answering + claim-review questions + live Recall interjections | `claude-haiku-4-5` (see cheap-first ladder below) | `google/gemini-2.5-flash` | `claude-sonnet-5` |
| 7 | Translation | `default_translation_route` + NEW `model_pool_translation` | zh-CN claim/question translation | `qwen/qwen-mt-plus` (specialized MT, proven) | `qwen/qwen3.7-max` | `google/gemini-2.5-flash` |
| 8 | General utility | `default_general_purpose_route` + `model_pool_general` | taxonomy naming, misc utility | `qwen/qwen3.7-max` (incumbent) | `claude-haiku-4-5` | `google/gemini-2.5-flash` |

Row 4's seeded values are the CURRENT prod pool — the seed must be a no-op there.
Row 1's fallbacks note: vision fallbacks only fire for vision calls, so all three must
be vision-capable (capability filter handles this).

### 8.1 Job briefs (the Copy button content)

Every row's brief lives in its auxiliary-registry entry and must contain, in order:
**(1) Background** — where the pass sits in the pipeline and why it exists;
**(2) The job** — what the model does; **(3) Input** — exactly what it receives;
**(4) Output** — expected shape/schema; **(5) Required capabilities** — hard filters;
**(6) Beneficial attributes** — what makes one model beat another here;
**(7) Failure modes** — what a bad model does in this seat.
Write the full prose from these facts:

- **Row 1 Vision:** Background: first pass over uploaded images; its transcription
  becomes persisted chunks that ALL downstream quotes must match verbatim. Job:
  transcribe diagrams/flowcharts to structured text topology (nodes `[Shape: "label"]`,
  edges `[A] --(cond)--> [B]`, lane `###` headers), one line per edge. Input: the raw
  image + optional document context. Output: plain structured text (no JSON schema).
  Required: vision. Beneficial: faithful verbatim labels, person-level lane attribution
  (the qwen3-vl vs gemini test case: "Carlos" vs "department"), determinism across
  runs, speed. Failure modes: paraphrased labels (breaks quote validation), merged or
  split edge lines, invented nodes.
- **Row 2 Workflow read:** Background: THE holistic read — runs before extraction;
  its map directs extraction and feeds the business-model merge; quality here caps the
  whole system's understanding. Job: read all chunks IN ORDER and emit the source's
  complete workflow topology. Input: full ordered chunk text (windowed sequentially if
  huge) + entity registry hints. Output: strict flat JSON lists (nodes, edges, lanes,
  paths, summary, mapKind) per §5.2; every element carries a verbatim evidenceQuote +
  chunkId. Required: strict structuredOutputs, long context. Beneficial: strong
  multi-step reasoning, disciplined ID cross-referencing, no hallucinated elements
  (deterministic validation will drop them and degrade the map). Failure modes:
  invented nodes, paraphrased quotes, dropped terminal stages, schema violations.
- **Row 3 Model merge:** Background: decides whether a new source confirms, refines,
  or contradicts the existing business model — the cumulative-understanding step. Job:
  align source-map elements against existing process elements and emit verdicts only
  (the diff is computed in code). Input: compact rendering of the source map + the
  candidate process version(s). Output: strict flat JSON list of
  `{mapNodeId, modelNodeId|null, verdict}`. Required: strict structuredOutputs.
  Beneficial: cheap, fast, consistent entity/label matching. Failure modes:
  over-matching distinct stages, under-matching renamed stages, schema violations.
- **Row 4 Claim extraction:** Background: produces the atomic evidence layer; every
  claim needs an exact verbatim quote from one chunk; runs per window, highest call
  volume of the ingestion passes. Job: extract one canonical claim per visible map
  element + genuine extras. Input: chunk window + injected workflow map (guidance
  only) + correction lessons. Output: strict claim-candidate schema with exactQuote.
  Required: strict structuredOutputs. Beneficial: verbatim quoting discipline, recall
  across claim types, speed/cost (per-chunk volume). Failure modes: paraphrased quotes
  (mass rejection), near-duplicate flooding, missed conditional branches. Current
  seeds are the 2026-06-26 live bake-off result (54 vs 12 claims for gpt-4.1-mini).
- **Row 5 Deep synthesis:** Background: the consultant voice — writes recommendation
  narratives from analyzer findings (§4.7) AND Brain section drafts from approved
  claims + process versions; low volume, but output is STORED and served, so quality
  compounds. Job: long-form grounded synthesis citing only supplied IDs. Input:
  process version + analyzer findings + supporting claims (recommendations); domain
  claims + process context (Brain). Output: strict flat JSON for recommendations;
  validated narrative for Brain. Required: strict structuredOutputs, long context.
  Beneficial: best reasoning within cost policy, citation discipline, consultant-grade
  prose. Failure modes: fabricated IDs (deterministically rejected), generic
  McKinsey-speak unmoored from evidence, missed cross-process implications.
- **Row 6 Conversation:** Background: every human-facing surface — chat answers,
  claim-review questions to employees, live meeting interjections. Highest call
  volume in the system; macro-first deliberately makes this a RENDERING job (the
  understanding is precomputed), so it is filled cheap-first (ladder below). Job:
  answer from the supplied process context pack + claims, cite claim IDs, state
  provisional/gap status honestly; or compose short review questions/interjections.
  Input: process context blocks, retrieved claims, conversation history. Output:
  prose (+ light JSON for interjection decisions). Required: none strict (this is the
  one row where Qwen is eligible). Beneficial: citation discipline, latency (live
  interjections), tone, cost at volume. Failure modes: uncited assertions, ignoring
  the provisional label, verbose answers, slow interjections.
- **Row 7 Translation:** Background: zh-CN bilingual layer for the China team;
  evidence quotes are never translated. Job: translate claim summaries and review
  questions. Input/Output: text → translated text. Required: nothing strict; MT
  models reject system roles (already shaped for). Beneficial: MT quality, cost.
  Failure modes: translating quoted evidence, register drift.
- **Row 8 General utility:** Background: leftover cheap tasks (taxonomy cluster
  naming, misc labeling). Job/Input/Output: task-specific small calls, loose JSON.
  Required: json_object mode. Beneficial: cheap. Failure modes: none critical — this
  slot must NEVER be borrowed for pipeline-critical passes (that borrowing caused
  ERR-001).

### 8.2 Conversation row: cheap-first ladder (Albert's cost decision)

Macro-first inverts chat's economics ON PURPOSE: the hard reasoning happens at
ingestion time (workflow read, merge, synthesis — low volume, mid-tier models), so
chat's run-time job shrinks to matching the question to a process, rendering the
PRECOMPUTED narrative, attaching citations, and stating gaps honestly. That is a
rendering-and-discipline task, not a reasoning task — so the conversation row is
filled CHEAP-FIRST, decided by the battery, not by intuition:

1. Run B1–B10 with `claude-haiku-4-5` seated. Score ≥18/20 → Haiku stays primary.
   (Known risks to watch when scoring: citation sloppiness; clumsy synthesis on
   multi-process consultant questions B8/B9.)
2. If it fails, seat `google/gemini-2.5-flash`; same bar.
3. Only then seat `claude-sonnet-5`.

Re-run this ladder whenever the chat prompt or context-pack shape changes materially
(the Stage 6 gate includes the first run). Escalation/de-escalation is an admin
settings change, so trying cheap first costs nothing.

### 8.3 Bake-offs

The seeded orders above are HYPOTHESES. `MODEL_BAKEOFF_SPEC.md` is the complete,
self-contained protocol for validating them empirically (one-element pools, fixtures,
scoring rubrics, recording, safe settings restore). Stage 2 (workflow read, vision),
Stage 3 (extraction re-run), Stage 4 (merge), Stage 6 (conversation ladder), and
Stage 7 (deep synthesis) gates each require their bake-off from that spec.

---

## 9. Implementation stages with verification gates

Work in this order. Each stage ends with: typecheck all packages, the listed gate,
a battery scoring run appended to `evals/macro-first-battery.md`, `HANDOFF.md` updated,
and — when worker behavior changes — a Trigger.dev prod deploy recorded. Do not start
stage N+1 with stage N's gate red. NOTE: the working tree already has uncommitted
changes (macro admin UI, cache work — see `git status` / HANDOFF 2026-07-03); get those
committed/deployed with Albert's sign-off BEFORE Stage 0 so your baseline is clean.

Staging principles (why this order): schema and the §4.8 contract land BEFORE any LLM
work, so a wrong data model can't hide behind prompt-tuning; the merge runs in SHADOW
mode (proposals produced, nothing applied) one full stage before transactional apply
exists, because apply is the highest-risk code in the redesign and deserves its own
stage and gate; backfill and cleanup are separate stages, because cleanup is only safe
after the backfill proves the new model survives real corpus diversity.

- **Stage 0 — Baseline.** Create `evals/macro-first-battery.md`; run B1–B10 against
  current prod chat, score, record (expect ~0s — that's the point). Run BO-0 (ceiling
  benchmark) for its Stage-0 measurement. Snapshot claim/relationship counts for the
  test document. No code changes. *Gate: baseline + ceiling recorded.*
- **Stage 1 — Schema + contract (no LLM work).** ALL migrations §6.1–6.6 (additive),
  `schema.ts` mirrors, RLS, the §4.8 state-machine/transaction contract implemented as
  shared helpers (`packages/oracle-engines/src/model/lifecycle.ts` + apply-transaction
  skeleton with the advisory lock and optimistic-lock check, unit-tested against a
  seeded fixture — no LLM anywhere); settings seeds; the §8 Model Passes table UI
  (new rows, relabels, pools) with empty-state admin pages for the new tables.
  *Gate: migrations applied to prod AND a fresh-DB apply proves idempotency; RLS
  verified (anon denied, service role passes); settings read back single-encoded;
  Model Passes table renders all 8 rows with seeded pools; lifecycle/transaction unit
  tests pass, including the stale-base-version and mid-transaction-error paths.*
- **Stage 2 — Workflow reader.** `source-workflow-read` worker + deterministic
  validation + supersede-on-reingest semantics (§6.1) + token-budget windowing (§5.2);
  rewire `processDocument` to await it before extraction and inject the map (no flag);
  write `macro_health`. Lens fan-out: disabled via its existing kill-switch setting
  this stage; code deleted in Stage 3. Run BO-1 (vision) and BO-2 (workflow read)
  bake-offs. *Gate: re-ingest the test document → validated map with ≥90% of the
  diagram's nodes/edges surviving validation (answer key: `fix_enhancement.md` §2.1);
  re-ingest again → old map `superseded`, exactly one non-superseded map; forced
  reader failure shows in `macro_health`; re-dispatch with same content hash is a
  no-op (§4.8 idempotency).*
- **Stage 3 — Map-directed extraction + dedup + kills.** §5.4; delete lens fan-out and
  outline-injection flag path per §3.2. Keep the OLD extraction path callable behind a
  setting until the Stage 5 gate passes (comparison + emergency fallback while merge/
  review are being proven), then delete it. Re-run BO-4 (extraction — the map-injection
  prompt change qualifies as material). *Gate: test document yields ≤100 promoted
  claims with ≥95% of map elements evidenced by ≥1 claim; zero elements with 3+
  same-element claims; typecheck passes with killed files gone.*
- **Stage 4 — Merge in SHADOW mode.** Tables already exist (Stage 1);
  `business-model-merge` produces proposals — NOTHING applies, not even `confirm`
  (auto-apply is switched on in Stage 5). Read-only admin list of proposals. Run BO-3
  (merge). *Gate: first ingest → `create_process` proposal whose operations reproduce
  the map; re-ingest same doc → `confirm` proposal, not a duplicate process proposal;
  doctored variant (one edge changed) → `refine`/`contradict` touching only that
  edge's neighborhood; re-dispatching the merge produces NO duplicate proposals
  (§4.8 idempotency key).*
- **Stage 5 — Review, apply, versioning (the transactional core).** `/admin/macro`
  rebuilt for proposals (before/after graph diff, per-op claims with quotes, per-claim
  veto, eligibility-failure list); bundle approval per §4.5; §4.8 transactional apply
  live, `confirm` auto-apply switched on; rebase path working. Delete the old
  extraction path after this gate. *Gate: approving the test proposal creates version
  1, approves eligible bundled claims with `model_change_bundle` events, links
  `process_element_claims`; veto → `provisional` element; reject → claims back to
  `pending_review`; CONCURRENCY TEST: two pending proposals on the same base version —
  first applies, second flips `needs_rebase`, rebase yields a correct replacement
  proposal; injected mid-apply error → `failed_apply` with zero partial state.*
- **Stage 6 — Answering inversion.** Chat context per §4.6 with read-time
  verification; `oracle-system.ts` update; Brain re-anchor §5.6. Run BO-6
  (conversation ladder) and BO-0's second measurement. *Gate: battery B1–B7 all score
  2; B10 scores 2; answers cite claim IDs; rejecting a support claim demotes the
  element to provisional in the live answer.*
- **Stage 7 — Consultant layer.** Analyzers + `recommendations` + LLM synthesis +
  `/admin/recommendations`; repurposed `macro_relationships` writers for inferential
  types. Run BO-5 (deep synthesis). *Gate: B8/B9 score 2; every recommendation's
  element/claim citations resolve; a fabricated-ID canary in a test fixture is
  rejected.*
- **Stage 8 — Backfill (its own stage — this is the real-world shakedown).** Re-ingest
  the historical corpus through the new pipeline, BATCHED, not naively: (1) first a
  DRY-RUN REPORT — for the whole corpus, produce maps + shadow proposals without
  apply, and report expected proposal counts per document/domain so Albert can see the
  review load before committing to it; (2) priority order chosen by Albert
  (highest-value domains first); (3) bulk-accept UI action for `confirm` proposals;
  (4) review sessions sized to a human — target ≤10 structural proposals per sitting,
  batches sequenced so early approvals make later merges smarter. Run BO-0's third
  measurement. *Gate: full corpus ingested; no `pending` maps/proposals older than the
  backfill window; full battery ≥18/20; BO-0 ≥80% of ceiling on all three fixtures.*
- **Stage 9 — Cleanup.** ONLY after Albert confirms the backfill: cleanup migration
  dropping dead settings keys + retired tables (§3.3); retire old `macro` slot keys;
  delete `HANDOFF.md` items this supersedes. *Gate: typecheck + drift check clean;
  grep proves no references to killed modules or dead settings keys.*

Rollback posture: Stages 2–3 are shadowable (the old extraction path stays callable
until the Stage 5 gate); Stage 4 is shadow by design (nothing applies); from Stage 5
on, all new tables are additive and rollback = stop the new workers and stop serving
process context (a settings flip). Never half-apply a stage to prod.

---

## 10. Forks in the road — what I would do

- **F1: The reader's map is mediocre on prose (non-diagram) documents.** Do NOT add a
  lens/multi-pass system back. First improve the prompt with 2–3 few-shot examples from
  real corpus docs; if still weak, run the reader per document section (heading-split)
  and merge in code. The failure budget is the `degraded` state — partial maps are
  acceptable, silent compensation subsystems are not.
- **F2: Two sources describe the same process differently.** Never silently overwrite.
  `contradict` proposal + `contradictions` row; the human picks. If sources are
  same-authority and both plausible, model both as alternate paths with distinct
  evidence and let the coverage/consultant layer flag the ambiguity.
- **F3: An element has zero valid quotes (vision transcribed it, extraction can't match
  a quote).** Keep the element as `provisional`, file the coverage gap, move on. Never
  relax the quote validator; never promote map prose to evidence (D1).
- **F4: Should provisional elements appear in chat answers?** Yes, labeled (seeded
  `serve_provisional_process_elements=true`) — a consultant says "I believe X but
  haven't verified it," which is more useful than silence. If Albert objects to any
  unverified content in answers, flip the setting; the code supports both.
- **F5: A source is too big for one reader call.** Sequential windows (chunk order
  preserved), each producing partial flat lists with a carried-forward node-label
  registry; merge + re-validate in code. Never sample, never impact-sort — order IS the
  information (that mistake is why the old macro layer failed).
- **F6: The source isn't a process at all.** Reader returns `map_kind='reference'`;
  pipeline = plain claim extraction, no merge, `macro_health='not_applicable'`. Don't
  force process shape onto reference data.
- **F7: A slot's model underperforms on a specific pass.** First try prompt/few-shot
  fixes; then bake off the other pool members (one-element pools, per the repo
  convention); only add a further dedicated slot if a pass provably needs a different
  capability class than the three defined in §8. Never hard-code a model ID (routing
  lesson, HANDOFF 2026-06-26).
- **F8: Temptation to wire live meeting interjections to the model early.** Don't.
  Live interjections are clamped off by settings and stay that way; the model-aware
  interjection is a post-redesign product decision for Albert.
- **F9: A stage gate keeps failing and a shortcut would pass it.** The gates encode the
  product goal; gaming one (e.g., loosening validation to hit the ≥90% map gate) is
  self-deception. Diagnose with the fixture, fix the real cause, and if the gate itself
  is provably miscalibrated, change it IN THIS DOCUMENT with a changelog entry.
- **F10: You find code this document says to kill being load-bearing for something
  unlisted.** Trace the dependency, add it to §3's tables with its disposition, note it
  in the changelog. Do not quietly keep the dead subsystem alive.

---

## 11. Invariants (extended from `fix_enhancement.md` §6.5 — all still binding)

1. Atomic claims: exact-quote validation against one chunk/message. Maps, narratives,
   proposals, and recommendations are never quotable evidence.
2. Read-time verification: any served structure (process element, relationship,
   recommendation) re-checks its supporting claims are `approved` at read time;
   non-approved support ⇒ provisional handling per settings. (Pattern:
   `approved-relationships.ts`.)
3. New tables: RLS enabled, no anon policies, service-role access only.
4. Vector indexes: `ORACLE_RUN_VECTOR_INDEXES=1` gated.
5. Hand-written SQL owns the new tables; Drizzle must not re-emit them.
6. LLM outputs may only reference supplied IDs; deterministic code verifies before
   persisting. Fabricated IDs ⇒ drop the element + log, never guess-repair.
7. No new Trigger.dev SCHEDULED tasks (10/10 limit) — all new workers are
   event-dispatched.
8. Commit to `main` / push / prod-migrate only with Albert's explicit go-ahead;
   never run prod migrations from local env without overriding `DIRECT_URL`
   (`.env.local` points at the OLD Supabase project — see HANDOFF).

---

## 12. Operational constraints & environment gotchas

- Prod DB: Supabase `eqccjfbyrywsqkxxpjvg`, session-pooler URL in 1Password ("Supabase
  DB Direct URL - The Oracle (CURRENT PROD)"). Supabase MCP allowed for reads +
  hand-written idempotent SQL.
- Workers: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`; deploy via CLI/MCP; record
  each deployed version in `HANDOFF.md`.
- Use `corepack pnpm` (plain `pnpm` is not on PATH on this machine).
- CRLF: generated-migration hash drift gotcha (HANDOFF 2026-06-26) — hand-written SQL
  avoids it; keep it that way.
- Model facts you must not relearn the hard way: Qwen = no strict json_schema;
  Gemini rejected NESTED schemas (`400 too-complex`) — hence D6; OpenAI strict mode
  requires optionals as nullable + all-keys-required (already handled in
  `openai-adapter.ts`).

## 13. Glossary

Claim, quote validator, chunk — see `fix_enhancement.md` §6.1. New terms: **source
workflow map** (§4.2, per-source immutable topology), **business process / version /
node / edge / path** (§4.1, durable cross-source model), **model change proposal**
(§4.3/6.4, the reviewable diff), **bundle review** (§4.5), **provisional element**
(no approved supporting claim), **battery** (§1 acceptance questions B1–B10).

## 14. Changelog

- 2026-07-06 (Claude, Fable 5): Initial version. Supersedes `fix_enhancement.md` as the
  forward plan (that doc remains the diagnosis record and ground-truth workflow read).
- 2026-07-06 (Claude, Fable 5), after Albert's model-policy review: Rewrote §8 —
  replaced the single `macro` slot with three slots (`workflow_read`, `model_merge`,
  `consultant`), each with seeded default + bake-off candidate list; added Albert's
  cost policy (no premium-tier models); made explicit that model names are seeded
  defaults, never code dependencies. Clarified D6's rationale (model-agnosticism, not
  model accommodation). Updated F7 and all `macro`-slot cross-references; the old
  `macro` slot settings retire in Stage 7.
- 2026-07-06 (Claude, Fable 5), second model-policy pass: Expanded §8 to cover every
  LLM pass including human-facing slots (interview, live interjections, translation,
  general utility, brain synthesis). Added the "chat cheap-first ladder" (Albert's
  decision): Haiku → gemini-2.5-flash → Sonnet, promoted only on battery failure
  (≥18/20 bar), re-checked when the chat prompt/context shape changes. Rationale:
  macro-first precomputes understanding at ingestion time, so run-time chat is a
  rendering task and should be filled by the cheapest model that passes the battery.
- 2026-07-06 (Claude, Fable 5), third model-policy pass (Albert's settings-UI
  requirement): §8 rewritten around the consolidated 8-row "Model passes" admin
  settings table — primary + 2 fallbacks per row, seeded (never hard-coded), Copy job
  brief per row with content spec (§8.1). Consolidations per Albert: consultant +
  Brain synthesis share the existing `synthesis` slot (no `default_consultant_route`);
  chat + review questions + interjections share the interview slot relabeled
  "Conversation" (keys unchanged). Verified against code: chat already resolves
  `default_interview_route` (chat/route.ts:9); brain-synthesis already resolves slot
  `synthesis` (brain-synthesis.ts:759). Added `MODEL_BAKEOFF_SPEC.md` (§8.3) as the
  empirical validation protocol; stage gates reference it.
- 2026-07-06 (Claude, Fable 5), cross-source-context pass (Albert's questions): Added
  the reader "referents, NOT structure" rule to §5.2 (referent pack for acronym/lane
  resolution; existing process graphs withheld from the reader to avoid harmonizing
  away contradictions — full model context arrives at merge). Made merge shortlisting
  domain-scoped in §4.3 (domains filter first, embeddings rank second) backed by the
  new `process_top_domains` table in §6.2 — a licensing source is never analyzed
  against logistics processes. Added BO-0 (pipeline ceiling benchmark vs. frontier
  chat apps on three modality fixtures: swimlane image, licensing prose doc, ClickUp/
  Cloudflare-D1 data export) to `MODEL_BAKEOFF_SPEC.md`, run at Stages 0/2/5/7 with a
  ≥80%-of-ceiling target and a regression alarm.
- 2026-07-06 (Claude, Fable 5), Codex-review integration (Albert directed adopting
  the "Where Codex is right" findings; Codex CLI reviewed both docs in full): NEW
  §4.8 state-machine + transaction contract — exhaustive status enums (proposals gain
  `needs_rebase`/`superseded`/`failed_apply`), transactional apply with advisory lock
  + optimistic lock on `current_version_id`, rebase path, per-worker idempotency
  keys, bounded retries/poison-job handling. §4.5 rewritten: bundle approval now runs
  per-claim ELIGIBILITY checks (quote valid, role matches element, no open
  contradiction, not a canonical duplicate) instead of blanket auto-approval. §4.8
  adds CROSS-source canonical dedup (newcomers link `corroborating`). §6.1: maps
  supersede, never replace (audit trail). §6.2: `claim_status_at_link` is audit-only.
  §4.3/§6.5: `merge_candidate_top_k=5` internal shortlist, narrow before the LLM.
  §5.2: `workflow_read_max_estimated_input_tokens` windowing guardrail. §9 restaged
  0–9: schema+contract land BEFORE any LLM work (Stage 1); merge runs in SHADOW mode
  (Stage 4) before transactional apply gets its own stage and concurrency gate
  (Stage 5); old extraction path retained until the Stage 5 gate; backfill (Stage 8,
  batched with dry-run report + bulk-accept confirms + human-sized review sessions)
  split from cleanup (Stage 9). All stage cross-references renumbered here, in
  `MODEL_BAKEOFF_SPEC.md`, and in `HANDOFF.md`.
- 2026-07-07 (Codex): Implemented the local Stage 2 foundation in source:
  `workflow-read-v1` flat schema/prompt, `source-workflow-read` worker/service,
  immutable `source_workflow_maps` supersede/validate/fail behavior, awaited
  document-ingestion workflow-read barrier, workflow-map guidance injection into
  extraction windows, and `mapElementRef` extraction linkage. Not deployed or
  live-gate verified yet; see `HANDOFF.md` for exact verification state.
- 2026-07-07 (Claude, Fable 5), Stage 2 deviation-fix specs (Albert directed): after
  reviewing the shipped Stage 2 code, wrote the correct target for the two deviations
  from plan into the sections they belong to, so a later session implements them
  rather than inheriting undocumented gaps. (1) §5.1 — reader-failure fallback: the
  workflow reader must NOT be a hard dependency of ingestion; on total pool failure,
  gated by new setting `require_workflow_map_for_ingestion` (seed `false`), the
  document ingests via the blind-extraction path and completes `degraded` with
  `macro_health='map_failed'`, never silently failing all ingestion. (2) §5.2 —
  entity resolution: the reader may keep emitting raw `ownerName`/`systems` strings
  (deferral is fine), but the merge worker (§5.3) MUST resolve them against `entities`
  / file `entity_proposals` when it writes durable `process_node` owner FKs and
  `process_node_systems`, preserving the no-silent-entity-invention invariant. Both
  are open items in `HANDOFF.md`; neither blocks the Stage 2 gate's map-quality
  measurement, but the fallback should land before Stage 2 is declared green.
- 2026-07-07 (Codex): Ran the live Stage 2 workflow-reader gate. The reader validated
  the canonical swimlane fixture and the fallback chain proved load-bearing:
  `claude-sonnet-5` hit the pre-fix Anthropic temperature request shape, Gemini 2.5 Pro
  rejected the schema as too complex, and `openai/gpt-4.1` succeeded. Updated the
  workflow-read seeded primary/pool order to put OpenAI first. Anthropic request-shape
  handling is now guarded, but BO-2 must be rerun before changing the workflow-read
  primary.
- 2026-07-07 (Codex): Implemented the Stage 2 deviation #2 foundation. Added
  `resolveWorkflowMapNodeEntities()` in
  `packages/oracle-engines/src/model/entity-resolution.ts`, exported it from
  `@oracle/engines`, and covered it in `verify:macro-first`. The workflow reader still
  persists raw `ownerName`/`systems` strings by design; Stage 4's merge worker must call
  this helper when writing durable `process_nodes` / `process_node_systems` so matched
  owners/systems become FKs and unknown names become `entity_proposals` inputs without
  silently inventing entities.
