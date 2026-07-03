# Fix Enhancement: Holistic Macro Understanding

## Problem

The primary job The Oracle needs to do is understand operational documents holistically.

The `Pop Creations Flow 12112025.png` swimlane diagram is not just a set of independent arrows. It is a full business workflow: the path of a licensed Edge Home product from buyer concept, through design, costing, factory sourcing, licensor approval, sampling, PPS audit, production, and shipment from Asia to the US.

Right now The Oracle is still treating this kind of document mostly as a pile of small claims. It can see many individual boxes and arrows, but it does not reliably understand the complete business process those arrows form. Nothing in the business works as isolated claims. Every step is context: ownership, prerequisites, branches, approvals, systems, handoffs, exceptions, and downstream consequences.

## Observed Failure On The Swimlane Diagram

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
- Some visible late-stage concepts were missed or underrepresented, including `SKU creation` and `Production order`.
- Source outline fanout skipped later groups such as SKU/system entry and mass production because the lens budget selected only a few early/middle groups.

## What The Oracle Should Produce

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

## Required Fix Direction

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

## Code-Level Diagnosis

The current system has the right ingredients, but the control flow still makes atomic claims the primary truth object and treats macro understanding as an optional follow-up.

### 1. The extraction prompt optimizes for fragments

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

### 2. The lens fanout budget skipped process coverage

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
- Add stage-critical priority: terminal outcomes, branch points, production, shipment, system-entry, and approvals should not be skipped simply because they are late in sort order.

### 3. Macro extraction tries to rediscover the whole process from a small claim sample

`apps/workers/src/trigger/macro-relationship-extraction.ts` loads support claims with `LIMIT 40`, then further slices them to `macro_auto_max_support_claims`.

That approach is fragile for a diagram that generated 241 claims. The macro pass sees only a small ranked subset of already-fragmented facts. It is being asked to infer the whole workflow after the topology has already been flattened.

Effect on this document:

- The system had enough low-level evidence to understand the flow.
- The macro extractor did not get a reliable full-process input.
- `macro_relationships` remained zero after the rerun.

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

### 4. Macro and coverage followups are best-effort and their failure is too quiet

`source-outline` and `document-lens-extraction` trigger:

- `macro-relationship-extraction`
- `source-coverage-audit`

But those followups are downstream best-effort tasks. The parent document/lens job can complete successfully even if macro extraction and coverage audit fail later.

Effect on this document:

- The document looked processed because document ingestion and lens extraction completed.
- The actual holistic layer failed repeatedly.
- No durable document-level degraded status told reviewers: "atomic extraction exists, but macro understanding failed."

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

### 5. Coverage audit failed, so the system did not identify its own blind spots

`source-coverage-audit` is supposed to compare outline elements against extracted claims and macro relationships. For this document, Trigger history showed repeated failures and the cached comparison showed zero findings.

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

### 6. Dedup is not strict enough for lens fanout

The rerun produced 241 claims from 59 unique evidence quotes. Many single edge quotes produced multiple claims with slightly different wording and claim types.

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

## Proposed Architecture Change

Add a workflow-map layer between vision transcription and claims.

### New artifact: `source_workflow_maps`

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

### Pipeline change

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

### Evaluation change

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

## Acceptance Criteria

The Oracle should be considered fixed for this class of document only when it can answer questions such as:

- "What is the full path of an Edge Home licensed product from concept to shipment?"
- "What changes for new products versus existing products?"
- "Where does licensor approval happen and what loops can occur?"
- "What has to happen before mass production?"
- "Which teams own each stage?"
- "Which systems are updated, and when?"
- "Where can the process branch or fail?"

The answer must be grounded in evidence, but it must read like an understanding of the workflow, not a bag of unrelated claims.
