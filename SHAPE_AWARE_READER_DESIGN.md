# Shape-Aware Source Reader — Design (First Iteration)

Status: APPROVED. Stages 1 and 2 are implemented and real-corpus validated as of
2026-07-13. This supersedes the workflow-only Stage 2 reader in
`MACRO_FIRST_REDESIGN.md` §5.2. Stage 3 (non-process shape readers) is next.

---

## 1. Why (the problem, proven on the real corpus)

The current reader forces EVERY document through one lens — "read it as a process
flowchart" (nodes → edges → lanes → paths). Measured on the real corpus:

- Only the swimlane diagram gets real macro understanding.
- Text business documents produced **403 of 469 claims (86%) with NO structure — 96%
  blind** (fragment soup: `business-process.md` → 207 disconnected claims; a
  responsibilities list → 170).
- Even a process-ish text doc got mangled into a broken graph (31 nodes / 4 edges).

Root cause, confirmed by reading the 5 real documents Albert provided: **a real business
document is a COMPOSITE of several different knowledge shapes.** `business-process.md`
alone contains a process journey, role/responsibility tables, reference tables (licensor
turnaround times, per-product time estimates), rules (cancellation criteria), and a
pain-point list. A single-lens reader mis-reads everything that isn't its lens.

Design principle (the documents say it themselves): *"the business needs to know what
KIND of thing it is looking at before it can manage it."* So: **segment a document into
coherent passages, then read each passage into the structure that fits its shape.**

## 2. What we KEEP (proven; do not rebuild)

The Stage-2 machinery works — we generalize what an "element" is, not the engine:
- Every structural element carries a **verbatim `evidenceQuote` + `chunkId`**, validated
  against the source (the provenance backbone). Never weakened.
- **Element-ref dedup**: claims key on `(documentId, elementRef)`; first valid wins.
- The structure map is injected into extraction as **non-quotable guidance**.
- **Immutable, supersede-not-replace** maps; `job_runs` + `macro_health` observability.
- Coverage measured **per element**, on the *primary* elements of the shape (the swimlane
  lesson: measure the relationships/flow, not every box).

## 3. The shapes (first iteration — 6)

