---
summary: Learnings and reproduction notes from the stage 2 embeddings bake-off of 2026-11-03.
kind: proof
status: done
read-when: re-running the embeddings comparison
---

# Stage 2 — Embeddings bake-off: full learnings and reproduction notes

Companion to the results report
[`2026-11-03-stage-2-embeddings.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/company-map/bake-off/2026-11-03-stage-2-embeddings.md)
and its JSON twin. Results merged in
[u2giants/theoracle#328](https://github.com/u2giants/theoracle/pull/328).
Run window: 11:39 AM – 11:45 AM EST, 2026-11-03, on the test services host.

## 1. What was decided

- **Winner: `voyageai/voyage-4-lite`. Runner-up: `openai/text-embedding-3-large`
  (incumbent).** Rejected: `openai/text-embedding-3-small` (retrieval clearly
  weaker), `qwen/qwen3-embedding-8b` (similarity compressed upward — floods the
  resolve judge band — and ~8× slower on chunk batches).
- **No dimension migration is needed for any candidate.** All four return
  exactly 1024 floats when sent `dimensions: 1024`, which is what
  [`apps/brain/brain/embed.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/embed.py)
  already sends. Switching is an env change (`BRAIN_EMBED_MODEL`) plus a full
  re-embed of every stored vector (chunks, entity descriptions, question /
  recommendation dedupe vectors). Never mix two models' vectors.
- Nothing in production, Coolify, or the job brief was changed by this session.

## 2. The most important finding: the resolve bands are model-specific

Resolve rule 4 auto-merges at cosine ≥0.92; rule 5 judges 0.80–0.92; below
0.80 is "different". On 25 hand-checked same-entity name pairs:

- The incumbent puts **0 of 25** at ≥0.92 and only 28% at ≥0.80. In practice
  rule 4 almost never fires on short name strings with the current model, and
  most true aliases (Jen ↔ Jennifer Chaffier 0.46, Liz ↔ Elizabeth Parkin 0.35,
  PPS ↔ Pre-Production Sample 0.31) fall in the "different" zone.
- The incumbent also places one hard negative in the judged band:
  **Lic Manager ↔ Lic Coordinator = 0.873**.
- Voyage-4-lite: 20% of true pairs ≥0.92, 40% ≥0.80, and **every** different
  pair under 0.80.
- Qwen: 68% of true pairs ≥0.80, but also 36% of different pairs ≥0.80 (Jen ↔
  Jessica 0.88, Walmart ↔ Dollar General 0.87, Laura ↔ Angie 0.84).

Consequence for whoever switches the model: re-fit the 0.80 / 0.92 thresholds
on a labelled pair set for the new model before trusting rules 4–5. Name-only
embeddings cannot resolve nicknames, initials or code↔name (One Piece ↔ TOEI,
Strawberry Shortcake ↔ WildBrain CPLP, BA number ↔ Licensor Reference Number)
for any model — those need the LLM judge or an alias table.

## 3. Results summary

| Model | R@5 | R@10 | MRR | Alias AUC | same ≥0.80 | same ≥0.92 | diff <0.80 | $/1M tok | $ per 10k chunks |
|---|---|---|---|---|---|---|---|---|---|
| text-embedding-3-large | 0.943 | 0.969 | 0.899 | 0.706 | 28% | 0% | 96% | 0.13 | $0.39 |
| voyage-4-lite | 0.953 | 0.969 | 0.850 | 0.749 | 40% | 20% | 100% | 0.02 | $0.06 |
| text-embedding-3-small | 0.833 | 0.891 | 0.778 | 0.730 | 32% | 0% | 100% | 0.02 | $0.06 |
| qwen3-embedding-8b | 0.938 | 0.953 | 0.760 | 0.742 | 68% | 20% | 64% | 0.01 | $0.03 |

Latency for the 97-chunk set (two batches of 64+33): large 2.3 s, voyage 1.7 s,
small 2.4 s, qwen 18.6 s. Tokens for the chunk set: ≈30.0k (OpenAI tokenizer),
≈31.2k (Voyage, Qwen). Whole bake-off cost under $0.01.

## 4. Method, exactly

1. Cloned the real-corpus DB inside the pg container:
   `createdb -U oracle -T cmap_bake_5 cmap_s2_embed`. Read only; dropped after.
2. Exported chunks ordered by source title then ordinal (97 rows; index 0–96 in
   that order is what the gold indices below refer to).
3. Embedded every chunk, every question and every name string with each model
   using the production request shape (`/embeddings`, batches of 64,
   `dimensions: 1024`, 3 attempts). Vectors L2-normalised; cosine ranking in
   memory.
4. Retrieval metrics per question: recall@k = fraction of gold chunks in top k;
   MRR = 1 / rank of the best gold chunk. Averaged over 32 questions.
5. Alias metrics: cosine of each pair; AUC = probability a same-entity pair
   scores above a different-entity pair; band placement at 0.80 / 0.92.
6. Composite quality score in the JSON = mean(R@5, MRR, alias AUC,
   diff-pair <0.80 rate). Scores: voyage 0.888, large 0.877, small 0.835,
   qwen 0.770.

