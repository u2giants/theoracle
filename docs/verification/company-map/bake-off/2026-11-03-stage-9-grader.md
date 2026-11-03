# Stage 9 — eval grader bake-off (2026-11-03)

Stage: `brain/eval/run.py` `grade_answer` (prompt `prompts/grade.md`, JSON mode, temperature 0, max_tokens 800, 3 attempts, shared empty-content rescue), model set per run via `BRAIN_EVAL_MODEL`.

## Candidates and availability

| Model | Available | Note |
|---|---|---|
| deepseek/deepseek-v4.1-flash | yes | |
| z-ai/glm-5.3-flash | yes | |
| qwen/qwen-3.8-27b | **no** | not in OpenRouter `/api/v1/models` today (no qwen 3.8 27b id of any form); not substituted |
| openai/gpt-6-luna | yes | |
| anthropic/claude-haiku-5.5 | yes | |
| meta/muse-spark-1.3-contributor | yes | |

Judge: `anthropic/claude-sonnet-5.5` (available; no fallback needed).

## Method

- **Items (35).** 45 stored results in `cmap.eval_run.results` across `cmap_bake_1,2,3,5,6` (`cmap_bake_4` and `brain_test` had no eval runs) — 5 questions × 9 distinct answers, all originally graded by the retired sonnet-4.5 seat. 30 picked evenly across stored score (13 at 0, 9 at 0.33, 6 at 0.67, 2 at 1.0), plus 5 hand-written **corrupted** answers (one per question) planting 9 contradictions in total alongside correct cited sentences. Read-only; no DB was modified.
- **Reference.** Sonnet-5.5 graded all 35; I reviewed every point where it disagreed with the stored sonnet-4.5 grade or my planted expectation (items 3, 4, 6, 15, 17, 18, 19, 27, 29, 31). Two overrides: item 18 point 0 → covered (answer places the stall between licensor email and Artwork Log entry, with citations); item 29 point 0 → covered (consistency with item 27, which names Jessica with the same hedge). Judge's 31 point 1 contradiction ("nothing re-enters the queue") accepted as a genuine contradiction.
- **Runs.** Each candidate graded the 35 items once through the production `grade_answer` path (harness wraps `_post_chat` only to record latency/usage), then re-graded 10 items (every 3rd) for stability. 6 parallel workers.
- **Metrics.** point agreement = share of 105 point labels (covered/missing/contradicted) equal to the reference; score correlation = Pearson of per-item score vs reference score; contradiction recall = reference contradictions found (all 9 are in corrupted items); false contradictions = contradicted where reference is not; bias = mean(candidate score − reference score); stability = identical labels on both runs; JSON invalid = raw replies that are not bare JSON (all were still recovered by `parse_model_json`, so 0 grade failures).
- **Quality score 0–1** = 0.4·agreement + 0.2·correlation + 0.2·stability + 0.2·contradiction recall − 0.01·false contradictions.

## Results

Prices from OpenRouter `/api/v1/models` as of 2026-11-03 ($/M in/out): deepseek-v4.1-flash 0.045/0.50, glm-5.3-flash 0.0313/0.0846, gpt-6-luna 0.10/0.50, claude-haiku-5.5 0.10/0.50, muse-spark-1.3-contributor 0.10/0.20, judge sonnet-5.5 2.00/10.00. Cost = tokens_in·price_in + tokens_out·price_out over 45 calls.

| Model | Quality | Agreement | Corr | Contra. found | False contra. | Bias | Stable | Fails | Latency med/p90 s | Tokens in/out | $ sample | $ 20-q run | $ 100x |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-luna | 0.88 | 0.895 | 0.91 | 9/9 | 4 | -0.053 | 9/10 | 0 | 3.39 / 9.52 | 25,711 / 12,164 | 0.0086 | 0.0039 | 0.38 |
| anthropic/claude-haiku-5.5 | 0.796 | 0.876 | 0.849 | 7/9 | 6 | +0.008 | 9/10 | 0 | 1.82 / 2.61 | 38,236 / 13,999 | 0.0108 | 0.0048 | 0.48 |
| deepseek/deepseek-v4.1-flash | 0.796 | 0.895 | 0.892 | 9/9 | 8 | -0.036 | 7/10 | 0 | 6.19 / 21.78 | 26,595 / 50,118 | 0.0263 | 0.0117 | 1.17 |
| meta/muse-spark-1.3-contributor | 0.794 | 0.886 | 0.9 | 9/9 | 10 | -0.055 | 8/10 | 0 | 14.54 / 22.42 | 24,914 / 49,131 | 0.0123 | 0.0055 | 0.55 |
| z-ai/glm-5.3-flash | 0.708 | 0.79 | 0.644 | 6/9 | 3 | +0.152 | 8/10 | 0 | 1.28 / 5.27 | 25,355 / 5,186 | 0.0012 | 0.0006 | 0.05 |
| *judge sonnet-5.5* | — | 0.981 | 0.972 | 9/9 | 0 | -0.019 | 9/10 | 0 | 1.7 / 3.06 | 38,236 / 7,388 | 0.1504 | 0.0668 | 6.68 |

