# Stage 5 — Entity resolution bake-off (2026-11-03)

Winner: **openai/gpt-6-luna**. Runner-up: **meta/muse-spark-1.3-contributor**.

## Candidates and availability

All four candidates (Albert's list, verbatim) were listed on OpenRouter `/api/v1/models` on 2026-11-03 and all completed a full run:
`anthropic/claude-haiku-5.5`, `deepseek/deepseek-v4.1-flash`, `openai/gpt-6-luna`, `meta/muse-spark-1.3-contributor`.
Grader: `anthropic/claude-sonnet-5.5` (present on OpenRouter).

## Method

- Per candidate, a clone of the real-corpus test DB `cmap_bake_5` on the test services host (`cmap_s5_haiku55`, `cmap_s5_dsv41flash`, `cmap_s5_gpt6luna`, `cmap_s5_muse13c`). In each clone: `resolve_decision`, `entity_alias` and `entity` were emptied and every `mention.entity_id` set to NULL (`run_resolve` only resolves mentions with `entity_id IS NULL`), so all 2,077 mentions were re-resolved.
- `run_resolve()` (unchanged code) with `BRAIN_FRONTIER_MODEL=<candidate>`, `BRAIN_EMBED_MODEL=openai/text-embedding-3-large`, frontier cap 2000. A wrapper around `post_chat_with_rescue` recorded per-call kind (judge/describe), tokens, OpenRouter `usage.cost`, latency and empty-content failures. The full corpus (97 chunks) was run rather than a sample, since the whole stage cost under $0.16 per model.
- Grading (Sonnet 5.5, temperature 0):
  - Judge decisions: every judge merge (up to 30) plus 10 random rejections (seed 5) re-judged by the grader; merge precision = grader-agrees / merges graded ("unclear" excluded). The corpus produced only 14–20 judge merges per model, so ~21–23 decisions were gradable per model, not 40.
  - Missed duplicates: 23 hand-built true alias pairs from the corpus (e.g. Liz / Liz Parkin, Jen / Jen Chaffier, DFlow / DesignFlow, Click Up / ClickUp, NBC Universal / NBCUniversal) and 18 hand-built different-thing pairs (Walmart / HomeGoods, Marvel / DC Comics, Lic Manager / Lic Coordinator…), checked for shared entity.
  - Descriptions: 8 random described entities scored 0–1 for faithfulness to their quotes.
- `duplicate_of`: not part of stage 5 — that field belongs to the recommendations stage (`recommend.md`); resolve has no such output. Nothing to measure here.

## Results

| Model | Entities | Judge merges | Judged merge precision | Gold true pairs merged | Gold different pairs wrongly merged | Description faithfulness | Failures | p50 / p95 latency (s) | Wall (s) | Tokens in / out | $ actual (= corpus) | $ at 100x |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| openai/gpt-6-luna | 968 | 20 | 0.87 (13/15) | 3/23 | 6/18 | **0.88** | 0 | 2.9 / 7.0 | 1209 | 191,801 / 51,262 | **$0.046** | $4.60 |
| meta/muse-spark-1.3-contributor | 971 | 16 | **0.92 (12/13)** | 4/23 | 6/18 | 0.77 | 0 | 7.9 / 19.0 | 3375 | 192,601 / 410,819 | $0.100 | $10.00 |
| deepseek/deepseek-v4.1-flash | 972 | 14 | 0.85 (11/13) | 4/23 | 6/18 | **0.89** | 3 empty | 2.0 / 24.0 | 1787 | 208,815 / 224,168 | $0.151 | $15.10 |
| anthropic/claude-haiku-5.5 | 973 | 14 | 0.82 (9/11) | 3/23 | 6/18 | 0.62 | 0 | 1.8 / 3.1 | 723 | 318,055 / 96,896 | $0.080 | $8.00 |

Reference: prior GLM run on the same corpus — 969 entities, 340 frontier calls, ~299k tokens. Every candidate made 339–341 frontier calls (~161 judge + ~178 describe). Rejections were 100% correct for all four.

Cost formula: $ actual is the sum of OpenRouter `usage.cost` over all calls (prices as of 2026-11-03 per 1M tokens in/out: haiku-5.5 $0.10/$0.50, deepseek-v4.1-flash $0.045/$0.50, gpt-6-luna $0.10/$0.50, muse-spark-1.3-contributor $0.10/$0.20). The run covered the whole 97-chunk corpus, so corpus $ = actual $. 100x ≈ actual × 100 (judge and describe calls scale roughly linearly with mentions and entities). Grader cost ~ $0.08 per candidate, not included.

## Key findings

1. **The gold-pair metrics are identical across all four models** — 19–20 of 23 known duplicates are missed and the same 6 of 18 different-thing pairs are wrongly fused, for every model. These outcomes are decided by the deterministic rules (alias table and embedding cosine ≥ 0.92) and by whether the pair ever reaches the judge band, not by the stage-5 model. Example: Walmart/HomeGoods, Disney/NBC Universal, Lic Manager/Lic Coordinator fuse via the embedding rule before any model sees them; DFlow/DesignFlow and Click Up/ClickUp fall below 0.80 cosine and never reach the judge. This is the biggest quality problem in the stage and it is not a model-choice problem (follow-up for the coordinator: rule 4 threshold / name-normalisation).
2. Judged false merges are few for everyone (1–2 per model) and of the same kind: a vague phrase (e.g. "submit", a problem sentence) fused into a neighbouring Step or Issue. Muse made 1, the others 2. On 11–15 graded merges per model the precision differences are within one decision and not statistically meaningful.
3. Descriptions separate the models: gpt-6-luna and DeepSeek stay close to the quotes; Haiku 5.5 invented step names/content in several entries.
4. DeepSeek returned empty content 3 times (recovered on retry) and spends heavily on hidden reasoning tokens; Muse is very verbose (411k output tokens) and 3–4x slower.

## Recommendation

- **Winner: openai/gpt-6-luna** — tied-best precision band, near-best descriptions, zero failures, lowest cost ($0.05 corpus, ~$4.60 at 100x), good latency.
- **Runner-up: meta/muse-spark-1.3-contributor** — best judged precision (one false merge) but slower, ~2x cost, weaker descriptions.
- Not recommended: deepseek-v4.1-flash (empty-content failures, highest cost), claude-haiku-5.5 (weakest descriptions).

## Reproducibility

- Run dates: 2026-11-03, roughly 12:55 PM–1:50 PM EST (resolve), grading 1:55–3:15 PM EST.
- Cloned DBs kept on the test services host: `cmap_s5_<slug>` (slugs above); source `cmap_bake_5` untouched.
- Harness: a wrapper script calling `brain.resolve.resolve.run_resolve()` with the env above, and a scoring script (gold pair lists, grader prompts, seed 5). Both are session-local scratch, summarised here; per-call logs recorded tokens, cost and latency per model.
- A first launch was killed mid-run when its parent shell exited; the clones were reset and all four reruns are the numbers above.
