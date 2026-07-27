---

# Independent Principal Engineer Analysis: Post-R0 Macro-First Reader Results

## Repository Material Inventory

**Files inspected by glob inventory:**
- 42 tracked `.md` files (root plans/decisions/handoffs, docs, evals, folder READMEs)
- 36 tracked `.ts` files in `apps/workers/src/` (lib, trigger, __verify__, wet-test)
- 33 tracked `.ts` files in `packages/oracle-engines/src/` (extraction, macro, synthesis, __verify__)
- 13 tracked `.ts` files in `packages/db/src/` (schema, client, audit, verify, migrate, seed)
- 4 tracked `.ts` files in `packages/ai/src/prompts/`
- 2 eval `.md` files
- 1 migration SQL file (`94_r0_validator_coverage_limits.sql`) read directly; migrations 86 and 93 inspected via subagent
- Root config/package files inspected via AGENTS.md context

**Files fully read (code):** `source-workflow-read.ts` (1546 lines, full), `workflow-map-validator.ts` (full), `source-quote-policy.ts` (full), `source-reader-budget.ts` (full), `workflow-read.ts` prompts (full), `quote-validator.ts` (full), `normalization.ts` (full), `types.ts` (full), `audit-r0-release-map.ts` (full), `audit-r0-reader-drops.ts` (full), `r0-reader-validator.ts` (full), `r0-production-replay.ts` (full), `map-coverage.ts` (full), `map-coverage-gaps.ts` (full), `trigger/source-workflow-read.ts` (full), `schema-repair.ts` (inspected via grep).

**Files fully read (docs):** `MACRO_FIRST_IMPLEMENTATION_PLAN.md` (1155 lines, full), `SHAPE_AWARE_READER_DESIGN.md` (full), `evals/shape-aware-stage2.md` (full), `HANDOFF.md` (first 280 lines; key R0 sections confirmed in eval log), `DECISIONS.md` (D-transcript-fuzzy-quote section, L509-516).

**Call-graph traced via subagents:** `document-ingestion.ts` call sites for `generateSourceWorkflowMap`, `loadLatestWorkflowMapContext`, `validateMapElementRefMembership`; `schema.ts` `sourceWorkflowMaps` table definition (L738-775) and `documents.macroHealth` (L458); migration files 86 and 93; settings in `94_r0_validator_coverage_limits.sql`.

**Could not inspect (not blocking):** `HANDOFF.md` beyond L280 (R0 content confirmed in eval log), `DECISIONS.md` beyond the fuzzy-quote decision, `docs/architecture.md`, `docs/configuration.md` (key settings confirmed in code), the full `schema.ts` (relevant tables inspected via subagent), `document-ingestion.ts` full source (call sites traced via subagent). No secret files were read.

---

## 1. Executive Verdict

**R0 should stand. R1 should proceed unchanged. No reader code change is justified before R1.**

The two root `quote_mismatch` failures are **model/prompt quotation defects**: the workflow-read model produced evidence quotes that are not verbatim or normalizable substrings of their cited document chunks. The deterministic validator correctly rejected them. The six cascades (4 edge + 2 path) are correct deterministic consequences of the two root drops. The whole-map metrics (3.6% drop ratio, 95.2% relation evidence coverage) are healthy. The one visibly degraded segment (`pop-costing-sourcing-manufacturing-constraints`, 24.2% local drops) is a quality signal, not a bug — and the canonical plan explicitly states that drop ratio and relation coverage are "reported outcomes, not pass thresholds" (§R0 Exit Gate).

The canonical plan also says: "Any prompt under-production preventing the intended range becomes its own explicit reader gate; it is not relabeled as validator success." This means the two root mismatches should be tracked as a reader-quality gate for a future stage, not patched into R0. R1 is additive DDL and lifecycle/transaction work — it does not touch the reader, validator, or prompt. The two workstreams are orthogonal and can proceed in parallel, but R1's mandatory pre-DDL production audit must not be delayed.

