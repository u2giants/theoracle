# HANDOFF — Prior completed work and remaining historical watchouts

Last updated: 2026-07-03. Delete this file once the remaining open items below are closed.

HOW TO TRUST THIS DOC: the 2026-07-02 macro-understanding block below is closed out. Older dated sections are retained only for history and implementation context; do not treat them as next actions when they conflict with current code or deployment state.

### ⚠️ Active runtime failures — see `AGENT_ERROR_LOG.md` (2026-07-03)

`AGENT_ERROR_LOG.md` is the designated in-repo log of runtime worker failures, written so a coding agent can fix them. It is REQUIRED reading. Open right now:
- **ERR-001 + ERR-002 — ✅ FIXED & VERIFIED IN PROD (2026-07-03, worker `20260703.4`).** The macro/holistic layer (`source-outline`, `macro-relationship-extraction`, `source-coverage-audit`) had hard-failed on every run. Two root causes, both fixed and verified live:
  - **Model route:** it borrowed the `general` slot (Qwen, no strict schema, no fallback). Now a dedicated **`macro` slot** with an admin picker (`default_macro_route`) + **fallback pool** (`model_pool_macro`). **Key discovery from the fallback logs: Gemini 2.5 flash *and* pro also reject the nested macro schemas (`400 too-complex`)** — so the primary is now **`openai/gpt-4.1-mini`** (Gemini is fallback only). The pool is what made the layer survive both the Qwen and Gemini failures — it is load-bearing.
  - **SQL:** three support-claim queries hit `42P10 (SELECT DISTINCT / ORDER BY)` — fixed.
  - **Verified:** migrations `83/84/85` applied to prod; workers deployed `20260703.4`; `macro_relationships` inserted, `source_coverage_findings=4`, `documents.macro_health=complete` on a clean run (`run_cmr5h0izj…`, attempt `openai/gpt-4.1-mini primary=true success`). Observability now real: `job_runs` + `documents.macro_health` are written by all macro workers.
  - **Implemented locally after the prod fix (needs deploy/rerun verification):** `model_pool_macro` is exposed in the model-pool-editor UI; `macro_health` renders in Admin → Documents; **ERR-003** followup fan-out is debounced so lens fan-out claims a one-time macro dispatch latch, and coverage now runs after macro. **Still open (non-blocking, tracked in `fix_enhancement.md`):** Bug D (relationships born `blocked_pending_support`, confirmed live), deeper workflow-map artifact/eval fixture work, and optional schema-repair hardening. See `AGENT_ERROR_LOG.md` + `fix_enhancement.md`.
- **Verified clean:** `@oracle/{ai,db,workers}` typecheck; `verify:r2` + `verify:auxiliary-defaults` pass. Web typecheck has a pre-existing `@oracle/engines` workspace-link issue unrelated to these changes. **Code changes are NOT committed/pushed** (per repo rule — push only when asked). Prod DB + Trigger workers ARE updated. `default_general_purpose_route` was left on Qwen (correct — `general` is still the utility slot).

The full holistic-understanding diagnosis + fix plan for the swimlane-diagram class of document lives in `fix_enhancement.md`.

---

## Macro understanding implementation — 2026-07-02

Status:
complete. Macro understanding, automatic followups, hardening fixes, and document lens fan-out were implemented, migrated, deployed, committed, pushed, and verified through CI on 2026-07-02.

What is fully done:
- Added macro-understanding schema and hand-written migration `packages/db/migrations/sql/79_macro_understanding.sql`.
- Added source outline, macro relationship, and coverage audit prompts under `packages/ai/src/prompts/`.
- Added Trigger.dev tasks `source-outline`, `macro-relationship-extraction`, and `source-coverage-audit`.
- Added budgeted document lens fan-out via `apps/workers/src/lib/document-lens-budget.ts`, `apps/workers/src/trigger/document-lens-extraction.ts`, and migration `packages/db/migrations/sql/81_macro_lens_fanout_settings.sql`.
- Wired document ingestion to optionally inject source-outline guidance, label claim kinds, and dispatch source-outline orchestration; `source-outline` now dispatches budgeted lens passes plus macro relationship and coverage followups.
- Carried claim kind/confidence through extraction candidates, promotion, and admin claim review.
- Added `/admin/macro` for reviewing/approving/rejecting macro relationships, dropping support links, running coverage audits, converting findings into gaps, and manually authoring relationships from approved claims.
- Added approved macro-relationship helpers in `packages/oracle-engines/src/macro/approved-relationships.ts`; chat and Brain synthesis now consume approved relationships only after read-time support-claim verification.
- Updated `docs/architecture.md`, `docs/macro-understanding-implementation-plan.md`, `DECISIONS.md`, and AGENTS routing/pending-work notes.

What is partially done:
- Production calibration/evals and broad historical-document backfills remain product/ops follow-ups, not unfinished implementation.
- `macro_outline_injection_enabled` is seeded false; enabling outline injection into the broad extraction prompt remains a rollout decision after a small admin-reviewed pilot. Lens fan-out itself is separately controlled by `macro_lenses_enabled`.

Exact next action:
- No code/deploy continuation is required for the macro work. For operations, run a small admin-reviewed pilot, review macro relationship queue quality, then decide whether to enable `macro_outline_injection_enabled`.

Known risks / blockers / unknowns:
- Existing documents are not backfilled automatically; run outline/macro/audit actions manually or add a deliberate backfill job later.
- No production calibration/eval pass has been run for the new macro prompts yet.
- Approved macro relationships intentionally cite approved claim IDs, not raw outline prose. Do not weaken that provenance boundary.
- Lens fan-out is intentionally budget-clamped by `macro_max_lenses_per_document`, `macro_max_lens_groups_per_document`, `macro_max_lens_model_calls_per_document`, and `macro_max_lens_estimated_input_tokens`.

Verification already run in this checkout:
- PASS: production DB migration via `pnpm db:migrate` (`79_macro_understanding.sql` applied).
- PASS: production DB migration via `corepack pnpm --filter @oracle/db migrate` (`81_macro_lens_fanout_settings.sql` applied).
- PASS: DB verification found `source_outlines`, `macro_relationships`, `source_coverage_findings`, claim-kind columns, and `macro_outline_injection_enabled`.
- PASS: Trigger.dev prod worker `20260702.1` deployed with 24 tasks.
- PASS: Trigger.dev prod worker `20260702.6` deployed with 26 tasks, including `document-lens-extraction`.
- PASS: GitHub PR check for `87a6cb3 feat(macro): ship document lens fan-out`.
- PASS: per-package `tsc --noEmit` through root `corepack pnpm exec tsc` for shared, db, auth, oracle-engines, ai, workers, and web.
- PASS: `corepack pnpm exec tsx packages/oracle-engines/src/__verify__/r5-validator-smoke.ts`
- PASS: MCP registry, retrieval filter parity, Vertex file-cache, Vertex inline-image, and auxiliary-model guards through root `corepack pnpm exec tsx`.
- PASS: web lint via root ESLint binary from `apps/web`.
- PASS: production Next build via root Next binary from `apps/web`.
- PASS: `git diff --check`

---

## ACTIVE (2026-07-06): Macro-first redesign → see `MACRO_FIRST_REDESIGN.md`

### ▶ RESUME HERE (snapshot as of 2026-07-07, end of a long planning+build session)

**What this project is.** The Oracle extracted tiny quote-validated "claims" and never
understood whole business processes (proven on swimlane diagram `9d09fa89-…`: 241
fragment claims, zero assembled workflow). Albert approved a full **macro-first**
refactor: a durable, versioned **business model** (processes → stages/owners/systems/
gates/branches) becomes the primary understanding object; atomic claims are demoted to
the auditable **evidence layer** (quote-level provenance stays sacred). Chat/Brain will
reason from the model and cite claims downward. End goal: answer like a McKinsey
consultant, every assertion traceable to a quote. Full plan: `MACRO_FIRST_REDESIGN.md`
(the forward brief, 0–9 staged). `MODEL_BAKEOFF_SPEC.md` = empirical model selection.
`fix_enhancement.md` = superseded as a plan, kept as diagnosis + the §2.1 ground-truth
workflow read used as the gate answer-key.

**Git state:** `main` clean, all pushed, HEAD `3037b88`. Parked branch
`wip/vision-cache-tests` (`75291d9`) holds an unrelated, untested vision/cache
workstream — leave it until someone runs `test_code_changes.md` Tests 1–2.

**Done and verified:**
- **Stage 1 (schema + §4.8 transaction contract)** — code merged; migration
  `86_macro_first_schema.sql` (amended by `01ed195` to drop a stale orphan prod table)
  **APPLIED TO PROD `eqccjfbyrywsqkxxpjvg` and fully verified** (12 tables, RLS on +
  zero policies, partial-unique idempotency indexes, 13 settings 44→57 single-encoded).
  Details in the dated block below.
- **Stage 2 (workflow reader)** — `source-workflow-read` worker/service + flat
  `workflow-read-v1` prompt/schema built, deployed prod (Trigger `20260707.2`).
  Ingestion now AWAITS the reader before extraction, writes immutable superseding
  `source_workflow_maps`, validates evidence quotes with the real validator, injects
  the map as non-quotable extraction guidance, carries `mapElementRef` into claims.
  Two live bugs found in review and **already hotfixed** (`37ee7d5`): failed/pending
  maps no longer poison retries; cross-window edge IDs no longer mangled.

**NEXT ACTIONS, in order:**
1. **Implement the Stage 2 reader-failure fallback** (deviation #1, spec in
   `MACRO_FIRST_REDESIGN.md` §5.1 + open-items list below). Small; should land before
   the gate so the gate measures intended behavior.
2. **Run the Stage 2 gate** (NOT yet done — this is the real proof the redesign works):
   re-ingest doc `9d09fa89-3a46-465e-a98b-837287c9e22a` via
   `scripts/reevaluate-document.mjs` (DRY-RUN by default; prod DB access via the
   1Password session pooler, NEVER local `.env.local` which points at the OLD project),
   then score the produced `source_workflow_maps` row against `fix_enhancement.md` §2.1.
   PASS = ≥90% of ground-truth nodes/edges survive validation; also confirm re-ingest
   supersedes cleanly and a forced reader failure shows in `macro_health`. Then run
   BO-1/BO-2 bake-offs (`MODEL_BAKEOFF_SPEC.md`). Record in `evals/` per the spec.
3. Then **Stage 3** (map-directed extraction + edge-dedup + kill lens fan-out) →
   Stage 4 (shadow merge) → Stage 5 (transactional apply/review) → 6 answering → 7
   consultant → 8 backfill → 9 cleanup.

**HOW TO RUN EACH STAGE (working pattern, keep using it):** spin up a FRESH-context
agent (clean window beats continuity — everything durable is in the docs/code/prod, and
stale context causes errors). Codex CLI has been doing implementation well; use a
sub-agent for prod DB ops. Seed each with: this RESUME block, the relevant
`MACRO_FIRST_REDESIGN.md` §9 stage entry + its §5.x, and `AGENTS.md`. After each stage:
typecheck, run the stage gate, update THIS file, deploy + record the Trigger version.
Albert pushes to `main` from his own machine; commit only when he says so (he has).

