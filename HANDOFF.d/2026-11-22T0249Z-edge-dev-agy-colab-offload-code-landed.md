---
summary: "Resume #664 after all Colab offload, vLLM, QLoRA, and pull-lease code/SQL/tests landed; blocked on one-time Google Colab OAuth."
kind: handoff
status: open
read-when: resuming Google Colab GPU batch offload (#664) for live GPU smokes, #607 sandbox bake-off, or lease-drain proofs
issue: 664
owner: feat/colab-gpu-offload-664
---

# Handoff — Google Colab GPU batch offload code & tests landed; live GPU steps blocked on OAuth (#664)

Registered plan: [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md)
Tracking issue: https://github.com/u2giants/theoracle/issues/664

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None blocking the next technical steps — zero business decisions are waiting on Albert right now.**

*(Note per owner ruling 2026-09-28: the one-time Google `colaboratory` OAuth grant on `accounts.google.com` that blocks live GPU execution in Steps `0.1`, `1.2`, `1.3`, `2.1`–`2.2`, and `4.1`–`4.2` is a platform authentication boundary reported under `Blocked —`, NOT a business-meaning approval.)*

When `#664` and `#607` later reach the post-pilot milestone, present the downstream `#607` business checkpoints together in **one** plain-English message before expanding beyond the two project managers:

- **Not blocking now — downstream `#607` post-pilot business checkpoints (tracked on https://github.com/u2giants/theoracle/issues/607):**
  1. *Whether to keep the exact-verbatim-quote rule after seeing measured 14-day pilot cost and monthly Colab Compute Unit (CCU) usage projected across all employees.* **Recommendation:** Keep exact verbatim quotes — Colab GPU offload drops marginal relation-extraction API cost to `$0` within the prepaid 2,000 monthly CCUs. Blocks only post-pilot company-wide expansion (`#607` Step 4.1).
  2. *Final live-proof acceptance of the Company Map project-management function page, five cited answers, and unsent interview questions.* **Recommendation:** Present five cited answers and the unsent question list together once `#607` Step 4.1 and `#664` Step 4.2 finish. Blocks closing `- [ ] live proof` on `#607` and `#664`.

### Already settled — do NOT re-ask
- **Integrate prepaid Google Colab compute units into The Oracle (2026-11-21):** Authorized by Albert in chat.
- **No frontier cloud API bills for bulk intake (2026-11-18, `#607` L9):** *"we can't afford frontier models."*
- **Keep exact verbatim quotes through the pilot (2026-11-19, `#607`):** *"ok, keep exact words through the pilot."*
- **Expanded 350-thread held-out frame verified in private sandbox (2026-11-21, `#607`):** Verified in [the `#607` expanded sample handoff](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0202Z-edge-dev3-codex-intake-expanded-sample.md), removing the earlier 150-thread truncation sample-size shortfall.
- **Never ask Albert to click, run commands, open notebooks, or approve technical steps (2026-09-28 / 2026-10-29 standing rulings):** AI sessions run Colab headlessly via CLI and merge PRs themselves.

---

## 1. What this application is

**The Oracle** is the Company Map and evidence-backed operational adviser for POP Creations / Spruce Line. It ingests company documents, diagrams, meeting transcripts, Teams chats, ClickUp tasks, and authorized email into a structured knowledge graph (`cmap` schema in Supabase Postgres + FalkorDB graph `company`), answers employee questions in English and Mandarin citing exact verbatim quotes, and interviews employees over Microsoft Teams to close knowledge gaps.

- **Repository:** https://github.com/u2giants/theoracle (**PUBLIC** — single protected branch `main`).
- **Web app (`apps/web`):** Next.js 16 on Vercel (`https://oracle.designflow.app`), documented in [README.md](https://github.com/u2giants/theoracle/blob/main/README.md) and [docs/architecture.md](https://github.com/u2giants/theoracle/blob/main/docs/architecture.md).
- **Brain service (`apps/brain`):** Python 3.12+ FastAPI API and background worker on Coolify (`oracle-brain`, `https://oracle-brain.designflow.app`, image `ghcr.io/u2giants/theoracle-brain`).
- **Private Coolify sandbox:** Isolated Coolify brain + Postgres environment (`oracle-sandbox-private` / `quote-tools`) holding `#607` private message-intake threads, gold annotations, and benchmark packets ([sandbox custody details](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0202Z-edge-dev3-codex-intake-expanded-sample.md#8-evidence-access-and-ownership)).

---

## 2. What we set out to do this session, and why

Albert asked to clear https://github.com/u2giants/theoracle/issues/664 through to completion, executing [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) from Step `0.1`.

**Business & technical objective:** Turn Albert's prepaid 2,000 monthly Google Colab Compute Units (Google AI Ultra) into an automated, headless GPU batch worker and QLoRA fine-tuning pipeline for `apps/brain` so bulk message/transcript backfills (`#607`'s 3,373 staged threads) and open-weight bake-offs run at `$0` incremental API cost while keeping live web/Teams traffic 100% independent of Colab.

---

## 3. Current state — what is true right now

- **Predecessor handoff retired under the successor rule:** `HANDOFF.d/2026-11-22T0157Z-edge-dev-agy-colab-gpu-offload-plan.md` was verified on `main` (commit [`aa1beef3`](https://github.com/u2giants/theoracle/commit/aa1beef3), merged in [`f9aa91df`](https://github.com/u2giants/theoracle/commit/f9aa91df) / PR [#666](https://github.com/u2giants/theoracle/pull/666)), all remaining obligations and dead ends are carried forward into [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) and this handoff, and the predecessor file is deleted in this session's PR (`feat/colab-gpu-offload-664` → `main`).
- **Workstation CLI installed (`edge-dev`):** `google-colab-cli v0.8.0` (`colab` executable) installed via `uv tool install google-colab-cli`.
- **1Password secrets provisioned & hash-verified in vault `vibe_coding`:**
  - Sandbox token: `"The Oracle — Sandbox Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` (item `naytnzqu4ldh4t7jutxbx7btzq`, reference `op://vibe_coding/naytnzqu4ldh4t7jutxbx7btzq/BRAIN_COLAB_WORKER_TOKEN`, SHA-256 prefix `4d4ae893c105bf1e`).
  - Production token: `"The Oracle — Production Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` (item `gulz2yow5h7tkkrdsopkh4udxq`, reference `op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN`, SHA-256 prefix `fed094b69ac780bb`).
- **All repository code, SQL schema, API endpoints, worker CLIs, docs, and all 8 pytest suites (50 new tests + full existing `apps/brain` suite) implemented and landing on `main` via branch `feat/colab-gpu-offload-664`:**
  - **Step 0.1 (`🟨 code landed, awaiting live proof`):** [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py), [apps/brain/colab/requirements-colab.txt](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/requirements-colab.txt), and [apps/brain/tests/test_colab_preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_preflight.py) (7/7 unit & §9a tests green; live L4 `nvidia-smi` smoke awaits one-time Google `colaboratory` OAuth).
  - **Step 0.2 (`✅ done`):** [apps/brain/brain/config.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/config.py), [apps/brain/deploy/compose.coolify.yaml](https://github.com/u2giants/theoracle/blob/main/apps/brain/deploy/compose.coolify.yaml), [docs/configuration.md](https://github.com/u2giants/theoracle/blob/main/docs/configuration.md), [docs/agents/12-credentials-and-environment.md](https://github.com/u2giants/theoracle/blob/main/docs/agents/12-credentials-and-environment.md), [.env.example](https://github.com/u2giants/theoracle/blob/main/.env.example), and [apps/brain/tests/test_colab_config.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_config.py) (12/12 tests green, including `pyproject.toml` GPU-dependency guard).
  - **Step 1.1 (`✅ done`):** [apps/brain/brain/colab_packet.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/colab_packet.py) and [apps/brain/tests/test_colab_packet.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_packet.py) (4/4 round-trip parity & §9a tests green against real Postgres).
  - **Step 1.2 (`🟨 code landed, awaiting live proof`):** [apps/brain/colab/run_vllm_batch.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/run_vllm_batch.py) and [apps/brain/tests/test_colab_vllm_runner.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_vllm_runner.py) (9/9 offline unit & §9a tests green; 10-passage synthetic Colab smoke awaits one-time Google `colaboratory` OAuth).
  - **Step 2.1 (`🟨 code landed, awaiting live proof`):** [apps/brain/colab/build_tuning_sft.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/build_tuning_sft.py), [apps/brain/colab/train_relations_lora.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/train_relations_lora.py), and [apps/brain/tests/test_colab_lora_leakage_guard.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_lora_leakage_guard.py) (3/3 holdout-leakage & trainer safety tests green; live QLoRA run conditional on Step 1.3).
  - **Step 3.1 (`✅ done`):** [apps/brain/brain/sql/039_colab_leases.sql](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/039_colab_leases.sql), [apps/brain/brain/extract/relations.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py), [apps/brain/brain/chain.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/chain.py), [apps/brain/tests/test_schema.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_schema.py), and [apps/brain/tests/test_colab_leases_db.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_leases_db.py) (4/4 DB constraint, idempotence, `FOR UPDATE SKIP LOCKED`, and `awaits_reply` exclusion tests green).
  - **Step 3.2 (`✅ done`):** [apps/brain/brain/api/deps.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/deps.py), [apps/brain/brain/api/colab.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/colab.py), [apps/brain/brain/main.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/main.py), and [apps/brain/tests/test_colab_api.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_api.py) (7/7 API & §9a adversarial tests green).
  - **Step 3.3 (`✅ done`):** [apps/brain/colab/drain_leases.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/drain_leases.py) and [apps/brain/tests/test_colab_drain_worker.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_colab_drain_worker.py) (4/4 multi-batch FastAPI TestClient drain, backoff, teardown, and token-redaction tests green).
- **Still open (`⬜ open` / live-Colab-gated):**
  - Live Colab GPU smokes (`0.1` and `1.2`), Step `1.3` (`#607` 50-tuning-thread open-weight bake-off in private sandbox), Step `2.1`/`2.2` (conditional QLoRA run + blind held-out `#607` qualification & 15-question eval), Step `4.1` (private Coolify sandbox 100+ passage kill-recovery & drain proof), and Step `4.2` (production pilot drain proof & `- [ ] live proof` on `#664`).
- **Production & sandbox deployment state:** Production (`oracle.designflow.app` and `oracle-brain.designflow.app`) and the private Coolify sandbox remain untouched (`BRAIN_COLAB_LEASE_ENABLED` defaults to `false`). Merging to `main` publishes `ghcr.io/u2giants/theoracle-brain:<sha>` via `brain-image.yml` ready for Step 4.1 sandbox deploy.

---

## 4. Everything we tried that did NOT work

1. **Blocked at live Colab CLI authentication (`colab --auth=adc usage` and `colab --auth=oauth2 sessions`):**
   - *What we tried:* Installed `google-colab-cli v0.8.0` on `edge-dev`, tested `colab --auth=adc whoami` / `colab --auth=adc usage`, checked `edge-dev3` for cached ADC/Colab credentials, and inspected the active `gcloud` CLI token scopes for `u2giants@gmail.com` via `https://oauth2.googleapis.com/tokeninfo`.
   - *How & why it failed:* Neither `edge-dev` nor `edge-dev3` has `application_default_credentials.json` (`DefaultCredentialsError`) or a cached `colab-cli` keyring token, and the existing `gcloud` CLI login token carries `cloud-platform`, `compute`, `appengine.admin`, `sqlservice.login`, and `userinfo.email` — **missing** `https://www.googleapis.com/auth/colaboratory`. Running `colab` with `--auth=oauth2` or `gcloud auth application-default login --scopes=...,https://www.googleapis.com/auth/colaboratory` opens a protected `accounts.google.com` OAuth consent screen that AI agents are strictly forbidden from clicking through or bypassing under platform security guidelines.
   - *How we handled it:* Built `probe_account_balance` in [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) with `stdin=subprocess.DEVNULL` so headless runs fail fast with `ColabAuthError` (exit code `3`) instead of hanging on stdin, completed and verified 100% of the unblocked repository code/SQL/API/tests across Phases 0–3, and recorded the exact one-time OAuth blocker.
2. **Pydantic v2 `ValidationError.errors()` JSON serialization quirk on `POST /colab/submit`:**
   - *What happened:* When `SubmitRequest.model_validate_json(raw_body)` raised a custom `@field_validator` `ValueError` on invalid `model_tag`, passing `exc.errors(include_url=False)` to `HTTPException(status_code=422, detail=...)` caused Starlette's `JSONResponse` to raise `TypeError: Object of type ValueError is not JSON serializable` because `ctx['error']` holds the raw `ValueError` instance.
   - *Fix:* Passed `exc.errors(include_url=False, include_context=False)` in [apps/brain/brain/api/colab.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/colab.py).
3. **Prior `#607` cloud API failures & architectural dead ends (carried forward from predecessor):**
   - All four cheap cloud routes + fallback missed `#607` Step 2.3's `>=95%` correctness lower bound ([verification report](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-20-pm-intake-relations.md), [Luna batch receipt](https://github.com/u2giants/theoracle/issues/607#issuecomment-7071834212)). Never re-run those settled cloud jobs, never expose Colab via inbound `ngrok`/`cloudflared` tunnels, never put `DATABASE_URL` or `OPENROUTER_API_KEY` on Colab, and never add GPU packages to [apps/brain/pyproject.toml](https://github.com/u2giants/theoracle/blob/main/apps/brain/pyproject.toml).

---

## 5. Root causes and key findings

1. **`google-colab-cli v0.8.0` real CLI contract (differs slightly from pre-install assumptions):**
   - Subcommands are `colab usage`, `colab sessions`, `colab run [-s <name>] [--gpu L4|A100] [--timeout 0] [--env KEY=VAL] <script.py> [args...]`, and `colab stop -s <name>` (there is no `colab runtime` subcommand).
   - Global flags `--auth={adc,oauth2}` and `--config <sessions.json>` MUST precede the subcommand (`colab --auth=adc --config <tmp> run ...`). Note that `--help` defaults to `oauth2`, whereas headless automation should pass `--auth=adc` once ADC is minted with `openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory`.
   - Unrecognized `--gpu` strings silently fall back to `A100` in `google-colab-cli`, so [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) explicitly allowlists `CPU`, `T4`, `L4`, `G4`, `A100`, `H100`.
2. **Packaging separation between `brain` and `colab`:**
   - [apps/brain/Dockerfile](https://github.com/u2giants/theoracle/blob/main/apps/brain/Dockerfile) copies only `brain/` into `ghcr.io/u2giants/theoracle-brain`, keeping `apps/brain/colab/` out of production container images while `pythonpath = ["."]` in [apps/brain/pyproject.toml](https://github.com/u2giants/theoracle/blob/main/apps/brain/pyproject.toml) makes `colab.*` importable during `uv run pytest` in `brain-ci.yml`.
3. **Hourly `ensure_chain` interaction with `colab_offload` ([apps/brain/brain/chain.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/chain.py)):**
   - When `BRAIN_COLAB_LEASE_ENABLED=true`, `handle_relations` defers pending chunks of `colab_offload=true` sources (leaving `read_state = 'extracting'` until `POST /colab/submit` finishes the last chunk). `_heal_sources` in `chain.py` now skips re-queuing `classify_extract` while `BRAIN_COLAB_LEASE_ENABLED=true` and `relations` already deferred, and automatically heals/processes those sources on the cloud worker if `BRAIN_COLAB_LEASE_ENABLED` is flipped back to `false` (instant rollback).
4. **Concurrent chunk locking without `UniqueViolation` ([apps/brain/brain/api/colab.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/colab.py)):**
   - `claim_lease_batch` locks candidate rows directly on `cmap.chunk` with `FOR UPDATE OF c SKIP LOCKED` after sweeping expired leases (`expires_at <= now()`), ensuring concurrent GPU workers never collide on `colab_lease_one_active_chunk_idx`.

---

## 6. Exact next steps

1. **Clear the one-time Google Colab OAuth blocker on `edge-dev` (prerequisite for all live GPU steps):**
   - Once one-time interactive Google OAuth with the `colaboratory` scope is completed (`gcloud auth application-default login --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory` or `colab --auth=oauth2 sessions`), verify headless auth works with `colab --auth=adc usage` and `colab --auth=adc sessions`.
   - *You'll know it worked when:* `colab --auth=adc usage` exits `0` with no browser prompt and reports the Google AI Ultra CCU balance.
2. **Complete live GPU smoke gates for Steps `0.1` and `1.2`:**
   - Run `uv run python -m colab.preflight --smoke --gpu L4 --max-wall-minutes 5 --max-ccu 2` from `apps/brain`.
   - Run a 10-passage synthetic fixture through `colab.preflight --script colab/run_vllm_batch.py --gpu L4 --max-wall-minutes 15 --max-ccu 2` with a pinned 40-char Hugging Face commit SHA (`--hf-model` + `--hf-revision`).
   - *You'll know it worked when:* `nvidia-smi` prints the GPU name, all 10 synthetic passages return schema-valid JSON accepted by `python -m brain.colab_packet import --dry-run`, `colab --auth=adc sessions` shows **0 active sessions**, and Steps `0.1` and `1.2` flip from `🟨` to `✅ done` in [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md).
3. **Step `1.3` — Run open-weight bake-off on `#607`'s 50 tuning threads in the private Coolify sandbox:**
   - Export only the 50 `#607` tuning threads inside `oracle-sandbox-private` via `python -m brain.colab_packet export`, run 2–3 allowlisted open-weight models on Colab `A100`, score with `import --dry-run` + `#607` tuning rubric, and commit aggregate-only metrics to `docs/verification/2026-11-colab-openweight-tuning.md`.
   - *You'll know it worked when:* Aggregate tuning correctness, quote match, truncation rate, and CCUs/1,000 passages are committed (zero private text) and decide whether to advance zero-shot to Step `2.2` or run Step `2.1` QLoRA fine-tuning.
4. **Steps `2.1` (if triggered) & `2.2` — QLoRA fine-tuning & blind 350-thread `#607` qualification:**
   - If zero-shot tuning misses `>=96%` correctness / `>=99%` quote match, run `colab.build_tuning_sft` + `colab.train_relations_lora --upload-private` (`<=25` CCUs on `A100`).
   - Coordinate with `#607`'s calibrated protected blind-review surface ([`#607` handoff §6](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0202Z-edge-dev3-codex-intake-expanded-sample.md#6-ordered-continuation-and-verification)) over the frozen 350-thread held-out frame + 15-question `brain/eval` check, committing aggregate results to `docs/verification/2026-11-colab-relations-qualification.md`.
   - *You'll know it worked when:* Correctness `>=95%`, recall `>=90%`, quote match `>=98%`, truncation `<=1%` (one-sided 95% confidence bounds), and 15-question eval >= reference all pass.
5. **Step `4.1` — Private Coolify sandbox end-to-end lease-drain & kill-recovery proof:**
   - Configure `BRAIN_COLAB_LEASE_ENABLED=true` and `op://vibe_coding/naytnzqu4ldh4t7jutxbx7btzq/BRAIN_COLAB_WORKER_TOKEN` on `oracle-sandbox-private`, verify kill-mid-lease expiry recovery + 100+ passage drain via `colab.drain_leases`, and commit `docs/verification/2026-11-colab-sandbox-drain-proof.md`.
   - *You'll know it worked when:* All 100+ passages drain to `read_state = 'read'`, `resolve` → `communities` completes, `$0.00` cloud relations spend occurs, and `0` Colab sessions remain active.
6. **Step `4.2` — Production pilot backfill drain proof (`- [ ] live proof` on `#664`):**
   - Redeclare `ai-task-gates start --class production`, wire `op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN` and `BRAIN_COLAB_LEASE_ENABLED=true` on production `oracle-brain`, drain the approved `#607` pilot window, verify citations on `https://oracle.designflow.app/map`, check off `- [ ] live proof` on `#664`, and delete this handoff file in the closing PR.
   - *You'll know it worked when:* Live citations with `colab-vllm/...` provenance render on `/map`, CCU economics are posted on `#664`, and `#664` closes cleanly.

---

## 7. Constraints and gotchas in force

- **Worktree & task-gate discipline:** Always work in an isolated worktree from `origin/main` and run `ai-task-gates start --class code` (or `--class production` before Step 4.2).
- **Never bypass Google OAuth / CAPTCHA / auth gates:** If `colab` CLI credentials expire or lack `colaboratory` scope, stop and report `Blocked —` rather than probing undocumented browser/cookie paths.
- **Public repo privacy boundary (`L8`):** Never commit message text, thread titles, raw completions, private hosts/IPs, or LoRA weights to `u2giants/theoracle` or public Hugging Face Hub. Run `ai-doc-safety --changed origin/main` and `ai-doc-health --repo .` before every PR/merge.
- **30-minute hold ceiling (`L4`):** Keep `BRAIN_COLAB_LEASE_TTL_SECONDS` at `900` (`<=1800` enforced in Pydantic and Postgres `CHECK`), and never lease `awaits_reply(source_id)` live interview sources to Colab.
- **Do not delete `#607` handoffs** (`HANDOFF.d/2026-11-22T0202Z-edge-dev3-codex-intake-expanded-sample.md`, etc.) — `#607` is an active sibling workstream.

---

## 8. Access and environment

- **GitHub CLI (`gh`):** Authenticated as `u2giants` (`repo`, `workflow` scopes).
- **Colab CLI (`colab`):** Installed on `edge-dev` (`google-colab-cli v0.8.0`); **blocked on one-time interactive Google OAuth** for scope `https://www.googleapis.com/auth/colaboratory` on `u2giants@gmail.com`.
- **1Password vault `vibe_coding` (titles & item IDs only — never print secret values):**
  - `"The Oracle — Sandbox Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `naytnzqu4ldh4t7jutxbx7btzq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - `"The Oracle — Production Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `gulz2yow5h7tkkrdsopkh4udxq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - Existing Oracle & `hetz` items listed in [docs/agents/12-credentials-and-environment.md](https://github.com/u2giants/theoracle/blob/main/docs/agents/12-credentials-and-environment.md).
- **Test databases for `apps/brain`:** `edge-dev` has no local Docker daemon; spin up ephemeral `pgvector/pgvector:pg16` + `falkordb/falkordb:v4.20.7` containers on `edge-dev3` on distinct high ports per [docs/development.md](https://github.com/u2giants/theoracle/blob/main/docs/development.md) and remove them after test runs.

---

## 9. Open questions and risks

- **External blocker (`Step 0.1` / `1.2` / `1.3`+):** One-time Google OAuth consent on `accounts.google.com` for `https://www.googleapis.com/auth/colaboratory` (`u2giants@gmail.com`) must be completed once on the workstation before `colab` CLI can allocate L4/A100 runtimes headlessly.
- **Sibling dependency (`Step 2.2`):** Full blind semantic qualification on `#607`'s 350 held-out threads shares `#607`'s calibrated protected blind-review dependency documented in [`#607` handoff §4 & §6](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0202Z-edge-dev3-codex-intake-expanded-sample.md#4-failed-attempts-and-recoveries).

---

## Coordinator record (model-tier delegation)

- **Step 0.2 Config Helper (`flash` subagent `b438dd36`):** Implemented `BRAIN_COLAB_*` settings and `@field_validator` bounds in `apps/brain/brain/config.py`, `compose.coolify.yaml`, `.env.example`, `docs/configuration.md`, `docs/agents/12-credentials-and-environment.md`, and `apps/brain/tests/test_colab_config.py`. Verified by lead (`12 passed`, `ruff` clean); shared worktree now merged, zero commits/pushes made by helper.
- **Step 1.2 vLLM Runner Helper (`flash` subagent `c8366766`):** Implemented `apps/brain/colab/run_vllm_batch.py` (zero top-level GPU imports, 40-char SHA & L7 architecture allowlist, guided JSON schema, 64-item checkpoint resume, 4000-token length retry, `unassign` teardown) and `apps/brain/tests/test_colab_vllm_runner.py`. Verified by lead (`9 passed`, `ruff` clean); did not run live Colab or git commands.
- **Step 3.3 Lease Drain Helper (`flash` subagent `fb89b826`):** Implemented `apps/brain/colab/drain_leases.py` (env/stdin-only token intake, `TokenRedactingFilter`, multi-batch `/colab/lease` → vLLM → `/colab/submit` loop, 3-error `<120s` retry cap, `finally` `unassign`) and `apps/brain/tests/test_colab_drain_worker.py`. Verified by lead (`4 passed` against real FastAPI app + Postgres, `ruff` clean); did not touch `apps/brain/brain/*` or git.

---

## Self-audit (handoff-writer standard)

1. *Comprehensive enough for a brand-new developer with zero project/session context to pick up without skipping a beat?* **Yes** — §1–§3 define The Oracle, its repos/containers, exact landed modules/tests on `main`, and provisioned 1Password item IDs; §6 gives ordered commands and verification gates.
2. *Detailed enough to continue as effectively as I could right now?* **Yes** — §4 and §5 record the exact `google-colab-cli v0.8.0` subcommand/flag behavior, missing `colaboratory` token scope diagnosis, Pydantic v2 `include_context=False` fix, `chain.py` rollback interaction, and `FOR UPDATE OF c SKIP LOCKED` locking design.
3. *Every relevant detail included (background, goals, current state, failures, decisions, constraints, risks, next actions, verification)?* **Yes** — covered across §0–§9 plus the Coordinator record, with portable GitHub URLs throughout and zero machine-local paths or secret values.
4. *Line-by-line Section 0 sweep: if Albert read ONLY §0, would he see every business decision across §1–§9 and the Coordinator record, with zero technical approvals?* **Yes** — walked §1–§9 and the Coordinator record line by line: the Google OAuth gate in §3/§4/§6/§8/§9 is a platform auth blocker (explicitly excluded from technical approvals per 2026-09-28 ruling), while the two downstream `#607` post-pilot business decisions (exact-quote rule after pilot cost projection and final Company Map acceptance) appear in §0 with explicit recommendations and settled-ruling dates.