There IS one worthwhile improvement — a **bounded workflow-read quote repair pass** — that directly addresses the root cause without weakening provenance. It should be scheduled as an **R1.5 quality improvement** (after R1 DDL, before R2 readers) or in parallel with R1 since it touches different code. It mirrors the existing segmentation repair pattern that is already proven in production.

---

## 2. Root-Cause Analysis

### 2.1 The two root `quote_mismatch` node rejections

**Classification: Model/prompt quotation defect. Not a validator defect, not a segmentation defect, not a cascade.**

**Proven from code:**

1. The `WorkflowReadNodeSchema` (`packages/ai/src/prompts/workflow-read.ts`, L155-166) requires `evidenceQuote: z.string().min(3).max(2000)` and `chunkId: z.string().uuid()`. It does **not** include character-offset fields (`charStart`/`charEnd`). The `ValidateQuoteInput` type (`packages/oracle-engines/src/extraction/types.ts`, L85-90) supports `charStartProvided`/`charEndProvided`, and `validateQuote` (`quote-validator.ts`, L82-120) has an offset-matching path. But the model has no schema field to supply offsets, so the validator always falls through to the `indexOf` and normalization paths.

2. The `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY` (`types.ts`, L66-72) already enables five normalizations: CRLF normalization, smart-quote mapping, internal whitespace collapse, leading/trailing trim, and Markdown formatting removal (`normalization.ts`, `normalizeMarkdownFormatting` L73-88). This is already a generous policy — it strips emphasis markers, inline code ticks, links, heading/list prefixes, and table separators before matching. A quote that fails this policy is not a formatting mismatch; it is a content mismatch (paraphrase or hallucination).

3. The `validateWorkflowMap` function (`workflow-map-validator.ts`, L193-218) calls `validateEvidence` for each node, which calls `validateQuote` with the source-kind-appropriate policy. For a `.md` document, `quoteSourceKindForDocument` (`source-quote-policy.ts`, L79-90) returns `'native_text_document'`, which resolves to the `markdown_document` policy. If the quote is not found via `indexOf` or after normalization, the verdict is `'failed'` with `failedCheckName: 'quote_exact_match'`. The diagnostic records `passesAlternatePolicies` by testing all other policies (`workflow-map-validator.ts`, L152-167).

4. The prompt (`WORKFLOW_READ_SYSTEM_PROMPT`, `workflow-read.ts`, L97-110) says: "Every node and edge must include a verbatim evidenceQuote copied from exactly one provided Document Chunk ID." The request block (L791-796 of `source-workflow-read.ts`) says: "Every node and edge must cite a verbatim quote from one chunk." The instruction is clear, but there is no structural mechanism to enforce it — the model must self-police its own copying.

**Inferred from telemetry (per `evals/shape-aware-stage2.md` R0 production gate):**

Both root failures used the `markdown_document` policy with `verbatim_includes` as the validation method, and would pass only the `transcript_fuzzy` alternate (fuzzy token overlap ≥ 0.5). This means:
- The model's quote was not found in the chunk text by `.indexOf` (verbatim scan failed).
- The model's quote was not found after Markdown normalization (all five normalizations applied).
- The model's quote tokens overlap the chunk text by ≥ 50% — the model produced a **paraphrase** of the source text, not a formatted variant. This is a known LLM behavior: models tend to "clean up" or rephrase dense source text, especially when the source contains tables, lists, or verbose formatting.

The rejected quotes are bounded to 240 characters in diagnostics (`DEFAULT_QUOTE_EXCERPT_CHARS = 240`, `workflow-map-validator.ts` L46). The actual full quote text and the chunk text are persisted in `validation_json.processSegments[].dropped[].failingQuoteExcerpt` and in the `readerOutputAudit.boundedJson` (bounded to 64K chars). I cannot access the production database to inspect the exact text — this is an uncertainty listed in §7.

### 2.2 The four `missing_endpoint_cascade` relation rejections

**Classification: Correct cascade behavior. Not a root defect.**

**Proven from code:**

