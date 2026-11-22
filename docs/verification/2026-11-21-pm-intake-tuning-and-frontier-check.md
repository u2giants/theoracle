---
summary: "Step 2.3 addendum (#607): blind scores across 11 routes (incl. frontier diagnostics), message-prompt tuning, and flat-mention bottleneck."
kind: proof
status: current
read-when: reviewing why frontier models also fail the original prompt, how message-specific prompting and an L8 verify/narrow guard perform on tuning, or the precision-recall trade-off for issue 607
---

# Message intake step 2.3 — frontier blind check, message-prompt tuning, and recall bottleneck

This addendum supplements [2026-11-21-pm-intake-step-2-3-qualification.md](2026-11-21-pm-intake-step-2-3-qualification.md). It keeps the same gated stop on step 2.3 and leaves production, model seats, and the 350-thread holdout untouched.

## 1. Calibrated L8 2-of-3 blind review (`calibrated-blind-review-v2`)

Inside `oracle-sandbox-private` (`quote-tools`, zero raw text exported), combining deterministic single-turn verbatim checking (`Gate 0`: quote must be a byte-verbatim substring inside a single source turn) with a 2-of-3 non-author L8 judge panel (`claude-haiku-5-5` medium, `deepseek-v4.1-flash`, `gpt-6-luna` medium, `z-ai/glm-5.3-flash`) produced:

- **Synthetic adversarial traps (10 cases):** `10/10` (`100%`) across all three primary L8 judges (`haiku-med`, `deepseek`, `luna-med`) covering wrong actor, obsolete status, one-off vs standing practice, request as completed action, role as ownership, signature `MENTIONS`, packer-header quote (`Gate 0`), valid policy rule, valid paraphrase, and valid scoped request.
- **Disjoint Step 2.1 hidden controls (`120` total across seeds `607901` and `607902`):** `38/39` (`97.4%`) rejection accuracy (`20/20 = 100%` on unseen disjoint seed `607902`), `91.3%` inter-judge binary agreement (`90.9%` on `607901`, `91.7%` on `607902`), and conservative binary accuracy `82.1%` / `78.3%` (with stricter false-rejects than false-accepts).
- **Sandbox receipt digests:** `c0800b6066dbcac7929d87630e272fe88c1028683414a3b6e13b57f283b1e0c6` (`calibration-report.json`), `6af31e0d9340d315c1370b06960b4b9deebd171c81d570b0dd2051b7393f9ca5` (`calibration-v2-disjoint-607902.json`).

## 2. Complete 11-route blind scoring on the original prompt (30 frozen scoring threads)

Using the calibrated L8 2-of-3 panel on `548` stratified novel claims plus exact Step 2.1 gold overlaps (`routes12-blind-scores.json`, SHA-256 `5f11300fd3ce050088df383f366df3acf486750b779611a7389da22c0f95393e`), **every route failed the 95% correctness gate under `prompts/relations.md` — including every frontier diagnostic**:

| Route | USD / 1,000 | Gate-0 in-turn quotes | Novel sample keep | Estimated overall correctness |
|---|---:|---:|---:|---:|
| GPT-6 Luna, OpenAI native batch | $0.514 | 93.5% | 27/47 (57.4%) | **59.5%** |
| GPT-6 Luna, direct 16k | $1.031 | 92.8% | 24/44 (54.5%) | 57.2% |
| GPT-6 Luna, OpenRouter pinned batch | $0.574 | 91.6% | 24/46 (52.2%) | 53.1% |
| Gemini 3.8 Flash, batch (diagnostic) | $4.740 | 96.0% | 20/42 (47.6%) | 49.5% |
| GLM 5.3 max, xhigh (diagnostic) | $15.464 | 95.5% | 16/41 (39.0%) | 40.3% |
| Claude Opus 5.5 low (frontier diagnostic) | $28.953 | 94.9% | 15/41 (36.6%) | 39.5% |
| GPT-6.2 Sol low (frontier diagnostic) | $15.593 | 87.8% | 16/42 (38.1%) | 38.1% |
| Claude Haiku 5.5, direct 16k | $1.199 | 97.4% | 14/40 (35.0%) | 36.0% |
| Muse Spark 1.3 Contributor (diagnostic) | $1.536 | 92.8% | 13/40 (32.5%) | 32.9% |
| Claude Haiku 5.5, native batch | $0.633 | 96.8% | 13/41 (31.7%) | 31.2% |
| Gemini 4 Hydrogen, batch (diagnostic) | $26.239 | 84.1% | 10/46 (21.7%) | 22.5% |