**HARD RULES that bit us already:** local `.env.local` → OLD Supabase project, never
migrate prod from it (use 1Password session pooler). Flat schemas only (Qwen/Gemini
reject nested — D6). No new Trigger SCHEDULED tasks (10/10 full). Every new worker
writes `job_runs` + `macro_health` (silent failures hid ERR-001 for weeks). Verify a
sub-agent's/Codex's work — this session caught real bugs in otherwise-good output every
time by reading the diff and running the gates.

**Two OPEN Stage 2 deviations** (fixes already spec'd in `MACRO_FIRST_REDESIGN.md`
§5.1/§5.2; also listed in the Stage 2 block below): (1) reader is currently a HARD
dependency of ingestion — add `require_workflow_map_for_ingestion` (seed false) blind-
path fallback; (2) owner/system names stored raw — the merge worker (Stage 4/§5.3) must
resolve them to `entities` / file `entity_proposals`.

---

Albert approved refactoring the Oracle to a macro-first architecture (business model as
the primary understanding object; claims demoted to the evidence layer). The complete,
self-contained implementation brief — keep/kill inventory, target schema, staged plan
with verification gates, and pre-made decisions for forks — is `MACRO_FIRST_REDESIGN.md`.
It SUPERSEDES `fix_enhancement.md` as the forward plan (that file remains the diagnosis
record and ground-truth workflow read). Start at Stage 0 (baseline), and note the
redesign doc's warning: commit/deploy the currently-uncommitted working-tree changes
with Albert's sign-off before starting.

Companion spec: **`MODEL_BAKEOFF_SPEC.md`** — the complete protocol for empirically
choosing the model for every LLM pass (one-element-pool isolation, per-slot fixtures
and rubrics, cheap-first conversation ladder, decision rules, settings-restore
checklist). The redesign's §8 admin "Model passes" table (8 rows, primary + 2
fallbacks each, Copy-job-brief per row) seeds Claude's suggested defaults; stage gates
2/3/4/6/7 each require the corresponding bake-off from the spec. BO-1 (vision) can run
immediately and folds in the pre-existing `test_code_changes.md` Test 2.
2026-07-06 update: a Codex CLI review of both docs was adopted — new §4.8
state-machine/transaction contract (optimistic locking, rebase, idempotency keys),
per-claim eligibility checks in bundle approval, cross-source canonical dedup,
supersede-not-replace maps, and a restaged 0–9 plan (schema+contract first, shadow-mode
merge before transactional apply, backfill split from cleanup).

2026-07-07 local Codex implementation update (not committed, not migrated, not
deployed): Stage 1 foundation is implemented in source. Added hand-written migration
`packages/db/migrations/sql/86_macro_first_schema.sql` for source workflow maps,
business-process graph/version tables, model-change proposals/events, recommendations,
claim/candidate map-element linkage, process-serving settings, and model-pass pool
settings. Mirrored the tables in `packages/db/src/schema.ts`; added macro-first
workflow/model-merge route slots and fallback pools in `packages/ai/src/routes/*`;
expanded Admin → Settings / model pool to the eight macro-first model passes while
leaving the legacy `macro` slot resolvable for old workers until Stage 9 cleanup; and
added `packages/oracle-engines/src/model/lifecycle.ts` with the status-machine helpers
and advisory-lock / optimistic-lock apply transaction skeleton. Verification run
locally: `corepack pnpm -r typecheck`, `corepack pnpm --filter @oracle/engines run
verify:macro-first`, and `git diff --check` all pass. Not run: Stage 0 prod battery,
prod migration, RLS live checks, fresh-DB idempotency, Trigger deploy, or any LLM/worker
behavior.

2026-07-07 local review fix (not committed, not migrated, not deployed): Hardened
`applyBusinessModelChangeTransaction` against the Stage-1 TOCTOU bug by re-reading the
proposal after the advisory lock, no-oping terminal statuses, status-guarding
`needs_rebase` / `failed_apply` updates, and adding smoke coverage for stale-base and
failed-apply overwrite guards. Added read-only empty-state admin pages for
`/admin/business-model` and `/admin/recommendations`.

2026-07-07 Codex Stage 2 implementation update (committed, pushed, deployed):
Added the macro-first `source-workflow-read` worker/service and flat
`workflow-read-v1` prompt/schema. Document ingestion now awaits the workflow reader
after chunk persistence and before claim extraction, writes immutable
`source_workflow_maps` rows (`pending` → `validated`/`degraded`/`failed`,
superseding older active maps), validates node/edge evidence quotes against cited
chunks, records job/model/context-pack observability, and injects the rendered
workflow map into every extraction window as non-quotable guidance. Extraction schema
version is now `2.4.0` with optional `mapElementRef`; document candidates and newly
inserted claims persist that ref. The old post-extraction fire-and-forget
`source-outline` dispatch and `macro_outline_injection_enabled` loader were removed
from `document-ingestion`, but legacy source-outline/lens files still exist for Stage
3 cleanup. Added `@oracle/ai` smoke gate `verify:workflow-read`. Commit:
`5acddc9 feat(macro): add source workflow reader`. Trigger.dev prod deploy:
`20260707.1` with 27 detected tasks, deployment `hxvtrlqa`
(`https://cloud.trigger.dev/projects/v3/proj_wgpzsvhmsopqhvwqaycn/deployments/hxvtrlqa`).
Verification run
locally: `corepack pnpm --filter @oracle/ai run verify:workflow-read`,
`corepack pnpm -r typecheck`, `corepack pnpm --filter @oracle/ai run
verify:auxiliary-defaults`, `corepack pnpm --filter @oracle/ai run verify:r2`,
`corepack pnpm --filter @oracle/engines run verify:r5`, `corepack pnpm --filter
@oracle/engines run verify:macro-first`, and `git diff --check`. Not run: live Stage
2 gate on document `9d09fa89-3a46-465e-a98b-837287c9e22a`, BO-1/BO-2 bake-offs, or
prod re-ingest.

2026-07-07 Stage 2 hotfix (committed, pushed, deployed): fixed two live
workflow-reader bugs. Failed/pending same-hash maps are no longer treated as reusable
idempotency hits; only active `validated`/`degraded` maps are skipped, with degraded
health mirrored correctly. Multi-window ID prefixing now preserves endpoints that
already refer to prior-window node IDs, so cross-window edges are not deterministically
dropped. Added `@oracle/workers` smoke gate `verify:source-workflow-read`. Commit:
`37ee7d5 fix(macro): retry failed workflow reads`. Trigger.dev prod deploy:
`20260707.2` with 27 detected tasks, deployment `yvrhtfyg`
(`https://cloud.trigger.dev/projects/v3/proj_wgpzsvhmsopqhvwqaycn/deployments/yvrhtfyg`).
Verification run locally: `corepack pnpm --filter @oracle/workers run
verify:source-workflow-read`, `corepack pnpm --filter @oracle/workers typecheck`,
`corepack pnpm -r typecheck`, and `git diff --check`.

**OPEN — Stage 2 deviations from the plan (correct fixes now written into
`MACRO_FIRST_REDESIGN.md`; implement in a later session):**
1. **Reader-failure fallback (§5.1).** As shipped, the workflow reader is a HARD
   dependency: if all `workflow_read` pool models fail, the whole document fails, so a
   reader outage would halt ALL document ingestion. Target: gate on new setting
   `require_workflow_map_for_ingestion` (seed `false`); on total reader failure, log
   loudly, set the map `failed` + `macro_health='map_failed'`, and CONTINUE to
   blind-path extraction so the document completes `degraded` rather than failing.
   Land this before declaring the Stage 2 gate green.
2. **Entity resolution deferred (§5.2).** The reader stores `ownerName`/`systems` as
   raw strings and does not resolve them against `entities` or file `entity_proposals`
   yet. Accepted as a deferral ONLY if the merge worker (§5.3) does the resolution when
   it writes durable `process_node` owner FKs + `process_node_systems` (preserving the
   no-silent-entity-invention invariant). Nothing downstream consumes the unresolved
   FKs until merge exists, so this is not urgent — but it must be done at/by merge.

2026-07-07 Stage 2 live gate (not committed yet): PASS for the workflow-reader gate on
the canonical swimlane fixture with one explicit limitation. The destructive clean
re-ingest path was blocked by the existing provenance guard (old fixture claims have 1
Brain citation and 2 gap references), so the gate ran `source-workflow-read` directly
against the existing chunks instead of wiping the document. Live checks completed:
first read `run_cmra2epx05qke0kmvp80vlrmd` produced a validated map with
`keptCount=151`, `droppedCount=0`; same-content redispatch
`run_cmra2g75q5z1m0wmvs9b47pz9` returned `skipped_existing`; forced rerun
`run_cmra2gfri5u5l0mmzn7adxwj0` superseded the old map and produced one active map;
controlled invalid-route failure `run_cmra2iihl5v400mmzp0rich66` wrote a failed map and
set `documents.macro_health='failed'`; repair/final runs restored health. Final active
map `72ed0ef9-8ea7-4e60-84a3-a7e9236eb7c8` from
`run_cmra2ork561l00jonzlrqxfcv` is `validated`, `nodes=63`, `edges=71`, `lanes=14`,
`paths=1`, `keptCount=149`, `droppedCount=0`; document is back to
`status='complete'`, `macro_health='complete'`, `processing_error=NULL`, and exactly
one non-superseded map remains. Scored against `fix_enhancement.md` §2.1, it covers
9/9 stage groups plus the named branch/loop/system landmarks. The run exposed a model
route issue: `claude-sonnet-5` failed before the Anthropic temperature request-shape
guard landed, and Gemini 2.5 Pro rejected the schema as too complex, while
`openai/gpt-4.1` succeeded. Updated source defaults/docs and prod settings to make
`default_workflow_read_route='openai/gpt-4.1'` and
`model_pool_workflow_read=['openai/gpt-4.1','anthropic/claude-sonnet-5','google/gemini-2.5-pro']`.
Recorded the gate in `evals/macro-first-battery.md`. Anthropic temperature handling is
now guarded by `verify:adapter-request-shapes`; rerun BO-2 before seating Sonnet as the
workflow-read primary again.

#### 2026-07-06 — Stage 1 migration 86 **APPLIED TO PROD and VERIFIED** ✅

Migration `packages/db/migrations/sql/86_macro_first_schema.sql` (as amended by commit
`01ed195`) was applied to prod (`eqccjfbyrywsqkxxpjvg`) in one shot and fully verified.
Note: a first attempt earlier the same day ABORTED with zero prod changes — prod had an
orphan legacy `source_workflow_maps` table (pre-Stage-1 shape: `source_outline_id` /
`workflow_version` / `coverage_json`, 0 rows, defined by no migration) which made the
original migration fail `42703: column "channel_id" does not exist` at the new unique
index. Albert approved the guarded reconciliation pre-step in `01ed195` (drops ONLY that
legacy shape, ONLY when empty, raises loudly if it holds rows, no-op on fresh DBs and
re-runs), which resolved it.

Access notes: psql and Supabase MCP were unavailable; apply/verify ran via the `pg` node
client over the 1Password **session pooler** (`aws-1-us-east-1.pooler.supabase.com:5432`)
— the direct `db.<ref>.supabase.co` host does not resolve locally (IPv6-only).

