# Codex evaluation of Kimi K3 reader improvement review

Date: 2026-07-26

## Invocation and coverage

- Kimi Code CLI version: 0.27.0
- Requested model: `kimi-code/k3`
- Session: `session_44c956d0-d403-47cf-b122-538b981f89a5`
- Result: successful, exit code 0
- Runtime: about 27.5 minutes
- Repository baseline: `main` at `2a13b570dcc0eb5cf60d9b8f9c95e4ff08d959d0`
- Repository changes made by Kimi: none
- Raw transcript: `.ai/reviews/kimi-k3-reader-improvement-result.jsonl`
- Full Kimi report: `.ai/reviews/kimi-k3-reader-improvement-review.md`

Kimi used the tracked repository file list as its coverage record. It reconciled all 453 tracked files:

- 415 files fully read
- 6 low-risk files substantially inspected
- 19 generated Drizzle files checked for consistency
- 1 binary viewed
- 12 permitted cache, lock, generated, or packaged files omitted

It fully read all 37 tracked Markdown files outside permitted cache exclusions, all 5 current review Markdown files, all worker code, all AI and engine packages, all database source files, all 67 handwritten migrations, the web application, scripts, tests, workflows, and root configuration.

## Verdict

Kimi's main conclusion is sound:

- R0 is healthy and complete.
- R1 can start now.
- The reader should receive one narrow quote-repair attempt in parallel with R1.
- The repair should be green before R2 starts.
- This does not need a new formal stage or a database migration.

## Evidence behind the recommendation

The production gate had two root quote failures. Both came from the same source chunk. The model selected the right text but copied it imperfectly:

- It dropped short lead-in text such as `The problem:` and `The fix:`.
- It changed lowercase `the` to uppercase `The`.
- One quote also changed Markdown formatting.

The strict validator rejected both quotes correctly. Four edge drops and two path drops followed from those two root failures. The full map remained strong, with 3.6 percent drops and 95.2 percent relationship evidence coverage.

## Agreed implementation

I agree with Kimi's proposed code design:

1. Add a strict repair response with `elementId`, `elementType`, `chunkId`, and `evidenceQuote`.
2. Use the existing configurable `workflow_read` model route.
3. Repair only root `quote_mismatch` and `quote_ambiguous` failures.
4. Never repair unknown chunks, foreign chunks, or uncovered chunks.
5. Require the repair to keep the original chunk ID.
6. Reject unknown IDs, wrong element types, duplicate repairs, and chunk moves.
7. Change only the failed quote in the temporary map result.
8. Run the same strict validator again with no relaxed rules.
9. Keep the repair only when it reduces the number of root failures.
10. Reuse the existing one-repair budget and repair reservation code.
11. Record attempts, skip reasons, and before-and-after counts in existing validation data.
12. Add prompt wording that says to preserve lead-ins, case, punctuation, and Markdown exactly.
13. Bump the workflow prompt and pipeline versions.

## Why this is the best path

- It fixes model copying errors without weakening evidence rules.
- It cannot move a quote to a different chunk.
- It cannot invent support for a failed map element.
- It makes one small extra model call at most.
- It uses existing settings, budgets, logs, and database fields.
- It avoids regenerating a good map because two quotes were copied badly.

## Files to change

- `packages/ai/src/prompts/workflow-read.ts`
- `apps/workers/src/lib/source-workflow-read.ts`
- `apps/workers/src/__verify__/r0-reader-validator.ts`
- `packages/ai/src/__verify__/workflow-read-smoke.ts`
- `packages/db/src/audit-r0-release-map.ts`
- `DECISIONS.md`
- `evals/shape-aware-stage2.md`
- `docs/configuration.md`

## Required release checks

- A repair changes only the selected quote field.
- The original map object is not changed.
- Chunk moves are rejected.
- Unknown IDs, wrong types, and duplicate repairs are rejected.
- An exhausted optional repair budget keeps the original result and completes the source read.
- A base-read budget failure still stops loudly.
- A repaired map is kept only when root failures decrease.
- Existing strict validator tests still pass.
- Strict response schema and adapter request tests still pass.
- A read-only replay checks the two real R0 failures against stored source text.
- One authorized production read confirms no evidence rule was relaxed.

The production target is zero root drops. A small number of honest edge drops may appear after the repaired nodes allow previously skipped edge quotes to be checked.

## Changes to earlier advice

- Kimi improved the earlier repair contract by requiring `elementType`; node and edge IDs can overlap.
- Kimi correctly rejected allowing the model to change `chunkId`.
- Character offsets are not worth adding now.
- A new repair setting and a new database migration are not needed.
- R1 is not blocked by this fix, but R2 should wait for the repair gate.

## Other findings

- `scripts/verify-workflow-map-prod.mjs` is stale and refers to removed or renamed database columns. It should be fixed or retired before anyone uses it for R1.
- `apps/workers/src/lib/schema-repair.ts` has no callers and hard-codes a route. It should not be reused.
- Four edge quotes were skipped after their endpoint nodes failed. They may expose real quote failures after node repair.
- `audit-r0-reader-drops.ts` covers the old map only. The release-map audit is the right check after migration 94.
