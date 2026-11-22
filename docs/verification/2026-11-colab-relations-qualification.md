---
summary: "Phase 2 proof: holdout-isolated QLoRA adapter training on tuning_50 and blind held-out evaluation on 30 frozen Step 2.1 gold threads across A100 and L4 (#664)."
kind: proof
status: current
read-when: reviewing QLoRA fine-tuning results, L4 vs A100 adapter economics, or held-out qualification bounds for issue 664 and companion issue 607
---

# Google Colab GPU offload Phase 2 — QLoRA fine-tuning & blind held-out qualification (`#664` / `#607`)

Executed 2026-11-22 EST strictly inside `oracle-sandbox-private` (`quote-tools`, `0700`/`0600` custody) and ephemeral Google Colab GPU runtimes orchestrated by `apps/brain/colab/preflight.py`. Zero private company text, message excerpts, or trained adapter weights were written to GitHub or public Hugging Face Hub (`L8`), and zero production writes occurred.

## 1. Step 2.1 — Holdout-isolated SFT dataset & 4-bit QLoRA training

- **Holdout leakage guard (`L5`):** `apps/brain/colab/build_tuning_sft.py` verified **`0` overlapping thread keys or source IDs** against `holdout_350_sha256_manifest.json` (`350` held-out threads = `30` initial + `120` reserve + `200` expanded; SHA-256 `786662cf484b5b0b165f99b25816bba1cf679dd799e1933ca39f0b6c17580801`).
- **Training corpus (`tuning50_sft.jsonl`):** Built strictly from `#607`'s `50` tuning threads using consensus-adjudicated single-turn verbatim relations passing `relations.validate_response`:
  - **`101` passage windows** (`59` positive windows across `43 / 50` tuning threads + `42` negative/chatter restraint windows formatted as `{"relations": [], "new_mentions": []}`).
  - **`214` verified relations** + **`91` verified `new_mentions`**, wrapped in the exact `relations.build_prompt` user message.
  - **Dataset SHA-256:** `e6d168169f08a37f7e9b6c72d1a9511863314198c06843e08c7f4442247f4509`.
- **QLoRA training (`apps/brain/colab/train_relations_lora.py` on Colab `A100`):**
  - **Base model:** `Qwen/Qwen2.5-14B-Instruct` @ `cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8` (`trust_remote_code=False`).
  - **Hyperparameters:** 4-bit NF4 double quantization (`bnb_4bit_compute_dtype=bfloat16`), `r=16`, `lora_alpha=32`, `lora_dropout=0.05`, `target_modules="all-linear"`, cosine LR `2e-4`, `3` epochs, `seed=42`, `gradient_checkpointing=True`.
  - **Private custody (`L1`, `L8`):** Retrieved via `preflight.py --download` (`adapter.tar.gz` + `adapter_manifest.json`) with zero Supabase or OpenRouter secrets on Colab, and stored with `0700`/`0600` permissions inside `oracle-sandbox-private` (`/sandbox/records/step-2.3-relations/colab-664-20261121/lora-adapter/`).
  - **Adapter manifest (`qwen25-14b-tuning50-v1`):**
    - `model_tag`: `colab-vllm/Qwen/Qwen2.5-14B-Instruct@cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8+lora:028552c75e06`
    - `adapter_sha256`: `028552c75e063ae1cb4be0a9d67e37e269132710d87a94af98490339209302a7`
    - **Training convergence (`21` optimizer steps, `4.80e5` tokens, `3` epochs):** loss `1.796` (`epoch 1.47`, `mean_token_accuracy = 63.62%`) → `1.115` (`epoch 2.94`, `mean_token_accuracy = 77.74%`), final `mean_token_accuracy = 78.35%` (`train_runtime = 531.2s`, total `wall_sec = 789.72s`).
    - **Compute-unit cost:** **`~1.48 CCUs` actual** on `A100` at `6.73 CCUs/hr` (`3.29 CCUs` conservative cap estimate; `<= 25` CCU budget gate cleared by `>16×`), `Active assignments: 0` verified immediately after download.

## 2. Step 2.2 — Blind held-out evaluation (`initial_30` frozen gold threads, `A100` vs `L4`)

- **Frozen held-out packet (`initial30_packet.jsonl`):** `30` Step 2.1 gold scoring threads = **`57` passages**, `prompt_hash` `83b2629a328206286d3ff0443709d8c7d477d673b2a78a3d5308c74908806df0`, SHA-256 `690f24caa4b45008f127de7545177594302f42197c68c954aa4d5339e4361340` (`0` overlap with `tuning50_sft.jsonl`).
- **Scoring rubric:** `apps/brain/brain/colab_bakeoff.py` + `apps/brain/brain/intake/bakeoff.py` (`score_candidate`) + calibrated ZDR 2-of-3 non-author L8 judge panel (`claude-haiku-5-5`, `gpt-6-luna`, `deepseek-v4.1-flash`) + Step 2.1 `accepted_candidate_claims` (`944`) and `source_first_observations` (`51`).

