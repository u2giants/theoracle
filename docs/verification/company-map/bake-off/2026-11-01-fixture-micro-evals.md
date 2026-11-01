# Model bake-off — fixture micro-evals (2026-11-01)

Protocol: `docs/company-map/model-stage-job-brief.md` §5, cheapest evidence
first. This file is the micro-eval evidence the results table accepts (§5:
"no number enters it without an eval_run id or a micro-eval output file under
`docs/verification/company-map/bake-off/`").

**Method.** One fresh database per candidate on the shared test services; the
five invented fixtures (253 chunks, incl. the 246-chunk transcript) run through
the production pipeline exactly as production runs it: reading + embeddings,
flat extraction (ScaleDown primary, frontier fallback), relationship
extraction, entity resolution, graph projection. **Community reports are
excluded from the micro-eval** (that stage is the cost center and waits for
finalists, per §5 "real-corpus graph rebuilds ... only for finalists"). Then
the five seed questions run through the step-11 eval. All runs used the
production prompts verbatim (§7 "testing equals production").

**Frozen across runs:** grader `anthropic/claude-sonnet-4.5` (§7 decision 3),
conversation model `anthropic/claude-haiku-5.5` (the assigned seat), vision
`openai/gpt-4.1`, embeddings `openai/text-embedding-3-large` (1024 dims),
ScaleDown enabled. `BRAIN_FRONTIER_MODEL` is the only variable in the
heavy-seat pass. All runs included the PR #307 empty-content rescue.

Caveats: 5 seed questions is a noise-level instrument (one question = 0.2 of
mean); means here are comparable across candidates but NOT comparable to the
2026-10-30 full-pipeline numbers (0.47 / 0.40), which included community
reports. Step-11 real-corpus swaps are the decision instrument and are still
pending for finalists.

## Heavy seat (JSON stages: flat fallback, relations, resolve, reports, recommend)

| Candidate (BRAIN_FRONTIER_MODEL) | Price in/out $/M | Fixture mean | eval_run id | relations | entities | Truncations | Notes |
|---|---|---|---|---|---|---|---|
| `anthropic/claude-sonnet-4.5` (incumbent) | 3 / 15 | 0.5333 | `269558df-9300-48e5-91f3-241505c257d4` | 530 | 454 | 4 | baseline, same-day; one `describe` skipped on empty content after rescue (stage continued) |
| `google/gemini-3.1-flash-lite` | 0.25 / 1.5 | 0.5333 | `b21c92a6-f507-4aaf-a65d-5c056bc68814` | 423 | 452 | 0 | parity on mean; 17% fewer relations than baseline — recall check required before seating |
| `z-ai/glm-5.3-flash` | 0.015 / 0.154 | 0.6 | `4f88dd04-96d5-48c4-939a-490934b5a1f9` | 495 | 438 | 5 | best mean; 5 truncations at 2000 tokens (item-wise salvage kept them); verbose completions |
| `qwen/qwen3.7-flash` | 0.03 / 0.13 | FAIL | — | — | — | — | relations stage returned empty content even after the PR #307 rescue (reasoning-tier behavior) — **disqualified** for JSON stages (dead-end-4 class) |

## Conversation seat (BRAIN_CHAT_MODEL; same Sonnet-built graph, frozen grader)

| Candidate | Fixture mean | eval_run id | Answer lengths | Notes |
|---|---|---|---|---|
| `anthropic/claude-haiku-5.5` (assigned seat) | 0.5333 | `269558df-9300-48e5-91f3-241505c257d4` | 742–2517 chars | 5/5 non-empty (the empty-content gate); seeded in production |
| `z-ai/glm-5.3-flash` | 0.6 | `0b732084-1c76-4c72-8a2e-82266c5d524b` | 826–3708 chars | above Haiku on 5 seeds (inside noise); longer answers |
| `google/gemini-3.1-flash-lite` | 0.4 | `eb516e0c-2fc7-4401-815f-8cfb40df058a` | 268–1144 chars | below Haiku; short answers. First attempt crashed the answer path on a non-uuid `source_id` — fixed in PR #310, rerun recorded here |

## Defects found by this bake-off

1. `qwen/qwen3.7-flash` (and the earlier `deepseek/deepseek-v4.1-flash`,
   `qwen/qwen3.8-flash`) burn `max_tokens` on reasoning and return empty
   content in JSON mode; the rescue retry is not enough at 2x budget. Keep
   reasoning-flagged tiers off the JSON seats.
2. Global answers crashed on a citation with a non-uuid `source_id`
   ("REPORTS") — fixed in PR #310 (drop such citations, mark `(uncited)`).
3. GLM 5.3 Flash truncates relations JSON at 2000 tokens more often (5
   chunks); the item-wise salvage kept the runs clean but tail relations are
   at risk — relevant if it takes the relations seat.

## Provisional read (not a seating decision)

- **Heavy seat finalist: `z-ai/glm-5.3-flash`** (best fixture mean at 1/100th
  of Sonnet's input price). Before seating: step-11 real-corpus swap + the
  §4.4 relations-recall probe (its 495 vs baseline 530 relations), and a
  community-reports quality pass (§4.6 (a)+(b)) since that slot is human-read.
- **Second finalist: `google/gemini-3.1-flash-lite`** if GLM fails the recall
  pass (mean parity, but 423 relations is the recall warning).
- **Conversation seat: stays `anthropic/claude-haiku-5.5`** (Albert's
  assignment; the challengers are inside the 5-question noise band — GLM
  above, Gemini below; §4.7's report-back triggers only when the assigned seat
  lands materially BELOW).

Runs executed 2026-11-01 00:00–00:25 UTC from the edge-dev coordinator against
the shared test services; each candidate used its own database and the shared
FalkorDB `company` graph (rebuilt per run). Runner and logs are machine-local;
every number above is reproducible from the recorded `eval_run` rows
(`cmap.eval_run.models` manifests the exact configuration — PR #297).
