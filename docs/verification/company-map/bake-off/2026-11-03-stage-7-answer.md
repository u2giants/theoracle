---
summary: Results of the stage 7 question-answering bake-off of 2026-11-03 for BRAIN_CHAT_MODEL on twenty draft questions.
kind: proof
status: done
read-when: checking the answer-model choice
---

# Stage 7 bake-off — question answering (2026-11-03)

Stage: `brain/answer/answer.py` `answer_question`, model from `BRAIN_CHAT_MODEL`.
Run on 2026-11-03, 11:45 AM – 12:45 PM EST, on the test services host.
Machine-readable twin: `2026-11-03-stage-7-answer.json`.

## Candidates and availability

All five listed ids exist on OpenRouter (`GET /api/v1/models`, checked 11:45 AM EST). The duplicate DeepSeek id was tested once.

| Model | Available | Price in / out (USD per 1M tokens, OpenRouter, 2026-11-03) |
|---|---|---|
| anthropic/claude-haiku-5.5 (current seat) | yes | 0.10 / 0.50 |
| openai/gpt-6-luna | yes | 0.10 / 0.50 |
| deepseek/deepseek-v4.1-flash | yes | 0.045 / 0.50 |
| google/gemini-3.8-flash | yes | 0.825 / 4.125 |
| z-ai/glm-5.3-flash | yes | 0.0313 / 0.0846 |

Judge: `anthropic/claude-sonnet-5.5` (present on OpenRouter; the fixed judge).

## Method

- Instrument: a private clone of `cmap_bake_5` (8 real sources, 97 embedded chunks, 969 entities) projected with `run_project` into a session-only FalkorDB (969 nodes, 752 edges). Both were removed afterwards; `cmap_bake_1..6` and the shared FalkorDB were not touched.
- Mode: **local only**. `cmap_bake_5` has no community reports, and generating them (stage 6) was skipped to stay inside budget, so global and auto mode were not tested.
- Questions: the 20 real-corpus questions in Appendix A of `HANDOFF.d/2026-11-02T2057Z-edge-dev-mimo-model-overhaul-bakeoff-round2.md`. **These are drafts awaiting Albert and Ilona's edits**, so the scores here should be read as a comparison between models, not as a final quality number. The five fixture seed questions were not used.
- Settings: `BRAIN_EMBED_MODEL=openai/text-embedding-3-large` (1024 dims), ScaleDown compression on, production prompt and code unchanged. Each candidate ran in its own process with only `BRAIN_CHAT_MODEL` changed.
- Grading: the judge saw the question, the final answer (after quote validation and renumbering), the stated unknowns and the surviving citations with their source titles. It scored five 0–5 criteria: correctness against the cited evidence, cross-source synthesis (≥3 sources), honesty about unknowns, citation validity and readability. Quality = sum ÷ 25. A hard failure scores 0. The first judge pass ran out of output tokens on 35 of the 100 answers (max_tokens 600, used up by its own reasoning). Those 35 were regraded with max_tokens 4000; no judge errors remain.
- Empty content: every chat-completions call was counted, including any whose content came back empty and was rescued by the PR #307 retry in `brain/llm.py`. A call still empty after the rescue counts as a stage failure; none occurred.

## Results (20 draft questions, local mode)

| Model | Quality 0–1 | Correct | Synth | Honest | Cite valid | Read | ≥3 sources | Hard fails | Empty→rescued | Latency mean / p50 s | Tokens in / out | $ sample | $ per question | $ per 1,000 q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| z-ai/glm-5.3-flash | **0.682** | 2.95 | 3.70 | 3.65 | 2.85 | 3.90 | 14/20 | 0 | 20 | 44.8 / 45.7 | 2,234,084 / 204,455 | 0.087 | 0.0044 | 4.36 |
| anthropic/claude-haiku-5.5 | **0.680** | 3.05 | 3.30 | 4.00 | 2.85 | 3.80 | 12/20 | 0 | 11 | 58.0 / 61.0 | 2,633,031 / 265,421 | 0.396 | 0.0198 | 19.80 |
| deepseek/deepseek-v4.1-flash | 0.674 | 3.40 | 3.75 | 3.30 | 3.10 | 3.30 | 14/20 | 0 | 17 | 79.6 / 82.6 | 2,030,972 / 328,293 | 0.256 | 0.0128 | 12.78 |
| google/gemini-3.8-flash | 0.574 | 2.95 | 3.11 | 2.74 | 2.74 | 3.58 | 11/20 | 1 (q9) | 0 | 76.1 / 57.1 | 1,861,176 / 190,203 | 2.320 | 0.1160 | 116.00 |
| openai/gpt-6-luna | 0.568 | 3.00 | 2.95 | 4.05 | 1.25 | 2.95 | 12/20 | 0 | 0 | 24.3 / 23.5 | 1,055,927 / 48,296 | 0.130 | 0.0065 | 6.49 |

