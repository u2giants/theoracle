# MODEL BAKE-OFF SPEC — choosing the best model for every pass, empirically

Status: ready to execute in the stages noted per protocol. Written 2026-07-06.
Author: Claude (Fable 5), commissioned by Albert.
Parent document: `MACRO_FIRST_REDESIGN.md` §8 (the Model Passes table, seeded defaults,
cost policy). This spec is the empirical validation of §8's seeded model orders.

Audience: a developer/agent with NO prior context. Every step is spelled out. Where a
judgment call could appear, this spec makes it. Do not improvise; if a step cannot be
executed as written, stop and record why in §9 before deviating.

---

## 1. Purpose and non-negotiable ground rules

A bake-off answers ONE question per pass: *which allowed model does this specific job
best on our real data?* The seeded defaults in `MACRO_FIRST_REDESIGN.md` §8 are
hypotheses; only a bake-off result may change a primary model in prod settings.

Ground rules (all learned the hard way in this repo — see HANDOFF 2026-06-26):

- **G1 — One-element pools.** During a bake-off, each candidate runs in a pool
  containing ONLY itself. Fail-over silently masks failures — four adapter bugs went
  unnoticed for weeks because broken candidates "looked fine" while the pool failed
  over past them. Never bake off with fallbacks enabled.
- **G2 — Restore state after every run.** Bake-offs temporarily change prod `settings`
  rows. Before touching anything, record the current values (§4 step 2). After the
  bake-off — including after a crash or an abandoned run — restore them. Never leave a
  one-element pool in prod overnight.
- **G3 — Cost policy.** Candidates must not include premium-tier models: Claude Opus,
  Claude Fable, GPT-5.5, Gemini 3.1 Pro Preview. Mid-tier (Claude Sonnet 5,
  Gemini 2.5 Pro, GPT-4.1) is allowed.
- **G4 — Everything is recorded.** Every run appends to `evals/bakeoffs/<slot>.md`
  (create the directory) using the template in §8. A bake-off that isn't recorded
  didn't happen.
- **G5 — Same fixture, same prompt, same settings for every candidate.** Only the
  model changes. If you fix a prompt bug mid-bake-off, restart the whole bake-off for
  that slot.
- **G6 — Vary nothing else in prod during a bake-off window.** Don't run other
  reprocessing jobs against the fixture document while a candidate is being measured.
- **G7 — Capability eligibility is checked first.** `enforce_model_capabilities=true`
  will refuse ineligible models loudly. Known hard facts: Qwen/DashScope cannot do
  strict `json_schema` (ineligible for rows 2, 3, 4, 5); non-VL Qwen models are not
  vision-capable; check `model_capabilities` (Admin → model dropdowns read it) before
  scheduling a candidate.

---

## 2. Environment and access (read once, verify before first run)

- **Prod DB**: Supabase project `eqccjfbyrywsqkxxpjvg`. Connection string: 1Password →
  "Supabase DB Direct URL - The Oracle (CURRENT PROD …)". ⚠️ Local `.env.local` points
  at the OLD project (`vokucjpanhvqunimlvsp`) — never run migrations or writes from
  local env without overriding `DIRECT_URL`. Reads/ad-hoc SQL may also go through the
  Supabase MCP.
- **Workers**: Trigger.dev project `proj_wgpzsvhmsopqhvwqaycn`. Use the Trigger.dev
  MCP/dashboard to trigger tasks and read run logs. Do NOT add scheduled tasks (the
  project is at its 10/10 schedule limit) — everything here is on-demand dispatch.
- **Settings changes**: make them through Admin → Settings (the UI writer normalizes
  encoding). If you must write SQL, mimic the UI's single-encoded format and verify
  afterward: `SELECT key, value FROM settings WHERE key = '<key>';` — the value must
  not be double-JSON-encoded (a string containing an escaped JSON string). This bug
  class existed and was fixed; don't reintroduce it.