Verification results (all read-only, post-apply):
- **3a PASS** — all 12 tables exist (source_workflow_maps, business_processes,
  business_process_versions, process_nodes, process_edges, process_node_systems,
  process_paths, process_element_claims, process_top_domains, business_model_changes,
  business_model_change_events, recommendations).
- **Legacy drop confirmed** — `source_workflow_maps` now has the NEW 20-column shape
  including `source_type, channel_id, segment_ref, source_content_hash, map_kind,
  lanes_json, validation_json, superseded_by_map_id, finalized_at`.
- **3b PASS** — `relrowsecurity = true` on all 12; `pg_policies` empty for all 12
  (RLS enabled, zero policies → service-role only).
- **3c PASS** — partial unique indexes exist:
  `source_workflow_maps_active_source_hash_unique`,
  `business_model_changes_active_idempotency_unique`,
  `process_element_claims_primary_unique`.
- **3d PASS** — new columns exist: `extraction_candidates.map_element_ref`,
  `claims.map_element_ref`, `claim_review_events.review_source`,
  `claim_review_events.business_model_change_id`.
- **3e PASS** — `documents_macro_health_check` re-created and includes `map_failed`
  (and `map_degraded`, `merge_pending_review`).
- **3f PASS** — all 13 new settings rows seeded and **single-encoded** (jsonb_typeof
  boolean/number/string/array as appropriate; pools are real JSON arrays, not escaped
  strings). Settings count went **44 → 57** (+13, matching the seed block).
- **3g PASS** — idempotency: re-ran ONLY the settings INSERT … ON CONFLICT DO NOTHING
  block a second time; count unchanged at 57.
- **3h NOT TESTED** — anon-key access denial was not exercised: this session only had the
  postgres pooler connection (service path), no anon key. RLS-enabled + zero policies
  implies anon deny, but a live anon probe remains open.
- **Task 4 PASS** — all 9 pre-existing model-pass settings present alongside the new ones:
  `default_vision_route`, `default_interview_route`, `model_pool_interview`,
  `default_synthesis_route`, `model_pool_synthesis`, `default_extraction_route`,
  `model_pool_extraction`, `default_translation_route`, `default_general_purpose_route`.
  None missing.

Remaining for the Stage 1 gate:
- Albert's visual check of Admin → Settings "Model Passes" (all 8 rows render with seeded
  pools) — data side is verified; UI not exercised (no auth bypass attempted).
- Live anon-RLS probe (3h above).
- Fresh-DB idempotency apply (gate wording): prod re-run idempotency of the settings block
  is proven; a full fresh-DB apply was not run this session.

Next step: Stage 2 (`source-workflow-read` worker). UNBLOCKED 2026-07-06: the 8
uncommitted cache-workstream files were parked on branch `wip/vision-cache-tests`
(commit `75291d9`), so the main working tree is clean. Run Stage 2 in a FRESH session
seeded with `MACRO_FIRST_REDESIGN.md` (§9 Stage 2 + §5.1/§5.2) + this file. No Trigger
deploy was done in Stage 1 (no worker changes).

---

## ACTIVE (2026-07-06): Vision transcription & claim-extraction test plan → see `test_code_changes.md`

We ingested a swimlane process diagram (test doc `9d09fa89-3a46-465e-a98b-837287c9e22a`) and the Oracle drew many wrong conclusions from it. We root-caused the failures (image→text→claims pipeline; the extractor never sees the image), made a first round of code changes (information-weight windowing, `buildStandardAdapters` adding deepseek+qwen, `decideCacheProfitability` cache gating, admin cache visibility, a new `verify:openai-qwen-cache` gate), and defined **two tests** to run next in a fresh session:

1. **Test 1** — faithfulness: what the system transcribes/claims vs. a human reading of the diagram (scored rubric + ground truth).
2. **Test 2** — 5 vision models head-to-head on transcription quality **and** prompt-cache effectiveness (to decide whether good caching lets us afford a stronger/more expensive vision model than the current `qwen/qwen3-vl-235b-a22b-thinking`).

**`test_code_changes.md` is the complete, self-contained brief** — background, every change made and not-yet-made, prior bake-off results, ground truth, step-by-step commands, cache-metric locations, cost model, and env/tooling. Written for a developer new to the app. Start there.

**2026-07-06: this workstream's code changes are parked on branch
`wip/vision-cache-tests` (commit `75291d9`)** — they were untested and sat uncommitted
in the main working tree, blocking macro-first Stage 2 (which must edit
`document-ingestion.ts`). To resume: check out that branch, rebase onto current
`main`, run Tests 1–2, then merge deliberately.

---

## Four model-adapter bugs fixed + extraction bake-off — 2026-06-26 (DONE: fixed, proven, deployed, prod set)

Status: complete. Code on `main` (`c9cc5d0`), prod worker deployed (`20260626.7`), prod settings updated to the bake-off winner. All four bugs were live-API proven, not just typechecked.

The four bugs (all were silently masked by pool fail-over, so most candidate models looked "fine" while actually 400ing instantly):
1. **OpenAI strict structured output** rejected the extraction schema — optional Zod fields were absent from the JSON-schema `required` array. Fix (`packages/ai/src/providers/openai-adapter.ts` `walk()`/`makeNullable()`): OpenAI-only transform makes formerly-optional properties nullable AND promotes `required` to all keys; `extraction-system.ts` optionals mapped to `.nullish()`. Gemini/Vertex still receive the original schema. PROVEN: `gpt-4o-mini` + `gpt-4.1-mini` return schema-valid claims live.
2. **Gemini Google-API hard 60s timeout** aborted dense extraction at ~60.1s. Fix (`google-gemini-adapter.ts`): `DEFAULT_GEMINI_REQUEST_TIMEOUT_MS=180_000`, overridable via `GOOGLE_GEMINI_REQUEST_TIMEOUT_MS` env or constructor; applied on both the API-key SDK path and the OAuth/REST path. PROVEN: `google/gemini-2.5-flash` extraction completes at 59.8s where it previously aborted.
3. **Gemini `thinkingLevel` broke gemini-2.5-flash vision** ("Thinking level not supported"). Fix is capability-driven, NO hard-coded model ids: new `geminiThinkingStyle` (`thinking_budget` for Gemini 2.x, `thinking_level` for 3.x, `none`) in `routes/types.ts` + `routes/resolve.ts`; the adapter emits the field shape each model generation supports. PROVEN on a real image: `google/gemini-2.5-flash` vision call succeeded.
4. **Settings double-JSON-encoding.** Data was already repaired; the writer is now idempotent via `normalizeSettingValue()` (`packages/ai/src/routes/settings-encoding.ts`), applied in the admin settings POST (`apps/web/app/api/admin/settings/route.ts`). Regression guard: `packages/ai/src/__verify__/settings-encoding.ts`. Prod scan: 0 double-encoded of 29 settings.

Extraction bake-off (test doc `9d09fa89-3a46-465e-a98b-837287c9e22a`, vision held at qwen3-vl, each model isolated into a one-element pool so fail-over could not mask failures):
- `gpt-4o-mini` → 9 claims · `gpt-4.1-mini` → 12 · **`google/gemini-2.5-flash` → 54 (dep 47 / process_rule 5 / exception_rule 2 — captured conditional branches)** · `vertex/gemini-2.5-flash` → 52 (all flat dependency that run) · `gemini-3.1-flash-lite` → 5.
- Winner: `google/gemini-2.5-flash` — most claims, best type variety, faithful verbatim edge quotes, faster than Vertex (59.8s vs 68.5s).

FINAL PROD CONFIG (verified single-encoded):
- `default_extraction_route = google/gemini-2.5-flash`
- `model_pool_extraction = [google/gemini-2.5-flash, vertex_gemini_2_5_flash_extraction_primary, openai/gpt-4.1-mini]` (vendor + infra diverse; all three confirmed working)
- `default_vision_route = qwen/qwen3-vl-235b-a22b-thinking` (kept — proven person-level lane attribution + cross-vendor diversity)
- `enforce_model_capabilities = true`, `default_extraction_reasoning_effort = off`, `default_vision_reasoning_effort = medium`

Vision side-finding (optional follow-up): `google/gemini-2.5-flash` vision works post-fix, is ~3× faster than qwen3-vl (33s vs ~90s) and yielded the single richest extraction (60 claims), and its transcript is faithful — BUT it labeled some person-lanes by department ("Carlos" absent where qwen3-vl names him). To switch vision to it, set `default_vision_route = "google/gemini-2.5-flash"` (no pool change needed; `model_pool_vision` does not exist — vision routes directly off `default_vision_route`).

New env var documented: `GOOGLE_GEMINI_REQUEST_TIMEOUT_MS` (optional; default 180000).

---

## Fail-loud routing + conversation-aware extraction completion — 2026-06-26

Status:
done in source, pushed, migrated, and worker-deployed.

Done:
- Committed and pushed `8e0a45c` (`feat(ai): remove silent fallbacks and preserve extraction conversations`) to `main`.
- Applied prod DB migrations/seeds against current prod Supabase `eqccjfbyrywsqkxxpjvg` using the 1Password current-prod session pooler.
- Deployed Trigger.dev prod worker version `20260626.5`.
- Reran GitHub Actions `PR check` for the pushed commit; final rerun passed.
- Implemented `fix_claim_extr.md`: sync and batch claim extraction now claim whole same-channel conversation segments and include prior same-channel complete/skipped messages only as non-quotable carry-in context.
- Verified prod settings after migration:
  - `default_extraction_route = google/gemini-3.1-flash-lite`
  - `default_general_purpose_route = qwen/qwen3.7-max`
  - `default_translation_route = qwen/qwen-mt-plus`
  - `default_vision_route = qwen/qwen3-vl-235b-a22b-thinking`
  - `extraction_char_budget = 24000`
  - `extraction_carry_in_count = 12`
- Reconciled production Drizzle journal drift for generated migration `0007_tricky_charles_xavier.sql`: prod already had the `claim_translations` table plus `claims.source_lang` and `employees.locale`; CI expected the LF checkout hash `af12b253571b59ea7c214c978f11c21ef216bcca8e0dbe885ce61a011594cb5f`.
- Added missing local/session secrets to 1Password `vibe_coding` as Secure Notes: `Supabase Runtime Keys - The Oracle (oracle.old local .env.local)`, `OpenRouter API Key - The Oracle (local .env.local)`, `Trigger.dev Secret Key - The Oracle (local .env.local)`, and `Vercel OIDC Token - The Oracle (local .env.local)`.

Next action:
- No continuation is required for this workstream. Web deployment was not directly confirmed through Vercel CLI/MCP because local Vercel metadata was absent and the CLI status check timed out; the pushed commit's Next.js build and CI passed, and the repo's Vercel Git integration remains the expected web deploy path.

Risks / watchouts:
- Local `.env.local` still points at `oracle.old` (`vokucjpanhvqunimlvsp`). Do not run prod migrations from local env without overriding `DIRECT_URL` to the current prod 1Password session pooler.
- The migration runner hashes generated Drizzle files from the current checkout. Windows CRLF vs CI LF can surface as journal drift if a generated migration was previously recorded with a different line ending hash; reconcile only after verifying the schema objects already exist.

---

## Test plan run — 2026-06-26

Ran `fix_TESTPLAN.md` as far as current prod access/state allows.

