# Stage 6 — Community reports bake-off (2026-11-03)

Owner request (Albert, 2026-11-03): "Claude Sonnet 4.5 is an old model, i don't want to use that anymore. i want to evaluate new models for all stages."

## Candidates and availability

All six candidates exist on OpenRouter (checked `GET /api/v1/models`, 2026-11-03 ~11:45 AM EST). Judge: `anthropic/claude-sonnet-5.5` (available). Prices below are OpenRouter list prices per 1M tokens as of 2026-11-03.

| Model | Available | $/1M in | $/1M out |
|---|---|---|---|
| `openai/gpt-6-luna` | yes | 0.1 | 0.5 |
| `meta/muse-spark-1.3-contributor` | yes | 0.1 | 0.2 |
| `z-ai/glm-5.3-flash` | yes | 0.0313 | 0.0846 |
| `anthropic/claude-haiku-5.5` | yes | 0.1 | 0.5 |
| `deepseek/deepseek-v4.1-flash` | yes | 0.045 | 0.5 |
| `google/gemini-3.8-flash` | yes | 0.825 | 4.125 |

## Method

- Clone `cmap_s6_reports` of `cmap_bake_5` on the test services host (8 sources, 969 entities). Leiden levels were computed once with the production code (`_level0_membership`/`_level1_membership`, seed 0): **416 L0 and 399 L1 communities** on this clone (the brief's 867 is used for projections).
- No FalkorDB was needed: `run_communities` reads Postgres only (graph projection is not an input to reports), so no container was started.
- Fixed sample, identical for every model: 9 L0 communities spread across the size ranking (sizes 40, 36, 24, 19, 14, 6, 5, 4, 3 entities), 2 L1 reports (the L1 parents of the sampled L0s: one with 5 children, one with 1) and the single company (L2) report. L1/L2 inputs are each model's OWN L0 reports, as in production. Contexts built with the production `_context_l0` / `_context_reports` / prompt `community_report.md`; JSON mode, temperature 0, max_tokens 4000, the `brain/llm.py` empty-content rescue (doubled budget, low reasoning).
- Each parsable report graded by the judge on DATA vs BRIEFING: faithfulness, unsupported-claim count, coverage of key entities/hand-offs, readability for a business owner, citation correctness (0–10). Quality score = mean of the four 0–10 scores / 10.
- Cost = OpenRouter-reported `usage.cost` for the 12 report calls (judge cost excluded). Projection: `cost_per_call × 867` (current real corpus) and `cost_per_call × 86,700` (100× corpus ≈ 10,000 chunks, assuming communities scale linearly).

## Results

| Model | JSON valid | Quality 0–1 | Faith | Unsupported claims | Coverage | Readability | Citations | Findings (dropped: no valid source) | Latency median / max s | Tokens in / out | $ sample | $ corpus (867) | $ 100× |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `openai/gpt-6-luna` | 11/12 | 0.816 | 8.45 | 14 | 7.91 | 8.0 | 8.27 | 68 (0) | 15.5 / 36.5 | 33,564 / 21,553 | 0.0147 | 1.06 | 107 |
| `meta/muse-spark-1.3-contributor` | 11/12 | 0.759 | 7.82 | 24 | 7.18 | 7.36 | 8.0 | 79 (0) | 22.950000000000003 / 29.6 | 32,957 / 39,573 | 0.0111 | 0.80 | 80 |
| `z-ai/glm-5.3-flash` | 12/12 | 0.765 | 7.83 | 33 | 7.67 | 7.17 | 7.92 | 100 (1) | 12.149999999999999 / 114.5 | 36,409 / 21,686 | 0.0091 | 0.66 | 66 |
| `anthropic/claude-haiku-5.5` | 9/12 | 0.789 | 7.67 | 24 | 8.22 | 7.33 | 8.33 | 79 (0) | 14.45 / 43.4 | 49,242 / 40,986 | 0.0252 | 1.82 | 182 |
| `deepseek/deepseek-v4.1-flash` | 7/12 | 0.757 | 7.86 | 14 | 7.43 | 7.14 | 7.86 | 73 (0) | 33.15 / 90.4 | 34,713 / 64,899 | 0.0596 | 4.30 | 430 |
| `google/gemini-3.8-flash` | 9/12 | 0.745 | 7.33 | 30 | 7.56 | 7.11 | 7.78 | 53 (0) | 24.15 / 32.6 | 34,447 / 34,475 | 0.1536 | 11.10 | 1110 |

Judge cost for the whole bake-off: $0.98. Total spend ≈ $1.25.

**Every JSON failure is a truncation at the 4,000-token output cap** (output token count = 4,000 on each failed call; reasoning tokens count against it). The company report — the longest output, with the Top-10 section — failed for gpt-6-luna, muse-spark, gemini and deepseek. Only glm-5.3-flash produced all 12. A production switch should raise the report `max_tokens` (e.g. 8,000) or set low reasoning on the first attempt; the coordinator owns that change.

## Recommendation

- **Winner: `openai/gpt-6-luna`** — highest quality (0.816), best faithfulness (8.45) and readability (8.0), joint-fewest unsupported claims (14), 11/12 valid, fast (15 s median), ~$1.07 for the current corpus and ~$107 at 100×. Its one failure (company report truncated) is fixed by a larger output cap.
- **Runner-up: `meta/muse-spark-1.3-contributor`** — 11/12 valid, cheap (~$0.80 corpus, ~$80 at 100×), citations 8.0, but lower coverage (7.18) and 24 unsupported claims.
- Notable: `z-ai/glm-5.3-flash` is the only 12/12 and cheapest (~$66 at 100×) but has the most unsupported claims (33) and a 114 s tail. `claude-haiku-5.5` scores well (0.789) but truncated 3 of the 3 largest L0s. `deepseek-v4.1-flash` (7/12, slow) and `gemini-3.8-flash` (10× the price, most unsupported claims after GLM) are not recommended.

## Excerpts (person names and source ids redacted)

**`openai/gpt-6-luna`**

> L0 summary: This area covers how creative inventory is distinguished from buyer-committed products and how design work is organized and timed. [person] tracks design collections, account projects, selections PDFs, and style-numbered products as distinc…

> company/L1 finding: The procedure places [person]’s screen for obvious AI-art mistakes before [person]’s review, while [person] and [person] are both described as reviewing artwork and tech packs. The conversation also assigns product approvals to [person], so…

**`meta/muse-spark-1.3-contributor`**

> L0 summary: This area covers how original art becomes sellable home decor, from trend-based design collections to buyer-committed style-numbered products. [person] tracks this distinction for wall art, floor coverings including coir mats, storage, gard…

> company/L1 finding: Both the business-process document and the licensed-flow diagram show tech packs move through splitting/allocation and formal approval before a sample is requested from the factory, which then produces a pre-production sample.

**`z-ai/glm-5.3-flash`**

> L0 summary: The company designs and sources home decor products (wall art, storage, floor coverings, garden items, desk accessories), manufactured in China and imported to the US for major retail chains. [person] tracks three distinct artifact types: d…

> company/L1 finding: Policy documents assign approval of all art, tech packs, and samples to [person] [person] ([person] [person]), while also stating [person] approves files, tech packs, and samples and 'does all the approvals on the product' — which [person] …

**`anthropic/claude-haiku-5.5`**

> L0 summary: This area covers how the company's home decor design work moves from creative inventory to commercial product. The company designs and sources home decor items (wall art, canvas, storage, floor coverings, garden items and others), manufactu…

> company/L1 finding: Design collections are raw creative inventory and come before style-numbered products. A style-numbered product exists only once a buyer selects designs and either places an order or requests a sample.

**`deepseek/deepseek-v4.1-flash`**

> L0 summary: This area covers how design collections are tracked and converted into style-numbered products, and how that affects production visibility. [person] tracks three distinct things: account-agnostic design collections (trend/art themes such as…

> company/L1 finding: Both the business-process document and the 14 March transcript show that [person] creates initial tech packs and approves files, tech packs, samples, and product, while [person] [person] also approves all art, tech packs, and samples. This …

**`google/gemini-3.8-flash`**

> L0 summary: This area covers the creative categorization, design phase timelines, and transition of raw creative assets into committed production products. The company designs and sources home decor products—such as wall art, floor coverings, storage, …

> company/L1 finding: Before artwork reaches directorial review, [person] [person] [person] screens AI-generated art to filter out poor-quality pieces and obvious AI mistakes.

## Reproducibility

- Run 2026-11-03 ~11:50 AM–12:05 PM EST on the test services host, DB clone `cmap_s6_reports` (left in place, read-only use). Script: one process per model calling the production context builders and prompt, then the judge; outputs kept in the session scratchpad (not committed: they contain employee names).
- Sample L0 community ids (seed-0 Leiden order): 0, 4, 8, 12, 16, 20, 24, 28, 32; L1 groups: {'0': [0, 4, 8, 12, 16], '3': [20]}.
