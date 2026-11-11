---
summary: "Results of the stage 3 flat-extraction fallback bake-off of 2026-11-03: candidates, pricing and scores."
kind: proof
status: done
read-when: checking the flat-extraction fallback model choice
---

# Stage 3 — Flat extraction (frontier fallback) bake-off, 2026-11-03

Run 11:40 AM – 12:10 PM EST on the test services host. Owner request (2026-11-03): evaluate new models for all stages; claude-sonnet-4.5 retired.

## Candidates and availability

All five verified on the OpenRouter catalog (`/api/v1/models`, 2026-11-03). `qwen/qwen-3.8-27b` as written is not a catalog id; the catalog's `qwen/qwen3.8-27b` (same model) was tested. Reference: ScaleDown primary path (`/classify` + `/extract`) on the same chunks.

Pricing as of 2026-11-03 (OpenRouter):
- deepseek/deepseek-v4.1-flash: $0.045/M in, $0.5/M out
- z-ai/glm-5.3-flash: $0.0313/M in, $0.0846/M out
- qwen/qwen3.8-27b: $0.15/M in, $1.875/M out
- openai/gpt-6-luna: $0.1/M in, $0.5/M out
- anthropic/claude-haiku-5.5: $0.1/M in, $0.5/M out
- judge anthropic/claude-sonnet-5.5: $2/M in, $10/M out

## Method

- DB: clone `cmap_s3_flat` of `cmap_bake_5` (97 chunks); flat mentions (2,077) and flat extractions (193) wiped in the clone only.
- Sample: every 4th chunk ordered by source/ordinal, first 25 (same 25 for every run).
- Each candidate ran the production code path unchanged: `brain.extract.flat._post_chat` (with the `brain/llm.py` empty-content rescue) on `prompts/flat_extract.md`, then `parse_model_json`, `_classify_half`, `mentions_from_entities` (type / confidence ≥0.5 / span-repair filter), `is_chatter`. `BRAIN_SCALEDOWN_ENABLED=false`, `BRAIN_FRONTIER_MODEL=<candidate>`, 8 threads.
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

## Follow-up: richer ScaleDown instructions (12:25 PM EST)

Question from the owner: can better instructions lift ScaleDown? Variant: every passage-kind and entity-type description rewritten with generic consumer-products / licensing examples (no names taken from the sample), and the chatter label tightened to "NOT chatter if it names any system, document, brand, customer, team, rule or work step". Same 25 chunks, same code path otherwise. New mentions not seen by the original judge pass were judged by the same judge and added to the reference; all rows re-scored on the enlarged reference.

| Path | Precision | Recall | F1 | Type acc | Passage-kind acc | Chatter false-skips |
|---|---|---|---|---|---|---|
| ScaleDown, production instructions | 0.785 | 0.533 | 0.635 | 0.813 | 0.60 | 0 |
| ScaleDown, richer instructions | 0.745 | 0.465 | 0.573 | 0.852 | **0.76** | 0 |
| z-ai/glm-5.3-flash (re-scored) | 0.855 | 0.650 | 0.739 | 0.849 | 0.68 | 1 |

Finding: richer entity descriptions made ScaleDown extraction worse (longer descriptions appear to dilute its matching), but the richer passage-kind descriptions made its labelling the best of every path tested (0.76 vs 0.60), with no false chatter skips. Extraction does not depend on the label here (no chunk was chatter-skipped in either run), so the hybrid — richer classify labels + production entity descriptions — would score 0.635 F1 / 0.76 kind accuracy. Recommendation: adopt the richer classify labels only; keep the entity descriptions as they are. Not yet applied to the code.

## Follow-up 2: entity-description variants to close the gap with GLM (1:20 PM EST)

Richer passage-kind rubrics are now the production ScaleDown classify labels (this PR). Entity descriptions were left as they are; variants were tested to see whether ScaleDown extraction can match z-ai/glm-5.3-flash. Tuning set = the original 25 chunks; confirmation on a fresh held-out set of 24 different chunks (every 4th chunk from offset 2), judged the same way (pooled, anthropic/claude-sonnet-5.5). New mentions were judged before scoring, so scores below supersede earlier rows for the tuning set.

Variants (ScaleDown `/extract` calls per chunk in brackets): base = production descriptions [1]; short = 3–6 word descriptions [1]; split3 = the 16 types in three groups (actors / things / process-language) [3]; single = one type per call [16]. Ensembles merge passes by surface, type by vote (base weighted).

| Path | Calls/chunk | F1 tuning | F1 held-out | Precision held-out | Recall held-out | Type acc held-out |
|---|---|---|---|---|---|---|
| ScaleDown base | 1 | 0.608 | 0.647 | 0.718 | 0.589 | 0.862 |
| short | 1 | 0.614 | 0.659 | 0.692 | 0.628 | 0.750 |
| split3 | 3 | 0.586 | 0.653 | 0.710 | 0.605 | 0.781 |
| single | 16 | 0.637 | 0.650 | 0.716 | 0.596 | 0.654 |
| base + short | 2 | 0.681 | 0.687 | 0.645 | 0.736 | 0.779 |
| base + short + split3 | 5 | 0.705 | 0.698 | 0.619 | 0.799 | 0.778 |
| base + (≥2 of short/split3/single) | 21 | 0.695 | 0.711 | 0.689 | 0.734 | — |
| **z-ai/glm-5.3-flash** | 1 (frontier) | **0.708** | **0.754** | 0.750 | 0.758 | 0.881 |

Held-out passage-kind accuracy with the new labels: ScaleDown 0.79, GLM 0.92; no chatter false-skips by either on the held-out set.

Findings: no single description change closes the gap; description wording moves ScaleDown F1 by only ±0.03. Running several ScaleDown passes and merging them raises recall past GLM's but lowers precision, ending ~0.05 F1 below GLM on unseen chunks (0.698 vs 0.754) at 5x the ScaleDown calls. Best value option if ScaleDown stays primary: base + short (2 calls, +0.04 F1). Not applied to the code — it doubles ScaleDown spend and adds more incorrect items; that trade-off is the owner's call.