| Serving configuration (`+lora:028552c75e06`) | GPU | Malformed JSON | First-truncation threads (`UB95`) | Raw -> quote-valid relations | Quote valid (`LB95`) | Gate-0 in-turn quote (`LB95`) | 2-of-3 non-author correctness (`LB95`) | Source-first semantic recall (`LB95`) | Inference sec (wall sec) | Actual CCUs / 1k passages (cap est.) | API USD / 1k |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `Qwen/Qwen2.5-14B-Instruct` (`bf16`) + QLoRA | `A100` | `0 / 57` | `8 / 30` (`36.67%`) | `112 -> 108` | `96.43%` (`90.57%`) | `74.11%` (`48.21%`) | **`22.22%`** (`15.87%`) | **`9.80%`** (`8.33%`) | `752.4s` (`1188.3s`) | `39.0 CCU` (`86.87`) | `$0.00` |
| `Qwen/Qwen2.5-14B-Instruct-AWQ` + QLoRA | `L4` | `0 / 57` | `4 / 30` (`23.33%`) | `45 -> 44` | **`97.78%`** (`93.10%`) | `71.11%` (`63.41%`) | **`27.27%`** (`16.67%`) | `7.84%` (`4.08%`) | `872.6s` (`1340.1s`) | **`12.7 CCU`** (`13.06`) | `$0.00` |

**Private sandbox score receipt digests (SHA-256):**
- `step22_initial30_scores.json` (`A100` `bf16 + LoRA`): `5f2e6d727b618a1509ac78d2779cdafc1b6caffe1f208756ecd891a0dee0b398` (`83` novel claims blind-judged; ZDR judge spend `$0.0503`).
- `step22_initial30_l4_score.json` (`L4` `AWQ + LoRA`): `a7d796c9be7ad005bb272407aff21da772abe6c021c5efc1c55ab8c899ebe6e0` (`32` novel claims blind-judged; ZDR judge spend `$0.0391`).

## 3. Findings, `L4` vs `A100` economics, & `#607` qualification gate

1. **Measurable QLoRA lift over zero-shot (`Step 1.3` -> `Step 2.2`):**
   - Training `qwen25-14b-tuning50-v1` on just `50` tuning threads (`~1.48` CCUs) lifted verbatim quote compliance from `90.38%` to **`96.43%–97.78%`**, lifted strict 2-of-3 blind correctness by **1.85×–2.27×** (`11.99%` -> **`22.22%` on `A100` / `27.27%` on `L4`**), and suppressed spurious conversational chatter volume by **>85%** (`45` raw relations across `57` passages on `L4` vs `400+` zero-shot).
2. **`L4` (`AWQ + LoRA`) beats `A100` (`bf16 + LoRA`) by `3.1×` on CCUs per 1,000 passages:**
   - Because `NVIDIA L4` burns `1.94 CCU/hr` vs `6.73 CCU/hr` on `A100` (`enforce_eager=True` Punica LoRA mode), `L4` delivered **`12.7` actual CCUs / 1,000 passages** vs `39.0` on `A100` while also achieving higher verbatim quote compliance (`97.78%`) and higher blind precision (`27.27%`).
3. **Single-pass QLoRA vs `#607`'s newly qualified 3-pass `GPT-6 Luna` (`relations_messages` seat):**
   - Both single-pass `A100` and `L4` QLoRA runs under `prompts/relations.md` remain below `#607` Step 2.3's strict `>=95%` correctness LB95, `>=90%` recall LB95, and `<=1%` truncation UB95 bar on informal employee messages because single-pass `prompts/relations.md` lacks multi-pass self-audit and independent precision gating across noisy chat turns (`59` positive training windows vs broad conversational variety).
   - Companion `#607` Step 2.3 ([`2026-11-22-pm-intake-luna-v7-qualification.md`](2026-11-22-pm-intake-luna-v7-qualification.md)) independently solved unstructured employee messages by seating three-pass `GPT-6 Luna` (`relations_messages`: `97.45%–98.47%` correctness, `94.23%–96.15%` recall, `100.00%` quote validation, `$1.36/1,000` passages in OpenAI native batch), while `#664`'s offline Colab `L4` pull-lease pipeline ([`2026-11-colab-sandbox-drain-proof.md`](2026-11-colab-sandbox-drain-proof.md): `100.0%` verbatim quote validation, `$0.00` API spend, `~2.45` CCUs/1k passages cold / `<0.5` CCU/1k warm) is dedicated to bulk document/transcript offload (`colab_offload = true`) in `Step 4.2`.
