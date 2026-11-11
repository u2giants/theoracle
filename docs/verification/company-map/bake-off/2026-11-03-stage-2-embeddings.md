---
summary: "Results of the stage 2 embeddings bake-off of 2026-11-03: candidates, availability, price and scores."
kind: proof
status: done
read-when: checking which embedding model was chosen and why
---

# Stage 2 — Embeddings bake-off (2026-11-03)

Run 11:41–11:42 AM EST on the test services host. Machine-readable twin:
`2026-11-03-stage-2-embeddings.json`.

## Candidates and availability

| Model | On OpenRouter | 1024 dims | Price $/1M tokens (OpenRouter `/models`, 2026-11-03) |
|---|---|---|---|
| openai/text-embedding-3-large (incumbent) | yes | yes (`dimensions` truncation) | 0.13 |
| voyageai/voyage-4-lite | yes | yes | 0.02 |
| openai/text-embedding-3-small | yes | yes | 0.02 |
| qwen/qwen3-embedding-8b | yes | yes | 0.01 |

All four returned exactly 1024-dim vectors when called the way `brain/embed.py`
calls them (`dimensions: 1024`). **No schema migration is needed** for any
candidate; `cmap.chunk.embedding` / `cmap.entity.embedding` stay `vector(1024)`.
A switch still requires a full re-embed (never mix vector spaces) — chunks,
entity descriptions, and the open-question / recommendation dedupe vectors.

## Method

- Corpus: clone `cmap_s2_embed` of `cmap_bake_5` (97 real chunks, 8 sources);
  read only. All vectors were computed in memory; nothing was written back.
- Retrieval: 32 hand-written paraphrase questions, each with gold chunk(s)
  identified by hand (multi-gold where the answer spans chunks). Cosine
  ranking over all 97 chunks; recall@5, recall@10, MRR (first gold hit).
- Alias pairing (resolve rules 4–5): 25 hand-curated same-entity pairs
  (e.g. Jen / Jennifer Chaffier, DesignFlow / Dflow, Lic Manager / Licensing
  Manager, BA number / Licensor Reference Number, One Piece / TOEI) and 25 hard
  different-entity pairs (Jen / Jessica, Marvel / DC Comics, Mockup vs
  Packaging Production Standards, Lic Manager / Lic Coordinator, Laura / Angie…).
  The GLM-extracted `cmap.entity_alias` rows were not used as gold: a sample
  showed many wrong merges (e.g. Marvel→"dc comics", Sales→"production").
  Metrics: AUC (same-entity cosine > different-entity cosine), and placement
  against the production bands (≥0.92 auto-merge, 0.80–0.92 judged, <0.80 apart).
- Same request shape as production: batches of 64, 3 attempts.
- Script and raw per-pair cosines: kept in the session scratch (not committed);
  a copy of the question/pair lists is in the shared bake-off notes folder.

## Results

| Model | R@5 | R@10 | MRR | Alias AUC | same-pair mean cos | diff-pair mean cos | same ≥0.80 | same ≥0.92 | diff <0.80 | Failures | Latency (all calls) | Tokens | $ sample | $ corpus (97 chunks) | $ 100× (~10k chunks) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| text-embedding-3-large | 0.943 | 0.969 | **0.899** | 0.706 | 0.623 | 0.475 | 28% | 0% | 96% | 0 | 4.5 s | 30,564 | $0.0040 | $0.0039 | $0.39 |
| **voyage-4-lite** | **0.953** | 0.969 | 0.850 | **0.749** | 0.706 | 0.537 | 40% | 20% | **100%** | 0 | **3.0 s** | 31,707 | $0.0006 | $0.0006 | $0.06 |
| text-embedding-3-small | 0.833 | 0.891 | 0.778 | 0.730 | 0.623 | 0.428 | 32% | 0% | 100% | 0 | 4.4 s | 30,564 | $0.0006 | $0.0006 | $0.06 |
| qwen3-embedding-8b | 0.938 | 0.953 | 0.760 | 0.742 | 0.826 | 0.735 | 68% | 20% | 64% | 0 | 30.9 s | 31,920 | $0.0003 | $0.0003 | $0.03 |

Cost formula: `$ = tokens × price_per_token`. Corpus = this run's chunk tokens
(≈30–31k for 97 chunks); 100× = corpus × 100. Chunks are only one embed
consumer (mentions, entity re-describes, question dedupe add more calls), but
every consumer scales by the same price ratio: voyage-4-lite and 3-small are
6.5× cheaper than the incumbent, qwen 13×. Total spend for this bake-off:
under $0.01; key limit remaining after the run $24.57.

## Findings

1. **Retrieval:** large, voyage-4-lite and qwen tie on recall (≈0.94–0.95@5);
   large ranks the gold chunk first most often (MRR 0.90 vs 0.85). 3-small is
   clearly behind.
2. **Short-name aliases are weak for every model.** No candidate puts most
   true alias pairs at ≥0.80, and the incumbent puts **none** in the ≥0.92
   auto-merge band. Rule 4 effectively never fires on name strings alone today;
   the 0.80/0.92 bands are not model-neutral and should be recalibrated if the
   model changes (coordinator item, not changed here).
3. **qwen3-embedding-8b compresses everything upward** (different-entity mean
   0.735; 36% of hard negatives ≥0.80), so it would flood the rule-5 judge band
   with wrong candidates. It was also ~8× slower on the chunk batch (18.6 s).
4. voyage-4-lite is the only model with perfect negative placement *and*
   some positives in the auto-merge band.

## Recommendation

- **Winner: voyageai/voyage-4-lite** — best alias separation (AUC 0.749, all
  different-entity pairs under 0.80), equal-or-better recall@5/@10, fastest,
  6.5× cheaper. Cost: MRR 0.05 lower than the incumbent. Switching requires a
  full re-embed (cents at today's corpus, ~$0.06 per 10k chunks) and a band
  re-check; no dimension migration.
- **Runner-up: openai/text-embedding-3-large (incumbent)** — best MRR; keep it
  if first-hit ranking for answering matters more than alias banding.

## Run notes

- Clone DB: `cmap_s2_embed` (from `cmap_bake_5`), read only.
- OpenRouter key limit_remaining before the first model ≈$24.6.
- No failures, no empty vectors, no retries needed.