### 4.1 The 32 retrieval questions and gold chunk indices

Sources: 0–1 company flow chart (image); 2–29 business-process doc; 30–40
Licensed Team Responsibilities; 41–47 Mockup SOP; 48–55 Packaging SOP; 56–63
Licensing Sheet Automation; 64–71 Artwork SOP; 72–96 meeting transcript.

| # | Question | Gold |
|---|---|---|
| 1 | Which retail chains buy our products? | 3 |
| 2 | Who is the technical lead designer that talks to the factories? | 5 |
| 3 | Who approves art, tech packs and samples and runs the trend collections? | 6 |
| 4 | Where do new product ideas come from? | 7 |
| 5 | How many days does each licensor take to review a submission? | 13 |
| 6 | Estimated design hours by product type such as storage and desk accessories | 15, 16 |
| 7 | What happens when two buyers pick the same design? | 17 |
| 8 | What is the number one pain point about designs shown to buyers? | 18 |
| 9 | Why do Spruce projects stall and how often are stale ones removed? | 25 |
| 10 | What frustrates Jen most about getting people to do their part? | 26 |
| 11 | Glossary definition of a licensor style guide | 29 |
| 12 | Where must the BA licensor reference number be saved? | 31 |
| 13 | What to do when a licensor approves a concept with only minor comments | 32 |
| 14 | Steps when factory sample photos arrive by email | 33 |
| 15 | Requesting a contractual sample exemption from licensors | 35 |
| 16 | Where to store the licensor approval letter and expiration dates | 36 |
| 17 | Weekly Walmart sales recap sent to the Disney licensor | 39 |
| 18 | Outside partners who need licensed assets and submit techpacks through us | 40 |
| 19 | Mockup file naming convention | 42 |
| 20 | What color mode and resolution must mockups use? | 41, 43 |
| 21 | Packaging folder structure and required export files | 49, 54 |
| 22 | Which Pantone swatch library is approved? | 51, 67, 68 |
| 23 | Example dieline for a doormat package | 53 |
| 24 | How does the automation generate a licensing sheet? | 56, 58 |
| 25 | What happens after the technical designer types in a SKU? | 59 |
| 26 | Are linked images allowed in artwork files? | 69 |
| 27 | What must designers remove from artwork before saving? | 70 |
| 28 | Who handles the Dollar General account? | 76 |
| 29 | Who sends tech packs to the factory now that Laura was replaced? | 83 |
| 30 | Swimlane flowchart of the licensed product flow | 0, 1 |
| 31 | Licensing sheet build and pre-production sample submission steps | 10, 11 |
| 32 | What data does Master Data hold, like pricing and shipping origin? | 92, 93 |

### 4.2 Alias pairs and cosines (large / voyage-4-lite / 3-small / qwen)

Same entity:

| A | B | large | voyage | small | qwen |
|---|---|---|---|---|---|
| Jen | Jennifer Chaffier | 0.462 | 0.567 | 0.269 | 0.815 |
| Liz | Elizabeth Parkin | 0.350 | 0.468 | 0.322 | 0.876 |
| Uma | Umamaheswararao Meka | 0.377 | 0.473 | 0.291 | 0.691 |
| Jess | Jessica | 0.804 | 0.955 | 0.837 | 0.942 |
| DesignFlow | Dflow | 0.600 | 0.708 | 0.583 | 0.697 |
| MasterData | Master Data | 0.888 | 0.984 | 0.912 | 0.912 |
| Nickelodeon | Paramount/Nickelodeon | 0.755 | 0.831 | 0.819 | 0.851 |
| Star Wars | Star Wars (LucasFilm) | 0.784 | 0.710 | 0.809 | 0.964 |
| One Piece | TOEI | 0.358 | 0.378 | 0.336 | 0.683 |
| Lic Manager | Licensing Manager | 0.617 | 0.823 | 0.778 | 0.899 |
| Lic Coordinator | Licensing Coordinator | 0.560 | 0.848 | 0.738 | 0.867 |
| PPS | Pre-Production Sample | 0.311 | 0.394 | 0.354 | 0.595 |
| BA number | Licensor Reference Number | 0.269 | 0.501 | 0.407 | 0.719 |
| Wal-Mart | Walmart | 0.896 | 0.953 | 0.906 | 0.992 |
| Techpack | Tech Pack | 0.915 | 0.935 | 0.873 | 0.959 |
| ColdLion | ColdLion System | 0.851 | 0.832 | 0.909 | 0.850 |
| Strawberry Shortcake | WildBrain CPLP | 0.280 | 0.326 | 0.161 | 0.629 |
| Licensed Team | Licensing Team | 0.722 | 0.839 | 0.576 | 0.834 |
| Creative Directors | Creative Direction | 0.772 | 0.736 | 0.794 | 0.853 |
| Sales Team | Sales | 0.562 | 0.688 | 0.665 | 0.843 |
| Tech Pack Automation | Techpack Automation system | 0.851 | 0.937 | 0.894 | 0.929 |
| FAMA Server | SharedLic FAMA server | 0.801 | 0.783 | 0.717 | 0.877 |
| Albert | Albert Hazan | 0.486 | 0.687 | 0.418 | 0.771 |
| Adam | Adam (Sales) | 0.568 | 0.609 | 0.539 | 0.819 |
| TJ Maxx | TJX | 0.744 | 0.675 | 0.673 | 0.793 |

