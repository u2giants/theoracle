Role: You are an independent principal engineer specializing in evidence-backed knowledge graphs,
LLM document readers, deterministic provenance validation, TypeScript, PostgreSQL, and Trigger.dev.

Task: Perform a read-only, repository-wide analysis of The Oracle and recommend how its code should
change to improve the post-R0 macro-first reader results, especially the one localized degraded
`business-process.md` process segment, without weakening evidence validation. Do not implement.

Context:
- Repository: C:\repos\oracle, GitHub u2giants/theoracle, branch main.
- The product is moving to macro-first reasoning: durable business structure is primary; atomic
  claims exist as evidence receipts traceable to source quotes.
- Canonical plan: MACRO_FIRST_IMPLEMENTATION_PLAN.md.
- Reader design: SHAPE_AWARE_READER_DESIGN.md.
- Production/eval record: evals/shape-aware-stage2.md and HANDOFF.md.
- R0 is deployed. Forced production run `run_06fof96hugnkrumk86vi8f0d01` created map
  `a2f38158-063f-4fcb-96e8-3e595766e6df` for document
  `ee1fa682-9e5c-4cf5-89c5-b2f95d047eea` (`business-process.md`).
- Result: 214 kept, 8 dropped (3.6% whole-map); 79/83 important relations retained (95.2%).
- Drops: 2 root `quote_mismatch` nodes, 4 missing-endpoint relation cascades, and 2 missing-path-node
  cascades. Both roots used selected `markdown_document` + `verbatim_includes` and would pass only
  the looser `transcript_fuzzy` alternate. They were correctly rejected.
- One segment, `pop-costing-sourcing-manufacturing-constraints`, has 8/33 drops (24.2%) and 66.7%
  relation evidence coverage, so the persisted whole map remains visibly `degraded`.
- Budget: 7/40 reads, 26,567/500,000 estimated input tokens, no repairs, estimated input cost
  $0.132835/$10.
- Relevant starting paths include apps/workers/src/lib/source-workflow-read.ts,
  apps/workers/src/lib/workflow-map-validator.ts, apps/workers/src/lib/source-quote-policy.ts,
  apps/workers/src/lib/source-reader-budget.ts, packages/ai/src/prompts/workflow-read.ts,
  packages/oracle-engines/src/validation/quote-validator.ts, packages/db/src/schema.ts,
  packages/db/src/audit-r0-release-map.ts, and the related verification files. Do not limit the
  analysis to these paths.

Repository material requirement:
1. Start by inventorying `git ls-files`.
2. Inspect every tracked `.md` file, including root plans/decisions/handoffs, docs, evals, and
   folder-level READMEs.
3. Inspect the full tracked project-owned codebase and configuration: apps/**, packages/**,
   scripts/**, migrations, workflows, root config/package files, and relevant assets/templates.
4. Ignore node_modules, build output, caches, coverage, `.next`, `.turbo`, generated eval runs,
   secrets, `.env*` values, and the unrelated untracked PNGs. Do not read secret files.
5. Use repository search and call-graph tracing to connect recommendations to actual callers,
   persistence behavior, tests, and rollout gates. Do not rely only on the context summary above.
6. State the inventory counts you inspected and disclose any tracked files you could not inspect.

Constraints:
- Strictly read-only: no edits, writes, generated files, migrations, commands that mutate state,
  commits, pushes, deployments, database access, or external side effects.
- Never recommend relaxing Markdown/document quote validation to transcript-fuzzy or semantic
  matching. Exact evidence traceability is non-negotiable.
- Preserve immutable maps/claims, source-kind policy separation, deterministic validation,
  active-map membership checks, loud degradation, bounded diagnostics, and budget caps.
- Distinguish a model/prompt quotation defect from a validator defect, segmentation defect,
  cascade behavior, and mere alert calibration.
- Consider whether exact quote copying can be made structurally reliable through input/output
  contracts, deterministic quote handles/spans, constrained lookup, targeted bounded repair, or
  graph construction order rather than fuzzy acceptance.
- Respect the canonical R0 -> R1 -> R2 sequence. If a worthwhile change should be scheduled later
  rather than inserted before R1, say so explicitly.

Required output:
1. Executive verdict: whether any reader code change is justified now, or whether R0 should stand
   and R1 proceed unchanged.
2. Root-cause analysis of the two root mismatches and six cascades, grounded in exact repository
   files/functions/lines. Clearly label what is proven from code versus inferred from telemetry.
3. A ranked recommendation table. For every proposal include exact files/functions, proposed
   behavior, expected metric impact, evidence-integrity impact, complexity, risks, rollout stage,
   rollback, and deterministic plus production verification gates.
4. For the top recommendation, provide a concrete implementation design detailed enough for a
   separate engineer to implement: data contracts, algorithms, call-site changes, telemetry,
   tests, migration need or no-migration rationale, and acceptance thresholds.
5. Identify tempting changes that must be rejected because they weaken provenance, hide degraded
   state, distort denominators, overfit one document, or conflict with the canonical plan.
6. Recommend the smallest high-information next experiment and say whether it blocks R1.
7. List uncertainties or missing evidence. Do not fabricate production quote text that is absent.
8. End with a concise proposed decision for Albert in plain business English.

Return conclusions and supporting evidence only; do not provide hidden chain-of-thought.
