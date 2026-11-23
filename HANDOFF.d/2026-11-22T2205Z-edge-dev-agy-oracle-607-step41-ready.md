---
summary: "Oracle #607 Step 4.1 handoff after completing Step 3.1 (14-day live pilot), Step 3.1a (Ilona live Brain question comparison), and #664 Step 4.2 (Colab L4 production drain)."
kind: handoff
status: OPEN
read-when: starting the #607 Step 4.1 90-day full-window run and final live-proof acceptance after Albert's post-pilot verbatim-quote ruling
issue: 607
owner: agy/oracle-607-step41-ready
---

# Handoff — Oracle `#607` Step 4.1 (90-Day Full Run & Live Proof) After Live Pilot & `#664` Colab Production Drain

- **Tracking issues:** [#607](https://github.com/u2giants/theoracle/issues/607) (project-manager message intake — only Step `4.1` + `- [ ] live proof` remain) and [#664](https://github.com/u2giants/theoracle/issues/664) (Google Colab GPU batch offload — all technical steps `0.1`–`4.2` complete; `- [ ] live proof` awaits Albert's visual sign-off alongside `#607`).
- **Plans:** [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md) and [`plan_colab_gpu_offload.md`](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md).
- **Production verification proof:** [`docs/verification/2026-11-22-pm-intake-pilot-and-colab-drain-proof.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-pilot-and-colab-drain-proof.md).
- **Predecessor handoffs retired under the successor rule (`AGENTS.md` §3a) in this closing PR:**
  - `HANDOFF.d/2026-11-22T1819Z-edge-dev-agy-oracle-607-664-consolidated-pilot.md` (verified on `main` via [`473069f9`](https://github.com/u2giants/theoracle/commit/473069f9); all `#607` Step 3.1, `#664` Step 4.2, and `#668`/`#670`/`#675`/`#680` obligations completed or carried forward below).
  - `HANDOFF.d/2026-11-22T1505Z-edge-dev-agy-intake-step31-pilot.md` (verified on `main` via PR [#679](https://github.com/u2giants/theoracle/pull/679)).
  - `HANDOFF.d/2026-11-22T1358Z-edge-dev-agy-colab-adc-vaulted-step42-gated.md` (verified on `main` via PR [#678](https://github.com/u2giants/theoracle/pull/678), [`8e38f495`](https://github.com/u2giants/theoracle/commit/8e38f495d85da80e941dc74cddf0b5ae8ab07c44)).
  - `HANDOFF.d/2026-11-22T1350Z-edge-dev3-codex-ilona-live-pilot.md` (verified on `main` via PR [#677](https://github.com/u2giants/theoracle/pull/677); Ilona `3.1a` live import and Brain question comparison completed; ClickUp actor-level change-history limitation and `#604` live referral/serial-staff continuation preserved in §§3, 4, 6, 9, and `HANDOFF.d/2026-11-19T0545Z-edge-dev-claude-604-finish.md`).
  - `HANDOFF.d/2026-11-22T0053Z-edge-dev3-codex-intake-luna-reconciled.md` (verified on `main`; all references in `plan_colab_gpu_offload.md` updated in PR [#687](https://github.com/u2giants/theoracle/pull/687), [`74625ef2`](https://github.com/u2giants/theoracle/commit/74625ef22e07012a180951be809c16553ac64f69)).

---

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Present **all** open business questions in **one** plain-English message (zero technical approvals — never ask Albert to approve a deploy, PR merge, credential, or CLI command):

1. **Blocking Step 4.1 (90-day full-window run) — post-pilot exact-verbatim-quote cost ruling (`plan_pm_message_intake.md` STATUS `2026-11-19` ruling):** Now that the 14-day two-manager live pilot (`812` kept threads) measured **`$0.0059` per kept thread** (`$4.79` steady-state across 2 weeks for 2 project managers; full-company 30-day run-rate projection **`$302.36/mo`** and 90-day backfill **`$870.26`** across all `56` active employees), confirm keeping exact verbatim quotes (`L1`) for the 90-day run (`~2,672` remaining staged PM threads, projected `~$23.13`). **Recommendation:** Keep exact verbatim quotes — three-pass `GPT-6 Luna` batch + low-reasoning `GLM-5.3 Flash` costs pennies per thread while keeping every Company Map claim backed by an exact auditable quote.
2. **Downstream after Step 4.1 completes — final live-proof business acceptance (blocks ticking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607) and [#664](https://github.com/u2giants/theoracle/issues/664)):** Review `https://oracle.designflow.app/map` (project-management processes, people, verbatim quotes, and Colab-offloaded document relations), five cited web answers on PM hand-offs/bottlenecks, and the Brain's generated (**unsent**) follow-up questions for Jessica, Carlos, and Ilona to judge question quality before re-enabling the Teams interview bot (`#518` / `#604`). **Recommendation:** Inspect the live `/map` page and unsent questions after Step 4.1 finishes, then confirm whether question quality is ready to resume `#604`'s serial interview rollout.

### Already settled — do NOT re-ask
- **Stick with qualified three-pass `GPT-6 Luna` for message intake (2026-11-22 12:46 PM EST, verbatim):** *"so stick with Luna."* Do not switch models, alternate models per message, add RAG to message extraction, or route messy chats/emails to Colab.
- **Scope & silence (2026-11-18, `L10` & `#518`):** Jessica's and Carlos's mailboxes, private/group Teams chats, and ClickUp (plus Ilona's scoped `3.1a` comparison authorized 2026-11-19) are in scope; reading is unannounced; the Teams interview bot stays **off** (`BRAIN_INTERVIEW_ENABLED=false`).
- **No frontier models in bulk intake (2026-11-18, `L9`):** *"we can't afford frontier models."* Never route extraction, retries, function sorting, or routine grading to Opus, Sol, GLM MAX, or Hydrogen.
- **Keep exact verbatim words through the 14-day pilot (2026-11-19, `L1`):** *"ok, keep exact words through the pilot."* (Pilot now complete; Checkpoint 1 above governs Step 4.1.)
- **Step 2.5 ScaleDown `/classify` business-area test (2026-11-22):** Tested and missed gates (`23.88%` wrong picks); message `function_assign` routes to `openai/gpt-6-luna`.
- **Prepaid Google Colab integration (`#664`, 2026-11-21 / 2026-11-22):** Authorized and vaulted permanently in 1Password `vibe_coding` (`whgwmjd6wvcq4rttpo6mx4367i`). Keep `BRAIN_COLAB_LEASE_ENABLED=false` by default and enable only during clean `colab_offload = true` document/transcript backfills.

---

## 1. What this application is

**The Oracle** is the Company Map and evidence-backed operational adviser for **POP Creations / Spruce Line**. It reads company documents, meeting transcripts, Teams chats, ClickUp tasks, and authorized employee email into a structured graph of how work flows across departments, answers employee questions in English and Mandarin citing exact verbatim quotes, and interviews employees over Microsoft Teams to fill knowledge gaps.

- **Repository:** [`https://github.com/u2giants/theoracle`](https://github.com/u2giants/theoracle) (**PUBLIC** — single protected branch `main`; never commit private company text, quotes, emails, private source UUIDs, LAN/tailnet IPs, or secrets).
- **Web app (`apps/web`):** Next.js 16 on Vercel (`https://oracle.designflow.app`).
- **Brain service (`apps/brain`):** Python 3.12 FastAPI + background worker on Coolify (`https://oracle-brain.designflow.app`, Coolify application `uge6pfm4qapktivto4981mtg`, image `ghcr.io/u2giants/theoracle-brain:<sha>`), backed by Supabase Cloud Postgres (`public` + `cmap` schemas) and FalkorDB (`company` graph).

---

## 2. What we set out to do this session, and why

Execute the consolidated coordinator plan in `HANDOFF.d/2026-11-22T1819Z-edge-dev-agy-oracle-607-664-consolidated-pilot.md` using parallel helper sub-agents and parallel worker pools:
1. Land all remaining pre-pilot `#607` and `#664` code/review-finding fixes (`#675`, `#680`, `#670`, `#668`, `#651`, `#644`, `#635`, `#621`, `#623`) and missing Coolify compose environment variable pass-throughs.
2. Deploy `oracle-brain` on Coolify with `relations_messages`, `process`, and `contradictions` seated to `openai/gpt-6-luna` (zero frontier models `L9`), `OPENAI_API_KEY` + `BRAIN_RELATIONS_BATCH_ENABLED=true`, `BRAIN_INTAKE_ENABLED=false`, and `BRAIN_INTERVIEW_ENABLED=false`.
3. Execute **`#664` Step 4.2** (live Google Colab `L4` GPU pull-lease drain on a genuine `colab_offload = true` production company document, verify Company Map resolution, reset `BRAIN_COLAB_LEASE_ENABLED=false`, and confirm `Active assignments: 0`).
4. Execute **`#607` Step 3.1** (14-day live pilot for Jessica and Carlos across ClickUp, Teams chats, and authorized email through `recommend`, audit 20 random dropped threads, verify live `/map` results, and compute measured cost per kept thread + full-company projection for Checkpoint 1).
5. Execute **`#607` Step 3.1a** (stage, ingest, extract, and build Ilona Kereki's `1,009` `ilona-607-v1:` focused threads in live production while `interviews_paused = true`, then capture and compare live Brain-generated questions against her 102-question baseline).

---

## 3. Current state — what is true right now

- **Deployed production `oracle-brain` (`uge6pfm4qapktivto4981mtg`):** Running [`95e5e839`](https://github.com/u2giants/theoracle/commit/95e5e8390fc869d6deac1aa52ad19597b9d4f85a) (code-identical to `HEAD` after this docs-only closeout PR), `/health` = `200 {"ok": true, "db": true, "graph": true}`, `BRAIN_INTAKE_ENABLED=false`, `BRAIN_INTERVIEW_ENABLED=false`, `BRAIN_COLAB_LEASE_ENABLED=false` (`/colab/status` verified `lease_enabled: false`), `BRAIN_INTAKE_MAX_USD=5.00`, `BRAIN_RELATIONS_BATCH_ENABLED=true`, and `/models` verified with `flat = z-ai/glm-5.3-flash` and `relations_messages / resolve / process / contradictions / reports / recommend / grade = openai/gpt-6-luna`.
- **Merged code PRs & closed issues this session:**
  - PR [#686](https://github.com/u2giants/theoracle/pull/686) ([`bb466582`](https://github.com/u2giants/theoracle/commit/bb466582fb49c16128d083e7240c5e71fea2d3ac)) — closed [#668](https://github.com/u2giants/theoracle/issues/668), [#670](https://github.com/u2giants/theoracle/issues/670), [#675](https://github.com/u2giants/theoracle/issues/675), [#680](https://github.com/u2giants/theoracle/issues/680) (+ verified/closed [#651](https://github.com/u2giants/theoracle/issues/651)).
  - PR [#687](https://github.com/u2giants/theoracle/pull/687) ([`74625ef2`](https://github.com/u2giants/theoracle/commit/74625ef22e07012a180951be809c16553ac64f69)) — capped `flat._post_chat` reasoning effort (`reasoning={"effort": "low", "exclude": True}`) and closed [#621](https://github.com/u2giants/theoracle/issues/621), [#623](https://github.com/u2giants/theoracle/issues/623), [#635](https://github.com/u2giants/theoracle/issues/635), [#644](https://github.com/u2giants/theoracle/issues/644).
  - PR [#689](https://github.com/u2giants/theoracle/pull/689) ([`84149e0d`](https://github.com/u2giants/theoracle/commit/84149e0ddbd0b79ba84d0bf122e6b439f6ad4a1b)) — guarded widened `CHECK` constraints across [`024`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/024_function_assignment.sql), [`025`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/025_source_dates.sql), [`032`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/032_contradictions.sql), [`038`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/038_intake_sources.sql), and [`040`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/040_message_relations_seat.sql) during `migrate()` replay and hardened [`llm_batch.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm_batch.py) + [`relations.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py) sibling requeue.
  - PR [#691](https://github.com/u2giants/theoracle/pull/691) ([`95e5e839`](https://github.com/u2giants/theoracle/commit/95e5e8390fc869d6deac1aa52ad19597b9d4f85a)) — moved FalkorDB `Entity(id, name, type)` index creation ahead of node/edge Cypher batches in [`project.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/graph/project.py) and bounded `/health` FalkorDB ping socket timeouts in [`main.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/main.py).
- **`#664` Step 4.2 — COMPLETE:** Drained genuine stuck `partial` uploaded company document chunk on Google Colab `NVIDIA L4` (`Qwen/Qwen2.5-14B-Instruct-AWQ@539535859b135b0244c91f3e59816150c8056698`), wrote `16` validated relations (`$0.00` cloud API spend, `0.07 CCU` consumed: `3,027.44 -> 3,027.37`), healed source `partial -> read`, verified `16` entities across `13` functions resolved on `/map`, reset `BRAIN_COLAB_LEASE_ENABLED=false`, and verified `Active assignments: 0`.
- **`#607` Step 3.1 — COMPLETE:** Ingested `812` kept 14-day threads (`3,699` chunks; `159` dropped, `20/20` random dropped-thread audit = `0` durable process loss), wrote `16,286` validated verbatim-quote relations (`98.79%` quote validation, `2` truncations, `0` frontier calls), completed full Company Map rebuild through `recommend` (`graph_version = 51`), and measured **`$0.0059` steady-state per kept thread** (`$4.79` steady-state `< $5.00` cap; `$5.08` raw incl. pre-[#687](https://github.com/u2giants/theoracle/pull/687) flat calls).
- **`#607` Step 3.1a — COMPLETE:** Ingested and verified all `1,009/1,009` `ilona-607-v1:` threads (`18,903` live relations, `graph_version = 52`, `interviews_paused = true`), capturing `1203` vetted live Brain questions vs her `102` baseline (`263` refined overlap, `940` novel evidence-backed gap questions; private comparison SHA-256 `8a56a26de6b0a6d3...`). *(Note carried forward from `2026-11-22T1350Z`: ClickUp API snapshots + paginated comments were ingested; archived actor-level field change history denied API access and remains an explicit source limitation on `#607`. Sibling `#604` live referral + remaining 3-staff serial interview run stays tracked in [`HANDOFF.d/2026-11-19T0545Z-edge-dev-claude-604-finish.md`](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-19T0545Z-edge-dev-claude-604-finish.md).)*
- **What is NOT started yet:** **`#607` Step 4.1** (90-day full-window run across the remaining `~2,672` staged PM threads + 20-thread spot-check + 5 cited web answers + enabling `BRAIN_INTAKE_ENABLED=true` for hourly ongoing intake), gated on Albert's §0 Checkpoint 1 answer.

---

## 4. Everything we tried that did NOT work

1. **Running `flat._post_chat` on `z-ai/glm-5.3-flash` without explicit `reasoning` cap:** During the first 291 chunks of Step 3.1, `flat._post_chat` ([`apps/brain/brain/extract/flat.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/flat.py)) sent `{"model": model, "messages": messages, "temperature": 0}` with no `reasoning` object. On OpenRouter, `z-ai/glm-5.3-flash` defaults to unconstrained thinking and generated `~10,600` hidden reasoning tokens per chunk (`~63s` latency and `~$0.0027`/chunk — `10.4x` costlier and `28x` slower than Step 2.2's qualified run). Passing `"reasoning": {"enabled": False}` was rejected by Z-AI on OpenRouter (`empty reply`), whereas `"reasoning": {"effort": "low", "exclude": True}` + `"response_format": {"type": "json_object"}` + `"max_tokens": 8000` works across both `z-ai/glm-5.3-flash` (`~50` reasoning tokens, `~2.2s`, `~$0.00026`/chunk) and `openai/gpt-6-luna`, while `gate_payload_for_provider` strips `reasoning` cleanly on direct Meta/OpenAI endpoints (PR [#687](https://github.com/u2giants/theoracle/pull/687)).
2. **Container startup `migrate()` failing with `CheckViolation: source_date_origin_check` once `'message_record'` rows existed:** Every `oracle-brain` boot runs `sql/001`..`040` in order. `025_source_dates.sql` unconditionally ran `DROP CONSTRAINT IF EXISTS source_date_origin_check` and re-added the pre-`038` list (without `'message_record'`), which succeeded only while zero `'message_record'` rows existed and crashed container startup once Step 3.1 ingested real threads (`024_function_assignment.sql` had the identical latent bug against `032`'s `'contradiction'` stage). Guarded all five constraint-widening migrations with `pg_constraint` checks in PR [#689](https://github.com/u2giants/theoracle/pull/689).
3. **High-concurrency workers against Supabase Session Pooler (`:5432`):** Running `>12` worker connections against `oracle_session_pooler` (`:5432`) alongside Coolify `oracle-brain` hit `EMAXCONNSESSION` (`max clients reached in session mode - pool_size: 15`). Switching transient batch/extraction boosters to Supabase Transaction Pooler (`:6543`) with `psycopg` `prepare_threshold=None` eliminated connection exhaustion completely.
4. **Uncaught `httpx.ReadTimeout` on OpenAI `service_tier="flex"` tail calls:** Under heavy concurrent batch load, individual `service_tier="flex"` calls occasionally exceeded `120s`, raising `httpx.ReadTimeout` out of `_post_flex_response`. Fixed in PR [#689](https://github.com/u2giants/theoracle/pull/689) with `240s` timeout + 3-attempt bounded retry + error-`BatchResult` capture + `try ... finally` requeue of unsettled claimed sibling `relations` jobs.
5. **Prior Phase 2 & `#664` dead ends (preserved for reference):** Single-pass L8 cloud models, RAG (`89%`), forced substring endpoints (`v6`), aggressive Pass 3 drops (`v8`), `w600` sub-turn chopping, ScaleDown `/classify` business-area softmax (`23.88%` wrong picks), OpenAI `/v1/fine_tuning/jobs` (`HTTP 403`), and Colab Qwen/QLoRA on messy chat threads (`27.27%` correctness) all failed `#607`'s `95%/90%` message gates — detailed in [`docs/verification/2026-11-22-pm-intake-luna-v7-qualification.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-luna-v7-qualification.md), [`docs/verification/2026-11-22-pm-intake-step-2-4-and-2-5-proof.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-step-2-4-and-2-5-proof.md), and [`docs/verification/2026-11-colab-relations-qualification.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-colab-relations-qualification.md).

---

## 5. Root causes and key findings

- **Pre-pilot Coolify environment traps caught and repaired:** Before this session, Coolify `oracle-brain` had `BRAIN_INTERVIEW_ENABLED=true` (left from `#604` testing), lacked `BRAIN_INTAKE_*`/`CLICKUP_API_TOKEN`/`AZURE_*` in [`compose.coolify.yaml`](https://github.com/u2giants/theoracle/blob/main/apps/brain/deploy/compose.coolify.yaml), and defaulted `process` and `contradictions` via env to `anthropic/claude-sonnet-4.5` (`L9` violation). All three are now fixed in Git and live Coolify/DB seats (`PUT /models/{stage}` requires `public.employee_identities.auth_user_id`, not `public.employees.id`, per [`deps.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/deps.py#L20-L35)).
- **Coolify API Cloudflare header & endpoint split:** Requests to `https://coolify.designflow.app/api/v1/*` with Python's default `urllib` User-Agent receive Cloudflare `403`; pass explicit `User-Agent` via `httpx`. `GET /colab/status` authenticates via `x-brain-token` (`admin_or_service`), whereas `POST /colab/lease` and `POST /colab/submit` use `Authorization: Bearer <BRAIN_COLAB_WORKER_TOKEN>`.
- **Microsoft Graph meeting transcripts (`#593`):** Re-probed `GET /users/{id}/onlineMeetings/getAllTranscripts` on 2026-11-22 -> still `HTTP 403` (Entra admin consent for `OnlineMeetingTranscript.Read.All` remains pending under `plan_meeting_triage_pipeline.md`).

---

## 6. Exact next steps (once Albert answers §0 Checkpoint 1)

1. **Confirm §0 Checkpoint 1 with Albert first.** If Albert confirms keeping exact verbatim quotes (`L1`), proceed immediately to Step 2 below; if he directs a change to `L1`, update `plan_pm_message_intake.md` STATUS first.
2. **Execute `#607` Step 4.1 (90-day full-window run):**
   - Create an isolated git worktree from `origin/main` and run `ai-task-gates start --class production` (plus `check --before production` and `check --before deploy`).
   - Refresh the 90-day staging window if needed (`clickup`, `graph_chats`, `graph_mail` with `--days 90 --people Jessica,Carlos`, then `clean.apply` with the private signature allowlist).
   - Raise `BRAIN_INTAKE_MAX_USD` on Coolify `oracle-brain` to cover the remaining `~2,672` un-ingested 90-day PM threads (`~$25.00` cap gives safe headroom above projected `~$23.13`) and run `python -m brain.intake.ingest` (unprefixed PM threads; notice Ilona's `1,009` `ilona-607-v1:` threads already have `source_id IS NOT NULL` so `ingest` skips them automatically!).
   - Drain `read_source -> classify_extract -> relations -> resolve -> project -> process_pass -> contradictions -> function_assign -> communities -> recommend` (for parallel worker boosters, connect via Transaction Pooler `:6543` with `prepare_threshold=None`, leaving `project` to Coolify `oracle-brain` so FalkorDB updates).
   - *You'll know it worked when:* `SELECT count(*) FROM cmap.intake_thread WHERE verdict = 'pending' AND source_id IS NULL` is `0`, `cmap.job` has `0` queued/running pipeline jobs, and `communities` + `recommend` completed after the last `relations` job.
3. **Run Step 4.1 quality & live-map checks + enable hourly intake:**
   - Spot-check 20 random extracted 90-day threads (`>= 98%` verbatim quote match, zero frontier calls) and run 5 real PM questions through `POST /answer` / `https://oracle.designflow.app/map`, verifying every answer cites verbatim message/ClickUp/email quotes.
   - Set `BRAIN_INTAKE_ENABLED=true` (with a bounded daily/run `BRAIN_INTAKE_MAX_USD`, e.g. `5.00`, keeping `BRAIN_INTERVIEW_ENABLED=false`) on Coolify `oracle-brain` so ongoing hourly `intake_ingest` stays live.
   - *You'll know it worked when:* `/health` = `200`, all 5 answers return `200` with cited quotes, and aggregate 90-day numbers are posted on [#607](https://github.com/u2giants/theoracle/issues/607).
4. **Present §0 Checkpoint 2 to Albert & close out:**
   - Present the live `/map` link, the 5 cited answers, and the unsent follow-up question counts to Albert. Once he accepts, tick `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607) and [#664](https://github.com/u2giants/theoracle/issues/664), mark `4.1` `✅ done` in [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md), and delete this handoff under the successor rule.

---

## 7. Constraints and gotchas in force

- **Public repo privacy (`L7`) & Colab secret boundary (`L1`):** Never put message text, verbatim quotes, emails, private thread subjects, private source UUIDs, LAN/tailnet IPs, or secret values into Git, PRs, issues, or logs. Never pass DB/Supabase/OpenRouter/shared keys onto Colab VMs.
- **Zero frontier models (`L9`) & Teams interview bot OFF (`#518`, `BRAIN_INTERVIEW_ENABLED=false`).**
- **30-minute ceiling:** Never wait/poll/hold `> 30` minutes (`MAX_POLL_DEADLINE_SECONDS = 1800.0`).
- **Supabase pooler ports:** Session pooler `:5432` caps at `15` clients; use `:6543` with `prepare_threshold=None` for multi-worker boosters, and always let Coolify `oracle-brain` execute `project` so internal `oracle-falkordb` stays current.
- **SQL migrations (`apps/brain/brain/sql/*.sql`):** `.ai-devops/task-gates.json` classifies `sql/*.sql` under `--class shared-db` even though `cmap` lives in Oracle's dedicated Supabase project; redeclare `--class shared-db` before `ai-pr-wait` if touching `sql/*.sql`, and always guard `DROP CONSTRAINT` upgrades with `pg_constraint` checks (`test_schema.py`).

---

## 8. Access and environment

- **GitHub:** `gh` authenticated as `u2giants` (`Albert Hazan <u2giants@users.noreply.github.com>`).
- **Coolify API & services:** `https://coolify.designflow.app/api/v1`; production `oracle-brain` application `uge6pfm4qapktivto4981mtg`; private evaluation sandbox `oracle-sandbox-private` service `lh8tiwrst3hwij9yr3ss4vdx` (volume `lh8tiwrst3hwij9yr3ss4vdx_sandbox-evidence` holding sealed Step 2.3 qualification receipts & QLoRA adapter `028552c75e06...`).
- **Google Colab CLI:** `google-colab-cli v0.8.0` (`colab --auth=adc`), `3,027.37` CCUs remaining, `Active assignments: 0`.
- **1Password vault `vibe_coding` (IDs/titles only — NEVER print secret values):**
  - Prod Supabase DB: `vibe_coding` item titled `Supabase - theoracle` (field `oracle_session_pooler`)
  - OpenAI direct key (`OPENAI_API_KEY`): `3onekcbg3dxnazpnt36d4yzfcq` (field `6tez7ajfmk4eogwywl75talobm`)
  - ClickUp token (`CLICKUP_API_TOKEN`): `vd5q2ryp7rm3fytxl65pkx5ysu` (field `api token`)
  - ScaleDown key (`SCALEDOWN_API_KEY`): `epna47xmzcnbdc6eb3tjpx6phm` (field `SCALEDOWN_API_KEY`)
  - Google Colab ADC (`ADC_JSON`): `whgwmjd6wvcq4rttpo6mx4367i` (field `ADC_JSON`)
  - Production Colab Worker Token (`BRAIN_COLAB_WORKER_TOKEN`): `gulz2yow5h7tkkrdsopkh4udxq` (field `BRAIN_COLAB_WORKER_TOKEN`)
  - Sandbox Colab Worker Token: `naytnzqu4ldh4t7jutxbx7btzq` (field `BRAIN_COLAB_WORKER_TOKEN`)
  - Coolify write API token: `c44ghscsnug2xvvrzzp3on7mme` (field `credential`)
  - OpenRouter Management API key (`oracle-pm-intake-sandbox`): `vqk7qypdfdqog6bo7r6f63zz5m` (field `credential`)

---

## 9. Open questions and risks

- **Checkpoint 1 owner decision (2026-11-22):** Listed in §0 item 1; gates starting Step 4.1's 90-day run.
- **ClickUp actor-level field change history (2026-11-22, carried from `2026-11-22T1350Z`):** ClickUp's archived change-history endpoint returned 403/denied; task snapshots + paginated comments are ingested, and that upstream API boundary remains documented on [#607](https://github.com/u2giants/theoracle/issues/607).
- **Sibling `#604` interview continuation (2026-11-22):** Ilona's `3.1a` live Brain question comparison is now complete while keeping `interviews_paused = true` and `BRAIN_INTERVIEW_ENABLED=false`; `#604`'s live referral + remaining 3-staff serial run continues via [`HANDOFF.d/2026-11-19T0545Z-edge-dev-claude-604-finish.md`](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-19T0545Z-edge-dev-claude-604-finish.md) when authorized.
- **Post-merge advisory `review-finding` tickets [#688](https://github.com/u2giants/theoracle/issues/688) and [#690](https://github.com/u2giants/theoracle/issues/690) (2026-11-22):** Opened asynchronously on PRs [#687](https://github.com/u2giants/theoracle/pull/687) and [#689](https://github.com/u2giants/theoracle/pull/689) (`#690`'s `locator` test finding on `f541602f` was already fixed in `84149e0d` before merge; remaining minor collector/test follow-ups can be swept alongside Step 4.1 cleanup).
- **Unrelated scheduled `Brain quality gate` noise on [#546](https://github.com/u2giants/theoracle/issues/546) (2026-11-22):** Pre-existing `no eval questions` failure on unseeded live `oracle-brain`; unrelated to `#607`/`#664`.

---

## Part (b) — Coordinator sub-agent records (session `bf9773ed`, plus prior `#664` helper records)

### Agent: `65013050` (`Compose Env & Colab Lease Helper`, `flash` — session `bf9773ed`)
- **Asked to do:** Wire missing `#607` / Graph / Meta / DesignFlow env vars into [`compose.coolify.yaml`](https://github.com/u2giants/theoracle/blob/main/apps/brain/deploy/compose.coolify.yaml) + [`configuration.md`](https://github.com/u2giants/theoracle/blob/main/docs/configuration.md) and fix [#668](https://github.com/u2giants/theoracle/issues/668) (`colab.py` `finish_reason == "length"` salvage + immediate `skipped_ids` cleanup, `colab_packet.py` `SELECT ... FOR UPDATE` source lock, `chain.py` 30-minute Colab fallback).
- **Actually did:** Implemented all four fixes and unit tests (`test_deploy.py`, `test_colab_api.py`, `test_colab_packet.py`, `test_chain.py`). Lead verified and patched one additional `failed=(state == "failed")` propagation in `colab_packet.py`.
- **Found:** Confirmed `compose.coolify.yaml` had omitted `BRAIN_INTAKE_*`, `CLICKUP_API_TOKEN`, and `AZURE_*`.
- **PR / branch:** Merged in PR [#686](https://github.com/u2giants/theoracle/pull/686) ([`bb466582`](https://github.com/u2giants/theoracle/commit/bb466582fb49c16128d083e7240c5e71fea2d3ac)).
- **Worktree:** Finished (worktree removed and sub-agent terminated).
- **Deliberately did NOT do, and why:** Did not touch production Coolify, 1Password, or SQL files (`lead-only`).

### Agent: `25b77523` (`Message Relations & Seats Helper`, `flash` — session `bf9773ed`)
- **Asked to do:** Fix [#675](https://github.com/u2giants/theoracle/issues/675) (`_clean_message_quote` colon/header guard, skip duplicate 16k truncation retry on `relations_messages`, `seat_report`/`stage_model` alignment) and [#680](https://github.com/u2giants/theoracle/issues/680) (`handle_relations` sibling `failed` state + `_enqueue_resolve()`, `llm.py` dual `openai/*` vs `openai-api/*` fallback).
- **Actually did:** Implemented all fixes across [`relations.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py), [`seats.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/seats.py), and [`llm.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/llm.py) with regression tests (`test_relations.py`, `test_model_seats.py`, `test_llm.py`).
- **Found:** Verified ClickUp `Task name:` / `Status:` and in-body `Reminder:` colons are preserved verbatim while genuine speaker prefixes still strip cleanly.
- **PR / branch:** Merged in PR [#686](https://github.com/u2giants/theoracle/pull/686) ([`bb466582`](https://github.com/u2giants/theoracle/commit/bb466582fb49c16128d083e7240c5e71fea2d3ac)).
- **Worktree:** Finished (worktree removed and sub-agent terminated).
- **Deliberately did NOT do, and why:** Did not modify `prompts/relations_messages*.md` (preserving `message_relations_prompt_hash()`) or run live production extraction (`lead-only`).

### Agent: `417c75d4` (`Bakeoff Bounds & Ingest Helper`, `flash` — session `bf9773ed`)
- **Asked to do:** Fix [#670](https://github.com/u2giants/theoracle/issues/670) (`bakeoff.py` attempted-thread truncation denominator & exact DP stratum bound) and [#680](https://github.com/u2giants/theoracle/issues/680) (`handle_intake_ingest` `thread_prefix` forwarding & positive-int `days`/`limit` validation).
- **Actually did:** Updated [`bakeoff.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/bakeoff.py) and [`ingest.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/ingest.py) with unit tests (`test_intake_bakeoff.py`, `test_intake_ingest.py`).
- **Found:** Confirmed boolean `days=True` (`isinstance(True, int)`) previously bypassed naive `int` checks; explicitly rejected `bool` values.
- **PR / branch:** Merged in PR [#686](https://github.com/u2giants/theoracle/pull/686) ([`bb466582`](https://github.com/u2giants/theoracle/commit/bb466582fb49c16128d083e7240c5e71fea2d3ac)).
- **Worktree:** Finished (worktree removed and sub-agent terminated).
- **Deliberately did NOT do, and why:** Did not run live production ingest (`lead-only`).

### Agent: `09026a78` (`Intake Collectors & Clean Helper`, `flash` — session `bf9773ed`)
- **Asked to do:** Fix [#635](https://github.com/u2giants/theoracle/issues/635), [#621](https://github.com/u2giants/theoracle/issues/621), and [#623](https://github.com/u2giants/theoracle/issues/623) across `clean.py`, `graph_mail.py`, `clickup.py`, `sizing.py`, and `graph_chats.py`.
- **Actually did:** Implemented single-quoted hidden HTML stripping, `meetingMessageType` in `graph_mail.SELECT`, `too_short` revival, ClickUp `None`-list/string-ID/403-404 guards, and `graph_chats.store` shorter-window count recomputation + un-ingested orphan pruning (`52 passed`). Lead added `signatures` generator materialization, multi-team ClickUp matching, and `@pytest.mark.skipif` DB guards.
- **Found:** Confirmed `test_intake_clean.py` held two unbroken synthetic `AKIA`/`PRIVATE KEY` literals that tripped `ai-public-boundary-check` when touched; split via string concatenation in PR [#687](https://github.com/u2giants/theoracle/pull/687).
- **PR / branch:** Merged in PR [#687](https://github.com/u2giants/theoracle/pull/687) ([`74625ef2`](https://github.com/u2giants/theoracle/commit/74625ef22e07012a180951be809c16553ac64f69)).
- **Worktree:** Finished (worktree removed and sub-agent terminated).
- **Deliberately did NOT do, and why:** Did not run live collector sweeps or touch production credentials (`lead-only`).

### Agent: `668532e9` (`Intake Ingest Spend Cap Helper`, `flash` — session `bf9773ed`)
- **Asked to do:** Fix [#644](https://github.com/u2giants/theoracle/issues/644) in [`ingest.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/ingest.py) so `can_afford(est + usd, cap)` runs before `storage.upload(...)`.
- **Actually did:** Moved affordability check ahead of `storage.upload` and added `test_spend_cap_never_uploads_orphan_objects` in [`test_intake_ingest.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_intake_ingest.py).
- **Found:** Confirmed zero orphan Supabase Storage uploads when `BRAIN_INTAKE_MAX_USD` stops queueing mid-run.
- **PR / branch:** Merged in PR [#687](https://github.com/u2giants/theoracle/pull/687) ([`74625ef2`](https://github.com/u2giants/theoracle/commit/74625ef22e07012a180951be809c16553ac64f69)).
- **Worktree:** Finished (worktree removed and sub-agent terminated).
- **Deliberately did NOT do, and why:** Did not alter `ingest.py` schema or production spend caps (`lead-only`).

### Prior `#664` session sub-agents (`b438dd36`, `c8366766`, `fb89b826` in `6aba6e03`; `e8f80585`, `a3887803` in `8feab216`)
- All five completed, verified, and merged in PRs [#667](https://github.com/u2giants/theoracle/pull/667) ([`e29b8876`](https://github.com/u2giants/theoracle/commit/e29b8876a2569cced0aa9a122d9b5c0d25a22df8)), [#672](https://github.com/u2giants/theoracle/pull/672) ([`f858b6d9`](https://github.com/u2giants/theoracle/commit/f858b6d9a463986e9e0ee27b63fe8a51724977eb)), [#676](https://github.com/u2giants/theoracle/pull/676) ([`84690000`](https://github.com/u2giants/theoracle/commit/8469000075b39a052b9706bebd5370e440e3566f)), and [#678](https://github.com/u2giants/theoracle/pull/678) ([`8e38f495`](https://github.com/u2giants/theoracle/commit/8e38f495d85da80e941dc74cddf0b5ae8ab07c44)), with all worktrees removed and zero open items remaining.

---

## Self-audit (`handoff-writer` mandatory 4-question gate)

1. *Is this handoff comprehensive enough that a brand-new developer with no project knowledge and no session context could pick up and not skip a beat?* **Yes** — §§1–3 explain The Oracle, its services, every merged PR (`#686`, `#687`, `#689`), the exact live Coolify `oracle-brain` SHA and seats, and the completed `#664` Step 4.2, `#607` Step 3.1, and `#607` Step 3.1a outcomes; §6 gives step-by-step instructions and verification gates for Step 4.1; §8 lists all 1Password item IDs and service UUIDs.
2. *Is it detailed enough that they could continue as well as I could right now, with all session knowledge and background?* **Yes** — §§4–5 document every production trap uncovered during live pilot execution (`flat._post_chat` GLM hidden-thinking 10x cost/latency bug, `024`/`025` `migrate()` constraint-narrowing crash on `'message_record'` rows, `:5432` vs `:6543` pooler limits, `flex` tail timeout & sibling-job requeue, Coolify User-Agent `403`, and `PUT /models` `auth_user_id` lookup).
3. *Is every relevant detail included with portable GitHub URLs only?* **Yes** — all ten sections (0–9) plus Part (b) use full `https://github.com/u2giants/theoracle/...` URLs, with zero machine-local paths, zero private employee text, and zero secret values.
4. *If Albert read ONLY §0, would he see every business decision needed from him and zero technical approvals?* **Yes** — verified line by line across §§1–9 and Part (b): §0 consolidates both remaining business judgements (Checkpoint 1 post-pilot `L1` exact-quote confirmation before Step 4.1, and Checkpoint 2 final live-proof acceptance) with clear recommendations and zero technical approvals.

## Next-session prompt

```text
Resume The Oracle on main of https://github.com/u2giants/theoracle using:
https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T2205Z-edge-dev-agy-oracle-607-step41-ready.md

Read https://github.com/u2giants/theoracle/blob/main/AGENTS.md,
https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md (STATUS first),
https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-22-pm-intake-pilot-and-colab-drain-proof.md,
and the handoff above.

Steps 3.1 (14-day live PM pilot), 3.1a (Ilona live Brain question comparison), and #664 Step 4.2 (Colab L4 production drain) are complete and deployed on main. Once the owner confirms §0 Checkpoint 1 (keeping exact verbatim quotes L1 for the 90-day run), create an isolated worktree, declare ai-task-gates start --class production, execute #607 Step 4.1 (90-day full-window ingest, extraction through recommend, 20-thread spot-check, 5 cited web answers, and enabling BRAIN_INTAKE_ENABLED=true while keeping BRAIN_INTERVIEW_ENABLED=false), post aggregate results on #607, and present §0 Checkpoint 2 for final live-proof sign-off on #607 and #664.
```
