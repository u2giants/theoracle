# Independent Review: Post-R0 Macro-First Reader Improvement

Review of `u2giants/theoracle` @ `2a13b57` (main). Read-only; no edits, no DB queries, no model calls, no secrets read.

---

## 1. Plain-English verdict for Albert

**The system worked exactly as designed. R0 is healthy; proceed with R1's read-only audit now.**

On the forced `business-process.md` read, the reader model made two small copying mistakes in its evidence quotes: it dropped a lead-in like "The problem:" / "The fix:", capitalized "the" into "The", and once dropped Markdown formatting characters. The words were 100% correct and from the right chunk — but they were not byte-exact, and The Oracle's core promise is byte-exact evidence. The validator correctly refused both quotes. The other 6 drops (4 edges, 2 paths) are not independent failures — they are the automatic, deterministic consequences of those 2 rejected nodes. Whole-map numbers are strong: 3.6% drops, 95.2% of relationship evidence kept.

**The one real gap:** the reader gives the model a second chance when it botches *segmentation* (a bounded retry with validator feedback), but gives it no second chance when it botches a *quote*. The fix is to extend that same proven pattern to quotes: tell the model exactly which quotes failed, show it the real chunk text, ask for only the corrected quotes, then run the same unchanged strict validator. Nothing about evidence rules changes — the repair just gives the model one bounded opportunity to produce a quote that passes the check it already had to pass.

Do it **in parallel with R1** (different code, no migration), **prove it before R2** multiplies readers. Expected result on the next forced read: 8 drops → 0 (or close), the degraded segment goes green, the map becomes `validated`. If the repair doesn't help, nothing gets worse — the original validated result is kept and the attempt is logged.

---

## 2. Repository coverage report (honest counts)

Method: `git ls-files` as the authoritative manifest (**453 tracked files**), categorized by script. I personally read the entire reader/validator/budget/prompt/policy core plus all R0 evidence files; six parallel read-only subagents read everything else completely and returned per-file FULL/PARTIAL ledgers, which I reconciled against the manifest by area (root 32, `.github` 1, docs 15, evals 2, scripts 8, `.cache` 9, apps/web 123, apps/workers 39, packages/ai 76, packages/oracle-engines 35, packages/db 103, packages/auth 6, packages/shared 4 — sums to 453).

| Category | Count | Treatment |
|---|---:|---|
| **Fully read** (every line, by me or a named subagent with a FULL ledger entry) | **415** | All 37 non-cache tracked `.md` (incl. `MACRO_FIRST_IMPLEMENTATION_PLAN.md` 1154, `MACRO_FIRST_REDESIGN.md` 1180, `HANDOFF.md` 1452, `DECISIONS.md`, all `docs/`, both eval logs); all of apps/workers (39, incl. `source-workflow-read.ts` 1545 and `document-ingestion.ts` 1743); all of packages/ai (76), packages/oracle-engines (35), packages/db/src (13, incl. `schema.ts` 2472), all 67 hand-written `migrations/sql/*` + superseded-86, packages/auth (6), packages/shared (4), all root configs, `vercel.json`, `pr-check.yml`, `.env.example` (variable names only), 5 of 8 scripts |
| **Substantially inspected** | **6** | 3 PowerShell Graph probes (headers/purpose only — Teams subscription diagnostics, irrelevant to the reader); 3 `components/ui/*` shadcn primitives (framework layer, skimmed) |
| **Generated-only checked** | **19** | Drizzle `migrations/0000–0008*.sql` + `meta/*.json` — per AGENTS.md these are generated. Checked: journal has exactly 9 entries; `0008` is intentionally SQL-empty; **`source_workflow_maps` appears in no generated file** (hand-SQL-owned by 86/93, matching the documented snapshot quirk) |
| **Binary viewed** | **1** | `model_pass_stages_matrix.png` (model-passes planning matrix — planning artifact, not code) |
| **Omitted by policy** | **12** | `.cache/**` (9 cache artifacts), `pnpm-lock.yaml` (AGENTS.md: ignore unless dependency resolution is the task), `next-env.d.ts` (Next-generated), `theoracle-teams-app.zip` (build artifact of `manifest.template.json`) |
| Untracked `.ai/reviews/` | — | 5 review `.md` files + `inspect-r0-root-quote-failures.ts` fully read (note: there are **5**, not 4, review markdown files; I read all 5). The 3 raw JSON/JSONL session logs were omitted per your instruction 6 |

**Nothing that could change the answer was left unread.** The only non-full items are PowerShell Teams probes, shadcn UI primitives, caches, the lockfile, and generated artifacts — none touch the reader, validator, evidence policy, model routing, budgets, or release gates.

---