`validateWorkflowMap` (`workflow-map-validator.ts`, L240-270) validates nodes first, building `validNodeIds` only from nodes whose evidence quotes pass validation. When an edge is processed (L273-310), it checks `missingEndpoints = [edge.fromNodeId, edge.toNodeId].filter(nodeId => !validNodeIds.has(nodeId))`. If any endpoint was dropped as a root failure, the edge is dropped with `failureClass: 'missing_endpoint_cascade'`, `failureOrigin: 'cascade'`, and `cascadeFromElementIds: missingEndpoints`. The edge's own evidence quote is never validated (it doesn't need to be — the edge cannot survive without its endpoints).

The four cascade edges are the relations whose `fromNodeId` or `toNodeId` reference one of the two rejected root nodes. If the root nodes had passed validation, these edges would have been validated independently. The cascade count (4 edges from 2 root nodes) is consistent with each root node participating in approximately 2 edges.

### 2.3 The two `missing_path_node_cascade` path rejections

**Classification: Correct cascade behavior. Not a root defect.**

**Proven from code:**

`validateWorkflowMap` (`workflow-map-validator.ts`, L312-345) validates paths after nodes and edges. For each path, it checks `missing = path.nodeIdsOrdered.filter(nodeId => !validNodeIds.has(nodeId))`. If any path node was dropped, the path is dropped with `failureClass: 'missing_path_node_cascade'`, `failureOrigin: 'cascade'`. The two cascade paths are paths whose `nodeIdsOrdered` arrays contain one or both of the rejected root nodes.

### 2.4 The degraded segment

The segment `pop-costing-sourcing-manufacturing-constraints` has 8/33 drops (24.2%), exceeding the 20% `maxDroppedRatio` alert threshold (`workflow_map_max_dropped_ratio` setting, default 0.2). This causes the segment's validation status to be `'degraded'` (`workflow-map-validator.ts`, L380-384), which in turn makes the whole-map status `'degraded'` (`source-workflow-read.ts`, L1395-1398). The 24.2% is 2 root drops + 6 cascades out of 33 total graph items. If the 2 root drops were fixed, all 6 cascades would disappear, the segment would have 0 drops, and the whole map would become `'validated'`.

### 2.5 The repair asymmetry (key architectural finding)

**Proven from code:**

The segmentation model (`runSegmentationModel`, `source-workflow-read.ts` L575-730) has a `repairFeedback?: string` parameter (L581). When provided, the prompt includes a `REPAIR REQUIRED` block (L627-631) that tells the model the prior output failed deterministic validation and provides the exact valid chunk ID list and validator feedback. The segmentation repair loop (L1310-1328) retries while `integrityRepairCount > 0` and the attempt count stays under `readerBudget.limits.maxRepairAttempts` (default 1). It also breaks early if the retry did not improve (L1327).

The workflow-read model (`runWorkflowReadModel`, `source-workflow-read.ts` L735-901) has **no** `repairFeedback` parameter and **no** retry loop. Each process segment gets exactly one workflow-read model call (L1351, inside `mapWithConcurrency`). If the model produces paraphrased quotes, there is no second chance.

The `source_reader_max_repair_attempts_per_source` setting (`94_r0_validator_coverage_limits.sql` L15-16, loaded at L1058 of `source-workflow-read.ts`) is consumed **only** by the segmentation repair loop. A grep for `workflow_read.*repair` across the entire repository returns zero matches.

This asymmetry is the single most actionable finding: the system already has a proven bounded-repair pattern for segmentation, but it was never extended to the workflow-read model. The 2 root quote mismatches could potentially have been fixed by a repair pass that tells the model which quotes failed and asks it to copy verbatim from the correct chunk text.

---

## 3. Ranked Recommendation Table