- **Shell**: use `corepack pnpm` (plain `pnpm` is not on PATH on this machine).
- **The canonical fixture document**: `9d09fa89-3a46-465e-a98b-837287c9e22a`
  ("Pop Creations Flow 12112025 (1).png") — the swimlane diagram. Ground truth for its
  workflow content: `fix_enhancement.md` §2.1 (a human-verified reconstruction:
  9 lanes, the full lifecycle, all branches/loops — treat it as the answer key).
- **Re-running the fixture**: `scripts/reevaluate-document.mjs` (DRY-RUN by default;
  read its header before using) wipes the document's claims/chunks/candidates and
  resets it to `pending_processing`; then trigger `document-ingestion` for it via the
  Trigger.dev MCP/dashboard. ⚠️ This destroys the document's current claims in prod —
  confirm with Albert before the FIRST wipe in any session, and prefer running the
  whole bake-off in one sitting so the document ends in a good state.
- **Where measurements live**:
  - `model_runs` / `model_run_attempts` — per-call success/failure, provider, model,
    slot, task type.
  - `model_run_usage_details` — token usage and cost per call.
  - `job_runs` + `documents.macro_health` — pipeline-level outcome.
  - Trigger.dev run logs — errors, latency (run duration).

---

## 3. Which bake-offs, when, and their candidates

| # | Slot (row in §8 table) | Earliest stage it can run | Candidates (in seeded order) | Protocol |
|---|---|---|---|---|
| BO-0 | — (PIPELINE ceiling benchmark, not a model test) | NOW (Stage 0), re-run at Stages 2, 5, 7 | n/a — compares the Oracle end-to-end against frontier chat apps | §5.0 |
| BO-1 | Vision transcription | NOW (Stage 0) | `qwen/qwen3-vl-235b-a22b-thinking`, `google/gemini-2.5-flash`, `claude-sonnet-5` | §5.1 |
| BO-2 | Workflow read | Stage 1 (needs the `source-workflow-read` worker) | `claude-sonnet-5`, `google/gemini-2.5-pro`, `openai/gpt-4.1` | §5.2 |
| BO-3 | Model merge | Stage 3 (needs `business-model-merge`) | `openai/gpt-4.1-mini`, `google/gemini-2.5-flash`, `claude-haiku-4-5` | §5.3 |
| BO-4 | Claim extraction | Only if extraction prompts change materially (already decided 2026-06-26) | current pool members + any new candidate | §5.4 |
| BO-5 | Deep synthesis | Stage 6 (needs the consultant pass; Brain half can run at Stage 5) | `claude-sonnet-5`, `google/gemini-2.5-pro`, `openai/gpt-4.1` | §5.5 |
| BO-6 | Conversation (cheap-first ladder) | Stage 5 (needs the new chat context path) | `claude-haiku-4-5`, `google/gemini-2.5-flash`, `claude-sonnet-5` | §5.6 |
| — | Translation, General utility | no bake-off — incumbents proven; revisit only on observed failure | — | — |

---

## 4. The universal run procedure (used by every protocol in §5)

For ONE candidate on ONE slot:

1. **Eligibility check**: confirm the candidate appears in the admin model dropdown for
   that slot (capability-filtered). If not, record `ineligible` and skip.
2. **Snapshot**: `SELECT key, value FROM settings WHERE key IN
   ('default_<slot>_route', 'model_pool_<slot>');` — paste the values into the results
   file BEFORE changing anything.
3. **Isolate**: set `default_<slot>_route = <candidate>` and
   `model_pool_<slot> = [<candidate>]` (one element — G1) via Admin → Settings.
4. **Run the fixture** per the slot's protocol in §5.
5. **Collect**: from `model_run_attempts` confirm the run actually used
   `<provider>/<model>` with `success=true` (or record the exact error); from
   `model_run_usage_details` record tokens + cost; from the Trigger run record
   duration; then score per the slot's rubric.
