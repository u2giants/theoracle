---
summary: "Steps 2.4 & 2.5 proof (#607): OpenAI native /v1/batches + prefix-cache measurement on 100 passages, and ScaleDown vs GPT-6 Luna function sorting."
kind: proof
status: current
read-when: reviewing the Step 2.4 OpenAI native batch and prefix-cache live measurement, the Step 2.5 ScaleDown /classify business-area bake-off, or the end-of-Phase-2 readiness check for plan_pm_message_intake.md (#607)
---

# Message intake steps 2.4 and 2.5 — OpenAI native batch, prefix-cache measurement, and business-area sorting proof

This document records the aggregate-only verification evidence completing Phase 2 (steps 2.4 and 2.5) of [`plan_pm_message_intake.md`](../../plan_pm_message_intake.md) ([issue #607](https://github.com/u2giants/theoracle/issues/607)). All live evaluations ran inside `oracle-sandbox-private` (`quote-tools` and isolated ephemeral Postgres/FalkorDB containers), with zero company text, quotes, employee emails, or secrets exported (`L7`), zero frontier models anywhere in the pipeline (`L9`), and production kept untouched prior to the Phase 3 pilot cut point.

## 1. Step 2.4 — OpenAI native `/v1/batches`, stall-salvage, and prefix-cache measurement (`100` live passages)

### 1.1 Provider routing and batch architecture

- **Direct OpenAI provider & native batch client:** Added [`apps/brain/brain/llm_batch.py`](../../apps/brain/brain/llm_batch.py) (`submit_and_wait_batch`, `build_responses_batch_jsonl`, `reconcile_batch_results`) plus `openai-api/*` provider resolution and parameter gating in [`apps/brain/brain/llm.py`](../../apps/brain/brain/llm.py) (`OPENAI_API_KEY` / `BRAIN_OPENAI_API_KEY` in [`apps/brain/brain/config.py`](../../apps/brain/brain/config.py)). When the direct OpenAI key is unset, [`apps/brain/brain/extract/relations.py`](../../apps/brain/brain/extract/relations.py) logs a warning and falls back cleanly to the synchronous OpenRouter path.
- **Three-round cross-source batching (`Pass 1 -> Pass 2 -> Pass 3`):** Instead of waiting on three serial batches per source, `handle_relations` (`_claim_sibling_message_jobs` + `_run_message_batch` in [`apps/brain/brain/extract/relations.py`](../../apps/brain/brain/extract/relations.py)) coalesces up to `100` queued `origin IS NOT NULL` message sources (`w3000` intact-turn windowing: `<= 12,000` characters and `<= 18` chunks intact; `<= 8,000` characters / `<= 16` chunks on mega-threads) and submits all pending windows together in **3 batch rounds total**: Pass 1 (`relations_messages.md`), Pass 2 (`relations_messages_audit.md`), and Pass 3 (`relations_messages_gate.md`, `<= 25` candidate relations per item, `max_output_tokens = 16000`).
- **30-minute ceiling, tail-stall salvage, and temporary file hygiene:** Every batch enforces `MAX_POLL_DEADLINE_SECONDS = 1800.0` (`<= 30` minutes), strictly rejects missing, duplicate, or foreign `custom_id` entries (`tests/test_llm_batch.py::test_result_id_mismatch_rejected`), deletes uploaded input/output/error batch files via `DELETE /v1/files/{id}` in `finally`, and — when `/v1/batches` stalls on a small tail of items — cancels after `180s` without progress, waits up to `300s` for `cancelled` to harvest all completed `output_file_id` items, and completes only the remaining tail items via `/v1/responses` `service_tier="flex"` (which bills at the identical 50% batch list rate: `$0.05/1M` input, `$0.005/1M` cached input, `$0.25/1M` output).

### 1.2 Prompt-cache anatomy and decision not to reorder `relations_messages*.md`

OpenAI automatic prefix caching activates only when two prompts share **`>= 1,024` identical leading tokens** (~4,100 characters). Measuring the fixed instruction text of all three qualified `v7` prompts (`live-100-passages-report.json` `static_template_char_counts`):

| Pass template | Fixed chars before first `{{...}}` slot | Total fixed template chars (all variable slots empty) | Approx. fixed tokens | Reaches OpenAI `1,024`-token cache threshold even if moved to top? |
|---|---:|---:|---:|---|
| `prompts/relations_messages.md` (Pass 1) | 371 | 3,857 | ~964 | No (`< 1,024` tokens) |
| `prompts/relations_messages_audit.md` (Pass 2) | 287 | 2,947 | ~737 | No (`< 1,024` tokens) |
| `prompts/relations_messages_gate.md` (Pass 3) | 258 | 2,556 | ~639 | No (`< 1,024` tokens) |

Even if artificial padding were added to force `1,024` cached tokens per call at the `$0.045/1M` batch cache discount (`$0.050 -> $0.005`), the theoretical maximum gross saving across 3 passes is **`~$0.138` per 1,000 windows** (`~$0.46` across the entire 3,373-thread backlog) before subtracting padding cost — while invalidating `message_relations_prompt_hash()` and risking attention drift on the qualified `v7` prompts. Per `plan_pm_message_intake.md` step 2.4 (*"restructure the prompt only if the measured saving is worth it"*), all three `relations_messages*.md` prompt files remain byte-identical to Step 2.3.

### 1.3 Live 100-passage sandbox batch run (`live-100-passages-report.json`)

Running the three-pass `GPT-6 Luna` (`relations_messages`) pipeline across **100 live `w3000` turn-packed message windows** (`92` non-tuning threads including all `30` Step 2.1 gold scoring threads; `122` standard 400-token chunks) via OpenAI `/v1/batches` + `service_tier="flex"` tail-salvage (`live-100-passages-report.json`, SHA-256 `3f4e5ad2e96f39a959b29ab3002240cd76cd2f0cdf382fb7eabd9d204fa959b8`) produced:

| Round | Batch ID | Submitted | `/v1/batches` completed | `flex` tail completed | First-attempt `ok` (`truncations`) | Input tokens | Cached tokens (`cache_hit_share`) | Output tokens | Measured 50%-batch USD |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| Pass 1 (`relations_messages.md`) | `batch_6b03055f29348190a3cfcb2f4913a0ad` | 100 | 100 | 0 | `100 / 100` (`0`) | 185,155 | 0 (`0.00%`) | 310,888 | $0.086980 |
| Pass 2 (`relations_messages_audit.md`) | `batch_6b03066b22a48190a7820166daba4f78` | 100 | 0 *(salvaged)* | 100 | `100 / 100` (`0`) | 280,149 | 35,819 (`12.79%`) | 299,071 | $0.087163 |
| Pass 3 (`relations_messages_gate.md`, `<= 25` claims/item) | `batch_6b0309f0420c81908c60ab214ed03ae4` | 110 | 0 *(salvaged)* | 110 | `110 / 110` (`0`) | 312,082 | 15,977 (`5.12%`) | 212,724 | $0.068066 |
| **Total (`100` `w3000` windows)** | — | **310** | **100** | **210** | **`100 / 100` windows (`0`)** | **777,386** | **51,796 (`6.66%`)** | **822,683** | **$0.242209** |

- **Step 2.4 cost-vs-forecast gate (`<= 10%`):** Step 2.3's measured OpenAI native batch rate on turn-packed `w3000` windows (`455` windows across 350 held-out threads in `stage4-heldout350-w3000-qualification.json`) forecast **`$0.259350`** per 100 `w3000` windows (`$2.5935 / 1,000` turn-packed windows). Actual 100-window batch spend was **`$0.242209`** (`$2.4221 / 1,000` turn-packed windows; `$1.9853 / 1,000` standard 400-token chunks on this shorter-thread alphabetical slice) — **`-6.61%` relative difference (`within_10pct_of_forecast: true` — PASS)**.
- **Measured cache-hit share:** `51,796 / 777,386 = 6.66%` overall (`0.00%` inside `/v1/batches`, `12.79%` in Pass 2 `flex`, `5.12%` in Pass 3 `flex`), saving `$0.00233` across 100 windows and confirming that prompt reordering is not warranted.
- **Quote match & runtime multi-pass carry-forward fix caught by live batch:** Across `1,009` sanitized relations (`0` truncations), only `6` failed quote matching (**`99.41%` raw quote match**, `502 / 508 = 98.82%` among endpoint-resolved items). The live run also caught two runtime gaps in `relations.py` relative to the Step 2.3 qualification harness (`verify_w3000_350.py`): (a) Pass 1 `new_mentions` keys (`x1`, `x2`) were not carried forward when Pass 2/3 returned `"new_mentions": []`, and (b) non-standard entity labels (`"Task"`, `"Order"`) in `new_mentions` were not normalized to `"Artifact"`. Fixed in [`apps/brain/brain/extract/relations.py`](../../apps/brain/brain/extract/relations.py) (`_merge_message_new_mentions` + `_sanitize_message_payload`, verified in `tests/test_relations.py::test_sanitize_message_payload_enforces_ontology_and_quotes`). Also reset `llm_batch.py`'s stall clock on the `validating -> in_progress` transition so validation queue time never triggers premature stall cancellation.

## 2. Step 2.5 — Business-area sorting: ScaleDown `/classify` vs `GPT-6 Luna` (`function_assign`)

### 2.1 Why `flat.classify_body` and `function_assign` cannot share one `/classify` request

In [`apps/brain/brain/extract/flat.py`](../../apps/brain/brain/extract/flat.py), `classify_body` relies on ScaleDown `/classify`'s default single-label **softmax** normalization (`sum(scores) == 1.0` across the 6 passage-kind labels) to skip chatter at `CHATTER_SKIP_SCORE = 0.8`. Combining 13 active `cmap.function` business-area labels into the same softmax request dilutes probability mass across 19 labels and lowers chatter scores below `0.8` (`plan_pm_message_intake.md` §11 forbids lowering `CHATTER_SKIP_SCORE`). Therefore `function_assign` was evaluated as its own `/classify` call (`"reasoning": false`, labels built dynamically from `cmap.function` key + name + description + aliases) across both default softmax (`multi_label=false`) and independent sigmoid (`multi_label=true`) modes.

### 2.2 Calibration on `tuning_50` and one-shot held-out bake-off on `heldout_30`

Thresholds `0.10..0.90` and both `multi_label` modes were calibrated strictly on `tuning_50` (`50` threads, `58` passages); the strongest configuration was `multi_label=false, reasoning=false, threshold=0.10`. Pooled unlabelled passage picks from `ScaleDown /classify`, `z-ai/glm-5.3-flash` (`flat` seat), and `openai/gpt-6-luna` (Step 2.3 winner) on the **30 frozen Step 2.1 held-out threads** (`36` passages) were adjudicated by a non-candidate blind panel (`anthropic/claude-haiku-5.5` + `deepseek/deepseek-v4.1-flash`) (`step25-bakeoff-report.json`, SHA-256 `f7cac7314cc7b91d0d19fea24047e7c5976129096bbc8639963a7a152a142297`):

| Candidate (`heldout_30`: `30` threads, `36` passages) | Main function right (95% LB, gate `>= 90%`) | Gold functions found (95% LB, gate `>= 85%`) | Wrong picks (95% UB, gate `<= 10%`) | `tuning_50` main right / wrong picks | Measured USD / 1,000 passages | Step 2.5 outcome |
|---|---|---|---|---|---:|---|
| `ScaleDown /classify` (`reasoning=false`, `threshold=0.10`) | 86.11% (`77.78%` LB) | 72.86% (`66.18%` LB) | 23.88% (`30.43%` UB) | 93.10% / 21.36% | $0.0000 (`7.57M` ScaleDown input tok/1k) | **FAIL** (`wrong_picks` UB `30.43% > 10%`, recall LB `66.18% < 85%`) |
| `z-ai/glm-5.3-flash` (`prompts/function_assign.md`, prior `flat` seat) | 91.67% (`86.05%` LB) | 81.43% (`76.71%` LB) | 17.39% (`22.95%` UB) | 96.55% / 19.47% | $0.1966 (sync) | Baseline ("before" cost) |
| **`openai/gpt-6-luna` (`prompts/function_assign.md`, Step 2.3 winner)** | **86.11%** (`78.12%` LB) | **77.14%** (`72.22%` LB) | **8.47%** (`14.10%` UB; `1.96%` LB) | **98.28%** (`94.92%` LB) / **5.49%** (`9.18%` UB) | **$0.1704 sync / $0.0852 batch** | **Selected per Step 2.5 rule** (`2.8x` fewer wrong picks than ScaleDown, `2.0x` fewer than GLM, lowest paid cost, zero frontier models `L9`) |

- **Cost per 1,000 passages before vs after Step 2.5:** Before Step 2.5 (seated `flat` model `z-ai/glm-5.3-flash`), message `function_assign` cost **`$0.1966 / 1,000` passages**. After Step 2.5 (`openai/gpt-6-luna` via `message_function_model` in [`apps/brain/brain/function_assign.py`](../../apps/brain/brain/function_assign.py)), message `function_assign` costs **`$0.1704 / 1,000` passages synchronous** (`-13.3%` while cutting wrong picks in half from `17.39%` to `8.47%`) and **`$0.0852 / 1,000` passages at batch/flex pricing** (`-56.7%`).
- **Runtime wiring & tests:** [`apps/brain/brain/function_assign.py`](../../apps/brain/brain/function_assign.py) keeps the full ScaleDown `/classify` implementation behind `BRAIN_SCALEDOWN_FUNCTION_ASSIGN_ENABLED=false` (with dynamic `cmap.function` label+alias building, top-3 thresholding, 3-attempt automatic model fallback, and unchanged `merge_priors` + `executive-company-wide` fallback) while routing `origin IS NOT NULL` sources by default to `BRAIN_MESSAGE_FUNCTION_MODEL` or `relations_messages` (`openai/gpt-6-luna`). Verified by `tests/test_functions.py` (`test_scaledown_labels_built_from_function_table`, `test_scaledown_scores_become_weights_top_three`, `test_scaledown_failure_falls_back_to_model`, `test_priors_still_apply_on_scaledown_path`) and `tests/test_answer.py::test_scoped_answer_excludes_other_functions`.

### 2.3 15-question `brain/eval` end-to-end Company Map check (`step25-15q-e2e-eval.json`)

Re-running the full 15-question `brain/eval` end-to-end Company Map pipeline on the `30` Step 2.1 gold threads (`step25-15q-e2e-eval.json`, SHA-256 `ddfa31ab2fb19231e10dc0f0d8b76e767986ace3a68bcedb12d1ba4498dcb1f2`) confirmed **zero drop** relative to Step 2.3:

| End-to-end Map build (`30` Step 2.1 gold threads) | Entities | Relations | Communities | Questions (`errors`) | `mean_score` | `mean_score_legacy` | Delta vs Step 2.3 (`0.7118`) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Step 2.3 `relations.md` reference (`GPT-6 Luna`) | 309 | 491 | 91 | 15 (`0`) | 0.6361 | 0.5867 | `-0.0757` |
| Step 2.3 winner baseline (`3-pass Luna` + `GLM` `function_assign`) | 292 | 196 | 100 | 15 (`0`) | 0.7118 | 0.6889 | baseline |
| **Step 2.5 selected (`3-pass Luna` + `GPT-6 Luna` `function_assign`)** | **292** | **196** | **83** | **15 (`0`)** | **0.7163** | **0.7222** | **`+0.0045` (PASS — zero drop)** |
| Diagnostic: `3-pass Luna` + `ScaleDown /classify` (`0.10` frozen) | 292 | 196 | 70 | 15 (`0`) | 0.7340 | 0.7178 | `+0.0222` |

## 3. End-of-Phase-2 reciprocal review through Step 5.1

Re-reading Steps `3.1`, `3.1a`, `4.1`, and `5.1` of [`plan_pm_message_intake.md`](../../plan_pm_message_intake.md) against the landed runtime surfaced three concrete adjustments, repaired in this PR before Phase 3 starts:

1. **14-day recency window and 3-pass spend estimate in `ingest.py`:** Because all `3,373` cleaned 90-day threads are already staged in `cmap.intake_thread` and `ingest._threads` orders oldest-first, running `python -m brain.intake.ingest` without a date window in Step 3.1 would have ingested 90-day-old threads instead of the 14-day pilot window, and its old `$0.0008/passage` constant predated three-pass `relations_messages`. Added `--days` (`COALESCE(ended_at, started_at, updated_at) >= since`) and `estimated_usd_per_passage(settings)` (`$0.0018/passage` batch, `$0.0032/passage` sync) in [`apps/brain/brain/intake/ingest.py`](../../apps/brain/brain/intake/ingest.py) (`tests/test_intake_ingest.py::test_days_window_and_3pass_cost_rate`).
2. **Seat API route correction for Step 3.1:** The admin seat endpoint in [`apps/brain/brain/api/models.py`](../../apps/brain/brain/api/models.py) is `PUT /models/{stage}` (`PUT /models/relations_messages`), not `PUT /models/seats/relations_messages`. Recorded in the Phase 3 handoff.
3. **Ilona `3.1a` isolation:** PR `#677` (`HANDOFF.d/2026-11-22T1350Z-edge-dev3-codex-ilona-live-pilot.md`) tracks Ilona's prefixed live comparison separately via `--thread-prefix`; Step 3.1's project-manager pilot must scope `--days 14` to the project-manager cohort (or keep `BRAIN_INTAKE_ENABLED=false` during CLI ingest so the hourly global sweep never pulls unprefixed backlog outside the 14-day pilot).
