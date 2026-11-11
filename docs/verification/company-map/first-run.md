---
summary: "Step 14 evidence: first real-corpus Company Map run on the hosted brain with the eight imported files."
kind: proof
status: done
read-when: checking proof that the pipeline ran end to end on real data
---

# Company Map — first real-corpus run (step 14)

Hosted brain: `oracle-brain` on Coolify (health `{"ok":true,"db":true,"graph":true}`);
web: https://oracle.designflow.app (login → `/map`). Corpus: the 8 Oracle-1
files imported 2026-10-30 (bucket batch of 26 objects: 8 new, 18 already
ingested). Pipeline completed end to end; this file is the step-14 evidence.

## Pipeline counts (prod `cmap` schema, verified 2026-11-02)

| Table | Rows | Notes |
|---|---|---|
| source | 8 | 1 flowchart PNG, 1 business-process MD, 1 responsibilities TXT, 4 SOP PDFs, 1 Teams transcript |
| chunk | 97 | |
| extraction | 289 | ScaleDown primary path (`BRAIN_SCALEDOWN_ENABLED=true`) |
| mention | 2045 | |
| entity | 977 | |
| relation | 862 | |
| community | 867 | 441 L0 + 425 L1 + 1 L2 (the company report) |
| recommendation | 7 | the `recommend` job chained after `communities` and is **done** |
| open_question | 4656 | extracted open questions for the interview queue (interviews stay OFF) |

Jobs: `read_source` 8/8, `classify_extract` 8/8, `relations` 8/8, `resolve`,
`project`, `communities`, `recommend` all **done**. One historical
`communities` failure (2026-10-30, "embeddings call failed after retries" —
daily cap exhaustion) was resumed via `POST /map/rebuild`; stored-report reuse
kept the 440 L0 reports already written.

## Models (Coolify env, live)

`BRAIN_FRONTIER_MODEL=anthropic/claude-sonnet-4.5`,
`BRAIN_CHAT_MODEL=anthropic/claude-haiku-5.5` (seated 2026-10-31 after the
PR #307 empty-content fix; gate: 5/5 seed answers non-empty),
`BRAIN_EVAL_MODEL` unset → frozen grader falls back to the frontier model,
`BRAIN_VISION_MODEL=openai/gpt-4.1`,
`BRAIN_EMBED_MODEL=openai/text-embedding-3-large` (1024 dims),
ScaleDown enabled, `BRAIN_MAX_FRONTIER_CALLS_PER_JOB=3000`.
Migration `004_eval_models.sql` applied to prod (`cmap.eval_run.models`).

## Eval (step-11 seed questions, real corpus)

Five seed questions loaded to prod; eval run `b4cbe36b-f7ba-4b88-aa61-afdebfa43c9e`
completed as **eval_run `5cd3a206-de53-4611-8732-cf047491572e`, mean 0.2**
(grader `anthropic/claude-sonnet-4.5`, answers `anthropic/claude-haiku-5.5`;
`cmap.eval_run.models` records the full manifest).

Read that number carefully: the five seed questions' expected points are
written against the **invented fixture corpus** (names, systems and durations
like "Jessica records the sign-off in the Artwork Log"); the real documents
describe the real roles and systems, so the grader marks those points missing
even when the answers are sound. Per-question scores: 0.667 / 0.333 / 0 / 0 / 0
— the two that overlap real-corpus facts score; the three fixture-specific
ones do not. The same five questions scored **0.5333** on the fixture corpus
under identical seating (eval_run `269558df-9300-48e5-91f3-241505c257d4`).

The real-corpus instrument is the 20 owner questions
(`eval-questions-draft-20.md`, drafted for Albert and Ilona, each needing 3+
sources). The eval page is ready for them.

## Cost and spend controls

Shared OpenRouter key, $25/day cap (kept at the owner's direction). The
real-corpus run spent most of one day's cap on community reports (the cost
center); the model bake-off's fixture micro-evals
(`docs/verification/company-map/bake-off/2026-11-01-fixture-micro-evals.md`)
show `z-ai/glm-5.3-flash` as the heavy-seat finalist at roughly 1/100th of
Sonnet's input price — seating waits for the real-corpus swap pass.

## Owner review (pending — plan step 14 items)

1. Albert and Ilona: mark wrong items on the first Map (30 minutes).
2. Albert: message the Teams bot "hi" from his own account (interviews to
   employees stay OFF).
3. Albert and Ilona: approve/edit the 20 draft eval questions.

Verdict goes verbatim into the plan STATUS row when given.