| # | Proposal | Exact files/functions | Proposed behavior | Expected metric impact | Evidence-integrity impact | Complexity | Risks | Rollout stage | Rollback | Verification gates |
|---|---|---|---|---|---|---|---|---|---|---|
| **1** | **Bounded workflow-read quote repair pass** | `source-workflow-read.ts`: `runWorkflowReadModel` (add `repairFeedback` param), `generateSourceWorkflowMap` (add repair loop after `validateWorkflowMap`); `source-reader-budget.ts`: `reserveRepair` (reuse); `94_*.sql` or new settings migration (add `workflow_read_max_quote_repair_attempts_per_segment`) | After `validateWorkflowMap` identifies root `quote_mismatch` failures, re-run the model for that segment with feedback: failing element IDs, their chunk text, validation errors. Re-validate. Use the repaired output if it has fewer root failures. | Could fix both root failures → eliminate all 6 cascades → 0 drops on that segment → map becomes `validated`. Whole-map drops: 8 → 0. | **None.** Repaired output goes through the same deterministic `validateWorkflowMap`. No policy relaxation. | Medium — mirrors the existing segmentation repair pattern, but needs per-segment feedback formatting and a separate budget setting. | Additional model call per failing segment (bounded); repair may not improve if the model continues to paraphrase. | **R1.5** (after R1 DDL, before R2) or in parallel with R1 (different code paths). | Disable the repair loop; the validator alone produces the same behavior as today. | (1) `verify:r0-reader-validator` extended with repair-feedback test. (2) Forced `business-process.md` re-read: root drops ≤ 0 or reduced ≥ 50%. (3) Swimlane regression unchanged. (4) Budget does not exceed configured limits. |
| **2** | **Prompt strengthening with verbatim-copy examples** | `packages/ai/src/prompts/workflow-read.ts`: `WORKFLOW_READ_SYSTEM_PROMPT` | Add 2-3 few-shot examples showing correct verbatim copying (including formatting markers) vs. incorrect paraphrasing. Add a negative instruction: "Do not rephrase, clean up, or improve the source text." | May reduce root quote_mismatch rate by 1-2 per document. Marginal effect on the `pop-costing` segment. | **None.** Prompt-only change. | Low. | Prompt length increase (~200 tokens); possible overfitting to one document's formatting style. | **Parallel with R1** (no code change; prompt version bump triggers source-hash advance so old maps are re-read). | Revert the prompt text; bump the version back. | (1) Forced `business-process.md` re-read: root drops reduced. (2) Swimlane regression unchanged. (3) `verify:workflow-read` schema smoke passes. |
| **3** | **Per-segment degradation alert calibration** | `workflow-map-validator.ts`: `validateWorkflowMap` (add per-segment `degradedBySegmentOnly` flag); `source-workflow-read.ts`: status logic (L1395-1398) | Add a `whole_map_degraded_reasons` field distinguishing "one segment degraded" from "multiple segments degraded" or "segmentation degraded." This does NOT change the status — it only enriches the diagnostic. | No metric change. Improves operator ability to distinguish localized vs systemic degradation. | **None.** Diagnostic-only. | Low. | None. | **R1.5** or parallel with R1. | Remove the field; status logic unchanged. | (1) `verify:r0-reader-validator` extended. (2) Production audit shows the flag. |
| **4** | **Optional character-offset fields in workflow read schema** | `packages/ai/src/prompts/workflow-read.ts`: `WorkflowReadNodeSchema`, `WorkflowReadEdgeSchema` (add `quoteCharStart?`/`quoteCharEnd?`); `quote-validator.ts` (already supports offsets); `source-workflow-read.ts` validator call site | Add optional offset fields. The validator tries offset-based matching first (L82-120 of `quote-validator.ts`). The prompt instructs the model to supply offsets when possible. | Could fix ambiguous matches and improve diagnostic precision. Unlikely to fix paraphrase — if the model can't copy text, it can't count offsets either. | **None.** Offsets are validated against source text; mismatched offsets are rejected. | Medium — schema version bump, prompt change, pipeline version advance. | LLMs are notoriously bad at character offset counting; may introduce new failure modes; schema complexity. | **R2 or later** — requires pipeline version bump; should not precede R1. | Remove the fields; revert the pipeline version. | (1) Schema smoke. (2) Offset-based test fixture. (3) Forced re-read. |
| **5** | **Quote handle/span lookup mechanism** | `source-workflow-read.ts` (pre-process chunks into labeled spans); `workflow-read.ts` (prompt + schema); `quote-validator.ts` (handle-based lookup) | Pre-process each chunk into labeled text spans (e.g., `[SPAN:chunk-abc:0-120]`). The model references handles instead of copying text. The validator resolves handles to source text. | Could eliminate quote-copying errors entirely if the model can reliably reference handles. | **Potentially changes the evidence contract.** Requires careful design to ensure handles resolve to real source text spans. | High — new pre-processing, new schema fields, new validation path, pipeline version bump. | Changes evidence contract; requires migration; may not be compatible with existing maps; handle resolution complexity. | **R3+** — major contract change; needs R1 spine first. | Disable the handle path; revert to text-copying. | (1) Full schema test. (2) Handle resolution test. (3) Forced re-read. |