## 3. Proven root cause vs. inference

**Proven (code + persisted telemetry + two independent production inspections):**

1. Both root `quote_mismatch` rejections cite the same chunk (index 5) of `business-process.md`; both quotes have 100% word-token overlap with that chunk; both omit a lead-in (`The problem:` / `The fix:`) and change `the` → `The`; one omits Markdown escaping. Only `transcript_fuzzy` would accept them.
2. The mechanism from code: `validateQuote` (`packages/oracle-engines/src/extraction/quote-validator.ts:48`) — stage 2 verbatim `indexOf` fails on the case difference (`:128`); stage 3 normalized scan fails because `MARKDOWN_DOCUMENT_NORMALIZATION_POLICY` strips formatting but **never folds case and cannot restore omitted lead-in words** (`normalization.ts`, `types.ts:66-72`); stage 4 fuzzy is disabled for `native_text_document` (`source-quote-policy.ts:52-58`). Verdict `failed`, `failedCheckName: 'quote_exact_match'` → mapped to `quote_mismatch`, `failureOrigin: 'root'` (`workflow-map-validator.ts:126-128, 341-357`).
3. The 4 edge and 2 path drops are deterministic cascades: edges whose endpoints failed node validation drop with `missing_endpoint_cascade` **without their own quote ever being validated** (`workflow-map-validator.ts:392-417`); paths drop the same way (`:467-484`).
4. The repair asymmetry: segmentation has a `repairFeedback` parameter and bounded retry loop (`source-workflow-read.ts:581, 626-631, 1310-1329`); the workflow-read model has **none** (`runWorkflowReadModel`, `:735-935` — no repair parameter, no loop; grep for workflow-read repair returns zero). The R0 run used 0 of its 1 repair attempts.
5. The degraded map still feeds extraction guidance, minus the 8 dropped items (`loadLatestWorkflowMapContext` accepts `'validated'|'degraded'`, `:1108-1135`; `renderWorkflowMapGuidance` lists only survivors, `:937-989`; extraction request says listed elements "MUST get exactly one canonical claim", `document-ingestion.ts:879`). The 8 items' structural knowledge never becomes claims.

**Inference (flagged as such, not proven):**

- *Why* the model does this: likely quote "cleanup" on a dense Markdown passage — dropping a bolded lead-in label and normalizing sentence case. The prompt says "verbatim evidenceQuote copied from exactly one provided Document Chunk ID" (`workflow-read.ts:105`) but has no negative "do not clean up / do not change case / keep lead-ins" clause. Unprovable without model internals.
- Repair success probability: high for this defect class (the model has the right words and the right chunk; the repair shows it the exact source text and the exact failure), but **unproven until one live call**.
- The chunk-5 formatting (bolded lead-in labels) is inferred from the "omitted Markdown escaping" evidence; I did not inspect production bytes (read-only review, no DB access used).

---

## 4. Answers to the 12 questions (summary table)

