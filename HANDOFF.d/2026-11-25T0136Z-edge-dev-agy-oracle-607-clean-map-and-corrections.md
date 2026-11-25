---
summary: "Handoff after Phase 1 intake filter, retroactive re-filtering, clean Company Map rebuild (gv=58), and restricted employee corrections page (/map/corrections); intake remains paused awaiting owner map sign-off."
kind: handoff
status: OPEN
read-when: continuing Oracle #607/#664 after owner reviews the rebuilt Company Map (gv=58) or when unpausing intake / triaging /map/corrections submissions
issue: 607
owner: agy/oracle-607-clean-map-and-corrections
---

# Handoff — Clean Company Map (`gv=58`) & Restricted Employee Corrections Page (`/map/corrections`)

## 0. ⚠️ BUSINESS DECISIONS ONLY THE OWNER CAN MAKE

Ask Albert **all** business-meaning questions below together in **one** message before touching paused flags (do NOT ask for technical approvals):

1. **Blocking Step 1 (unpausing live message intake — `#607`):** Have you finished inspecting the rebuilt Company Map at [https://oracle.designflow.app/map](https://oracle.designflow.app/map), and should we turn automatic email/Teams/ClickUp intake (`BRAIN_INTAKE_ENABLED`) back on now?
   - **Recommendation:** **Yes**, once you confirm the cleaned Company Map looks right (noise removed, workflows intact), flip `BRAIN_INTAKE_ENABLED=true` on Coolify with the existing `$5.00` per-run cap (`BRAIN_INTAKE_MAX_USD=5.00`). New threads now pass automatically through the calibrated 4-tier gate (`prompts/intake_gate.md`).
   - **What it blocks:** Resuming automatic intake (`BRAIN_INTAKE_ENABLED=false` is intentionally paused by owner instruction until map inspection) and ticking `- [ ] live proof` on [`#607`](https://github.com/u2giants/theoracle/issues/607) and [`#664`](https://github.com/u2giants/theoracle/issues/664).
2. **Recoverable choice (reviewing employee corrections — `/map/corrections`):** As the 7 designated reviewers submit text corrections on [https://oracle.designflow.app/map/corrections](https://oracle.designflow.app/map/corrections), do you want AI assistance periodically applying/summarizing open corrections into the map, or will you personally click **Apply to map** / **Dismiss** on each note?
   - **Recommendation:** Admin-reviewed apply on `/map/corrections` (already live) so unvetted text never bypasses review; reversible anytime.
   - **What it blocks:** Only whether an automated triage sweep is needed later; does not block reviewers from submitting right now.
3. **Already settled — do NOT re-ask (owner rulings from this session, 2026-11-24):**
   - **Process knowledge vs. everyday execution:** Normal everyday single-SKU work — including written licensor artwork rejections and automated portal templates (`DesignFlow Licensing Feedback`, `Disney OPA`, `STARLABS`, etc.) — belongs in `transactional_routine` (searchable only, excluded from the Company Map), NOT `knowledge`, unless it states a company/licensor-wide workflow rule, role ownership, or systemic breakdown. (Calibrated 15/15 against Albert's 15 rulings + follow-up clarification.)
   - **Teams group chats:** Group chat membership alone never determines company team membership; automated Teams add-to-team alerts are dropped (`drop_marketing_auto`).
   - **ScaleDown / decision model budget:** Never trade classification decision quality for pennies on decision models; `openai/gpt-6-luna` stays on `intake_gate` while Frontier (`claude-sonnet` / `sol`) stays reserved for yardstick evals rather than ongoing per-thread production gating.
   - **Employee correction access:** All 56 active employees can view the Company Map (read-only); text correction submissions on `/map/corrections` are restricted initially to the 7 named reviewers (Ilona Kereki, Laura Arevalo, Marcel Zabolotniy, Elizabeth Parkin, Jessica Cortazar, Carlos Corral, Jennifer Chaffier) plus admins, adjustable by admin inside `/map/corrections`.

---

## 1. What this application is

**The Oracle** (`u2giants/theoracle`, [`https://github.com/u2giants/theoracle`](https://github.com/u2giants/theoracle)) builds POP Creations / Spruce Line's evidence-backed **Company Map** from company documents, meeting transcripts, and authorized employee email/Teams/ClickUp threads.

- **Web UI (`apps/web`):** Next.js 16 on Vercel ([`https://oracle.designflow.app`](https://oracle.designflow.app), map at [`/map`](https://oracle.designflow.app/map)), proxying API calls via [`/api/brain/[...path]`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/api/brain/%5B...path%5D/route.ts) with `x-brain-token` and Supabase `x-user-id`.
- **Brain Service (`apps/brain`):** FastAPI + background worker deployed as a GHCR container on Coolify (`oracle-brain`, API at `https://oracle-brain.designflow.app`). Runs `python -m brain.migrate` idempotently on every container boot (`apps/brain/brain/sql/*.sql`).
- **Database / Auth / Storage:** Supabase Postgres (`cmap` schema for the map; `public.employees`, `public.employee_identities` for auth) + FalkorDB graph.

---

## 2. What we set out to do this session, and why

1. **Stop noise from polluting the Company Map (`#607`):** Earlier PM/Licensing ingestion let marketing blasts, Teams add-to-team alerts, casual personal chatter, and thousands of routine single-SKU licensor/portal updates extract into the Company Map.
2. **Build and calibrate a 4-tier intake relevance gate (`prompts/intake_gate.md`):** Separate `knowledge` (feeds Company Map) vs. `transactional_routine` (searchable RAG-only, excluded from map projection & community summaries) vs. `drop_marketing_auto` / `drop_irrelevant_internal` (purged), incorporating Albert's 15 borderline rulings and his clarification on routine written licensor rejections.
3. **Re-filter all existing ingested threads retroactively & rebuild a clean Company Map:** Purge dropped/legacy noise, optimize `communities.py` so the full rebuild completes reliably, and verify clean L0/L1/L2 reports.
4. **Add a restricted text-correction page (`/map/corrections`):** Give the 7 designated employees (and admins) a place to type free-text corrections on what is wrong on the map and how the process actually works, with admin Apply-to-map / Dismiss and an admin toggle UI to add/remove reviewers anytime.

---

## 3. Current state — what is true right now

### Code & Deployments (all merged to `main` and live)
- **PR [#699](https://github.com/u2giants/theoracle/pull/699)** ([`759f2480`](https://github.com/u2giants/theoracle/commit/759f2480)) & **PR [#701](https://github.com/u2giants/theoracle/pull/701)** ([`d0c7b00c`](https://github.com/u2giants/theoracle/commit/d0c7b00c)): Added Phase 1 relevance gate, `sql/041_intake_relevance_and_map_eligibility.sql`, `intake_gate` model seat (`openai/gpt-6-luna`), HTML/quoted-chain pre-stripping, and calibrated `prompts/intake_gate.md` (15/15 exact calibration).
- **PRs [#702](https://github.com/u2giants/theoracle/pull/702)** ([`023e1234`](https://github.com/u2giants/theoracle/commit/023e1234)), **[#706](https://github.com/u2giants/theoracle/pull/706)** ([`b6128e63`](https://github.com/u2giants/theoracle/commit/b6128e63)), **[#707](https://github.com/u2giants/theoracle/pull/707)** ([`03ea4f47`](https://github.com/u2giants/theoracle/commit/03ea4f47)), **[#711](https://github.com/u2giants/theoracle/pull/711)** ([`6f23f297`](https://github.com/u2giants/theoracle/commit/6f23f297)): Fixed $O(K^2)$ Leiden folding CPU stall, N+1 `_content_hash` SQL scans, early memory freeing, chunked L0 commits (`L0_ASK_CHUNK=64`, `REPORT_WORKERS=32`), `_quote_rows_bulk`, parallel `_fit` & L1 rollups, and batched/parallel `_vet_question_groups` (`communities.py` sped up ~25–30x, from ~12m/24 clusters to ~64 clusters every ~60–90s).
- **PR [#716](https://github.com/u2giants/theoracle/pull/716)** ([`9492fef3`](https://github.com/u2giants/theoracle/commit/9492fef3)): Added [`sql/042_employee_corrections.sql`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/042_employee_corrections.sql), [`brain/api/correction_notes.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/correction_notes.py), [`/map/corrections`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/map/corrections/page.tsx), conditional links in [`map-home.tsx`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/map/_components/map-home.tsx) and [`function-view.tsx`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/map/_components/function-view.tsx), and [`tests/test_correction_notes.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_correction_notes.py). All 760 brain tests and Next.js build/typecheck/lint passed in CI.
- **Live Coolify `oracle-brain` (`uge6pfm4qapktivto4981mtg`):** Running [`9492fef3`](https://github.com/u2giants/theoracle/commit/9492fef3dc888787c60cc13ce4b43462a35e2b95), `/health` = `200 {"ok":true,"db":true,"graph":true}`, **`BRAIN_INTAKE_ENABLED=false`** (intentionally paused), **`BRAIN_MAX_FRONTIER_CALLS_PER_JOB=3000`** (restored after rebuild), `BRAIN_INTERVIEW_ENABLED=false`.
- **Live Vercel (`prj_rP6Jlima7iK1paffEPhLqxlswGsC`):** Deployment for [`9492fef3`](https://github.com/u2giants/theoracle/commit/9492fef3dc888787c60cc13ce4b43462a35e2b95) succeeded; `https://oracle.designflow.app/map/corrections` returns HTTP `307` -> `/` (live route active behind login).

### Verified Production Database & Map State (`graph_version = 58`)
- **Source corpus after full retroactive re-filter + legacy cleanup:**
  - Map-eligible (`ingest_tier = 'full'`, `map_eligible = true`): **`1,996` message threads** (`1,342` email, `608` Teams chat, `46` ClickUp) + **`79` company documents** (`73` clean + `6` with partial page read notes).
  - Searchable-only (`ingest_tier = 'rag_only'`, `map_eligible = false`, `read_error IS NULL`): **`4,976` everyday operational threads** (`4,685` email, `267` Teams chat, `24` ClickUp).
  - Purged dropped (`ingest_tier = 'rag_only'`, `map_eligible = false`, `read_error IN ('dropped:gate', 'dropped:marketing')`): **`610` sources** (`462` + `91` email, `57` Teams chat); `0` remaining chunks/mentions on dropped sources.
  - Active map-eligible entities: **`52,116`** (`66,342` total entities after pruning orphaned entities).
- **Clean Company Map (`graph_version = 58`, job `51179c27-551e-4c8c-906d-b7535d084e2b` `done`):**
  - `level = 0`: **`4,287`** area reports (`0` failed, `0` incomplete).
  - `level = 1`: **`13`** department reports (`5` `incomplete = false`, `8` large departments `incomplete = true` purely due to context compression rounding; all 13 render clean business-process summaries on live `/communities?level=1`).
  - `level = 2`: **`1`** Company Report — *"Cross-Department Product Approval and Release"* (`incomplete = false`, `9` findings, clean Top 10 cross-department issues with zero marketing/webinar/spam noise on live `/map/company`).
- **Live `/map/corrections` Access Control Proof (`9492fef3`):**
  - `cmap.employee_flags.can_correct = true` seeded in DB for exact 7 employees: `Carlos Corral`, `Elizabeth Parkin`, `Ilona Kereki`, `Jennifer Chaffier`, `Jessica Cortazar`, `Laura Arevalo`, `Marcel Zabolotniy` (across `56` active employees).
  - Verified against live `https://oracle-brain.designflow.app`:
    - Admin (`albert@popcre.com`): `GET /corrections/access` -> `200 {"can_correct": true, "is_admin": true}`, `GET /corrections/permissions` lists the 7 enabled across 56 active employees.
    - Reviewer (`Carlos Corral`): `GET /corrections/access` -> `200 {"can_correct": true, "is_admin": false}`, `GET /corrections/notes` -> `200`.
    - Non-reviewer (`Martina Cardoso`): `GET /corrections/access` -> `200 {"can_correct": false, "is_admin": false}`, `GET /corrections/notes` -> `403`.

---

## 4. Everything we tried that did NOT work

1. **ScaleDown `/extract` and `/summarize` for intake noise filtering:** Investigated first per owner question. Neither removes irrelevant marketing newsletters (`98.3%` email pass-through under 7-label `flat.py`), and `sd_summarize` just summarizes spam rather than dropping it. Solved with the dedicated 4-way rubric in [`prompts/intake_gate.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/intake_gate.md) on `openai/gpt-6-luna`.
2. **OpenAI `/v1/batches` for the 7,487 retroactive classification:** 5 consecutive batches stalled at `0` completed on `gpt-6-luna`. Bypassed by running concurrent direct `flex` responses with sync fallback, classifying all `7,152` non-Tier-0 threads cleanly.
3. **Running `communities` before optimizing [`communities.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/graph/communities.py):** Four separate bottlenecks stalled `communities`: (a) $O(K^2)$ Leiden folding loops (>30m), (b) 5,000+ N+1 `_content_hash` SQL queries (>25m), (c) monolithic 3,000+ cluster memory retention causing container restart at 27m with 0 committed rows, and (d) serial L0 `_quote_rows` + `_fit` + per-cluster `vet_questions` embed/pgvector/LLM loops projecting ~21 hours. Fixed across PRs [#702](https://github.com/u2giants/theoracle/pull/702), [#706](https://github.com/u2giants/theoracle/pull/706), [#707](https://github.com/u2giants/theoracle/pull/707), and [#711](https://github.com/u2giants/theoracle/pull/711).
4. **Initial retroactive re-filter left 241 legacy/untiered message sources as `map_eligible=true`:** `91` emails already marked `read_error='dropped:marketing'` and `147` pre-gate legacy sources had `map_eligible = true` by migration default, leaking Black Friday/webinar clusters into `gv=57`. Purged all 91 + classified all 147 before running `gv=58` (`33` classified `knowledge` have no legacy `cmap.intake_thread` row but are accurately `ingest_tier='full', map_eligible=true`).
5. **Cloudflare WAF & Coolify API gotchas:** Python's default `urllib` `User-Agent` triggers Cloudflare `HTTP 403` on `coolify.designflow.app` — always pass a custom `User-Agent` header. Also Coolify stores `is_preview=true` env rows alongside production rows — always filter `not e["is_preview"]` when reading `BRAIN_SHARED_TOKEN`.
6. **Test UUID & CI schema table collisions in PR [#716](https://github.com/u2giants/theoracle/pull/716):** Initially missed registering `correction_note` in [`tests/test_schema.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/tests/test_schema.py) and reused test UUIDs `...00c1`/`...00c2`/`...00c3` already used by `test_functions.py` (`Ada`) and `test_interview.py`. Fixed in [`37e26cb5`](https://github.com/u2giants/theoracle/commit/37e26cb5).

---

## 5. Root causes and key findings

- **Why "written licensor rejection" emails still cluttered the map initially:** Under an earlier prompt draft, any thread involving a licensor/buyer revision looked operational. Albert clarified that routine written rejections on individual SKUs are normal everyday execution (`transactional_routine`), whereas company-wide policies, compliance rules, or systemic breakdowns are `knowledge` (codified in [`prompts/intake_gate.md`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/prompts/intake_gate.md)).
- **Why legacy sources leaked after the first pass:** Migration [`041_intake_relevance_and_map_eligibility.sql`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/041_intake_relevance_and_map_eligibility.sql) defaulted `map_eligible` to `true`, so pre-existing `dropped:marketing` rows and older emails lacking `cmap.intake_thread` rows remained eligible until explicitly purged/gated.
- **Why existing `MarkWrongButton` (`POST /flags`) was left untouched:** `MarkWrongButton` in [`mark-wrong.tsx`](https://github.com/u2giants/theoracle/blob/main/apps/web/app/map/_components/mark-wrong.tsx) flags an entity/edge/community as wrong (without a standalone free-text "how it works" workflow) and is tested for any logged-in user; [`correction_notes.py`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/api/correction_notes.py) provides the separate free-text correction + admin-apply-as-source + per-employee permission system requested.
- **Why `test_schema.py` had a `# sql/042_meeting_transcript.sql` sibling:** Concurrent PR [#715](https://github.com/u2giants/theoracle/pull/715) added [`042_meeting_transcript.sql`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/042_meeting_transcript.sql) alongside our [`042_employee_corrections.sql`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/sql/042_employee_corrections.sql). Both are idempotent and non-conflicting (`test_migrate_runs_twice_without_error` and Coolify startup both passed); next migration should be `043_*`.

---

## 6. Exact next steps

1. **Ask Albert Business Decision #1 (Section 0):** Confirm he reviewed [https://oracle.designflow.app/map](https://oracle.designflow.app/map) and wants automatic intake unpaused.
   - *Gate:* Clear explicit "yes / turn intake back on" in Albert's reply.
2. **When approved, re-enable intake cleanly on Coolify (`uge6pfm4qapktivto4981mtg`):**
   - PATCH `BRAIN_INTAKE_ENABLED` (`is_preview: False`) to `"true"` (keep `BRAIN_INTAKE_MAX_USD="5.00"` and `BRAIN_MAX_FRONTIER_CALLS_PER_JOB="3000"`).
   - Deploy/restart `oracle-brain` and verify `GET https://oracle-brain.designflow.app/health` returns `200` and `BRAIN_INTAKE_ENABLED == "true"`.
   - *Verification:* Trigger or inspect the next `intake_ingest` sweep to confirm only `knowledge` threads get `map_eligible = true` (`transactional_routine` stays `rag_only`, marketing/chatter drops).
3. **Close out tracking issues & predecessor handoffs once owner confirms:**
   - Tick `- [ ] live proof` on [`#607`](https://github.com/u2giants/theoracle/issues/607) and [`#664`](https://github.com/u2giants/theoracle/issues/664), update [`plan_pm_message_intake.md`](https://github.com/u2giants/theoracle/blob/main/plan_pm_message_intake.md) Step `4.1` -> `✅ done`, and retire both `HANDOFF.d/2026-11-23T2300Z-edge-dev-agy-oracle-607-664-live-proof-ready.md` and this handoff in the closing commit (successor rule in [`AGENTS.md`](https://github.com/u2giants/theoracle/blob/main/AGENTS.md)).
4. **Deferred non-blocking maintenance (do NOT block unpausing on these unless desired later):**
   - If you ever want all `8` large L1 department reports (`156`–`1,014` L0 children) to store `incomplete = false` in `cmap.community`, cap/dedupe per-group `sources:` lines or do 2-level group reduction inside [`_context_reports`](https://github.com/u2giants/theoracle/blob/main/apps/brain/brain/graph/communities.py) before `_fit()`.
   - When unpausing intake, check whether `function_assign` still needs a sweep over any `rag_only` chunks or should skip `map_eligible = false` sources if desired.

---

## 7. Constraints and gotchas in force

- **Never re-enable `BRAIN_INTAKE_ENABLED` without owner approval.**
- **Coolify pins `BRAIN_IMAGE_TAG` to a specific git SHA** (NOT `latest`) — always PATCH `BRAIN_IMAGE_TAG` before `/deploy`.
- **Use `"User-Agent": "oracle-ops/1.0"`** on all Python HTTP calls to `coolify.designflow.app` and `oracle-brain.designflow.app`.
- **Direct `/api/brain` vs Brain FastAPI auth:** FastAPI routes using `current_user` require BOTH `x-brain-token` AND an active employee's `x-user-id` (UUID from `public.employee_identities`).
- **GitHub delivery rules:** Never push directly to `main`, never use `--admin` or `--squash` on `gh pr merge` (use `--merge`), never edit `HANDOFF.md` or another session's `HANDOFF.d/` file, and never commit secret values or private email/chat bodies (`u2giants/theoracle` is a **PUBLIC** repo).

---

## 8. Access and environment

- **Repo:** [`https://github.com/u2giants/theoracle`](https://github.com/u2giants/theoracle) (`main` at [`9492fef3`](https://github.com/u2giants/theoracle/commit/9492fef3dc888787c60cc13ce4b43462a35e2b95)).
- **Web App (Vercel `prj_rP6Jlima7iK1paffEPhLqxlswGsC`):** `https://oracle.designflow.app` (map at `/map`, corrections at `/map/corrections`).
- **Brain Service (Coolify `uge6pfm4qapktivto4981mtg`):** `https://oracle-brain.designflow.app`.
- **Credentials (1Password vault `vibe_coding` — no values stored here):**
  - Coolify API token: item `c44ghscsnug2xvvrzzp3on7mme` (`credential`)
  - Postgres session pooler DSN: item `qcuyabwseaptvuzvtjejffi2ou` (`oracle_session_pooler`)
  - Runtime API keys (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `BRAIN_SHARED_TOKEN`, etc.) live in Coolify service envs and Vercel env settings.

---

## 9. Open questions and risks

- **Risk — `8` L1 department rows store `incomplete = true`:** Does not break `/map`, `/map/functions/<key>`, `/communities?level=1`, or `/map/company` (L2 is `incomplete = false`), and existing prose is clean; only means the next `communities` run will regenerate those 8 L1 reports instead of caching them until `_context_reports` compresses large group lists under `12,000` tokens.
- **Risk — Only 18 of 56 active employees have signed in so far:** Employees among the 7 named reviewers who have not signed in yet (`linkOrRejectEmployee` creates their `public.employee_identities` row automatically on first M365/Google sign-in) are already matched by `public.employees.id` in `cmap.employee_flags.can_correct`, so they will have access immediately on first sign-in. Verified live with `Carlos Corral` (`200`), `Albert Hazan` (`200`), and non-reviewer `Martina Cardoso` (`403`).
- **Decision log (2026-11-24):** Temporary bump of `BRAIN_MAX_FRONTIER_CALLS_PER_JOB` to `10000` during `gv=58` full rebuild was restored back to `3000` after `communities` completed.

---

### Handoff self-audit gate
1. *Comprehensive enough for a brand-new developer with zero context?* **Yes** — Sections 1–5 supply the full system map, all 7 merged PRs with SHAs, exact live database counts, the 6 failed approaches/pitfalls so none are repeated, and exact locations via GitHub URLs.
2. *Detailed enough to continue as effectively as this session?* **Yes** — Section 0 separates exact owner decisions from settled rulings, Section 6 gives exact Coolify toggles and successor retirement rules, and Section 8 identifies all live services and 1Password item references without exposing secrets.
3. *Every relevant detail included (background, goals, state, failures, decisions, constraints, risks, next actions, verification)?* **Yes** — Checked all 10 sections (`0–9`), verified zero machine-local paths and zero secret values.