---

## 4. Top Recommendation: Bounded Workflow-Read Quote Repair Pass

### 4.1 Overview

Extend the proven segmentation repair pattern to the workflow-read model. When `validateWorkflowMap` identifies root `quote_mismatch` failures, re-run the model for that segment with targeted repair feedback. The repaired output goes through the same deterministic validator. The repair is bounded by a new per-segment budget setting and the existing read-call/token/cost budgets.

### 4.2 Data Contracts

**New setting:** `workflow_read_max_quote_repair_attempts_per_segment` (default `1`, type `jsonb integer`). Seeded in a new hand-written migration or in the next settings migration. This is separate from `source_reader_max_repair_attempts_per_source` (which remains segmentation-only) to avoid one repair type starving the other.

**New function parameter:** `repairFeedback?: string` on `runWorkflowReadModel` (`source-workflow-read.ts` L735), mirroring `runSegmentationModel`'s parameter at L581.

**Repair feedback format:** A JSON-serialized string containing:
```json
{
  "failingElements": [
    {
      "elementId": "node_xxx",
      "elementType": "node",
      "chunkId": "abc-...",
      "failingQuoteExcerpt": "first 240 chars of the rejected quote",
      "failureClass": "quote_mismatch",
      "validationMethod": "verbatim_includes",
      "detail": "exactQuoteProvided was not found in sourceText."
    }
  ],
  "instruction": "The following nodes had evidence quotes that were not found verbatim in their cited chunk. Re-emit the COMPLETE workflow map for this segment. For each failing element, copy the evidence text EXACTLY from the chunk — do not rephrase, clean up, or improve the source text. The chunk text for each failing element is provided below.",
  "chunkTexts": {
    "abc-...": "first 2000 chars of the chunk raw text"
  }
}
```

The `chunkTexts` map is bounded to the chunks cited by failing elements only (not all chunks), keeping the repair prompt focused and within budget.

### 4.3 Algorithm

```
for each process segment (inside mapWithConcurrency):
  1. Call runWorkflowReadModel(segment, repairFeedback=undefined)
  2. Call validateWorkflowMap(output)
  3. rootQuoteFailures = diagnostics.filter(d => d.failureClass === 'quote_mismatch' && d.failureOrigin === 'root')
  4. if rootQuoteFailures.length > 0 AND repairBudgetRemaining AND readerBudget allows:
     a. Build repairFeedback from rootQuoteFailures + chunk texts
     b. Call readerBudget.reserveRepair('workflow read quote repair')
     c. Call readerBudget.reserveRead({ estimatedInputTokens, label: 'workflow read repair ...' })
     d. Call runWorkflowReadModel(segment, repairFeedback)
     e. Call validateWorkflowMap(repairedOutput)
     f. if repaired.rootDroppedCount < original.rootDroppedCount:
          use repaired validation result
        else:
          keep original validation result (repair did not improve)
  5. Return { segment, validation, map, modelRunIds, contextPackIds }
```

Step 4f mirrors the segmentation repair's early-break at L1327 (`if (retryValidation.integrityRepairCount >= segmentation.integrityRepairCount) break`).