6. **Record** into `evals/bakeoffs/<slot>.md` using the §8 template.
7. **Next candidate**: repeat 3–6.
8. **Decide & restore**: apply the §6 decision rule; set the winner as primary with
   the two runners-up as fallbacks (three-element pool — G2 ends the one-element
   state); verify the settings read back single-encoded.

Run each candidate **twice** (vision: three times — it is the most nondeterministic
pass). Score each run; a candidate's score is its MEAN; also record the spread. If the
two runs of one candidate disagree wildly (>30% score difference), run a third and note
the instability in the results — instability is itself a scoring criterion.

---

## 5. Per-slot protocols

### 5.0 BO-0 The ceiling benchmark (pipeline test, NOT a model test — Albert's requirement)

Purpose: establish the UNDERSTANDING CEILING — what a frontier model extracts from the
same source with NO pipeline in the way — and measure how close the Oracle's end-to-end
pipeline gets to it. A large gap means the pipeline is destroying information; the gap
must shrink as the redesign stages land. This does not pick a model for any slot; it
grades the architecture. G1–G2 do not apply (no prod settings change); G4 applies.

Fixtures (one per modality the system must handle):
1. **Visual**: the canonical swimlane diagram (`9d09fa89-…`, the image file itself).
2. **Prose**: a representative licensing-department workflow/responsibility document
   from the corpus — Albert designates which one; record its document id.
3. **Structured data**: the Cloudflare D1 workers aggregation of ClickUp
   project-management data. ⚠️ Not currently in the repo/corpus as a fixture — Albert
   must provide/designate the export before this leg can run; store a frozen copy
   under `evals/bakeoffs/fixtures/` so re-runs use identical input.

Procedure, per fixture:
1. **Ceiling side**: give the RAW source file directly to each of two frontier chat
   apps (Claude app and ChatGPT app, current flagship models — premium models are
   allowed HERE because they are measuring the ceiling, not candidates for a slot).
   Ask each the battery questions applicable to that fixture (B1–B7 for the swimlane;
   write 5 analogous questions per other fixture ONCE, record them in the results
   file, and never change them between re-runs). Save full transcripts.
2. **Oracle side**: ingest the same source through the full pipeline, then ask the
   SAME questions through the Oracle chat endpoint. Save transcripts.
