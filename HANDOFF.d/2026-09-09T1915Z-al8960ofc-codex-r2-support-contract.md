---
issue: 4
status: BLOCKED
owner: codex/r2-support-contract
---

# R2 support-contract audit found no proven basis for 27/30

## 0. Decisions only the owner can make

Choose the intended evaluation semantics before more reader work: may one expected responsibility combine
evidence from multiple source spans, and which paraphrases count as equivalent? Recommendation: require one
source-bound duty per expected row, allow only the matcher’s explicit action equivalences, and revise any
answer row that needs object wording absent from that span. Recompute the threshold only after that review.

Deferred security decision: the exposed DesignFlow MCP and NAS MCP bearer tokens still need rotation.

## 1. What this application is

The Oracle is POP Creations' evidence-backed operational knowledge system. R2 evaluates extraction of a
licensed team-responsibility document into traceable, source-faithful records.

## 2. What this session set out to do, and why

Albert authorized a local/read-only review after first-divergence evidence showed the old pinned support
gate and production fidelity rule disagreed. The goal was to calculate defensible eligibility without
silently changing the frozen answer key, matcher or threshold.

## 3. Current state — what is true right now

The audit reports: historical partial overlap 28/30; literal answer-row fidelity 2/30; canonical source-
faithful record through the actual matcher 23/30. All results use the frozen fixture, answer key and matcher.
The old pinned gate remains unchanged. Production remains on map `339ca8b1-e412-4447-8336-7586f08bd746`
at 23/30. Issue #4 is open.

## 4. Everything tried that did not work

Replacing partial overlap directly with literal answer-row fidelity is invalid: it collapses to 2/30
because normalized answer rows paraphrase source wording. Treating canonical source records as the whole
feasibility ceiling is also unjustified; it is a reproducible lower bound, and models can choose other
legal wording. Do not adopt either number as the new threshold without semantic decisions.

## 5. Root causes and key findings

The evaluation has three different concepts conflated as “supported”: partial topical overlap, literal
source fidelity of normalized answers, and the matcher’s acceptance of legal extracted records. They yield
different row sets and counts. None independently proves that 27/30 is achievable or fair.

## 6. Exact next steps

1. Obtain Albert's answers to the two semantic questions in section 0.
2. Encode those answers as a versioned support contract with deterministic row-level reasons.
3. Review only the rows whose eligibility changes; preserve licensed text confidentiality.
4. Present the recalculated eligible count and proposed threshold to Albert before changing frozen gates.
5. Merge approved contract changes normally. Authorize production separately only if new reader behavior is
   required and locally proven. Close issue #4 only after every approved condition passes in production.

## 7. Constraints and gotchas in force

No production run, deployment, retry, migration, rollback or map mutation is authorized. Never print
licensed source, answer text, model output, production rows or secrets. Do not label a lower bound a ceiling.

## 8. Access and environment

Host `al8960ofc`, Windows PowerShell. GitHub is authenticated. The licensed audit command is
`verify:r2-support-contract`; the fixture remains external and hash-pinned. Secrets remain in 1Password.

## 9. Open questions and risks

Composite evidence could legitimately support some normalized duties but would change the one-duty/one-span
contract. Broad paraphrase equivalence could also hide invented business meaning. Either choice needs an
explicit owner decision. The exposed MCP bearer tokens remain a separate unresolved security risk.

## Handoff self-audit

Sections 0-9 preserve the purpose, exact measurements, rejected shortcuts, production state, constraints,
owner decisions and bounded next steps. All predecessor obligations were carried forward; its merged commit
is on main, so the predecessor handoff is retired under the successor rule.