Different entity (hard negatives):

| A | B | large | voyage | small | qwen |
|---|---|---|---|---|---|
| Jen | Jessica | 0.533 | 0.547 | 0.414 | 0.884 |
| Liz | Lucy | 0.434 | 0.456 | 0.485 | 0.827 |
| Marvel | DC Comics | 0.515 | 0.664 | 0.492 | 0.774 |
| Sales | Production | 0.481 | 0.781 | 0.466 | 0.572 |
| Laura | Angie | 0.417 | 0.435 | 0.343 | 0.840 |
| Mockup Production Standards | Packaging Production Standards | 0.681 | 0.668 | 0.598 | 0.750 |
| Artwork Production Standards | Packaging Production Standards | 0.650 | 0.671 | 0.646 | 0.721 |
| DesignFlow | MasterData | 0.350 | 0.477 | 0.396 | 0.535 |
| Lic Manager | Lic Coordinator | 0.873 | 0.559 | 0.660 | 0.850 |
| Burlington | Ross | 0.254 | 0.556 | 0.196 | 0.738 |
| HomeGoods | Hobby Lobby | 0.548 | 0.538 | 0.459 | 0.542 |
| Walmart | Dollar General | 0.549 | 0.679 | 0.455 | 0.868 |
| Technical Designers | Creative Designers | 0.752 | 0.762 | 0.779 | 0.810 |
| Licensor | Licensing Team | 0.582 | 0.792 | 0.627 | 0.747 |
| Disney | Warner Brothers | 0.477 | 0.512 | 0.391 | 0.826 |
| Care Bears | Sesame Street | 0.422 | 0.443 | 0.453 | 0.798 |
| SEGA | WWE | 0.327 | 0.233 | 0.294 | 0.629 |
| PPS | Contractual Sample | 0.283 | 0.262 | 0.200 | 0.550 |
| Emma | Yuchen | 0.310 | 0.502 | 0.269 | 0.628 |
| Peanuts | Strawberry Shortcake | 0.395 | 0.409 | 0.233 | 0.782 |
| Sourcing | Production | 0.443 | 0.594 | 0.363 | 0.654 |
| Concept Approval | Pre-Pro Approval | 0.664 | 0.762 | 0.687 | 0.771 |
| PNG | PSD | 0.529 | 0.498 | 0.422 | 0.800 |
| Carlos | Gina | 0.337 | 0.387 | 0.318 | 0.802 |
| Umamaheswararao Meka | Jennifer Chaffier | 0.064 | 0.250 | 0.054 | 0.679 |

## 5. Things learned about the environment (for the next bake-off)

- **The stored entity aliases are not usable as gold.** A random sample of
  `cmap.entity_alias` in `cmap_bake_5` (878 aliases that differ from their
  canonical name) contains many wrong merges from the earlier GLM extraction,
  e.g. Marvel ← "dc comics", Sales ← "production", Product Categories ←
  "royalty increas", Concept Submit to Licensor ← "mass production". Aliases are
  also stored stemmed ("movie releas", "star war"). Hand-curate pairs instead.
  This is also a quality signal for the stage-5/6 (resolve) bake-off.
- `cmap.entity` columns are `entity_type` and `canonical_name` (not
  `kind`/`name`); aliases live in `cmap.entity_alias.normalized_name`.
- The system `python3` on the test services host has no `httpx`; run ad-hoc
  scripts with `uv run --no-project --with httpx python -I script.py`.
- Calling the 1Password `op_run` tool with a long-running direct `argv`
  dropped the MCP connection ("Connection closed") before any output. Running
  it via `command` with output redirected to a log file worked (≈44 s run).
- OpenRouter exposes embedding models at `GET /api/v1/embeddings/models`
  (they are not all in `/api/v1/models`); pricing is in `pricing.prompt`
  ($/token). Voyage reports usage as `total_tokens`; handle `prompt_tokens`
  as a fallback.
- `bin/ai-doc-safety` (public-boundary check named in the common rules) does
  not exist in this repository, so it could not be run; the reports were
  checked by hand for secrets, LAN addresses and project refs.
- Key spend: limit_remaining was ≈$24.6 before and $24.57 after; embeddings
  are effectively free at this corpus size, so budget is not a selection
  factor — band accuracy and retrieval are.

## 6. Open items for the coordinator (not done here)

- If voyage-4-lite is adopted: set `BRAIN_EMBED_MODEL` in the brain env, run a
  full re-embed, and re-fit the rule-4/5 cosine thresholds on a labelled pair
  set (the table in §4.2 is a starting set) before relying on auto-merge.
- Update the job brief's stage-2 row (the coordinator owns that file).
- Consider a larger labelled alias set (≥100 pairs) before final threshold
  choice; 25+25 pairs gives only a coarse AUC.
