---
summary: "Step 1.3 sandbox proof: zero-shot open-weight vLLM guided-JSON bake-off on 50 tuning threads across Qwen2.5-32B, Qwen3-32B, and Qwen2.5-14B (#664)."
kind: proof
status: current
read-when: reviewing zero-shot open-weight model performance on #607 tuning threads, Colab CCU economics, or why #664 proceeded to Step 2.1 QLoRA tuning
---

# Google Colab GPU offload Step 1.3 — open-weight relations bake-off on `#607` `tuning_50`

Executed 2026-11-21 / 2026-11-22 EST strictly inside `oracle-sandbox-private` (`quote-tools`, `0700`/`0600` custody; zero raw message text, quotes, or employee/customer names exported; production untouched). All three open-weight candidates ran headlessly on prepaid Google Colab GPUs via `apps/brain/colab/preflight.py` + `apps/brain/colab/run_vllm_batch.py` (`trust_remote_code=False`, 40-char commit SHA pins, vLLM V1 `GuidedDecodingParams` enforcing `export_relations_schema()`) and were blind-scored via `apps/brain/brain/colab_bakeoff.py` + `apps/brain/brain/intake/bakeoff.py` + the calibrated ZDR 2-of-3 non-author L8 judge panel (`claude-haiku-5-5`, `gpt-6-luna`, `deepseek-v4.1-flash` under guardrail `"Oracle 607 no retention"`).

## 1. Frozen benchmark & holdout isolation (`L5`, `L8`)

- **Tuning packet (`tuning50_packet.jsonl`):** `50` tuning threads = **`101` passages**, `prompt_hash` `83b2629a328206286d3ff0443709d8c7d477d673b2a78a3d5308c74908806df0`, SHA-256 `db9bfdbedd7d60a578680457f9befc2e818dbdf8f41ae45c4206e5fa22de09e5`.
- **Held-out seal (`holdout_350_sha256_manifest.json`):** `350` held-out threads (`30` initial + `120` reserve + `200` expanded = `867` passages), SHA-256 `786662cf484b5b0b165f99b25816bba1cf679dd799e1933ca39f0b6c17580801`, verified **`0` thread/source overlap** with `tuning_50`.
- **Target gates (`plan_colab_gpu_offload.md` Step 1.3):** `>=96%` correctness and `>=99%` quote validation to skip Phase 2 QLoRA; otherwise proceed to Step 2.1 QLoRA fine-tuning on `tuning_50`.

## 2. Step 1.3 zero-shot open-weight results (`50` tuning threads, `101` passages)

| Candidate (pinned `repo@sha`) | GPU | Malformed JSON | First-truncation threads (`UB95`) | Quote valid (`LB95`) | Gate-0 in-turn quote (`LB95`) | 2-of-3 non-author correctness (`LB95`) | Source-first semantic recall (`LB95`) | Inference sec (wall sec) | Actual CCUs / 1k passages (cap est.) | API USD / 1k |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen/Qwen2.5-32B-Instruct-AWQ@5c7cb76a268fc6cfbb9c4777eb24ba6e27f9ee6c` | `A100` | `0 / 101` | `7 / 50` (`22.0%`) | `75.39%` (`71.00%`) | `54.04%` (`48.46%`) | **`12.36%`** (`8.70%`) | `10.26%` (`5.13%`) | `324.1s` (`819.2s`) | **`12.9 CCU`** (`33.79`) | `$0.00` |
| `Qwen/Qwen3-32B-AWQ@0499c3ac83fdef8810b907a23894ba91e95eddd8` | `A100` | `0 / 101` | `4 / 50` (`12.0%`) | `74.51%` (`70.69%`) | `57.35%` (`49.26%`) | **`2.63%`** (`1.31%`) | `6.41%` (`2.70%`) | `338.8s` (`913.1s`) | **`16.9 CCU`** (`37.67`) | `$0.00` |
| `Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698` | `L4` | `0 / 101` | `7 / 50` (`22.0%`) | **`90.38%`** (`87.52%`) | **`73.37%`** (`68.26%`) | **`11.99%`** (`8.82%`) | `10.26%` (`5.19%`) | `813.7s` (`1139.1s`) | **`6.08 CCU`** (`6.27`) | `$0.00` |

**Private sandbox score receipt digests (SHA-256):**
- `step13_qwen25_32b_score.json`: `4d584c718b6dc5100605cfdb8d9881f08beef89934149ceb05231ccf872e6c226` (`313` novel claims blind-judged; ZDR judge spend `$0.1663`).
- `step13_qwen3_32b_score.json`: `7d89b311282b4455a335bfdc05c3e74859bde467f0868136f8270bee9fad6b4d` (`556` novel claims blind-judged; ZDR judge spend `$0.2326`).
- `step13_qwen25_14b_score.json`: `8556a89ce7554f2e40991e9c7dbc54ed37efb0664111709c26c7689bca07e786` (`418` novel claims blind-judged; ZDR judge spend `$0.2295`).

### Measured Colab Compute Unit (CCU) burn rates

Live `colab --auth=adc usage` instrumentation established exact Google AI Ultra burn rates significantly lower than our conservative preflight caps:

- **`NVIDIA A100-SXM4-40GB`:** **`6.73 CCUs/hr`** actual (`15.0 CCU/hr` conservative cap in `preflight.py` — 2,000 monthly CCUs buy **~297 A100 hours/month**).
- **`NVIDIA L4` (24 GB):** **`1.94 CCUs/hr`** actual (`2.0 CCU/hr` cap in `preflight.py` — ~1,030 L4 hours/month).

## 3. Failure-mode diagnosis & Step 1.3 decision branch

1. **100% grammar-valid JSON, zero syntax failures:** vLLM V1 `GuidedDecodingParams(json=relations_schema)` eliminated malformed JSON (`0 / 101` across every model), confirming the offline packet + guided-decoding pipeline works cleanly.
2. **Same conversational ontology failure mode observed on cloud/frontier models (`#607`):** Under the document-oriented `prompts/relations.md`, zero-shot open-weight models exhibit the exact over-extraction and multi-turn quote-splicing failure mode seen on closed cloud models (where even frontier `Claude Opus 5.5` scored `39.5%` and `GPT-6.2 Sol` scored `38.1%` in [`2026-11-21-pm-intake-tuning-and-frontier-check.md`](2026-11-21-pm-intake-tuning-and-frontier-check.md)): over-assigning `OWNS` / `PRODUCES` / `policy` to routine chat/email turns and copying across packer turn headers (`Gate 0` drop).
3. **Decision branch executed (`plan_colab_gpu_offload.md` §9 Step 1.3):** Because zero-shot open-weight candidates missed `>=96%` correctness and `>=99%` quote validation on `tuning_50`, execution proceeded directly to **Phase 2 (`Step 2.1` QLoRA fine-tuning on `tuning_50` + `Step 2.2` held-out evaluation)**, documented in [`2026-11-colab-relations-qualification.md`](2026-11-colab-relations-qualification.md).
