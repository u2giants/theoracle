---
issue: 664
status: OPEN
owner: docs/colab-gpu-offload-plan
---

# Handoff — Google Colab GPU batch offload and fine-tuning plan (#664)

Registered plan (direct relative link): [../plan_colab_gpu_offload.md](../plan_colab_gpu_offload.md) (`https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md` once merged to `main`).
Tracking issue: https://github.com/u2giants/theoracle/issues/664.

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

**None blocking implementation of Phases 0–3 or sandbox proof (Step 4.1) — nothing in this workstream needs Albert before work starts.**

If a downstream milestone or an adjacent workstream later reaches one of the business checkpoints below, the implementing session must present any open business questions together in **one** concise plain-English message (never asking technical approvals):

- **Not blocking now — downstream `#607` post-pilot business checkpoints (already tracked on `#607`):**
  1. *Whether to keep the exact-verbatim-quote rule after seeing measured 14-day pilot cost and Colab Compute Unit (CCU) usage projected across all employees.* **Recommendation:** Keep exact verbatim quotes, especially once Colab GPU offload drops marginal relation-extraction API cost toward `$0`. Blocks only post-pilot expansion (`#607` Step 4.1), not Phases 0–3 here.
  2. *Final live-proof look on the Company Map project-management page and unsent interview questions after full run.* **Recommendation:** Show five evidence-backed answers and the unsent question list once `#607` Step 4.1 and `#664` Step 4.2 finish. Blocks closing `- [ ] live proof` on `#607` and `#664`.
