---
summary: "Google Colab GPU offload (#664) Steps 0.1–4.1 complete and Colab ADC vaulted in 1Password; Step 4.2 awaits #607 Step 3.1 / approved transcript batch."
kind: handoff
status: BLOCKED
read-when: resuming Google Colab GPU batch offload (#664) for Step 4.2 production backfill drain once an approved colab_offload=true batch and production gate are ready
issue: 664
owner: feat/colab-e2e-execution-664
---

# Handoff — Google Colab GPU offload Steps `0.1`–`4.1` complete & Colab ADC vaulted in 1Password; Step `4.2` gated on `#607` pilot / approved backfill (#664)

Registered plan: [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md)
Tracking issue: https://github.com/u2giants/theoracle/issues/664

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None blocking right now** — companion `#607` Step 2.3 qualified three-pass `GPT-6 Luna` (`relations_messages` seat, [`2712f979`](https://github.com/u2giants/theoracle/commit/2712f979)) and is advancing through `#607` Steps `2.4 → 3.1` ([`#607` handoff](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0525Z-edge-dev-agy-intake-step24-batch-and-cache.md)).

**Downstream post-pilot business checkpoints (not blocking now; present together in one plain-English message once `#607` Step 3.1 14-day pilot numbers exist):**
1. *Whether to keep the exact-verbatim-quote rule after seeing measured 14-day pilot cost and monthly Colab Compute Unit (CCU) usage projected across all employees.* **Recommendation:** Keep exact verbatim quotes (`L1`). Blocks `#607` Step 4.1 company-wide expansion only if changed.
2. *Final live-proof review of the Company Map project-management page, five cited answers, and unsent interview questions.* **Recommendation:** Present five cited answers and the unsent interview questions together once `#607` Step 4.1 and `#664` Step 4.2 complete while keeping the interview bot off. Blocks checking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607) and [#664](https://github.com/u2giants/theoracle/issues/664).

### Already settled — do NOT re-ask
- **Integrate prepaid Google Colab compute units into The Oracle (2026-11-21 / 2026-11-22):** Authorized by Albert in chat; one-time Google `colaboratory` OAuth completed by Albert and vaulted permanently in 1Password `vibe_coding` item `whgwmjd6wvcq4rttpo6mx4367i` (`3,027.44` CCUs verified available; `Active assignments: 0`).
- **No frontier cloud API bills for bulk intake (2026-11-18, `#607` L9):** *"we can't afford frontier models."*
- **Keep exact verbatim words through the 14-day pilot (2026-11-19, `#607`):** *"ok, keep exact words through the pilot."*
- **AI executes all manual steps and merges PRs itself (2026-09-28 / 2026-10-23 / 2026-10-29 standing rulings):** Never ask Albert to click notebooks, paste keys, or review PRs.

---

## 1. What this application is

**The Oracle** (`https://github.com/u2giants/theoracle`, **PUBLIC** repository, single protected branch `main`) is the Company Map and evidence-backed operational adviser for POP Creations / Spruce Line. It ingests company documents, flowcharts, meeting transcripts, Teams chats, ClickUp tasks, and authorized email into a structured knowledge graph (`cmap` schema in Supabase Postgres + FalkorDB graph `company`), answers employee questions in English and Mandarin citing verbatim source quotes, and interviews employees over Microsoft Teams to fill gaps ([developer guide](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [architecture](https://github.com/u2giants/theoracle/blob/main/docs/architecture.md), [service inventory](https://github.com/u2giants/theoracle/blob/main/docs/agents/09-container-and-service-inventory.md)):

- `apps/web` — Next.js 16 web app on Vercel (`https://oracle.designflow.app`, project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`).
- `apps/brain` — Python 3.12+ FastAPI API and background worker on Coolify (`oracle-brain`, application UUID `uge6pfm4qapktivto4981mtg`, `https://oracle-brain.designflow.app`, image `ghcr.io/u2giants/theoracle-brain`).
- `oracle-sandbox-private` — Dedicated isolated Coolify sandbox (`lh8tiwrst3hwij9yr3ss4vdx`, `quote-tools` + `sandbox-db`) holding `#607` private message threads, gold sets, QLoRA adapters, and sealed blind-review receipts.

---

## 2. What we set out to do this session, and why

Complete the one-time Google `colaboratory` OAuth grant requested by Albert, persist the resulting headless Application Default Credentials into 1Password `vibe_coding` and across both Windows (`edge-dev`) and Linux (`edge-dev3`) workstations so future sessions never prompt Albert again, re-verify live Colab `L4` GPU provisioning and teardown, and inspect Step `4.2` readiness on [#664](https://github.com/u2giants/theoracle/issues/664) ([plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md)).

---

## 3. Current state — what is true right now

- **Predecessor handoff retired under the successor rule (`AGENTS.md` §3a):** `HANDOFF.d/2026-11-22T0637Z-edge-dev-agy-colab-offload-qualified.md` was verified on `main` (commit [`84690000`](https://github.com/u2giants/theoracle/commit/8469000075b39a052b9706bebd5370e440e3566f), merged in PR [#676](https://github.com/u2giants/theoracle/pull/676)), every open obligation, 1Password item ID, dead end, and coordinator record is carried forward into [plan_colab_gpu_offload.md](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) and this handoff, all router links were updated, and the predecessor file is deleted in this PR (`feat/colab-e2e-execution-664` → `main`).
- **Google Colab ADC vaulted in 1Password `vibe_coding` & verified on both `edge-dev` and `edge-dev3` (2026-11-22 8:49 AM EST):**
  - Stored `"Google Colab CLI Application Default Credentials - u2giants@gmail.com (AI Ultra CCUs, theoracle)"` in vault `vibe_coding` (item `whgwmjd6wvcq4rttpo6mx4367i`, concealed field `ADC_JSON`, normalized SHA-256 prefix `f0e756635d5db2b1`, quota project disabled).
  - Verified headless `colab --auth=adc usage` + `colab --auth=adc sessions` on both `edge-dev` and Linux `edge-dev3`, plus a fresh guarded `NVIDIA L4, 23034 MiB` smoke via [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) (`Current balance: 3027.44 compute units`, `Usage rate: 0.00/hr`, `Active assignments: 0`).
- **All Steps `0.1`–`4.1` completed and merged on `main` ([`84690000`](https://github.com/u2giants/theoracle/commit/8469000075b39a052b9706bebd5370e440e3566f)):**
  - **Steps `0.1`, `0.2`, `1.1`, `1.2`:** Guarded CLI preflight (`preflight.py`), config (`config.py`), deterministic packet exporter/importer (`colab_packet.py`), and offline guided-JSON vLLM runner (`run_vllm_batch.py`) all `✅ done` (`667+` brain tests green).
  - **Step `1.3` ([docs/verification/2026-11-colab-openweight-tuning.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-openweight-tuning.md)):** Scored `Qwen2.5-32B-Instruct-AWQ` (`A100`, `12.36%` blind correctness), `Qwen3-32B-AWQ` (`A100`, `2.63%`), and `Qwen2.5-14B-Instruct-AWQ` (`L4`, `11.99%`, `90.38%` quote valid, `6.08` CCUs/1k) across `tuning_50` (`101` passages, `0/101` malformed JSON).
  - **Steps `2.1`–`2.2` ([docs/verification/2026-11-colab-relations-qualification.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-relations-qualification.md)):** Trained holdout-isolated 4-bit QLoRA adapter `qwen25-14b-tuning50-v1` (`adapter_sha256 = 028552c75e06...`, `~1.48` CCUs on `A100`) and blind-scored on frozen `initial_30` gold (`L4` `AWQ + LoRA`: `97.78%` quote valid, `27.27%` blind correctness, `12.7` CCUs/1k; `A100` `bf16 + LoRA`: `96.43%` quote valid, `22.22%` blind correctness, `39.0` CCUs/1k). Companion `#607` qualified three-pass `GPT-6 Luna` (`relations_messages`, [`2712f979`](https://github.com/u2giants/theoracle/commit/2712f979)) for informal chat threads while Colab `L4` (`Qwen2.5-14B-Instruct-AWQ`) is retained for `colab_offload = true` document/transcript backfills.
  - **Steps `3.1`–`3.3` & `4.1` ([docs/verification/2026-11-colab-sandbox-drain-proof.md](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-sandbox-drain-proof.md)):** `039_colab_leases.sql`, `/colab/lease`, `/colab/submit`, `/colab/status`, and `drain_leases.py` proven live in isolated Coolify sandbox across `110/110` passages (`60s` kill-mid-lease recovery, `HTTP 409` stale-lease rejection, `100.0%` verbatim quote validation, `$0.00` OpenRouter relations spend, `~0.27` actual CCUs, `0` post-run sessions).
- **Read-only production & Step `4.2` gate audit (2026-11-22 8:57 AM EST — zero production mutations performed):**
  - Production Coolify application `oracle-brain` (`uge6pfm4qapktivto4981mtg`) is currently running `ghcr.io/u2giants/theoracle-brain:2ecd9eee3f9b4fe409fd0dab1a6448eb02987e20` (`running:healthy`), while `ghcr.io/u2giants/theoracle-brain:8469000075b39a052b9706bebd5370e440e3566f` is built and published in GHCR (`brain-image.yml` run `44995571210`).
  - Production `cmap.model_seat` seats `meta-model-api/muse-spark-1.3-contributor` on `relations` for live documents/transcripts; `cmap.intake_thread` holds `4,169` staged raw rows (`65` ClickUp, `957` Teams chat, `3,147` email) untouched while `#607` Steps `2.4` and `2.5` remain `⬜ open` and `plan_meeting_triage_pipeline.md` remains blocked at Step `0.1` on Entra `OnlineMeetingTranscript.Read.All` tenant consent.
  - `ai-task-gates check --before deploy` / `--before production` under `--class production` enforces `current-chat-resource-and-action-authorization` (`STOP before "deploy"` / `"production"` without explicit production resource/action authorization).
- **Unrelated `HANDOFF.d/` successor-review candidates noted (untouched per non-interference rule):** Issue [#27](https://github.com/u2giants/theoracle/issues/27) is `CLOSED`; the 13 older files carrying `issue: 27` (`2026-10-12T0434Z` through `2026-10-21T0110Z`) remain for reconciliation by their owners.

---

## 4. Everything we tried that did NOT work

1. **Automated opening of `https://accounts.google.com` inside Antigravity's built-in browser subagent (`a3887803`):**
   - *How & why it failed:* Host security policy blocks agent navigation to protected authentication origins (`blocked_origins: https://accounts.google.com`, `NAVIGATION_NEEDS_PERMISSION`). Resolved cleanly by running `gcloud auth application-default login --disable-quota-project --scopes=openid,https://www.googleapis.com/auth/cloud-platform,https://www.googleapis.com/auth/userinfo.email,https://www.googleapis.com/auth/colaboratory` on `edge-dev`, which opened desktop Chrome to the loopback `http://localhost:8085/` callback so Albert completed sign-in once and the credential was immediately vaulted in 1Password (`whgwmjd6wvcq4rttpo6mx4367i`).
2. **Querying Coolify `oracle-brain` (`uge6pfm4qapktivto4981mtg`) under `/api/v1/services/{uuid}`:**
   - *How & why it failed:* Returned `HTTP 404` because `oracle-brain` is registered in Coolify as a docker-compose **application** (`/api/v1/applications/uge6pfm4qapktivto4981mtg`), whereas `oracle-sandbox-private` (`lh8tiwrst3hwij9yr3ss4vdx`) is a Coolify **service** (`/api/v1/services/lh8tiwrst3hwij9yr3ss4vdx`).
3. **Prior `google-colab-cli` / `vllm` / QLoRA dead ends (carried forward from PRs [#672](https://github.com/u2giants/theoracle/pull/672) & [#676](https://github.com/u2giants/theoracle/pull/676)):**
   - Do not set a GCP `quota_project_id` on the Colab ADC file (`colab.pa.googleapis.com` rejects consumer quota projects with `403`); always use `--disable-quota-project`.
   - Keep single-`colab exec` flat-upload staging, `<= 8 MiB` chunked uploads for `> 100 MB` archives, 20-second WebSocket heartbeat streaming, `COLAB_GUARD_MANAGED_TEARDOWN=1`, chat-template rendering (`enable_thinking=False`), and `enforce_eager=True, max_loras=1` in [apps/brain/colab/preflight.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py) and [apps/brain/colab/run_vllm_batch.py](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/run_vllm_batch.py).

---

## 5. Root causes and key findings

1. **Coolify API distinction for `oracle-brain` in Step `4.2`:**
   - Production `oracle-brain` (`uge6pfm4qapktivto4981mtg`) is a Coolify **application** (`/api/v1/applications/uge6pfm4qapktivto4981mtg`), pinned via `BRAIN_IMAGE_TAG=<40-char-commit-sha>` in [apps/brain/deploy/compose.coolify.yaml](https://github.com/u2giants/theoracle/blob/main/apps/brain/deploy/compose.coolify.yaml#L8).
2. **Measured Google AI Ultra CCU rates & model roles (`#664` + `#607`):**
   - `NVIDIA L4` (24 GB) burns `1.94 CCUs/hr` (`~1,030 hrs/mo` per 2,000 CCUs); `NVIDIA A100-SXM4-40GB` burns `6.73 CCUs/hr` (`~297 hrs/mo` per 2,000 CCUs); current account balance is **`3,027.44` CCUs** (`Active assignments: 0`).
   - Unstructured `#607` chat/email/ClickUp threads (`origin IS NOT NULL`) use three-pass `GPT-6 Luna` (`relations_messages` seat: `97.45%–98.47%` correctness, `94.23%–96.15%` recall), while `colab_offload = true` document/transcript backfills use Colab `L4` (`Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698`, `100.0%` verbatim quote validation in Step `4.1` at `$0.00` API spend and `~2.45` CCUs/1k cold / `<0.5` CCU/1k warm).

---

## 6. Exact next steps

1. **Wait for an approved `colab_offload = true` production backfill batch (`#607` Step 3.1 pilot window or `plan_meeting_triage_pipeline.md` Step 2.3 staged transcripts) and explicit production deploy authorization:**
   - *You'll know it's ready when:* Approved `colab_offload = true` sources are staged for production ingestion and `ai-task-gates start --class production` + `ai-task-gates check --before deploy` / `--before production` opens cleanly.
2. **Restore Colab ADC on any workstation if missing (zero browser interaction needed):**
   - `op read "op://vibe_coding/whgwmjd6wvcq4rttpo6mx4367i/ADC_JSON" | (umask 077; cat > "$ADC_FILE")` and verify `colab --auth=adc usage` exits `0` with `Active assignments: 0`.
3. **Execute Step `4.2` — Production backfill drain proof (`- [ ] live proof` on [#664](https://github.com/u2giants/theoracle/issues/664)):**
   - Pin `BRAIN_IMAGE_TAG` on Coolify application `uge6pfm4qapktivto4981mtg` (`oracle-brain`) to the current `main` 40-char SHA, set `BRAIN_COLAB_WORKER_TOKEN` from `op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN` and `BRAIN_COLAB_LEASE_ENABLED=true`, deploy, and verify `https://oracle-brain.designflow.app/health`.
   - Run `uv run python -m colab.preflight --script colab/drain_leases.py --gpu L4 --max-wall-minutes 60 --max-ccu 4 --install-requirements colab/requirements-colab.txt --pass-env BRAIN_COLAB_API_URL --pass-env BRAIN_COLAB_WORKER_TOKEN -- --hf-model Qwen/Qwen2.5-14B-Instruct-AWQ --hf-revision 539535859b135b0244c91f3e59816150c8056698` against `https://oracle-brain.designflow.app`, then flip `BRAIN_COLAB_LEASE_ENABLED=false` when the batch finishes.
   - *You'll know it worked when:* Newly ingested entities, edges, and verbatim citations with `colab-vllm/...` provenance render cleanly on `https://oracle.designflow.app/map`, `colab --auth=adc usage` shows `Active assignments: 0` (`Usage rate: 0.00/hr`), production CCU economics are posted on `#664`, `- [ ] live proof` is checked off on `#664`, and this handoff file is deleted in the closing PR.

---

## 7. Constraints and gotchas in force

- **Never weaken quality gates (`plan_colab_gpu_offload.md` §1 rule 3) or inject synthetic test text into production `cmap.source`:** Never substitute an unqualified single-pass model onto `#607` `origin IS NOT NULL` message threads (`relations_messages` owns those), and never seed fake passages into production Company Map.
- **Hard `L1` secret boundary:** Never pass `DATABASE_URL`, `DIRECT_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `OPENROUTER_API_KEY`, `BRAIN_SHARED_TOKEN`, or `ADC_JSON` onto Colab VMs. Pass `BRAIN_COLAB_WORKER_TOKEN` exclusively via `preflight.py --pass-env BRAIN_COLAB_WORKER_TOKEN`.
- **Always verify `Active assignments: 0` before ending any session:** Run `colab --auth=adc usage` and `colab --auth=adc sessions` after every Colab run.

---

## 8. Access and environment

- **GitHub CLI (`gh`):** Authenticated as `u2giants`.
- **Google Colab CLI (`google-colab-cli v0.8.0`):** Authenticated via ADC on both `edge-dev` and Linux `edge-dev3` (`3,027.44` CCUs remaining, `Usage rate: 0.00/hr`, `Active assignments: 0`).
- **1Password vault `vibe_coding` (item IDs & titles only — never print secret values):**
  - `"Google Colab CLI Application Default Credentials - u2giants@gmail.com (AI Ultra CCUs, theoracle)"` — item `whgwmjd6wvcq4rttpo6mx4367i`, field `ADC_JSON`.
  - `"The Oracle — Sandbox Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `naytnzqu4ldh4t7jutxbx7btzq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - `"The Oracle — Production Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` — item `gulz2yow5h7tkkrdsopkh4udxq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - `"Coolify API token - Oracle read-only observer (theoracle, experiments)"` — item `5xjuaif5okkiqoszmh7ncrf3sy`, field `credential`.

---

## 9. Open questions and risks

- **Step `4.2` upstream batch & production gate (2026-11-22):** Step `4.2` awaits an approved `colab_offload = true` production backfill batch (`#607` Step 3.1 pilot window after Steps `2.4`–`2.5`, or `plan_meeting_triage_pipeline.md` Step 2.3 staged transcripts after Entra `OnlineMeetingTranscript.Read.All` consent) plus `ai-task-gates` `current-chat-resource-and-action-authorization` for `--class production`.
- **Owner business decisions:** Consolidated in §0 above.

---

## Part (b) — Coordinator record (sub-agent delegation)

- **This session (`8feab216`) — Google Colab OAuth Browser Opener (`browser` `flash` subagent `a3887803`):**
  - *Asked to do:* Open the Google OAuth URL in Antigravity's shared browser pane and pause without interacting with `accounts.google.com`.
  - *Actually did & found:* Host-verified `BROWSER_HOST_FACTS` reported `blocked_origins: https://accounts.google.com` (`NAVIGATION_NEEDS_PERMISSION`); Albert completed the sign-in via the desktop Chrome loopback window opened on `edge-dev`, after which the lead vaulted `whgwmjd6wvcq4rttpo6mx4367i` and synced `edge-dev3`. Subagent left idle per `<subagents>` lifecycle rules.
- **Carried forward from PRs [#667](https://github.com/u2giants/theoracle/pull/667), [#672](https://github.com/u2giants/theoracle/pull/672), and [#676](https://github.com/u2giants/theoracle/pull/676):** `flash` helpers `b438dd36` (Step `0.2`), `c8366766` (Step `1.2`), `fb89b826` (Step `3.3`), and `e8f80585` (Step `1.2` `first_finish_reason` telemetry) — all merged on `main`, worktrees closed.

---

## Self-audit (`handoff-writer` standard)

1. *Comprehensive enough for a brand-new developer with no project/session context to pick up without skipping a beat?* **Yes** — §§1–3 explain The Oracle, its Coolify application/service UUIDs, all completed Steps `0.1`–`4.1` with proof links, the newly vaulted Colab ADC item (`whgwmjd6wvcq4rttpo6mx4367i`), and the exact Step `4.2` state; §6 gives exact ADC restore and Step `4.2` commands and pass criteria.
2. *Detailed enough to continue as well as I could right now?* **Yes** — §§4–5 document the Coolify `/api/v1/applications/uge6pfm4qapktivto4981mtg` vs `/api/v1/services/...` distinction, `--disable-quota-project` ADC requirement, measured `L4`/`A100` CCU rates, and `relations_messages` vs `colab_offload = true` routing split.
3. *Every relevant detail included (background, goals, current state, failures, decisions, constraints, risks, next actions, verification)?* **Yes** — covered across §§0–9 and Part (b) with portable GitHub URLs (zero machine-local paths or private IPs) and 1Password item IDs only.
4. *Line-by-line Section 0 sweep: if Albert read ONLY §0, would he see every business decision across §§1–9 and Part (b), and zero technical approvals?* **Yes** — walked §§1–9 and Part (b) line by line: zero blocking business decisions exist now, both downstream post-pilot checkpoints appear in §0 with explicit recommendations and settled-ruling dates, and the technical Step `4.2` batch/gate dependencies stay in §§3, 6, 9 out of §0.

## Next-session prompt

```text
Resume #664 from main of https://github.com/u2giants/theoracle once an approved colab_offload=true production backfill batch is staged and production deploy is authorized.
Read AGENTS.md first, then https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md (STATUS first), and https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T1358Z-edge-dev-agy-colab-adc-vaulted-step42-gated.md.
If running on a fresh machine, restore Colab ADC from `op://vibe_coding/whgwmjd6wvcq4rttpo6mx4367i/ADC_JSON` and verify `colab --auth=adc usage` shows Active assignments: 0; then run `ai-task-gates start --class production` + `check --before deploy` / `--before production`, deploy `oracle-brain` (`uge6pfm4qapktivto4981mtg`) pinned to `main`'s 40-char SHA with `op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN`, drain the batch via `preflight.py` + `drain_leases.py`, verify `/map` citations and `Active assignments: 0`, check off `- [ ] live proof` on #664, and delete this handoff in the closing PR.
```
