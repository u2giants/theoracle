Role: You are an independent principal engineer reviewing an evidence-backed enterprise knowledge
system. You specialize in LLM readers, deterministic evidence validation, TypeScript, PostgreSQL,
Trigger.dev, and safe staged refactors.

Task: Review the entire Oracle repository and recommend exact code changes that would improve the
post-R0 macro-first reader results without weakening evidence traceability. This is a read-only
review. Do not implement anything.

Context:

- Repository: C:\repos\oracle
- GitHub: u2giants/theoracle
- Branch: main
- Current commit: 2a13b570dcc0eb5cf60d9b8f9c95e4ff08d959d0
- Canonical plan: MACRO_FIRST_IMPLEMENTATION_PLAN.md
- Supporting design: SHAPE_AWARE_READER_DESIGN.md and MACRO_FIRST_REDESIGN.md
- Production evidence: evals/shape-aware-stage2.md and HANDOFF.md
- Prior independent review: .ai/reviews/qwen-glm52-r0-improvement-resumed-review.md
- Codex evaluation: .ai/reviews/qwen-glm52-r0-improvement-evaluation.md

Business goal:

The Oracle is being changed from claim-first to macro-first. Durable business structure should
lead reasoning. Atomic claims should remain only as traceable evidence receipts. Every important
statement must still resolve to a real source quote.

Current R0 production result:

- Forced Trigger run: run_06fof96hugnkrumk86vi8f0d01
- Map: a2f38158-063f-4fcb-96e8-3e595766e6df
- Source: business-process.md
- 214 items kept
- 8 items dropped
- Whole-map drop rate: 3.6%
- Important relationship evidence kept: 79/83, or 95.2%
- Drops: 2 root quote mismatches, 4 edge cascades, and 2 path cascades
- One process segment remained degraded at 24.2% local drops
- Reader budget: 7/40 calls, 26,567/500,000 estimated input tokens, zero repairs,
  estimated input cost $0.132835/$10

Verified root-failure evidence:

- Both root failures cite the same source chunk, chunk index 5.
- Both model quotes contain the correct source words with 100% word-token overlap.
- In both cases, the model omitted a lead-in such as "The problem:" or "The fix:".
- The model then changed the following source word from lowercase "the" to uppercase "The".
- One quote also omitted Markdown escaping or formatting characters.
- The strict Markdown policy correctly rejected both.
- Only the transcript-fuzzy policy would accept them.
- Do not propose fuzzy, semantic, or case-insensitive matching for written documents.

Prior GLM recommendation:

- Keep R0 complete and proceed with R1.
- Add a bounded quote-repair pass in parallel with R1 and verify it before R2.
- Use a narrow strict response with only element ID, chunk ID, and replacement evidence quote.
- Patch only the failed quote fields in the temporary model output.
- Re-run the unchanged deterministic validator.
- Reuse the existing source-level repair budget.
- Do not regenerate the full map.
- Do not add a migration or new setting yet.

Repository coverage requirement:

1. Run `git ls-files` and use it as the authoritative tracked-file manifest.
2. Read every one of the 41 tracked `.md` files completely.
3. Read the four current review Markdown files under `.ai/reviews/`.
4. Inspect the entire tracked project-owned codebase, configuration, scripts, workflows, and
   migrations. There are about 401 code/config files totaling about 5 MB.
5. Generated Drizzle SQL and metadata may be checked for contract consistency without line-by-line
   review because AGENTS.md marks them generated. State this clearly.
6. Ignore node_modules, build output, caches, coverage, `.next`, `.turbo`, `.vercel`, raw review
   JSON logs, unrelated untracked PNG files, and all secret or `.env` values.
7. Use search and call-graph tracing to connect each recommendation to real callers, persistence,
   model routing, tests, admin settings, and release gates.
8. Report exact counts as fully read, substantially inspected, generated-only checked, or omitted.
   Never call an inventory hit a completed read.
9. If context limits prevent literal full reading, use internal subagents or staged file batches.
   If anything still cannot be read, list it exactly and explain whether it could change the answer.

Constraints:

- Strictly read-only.
- Do not edit, create, delete, format, or generate repository files.
- Do not run database queries, model production calls, deployments, migrations, commits, or pushes.
- Do not read secret values.
- Preserve immutable maps and claims.
- Preserve strict source-kind quote policies.
- Preserve active-map membership checks.
- Preserve loud degraded status and honest denominators.
- Preserve bounded diagnostics and reader budgets.
- Respect the canonical R0 to R1 to R2 order.
- R1 begins with its required read-only production data audit before any R1 database change.
- Models must remain configurable. Do not hard-code a model.

Questions to answer:

1. What exactly caused the two root failures?
2. Is the validator, prompt, model output contract, repair flow, chunk format, or graph order wrong?
3. Is a narrow evidence-only repair call the best fix?
4. Should the repair return only `elementId`, `chunkId`, and `evidenceQuote`, or additional fields?
5. Should chunk ID ever be allowed to change during repair?
6. Should the existing source-level repair budget cover both segmentation and quote repair?
7. Where should repair happen relative to concurrent segment reads?
8. How do we prevent two failing segments from racing for a one-repair source budget?
9. Should prompt strengthening ship with repair, before it, or not at all?
10. Does this work run in parallel with R1, block R2, or change the canonical stage plan?
11. What tests and one real production gate prove improvement without weakening evidence?
12. What tempting changes must be rejected?

Required output:

1. Plain-English verdict for Albert.
2. Honest repository coverage report with exact counts and omissions.
3. Proven root cause versus inference.
4. Ranked recommendation table.
5. Exact implementation design for the best option.
6. Exact files and functions to change.
7. Data contracts and algorithm.
8. Concurrency and budget handling.
9. Telemetry and rollback.
10. Unit, integration, migration, and production verification gates.
11. Expected effect on the 2 root failures and 6 cascades.
12. Comparison with GLM. Agree, change, or reject each major point.
13. Smallest useful next experiment.
14. Whether R1 or R2 is blocked.
15. Open risks and missing evidence.

Return conclusions and supporting evidence only. Do not provide hidden chain-of-thought.