- **Conditional only (raise ONLY if `#607` Step 2.3's held-out pool lacks enough independent threads to prove the `<=1%` truncation bound mathematically):**
  - Per [the `#607` Luna reconciliation handoff](https://github.com/u2giants/theoracle/blob/aa15025a9d37/HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md#L38), proving `<=1%` one-sided 95% truncation upper bound requires at least 299 independent zero-truncation threads (versus 150 currently frozen). If the approved 2-manager pool cannot supply 149 more independent held-out threads, present Albert with the exact shortfall and **recommend** widening the held-out sample window slightly so the statistical bound can be proven without weakening the `1%` rule.

### Already settled — do NOT re-ask
- **Integrate prepaid Google Colab compute units into The Oracle (2026-11-21):** Authorized by Albert in chat (*"make a plan to integrate it into The Oracle"*).
- **No frontier cloud API bills for bulk intake (2026-11-18, `#607` L9):** *"we can't afford frontier models."*
- **Keep exact verbatim quotes through the pilot (2026-11-19, `#607`):** *"ok, keep exact words through the pilot."*
- **Authorized mailboxes, private/group Teams chats, and ClickUp for the two project managers, unannounced (2026-11-18, `#607`):** Settled in [plan_pm_message_intake.md](https://github.com/u2giants/theoracle/blob/aa15025a9d37/plan_pm_message_intake.md#L48).
- **Never ask Albert to click, run commands, open notebooks, or approve technical steps (2026-09-28 / 2026-10-29 standing rulings):** AI sessions run Colab headlessly via CLI and merge PRs themselves.

---

## 1. What this application is

**The Oracle** is the Company Map and evidence-backed adviser for POP Creations / Spruce Line. It reads company documents, diagrams, meeting transcripts, Teams chats, ClickUp tasks, and authorized email into a graph of how departments operate, answers employee questions in English and Mandarin with verbatim source quotes, and interviews employees over Microsoft Teams to fill gaps.

- **Repository:** https://github.com/u2giants/theoracle (**PUBLIC** — single protected branch `main`).
- **Web app (`apps/web`):** Next.js 16 on Vercel (`https://oracle.designflow.app`), documented in [README.md](https://github.com/u2giants/theoracle/blob/aa15025a9d37/README.md) and [docs/architecture.md](https://github.com/u2giants/theoracle/blob/aa15025a9d37/docs/architecture.md).
- **Brain service (`apps/brain`):** Python 3.12+ FastAPI API and background worker on Coolify (`oracle-brain`, `https://oracle-brain.designflow.app`, image `ghcr.io/u2giants/theoracle-brain`), owning Supabase Postgres schema `cmap` and FalkorDB graph `company`.
- **Private Coolify sandbox:** Separate isolated Coolify brain + Postgres environment holding `#607` private message-intake threads, gold annotations, and benchmark artifacts ([sandbox custody details](https://github.com/u2giants/theoracle/blob/aa15025a9d37/HANDOFF.d/2026-11-20T2108Z-edge-dev3-codex-intake-blind-review.md#8-access-and-custody)).

---

## 2. What we set out to do this session, and why

Albert cloned `u2giants/theoracle` to inspect whether his **Google AI Ultra** allotment of **2,000 monthly Google Colab Compute Units (CCUs)** can help run or build The Oracle, then asked for a complete standalone implementation plan (`implementation-plan-writer` standard) to integrate Colab into The Oracle.

**Business & technical objective:** Turn Albert's unused 2,000 monthly Colab Compute Units into an automated, headless GPU batch worker and QLoRA fine-tuning pipeline for `apps/brain` — solving `#607`'s Step 2.3 cost-vs-correctness bottleneck (3,373 pending message threads where every cheap cloud API missed the `>=95%` correctness gate while frontier APIs are cost-prohibitive) without putting ephemeral Colab VMs in the live web/Teams request path.

---

## 3. Current state — what is true right now

- **Base commit inspected:** [`aa15025a9d37`](https://github.com/u2giants/theoracle/commit/aa15025a9d37) (`main` as of 2026-11-21 8:55 PM EST).
- **Tracking issue opened:** https://github.com/u2giants/theoracle/issues/664 (includes phase checklist and `- [ ] live proof`).
- **Plan & router docs written and landing on `main` in this session's PR:**
  - Implementation plan: [../plan_colab_gpu_offload.md](../plan_colab_gpu_offload.md) (`https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md`).
  - Router & doc-map updates: [AGENTS.md](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [docs/agents/03-documentation-map.md](https://github.com/u2giants/theoracle/blob/main/docs/agents/03-documentation-map.md), [docs/company-map/model-stage-job-brief.md](https://github.com/u2giants/theoracle/blob/main/docs/company-map/model-stage-job-brief.md), and regenerated [docs/INDEX.md](https://github.com/u2giants/theoracle/blob/main/docs/INDEX.md).
- **Application code state:** Zero runtime code or database schema has been modified yet (`STATUS` rows `0.1`–`4.2` in `plan_colab_gpu_offload.md` are all `⬜ open`). Production (`oracle.designflow.app` and `oracle-brain.designflow.app`) and the private Coolify sandbox are completely untouched.
- **Verified landmarks for the implementer:**
  - Provider chat seam: [apps/brain/brain/llm.py#L40-L250](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/llm.py#L40-L250).
  - Model seats: [apps/brain/brain/seats.py#L22-L157](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/seats.py#L22-L157).
  - Settings: [apps/brain/brain/config.py#L15-L92](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/config.py#L15-L92).
  - Relations prompt building, quote validation (`find_quote`, `validate_response`), idempotency (`_load_done`), and source completion (`handle_relations`): [apps/brain/brain/extract/relations.py#L207-L952](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/extract/relations.py#L207-L952).
  - FastAPI auth & app router: [apps/brain/brain/api/deps.py#L38-L100](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/api/deps.py#L38-L100) and [apps/brain/brain/main.py#L22-L34](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/main.py#L22-L34).
  - Latest `cmap` SQL migration: [apps/brain/brain/sql/038_intake_sources.sql](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/sql/038_intake_sources.sql) (next available number: `039_colab_leases.sql`, re-verify before creating).

---

## 4. Everything we tried that did NOT work

No runtime experiments failed this session (this was a research + architecture planning session), so this section records both **already-measured `#607` model failures** and **architectural dead ends explicitly ruled out** so the implementing session never walks into them:

1. **Failed in `#607` Step 2.3 — All four low-cost cloud API candidates + fallback missed the `>=95%` correctness gate:**
   - Documented in [docs/verification/2026-11-20-pm-intake-relations.md](https://github.com/u2giants/theoracle/blob/aa15025a9d37/docs/verification/2026-11-20-pm-intake-relations.md) and [HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md#L28](https://github.com/u2giants/theoracle/blob/aa15025a9d37/HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md#L28): synchronous correctness topped out at `65.79%` (`57.07%` lower bound), and reconciled batch upper bounds topped out at `93.28%–94.83%` even counting every unreviewed claim as right. Do not re-run those settled cloud jobs.
2. **Dead end ruled out — Putting Colab behind an `ngrok` / `cloudflared` tunnel as `oracle-brain`'s live `relations` endpoint:**
   - Colab VMs recycle, hit session ceilings, and stop if CCUs run out; live interview replies (`awaits_reply(source_id)` at [relations.py#L985](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/extract/relations.py#L985)) would stall or fail, and inbound public tunnels create unnecessary exposure.
3. **Dead end ruled out — Putting `DATABASE_URL` / `DIRECT_URL` or `OPENROUTER_API_KEY` inside Colab:**
   - Violates least privilege and production read-only safety. Pull leases (`BRAIN_COLAB_WORKER_TOKEN`) expose only the leased prompt batch and enforce all validation inside `apps/brain`.
4. **Dead end ruled out — Adding `torch`, `vllm`, `peft`, or `bitsandbytes` to [apps/brain/pyproject.toml](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/pyproject.toml):**
   - Would bloat `ghcr.io/u2giants/theoracle-brain` by >8 GB and blow GitHub Actions runner disk limits in `brain-image.yml`. GPU packages belong exclusively in `apps/brain/colab/requirements-colab.txt`.
5. **Dead end ruled out — Holding `cmap.job` rows >30 minutes waiting for Colab:**
   - Violates the standing 30-minute hold ceiling. Lease TTL is capped at `15 minutes` (`900s`, DB-enforced `<= 30 minutes`).

---

## 5. Root causes and key findings

1. **`cmap.extraction` is already chunk-idempotent by `(chunk_id, stage, prompt_hash)` ([001_cmap.sql#L41](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/sql/001_cmap.sql#L41), [relations.py#L607-L616](https://github.com/u2giants/theoracle/blob/aa15025a9d37/apps/brain/brain/extract/relations.py#L607-L616)):**
   - This makes ephemeral GPU workers a natural fit: if a Colab VM dies mid-batch, any unsubmitted chunk simply expires its 15-minute lease and gets leased to the next worker (or processed by `handle_relations` when `BRAIN_COLAB_LEASE_ENABLED=false`) with zero corruption.
2. **Official `google-colab-cli` (`googlecolab/google-colab-cli`) eliminates manual notebook operation:**
   - Installed via `uv tool install google-colab-cli`, it provisions L4/A100 GPUs from Albert's AI Ultra 2,000-CCU pool, runs repo scripts headlessly, and pairs with `google.colab.runtime.unassign()` in `try/finally` so idle compute units are never wasted.
3. **vLLM guided JSON + QLoRA directly attack `#607`'s two failure modes:**
   - Grammar-guided JSON decoding (`GuidedDecodingParams(json=schema)`) eliminates malformed JSON and invalid `ENTITY_TYPES`/`REL_TYPES`/`STANCES`, while QLoRA fine-tuning (~8 CCUs on an A100) on `#607`'s 50 tuning threads trains POP Creations' exact actor/stance/verbatim-quote discipline without touching the 30+120 held-out scoring threads.
4. **Task-gate rule in this repo ([.ai-devops/task-gates.json#L5-L24](https://github.com/u2giants/theoracle/blob/aa15025a9d37/.ai-devops/task-gates.json#L5-L24)):**
   - Even when editing only `AGENTS.md`, `HANDOFF.d/**`, or `plan_*.md`, `.ai-devops/task-gates.json` classifies those paths as `"code"`, so always declare `ai-task-gates start --class code` (not `prose`) when updating plan/handoff/router files!

---

## 6. Exact next steps

Execute [../plan_colab_gpu_offload.md](../plan_colab_gpu_offload.md) starting at **Step 0.1**:

1. **Step 0.1 (`lead-only`):** Install `google-colab-cli` (`uv tool install google-colab-cli`), build `apps/brain/colab/preflight.py` + `apps/brain/colab/requirements-colab.txt` + `apps/brain/tests/test_colab_preflight.py`.
   - *You'll know it worked when:* `pytest apps/brain/tests/test_colab_preflight.py` is green AND live `python -m colab.preflight --smoke --gpu L4 --max-wall-minutes 5 --max-ccu 2` prints `nvidia-smi`, exits cleanly, and leaves **0 active Colab runtimes**.
2. **Step 0.2 (`helper-ok`):** Add `brain_colab_worker_token`, `brain_colab_lease_enabled`, `brain_colab_lease_ttl_seconds` (`60..1800`), and `brain_colab_max_batch_size` to `apps/brain/brain/config.py` and document in `docs/configuration.md`.
   - *You'll know it worked when:* `pytest apps/brain/tests/test_colab_config.py` passes (including the guard proving `apps/brain/pyproject.toml` has zero GPU deps).
3. **Step 1.1 (`lead-only`):** Implement `apps/brain/brain/colab_packet.py` (`export`, `export_relations_schema`, `import` with `dry_run` mode reusing `relations.validate_response`).
   - *You'll know it worked when:* `pytest apps/brain/tests/test_colab_packet.py` proves round-trip parity with `handle_relations` and passes all packet adversarial checks.
4. **Step 1.2 (`helper-ok`):** Implement `apps/brain/colab/run_vllm_batch.py` (pinned `--hf-revision`, `trust_remote_code=False`, guided JSON schema, 64-item checkpointing, 4000-token length retry).
   - *You'll know it worked when:* `pytest apps/brain/tests/test_colab_vllm_runner.py` passes offline AND a 10-item synthetic Colab smoke yields 100% valid JSON and 0 leftover runtimes.
5. **Step 1.3 (`lead-only`):** Run 2–3 open-weight candidates on `#607`'s 50 tuning threads inside the private Coolify sandbox; commit aggregate tuning numbers to `docs/verification/2026-11-colab-openweight-tuning.md`.
   - *You'll know it worked when:* Tuning metrics and CCU/1,000-passage numbers are committed and either advance a zero-shot finalist to Step 2.2 or trigger Step 2.1 QLoRA tuning.
6. **Phases 2–4 (`Steps 2.1–4.2`):** Follow [../plan_colab_gpu_offload.md](../plan_colab_gpu_offload.md) §9 verbatim (QLoRA adapter on tuning threads if needed → blind held-out `#607` qualification → `039_colab_leases.sql` + `/colab/lease` & `/colab/submit` + `drain_leases.py` → sandbox kill-recovery & drain proof → production pilot drain proof).

---

## 7. Constraints and gotchas in force

- **Isolated git worktree required** for every write task; never edit the canonical checkout directly.
- **`ai-task-gates start --class code`** before editing code/plans/handoffs; redeclare `--class production` before Step 4.2.
- **Public repo boundary:** Zero real messages, employee emails, raw completions, or private QLoRA adapter weights in git, issues, or PRs. Run `ai-doc-safety --changed origin/main` and `ai-doc-health --repo .` before every PR/merge.
- **Never push to `main`; merge via PR with plain `gh pr merge`** (never `--admin` or `--squash`), waiting via `ai-pr-wait <pr>`. Sign every GitHub post with `ai-gh-signature` / `Posted by <App> chat ... on <machine>`.
- **Zero holds > 30 minutes:** Lease TTL stays `<= 15 minutes` (`900s`); live `awaits_reply(source_id)` interview turns never wait on Colab.
- **Do not touch `#607` predecessor handoffs** (`HANDOFF.d/2026-11-20T2108Z-...` or `HANDOFF.d/2026-11-22T0053Z-...`) — `#607` Step 2.3 is an active sibling workstream owned by those handoffs. Retire **this** handoff only when Step 0.1+ lands and carries every remaining obligation forward under the successor rule.

---

## 8. Access and environment

- **GitHub CLI (`gh`):** Authenticated as `u2giants` with `repo` and `workflow` scopes.
- **1Password vault `vibe_coding` (item titles only — never log or commit secret values):**
  - Existing ScaleDown, OpenRouter, Supabase, and Azure Graph items documented in [docs/configuration.md](https://github.com/u2giants/theoracle/blob/aa15025a9d37/docs/configuration.md) and [plan_pm_message_intake.md#L318](https://github.com/u2giants/theoracle/blob/aa15025a9d37/plan_pm_message_intake.md#L318).
  - Create `"The Oracle — Sandbox Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` and `"The Oracle — Production Brain Colab Worker Token (BRAIN_COLAB_WORKER_TOKEN)"` via `secrets-to-1password` when executing Phase 3–4.
- **Private Coolify sandbox:** Custody and `step-2.3-relations` layout documented in [HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md#L54-L57](https://github.com/u2giants/theoracle/blob/aa15025a9d37/HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md#L54-L57).

---

## 9. Open questions and risks

- **First-time `google-colab-cli` OAuth on workstation (`Step 0.1`):** If `google-colab-cli` has not yet cached an OAuth token for Albert's Google AI Ultra account and opens a protected Google login gate that automation is forbidden to click through, stop cleanly at Step 0.1 and report `Blocked —` naming the exact OAuth state (never attempt to bypass auth checks).
- **CCU burn safety:** Mitigated by `preflight.py`'s pre-check, wall-clock kill timer, and `try/finally` `runtime.unassign()` + post-run `0 active runtimes` check (locked decision L3).
- **Coordination with `#607` Step 2.3:** Keep `#607`'s blind-review calibration and held-out freeze untouched; treat Colab open-weight / QLoRA runs as additional routes evaluated under `#607`'s exact statistical gates.

---

### Handoff self-audit (handoff-writer standard)

1. *Could a brand-new developer with no project knowledge and no session context pick up where I left off and not skip a beat?* **Yes** — §1–§3 explain The Oracle, its containers, `#664`, base commit `aa15025a9d37`, and exact GitHub file:line landmarks; §6 gives concrete ordered steps with verification gates pointing into [../plan_colab_gpu_offload.md](../plan_colab_gpu_offload.md).
2. *Could they continue as well as I could right now, with all my session knowledge and purpose?* **Yes** — §2, §4, and §5 preserve why Colab fits batch offload + QLoRA tuning rather than live serving or coding, the `#607` failure numbers, the `google-colab-cli` headless teardown pattern, and the `.ai-devops/task-gates.json` `"code"` class rule.
3. *Is every relevant detail included (background, goals, current state, failures, decisions, constraints, risks, exact next actions, verification)?* **Yes** — covered across §0–§9 and cross-linked to `plan_colab_gpu_offload.md` §1–§13.
4. *Line-by-line Section 0 sweep: if Albert read ONLY §0, would he see every business decision needed across §1–§9 (including adjacent `#607` items) and zero technical approvals?* **Yes** — walked §1–§9 line by line: zero technical approvals appear in §0 (OAuth/CLI setup in §9 is handled by AI or reported `Blocked —`, never asked as an approval), while downstream `#607` pilot-cost/exact-quote and conditional holdout-expansion business decisions are consolidated in §0 with explicit recommendations and "Already settled — do NOT re-ask" dates.