The criterion columns are means over graded answers on a 0–5 scale. Token totals include rescue retries and the `_ask` retries.

The gemini q9 failure: the response was not valid JSON on all three attempts (its `answer_md` was cut off), so the call raised `frontier answer failed after retries`.

### Cost projection (formula)

`$ per question = (tokens_in × price_in + tokens_out × price_out) ÷ 20`, and `$ per 1,000 questions = $ per question × 1,000`.

Stage 7 is billed per question, not per corpus, so the cost does not grow with the corpus. Retrieval is capped at 8 seed entities, 60 nodes, 150 edges and 30 chunks, and ScaleDown compresses passages above 6,000 tokens. Projected $ per question is therefore the same on the current corpus (97 chunks) and on a 100× corpus (~10,000 chunks); the JSON fields `cost_usd_corpus` and `cost_usd_100x` hold it. The assumption is that the caps stay the same. At 100× the prompt might grow slightly because a denser graph fills the edge cap; that is bounded by the caps.

## Recommendation

**Winner: keep `anthropic/claude-haiku-5.5`.** It is statistically tied with GLM and DeepSeek on quality (0.674–0.682 is within judge noise on 20 draft questions). It has the best honesty score among the top three, which matters most for an answer read by people. It is the current seat, so nothing changes. Its empty-content problem is real (11 calls) but fully handled by the PR #307 rescue. Cost is about $20 per 1,000 questions.

**Runner-up: `z-ai/glm-5.3-flash`.** It has the top mean by a hair, about 4.5× cheaper than Haiku ($4.36 per 1,000 questions) and faster (p50 46 s). It is not the winner because **every** first call (20 of 20) came back empty and only the rescue retry produced an answer. A change to that rescue path, or a provider-side change, would turn it into a 100% failure. Its correctness score (2.95) is also lower than DeepSeek's.

Not recommended:
- DeepSeek has the best correctness and synthesis but is the slowest (p50 83 s) and had 17 rescues.
- Gemini is the most expensive by far, had one hard failure and scored lowest on honesty.
- GPT-6 Luna is fast and cheap, but its quotes often fail validation (citation validity 1.25), which leaves many sentences marked (uncited).

Re-run this comparison once the 20 questions are final, and also in global mode once community reports exist.

## Budget note

Actual spend was about **$4.56**: candidates $3.19, of which Gemini alone was $2.32, plus judge about $1.37 including the 35 failed first-pass gradings. That is **over the $2.50 per-session limit** in the common rules. The overrun came from Gemini's price and the judge regrade. The OpenRouter key had $14.91 left before the judge started (12:21 PM EST), so the $5 floor was never crossed.

## Reproducibility

- Harness: the scripts `run.py`, `judge.py` and `agg.py`, plus every raw answer, grade and aggregate (`ans.*.jsonl`, `grades.jsonl`, `grades.round1.jsonl`, `agg.json`), are kept in the bake-off coordinator's shared notes folder under `s7-answer/` (outside the repo).
- `run.py` wraps `brain.llm`'s httpx post to record per-call usage, empty content and rescue. It calls `answer_question(q, mode="local")` with `BRAIN_CHAT_MODEL=<candidate>`.
- OpenRouter generation ids are in the raw usage records. No eval_run rows were written, because this was a direct harness run rather than the admin eval page.
- DB clone `cmap_s7_answer` from template `cmap_bake_5`; session FalkorDB on its own port; both removed at 12:45 PM EST.