### 4.4 Call-Site Changes

**`runWorkflowReadModel`** (`source-workflow-read.ts` L735):
- Add `repairFeedback?: string` to the args type.
- Add a `REPAIR REQUIRED` block to the prompt blocks array (after the `workflow-read-request` block), mirroring L627-631 of `runSegmentationModel`:
  ```typescript
  ...(repairFeedback
    ? [makeBlock({
        id: 'workflow-read-repair-feedback',
        label: 'Workflow read repair feedback',
        kind: 'dynamic_input' as const,
        content: `REPAIR REQUIRED: The prior output had evidence quotes that failed deterministic validation. Re-emit the complete workflow map for this segment. For each failing element, copy the evidence text EXACTLY from the chunk text provided.\n\nValidator feedback:\n${repairFeedback}`,
        reasonIncluded: 'bounded deterministic workflow read quote repair',
      })]
    : []),
  ```

**`generateSourceWorkflowMap`** (`source-workflow-read.ts` L1336-1380):
- Inside the `mapWithConcurrency` `run` callback, after `validateWorkflowMap` returns, check for root `quote_mismatch` failures.
- If present and budget allows, call `runWorkflowReadModel` again with `repairFeedback`.
- Re-validate and select the better result.
- Add `workflowReadAttempts` to the persisted `validationJson` (mirroring `segmentationAttempts`).

**`loadSourceReaderBudgetLimits`** (L1045-1067):
- Add `readNumberSetting(db, 'workflow_read_max_quote_repair_attempts_per_segment', 1)`.
- Return it as a new field on `SourceReaderBudgetLimits` or track it separately.

### 4.5 Telemetry

The persisted `validation_json` should gain a `workflowReadAttempts` array per process segment, mirroring `segmentationAttempts`:
```json
{
  "processSegments": [{
    "segmentId": "pop-costing-...",
    "promptVersion": "workflow-read-v1",
    "workflowReadAttempts": [
      { "attempt": 1, "rootDroppedCount": 2, "cascadeDroppedCount": 6, "droppedCount": 8, "validationMethod": "verbatim_includes" },
      { "attempt": 2, "repairRequested": true, "rootDroppedCount": 0, "cascadeDroppedCount": 0, "droppedCount": 0, "validationMethod": "verbatim_includes" }
    ],
    "policySelected": "markdown_document",
    "dropped": [],
    ...
  }]
}
```

### 4.6 Tests

1. **`r0-reader-validator.ts`**: Add a test where a synthetic output has one root `quote_mismatch` failure. Verify that the repair feedback is correctly formatted (contains the failing element ID, chunk text, and validation error).
2. **`source-workflow-read-smoke.ts`**: Add a test for the repair loop logic (mock the model call, verify it retries when root failures exist and stops when budget is exhausted).
3. **Budget test**: Verify that `reserveRepair` and `reserveRead` are called for the repair and that the budget fails loudly when exhausted.
4. **Improvement test**: Verify that when the repaired output has fewer root failures, it is selected; when it doesn't, the original is kept.

### 4.7 Migration Need

**No migration needed for the repair mechanism itself.** All repair state is in-memory (the `SourceReaderBudget` object) and persisted in `validation_json` (jsonb column, already exists). The only DDL is seeding the new `workflow_read_max_quote_repair_attempts_per_segment` setting, which can go in the next settings migration or a small hand-written `INSERT INTO settings ... ON CONFLICT DO NOTHING`.

**Pipeline version bump required:** Change `SOURCE_READER_PIPELINE_VERSION` from `'shape-reader-v2-r0-validator'` to `'shape-reader-v2-r1-quote-repair'` so unchanged sources are re-read with the new repair capability. This is the same pattern used for the R0 release (per `evals/shape-aware-stage2.md`).

### 4.8 Acceptance Thresholds

