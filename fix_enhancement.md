# Fix Enhancement: Holistic Macro Understanding of Structured / Diagram Sources

## About this document (READ THIS FIRST)

**Authorship.** The original diagnosis was written by **Codex**. On **2026-07-03**, **Claude** expanded it into this comprehensive version.

- Codex's original text is preserved **verbatim** under **§7 "Original diagnosis (Codex)"**. Nothing Codex wrote has been deleted.
- Where Claude disagrees with a specific Codex statement, the Codex line is kept and immediately followed by a callout:
  > **⚠️ Claude disagrees with this** — <reason> — <what is actually correct>
- Everything in **§0–§6 and §8** is new material added by Claude. Claude-added prose is factual and code-verified; where a claim could not be verified from source alone, it is explicitly flagged.

**Evidence basis.** This analysis is grounded in:
- The most recent full pipeline run of the target document, cached at
  `.cache/macro-comparison/9d09fa89-3a46-465e-a98b-837287c9e22a/rerun-20260702T220901Z/`
  (document **"Pop Creations Flow 12112025 (1).png"**, id `9d09fa89-3a46-465e-a98b-837287c9e22a`).
- The current worker/prompt/schema source in `apps/workers/`, `packages/ai/`, `packages/oracle-engines/`, and `packages/db/`.

**~~One honesty caveat~~ — RESOLVED 2026-07-03 (Trigger logs pulled).** The macro-relationship and coverage workers **threw exceptions** — they did not return empty. Codex's "repeated failures" is **confirmed**. The exact errors and their root cause are in **§5 Bug H (the proximate cause) and Bug I**. In short: the `general` auxiliary route resolves to `qwen/qwen3.7-max`, Qwen cannot reliably emit the nested output schema (it omits the required top-level `relationships`/`findings` array), and the single-pick auxiliary slot has no working fallback, so the task hard-fails with `AllCandidatesFailedError`. An earlier worker version additionally failed on a broken cross-source SQL query before the model call.

---

## 0. What this application is supposed to do, and how

### 0.1 The product goal

The Oracle is an **evidence-backed knowledge graph** for POP Creations / Spruce Line. For a source like the Pop Creations swimlane flow diagram, the job is **not** to emit a pile of isolated facts. It is to **understand the source holistically**:

- the **complete lifecycle** of a licensed product from buyer concept → design → costing → factory sourcing → licensor approval → sampling → PPS audit → production → shipment to the US;
- **who owns each stage** (swimlane / role);
- the **order and dependencies** between stages;
- the **conditional branches** (new vs. existing product; audit pass vs. fail; licensor comment about legal/packaging vs. creative design);
- the **approval loops** (licensor revision cycles, re-sampling);
- the **systems of record** and data-entry points (DFlow, ColdLion, MasterData, ClickUp, PPT);
- and the **coverage gaps** where the diagram shows something the extraction missed.

The failure this document exists to fix: **the Oracle currently reads the diagram as ~240 disconnected "A → B" claims and assembles zero of them into a workflow. It sees every tree and no forest.** A user cannot ask "what is the full path of a product?" or "what changes for new vs. existing products?" because nothing in the system holds the assembled process.

### 0.2 The non-negotiable trust contract (why this is hard)

The Oracle's core guarantee is **quote-level provenance**: every durable atomic claim must cite an **exact verbatim quote** from one persisted `document_chunk` (or one source message). This is enforced deterministically by the quote validator and is **load-bearing** — it is why the Oracle's answers are auditable.

Holistic understanding must be added **without breaking that contract**. The rule (from `DECISIONS.md` `D-macro-understanding-boundary`):

- **Source outlines / workflow reads are guidance, not evidence.** They can help the extractor interpret structure; they can never be quoted or become a claim by themselves.
- **Atomic claims still require exact quotes.**
- **Durable macro relationships cite approved *claim IDs*, not raw model interpretation**, and any consumer (Brain, chat, MCP) must verify every support claim is `approved` **at read time**.

### 0.3 How the pipeline is *supposed* to work today

```
image upload
  → vision transcription (Pass 1): image → faithful text topology
        nodes  [Shape/Color: "label"]
        edges  [A] --(condition)--> [B]
        swimlanes ### headers
  → structure-aware chunking → document_chunks (persisted, embedded)
  → source-outline worker: reads chunks, produces a provisional macro read
        (source_outlines + source_groups + recommended lenses)
  → document-ingestion broad extraction pass: chunk → extract → quote-validate → promote
  → budgeted lens fan-out: document-lens-extraction × N (per source group × lens)
  → macro-relationship-extraction: infer cross-claim relationships from validated claims
  → source-coverage-audit: compare outline expectations vs. what got extracted
  → Brain / chat consume APPROVED claims + APPROVED macro relationships
```

### 0.4 The one-sentence thesis of the fix

**The diagram already encodes the macro structure (sequence, branches, loops, ownership, handoffs). The vision pass captures it. The pipeline then destroys it at the "flatten to atomic claims" step, and asks the macro layer to *rediscover* it from a truncated bag of prose. Stop rediscovering — capture the graph once, persist it as a first-class artifact, derive claims from it, and generate macro relationships from its structure.**

---

## 1. Observed behavior (the concrete run)

Run: `document 9d09fa89-…`, cached rerun `rerun-20260702T220901Z` (Trigger run set from 2026-07-03T02:16Z).

**Jobs that ran (from `job-outputs-after-rerun.json`):**

| Job | Status | Output |
|---|---|---|
| `document-ingestion` (broad pass) | complete | 3 chunks, 53 staged, 53 promoted |
| `source-outline` | complete | 10 groups, 30 group items, lens fanout `triggered: 4`, `macroFollowups: { triggered: true }` |
| `document-lens-extraction` × 4 | complete | each ~52–53 staged, ~46–48 promoted |
| `macro-relationship-extraction` | **absent from job trace** | — |
| `source-coverage-audit` | **absent from job trace** | — |

**Final numbers (from `comparison-summary.md`):**

- Old GUI baseline claims: **122**. New post-rerun claims: **241** (net **+119**).
- New claims came from only **56 unique evidence quotes** (old: 66). → ≈**4× duplication**.
- **`macro_relationships` for the document: 0.**
- **`source_coverage_findings` for the document: 0.**
- Only **6** of 241 claims auto-approved; the rest are `pending_review`.

