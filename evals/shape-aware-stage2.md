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

## Production task verification

Deployed Trigger.dev worker `20260714.1` ran `source-workflow-read` against the real
production `business-process.md` document in run `run_cmrjyc4mg3mq80pom8wpz2odn`.
Persisted map `9e84efda-755d-4a05-be5a-bbbadfce144e` records:

- Stage 2 segmentation: validated, 12/12 chunks covered, 19 segments, dominant `process`,
  zero integrity repairs.
- Persisted shapes: 5 process, 8 narrative, 4 reference, 2 responsibilities.
- Whole-map status: degraded because the existing Stage 1 workflow quote validator retained
  64 and dropped 101 graph items. This is a downstream process-reader quality finding; it did
  not fail or repair Stage 2 segmentation.

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

## 2026-07-21 — R0 validator/reference/coverage implementation gate

Scope: local implementation plus SELECT-only production audits. This session was explicitly
not authorized to deploy, mutate production, or supersede a production map, so it did not run a
new model-generated `business-process.md` read.

Local deterministic gates:

- PASS: `corepack pnpm --filter @oracle/workers run verify:r0-reader-validator`
- PASS: `corepack pnpm --filter @oracle/workers run verify:source-workflow-read`
- PASS: `corepack pnpm --filter @oracle/engines run verify:r5`
- PASS: `corepack pnpm --filter @oracle/ai run verify:workflow-read`
- PASS: workers, engines, AI, and DB package typechecks
- PASS after parent review: reader pipeline version/source hash advanced to
  `shape-reader-v2-r0-validator`, preventing silent reuse of pre-R0 maps for unchanged sources.
- CI-only: the fresh pgvector database migration gate is wired into `pr-check.yml`. It could not
  run on this workstation because Docker, Podman, `psql`, and WSL are unavailable.
- First CI execution exposed a test-environment defect before reaching the R0 schema: plain
  pgvector Postgres lacks Supabase's `auth` schema and `anon`/`authenticated`/`service_role` roles.
  The permanent CI fixture now creates only those Supabase-owned prerequisites in the guarded
  loopback-only `oracle_fresh` database before running the complete application migration chain.
- The next CI execution reached migration 31 and exposed a second historical bootstrap defect:
  its observability view had been amended to select `model_runs.dispatch_mode`, although migration
  60 introduces that column later. Migration 31 now declares the nullable column idempotently;
  migration 60 still owns its constraint and index, and existing production databases are unchanged.
- The following execution reached migration 49 and found a hidden-project-state assumption:
  security hardening referenced an optional `public.rls_auto_enable()` helper that no repository
  migration creates. Its privilege lockdown is now conditional on the helper existing, preserving
  production security without making a clean repository-built database depend on it.

Historical 101-drop audit:

- Command: `corepack pnpm --filter @oracle/db run audit:r0-reader-drops`, with the current
  production session-pooler supplied only as `R0_AUDIT_DATABASE_URL` from 1Password.
- Map `9e84efda-755d-4a05-be5a-bbbadfce144e`, document
  `ee1fa682-9e5c-4cf5-89c5-b2f95d047eea` (`business-process.md`): 64 kept, 101 dropped,
  historical drop ratio `101 / 165 = 61.2%`.
- 36 root nodes: `quote_not_found`. Decided disposition:
  `separately_scheduled_post_fix_replay`. The old telemetry retained element ID/reason but not
  the rejected quote or raw reader output, so it is impossible to decide honestly which of these
  would pass Markdown normalization versus remain a correct paraphrase rejection.
- 46 edges: `missing_endpoint_cascade`; disposition `cascade`.
- 19 paths: `missing_path_node_cascade`; disposition `cascade`.
- Zero persisted reasons fall into an unresolved classification. Historical important-relation
  evidence survival was `14 / (14 + 46) = 23.3%`; this is a reported outcome, not a weakened
  acceptance threshold. R0 now retains enough diagnostics/raw output for the next read to compute
  exact selected/alternate policy outcomes instead of repeating this telemetry limitation.

SELECT-only swimlane regression:

- Command: `corepack pnpm --filter @oracle/workers run verify:r0-production-replay`, with the
  current session-pooler supplied only as `R0_REPLAY_DATABASE_URL` from 1Password.
- Current map `a008239d-773f-4c31-b78b-6cf639697c82` replayed through the new validator under
  `vision_transcription_strict`: 58 nodes, 56 relations, 13 lanes, 0 paths; 0 root drops,
  0 cascade drops, and 56/56 relation evidence survived.
- Duplication regression: 0 duplicate node/relation IDs, maximum 1 current claim per map ref,
  and 0 refs with 3 or more claims. The previously scored answer-key coverage remains the pinned
  reader baseline because this audit replays persisted output and intentionally makes no model
  call; the R0 validator introduced no survival or duplication regression.

Gate decision: the R0 code and every deterministic/read-only gate available in this session pass.
The authorized post-deploy `business-process.md` model rerun remains separately scheduled; do not
claim a new post-fix drop ratio or alternate-policy split until that run produces R0 diagnostics.
