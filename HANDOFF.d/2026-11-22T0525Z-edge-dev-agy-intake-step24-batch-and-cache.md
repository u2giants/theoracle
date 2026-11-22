---
summary: "Oracle #607 step 2.3 qualified (three-pass GPT-6 Luna); resume at step 2.4 batch + cache path and step 2.5 ScaleDown function sorting."
kind: handoff
status: OPEN
read-when: continuing Oracle issue 607 at step 2.4 (batch + cached-prefix path), step 2.5 (ScaleDown function-assign bake-off), or step 3.1 (14-day pilot)
issue: 607
owner: agy/oracle-607-tune-95
---

# Oracle #607 — step 2.3 qualified (`GPT-6 Luna` three-pass `relations_messages`); resume at step 2.4

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None blocks starting or finishing steps 2.4 and 2.5.** Do **not** ask Albert to approve any technical step, credential, or OAuth flow. Surface the two downstream business checkpoints below to Albert together **only after** the measured evidence for each exists:

- **Downstream checkpoint 1 — post-pilot exact-verbatim-quote cost review (after step 3.1's 14-day pilot finishes):** Present the measured dollar cost per kept thread from the 14-day project-manager pilot alongside a full-company projection so Albert can decide whether to keep the exact-verbatim-quote evidence rule (`L1`) for company-wide rollout. **Recommendation:** Keep exact verbatim quotes — with `GPT-6 Luna` native batch (`$1.3611` per 1,000 standard 400-token passages / `$3.37` per 1,000 threads, or roughly `$11.37` across the entire 3,373-thread project-manager backlog), verbatim evidence remains affordable without sacrificing auditability. Blocks step 4.1 only if Albert changes `L1`.
- **Downstream checkpoint 2 — final live-proof business acceptance (after step 4.1's 90-day run and five cited answers pass):** Show Albert the live project-management function page and the Brain's generated (unsent) follow-up questions for Jessica and Carlos so he can judge the Brain's question quality before checking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607). **Recommendation:** Present the function page and unsent questions together in one message while keeping the Teams interview bot off (`#518`). Blocks checking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607).
- **Already settled — do NOT re-ask:**
  - *Jessica's and Carlos's mailboxes, private/group Teams chats, and ClickUp are in scope; reading is unannounced; the Teams interview bot stays off* (settled 2026-11-18 in [plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md#status--read-this-first), rules `L10` and `#518`).
  - *No frontier cloud models (`Opus`, `Sol`, `GLM MAX`, `Hydrogen`) anywhere in this pipeline* (settled 2026-11-18, rule `L9`).
  - *Keep exact verbatim words through the 14-day pilot* (settled 2026-11-19, rule `L1`).
  - *Business-area sorting with ScaleDown classify is approved to test in step 2.5* (settled 2026-11-18).

---

## 1. What this application is

**The Oracle** (`https://github.com/u2giants/theoracle`, **public** repository — never commit raw company messages, quotes, employee emails, or secrets) is the Company Map and operational adviser for **POP Creations / Spruce Line**. It ingests company documents, flowcharts, meeting transcripts, Teams chats, ClickUp tasks, and authorized employee email; extracts entities and verbatim-quoted relationships into Postgres (`cmap` schema on Supabase) and FalkorDB (`company` graph); answers employee questions citing exact source quotes; and drafts follow-up interview questions.

Runtime inventory ([developer guide](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [service inventory](https://github.com/u2giants/theoracle/blob/main/docs/agents/09-container-and-service-inventory.md)):
- `apps/web` — Next.js 16 web app on Vercel (`https://oracle.designflow.app`, project `prj_rP6Jlima7iK1paffEPhLqxlswGsC`).
- `apps/brain` — Python 3.12+ FastAPI API and background job worker (`oracle-brain` on Coolify, image `ghcr.io/u2giants/theoracle-brain`).
- `oracle-sandbox-private` — Dedicated isolated Coolify sandbox (`lh8tiwrst3hwij9yr3ss4vdx`: `quote-tools-lh8tiwrst3hwij9yr3ss4vdx` + isolated `sandbox-db-lh8tiwrst3hwij9yr3ss4vdx`) holding all private `#607` message threads, gold references, and qualification checkpoints on volume `lh8tiwrst3hwij9yr3ss4vdx_sandbox-evidence` (`/sandbox`).

## 2. What we set out to do this session, and why

Albert asked which model performed best on [#607](https://github.com/u2giants/theoracle/issues/607) (`plan_pm_message_intake.md` step 2.3) and instructed us to keep tuning it to clear the **95% accuracy requirement** while keeping production untouched until every step 2.3 gate passed (`≥95%` correctness 95% lower bound, `≥90%` recall 95% lower bound, `≥98%` quote validation 95% lower bound, `≤1%` first-attempt truncation 95% upper bound, plus the 15-question `brain/eval` end-to-end comparison).

## 3. Current state — what is true right now

- **Best-performing model confirmed & qualified (`openai/gpt-6-luna`, medium effort, three-pass `relations_messages`):**
  - Full aggregate proof and SHA-256 digests are committed in [`docs/verification/2026-11-22-pm-intake-luna-v7-qualification.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-luna-v7-qualification.md).
  - On the 30 frozen Step 2.1 held-out gold threads (zero tuning overlap, zero prompt edits after freezing `v7` on `tuning_50`):
    - **Tie-broken 2-of-3 non-author blind panel (`stage4-heldout30-v7-qualification.json`, SHA-256 `7d1c7078ede4035a7dd808e5502d34b61c8582b3a4e84329c699a0c6e8f177f0`):** `30/30` first-attempt OK (`0` truncations), **`196/196 = 100.00%` quote validation** (`LB 100.00% >= 98%`), **`193/196 = 98.47%` correctness** (`LB 97.40% >= 95%`), and **`50/52 = 96.15%` Step 2.1 lead source-first recall** (`LB 94.12% >= 90%`).
    - **Full 3-of-3 non-author audit where all three judges grade every claim (`stage4-heldout30-v7-full3j-audit.json`, SHA-256 `a219f4e315bd5b5e1da67f0b235b072715f90a3721e09fa303f38037c5247e7f`):** `196/196` claims with all 3 votes (`j-glm-flash 97.96%`, `j-deepseek 92.86%`, `j-haiku-med 90.31%`), **`191/196 = 97.45%` correctness** (`LB 95.57% >= 95%` both weighted and unweighted; `0` `timing_status`, `0` `scope_stance`, and `0` `description_exact` misses), and **`49/52 = 94.23%` Step 2.1 lead source-first recall** (`LB 90.48% >= 90%` both weighted and unweighted).
  - **Full 350-thread held-out truncation & quote qualification (`stage4-heldout350-w3000-qualification.json`, SHA-256 `7936a13d25837c4e6bceef87c4950a29820635adcde2cd97d946d4248ec47a5f`):** `initial_30_identical_to_v7: true`, **`0 / 350` first-attempt truncations** (`0` in `initial_150`, `0` in `added_200`; exact conditional 95% upper bound **`0.78% <= 1.00%` PASS**), **`100.00%` quote validation** (`3,840` unique validated claims, `LB 100.00% >= 98.00%` **PASS**), and **`$1.1800` total native batch cost across all 350 threads** (`$1.3611` per 1,000 standard 400-token passages / `$3.37` per 1,000 threads, or `~$11.37` for all `3,373` staged PM threads).
  - **15-question `brain/eval` end-to-end Company Map comparison (`stage4-15q-e2e-eval.json`, SHA-256 `cf415277a317a35600f6c0222398957a23266d6be2b7e93ab72ef5fd5617547d`):** `winner_luna_v7_multipass` scored **`0.7118` `mean_score`** (`0.6889` legacy, `0.6255` supported share, `0/15` errors), outscoring both `reference_relations_md_luna` (`0.6361`, **`+0.0757`**) and `step21_gold_reference` (`0.6040`, **`+0.1078`**) (**PASS**).
- **Runtime `relations_messages` seat & three-pass extractor landed on `main` (production untouched and off):**
  - [`apps/brain/brain/sql/040_message_relations_seat.sql`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/040_message_relations_seat.sql) — idempotently widens `cmap.model_seat`'s `model_seat_stage_check` to include `relations_messages` and all stages in `STAGES`.
  - [`apps/brain/brain/seats.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/seats.py), [`apps/brain/brain/config.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/config.py), [`apps/brain/brain/api/models.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/models.py), [`apps/brain/deploy/compose.coolify.yaml`](https://github.com/u2giants/theoracle/blob/main/apps/brain/deploy/compose.coolify.yaml), [`.env.example`](https://github.com/u2giants/theoracle/blob/main/.env.example), [`docs/configuration.md`](https://github.com/u2giants/theoracle/blob/main/docs/configuration.md), and [`docs/agents/12-credentials-and-environment.md`](https://github.com/u2giants/theoracle/blob/main/docs/agents/12-credentials-and-environment.md) — adds `relations_messages` stage + `BRAIN_MESSAGE_RELATIONS_MODEL` + `message_relations_chosen()`.
  - [`apps/brain/brain/prompts/relations_messages.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages.md), [`apps/brain/brain/prompts/relations_messages_audit.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages_audit.md), [`apps/brain/brain/prompts/relations_messages_gate.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages_gate.md), and [`apps/brain/brain/extract/relations.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py) — executes the 3-pass `relations_messages` pipeline + `_sanitize_message_payload` on `origin IS NOT NULL` sources whenever `message_relations_chosen(settings)` is true (`668/668` `pytest` tests green; `ruff` clean).
- **Companion [#664](https://github.com/u2giants/theoracle/issues/664) SFT dataset sealed in sandbox (`tuning50_sft_input.jsonl`):** `367` verified `keep` claims across `50` tuning threads (`58` windows, `0` holdout overlap, SHA-256 `37d944656c8f5f24cacb470827c85dffc2cce0c51fb882b295c2bff69fa58dab`) ready if `#664` later offloads bulk extraction to prepaid Google Colab GPUs (`#664` remains independent and non-blocking for `#607`).
- **Production state:** Completely untouched (`BRAIN_INTAKE_ENABLED` stays `false`, `BRAIN_MESSAGE_RELATIONS_MODEL` unset in production Coolify until step 3.1 pilot, interview bot `#518` off).
- **Handoff housekeeping (`AGENTS.md` §3a successor rule):** Retired four superseded `#607` Step 2.3 handoffs (`2026-11-20T1258Z-edge-dev3-codex-intake-relations-bakeoff.md`, `2026-11-20T2108Z-edge-dev3-codex-intake-blind-review.md`, `2026-11-22T0202Z-edge-dev3-codex-intake-expanded-sample.md`, and `2026-11-22T0302Z-edge-dev-agy-intake-step23-gated-stop.md`) after verifying all their commits are on `main`, carrying forward all open downstream obligations (2.4, 2.5, 3.1, 3.1a, 4.1) in [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md) and §6 below, and preserving all dead ends/decisions in `docs/verification/` and §§4–5 below. Retained `2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md` solely because companion `plan_colab_gpu_offload.md` (currently being updated by an active `#664` session) links to it locally, avoiding a cross-session merge collision; `#664` can retire `0053Z` once its local link moves to `docs/verification/`.

## 4. Everything we tried that did NOT work

- **OpenAI Cloud Fine-Tuning API (`POST https://api.openai.com/v1/fine_tuning/jobs`):** Tested across `gpt-6-luna`, `gpt-5.6-luna`, `gpt-5.4-mini-2026-03-17`, and `gpt-4.1-mini-2025-04-14`; all returned `HTTP 403` (*"OpenAI is winding down the fine-tuning platform and your organization is no longer able to create new fine-tuning training jobs"*). Do not build an OpenAI cloud fine-tuning path.
- **Forcing verbatim noun-phrase substring endpoints + rewriting `Person->Person` to `HANDS_OFF_TO` (`Iter 3 / v6` on `tuning_50`):** Regressed non-author precision from `95.24%` to `68.59%` (`262/382`) and recall from `90.24%` to `65.84%` (`106/161`) because conversational pronouns ("we", "can you check") lack adjacent clean noun-phrase substrings and routine questions between two people are not workflow handoffs. Keep natural canonical entity names and forbid `Person->Person APPLIES_TO` without forcing `HANDS_OFF_TO`.
- **Aggressive Pass 2 drop instructions (`Iter 5 / v8` on `tuning_20`):** Telling Pass 2 to aggressively drop any claim that wasn't indisputable caused it to drop `31/64` (`48%`) valid operational facts, collapsing recall to `48.78%` (`20/41`) and precision to `67.65%` (`23/34`). Keep the `v5`/`v7` **rewrite-and-narrow** rule: drop only `operational = N` noise, and rewrite any borderline `type`/`stance`/actor claim to `APPLIES_TO` + `stance = "report"` + exact single-turn quote.
- **Unsplit `18`-turn megaslices with `8,000` Pass 3 output cap vs sub-400-token turn chopping (`stage4-heldout350-v7-expansion.json`, `stage4-heldout30-w600-full3j.json`):** Grouping up to `18` unsplit email turns into one window produced `4,500–10,422`-token slices (`101` claims in one slice) that hit `status = "incomplete"` on `5/350` threads when Pass 3 used `max_output_tokens = 8000` (`1.56%` truncation UB `> 1%`), whereas chopping single turns mid-thought at `400` tokens (`w600`) fragmented intra-turn context (`94.40%` precision, `86.54%` recall). Keeping turns intact up to `12,000` characters (`3,000` tokens), splitting only `> 12,000`-character mega-emails on turn/paragraph boundaries `<= 8,000` characters, raising all three passes to `16,000` max output tokens, and batching Pass 3 into `<= 25`-claim chunks (`w3000`, matching [`relations.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py)) eliminated all truncations (`0/350`) while preserving `100%` byte-identical outputs on `initial_30`.
- **OpenRouter `z-ai/fp8` ZDR provider tag & un-rescued `z-ai/glm-5.3-flash` JSON calls:** `z-ai/fp8` was retired from OpenRouter's ZDR endpoint list (use `fireworks/us` or `parasail/fp8` / `baseten/fp8`), and calling `z-ai/glm-5.3-flash` without `post_chat_with_rescue` or bounded `reasoning.max_tokens` can return `content: null` when reasoning consumes the output budget.
- **OpenAI `/v1/responses` `json_object` format without `"json"` in `input`:** Returns HTTP 400 (`error: 20`) unless the literal word `"JSON"`/`"json"` appears in the `input` messages.

## 5. Root causes and key findings

- **Why single-pass models failed `95%` correctness on messages while three-pass `GPT-6 Luna` passed (`97.45%–98.47%`):** On informal chat/email/ClickUp turns, even frontier `Claude Opus 5.5` (`39.5%`) and `GPT-6.2 Sol` (`38.1%`) fail `prompts/relations.md` because single-pass extraction conflates situational task requests, ClickUp assignees, and folder paths with permanent `OWNS`/`PRODUCES`/`PART_OF`/`policy` claims. Splitting message extraction into Pass 1 (`relations_messages.md` high-recall turn scan with `new_mentions`), Pass 2 (`relations_messages_audit.md` 6-criterion narrowing rewrite + missed-fact check), and Pass 3 (`relations_messages_gate.md` independent 6-criterion precision gatekeeper) plus deterministic `_sanitize_message_payload` single-turn quote cleaning solves both recall (`94.23%–96.15%`, LB `90.48%–94.12%`) and precision (`97.45%–98.47%`, LB `95.57%–97.40%`) at `$1.3611` per 1,000 standard 400-token passages (`$2.5935` per 1,000 turn-packed passages / `$3.37` per 1,000 threads) in native batch (`~$11.37` for the entire 3,373-thread backlog).
- **Flat-stage mention bottleneck bypassed safely:** Because [`relations_messages.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages.md) instructs Pass 1/2 to emit missing operational endpoints in `new_mentions` and [`relations.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py) skips `passage_kind == "chatter" and not chunk_mentions` suppression when `message_mode=True`, flat-stage entity misses no longer cap relation recall at `35%–41%`.

## 6. Exact next steps

1. **Execute Step 2.4 — Batch and cached-prefix sending path ([`plan_pm_message_intake.md` step 2.4](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md#phase-2--choose-the-cheapest-models-that-pass-context-cut-point-start-a-fresh-session-here)):**
   - Check OpenAI's direct `/v1/batches` (`gpt-6-luna` native batch, 50% discount) vs OpenRouter synchronous/pinned routing for the three-pass `relations_messages` pipeline (Pass 1 batch → Pass 2 batch → Pass 3 batch per job, falling back cleanly to synchronous `_process_window` when the direct batch key `OPENAI_API_KEY` is unset).
   - Measure prompt-cache hit share across a 100-passage sandbox run first (note: [`relations_messages.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages.md), [`relations_messages_audit.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages_audit.md), and [`relations_messages_gate.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/relations_messages_gate.md) put variable `CONTEXT`/`PASSAGE` near the top; moving fixed instructions above `MENTIONS`/`CONTEXT`/`PASSAGE` may increase OpenAI automatic prefix caching — **if you reorder any prompt text, you MUST re-run the 30-thread Step 2.3 qualification check to confirm all four gates still pass**).
   - Add `apps/brain/brain/llm_batch.py` + `apps/brain/tests/test_llm_batch.py` (mocked success, partial failure, expiry, duplicate/foreign passage IDs — including §9a `test_result_id_mismatch_rejected`).
   - *You'll know it worked when:* `uv run pytest tests/test_llm_batch.py` passes and a 100-passage live sandbox batch run on gold finishes within 10% of the forecast batch price (`~$1.36` per 1,000 standard 400-token passages / `~$2.59` per 1,000 turn-packed passages).

2. **Execute Step 2.5 — Business-area sorting with ScaleDown `/classify` ([`plan_pm_message_intake.md` step 2.5](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md#phase-2--choose-the-cheapest-models-that-pass-context-cut-point-start-a-fresh-session-here)):**
   - Calibrate ScaleDown `/classify` (`"reasoning": false`, labels built dynamically from active `cmap.function` rows in [`apps/brain/brain/function_assign.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/function_assign.py)) strictly on the `50` tuning threads in `oracle-sandbox-private`.
   - Score on the `30` Step 2.1 held-out threads against pooled blind passage function labels: require 95% lower bounds `≥90%` main function right, `≥85%` gold functions found, and 95% upper bound `≤10%` wrong picks, plus re-run `tests/test_answer.py::test_scoped_answer_excludes_other_functions` and the 15-question `brain/eval` check with zero drop.
   - Add `tests/test_functions.py` (`test_scaledown_labels_built_from_function_table`, `test_scaledown_scores_become_weights_top_three`, `test_scaledown_failure_falls_back_to_model`, `test_priors_still_apply_on_scaledown_path`). If ScaleDown misses any gate, seat `openai/gpt-6-luna` (never a frontier model) for message `function_assign` and record measured cost per 1,000 passages in `docs/verification/` and on [#607](https://github.com/u2giants/theoracle/issues/607).
   - *You'll know it worked when:* `uv run pytest tests/test_functions.py tests/test_answer.py` is green, the verification table is committed under `docs/verification/`, and Step 2.5 is marked `✅ done` in [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md).
   - **Reciprocal end-of-phase check:** At the end of Phase 2 (and each phase after), re-read every remaining downstream phase through Step 5.1 in [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md) and record/report any drift in `STATUS` and on [#607](https://github.com/u2giants/theoracle/issues/607) before handing forward.

3. **Execute Step 3.1 (14-day production pilot) and Step 3.1a (Ilona's Brain-generated question comparison):**
   - Declare `ai-task-gates start --class production` (and check `docs/standing-rules-details.md` + [`docs/agents/13-deployment.md`](https://github.com/u2giants/theoracle/blob/main/docs/agents/13-deployment.md)).
   - Seat `openai/gpt-6-luna` on `relations_messages` (`BRAIN_MESSAGE_RELATIONS_MODEL=openai/gpt-6-luna` or `PUT /models/seats/relations_messages`), set `BRAIN_INTAKE_MAX_USD` from the verified forecast, verify `038_intake_sources.sql` and `040_message_relations_seat.sql` are applied on production, and run the 14-day literal project-manager cohort through `recommend` while keeping the Teams interview bot off (`#518`).
   - Audit 20 randomly sampled dropped threads, record stage spend, quote validation rate, cost per kept thread, and full-company cost projection on [#607](https://github.com/u2giants/theoracle/issues/607), and complete Step 3.1a's private Brain-generated question comparison + ClickUp history check.
   - *You'll know it worked when:* the live `/map` project-management function page displays message-backed processes and people with verbatim source quotes within `BRAIN_INTAKE_MAX_USD`, and pilot cost + projection are ready for Albert's §0 Checkpoint 1.

4. **Execute Step 4.1 (90-day full window & live proof preparation):**
   - Run the 90-day window, ask five project-management questions on the live web app confirming message-derived citations, and present the function page + generated (unsent) interview questions to Albert per §0 Checkpoint 2 while leaving `- [ ] live proof` open on [#607](https://github.com/u2giants/theoracle/issues/607) until he accepts.

## 7. Constraints and gotchas in force

- **Zero private text outside `/sandbox` (`L7`):** Never print or commit message bodies, verbatim quotes, employee/customer/vendor names from private threads, email addresses, or raw verdicts.
- **No frontier cloud models (`L9`):** Never use Opus, Sol, GLM MAX, or Hydrogen for extraction, retries, function sorting, or routine grading.
- **Prompt-hash & gate lock:** [`relations.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py) hashes all three `relations_messages*.md` files together (`message_relations_prompt_hash()`); any edit to those three files invalidates extraction cache and requires re-verifying the Step 2.3 gates on `initial_30`.
- **Ephemeral OpenRouter keys in sandbox:** Always mint short-lived capped keys in workspace `oracle-pm-intake-sandbox` attached to guardrail `"Oracle 607 no retention"` and `DELETE /api/v1/keys/{hash}` in `finally`.
- **Canonical checkout discipline:** Keep the canonical repository checkout on clean `main`; create a fresh git worktree from `origin/main` before editing.

## 8. Access and environment

- **Coolify host & private sandbox:** SSH `vps2-direct`, container `quote-tools-lh8tiwrst3hwij9yr3ss4vdx` mounting volume `lh8tiwrst3hwij9yr3ss4vdx_sandbox-evidence` at `/sandbox`.
- **1Password vault `vibe_coding` (item IDs only — never print secret values):**
  - Service account token provisioned by `ai-devops` workstation setup (`OP_SERVICE_ACCOUNT_TOKEN` via `op-service-account`).
  - OpenAI direct API key (for `gpt-6-luna` native batch / responses): item `3onekcbg3dxnazpnt36d4yzfcq`, field `6tez7ajfmk4eogwywl75talobm`.
  - Anthropic direct API key: item `5uq6z66ibusmypkvnl276ta22e`, field `credential`.
  - OpenRouter Management API key (`oracle-pm-intake-sandbox` ephemeral keys): item `vqk7qypdfdqog6bo7r6f63zz5m`, field `credential`.
  - ScaleDown API key (for step 2.5): see [`docs/agents/12-credentials-and-environment.md`](https://github.com/u2giants/theoracle/blob/main/docs/agents/12-credentials-and-environment.md).
- **Sandbox qualification directory (`/sandbox/records/step-2.3-relations/stage4-luna-95-tuning/`):**
  - `iter1-v4-tuning20.json`, `iter2-v5-tuning20.json`, `iter4-v7-tuning50.json`
  - `tuning50_sft_input.jsonl` + `tuning50_sft_input.manifest.json` (`#664` Step 2.1 SFT input)
  - `heldout30_v7_ckpts/`, `heldout350_w3000_ckpts/`
  - `stage4-heldout30-v7-qualification.json`, `stage4-heldout30-v7-full3j-audit.json`, `stage4-heldout350-w3000-qualification.json`, `stage4-15q-e2e-eval.json`

## 9. Open questions and risks

- **Risk (dated 2026-11-22):** Three sequential passes per chunk (`Pass 1 -> Pass 2 -> Pass 3`) multiply synchronous wall-clock latency by ~2.6× (`~350` threads took ~10 minutes at 14 workers). Step 2.4's batch path should submit all pending chunks' Pass 1 requests as Batch 1, Pass 2 as Batch 2, and Pass 3 as Batch 3 (3 batch rounds total regardless of source count, rather than 3 serial batch waits per chunk).
- **Risk (dated 2026-11-22):** Moving fixed rubric text above `CONTEXT`/`PASSAGE` in `relations_messages*.md` for step 2.4 prefix caching could subtly shift attention weights; measure cache hit share first and re-verify `initial_30` gates if prompt layout changes.
- **Companion `#664` status (dated 2026-11-22):** A sibling `#664` session is independently evaluating open-weight / QLoRA Google Colab offload in its own worktree (`plan_colab_gpu_offload.md`); `#664` does not block `#607` now that cloud `GPT-6 Luna` passed step 2.3.

---

## Self-audit (`handoff-writer` mandatory 4-question gate)

1. *Is this file comprehensive enough that a brand-new developer with no project knowledge and no session context could pick up where I left off and not skip a beat?* **Yes** — §1 defines The Oracle, its public-repo privacy boundary, and runtime services; §3 lists every landed file by GitHub URL and every sandbox proof digest; §6 gives ordered, gate-checked instructions for steps 2.4, 2.5, 3.1, 3.1a, and 4.1; §8 gives exact SSH, container, volume, and 1Password item IDs.
2. *Is it detailed enough that they could continue as well as I could right now, with all my session knowledge and the relevant background and purpose?* **Yes** — §4 and §5 document every dead end (`OpenAI /v1/fine_tuning/jobs 403`, `v6` forced substring endpoints, `v8` aggressive Pass 2 drops, unsplit megaslice truncation vs `w600` chunking, retired `z-ai/fp8` ZDR tag, OpenAI `/v1/responses` `"json"` input requirement) and why 3-pass `relations_messages` solved the precision-recall trade-off.
3. *Is every single relevant detail needed for flawless execution included: background, goals, intended outcome, current state, failures, decisions, constraints, risks, exact next actions, and verification evidence?* **Yes** — §§0–9 cover every dimension with portable GitHub URLs, SHA-256 digests, test commands, and explicit 3-round batch design guidance in §6.1 and §9.
4. *If the owner read ONLY section 0, would he see every business decision I need from him — including ones outside this workstream — and no technical approval at all?* **Yes** — walked §§1–9 line by line: steps 2.4 and 2.5 need zero owner input, both downstream business checkpoints (post-pilot `L1` exact-quote cost review and post-4.1 live-proof acceptance) are consolidated in §0 with clear recommendations, settled rulings are listed so they are not re-asked, and technical `#664` status is kept in §9 out of §0.

## Next-session prompt

```
Resume #607 on main of https://github.com/u2giants/theoracle at Step 2.4 (Batch + cached-prefix sending path) and Step 2.5 (ScaleDown business-area sorting).
Read AGENTS.md, https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md (STATUS first),
https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-luna-v7-qualification.md,
and https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0525Z-edge-dev-agy-intake-step24-batch-and-cache.md.
Three-pass GPT-6 Luna (relations_messages) is qualified and wired on main; keep production off until Steps 2.4 and 2.5 pass their gates.
```
