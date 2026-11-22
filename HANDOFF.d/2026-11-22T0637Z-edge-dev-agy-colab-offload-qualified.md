---
summary: "Google Colab GPU offload (#664) Phases 0–3, Step 1.3 open-weight bake-off, Phase 2 QLoRA & held-out evaluation, and Step 4.1 sandbox drain completed; Step 4.2 awaits #607 pilot."
kind: handoff
status: OPEN
read-when: resuming Google Colab GPU batch offload (#664) for Step 4.2 production backfill drain once #607 Step 3.1 pilot window is authorized
issue: 664
owner: feat/colab-live-proofs-664
---

# Handoff — Google Colab GPU offload live proofs, open-weight bake-off, QLoRA fine-tuning, and sandbox lease drain completed; Step 4.2 gated on `#607` pilot (#664)

Registered plan: [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md)
Tracking issue: https://github.com/u2giants/theoracle/issues/664

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None blocking right now** — companion `#607` Step 2.3 qualified three-pass `GPT-6 Luna` (`relations_messages` seat, [`2712f979`](https://github.com/u2giants/theoracle/commit/2712f979)) and is advancing through `#607` Steps `2.4 → 3.1` (`HANDOFF.d/2026-11-22T0525Z-edge-dev-agy-intake-step24-batch-and-cache.md`).

**Downstream post-pilot business checkpoints (not blocking now; present together once `#607` Step 3.1 14-day pilot numbers exist):**
1. *Whether to keep the exact-verbatim-quote rule after seeing measured 14-day pilot cost and monthly Colab Compute Unit (CCU) usage projected across all employees.* **Recommendation:** Keep exact verbatim quotes (`L1`). Blocks `#607` Step 4.1 company-wide expansion only if changed.
2. *Final live-proof review of the Company Map project-management page, five cited answers, and unsent interview questions.* **Recommendation:** Present five cited answers and the unsent interview questions together once `#607` Step 4.1 and `#664` Step 4.2 complete while keeping the interview bot off. Blocks checking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607) and [#664](https://github.com/u2giants/theoracle/issues/664).

### Already settled — do NOT re-ask
- **Integrate prepaid Google Colab compute units into The Oracle (2026-11-21):** Authorized by Albert in chat; one-time Google `colaboratory` OAuth completed by Albert on 2026-11-21 (~`3,034.74` CCUs verified; `3,027.44` CCUs remaining after all `#664` live GPU runs).
- **No frontier cloud API bills for bulk intake (2026-11-18, `#607` L9):** *"we can't afford frontier models."*
- **Keep exact verbatim words through the 14-day pilot (2026-11-19, `#607`):** *"ok, keep exact words through the pilot."*
- **AI executes all manual steps and merges PRs itself (2026-09-28 / 2026-10-23 / 2026-10-29 standing rulings):** Never ask Albert to click notebooks, paste keys, or review PRs.

*(Instruction for the next session: zero business questions block Step 4.2 — execute Step 4.2 automatically as soon as `#607` Step 3.1's pilot window or another `colab_offload = true` batch is staged.)*

---

## 1. What this application is

**The Oracle** (`https://github.com/u2giants/theoracle`, **PUBLIC** repository, single protected branch `main`) is the Company Map and evidence-backed operational adviser for POP Creations / Spruce Line. It ingests company documents, flowcharts, meeting transcripts, Teams chats, ClickUp tasks, and authorized email into a structured knowledge graph (`cmap` schema in Supabase Postgres + FalkorDB graph `company`), answers employee questions in English and Mandarin citing verbatim source quotes, and interviews employees over Microsoft Teams to fill gaps ([developer guide](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [architecture](https://github.com/u2giants/theoracle/blob/main/docs/architecture.md), [service inventory](https://github.com/u2giants/theoracle/blob/main/docs/agents/09-container-and-service-inventory.md)):

- `apps/web` — Next.js 16 web app on Vercel (`https://oracle.designflow.app`, project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`).
- `apps/brain` — Python 3.12+ FastAPI API and background worker on Coolify (`oracle-brain`, `https://oracle-brain.designflow.app`, image `ghcr.io/u2giants/theoracle-brain`).
- `oracle-sandbox-private` — Dedicated isolated Coolify sandbox (`lh8tiwrst3hwij9yr3ss4vdx`, `quote-tools` + `sandbox-db`) holding `#607` private message threads, gold sets, QLoRA adapters, and sealed blind-review receipts.

---

## 2. What we set out to do this session, and why

Clear [#664](https://github.com/u2giants/theoracle/issues/664) across [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) after Albert completed the one-time Google `colaboratory` OAuth sign-in: execute the live `L4` and `A100` GPU smoke gates (`0.1`, `1.2`), run the `#607` `tuning_50` open-weight bake-off (`1.3`), build the holdout-isolated SFT corpus and train/evaluate the 4-bit QLoRA adapter on `A100` and `L4` (`2.1`–`2.2`), and prove end-to-end 110-passage pull-lease draining + 60-second kill-mid-lease recovery in an isolated Coolify sandbox (`4.1`) while keeping production untouched until `#607` Step 3.1's pilot window opens (`4.2`).

---

## 3. Current state — what is true right now

- **Predecessor handoff retired under the successor rule (`AGENTS.md` §3a):** `HANDOFF.d/2026-11-22T0346Z-edge-dev-agy-colab-offload-hardened.md` was verified on `main` (commit [`f858b6d9`](https://github.com/u2giants/theoracle/commit/f858b6d9a463986e9e0ee27b63fe8a51724977eb), merged in PR [#672](https://github.com/u2giants/theoracle/pull/672)), every open obligation, 1Password item ID, dead end, and coordinator record is carried forward into [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) and this handoff, all router links were updated, and the predecessor file is deleted in this PR (`feat/colab-live-proofs-664` → `main`).
- **Steps `0.1`, `0.2`, `1.1`, `1.2`, `1.3`, `2.1`, `2.2` (sandbox evaluation), `3.1`, `3.2`, `3.3`, and `4.1` completed and verified (`7.30` total CCUs spent across all runs; `Active assignments: 0`):**
  - **Step `0.1` & `1.2` live GPU smokes:** Verified `NVIDIA L4, 23034 MiB` (`1.94 CCU/hr` actual) and `NVIDIA A100-SXM4-40GB, 40960 MiB` (`6.73 CCU/hr` actual), plus 10-passage synthetic vLLM guided-JSON batch (`10/10` valid JSON & verbatim quotes, `0.17 CCU`, `0` post-run sessions). Hardened [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) into a single-`colab exec` flat-upload + `<= 8 MiB` chunked-reassembly + 20s WebSocket keepalive architecture (`COLAB_GUARD_MANAGED_TEARDOWN=1`, proxy-token error redaction).
  - **Step `1.3` open-weight bake-off ([docs/verification/2026-11-colab-openweight-tuning.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-openweight-tuning.md)):** Scored all three pinned open-weight models on `tuning_50` (`101` passages, `0/101` malformed JSON across all three): `Qwen/Qwen2.5-32B-Instruct-AWQ@5c7cb76a268fc6cfbb9c4777eb24ba6e27f9ee6c` (`A100`, `12.36%` blind correctness, `75.39%` quote valid, `12.9` actual CCUs/1k), `Qwen/Qwen3-32B-AWQ@0499c3ac83fdef8810b907a23894ba91e95eddd8` (`A100`, `2.63%` blind correctness, `74.51%` quote valid, `16.9` actual CCUs/1k), and `Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698` (`L4`, `11.99%` blind correctness, `90.38%` quote valid, `6.08` actual CCUs/1k), confirming zero-shot open-weight models hit the same `prompts/relations.md` conversational over-extraction failure mode as cloud/frontier models and triggering Phase 2 QLoRA.
  - **Steps `2.1`–`2.2` QLoRA fine-tuning & blind held-out check ([docs/verification/2026-11-colab-relations-qualification.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-relations-qualification.md)):** Built holdout-isolated `tuning50_sft.jsonl` (`101` windows: `59` positive + `42` negative, SHA-256 `e6d16816...`; `0` overlap with `350` held-out threads), trained `qwen25-14b-tuning50-v1` (`adapter_sha256 = 028552c75e06...`) on `Qwen/Qwen2.5-14B-Instruct@cf98f3b3bbb457ad9e2bb7baf9a0125b6b88caa8` in `~1.48` actual CCUs on `A100`, and blind-scored on the `30` frozen Step 2.1 gold threads (`initial30_packet.jsonl`): `L4` (`AWQ + LoRA`) reached **`97.78%` quote valid** and **`27.27%` blind correctness** at **`12.7` actual CCUs/1k passages** (`7.84%` semantic recall, receipt `a7d796c9...`), and `A100` (`bf16 + LoRA`) reached **`96.43%` quote valid** and **`22.22%` blind correctness** at **`39.0` actual CCUs/1k passages** (`9.80%` semantic recall, receipt `5f2e6d72...`). Companion `#607` qualified three-pass `GPT-6 Luna` (`relations_messages`, [`2712f979`](https://github.com/u2giants/theoracle/commit/2712f979)) for informal chat threads while Colab `L4` (`Qwen2.5-14B-Instruct-AWQ`) handles `colab_offload = true` document/transcript drains.
  - **Step `4.1` sandbox lease-drain & kill-recovery proof ([docs/verification/2026-11-colab-sandbox-drain-proof.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-sandbox-drain-proof.md)):** Verified 60s kill-mid-lease expiry, disjoint concurrent `FOR UPDATE SKIP LOCKED` claims (`64` + `46`, `overlap = 0`), `HTTP 409 Conflict` on expired lease submit, and live Colab `L4` `drain_leases.py` completion across `110/110` passages (`2` batches, `100%` quote validation, `11/11` sources `read`, `$0.00` OpenRouter relations spend, `~0.27` actual CCUs, `0` post-run sessions).
- **Full repository test suite verified:** `667 passed` in `apps/brain` against real `pgvector:pg16` + `falkordb:v4.20.7`, `ruff` clean, `scripts/test-task-gates.sh` `38/38` passed, `verify-vercel-contract.mjs` passed, and `ai-doc-health` / `ai-doc-reachability` / `ai-doc-safety` clean.
- **Still open (`⬜`):** Step `4.2` production backfill drain proof (`- [ ] live proof` on [#664](https://github.com/u2giants/theoracle/issues/664)), gated on `#607` Step 3.1 pilot window ([plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md#L36)). Production (`oracle.designflow.app`, `oracle-brain.designflow.app`) remains untouched (`BRAIN_COLAB_LEASE_ENABLED=false`).
- **Unrelated `HANDOFF.d/` successor-review candidates noted (`handoff-writer` § Retention — untouched per non-interference rule):** GitHub issue [#27](https://github.com/u2giants/theoracle/issues/27) is `CLOSED`; 13 older files still list `issue: 27` for reconciliation by their owners: `2026-10-12T0434Z-edge-dev3-codex-operating-model-release.md` (`codex/01a12d57-75a5-7733-b8c0-0a5d5dc93f24`), `2026-10-12T1540Z-edge-dev3-codex-semantic-acceptance-continuation.md` (`codex/01a130a9-5aca-7561-8dff-38bf645c6055`), `2026-10-13T1436Z-edge-dev3-codex-native-live-acceptance.md` (`codex/01a132aa-596e-7d72-9957-cbabf6a79cf6`), `2026-10-13T1639Z-edge-dev3-codex-current-admission-closeout.md` (`codex/01a135e2-53ea-73d0-8ff2-9047b8c094bb`), `2026-10-14T0113Z-edge-dev3-codex-admission-runtime-closeout.md` (`codex/01a1362e-9981-7980-b191-089c0d73b9e0`), `2026-10-14T2047Z-edge-dev3-codex-toolkit-admission-closeout.md` (`codex/chat-01a13a68-dc8a-73b1-8506-808c7227d8d9`), `2026-10-14T2340Z-edge-dev3-claude-falkordb-coolify-plan.md` (`claude (s02-coordination-pr-gates-baf147 worktree)`), `2026-10-15T1200Z-edge-dev3-claude-falkordb-coolify-deploy.md` (`claude/falkordb-coolify-deploy`), `2026-10-15T1915Z-edge-dev3-claude-falkordb-offserver-backup.md` (`Claude chat 96374819`), `2026-10-18T1352Z-edge-dev3-mimo-live-proof-120s-wrap.md` (`mimo/edge-dev3-live-proof-120s-wrap`), `2026-10-18T1838Z-edge-dev3-codex-fresh-native-v2.md` (`codex/native-fresh-v2`), `2026-10-20T0103Z-edge-dev3-mimo-native-v2-run-proof.md` (`mimo/native-v2-run-proof-standing-order`), and `2026-10-21T0110Z-edge-dev-mimo-offline-rebuild-implementation.md` (`mimo/offline-rebuild-implementation`).

---

## 4. Everything we tried that did NOT work

1. **Running two sequential `colab exec` commands on the same `google-colab-cli v0.8.0` session:**
   - *What we tried:* Ran a `staged_install.py` `colab exec` followed by a second `wrapped_<script>.py` `colab exec` on the same session.
   - *How & why it failed:* `google-colab-cli` saves `s.session_id` in `sessions.json` after the first `colab exec` closes its Jupyter WebSocket, and the second `colab exec` intermittently hangs forever on `execution.py:225` (`os.makedirs('/content', ...)`). Fixed permanently in [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) by uploading nested files to flat `/content/_cg_stage_*` paths via HTTP REST (`colab upload`) and executing package installation, directory moves, and target script launch inside a **single `colab exec`**.
2. **Using `colab install` or pinned `vllm<1.0.0` / `peft==0.15.2` on Colab Python 3.12/3.13:**
   - *How & why it failed:* `colab install` enforces a 30-second output-silence timeout that aborts during `vllm` wheel downloads, and strict upper-bound pins conflict with Colab's preinstalled CUDA/PyTorch stack. Fixed via in-VM `uv pip install --system` inside `preflight.py` and compatible lower-bound pins in [apps/brain/colab/requirements-colab.txt](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/requirements-colab.txt).
3. **In-VM `google.colab.runtime.unassign()` inside `drain_leases.py` before `colab exec` finishes:**
   - *How & why it failed:* Calling `runtime.unassign()` inside the child script powered off the Colab VM before the Jupyter kernel sent its final `status: idle` WebSocket message, causing host `colab exec` to raise `RuntimeError: Connection was lost.` even after all `110/110` chunks had been submitted cleanly. Fixed via `COLAB_GUARD_MANAGED_TEARDOWN=1` in [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) and [apps/brain/colab/run_vllm_batch.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/run_vllm_batch.py) so host-side `finally: colab stop` tears down the VM cleanly after reading exit status and downloading outputs.
4. **Running `vllm.LLM` directly inside IPython `exec` or feeding raw prompts without chat-template rendering:**
   - *How & why it failed:* vLLM V1 `EngineCore` spawns worker processes requiring `__main__.__file__` (fixed by launching `/content/<script.py>` via `Popen`), and instruct/Qwen3 models require `tokenizer.apply_chat_template(..., enable_thinking=False)` so thinking tokens do not exhaust `max_tokens` inside guided JSON decoding (fixed in `_format_prompts_for_llm` in [apps/brain/colab/run_vllm_batch.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/run_vllm_batch.py)).
5. **Uploading a `105 MB` QLoRA `adapter.tar.gz` in a single `colab upload` HTTP `PUT`:**
   - *How & why it failed:* `google-colab-cli`'s `ContentsClient.upload` base64-encodes the entire file into one JSON `PUT` (~`140 MB`), causing the Colab runtime proxy to reset the TCP socket (`ConnectionResetError(10054)`). Fixed permanently in [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) by splitting uploads `> 8 MiB` into `_cg_part_*.bin` flat chunks and reassembling + unlinking them inside the single `colab exec` prelude (`test_large_upload_splits_into_proxy_safe_chunks`).
6. **Buffered `subprocess.run(..., capture_output=True)` and Punica LoRA CUDA graph compilation inside `colab exec`:**
   - *How & why it failed:* Inside Colab's Jupyter kernel (`ipykernel`), `sys.stdout` is a Python `OutStream` rather than OS file descriptor `1`; running `subprocess.call` / `capture_output=True` kept the WebSocket completely silent for 6–10 minutes during 28 GB weight downloads and Punica LoRA 134-graph compilation (`Connection was lost.`), while default LoRA slot buffers strained `L4`'s 12.7 GB host RAM. Fixed permanently via line-buffered `Popen` streaming + a 20-second WebSocket heartbeat thread in [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) and `max_loras=1, max_cpu_loras=1, enforce_eager=True` for LoRA runs in [apps/brain/colab/run_vllm_batch.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/run_vllm_batch.py).

---

## 5. Root causes and key findings

1. **Measured Google AI Ultra CCU economics (`colab --auth=adc usage`):**
   - `NVIDIA A100-SXM4-40GB` burns **`6.73 CCUs/hr`** actual (vs `15.0 CCU/hr` conservative cap -> **~297 A100 hours/month** inside 2,000 CCUs).
   - `NVIDIA L4` (24 GB) burns **`1.94 CCUs/hr`** actual (**~1,030 L4 hours/month** inside 2,000 CCUs).
   - Concurrent `A100` + `L4` sessions (`8.67 CCU/hr` combined) work cleanly on Google AI Ultra.
2. **Why `google-colab-cli` orphaned `[?]` sessions need `state.client.unassign(endpoint)` if a host process is hard-killed (`SIGKILL`):**
   - Normal `SIGINT`/`SIGTERM`/exceptions run `preflight.py`'s `finally: _teardown_session` while `oracle-colab-guard-*/sessions.json` still exists. If the host process itself is externally `SIGKILL`ed, `colab stop` cannot resolve `[?]` server-only endpoints by name; unassigning via `colab_cli.common.state` (`state.auth_provider = AuthProvider.ADC; state.client.unassign(a.endpoint)`) immediately zeroes server burn.
3. **Extraction accuracy & recall findings across zero-shot open-weight and QLoRA (`#664` + `#607`):**
   - Zero-shot open-weight models (`Qwen2.5-32B` `12.36%`, `Qwen2.5-14B` `11.99%`, `Qwen3-32B` `2.63%`) exhibit the exact same `prompts/relations.md` conversational over-extraction failure mode as cloud/frontier models (`Opus 5.5` `39.5%`, `Sol` `38.1%`).
   - 4-bit QLoRA (`qwen25-14b-tuning50-v1`, `~1.48` CCUs on `A100`) lifted verbatim quote validity to **`97.78%`** and strict blind correctness to **`27.27%`** on `L4` (`12.7` CCUs/1k passages — `3.1x` cheaper than `A100`'s `39.0` CCUs/1k) while cutting spurious chatter by `>85%`, but two-stage `flat -> relations` still caps recall at `~8%–10%` on unstructured chats compared to `#607`'s single-pass `GPT-6 Luna` + few-shot RAG route (`89.11%` precision / `93.81%` recall). Colab `L4` (`Qwen2.5-14B-Instruct-AWQ`, `100%` quote validation on document-shaped sources at `~2.45` CCUs/1k cold / `<0.5` CCU/1k warm) is optimal for zero-API-cost bulk document/transcript backfills while `GPT-6 Luna` + RAG leads unstructured chat intake.

---

## 6. Exact next steps

1. **Wait for `#607` Steps `2.4 → 3.1` pilot staging (`HANDOFF.d/2026-11-22T0525Z-edge-dev-agy-intake-step24-batch-and-cache.md`) or an approved `colab_offload = true` document/transcript backfill:**
   - *You'll know it's ready when:* `#607` Step 3.1 pilot sources or another approved `colab_offload = true` backfill batch is ready for production ingestion.
2. **Execute Step `4.2` — Production backfill drain proof (`- [ ] live proof` on [#664](https://github.com/u2giants/theoracle/issues/664)):**
   - Redeclare `ai-task-gates start --class production` and pass `ai-task-gates check --before production`.
   - Inject `op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN` and `BRAIN_COLAB_LEASE_ENABLED=true` on production Coolify `oracle-brain` (`https://oracle-brain.designflow.app`), then verify `/health` and `scripts/verify-live-version.sh`.
   - Run `uv run python -m colab.preflight --script colab/drain_leases.py --gpu L4 --max-wall-minutes 60 --max-ccu 4 --install-requirements colab/requirements-colab.txt --pass-env BRAIN_COLAB_API_URL --pass-env BRAIN_COLAB_WORKER_TOKEN -- --hf-model <pinned_repo> --hf-revision <40_char_sha> [--lora-path /content/adapter.tar.gz]` against `https://oracle-brain.designflow.app`.
   - *You'll know it worked when:* Newly ingested entities, edges, and verbatim citations with `colab-vllm/...` provenance render cleanly on `https://oracle.designflow.app/map`, `colab --auth=adc usage` shows `Active assignments: 0` (`Usage rate: 0.00/hr`), production CCU economics are posted on `#664`, `- [ ] live proof` is checked off on `#664`, and this handoff file is deleted in the closing PR.

---

## 7. Constraints and gotchas in force

- **Zero Colab dependency in live paths:** Keep `BRAIN_COLAB_LEASE_ENABLED=false` in production until an active Step 4.2 batch drain runs; live uploads (`colab_offload = false`) and `#604` live interview turns (`awaits_reply(source_id)`) never touch Colab.
- **Hard `L1` secret boundary:** Never pass `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, or `BRAIN_SHARED_TOKEN` to Colab. Pass `BRAIN_COLAB_WORKER_TOKEN` exclusively via `preflight.py --pass-env BRAIN_COLAB_WORKER_TOKEN`.
- **Public repo privacy (`L8`) & `#607` holdout seal (`L5`):** Never commit message text, thread titles, raw JSONL model outputs, server IPs, or LoRA weights to `u2giants/theoracle` or public Hugging Face Hub.
- **Always verify `Active assignments: 0` before ending any session:** Run `colab --auth=adc usage` and `colab --auth=adc sessions` after every Colab run.

---

## 8. Access and environment

- **GitHub CLI (`gh`):** Authenticated as `u2giants`.
- **Google Colab CLI (`google-colab-cli v0.8.0`):** Authenticated via ADC (`colab --auth=adc usage` verified active, `3,027.44` CCUs remaining, `Active assignments: 0`).
- **Private Coolify sandbox (`oracle-sandbox-private`):** Holds `/sandbox/records/step-2.3-relations/colab-664-20261121/` (`0700`/`0600` packets, blind-score receipts, and trained `lora-adapter/adapter.tar.gz` + `adapter_manifest.json`).
- **1Password vault `vibe_coding` (item IDs & titles only — never print secret values):**
  - `"The Oracle — Sandbox Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `naytnzqu4ldh4t7jutxbx7btzq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - `"The Oracle — Production Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `gulz2yow5h7tkkrdsopkh4udxq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - `"OpenRouter Management API Key - POP AI services (production)"` — item `vqk7qypdfdqog6bo7r6f63zz5m`, field `credential`.

---

## 9. Open questions and risks

- **Companion `#607` Step 2.3 / Step 3.1 gate (2026-11-22):** Step `4.2` production backfill drain waits on `#607` Step 3.1's approved pilot batch (or another `colab_offload = true` batch); consolidated in §0 above.
- **Meeting-transcript triage (`plan_meeting_triage_pipeline.md`, 2026-11-08):** Remains blocked at Step 0.1 on Entra tenant admin consent for `OnlineMeetingTranscript.Read.All` + `CallTranscripts.Read.All` (tracked separately under its own plan).

---

## Part (b) — Coordinator record (sub-agent delegation)

- **Carried forward from PR [#667](https://github.com/u2giants/theoracle/pull/667) ([`e29b8876`](https://github.com/u2giants/theoracle/commit/e29b8876a2569cced0aa9a122d9b5c0d25a22df8)) and PR [#672](https://github.com/u2giants/theoracle/pull/672) ([`f858b6d9`](https://github.com/u2giants/theoracle/commit/f858b6d9a463986e9e0ee27b63fe8a51724977eb)):**
  - `flash` helpers `b438dd36` (Step `0.2`), `c8366766` (Step `1.2`), `fb89b826` (Step `3.3`), and `e8f80585` (Step `1.2` `first_finish_reason` telemetry) — all merged on `main`, worktrees closed; all `lead-only` live GPU, private sandbox, QLoRA, scoring, and Coolify verification steps in this session were executed directly by the lead (`6aba6e03`).

---

## Self-audit (`handoff-writer` standard)

1. *Comprehensive enough for a brand-new developer with no project/session context to pick up without skipping a beat?* **Yes** — §§1–3 explain The Oracle, its runtime services, all completed Steps `0.1`–`4.1` with links to their three verification proofs, and the exact Step `4.2` boundary; §6 gives the exact Step `4.2` production commands and pass criteria.
2. *Detailed enough to continue as well as I could right now?* **Yes** — §§4–5 document all six live `google-colab-cli` / `vllm` / LoRA / teardown constraints uncovered and fixed on real Colab VMs, exact `A100` (`6.73/hr`) and `L4` (`1.94/hr`) CCU rates, orphan-session recovery, and the full Step `1.3` / Phase `2` accuracy findings.
3. *Every relevant detail included (background, goals, current state, failures, decisions, constraints, risks, next actions, verification)?* **Yes** — covered across §§0–9 and Part (b) using portable GitHub URLs (zero machine-local paths) and vault/item IDs only for secrets, plus the `issue: 27` successor-review audit in §3.
4. *Line-by-line Section 0 sweep: if Albert read ONLY §0, would he see every business decision across §§1–9 and Part (b), and zero technical approvals?* **Yes** — walked §§1–9 and Part (b) line by line: zero blocking owner decisions remain after `#607` Step 2.3 qualified three-pass `GPT-6 Luna` (`2712f979`), both downstream post-pilot checkpoints appear in §0 with explicit recommendations and settled-ruling dates, and zero technical approvals appear anywhere in §0.

## Next-session prompt

```text
Resume #664 from main of https://github.com/u2giants/theoracle once #607 Step 3.1's pilot window (or another colab_offload=true backfill batch) is ready.
Read AGENTS.md first, then https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md (STATUS first), and this handoff in HANDOFF.d/.
Verify `colab --auth=adc usage` shows Active assignments: 0, redeclare `ai-task-gates start --class production` and pass `ai-task-gates check --before production`, configure `op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN` and `BRAIN_COLAB_LEASE_ENABLED=true` on production `oracle-brain`, drain the approved `colab_offload=true` pilot batch via `preflight.py` + `drain_leases.py`, verify live `colab-vllm/...` citations on `https://oracle.designflow.app/map`, check off `- [ ] live proof` on #664, and delete this handoff file in the closing PR.
```