| # | Question | Answer |
|---|---|---|
| 1 | What caused the 2 root failures? | Model quote-copy fidelity defects (lead-in omission + case change + escaping omission) on the correct chunk. Not paraphrase, not hallucination, not a validator/segmentation/policy error. |
| 2 | Is validator / prompt / contract / repair flow / chunk format / graph order wrong? | Only the **repair flow is missing** for workflow reads (segmentation has it; workflow read doesn't). Validator, chunk format, graph order, and output contract are all correct. Prompt is adequate but silent on this failure class. |
| 3 | Is narrow evidence-only repair the best fix? | **Yes.** Graph structure is correct; only quote text is wrong. Narrow patch + unchanged validator beats full-map regeneration (structural churn risk, cost, poor diff), deterministic re-anchoring (forbidden — it's case-insensitive matching), prompt-only (no cure for the current defect class), and do-nothing (loses 8 items of durable knowledge per degraded read). |
| 4 | Repair fields? | `{ elementId, elementType, chunkId, evidenceQuote }` per repair, wrapped `{ repairs: [...min 1, max 100] }`. `elementType` is required (nodes and edges are separate ID namespaces; an ID can exist in both arrays). Nothing else — no labels, summaries, conditions. |
| 5 | May chunkId change during repair? | **No (v1).** The echoed chunkId must equal the originally cited chunkId; a mismatch is rejected deterministically and logged. A chunk move silently changes what the element cites — a semantic change, and the validator would pass same-document covered moves without any guard. Wrong-chunk selection is a different failure class with its own diagnostics (`crossSegmentStatus`, foreign/uncovered classes); give it explicit handling later, not a side-door now. |
| 6 | One shared source-level repair budget for segmentation + quotes? | **Yes for v1.** Reuse `source_reader_max_repair_attempts_per_source` (94, default 1) + `SourceReaderBudget.reserveRepair`. No new setting/migration (plan §14 defers calibration; admins can raise the value in the settings UI without DDL). Record `repairSkipped` so calibration data exists. One hardening required — see §8. |
| 7 | Where relative to concurrent segment reads? | **Inside the per-segment `mapWithConcurrency` callback**, right after that segment's `validateWorkflowMap`, before returning the segment result. All needed state is local: segment chunk raw text, diagnostics, shared budget, client, db. A serial post-pass adds a phase and buys nothing until >1 segment fails. |
| 8 | Budget race between two failing segments? | `reserveRepair` is synchronous and JS is single-threaded (`source-reader-budget.ts:111-120`) — check+increment is atomic in-process. First caller wins; losers throw `SourceReaderBudgetExceededError`, which the repair block **catches** → records `repairSkipped:'budget_exhausted'` → keeps the original validation. A repair must never crash a read. The map write happens once after the join (`:1441-1461`), so persistence is race-free. |
| 9 | Prompt strengthening: with, before, or never? | **With, same deploy, independent version bump.** A fidelity clause (copy lead-ins; preserve case; preserve Markdown characters; do not clean up) fires first as prevention; repair is the cure when it still fails. Keep it shape-general — no `business-process.md`-specific few-shots. `WORKFLOW_READ_PROMPT_VERSION` already participates in the source hash (`source-workflow-read.ts:133-143`), so the bump alone forces honest re-reads. Plan §13 notes a material prompt change may trigger a bake-off; BO-2 is already owed before any non-OpenAI primary. |
| 10 | Parallel with R1 / block R2 / change the plan? | **R1-parallel, verify green before R2, no plan change, no R1.5.** R1 is additive DDL + lifecycle helpers (disjoint code). R2 multiplies pass-2 readers that will inherit this validation+repair pattern — fixing it first prevents multiplying the failure mode across 5 more shapes. R1's mandatory read-only audit is untouched. The plan's own R0 exit gate contemplates this: prompt under-production "becomes its own explicit reader gate." |
| 11 | Tests + one production gate? | See §10 below: 7 deterministic CI tests + a SELECT-only deterministic replay proving the persisted R0 failures flip to kept + one authorized forced production read with explicit acceptance thresholds. |
| 12 | Tempting changes to reject? | See §12: fuzzy/semantic/case-insensitive matching for documents; case-folding in the Markdown policy; deterministic case-insensitive re-anchor; full-map regeneration; chunk moves; new settings/migrations; hiding degraded status or denominators; reusing the dead hard-coded `schema-repair.ts`; model escalation; offset fields. |

---

## 5. Ranked recommendation table

| # | Proposal | Files / functions | Behavior | Metric impact | Evidence impact | Complexity | Risks | Stage | Rollback | Verification |
|---|---|---|---|---|---|---|---|---|---|---|
| **1** | **Bounded narrow quote-repair pass** | `packages/ai/src/prompts/workflow-read.ts` (new schema/prompt/version); `apps/workers/src/lib/source-workflow-read.ts` (`runWorkflowReadQuoteRepairModel`, `applyQuoteRepairs`, repair block in the segment callback, telemetry) | After `validateWorkflowMap`, for root `quote_mismatch`/`quote_ambiguous` failures only: one budgeted model call returning `{elementId, elementType, chunkId, evidenceQuote}` repairs; sanitize (unknown ID, wrong type, chunk move → reject); patch only those fields in the ephemeral output; re-run the unchanged validator; keep whichever result has fewer root drops | R0 case: 8 drops → 0 expected; degraded segment → green; map → `validated` | **None.** Same validator, same policies, same chunk; model output is never "rewritten" — a new candidate quote must pass the same verbatim gate | Medium (mirrors existing segmentation repair) | Repair model repeats the error (no harm: original kept); budget consumed by segmentation first (loud skip) | R1-parallel, green before R2 | `source_reader_max_repair_attempts_per_source=0`, or redeploy prior worker; maps immutable | §10 gates |
| **2** | **Prompt fidelity clause** (ships with #1) | `workflow-read.ts`: `WORKFLOW_READ_SYSTEM_PROMPT` + `WORKFLOW_READ_PROMPT_VERSION → 'workflow-read-v2'` | Add: copy from passage start including lead-ins; preserve source case; preserve Markdown characters; do not rephrase or clean up | Prevents the observed defect class on future reads | None — prompt text only | Low | Prompt overfit if examples are fixture-specific (avoid); ~150 tokens | Same deploy as #1 | Revert text/version | Forced re-read; swimlane replay; `verify:workflow-read` |
| **3** | **Budget-guard hardening** (ships with #1) | `source-workflow-read.ts:1310-1314` (segmentation loop guard) + try/catch around every repair-side `reserveRepair`/`reserveRead` | Today the segmentation loop guards on `segmentationModels.length - 1 < maxRepairAttempts` — it does **not** see quote repairs consuming the shared counter. Guard on the shared counter / catch `SourceReaderBudgetExceededError` so an exhausted repair budget can never fail a whole read | Prevents a new crash class | None | Low | None | Same deploy as #1 | N/A | New deterministic budget tests |
| **4** | **Audit-script diagnostics surfacing** | `packages/db/src/audit-r0-release-map.ts` (extend `Diagnostic` type + per-segment output) | Print `elementId`, `citedChunkId`, `failingQuoteExcerpt` per root diagnostic (data is persisted; the script just doesn't surface it — GLM's correct catch) | Enables the §10 production-gate audit without raw SQL | None — read-only tooling | Low | None | Anytime (no deploy) | Revert | Script prints excerpts for remaining roots |
| **5** | **Whole-map degradation enrichment** (optional, low) | `workflow-map-validator.ts` `validationJson`; `source-workflow-read.ts` status assembly | Add `degradedSegmentCount` / `totalSegmentCount` so "1 of 6 degraded" is distinguishable from systemic degradation. No status change | Triage quality only | None | Low | None | R1-parallel or later | Remove field | Deterministic test + audit output |
| **6** | **Housekeeping notes (not changes)** | `scripts/verify-workflow-map-prod.mjs` is schema-stale (selects `source_outline_id` dropped by migration 86, and `macro_relationships.confidence` — actual column is `confidence_score`); `apps/workers/src/lib/schema-repair.ts` is **dead code** (zero callers since the Stage 3 writer deletions) with a hard-coded route | Fix or retire the script; delete the dead utility at R10 cleanup | None | None | Trivial | None | R10 (or a tiny standalone fix if the script is wanted) | N/A | — |
| — | **Rejected: offsets, full-map regen, chunk moves, new settings, fuzzy/case-insensitive, deterministic re-anchor, model escalation** | — | See §12 | — | — | — | — | — | — | — |

---

## 6. Exact files and functions to change (recommendation #1 + #2 + #3)

1. **`packages/ai/src/prompts/workflow-read.ts`**
   - Add `WORKFLOW_READ_QUOTE_REPAIR_PROMPT_VERSION = 'workflow-read-quote-repair-v1'`.
   - Add `WorkflowReadQuoteRepairSchema` (flat; reuses the `workflowId` regex; `evidenceQuote: z.string().min(3).max(2000)` mirroring node/edge schemas at `:138,148`; `chunkId: z.string().uuid()`; `elementType: z.enum(['node','edge'])`; `repairs` array `min(1).max(100)`) + inferred type.
   - Add `WORKFLOW_READ_QUOTE_REPAIR_SYSTEM_PROMPT` (repair-only role; the chunk text is the only source of truth; copy exactly; never change case; never omit lead-ins or formatting; return only the `repairs` array).
   - Strengthen `WORKFLOW_READ_SYSTEM_PROMPT` (`:98-110`) with the fidelity clause; bump `WORKFLOW_READ_PROMPT_VERSION` to `'workflow-read-v2'`.
   - Bump `SOURCE_READER_PIPELINE_VERSION` (`:5`) to `'shape-reader-v2-r1-quote-repair'` (same pattern as the R0 bump; it participates in `sourceHashForDocument` at `source-workflow-read.ts:137`, so unchanged sources are honestly re-read rather than silently reusing pre-repair maps).
2. **`apps/workers/src/lib/source-workflow-read.ts`**
   - `runWorkflowReadQuoteRepairModel(...)` — new function mirroring `runWorkflowReadModel`'s full observability pattern (`:735-935`): `resolveRouteCandidates(db,'workflow_read')` (same approved pool — **no hard-coded model**), `budget.reserveRead` before dispatch, context-pack insert, `client.runObject` with the repair schema + `.catch(logAllCandidatesFailedAttempts)` + rethrow, `model_runs` row with `taskType:'source-workflow-read-quote-repair'` (free-form column) and composed `promptVersion: ${WORKFLOW_READ_PROMPT_VERSION}:${WORKFLOW_READ_QUOTE_REPAIR_PROMPT_VERSION}`, `model_run_usage_details` using **result** route metadata (`result.routeId ?? route.routeId` — non-primary dispatch is real), `logModelRunAttempts`, context-pack back-link. Single call — no windowing; `maxOutputTokens` small (~2,000).
   - `applyQuoteRepairs(output, repairs)` — new **pure** function returning a new `WorkflowReadOutput`; only `evidenceQuote` fields on matched nodes/edges change; every other byte identical. Export via `__sourceWorkflowReadTestHooks` (`:1539`) for the CI tests.
   - `sanitizeQuoteRepairs(repairs, rootFailures)` — new pure guard: drop and log any record with unknown `elementId`, `elementType` mismatch, `chunkId ≠` originally cited chunk, or duplicates; only elements that were actually requested may be patched (a hallucinated repair ID can never resurrect anything).
   - Repair block inside the `mapWithConcurrency` segment callback (after `validateWorkflowMap` at `:1370-1377`): collect root quote failures; `try { readerBudget.reserveRepair('workflow read quote repair') } catch → record skip, keep original`; build feedback (failing elements + full raw text of each unique cited chunk, taken from in-memory `segmentChunks`, falling back to the `validationChunks` map for covered cross-segment citations); call the repair model; sanitize; patch; re-run `validateWorkflowMap` with identical args; select the result with fewer `rootDroppedCount` (mirrors the segmentation early-break at `:1327`).
   - Persist `workflowReadAttempts` per segment in `validationJson.processSegments[]` (`:1431-1435`), mirroring `segmentationAttempts` (`:1430`).
   - Harden the segmentation guard (`:1311-1314`) per §8 so the shared counter can't throw into the read.
3. **`apps/workers/src/__verify__/r0-reader-validator.ts`** — add the deterministic tests (§10).
4. **`packages/ai/src/__verify__/workflow-read-smoke.ts`** — assert the repair schema stays flat/strict-compatible.
5. **`packages/db/src/audit-r0-release-map.ts`** — extend the `Diagnostic` type and per-segment output (#4).
6. **Docs on implementation**: `DECISIONS.md` (new `D-workflow-read-quote-repair`: budget reuse, chunk-move guard, skip semantics), `evals/shape-aware-stage2.md` (append gate evidence), `docs/configuration.md` (widened budget semantics note).

**No migration, no `schema.ts` change, no new settings key.** `validation_json` is free-form jsonb; `model_runs.task_type` and `model_run_attempts` accept any string; the budget setting exists. (One caveat from the DB sweep: if you ever want a new `extraction_validation_results.check_name`, that CHECK is a closed whitelist — but the map repair writes no such rows, so this doesn't bite.)

---

## 7. Data contracts and algorithm

**Repair request (model input):** repair system prompt block + document metadata + one `retrieved_context` block per unique cited chunk (full chunk raw text — chunks are already ≤ ~4k chars; the quote must be copyable from it) + one `dynamic_input` block:

```json
{
  "instruction": "These evidence quotes failed deterministic verbatim validation. For each elementId, copy the evidence text EXACTLY from the chunk shown, including lead-in words, original capitalization, and all Markdown characters. Return only the repairs array.",
  "failingElements": [{ "elementId", "elementType", "chunkId", "failingQuoteExcerpt", "checkName", "detail" }]
}
```

**Repair response (Zod):** `{ repairs: [{ elementId, elementType, chunkId, evidenceQuote }] }` (§6.1).

**Algorithm (per process segment, inside the existing concurrent callback):**

```
1. validation = validateWorkflowMap(output)                       // unchanged
2. roots = validation.diagnostics.filter(d =>
     d.failureOrigin === 'root' &&
     d.failureClass IN ('quote_mismatch','quote_ambiguous'))      // nodes AND edges
3. if roots empty → proceed with validation
4. try budget.reserveRepair(...)  catch → record repairSkipped:'budget_exhausted', goto done
5. build feedback from roots + full cited-chunk text
6. try budget.reserveRead(estimate) catch → record skip, goto done
7. repairResult = runWorkflowReadQuoteRepairModel(...)            // full logging pattern
8. accepted = sanitizeQuoteRepairs(repairResult.repairs, roots)   // unknown IDs / wrong type / chunk moves rejected + logged
9. if accepted empty → record no_improvement, goto done
10. repaired = validateWorkflowMap(applyQuoteRepairs(output, accepted))   // same args
11. if repaired.rootDroppedCount < validation.rootDroppedCount
       → use repaired (its .map now includes revived nodes; edges/paths re-evaluated)
    else → keep original
12. record workflowReadAttempts[{attempt 1…}, {attempt 2, repairRequested, repairedElementIds, root/cascade counts, improved}]
```

Why `quote_ambiguous` is included: it is also a root evidence failure repairable by a longer, distinctive quote copied from the same chunk. Why `unknown_chunk_id` / foreign / uncovered are excluded: those are citation-target defects, not quote fidelity (§4, Q5).

**Why step 11 is safe:** `validateWorkflowMap`'s returned `map` keeps only surviving items (`:511`), and `workflowToProcessStructureMap` builds the persisted structure from `validation.map` (`:1381-1388`). Selecting `repaired` flows revived nodes/edges/paths through the exact same persistence, status, coverage, and guidance code — no second path. Note the re-run validates the 4 cascade edges' **own** quotes for the first time (they were never checked); if one fails, it becomes a new, honest, smaller root failure — correct behavior.

---

## 8. Concurrency and budget handling

- **Placement:** inside `mapWithConcurrency` (`source-reader-budget.ts:133-158`, preserves output order by index) with the existing `maxConcurrency` (default 4). Up to 4 repair calls may be in flight; all budget reservations are synchronous.
- **Race for the 1-repair budget:** impossible to double-spend — `reserveRepair` check+increment is atomic in the single-threaded process. Losers get `SourceReaderBudgetExceededError`, caught in the repair block → `repairSkipped:'budget_exhausted'` → original validation kept. Base reads stay fail-loud (the R0 gate "budgets fail loudly" is untouched); only the *optional enhancement* is skippable.
- **Segmentation-vs-quote budget interaction (the one real hazard found):** the segmentation loop guard (`source-workflow-read.ts:1311-1312`) counts *segmentation models*, not the shared counter. Execution order (segmentation repair at `:1310-1329`, then process reads at `:1335`) currently protects it, but if a quote repair ever consumed the budget first, `reserveRepair` at `:1314` would throw and fail the entire read. Fix in the same change: guard on the shared counter (`readerBudget.snapshot().repairAttempts`) or wrap the reservation. This is recommendation #3.
- **Persistence:** single writer after the join (`:1441-1461`); `createPendingMap` supersedes + inserts in one transaction with the partial unique index `source_workflow_maps_active_source_hash_unique` (migration 86) guarding concurrent ingestions of the same document. The repair changes nothing here.
- **Caller contract:** `document-ingestion` awaits `generateSourceWorkflowMap` once before extraction windows (`document-ingestion.ts:753-759`); the repair is invisible to it — same `SourceWorkflowReadResult`, same failure/fallback semantics (`require_workflow_map_for_ingestion` untouched). Repair calls add ≤1 model call per failing segment (R0: 1 segment → 8/40 calls, well within budgets).

---

## 9. Telemetry and rollback

**Telemetry (all existing surfaces, no DDL):**
- Per repair call: `oracle_context_packs` (blocks, hashes, cited chunk IDs), `model_runs` (`task_type='source-workflow-read-quote-repair'`, composed prompt version, actual provider/model from result metadata), `model_run_usage_details` (tokens incl. cache fields), `model_run_attempts` (pool attempts; non-primary visible), and `logAllCandidatesFailedAttempts` on total failure.
- Per segment: `validation_json.processSegments[].workflowReadAttempts[]` with before/after root+cascade counts, repaired element IDs, rejected repair records (with reasons), skip reasons, and `improved` boolean. The tolerant readers in `audit-r0-release-map.ts` (`number()` defaults) already survive the new keys; `readerBudget.repairAttempts` is already printed.
- Admin visibility with zero UI work: `/admin/ai/runs?task_type=…` + run detail, the 7-day attempt alert banner on every admin page, `/admin/documents` `macroHealth` badge (`map_failed`/`degraded`/`complete` CHECK already covers outcomes), `/admin/business-model` map status.
- Never persisted twice: chunk text goes into the context pack by hash reference (block hashes + `includedDocumentChunkIds`), not into `validation_json` — consistent with the bounded-diagnostics rule.

**Rollback:** (a) set `source_reader_max_repair_attempts_per_source=0` in Admin → Settings — disables all reader repairs immediately (acceptable: it also disables the segmentation retry until flipped back); (b) redeploy the previous worker version — behavior returns exactly to R0; (c) maps are immutable — a repaired read only ever creates a *new* map via the normal supersede path; old maps/claims are never rewritten; (d) prompt rollback = revert the two version strings. No data migration in any direction.

---

## 10. Verification gates

**Deterministic, DB-free (CI — extends `verify:r0-reader-validator`, already a `pr-check.yml` step):**
1. `applyQuoteRepairs`: patch 2 records in a synthetic output → only targeted `evidenceQuote` fields differ; original object unmutated; IDs/labels/lanes/paths byte-identical.
2. Chunk-move rejection: repair with `chunkId ≠` cited → not applied, logged.
3. Unknown-ID / wrong-`elementType` / duplicate records → ignored, logged; nothing resurrected.
4. Budget: `maxRepairAttempts=0` → repair skipped + recorded; exhausted shared counter mid-flight → skip, **read completes** (the §8 crash class); base-read over-budget still throws (existing test pattern at `r0-reader-validator.ts:331-347`).
5. Improvement selection: fewer root drops → repaired selected; equal/worse → original kept (mirrors `:1327`).
6. **Unchanged-validator proof:** the entire existing `r0-reader-validator` suite passes unmodified (policies, cascades, cross-segment, membership, coverage, budgets).
7. `verify:workflow-read`: repair schema is flat and OpenAI-strict-compatible; `verify:adapter-request-shapes` covers request shaping for the pool's Anthropic candidate.

**Deterministic production replay (SELECT-only, no model call):** a small `__verify__` replay that loads map `a2f38158`'s persisted root diagnostics + the cited chunk text, constructs the patched output with the true source substring, and proves `validateWorkflowMap` flips the 2 roots and all 6 cascades to kept. This proves the *mechanism* end-to-end, leaving only the model's cooperation as the live variable.

**Production gate (one authorized forced run, after deploy):** `source-workflow-read` with `force:true` on document `ee1fa682-…`. Acceptance: root `quote_mismatch` drops 2 → ≤1 (target 0); cascades fall correspondingly; whole-map status → `validated` (the other 5 segments were already at 100%); `verify:r0-production-replay` swimlane unchanged (0 drops, 56/56); budget ≤ caps with `repairAttempts ≤ 1` recorded; `audit:r0-release-map` (extended, #4) shows any remaining failures with excerpts; zero `transcript_fuzzy` admissions for document sources. **Migration gates:** none — `pnpm db:check-drift` stays green by construction.

---

## 11. Expected effect on the 2 root failures and 6 cascades

- **Best case (expected):** the repair model, shown chunk 5's exact text and told "copy including the lead-in, preserve case and formatting," returns verbatim quotes. Both roots pass `verbatim_includes`; the 4 edges and 2 paths re-validate (their nodes now survive); if the edges' own quotes are clean, the segment goes 33 items → 0 drops, whole map 222 → 0, status `validated`, `macro_health` `complete`. The revived elements/relations enter `elements_json`/`relations_json`, extraction guidance, map-ref membership, and coverage denominators on the next ingestion — their knowledge is no longer lost from the claim layer.
- **Honest partial case:** an edge's own quote fails on re-validation → a new, smaller root failure set, loudly diagnosed. This is correct, not a regression.
- **No-improvement case:** the repair repeats the fidelity error → original validation kept, `workflowReadAttempts` shows the failed attempt, budget shows 1 used. The map is byte-identical to today.
- **On the R0 map itself:** none — `a2f38158` is immutable. The improvement lands on the *next* read (forced by the pipeline-version bump), which supersedes it normally.

---

## 12. Comparison with GLM (agree / change / reject)

| GLM point | Verdict | Note |
|---|---|---|
| Keep R0 complete; proceed with R1 | **Agree** | Unanimous with Codex. |
| Narrow strict repair, not full-map regeneration | **Agree** | GLM corrected itself here in the resumed review; my independent read of the validator/concurrency code concurs. |
| Repair schema `{elementId, chunkId, evidenceQuote}` (+`elementType` in GLM's resumed version) | **Agree, with GLM's `elementType`** | Codex's 3-field variant omits it; node/edge ID namespaces are separate arrays, so the discriminator is load-bearing for patching. |
| Patch only failed quote fields in the temporary output | **Change (one guard)** | GLM's `applyQuoteRepairs` applies `chunkId` changes blindly. Repair must echo-match the cited chunk; moves are rejected + logged (§4, Q5). With that guard, agree. |
| Re-run the unchanged deterministic validator; keep better result | **Agree** | Mirrors the segmentation early-break. |
| Reuse the source-level repair budget; no new setting/migration | **Agree, with a hardening** | The segmentation loop's guard doesn't see the shared counter — fix in the same change (§8). |
| R1-parallel, verify before R2, no formal R1.5 | **Agree** | Identical to Codex's stage decision. |
| Pipeline version bump | **Agree** | `'shape-reader-v2-r1-quote-repair'` + prompt version bump for the clause. |
| GLM #3: extend audit script to surface failing quotes | **Agree** | Recommendation #4. GLM's correction is accurate: the data is persisted, the script doesn't print it. |
| GLM #4: `degradedSegmentCount` enrichment | **Agree (optional)** | Recommendation #5, low priority. |
| GLM #5: optional char-offset fields | **Reject for now** | LLMs are unreliable at offsets; doesn't address this defect class; schema churn. GLM itself ranked it last/deferred. |
| GLM's smallest experiment (SQL to inspect failing quotes) | **Obsolete** | Codex already inspected them read-only and concluded another SQL inspection adds nothing. The smallest experiment is the deterministic replay + test seam (§13) — Codex's formulation, which I adopt. |

New findings of this review beyond GLM/Codex: the segmentation-guard/shared-counter crash hazard (§8); `schema-repair.ts` is dead code with a hard-coded route and must not be reused (use the `workflow_read` pool); `verify-workflow-map-prod.mjs` is schema-stale; the docs-sanction tension (docs/oracle/02–03 discourage quote re-asks on the *claim* path) is resolved by the reader's own `D-r0-reader-quality-contract`, which already budgets "repairs" per source and sanctions the segmentation model-retry pattern this design mirrors.

---

## 13. Smallest useful next experiment

**Implement the repair behind a pure-function test seam, then run the deterministic production replay — before any model call or deploy.**

1. Land `applyQuoteRepairs` + `sanitizeQuoteRepairs` + the schema/prompt constants with the 7 CI tests (§10). Prove only the two quote fields change and everything else is byte-identical.
2. Run the SELECT-only replay (§10): persisted R0 root diagnostics + cited chunk text → patched output → `validateWorkflowMap` → assert 2 roots + 6 cascades flip to kept. No DB writes, no model call, no deploy.
3. Only then deploy and run the single authorized forced read with the §10 acceptance thresholds.

This sequences proof as: mechanism (deterministic) → mechanism against real production data (deterministic) → model cooperation (one bounded live call). It does not touch R1's audit.

---

## 14. Whether R1 or R2 is blocked

- **R1: not blocked, not delayed.** The repair touches `packages/ai/src/prompts/workflow-read.ts` and `apps/workers/src/lib/source-workflow-read.ts`; R1 touches `packages/db` schema/migrations/lifecycle helpers and starts with a read-only production audit. Disjoint. Run R1's audit now.
- **R2: not formally blocked, but should not start before the repair is green.** R2 multiplies pass-2 readers (responsibilities first) that will reuse this validation/repair machinery; shipping the repair first prevents multiplying the root-failure mode across five more shapes. The canonical plan's R2 entry ("R0 and R1 green") is unchanged; treat "quote-repair verified" as an R0-quality addendum recorded in `DECISIONS.md` + `evals/shape-aware-stage2.md`, not a plan amendment.

---

## 15. Open risks and missing evidence

1. **Repair-model cooperation is unproven.** The defect class is the most tractable kind (right words, right chunk), and the repair shows the exact source text, but only the live gate settles it. Mitigation: no-improvement case is free and loud.
2. **The edges' own quotes are unvalidated today.** Fixing the roots may expose up to 4 new honest root failures on the formerly cascaded edges. Expected drop outcome is therefore 8 → 0–2, not guaranteed 0.
3. **Shared-budget scarcity.** `maxRepairAttempts=1` means a source needing both segmentation and quote repair gets only one. Acceptable for v1 (R0 needed zero segmentation repairs); `repairSkipped` telemetry + admin-tunable value cover calibration. Raising the default is a settings-value decision, not a migration.
4. **240-char `failingQuoteExcerpt` bound** (`workflow-map-validator.ts:89`) may truncate long quotes; the repair design sidesteps this by sending full chunk text, but if a future failing quote is itself near the 2,000-char schema cap, the excerpt in telemetry won't contain it whole. Consider a full-quote field only if evidence shows the need.
5. **`deepSchemaAccepted` pool breadth:** the repair rides the `workflow_read` slot, whose capability gate excludes Gemini (deep-schema rejection) and Qwen/DeepSeek (no strict schema). Today's pool (`gpt-4.1` primary, Sonnet, Gemini) resolves to OpenAI — fine — but BO-2 must be rerun before seating Sonnet, per the recorded decision; a repair call inherits exactly the same constraint surface, nothing new.
6. **Broken tooling noted:** `scripts/verify-workflow-map-prod.mjs` references pre-Stage-1 columns and errors against the current schema; fix or retire before anyone relies on it for the R1 audit. `audit-r0-reader-drops.ts` hard-fails on post-R0 diagnostic vocabulary by design — use the release-map audit for anything after migration 94.
7. **Missing evidence I did not have:** raw production bytes of chunk 5 and the two full failing quotes (read-only review; the bounded excerpts and two independent inspections are consistent and sufficient for the defect classification). If the forced gate surprises us, that raw text is the first thing to pull via the extended audit script.

---

**Bottom line:** R0 stands. Ship the bounded, evidence-only quote repair (+fidelity clause + budget-guard hardening) in parallel with R1, prove it deterministically then with one forced production read, and have it green before R2. Expected: the 2 roots and all 6 cascades resolve, the degraded segment goes green, and the map becomes `validated` — with zero changes to evidence policy, validator behavior, immutability, degraded-status honesty, or the canonical stage plan.