Projection formulas: grading cost scales with the number of questions, not chunks, so "current corpus" = one 20-question eval run = 20 × ($ sample ÷ 45); "100x" = 2,000 grades (assumes the question set grows with the corpus). The judge's agreement is with the reviewed reference built from its own output, so it is not an independent score; its 9/10 stability (one flip, item 18/29 class of hedged answers) is.

## Recommendation

- **Winner: openai/gpt-6-luna.** Ties the best agreement (0.895), best correlation (0.91), 9/10 stable, finds all 9 planted contradictions with only 4 false ones, ~$0.004 per 20-question run. Slight strictness bias (−0.05) — not generosity drift.
- **Runner-up: anthropic/claude-haiku-5.5.** Fastest strong option, 9/10 stable, unbiased on score, but missed 2/9 planted contradictions — the generosity failure the brief warns about.
- No candidate meets the brief's bar of identical indexes on every re-run (best is 9/10, same as the judge). Since this stage is about trust and a 20-question run with sonnet-5.5 costs ~$0.07, keeping sonnet-5.5 as the frozen grader for the next cycle and gpt-6-luna as its cheaper successor-in-waiting is the conservative choice; the switch must happen between cycles, never mid-cycle.
- Not recommended: deepseek-v4.1-flash (7/10 stable, slow), muse-spark-1.3-contributor (over-calls contradictions, slowest), glm-5.3-flash (+0.15 generous, misses contradictions).

## Reproducibility

- Source eval runs: `cmap_bake_1` (3 runs), `cmap_bake_2`, `cmap_bake_3` (1 each), `cmap_bake_5`, `cmap_bake_6` (2 each), on the test services host; item `src` field records db + run-id prefix.
- Harness, item set, reference labels and raw replies were kept in the session scratch area (not committed: they contain full answer text). Harness = production `grade_answer` with `BRAIN_EVAL_MODEL` set per process; corrupted answers and reference overrides are described above.
- Spend: ~$0.21 total across all runs (OpenRouter key limit_remaining was $24.57 before starting).
- Run window: 2026-11-03, 11:43 AM – 11:51 AM EST.

## Follow-up: grade prompt revision (adopted 2026-11-03, 12:30 PM EST)

Luna's 11 disagreements with the reference fell into two patterns: (a) calling a point *contradicted* when the answer only said the data does not show or confirm it, or listed other causes; (b) refusing *covered* when a cited sentence stated the fact with a hedge (person in one source, role in another). `prompts/grade.md` now defines contradicted as a positive conflicting assertion, says "data does not show" is missing, and says hedged-but-stated cited facts are covered. Albert approved adoption ("yes").

Same 35 items, same reference, revised prompt:

| Model | Agreement | Corr | Contra. found | False contra. | Bias | Stable |
|---|---|---|---|---|---|---|
| openai/gpt-6-luna (old → new) | 0.895 → 0.933 | 0.91 → 0.925 | 9/9 → 9/9 | 4 → 3 | −0.053 → −0.044 | 9/10 → 8/10 |
| anthropic/claude-sonnet-5.5 (old → new) | 0.981 → 0.99 | 0.972 → 0.986 | 9/9 → 9/9 | 0 → 0 | −0.019 → −0.010 | 9/10 → 8/10 |

Luna and Sonnet agree on 92% of point labels when both use the revised prompt. The stability dip appears in both models at n=10 and is within noise. Extra spend ≈ $0.17. Because this changes the grading instrument, eval scores recorded before this change (prompt hash differs in `cmap.eval_run.prompt_hashes`) are not directly comparable with later ones.
