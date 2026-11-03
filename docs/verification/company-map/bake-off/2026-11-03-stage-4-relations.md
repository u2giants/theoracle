# Stage 4 — relationship extraction bake-off (2026-11-03)

Run 11:41 AM – 12:24 PM EST on 2026-11-03 on the test services host. Owner request (Albert, 2026-11-03): "i want to evaluate new models for all stages."

## Winner

**Winner: `meta/muse-spark-1.3-contributor`** — highest recall (0.60 of the union of judge-approved links), precision 0.80, zero failed or retried chunks, widest type spread (18 HANDS_OFF_TO, 3 EXCEPT_WHEN), about $7 at 100x scale.
**Runner-up: `z-ai/glm-5.3-flash`** — zero failures, fastest (14 s median per chunk) and cheapest ($6 at 100x), most links kept, recall 0.54. Its precision is lower (0.65).

Disqualified for now: `anthropic/claude-haiku-5.5` (truncated on 56% of chunks, and the brief allows under 2%), `deepseek/deepseek-v4.1-flash-1017` (40% of chunks came back empty even after the rescue retry), `inclusionai/ling-3.1-flash` (88% of chunks failed from empty content and provider 429s).

## Candidates and availability

All six ids from the brief were listed on OpenRouter `/api/v1/models` on 2026-11-03, and all accept `response_format`. The judge was `anthropic/claude-sonnet-5.5`, which was available. Sonnet 4.5 was not used.

## Method

- DB: `cmap_s4_relations` = `createdb -T cmap_bake_5`. Sample = 25 non-chatter chunks, `ORDER BY md5(id::text) LIMIT 25`. The 212 existing GLM relations for these chunks were deleted in the clone only. `cmap_bake_*` was not touched.
- Each chunk ran through the production code path: `known_mentions` → `build_prompt` (`prompts/relations.md`, previous-chunk context) → `post_chat_with_rescue` (temperature 0, JSON mode, max_tokens 2000, 180 s timeout, 3 attempts) → `parse_relations_json` (salvage) → `validate_response`. It used 8 threads, and models ran one after another.
- Empty content after the rescue counts as a failure. "Truncated" means `finish_reason=length` or a salvaged parse.
- Precision: a seeded random sample of 40 kept relations per model (all 10 for Ling). The judge saw the chunk text and the relation list, grouped by chunk, and gave correct or incorrect for each relation.
- Recall: the union of judge-approved links across all models, keyed by chunk and unordered entity pair (126 pairs). A model gets credit when it emitted the same pair in that chunk with any type. Union recall measures relative recall only, not recall against a human gold set.
- Quality score = F1(precision, recall).
- Cost: OpenRouter's reported `usage.cost`. Projection formula: corpus = sample$ / 25 × 97; 100x = sample$ / 25 × 10,000. Prices per M tokens in/out as of 2026-11-03: DeepSeek 0.15/0.60, GLM 0.0313/0.0846, Ling 0.075/0.225, Luna 0.10/0.50, Muse 0.10/0.20, Haiku 0.10/0.50. Judge cost $0.180. Total bake-off spend was about $0.29.

## Results

| Model | Kept | Precision (n) | Recall | F1 | Failed chunks | Truncated | Latency median s / wall s | Tokens in / out | $ sample | $ corpus (97) | $ 100x (10k) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 139 | 0.70 (40) | 0.49 | 0.58 | 0 | 14 | 8.2 / 29.9 | 44,067 / 44,697 | 0.0265 | 0.103 | 10.60 |
| deepseek/deepseek-v4.1-flash-1017 | 70 | 0.85 (40) | 0.33 | 0.47 | 10 | 5 | 51.1 / 309.9 | 15,999 / 44,669 | 0.0261 | 0.101 | 10.44 |
| inclusionai/ling-3.1-flash | 10 | 0.70 (10) | 0.06 | 0.10 | 22 | 1 | 713.5 / 1723.2 | 3,204 / 11,610 | 0.0027 | 0.010 | 1.07 |
| meta/muse-spark-1.3-contributor | 210 | 0.80 (40) | 0.60 | 0.69 | 0 | 4 | 37.9 / 150.8 | 29,112 / 74,188 | 0.0176 | 0.068 | 7.03 |
| openai/gpt-6-luna | 188 | 0.65 (40) | 0.45 | 0.53 | 1 | 6 | 20.7 / 94.3 | 32,764 / 43,519 | 0.0252 | 0.098 | 10.07 |
| z-ai/glm-5.3-flash | 218 | 0.65 (40) | 0.54 | 0.59 | 0 | 6 | 14.3 / 67.6 | 29,267 / 29,837 | 0.0150 | 0.058 | 6.01 |

Historical reference only (full 97-chunk corpus, earlier rounds): GLM 946 relations, gemini-3.1-flash-lite 360, old sonnet-4.5 862.

## Notes per model

- `meta/muse-spark-1.3-contributor`: Zero failures; best recall and second-best precision; richest type spread incl. HANDS_OFF_TO and EXCEPT_WHEN; slower (median 38 s/chunk).
- `z-ai/glm-5.3-flash`: Zero failures, fastest and cheapest; lower precision (0.65), most over-generalised PERFORMS/APPLIES_TO.
- `anthropic/claude-haiku-5.5`: Truncated at 2000 tokens on 14/25 chunks (56%, brief requires <2%); tail relations lost.
- `openai/gpt-6-luna`: 1 failed chunk; precision 0.65; most new mentions (22).
- `deepseek/deepseek-v4.1-flash-1017`: 10/25 chunks empty content even after the rescue retry (stage failure); slow (median 51 s/chunk).
- `inclusionai/ling-3.1-flash`: 22/25 chunks failed: empty content (47 attempts) and provider 429s (21); 29 min wall time. Unusable today.

## Reproduce

The harness and grading scripts were session scratch on the test services host and are not committed. To reproduce, rerun the method above against a fresh `cmap_bake_5` clone. Per-model raw outputs are not kept in the repo. Precision is based on 40 relations per model, so each value has about ±0.15 sampling noise. Muse's lead in recall is clear. The gap in precision between the 0.65 and 0.80 groups is suggestive, not proven.