- **Primary**: Forced `business-process.md` re-read with the repair enabled: root `quote_mismatch` failures ≤ 0, OR reduced by ≥ 50% from the R0 baseline (2 → ≤ 1).
- **Cascade**: If root drops are eliminated, cascade drops must also be 0 (they are deterministic consequences).
- **Whole-map status**: If all segments pass, map status should be `'validated'`, not `'degraded'`.
- **Budget**: Repair must not cause read calls to exceed 40, input tokens to exceed 500K, or cost to exceed $10. The repair adds at most 1 model call per failing segment (6 segments → max 6 additional calls → 13/40 total).
- **Swimlane regression**: Unchanged (0 drops, 56/56 relation evidence).
- **Evidence integrity**: No change to `validateQuote`, `resolveSourceQuotePolicy`, `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY`, or any source-kind policy. The validator is unchanged. The repair only gives the model a second chance to produce a quote that passes the **same** deterministic check.

---

## 5. Rejected Changes

| Proposal | Why it must be rejected |
|---|---|
| **Apply `transcript_fuzzy` to markdown documents** | Directly violates the non-negotiable invariant: "No LLM judges whether a quotation is 'close enough.'" The `transcript_fuzzy` policy was a product-owner decision for spoken disfluent speech (D-transcript-fuzzy-quote); applying it to written documents would accept paraphrases as evidence, destroying quote-level provenance. |
| **Relax `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY`** | The policy already normalizes CRLF, smart quotes, whitespace, trim, and all Markdown formatting. Any further relaxation would approach semantic matching, which is explicitly prohibited for document sources. |
| **Hide the `degraded` status on the whole map** | Violates the "No silent fallback" invariant and the "loud degradation" principle. The degraded status is a quality signal that must remain visible to operators. |
| **Distort the drop-ratio denominator (exclude cascades)** | The denominator (kept + dropped) includes cascades by design. Excluding cascades would make the metric look better (2/220 = 0.9% instead of 8/222 = 3.6%) without fixing the root cause. The cascade count is a reported outcome, not a pass threshold. |
| **Overfit the prompt to `business-process.md`** | Few-shot examples or formatting-specific instructions that are too tailored to one document would harm generalization to the real corpus (responsibilities, reference, ruleset, conversation). The prompt must remain shape-general. |
| **Insert the workflow-read repair before R1** | Violates the canonical R0→R1→R2 sequence. R1 is additive DDL that doesn't touch the reader. Inserting a reader change before R1's mandatory pre-DDL audit would delay the audit and the spine work. The repair should be R1.5 or parallel with R1 (different code paths). |
| **Auto-supersede the degraded map after a repair** | Existing maps are immutable. A repaired read creates a **new** map with a new `sourceContentHash` (because the pipeline version advanced). The old map is superseded normally. Auto-superseding without a new model call would violate the immutability contract. |
| **Remove the `maxDroppedRatio` alert for the one segment** | The 20% alert threshold is a quality signal, not a pass/fail gate. Removing it would hide localized degradation. The alert should stay; the fix should reduce the actual drop count. |

---

## 6. Smallest High-Information Next Experiment

**Experiment: Inspect the actual failing quotes and chunk text in the production map's `validation_json` diagnostics.**

This is read-only, requires no code change, no model call, and no deployment. The R0 diagnostics now retain:
- `failingQuoteExcerpt` (bounded to 240 chars) in each dropped diagnostic (`workflow-map-validator.ts` L46, L88-90)
- `passesAlternatePolicies` (which policies would have accepted the quote)
- `readerOutputAudit.boundedJson` (first 64K of the raw model output, `workflow-map-validator.ts` L50-58)

**Command:** `corepack pnpm --filter @oracle/db run audit:r0-release-map` with `R0_AUDIT_DATABASE_URL` from 1Password and `R0_AUDIT_MAP_ID=a2f38158-063f-4fcb-96e8-3e595766e6df`.