This confirms the failure under `prompts/relations.md` is a prompt/rubric mismatch for message text rather than cheap-model weakness: `$0.514/1k` GPT-6 Luna outperformed `$28.95/1k` Opus and `$15.59/1k` Sol.

## 3. Bounded tuning on 20 stratified tuning threads (`stage3-tuning-20261121`)

All tuning ran strictly on 20 stratified threads from the 50-thread tuning split (zero held-out access).

### 3a. Message-specific prompt + L8 verify/narrow guard (existing `flat → relations` pipeline)

Tightening the relations prompt for message threads (single-turn verbatim quote rule, boilerplate exclusion, request/directive vs completed-action distinction, and strict `OWNS`/`DEPENDS_ON`/`policy` scope) produced large precision gains without losing kept claims (`tuning-summary.json` SHA-256 `02bf2dd8a5364dbb25247bc287c33fd2f207d18da2b9bf3d19f4816c30b50ac3`; `f2-and-recall-summary.json` SHA-256 `94d417b9603d51b118e33157e3a387aad308389c416d7c9bfab4ca5915a72225`):

| Tuning arm (20 tuning threads, 21 passages) | Quote valid | In-turn valid | Non-author precision | Kept claims | Est. batch USD / 1k |
|---|---:|---:|---:|---:|---:|
| Control: `GPT-6 Luna` + original `relations.md` | 100.0% | 93.6% | 51.4% | 56 | $0.572 |
| Control: `Claude Haiku 5.5` + original `relations.md` | 100.0% | 96.0% | 30.7% | 31 | $0.566 |
| Tuned: `GPT-6 Luna` + message prompt | 100.0% | 100.0% | **89.1%** | 57 | $0.632 |
| Tuned: `Claude Haiku 5.5` + message prompt | 100.0% | 98.0% | 80.0% | 36 | $0.541 |
| Tuned: `GLM-5.3 Flash` + message prompt (6 truncations) | 100.0% | 93.7% | 59.6% | 31 | $0.476 |
| Tuned: `DeepSeek 4.1 Flash` + message prompt (4 truncations) | 100.0% | 98.5% | 92.4% | 61 | $15.487 |
| **L8 Pair (`msg-luna` → `Haiku 5.5` verify/narrow guard)** | **100.0%** | **100.0%** | **93.4%–95.1%** | **56–58** | **$0.886** |

However, checking semantic recall against source-first operational facts (`46` facts across `19` tuning threads; `stage3-finalists-report.json` SHA-256 `2ed143024133d3ca8bf50013495cefd175a2d17f67693bf1e2ef856eb5dc8b3c`) revealed that the existing `flat → relations` mention bottleneck capped semantic recall at **34.8%–41.3%** (`F1` 37.0%, `F2b` 34.8%, `F3` 41.3%).

### 3b. Removing the flat-mention bottleneck (single-pass full-thread extraction)

Extracting relations directly from full thread turns without restricting endpoints to prior flat-extraction mentions (`unbottlenecked-recall-diag.json` SHA-256 `99ac8017e9715d41e84088f053ca3c958bea18b7083240a13a099ce5837bb76a`; `unbottlenecked-l8-results.json` SHA-256 `40322391fe8c2db59be41b349242072631605a67eaa06703cc231d5b4a230f89`) doubled L8 semantic recall while eliminating the separate flat-extraction call:

| Unbottlenecked full-thread arm (20 tuning threads) | First-attempt OK | In-turn quote % | Semantic recall (source-first) | Non-author precision (DeepSeek / GLM) | Est. batch USD / 1k threads |
|---|---:|---:|---:|---:|---:|
| `GPT-6 Luna` medium, JSON mode (L8) | 20/20 | 98.8% | **85.1%** (40/47) | 72.3% / 90.2% | **$0.513** |
| `Claude Haiku 5.5` medium (L8) | 20/20 | 98.9% | 83.0% (39/47) | 60.4% / 77.4% | $0.555 |
| `GPT-6 Luna` → `Claude Haiku 5.5` verify/narrow guard (L8 pair) | 20/20 | 100.0% | 74.5% (35/47) | **86.7% / 86.8%** | **$0.850** |
| `Claude Opus 5.5` medium (frontier diagnostic, 20 threads) | 20/20 | — | 95.2% (40/42) | — / 68.6% | ~$29.00 |

### 3c. Dynamic few-shot RAG with `GPT-6 Luna` (zero Colab, zero frontier)

