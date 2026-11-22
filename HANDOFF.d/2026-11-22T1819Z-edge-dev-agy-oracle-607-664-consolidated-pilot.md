---
summary: "Consolidated Oracle handoff uniting #607 (Phase 2 complete -> Step 3.1 14-day pilot) and #664 (Steps 0.1-4.1 complete -> Step 4.2 live drain) for one fresh chat."
kind: handoff
status: OPEN
read-when: starting a single consolidated Oracle session for #607 Step 3.1 (14-day live pilot), Step 4.1 (90-day run), and #664 Step 4.2 (Colab live drain)
issue: 607
owner: agy/oracle-607-664-consolidated-pilot
---

# Consolidated Handoff — Oracle `#607` (14-Day Live Pilot & 90-Day Run) + `#664` (Colab Live Drain)

- **Tracking issues:** [#607](https://github.com/u2giants/theoracle/issues/607) (project-manager message intake) and [#664](https://github.com/u2giants/theoracle/issues/664) (Google Colab GPU batch offload)
- **Plans:** [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md) and [`plan_colab_gpu_offload.md`](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md)
- **Why this file exists:** Consolidates six completed/idle Antigravity sessions (three on `#607`, three on `#664`) that all converged onto the exact same next gate — **Phase 3 Step 3.1 (14-day live project-manager pilot)** — plus Albert's 2026-11-22 ruling (*"so stick with Luna."*) so **one fresh chat** can drive execution from here.
- **Supersedes (for the next session to retire under the successor rule once its work completes — do not edit them here):**
  - [`HANDOFF.d/2026-11-22T1505Z-edge-dev-agy-intake-step31-pilot.md`](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T1505Z-edge-dev-agy-intake-step31-pilot.md) (`#607` Step 3.1 handoff)
  - [`HANDOFF.d/2026-11-22T1358Z-edge-dev-agy-colab-adc-vaulted-step42-gated.md`](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T1358Z-edge-dev-agy-colab-adc-vaulted-step42-gated.md) (`#664` Step 4.2 handoff)
  - [`HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md`](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md) (older `#607` Step 2.3 handoff — keep until `plan_colab_gpu_offload.md` §2 reference is updated)

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None blocks starting or finishing Step 3.1 (the 14-day live pilot).** Never ask Albert to approve a technical step, deploy, credential, PR merge, or OAuth flow. When each downstream business checkpoint below is reached, present **all** open business questions in **one** plain-English message once real measured evidence exists:

1. **Downstream checkpoint 1 — post-pilot exact-verbatim-quote cost review (after Step 3.1 finishes; blocks Step 4.1 company-wide rollout only if Albert changes `L1`):** Present the measured dollar cost per kept thread from the 14-day pilot plus a full-company projection so Albert can decide whether to keep exact verbatim quotes (`L1`). **Recommendation:** Keep exact verbatim quotes — three-pass `GPT-6 Luna` native batch (`$2.42/1k` `w3000` windows + `$0.085–$0.17/1k` passages for business-area sorting, ~$11.50–$12.00 for all 3,373 staged PM threads) is inexpensive while preserving auditable citations.
2. **Downstream checkpoint 2 — final live-proof business acceptance (after `#607` Step 4.1 90-day run + 5 cited answers and `#664` Step 4.2 Colab drain complete; blocks checking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607) and [#664](https://github.com/u2giants/theoracle/issues/664)):** Show Albert the live project-management page (`https://oracle.designflow.app/map`), the five cited web answers, and the Brain's generated (**unsent**) follow-up questions for Jessica and Carlos so he can judge the Brain's question quality while keeping the Teams interview bot off (`#518`).

### Already settled — do NOT re-ask
- **Stick with qualified three-pass `GPT-6 Luna` for message intake (2026-11-22 12:46 PM EST, verbatim):** *"so stick with Luna."* Do not switch models, alternate models per message, add RAG to message extraction, or route messy chats/emails to Colab.
- **Scope & silence (2026-11-18, `L10` & `#518`):** Jessica's and Carlos's mailboxes, private/group Teams chats, and ClickUp are in scope; reading is unannounced; the Teams interview bot stays **off**.
- **No frontier models in bulk intake (2026-11-18, `L9`):** *"we can't afford frontier models."* Never route extraction, retries, function sorting, or routine grading to Opus, Sol, GLM MAX, or Hydrogen.
- **Keep exact verbatim words through the 14-day pilot (2026-11-19, `L1`):** *"ok, keep exact words through the pilot."*
- **Step 2.5 ScaleDown `/classify` test (2026-11-18):** Tested and failed its gates; per the plan's fallback rule, message `function_assign` routes to `openai/gpt-6-luna`.
- **Prepaid Google Colab integration (`#664`, 2026-11-21 / 2026-11-22):** Authorized and Google `colaboratory` OAuth completed by Albert; credentials vaulted permanently in 1Password `vibe_coding` (`whgwmjd6wvcq4rttpo6mx4367i`). Use Colab (with automatic cloud fallback when off/out of units) only for cleaner `colab_offload = true` document/transcript backfills.

---

## 1. What this application is

**The Oracle** (`https://github.com/u2giants/theoracle`, **PUBLIC** repository, single protected branch `main`) is the Company Map and evidence-backed operational adviser for **POP Creations / Spruce Line**. It ingests company documents, flowcharts, meeting transcripts, Teams chats, ClickUp tasks, and authorized employee email into Supabase Postgres (`cmap` schema) and FalkorDB (`company` graph); answers employee questions in English and Mandarin citing verbatim quotes; and generates targeted Teams interview questions to close knowledge gaps ([`AGENTS.md`](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [`docs/architecture.md`](https://github.com/u2giants/theoracle/blob/main/docs/architecture.md), [`docs/agents/09-container-and-service-inventory.md`](https://github.com/u2giants/theoracle/blob/main/docs/agents/09-container-and-service-inventory.md)).

- **`apps/web`:** Next.js 16 web app on Vercel (`https://oracle.designflow.app`, project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`).
- **`apps/brain`:** Python 3.12+ FastAPI API and background job worker on Coolify (`oracle-brain`, Coolify **application** UUID `uge6pfm4qapktivto4981mtg`, `https://oracle-brain.designflow.app`, image `ghcr.io/u2giants/theoracle-brain`).
- **`oracle-sandbox-private`:** Dedicated isolated Coolify **service** (`lh8tiwrst3hwij9yr3ss4vdx`: `quote-tools-lh8tiwrst3hwij9yr3ss4vdx` + `sandbox-db-lh8tiwrst3hwij9yr3ss4vdx`) holding all `#607` private message threads, gold sets, QLoRA adapters, and sealed verification receipts on volume `lh8tiwrst3hwij9yr3ss4vdx_sandbox-evidence` (`/sandbox`).

---

## 2. What we set out to do, and why

Two parallel tracks ran across six separate Antigravity sessions (`aab22be9`, `097fb84f`, `b3f49105` on `#607`; `0e6ed4f6`, `6aba6e03`, `8feab216` on `#664`):
1. **`#607` (`plan_pm_message_intake.md`):** Qualify the cheapest passing non-frontier extraction pipeline on Jessica's and Carlos's Teams chats, ClickUp tasks, and email, build half-price native batching and business-area sorting, and prepare the 14-day live pilot so Albert can judge The Oracle's questions against real project-management data.
2. **`#664` (`plan_colab_gpu_offload.md`):** Harness Albert's 2,000+ prepaid monthly Google Colab Compute Units headlessly (zero notebook clicking, automatic cloud fallback, strict secret isolation) to benchmark open-weight models / QLoRA and drain `colab_offload = true` backfills at `$0` cloud API spend.

Both tracks finished all pre-production engineering, proofs, and merges on `main` (`45e9a43d`), leaving zero open PRs and zero active conflicts. Albert asked to retire all six old chats and consolidate both tracks into **one handoff doc** for **one fresh chat**.

---

## 3. Current state — what is true right now

- **Repository `u2giants/theoracle` (`main` @ [`45e9a43d`](https://github.com/u2giants/theoracle/commit/45e9a43d)):** Clean, zero open PRs, `668+` brain `pytest` tests passing, production (`oracle-brain`, `BRAIN_INTAKE_ENABLED=false`, `BRAIN_COLAB_LEASE_ENABLED=false`, `#518` interview bot off) untouched.
- **`#607` Phase 0, Phase 1, Phase 2 (Steps `2.1`–`2.5`), and Phase 5 (`5.1`) are `✅ done` and merged on `main`:**
  - **Step 2.3 qualification (PRs [#669](https://github.com/u2giants/theoracle/pull/669), [#671](https://github.com/u2giants/theoracle/pull/671), [#673](https://github.com/u2giants/theoracle/pull/673), [#674](https://github.com/u2giants/theoracle/pull/674)):** Three-pass `openai/gpt-6-luna` (`relations_messages` seat via [`040_message_relations_seat.sql`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/040_message_relations_seat.sql), [`prompts/relations_messages*.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages.md)) passed every held-out gate on `30` Step 2.1 gold threads (`97.45%–98.47%` correctness, LB `95.57%–97.40% >= 95%`; `94.23%–96.15%` lead recall, LB `90.48%–94.12% >= 90%`; `100.0%` quotes), across all `350` held-out threads (`0/350` truncations, UB `0.78% <= 1%`; `100.0%` quotes on `3,840` relations), and on the 15-question `brain/eval` check (`0.7118` vs `0.6361` reference and `0.6040` Step 2.1 pool). Proofs: [`2026-11-22-pm-intake-luna-v7-qualification.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-luna-v7-qualification.md), [`2026-11-21-pm-intake-tuning-and-frontier-check.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-21-pm-intake-tuning-and-frontier-check.md).
  - **Steps 2.4 & 2.5 (PR [#679](https://github.com/u2giants/theoracle/pull/679), merged as [`45e9a43d`](https://github.com/u2giants/theoracle/commit/45e9a43d9d385c94aaf8ed3ad82a331f90e56b2d); GHCR image published in [`brain-image.yml` run `45040442324`](https://github.com/u2giants/theoracle/actions/runs/45040442324)):** Landed OpenAI `/v1/batches` + `service_tier="flex"` tail-salvage client ([`llm_batch.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm_batch.py#L1-L778), incl. `validating -> in_progress` stall-clock reset), direct OpenAI routing ([`llm.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm.py#L36-L141)), `w3000` turn-packed windowing + Pass 1->3 `_merge_message_new_mentions` carry-forward + `Artifact` entity-type normalization + 3-round cross-source job coalescing ([`relations.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py#L858-L1728)), message `function_assign` routing to `openai/gpt-6-luna` ([`function_assign.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/function_assign.py#L63-L655)), and `--days` recency filtering in [`ingest.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/ingest.py#L39-L290). Live 100-passage sandbox batch passed at `$0.2422` vs `$0.2594` forecast (`-6.61%`, `0` truncations, `99.41%` raw quotes); Step 2.5 `GPT-6 Luna` cut wrong business-area picks to `8.47%` (`$0.0852/1k` batch) and raised 15-question `brain/eval` to `0.7163`. Proof: [`2026-11-22-pm-intake-step-2-4-and-2-5-proof.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-step-2-4-and-2-5-proof.md); `#607` update: [comment `7081608866`](https://github.com/u2giants/theoracle/issues/607#issuecomment-7081608866).
- **`#664` Steps `0.1`–`4.1` are `✅ done` and merged on `main` (PRs [#667](https://github.com/u2giants/theoracle/pull/667), [#672](https://github.com/u2giants/theoracle/pull/672), [#676](https://github.com/u2giants/theoracle/pull/676), [#678](https://github.com/u2giants/theoracle/pull/678)):**
  - Guarded CLI preflight ([`preflight.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/preflight.py)), offline vLLM guided-JSON runner ([`run_vllm_batch.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/run_vllm_batch.py)), pull-lease schema ([`039_colab_leases.sql`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/039_colab_leases.sql)), `/colab/lease|submit|status` API ([`colab.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/colab.py)), and [`drain_leases.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/colab/drain_leases.py) are all proven live in isolated Coolify sandbox (`110/110` passages, `100.0%` quotes, kill-recovery, `$0` API spend, `~0.27` CCUs, `0` sessions remaining). Proof: [`2026-11-colab-sandbox-drain-proof.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-sandbox-drain-proof.md).
  - Google Colab ADC is vaulted in 1Password `vibe_coding` (`whgwmjd6wvcq4rttpo6mx4367i`) and verified headless on both workstations (`3,027.44` CCUs available, `Active assignments: 0`).
- **Remaining open work:**
  1. `#607` **Step 3.1** (14-day live project-manager pilot on production `oracle-brain`), **Step 3.1a** coordination ([`HANDOFF.d/2026-11-22T1350Z-edge-dev3-codex-ilona-live-pilot.md`](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T1350Z-edge-dev3-codex-ilona-live-pilot.md)), and **Step 4.1** (90-day run + 5 cited web answers + `- [ ] live proof`).
  2. `#664` **Step 4.2** (production backfill drain proof on an approved `colab_offload = true` document/transcript batch + `- [ ] live proof`).
  3. **Post-merge advisory `review-finding` follow-up [#680](https://github.com/u2giants/theoracle/issues/680) on PR [#679](https://github.com/u2giants/theoracle/pull/679) (deferred by session `b3f49105` under `/wrap-up` scope freeze; non-blocking for Step 3.1 CLI pilot):**
     - `(a)` [`apps/brain/brain/intake/ingest.py#L244-L251`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/ingest.py#L244-L251): `handle_intake_ingest` forwards `origin`, `limit`, and `days` from `job["payload"]`, but omits `thread_prefix=payload.get("thread_prefix")` and calls unguarded `int(days_raw)`. Step 3.1's CLI `python -m brain.intake.ingest --days 14` already supports `--thread-prefix` and `argparse` `type=int`, so the CLI pilot is unaffected; forward `thread_prefix` and guard `int(days_raw)` in `handle_intake_ingest` before using queued `intake_ingest` jobs for `3.1a`/`4.1`.
     - `(b)` [`apps/brain/brain/extract/relations.py#L1715-L1728`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py#L1715-L1728): per-chunk failures in `_run_message_batch` already retry 3× synchronously (`_call_with_retries`) and record persistent failures via `record_chunk_failure` + `finish_source(sib_sid)`, but `source_chain_ended(sib_sid, failed=False, ...)` passes hardcoded `failed=False` instead of `sib_state = finish_source(sib_sid)` -> `failed=(sib_state == "failed")`.
     - `(c)` [`apps/brain/brain/llm.py#L98-L112`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm.py#L98-L112) vs [`apps/brain/brain/llm_batch.py#L43-L100`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm_batch.py#L43-L100): `openai/*` intentionally uses OpenAI `/v1/batches` when `OPENAI_API_KEY` is present and OpenRouter (`OPENROUTER_API_KEY`, already set on Coolify `oracle-brain`) for synchronous calls/fallback per `plan_pm_message_intake.md` step 2.4, whereas `openai-api/*` forces direct OpenAI on both paths; document or allow direct fallback when `OPENROUTER_API_KEY` is absent, then close `#680` (alongside sibling `#607`/`#664` `review-finding` issues `#675`, `#670`, `#668`, `#651`, `#644`, `#635` as reviewed).

---

## 4. Everything we tried that did NOT work

1. **Single-pass `prompts/relations.md` on messy messages (all L8 AND frontier models):** Even `Claude Opus 5.5` (`39.5%`, `$28.95/1k`) and `GPT-6.2 Sol` (`38.1%`, `$15.59/1k`) failed; `39.1%` of claims overstated scope/timing/type and `flat -> relations` mention filtering capped recall at `35%–41%`. Fixed by three-pass full-thread `relations_messages*.md` on `GPT-6 Luna`.
2. **Dynamic few-shot RAG + `GPT-6 Luna` (single-pass):** Retrieved top-4 verified examples from 29 disjoint tuning threads; lifted 30-gold held-out recall to `100%` (51/51 lead facts) / `93.8%` overall and precision to `89.1%` (`LB 82.9%`) at `$0.67/1k` threads, but still missed the `95%` LB. Superseded by 3-pass Luna (`97.5%–98.5%`).
3. **Pairing `GPT-6 Luna` with `Claude Haiku 5.5` as a checker/repair guard:** Over-dropped valid facts and lowered both recall (`85% -> 75%`, `87% -> 66%`) and precision (`88% -> 73.5%`). Albert ruled *"so stick with Luna."*
4. **Open-weight Colab models (`Qwen3-32B`, `Qwen2.5-32B`, `Qwen2.5-14B`) AND QLoRA (`qwen25-14b-tuning50-v1`) on messy chat/email:** Failed blind correctness (`2.6%–12.4%` zero-shot; `27.3%` QLoRA) on informal chat threads ([`2026-11-colab-openweight-tuning.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-openweight-tuning.md), [`2026-11-colab-relations-qualification.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-relations-qualification.md)). Keep Colab strictly for cleaner `colab_offload = true` document/transcript backfills.
5. **OpenAI `/v1/fine_tuning/jobs`:** Returns `HTTP 403` (*"OpenAI is winding down the fine-tuning platform"*).
6. **OpenAI `/v1/batches` without stall-salvage or with short cancel grace (`15–30s`):** Batches frequently stall on the last `1–16%` of items, and `POST /cancel` stays in `cancelling` with `output_file_id = null` for `3–5` minutes before populating `output_file_id`. Keep `DEFAULT_STALL_SALVAGE_SECONDS = 180.0` and `DEFAULT_CANCEL_GRACE_SECONDS = 300.0` + `service_tier="flex"` in [`llm_batch.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm_batch.py#L36-L37).
7. **Reordering `prompts/relations_messages*.md` for prefix caching:** All three templates are `< 1,024` tokens (OpenAI's cache minimum); do not reorder/pad them or break `message_relations_prompt_hash()`.
8. **ScaleDown `/classify` for `function_assign` (combined or standalone):** Softmax diluted chatter scores below `0.8`, and standalone missed all three Step 2.5 gates (`23.88%` wrong picks, `72.86%` recall). Keep `BRAIN_SCALEDOWN_FUNCTION_ASSIGN_ENABLED=false`.
9. **Wrong API endpoints & Colab quirks:**
   - Seat route is `PUT /models/relations_messages` (NOT `/models/seats/relations_messages` -> 404).
   - Coolify `oracle-brain` (`uge6pfm4qapktivto4981mtg`) is an **application** (`/api/v1/applications/...`), whereas `oracle-sandbox-private` (`lh8tiwrst3hwij9yr3ss4vdx`) is a **service** (`/api/v1/services/...`).
   - Colab ADC must omit `quota_project_id` (`--disable-quota-project`; otherwise `colab.pa.googleapis.com` returns `403`).
   - OpenRouter retired `z-ai/fp8` ZDR tag (use `fireworks/us`, `parasail/fp8`, or `baseten/fp8`).

---

## 5. Root causes and key findings

- **Split routing plays to each engine's verified strength:**
  - Unstructured `#607` message threads (`origin IS NOT NULL`): **three-pass `GPT-6 Luna`** (`relations_messages`, OpenAI native `/v1/batches` + `flex` salvage at `$2.4221/1k` `w3000` windows, `~$11.37` full 3,373-thread backlog) + **`GPT-6 Luna` `function_assign`** (`8.47%` wrong picks, `$0.0852/1k` batch).
  - Cleaner `colab_offload = true` documents/transcripts (`#664`): **Colab `L4` (`Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698`)** at `1.94 CCU/hr` (`100%` quote match in Step 4.1, `$0` API spend), with automatic cloud fallback whenever `BRAIN_COLAB_LEASE_ENABLED=false` or Colab is off.
- **Pilot window isolation (`--days 14`):** `cmap.intake_thread` currently holds `4,169` staged rows ordered oldest-first (`ORDER BY COALESCE(started_at, updated_at) ASC`). Always keep `BRAIN_INTAKE_ENABLED=false` during Step 3.1 and trigger ingestion explicitly via `python -m brain.intake.ingest --days 14` so neither older 90-day threads nor Ilona's `3.1a` prefixed threads are pulled prematurely.

---

## 6. Exact next steps

1. **Deploy latest `main` to `oracle-brain` and configure Step 3.1 seats/env (production):**
   - Create a fresh git worktree from `origin/main` and run `ai-task-gates start --class production` + `ai-task-gates check --before deploy` and `--before production` (reading [`docs/agents/13-deployment.md`](https://github.com/u2giants/theoracle/blob/main/docs/agents/13-deployment.md)).
   - Verify `.github/workflows/brain-image.yml` built `ghcr.io/u2giants/theoracle-brain:<main-40-char-sha>` (commit `45e9a43d` or newer). Pin `BRAIN_IMAGE_TAG` on Coolify application `uge6pfm4qapktivto4981mtg` (`oracle-brain`), set:
     - `BRAIN_MESSAGE_RELATIONS_MODEL=openai/gpt-6-luna` (and seat `PUT /models/relations_messages` = `{"model": "openai/gpt-6-luna"}`)
     - `OPENAI_API_KEY` from 1Password `vibe_coding` item `3onekcbg3dxnazpnt36d4yzfcq` (field `6tez7ajfmk4eogwywl75talobm`) with `BRAIN_RELATIONS_BATCH_ENABLED=true`
     - `BRAIN_INTAKE_MAX_USD=5.00` (expected 14-day spend `~$2–$3`)
     - `BRAIN_INTAKE_ENABLED=false` (keep hourly global sweep off during Step 3.1) and keep Teams interview bot **off** (`#518`).
   - Deploy and confirm `GET https://oracle-brain.designflow.app/health`, idempotent migrations `038`–`040`, and `GET /models` showing `relations_messages = openai/gpt-6-luna`.
   - *You'll know it worked when:* `oracle-brain` is `running:healthy` on the new SHA, `relations_messages` is seated to `openai/gpt-6-luna`, and zero unscoped sweep jobs run.

2. **Execute `#607` Step 3.1 — 14-day live project-manager pilot through `recommend`:**
   - Collect/clean the recent 14-day window for Jessica and Carlos (ClickUp, Teams chats, email — preserving `--thread-prefix` separation from Ilona's `3.1a` cohort) and run `python -m brain.intake.ingest --days 14`.
   - Wait for `read_source -> classify_extract -> relations (3-round batch) -> resolve -> project -> process_pass -> contradictions -> function_assign -> communities -> recommend` to complete.
   - Audit `20` randomly sampled **dropped** threads for wrongly dropped operational content (target `0`).
   - Post aggregate-only pilot metrics on [#607](https://github.com/u2giants/theoracle/issues/607) (counts, skipped `0.8` passages, calls/USD per stage, quote rate, **cost per kept thread**, **full-company projection**) and present §0 **Checkpoint 1** to Albert.
   - *You'll know it worked when:* `https://oracle.designflow.app/map` project-management page shows new message-backed processes/people with verbatim quotes, spend `<= BRAIN_INTAKE_MAX_USD`, 20 dropped threads are audited, and metrics are posted on `#607`.

3. **Coordinate Step `3.1a` and execute `#607` Step 4.1 (90-day full run + 5 cited web answers):**
   - Coordinate with [`HANDOFF.d/2026-11-22T1350Z-edge-dev3-codex-ilona-live-pilot.md`](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T1350Z-edge-dev3-codex-ilona-live-pilot.md) once the Step 2.4/2.5 image is live.
   - Run the full 90-day project-manager window (`Step 4.1`), ask five project-management questions on `https://oracle.designflow.app` verifying each cites message-derived sources, and verify unsent follow-up questions are generated (`#518` bot stays off).
   - *You'll know it worked when:* all five live web answers cite message-derived sources and unsent questions are ready for §0 **Checkpoint 2**.

4. **Execute `#664` Step 4.2 (Colab production drain proof on approved `colab_offload = true` batch) and close out:**
   - Once an approved `colab_offload = true` document/transcript batch is staged (never synthetic text and never unstructured `#607` message threads), restore Colab ADC if needed from `op://vibe_coding/whgwmjd6wvcq4rttpo6mx4367i/ADC_JSON`, set `BRAIN_COLAB_WORKER_TOKEN` (`op://vibe_coding/gulz2yow5h7tkkrdsopkh4udxq/BRAIN_COLAB_WORKER_TOKEN`) and `BRAIN_COLAB_LEASE_ENABLED=true` on `oracle-brain`, run `preflight.py --script colab/drain_leases.py --gpu L4 --max-wall-minutes 60 --max-ccu 4 --install-requirements colab/requirements-colab.txt --pass-env BRAIN_COLAB_API_URL --pass-env BRAIN_COLAB_WORKER_TOKEN -- --hf-model Qwen/Qwen2.5-14B-Instruct-AWQ --hf-revision 539535859b135b0244c91f3e59816150c8056698`, then set `BRAIN_COLAB_LEASE_ENABLED=false` and verify `colab --auth=adc usage` shows `Active assignments: 0`.
   - Present §0 **Checkpoint 2** to Albert; once he accepts, check off `- [ ] live proof` on `#607` and `#664`, and delete this handoff plus the superseded `2026-11-22T1505Z` and `2026-11-22T1358Z` handoffs under the successor rule in the closing PR.
   - *You'll know it worked when:* `/map` renders `colab-vllm/...` citations, `Active assignments: 0`, both issues have live proof verified, and all superseded handoffs are retired cleanly.

---

## 7. Constraints and gotchas in force

- **Public repo privacy (`L7`):** Never commit or paste raw message text, verbatim quotes, employee/customer/vendor emails, private thread subjects, source UUIDs tied to private threads, LAN/tailnet IPs, or secret values into Git, PRs, issues, or logs.
- **Zero frontier models (`L9`) & Teams interview bot OFF (`#518`).**
- **Keep `BRAIN_INTAKE_ENABLED=false` during Step 3.1** (use explicit `--days 14` CLI trigger); enable only for Step 4.1.
- **Prompt-hash lock:** Do not edit `prompts/relations_messages*.md` without re-qualifying Step 2.3.
- **Hard 30-minute ceiling:** Never wait/hold/poll `> 30` minutes (`MAX_POLL_DEADLINE_SECONDS = 1800.0`).
- **Hard `L1` Colab secret boundary:** Never pass DB/Supabase/OpenRouter/shared tokens or `ADC_JSON` onto Colab VMs — only `BRAIN_COLAB_WORKER_TOKEN` via `--pass-env`. Always verify `Active assignments: 0` after any Colab run.
- **Canonical checkout discipline:** Edit only inside isolated git worktrees; declare `ai-task-gates`; AI merges PRs with `--merge --delete-branch` (never `--admin` or `--squash`).

---

## 8. Access and environment

- **GitHub:** `gh` authenticated as `u2giants` (`Albert Hazan <u2giants@users.noreply.github.com>`).
- **Coolify host & containers:** SSH `vps2-direct` / `hetzner`; production `oracle-brain` (Coolify **application** `uge6pfm4qapktivto4981mtg`); isolated sandbox `oracle-sandbox-private` (Coolify **service** `lh8tiwrst3hwij9yr3ss4vdx`, `quote-tools-lh8tiwrst3hwij9yr3ss4vdx`).
- **Google Colab CLI:** `google-colab-cli v0.8.0` (`colab --auth=adc`), `3,027.44` CCUs available, `Active assignments: 0`.
- **1Password vault `vibe_coding` (IDs/titles only — NEVER print secret values):**
  - OpenAI direct key (`OPENAI_API_KEY`): item `3onekcbg3dxnazpnt36d4yzfcq`, field `6tez7ajfmk4eogwywl75talobm`.
  - ClickUp token (`CLICKUP_API_TOKEN`): item `"clickup.com API credentials"`, field `api token`.
  - Microsoft Graph (`AZURE_TENANT_ID`, `AZURE_GRAPH_CLIENT_ID`, `AZURE_GRAPH_CLIENT_SECRET`): already on Coolify `oracle-brain`; vault `"Designflow - Azure Graph client secret (AZURE_CLIENT_SECRET)"`.
  - ScaleDown key (`SCALEDOWN_API_KEY`): item `epna47xmzcnbdc6eb3tjpx6phm`, field `SCALEDOWN_API_KEY`.
  - Google Colab ADC (`ADC_JSON`): item `whgwmjd6wvcq4rttpo6mx4367i`, field `ADC_JSON`.
  - Production Colab Worker Token (`BRAIN_COLAB_WORKER_TOKEN`): item `gulz2yow5h7tkkrdsopkh4udxq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - Sandbox Colab Worker Token: item `naytnzqu4ldh4t7jutxbx7btzq`, field `BRAIN_COLAB_WORKER_TOKEN`.
  - Coolify read-only observer token: item `5xjuaif5okkiqoszmh7ncrf3sy`, field `credential`.

---

## 9. Open questions and risks

- **Global sweep vs 14-day pilot scope (2026-11-22):** Guarded by keeping `BRAIN_INTAKE_ENABLED=false` and running explicit `--days 14` ingest during Step 3.1.
- **`#664` Step 4.2 batch source (2026-11-22):** Step 4.2 needs a genuine `colab_offload = true` document/transcript backfill (e.g., meeting transcripts once `plan_meeting_triage_pipeline.md` Entra consent clears, or an approved clean document batch) — do NOT substitute synthetic data or unstructured `#607` chat threads.
- **Sibling `3.1a` coordination (2026-11-22):** Check `gh pr list` and recent `#607` comments before mutating `oracle-brain` env vars so Ilona's prefixed `3.1a` cohort remains isolated.
- **Unrelated scheduled `Brain quality gate` noise on [#546](https://github.com/u2giants/theoracle/issues/546) (2026-11-22):** Scheduled workflow runs (e.g. [`45051644174`](https://github.com/u2giants/theoracle/actions/runs/45051644174)) fail with `no eval questions: add some on the eval page (or load the seed)` on unseeded live `oracle-brain`; pre-existing and unrelated to `#607`/`#664`.
- **Advisory `#680` cleanup before Step 4.1 hourly sweep (2026-11-22):** Resolve the three small follow-ups in [#680](https://github.com/u2giants/theoracle/issues/680) (§3 item 3 above: `handle_intake_ingest` `thread_prefix`/`days` guard, `source_chain_ended` `sib_state == "failed"`, and `openai/*` vs `openai-api/*` note) in a quick code PR before turning `BRAIN_INTAKE_ENABLED=true` for Step 4.1.

---

## Self-audit (`handoff-writer` mandatory 4-question gate)

1. *Is this handoff comprehensive enough that a brand-new developer with no project knowledge and no session context could pick up and not skip a beat?* **Yes** — §§1–3 define The Oracle, Coolify UUIDs, and exact merged `main` (`45e9a43d`) status across both `#607` and `#664`; §6 gives exact ordered execution steps and verification gates for Steps 3.1, 3.1a, 4.1, and 4.2; §8 lists every CLI, host, and 1Password item ID.
2. *Is it detailed enough to continue as well as the prior six sessions combined?* **Yes** — §§4–5 preserve every hard-won failure and nuance across both tracks (RAG 89% vs 3-pass Luna 98%, Luna+Haiku over-dropping, Colab Qwen/QLoRA failing messy chats, OpenAI fine-tune 403, `/v1/batches` 180s/300s `flex` salvage, `<1,024`-token prefix cache ceiling, ScaleDown softmax failure, `PUT /models/relations_messages`, Coolify `applications` vs `services`, `--disable-quota-project`, and `--days 14` recency isolation).
3. *Is every relevant detail included with portable GitHub URLs only?* **Yes** — all ten sections (0–9) are complete with full GitHub URLs (zero machine-local paths, zero private data, zero secret values).
4. *If Albert read ONLY §0, would he see every business decision needed from him and zero technical approvals?* **Yes** — verified line by line across §§1–9: zero blocking decisions exist to start Step 3.1; both downstream business checkpoints (post-pilot `L1` cost review and final live-proof review) sit in §0 with recommendations and what they block; today's *"so stick with Luna."* ruling and all prior owner rulings sit under "Already settled — do NOT re-ask"; zero technical approvals appear in §0.

## Next-session prompt

```text
Resume The Oracle on main of https://github.com/u2giants/theoracle using the consolidated handoff:
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T1819Z-edge-dev-agy-oracle-607-664-consolidated-pilot.md

Read https://github.com/u2giants/theoracle/blob/main/AGENTS.md,
https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md (STATUS first),
https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md (STATUS first),
and the consolidated handoff above.

Both #607 Phase 2 (Steps 2.1-2.5) and #664 pre-production proofs (Steps 0.1-4.1 + vaulted Colab ADC) are complete and merged on main, and the owner confirmed sticking with qualified three-pass GPT-6 Luna ("so stick with Luna.") for message intake. Create an isolated worktree, declare ai-task-gates start --class production (plus check --before deploy and --before production), deploy oracle-brain (uge6pfm4qapktivto4981mtg) on latest main with relations_messages seated to openai/gpt-6-luna + OPENAI_API_KEY + BRAIN_INTAKE_MAX_USD=5.00 (keeping BRAIN_INTAKE_ENABLED=false and the #518 interview bot off), and execute #607 Step 3.1 (14-day live pilot via python -m brain.intake.ingest --days 14 through recommend, 20 dropped-thread audit, and aggregate cost report). Then proceed through #607 Step 4.1 (and #664 Step 4.2 once an approved colab_offload=true document/transcript batch is staged), retiring superseded handoffs under the successor rule upon completion.
```
