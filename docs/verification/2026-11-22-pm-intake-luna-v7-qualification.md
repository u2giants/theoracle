---
summary: "Step 2.3 qualification proof (#607): three-pass GPT-6 Luna clears correctness, recall, quote, truncation, and 15-question brain/eval gates."
kind: proof
status: current
read-when: reviewing how GPT-6 Luna qualified for message-intake relations (step 2.3 of plan_pm_message_intake.md), the tuning progression on the 50 tuning threads, or the sealed #664 SFT dataset manifest
---

# Message intake step 2.3 — three-pass `GPT-6 Luna` qualification and `#664` SFT manifest

This document records the aggregate-only qualification evidence for step 2.3 of [`plan_pm_message_intake.md`](../../plan_pm_message_intake.md) ([issue #607](https://github.com/u2giants/theoracle/issues/607)). Every experiment ran inside `oracle-sandbox-private` (`quote-tools` and isolated ephemeral Postgres/FalkorDB containers, zero raw text or quotes exported, zero frontier models in the pipeline, production untouched).

## 1. Cloud fine-tuning availability check (`OpenAI /v1/fine_tuning/jobs`)

Probing OpenAI's fine-tuning endpoint (`POST https://api.openai.com/v1/fine_tuning/jobs` with a zero-data probe across `gpt-6-luna`, `gpt-5.6-luna`, `gpt-5.4-mini-2026-03-17`, and `gpt-4.1-mini-2025-04-14`) returned `HTTP 403`:

> *"OpenAI is winding down the fine-tuning platform and your organization is no longer able to create new fine-tuning training jobs."*

Accordingly, weight-level fine-tuning is routed exclusively to prepaid Google Colab GPUs via companion plan [`plan_colab_gpu_offload.md`](../../plan_colab_gpu_offload.md) ([issue #664](https://github.com/u2giants/theoracle/issues/664)), while cloud qualification uses multi-pass structured inference on `openai/gpt-6-luna` (`medium` effort, JSON mode).

## 2. Iterative multi-pass tuning on the 50 tuning threads (zero held-out access)

All prompt and pass-structure iterations used only the 50 frozen tuning threads (`sample-v1` `split == "tuning"`), scored by the calibrated 2-of-3 non-author blind panel (`claude-haiku-5-5` medium, `deepseek/deepseek-v4.1-flash`, `z-ai/glm-5.3-flash`) and source-first operational fact recall:

| Iteration | Split | Architecture (`openai/gpt-6-luna`, medium) | First-attempt OK | Quote valid | 2-of-3 non-author precision | Source-first recall | Native batch USD / 1k passages | Sandbox SHA-256 |
|---|---|---|---:|---:|---:|---:|---:|---|
| Control (`relations.md`) | `initial_30` | Single-pass original prompt | 30/30 | 97.28% LB | 59.50% | — | $0.5140 | `5f11300fd3ce0500...` |
| Iter 1 (`v4`) | `tuning_20` | 2-pass extract + audit | 20/20 | 100.00% | 94.12% (48/51) | 70.73% (29/41) | $0.8131 | `b6b5b816c258235f...` |
| Iter 2 (`v5`) | `tuning_20` | 2-pass turn-by-turn scan + 6-criterion rewrite (never drop valid work) | 20/20 | 100.00% | **95.24%** (80/84) | **90.24%** raw / 87.80% kept | $1.4091 | `e71aab323cb20915...` |
| Iter 3 (`v6`, rejected) | `tuning_50` | Forced verbatim-substring endpoints + `P2P -> HANDS_OFF_TO` | 50/50 | 100.00% | 68.59% (262/382) | 65.84% (106/161) | $1.8027 | *(abandoned)* |
| **Iter 4 (`v7`, frozen finalist)** | **`tuning_50`** | **`v5` + Pass 3 independent 6-criterion precision gatekeeper** | **50/50** | **100.00%** | **92.44%** (367/397; DeepSeek `94.90%`, Haiku `93.20%`) | **83.23%** (134/161 GLM) | **$2.2833** | `2de384dd65df3a57...` |
| Iter 5 (`v8`, rejected) | `tuning_20` | Aggressive Pass 2 drop rule (`drop` `31/64` candidates) | 20/20 | 100.00% | 67.65% (23/34) | 48.78% (20/41) | $1.2900 | *(abandoned)* |

### Sealed `#664` Step 2.1 QLoRA SFT dataset from `tuning_50`

The `367` non-author-verified `keep` relations from `Iter 4 (v7)` across all `50` tuning threads were exported in `apps/brain/colab/build_tuning_sft.py` format inside `oracle-sandbox-private`:

- **Manifest (`tuning50_sft_input.manifest.json`):** SHA-256 `18b3fe60570713ed1ecc12cf3446dbcc09488e19e99fb22342ae0eb9d859bf92`
- **Dataset (`tuning50_sft_input.jsonl`):** `58` windows (`50` positive, `8` negative), `holdout_overlap: 0`, SHA-256 `37d944656c8f5f24cacb470827c85dffc2cce0c51fb882b295c2bff69fa58dab`

## 3. One-shot held-out qualification on the 30 frozen Step 2.1 gold threads

Freezing `v7` (`prompts/relations_messages.md` → `prompts/relations_messages_audit.md` → `prompts/relations_messages_gate.md` plus deterministic `_sanitize_message_payload` single-turn quote cleaning and `Person->Person APPLIES_TO` exclusion) with zero further prompt edits on the 30 held-out Step 2.1 scoring threads produced:

- **Tie-broken 2-of-3 non-author blind panel (`stage4-heldout30-v7-qualification.json`, SHA-256 `7d1c7078ede4035a7dd808e5502d34b61c8582b3a4e84329c699a0c6e8f177f0`):**
  - First-attempt completion: `30 / 30` (`0` truncations, `0` malformed).
  - Quote validation (`validate_response` + single-turn verbatim): **`196 / 196 = 100.00%`** (stratified bootstrap 95% LB **`100.00%`**, gate `>= 98.00%` **PASS**).
  - Non-author correctness: **`193 / 196 = 98.47%`** (95% LB **`97.40%`**, UB `99.49%`, gate `>= 95.00%` **PASS**; `j-deepseek 97.85%`, `j-glm-flash 95.45%`, `j-haiku-med 89.80%`).
  - Step 2.1 lead source-first recall (`52` human/lead observations + verified missing relations): **`50 / 52 = 96.15%`** (95% LB **`94.12%`**, UB `97.18%`, gate `>= 90.00%` **PASS**).
- **Full 3-of-3 non-author audit where all three judges independently grade all `196` claims (`stage4-heldout30-v7-full3j-audit.json`, SHA-256 `a219f4e315bd5b5e1da67f0b235b072715f90a3721e09fa303f38037c5247e7f`):**
  - Full 3-judge coverage: `196 / 196` claims (`j-glm-flash`: `192/196 = 97.96%`, `j-deepseek`: `182/196 = 92.86%`, `j-haiku-med`: `177/196 = 90.31%`; `0` `timing_status`, `0` `scope_stance`, and `0` `description_exact` misses).
  - Weighted & unweighted `bakeoff.py` correctness: **`191 / 196 = 97.45%`** (95% LB **`95.57%`**, UB `98.86%`, gate `>= 95.00%` **PASS**).
  - Weighted & unweighted `bakeoff.py` Step 2.1 lead source-first recall: **`49 / 52 = 94.23%`** (95% LB **`90.48%`**, UB `96.67%`, gate `>= 90.00%` **PASS**).
  - Auxiliary dense GLM 30-thread source-first check: `63 / 73 = 86.30%` (95% LB `81.82%`).

## 4. Full 350-thread held-out truncation and quote qualification

Evaluating the frozen three-pass `GPT-6 Luna` pipeline across all **350 held-out scoring threads** (`150` initial held-out + `200` stratified expansion threads, `867` standard 400-token passages / `455` turn-packed passages, zero overlap with `tuning_50`) verified the windowing contract (`stage4-heldout350-w3000-qualification.json`, SHA-256 `7936a13d25837c4e6bceef87c4950a29820635adcde2cd97d946d4248ec47a5f`):

- **Window & output-budget contract (`w3000_intact_turns_16k_out_chunked_p3`):** Threads up to `12,000` characters and `<= 18` turns run intact (`initial_30_identical_to_v7: true` — 100% byte-identical across all 30 Step 2.1 gold threads), oversized `> 12,000`-character email chains (`7` of `350` threads) split on turn/paragraph boundaries `<= 8,000` characters, all three passes run at `max_tokens = 16000`, and Pass 3 batches `<= 25` candidate relations per call (matching `relations.py` `_post_chat` and `_process_window`).
- **Diagnostic note on unsplit megaslices vs sub-400-token splitting:** Grouping unsplit `4,500–10,422`-token emails with a `8,000` Pass 3 cap truncated `5/350` threads (`1.56%` UB), while chopping single turns mid-thought at `400` tokens (`stage4-heldout30-w600-full3j.json`, SHA-256 `7b12cebf...`) fragmented intra-turn context (`94.40%` precision, `86.54%` recall). Keeping turns intact up to `3,000` tokens with `16,000` output tokens and `<= 25`-item Pass 3 batches preserved full intra-turn context with zero truncations.
- **First-attempt truncations across all 350 held-out threads:** **`0 / 350`** (`0` in `initial_150`, `0` in `added_200`; `349` first-attempt `ok` + `1` transient socket `http-0` recovered to `ok` on automatic retry, `0` malformed JSON).
- **Exact conditional 95% upper truncation bound (`bakeoff.conditional_truncation_upper_bound` on `641` non-tuning frame):** **`0.0078` (`0.78% <= 1.00%` gate PASS)**.
- **350-thread quote validation (`3,840` unique validated relations):** **`100.00%`** (`estimate: 1.0`, `lower_95: 1.0`, `upper_95: 1.0`, gate `>= 98.00%` **PASS**).
- **Measured cost across all 350 held-out threads:** `$2.3601` synchronous / **`$1.1800` OpenAI native batch** (`$1.3611` per 1,000 standard 400-token passages, `$2.5935` per 1,000 turn-packed passages, or **`$3.37` per 1,000 threads** — projecting **`~$11.37` total** for the entire `3,373`-thread project-manager staging backlog).

## 5. 15-question `brain/eval` end-to-end Company Map comparison

Building three full Company Maps (`resolve` → `function_assign` → `project` → `communities` → `brain.eval.run.evaluate_question`, `0` errors across all `15` questions) from the `30` frozen Step 2.1 gold threads inside isolated Postgres/FalkorDB (`stage4-15q-e2e-eval.json`, SHA-256 `cf415277a317a35600f6c0222398957a23266d6be2b7e93ab72ef5fd5617547d`, answered on `anthropic/claude-haiku-5.5` and graded on `z-ai/glm-5.3-flash`) confirmed the winner outscored both references:

| Map build (`30` Step 2.1 gold threads) | Entities | Validated relations | Communities | Questions (`errors`) | `mean_score` | `mean_score_legacy` | `mean_supported_share` | Gate (`>= reference`) |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `reference_relations_md_luna` (original `relations.md` on `GPT-6 Luna`) | 309 | 491 | 91 | 15 (`0`) | 0.6361 | 0.5867 | 0.6204 | reference |
| `step21_gold_reference` (all `702` accepted Step 2.1 candidate claims) | 278 | 702 | 93 | 15 (`0`) | 0.6040 | 0.5311 | 0.6265 | reference |
| **`winner_luna_v7_multipass` (3-pass `GPT-6 Luna` `relations_messages`)** | **292** | **196** | **100** | **15 (`0`)** | **0.7118** | **0.6889** | **0.6255** | **PASS (`+0.0757` vs `relations.md`, `+0.1078` vs Step 2.1 pool)** |

## 6. Runtime wiring landed in `apps/brain` (production kept off until pilot)

- [`apps/brain/brain/sql/040_message_relations_seat.sql`](../../apps/brain/brain/sql/040_message_relations_seat.sql) — idempotently widens `cmap.model_seat`'s `model_seat_stage_check` to include `relations_messages` and all stages in `brain.seats.STAGES`.
- [`apps/brain/brain/seats.py`](../../apps/brain/brain/seats.py), [`apps/brain/brain/config.py`](../../apps/brain/brain/config.py), [`apps/brain/brain/api/models.py`](../../apps/brain/brain/api/models.py) — adds `relations_messages` stage and `BRAIN_MESSAGE_RELATIONS_MODEL` fallback (`message_relations_chosen()`), keeping document/meeting `relations` completely unchanged when unset.
- [`apps/brain/brain/prompts/relations_messages.md`](../../apps/brain/brain/prompts/relations_messages.md), [`relations_messages_audit.md`](../../apps/brain/brain/prompts/relations_messages_audit.md), [`relations_messages_gate.md`](../../apps/brain/brain/prompts/relations_messages_gate.md), and [`apps/brain/brain/extract/relations.py`](../../apps/brain/brain/extract/relations.py) — runs the qualified three-pass extract → audit/rewrite → precision-gatekeeper flow plus `_sanitize_message_payload` on `origin IS NOT NULL` sources whenever `message_relations_chosen(settings)` is true (`668 / 668` `pytest` tests passing).
