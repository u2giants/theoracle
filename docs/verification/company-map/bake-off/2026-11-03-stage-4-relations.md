---
summary: "Results of the stage 4 relationship-extraction bake-off of 2026-11-03: winner Muse Spark, runner-up GLM, with recall and precision."
kind: proof
status: done
read-when: checking the relationship-extraction model choice
---

# Stage 4 — relationship extraction bake-off (2026-11-03)

Run 11:41 AM – 12:24 PM EST on 2026-11-03 on the test services host. Owner request (Albert, 2026-11-03): "i want to evaluate new models for all stages."

## Winner

**Winner: `meta/muse-spark-1.3-contributor`** — tied for best quality (recall 0.52, precision 0.78, F1 0.62), with zero failed chunks and the widest type spread, at about $7 per 10k chunks.
**Runner-up: `z-ai/glm-5.3`** (full GLM, added at Albert's request) — equal quality (recall 0.54, precision 0.75, F1 0.63), the most links kept (281), zero failures, and about 3x faster than Muse. Output tokens cost far more, so it runs about $39 per 10k chunks, roughly 5.5x Muse. Pick GLM-5.3 if speed matters more than cost.
`z-ai/glm-5.3-flash` is cheapest and fast, but has the lowest precision (0.58) of the reliable models.

Disqualified for now: `anthropic/claude-haiku-5.5` (truncated on 56% of chunks, and the brief allows under 2%), `deepseek/deepseek-v4.1-flash-1017` (40% of chunks empty even after the rescue retry), `inclusionai/ling-3.1-flash` (88% of chunks failed from empty content and provider 429s).

## Candidates and availability

All six ids (plus `z-ai/glm-5.3`, added 1:01 PM EST) from the brief were listed on OpenRouter `/api/v1/models` on 2026-11-03, and all accept `response_format`. The judge was `anthropic/claude-sonnet-5.5`, which was available. Sonnet 4.5 was not used.

## Method

- DB: `cmap_s4_relations` = `createdb -T cmap_bake_5`. Sample = 25 non-chatter chunks, `ORDER BY md5(id::text) LIMIT 25`. The 212 existing GLM relations for these chunks were deleted in the clone only. `cmap_bake_*` was not touched.
- Each chunk ran through the production code path: `known_mentions` → `build_prompt` (`prompts/relations.md`, previous-chunk context) → `post_chat_with_rescue` (temperature 0, JSON mode, max_tokens 2000, 180 s timeout, 3 attempts) → `parse_relations_json` (salvage) → `validate_response`. It used 8 threads, and models ran one after another.
- Empty content after the rescue counts as a failure. "Truncated" means `finish_reason=length` or a salvaged parse.
- Precision: a seeded random sample of 40 kept relations per model (all 10 for Ling). The judge saw the chunk text and the relation list, grouped by chunk, and gave correct or incorrect for each relation.
- Recall: the union of judge-approved links across all models, keyed by chunk and unordered entity pair (149 pairs, all seven models regraded together). A model gets credit when it emitted the same pair in that chunk with any type. Union recall measures relative recall only, not recall against a human gold set.
- Quality score = F1(precision, recall).
- Cost: OpenRouter's reported `usage.cost`. Projection formula: corpus = sample$ / 25 × 97; 100x = sample$ / 25 × 10,000. Prices per M tokens in/out as of 2026-11-03: DeepSeek 0.15/0.60, GLM 0.0313/0.0846, Ling 0.075/0.225, Luna 0.10/0.50, Muse 0.10/0.20, Haiku 0.10/0.50. Price for GLM-5.3: 0.08/3.60. Judge cost $0.180 first pass + $0.171 regrade. Total bake-off spend was about $0.56.

## Results

| Model | Kept | Precision (n) | Recall | F1 | Failed chunks | Truncated | Latency median s / wall s | Tokens in / out | $ sample | $ corpus (97) | $ 100x (10k) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 139 | 0.80 (40) | 0.47 | 0.59 | 0 | 14 | 8.2 / 29.9 | 44,067 / 44,697 | 0.0265 | 0.103 | 10.60 |
| deepseek/deepseek-v4.1-flash-1017 | 70 | 0.88 (40) | 0.28 | 0.43 | 10 | 5 | 51.1 / 309.9 | 15,999 / 44,669 | 0.0261 | 0.101 | 10.44 |
| inclusionai/ling-3.1-flash | 10 | 0.70 (10) | 0.05 | 0.09 | 22 | 1 | 713.5 / 1723.2 | 3,204 / 11,610 | 0.0027 | 0.010 | 1.07 |
| meta/muse-spark-1.3-contributor | 210 | 0.78 (40) | 0.52 | 0.62 | 0 | 4 | 37.9 / 150.8 | 29,112 / 74,188 | 0.0176 | 0.068 | 7.03 |
| openai/gpt-6-luna | 188 | 0.70 (40) | 0.42 | 0.53 | 1 | 6 | 20.7 / 94.3 | 32,764 / 43,519 | 0.0252 | 0.098 | 10.07 |
| z-ai/glm-5.3-flash | 218 | 0.57 (40) | 0.48 | 0.53 | 0 | 6 | 14.3 / 67.6 | 29,267 / 29,837 | 0.0150 | 0.058 | 6.01 |
| z-ai/glm-5.3 | 281 | 0.75 (40) | 0.54 | 0.63 | 0 | 8 | 11.5 / 64.4 | 29,257 / 35,184 | 0.0966 | 0.375 | 38.65 |

Historical reference only (full 97-chunk corpus, earlier rounds): GLM 946 relations, gemini-3.1-flash-lite 360, old sonnet-4.5 862.

## Notes per model

- `z-ai/glm-5.3`: Added 2026-11-03 1:01 PM EST at Albert's request ("test glm 5.3 (not flash)"). Zero failures, most links kept (281), best recall, fastest after Haiku (11.5 s median); output tokens cost 42x Flash, so about 5.5x Muse's bill.
- `meta/muse-spark-1.3-contributor`: Zero failures; recall and precision tied with GLM-5.3 within sampling noise; widest type spread incl. HANDS_OFF_TO and EXCEPT_WHEN; slower (median 38 s/chunk) but cheapest of the top tier.
- `anthropic/claude-haiku-5.5`: Truncated at 2000 tokens on 14/25 chunks (56%, brief requires <2%); tail relations lost.
- `openai/gpt-6-luna`: 1 failed chunk; precision 0.65; most new mentions (22).
- `z-ai/glm-5.3-flash`: Zero failures, fast and cheapest; lowest precision of the reliable models.
- `deepseek/deepseek-v4.1-flash-1017`: 10/25 chunks empty content even after the rescue retry (stage failure); slow (median 51 s/chunk).
- `inclusionai/ling-3.1-flash`: 22/25 chunks failed: empty content (47 attempts) and provider 429s (21); 29 min wall time. Unusable today.

## Reproduce

The harness and grading scripts were session scratch on the test services host and are not committed. To reproduce, rerun the method above against a fresh `cmap_bake_5` clone. Per-model raw outputs are not kept in the repo. Precision is based on 40 relations per model, so each value has about ±0.15 sampling noise. Muse and GLM-5.3 cannot be separated on quality. Both clearly beat the rest on recall.


## Addendum — ScaleDown Extract trial (2026-11-03, 1:21–1:50 PM EST)

Albert asked (verbatim): "since this is an extraction task, see if scaledown's Extract model can match Muse. try several different prompts/instructions to score as high as possible".

**Result: Extract does not match Muse.** Its best version scored F1 0.45, against Muse's 0.58 and GLM-5.3's 0.62. Extract is very cheap, about $1.30 per 10,000 chunks, but more than half of the links it keeps are wrong. It also never uses the exception and conflict link types, which the brief ranks as the second priority. The winner and runner-up are unchanged.

How it was run: Extract (ScaleDown `extract` model, its own API) is a span finder driven by a JSON schema, not a chat model. So the `prompts/relations.md` prompt cannot be used as-is. Each design asked for arrays of links and was then passed through the production validator unchanged (exact quote, known entity keys, ontology types). Six designs were tried on 4 chunks first:

- v1: one array of links, type as free text, with the full instruction. Kept 5 of 19 raw.
- v2: same with minimal instruction. Kept 1 of 22.
- v3: one array per link type. Kept 18 of 77.
- v4: v3 plus direction and "prefer specific types" guidance. Kept 34 of 107.
- v5: v4 plus a small adapter that repairs near-miss quotes and entity names (a real Extract integration would need this). Kept 50 of 91.
- v6: v5 plus "copy entity names exactly from the list". Kept 49 of 74.

Muse kept 30 links on the same 4 chunks. v5 and v6 then ran on all 25 chunks and were graded in one fresh pass together with all seven models. The judge was `anthropic/claude-sonnet-5.5`, with a 40-link sample per model and 166 union pairs.

| Model (same grading pass) | Kept | Precision | Recall | F1 |
|---|---|---|---|---|
| GLM-5.3 | 281 | 0.80 | 0.51 | 0.62 |
| Muse Spark 1.3 Contributor | 210 | 0.72 | 0.48 | 0.58 |
| ScaleDown Extract v6 (best) | 321 | 0.50 | 0.42 | 0.45 |
| ScaleDown Extract v5 | 483 | 0.15 | 0.48 | 0.23 |

v5 found many links, so its recall equals Muse's, but most of them were noise (precision 0.15). v6's links were mostly PERFORMS/PART_OF/MENTIONS, with zero EXCEPT_WHEN or CONTRADICTS. Extract cost: $0.05 per M input tokens, and output is free. v6 used 64,206 input tokens over 25 chunks, about $0.0032, which projects to about $0.012 for the 97-chunk corpus and $1.28 at 10,000 chunks. Latency was about 34 s wall time for 25 chunks, with zero failures.

Precision moves by about ±0.05 between grading passes, as sampling noise. In this pass GLM-5.3 edged Muse (0.80 vs 0.73 precision). In the earlier pass Muse edged GLM-5.3. The two stay tied on quality, and Muse stays the pick because it costs about 5.5x less.
