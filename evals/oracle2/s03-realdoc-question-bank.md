# S03 real-document understanding — question bank (multi-dept)

Purpose: judge whether Oracle understands **real uploaded production documents**
— not a synthetic table. Built only from Admin → Documents text (ingested
2026-10-06). Process owners grade each Oracle answer Pass/Fail on: fact
correctness, mandatory exceptions, citations, scope, usefulness, clarity. Any
Fail counts. Aggregate only after all items are scored.

**Departments / graders**
- **Ilona** (licensing / Licensed Team): L items.
- **Jessica** (PM / whole POP pipeline): J items.

**Source documents (ONLY these; do not invent beyond them)**
| Tag | Document |
|---|---|
| BP | business-process.md — How the Business Works (POP + Spruce) |
| LTR | Licensed Team Responsibilities 2 - tagged.txt |
| LSA | Licensing Sheet Automation Workflow.pdf |
| APS | SOP Artwork standards creation and saving.pdf |
| PPS | SOP Packaging creating & saving.pdf |
| MPS | SOP Mockup Creation.pdf |
| FLOW | Pop Creations Flow 12112025.png (visual transcription) |
| TR | transcript-Book report overview.txt |

Run: one isolated Oracle Q&A per question against the ingested document set.
This file holds **questions only** (no answer keys). Record run id + answer
privately.

Categories: P=procedure ownership, E=conditional exception, X=cross-department,
H=historical/as-of, I=improvement decision, A=abstain / do-not-infer.

---

## Licensing — Ilona (L)

### Procedure ownership (P)

1. [LTR] Who owns concept submission into licensor systems, and what must be
   saved to MasterData, DesignFlow, and ColdLion after a BA number exists?
2. [LTR] Walk through Concept Resubmit from the licensor’s request to the EOD
   email summary. What is recorded on the first resubmit only?
3. [LTR] When may Licensed Team issue an **internal** concept/PPS approval, and
   what check is mandatory first?
4. [LTR] Who fills the LOG (Letter of Guarantee) for Hazardous Substances/LHAMA
   on DIY canvas, and for which licensor is that step named?
5. [BP+LTR] What is the difference between a product being “approved” and
   “finished,” and who closes the submission?

### Conditional exceptions (E)

6. [LTR] Licensor asks for a small concept tweak (CAWR) versus a change that
   alters the concept to a 70% — when is a full resubmit required?
7. [LTR] When can Licensed Team **push back** on a licensor revision, and what
   evidence must accompany the resubmit?
8. [LTR] Are PPS photo resubmissions required for reorders? State the boundary.
9. [APS] Saving artwork in an Illustrator version other than 2020 — who must
   approve, and what file-name patterns are not permitted?
10. [PPS] Failure to meet Packaging Production Standards — what business
    consequences are named in the document?

### Cross-department (X)

11. [LTR+BP] After Concept Approved, what must happen before PPS photos go to
    the licensor, and which roles touch that handoff?
12. [BP] Who talks to the licensor, who handles packaging revisions versus
    creative revisions, and what internal gate runs first?
13. [FLOW] In the licensed flow swimlanes, where does Creative Direction’s
    “Tech Pack Submit Authorization” sit relative to factory and licensor steps?

### Abstain / do-not-infer (A)

14. [LTR] If the documentation is silent on a new licensor’s Brand Assurance
    rules, should Oracle invent the process or state the gap?
15. [BP] Does portal silence alone prove a licensor withdrew rights? What must
    we **not** infer?

---

## Project / POP pipeline — Jessica (J)

### Procedure ownership (P)

16. [BP] Who owns the whole POP pipeline, who is the internal quality gate
    before any licensor submission, and who converts buyer picks into orders?
17. [BP] List the three things POP really tracks (offer/project, SKU, lost
    preliminary designs) and when a pick becomes a product to build.
18. [BP+FLOW] Walk the licensed product journey from brief/offer creation to
    shipping & import — name the owner at each major step.
19. [FLOW] Which swimlane owns “SKUs creation (DFlow, ColdLion, MasterData,
    ClickUp)” and “Review Audit and send to factory”?

### Conditional exceptions (E)

20. [BP] When do 10a (PO received) and 10b (sample requested without order)
    diverge, and what do they share afterward?
21. [BP] Two buyers pick the same design at once — what is the prescribed
    workaround, and what is deliberately **not** explained to the buyers?
22. [BP] When should a product be canceled (cost / licensing / sampling /
    buyer)? How does that differ from an approved-but-unsold concept?

### Cross-department (X)

23. [BP] Where can the handoff fail between Creative Director review and
    licensing submission, and what is one named bottleneck cause?
24. [BP] How should a licensing withdrawal or licensor revision affect design,
    production planning, and active POs — based on the documented journey?
25. [BP+LTR] Brand Assurance is both a submission record and a shipping
    document — who holds it, and who needs it at import time?

### Historical / as-of (H)

26. [BP] The Creative Director role changed after Sarbani left. How should an
    answer describe the current internal gate without claiming a formal named
    checkpoint that no longer exists?

### Improvement / experiment (I)

27. [BP] Propose one improvement to stop losing unpicked preliminary designs.
    Separate observation, hypothesis, measure, and missing data. Do not claim
    ROI without data.
28. [BP] Would surfacing manufacturing constraints at design time reduce sample
    rework? State the experiment, not a guarantee.

### Abstain / do-not-infer (A)

29. [BP] If asked which specific buyer will reorder next season, and the docs
    only describe how reuse works case-by-case, what should Oracle do?
30. [FLOW] If the swimlane PNG and business-process.md disagree on a step order,
    which is authoritative and what should the answer say?

---

## Scoring sheet (copy per run)

| # | Dept | Category | Pass/Fail | Notes |
|---|---|---|---|---|
| 1–30 | | | | |

Threshold for “understands the real documents”: no Fail on E, A, or X items;
at most one Fail on P/H; I items must label hypothesis vs fact. Process
owners’ aggregate score is the S03 business claim.

**S03 gate:** Ilona and Jessica both Accept the understanding quality on their
sections (or a joint Accept covering both). Then update
`docs/verification/oracle2/S03-pilot.md` and plan STATUS; only then close
#27/#58 and name S04 (#28).