3. **Score both sides** on the same 0–2 rubric per question (coherence, completeness,
   correctness vs. the source; for the Oracle also note citations, which the ceiling
   side won't have). Ceiling score = the better of the two chat apps per question.
4. **Report the gap**: `oracle_total / ceiling_total` per fixture. Record in
   `evals/bakeoffs/ceiling.md` with the stage label (0, 2, 5, 7).

Expected trajectory: Stage 0 gap is large (that is the point of the redesign);
Stage 5 should reach ≥80% of ceiling on the swimlane and prose fixtures; Stage 7
≥80% on all three. If a re-run REGRESSES by more than 10 points, stop feature work
and diagnose before proceeding (this is a pipeline health alarm, not a model issue).

### 5.1 BO-1 Vision transcription

An existing, more detailed plan for this exact bake-off already exists:
**`test_code_changes.md` (Test 2)** — 5 vision models head-to-head on transcription
quality AND prompt-cache effectiveness, with ground truth and a scoring rubric.
**Follow that document for BO-1**; it predates this spec and is more specific about
cache metrics. Additions from this spec that override/extend it:
- Add `claude-sonnet-5` to its candidate list.
- Apply this spec's G1–G7 and §8 recording format alongside its own.
- The decision also updates `model_pool_vision` (primary + 2 fallbacks) once that pool
  exists (redesign Stage 1), not just `default_vision_route`.

Scoring core (if executing without Test 2's rubric): against `fix_enhancement.md`
§2.1 ground truth, count node recall, edge recall, branch-condition recall, lane/person
attribution accuracy (the known differentiator: does the "Carlos" lane keep its name?),
one-line-per-edge discipline (% of edges on a single line — this feeds quote
validation), latency, cost. Weights: fidelity metrics 70%, edge-line discipline 15%,
latency+cost 15%.

### 5.2 BO-2 Workflow read (the most important bake-off)

Fixture: the canonical diagram document, freshly re-ingested so chunks exist.
Run: trigger `source-workflow-read` for the document (or full `document-ingestion` if
the reader is inline by then). The map lands in `source_workflow_maps`.

Score against `fix_enhancement.md` §2.1 (the answer key). Metrics, per run:

| Metric | How to compute | Weight |
|---|---|---|
| Node recall | ground-truth stages/boxes present in `nodes_json` ÷ total (count them from §2.1's 9 numbered stage groups; enumerate once into the results file as the checklist) | 25% |
| Edge recall | ground-truth transitions present in `edges_json` ÷ total | 25% |
| Branch recall | the named branches (new-vs-existing product; audit pass/fail; licensor legal-vs-creative) present with condition labels | 15% |
| Lane/owner accuracy | lanes matching ground truth ÷ 9 | 10% |
| Evidence validity | elements SURVIVING deterministic validation ÷ elements emitted (from `validation_json`) — punishes hallucination and paraphrase | 15% |
| Schema validity | 1 if the structured output parsed first try; 0.5 if a retry was needed; 0 if the run failed on schema | 5% |
| Latency + cost | record both; score relative to cheapest/fastest candidate | 5% |

### 5.3 BO-3 Model merge

Fixture: three sub-cases, run all of them per candidate:
1. **Identity**: re-run merge for the same source map against the process version it
   itself created → expected verdict pattern: all elements aligned, proposal type
   `confirm`. Any `contradict` here is a false positive.
2. **Doctored variant**: take the fixture image, edit ONE edge meaningfully (e.g.,
   reroute "If Audit: Fail" to a different stage; keep a copy of the doctored file in
   `evals/bakeoffs/fixtures/`), ingest as a new document → expected: `refine`/
   `contradict` touching ONLY that edge's neighborhood.
3. **Disjoint**: ingest a genuinely unrelated process doc (any SOP from the corpus) →
   expected: no forced alignment; `create_process`.

Score: correct proposal type per sub-case (3 × 20%), alignment precision on the
doctored case (no unrelated elements flagged, 20%), schema validity (10%), cost+latency
(10%). This slot is high-volume-ish and simple — when quality ties, the CHEAPEST
candidate wins.

### 5.4 BO-4 Claim extraction (conditional re-run only)

The 2026-06-26 live bake-off already decided this slot (gemini-2.5-flash: 54 claims
with branch capture, vs 12 for gpt-4.1-mini, 5 for gemini-3.1-flash-lite). Re-run ONLY
if the extraction prompt changes materially (the §5.4 map-injection change in the
redesign QUALIFIES — re-run this at Stage 2). Procedure: exactly the historical one —
each candidate isolated per §4, full fixture re-ingest, score = promoted-claim count ×
type variety × quote-validation pass rate × map-element coverage (new metric: % of map
elements that got their canonical claim). Record deltas against the 2026-06-26 numbers.

### 5.5 BO-5 Deep synthesis

Two halves, same candidates, one winner (the slot is shared — §8 row 5):

- **Consultant half** (Stage 6): run the recommendation pass over the approved fixture
  process version. Score: grounding (every elementId/claimId cited actually exists —
  any fabricated ID = automatic 0 for the run), usefulness (blind-rank the candidates'
  recommendation sets 1–3 — Albert or the reviewing admin does the ranking, not the
  agent running the bake-off), specificity (counts concrete stage/system references vs
  generic advice), schema validity, cost.
- **Brain half** (Stage 5): run `brain-synthesis` for `domain-licensing` (the
  established heavyweight: 124+ approved claims). Score: passes the R9 named-entity
  validator first try; draft coherence blind-rank; length within section norms; cost.

Winner = best combined rank; grounding failures are disqualifying regardless of prose
quality. When quality ties, prefer the cheaper candidate.

### 5.6 BO-6 Conversation (the cheap-first ladder — different shape!)

This is NOT a three-way comparison. It is a LADDER (Albert's cost decision,
`MACRO_FIRST_REDESIGN.md` §8.2): the cheapest candidate that passes KEEPS the seat;
stronger candidates are never even tried unless the cheaper one fails.

1. Seat `claude-haiku-4-5` (per §4 steps 1–3, on `default_interview_route` +
   `model_pool_interview`).
2. Run the acceptance battery B1–B10 (`MACRO_FIRST_REDESIGN.md` §1) through the real
   chat endpoint. Score each 0–2 against the battery's rubric; record in
   `evals/macro-first-battery.md` AND the bake-off file.
3. Total ≥18/20 AND no individual question at 0 → Haiku stays. DONE — do not try the
   others.
4. Else seat `google/gemini-2.5-flash`, repeat. Pass → done.
5. Else seat `claude-sonnet-5`, repeat. (If even Sonnet fails, the problem is the
   context pack or prompt, not the model — stop and fix that; see F9 in the redesign
   doc.)
6. Pool after the ladder: winner primary; the two non-winners as fallbacks in
   ascending-cost order.

Also verify with the winner seated: one claim-review question send (text reads
correctly, zh-CN recipient gets Chinese) and — ONLY if Albert explicitly opens a live
test window — one interjection latency check. Live interjections are clamped off in
settings; do NOT unclamp them for this bake-off.

---

## 6. Decision rule (all slots except BO-6's ladder)

1. Compute weighted scores per the slot's rubric.
2. If the top two are within 5 percentage points, the CHEAPER model wins (cost policy).
3. The winner becomes `default_<slot>_route`; runners-up become the pool in score
   order: `model_pool_<slot> = [winner, second, third]`.
4. If ALL candidates score under 60%, do not seat anyone new — restore the snapshot,
   record the failure, and escalate to Albert: the pass's prompt/design needs work
   before a model choice is meaningful.
5. A seeded default may only be changed by this rule. Record the decision and the new
   settings values in the results file and in `HANDOFF.md`.

## 7. Cleanup checklist (run after EVERY bake-off session, even aborted ones)

- [ ] All `default_*_route` / `model_pool_*` values restored or set to the decided
      winners (compare against the §4 step-2 snapshots).
- [ ] No one-element pools remain in prod settings.
- [ ] Settings values verified single-encoded.
- [ ] Fixture document re-ingested to a clean `complete` state (not left half-wiped).
- [ ] Live-interjection clamps untouched (`max_oracle_interjections_per_hour = 0`,
      `teams_live_recall_min_confidence_to_post = 101`).
- [ ] Results committed to `evals/bakeoffs/` (ask Albert before pushing, per repo rule).
- [ ] `HANDOFF.md` updated with the outcome and any settings now different from seeds.

## 8. Results file template (`evals/bakeoffs/<slot>.md`, append per candidate run)

```
## <date> <slot> — <provider>/<model> — run <n>
- settings snapshot before: default=<...> pool=<...>
- trigger runs: <run ids>
- attempt row: provider=<..> model=<..> success=<true/false> error=<...>
- usage: input_tokens=<..> output_tokens=<..> cost_usd=<..> duration_s=<..>
- metric scores: <metric>=<value> ... weighted_total=<..%>
- artifacts: <map id / claim counts / answer transcript path>
- notes: <anything odd — instability, retries, partial failures>
```

And per slot, one final block:

```
## DECISION <date> <slot>
- ranking: 1. <model> (<score>) 2. ... 3. ...
- rule applied: <top-2-within-5%→cheaper / clear winner / all-under-60%→escalated>
- settings written: default=<...> pool=[...]
- recorded in HANDOFF: yes
```

## 9. Deviations log

If a step could not be executed as written, record here: date, step, why, what was
done instead. An empty section means the spec was followed exactly.

*(empty)*
