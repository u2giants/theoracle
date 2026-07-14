# Shape-Aware Reader Stage 2 — Segmentation Gate

Date: 2026-07-13 (America/New_York)

## Goal

Prove that the Stage 2 reader can classify the real POP Creations / Spruce Line corpus
before detailed per-shape reading, without losing source chunks or weakening quote-level
provenance. Stage 2 must preserve the Stage 1 process reader and persist the non-process
segments that Stage 3 will read.

## Implementation under test

- Six-shape extensible registry: process, responsibilities, reference, ruleset,
  conversation, narrative.
- One segmentation model call through the production `workflow_read` route, currently
  `openai/gpt-4.1` in this gate.
- Complete source coverage: every persisted chunk appears in at least one segment.
- Controlled overlap: a genuinely composite 4,000-character chunk may appear in
  differently shaped segments with separate titles/summaries.
- Deterministic validation for unknown IDs, duplicate IDs within a segment, omissions,
  non-contiguous groupings, and dominant shape.
- One bounded repair retry if validation required a source-integrity repair; deterministic
  narrative fallback remains if the retry still misses material.
- Existing workflow reading runs only for process segments. Non-process readers are Stage 3.
- Reader pipeline version participates in the source hash, preventing stale Stage 1 maps
  from being reused after this upgrade.

## Final real-data results

Command:

```powershell
corepack pnpm --filter @oracle/workers run verify:shape-segmentation-real
```

Result: **PASS, 6/6 fixtures**, generated 2026-07-14 01:00:58 UTC. All fixtures used
the production-selected `openai/gpt-4.1` route and passed on the first model attempt.

| Fixture | Chars | Chunks | Dominant | Shapes found | Segments |
|---|---:|---:|---|---|---:|
| `business-process.md` | 42,442 | 12 | process | narrative, process, reference, responsibilities, ruleset | 21 |
| `Licensed Team Responsibilities 2 - tagged.txt` | 16,847 | 5 | responsibilities | process, responsibilities, ruleset | 15 |
| `transcript-Book report overview.txt` | 30,290 | 8 | conversation | conversation, process, reference, responsibilities | 4 |
| `Team Communication and Product Details 2.docx` | 6,271 | 2 | narrative | narrative, process, responsibilities, ruleset | 4 |
| `SKU descriptions naming convention.pdf` | 5,206 | 2 | ruleset | reference, ruleset | 2 |
| Latest production-ingested Teams transcript | 7,145 | 2 | conversation | conversation | 2 |

The Book Report transcript is the important design proof: the same source produced
conversation segments plus a separate process segment that reconstructs the described
licensed/non-licensed design flow. That satisfies Albert's 2026-07-08 decision that a
meeting can be both conversation and process.

## What did not work

1. The first contract forced every chunk into exactly one segment. That failed on real
   composite chunks: the responsibilities file contains role duties plus embedded approval
   workflows, and the SKU file contains lookup examples plus rules. The permanent fix is
   controlled cross-segment overlap with at-least-once source coverage.
2. The first prompt over-classified the responsibilities file as process. Tightening the
   boundary to classify by passage purpose (role duties vs. end-to-end flow) produced both
   responsibility and process segments correctly.
3. The initial gate expected the Team Communication DOCX to be conversation. Inspection
   showed it is an explanatory memo, so narrative is correct; the final model also found
   its embedded process, responsibilities, rules, and references.
4. One intermediate business-process run copied a valid chunk UUID with one character
   changed. Deterministic validation caught it and preserved the omitted chunk as narrative.
   Production now adds one bounded repair retry with the exact valid ID list before using
   that fallback.
5. The first Teams fixture query admitted unbounded live Recall channels and made the
   validation process appear hung. The gate now selects a completed `teams_transcript`
   channel only and exits explicitly after flushing its report.

## Gate decision and next step

Stage 2 is green. Proceed to Stage 3: implement the non-process per-segment readers and
their element kinds, extraction directives, and deterministic per-shape coverage. Do not
retire the blind extraction fallback until every Stage 3 shape passes its real-data gate.
