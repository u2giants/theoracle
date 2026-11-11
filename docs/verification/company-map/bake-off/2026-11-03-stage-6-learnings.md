---
summary: Learnings from the stage 6 community-reports bake-off, chiefly the 4,000-token output cap finding.
kind: proof
status: done
read-when: re-running the community-report comparison or changing its output limit
---

# Stage 6 (community reports) bake-off — what we learned

Date: 2026-11-03 (run 11:40 AM–12:20 PM EST). Results: [2026-11-03-stage-6-community-reports.md](2026-11-03-stage-6-community-reports.md) and its `.json`. Follow-up issue: [#347](https://github.com/u2giants/theoracle/issues/347).

## 1. Outcome in one paragraph

Six candidates wrote the same 12 community reports (9 L0, 2 L1, 1 company report) from a clone of `cmap_bake_5`; `anthropic/claude-sonnet-5.5` graded each. **Winner `openai/gpt-6-luna`** (quality 0.816, fewest unsupported claims, ~$1.07 for the current corpus, ~$107 at 100×). **Runner-up `meta/muse-spark-1.3-contributor`** (0.759, ~$0.80 / ~$80). Total spend was about $1.10 (≈$0.10 in reports, ≈$0.98 in judging).

## 2. The most important finding: the 4,000-token output cap

- Every invalid report across all six models was a truncation: the call returned exactly 4,000 completion tokens (gemini 3,996) and the JSON was cut mid-finding. No model returned malformed JSON for any other reason, and no model refused or returned empty content.
- The cap is `MAX_TOKENS = 4000` in `apps/brain/brain/resolve/resolve.py`, shared by every frontier stage. Reasoning tokens count against it on reasoning models.
- The company (L2) report is the longest output (summary + findings + "Top 10 cross-department issues"); 4 of 6 models truncated it, including the winner. In production this is fatal: `run_communities` raises `company community report failed after retries`, because the retry resends the same cap.
- The `brain/llm.py` rescue does not help here: it only fires on *empty* content, not on truncated content.
- Fix is tracked in [#347](https://github.com/u2giants/theoracle/issues/347): give reports their own larger budget rather than raising the shared constant.

## 3. Model-by-model observations

- **gpt-6-luna**: concise (lowest output tokens of the strong models, 21.5k for 12 reports), best faithfulness (8.45) and readability (8.0). Tone is plain and analytical; it states policy-vs-practice conflicts clearly.
- **muse-spark-1.3-contributor**: very cheap, consistent latency (max 30 s), good citations; coverage slightly weaker (7.18).
- **glm-5.3-flash**: the only 12/12 and the cheapest, and it writes the most findings (100), but the judge counted the most unsupported claims (33) and one finding cited no valid source. One call took 114 s.
- **claude-haiku-5.5**: good quality (0.789) and best coverage (8.22) but verbose; it truncated the three largest L0 communities (24–40 entities).
- **deepseek-v4.1-flash**: highest output tokens (65k) with heavy reasoning, 5 of 12 truncated, 33 s median latency. Not suitable at a 4k cap.
- **gemini-3.8-flash**: about 10× the price of the others (~$1,110 at 100×), 3 truncations, many unsupported claims. Not recommended.

## 4. Facts about the corpus and the code

- The real clone gives **416 L0 and 399 L1** communities with the production Leiden settings (seed 0). The brief's 867 total was used for projections; 416 + 399 + 1 = 816 is the current measured count, so projections are slightly conservative.
- Most L1 communities contain a single L0 child (399 L1 vs 416 L0): the L1 layer at resolution 0.5 barely groups anything on this corpus, so almost every L1 call re-summarises one L0 report. Worth revisiting in the community design; it nearly doubles report cost for little value.
- `run_communities` reads Postgres only. FalkorDB/graph projection is **not** needed to bake-off reports, so no graph container was started.
- Context builders (`_context_l0`, `_context_reports`) and the prompt can be called directly for a fixed sample without writing to `cmap.community`; this is how the bake-off avoided running all communities.
- Entity names in reports include employee names; result excerpts in this public repo were redacted to `[person]` and source ids to `[source]`.

## 5. Method notes that worked (and one that did not)

- Running each model as its own detached background process (started inside `op_run` so the key stays in the environment) finished all six in about 10 minutes.
- **Did not work:** running the bake script in the foreground of `op_run`; it hit the tool's time limit and the process died with no output saved. Detach long runs and write per-model files.
- Judging cost ~10× the reports themselves (Sonnet 5.5 at $2/$10 per 1M tokens reading 12k-token contexts). Budget judges separately.
- The test database clone `cmap_s6_reports` was dropped after the run (the results doc's note that it was left in place is superseded).

## 6. What is still open

- [#347](https://github.com/u2giants/theoracle/issues/347): larger output budget for reports, then rerun the 12-report sample on the chosen model to confirm 12/12 before switching production.
- Coordinator: consolidate stage 6 with the other stages and decide the production model.
