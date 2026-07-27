# Codex evaluation of GLM 5.2 reader-improvement review

Date: 2026-07-22

## Invocation evidence

- Qwen Code version: `0.20.1`
- Requested and actual model: `glm-5.2`
- Successful session: `5f174808-0614-4f8b-b815-0c4ba0fe13c5`
- Exit code: `0`
- Duration: 821.5 seconds
- Model requests/errors: 28/0
- Tool calls: 92 (91 successful, one search failure)
- Tokens: 1,993,954 total; 1,646,720 cached
- Workspace changes made by GLM: zero

Resumed corrective pass:

- Same session and actual model: `5f174808-0614-4f8b-b815-0c4ba0fe13c5`, `glm-5.2`
- Exit code: `0`
- Duration: 362.2 seconds
- Turns: 4
- Workspace changes made by GLM: zero
- Corrected result: `.ai/reviews/qwen-glm52-r0-improvement-resumed-review.md`

The brief gave GLM the complete repository manifest requirement and access to the repository. Its
successful review deeply traced the reader path but did not actually read every tracked file: the
repo has 453 tracked files, including 41 tracked Markdown files and about 400 code/config/migration
files. GLM fully read the critical reader/validator/plan/eval paths and sampled or inventoried the
remainder. A first corrective continuation explicitly requiring full coverage ran for 20 minutes
and timed out. After quota reset, the same session resumed successfully and issued a corrected
review, but still honestly reported that unrelated UI, migrations, and roughly 27 Markdown files
were inventoried rather than fully read because its background readers received 429 errors.
Therefore the result is a strong focused repository review, not a literal line-by-line review of
all tracked files.

## GLM's main verdict

R0 should stand and R1 should proceed. The validator is correct. The best improvement is one bounded
workflow-read repair attempt that asks the model to replace failed quotes with exact text and then
runs the unchanged deterministic validator again. In its corrected review, GLM withdrew its
full-map regeneration and separate-setting proposals and agreed with the narrower design below.

## Independent evidence check

The production `validation_json` and cited chunk show both root failures come from chunk index 5.
Both failed quotes have 100% word-token overlap with the source. In each case the model omitted a
lead-in (`The problem:` or `The fix:`) and capitalized the following source word from `the` to `The`;
one quote also omitted Markdown escape characters. This proves a quote-copy fidelity defect, not a
semantic extraction error, segmentation defect, or validator defect.

## Agreed direction

Accept the bounded repair concept, but make it smaller and safer:

1. Do not regenerate the complete workflow map. Use a strict repair schema returning only
   `{ elementId, chunkId, evidenceQuote }` replacements for root `quote_mismatch` elements.
2. Patch those fields only in the in-memory, not-yet-persisted model output, then rerun the existing
   `validateWorkflowMap`. Graph identity, labels, lanes, edges, and paths must not change.
3. Reuse the existing source-level `source_reader_max_repair_attempts_per_source` and
   `SourceReaderBudget.reserveRepair` for the first implementation. Do not add a setting/migration
   until production evidence shows segmentation and quote repairs need independent quotas.
4. Persist attempt telemetry: requested element IDs, before/after root and cascade counts, whether
   the repair improved, budget use, and a bounded audit hash. Never persist source text twice.
5. Advance the reader pipeline/prompt version so unchanged documents cannot reuse pre-repair maps.
6. Keep every source quote policy and degradation threshold unchanged.

## Stage decision

This does not reopen or invalidate R0, and it does not block R1's mandatory production-data audit or
R1 DDL. Treat it as an R1-parallel reader-quality improvement that must be green before R2 begins
multiplying pass-2 readers. Do not invent a new formal `R1.5` stage unless the canonical plan is
deliberately amended.

## Smallest next experiment

The production diagnostics and source chunk have already been inspected read-only. Both roots use
the same chunk and show the same proven failure class, so another SQL-only inspection adds no new
information. Implement the targeted repair behind a test seam first, replay the persisted failing
output locally against the cited chunk, and prove that only the two quote fields change while all
graph IDs and non-evidence fields remain byte-identical. Then run one authorized forced production
read. Acceptance: root drops decrease from 2 to 0 or 1; cascades correspondingly fall; swimlane
regression remains unchanged; no fuzzy document match is admitted; budget remains within the
existing caps. This experiment does not block R1.
