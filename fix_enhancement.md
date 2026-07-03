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