**What this tells us:**
1. Whether the rejected quotes are close paraphrases (semantically correct, wording different) or complete hallucinations (semantically wrong). This determines whether a repair pass is likely to succeed (the model can be told "copy this text" and succeed) or whether the model fundamentally can't extract from this segment.
2. Whether the quotes fail on specific formatting patterns (tables, lists, links) that could be addressed by prompt examples.
3. Whether the `passesAlternatePolicies` list confirms that only `transcript_fuzzy` would accept them (as the eval log states) or whether the `pdf_ocr_document` policy (which uses the same normalization minus markdown formatting) would also accept them — if the latter, there may be a policy-selection issue rather than a pure paraphrase.

**Does this block R1?** No. R1 is additive DDL and lifecycle/transaction work. This experiment is a SELECT-only audit that can run in parallel with R1's mandatory pre-DDL audit.

---

## 7. Uncertainties and Missing Evidence

1. **The exact text of the two failing quotes and their chunk text is not available in this analysis.** The production database is not accessible from this read-only repository analysis. The `evals/shape-aware-stage2.md` log states they used `markdown_document` + `verbatim_includes` and would pass only `transcript_fuzzy`, but the actual quote text is persisted only in the production `validation_json` column. I have not fabricated any production quote text.

2. **Whether the model CAN copy verbatim when explicitly told to is unknown without a model call.** The repair design assumes the model will produce verbatim quotes when given the chunk text and told to copy exactly. This is plausible (models can copy text when explicitly instructed), but unproven for this specific segment's source text.

3. **Whether the 2 root failures are from the same chunk or different chunks is unknown.** The diagnostics record `citedChunkId` per element, but the production audit output in the eval log does not print per-element chunk IDs. If both failures cite the same chunk, the issue may be chunk-specific (e.g., a dense table the model struggles to quote from). If they cite different chunks, the issue is more general.

4. **Whether the `pop-costing-sourcing-manufacturing-constraints` segment's source text has specific formatting (tables, nested lists, complex Markdown) that makes verbatim copying harder is unknown.** The document is `business-process.md` (42,442 chars, 12 chunks), but the specific segment's chunk text is not in the repository.

5. **The historical 101-drop map (`9e84efda-...`) is not directly comparable.** The R0 audit (`audit-r0-reader-drops.ts`) confirmed that the old validator did not retain rejected quotes, so alternate-policy outcomes for the historical 36 root failures "cannot be reconstructed." The R0 run is a fundamentally different model call with a different prompt version and pipeline version, so the 101→8 improvement is real but not a controlled experiment.

6. **The budget had 0 repairs used (of 1 allowed for segmentation).** If the workflow-read repair is added, it would consume from a separate budget (proposed `workflow_read_max_quote_repair_attempts_per_segment`). The existing segmentation repair budget is not affected.

---

## 8. Proposed Decision for Albert

**R0 is complete and healthy. The 8 drops on `business-process.md` are 2 correct quote rejections (the model paraphrased instead of copying verbatim) plus 6 deterministic cascades from those 2 roots. The validator is working correctly — it is protecting you from untraceable claims. No evidence validation was weakened, and the whole-map metrics (3.6% drop rate, 95.2% relationship survival) are strong.**

**Proceed with R1 as planned.** R1 creates the durable cross-shape business-model storage that every future reader stage depends on. It does not touch the reader, validator, or prompt, so it cannot affect the quote-mismatch finding either way. The mandatory pre-R1 production audit should run first, as the canonical plan requires.

**Schedule a bounded workflow-read quote repair as a parallel or immediately-following quality improvement (R1.5).** The system already has a proven repair pattern for segmentation — when the model produces bad chunk IDs, it gets one retry with feedback. The workflow-read model has no equivalent: when the model paraphrases instead of copying verbatim, it gets no second chance. Adding one bounded retry (same budget framework, same validator, no policy relaxation) could fix both root failures and eliminate all 6 cascades, turning the degraded segment green. This is the single highest-value change available, it does not weaken provenance, and it mirrors a pattern that is already in production.

**Before implementing the repair, inspect the actual failing quotes** in the production map's diagnostics. This is a read-only database query that will confirm whether the model's quotes are close paraphrases (repairable) or hallucinations (not repairable by a retry). It takes 5 minutes and does not block R1.