Static gates:
- PASS: `corepack pnpm -r typecheck`
- PASS: `corepack pnpm --filter @oracle/ai run verify:r2`
- PASS: `corepack pnpm --filter @oracle/ai run verify:vertex-inline-image`
- PASS: `corepack pnpm --filter @oracle/engines run verify:r5`
- PASS: `corepack pnpm --filter @oracle/engines run verify:r7`
- PASS: direct recursive lint via `corepack pnpm -r --if-present run lint`
- PASS: direct recursive build via `corepack pnpm -r --if-present run build`
- NOTE: root `pnpm lint` / `pnpm build` still fail in this local shell because Turbo cannot find a plain `pnpm` binary; `corepack pnpm` works, but `pnpm` is not on PATH and `corepack enable` cannot write to `C:\Program Files\nodejs`.

Code fix made during testing:
- Fixed React purity lint in `apps/web/app/admin/_components/model-attempt-alert-banner.tsx` by replacing render-time `Date.now()` with SQL `now() - interval '7 days'`.

Prod prep:
- Applied prod migrations through `corepack pnpm --filter @oracle/db migrate` using the current prod session pooler from 1Password.
- Deployed Trigger worker from local source: prod worker version `20260626.1`, 21 tasks.
- WARNING: the migration runner's seed step reset model settings to legacy defaults. Restored the pre-run Qwen-oriented pools/routes, then intentionally set `default_extraction_route='google/gemini-3.1-flash-lite'` for the image test and kept it there because the test succeeded. Also corrected `default_interview_route='anthropic/claude-haiku-4-5-20251001'` so it matches `model_pool_interview`.

Live runtime results:
- PASS: no live references to `fallbackRouteId`, `DEFAULT_ORACLE_ROUTES`, or `FALLBACK_ROUTE_ID` under `packages` / `apps`.
- PASS: image document `9d09fa89-3a46-465e-a98b-837287c9e22a` re-evaluated and `document-ingestion` run `run_cmquevo9l5tc70un6px1u0xj8` completed: 3 chunks, 7 candidates, 7 promoted claims, 0 rejections. Document is `complete`, `processing_error=NULL`.
- PASS: latest vision run used `provider=qwen`, `model=qwen3-vl-235b-a22b-thinking`, success, no error. Latest extraction run used `provider=google`, `model=gemini-3.1-flash-lite`, success, no error.
- PARTIAL QUALITY: image claim mix was 4 `process_rule`, 1 `dependency`, 1 `exception_rule`, 1 `bottleneck`. This is not the dependency-dominated mix the plan hoped for, but it is no longer 0 claims and no longer ~80 shallow process-rule claims.
- PASS: document vision/extraction success attempts were recorded in `model_run_attempts`.
- PASS after config correction: `contradiction-watcher` run `run_cmquf1jks5yr80mn33f3kh7df` completed for claim `e2fa818d-c5aa-483a-afa8-43c305ad0367`.
- PASS/Loud failure: before correcting interview config, `contradiction-watcher` failed with `NoConfiguredModelError` instead of silently falling back.
- PASS/Loud failure: `claim-translation` run `run_cmquf0c885ycc0ulpsibvhupg` failed with `AllCandidatesFailedError` instead of silently falling back.

Failures / blockers found:
- FAIL: translation through `default_translation_route='qwen/qwen-mt-plus'` fails with `400 Role must be in [user, assistant]`. Likely adapter/message-shaping issue for Qwen MT, because the translation prompt uses a system block and Qwen MT rejects the resulting role shape.
- FAIL: the all-failed translation path did not write `model_run_attempts` rows, so 5.6 is not satisfied for auxiliary all-failed calls. Document success attempts do log correctly.
- FAIL/PARTIAL: capability probe temporarily set `default_vision_route='qwen/qwen3.7-plus'` and `resolveRouteCandidates(db, 'vision')` returned a candidate instead of skipping/refusing it. Either the catalog marks that model as vision-capable or auxiliary capability enforcement is too loose. The real setting was restored to `qwen/qwen3-vl-235b-a22b-thinking`.
- BLOCKED: synthesis could not be exercised as written because prod has 0 `brain_sections` rows, despite approved claims existing.
- BLOCKED/PARTIAL: taxonomy `general` picker is wired to `taxonomy-reevaluation-manual`, but prod approved claims mostly lack embeddings. Scoped run `run_cmquf23pr5voa0un6rrwvsl4t` completed without reaching cluster naming (`domainsReady=0`).
- NOT VERIFIED: interview/chat UI, admin alert banner live UI, chat image/PDF attachments, batch extraction mode, missing-key boot logs, graph 404 logging, OpenAI malformed batch-line logging. These need authenticated web/browser interaction, deliberate env breakage, or a batch fixture.

Final prod setting state after this run:
- `default_extraction_route = google/gemini-3.1-flash-lite`
- `default_vision_route = qwen/qwen3-vl-235b-a22b-thinking`
- `default_translation_route = qwen/qwen-mt-plus` (currently failing; see above)
- `default_interview_route = anthropic/claude-haiku-4-5-20251001`
- `enforce_model_capabilities = true`

Follow-up fix run (same day):
- Fixed Qwen MT translation by folding system instructions into the first user message for `claim_translation` / `qwen-mt*` calls, because MT models reject the OpenAI `system` role. Verified `claim-translation` run `run_cmqufk37c61jk0ioh15c84xdd` completed and wrote a `zh-CN` `claim_translations` row.
- Fixed auxiliary attempt logging for translation success and all-candidates-failed paths. Verified `model_run_attempts` records `task_type='claim-translation'`, `slot='translation'`, `provider=qwen`, `model=qwen-mt-plus`, `success=true`.
- Tightened runtime capability enforcement for Qwen vision models: non-VL/non-omni Qwen catalog entries are normalized to `vision=false`. Verified `default_vision_route='qwen/qwen3.7-plus'` now raises `ModelCapabilityError` for missing `vision`; prod setting restored to `qwen/qwen3-vl-235b-a22b-thinking`.
- Fixed the Qwen catalog source to honor `DASHSCOPE_BASE_URL`, matching inference.
- Fixed seed safety: migrations still seed defaults, but existing `settings.value` is no longer overwritten on conflict. Default model settings were also updated to the current approved pools/routes.
- Seeded stable `brain_sections` for every legacy knowledge domain so synthesis has targets. Verified prod now has 17 sections; `brain-synthesis` for `domain-costing` completed as run `run_cmqufzj4m63n40hojuh7ywtf4` and wrote draft version `3b6c7f6e-9dff-42bd-ad3c-4bbda0e95dba`.
- Increased on-demand `brain-synthesis` max duration from 10 minutes to 30 minutes, matching scheduled synthesis. A larger `domain-licensing` run hit the old 10-minute cap before this change.
- Fixed taxonomy reevaluation so historical approved claims without embeddings get embedded before clustering, instead of making the general-purpose picker path unreachable. Verified run `run_cmqug5j2m6e380on6lhxixis7` wrote one model-named proposal: `operations_systems` / `Design Workflow System Management`, with successful `taxonomy-cluster-naming` attempt rows through `default_general_purpose_route`.
- Fixed Qwen JSON-object calls to include an explicit JSON instruction when DashScope requires it for `response_format=json_object`.
- Applied prod migrate/seed after the seed fixes and deployed workers through prod version `20260626.4`.

---

## Current carried-over items — verified / cleaned up 2026-06-29

- **Worker deploy state is verified.** Trigger.dev MCP reports current prod worker `20260629.1` with 21 tasks. This deploy includes the R9 synthesis validator false-positive fix.
- **Fuller Brain synthesis has been exercised.** `brain-synthesis` for `domain-licensing` ran over 124 approved claims. The first run on worker `20260626.7` produced a valid-looking 5.5k-character draft but was rejected by false-positive named-entity validation (`Furthermore`, `Additionally`, possessive `Creative Director's`). The validator was fixed, verified with `@oracle/engines verify:r9`, deployed as worker `20260629.1`, and rerun. The successful run `run_cmqymg81k43rc0hke6yxu61gi` created current version `f3de1eff-52f5-4001-9cf5-a1521d7c082f`, `review_status='needs_review'`, linked 62 section claims, and updated `brain_sections.current_version_id`.
- **Diagram/image ingestion is no longer blocked by the old extraction-model issue.** Current prod config from the 2026-06-26 bake-off is `default_vision_route=qwen/qwen3-vl-235b-a22b-thinking`, `default_extraction_route=google/gemini-2.5-flash`, pool `[google/gemini-2.5-flash, vertex_gemini_2_5_flash_extraction_primary, openai/gpt-4.1-mini]`. The useful durable lesson is still: keep diagram transcription one-line-per-edge so strict quote validation can match relationship claims to persisted chunks.
- **Entity registry and active top-domains are seeded.** Do not repeat older notes claiming the registry is empty.
- **China bilingual setup is mechanically done.** Employees can be set to `zh-CN` in the UI, translation uses `default_translation_route`, and Qwen MT was verified after the system-role shaping fix. Optional product follow-up: admin side-by-side translation review.
- **Meeting-picker subject remains optional polish.** Discovery/ingest works, but `meeting_transcripts.subject` and participant names are not populated yet; see the meeting-picker section below.
- **Live Recall interjections remain intentionally clamped by confidence threshold.** Older notes disagree on `max_oracle_interjections_per_hour`; verify live settings before reopening tests.

---

## Meeting transcript picker (2026-06-24)

Status:
done + deployed (core). Optional follow-ups remain.

Done (live in prod, `main` == deployed):
- The Oracle no longer auto-ingests meetings. Discovery (webhook + `teams-transcript-discovery-scan`) records available meetings into `meeting_transcripts` (migration `77`, prod-applied); `/admin/transcripts` is a picker where an admin chooses which to ingest. Ingesting → `teams-transcript-ingestion` writes `messages` as `pending`, anchored to real meeting time, and flips the row to `ingested`. See DECISIONS.md `D-meeting-picker` + architecture.md. Worker `v20260624.5`; commits through `38ea974`.
- Also shipped this session: claims grouped by source + shift-click range select on `/admin/claims`.

Next action (optional, not blocking):
- Populate `meeting_transcripts.subject` (and ideally participant names) — the picker has the columns but only organizer + meeting time are filled today. Subject needs an extra Graph call (`onlineMeeting` details by join id) the discovery path doesn't make yet.
- Drop the now-unused `awaiting_approval` enum value + `raw_transcripts.approval_status` columns (migrations 75/76) in a future cleanup migration — left in place because removing a PG enum value is disruptive (see `D-meeting-picker`).
- Discovery scan is on-demand only (Trigger is at the 10/10 schedule limit). If a schedule slot frees up, consider a periodic scan so the picker stays fresh without a manual "Scan for recent meetings" click.

Risks / watchouts:
- Do NOT re-introduce auto-ingest in the webhook (it must stay discovery-only). See the AGENTS.md §10 quirk on transcript ids / pull endpoint for two bugs not to reintroduce.
- `.env.local` points at `oracle.old` (`vokucjpanhvqunimlvsp`), NOT current prod (`eqccjfbyrywsqkxxpjvg`). Local `pnpm db:migrate` hits the old DB unless `DIRECT_URL` is overridden (prod connection string is in 1Password → "Supabase DB Direct URL - The Oracle (CURRENT PROD …)").

