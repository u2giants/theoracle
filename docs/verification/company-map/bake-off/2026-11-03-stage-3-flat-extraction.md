# Stage 3 — Flat extraction (frontier fallback) bake-off, 2026-11-03

Run 11:40 AM – 12:10 PM EST on the test services host. Owner request (2026-11-03): evaluate new models for all stages; claude-sonnet-4.5 retired.

## Candidates and availability

All five verified on the OpenRouter catalog (, 2026-11-03).  as written is not a catalog id; the catalog's  (same model) was tested. Reference: ScaleDown primary path ( + ) on the same chunks.

Pricing as of 2026-11-03 (OpenRouter):
- deepseek/deepseek-v4.1-flash: $0.045/M in, $0.5/M out
- z-ai/glm-5.3-flash: $0.0313/M in, $0.0846/M out
- qwen/qwen3.8-27b: $0.15/M in, $1.875/M out
- openai/gpt-6-luna: $0.1/M in, $0.5/M out
- anthropic/claude-haiku-5.5: $0.1/M in, $0.5/M out
- judge anthropic/claude-sonnet-5.5: $2/M in, $10/M out

## Method

- DB: clone  of  (97 chunks); flat mentions (2,077) and flat extractions (193) wiped in the clone only.
- Sample: every 4th chunk ordered by source/ordinal, first 25 (same 25 for every run).
- Each candidate ran the production code path unchanged:  (with the  empty-content rescue) on , then , ,  (type/confidence ≥0.5/span-repair filter), . , , 8 threads.
- Reference set: pooled judging. Per chunk, the judge saw the passage plus the union of every run's accepted mentions, marked each valid/invalid with its best type, added missed entities, and gave the correct passage kind (25 judge calls, 0 errors, ≈$0.525).
- Precision = accepted mentions the judge marked valid / accepted. Recall = judged-valid ∪ missed entities found / all. Type acc = correct type among valid hits. Kind acc = top_label matches judge's kind. Chatter false-skip = chunk skipped (chatter ≥0.8) that the judge called non-chatter.
- Cost: sample $ = tokens_in × in price + tokens_out × out price. Corpus $ = sample $ / 25 × 97. 100x $ = sample $ / 25 × 10,000.

## Results (25 chunks)

| Model | Precision | Recall | F1 | Type acc | Kind acc | Chatter false-skips | Failures (JSON/empty) | Median latency s | Tokens in / out | $ sample | $ 97 chunks | $ 10k chunks |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 0.896 | 0.465 | 0.612 | 0.839 | 0.68 | 0 | 0 | 30.25 | 37,535 / 191,601 | 0.0996 | 0.3863 | 39.82 |
| deepseek/deepseek-v4.1-flash | 0.703 | 0.809 | 0.752 | 0.872 | 0.68 | 0 | 0 | 133.94 | 26,010 / 712,401 | 0.3574 | 1.3866 | 142.95 |
| openai/gpt-6-luna | 0.79 | 0.51 | 0.62 | 0.897 | 0.64 | 0 | 0 | 62.49 | 24,651 / 168,400 | 0.0867 | 0.3363 | 34.67 |
| qwen/qwen3.8-27b | 0.659 | 0.815 | 0.729 | 0.826 | 0.6 | 0 | 0 | 248.74 | 27,403 / 853,458 | 1.6043 | 6.2249 | 641.74 |
| scaledown (reference) | 0.785 | 0.546 | 0.644 | 0.813 | 0.6 | 0 | 0 | 4.37 | 0 / 0 | None | None | None |
| z-ai/glm-5.3-flash | 0.855 | 0.666 | 0.748 | 0.849 | 0.68 | 1 | 0 | 96.37 | 25,327 / 340,618 | 0.0296 | 0.1149 | 11.84 |

No candidate produced invalid JSON or empty content (rescue not needed to pass). The ≥95% gold-recall benchmark in the job brief is measured against fixture gold, not this pooled reference; no model reaches it here — pooled recall is a stricter yardstick.

## Recommendation

**Winner: z-ai/glm-5.3-flash.** F1 0.748, essentially tied with the best (0.752), beats the ScaleDown reference (0.644) and both shallow models, at ≈$0.11 for the corpus and ≈$12 per 10k chunks — 12x cheaper than DeepSeek and 3x cheaper than Haiku/Luna. Caveat: 1 chatter false-skip in 25 (a meeting excerpt with system names scored chatter 0.85); watch this in the step-11 run, it silently drops knowledge.

**Runner-up: deepseek/deepseek-v4.1-flash.** Highest F1 and recall with zero false skips, but heavy hidden reasoning (≈28k output tokens/chunk) makes it ≈$143 per 10k chunks and ~2 min per chunk.

Not recommended: qwen3.8-27b (high recall, lowest precision, $642/10k, slowest); gpt-6-luna and claude-haiku-5.5 (precise but recall ≈0.5 — the shallow-extraction pitfall).

## Reproducibility

Run outputs (raw responses, per-chunk mentions, judge verdicts) kept on the test services host under the session scratchpad; runner/judge/score scripts are the three small scripts described above. Budget: key limit_remaining was ≈$22.46 before the last candidate; this stage spent ≈$2.7 total (candidates ≈$2.18 + judge ≈$0.525).
