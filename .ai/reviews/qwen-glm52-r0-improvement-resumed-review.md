---

# Corrected Final Review: Post-R0 Macro-First Reader Results

## 1. Repository Material Coverage Report

### Method
No `run_shell_command` or `git ls-files` tool was available in this environment. The authoritative manifest was assembled via `glob` (which respects `.gitignore` by default) across all tracked extensions, supplemented by `grep_search` for call-graph tracing. Three background subagents were launched to read remaining `.md`, root-plan, and migration-SQL files; all three failed with a `429` quota-exhaustion error before completing. Findings from the first session's subagents (document-ingestion call graph, schema.ts table definitions, migrations 86/93) are incorporated.

### Total tracked files by extension (excluding `.cache/`, `node_modules/`, build artifacts, `pnpm-lock.yaml`)

| Extension | Glob count | Fully read | Substantially inspected | Inventoried only |
|---|---|---|---|---|
| `.ts` (apps + packages + scripts) | ~195 | 18 | 2 | ~175 |
| `.tsx` (apps/web) | not globbed | 0 | 0 | unknown (~200+ estimated) |
| `.sql` (hand-written `sql/`) | ~67 | 1 (migration 94) | 2 (via subagent: 86, 93) | ~64 |
| `.sql` (generated `0*.sql`) | 9 | 0 | 0 | 9 (AGENTS.md says ignore) |
| `.md` / `.txt` | ~39 | 10 | 2 (HANDOFF L1-280, DECISIONS L509-516) | ~27 |
| `.json` / `.yml` / `.mjs` / `.js` | ~42 | 4 (turbo, vercel, root package.json, pr-check.yml) | 0 | ~38 |
| `.ps1` scripts | 3 | 0 | 0 | 3 |
| Other config (`.npmrc`, `.gitattributes`, `.env.example`, etc.) | ~7 | 2 (`.prettierrc.json`, `.env.example` via AGENTS.md) | 0 | ~5 |

### Files fully read (entire file content)

**Code (18 files):** `source-workflow-read.ts` (1546 lines), `workflow-map-validator.ts`, `source-quote-policy.ts`, `source-reader-budget.ts`, `macro-health.ts`, `map-coverage.ts`, `map-coverage-gaps.ts`, `trigger/source-workflow-read.ts`, `r0-reader-validator.ts`, `r0-production-replay.ts`, `quote-validator.ts`, `normalization.ts`, `types.ts` (engines), `index.ts` (engines barrel), `workflow-read.ts` (prompts), `audit-r0-release-map.ts`, `audit-r0-reader-drops.ts`, `verify-workflow-map-prod.mjs`.

**Docs (10 files):** `MACRO_FIRST_IMPLEMENTATION_PLAN.md` (1155 lines), `SHAPE_AWARE_READER_DESIGN.md`, `evals/shape-aware-stage2.md`, `AGENTS.md` (context-provided), `.ai/reviews/qwen-glm52-r0-improvement-review.md`, `.ai/reviews/qwen-glm52-r0-improvement-brief.md` (task prompt), `.github/workflows/pr-check.yml`, `turbo.json`, `vercel.json`, `package.json` (root).

**SQL (1 file):** `94_r0_validator_coverage_limits.sql`.

### Files substantially inspected (key sections read, not full)

1. `apps/workers/src/trigger/document-ingestion.ts` — L745-805 (workflow read call + failure handling), L845-895 (map guidance injection into extraction prompt); call graph traced via first-session subagent.
2. `packages/db/src/schema.ts` — `sourceWorkflowMaps` table (L738-775), `documents.macroHealth` (L451-458), `settings` table, `gaps` table; inspected via first-session subagent.
3. `HANDOFF.md` — L1-280 (R0 status, root causes, next steps).
4. `DECISIONS.md` — L509-516 (D-transcript-fuzzy-quote only; grep confirmed no other decisions about "repair" or "workflow.*read.*repair").

### Files not inspected

- **All `.tsx` files** in `apps/web/app/` and `apps/web/components/` (not globbed; estimated 200+ files). These are admin UI, chat UI, and shadcn components — not relevant to the reader/validator pipeline.
- **~175 `.ts` files** not read — mostly in `apps/web` (API routes, lib helpers), `packages/ai` (providers, client, routes), `packages/db` (migrate, seed, client), `packages/auth`, `packages/shared`. The reader-relevant ones (`source-workflow-read.ts`, `workflow-map-validator.ts`, `quote-validator.ts`, etc.) are all fully read.
- **~64 hand-written `.sql` migration files** not read. The three most relevant (86, 93, 94) are covered. Migration 94 was fully read; 86 and 93 were inspected via subagent.
- **~27 `.md` files** not read — `docs/architecture.md`, `docs/configuration.md`, `docs/deployment.md`, `docs/development.md`, `docs/oracle/00-07`, `CLAUDE.md`, `README.md`, `AGENT_ERROR_LOG.md`, `fix_enhancement.md`, `MACRO_FIRST_REDESIGN.md`, `MODEL_BAKEOFF_SPEC.md`, `DECISIONS.md` (full), `HANDOFF.md` (full beyond L280), `evals/macro-first-battery.md`, and others. Three subagents were launched to read these but all failed with 429 quota errors.
- **~38 config/JSON files** not read — `tsconfig.json` files, sub-package `package.json` files, eval fixtures, Drizzle metadata snapshots.