---

## China bilingual claim layer — merged to main, migration applied; worker deployed (2026-06-20)

What it is: serve the knowledge graph to a China team in Mandarin while keeping one unified brain. Full design + resolved decisions are in `china_imp.md`; AGENTS.md §7–§10 document the code surfaces.

Exact current state:
- Code is **merged into `main`** (the `docs/china-bilingual-plan` branch was integrated with `origin/main` — which had since shipped the claim-review-groups feature — resolving 12 overlapping files; typecheck + `verify:retrieval-filter-parity`/`verify:auxiliary-defaults`/`verify:mcp`/`verify:vertex-file-cache` + web build + `db:check-drift` all green before push). Vercel auto-deploys web from `main`.
- DB migration **`0007_tricky_charles_xavier.sql`** is applied to the current prod DB (`eqccjfbyrywsqkxxpjvg`). Verified after the Virginia cutover: `claim_translations` table, `claims.source_lang`, `employees.locale`, and the Drizzle journal hash now match the on-disk migration. HNSW vector index on `claim_translations.embedding` intentionally skipped (build later with `ORACLE_RUN_VECTOR_INDEXES=1`). `0007` was hand-trimmed to only the new objects — see AGENTS.md §10 "The Drizzle snapshot was baselined at migration 0007".
- The **`claim-translation` Trigger.dev worker is deployed to prod** in worker version `20260620.1`.

What is done: schema + migration; `SUPPORTED_LOCALES` in `@oracle/shared`; locale-aware `searchWithRetrievalPlan`/`buildPlanMetadataFilters` (+ extended parity guard); `source_lang` stamping at promotion; `claim-translation` worker + `translation` auxiliary model (`default_translation_route`, "copy job brief" in settings); opt-in "Translate selected for China team" bulk action + ✓ persisted badges on `/admin/claims`. **Verify ("ask someone to confirm a claim") was folded into `main`'s existing claim-review-question + review-groups feature** (`assignClaimQuestion`): the separate `claim-recertification` worker and `claim_recertification` gap type were dropped; instead `assignClaimQuestionImpl` now translates the question per recipient so a `zh-CN` recipient is asked in Chinese.

Added 2026-06-18 (committed + pushed to `main`, deploys via Vercel):
- **Employee language is now editable in the UI** — `/admin/employees` has a "Language" column (English / 中文) writing `employees.locale` via `updateEmployeeLocale` (commit `8c7fb03`). This supersedes the old "set locale by SQL" step. `employees.locale` is the single switch the bilingual layer keys off.
- **Bulk "Ask selected to evaluate"** on `/admin/claims` — tick several `pending_review` claims, pick people/groups, route them all at once (commit `cc25775`). Extracted `assignClaimQuestionCore` so the per-row form and the bulk loop share one path (recipient resolution, dedup-against-existing-assignments, per-recipient zh-CN auto translation). Per-claim failures are non-fatal (reported as skipped).

Optional follow-up:
- Build admin side-by-side translation review if the China bilingual workflow needs human translation QA. The mechanical setup is done; employees can be set to `zh-CN` in the UI and `default_translation_route` is configured.

### "Sent to review" indicator on /admin/claims — DONE (2026-06-18)

Status: **committed + pushed to `main` (commit `e5179c0`)**; deploys via Vercel.

What shipped (single file, `apps/web/app/admin/claims/page.tsx`): a `review_assignees` subselect on the claims query and a 🔁 "Sent to review" badge + assignee-name chips in the Summary cell. Source of truth is open `claim_review_question` gaps (`gaps.related_claim_ids ? claim.id`, status in `open/queued/asked`) joined to `employees.name` — NOT a column on `claims`. Renders on every status tab, so a claim sent while pending still shows reviewers after it's approved.

Verified originally against the previous Ohio prod DB; the data was migrated to current prod (`eqccjfbyrywsqkxxpjvg`) during the 2026-06-20 Virginia cutover. The subquery returned real names (72 open review gaps, 7 distinct targets) — column names, the `?` jsonb-membership operator, and the gap statuses all match live data.

