---
summary: "Oracle #607 step 2.3 gated stop after protected blind-review calibration, live call-shape variant and fallback evaluation, and 350-thread forecast."
kind: handoff
status: OPEN
read-when: continuing Oracle issue 607 at step 2.3 or qualifying a companion #664 Colab model against the message-intake gates
issue: 607
owner: agy/oracle-607-qualify
---

# Oracle #607 — step 2.3 gated stop after blind-review calibration and all L8 variant checks

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Put the blocking business choice below to Albert in **one** plain-English message only if he wants `#607` to move before companion issue [#664](https://github.com/u2giants/theoracle/issues/664) finishes; never include any technical approval.

- **Blocking `#607` cloud-only rollout (unless companion `#664` supplies the qualifying model):** Every affordable cloud model on your approved four-model list (`gpt-6-luna`, `claude-haiku-5.5`, `glm-5.3-flash`, `deepseek-4.1-flash`) — including batch modes, all four planned message-packing/window variations, and two-model retry pairs — fell short of the 95% accuracy bar on real messages (best cloud batch pair reached at most 92.61% even counting unreviewed claims optimistically, because raw chat and email lines get overstated as permanent company rules or ownership). **Question for Albert:** Do you want to hold `#607` live intake until [#664](https://github.com/u2giants/theoracle/issues/664) tests larger open-weight and custom fine-tuned models on your prepaid Google Colab GPUs against the unchanged 95% bar, or change `#607`'s message-extraction rules/accuracy bar so a cloud model can run sooner? **Recommendation:** Hold `#607` rollout for `#664`'s prepaid Colab fine-tuning path — it keeps your 95% accuracy and exact-quote standard intact at $0 extra per-token API cost. Blocks `#607` steps 2.4, 3.1 (14-day pilot), and 4.1 (90-day run).
- **Downstream post-pilot and acceptance checkpoints (not blocking now; present together once pilot/full-run numbers exist):**
  1. *Whether to keep the exact-verbatim-quote rule after seeing measured 14-day pilot cost per kept thread and an all-employee cost projection.* **Recommendation:** Keep exact verbatim quotes through the pilot and beyond unless measured cost justifies revisiting it. Blocks step 4.1 only if changed.
  2. *Final live-proof look on the project-management function page and generated (unsent) interview questions after five cited answers are verified.* **Recommendation:** Present the function page and unsent questions together after step 4.1 finishes while keeping the interview bot off. Blocks checking `- [ ] live proof` on [#607](https://github.com/u2giants/theoracle/issues/607).
- **Already settled — do NOT re-ask:**
  - *Both project managers' mailboxes, private/group Teams chats, and ClickUp are in scope; reading is unannounced; interview bot stays off* (settled 2026-11-18 in [plan STATUS](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md#status--read-this-first)).
  - *No frontier cloud models anywhere in this pipeline* (settled 2026-11-18, rule L9).
  - *Keep exact verbatim words through the 14-day pilot* (settled 2026-11-19).

---

## 1. What this application is

The Oracle (`https://github.com/u2giants/theoracle`, public repository) builds an evidence-backed Company Map for POP Creations / Spruce Line from company documents, meeting transcripts, Teams chats, ClickUp tasks, and authorized email, answers employee questions with verbatim quotes, and drafts follow-up interview questions. Runtime components ([developer guide](https://github.com/u2giants/theoracle/blob/main/AGENTS.md), [service inventory](https://github.com/u2giants/theoracle/blob/main/docs/agents/09-container-and-service-inventory.md)):
- `apps/web` — Next.js 16 web app on Vercel (`prj_rP6Jlima7iK1paffEPhLqxlswGsC`).
- `apps/brain` — Python 3.12 FastAPI + worker service (`oracle-brain` on Coolify, image `ghcr.io/u2giants/theoracle-brain`), writing Postgres schema `cmap` on Supabase and graph `company` on FalkorDB.
- `oracle-sandbox-private` — Dedicated isolated Coolify sandbox (`quote-tools` + network-isolated `sandbox-db`) holding all private `#607` message corpus excerpts, candidate checkpoints, and sealed blind-review packets.

## 2. What we set out to do this session, and why

Resume [#607](https://github.com/u2giants/theoracle/issues/607) at step 2.3 of [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md) from [the expanded-sample handoff](https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0202Z-edge-dev3-codex-intake-expanded-sample.md): reverify all sealed digests and the 350-thread sampling design, resolve protected blind-review calibration without exporting raw message text, implement `apps/brain/brain/intake/bakeoff.py`, test all remaining registered call-shape variants and L8 failure-only fallbacks against the step 2.3 gates (`≥95%` correctness, `≥90%` recall, `≥98%` quote validation, `≤1%` truncation), forecast 350-thread expansion spend, and keep production untouched unless a model passes.

## 3. Current state — what is true right now

- **Sandbox custody and digests verified (`100%` match):** Read-only Coolify observer verified `oracle-sandbox-private` (`lh8tiwrst3hwij9yr3ss4vdx`, `running:healthy`) and isolated `quote-tools` / `sandbox-db` networks with zero host ports. Rehashed step 2.1 manifest (`54809ee73480a1b91a05c69bb4c9d8d0b074ceace17cedd6b677c9812c611c82`), step 2.2 manifest (`ba0a75e691909432852a6871db64ea1473552598ce3e5d6af9a481d1ee6dcf07`), 12-route blind packet (`9d2f69be67b49af8dc08861fbfb6727334f372776889cff998196ba38ce06325`), Luna batch reconciliation (`843c4f14f898f9e5c5959a63b82223136595f5ebb26393d6e7ff723254e26278`), expansion manifest (`4325180c2c273804ae3f345edd486728b11aff48a6a2590ce223c4b1c7eab9dd`), and expanded source (`eeec797996e49dbb1d8a23fd73219a68f9b698a9976f1b249285a28d8ca4dbfd`). Confirmed `50` tuning, `150` initial held-out, and `200` added held-out threads (`350` union, `0` overlap) and reproduced `P(0 | K = 5) = 7.47%`, `P(0 | K = 6) = 4.42%` (`5 / 641 = 0.78%` exact 95% upper truncation bound).
- **Scorer code and tests landed on branch `agy/oracle-607-qualify` (intended `main` paths via PR):**
  - [`apps/brain/brain/intake/bakeoff.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/bakeoff.py) — stratified whole-thread bootstrap bounds, exact conditional stratified hypergeometric truncation upper bound, call-shape helpers (`should_skip_low_mentions`, `is_short_joint_eligible`, `wider_window_indices`, `find_near_duplicate_threads`), `blend_fallback`, `score_candidate`, and `select_winner`.
  - [`apps/brain/tests/test_intake_bakeoff.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_intake_bakeoff.py) — 4/4 unit tests passing (`uv run pytest tests/test_intake_bakeoff.py`) and `uv run ruff check .` clean.
- **All eligible L8 candidates, batch routes, call variants (`a`–`d`), and fallbacks tested and failed `≥95%` correctness:** Full aggregate table and digests are in [`docs/verification/2026-11-21-pm-intake-step-2-3-qualification.md`](https://github.com/u2giants/theoracle/blob/main/docs/verification/2026-11-21-pm-intake-step-2-3-qualification.md) (sandbox receipt `0e8b4e91eecf70faf00d5858eda7ca3ad5f7447d1ffd5a8e0f36de925d132866`). Best-case correctness 95% lower bounds (counting 100% of unjudged novel claims as `keep`) peaked at `94.83%` (`Luna` OpenRouter batch, quote LB `96.24%`), `93.70%` (`Haiku` native batch, quote LB `100%`), `93.28%` (`Luna` native batch, quote LB `97.28%`), `92.61%` (`Luna batch → Haiku batch` fallback, quote LB `100%`, `$0.5713/1,000`), `77.14%` (`Luna` live joint `<400`-token call), and `58.22%` (`Luna` live 4-passage wider context). Variant `(d)` near-duplicate screen across all `350` held-out threads (`867` passages) and `50` tuning threads (`77` passages) found `0` pairs at `95%` similarity.
- **Protected blind-review calibration (`protected-review-20261121`):** Two-stage source-first + single-turn verbatim-quote gate + `medium`-effort structured rubric non-author ZDR workflow (`prereg_sha256` `23b6c42f7aa23b1f53de9df44fcce6b997f2e37fd5d9e8e5006e57a0d1c64e1b`, `sealed_verdicts_sha256` `08449b42c2d93465f1219a7cfb8af25388e5e9d764d1dc7bc6b2fe18a2a9c065`, `report_sha256` `bcfa36cad57b00935150d28298b97f802e6b030319c0ab540a9983030bc31b08`) resolved `72/72` controls (`0` unresolved) and reduced false-keep on `reject` controls to `1/24` (`4.2%`), reaching `54/72` (`75.0%` lead `R1`) and `52/72` (`72.2%` 3-family settled) binary agreement — below the preregistered `60/72` (`83.3%`) gate. Automated novel verdicts remain excluded.
- **Not started / gated:** Paid runs on the `200` added held-out threads (`431` passages, forecast `$0.2217–$1.0086` per route), 15-question `brain/eval` comparison, step 2.4 batching, step 2.5 full answer check, step 3.1 14-day pilot, and step 4.1 90-day live run. Production was completely untouched; predecessor `#607` handoffs are retained per `AGENTS.md` §3a because step 2.3 remains open.

## 4. Everything we tried that did NOT work

- **Automated L8 non-author ensemble calibration on `keep` vs `correct` scope boundaries (`Stage 1b`):** Adding deterministic raw-turn quote checking (`literal_evidence`) plus `medium`-effort structured rubric booleans (`c_boiler`, `c_type`, `c_scope`, `c_fact`) fixed `reject` detection (`22/24` on `R1`, `23/24` settled vs `6/15` in prior strict runs), because `106/220` step 2.1 `reject`s were non-verbatim turn quotes. However, on borderline scope-narrowing items (`correct` vs `keep`), `deepseek` and `glm` tie-breakers voted `keep` more permissively than `luna`/`haiku` (`correct -> keep` rose from `7/24` on `R1` to `10/24` settled), leaving overall binary accuracy at `75.0%` (`R1`) / `72.2%` (settled) against the `83.3%` requirement. Do not reuse those 72 controls for iterative prompt tuning — they have now been evaluated once.
- **Joint short-thread extraction (`variant b`) and 4-passage wider context (`variant c`) on zero-shot L8 models:** Live ZDR trials across all four L8 models completed `57/57` usable passages with `0` truncations, and `Luna` joint improved adjudicated correctness on short threads (`73.77%` est / `68.34%` LB vs `65.79%` / `57.07%` archived), while wider context slightly raised `GLM` (`49.39%` est) and `DeepSeek` (`50.51%` est). Neither came close to `≥95%` correctness because the underlying failure mode is `prompts/relations.md` inducing over-typed relations (`OWNS`, `PART_OF`, `PRODUCES`, `policy`) on conversational text.
- **Batch-to-batch failure fallback (`Luna native batch → Haiku native batch`):** Replacing the `2` Luna passages that had validation drops with Haiku native batch lifted quote validation to `497/497` (`100.00%` LB) at `$0.5713/1,000`, solving Luna's quote-gate miss, but known step 2.1 errors (`12 correct`, `9 reject`) still capped its optimistic best-case correctness 95% lower bound at `92.61%` (`< 95%`).
- **OpenRouter `z-ai/fp8` ZDR tag for `z-ai/glm-5.3-flash`:** Querying `GET /api/v1/endpoints/zdr` showed `z-ai/fp8` is no longer active; `run_candidates.py`'s hardcoded `"z-ai/glm-5.3-flash": "z-ai/fp8"` now raises `StopIteration`. Verified active ZDR tags for `z-ai/glm-5.3-flash` include `fireworks/us` (`$0.225/$0.75` per 1M) and `parasail/fp8` / `baseten/fp8` (`$0.15/$0.50` per 1M).

## 5. Root causes and key findings

- **Why zero-shot models miss `95%` correctness on messages (`step-2.1-sampled/scoring-adjudications.json`):** Out of `1,920` step 2.1 candidate claims, `944` (`49.2%`) were `keep`, `750` (`39.1%`) were `correct` (narrowed), `220` (`11.5%`) were `reject`, and `6` (`0.3%`) were `withhold`. Across ontology types, `77.4%` (`731/944`) of accepted `keep` claims are `APPLIES_TO` (`506`), `MENTIONS` (`225`), or `HANDS_OFF_TO` (`74`), whereas `OWNS` (`0/26` `keep`), `PRODUCES` (`9/83` `keep`), `PART_OF` (`34/161` `keep`), `DEPENDS_ON` (`26/127` `keep`), `USES` (`16/75` `keep`), and `stance = inference` (`29/154` `keep`) fail overwhelmingly because models treat item-theme descriptions, folder path strings, signatures, and situational requests as structural company facts.
- **Why prior automated judges failed `reject` controls:** [`apps/brain/brain/extract/relations.py#L263-L292`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/extract/relations.py#L263-L292) (`find_quote`) folds whitespace and allows quotes spanning packed passage boundaries, whereas step 2.1's `review_quotes.py` (`literal_evidence`) required `any(quote in turn["text"] for turn in raw_turns)` (`106` of `220` `reject`s failed `exact_source_evidence`).
- **Exact 350-thread corpus geometry:** All `350` held-out threads pack into `867` passages (`57` in `initial_30`, `379` in `reserve_120`, `431` in `added_200`; `241,733` stored tokens), while `tuning_50` packs into `77` passages (`23,714` tokens) and holds `3,576` pooled candidate claims in `blinded-candidates.json` ready for [#664](https://github.com/u2giants/theoracle/issues/664) step 2.1 QLoRA training.

## 6. Exact next steps

1. **Qualify an open-weight or QLoRA-tuned candidate via companion [#664](https://github.com/u2giants/theoracle/issues/664) (or apply Albert's §0 ruling if he changes `#607`'s scope/bar):**
   - Execute [`plan_colab_gpu_offload.md`](https://github.com/u2giants/theoracle/blob/main/plan_colab_gpu_offload.md) steps 0.1–2.2 using `#607`'s `50` tuning threads (`tuning_50`, never held-out threads!) to train/tune an adapter that suppresses unsupported `OWNS`/`PART_OF`/`PRODUCES`/`policy` overstatements and emits byte-verbatim single-turn quotes.
   - Gate: on `tuning_50` and then `initial_30`, `bakeoff.score_candidate` ([`apps/brain/brain/intake/bakeoff.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/bakeoff.py)) shows quote validation LB `≥98%` and zero-truncation completion before dispatching the `867` full held-out passages.
2. **Resolve novel-claim blind review for any finalist that clears step 1:**
   - Because L8 automated review reached `75.0%` (`< 83.3%`) on the 72 packet controls, either calibrate a distinct non-candidate open-weight adjudicator on Colab (`#664`) on `tuning_50` + fresh unused step 2.1 controls (`1,920` minus previously tested control IDs) to `≥85%` binary / `≤10%` false-keep before unsealing, or record `Blocked —` if no permitted non-author adjudicator passes calibration.
   - Gate: sealed calibration receipt in `/sandbox/records/step-2.3-relations/` passing preregistered control bounds with `0` raw text exported.
3. **Run full 350-thread (`867`-passage) qualification and 15-question `brain/eval` check:**
   - Run the single finalist across all `350` held-out threads (`867` passages), verify `bakeoff.conditional_truncation_upper_bound` `≤ 0.01` (`0.0078` at zero first-attempt truncations), quote LB `≥ 0.98`, correctness LB `≥ 0.95`, and recall LB `≥ 0.90`, then run the 15-question `brain/eval` comparison against the reference before seating for `origin IS NOT NULL` message sources.
   - Gate: `select_winner` returns a non-`None` `CandidateScore`, 15-question grade does not drop, and aggregate proof is committed under `docs/verification/` and posted on [#607](https://github.com/u2giants/theoracle/issues/607).
4. **Proceed to steps 2.4, 2.5, 3.1, and 4.1 only after step 3 passes:**
   - Measure 100-passage cache-hit share and batch path (2.4, if cloud provider), finish step 2.5 ScaleDown function-assign 15-question check, then under separate production task declaration run the 14-day pilot (3.1) and 90-day run (4.1), leaving `- [ ] live proof` open on [#607](https://github.com/u2giants/theoracle/issues/607) until Albert's §0 acceptance.

## 7. Constraints and gotchas in force

- **Zero private text outside `/sandbox`:** Never print message bodies, quotes, employee/customer names, email addresses, or source-derived masked labels in tool output, logs, commits, PRs, or issues.
- **No frontier cloud models (L9):** Never seat or fall back to Opus, Sol, GLM MAX, or Hydrogen for `#607` extraction, retries, or judging.
- **Never tune on held-out threads:** `initial_30`, `reserve_120`, and `added_200` (`350` threads total) are strictly held out; all prompt/LoRA tuning uses `tuning_50` only.
- **Ephemeral OpenRouter keys:** Always mint short-lived capped keys assigned to `"Oracle 607 no retention"` in `oracle-pm-intake-sandbox` via `OR_MGMT` and `DELETE keys/{hash}` in `finally`; recheck `GET /api/v1/endpoints/zdr` live because provider tags (`z-ai/fp8`) change without notice.
- **Keep production untouched:** Do not enable `BRAIN_INTAKE_ENABLED`, alter `cmap.model_seat`, or run live ingestion until step 2.3 qualifies a route. Keep the interview bot off (`#518`).

## 8. Access and environment

- **SSH to Coolify host:** `vps2-direct` (`ai` user via managed `ai-devops` SSH config), then `docker exec -i quote-tools-lh8tiwrst3hwij9yr3ss4vdx python3 -`.
- **1Password vault `vibe_coding` (references only, never print values):**
  - Service account token provisioned by `ai-devops` machine setup (`op-service-account`).
  - Coolify read-only observer: item `5xjuaif5okkiqoszmh7ncrf3sy` (`Coolify API token - Oracle read-only observer (theoracle, experiments)`), field `credential` against `http://127.0.0.1:8000/api/v1/services` on `vps2-direct`.
  - OpenRouter workspace management key (for ZDR verification + ephemeral key mint/revoke): item `vqk7qypdfdqog6bo7r6f63zz5m` (`OpenRouter Management API Key - POP AI services (production)`).
- **Sandbox artifact directories created this session (`/sandbox/records/step-2.3-relations/`):**
  - `protected-review-20261121/` (`calibration-prereg.json`, `calibration-sealed-verdicts.json`, `calibration-report.json`, `source-first/`).
  - `variants-and-forecast-20261121/` (`aggregate.json` sha256 `0e8b4e91eecf70faf00d5858eda7ca3ad5f7447d1ffd5a8e0f36de925d132866`, plus `joint-*` and `wider-*` per-passage ZDR checkpoints).

## 9. Open questions and risks

- **Risk (dated 2026-11-21):** Zero-shot L8 models structurally over-assign `PART_OF`, `OWNS`, `PRODUCES`, and `policy` on informal chat/email turns (`39.1%` narrowing rate). Companion [#664](https://github.com/u2giants/theoracle/issues/664) QLoRA tuning on `tuning_50` directly targets this ontology calibration without changing `L1` or `L9`.
- **Risk (dated 2026-11-21):** Only `1,920` step 2.1 adjudicated claims exist (`~250` already used as controls across prior and current calibration runs); conserve remaining unused `initial_30` controls strictly for one-shot verification of a `#664` adjudicator after tuning on `tuning_50`.
- **Owner decisions:** Consolidated in §0 above.

---

## Self-audit (`handoff-writer` checklist)

1. *Could a street-newcomer continue without asking a single question?* Yes — §§1–3, 6, and 8 specify the exact container, SSH alias, 1Password item IDs, sandbox paths, SHA-256 digests, and [`bakeoff.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/intake/bakeoff.py) entry points.
2. *Are all failed attempts, root causes, and ZDR tag changes documented?* Yes — §4 and §5 record the `Stage 1b` `54/72` (`75.0%`) calibration outcome, all live variant/fallback bounds, the `106/220` raw-turn verbatim root cause, and the retired `z-ai/fp8` tag.
3. *Are all file references portable GitHub URLs and all secrets referenced by vault/item ID only?* Yes — verified across §§0–9.
4. *Was the §0 owner-decision sweep run?* Yes — the cloud-vs-`#664` rollout gate and both downstream pilot/live-proof business checkpoints are consolidated in §0 with recommendations; technical calibration blockers stay assigned to AI engineering.

## Next-session prompt

```
Resume #607 (and companion #664 Step 1.3/2.1) from main of https://github.com/u2giants/theoracle.
Read AGENTS.md, plan_pm_message_intake.md (STATUS first), plan_colab_gpu_offload.md (STATUS first),
and https://github.com/u2giants/theoracle/blob/main/HANDOFF.d/2026-11-22T0302Z-edge-dev-agy-intake-step23-gated-stop.md.
All zero-shot L8 cloud routes, call-shape variants (a-d), and L8 fallbacks failed #607 Step 2.3's 95%
correctness gate (proof: docs/verification/2026-11-21-pm-intake-step-2-3-qualification.md). Keep
production untouched and evaluate #664 open-weight / QLoRA candidates against brain.intake.bakeoff.
```