### Honest disclosure

I cannot claim literal full coverage of the 453-file manifest. I fully read 29 tracked files (18 code + 10 docs + 1 SQL), substantially inspected 4 more, and inventoried the remainder via glob/grep. The files most directly relevant to the reader-improvement recommendation — the entire source-workflow-read pipeline, the validator, the quote-policy resolver, the budget tracker, the prompts, the audit scripts, the verification tests, the canonical plan, the reader design, and the eval log — are all fully read. The uninspected files are admin UI, API routes, provider adapters, migration DDL, and documentation not directly bearing on the reader/validator mechanics.

---

## 2. Corrected Root-Cause Analysis

### 2.1 Defect classification correction

**Earlier characterization (incorrect):** "model paraphrased instead of copying verbatim."

**Corrected characterization (from independently verified production evidence):** The two root `quote_mismatch` failures are **quote-copy fidelity defects** — the model copied the correct words from the correct chunk (chunk index 5) with 100% word-token overlap, but made three small mechanical errors:

1. **Omitted lead-in text**: The model started the quote partway through the source, skipping lead-ins like `The problem:` and `The fix:`. The quote is a proper substring of the source but does not start at the beginning of the source passage.
2. **Capitalization change**: The model capitalized the source's lowercase `the` to `The` after the omitted lead-in. This is a case-level fidelity error, not a content error.
3. **Markdown escaping omission**: One of the two quotes omitted Markdown escaping (e.g., didn't copy `*` or `_` formatting markers that the source contained).

**Why the existing normalization did not catch these:** The `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY` (`types.ts` L66-72) normalizes CRLF, smart quotes, internal whitespace, leading/trailing trim, and Markdown formatting (`normalizeMarkdownFormatting` in `normalization.ts` L73-88). It strips emphasis markers, inline code ticks, links, heading/list prefixes, and table separators. However:
- It does **not** change letter case. `the` and `The` remain different after normalization.
- The lead-in omission means the quote is a substring of the source but starts mid-passage — the `.indexOf` verbatim scan (`quote-validator.ts` L131) finds the substring only if case matches exactly. Since case differs, it fails.
- After normalization, the case difference persists, so the normalized `.indexOf` scan (L150-167) also fails.
- The `transcript_fuzzy` alternate would pass because it lowercases all tokens before checking overlap (`quote-validator.ts` L181-193), and all word tokens are present.

**Proven from code:** The `validateQuote` function (`quote-validator.ts` L82-193) has four stages: (1) offset-based matching (L82-120, not applicable — the `WorkflowReadSchema` has no offset fields), (2) verbatim `.indexOf` scan (L131-148, fails due to case mismatch), (3) normalized scan (L150-167, fails — normalization doesn't change case), (4) fuzzy fallback (L181-193, would pass but is not enabled for `native_text_document` source kind).

**Classification: Model/prompt quotation fidelity defect. Not a validator defect. Not a segmentation defect. Not a cascade. Not a policy defect (the policy correctly rejects non-verbatim quotes).**

### 2.2 The two root `quote_mismatch` node rejections

Both from chunk index 5 of `business-process.md`. The model selected the correct chunk and identified the correct evidence — the word tokens are 100% present. The rejection is purely a copy-fidelity issue: case, lead-in, and escaping.

### 2.3 The four `missing_endpoint_cascade` relation rejections

**Proven from code** (`workflow-map-validator.ts` L273-310): `validateWorkflowMap` builds `validNodeIds` from nodes that pass evidence validation. When an edge is processed, it checks `missingEndpoints = [edge.fromNodeId, edge.toNodeId].filter(nodeId => !validNodeIds.has(nodeId))`. The 4 cascade edges had endpoints referencing the 2 rejected root nodes. The edges' own evidence quotes were never validated — the cascade is deterministic and correct.

### 2.4 The two `missing_path_node_cascade` path rejections

**Proven from code** (`workflow-map-validator.ts` L312-345): Paths are validated last. `missing = path.nodeIdsOrdered.filter(nodeId => !validNodeIds.has(nodeId))`. The 2 cascade paths contained one or both rejected root nodes in their `nodeIdsOrdered` arrays.

### 2.5 Impact of the degraded map on downstream extraction

**Proven from code** (`document-ingestion.ts` L791, L857-866): `loadLatestWorkflowMapContext` (`source-workflow-read.ts` L1108) selects maps with status `'validated'` OR `'degraded'`. The degraded map's guidance is still injected into the extraction prompt. However, the 2 dropped nodes and 6 cascaded edges/paths are absent from the guidance text (`renderWorkflowMapGuidance` at L937 only lists elements/relations that survived validation). The extraction prompt says "Every listed map element or relation whose evidence is present in this window MUST get exactly one canonical claim" (L877) — so the dropped elements get no claims. The structural knowledge in those 8 graph items is lost from the durable claim layer.

### 2.6 The repair asymmetry

**Proven from code:** The segmentation model (`runSegmentationModel`, L575) has a `repairFeedback?: string` parameter (L581) and a bounded repair loop (L1310-1328) that retries while `integrityRepairCount > 0` and the attempt count stays under `readerBudget.limits.maxRepairAttempts` (default 1, loaded from `source_reader_max_repair_attempts_per_source` at L1058). The workflow-read model (`runWorkflowReadModel`, L735) has **no** `repairFeedback` parameter and **no** retry loop. A grep for `workflow_read.*repair` across the entire repository returns zero matches. In the R0 production run, segmentation used 0 repairs (zero integrity repairs needed), leaving the entire repair budget unused.

### 2.7 Corrected audit-script claim

**Correction:** My earlier review stated that the failing quotes could be inspected via `pnpm --filter @oracle/db run audit:r0-release-map`. This is **incorrect**. The `audit-r0-release-map.ts` script (`packages/db/src/audit-r0-release-map.ts`) types only 5 fields on `Diagnostic` (L7-12: `failureClass`, `failureOrigin`, `policySelected`, `validationMethod`, `passesAlternatePolicies`). It computes `diagnosticCounts` by grouping on those 5 fields (L35-46) and prints only aggregate counts plus per-segment summary statistics (L63-80). It does **not** type or print `failingQuoteExcerpt`, `citedChunkId`, `elementId`, `detail`, or `checkName`.

The `failingQuoteExcerpt` data **is persisted** in `validation_json.processSegments[].dropped[].failingQuoteExcerpt` (per `workflow-map-validator.ts` L88-90, bounded to 240 chars by `DEFAULT_QUOTE_EXCERPT_CHARS`), but the audit script does not surface it. The `verify-workflow-map-prod.mjs` script also does not query `validation_json` for individual diagnostics. To inspect the actual failing quotes, a direct SQL query against the `validation_json` column is required, or the audit script must be extended.

---

## 3. Re-evaluated Bounded Quote-Repair Recommendation

### 3.1 Full-map regeneration vs. narrow strict repair — narrow wins

**Full-map regeneration** (my earlier proposal): re-run `runWorkflowReadModel` for the entire segment, asking the model to fix all quotes. The repaired output is a complete new `WorkflowReadOutput` that goes through `validateWorkflowMap`.

**Narrow strict repair** (corrected approach): re-run the model with a **new narrow schema** that returns only `{ elementId, elementType, chunkId, evidenceQuote }` replacement records. The code patches only the `evidenceQuote` (and optionally `chunkId`) on the specific failing elements in the ephemeral original output, then re-runs the **unchanged** `validateWorkflowMap` on the patched output.

| Dimension | Full-map regeneration | Narrow strict repair |
|---|---|---|
| **Graph stability** | Risk: model may change node IDs, edge topology, paths, lanes — introducing new failures | **Safe**: graph structure (nodes, edges, lanes, paths) is preserved verbatim; only `evidenceQuote` field is patched |
| **Token cost** | High: model must re-emit the entire map (up to 250 nodes + 400 edges + 80 lanes + 80 paths) | **Low**: model emits only the failing elements (2 objects for the R0 case) |
| **Output schema** | Uses existing `WorkflowReadSchema` — no new schema needed | **New schema**: `WorkflowReadQuoteRepairSchema` — flat, simple, well within strict-schema limits |
| **Observability** | Hard to diff: entire map replaced, hard to see what changed | **Clear diff**: before/after on specific `evidenceQuote` fields only |
| **Failure modes** | If repair introduces a new node ID mismatch → new cascade | **Isolated**: if a repair quote still fails, only that element is still dropped — no new cascade |
| **Patching complexity** | None — use the new output directly | **Low**: simple field replacement on matching `elementId` |

**Decision: narrow strict repair is superior for this defect class.** The graph structure is correct (the model identified the right nodes, edges, and paths from the right chunks). Only the quote text has fidelity errors. Regenerating the entire map would risk introducing structural errors to fix a text-copying problem.

### 3.2 Configuration: reuse existing budget, no new setting

**Earlier proposal (corrected):** Add `workflow_read_max_quote_repair_attempts_per_segment` as a new setting. This adds configuration complexity and a migration.

**Corrected approach:** Reuse the existing `source_reader_max_repair_attempts_per_source` setting (default 1, seeded in `94_r0_validator_coverage_limits.sql` L15-16) and the existing `SourceReaderBudget.reserveRepair()` method (`source-reader-budget.ts` L111-119). No new setting. No migration.

**How prior segmentation repair affects quote-repair availability:**
- Segmentation repair and quote repair share the same `repairAttempts` counter on the per-source `SourceReaderBudget` instance.
- In the R0 production run: segmentation used **0** repairs (zero integrity repairs needed — all 12 chunks covered, 19 segments, validated on first attempt). Therefore the entire budget of 1 repair was available but unused.
- If a future document needs both segmentation repair AND quote repair, the budget of 1 would be exhausted after the first repair. This is a known limitation.
- The canonical plan says (§14): "Calibration continues in every vertical slice; R9 may tune the configurable values from the dry-run report but may not introduce the first budget enforcement." So the default can be increased via the admin settings UI or a future settings migration during R9 calibration — but no new budget mechanism should be introduced now.
- The quote repair also calls `reserveRead()` for the additional model call's estimated input tokens, consuming from the existing `maxReadCalls` (40) and `maxInputTokens` (500K) budgets. In the R0 case, 7/40 read calls were used, leaving ample room.

### 3.3 Staging: R1-parallel, verify before R2, do not invent R1.5

**Earlier proposal (corrected):** Schedule as "R1.5" (after R1 DDL, before R2 readers).

**Corrected approach:** This is **R1-parallel work** — it touches `source-workflow-read.ts` and `workflow-read.ts` (the reader pipeline), which R1 does not touch (R1 is additive DDL + lifecycle/transaction helpers). It should be **verified before R2** because R2 adds new pass-2 readers (responsibilities) that will also produce evidence quotes and would benefit from the repair pattern. But it does **not formally block R2** — the canonical plan's R2 entry condition is "R0 and R1 green" (§R2 Entry), with no mention of quote repair.

The canonical plan's R0 exit gate says: "Any prompt under-production preventing the intended range becomes its own explicit reader gate; it is not relabeled as validator success." The 2 root quote mismatches are this reader gate. Addressing them before R2 multiplies readers is prudent but not architecturally mandatory.

**Rationale against "R1.5":** The canonical plan defines formal stages (R0-R10) with explicit entry/exit gates. Inventing an intermediate stage introduces sequencing ambiguity. The quote repair is a quality improvement to existing R0 code, not a new architectural stage. It can be developed, verified, and deployed independently of R1's DDL timeline.

---

## 4. Ranked Recommendation Table (Corrected)

| # | Proposal | Exact files/functions | Proposed behavior | Expected metric impact | Evidence-integrity impact | Complexity | Risks | Rollout stage | Rollback | Verification gates |
|---|---|---|---|---|---|---|---|---|---|---|
| **1** | **Narrow strict quote-repair pass** | `source-workflow-read.ts`: `runWorkflowReadModel` (add `repairFeedback` param + new `WorkflowReadQuoteRepairSchema` call), `generateSourceWorkflowMap` (add repair loop inside `mapWithConcurrency` run callback after `validateWorkflowMap`); `source-reader-budget.ts`: reuse `reserveRepair` + `reserveRead`; `packages/ai/src/prompts/workflow-read.ts`: add `WORKFLOW_READ_QUOTE_REPAIR_SCHEMA` + repair prompt fragment; no migration | After `validateWorkflowMap` identifies root `quote_mismatch` failures, call model with narrow schema returning only `{elementId, elementType, chunkId, evidenceQuote}` replacements. Patch only those fields on the ephemeral output. Re-run unchanged `validateWorkflowMap`. Use repaired result if root drops decrease. | Could fix both root failures → eliminate all 6 cascades → 0 drops on that segment → map becomes `validated`. Whole-map drops: 8 → 0. | **None.** Patched output goes through the same deterministic `validateWorkflowMap`. No policy relaxation. No new validation path. | Medium — new narrow Zod schema, repair prompt fragment, patching function, repair loop. Mirrors existing segmentation repair pattern. | Additional model call per failing segment (bounded by existing budget); repair may not improve if model repeats the same fidelity error. | **R1-parallel**, verify before R2. | Disable the repair loop (one `if` guard); validator alone produces current behavior. | (1) `verify:r0-reader-validator` extended with patching + repair-budget test. (2) Forced `business-process.md` re-read: root drops ≤ 0 or reduced ≥ 50%. (3) Swimlane regression unchanged. (4) Budget within limits. |
| **2** | **Prompt strengthening** | `packages/ai/src/prompts/workflow-read.ts`: `WORKFLOW_READ_SYSTEM_PROMPT` | Add explicit instruction: "Copy the evidence text starting from the beginning of the source passage. Do not omit lead-in phrases. Do not change capitalization. Do not omit Markdown formatting characters." Add one positive and one negative example. | May reduce root quote_mismatch rate by 1-2 per document. Directly targets the observed defect class (lead-in omission, case, escaping). | **None.** Prompt-only change. | Low. | Prompt length increase (~150 tokens); possible overfitting to one document. | **R1-parallel** (prompt version bump triggers source-hash advance). | Revert prompt text; revert version. | (1) Forced re-read: root drops reduced. (2) Swimlane regression unchanged. (3) `verify:workflow-read` schema smoke passes. |
| **3** | **Extend audit script to print failing quotes** | `packages/db/src/audit-r0-release-map.ts`: extend `Diagnostic` type + per-segment output | Add `failingQuotes` array to per-segment output: `{ elementId, citedChunkId, failingQuoteExcerpt, failureClass, validationMethod }`. Currently the script only prints aggregate counts — the `failingQuoteExcerpt` data is in `validation_json` but not surfaced. | No metric change. Enables root-cause inspection without direct SQL. | **None.** Read-only diagnostic. | Low. | None. | **Immediate** (read-only script, no deploy needed). | Revert the script. | Script output includes `failingQuoteExcerpt` for each root diagnostic. |
| **4** | **Per-segment degradation enrichment** | `workflow-map-validator.ts`: `validateWorkflowMap` (add `degradedSegmentCount` to validationJson); `source-workflow-read.ts`: status logic | Add `degradedSegmentCount` and `totalSegmentCount` to persisted `validation_json` so operators can see "1 of 6 segments degraded" vs "6 of 6 degraded." Does NOT change status. | No metric change. Improves operator triage. | **None.** Diagnostic-only. | Low. | None. | **R1-parallel**. | Remove the field. | (1) `verify:r0-reader-validator` extended. (2) Production audit shows the count. |
| **5** | **Optional character-offset fields** | `packages/ai/src/prompts/workflow-read.ts`: `WorkflowReadNodeSchema`/`EdgeSchema`; `quote-validator.ts` (already supports offsets) | Add optional `quoteCharStart`/`quoteCharEnd`. Validator tries offset matching first. | Could fix ambiguous matches. Unlikely to fix case/lead-in errors — if the model can't copy text, it can't count offsets. | **None.** Offsets validated against source. | Medium — schema version bump, pipeline advance. | LLMs bad at offsets; new failure modes. | **R2+**. | Remove fields; revert version. | Schema smoke + offset fixture + forced re-read. |

---

## 5. Top Recommendation: Narrow Strict Quote-Repair Pass

### 5.1 Data Contracts

**New Zod schema** (in `packages/ai/src/prompts/workflow-read.ts`):

```typescript
export const WorkflowReadQuoteRepairSchema = z.object({
  repairs: z.array(z.object({
    elementId: workflowId,
    elementType: z.enum(['node', 'edge']),
    chunkId: z.string().uuid(),
    evidenceQuote: z.string().min(3).max(2000),
  })).min(1).max(100),
});
export type WorkflowReadQuoteRepair = z.infer<typeof WorkflowReadQuoteRepairSchema>;
```

**New prompt fragment** (in `packages/ai/src/prompts/workflow-read.ts`):

```typescript
export const WORKFLOW_READ_QUOTE_REPAIR_PROMPT_VERSION = 'workflow-read-quote-repair-v1';

export const WORKFLOW_READ_QUOTE_REPAIR_SYSTEM_PROMPT = `You repair evidence quotes for a source workflow map.

The prior output had evidence quotes that failed deterministic verbatim validation. For each failing element, copy the evidence text EXACTLY from the provided chunk text.

CRITICAL RULES:
- Start the quote from the beginning of the source passage, including lead-in phrases like "The problem:" or "The fix:".
- Do NOT change capitalization. If the source says "the", write "the", not "The".
- Do NOT omit Markdown formatting characters (*, _, \`, [, etc.). Copy them exactly.
- Do NOT rephrase, clean up, or improve the source text.
- Return only the repairs array with replacement quotes for the listed element IDs.`;
```

**New function parameter:** `repairFeedback?: string` on `runWorkflowReadModel` (L735), mirroring `runSegmentationModel`'s pattern.

### 5.2 Algorithm

```
inside mapWithConcurrency run callback, per process segment:
  1. Call runWorkflowReadModel(segment, repairFeedback=undefined) → output
  2. Call validateWorkflowMap(output) → validation
  3. rootQuoteFailures = validation.diagnostics.filter(d =>
       d.failureClass === 'quote_mismatch' && d.failureOrigin === 'root')
  4. if rootQuoteFailures.length > 0:
     a. Check readerBudget: can we reserveRepair() AND reserveRead()?
        - If not: keep original validation (budget exhausted, loud in telemetry)
     b. readerBudget.reserveRepair('workflow read quote repair')
     c. Build repairFeedback = JSON.stringify({
          failingElements: rootQuoteFailures.map(d => ({
            elementId: d.elementId,
            elementType: d.elementType,
            chunkId: d.citedChunkId,
            failingQuoteExcerpt: d.failingQuoteExcerpt,
            detail: d.detail,
          })),
          chunkTexts: { [chunkId]: chunk.rawText.slice(0, 2000) }
            for each unique citedChunkId in rootQuoteFailures
        })
     d. readerBudget.reserveRead({ estimatedInputTokens, label: 'workflow read quote repair' })
     e. Call client.runObject<WorkflowReadQuoteRepair>({
          schema: WorkflowReadQuoteRepairSchema,
          blocks: [repair system prompt, chunk texts, repair request],
          routeCandidates: same workflow_read candidates,
        })
     f. Patch output: for each repair in result.repairs,
        replace evidenceQuote (and chunkId if changed) on matching node/edge
     g. Call validateWorkflowMap(patchedOutput) → repairedValidation
     h. if repairedValidation.rootDroppedCount < validation.rootDroppedCount:
          use repairedValidation (and its map)
        else:
          keep original validation (repair did not improve)
  5. Return { segment, validation, map, modelRunIds, contextPackIds }
```

Step 4h mirrors the segmentation repair's early-break at L1327 (`if (retryValidation.integrityRepairCount >= segmentation.integrityRepairCount) break`).

### 5.3 Patching Function

```typescript
function applyQuoteRepairs(
  output: WorkflowReadOutput,
  repairs: WorkflowReadQuoteRepair[],
): WorkflowReadOutput {
  const repairByElementId = new Map(
    repairs.map(r => [r.elementId, r])
  );
  return {
    ...output,
    nodes: output.nodes.map(node => {
      const repair = repairByElementId.get(node.nodeId);
      return repair && repair.elementType === 'node'
        ? { ...node, evidenceQuote: repair.evidenceQuote, chunkId: repair.chunkId }
        : node;
    }),
    edges: output.edges.map(edge => {
      const repair = repairByElementId.get(edge.edgeId);
      return repair && repair.elementType === 'edge'
        ? { ...edge, evidenceQuote: repair.evidenceQuote, chunkId: repair.chunkId }
        : edge;
    }),
    lanes: output.lanes,
    paths: output.paths,
  };
}
```

### 5.4 Call-Site Changes

**`runWorkflowReadModel`** (`source-workflow-read.ts` L735): Add `repairFeedback?: string` parameter. When present, use `WorkflowReadQuoteRepairSchema` instead of `WorkflowReadSchema`, use `WORKFLOW_READ_QUOTE_REPAIR_SYSTEM_PROMPT`, and build blocks containing only: (1) repair system prompt, (2) document metadata, (3) chunk texts for failing elements, (4) repair request with failing element IDs and feedback.

**`generateSourceWorkflowMap`** (`source-workflow-read.ts` L1336-1380): Inside the `mapWithConcurrency` `run` callback, after `validateWorkflowMap` returns, add the repair loop (§5.2 steps 3-4h). Add `workflowReadAttempts` to the persisted `validationJson` (mirroring `segmentationAttempts`).

**`loadSourceReaderBudgetLimits`** (L1045-1067): No change. Reuse existing `maxRepairAttempts`.

### 5.5 Telemetry

Persisted `validation_json.processSegments[].workflowReadAttempts`:
```json
[{
  "attempt": 1,
  "rootDroppedCount": 2,
  "cascadeDroppedCount": 6,
  "droppedCount": 8,
  "validationMethod": "verbatim_includes"
}, {
  "attempt": 2,
  "repairRequested": true,
  "repairSchema": "workflow-read-quote-repair-v1",
  "repairedElementIds": ["node_a", "node_b"],
  "rootDroppedCount": 0,
  "cascadeDroppedCount": 0,
  "droppedCount": 0
}]
```

### 5.6 Tests

1. **`r0-reader-validator.ts`**: Add `applyQuoteRepairs` test — patch a synthetic output with 2 repair records, verify only the patched elements' `evidenceQuote` changed and all other fields are untouched.
2. **Budget test**: Verify `reserveRepair` and `reserveRead` are called for the repair; verify the budget fails loudly when exhausted.
3. **Improvement test**: When repaired output has fewer root failures, it is selected; when it doesn't, the original is kept.
4. **Immutability test**: Verify the original `WorkflowReadOutput` object is not mutated (the patching function returns a new object).

### 5.7 Migration Need

**No migration.** All repair state is in-memory and persisted in `validation_json` (jsonb, already exists). No new settings. No new columns. The `SourceReaderBudget.reserveRepair` method and `source_reader_max_repair_attempts_per_source` setting already exist and are reused.

**Pipeline version bump required:** Change `SOURCE_READER_PIPELINE_VERSION` from `'shape-reader-v2-r0-validator'` to `'shape-reader-v2-r1-quote-repair'` so unchanged sources are re-read with the repair capability. Same pattern as the R0 release.

### 5.8 Acceptance Thresholds

- **Primary**: Forced `business-process.md` re-read: root `quote_mismatch` failures ≤ 0, OR reduced ≥ 50% from R0 baseline (2 → ≤ 1).
- **Cascade**: If root drops eliminated, cascade drops must also be 0.
- **Whole-map status**: If all segments pass, map status should be `'validated'`.
- **Budget**: Repair must not cause read calls > 40, input tokens > 500K, cost > $10. The repair adds at most 1 model call per failing segment (R0: 1 failing segment → 8/40 total).
- **Swimlane regression**: Unchanged (0 drops, 56/56 relation evidence).
- **Evidence integrity**: No change to `validateQuote`, `resolveSourceQuotePolicy`, `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY`, or any source-kind policy. The validator is unchanged. The repair only gives the model a second chance to produce a quote that passes the **same** deterministic check.

---

## 6. Rejected Changes

| Proposal | Why rejected |
|---|---|
| **Apply `transcript_fuzzy` to markdown documents** | Violates the non-negotiable invariant. The fuzzy policy was a product-owner decision for spoken disfluent speech (DECISIONS.md D-transcript-fuzzy-quote, L509-516). Applying it to written documents would accept non-verbatim quotes as evidence. |
| **Add case-insensitive normalization to `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY`** | Would make `Sales` match `sales`, losing case-sensitivity that may carry business meaning (proper nouns, acronyms). The user explicitly states: "Never recommend relaxing Markdown/document quote validation." Case normalization is deterministic but is still a policy relaxation. |
| **Full-map regeneration instead of narrow repair** | Risks introducing new structural errors (changed node IDs, topology changes) to fix a text-copying problem. The graph structure is correct — only the quote text has fidelity errors. Narrow patching is safer, cheaper, and more observable. |
| **New `workflow_read_max_quote_repair_attempts_per_segment` setting** | Adds configuration complexity and a migration when the existing `source_reader_max_repair_attempts_per_source` (default 1) and `SourceReaderBudget.reserveRepair` already exist and are sufficient. The canonical plan says (§14): "R9 may tune the configurable values... but may not introduce the first budget enforcement." |
| **Formal "R1.5" stage** | Introduces sequencing ambiguity in the canonical plan. The quote repair is a quality improvement to existing R0 code, not a new architectural stage. It should be R1-parallel work verified before R2, not an invented intermediate stage. |
| **Hide the `degraded` status** | Violates "No silent fallback" invariant. The degraded status is a quality signal that must remain visible. |
| **Distort the drop-ratio denominator (exclude cascades)** | The denominator includes cascades by design. Excluding cascades would make 3.6% look like 0.9% without fixing the root cause. |
| **Insert the repair before R1** | R1's mandatory pre-DDL production audit must not be delayed. The repair is orthogonal to R1 (different code paths) and can proceed in parallel. |
| **Auto-supersede the degraded map** | Existing maps are immutable. A repaired read creates a new map via `force=true` with a new `sourceContentHash` (because the pipeline version advanced). The old map is superseded normally. |

---

## 7. Smallest High-Information Next Experiment

**Experiment: Run a direct SQL query against the production map's `validation_json` to extract the two failing `failingQuoteExcerpt` values and their `citedChunkId`, then manually compare them to the chunk text.**

This is read-only, requires no code change, no model call, and no deployment. The data is persisted in `validation_json.processSegments[].dropped[].failingQuoteExcerpt` (bounded to 240 chars) and `citedChunkId`.

**How to run it** (from the eval log's audit instructions):
```sql
SELECT
  seg->>'segmentId' AS segment_id,
  d->>'elementId' AS element_id,
  d->>'citedChunkId' AS cited_chunk_id,
  d->>'failingQuoteExcerpt' AS failing_quote,
  d->>'failureClass' AS failure_class,
  d->>'validationMethod' AS validation_method,
  d->'passesAlternatePolicies' AS passes_alternate_policies
FROM source_workflow_maps,
  jsonb_array_elements(validation_json->'processSegments') AS seg,
  jsonb_array_elements(seg->'dropped') AS d
WHERE id = 'a2f38158-063f-4fcb-96e8-3e595766e6df'::uuid
  AND d->>'failureOrigin' = 'root';
```

Use the session pooler from 1Password (`oracle_session_pooler` field). This is SELECT-only.

**What it tells us:** The user has already provided the answer independently: the quotes have 100% word-token overlap, with lead-in omission, case change, and escaping omission. The experiment confirms this from the persisted diagnostics and establishes whether the `failingQuoteExcerpt` (240-char bounded) captures enough context to design the repair prompt.

**Does this block R1?** No. R1 is additive DDL. This is a SELECT-only audit that can run in parallel.

**Does this block the quote-repair implementation?** No — the user has already provided the production evidence. But it would confirm the `failingQuoteExcerpt` field captures enough context, and it would validate that the repair prompt's chunk-text inclusion is necessary.

---

## 8. Uncertainties and Missing Evidence

1. **The full 240-character `failingQuoteExcerpt` for each root failure is not available in this analysis** — the production database is not accessible. The user has independently verified the nature of the defects (lead-in omission, case, escaping), which I accept as authoritative. I have not fabricated quote text.

2. **Whether the repair model will produce verbatim quotes is unproven without a model call.** The defect class (case + lead-in + escaping) is more tractable than paraphrase — the model has the correct words and just needs to copy them with exact case and formatting. The repair prompt explicitly instructs: "Do NOT change capitalization. Do NOT omit Markdown formatting characters." But whether the model reliably follows this instruction is unknown without a live test.

3. **Whether the narrow repair schema is strict-schema-compatible with the current `workflow_read` route (OpenAI/gpt-4.1).** The schema is simple and flat (`{ repairs: [{ elementId, elementType, chunkId, evidenceQuote }] }`), which should be well within OpenAI strict-schema limits. But this should be verified with `verify:adapter-request-shapes`.

4. **Whether the 240-character `failingQuoteExcerpt` bound is sufficient to convey the failing quote context to the repair model.** The `DEFAULT_QUOTE_EXCERPT_CHARS = 240` in `workflow-map-validator.ts` L46 may truncate long quotes. The repair prompt should include the full chunk text (not the excerpt) so the model can copy from it — the design in §5.2 does this by including `chunk.rawText.slice(0, 2000)` in the repair feedback.

5. **The three background subagents that were supposed to read all remaining `.md` files, root plans, and migration SQL files all failed with 429 quota errors.** I could not inspect `docs/architecture.md`, `docs/configuration.md`, `DECISIONS.md` (full), `HANDOFF.md` (beyond L280), `fix_enhancement.md`, or the ~64 unread migration SQL files. The reader-relevant code is fully read; the documentation gap is acknowledged but not blocking.

6. **The `.tsx` files (estimated 200+) in `apps/web` were not inventoried or read.** These are admin UI and chat components, not reader/validator code. The `apps/web/lib/stage-requirements.ts` file (which defines model picker requirements) was found via glob but not read — it's relevant to model routing but not to the quote-repair recommendation.

---

## 9. Decision for Albert

**R0 is complete and correct. The validator did its job — it caught two evidence quotes where the model made small copying mistakes (missed a lead-in phrase, changed a capital letter, dropped a formatting character). These are not paraphrases or hallucinations; the model had the right words from the right chunk. The 6 additional drops are just the automatic consequences of those 2 root drops (edges and paths that referenced the rejected nodes). The whole-map numbers are healthy: 3.6% drop rate, 95.2% of relationships survived.**

**Proceed with R1 as planned.** R1 creates the durable business-model storage. It doesn't touch the reader or validator, so it can't affect this finding.

**In parallel with R1, add a narrow quote-repair pass to the reader.** Right now, when the model makes a copying mistake on a quote, it gets no second chance — the node is dropped and its dependent edges and paths cascade. But the system already has a proven repair pattern for segmentation (it retries with feedback when chunk IDs are wrong). Extending that same pattern to the workflow-read quotes is the highest-value fix available. The design is simple: when a quote fails validation, send the model the exact chunk text and ask it to return just the corrected quote for that element — not the whole map. Patch the quote, re-run the same validator. No validation rules change. No new database columns. No new settings — it reuses the existing repair budget (which was completely unused in the R0 run). This could turn the 8 drops into 0 and make the map fully `validated`.

**Before building it, run the SQL query in section 7 to confirm the 240-character diagnostic captures enough of the failing quote to design the repair prompt.** It's a 5-minute read-only query against the production session pooler and doesn't block anything.

**The repair should be verified before R2 starts** (so the responsibilities reader can use the same pattern), but it doesn't formally block R2. It doesn't block R1. It's parallel work that makes the existing reader better before you multiply readers.