Retrieving top-k similar verified good/bad extraction examples strictly from the **other 30 tuning threads** (`rag_bank_tuning30_v2.json`: `29` usable threads, `78` consensus-good + `29` consensus-bad examples, zero held-out overlap) via TF-IDF cosine similarity + same-origin boost into single-pass `GPT-6 Luna` produced the largest single jump across all tuning experiments (`rag-l8-results.json` `804e7408...`; `rag-l8-v2-results.json` `34763645...`; `rag-l8-v3-results.json` `594d11b6...`):

| Tuning arm (20 tuning threads, zero held-out access) | First-attempt OK | In-turn quote % | Semantic recall (source-first) | Strict 2-of-3 non-author precision (Haiku / GLM / DeepSeek) | Est. batch USD / 1k threads |
|---|---:|---:|---:|---:|---:|
| `rag_luna_k3_full3j` (`k=3`, base message prompt) | 20/20 | 100.0% | 93.2% (41/44) | 91.4% (74/81) (`86.4%` / `93.8%` / `90.1%`) | $0.506 |
| **`rag_luna_k4_recall_full3j` (`k=4` + completeness check)** | **20/20** | **100.0%** | **95.5% (42/44)** | **91.0% (81/89)** (`84.3%` / `94.4%` / `87.6%`) | **$0.583** |
| `rag_luna_v3_tight` (heavier prompt rules) | 20/20 | 100.0% | 87.2% (41/47) | 88.0% (73/83) | $0.631 |
| `rag_luna_v3` + `Haiku` repair guard | 19/20 | 69.9% | 66.0% (31/47) | 73.5% (36/49, 2-of-2 non-author) | $1.056 |

### 3d. Zero-leakage held-out check on the 30 frozen Step 2.1 gold threads

Running the frozen winning recipe (`rag_luna_k4_recall_full3j`, zero further tuning, zero overlap between the 29-thread tuning RAG bank and the 30 frozen Step 2.1 scoring threads; `qualify-30gold-report.json` SHA-256 `2e6972c1e1fe1a4017b1f072571416e61170e5ee9fb851874a334de2d9e6b585`) gave:

- **First-attempt completion:** `30/30` (`0%` truncation) at **`$0.6704` per 1,000 threads** (OpenAI native batch; ~$2.26 for all 3,373 staged PM threads).
- **Exact single-turn verbatim quotes:** `202/204` = **`99.02%`** (stratified bootstrap 95% LB `97.93%`).
- **Lead source-first recall (51 Step 2.1 `source_first_observations`):** `51/51` = **`100.0%`** (95% LB **`100.0%`**).
- **Full-thread source-first recall (97 GLM facts across all 30 threads):** `91/97` = **`93.81%`** (95% LB **`91.25%`**, clearing `>= 90%`).
- **Granular 4-model-union claim coverage (944 Step 2.1 `accepted_candidate_claims`):** `662/944` = `70.13%` (95% LB `62.92%`; single-pass concise relations cover 100% of lead source-first facts while omitting redundant multi-chunk duplicates).
- **Strict 2-of-3 non-author blind precision:** `180/202` = **`89.11%`** (95% LB **`82.91%`**, UB `93.75%`; `j-haiku-med 88.6%`, `j-glm-flash 89.6%`, `j-deepseek 89.7%` — `+29.6` points above Luna on `relations.md` and `+49.6` points above frontier Opus, but still short of the `>= 95%` lower confidence bound).

## 4. Stop verdict and business options

Single-pass `GPT-6 Luna` + few-shot RAG clears source-first coverage (`100%` of lead source-first facts; `93.8%` full-thread recall, LB `91.25%`), quote accuracy (`99.02%`), and truncation (`0/30`) at `$0.67/1,000` threads with **zero Colab reliance**, but reaches **`89.11%` strict blind precision (LB `82.91%`, UB `93.75%`)** — still short of the `>= 95%` lower confidence bound. Per plan §2.3, paid runs on the remaining 320 held-out threads remain stopped awaiting an owner business decision:

1. **Adopt `GPT-6 Luna` + RAG (~89% strict blind accuracy, 94%–100% coverage, ~$0.67/1,000 threads, zero Colab)** by lowering the message-intake correctness bar (e.g., to `>= 85%` LB / `>= 88%` point) and running full 350-thread qualification + 15-question eval.
2. **Train a custom fine-tuned open-weight model** via companion plan [`plan_colab_gpu_offload.md`](../../plan_colab_gpu_offload.md) (`#664`) to pursue the unchanged `95% / 90%` dual gate (can also run on any rented cloud GPU if prepaid Colab units ever run out).
3. **Pause project-manager message intake** until one of the above is selected.