| Shape | Real examples (Albert's corpus) | Primary elements (what a claim is made for) | Structural-only (become graph, not claims) |
|---|---|---|---|
| **process** | swimlane diagram; the 19-step licensed journey in `business-process.md` | transitions/handoffs/branches (edges) | steps (nodes), lanes, paths |
| **responsibilities** | `Licensed Team Responsibilities`; role tables in `business-process.md` | responsibility records (owner→action→object, + system, + trigger) | roles, teams |
| **reference** | `SKU naming convention` tables; licensor turnaround table; product time estimates | attributes + relationships | entities (people, licensors, factories, products, systems) |
| **ruleset** | SKU DO/DON'T rules; cancellation criteria; approval gates; internal-approval policy | rules (scope + condition + requirement/effect + exception) | rule groups |
| **conversation** | the "Book report" Teams transcript; future Teams chats | decisions, assertions, disagreements/open-questions, problems, action items — **PLUS: when the meeting describes/draws a workflow, the segmenter tags that passage as a `process` segment so the flow is reconstructed too** (DECIDED, Albert 2026-07-08) | speakers, the meeting |
| **narrative** | explanatory prose that fits none of the above (fallback) | asserted operational facts | — |

`process` = today's workflow map exactly, so existing behavior is preserved as one shape
(regression-safe). `narrative` replaces today's "empty map → blind extraction" dead-end:
even unclassifiable prose yields structured asserted facts instead of fragment soup.

A single document is a **composite**: it has 1+ **segments**, each with its own shape.
Example — `business-process.md` → process (§5 journey) + responsibilities (§2 roles) +
reference (§6/§8 tables) + ruleset (§9 cancellation) + narrative/problems (§10).

**DECIDED (Albert, 2026-07-08): keep these six, but the shape set is an EXTENSIBLE
REGISTRY — more shapes will be added later.** Build accordingly: a shape is a
registry entry `{ shapeId, elementKinds, relationKinds, primaryElementKinds (for
coverage), extractionDirective, readInstruction }`. Adding a shape must be a new registry
entry + prompt fragment — NOT a schema migration or a change to the reader/extraction
engine. The unified model in §4 already supports this (shape is a discriminator; attributes
are generic), so new shapes cost prompt work, not surgery.

## 4. One unified structure model (not 6 schemas)

To avoid multiplying prompts/migrations, generalize the workflow map into ONE
"source structure map" with discriminators. Kept FLAT (Qwen/Gemini reject nested — D6):
attributes are a fixed set of OPTIONAL scalar fields, never an open nested object.

```
map:        { mapId, documentShape (dominant), summary,
              segments: [{ segmentId, shape, title, summary, chunkIds }] }
elements[]: { elementId, segmentId, shape, elementKind, label,
              # flat optional attribute fields, only those relevant to the shape:
              owner?, role?, action?, object?, trigger?, system?,
              entityType?, attrKey?, attrValue?,
              scope?, condition?, effect?, exception?,
              decisionStatus?, contested?, speaker?,
              evidenceQuote, chunkId }
relations[]:{ relationId, segmentId, fromElementId, toElementId, relationKind,
              condition?, evidenceQuote, chunkId }
```

Mapping proof: the current workflow map is exactly `shape='process'`,
`elementKind ∈ {step, decision, approval_gate, ...}`,
`relationKind ∈ {sequence, handoff, branch, loop, exception}`. Strict generalization.

## 5. Reader flow (two passes for reliability)

The coverage lesson (LLMs under-enumerate in one big pass) argues for smaller scopes:

1. **Segment + classify** (one cheap call): split the document into coherent segments and
   assign each a shape. Output: the `segments[]` list. Every persisted source chunk must
   be covered. A genuinely composite chunk may appear in multiple differently shaped
   segments with focused titles/summaries; this is required by the real 4,000-character
   chunks, which often contain both role duties and an embedded process, or both lookup
   examples and rules. Evidence still points to the original chunk, so provenance is
   unchanged.
2. **Per-segment structured read** (one call per segment, parallelizable): read each
   segment into elements/relations using the shape-specific instruction set. Smaller
   scope per call → far fewer tail omissions than one monolithic pass. Every element still
   gets a validated verbatim quote.

**DECIDED (Albert, 2026-07-08): two-pass is the approach** (reliability over per-document
cost — it directly fixes the under-coverage ceiling). Because the pass-1 segmenter assigns
a shape per segment, a single transcript naturally yields BOTH `conversation` segments AND
`process` segments (the decision above) — no special-casing needed. A one-pass mode may
still be kept behind a flag for trivially small/simple docs, but two-pass is the default.

## 6. Map-directed extraction, per shape

Extraction already keys on `mapElementRef`; only the DIRECTIVE changes per shape:
- process → one claim per transition/branch.
- responsibilities → one claim per responsibility record.
- reference → one claim per attribute/relationship.
- ruleset → one claim per rule.
- conversation → one claim per decision/assertion/problem/action-item.
- narrative → one claim per asserted fact.
Dedup by `(documentId, elementRef)` unchanged. Non-map "extra" facts still allowed.

## 7. Coverage gate, per shape (deterministic)

Coverage = % of a segment's **primary** elements (col 3 of §3) evidenced by ≥1 claim.
Structural-only elements (nodes, entities) are NOT in the denominator — they become
business-model graph nodes at merge (Stage 4). Target per segment ~90–95% of primary
elements. This fixes the swimlane mis-measurement generally, for every shape.

## 8. Schema / DB

- Generalize `source_workflow_maps` → a structure-map table (add `shape`, `segments`,
  generic `elements`/`relations` json; keep process rows readable). Hand-written
  idempotent migration; mirror in `schema.ts`; never let Drizzle re-emit.
- `claims.map_element_ref` already generic (points at an `elementId`) — unchanged.
- Deterministic per-shape coverage findings → `gaps` (§5.7).

## 9. Staged build (each stage regression-safe, validated on the 5 real docs + a transcript)

1. **DONE 2026-07-09:** Generalize the schema + reader to the unified model with ONLY
   `process` wired; reproduced the swimlane result at ~96% relation coverage.
2. **DONE 2026-07-13:** Add segmentation (pass 1). The strict six-shape contract,
   deterministic source-coverage validator, bounded repair retry, immutable persistence,
   and process-only pass-2 compatibility are implemented. All five named real files plus
   a production-ingested Teams transcript passed `verify:shape-segmentation-real`; see
   `evals/shape-aware-stage2.md`.
3. **Add the non-process shapes** (responsibilities, reference, ruleset, narrative) +
   their extraction directives + per-shape coverage. Validate on the real text docs
   (target: the responsibilities list and `business-process.md` go from ~96% blind to
   mostly structured).
4. **Add conversation shape** — validate on the "Book report" transcript.
5. Keep `map_directed_extraction_enabled` + the old blind path as fallback until every
   shape passes its coverage gate; then retire the blind path (macro-first Stage 5 gate).

## 10. Decisions (Albert, 2026-07-08) — RESOLVED

1. **Shapes:** keep the six, but build them as an **extensible registry** (more shapes
   later) — see §3.
2. **Reading approach:** **two-pass** (segment, then read each segment) — see §5.
3. **Conversation depth:** capture decisions/problems/action-items/assertions **AND
   reconstruct any process described mid-meeting** (segmenter tags those passages
   `process`) — see §3/§5.
4. **Composite handling:** per-segment reads (implied by two-pass) — confirmed.

Remaining minor question (non-blocking): keep `responsibilities` and `ruleset` separate
(current plan) vs merge — left separate for now; the registry makes it cheap to revisit.
```
