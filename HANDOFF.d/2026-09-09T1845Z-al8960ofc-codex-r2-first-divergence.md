---
issue: 4
status: BLOCKED
owner: codex/r2-first-divergence
---

# R2 first-divergence audit found an evaluation-contract conflict

## 0. Decisions only the owner can make

Issue #4 cannot close under the current evidence. Decide whether to authorize a separate evaluation-
contract correction: replace the partial-overlap definition of “supported” with the unchanged full
source-fidelity test, then review the answer key and 27/30 threshold against the resulting eligible
rows. Recommendation: authorize that read-only/local contract review before funding another production
run. Do not change the frozen contract silently.

Deferred security decision: the exposed DesignFlow MCP and NAS MCP bearer tokens still need rotation.
Recommendation: authorize both rotations, update their configured references, verify both services,
and retire the old values.

## 1. What this application is

The Oracle is POP Creations' evidence-backed operational knowledge system. R2 measures whether a
licensed team-responsibility document becomes complete, source-faithful structured records.

## 2. What this session set out to do, and why

Production stayed at 23/30 after source-bound canonicalization. This session built a SELECT-only
first-divergence trace for missed rows 5/14/15/23 to identify the earliest incompatible pipeline
decision without changing production, the reader, or any frozen gate.

## 3. Current state — what is true right now

The active production map remains `339ca8b1-e412-4447-8336-7586f08bd746`, degraded at 23/30, with
all protected rows preserved and controls 16/24/26 unmatched. No deployment, production run, retry,
tuning, migration, rollback, map mutation, or deletion occurred in this diagnostic step. Issue #4
remains open.

## 4. Everything tried that did not work

Repeated extraction, completion feedback, and exact source-bound canonicalization all preserved the
score rather than closing rows 5/14/15/23. Do not repeat them unchanged. The older missed-row tool's
post-hoc corrector result was hypothetical; it must not be read as proof that production persisted the
same correction.

## 5. Root causes and key findings

The pinned inventory gate uses partial role/action/object-token overlap and calls all four missed rows
supported. The complete answer-key record passes the unchanged source-fidelity validator on zero of
those supporting seeds: row 5 has 0/4; rows 14, 15 and 23 each have 0/1. Stored records reaching the
map pass fidelity but lack matcher details the source rule will not permit them to invent. Two frozen
tests therefore encode incompatible meanings of “supported.” The 27/30 target is not proven feasible
under all current frozen contracts.

## 6. Exact next steps

1. Obtain Albert's explicit authorization for an evaluation-contract review.
2. Make the pinned support gate require the complete expected row to pass the unchanged fidelity rule;
   separately test any proposed multi-span support policy.
3. Recompute eligible rows and present the answer-key or threshold implications to Albert. Do not
   change either without his decision.
4. Merge any authorized correction through normal checks. Request a separately bounded production
   cycle only if a new reader lever is proven locally.
5. Close issue #4 only after a production map satisfies every owner-approved acceptance condition.

## 7. Constraints and gotchas in force

Never print licensed text, model output, production rows, or secrets. Preserve the source-fidelity
validator, negative controls, map history, route and budgets unless Albert explicitly revises the
evaluation contract. No production action is authorized. Never retry an earlier bounded run.

## 8. Access and environment

Host `al8960ofc`, Windows PowerShell. GitHub is authenticated. Secrets remain in 1Password vault
`vibe_coding` and must move only through protected references. The diagnostic command is
`verify:r2-first-divergence`; it needs the production session-pooler URL and is SELECT-only.

## 9. Open questions and risks

The owner must decide whether source support can be composite across spans, whether over-specific
answer-key rows should change, and whether 27/30 remains meaningful after support is corrected.
Changing the reader again before resolving that conflict risks paying for records the fidelity gate
must reject. The two exposed MCP bearer tokens remain a separate security risk until rotated.

## Handoff self-audit

1. Sections 1-3 preserve the application, objective, production state, and explicit non-actions.
2. Sections 4-5 preserve failed approaches, the diagnostic distinction, and the first-divergence proof.
3. Sections 0 and 6 consolidate every owner decision and give a bounded successor path.
4. Sections 7-9 preserve all frozen safety rules, access boundaries, open questions, and security risk.