**Lens fan-out coverage (from the outline job's `lensFanout.skipped` list):**

- The 4 lens calls that ran were **all the `handoffs` lens**, on groups sorted 0–3 (Buyer Engagement, Creative Direction, Design Execution, Costing).
- Groups sorted 8–9 — **"SKU Creation & System Entry"** and **"Mass Production & Shipment"** — were dropped entirely (`group_skipped_over_max_8`).
- Every other lens (exceptions, dependencies, systems, ownership, risk) on every group was skipped (`model_call_count_exceeds_4`).

**Vision transcription quality (from the claim quotes):** the transcription is **excellent** — every branch, loop, and terminal stage in the diagram appears *somewhere* as an isolated edge quote (`If Audit: Pass`/`If Audit: Fail`, `New Products`/`existing products`, licensor legal-vs-creative branches, `Ship to US`, etc.). The raw material for holistic understanding was captured. It was simply never assembled.

---

## 2. Errors & shortcomings in the Oracle's analysis

### 2.1 The workflow, as it actually is (Claude's holistic read, reconstructed from the Oracle's own transcription)

> Note: the diagram image itself was not attached to the working session; this reconstruction is from the Oracle's vision transcription embedded in the claim quotes. It is therefore a read of *what the Oracle saw*, which is the correct baseline for judging the macro layer.

One continuous **licensed Edge Home product lifecycle**, ~9 swimlanes (Sales, Creative Direction, Creative Designers, Technical Designers, Junior Designers, Sourcing, Factories, Licensor / Licensing Team, PM; Carlos for SKU creation):

1. **Buyer engagement (Sales):** call/email or buyer meeting/trendboards → *Design Request Format*; kickoff → style-guide card.
2. **Creative direction:** Design Request Format → pre-brief + confirm size → Brief → Debrief → Costing-sheet approval → Designs Approval.
3. **Design execution:** style guides → assets/compositions selection → costing-sheet / tech-pack elaboration.
4. **Costing & factory sourcing:** upload to DFlow RFQ code → RFQ to factories → details & limitations → ask about limitations → details in ClickUp → **Price**. Branch: "if Sales confirms buyer approves the price" → Designs Approval. Price → **SKU creation (DFlow, ColdLion, MasterData, ClickUp)** by Carlos.
5. **New-vs-existing branch:** *new products* → concept image to ColdLion/ClickUp; *existing products* → jump to Mass Production.
6. **Tech pack + revision loop:** Designs Approval → Design in progress → art files + packaging → Tech Packing → Tech Pack Approval → Submit Authorization. Loop: revisions → back to Designs Approval.
7. **Licensor concept approval:** submit to Licensor → licensor's comment. Branch: "legal line/packaging" → Technical (tech-pack update → resubmit); "creative design" → Creative (revisions → loop). Repeats until approved.
8. **Sampling & PPS audit:** Buyer's approval → picks to PM → sample request → Junior Designers assemble factory files → samples → internal approval → **PPS Audit**. Branch: **pass** → PPS submit to licensor → PPS approved; **fail** → re-sampling loop.
9. **Order & production:** PPS approved → samples shipped to US → buyer sample approval → **order** → **Mass Production** → professional photos → photos approval → **Ship to US**.

Systems: DFlow, ColdLion (ERP), MasterData, ClickUp, PPT. Gates: buyer price, designs, costing, tech pack, licensor concept, PPS audit pass, PPS approval, sample approval, order.

### 2.2 Enumerated shortcomings in the Oracle's output

1. **Zero assembled lifecycle.** `macro_relationships = 0`. The system holds 241 edge-facts and no representation that they form one process.
2. **Branches and loops are not modeled as first-class.** They exist only as isolated edge quotes carrying a condition label; nothing connects "If Audit: Fail" back into the sampling loop, or the new-vs-existing fork into two paths.
3. **Ownership / swimlane structure is not retained at the macro level.** Owners appear per-edge; there is no per-stage or per-swimlane ownership model.
4. **Terminal stages are underrepresented.** The lens budget skipped "SKU Creation & System Entry" and "Mass Production & Shipment" entirely; SKU creation by Carlos, present in the old baseline, was dropped in the rerun.
5. **Massive duplication.** 241 claims from 56 unique quotes — the same edge restated as `dependency`, `process_rule`, and `policy` variants inflates the review queue and drowns any lifecycle signal.
6. **No self-awareness of the failure.** `source_coverage_findings = 0`, and the document is marked `complete`. The system does not know (or surface) that its holistic layer produced nothing.

---

## 3. The poor code logic causing these shortcomings (root-cause map)

Each row: symptom → the code that causes it → why it is wrong. (Bugs marked **★** are **not** in Codex's original diagnosis; see §5 for detail.)

| # | Symptom | Code location | Why it fails |
|---|---|---|---|
| 1 | Only 4 lens calls ran, all the *same* lens (`handoffs`), only on early groups | `apps/workers/src/lib/document-lens-budget.ts:185–189` (lens-major sort) + `:193` (`callLimit`) + `:142` (group cap) | ★ The candidate sort is **lens-major**, so the 4 calls are spent on the single highest-priority lens across groups 0–3 instead of covering the workflow. Combined with `maxGroupsPerDocument=8` dropping the terminal groups. |
| 2 | Macro layer produced 0 relationships — **the task THREW (verified from Trigger logs)** | **Proximate cause: `general`→`qwen/qwen3.7-max` returns output missing the required `relationships` array → `AllCandidatesFailedError`, no fallback (★ Bug H).** Contributing: `macro-relationship-extraction.ts:92` (topology stripped from prompt) + `:208` (`LIMIT 40`, `impact DESC`) | The model call never returns a valid object (Qwen can't emit strict json_schema; single-pick slot has no fallback). Even if it did, the input is de-structured prose truncated to 40 and reordered by impact. |
| 3 | Macro/coverage failures invisible; doc still `complete` | `apps/workers/src/trigger/source-outline.ts:284–294` (fire-and-forget `.catch(warn)`); neither followup writes `job_runs` | ★ Best-effort dispatch + missing `job_runs` rows mean a zero/failed macro pass looks identical to "nothing needed to run." No document-level `macro_health`. |
| 4 | Even a *working* macro layer would stay invisible | `packages/oracle-engines/src/macro/lifecycle.ts:16–18` | ★ Generated relationships are born `blocked_pending_support` unless **all** support claims are already `approved`. With 235/241 claims `pending_review`, the holistic layer is gated behind mass approval of a noisy queue. |
| 5 | Coverage audit can never assess macro coverage | `source-outline.ts:284 & 293` (both followups fired together); `source-coverage-audit.ts:95–104` reads macro rows | ★ Race: coverage is dispatched concurrently with macro extraction, so its `macro_relationships` read is (structurally) empty. |
| 6 | 241 claims / 56 quotes | broad pass + lens passes extract the same chunks; candidate-hash dedup keys on canonicalized **summary text** | The same edge phrased three ways hashes differently → all promote. No edge-level dedup key. |
| 7 | Endgame concepts thin/missing | `document-lens-budget.ts:142–150` group cap | Terminal groups dropped before lens selection. |
| 8 | Extraction never even tries to be holistic | `packages/ai/src/prompts/extraction-system.ts:318` | Prompt explicitly says "Prefer small, reviewable operational claims over broad document summaries." Correct for chat provenance; wrong as the *primary* representation of a swimlane. No workflow-map artifact exists anywhere. |

---

## 4. Required outcome (acceptance test for "fixed")

The Oracle is fixed for this class of document only when it can answer, grounded in evidence but **reading like an understanding of the workflow**:

- "What is the full path of an Edge Home licensed product from concept to shipment?"
- "What changes for new products versus existing products?"
- "Where does licensor approval happen and what loops can occur?"
- "What has to happen before mass production?"
- "Which teams own each stage?"
- "Which systems are updated, and when?"
- "Where can the process branch or fail?"

---

## 5. Additional bugs & enhancements NOT in Codex's original diagnosis

These were found by Claude on 2026-07-03 by reading the code against the cached run. Each is code-verified.

### ★ Bug A — The lens budget's `min()` clamp is inert at the seeded settings (Codex's headline budget fix does nothing)

`document-lens-budget.ts:193`:
```ts
const callLimit = Math.min(budget.maxModelCallsPerDocument, budget.maxLensesPerDocument);
```
Migration `81_macro_lens_fanout_settings.sql` seeds **both** `macro_max_lens_model_calls_per_document = 4` **and** `macro_max_lenses_per_document = 4`. So `min(4,4) = 4`. **Removing the clamp changes nothing at current settings.** The observed 4-call cap is caused by the budget *values*, not the clamp. (The clamp is still a *latent* bug — it would silently cap if the two settings ever diverged — but it is not the cause of the observed behavior.)
**Fix:** raise the two budgets to cover the workflow, and fix the sort (Bug B) and group cap; treat the clamp removal as cleanup, not the fix.

### ★ Bug B — Lens-major sort spends the whole budget on ONE lens

`document-lens-budget.ts:185–189` sorts candidates by lens priority first, group second. With `callLimit=4`, the 4 selected calls are all `handoffs` on groups 0–3 (the skip log confirms every non-`handoffs` candidate was dropped as `model_call_count_exceeds_4`). So exceptions, systems-of-record, ownership, and risk lenses **never run at all**, and only the first 4 of 10 groups get any lens.
**Fix:** budget by **coverage** — guarantee each major stage gets ≥1 pass and diversify lenses per stage — rather than draining the budget on the top-priority lens.

### ★ Bug C — The lens idempotency guard omits the terminal status (`'complete'`) → re-runs re-duplicate

`document-lens-budget.ts:213–226` (`documentHasCompletedLensBatch`) filters:
```sql
AND status IN ('pending_model', 'model_complete', 'validation_complete')
```
But the lens worker's **terminal** batch status is `'complete'` (`document-lens-extraction.ts:880, 901`). The function name promises "has a completed batch," yet its WHERE clause catches every state **except** the final one. So a fully-finished lens batch is invisible to the guard, and re-triggering the same document (same `sourceHash`) re-extracts and re-promotes duplicate lens claims.
**Fix:** include `'complete'` (and decide explicitly whether `'failed'` should also short-circuit or allow retry).

### ★ Bug D — Generated macro relationships are born `blocked_pending_support` → the holistic layer is invisible until mass approval

`packages/oracle-engines/src/macro/lifecycle.ts:16–18`:
```ts
export function statusForGeneratedMacroRelationship(statuses) {
  return allMacroSupportApproved(statuses) ? 'pending_review' : 'blocked_pending_support';
}
// allMacroSupportApproved = every support claim status === 'approved' (and ≥2 of them)
```
On this diagram, 235/241 claims are `pending_review`. So **even if macro extraction worked perfectly, every relationship would be born `blocked_pending_support`**, and the read-time serving helper excludes anything whose support isn't all `approved`. The holistic layer therefore cannot appear in Brain/chat/MCP until an admin approves the underlying flood of near-duplicate atomic claims. **Fixing macro *generation* alone will not make the Oracle "see the big picture."** This coupling is the deepest systemic issue and must be addressed alongside dedup and triage.
**Fix direction:** make dedup aggressive enough that the approval queue is small; consider allowing a relationship to be *reviewable* (visible in admin) while `blocked_pending_support`; and prioritize approving the small set of canonical edge claims that back high-value relationships.

### ★ Bug E — `macro_auto_max_support_claims` is a dead tunable above 40

`macro-relationship-extraction.ts:262` clamps the setting to `min 2, max 80`, but the support query hard-codes `LIMIT 40` (`:188` and `:209`) and the later `.slice(0, maxSupportClaims)` (`:283`) cannot recover rows the SQL never returned. Anyone raising `macro_auto_max_support_claims` to 60/80 to give macro more of the graph is **silently capped at 40**.
**Fix:** interpolate the setting into the SQL `LIMIT`, or (better, per §6) stop feeding raw claims and feed the workflow map.

### ★ Bug F — `maxLensesPerDocument` is applied per *group*, not per document

Despite the name, `document-lens-budget.ts:166` uses `budget.maxLensesPerDocument` as a **per-group** lens cap. This mislabeling is part of why the budget math is confusing and why Bug A's clamp looks meaningful when it isn't.
**Fix:** rename to `maxLensesPerGroup`, or make the semantics match the name, and document the intended budget model.

### ★ Bug G — Coverage-audit ordering makes it structurally blind to macro relationships

Because §3 #5's race fires coverage and macro concurrently, `source-coverage-audit.ts:95–104` reads `macro_relationships WHERE source_outline_id = X` before macro extraction could commit, so it always sees 0 relationships and can never report "macro relationships are missing."
**Fix:** sequence coverage **after** macro extraction (pipeline barrier, not fire-and-forget).

### ★ Bug H — THE PROXIMATE CAUSE of `macro=0 / coverage=0`: the `general`→Qwen route can't emit the schema, and the auxiliary slot has no fallback (verified from Trigger logs, 2026-07-03)

This is the actual reason the holistic layer is empty, confirmed from the prod run logs for document `9d09fa89-…` on worker `20260703.2`:

```
AllCandidatesFailedError: All model candidates failed for general:
  qwen_3_7_max_extraction_eval (qwen/qwen3.7-max):
  [{ "code":"invalid_type", "path":["relationships"], "message":"expected array, received undefined" }]
```
Coverage audit fails identically at `path:["findings",0,…] expected string`.

Chain of causation:
1. Both `macro-relationship-extraction` and `source-coverage-audit` resolve their model via the **`general` auxiliary route**, which in prod is **`qwen/qwen3.7-max`**.
2. Qwen uses `response_format: json_object` + Zod validation — **not** strict `json_schema** (see `DECISIONS.md` D12 and `docs/architecture.md`: Qwen "What it CAN'T do today: Strict json_schema"). On the deep nested `MacroRelationshipOutputSchema` / `CoverageAuditOutputSchema`, Qwen returns an object that **omits the required top-level array**. Zod rejects it.
3. The `general` slot is a **single-pick auxiliary route with no working fallback**. The same trace shows `PROVIDER UNAVAILABLE: "deepseek" was NOT registered (DEEPSEEK_API_KEY is not set)`, so there is no second candidate. One malformed Qwen response → `AllCandidatesFailedError` → the whole task throws (it retried 3×, ~3.7m, $0.0075, failing identically each time).

**Implication:** every input-quality fix in this document (workflow map, more support claims, better dedup) is **necessary but not sufficient** — with the `general`→Qwen route, macro/coverage would still hard-fail on schema. This is the first thing to fix.
**Fix (any of, ideally the first):**
- Route macro/coverage to a **strict-json-schema-capable** model — Vertex/Gemini `responseJsonSchema` or OpenAI `json_schema strict` — instead of Qwen `json_object`. (Consider a dedicated `default_macro_route` rather than borrowing `general`.)
- And/or give the auxiliary slot a **real fallback pool** so one malformed structured-output response doesn't fail the task.
- And/or add a **schema-repair sub-pass** on structured-output validation failure.
- Set `DEEPSEEK_API_KEY` in the worker env, or stop advertising deepseek as a phantom fallback.

### ★ Bug I — The cross-source support-claims SQL query failed outright on an earlier worker version

On worker `20260703.1`, `macro-relationship-extraction` failed **fast (~4.5s, $0.0002, before any model call)** with `Error: Failed query:` on the `cross_source` CTE (`seed_claims` / `seed_domains` / `related_claims`) in `loadSupportClaims` (`macro-relationship-extraction.ts:146`). Payload `relationshipScope: "cross_source"`. It appears fixed in `20260703.2` (which now reaches the model), but the query bug was real.
**Fix:** confirm the `20260703.2` query actually executes against prod for a `cross_source` payload; add a smoke test that runs the cross-source CTE against a seeded fixture.

### Consolidated fix priority (Claude)

0. **★ Fix the model route first (Bug H).** Nothing else matters until macro/coverage can return a valid object. Move macro/coverage off `general`→Qwen to a strict-json-schema model and/or add a real fallback + schema repair. Confirm Bug I's SQL fix.
1. **Make failure visible** (Bug C observability + §3 #3): write `job_runs` for macro/coverage; add a document-level `macro_health` (`pending | complete | failed | degraded`) surfaced in Admin → Documents. *Cheap, and would have surfaced Bug H months sooner.*
2. **Fix the budget** (Bugs A, B, F + §3 #7): coverage-first budgeting, diversify lenses, stop dropping terminal groups. Also fix Bug C idempotency and Bug E dead tunable.
3. **The real structural fix — a first-class workflow-map artifact** (Codex §7.7, expanded in §6 below): persist the graph, derive claims from it with edge-level dedup, generate macro relationships deterministically from graph structure.
4. **Un-gate the holistic layer** (Bug D): aggressive edge-dedup + triage so the approval queue is small; decide the visibility policy for `blocked_pending_support`.
5. **Sequence the followups** (Bug G): coverage after macro.

### Improvements from the workflow-enhancement analysis to keep

The external `workflow-enhancement-analysis` draft is directionally right, but it must be grounded in this repo's actual schema, worker names, migration conventions, and trust boundary. Keep these ideas; do not copy the draft's invented file/table names verbatim.

#### Keep 1 — Workflow graph / workflow map as a first-class artifact

This is the core architectural change. The Oracle needs a durable representation of the diagram's topology, separate from both `source_outlines` and `claims`.

Minimum graph concepts to preserve:

- `nodes`: visible workflow boxes / decisions / approvals / terminal outcomes.
- `edges`: transitions, handoffs, conditions, loops, and exception paths.
- `swimlanes`: owner roles/teams/systems.
- `paths`: main path, new-product path, existing-product path, audit-fail path, licensor-revision loop, order/production/shipment path.
- `systems`: DFlow, ClickUp, ColdLion, MasterData, PPT, and other systems of record.
- `evidence`: every node/edge must point back to the exact topology line or chunk span that supports it.

Important caveat: the workflow map is **guidance and structure**, not final business truth. It can guide claim extraction and macro generation, but durable claims still need exact quote validation, and durable macro relationships still need supporting claim IDs.

#### Keep 2 — Claim-to-workflow traceability

Claims need to link back to the workflow element they represent, not only to a document chunk. Without this, the system cannot answer whether a stage is covered.

Implementation direction:

- Add linkage at candidate/claim evidence time, not only as model prose.
- Prefer linking to an edge when the claim asserts sequence/handoff/dependency.
- Link to a node when the claim asserts ownership, system entry, approval, or a stage requirement.
- Preserve `document_chunk` evidence as the quote-level source of truth.

This enables direct questions:

- Which claims support `SKU creation`?
- Which claims cover the `PPS Audit` pass/fail branch?
- Which workflow nodes have no claims?
- Which claims are orphaned from the workflow map?

#### Keep 3 — Graph-aware coverage audit

Coverage audit should compare the expected workflow topology against extracted claims and macro relationships. It should not only ask the model for generic "missing stage" findings.

Keep these deterministic finding classes:

- missing node
- missing edge
- missing branch condition
- missing approval gate
- missing swimlane owner
- missing system/data-entry point
- incomplete path
- orphan claim
- duplicate node/edge
- skipped terminal group

The audit should run even if the LLM coverage pass fails. Deterministic graph checks can still mark the document `macro_degraded`.

#### Keep 4 — Deterministic macro derivation from graph structure

Do not ask an LLM to rediscover the workflow from 40 sampled claim summaries when the diagram already encodes the graph.

Generate draft macro relationships from:

- sequential paths
- swimlane handoffs
- branch points
- loops
- approval gates
- terminal outcomes
- systems-of-record transitions

Then attach support claims to those graph-derived macros. If support claims are still pending, the macro can remain blocked from Brain/chat serving, but it should still be visible in admin review as a generated structure needing support approval.

Important caveat: never assign `confidence = 1.0` merely because a relationship was graph-derived. Better language is "deterministic from extracted graph structure"; confidence still depends on transcription quality, edge validation, and supporting claim status.

#### Keep 5 — Coverage-driven lens selection

The current lens fanout spends scarce model calls by static lens priority and early group order. For diagrams, lens selection should be driven by uncovered workflow regions and criticality.

Coverage priority should favor:

- terminal outcomes
- production/shipment stages
- system-entry stages
- approval gates
- branch conditions
- loops/rework paths
- swimlane handoffs

This is more important than simply increasing the lens budget. A larger budget with the same lens-major sort can still waste calls on redundant early-stage extraction.

#### Keep 6 — Diagram-type-aware lens priority

Different structured sources need different extraction priorities.

- Swimlane diagrams: ownership, handoffs, systems, dependencies, branches.
- Flowcharts: sequence, branches, exceptions, approvals.
- SOP text: responsibilities, rules, exceptions, definitions, systems.
- Incident threads: contradictions, chronology, decisions, unresolved gaps.

This should be implemented from actual outline/workflow metadata, not by hard-coding a new lens that does not exist in `EXTRACTION_LENSES`.

#### Keep 7 — Workflow evaluation fixture for this exact diagram

The Pop Creations swimlane must become an eval fixture. The expected output should be a workflow baseline, not just a list of atomic claims.

Score at least:

- node recall
- edge recall
- branch recall
- swimlane/owner accuracy
- system coverage
- terminal path coverage
- duplicate claim rate
- macro relationship coverage
- degraded-status correctness when macro/coverage followups fail

Use offline fixture checks in CI first. Live LLM/provider evals should be optional/manual or separately gated; they should not become a flaky default CI dependency.

#### Keep 8 — Degraded macro-understanding status

If atomic extraction succeeds but macro extraction, workflow-map extraction, or coverage audit fails, the document must not look "fully understood."

Minimum states:

- `macro_pending`
- `workflow_map_failed`
- `macro_failed`
- `coverage_failed`
- `macro_degraded`
- `macro_complete`

The admin UI should show failed followups, skipped groups, route/schema errors, and coverage gaps.

#### Do not keep as-is

The attached draft includes useful design pressure, but these parts should not be copied directly:

- invented repo paths or table names that do not exist here;
- generated Drizzle migration paths that violate this repo's hand-SQL macro migration convention;
- `confidence: 1.0` for graph-derived macros;
- live LLM evals as default CI;
- new lens names not present in `EXTRACTION_LENSES`;
- a single giant implementation PR that mixes graph IR, macros, evals, contradiction detection, UI, and CI.

Practical implementation order:

1. Fix macro/coverage route/schema failure and make failures visible.
2. Add the workflow-map artifact and graph validators.
3. Add claim-to-node/edge traceability and edge-level dedup.
4. Generate deterministic draft macros from graph structure.
5. Add graph-aware coverage audit and degraded status.
6. Add the Pop Creations workflow eval fixture.
7. Only then consider advanced path-level contradiction detection.

---

## 6. New-developer onboarding (zero prior context)

If you have never seen this repo, read this before touching the macro pipeline.

### 6.1 The mental model

- **Claim** = one atomic operational fact + an exact quote from one chunk. The unit of truth. Gated by the quote validator.
- **Source outline** = a provisional, model-generated *reading* of a whole source (stages, owners, systems, terms, recommended extraction "lenses"). **Guidance only — never evidence, never quotable.**
- **Source group** = a meaning-based cluster of chunks (a workflow stage, a branch, an entity context).
- **Lens** = a targeted extraction pass over a group (handoffs, exceptions, systems, ownership, dependencies, risk, definitions, contradictions).
- **Macro relationship** = durable cross-claim structure (dependency, handoff, sequence, exception path, policy-vs-practice tension). **Evidence is a list of approved claim IDs**, verified `approved` at read time.
- **Coverage finding** = "the outline expected X but no claim covers it."

### 6.2 Where things live

| Concern | File |
|---|---|
| Lens budget gate | `apps/workers/src/lib/document-lens-budget.ts` |
| Outline worker + followup dispatch | `apps/workers/src/trigger/source-outline.ts` |
| Lens extraction worker | `apps/workers/src/trigger/document-lens-extraction.ts` |
| Macro relationship worker | `apps/workers/src/trigger/macro-relationship-extraction.ts` |
| Coverage audit worker | `apps/workers/src/trigger/source-coverage-audit.ts` |
| Broad document extraction + vision Pass 1 | `apps/workers/src/trigger/document-ingestion.ts` |
| Macro lifecycle / status rules | `packages/oracle-engines/src/macro/lifecycle.ts` |
| Read-time "approved macro" helper | `packages/oracle-engines/src/macro/approved-relationships.ts` |
| Prompts | `packages/ai/src/prompts/{source-outline,macro-relationship,coverage-audit,extraction-system}.ts` |
| Schema / migrations | `packages/db/src/schema.ts`, `packages/db/migrations/sql/79_macro_understanding.sql`, `80_…`, `81_…`, `82_…` |
| Runtime budgets | `settings` table rows seeded by migrations 80–82 |

### 6.3 The settings that control everything (seeded values)

| Setting | Seeded | Meaning |
|---|---|---|
| `macro_lenses_enabled` | `true` | run lens fan-out at all |
| `macro_max_lenses_per_document` | `4` | (mis-named; actually **per group** — Bug F) |
| `macro_max_lens_groups_per_document` | `8` | groups beyond this are dropped (Bug: drops terminal stages) |
| `macro_max_lens_model_calls_per_document` | `4` | hard cap on total lens calls (the real limiter — Bug A) |
| `macro_max_lens_estimated_input_tokens` | `32000` | token ceiling for fan-out |
| `macro_auto_followups_enabled` | `true` | dispatch macro + coverage after outline |
| `macro_auto_max_outline_groups` | `12` | max groups before auto-followups need manual review |
| `macro_auto_max_support_claims` | `40` | max claims into a macro pass (**dead above 40** — Bug E) |
| `macro_outline_injection_enabled` | `false` | inject outline into the broad extraction prompt (rollout-gated) |

### 6.4 How to reproduce / test this

- The canonical test document is `9d09fa89-3a46-465e-a98b-837287c9e22a` ("Pop Creations Flow …png").
- A prior full run is cached (read-only) at `.cache/macro-comparison/9d09fa89-…/rerun-20260702T220901Z/` — `comparison-summary.md`, `job-outputs-after-rerun.json`, and `new-claims-after-rerun.md` are the fastest way to see current behavior without touching prod.
- To re-run for real: use `scripts/reevaluate-document.mjs` (guarded, DRY-RUN by default) to wipe the document's prior claims/chunks/candidates and reset it to `pending_processing`, then trigger `document-ingestion` (via the Trigger.dev MCP/dashboard). The outline → lens → macro → coverage chain follows from there. Prod DB access is via the 1Password session pooler (see `docs/deployment.md`); local `.env.local` still points at the **old** Supabase project, so never migrate prod from local without overriding `DIRECT_URL`.
- Trigger.dev is at its **10/10 schedule limit** — do **not** add new scheduled tasks; reuse existing schedules or on-demand dispatch.

### 6.5 Invariants you must not break

- Atomic claims must keep exact-quote validation against one chunk. Never let outline/workflow-map prose become quotable evidence.
- Approved macro relationships must verify **every** support claim is `approved` **at read time** (not just trust `macro_relationships.status`).
- Macro tables are **server-only / service-role** (RLS enabled, no anon policies). If a browser path ever reads them, add RLS first.
- New vector indexes follow the gated `ORACLE_RUN_VECTOR_INDEXES=1` convention.
- Macro tables are deliberately owned by **hand-written** `sql/79_macro_understanding.sql`; do not let a generated Drizzle migration re-emit them.

### 6.6 Gotchas that will waste your day

- **Vision non-determinism.** One run transcribes a flowchart edge as one clean line (`[A] --(cond)--> [B]`) and quotes validate; the next splits an edge across two lines and the extractor paraphrases → quotes fail → claims rejected. Keep `IMAGE_TRANSCRIPTION_SYSTEM` at **one line per edge**, and use real *vision* models (never image-generation models).
- **`job_runs` blind spots.** Macro/coverage don't write `job_runs`, so "it didn't run" and "it failed" look the same in the runs dashboard. Check `model_runs` and the DB row counts, not just `job_runs`.
- **The clamp red herring.** Don't "fix" the budget by deleting the `min()` clamp and stop there — at the seeded config it does nothing (Bug A).

---

## 6.9 Changes implemented 2026-07-03, and the before/after ordering decision (Claude)

### Implemented this session

1. **Dedicated `macro` model slot (fixes the ERR-001 proximate cause).** The macro layer no longer borrows the `general` utility slot. New auxiliary slot `macro` with its own admin picker **`default_macro_route`** (Admin → Settings → "Macro understanding model"), a `requiredCapability: 'structuredOutputs'` filter, and a comprehensive **"Copy job brief"** (spells out that STRICT json-schema — not loose `json_object` — is a hard requirement, that it runs before *and* after atomic extraction, and what capabilities help/hurt). Seeded to `google/gemini-2.5-flash`.
   - Files: `packages/ai/src/routes/{errors,defaults,auxiliary,capability-requirements}.ts`; `apps/web/app/admin/settings/page.tsx`; `packages/db/migrations/sql/83_macro_route_setting.sql`; `packages/db/src/seed.ts`; workers `source-outline.ts`, `macro-relationship-extraction.ts`, `source-coverage-audit.ts` (`'general'` → `'macro'`, incl. attempt-logging slot).
   - **Why a separate slot at all:** macro is a reasoning/synthesis task over claims + structure, not verbatim quote-extraction — but the real point is it must be a *visible, explicit* choice, not an anonymous inheritance from "utility." See the settings job brief.
   - **Needs to go live:** apply migration 83, deploy workers, re-run doc `9d09fa89`, confirm `macro_relationships > 0`. Tracked as `AGENT_ERROR_LOG.md` ERR-001.
   - **Still open:** the slot is single-pick — add a **fallback pool + schema-repair pass** so one malformed structured-output response can't zero the layer.

2. **`AGENT_ERROR_LOG.md`** — a designated, in-repo, agent-readable failure log, referenced from `HANDOFF.md`. Seeded with ERR-001 (Qwen schema hard-fail) and ERR-002 (cross-source SQL). Rule: runtime failures must be captured here in a form specific enough to change code from — because a failure that lives only in Trigger.dev/`model_run_attempts` and nobody reads *is* a silent failure. Enabling work still open: macro/coverage must write `job_runs` + a `macro_health` status, then a `scripts/export-worker-failures.mjs` can refresh the log automatically.

### Implemented this session — batch 2 (2026-07-03)

Verified from the Trigger logs that ERR-001's macro/coverage failures were `AllCandidatesFailedError` on the Qwen `general` route, then landed the following (all typecheck-clean; `verify:r2` + `verify:auxiliary-defaults` pass):

3. **Macro fallback pool (resilience).** The `macro` slot is no longer single-pick — `model_pool_macro = [gemini-2.5-flash, gemini-2.5-pro, gpt-4.1-mini]` wired through the existing pool machinery so one malformed structured-output response falls through instead of zeroing the layer. (`packages/ai/src/routes/{defaults,candidates}.ts`, migration `84`, seed.)
4. **Observability — failures can't hide (§5 Bug C).** `macro-relationship-extraction` and `source-coverage-audit` now write `job_runs` (running → complete/failed) and update the new **`documents.macro_health`** (`not_applicable | pending | complete | degraded | failed`, migration `85`, `apps/workers/src/lib/macro-health.ts`, race-tolerant precedence). A failed holistic layer downgrades health so it can't read as a green `complete`. **Remaining:** render `macro_health` in the Admin → Documents UI.
5. **Lens fan-out is coverage-first (§5 Bugs A/B/F).** Rewrote `buildLensDispatchPlan`: every source group gets its top lens before any group gets a second (round-major), terminal stages are no longer dropped by the group cap, and the inert `min()` clamp is gone. Budgets raised to cover the workflow (migration `84`: model_calls 4→16, tokens 32k→64k). (`apps/workers/src/lib/document-lens-budget.ts`.)
6. **Bug C idempotency + Bug E dead tunable.** `documentHasCompletedLensBatch` now includes the terminal `'complete'` status (no more duplicate re-extraction on re-run). `macro_auto_max_support_claims` now actually raises the SQL `LIMIT` instead of being silently capped at 40.

Still not done (deliberately deferred, see below and §5): the workflow-map artifact (§7), Bug G sequencing (coverage still races macro), Bug D (`blocked_pending_support` gating), and the before/after reorder.

### The "macro before AND after atomic extraction" requirement — current state is WRONG, must change

Intended design (agreed): a macro read **before** atomic extraction (so extraction has whole-source context — referents, acronyms, branches, ownership) **and** a macro pass **after** (relationships + coverage, to check the claims reflect the big picture).

**Verified current reality — the "before" is not actually happening:**
- In `document-ingestion.ts`, `processDocument` runs parse → chunk → embed → **broad atomic extraction** (`buildDocumentChunkWindows`, ~line 713) → promote → mark document `complete` (~line 1291), and only THEN triggers `source-outline` (~line 1298). So the outline for a document is generated **after** its atomic extraction already ran.
- The broad extraction *does* have an outline-injection point (`source-outline-guidance` block, ~line 777), but it injects only a **prior** outline and only when `macro_outline_injection_enabled = true` — which is **seeded `false`** (migration 79). On a first ingestion there is no prior outline, so the broad pass runs blind.
- Net: today it's effectively **after-only**. The outline (the "before" artifact) exists but runs too late to inform the extraction it was meant to guide, and injection is off.

**Target change (open, not yet implemented — larger architectural edit):**
1. Reorder `processDocument`: generate the source outline **immediately after chunk+embed, before** `buildDocumentChunkWindows` extraction (await it; it's one model call).
2. Inject that fresh outline into the broad extraction as non-quotable guidance, and turn `macro_outline_injection_enabled` on (after a small pilot).
3. Keep `macro-relationship-extraction` + `source-coverage-audit` as the **after** pass, and sequence coverage *after* macro (Bug G).
4. This composes with the workflow-map artifact (§7): ideally the "before" pass produces the workflow map, extraction is driven from it, and the "after" pass derives relationships from it.

This is a deliberate follow-up because it changes prod extraction ordering and cost; it should ship with the `macro_health` observability so a failed/blind pass is visible.

---

## 7. Original diagnosis (Codex) — preserved verbatim

> The text in this section is Codex's original `fix_enhancement.md`, unchanged except for the inline **⚠️ Claude disagrees with this** callouts, which are additions, not edits, and never remove Codex's words.

### Problem

The primary job The Oracle needs to do is understand operational documents holistically.

The `Pop Creations Flow 12112025.png` swimlane diagram is not just a set of independent arrows. It is a full business workflow: the path of a licensed Edge Home product from buyer concept, through design, costing, factory sourcing, licensor approval, sampling, PPS audit, production, and shipment from Asia to the US.

Right now The Oracle is still treating this kind of document mostly as a pile of small claims. It can see many individual boxes and arrows, but it does not reliably understand the complete business process those arrows form. Nothing in the business works as isolated claims. Every step is context: ownership, prerequisites, branches, approvals, systems, handoffs, exceptions, and downstream consequences.

### Observed Failure On The Swimlane Diagram

The recent macro-understanding rerun improved atomic recall:

- Old baseline: 122 claims.
- New rerun: 241 claims.
- The pipeline captured many individual edges such as DFlow RFQ, factory limitations, price approval, licensor concept revisions, PPS audit, new-vs-existing product branches, samples, mass production, professional photos, and ship-to-US.

But the holistic layer failed:

- `macro_relationships` stayed at zero for the document.
- `source_coverage_audit` produced no findings.
- Trigger history shows repeated failures for `macro-relationship-extraction` and `source-coverage-audit`.
- The output is dominated by edge-level claims, not by lifecycle-level understanding.
- 241 claims came from only 59 unique evidence quotes, so lens fanout created many near-duplicate claims instead of a cleaner process model.

> **⚠️ Claude disagrees with this** — the correct number is **56** unique quotes, not 59 (`comparison-summary.md`: "new 56 unique quotes"). Minor, but since this doc is a source of truth, use 56. The point (heavy near-duplication) stands.

- Some visible late-stage concepts were missed or underrepresented, including `SKU creation` and `Production order`.
- Source outline fanout skipped later groups such as SKU/system entry and mass production because the lens budget selected only a few early/middle groups.

### What The Oracle Should Produce

For this kind of diagram, The Oracle should produce a process-level representation before, or at least alongside, atomic claims:

- The complete lifecycle path from concept to shipment.
- Swimlane ownership by role/team.
- Ordered stages and dependencies.
- Conditional branches such as new product vs existing product, audit pass vs audit fail, with order vs before an order.
- Approval loops, especially licensor revisions, resubmission, comments approval, and final concept approval.
- Systems of record and data-entry points such as DFlow, ClickUp, ColdLion, MasterData, and PPT references.
- Critical business gates: buyer price approval, design approval, tech pack approval, concept approval, PPS audit, PPS approval, sample approval, and order placement.
- Macro relationships that explain how early design/costing decisions affect downstream sourcing, licensor approval, sampling, production, and shipping.
- Coverage gaps when visible process stages have no claims or no macro relationship representation.

### Required Fix Direction

The fix should not be "extract even more little claims." The system needs a first-class workflow model for diagram/SOP-style sources.

Recommended direction:

1. Add a workflow-map extraction artifact for structured documents and diagrams.
   - Nodes: label, swimlane/owner, stage, system, artifact, approval gate.
   - Edges: source node, target node, condition, branch type, handoff owner, evidence quote.
   - Paths: main path, alternate paths, loops, terminal outcomes.

2. Use the workflow map to drive claim extraction.
   - Atomic claims should be derived from the map with awareness of the whole process.
   - Avoid generating multiple near-duplicate claims for the same edge unless they represent materially different facts.

3. Make macro relationships deterministic or semi-deterministic from the workflow map.
   - A swimlane diagram already encodes sequence, ownership, branch, and handoff structure.
   - Do not rely only on a later LLM pass over the top 40 claims to rediscover that structure.

4. Fix fanout budgeting for diagrams.
   - Budget by workflow coverage, not just by global lens count.
   - Ensure every outline group or major process stage gets at least one relevant pass.
   - Prioritize skipped late-stage groups if they contain terminal outcomes, system creation, production, or shipment.

5. Make coverage audit mandatory and visible.
   - If macro extraction or coverage audit fails, the document should be marked as having degraded macro understanding.
   - The admin UI should show missing macro coverage, failed followups, skipped groups, and why they were skipped.

6. Add an evaluation fixture for this swimlane diagram.
   - Expected output should include a human-authored workflow baseline, not only expected atomic claims.
   - Score path coverage, branch coverage, owner coverage, system coverage, duplicate rate, and macro relationship coverage.

### Code-Level Diagnosis

The current system has the right ingredients, but the control flow still makes atomic claims the primary truth object and treats macro understanding as an optional follow-up.

#### 1. The extraction prompt optimizes for fragments

`packages/ai/src/prompts/extraction-system.ts` tells the model:

> Prefer small, reviewable operational claims over broad document summaries.

That is correct for evidence-backed claim hygiene, but it is the wrong primary representation for a swimlane flow. The extractor is being asked to break the diagram into small local facts. It is not being asked to preserve a graph, lifecycle, or process topology as a first-class object.

Effect on this document:

- The pipeline extracted many correct individual arrows.
- It did not produce a durable representation of the full product path.
- It duplicated the same edge as `dependency`, `policy`, and `process_rule` variants.

Fix:

- Keep atomic claim extraction, but add a separate workflow-map extraction pass before claim extraction.
- The workflow map should represent nodes, edges, swimlanes, owners, branches, loops, systems, approvals, and terminal outcomes.
- Atomic claims should be generated from or reconciled against that workflow map.

#### 2. The lens fanout budget skipped process coverage

`apps/workers/src/lib/document-lens-budget.ts` builds the lens dispatch plan from source outline groups. It has two problematic behaviors for diagrams:

- It skips groups after `macro_max_lens_groups_per_document`.
- It sets the total call limit as:

```ts
const callLimit = Math.min(budget.maxModelCallsPerDocument, budget.maxLensesPerDocument);
```

With default-like settings, a 10-group swimlane diagram got only 4 lens jobs. Later outline groups such as SKU/system entry and mass production/shipment were skipped, even though those groups contain the process endgame.

Effect on this document:

- Early and middle flow got much better coverage.
- Late-stage concepts were weaker or missing.
- `SKU creation` and `Production order` were visible in the diagram but not represented in extracted claim text.

Fix:

- Budget by workflow coverage, not only by lens count.
- Ensure each major workflow stage gets at least one pass.
- Remove the `min(maxModelCallsPerDocument, maxLensesPerDocument)` clamp; those are different budgets.

> **⚠️ Claude disagrees with this** — removing the clamp **alone fixes nothing**. Migration `81` seeds *both* `macro_max_lens_model_calls_per_document` and `macro_max_lenses_per_document` to `4`, so `min(4,4)=4` — the clamp is inert at the real config. The 4-call cap comes from the budget *values* plus the **lens-major candidate sort** (`document-lens-budget.ts:185–189`), which spends all 4 calls on the single top-priority lens (`handoffs`) across the first 4 groups. The correct fix is: (a) budget by coverage and diversify lenses per stage, (b) raise the two budget values, (c) stop dropping terminal groups via the group cap, and only then (d) delete the clamp as cleanup. See §5 Bugs A, B, F.

- Add stage-critical priority: terminal outcomes, branch points, production, shipment, system-entry, and approvals should not be skipped simply because they are late in sort order.

#### 3. Macro extraction tries to rediscover the whole process from a small claim sample

`apps/workers/src/trigger/macro-relationship-extraction.ts` loads support claims with `LIMIT 40`, then further slices them to `macro_auto_max_support_claims`.

That approach is fragile for a diagram that generated 241 claims. The macro pass sees only a small ranked subset of already-fragmented facts. It is being asked to infer the whole workflow after the topology has already been flattened.

Effect on this document:

- The system had enough low-level evidence to understand the flow.
- The macro extractor did not get a reliable full-process input.
- `macro_relationships` remained zero after the rerun.

> **⚠️ Claude disagrees with this (as a *complete* diagnosis)** — the input-sampling problem is real, but it is **not sufficient** to explain `macro_relationships = 0`, and it hides three larger issues: (1) `formatClaimsForPrompt` (`:92`) strips the edge topology and sends only prose summaries, and the `impact DESC` ordering destroys sequence — so even with more claims the model can't rebuild the graph; (2) the `.slice(0, macro_auto_max_support_claims)` is a **no-op above 40** because the SQL hard-codes `LIMIT 40` (Bug E), so raising the setting won't help; (3) most importantly, even a *successful* macro pass produces relationships born `blocked_pending_support` (Bug D), so the holistic layer stays invisible regardless. Codex's LIMIT-40 observation is correct but is one of four causes, not the cause.

Fix:

- Feed macro extraction the workflow map, not only top-ranked claims.
- Generate deterministic macro relationships from graph structure where possible:
  - main sequence
  - branch paths
  - approval loops
  - cross-swimlane handoffs
  - system-of-record transitions
  - terminal outcomes
- Use claims as evidence/support links, not as the only source from which macro structure must be rediscovered.

#### 4. Macro and coverage followups are best-effort and their failure is too quiet

`source-outline` and `document-lens-extraction` trigger:

- `macro-relationship-extraction`
- `source-coverage-audit`

But those followups are downstream best-effort tasks. The parent document/lens job can complete successfully even if macro extraction and coverage audit fail later.

Effect on this document:

- The document looked processed because document ingestion and lens extraction completed.
- The actual holistic layer failed repeatedly.
- No durable document-level degraded status told reviewers: "atomic extraction exists, but macro understanding failed."

> **⚠️ Claude adds (agrees, with two specifics Codex omits)** — (1) the followups are dispatched **fire-and-forget** (`source-outline.ts:284–294`, `.trigger(...).catch(warn)`) and, critically, **neither macro nor coverage writes a `job_runs` row** — that is the concrete reason failures are invisible in the runs dashboard. (2) The two followups are fired **concurrently**, so coverage audit reads `macro_relationships` before macro extraction can commit and structurally sees zero (Bug G). Coverage must run **after** macro.

Fix:

- Track macro followup status per document/outline.
- Add document-level or outline-level macro health:
  - `macro_pending`
  - `macro_complete`
  - `macro_failed`
  - `coverage_failed`
  - `macro_degraded`
- Show failed followups and skipped groups in the admin UI.
- Do not let a document appear fully understood when macro extraction and coverage audit failed.

#### 5. Coverage audit failed, so the system did not identify its own blind spots

`source-coverage-audit` is supposed to compare outline elements against extracted claims and macro relationships. For this document, Trigger history showed repeated failures and the cached comparison showed zero findings.

> **⚠️ Claude confirms + specifies (2026-07-03, Trigger logs pulled)** — Codex is correct that it "failed," and here is the exact error: `source-coverage-audit` throws `AllCandidatesFailedError` on the `general`→`qwen/qwen3.7-max` route with a Zod `invalid_type` at `path: ["findings", 0, …]`. Same root cause as macro extraction: Qwen can't reliably emit the nested schema and the auxiliary slot has no fallback. See §5 Bug H. So "make coverage audit resilient" specifically means: move it off Qwen `json_object` to a strict-json-schema model and/or add fallback + schema repair — resilience is a *routing/validation* problem here, not just a prompt problem.

Effect on this document:

- The system did not flag missing SKU creation or production order coverage.
- It did not flag that macro relationships were absent.
- It did not flag skipped late-stage outline groups as coverage risk.

Fix:

- Make coverage audit resilient and cheap enough to run after every diagram/SOP ingestion.
- If coverage audit cannot run, store that as a finding or degraded status.
- Add deterministic coverage checks independent of the LLM:
  - each workflow node has at least one edge or claim
  - each branch condition is represented
  - each swimlane has ownership coverage
  - each terminal outcome has a path
  - skipped groups are listed as coverage gaps

#### 6. Dedup is not strict enough for lens fanout

The rerun produced 241 claims from 59 unique evidence quotes. Many single edge quotes produced multiple claims with slightly different wording and claim types.

> **⚠️ Claude disagrees with this** — again 56 unique quotes, not 59. The mechanism Codex describes is correct: candidate-hash dedup keys on canonicalized **summary text**, so the same edge phrased as `dependency` / `process_rule` / `policy` hashes differently and all three promote. The fix (edge-level dedup key) is right.

Effect on this document:

- Review load increased.
- The knowledge graph became noisier.
- Macro extraction had a harder input set because repeated local facts crowded out lifecycle structure.

Fix:

- Deduplicate by normalized evidence edge plus semantic summary.
- For diagram-derived edges, treat the edge itself as a stable key:
  - source node
  - target node
  - condition label
  - swimlane owner(s)
- Allow multiple claims per edge only when they assert materially different facts.
- Prefer one canonical edge claim plus optional typed annotations.

### Proposed Architecture Change

Add a workflow-map layer between vision transcription and claims.

#### New artifact: `source_workflow_maps`

Suggested shape:

- `id`
- `source_type`
- `document_id`
- `source_outline_id`
- `status`
- `workflow_version`
- `summary`
- `nodes_json`
- `edges_json`
- `paths_json`
- `coverage_json`
- `model_run_id`
- `context_pack_id`
- `created_at`
- `updated_at`

Node shape:

- `nodeId`
- `label`
- `swimlane`
- `ownerRole`
- `stage`
- `nodeType`: step, approval_gate, system_entry, document_artifact, branch, terminal
- `systems`
- `evidenceQuote`
- `chunkId`

Edge shape:

- `edgeId`
- `fromNodeId`
- `toNodeId`
- `condition`
- `edgeType`: sequence, handoff, approval, branch, loop, exception
- `fromOwner`
- `toOwner`
- `evidenceQuote`
- `chunkId`

Path shape:

- `pathId`
- `name`
- `pathType`: main, alternate, exception, loop, terminal
- `nodeIds`
- `edgeIds`
- `startCondition`
- `terminalOutcome`

#### Pipeline change

1. Vision transcription still converts the image into text topology.
2. Workflow-map extraction parses topology into a graph.
3. Deterministic validators check graph integrity:
   - every edge endpoint exists
   - every edge has evidence
   - branch labels are preserved
   - swimlane ownership is retained
4. Atomic claims are extracted from workflow nodes/edges with stable dedup keys.
5. Macro relationships are generated from workflow paths and supported by the underlying edge/node claims.
6. Coverage audit compares:
   - vision topology
   - workflow map
   - claims
   - macro relationships

#### Evaluation change

Add this swimlane diagram as a fixture with expected workflow answers:

- Full Edge Home licensed product path.
- New product path.
- Existing product path.
- Audit fail path.
- Licensor revision loop.
- Buyer/order path.
- Production and shipment path.
- Systems touched: DFlow, ClickUp, ColdLion, MasterData, PPT.
- Owners by swimlane.

Score:

- node recall
- edge recall
- branch recall
- owner/swimlane accuracy
- system coverage
- terminal path coverage
- duplicate claim rate
- macro relationship coverage

### Acceptance Criteria

The Oracle should be considered fixed for this class of document only when it can answer questions such as:

- "What is the full path of an Edge Home licensed product from concept to shipment?"
- "What changes for new products versus existing products?"
- "Where does licensor approval happen and what loops can occur?"
- "What has to happen before mass production?"
- "Which teams own each stage?"
- "Which systems are updated, and when?"
- "Where can the process branch or fail?"

The answer must be grounded in evidence, but it must read like an understanding of the workflow, not a bag of unrelated claims.

---

## 8. Change log

- **2026-07-03 (Claude) — Trigger logs pulled:** Resolved the honesty caveat — macro/coverage **threw**, they did not return empty. Added **§5 Bug H** (the proximate cause: `general`→`qwen/qwen3.7-max` can't emit the nested schema + no auxiliary fallback → `AllCandidatesFailedError`) and **§5 Bug I** (cross-source SQL query failure on worker `20260703.1`). Reordered the consolidated fix priority to put the model-route fix at step 0. Updated §3 map row 2 and the Codex §7 coverage callout to cite the verified error. Evidence: prod runs `run_cmr4bxmwi…` (macro) and `run_cmr4bxqat…` (coverage), worker `20260703.2`.
- **2026-07-03 (Claude):** Added §0 (product intent), §1 (observed behavior), §2 (Oracle-analysis errors + holistic workflow reconstruction), §3 (root-cause map), §5 (additional bugs A–G + fix priority), §6 (new-developer onboarding), §8 (this log). Preserved Codex's original diagnosis verbatim in §7 with inline disagreement callouts on: the 56-vs-59 quote count (×2), the `min()` clamp fix, the macro input-sampling framing, and the followup-visibility mechanism. Corrected metric: 56 unique quotes, not 59.
- **(earlier) Codex:** Original problem statement, code-level diagnosis, proposed `source_workflow_maps` architecture, evaluation and acceptance criteria (now §7).
