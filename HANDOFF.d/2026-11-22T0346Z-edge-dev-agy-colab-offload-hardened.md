---
summary: "Resume #664 after preflight session lifecycle, __future__ wrapper, L1 secret guard, and #607 bakeoff bridge landed; blocked on one-time Google Colab OAuth."
kind: handoff
status: BLOCKED
read-when: resuming Google Colab GPU batch offload (#664) for live GPU smokes, #607 sandbox bake-off, QLoRA tuning, or lease-drain proofs
issue: 664
owner: fix/colab-offload-hardening-664
---

# Handoff — Google Colab GPU offload hardened (`__future__`, session lifecycle, L1 secret boundary, `#607` bakeoff bridge); live GPU runs blocked on one-time OAuth (#664)

Registered plan: [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md)
Tracking issue: https://github.com/u2giants/theoracle/issues/664

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None blocking `#664`'s next technical steps — zero business decisions are waiting on Albert to finish `#664`.**

*(Per owner ruling 2026-09-28, the one-time interactive Google OAuth sign-in on `accounts.google.com` for scope `https://www.googleapis.com/auth/colaboratory` on `u2giants@gmail.com` is a platform authentication boundary reported under `Blocked —`, never a business-meaning approval.)*

Put any companion `#607` business question below to Albert in **one** plain-English message only when `#607` reaches that milestone (never include any technical approval):

- **Companion `#607` rollout choice — only if Albert wants `#607` live before `#664` finishes ([companion `#607` handoff §0](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0302Z-edge-dev-agy-intake-step23-gated-stop.md)):** Every affordable cloud model on the approved four-model list missed `#607`'s 95% accuracy bar on real messages (peaking at 92.61%–94.83% even under optimistic assumptions). **Recommendation:** Hold `#607` live intake until `#664` runs larger open-weight and custom fine-tuned models on Albert's prepaid 2,000 monthly Google Colab compute units against the unchanged 95% accuracy and exact-quote rules at `$0` extra per-token API cost. Blocks `#607` steps 2.4, 3.1, and 4.1 only if `#664` is bypassed.
- **Downstream post-pilot checkpoints on `#607` / `#664` (not blocking now; present together once 14-day pilot numbers exist):**
  1. *Whether to keep the exact-verbatim-quote rule after seeing measured 14-day pilot cost and monthly Colab Compute Unit (CCU) usage projected across all employees.* **Recommendation:** Keep exact verbatim quotes — Colab GPU offload keeps marginal relation-extraction API spend at `$0` inside the prepaid 2,000 monthly CCUs. Blocks company-wide rollout (`#607` step 4.1) only if changed.
  2. *Final live-proof acceptance of the Company Map project-management function page, five cited answers, and unsent interview questions.* **Recommendation:** Present five cited answers and the unsent interview questions together once `#607` step 4.1 and `#664` step 4.2 complete while keeping the interview bot off. Blocks checking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607) and [#664](https://github.com/u2giants/theoracle/issues/664).

### Already settled — do NOT re-ask
- **Integrate prepaid Google Colab compute units into The Oracle (2026-11-21):** Authorized by Albert in chat.
- **No frontier cloud API bills for bulk intake (2026-11-18, `#607` L9):** *"we can't afford frontier models."*
- **Keep exact verbatim words through the 14-day pilot (2026-11-19, `#607`):** *"ok, keep exact words through the pilot."*
- **Expanded 350-thread (`867`-passage) held-out frame verified in private sandbox (2026-11-21, `#607`):** Documented in [the `#607` gated-stop handoff](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0302Z-edge-dev-agy-intake-step23-gated-stop.md).
- **AI executes all manual steps and merges PRs itself (2026-09-28 / 2026-10-23 / 2026-10-29 standing rulings):** Never ask Albert to click notebooks, paste keys, or review PRs.

---

## 1. What this application is

**The Oracle** (`https://github.com/u2giants/theoracle`, **PUBLIC** repository, single protected branch `main`) is the Company Map and evidence-backed operational adviser for POP Creations / Spruce Line. It reads company documents, flowcharts, meeting transcripts, Teams chats, ClickUp tasks, and authorized email into a structured knowledge graph (`cmap` schema in Supabase Postgres + FalkorDB graph `company`), answers employee questions in English and Mandarin with verbatim source quotes, and interviews employees over Microsoft Teams to fill gaps ([developer guide](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [architecture](https://github.com/u2giants/theoracle/blob/main/docs/architecture.md), [service inventory](https://github.com/u2giants/theoracle/blob/main/docs/agents/09-container-and-service-inventory.md)):

- `apps/web` — Next.js 16 web app on Vercel (`https://oracle.designflow.app`, project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`).
- `apps/brain` — Python 3.12+ FastAPI API and background worker on Coolify (`oracle-brain`, `https://oracle-brain.designflow.app`, image `ghcr.io/u2giants/theoracle-brain`).
- `oracle-sandbox-private` — Dedicated isolated Coolify sandbox (`lh8tiwrst3hwij9yr3ss4vdx`, `quote-tools` + `sandbox-db`) holding `#607` private message threads, gold sets, and sealed blind-review packets.

---

## 2. What we set out to do this session, and why

Resume [#664](https://github.com/u2giants/theoracle/issues/664) from [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) at the first open STATUS row (`0.1` / `1.2` / `1.3`), auditing every gate end to end and delegating `helper-ok` mechanical work to the `flash` helper model under [model-tier-delegation.md](https://github.com/popcre/ai-devops/blob/main/templates/system/model-tier-delegation.md).

**Business & technical objective:** Spend Albert's prepaid 2,000 monthly Google Colab Compute Units (Google AI Ultra) automatically via headless CLI and pull leases so bulk `relations` backfills (`#607`'s 3,373 staged threads) and open-weight/QLoRA bake-offs run at `$0` extra API cost while keeping live web/Teams traffic 100% independent of Colab and preserving every quality and security gate (`L1`–`L10`).

---

## 3. Current state — what is true right now

- **Predecessor handoff retired under the successor rule (`AGENTS.md` §3a):** `HANDOFF.d/2026-11-22T0249Z-edge-dev-agy-colab-offload-code-landed.md` was verified on `main` (commit [`e29b8876`](https://github.com/u2giants/theoracle/commit/e29b8876a2569cced0aa9a122d9b5c0d25a22df8), merged in PR [#667](https://github.com/u2giants/theoracle/pull/667)), every remaining obligation, 1Password item ID, dead end, and coordinator record is carried forward into [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) and this handoff, all router references were updated, and the predecessor file is deleted in this session's PR (`fix/colab-offload-hardening-664` → `main`). Companion `#607` handoffs are untouched.
- **Linux host CLI provisioned in addition to Windows (`edge-dev3` + `edge-dev`):** Upstream `google-colab-cli v0.8.0` officially supports Linux and macOS (`colab readme` platform note); installed and verified `google-colab-cli v0.8.0` on Linux dev host `edge-dev3` (`colab version` → `0.8.0`) alongside `edge-dev`.
- **Five real-world execution & L1 security defects found during full gate audit of PR [#667](https://github.com/u2giants/theoracle/pull/667) — all fixed, tested against real Postgres + FalkorDB (`67/67` passed), and landing on `main` via branch `fix/colab-offload-hardening-664`:**
  1. **`__future__` wrapper `SyntaxError` fixed ([apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py#L220-L396)):** `build_remote_wrapper_source` previously indented the entire script inside `try:`, which raised `SyntaxError: from __future__ imports must occur at the beginning of the file` on all three real Colab scripts (`run_vllm_batch.py`, `drain_leases.py`, `train_relations_lora.py`). AST header splitting now keeps leading docstrings and `from __future__ import ...` at module top level; verified via `compile()` against all three production scripts in [apps/brain/tests/test_colab_preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_preflight.py#L254-L269).
  2. **Managed multi-step Colab session lifecycle added ([apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py#L463-L632)):** `colab run` sends only one `.py` file and destroys the VM before outputs can be retrieved. `run_with_colab_guard` now automatically orchestrates `colab new` → `colab install -r` → `colab upload` (including automatic AST discovery of sibling `colab/*.py` modules such as `colab/run_vllm_batch.py` imported by `drain_leases.py`) → `colab exec --timeout 0 -f` → `colab download` → `finally: colab stop` + `colab sessions` zero-session verification, with Windows drive-letter-safe `--upload LOCAL:REMOTE` and `--download REMOTE:LOCAL` parsers.
  3. **Hard L1 credential boundary & zero-argv worker token transfer ([apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py#L43-L55), [apps/brain/colab/train_relations_lora.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/train_relations_lora.py#L39-L94)):**
     - `preflight.py` hard-blocks `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `BRAIN_SHARED_TOKEN`, and `PROD_DIRECT_URL` before `colab usage` or VM provisioning, and transfers allowed worker tokens (`BRAIN_COLAB_WORKER_TOKEN`) via a `0600` temp file uploaded to `/content/.colab_guard_secrets.json` and immediately `os.remove()`d before target code runs — never via `--env KEY=SECRET` on subprocess `argv`.
     - `train_relations_lora.py` now refuses `--upload-private` and aborts if forbidden keys exist in a Colab runtime (`L1`), adds `--archive-tar` so `preflight.py --download` retrieves the trained adapter in one `.tar.gz`, and restricts `upload_adapter_to_private_bucket` (`--host-upload-only`, with tar path-traversal protection and manifest SHA-256 verification) strictly to the trusted host after VM teardown.
  4. **First-attempt truncation telemetry preserved for `#607` Step 2.3 ([apps/brain/colab/run_vllm_batch.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/run_vllm_batch.py#L639-L694)):** Implemented by `flash` helper `e8f80585` and verified by lead: records `"first_finish_reason"`, `"retried"`, and `BatchRunSummary.first_truncated_items` before `TRUNCATION_RETRY_MAX_TOKENS = 4000` overwrites `results[orig_idx]`.
  5. **Turn-key `#664` → `#607` bake-off bridge ([apps/brain/brain/colab_bakeoff.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/colab_bakeoff.py), [apps/brain/tests/test_colab_bakeoff.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_bakeoff.py)):** Converts verified `colab_packet` + `run_vllm_batch` JSONL pairs directly into `brain.intake.bakeoff.PassageAttempt` tuples (`cost_usd = 0.0` + `compute_ccu_economics` CCUs/1,000 passages) ready for `score_candidate` and `select_winner` (`#607` landed `bakeoff.py` in PR [#671](https://github.com/u2giants/theoracle/pull/671)).
- **Previously completed steps on `main` (verified green against real Postgres 16 + FalkorDB v4.20.7):**
  - Steps `0.2`, `1.1`, `3.1`, `3.2`, `3.3` (`✅ done`), plus 1Password `vibe_coding` worker tokens `naytnzqu4ldh4t7jutxbx7btzq` (sandbox) and `gulz2yow5h7tkkrdsopkh4udxq` (production).
- **Still open (`🟨` / `⬜` — all gated on one-time Google `colaboratory` OAuth):**
  - Live Colab GPU smokes (`0.1` and `1.2`), Step `1.3` (`#607` `tuning_50` open-weight bake-off in `oracle-sandbox-private`), Steps `2.1`–`2.2` (QLoRA fine-tuning on `tuning_50` + blind `350`-thread / `867`-passage qualification & 15-question `brain/eval`), Step `4.1` (private Coolify sandbox 100+ passage kill-recovery & drain proof), and Step `4.2` (production pilot drain proof & `- [ ] live proof` on `#664`).
- **Deploy status:** Production (`oracle.designflow.app`, `oracle-brain.designflow.app`) and `oracle-sandbox-private` remain completely untouched (`BRAIN_COLAB_LEASE_ENABLED=false`).

---

## 4. Everything we tried that did NOT work

1. **Non-interactive Google Colab CLI authentication across `edge-dev` and `edge-dev3` (`--auth=adc` and `--auth=oauth2`):**
   - *What we tried:* Checked `colab --auth=adc usage` and `colab --auth=oauth2 usage` (with `stdin=subprocess.DEVNULL`), inspected `colab_cli/auth.py` (`PUBLIC_SCOPES`, keyring `google-colab-cli`, `REMOTE_REDIRECT_URI = "https://sdk.cloud.google.com/applicationdefaultauthcode.html"`), checked 1Password `vibe_coding` item titles for any existing Colab user OAuth/ADC artifact, and installed `google-colab-cli v0.8.0` on Linux dev host `edge-dev3`.
   - *How & why it failed:* Neither `edge-dev` nor `edge-dev3` has `application_default_credentials.json` or a cached `google-colab-cli` keyring token, service accounts do not hold Albert's consumer Google AI Ultra 2,000-CCU entitlement (`u2giants@gmail.com`), and `gcloud`'s existing user login token lacks `https://www.googleapis.com/auth/colaboratory` (`user` credentials do not support `with_scopes` without interactive consent). Minting that token opens `accounts.google.com`, a protected authentication origin that AI agents are strictly forbidden from clicking through or bypassing.
2. **Wrapping `from __future__ import annotations` scripts inside `try:` (`preflight.py` from PR `#667`):**
   - *Why it failed:* PR `#667` tested `build_remote_wrapper_source` only on trivial 1-line strings without `from __future__ import annotations`; compiling wrapped `run_vllm_batch.py`, `drain_leases.py`, or `train_relations_lora.py` fails immediately in CPython because `__future__` statements must precede `try:`. Fixed via `_split_future_header_and_body`.
3. **Simulated Colab L1 secret test inside DB-backed pytest without `monkeypatch.context()`:**
   - *What happened:* When `test_colab_lora_leakage_guard.py` set `COLAB_RELEASE_TAG` during full DB-backed pytest, `assert_no_forbidden_colab_secrets()` immediately caught `conftest.py`'s session-scoped `DATABASE_URL` and `BRAIN_SHARED_TOKEN` (proving the L1 guard works!), and clearing `DATABASE_URL` at function scope would break `conftest.py`'s `_clean_cmap` teardown. Fixed cleanly by scoping the simulated Colab VM env inside `with monkeypatch.context() as colab_mp:`.
4. **Settled `#607` zero-shot cloud API dead ends (do NOT repeat):**
   - All four cheap cloud models, batch routes, call-shape variants (`a`–`d`), and L8 batch fallbacks missed `#607`'s `>=95%` correctness lower bound ([`#607` qualification report](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-21-pm-intake-step-2-3-qualification.md)) because `prompts/relations.md` induces `OWNS`/`PART_OF`/`PRODUCES`/`policy` overstatements on informal chat/email turns (`39.1%` narrowing rate). Expect zero-shot open-weight models in Step `1.3` to face the same conversational ontology pressure, making Step `2.1` QLoRA tuning on `tuning_50` (`77` passages) the primary path to `>=95%`.

---

## 5. Root causes and key findings

1. **Exact `google-colab-cli v0.8.0` runtime & consumption wire format (`colab_cli/consumption.py`, `colab_cli/commands/run.py`, `colab_cli/auth.py`):**
   - `colab usage` prints three lines: `Current balance: <float> compute units`, `Usage rate: <float>/hr`, `Active assignments: <int>`. Both `parse_balance_ccu` and `parse_active_assignments` in [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py#L142-L156) now parse this exact format.
   - `colab exec -f <script.py>` transmits the local file over the Jupyter WebSocket without setting `sys.argv[1:]` (unlike `colab run`). `build_remote_wrapper_source(..., exec_mode_argv=...)` sets `_colab_guard_sys.argv`, `__name__ = "__main__"`, and `sys.path.insert(0, "/content")` so `argparse` and sibling `from colab.run_vllm_batch import ...` work identically in managed multi-step sessions.
   - Upstream `colab readme` notes Windows is unsupported; run live `colab` sessions from Linux dev host `edge-dev3` (`google-colab-cli v0.8.0` already installed via `uv tool install google-colab-cli`).
2. **Why `run_vllm_batch.py` needed `first_finish_reason` before Step `1.3` / `2.2`:**
   - [apps/brain/brain/intake/bakeoff.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/bakeoff.py#L411-L413) counts `first_truncation_threads` from `PassageAttempt.first_status == "truncated"` (whole-thread first-attempt truncation ceiling `<= 1%`, `5 / 641 = 0.78%` at 0 failures across `350` threads). Without capturing `first_finish_reason` prior to the 4,000-token retry, recovered truncations would have been misreported as `first_status == "ok"`.
3. **Companion `#607` blind-review calibration state ([`#607` gated-stop handoff §3–§6](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0302Z-edge-dev-agy-intake-step23-gated-stop.md)):**
   - `tuning_50` has `77` passages (`23,714` tokens) and `3,576` adjudicated claims in `/sandbox/records/` ready for `colab.build_tuning_sft`; the full held-out frame is `350` threads = `867` passages (`initial_30` = `57`, `reserve_120` = `379`, `added_200` = `431`).
   - Automated L8 cloud blind-review calibration reached `54/72` (`75.0%` vs `83.3%` gate); Step `2.2` must also calibrate a distinct non-candidate open-weight adjudicator on Colab (`>=85%` binary / `<=10%` false-keep on `tuning_50` + unused `initial_30` controls) before scoring novel claims on the `350` held-out threads.

---

## 6. Exact next steps

1. **Complete one-time Google `colaboratory` OAuth on Linux host `edge-dev3` (prerequisite for all live GPU steps):**
   - Mint ADC with all four required scopes (`gcloud auth application-default login --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory`) and verify headlessly with `colab --auth=adc usage` and `colab --auth=adc sessions`.
   - *You'll know it worked when:* `colab --auth=adc usage` exits `0` with `stdin=/dev/null` and prints `Current balance: <N> compute units` and `Active assignments: 0`.
2. **Run live GPU smoke gates for Steps `0.1` and `1.2` from `edge-dev3`:**
   - Step `0.1`: `uv run python -m colab.preflight --smoke --gpu L4 --max-wall-minutes 5 --max-ccu 2`
   - Step `1.2`: Export a 10-passage synthetic fixture + schema via `python -m brain.colab_packet`, run `uv run python -m colab.preflight --gpu L4 --max-wall-minutes 20 --max-ccu 2 --install-requirements colab/requirements-colab.txt --upload /tmp/synth.jsonl:/content/synth.jsonl --upload /tmp/schema.json:/content/schema.json --download /content/results.jsonl:/tmp/results.jsonl --script colab/run_vllm_batch.py -- --input /content/synth.jsonl --schema /content/schema.json --output /content/results.jsonl --hf-model <allowlisted_repo> --hf-revision <40_char_sha>`, and validate with `python -m brain.colab_packet import --packet /tmp/synth.jsonl --results /tmp/results.jsonl --dry-run`.
   - *You'll know it worked when:* `nvidia-smi` prints `NVIDIA L4`, all 10 synthetic passages pass `import --dry-run` with `0` malformed JSON, `colab --auth=adc sessions` shows `0` active sessions, and Steps `0.1` and `1.2` flip to `✅ done` in [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md).
3. **Step `1.3` — Run open-weight bake-off on `#607`'s `tuning_50` (`77` passages) inside `oracle-sandbox-private`:**
   - Export only `tuning_50` via `brain.colab_packet export`, run 2–3 allowlisted 27B–32B open-weight models (`Qwen2ForCausalLM` / `Qwen3ForCausalLM` / `Gemma3ForCausalLM`) on Colab `A100` via `preflight.py`, score with `brain.colab_bakeoff.build_bakeoff_attempts_from_colab` + `brain.intake.bakeoff.score_candidate`, and commit aggregate-only metrics to `docs/verification/2026-11-colab-openweight-tuning.md`.
   - *You'll know it worked when:* Aggregate quote LB, correctness, recall, first-attempt truncation, and CCUs/1,000 passages (zero private text) are committed and determine whether a zero-shot candidate clears `>=96%` correctness / `>=99%` quote match or advances to Step `2.1` QLoRA.
4. **Steps `2.1` & `2.2` — QLoRA adapter training (if triggered), non-author adjudicator calibration, & `350`-thread qualification:**
   - Format SFT from `tuning_50` (`colab.build_tuning_sft` asserting zero overlap with all `350` held-out thread digests), train on Colab `A100` (`colab.train_relations_lora --archive-tar /content/adapter.tar.gz`, `<=25` CCUs), download via `preflight.py --download`, and upload from the trusted host via `python -m colab.train_relations_lora --host-upload-only` (never passing `SUPABASE_SERVICE_ROLE_KEY` to Colab).
   - Calibrate a distinct non-candidate open-weight adjudicator on unused controls (`>=85%` binary / `<=10%` false-keep), run the frozen finalist once across all `350` held-out threads (`867` passages), verify all four `#607` Step 2.3 bounds + the 15-question `brain/eval` check, and commit `docs/verification/2026-11-colab-relations-qualification.md`.
   - *You'll know it worked when:* `bakeoff.select_winner` returns a passing `CandidateScore` (`>=95%` correctness LB, `>=90%` recall LB, `>=98%` quote LB, `<=1%` truncation UB) and 15-question `brain/eval` mean >= reference.
5. **Step `4.1` — Private Coolify sandbox 100+ passage lease-drain & kill-recovery proof:**
   - Wire `BRAIN_COLAB_LEASE_ENABLED=true` and `op://vibe_coding/naytnzqu4ldh4t7jutxbx7btzq/BRAIN_COLAB_WORKER_TOKEN` on `oracle-sandbox-private`, prove kill-mid-lease expiry recovery + 100+ passage drain via `preflight.py --pass-env BRAIN_COLAB_API_URL --pass-env BRAIN_COLAB_WORKER_TOKEN --script colab/drain_leases.py`, and commit `docs/verification/2026-11-colab-sandbox-drain-proof.md`.
   - *You'll know it worked when:* 100+ passages finish (`read_state = 'read'`, `resolve` → `communities` green), `$0.00` cloud relations spend occurs, and `0` Colab sessions remain active.
6. **Step `4.2` — Production pilot drain proof (`- [ ] live proof` on `#664`):**
   - Redeclare `ai-task-gates start --class production` and pass `ai-task-gates check --before production`, configure `op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN` and `BRAIN_COLAB_LEASE_ENABLED=true` on production `oracle-brain`, drain the approved `#607` pilot batch, verify live `colab-vllm/...` citations on `https://oracle.designflow.app/map`, post CCU economics on `#664`, and delete this handoff in the closing PR.
   - *You'll know it worked when:* Live `/map` citations render cleanly, `0` Colab sessions remain active, and `#664` closes after live proof.

---

## 7. Constraints and gotchas in force

- **Never bypass Google OAuth / CAPTCHA / auth gates:** If `colab` lacks `colaboratory` credentials, stop and report `Blocked —`.
- **Hard L1 boundary:** Never pass `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, or `BRAIN_SHARED_TOKEN` to Colab (`preflight.py` and `train_relations_lora.py` both enforce this in code). Always pass `BRAIN_COLAB_WORKER_TOKEN` via `preflight.py --pass-env BRAIN_COLAB_WORKER_TOKEN` (uploaded `0600` file, unlinked before user code), never CLI key=value args.
- **Strict `#607` holdout seal (`L5`) & public-repo privacy (`L8`):** Never touch `initial_30`, `reserve_120`, or `added_200` (`350` held-out threads) during tuning/QLoRA; never commit message text, thread titles, raw outputs, private IPs, or LoRA weights to `u2giants/theoracle` or public Hugging Face Hub.
- **30-minute hold ceiling (`L4`):** Keep `BRAIN_COLAB_LEASE_TTL_SECONDS=900` (`<=1800`) and keep `awaits_reply(source_id)` live interview sources excluded from `/colab/lease`.

---

## 8. Access and environment

- **GitHub CLI (`gh`):** Authenticated as `u2giants`.
- **Colab CLI (`google-colab-cli v0.8.0`):** Installed on both Linux `edge-dev3` (`uv tool` binary `colab` on `PATH`, preferred host per upstream Linux/macOS support note) and Windows `edge-dev`; **blocked on one-time interactive Google OAuth** (`https://www.googleapis.com/auth/colaboratory` on `u2giants@gmail.com`).
- **Private Coolify sandbox (`oracle-sandbox-private`):** Reachable via SSH `vps2-direct` → `docker exec -i quote-tools-lh8tiwrst3hwij9yr3ss4vdx python3 -` ([`#607` handoff §8](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0302Z-edge-dev-agy-intake-step23-gated-stop.md#8-access-and-environment)).
- **1Password vault `vibe_coding` (item IDs & titles only — never print secret values):**
  - `"The Oracle — Sandbox Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `naytnzqu4ldh4t7jutxbx7btzq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - `"The Oracle — Production Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `gulz2yow5h7tkkrdsopkh4udxq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - Coolify read-only observer — item `5xjuaif5okkiqoszmh7ncrf3sy`, field `credential`.

---

## 9. Open questions and risks

- **External platform auth blocker (2026-11-21):** One-time interactive Google OAuth consent on `accounts.google.com` granting `https://www.googleapis.com/auth/colaboratory` for `u2giants@gmail.com` on `edge-dev3` blocks Steps `0.1` (live smoke), `1.2` (live smoke), `1.3`, `2.1`–`2.2`, and `4.1`–`4.2`.
- **Conversational ontology risk on Step `1.3` (2026-11-21):** Zero-shot models over-assign `OWNS`/`PART_OF`/`PRODUCES`/`policy` on chat/email threads (`39.1%` narrowing rate in `#607`); Step `2.1` QLoRA on `tuning_50` + Step `2.2` non-candidate Colab adjudicator calibration (`#607` §6.2) address both extraction precision and novel-claim blind review.
- **Owner business decisions:** Consolidated in §0 above.

---

## Part (b) — Coordinator record (sub-agent delegation)

- **This session (`8feab216`) — Step 1.2 First-Attempt Truncation Helper (`flash` subagent `e8f80585`):**
  - *Asked to do:* Add `first_truncated_items` to `BatchRunSummary` and emit `"first_finish_reason"` + `"retried"` on every JSONL output line in `apps/brain/colab/run_vllm_batch.py`, with unit tests in `apps/brain/tests/test_colab_vllm_runner.py`.
  - *Actually did & found:* Implemented exact changes across those two files only (+14/-2 and +38/-1 lines), passed `uv run ruff check` and offline `pytest` (`9 passed`), and noted `conftest.py`'s `DATABASE_URL` requirement for full-suite runs.
  - *Verification & branch state:* Verified by lead against real Postgres 16 + FalkorDB (`67 passed` across all Colab/bakeoff/schema/prompt suites, `ruff` clean); landing in this session's PR (`fix/colab-offload-hardening-664` → `main`), worktree removed after merge; helper deliberately did not run `git`, `gh`, or touch `apps/brain/brain/*`.
- **Carried forward from PR [#667](https://github.com/u2giants/theoracle/pull/667) (`6aba6e03`):** Step `0.2` (`flash` `b438dd36`), Step `1.2` (`flash` `c8366766`), and Step `3.3` (`flash` `fb89b826`) — all merged on `main` in [`e29b8876`](https://github.com/u2giants/theoracle/commit/e29b8876a2569cced0aa9a122d9b5c0d25a22df8), worktrees closed.

---

## Self-audit (`handoff-writer` standard)

1. *Comprehensive enough for a brand-new developer with no project/session context to pick up without skipping a beat?* **Yes** — §§1–3 define The Oracle, its public/private boundaries, runtime services, exact landed files on `main`, and all five preflight/L1/bakeoff fixes; §6 gives ordered commands with explicit pass gates.
2. *Detailed enough to continue as well as I could right now?* **Yes** — §§4–5 preserve the `google-colab-cli v0.8.0` Linux support requirement (`edge-dev3`), exact `colab usage` output format, `colab exec` `sys.argv` / `/content/colab` module staging behavior, `__future__` wrapper AST split, L1 host-only LoRA upload path, and `#607`'s `350`-thread (`867`-passage) + adjudicator-calibration state.
3. *Every relevant detail included (background, goals, current state, failures, decisions, constraints, risks, next actions, verification)?* **Yes** — covered across §§0–9 and Part (b), with portable GitHub URLs throughout (zero machine-local paths) and vault/item IDs only for secrets.
4. *Line-by-line Section 0 sweep: if Albert read ONLY §0, would he see every business decision across §§1–9 and Part (b), and zero technical approvals?* **Yes** — walked §§1–9 and Part (b) line by line: the Google `colaboratory` OAuth consent in §§3, 4, 6, 8, 9 is a platform authentication blocker (`Blocked —`, excluded from §0 asks per 2026-09-28 ruling), while companion `#607`'s cloud-vs-`#664` rollout choice and both post-pilot acceptance checkpoints appear in §0 with recommendations and settled-ruling dates.

## Next-session prompt

```text
Resume #664 from main of https://github.com/u2giants/theoracle.
Read AGENTS.md first, then https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md (STATUS first), then https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0346Z-edge-dev-agy-colab-offload-hardened.md, and companion https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0302Z-edge-dev-agy-intake-step23-gated-stop.md.
Verify `colab --auth=adc usage` on Linux host `edge-dev3` first; once one-time Google `colaboratory` OAuth is active, execute Steps 0.1/1.2 live GPU smokes, Step 1.3 (`tuning_50` open-weight bake-off in `oracle-sandbox-private` scored via `brain.colab_bakeoff` + `brain.intake.bakeoff`), Steps 2.1–2.2 (`tuning_50` QLoRA + `350`-thread qualification + 15-question `brain/eval`), and Steps 4.1–4.2.
```