Decisions made (and why): Brain synthesis stays English-only; evidence quotes are never translated (verbatim provenance); translation is opt-in per claim (cost proportional to what's directed to China); the verify/"ask to confirm" path reuses main's review-question/review-groups mechanism (no duplicate system) with the question translated per-recipient so only China recipients get Chinese.
---

## 2026-06-16 extraction A/B + employee-access update

Status:
Done. Code was committed, pushed, DB changes were applied where needed, and production web/workers were deployed.

Done:
- Fixed `/admin/ai/extraction-ab` source alignment: A/B/C model reruns now anchor to reviewed evidence quotes and do not fall back to unrelated leading document-chunk text when the quote is missing from the chunk.
- Moved extraction A/B/C reruns out of the page server action. `/admin/ai/extraction-ab` now queues rows through `claim_extraction_ab_tests.run_status`; Trigger.dev task `extraction-ab-eval` runs Gemini/Qwen and writes outputs/errors back. Migration `72_claim_extraction_ab_run_status.sql` was applied to production through linked Supabase CLI because this checkout did not have `DIRECT_URL` / `DATABASE_URL` for `pnpm db:migrate`.
- Trigger.dev worker deploy `20260616.2` succeeded after removing the attempted cron sweep. Trigger.dev was at 10/10 schedule slots, so `extraction-ab-eval` uses immediate dispatch only.
- Added Admin -> Employees Disable/Re-enable controls. They write `employees.disabled_at`; disabled employees cannot log in/link, but historical employee references remain intact.
- Production Vercel deployments were completed through commit `39c58fd Add employee access controls` before this documentation pass.

Next action:
Use Admin -> Employees for roster cleanup. For A/B/C evals, click rerun rows and let the queued worker populate results; if rows remain queued indefinitely, verify Vercel production `TRIGGER_SECRET_KEY` is a prod Trigger key and inspect Trigger.dev task runs for `extraction-ab-eval`.

Risks / watchouts:
- Do not hard-delete employees unless a separate archival/reference cleanup is designed.
- Do not move Gemini/Qwen A/B/C calls back into the page server action; multiple simultaneous rows previously hung the UI.
- Do not add another Trigger.dev schedule until the schedule limit is increased or existing schedules are consolidated.

---

## Historical completed work / superseded notes

### 0b. 2026-06-17 dynamic model route dispatch fix

Status:
Done. Commit `fe22f19 Support dynamic model routes in router` was pushed to `main`, and Trigger.dev production worker version `20260617.1` deployed successfully with 19 detected tasks.

Done:
- Fixed `ModelRouter` so admin-selected provider/model route IDs such as `qwen/qwen3.7-plus` resolve dynamically at dispatch time instead of failing static catalog lookup with `No OracleModelRoute found`.
- Added a smoke assertion covering `qwen/qwen3.7-plus` for a `document_claim_extraction` plan.
- Verified: `corepack pnpm --filter @oracle/ai typecheck`, `corepack pnpm --filter @oracle/ai exec tsx src/__verify__/oracle-ai-client-smoke.ts`, and `corepack pnpm --filter @oracle/workers typecheck`.

Watchout:
- This was a live issue for worker `20260617.1`; current prod worker is `20260626.7`. Reprocess old failed documents only if they still show a failed status in the admin UI.

### 0a. 2026-06-15 local/pushed commits and review workflow

Status:
Superseded by later claim-review updates. The `training_enablement` top-domain work was committed locally as `018c2d3 Add training enablement knowledge domain`. Claim-review/revise work landed, and the review surface has since been narrowed to direct assignments plus admin-managed review groups.

Done:
- Added `training_enablement` domain, retrieval hints, boundary docs, and migration `packages/db/migrations/sql/67_training_enablement_domain.sql`.
- Implemented claim-review workflow: `/admin/claims` shows top-domain chips and supports approve/reject/revise/assign; approved-claim edits supersede the original and create a replacement in `pending_review`; `/claims` is now direct-assignment only for non-admin reviewers; `packages/db/migrations/sql/68_claim_review_workflow.sql` adds `claim_review_events` and `knowledge_domain_review_departments`.
- Added claim review groups (`/admin/claim-groups`, migration `73_claim_review_groups.sql`) so a claim-review question can be sent to multiple people or reusable groups. Group sends materialize as one `claim_review_question` gap per active employee.
- Verified locally on 2026-06-15: `corepack pnpm --filter @oracle/ai verify:retrieval-plan-domain-boundaries`, `corepack pnpm --filter @oracle/web typecheck`, `corepack pnpm --filter @oracle/db typecheck`. Browser smoke reached `/claims`, compiled the route, and redirected to login; authenticated UI was not exercised because the in-app browser had no session.

Next action:
None for this historical block. Later Vercel deployments superseded this note.

Risks / watchouts:
- The claim-review feature depends on the tables from `68_claim_review_workflow.sql`; group assignment depends on `73_claim_review_groups.sql`.
- The seeded domain-review map is retained but not currently exposed through `/claims`. Non-admin review is direct-assignment only until domain queues are intentionally restored.
- Revision intentionally supersedes the original AI claim and creates a replacement claim; do not change it into in-place edits unless the audit/provenance model is redesigned.

### 0. Repo/deploy alignment note

The older 2026-06-10/11 working-tree warning has been superseded. Verified 2026-06-29: Trigger.dev prod current worker is `20260629.1`. Re-check `git status --short --branch` and Trigger.dev `get_current_worker` before future work.

### 1. Demonstrate synthesis

Done. Earlier sessions could not meaningfully exercise synthesis because the approved corpus was too small or `brain_sections` were missing. That blocker is gone. On 2026-06-29, `domain-licensing` synthesized over 124 approved claims and promoted current version `f3de1eff-52f5-4001-9cf5-a1521d7c082f` as `needs_review`.

Evidence:

1. Run `run_cmqymg81k43rc0hke6yxu61gi` completed on worker `20260629.1`.
2. `brain_sections.current_version_id` for `domain-licensing` now points to `f3de1eff-52f5-4001-9cf5-a1521d7c082f`.
3. The version links 62 section claims and should be reviewed in admin before treating it as polished narrative.

### 2. Seed entity registry + active knowledge domains

Done. Prod has seeded entities and active top-domains. The review/safety model still deliberately holds unresolved entities, invalid domains, and high-impact claims, so get owner sign-off before loosening gates.


### 3. Retrieval-backed context for live Oracle — DONE (2026-06-10)

Implemented and verified in production worker `20260610.4`; expanded locally on 2026-06-11:

- `teams-live-recall-utterance` now runs the one endorsed retrieval path (`buildRetrievalPlanFromQuery` → `searchWithRetrievalPlan`, topK 5) over each utterance that passes the heuristic + cooldown/rate gates, and injects the approved claims as a `retrieved_context` prompt block (prompt version `teams-live-recall-1.1.0`).
- The 2026-06-11 local update enriches retrieved claims with quote evidence and linked Brain snippets, includes recent meeting context in the retrieval query, and records the context pack/model-run/usage linkage for the live decision.
- The decision schema gained `evidenceClaimIds`; the worker validates them against the retrieved set and stores `retrievedClaimIds` + `evidenceClaimIds` in the job output and (when a question posts) in the interjection assistant-message `metadata_json`.
- Retrieval failures degrade to the no-context prompt (with the Postgres `cause` surfaced in the warn log); they never block utterance persistence.
- The live bot still only asks clarification questions; claim IDs never appear in Teams chat text.

Verification runs (Trigger prod, synthetic `transcript.data` payloads, bot id `verify-retrieval-20260610`, channel `b3a65666-ff4c-4e0d-8ce8-11a970808f50`):

- Contradicting utterance ("keep routing all Hobby Lobby holiday decor shipping through the Newark warehouse...") → run `run_cmq8erj3y7uh70uog5qd45swt`: `retrievedClaimIds=[bdbc9918-…]`, `evidenceClaimIds=[bdbc9918-…]`, decision reason explicitly cites the approved Atlanta-DC rule, `postedQuestion=null` (clamp respected).
- Small talk ("Good morning everyone...") → run `run_cmq8es7a87qdp0hogi33nukgc`: `heuristic_skip`, no model call, no retrieval.
- `contradiction-watcher` for the approved claim → run `run_cmq8es88r7swt0hok4li3fh3p`: completes (0 contradictions) — it had been failing on the same retrieval SQL.
- All synthetic test messages in channel `b3a65666-…` were set `extraction_status='skipped'` so the extraction pipeline never treats them as real knowledge.
- The posting/metadata path (actual Recall `send_chat_message` + assistant-message evidence metadata) still needs one real live-meeting test with the user present; everything up to the post is proven.

Three runtime SQL bugs were fixed in `searchWithRetrievalPlan` / `buildPlanMetadataFilters` (`packages/ai/src/retrieval.ts`) — the hybrid query had NEVER successfully executed with domain hints before, because there were no approved+embedded claims to exercise it:

1. Bare JS arrays in drizzle ``sql`` templates expand to `($1, $2)`, so `ANY((...)::text[])` was a syntax error → list filters now bind ONE JSON-string param unpacked via `jsonb_array_elements_text` / `jsonb_to_recordset` (see new AGENTS.md §10 quirk).
2. `::vector(${EMBEDDING_DIM})` parameterized a type modifier (`vector($4)`) → now inlined with `sql.raw`.
3. `cm.id` does not exist — `claim_metadata`'s PK is `claim_id` → `timeFilter` now uses `cm.claim_id`.

The static parity guard passes unchanged (it checks filter parity between branches, not SQL validity — none of these were catchable statically).

### Fresh-developer restart packet (updated 2026-06-29)

Use this subsection as the first stop for a brand-new developer. The rest of this file preserves the detailed history and evidence, but this is the current operating snapshot.

Current git/deploy snapshot:
- Verify `git status --short --branch` before editing. On 2026-06-29, local `main` was clean against `origin/main` before this docs cleanup.
- Trigger.dev production worker is **`20260629.1`** with 21 tasks.
- Current extraction config: `default_vision_route=qwen/qwen3-vl-235b-a22b-thinking`, `default_extraction_route=google/gemini-2.5-flash`, extraction pool `[google/gemini-2.5-flash, vertex_gemini_2_5_flash_extraction_primary, openai/gpt-4.1-mini]`.
- The silent-fallback and hard-coded route work is complete. Debug wrong-model questions through `model_run_attempts`, provider availability, and Admin attempt alerts.
- `business-process.md` and later document-ingestion history produced real `pending_review`/approved claims. Chat and synthesis still only use approved claims.

What The Oracle can do now:
- Post-call Teams transcript ingestion through Microsoft Graph is live and validated for ad-hoc Teams calls when the Graph subscription exists before transcription starts.
- Recall.ai live Teams participation is live and validated: Recall joins the Teams meeting, streams finalized utterances to Oracle, Oracle stores them as `messages`, and Oracle can post short clarification questions back into Teams chat through Recall.
- The Teams-native app/bot wrapper is wired: users can interact with the Teams org app `The Oracle`, whose Azure Bot endpoint is `https://oracle.designflow.app/api/teams/bot/messages`.
- Native Microsoft Teams app/bot commands do not replace Recall for live audio/STT. The Teams Bot Framework wrapper is the command surface; Recall is still the live meeting media/STT transport.

What is intentionally disabled right now:
- Live Oracle interjections are clamped off in `settings`.
- Keep them clamped off unless you are running an intentional live test with the user present.
- Expected clamp values:
  - `max_oracle_interjections_per_hour = 0`
  - `teams_live_recall_min_confidence_to_post = 101`
  - `teams_live_recall_force_model_pass = false`
  - `teams_live_recall_force_post = false`
  - `teams_live_recall_disable_posting_limits = false`
- 2026-06-10 settings timeline: `teams_live_recall_disable_posting_limits` was temporarily set `true` at ~18:27 UTC for the synthetic retrieval verification and clamped back `false` at 18:35:44 UTC. Separately, `max_oracle_interjections_per_hour` was found at `3` (changed 2026-06-10 00:01:38 UTC by an unknown actor — NOT this session) and was re-clamped to `0` at 18:36:11 UTC per the guardrail above. If Albert set it to 3 intentionally, restore it deliberately.

Most important next work:
1. Review the new Licensing Brain draft in admin and approve/edit it if it reads well enough for demo use.
2. Populate meeting picker subject/participant metadata if the admin transcript picker needs friendlier rows.
3. Optionally build China side-by-side translation review.
4. One real live-meeting test (user present) of the retrieval-backed interjection posting path, confirming `evidenceClaimIds` lands in assistant-message `metadata_json`, if live interjections are intentionally reopened.

Known-good live test utterance:
- Spoken: `Oracle, should artwork always go to China after licensor approval, or is Walmart an exception?`
- Expected posted question shape: `Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart an exception?`
- This path was validated through Recall chat delivery on 2026-06-09.

Operational guardrails:
- Do not rotate the shared Entra app secret without `--append`. The shared app id is `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`, and it is used by Supabase Microsoft SSO, Graph backend access, and Teams Bot Framework auth.
- Supabase Microsoft provider URL must be `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971`; do not add `/v2.0`.
- Do not paste or commit secret values. During prior debugging, secret-looking values appeared in tool output; future rotations should include any exposed Google service-account JSON, Recall webhook secret, Vercel token, and Trigger keys if policy requires cleanup.
- `supabase.exe db query --linked` may hang or hit auth circuit breakers. Stop `supabase*` processes and retry gently; do not hammer linked CLI auth.
- Vercel env writes may require CLI/API/dashboard access; the Vercel MCP is read-only in this environment.
- Trigger.dev CLI is authenticated on this Windows machine; Trigger production env is project `proj_wgpzsvhmsopqhvwqaycn`.

Before declaring future work done:
- Confirm `git status --short --branch` is clean or document any intentional uncommitted changes.
- If worker behavior changed, deploy to Trigger.dev production and record the worker version here.
- If Vercel route/env behavior changed, redeploy production and record the deployment.
- If live posting is opened for a test, clamp it off again and record the timestamp.
- If claims/synthesis state changes, record the exact DB/admin evidence.

---

## What is done (since the prior HANDOFF)

### Document ingestion: Word + image (vision), admin uploader, context/hints, auxiliary models (2026-06-14)

Committed (`d8dd2d6`, `195f9fc`, `bdb07c3`, `a2f9851`, `105addf`, `c388593`) and **deployed**: Trigger prod worker **`20260614.3`** (17 tasks) + Vercel production (auto-deploys on push to `main`). All `@oracle/*` typecheck, web ESLint, and `verify:vertex-inline-image` / `verify:vertex-file-cache` pass.

**New input formats**
- **Word (.docx)** parsed via `mammoth` (added to `apps/workers/package.json`). Old binary `.doc` still unsupported (convert to `.docx`/PDF). `resolveParseKind()` now falls back to the filename extension when the browser sends `application/octet-stream`.
- **Images (vision)** — PNG/JPEG/WebP/HEIC. Two-pass: Pass 1 = a vision model transcribes the image to faithful text; Pass 2 = that text flows through the SAME chunk → extract → quote-validate → promote pipeline. The transcription is persisted as `document_chunks`, so the quote-validation provenance guarantee holds (claims quote the transcription, never the raw image). GIF/BMP/TIFF → unsupported.
- Pass 1 prompt (`IMAGE_TRANSCRIPTION_SYSTEM`) instructs a **structured text-topology** output for diagrams/flowcharts/org charts — nodes `[Shape/Color: "label"]`, edges `[A] --(condition)--> [B]`, swimlane `### headers` — with verbatim labels kept inside the nodes so they stay exactly quotable.

**Vision is GUI-choosable, provider-agnostic**
- The Vertex adapter `buildContents`/`toVertexParts` now translate an inline `{type:'image',mimeType,data}` part into a Gemini `inlineData` part (guard: `verify:vertex-inline-image`). The worker formats the image part per provider (Gemini inlineData / Anthropic image block / OpenAI image_url) so whatever model the admin picks works. The file-backed Vertex cache path is skipped for images (a lone image is below the cache token minimum).
- **Auxiliary-model registry** (`packages/ai/src/routes/auxiliary.ts`, `AUXILIARY_MODELS`): vision + general-purpose are "auxiliary models" — single-pick selections that are NOT one of the 3 strict `OracleModelRole`s (which stay frozen). The picker, `/api/admin/models`, and `resolveAuxiliaryRouteFromSettings(db, id)` all iterate the registry. Adding the next one (e.g. audio transcription) = one registry entry + one `AUX_PRESENTATION` entry in the settings page.
- Settings: **`default_vision_route`** (+ `default_vision_reasoning_effort`). Shipped fallback `vertex_gemini_2_5_flash_extraction_primary` (Gemini — already credentialed in prod). **Seeded in prod** with `ON CONFLICT (key) DO NOTHING` (won't clobber an admin choice). Admin → Settings → "Image vision model" has a "Copy job brief" button.

**Inference vs catalog APIs** — the model dropdown reads the cached `model_capabilities` table (`GET /api/admin/models?stage=vision`), populated by `refreshModelCatalog` from direct provider list APIs + OpenRouter enrichment. Inference is always **provider-direct** (Gemini via `@google/genai`), never OpenRouter.

**Admin company-document uploader (no channel)**
- Channels can only be created by the Teams flows or the admin raw-import path — there is no "create channel" UI. So uploading company docs via a chat channel was unreachable. New: **Admin → Documents** has a multi-file drag-drop uploader → `POST /api/admin/documents` (admin-only) stores each file, inserts a `documents` row, triggers `document-ingestion`. No channel needed (the worker reads documents by id; `documents` has no channel dependency — the channel was only ever for the chat attachment message).

**Per-document context + domain hints**
- Hand-written idempotent migration `packages/db/migrations/sql/65_document_context_and_domain_hints.sql` adds nullable `documents.context` (text) and `documents.domain_hints` (jsonb), applied to prod **and** added to `schema.ts`. ⚠️ No Drizzle-generated migration accompanies the schema.ts change — the columns exist via the hand-written SQL only, so `pnpm db:check-drift` may flag them and a fresh-DB `pnpm db:migrate` will not recreate them unless the hand-written `sql/65` file is applied. Follow-up: fold into a generated migration if drift is undesirable.
- The admin uploader has a "What is this?" textarea + active-domain chips (batch-level, applied to every file in the upload). `document-ingestion` feeds `context` into BOTH the extraction prompt and the image vision prompt, and renders `domain_hints` as a non-binding prior — per-claim `domain_valid` stays authoritative.

**Not yet done / caveats**
- Vision/topology only affects images processed from now on; re-upload older images to reprocess.
- Live end-to-end image test (real upload → `complete` → claims) still pending a human upload.
- Cross-provider vision is wired but only the Vertex/Gemini path has a regression guard.
- `business-process.md` uploaded on 2026-06-15 originally failed because Trigger's Node 21 runtime needed an explicit Supabase WebSocket transport. That crash is fixed in worker `20260614.5+`, and the document row `ee1fa682-9e5c-4cf5-89c5-b2f95d047eea` was retried successfully to `status='complete'` with `processing_error=NULL`. However, the extraction attempts promoted 0 claims: the latest checked run (`run_cmqefjl0h1jif0olkl3kkpjk9`, batch `01469d78-0400-4a1e-a2fd-4f235980a94b`) staged 45 candidates, rejected 42 for strict quote mismatch and 3 for unresolved taxonomy entities. Worker `20260614.9` improves future uploads with paragraph-aware 4000-char chunks, but the existing row still has old 1500-char chunks. Re-upload the file or do a deliberate admin reprocess that recreates chunks if you want the new chunking applied to this document.

### Documentation maintenance audit from pasted task spec (2026-06-09)

Completed the broad Markdown audit requested from:

`C:\Users\ahazan2\.codex\attachments\0ddbc067-291d-421c-9a87-eaad3e2691a4\pasted-text.txt`

What was verified/updated:
- `AGENTS.md` remains canonical and now explicitly routes historical/spec docs without encouraging bulk-loading every Markdown file.
- `README.md` points new sessions to `HANDOFF.md` when present.
- `CLAUDE.md` was checked and left Claude-specific.
- Topic docs were aligned with the current live state: Graph post-call transcript ingestion is live, Recall live Teams participation is live, and Recall live posting is currently clamped off by runtime settings.
- `docs/configuration.md` now documents the live Recall safety/test settings.
- `docs/deployment.md` now has upsert-based SQL snippets to reopen and re-clamp live Recall tests.
- `.claudeignore`, `.cursorignore`, and `.copilotignore` were checked and already matched the project ignore policy.
- No secret values were added to docs.

### Teams transcript ingestion — LIVE and validated (2026-06-04/05)

- Real Meet-Now call → subscription → webhook → ingestion → **95 messages**, `speakersResolved 2/2`
- Speaker resolution by email (`fbb82cd`) + bootstrap-by-email for `@popcre.com` (`e73868b`)
- 38 employees seeded (all enabled `@popcre.com` humans)
- Two latent extraction bugs fixed: `segmentSummary` cap overflow (`71fa76f`) + broken `::uuid` cast in `stageEntityProposal` (`c159732`)
- Fuzzy quote matching for spoken transcripts (`89d2fd9`, D-transcript-fuzzy-quote)
- Raw VTT persistence (`89d2fd9`, D-raw-transcripts, hand-written `62_raw_transcripts.sql`)
- Workers deployed: Trigger.dev version **20260605.1**

### Recall.ai live Teams path — wired and deployed (2026-06-06)

The code (`bfd6612`) was committed by a prior session but was untested. This session wired it live:

- **Region bug fixed** (`4219c66`): default `RECALL_BASE_URL` was `us-west-2` but POP Creations workspace is US East. Fixed in `apps/web/lib/recall.ts`, `apps/workers/src/lib/recall.ts`, `.env.example`.
- **Vercel env vars set** (manually by user after CLI scripting issues): `RECALL_API_KEY`, `RECALL_WEBHOOK_SECRET`, `RECALL_BASE_URL=https://us-east-1.recall.ai`, `RECALL_REALTIME_WEBHOOK_URL=https://oracle.designflow.app/api/teams/live/recall`.
- **Trigger.dev env vars set** (via REST API): `RECALL_API_KEY`, `RECALL_BASE_URL`.
- **Workers deployed**: version **20260606.1** (17 tasks including `teams-live-recall-utterance`).
- **Vercel build**: `4219c66` deployed to production (READY), both verify guards passed.
- **Webhook confirmed live**: `POST /api/teams/live/recall` with no signature returns `{"error":"invalid_signature"}` — proving the route is live and `RECALL_WEBHOOK_SECRET` is loaded (if secret were missing the error would be "Recall verification secret is missing or invalid").

### Design File Operations taxonomy domain applied (2026-06-08)

Commit `616cf95` added the `design_file_operations` top-level domain, retrieval-boundary guard, seed updates, entity hints, and hand-written migration `packages/db/migrations/sql/63_design_file_operations_domain.sql`.

The local shell still could not run the normal Drizzle runner because `DIRECT_URL` / `DATABASE_URL` were unavailable. At the time, the repo was linked to the previous Ohio Supabase project and the hand-written SQL was applied through:

```
supabase.exe db query --linked --file packages\db\migrations\sql\63_design_file_operations_domain.sql --output table
```

Verification completed for:

- `entities.domain_hints`: `Google Drive`, `Illustrator`, `InDesign`, `Photoshop`, and `SharePoint` now include `design_file_operations`.
- `claim_top_domains`: backfill count for `design_file_operations` was `0` at verification time.

Follow-up verification queries against `knowledge_top_domains` started timing out after Supabase temporarily blocked linked CLI login attempts with `ECIRCUITBREAKER too many authentication failures`. Do not retry rapidly; let the pooler cool down before further linked CLI queries.

### Key lesson — TRIGGER_SECRET_KEY must be the prod key in Vercel

Vercel's `TRIGGER_SECRET_KEY` was initially a **dev** environment key. The webhook triggered `teams-transcript-ingestion` into the dev environment where no worker ran; the run expired (TTL 10m). Set Vercel Production `TRIGGER_SECRET_KEY` to the `tr_prod_…` key. See AGENTS.md §13 incident 2026-06-04.

---

## Recall.ai integration — how the pieces fit

| Component | File | Purpose |
|---|---|---|
| Bot creation | `apps/web/app/api/teams/live/start/route.ts` | Admin POST to join a meeting. Calls `createRecallLiveBot()` with `realtime_endpoints` pointing to the webhook URL. |
| Webhook receiver | `apps/web/app/api/teams/live/recall/route.ts` | Verifies `RECALL_WEBHOOK_SECRET` signature, triggers `teams-live-recall-utterance` worker. |
| Web helper | `apps/web/lib/recall.ts` | `createRecallLiveBot()` + `verifyRecallRequest()` |
| Worker helper | `apps/workers/src/lib/recall.ts` | `sendRecallChatMessage()` — posts Oracle question to meeting chat |
| Worker task | `apps/workers/src/trigger/teams-live-recall-utterance.ts` | Normalizes words → text, finds/creates channel, resolves speaker, inserts `messages` row, applies keyword gate + cooldown + rate cap, calls LLM, if confidence ≥ 70 sends chat message + inserts `oracle_interventions` row. |
| Teams-native bot | `apps/web/app/api/teams/bot/messages/route.ts`, `apps/web/teams-app/oracle/manifest.template.json` | Lets users type `@The Oracle join <link>` from inside Teams. Azure Bot + Teams channel + org app are wired; see current state below. |

**Important**: real-time webhook endpoints are per-bot, specified in `recording_config.realtime_endpoints` on Create Bot — NOT configurable in the Recall dashboard. The dashboard webhook section is for post-call lifecycle events only.

### Teams-native app/bot wrapper — wired (2026-06-09)

The Teams-native command wrapper is now wired on the platform side:

- Azure subscription `37077c95-ea53-4a19-8380-f3f48f0cc75d` (`paygo for teams Oracle bot`)
- Resource group `rg-oracle-teams-bot`
- Azure Bot resource `theoracle-popcre-teams-bot`, SKU `F0`, single-tenant app id `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc`
- Messaging endpoint `https://oracle.designflow.app/api/teams/bot/messages`
- Microsoft Teams channel enabled
- Teams organization app `The Oracle`: app id `17ccd7a1-b90b-428c-9966-33e7fb832923`, external id `850b2963-3583-4af9-bf18-84985ecbcf03`
- App availability is everyone; installed for Albert (`Albert@popcre.com`) on 2026-06-09

If the app does not appear in Teams immediately, check propagation and verify with:

```powershell
Get-M365TeamsApp -Id 17ccd7a1-b90b-428c-9966-33e7fb832923
```

Expected state: `IsBlocked=false`, `AvailableTo.AssignmentType=Everyone`, and Albert listed under `InstalledFor.InstallForUsers`.

### 2026-06-09 credential repair note

During Teams bot setup, an Entra secret rotation without `--append` temporarily broke Supabase Microsoft sign-in and invalidated the Graph backend secret. Recovery completed:

- Supabase Azure provider client secret was refreshed manually in the Supabase dashboard.
- Supabase Azure provider URL was corrected to `https://login.microsoftonline.com/1caeb1c0-a087-4cb9-b046-a5e22404f971` — do **not** include `/v2.0`.
- Vercel `AZURE_GRAPH_CLIENT_SECRET`, `MICROSOFT_BOT_APP_ID`, `MICROSOFT_BOT_APP_PASSWORD`, and `MICROSOFT_BOT_TENANT_ID` were refreshed and production redeployed.
- Trigger.dev prod `AZURE_GRAPH_CLIENT_SECRET` was refreshed via `POST https://api.trigger.dev/api/v1/projects/proj_wgpzsvhmsopqhvwqaycn/envvars/prod/import` using the authenticated Trigger CLI token.

Future Entra client secrets on shared app `ed0b64b2-2cb1-44b1-817e-ef1cb1da5bcc` must be created with `az ad app credential reset --append --display-name <purpose> ...` unless intentionally replacing every consumer.

### Current live Recall operational state

Production settings after the final 2026-06-09 test are intentionally clamped:

| Setting | Value | Why |
|---|---:|---|
| `max_oracle_interjections_per_hour` | `0` | Disables live interjections by rate cap. |
| `teams_live_recall_min_confidence_to_post` | `101` | Disables confidence-gated posting because model confidence max is 100. |
| `teams_live_recall_force_model_pass` | `false` | Restores keyword pre-gate. |
| `teams_live_recall_force_post` | `false` | Prevents blunt test echo mode. |
| `teams_live_recall_disable_posting_limits` | `false` | Restores cooldown/hourly limit enforcement. |

To test live interjections again, intentionally reopen the gates and clamp them back off afterwards:

```sql
INSERT INTO settings (key, value, description, updated_at)
VALUES
  ('max_oracle_interjections_per_hour', '3'::jsonb, 'Hard cap per channel per hour.', now()),
  ('teams_live_recall_min_confidence_to_post', '70'::jsonb, 'Minimum live Recall model confidence required before posting.', now()),
  ('teams_live_recall_force_model_pass', 'false'::jsonb, 'Test-only: force all live Recall utterances through the model gate.', now()),
  ('teams_live_recall_force_post', 'false'::jsonb, 'Test-only: force-post Oracle test utterances.', now()),
  ('teams_live_recall_disable_posting_limits', 'false'::jsonb, 'Test-only: bypass live Recall posting cooldown and rate caps.', now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = COALESCE(settings.description, EXCLUDED.description),
    updated_at = now();
```

To clamp off:

```sql
INSERT INTO settings (key, value, description, updated_at)
VALUES
  ('max_oracle_interjections_per_hour', '0'::jsonb, 'Hard cap per channel per hour.', now()),
  ('teams_live_recall_min_confidence_to_post', '101'::jsonb, 'Minimum live Recall model confidence required before posting.', now()),
  ('teams_live_recall_force_model_pass', 'false'::jsonb, 'Test-only: force all live Recall utterances through the model gate.', now()),
  ('teams_live_recall_force_post', 'false'::jsonb, 'Test-only: force-post Oracle test utterances.', now()),
  ('teams_live_recall_disable_posting_limits', 'false'::jsonb, 'Test-only: bypass live Recall posting cooldown and rate caps.', now())
ON CONFLICT (key) DO UPDATE
SET value = EXCLUDED.value,
    description = COALESCE(settings.description, EXCLUDED.description),
    updated_at = now();
```

Supabase CLI note:
- `supabase.exe db query --linked` intermittently hung during this session. If it sticks, kill `supabase*` processes and retry once:

```powershell
Get-Process | Where-Object { $_.ProcessName -like 'supabase*' } |
  Stop-Process -Force -ErrorAction SilentlyContinue
```

Do not hammer retries if the linked pooler returns authentication/circuit-breaker errors.

### Recall.ai live Teams path — end-to-end tested (2026-06-08)

Real Teams meeting test succeeded:

- Admin UI `/admin/settings` start path worked.
- ElevenLabs start failed because the Recall workspace has no ElevenLabs credentials configured.
- AssemblyAI fallback succeeded; bot `68cf8eca-459d-409e-b87d-67879615b61b` joined the Teams meeting and reached `in_call_recording`.
- Recall recording `0e591d96-e63d-4f8a-84f3-5d7f4e08f277` and transcript artifact `8256d8db-97d1-4f20-b9fd-132fe621deff` were created with `assembly_ai_v3_streaming`.
- Oracle realtime endpoint `https://oracle.designflow.app/api/teams/live/recall` was configured on the bot.
- Trigger jobs `teams-live-recall-utterance` completed successfully.
- `messages` rows were inserted with `metadata_json.source='teams_live_recall'` in channel `Teams live meeting 68cf8eca-459d-409e-b87d-67879615b61b`.

No Oracle question was posted during this test because the captured utterances were skipped by the cheap heuristic gate (`decisionReason='heuristic_skip'`), which is expected for small talk / non-operational speech.

### Temporary live Recall interjection test mode — tested, clamped OFF (2026-06-08)

Worker version **20260608.2** added temporary DB-controlled test knobs for the `teams-live-recall-utterance` task. Worker version **20260608.3** made the `force_post` override safer: it now only force-posts utterances that start with `Oracle test:`.

- `teams_live_recall_force_model_pass=true` — every non-empty live utterance is sent to the interjection decision model instead of using the cheap keyword/length pre-gate.
- `teams_live_recall_force_post=true` — posts a test question even when the model returns `shouldAsk=false`; if the model gives no question, it strips an `Oracle test:` prefix and posts the remaining utterance as the question.
- `teams_live_recall_disable_posting_limits=true` — bypasses cooldown + hourly cap for live Recall interjection tests.
- `teams_live_recall_min_confidence_to_post=0` — lowers the confidence threshold for posting when the model decides `shouldAsk=true`.

This confirms whether live utterances reach the model and whether the chat-send path can be exercised. Turn this off after testing:

Result: force-post testing succeeded with ElevenLabs bot `b2c114eb-2713-44ef-8196-f776b99d0d63`. Oracle posted the test clarification back through Recall into Teams, including:

- `Should artwork always go to China after license or approval, or is Walmart seasonal an exception?`

During the first force-post test, Oracle also echoed a few follow-up utterances because `force_post=true` was intentionally blunt in version `20260608.2`. The production settings were then hard-clamped at `2026-06-08 20:33:28`:

- `max_oracle_interjections_per_hour=0`
- `teams_live_recall_min_confidence_to_post=101`
- `teams_live_recall_force_model_pass=false`
- `teams_live_recall_force_post=false`
- `teams_live_recall_disable_posting_limits=false`

Verified after the clamp: no `teams_live_recall_interjection` assistant messages were inserted after `2026-06-08 20:33:28`.

Follow-up live test on 2026-06-09:

- Fresh Teams meeting bot `4e63dc18-a63d-4cdc-a7c7-b0e967027b20` joined and recorded successfully with ElevenLabs streaming.
- Recall recording `4c0a8a18-072f-40bc-8ae9-5cfe81f0b245` and transcript artifact `050437ce-6559-4b4f-984d-ca9e2b1b2a8b` reached `done`.
- Oracle received and stored live utterances in channel `0390c592-96af-450f-aaf9-63cecae61c92`.
- Worker versions deployed during testing:
  - `20260609.1` broadened the model prompt so business-process questions asked aloud can be captured in Teams chat.
  - `20260609.2` added deterministic fallback posting for direct business-process questions when the model recognizes the need but omits a structured `question`.
  - `20260609.3` treats leading direct address (`Oracle, ...`, `Hey Oracle, ...`) as invocation, not as meta/tool chatter, before deciding whether the remaining content is a business-process question.
- Later same-link retest bot `69b0bc21-e3a0-424c-aaa0-d75c83c40567` joined and recorded successfully with ElevenLabs streaming.
- Worker version `20260609.4` changed the deterministic direct-question fallback so Oracle no longer posts an exact echo. It frames the chat message as `Can we clarify this process question: ...`.
- The `20260609.4` path fired for: `Oracle, should artwork always go to China after licensor approval, or is Walmart a seasonal exception?`
- Oracle worker job completed with no error and `postedQuestion='Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart a seasonal exception?'`.
- Recall workspace logs independently confirmed `POST /api/v1/bot/69b0bc21-e3a0-424c-aaa0-d75c83c40567/send_chat_message/ -> 200` at `2026-06-09T17:04:09.580Z` with `to='everyone'` and the same framed message.
- Follow-up direct-send probe confirmed Recall chat delivery was visible in Teams: `direct chat probe 2026-06-09 1:13pm?`.
- After the first same-link bot stopped producing live utterance jobs, the user kicked it out and a fresh bot `5f529c48-f1de-48c2-a72b-b599b53be9c4` was created for the same meeting. It reached `in_call_recording`, recording `50a40fb6-b839-44c6-8c4a-e25126f4bf19`, transcript `afda8f7d-71ab-4579-ad97-5b024fe48f68`.
- Fresh-bot hearing test succeeded: Oracle received `Oracle hearing test, 1:28 p.m..` and skipped it correctly as a technical test.
- Final business-question test succeeded: Oracle received `Oracle, should artwork always go to China after licensor approval, or is Walmart an exception?` and posted `Can we clarify this process question: should artwork always go to China after licensor approval, or is Walmart an exception?` to Teams chat.
- During the same-link rejoin, temporary worker version `20260609.5` briefly added a `recall-live-bot-create` task so Codex could create the fresh Recall bot through Trigger's production env. The file was deleted and workers were redeployed as `20260609.6` with the normal 17 detected tasks.
- Safety state after testing: temporary settings were clamped off at `2026-06-09 17:34:23` (`max_oracle_interjections_per_hour=0`, `teams_live_recall_min_confidence_to_post=101`, all force flags `false`).

To restore normal gated live interjections later, use:

```sql
UPDATE settings
SET value = '3'::jsonb, updated_at = now()
WHERE key = 'max_oracle_interjections_per_hour';

UPDATE settings
SET value = '70'::jsonb, updated_at = now()
WHERE key = 'teams_live_recall_min_confidence_to_post';
```

To keep live interjections disabled, leave those clamp values as-is. To make sure temporary force settings are off:

```sql
UPDATE settings
SET value = 'false'::jsonb, updated_at = now()
WHERE key IN (
  'teams_live_recall_force_model_pass',
  'teams_live_recall_force_post',
  'teams_live_recall_disable_posting_limits'
);

UPDATE settings
SET value = '70'::jsonb, updated_at = now()
WHERE key = 'teams_live_recall_min_confidence_to_post';
```

---

## Tooling and identifiers

- **Supabase project ref**: `eqccjfbyrywsqkxxpjvg` (`theoracle`, N. Virginia). Previous Ohio project `vokucjpanhvqunimlvsp` is now `oracle.old`. Use the linked Supabase CLI or `POST https://api.supabase.com/v1/projects/eqccjfbyrywsqkxxpjvg/database/query` with the `sbp_...` token from Windows Credential Manager (`Supabase CLI:supabase`).
  - **Direct vs pooler from a local script (2026-06-25):** the prod **direct** host `db.eqccjfbyrywsqkxxpjvg.supabase.co` now resolves to an **IPv6-only** address — a v4-only Windows box gets `ENOENT`/`getaddrinfo` and cannot connect. Use the **session pooler** instead: `postgresql://postgres.eqccjfbyrywsqkxxpjvg:<db-pw>@aws-1-us-east-1.pooler.supabase.com:5432/postgres`. Username MUST be `postgres.<ref>` (plain `postgres` → `tenant not found`), pool host prefix is `aws-1` not `aws-0` (Ohio was `aws-1-us-east-2`), and the host is region-wide (the username ref does the routing). The ready-made string is in 1Password item *"Supabase DB Direct URL - The Oracle (CURRENT PROD …)"* → field **`oracle_session_pooler`**.
- **Trigger.dev project**: `proj_wgpzsvhmsopqhvwqaycn`, prod environment. Trigger MCP (`mcp__trigger__*`) is connected.
- **Recall.ai workspace**: `f2f8cedc-6d28-4fd2-8d06-402b74d65bcc` (POP Creations), US East. Recall MCP (`mcp__recall-ai__*`) is read-only.
- **Vercel project**: `prj_rP6Jlima7iK1paffEPhLqxlswGsC`. Vercel MCP (`mcp__vercel__*`) is read-only — env-var writes go via REST API or the Vercel dashboard.
- **Trigger.dev env var REST endpoint**: `GET/POST https://api.trigger.dev/api/v1/projects/{ref}/envvars/{env}` with PAT from `claude_desktop_config.json`.

---

## Cert material (do not commit)

`oracle-teams-cert/` is gitignored. It contains `private.pem` (in Vercel as `TEAMS_NOTIFICATION_PRIVATE_KEY`), `cert.b64.txt` (Trigger.dev as `TEAMS_NOTIFICATION_PUBLIC_CERT`), `clientState.txt`, `certId.txt`. Losing `private.pem` requires regenerating the cert and re-setting both Vercel + Trigger.dev + recreating the subscription.

---

## Risks and unknowns

- **Beta resource reliability** — `communications/adhocCalls/getAllTranscripts` is preview/flighted.
- **Subscription lapse = lost calls** — the `teams-subscription-renew` cron (`*/30`) must stay healthy; monitor `job_runs` for `teams-subscription-*`.
- **Fuzzy quote matching** relaxes the verbatim-provenance guarantee for transcripts. See DECISIONS.md D-transcript-fuzzy-quote.
- **`TEAMS_WEBHOOK_CLIENT_STATE`** must match in Vercel + Trigger.dev; the private key must pair with the worker's public cert.
