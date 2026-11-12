---
summary: "Current repair and consultant-upgrade plan (#520): phased fixes for answer quality, domains, dates, relationships, interviews and corrections."
kind: plan
status: open
read-when: starting or continuing any brain repair or consultant feature; read STATUS first
---

# Oracle repair and consultant-grade upgrade — implementation plan

Written 2026-11-11, 7:50 AM EST, by Claude (Fable 5.2) on edge-dev3 for Albert Hazan.
Program issue: [u2giants/theoracle#520](https://github.com/u2giants/theoracle/issues/520) (one checklist item per phase; no child issues unless a phase is handed to a separate session).
Source audit (read it once, it is the evidence base): [docs/audit-2026-11-11-oracle-goals.md](docs/audit-2026-11-11-oracle-goals.md).
Phase A record (no open handoff; this STATUS table is the baton): [docs/verification/repair/A8-baseline.md](docs/verification/repair/A8-baseline.md).
Predecessor program (complete except owner acceptance): [plan_oracle_company_map.md](plan_oracle_company_map.md). Its Part 3 defines the tables and pipeline this plan modifies; read the step it names when this plan points there.

**Who this is written for:** a fresh AI session with no memory of the audit conversation. Every step names files, the intended behaviour, and a test. If a step forces you to invent a design that is not written here, stop and record the gap in STATUS.

**Path shorthand used throughout:** `B/` = `apps/brain/brain/`, `T/` = `apps/brain/tests/`, `W/` = `apps/web/app/`. Line numbers are as of commit `3c7e2e39` on `main`; re-locate by function name if they have drifted.

---

## STATUS — read this first

Fresh session starts at: **the first row marked ⬜ open, in order.** Phases A and B come first and are strictly ordered; C–J may run in the order shown or in parallel sessions where the "needs" column allows. Update this table in the same PR that lands a step. A row is `✅ done` only when its gate passed and the evidence cell names an artifact a reader can open (test path, CI run id, commit SHA, file under `docs/verification/repair/`).

| Step | Title | Needs | State | Evidence / blocker | Updated (EST) |
|---|---|---|---|---|---|
| A1 | Company-wide answers read only the current map | — | ✅ done | `T/test_answer.py::test_global_ignores_superseded_reports`, `T/test_communities.py::test_old_versions_pruned`; reuse confirmed to stamp the new version (`communities.py` `_finish_l0`); live count + score land in `docs/verification/repair/A1.md`; live: `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| A2 | Failed reading is retried and never shows as "read" | — | ✅ done | `T/test_flat.py::test_one_bad_chunk_does_not_lose_the_source`, `T/test_worker_orphans.py::test_failed_job_retried_with_backoff`, `T/test_chain_debounce.py::test_stalled_chain_is_healed`; SQL `016_read_states.sql`; live: `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| A3 | Passage splitter loses no text | — | ✅ done | `T/test_chunk_cjk.py::test_no_text_lost_property`; live: `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| A4 | Office files with links/charts are read | — | ✅ done | `T/test_read.py::test_external_relationship_never_fetched`, `::test_large_sheet_streamed`; shared Office size cap 50 MB expanded; live: `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| A5 | Spreadsheets keep rows, columns, headers | A3 | ✅ done | `T/test_read.py::test_xlsx_header_repeated_and_columns_aligned`, `::test_csv_rows_never_split`, `::test_xlsx_dates_are_iso`, `::test_docx_table_and_image_read`; CSV/TSV stay stored as kind `text` and are routed at read time; live: `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| A6 | Diagrams on text pages are read | — | ✅ done | `T/test_read.py::test_mixed_page_text_and_diagram_both_read`, `::test_unreadable_regions_recorded`; SQL `017_source_read_notes.sql`; live: `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| A7 | Small reading bugs (speaker pattern, empty source, size caps) | — | ✅ done | `T/test_transcript_cjk.py::test_clock_time_is_not_a_speaker`, `T/test_intake.py::test_delete_answer_source`, `T/test_project.py::test_zero_mention_entities_not_projected`, `T/test_worker_orphans.py::test_result_write_is_retried`, `T/test_read.py::test_pptx_bad_picture_does_not_fail_deck`; SQL `018_answer_source_set_null.sql`; live: `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| A8 | Re-read everything and rebuild; baseline score | A1–A7 | ✅ done | `POST /sources/reread-all`, `T/test_flat.py::test_prompt_change_replaces_not_duplicates`; baseline 0.364 and 0.409 (mean 0.39) in `docs/verification/repair/A8-baseline.md` | 2026-11-11 8:30 PM EST |
| B1 | Owner-approved question set on the eval page | — | ✅ done | `T/test_eval_admin.py::test_only_approved_count`, `::test_admin_approve_edit_retire_actions`, `::test_b1_drafts_load_as_unapproved_drafts`, `::test_b1_drafts_meet_function_coverage`; Playwright `map.spec.ts::admin approves a draft eval question and it counts` (7/7 green, screenshots 14–15); 30 drafts + coverage table in `docs/verification/repair/B1.md`; columns `approved_at`/`function text[]`/`abstention`/`retired_at`/`recommendation` in SQL 019 | 2026-11-11 10:57 PM EST |
| B2 | Scoring counts sources and unsupported sentences | — | ✅ done | `T/test_eval_fixture.py::test_score_components`, `::test_errors_fail_run`, `::test_abstention_question`; `B/sql/021_eval_scoring.sql`; PR https://github.com/u2giants/theoracle/pull/536 | 2026-11-11 10:47 PM EST |
| B3 | Live quality gate after every deploy and nightly | B2 | ✅ done | `T/test_eval_fixture.py::test_gate_detects_drop`, `::test_gate_accepts_first_run_and_keeps_baseline`, `::test_gate_fails_on_question_error`, `::test_eval_service_calls_queue_and_read_runs`, `::test_live_gate_marks_accepted_and_catches_drop`, `::test_live_gate_surfaces_accept_failure`; `B/sql/020_eval_quality_gate.sql`, `B/eval/gate.py`, `.github/workflows/brain-quality.yml` (FAIL on mean drop > 0.05 or any question error; `cmap.eval_run.accepted` holds the baseline, marked via `POST /eval/runs/{id}/accept` — accept round-trip covered by the live tests); PR [#544](https://github.com/u2giants/theoracle/pull/544) (`fix/b3-quality-gate` → `main`, #520) + gate-fix [#545](https://github.com/u2giants/theoracle/pull/545); live: dispatch runs [43163303981](https://github.com/u2giants/theoracle/actions/runs/43163303981) (1:04 AM) and [43165847107](https://github.com/u2giants/theoracle/actions/runs/43165847107) (1:07 AM, 22-second correct verdict post-#545), issue [#546](https://github.com/u2giants/theoracle/issues/546); `docs/verification/repair/B3.md` — gate is red only while the 30 B1 drafts await owner approval, then the next passing run becomes the accepted baseline | 2026-11-12 1:10 AM EST |
| B4 | Pipeline health panel | — | ✅ done | `T/test_sources_health.py::test_health_surfaces_failed_and_retrying_job_errors`, `::test_health_reports_states_failed_extractions_build_and_spend`, `::test_sources_health_requires_admin`; Playwright `map.spec.ts::health panel shows the seeded failed job with its error text`; `apps/web/tests/__screenshots__/map/14-health-panel.png`; `GET /sources/health` in `B/api/sources.py` (no schema change); spend = `cmap.job` payload.usage token/call counters (no dollar-cost store exists); PR [#538](https://github.com/u2giants/theoracle/pull/538) (`fix/b4-health-panel` → `main`, #520) | 2026-11-11 10:58 PM EST |
| C1 | Business-function list (curated) | — | ✅ done | `T/test_functions.py::test_seed_and_edit_roundtrip`, `::test_reseed_is_idempotent`, `::test_functions_require_token_and_admin`, `::test_seed_aliases_match_department_evidence`; `B/sql/022_functions.sql` (seed = the 13 proposal functions, evidence-clustered aliases from cmap_s8_base Department mention names + fixture entities + department_hint values — mapping in the PR body); `B/api/functions.py` (list for any employee; add/rename/merge/retire admin-gated); Playwright `map.spec.ts::functions page renders the curated function list` (`apps/web/tests/__screenshots__/map/16-functions-list.png`); `W/map/functions` + map nav link; PR [#548](https://github.com/u2giants/theoracle/pull/548) (`feat/c1-function-list` → `main`, #520) | 2026-11-12 1:38 AM EST |
| C2 | Every source, passage and thing is assigned to functions | C1 | ✅ done | `T/test_functions.py::test_handoff_entity_in_two_functions`, `::test_admin_assignment_survives_rerun`, `::test_hint_is_prior_not_override` (plus `::test_eval_question_functions_backfilled`, `T/test_directory_sync.py::test_directory_department_title_written_and_map_to_function`); `B/sql/024_function_assignment.sql` (`cmap.source_function`/`chunk_function`/`entity_function`: pair PK, `weight real`, `origin auto|admin`; `cmap.extraction.stage` gains `'function'`); `B/function_assign.py` + `B/prompts/function_assign.md` (flat-seat multi-label classifier, 0–3 functions; `department_hint` and speaker-profile department are priors via the C1 aliases — add/lift only, never override evidence; `origin='admin'` rows never overwritten; source fallback `executive-company-wide` at 0.3, logged); `W/map/_components/function-assign.tsx` on the source and entity pages (`PUT /sources|entities/{id}/functions`); directory sync writes department/title when the directory row carries them; `cmap.eval_question.function` backfilled idempotently from `questions.b1.json` and editable on the eval page; Playwright `map.spec.ts::entity and source pages show function assignments and the admin sets one` (`apps/web/tests/__screenshots__/map/17-function-assignment.png`, 10/10 map tests green on throwaway `BRAIN_E2E_DATABASE_URL`); brain suite 369 passed + ruff clean. **Gap:** a merged chunk set can exceed 3 when priors add to a 3-pick model answer. Live: `docs/verification/repair/C2.md` (`function_assign` done via the chain heal; **0 sources without a function**; counts per function table) | 2026-11-12 3:45 AM EST |
| C3 | Clusters live inside functions; stable identities | C2 | ✅ done | `T/test_communities.py::test_function_report_id_stable_across_rebuilds`, `::test_cluster_id_reused_on_small_change`, `::test_new_relation_regenerates_report`, `::test_failed_child_does_not_poison_parent`, `::test_company_input_never_truncated`, plus `::test_recommendation_and_flag_references_survive_regeneration` (references **preserved**, not re-pointed: rows are updated in place under their stable id, so `cmap.recommendation`/`cmap.review_flag` never orphan — no migration re-point needed, and pre-C3 rows survive on A1's referenced-row protection); `B/sql/027_community_content_hash.sql` (`cmap.community.content_hash`/`incomplete`/`function_id`, `cmap.relation.updated_at`); `B/prompts/context_summary.md` + map-reduce `_fit` (no silent truncation left); brain suite **394 passed** + ruff clean. **Gaps:** (1) entities with no active-function assignment cluster in a logged `unassigned_entities` bucket parented straight under the company row (no level-1 report); (2) a level-0 cluster keeps its Jaccard-matched title when its content regenerates — by design ("reuse its id and title") but the body is fresh; (3) Leiden level-1 middle groups are gone (replaced by function reports) — `test_level1_groups_stay_under_entity_cap` removed with `_level1_membership` | 2026-11-12 4:53 AM EST |
| C4 | Function-scoped answering with a hard budget | C2 | ⬜ open | | |
| C5 | Map page organised by function | C3 | ⬜ open | | |
| D1 | Every source has a date | — | ✅ done | `T/test_dates.py` (one test per origin: `test_admin_entered_date_wins`, `test_meeting_start_from_transcript_metadata`, `test_interview_answer_timestamp`, `test_document_text_date_from_model`, `test_file_metadata_date`, `test_upload_time_floor_never_null`; plus `test_backfill_dates_idempotent`, `test_relation_dated_view_inherits_source_date`); `B/sql/025_source_dates.sql` (`cmap.source.date_origin`, view `cmap.relation_dated`); precedence resolver `B/read/dates.py` at read time + creation stamps (writers stop writing NULL); prompt `B/prompts/source_date.md` (flat seat, first+last page); backfill action `POST /sources/backfill-dates`; date + origin on `W/map/source` (Playwright `map.spec.ts::source page shows the effective date and its origin`, `apps/web/tests/__screenshots__/map/17-source-date.png`); PR body has the precedence table + backfill contract. Live: `docs/verification/repair/D1.md` (backfill done in 1 attempt; **zero NULL dates**; origins: 52 upload_time, 4 file_metadata, 2 document_text). Design note: the live Recall webhook capture posts transcripts without meeting metadata, so those resolve to the upload floor until that capture passes `effective_date` | 2026-11-12 3:10 AM EST |
| D2 | Newer versions supersede older ones | D1 | ⬜ open | | |
| D3 | Contradictions across sources are detected and queued | D1 | ⬜ open | | |
| D4 | Knowledge ageing and re-confirmation | D1, F1 | ⬜ open | | |
| E1 | Relationships across neighbouring passages | A8 | ⬜ open | | |
| E2 | Whole-document process pass (ordered steps) | E1 | ⬜ open | | |
| E3 | Missing relationship kinds | E1 | ⬜ open | | |
| E4 | Cross-function hand-offs reach the summaries | C3 | ⬜ open | | |
| E5 | Ordered flow view | E2 | ⬜ open | | |
| F1 | Systematic gap finder | C2, E2 | ⬜ open | | |
| F2 | Real multi-turn interviews | F1 | ⬜ open | | |
| F3 | Routing by role, referrals, re-asks | C2 | ⬜ open | | |
| F4 | Reply matching and chat-safety fixes | — | ✅ done | `T/test_interview.py::test_group_chat_reference_never_stored`, `::test_late_reply_matched_to_right_question`, `::test_thanks_is_not_a_profile`, `T/test_inbound_zh.py::test_stop_variants_and_resume`; shared `QUESTION_WINDOW_DAYS=7`; judge prompts `B/prompts/intent_check.md`, `profile_check.md`, `reply_match.md`; PR [#550](https://github.com/u2giants/theoracle/pull/550) | 2026-11-12 1:53 AM EST |
| F5 | Role interview ("tell me about your job") | F2, F3 | ⬜ open | | |
| F6 | Coverage scorecard page | F1 | ⬜ open | | |
| G1 | Corrections that stick | — | ✅ done | `T/test_corrections.py::test_rejected_relation_gone_after_rebuild`, `::test_correction_survives_full_reread`, `::test_edit_replaces_fact_in_answers` green (381 brain tests total); `B/sql/026_corrections.sql` + `B/corrections.py` (content-key scheme in its docstring); review-flag backfill counted in `T/test_corrections.py::test_review_flag_migration_backfills_and_is_idempotent`. Gaps: community flags have no correction target kind so they resolve without a correction row; flag creation itself writes no correction — the 026 backfill or the resolve action does | 2026-11-12 3:42 AM EST |
| G2 | Merge, split, rename | G1 | ⬜ open | | |
| G3 | Identity repair pass | G2 | ⬜ open | | |
| G4 | Employee feedback on answers | G1 | ⬜ open | | |
| H1 | Every sentence is supported or marked | B2 | ⬜ open | | |
| H2 | Honest "I don't know" that feeds the gap finder | F1 | ⬜ open | | |
| H3 | Ask the Oracle in Teams | C4 | ⬜ open | | |
| H4 | Conversation memory and question log | — | ⬜ open | | |
| H5 | Reliability: second provider, retries, spend cap | A2 | ⬜ open | | |
| I1 | Computed bottlenecks and single points of failure | E2 | ⬜ open | | |
| I2 | Recurring-problem detector across functions | C2 | ⬜ open | | |
| I3 | Recommendation follow-through | — | ⬜ open | | |
| I4 | Weekly owner briefing | I1, I2, D3 | ⬜ open | | |
| I5 | "What if" impact tracing | E2 | ⬜ open | | |
| I6 | Role playbooks for onboarding | E2, C2 | ⬜ open | | |
| I7 | Meeting follow-through (decisions and action items) | D1 | ⬜ open | | |
| J1 | Operational numbers: design and first feed | C1 | ⬜ open — blocked on owner choice of first data set (§13 Q3) | | |
| J2 | Numbers in answers and recommendations | J1 | ⬜ open | | |
| J3 | Measured before/after for recommendations | J2, I3 | ⬜ open | | |

**Drift log (each phase's finisher re-reads every later phase to plan-end and records what changed for them):**
- 2026-11-11 (Phase A, complete; baseline self-test 0.39 against the 0.6 target — Phase A did not lift the score, so B–E carry it): `cmap` SQL is applied at brain start-up since #528 (before that it was a manual `python -m brain.migrate`); SQL 016–018 are used, **next free number is 019**. `read_state` is now `queued|reading|extracting|read|partial|failed` and failed passages are rows in `cmap.extraction` with `error` set — B4's health panel reads these, and admin actions `POST /sources/reread-all`, `/sources/{id}/reread`, `/jobs/retry-failed` already exist. `cmap.source.read_notes` exists (A6); E1 adds its drop-reason counts under a new key there. CSV/TSV are stored as kind `text` and routed at read time (affects A5-style readers and D1's file-metadata dates). A full re-read re-creates entities, so entity row ids change: C3's "re-point recommendations and flags" and G1's content-based keys must not assume ids survive, and F1's `gap_key` must be content-based. H5's job retry/backoff half is done in A2 (`worker.finish_job`); H5 still owns the second provider and spend cap; a full re-read costs roughly 30–36k tokens per passage on the current flat seat (about five hours for 314 passages). The Meta API rejects OpenRouter-only request parameters (H5 second-provider work must gate parameters per provider, see `llm.py`).
- 2026-11-12 (Phase B, complete — B1/B2/B3/B4 merged and deployed as brain image `53a20db5`; PRs #536/#538/#543/#544 plus gate-fix #545): SQL 019 (B1: `cmap.eval_question.approved_at`, `function text[]`, `abstention bool`, `retired_at`, `recommendation`), 020 (B3: `cmap.eval_run.accepted bool`), 021 (B2: `eval_question.abstention` re-declare + `eval_run.mean_score_legacy`) are used; **next free number is 022**. For **C1**: `eval_question.function` is `text[]` (multi-valued — a question may span functions) and is still empty; `apps/brain/eval/questions.b1.json` carries a per-question `functions` key (documentation metadata) you can use to pre-fill, and the 13-function proposal is already the coverage vocabulary B1's drafts were written against. Two older Chinese negative seed questions are abstention-style but still `abstention=false` — flag them when C1/C2 touch question rows. For **H1**: `B/eval/run.py::supported_sentence_share()` is the seam B2 built — swap only its body; the live score is 0.6 points + 0.2 expected sources cited + 0.2 supported-share, and `score_legacy`/`mean_score_legacy` are carried for **three runs only** (retire them after the third eval-bearing landing — B3's gate run counts as one). For **H5**: there is **no dollar-cost store** — the only accounting is `cmap.job.payload.usage` token/call counters, which B4 exposes as `spend_today` on `GET /sources/health` (New York day); the spend ceiling must build on those counters and put its pause banner on B4's panel (that panel is the "visible fallback" surface). B3's live gate (`brain-quality.yml`, nightly 5:17 AM EST + after `Verify live version` + dispatch) compares against the last `accepted` run and marks acceptance through the app's own `POST /eval/runs/{id}/accept` (`admin_or_service`); a job that errored fails the gate even while A2 re-queues it (#545). **Gap recorded:** `Verify live version` has web-only path filters, so brain-only deploys do not trigger the gate — nightly and dispatch cover them; adding "Brain image" to the `workflow_run` list would gate every main push (including docs-only) at eval cost, deferred to H5's spend cap. For **F2**: B2's `judge_decline()` + `B/prompts/decline_check.md` (grader seat, bounded retries, never auto-accept) is the pattern for reply judging. Playwright: `map.spec.ts` now ends with the B1 approve-flow and B4 health-panel tests (append after them); map runs need a throwaway `BRAIN_E2E_DATABASE_URL`, never the brain pytest database. Office fixture builders must pin zip header fields (`build_office_fixtures.py:zip_package` pins `create_system`). Eval questions live on the site (owner ruling 2026-11-05 — the draft-.md path is retired); seeds load via `python -m brain.eval.run --seed`.

**Business acceptance:** after Phase A8, after C5, and after I4, Albert (and Ilona if he wishes) looks at the site. No other step needs a human.

---

# Part 1 — Why

## 1. The ultimate goal

Albert owns POP Creations / Spruce Line, a high-volume home decor company. He wants **an all-knowing business consultant**: something that has read every document, listened to every recorded conversation and interviewed every employee, and therefore understands how the company actually runs — and can tell him what is broken, why, what to change, and whether the change worked.

In his words (2026-11-11) the Oracle must:

1. learn from the company's documentation;
2. learn from interviewing employees;
3. know what and how to interview employees to fill knowledge gaps;
4. segment what it knows into **data domains**, "so as not to put unrelated data into its context window for a question about one part/function of the company";
5. see and establish the relationships between all the processes and actions in the company;
6. see the big picture of how the company operates and the internal business flow;
7. do "anything else you think an omniscient ai business consultant should do".

Today it does not. An audit on 2026-11-11 found the Oracle scores **0.38 out of 1** on its own test (target 0.6), ignores its domains when answering, cannot tell an old procedure from a new one, only links facts that sit in the same paragraph, generates interview questions by accident rather than by design, and forgets every correction.

**When this plan is done:** Albert asks "how does an order get from a customer PO to cash, and where does it get stuck?" and receives an ordered, step-by-step flow with the owner of each step, the hand-offs between departments, the three slowest points with numbers, the people the company cannot afford to lose, and what was tried before — every sentence backed by a source he can click, with stale or disputed facts marked as such. Each Monday the Oracle tells him, unasked, what changed, what contradicts what, and what it still does not know and whom it is asking.

**If a step in this plan conflicts with that goal, the goal wins. Stop, write the conflict into STATUS, and propose the correction.** Rules inherited from the previous plan still bind: never add a gate that stops a document from being read; never add an approval queue for individual facts; never add a permission system beyond login and an admin flag.

## 2. What this application is

- **The Oracle** — POP Creations' company adviser. Employees use it on the web and on Microsoft Teams.
- Repository: `u2giants/theoracle` (PUBLIC — no private data, no LAN addresses in the repo), default branch `main`, pnpm + turbo monorepo.
- `apps/brain/` — Python 3.12 service (FastAPI + one background worker thread in the same process, `B/__main__.py:21`). Owns reading, extraction, the map, answering, interviews, recommendations. Deployed as Coolify service `oracle-brain` (app uuid `uge6pfm4qapktivto4981mtg`) at `https://oracle-brain.designflow.app`; image built by `.github/workflows/brain-image.yml` to GHCR.
- `apps/web/` — Next.js app on Vercel at `https://oracle.designflow.app`. Supabase Auth login. Company Map pages under `W/map/` (`ask`, `community`, `entity`, `eval`, `questions`, `recommendations`, `review`, `source`, `sources`). It renders and proxies to the brain; no reasoning lives here.
- Teams bot: `W/api/teams/bot/messages/route.ts` (inbound) and `W/api/teams/bot/proactive/route.ts` (outbound).
- Data: the Oracle's **own** Supabase Postgres project, schema `cmap` (NOT the shared company database; the `shared-db` rules do not apply to `cmap`). Schema files are `B/sql/001…015_*.sql`, applied idempotently at start-up by `B/migrate.py` (wired into `B/__main__.py` by #528). FalkorDB graph `company` is a projection rebuilt from Postgres (`B/graph/project.py`).
- The pipeline, in order, each a job kind in table `cmap.job` run by `B/worker.py`: `read_source` (`B/read/pipeline.py`) → flat extraction of mentions (`B/extract/flat.py`) → relationships (`B/extract/relations.py`) → entity resolution (`B/resolve/resolve.py`) → graph projection (`B/graph/project.py`) → clustering and summaries (`B/graph/communities.py`) → recommendations (`B/recommend/recommend.py`). Answers: `B/answer/answer.py`. Interviews: `B/interview/*.py`. Self-test: `B/eval/run.py`.
- Vocabulary: a **source** is one document/transcript/interview answer; a **chunk** (called "passage" in owner-facing text) is ~400 tokens of a source; an **entity** is one real-world thing (16 types: Person, Role, Department, Process, Step, Decision, Rule, Exception, Issue, System, Artifact, Metric, Product, Customer, Vendor, Licensor); a **relation** is a typed link between two entities with a verbatim quote; a **community** is a cluster of entities with a written report, at level 0 (small), 1 (area), 2 (whole company); `graph_version` increments on each projection.
- Models: reached through OpenRouter; ids come only from environment/seat settings (`B/seats.py`, `B/config.py`). Seats: chat, frontier (heavy work), flat, vision, embed, eval (grader).

## 3. What triggered this work

Albert asked on 2026-11-11 for an audit of the code against the seven goals in §1, then: "write up a plan to fix everything and also think of improvements that i didn't even think of and include those". The audit is `docs/audit-2026-11-11-oracle-goals.md`. Live state that day: 57 sources (12 documents, 45 transcripts), 2,070 entities of which 1,790 appear in only one source, 2,311 relations, 10,074 dismissed interview questions, interview bot off, latest self-test 0.38.

## 4. Scope

### In
Everything in the STATUS table: repairs for every confirmed audit defect (Phases A, D, E, F, G, H), a release-blocking quality bar (B), real data domains (C), and the consultant capabilities Albert did not list (I, J).

### NOT in this plan
- Loading more of the company's documents. The owner has said the document corpus is complete; meeting transcripts grow through `plan_meeting_triage_pipeline.md`. Step A8 re-reads what is already there.
- The Chinese-language work (`plan_chinese_integration.md`) and the licensing-routing bug it tracks on issue #474 — except where F3 replaces the routing rule wholesale; coordinate through that plan's STATUS.
- Switching the interview bot back on: issue #518 owns that. This plan makes it safe; it does not flip the switch.
- Any permission model beyond login + admin flag. No per-function access control.
- Writing to any business system. Phase J reads numbers; it never writes to DesignFlow, the ERP or anything else.
- Live speaking in meetings; fine-tuning; mobile layout.
- Replacing FalkorDB, Supabase, Coolify, Vercel or the single-service shape.
- Deleting legacy `packages/*` web code not touched by a step.

---

# Part 2 — What we already know

## 5. Current state of the code (commit `3c7e2e39`, 2026-11-11)

Everything below is committed, on `main`, and deployed. Nothing in this plan is started.

**Works and must be preserved:** verbatim-quote validation on every mention/relation (`B/extract/relations.py:220,247-250`) and on local answers (`B/answer/answer.py:290-315`); stance tracking (policy/practice/report/inference) on every relation; interview answers enter the normal pipeline as speaker-attributed transcripts (`B/interview/inbound.py:334-343`, `B/interview/intake.py:180-190`); interview pacing guards (`B/interview/tick.py`: weekly cap, quiet hours, kill switch re-read per question at `:343`, vetted-only sending at `:337`); question vetting (`B/graph/communities.py:665-739`); recommendation guardrails (`B/recommend/recommend.py:76-79,109-147`); orphan-job requeue (`B/worker.py:102-147`); Chinese handling (`B/lang.py`, `B/translate.py`, `B/text_util.py`).

**Broken or missing**, by step that fixes it:

| Where | What is wrong | Step |
|---|---|---|
| `B/answer/answer.py:725-731` `_load_reports` | No `graph_version` filter; live DB holds 1,178 level-1 and 23 level-2 reports, current version has 32 and 1; all are fed to global answers | A1 |
| `B/graph/communities.py:608-611` | Communities only ever inserted, never pruned | A1 |
| `B/extract/flat.py:435-451,650-655` | One failed model call aborts the whole source's extraction; nothing written | A2 |
| `B/read/pipeline.py:132-135` | `read_state='read'` set before extraction; zero-chunk source also marked read | A2, A7 |
| `B/worker.py:87-99` | Failed job stays failed; `attempts` never read. 7 failed jobs live | A2 |
| `B/extract/relations.py:599-601`, `B/resolve/resolve.py:196,816` | A failed relations/resolve job stops the chain until another upload | A2 |
| `B/read/chunk.py:60-70` | Window edges snap only to a literal space; drops text (2,022 Chinese chars in → 1,083 out; 18 of 400 CSV rows whole in no chunk) | A3 |
| `B/read/office.py:79-87,112` | Rejects any package with `embeddings/` or an external relationship (charts, hyperlinks); rejects XML > 100,000 nodes | A4 |
| `B/read/office.py:167-243,282`, `B/read/detect.py:43` | Empty cells skipped (columns shift), headers not repeated, dates as serial numbers, CSV as plain text, DOCX tables flattened, DOCX images unread | A5 |
| `B/read/pdf.py:54` | Page with ≥200 chars of text never gets vision | A6 |
| `B/read/vision.py:162-179` | `unreadable_regions` discarded | A6 |
| `B/read/transcript.py:177` | "We agreed at 3:15 to ship" parsed as speaker "We agreed at 3" | A7 |
| `.github/workflows/brain-ci.yml:64-72`, `T/test_eval_fixture.py:165-177` | Only gate replays recorded answers; live quality can halve and merge green | B3 |
| `B/eval/run.py:108-113,287-296` | Grader scores covered points only; expected sources recorded but not scored; failed answer silently scores 0 | B2 |
| `B/answer/answer.py:410-451,537-545,674-682` | Local retrieval: top-8 entities no floor, 2-hop by global source count, 10 corpus-wide chunks + 20 neighbourhood chunks; no domain filter | C4 |
| `B/answer/answer.py:418-423` | Alias seeding is an unbounded substring match | C4 |
| `B/answer/answer.py:54-59,610-613,693` | No hard token budget in local mode | C4 |
| `B/answer/answer.py:228-256,862-872` | Routing falls back to running both modes and concatenating | C4 |
| `B/graph/communities.py:183-185,973,1047,1098` | One cluster per entity; cluster identity = exact entity set, so ids and titles churn | C3 |
| `cmap.source.department_hint` | Stored (37 of 57 sources) and used nowhere | C2 |
| `cmap.source.effective_date` | Stored, NULL on all 57 sources, used nowhere (`B/api/sources.py:376,434`, `B/interview/inbound.py:341`) | D1 |
| `B/api/sources.py:224-227` | Identity is byte hash only; a revised document is a second source | D2 |
| `B/extract/relations.py:74` + `B/prompts/relations.md:33` | CONTRADICTS only inside one chunk | D3 |
| `B/extract/relations.py:54,247-250,393`; `B/read/pdf.py:61`; `B/read/transcript.py:252-281` | Relations need both ends and quote in one chunk; chunks break at pages and speaker turns | E1 |
| `B/extract/relations.py:61-76` | 14 types; no trigger, input, approval, ownership kinds; no step order | E2, E3 |
| `B/graph/communities.py:489-494,514-523` | Cross-cluster edges excluded from every report; edge cap ranks by weight only | E4 |
| `B/graph/query.py:59` | `path/neighbors/by_type` exist, called by nothing | E5, I5 |
| `B/graph/communities.py:766`, `B/prompts/community_report.md:13` | Only source of interview questions: ≤3 free-form per report | F1 |
| `B/graph/communities.py:757-760` | Question dedupe is exact text within one run | F1 |
| `B/interview/inbound.py:344-349`, `B/prompts/reply_check.md` | Any partly-answering reply closes the question | F2 |
| `B/interview/inbound.py:318-331` | "I don't know, ask X" discards the referral | F3 |
| `B/interview/tick.py:190-225`; `B/directory_sync.py:8-9` | Routing by exact name / self-reported department; directory sync never writes department | F3 |
| `B/interview/tick.py:48,235` vs `B/interview/inbound.py:33,303` | 3-day free window vs 7-day match window → late reply filed on wrong question | F4 |
| `B/interview/inbound.py:237-238`; `W/api/teams/bot/proactive/route.ts:140,159` | Conversation reference stored for any chat incl. group/meeting | F4 |
| `B/interview/inbound.py:262-273`, `B/interview/profile.py:59` | Any ≤25-word message becomes the profile | F4 |
| `B/interview/inbound.py:63-64,84-87` | Reply-check model down → any message saved as the answer | F4 |
| `B/api/flags.py`, `B/sql/010_review_flags.sql` | Flags are notes; nothing reads them | G1 |
| `B/resolve/resolve.py:307,334-358,601-607,640-651` | No entity-to-entity merge pass; first-name auto-assign is permanent; generic names merge corpus-wide | G2, G3 |
| `B/answer/answer.py:276-278,333-368` | Uncited sentences pass unmarked; global citations accept any source id | H1 |
| `W/api/teams/bot/messages/route.ts:13-17,128-129` | Teams bot cannot answer questions | H3 |
| `W/map/_components/ask-client.tsx:127-133`, `B/api/answer.py:5` | Chat memory is 6 turns in the browser; nothing logged | H4 |
| `B/llm.py:84-87` | Raises on any non-200; no backoff, no second provider | H5 |
| `B/api/recommend.py:28,87,105` | Recommendation = card + status; no owner, result, date | I3 |

## 6. Key findings and root causes

1. **The low score has at least three independent causes**, in likely order of size: (a) stale-summary pollution (A1) — confirmed in live data; (b) silent content loss while reading (A2–A7); (c) too little joining across sources — 86% of entities appear in one source, partly because the corpus is small and partly because resolution never revisits existing entities (G3). Fix (a) and (b) and re-measure **before** building anything else; that is why A8 and B exist as a gate.
2. **Domains exist but are decorative.** Clustering is Leiden over an undirected graph (`B/graph/communities.py:44-49,119-128`). Clusters are not business functions, each entity is in exactly one, and answering never consults them. The owner's goal 4 needs a *curated* list of business functions that sources, passages and entities are assigned to, with multi-membership, and retrieval that filters on it.
3. **The "big picture" is built bottom-up from single-paragraph facts.** Nothing ever reads a whole procedure document as a procedure. Ordered flows cannot emerge from paragraph-level pairs; they need a document-level pass (E2).
4. **Interview questions are a by-product of report writing**, which is why 10,074 were dismissed. Gaps must be computed from the map's structure (F1), not suggested by a model writing prose.
5. **The system has no memory of being corrected or of time.** Both are schema-level gaps, not prompt problems.
6. **Citations validate existence, not support.** A second, cheap check per sentence is required (H1).
7. **The automated test protects plumbing, not quality** (`plan_oracle_company_map.md:597` says so itself).

## 7. Approaches considered and REJECTED

| Rejected | Why |
|---|---|
| Replace the graph approach with plain "search the documents and paste them in" | That was Oracle 1; it never joined the same thing across documents. The graph stays. |
| Keep automatic clusters as the domains and merely filter retrieval by cluster | Clusters reshuffle on every rebuild, are not business functions, and allow one membership. The owner asked for domains by "part/function of the company". Curated functions are the domain; clusters become sub-topics inside them (C3). |
| Fully manual taxonomy with human tagging of every source | Violates "no approval queue"; nobody will do it. Functions are curated once (~12 rows); assignment is automatic with admin override (C2). |
| A separate database/graph per function | Kills the cross-function view, which is the product. One graph, function is an attribute and a filter. |
| Fix the score by swapping to a stronger model | Model bake-offs were run twice (`HANDOFF.d/2026-10-30…bakeoff`, `…2026-11-02…round2`); structure, not model strength, is the limit. Do not start another bake-off under this plan. |
| Lower the pass bar or cut hard questions | The bar is the owner's protection. |
| Whole-document extraction by pasting entire files into one prompt | Oracle 2 did this and could not scale (`plan_oracle_company_map.md` §6.2). E2 uses the already-extracted steps of one source, not raw text of all sources. |
| Per-fact human approval before knowledge is used | Explicitly forbidden by the owner (2026-10-27). Corrections (G) are after-the-fact and optional. |
| Removing the weekly interview cap to learn faster | Tried 2026-11-10; flooded the company with messages ("it just sent me 30 messages in a row"). The cap stays. F2's multi-turn interview counts as one contact. |
| Making the Oracle write back to business systems | Out of scope and unsafe; read-only numbers only. |
| Delete-and-rebuild `cmap` to clear stale rows | Loses interview answers' linkage and review history. A1 prunes precisely; A8 re-reads in place. |
| Re-using Oracle 1's claim/gap tables for gap detection | Retired system; `cmap` is the only live model. |

## 8. Design decisions

**Locked (do not relitigate):**
- (Albert, 2026-10-27) No atomic-claim approval; no permissions beyond login + admin; FalkorDB stays; "none of the data going into this will be secret".
- (Albert, 2026-10-30) Chat seat is the Claude model; heavy work is a cheaper non-Claude model; grader seat is fixed so scores stay comparable. Model ids live only in env/seat settings — never in code (memory rule `no-hardcoded-model-names-in-adapters`).
- (Albert, 2026-11-10) Weekly interview quota stays on. Eval questions are approved on the site's eval page, never as chat files.
- (Albert, 2026-11-11) Domains are by part/function of the company and exist to keep unrelated material out of the context window.
- (This plan, 2026-11-11) Postgres is the source of truth; every new concept is a `cmap` table/column added by a new idempotent `B/sql/0NN_*.sql` file (next free number is 019); FalkorDB is always re-derivable.
- (This plan) Every new model call goes through `B/llm.py` and a seat from `B/seats.py`; every new prompt is a file in `B/prompts/` and is covered by `T/test_prompts.py`.
- (This plan) Human corrections always win over extraction and survive every rebuild (G1).
- (This plan) Pass bar: mean ≥ 0.6 on the owner-approved set with zero unsupported sentences counted as passes; release gate fails on a drop of more than 0.05 from the last accepted run.

**Open (implementer's judgment, criteria given in the step):** thresholds marked "tune" in steps; UI layout details within the stated content; whether E1 uses a sliding window of 2 or 3 passages (pick by measured relation yield on the fixture); order of phases C–J where "needs" allows.

---

# Part 3 — How to build it

## 9. The plan

General rules for every step: when a phase finishes, its implementer re-reads every downstream phase to the end of this plan and records any drift in the Drift log under STATUS before starting the next phase; branch from `main`, one PR per step (small steps in one phase may share a PR), `uv run ruff check . && uv run pytest` green in `apps/brain`, Playwright map test green when `W/map/**` changes, merge, confirm the deployed version (`.github/workflows/verify-live-version.yml`), then run the step's **live gate** against production read-only and save the output under `docs/verification/repair/<step>.md`. Update STATUS in the same PR.

### Phase A — stop the bleeding

**A1 — Company-wide answers read only the current map.**
Change `_load_reports` (`B/answer/answer.py:725`) to select only rows whose `graph_version` equals the current version; use the same helper the map API uses (`B/api/map.py:42,172`) — extract it to `B/graph/version.py::current_graph_version()` and call it from `answer.py`, `api/map.py`, `recommend/recommend.py:208-214`. Because reports are reused across versions by entity-set key (`communities.py:973-1000`), first confirm how a reused report's `graph_version` is stamped; if reuse leaves the old version number, stamp reused rows with the new version in the same transaction (this is the intended behaviour: "current" = every report the current build selected). Add pruning at the end of a successful community build: delete `cmap.community` rows whose `graph_version` is older than the newest **two** versions and that are not referenced by `cmap.recommendation` or `cmap.review_flag` (check both tables' foreign keys first; keep referenced rows).
*Gate:* new `T/test_answer.py::test_global_ignores_superseded_reports` (seed two versions with contradictory company reports; answer must cite only the newer). `T/test_communities.py::test_old_versions_pruned`. Live: `select level, count(*) from cmap.community group by 1` shows roughly one build's worth; re-run the eval and record the score.

**A2 — Failed reading is retried and never shows as "read".**
(a) `B/extract/flat.py`: wrap the per-chunk model call (`:435-451`) in the same bounded retry used by `B/embed.py` (3 attempts, exponential backoff); on final failure record the chunk as failed in `cmap.extraction` (add column `error text`) and **continue** with the remaining chunks; write successful chunks as they complete instead of after the loop (`:650-655`).
(b) New `read_state` values: `reading`, `extracting`, `read`, `partial`, `failed` (new SQL file altering the check constraint). `read/pipeline.py:135` sets `extracting`; the end of relations for that source sets `read`, or `partial` when any chunk failed, with `read_error` naming the count. A source with zero chunks is `failed` with error "no readable content".
(c) `B/worker.py:87-99`: on failure, if `attempts < 3` set state back to `queued` with `run_after = now() + (5 min × 4^attempts)`; only then `failed`.
(d) Chain healing: a small `ensure_chain` job, enqueued hourly by the existing tick, that enqueues relations/resolve/project/communities for any source or graph state left behind (sources in `extracting` with no queued/running job; unresolved mentions with no resolve job; mentions newer than the last projection).
(e) Sources page (`W/map/sources`) shows the state and a "retry" button for admin (calls existing re-read endpoint).
*Gate:* `T/test_flat.py::test_one_bad_chunk_does_not_lose_the_source`, `T/test_worker_orphans.py::test_failed_job_retried_with_backoff`, `T/test_chain_debounce.py::test_stalled_chain_is_healed`. Live: `select state, count(*) from cmap.job group by 1` shows 0 failed after requeue; no source in `read` with zero mentions.

**A3 — Passage splitter loses no text.**
Rewrite the windowing in `B/read/chunk.py:60-70` so boundaries are chosen from, in order: paragraph break, line break, sentence end (use the CJK-aware splitter in `B/text_util.py`), whitespace, and finally a hard cut at the token limit — never skipping text. Invariant: concatenating chunks with overlaps removed reproduces the input exactly.
*Gate:* `T/test_chunk_cjk.py::test_no_text_lost_property` (property test over English, Chinese-with-sparse-spaces, and a 400-row CSV: every input line appears whole in at least one chunk unless the line itself exceeds the limit).

**A4 — Office files with links/charts are read.**
`B/read/office.py:79-87`: stop rejecting the package. Skip (do not parse) `embeddings/` members and ignore external relationships — never fetch them. Keep the zip-bomb, path-traversal and size checks. Replace the 100,000-node rejection (`:112`) with streaming parse (`iterparse`) capped by total bytes, not node count. Raise the expanded-size cap (`:22`) to match the upload cap (`B/api/sources.py:40`) or lower the upload cap for Office types so the two agree; pick the smaller if memory on the Coolify host is the constraint.
*Gate:* fixtures `T/fixtures/with_hyperlink.docx`, `with_chart.pptx`, `large_sheet.xlsx` (40k cells) each read to >0 chunks; `T/test_read.py::test_external_relationship_never_fetched` (assert no network call).

**A5 — Spreadsheets keep rows, columns, headers.**
XLSX and CSV: detect the header row (first non-empty row); emit each chunk as a small Markdown table that **repeats the header** and keeps empty cells; never split inside a row; convert date-formatted cells from serial numbers to ISO dates using the cell style. Route `.csv`/`.tsv` to this reader in `B/read/detect.py:43`. DOCX: render tables as Markdown tables in place (`office.py:167-200`); send embedded images through the existing vision reader (`B/read/vision.py`) and insert the result at the image's position.
*Gate:* `T/test_read.py::test_xlsx_header_repeated_and_columns_aligned`, `::test_csv_rows_never_split`, `::test_xlsx_dates_are_iso`, `::test_docx_table_and_image_read`.

**A6 — Diagrams on text pages are read.**
`B/read/pdf.py:54`: send a page to vision when it has little text **or** when it contains images/vector drawings covering more than ~15% of the page area (pypdfium2 object inspection; tune). Append the vision description to the page's text rather than replacing it. Persist `unreadable_regions` (`vision.py:162-179`) in a new `cmap.source.read_notes jsonb` and show them on the source page so missing content is visible.
*Gate:* `T/test_read.py::test_mixed_page_text_and_diagram_both_read`; `::test_unreadable_regions_recorded`.

**A7 — Small reading bugs.**
Speaker pattern (`B/read/transcript.py:177`): require a speaker label to be at most 5 words, contain no digits-colon-digits, and be followed by colon+space at line start; add the failing sentence as a test. PPTX pictures: send the true image type and make one failed picture a noted gap, not a failed deck (`office.py:338`). `worker.py:179-182`: if `finish_job` fails, retry it; the orphan sweep covers the rest. Deleting an interview-answer source: add `ON DELETE SET NULL` to `cmap.open_question.answer_source_id` (`B/sql/001_cmap.sql:124`) via a new SQL file. Source deletion and re-read also remove entities left with zero mentions and aliases whose only evidence came from that source (`B/api/sources.py:472-487`, `B/read/pipeline.py:71`, `B/graph/project.py:109`).
*Gate:* one named test per bullet in `T/test_read.py`, `T/test_transcript_cjk.py`, `T/test_intake.py::test_delete_answer_source`, `T/test_project.py::test_zero_mention_entities_not_projected`.

**A8 — Re-read everything and rebuild; baseline.**
Add an admin action `POST /sources/reread-all` (queues `read_source` for every source, throttled to the per-job call cap). Guard against duplicated knowledge: the done-check keys on prompt hash (`flat.py:562`, `relations.py:474`) and inserts are plain — change both to delete that chunk's previous rows for the same extraction kind before inserting, inside one transaction. Run it in production (this is a normal application action through the deployed service, not a manual database command), wait for the chain to finish, run the eval twice.
*Gate:* `T/test_flat.py::test_prompt_change_replaces_not_duplicates`. Live: `docs/verification/repair/A8-baseline.md` records source/chunk/entity/relation counts before and after, and both eval scores. **Cut point: start a fresh session after A8.** If the mean is already ≥ 0.6, still do Phase B, then continue.

### Phase B — a quality bar that blocks releases

**B1 — Owner-approved question set.** The eval page (`W/map/eval`) already lists drafts. Add per-question "approve / edit / retire" for admin, an `approved_at` column on `cmap.eval_question`, and a `function` column (filled in C1). Generate drafts up to 30 questions: at least two per business function, five cross-function, five "the documents do not say" questions whose correct answer is an admission of ignorance. Only approved questions count toward the bar. *Gate:* Playwright `apps/web/tests/map.spec.ts` approve-flow; owner approves on the site (the one human action in this phase; drafts with a recommendation are ready for him).

**B2 — Scoring counts sources and unsupported sentences.** `B/eval/run.py`: score = 0.6 × covered expected points + 0.2 × expected sources actually cited (already recorded at `:294-296`) + 0.2 × share of sentences supported (from H1's check; until H1 lands use the existing citation validity). A failed answer is reported as `error`, shown separately, and fails the run rather than silently averaging to 0 (`:287-289`). "Do not know" questions score 1 only when the answer declines. Keep the previous formula's number alongside for continuity for three runs. *Gate:* `T/test_eval_fixture.py::test_score_components`, `::test_errors_fail_run`, `::test_abstention_question`.

**B3 — Live quality gate.** New workflow `.github/workflows/brain-quality.yml`: triggered after `verify-live-version` succeeds for a brain deploy, and nightly; calls the existing eval endpoint with the shared token (secret already used by the web proxy; name in §12), waits, compares to the last accepted run stored in `cmap.eval_run` (add `accepted bool`). Fails — and opens/updates one issue labelled `quality-regression` — when mean drops > 0.05 or any error occurs. This is advisory to merging (owner ruling 2026-10-30: only data-damage/secret checks may block merges) but it is the trigger for an immediate fix. *Gate:* a deliberately broken prompt on a preview/local run makes the script exit non-zero (`T/test_eval_fixture.py::test_gate_detects_drop`); first nightly run id recorded in STATUS.

**B4 — Pipeline health panel.** On `W/map/sources` (admin): sources by state, failed/retrying jobs with error text, chunks with failed extraction, last successful build time and version, spend today. Backed by one new endpoint in `B/api/sources.py`. *Gate:* Playwright assertion that a seeded failed job appears.

### Phase C — business functions as real data domains

**C1 — Curated function list.** New table `cmap.function(id, key, name, description, aliases text[], parent_id, sort, active)`. Seed from evidence: propose the list by clustering existing Department entities and `department_hint` values, then present on a new admin page `W/map/functions` where the owner can rename, merge, add, retire. Starting proposal (owner edits freely; see §13 Q1): Sales & Customer Accounts, Licensing, Product Design & Development, Sourcing & Vendor Management, Sampling, Production & Quality, Logistics & Shipping, Compliance & Testing, Finance & Accounting, IT & Systems, HR & Administration, China Office Operations, Executive/Company-wide. *Gate:* `T/test_functions.py::test_seed_and_edit_roundtrip`; page renders.

**C2 — Assignment.** New tables `cmap.source_function`, `cmap.chunk_function`, `cmap.entity_function` (each: id pair, `weight real`, `origin` in `auto|admin`). Assignment job (after resolve): each chunk is classified against the function list (model call on the flat seat, multi-label, returns 0–3 functions with weights; `department_hint` and the speaker's profile department are strong priors); a source's functions are the weighted union of its chunks; an entity's functions are the weighted union of the chunks that mention it, so a hand-off step naturally belongs to two functions. `origin='admin'` rows are never overwritten (admin can set them on the source and entity pages). Directory sync (`B/directory_sync.py:8-9`) starts writing each employee's department/title from the DesignFlow directory when present, mapped to a function. *Gate:* `T/test_functions.py::test_handoff_entity_in_two_functions`, `::test_admin_assignment_survives_rerun`, `::test_hint_is_prior_not_override`. Live: every source has ≥1 function; a table of counts per function saved to verification.

**C3 — Clusters inside functions; stable identities.** In `B/graph/communities.py`: level 1 becomes **one report per function** (id = the function's id → stable forever; title = function name); level 0 remains Leiden clusters but computed per function over the entities assigned to it (an entity may appear in several); level 2 remains the company report. Stable ids for level 0: match each new cluster to the previous build's cluster with the highest Jaccard overlap ≥ 0.5 and reuse its id and title; otherwise new. Regenerate a report when its **content hash** (sorted entity ids + relation ids + their updated-at) changes, not only when the entity set changes (fixes audit C2). A failed child report marks its parents `incomplete` so they are regenerated next run rather than cached without it (fixes `:1035-1037`). Replace silent truncation at 12,000 tokens (`:50,80-87`) with map-reduce: summarise in batches, then combine. Clustering edge weights: exclude MENTIONS and CONTRADICTS, weight sequence/hand-off kinds higher (`:115-119`). *Gate:* `T/test_communities.py::test_function_report_id_stable_across_rebuilds`, `::test_cluster_id_reused_on_small_change`, `::test_new_relation_regenerates_report`, `::test_failed_child_does_not_poison_parent`, `::test_company_input_never_truncated`.

**C4 — Function-scoped answering with a hard budget.** In `B/answer/answer.py`:
1. Route first: classify the question to 0–3 functions (same classifier as C2; conversation history is included so follow-ups inherit scope — fixes `:671`). No function ⇒ company-wide mode.
2. Scoped mode: candidate entities and chunks are restricted to those assigned to the routed functions (`weight ≥` tune 0.2) **plus** entities directly linked by a hand-off/sequence relation across the boundary (one hop only). Apply a similarity floor (tune; start 0.25 cosine) so "nearest of nothing" is not used. Replace 2-hop-by-popularity (`:447-451`) with expansion ranked by similarity to the question × relation-kind weight. Alias seeding (`:418-423`) uses word-boundary matching and ignores aliases under 3 characters.
3. Company-wide mode: company report + the function reports, selecting function reports by relevance always (not only above 60,000 tokens, `:823-828`).
4. Hard budget: assemble context by priority (function report → ordered flow from E2 when present → relations → quotes → passages) until a fixed token ceiling per seat (config `BRAIN_ANSWER_CONTEXT_TOKENS`, default 12,000); never exceed it; no dependency on ScaleDown for correctness.
5. Remove "run both and concatenate" (`:228-256,862-872`): when routing confidence is low, run scoped mode on the top function plus the company report in one prompt.
6. Return, with every answer, the functions consulted and the token count; show them under the answer on `W/map/ask` so the owner can see nothing unrelated was loaded.
*Gate:* `T/test_answer.py::test_scoped_answer_excludes_other_functions` (seed Licensing and Logistics; a Licensing question's context contains zero Logistics-only chunks), `::test_handoff_neighbour_included`, `::test_similarity_floor_returns_dont_know`, `::test_context_never_exceeds_budget`, `::test_short_alias_not_substring_matched`, `::test_followup_inherits_function`. Live: eval re-run; record mean and average context tokens before/after.

**C5 — Map page by function.** `W/map/page.tsx`: left = company report; centre = one card per function (coverage score from F6 when available, counts, top issues); function page = its report, its processes as ordered flows (E5), its sub-topics, its people, its open gaps. *Gate:* Playwright path company → function → process → source. **Owner look #2. Cut point.**

### Phase D — time, versions, contradictions

**D1 — Every source has a date.** Resolve `effective_date` at read time, first hit wins: admin-entered → meeting start time (transcripts; Teams/Recall metadata) → interview answer timestamp → date found in the document's own header/footer/revision table (model call on first and last page) → file metadata dates → upload time. Store `date_origin`. Backfill all existing sources. Bulk/folder/Teams imports stop writing NULL (`B/api/sources.py:376,434`, `B/interview/inbound.py:341`). Relations and mentions inherit the date through their source (view `cmap.relation_dated`). *Gate:* `T/test_dates.py` one test per origin; live: zero NULL dates.

**D2 — Supersession.** New table `cmap.source_version(source_id, supersedes_source_id, origin, decided_at)`. Detect at upload: same normalised title, or embedding similarity of the first 3 chunks ≥ 0.9 with a different hash ⇒ propose "newer version of X" (auto-accept when the title matches and the date is later; otherwise show on the sources page for one-click confirm). Effects: relations and mentions whose only sources are superseded get `status='superseded'` (new column on `cmap.relation`; computed, not hand-set), are excluded from projection weights, reports and answers by default, and remain viewable as history ("until March 2025 the rule was…"). *Gate:* `T/test_versions.py::test_revised_policy_supersedes_old_rule`, `::test_fact_also_in_live_source_stays_current`, `::test_history_question_can_still_reach_old_version`.

**D3 — Contradictions across sources.** New table `cmap.contradiction(id, relation_a, relation_b, kind, summary, status open|explained|resolved, resolution, resolved_by)`. Job after resolve: for each entity pair/entity with relations from ≥2 sources of conflict-prone kinds (OWNS/RESPONSIBLE_FOR, PRECEDES, APPROVES, Rule/Metric statements, policy-vs-practice stance pairs), a model call on the frontier seat compares the quoted statements and classifies: same / refinement / changed-over-time (dates differ → not a conflict, feed D2) / policy-vs-practice gap / true contradiction. Policy-vs-practice gaps and true contradictions are stored, shown on a new `W/map/contradictions` page and on both entities, included in reports and answers ("sources disagree: …"), and each generates a gap for F1 addressed to the function's most relevant role. An interview answer that contradicts a document triggers the same path immediately. Add a PRECEDES cycle check. *Gate:* `T/test_contradictions.py::test_two_owners_flagged`, `::test_date_change_is_not_contradiction`, `::test_policy_vs_practice_recorded`, `::test_interview_answer_contradicting_doc_creates_gap`, `::test_precedes_cycle_flagged`.

**D4 — Ageing and re-confirmation.** Each entity/relation gets `last_confirmed` = newest source date supporting it. Facts in fast-changing kinds (ownership, steps, systems, contacts) older than a per-kind horizon (config; start 18 months) are marked "may be out of date" in answers and produce low-priority "is this still true?" gaps (F1), batched so one person confirms several in one message. *Gate:* `T/test_dates.py::test_stale_fact_marked_and_gap_created`, `::test_confirmation_refreshes_date`.

### Phase E — relationships and ordered flows

**E1 — Relationships across neighbouring passages.** `B/extract/relations.py`: extract over a sliding window of the current passage plus the previous one or two **in full** (not two unquotable sentences, `:54,393`), allowing both ends and the quote to come from anywhere in the window; store the quote's true chunk id. Transcripts: build windows over consecutive speaker turns of the same exchange (question + reply), overlapping by one turn (`B/read/transcript.py:252-281`); PDF windows may span a page break (`B/read/pdf.py:61`). Deduplicate relations found in two windows. Count and store drop reasons (quote mismatch, unknown type, truncation) per source in `read_notes`; allow whitespace/quote-mark-normalised matching before declaring a mismatch (`:249`). *Gate:* `T/test_relations.py::test_question_and_answer_across_turns_linked`, `::test_relation_across_page_break`, `::test_no_duplicate_from_overlap`, `::test_drop_reasons_counted`. Live: relation count and relations-per-chunk before/after.

**E2 — Whole-document process pass.** New job `process_pass` per source classified as procedure/flowchart/process (labels already produced by flat classification), and per Process entity with steps from several sources. Input: the source's outline + its already-extracted Step/Decision/Role/System entities with quotes (not the raw full text). Output, stored in new tables `cmap.process_flow(id, process_entity_id, function_id, title, trigger, outcome, version, sources)` and `cmap.flow_step(flow_id, ordinal, step_entity_id, performer_entity_id, system_entity_id, input, output, decision, branch_of, typical_duration, evidence_relation_ids)`: an ordered, branching step list with performer, system, input, output, decision points, exceptions, trigger and end result. Every step must cite an existing relation or mention; steps the model cannot ground are dropped and logged. Diagram sources (vision output) get the same pass — a flowchart is the best evidence of order. Merge flows for the same process across sources, recording disagreements as D3 contradictions. *Gate:* `T/test_flows.py::test_fixture_approval_flow_ordered`, `::test_ungrounded_step_dropped`, `::test_two_sources_merged_with_conflict_recorded`, `::test_flowchart_image_yields_flow`.

**E3 — Missing relationship kinds.** Add to the ontology (`relations.py:61-76`, prompt `B/prompts/relations.md`, projection `B/graph/project.py`): TRIGGERS, REQUIRES_INPUT, APPROVES, OWNS (accountable owner, distinct from performer), ESCALATES_TO, MEASURED_BY, WAITS_FOR. Existing data is picked up by the A8-style re-read of relations only. *Gate:* `T/test_relations.py::test_new_types_extracted_and_projected`; `T/test_prompts.py` updated.

**E4 — Cross-function hand-offs reach the summaries.** `communities.py:489-494,514-523`: each level-0/function report also receives its **boundary edges** (relations to entities outside it), listed under "Hand-offs in / out"; the company report receives the full function-to-function hand-off matrix computed from relations and flows. Edge caps rank by kind weight × source count so a once-stated sequence is not cut before repeated generic links (`answer.py:516-517` as well). *Gate:* `T/test_communities.py::test_boundary_handoffs_in_function_report`, `::test_company_report_has_handoff_matrix`.

**E5 — Ordered flow view.** Endpoint `GET /flows`, `GET /flows/{id}`; page `W/map/flow/[id]` drawing the flow as swim-lanes by function/role with decision branches, each step clickable to its sources; an end-to-end "how the company runs" page chaining flows by their triggers/outcomes (customer order → design → licensing approval → sampling → production → shipping → invoice → cash), with unknown links shown as explicit gaps. Answering uses a flow as top-priority context when the question matches a process (C4 step 4). *Gate:* Playwright renders fixture flow in order; `T/test_answer.py::test_process_question_answers_in_step_order`. **Cut point.**

### Phase F — knowing what to ask, and asking well

**F1 — Systematic gap finder.** New module `B/gaps/find.py`, job after each build, writing to `cmap.open_question` with new columns `gap_kind`, `gap_key` (stable identity for dedupe), `function_id`, `target_role`, `value_score`. Computed checks, each a SQL/graph query, not a model guess:
- process with no owner; step with no performer; step with no successor that is not marked an end; decision with only one branch; hand-off with no receiving step;
- flow with a missing trigger or outcome; flows that should connect but do not (E5 gaps);
- entity with many mentions but no description, or seen in exactly one source while central (high degree);
- function with coverage below the median (F6); role or person in the directory with no knowledge attached;
- open contradictions (D3); stale facts (D4); exceptions with no handling; issues with no cause; systems with no owner;
- questions employees asked that the Oracle could not answer (H2).
A model call then **phrases** each gap as one plain question answerable in a sentence or two, in the recipient's language. Dedupe by `gap_key` against open, asked, answered **and dismissed** rows (a dismissed gap is never resurrected unless its evidence changed). Rank by `value_score` = centrality × how many other gaps it unblocks × function coverage deficit. Retire the free-form report questions (`communities.py:766`, prompt `community_report.md:13`) once F1's gate passes. A gap closes only when a rebuild shows the structural condition is gone — not when someone replied. *Gate:* `T/test_gaps.py` one test per check; `::test_dismissed_gap_not_resurrected`; `::test_gap_closes_only_when_filled`. Live: count of open gaps by kind; owner-visible on `W/map/questions`.

**F2 — Real multi-turn interviews.** Replace one-shot closing (`B/interview/inbound.py:344-349`): after each reply, a model call judges the reply against the gap's structural need and returns `filled | partial | vague | off-topic | dont-know | referral | clarifying-question`. `partial/vague` → one targeted follow-up (max 3 turns per gap, max ~6 messages per sitting; the whole sitting counts as **one** contact against the weekly cap). A sitting bundles up to 3 related gaps for the same person and function, opened with one sentence of context ("I'm mapping how samples get approved…"). `clarifying-question` → answer it from the map and continue (fixes the "type join" nonsense reply, `W/api/teams/bot/messages/route.ts:128-129`). Consecutive messages within the sitting are joined to the same answer. Close with a one-line thank-you stating what was learned. If the judging model is unavailable, hold the reply as `unjudged` and retry — never auto-accept (`inbound.py:63-64,84-87`). *Gate:* `T/test_interview.py::test_vague_answer_gets_followup`, `::test_sitting_counts_once_toward_cap`, `::test_clarifying_question_answered`, `::test_judge_down_holds_reply`, `::test_followups_capped`.

**F3 — Routing by role, referrals, re-asks.** Target selection order: (1) a person referred to by a previous answerer; (2) the performer/owner of the entity in the gap; (3) people whose role or function matches `target_role`/`function_id`, using directory department/title (C2) and aliases (fix exact-name-only match, `tick.py:204-208`); (4) the function's least-recently-asked member; (5) admin queue. Never route to the owner by "most mentioned" (the #474 bug) unless he is the performer. `dont-know` with a named person → store the referral and route there (`inbound.py:318-331`); record "X does not know about Y" so the same person is not asked that topic again. An unanswered question returns to `open` after 7 days and goes to the next candidate (max 3 people, then admin queue). Quiet hours use the employee's own time zone (directory office/locale; `tick.py:51-61`). Same-name employees are keyed by id (`tick.py:157`). Admin page shows the true next target (`B/api/interview.py:181-185`). *Gate:* `T/test_interview.py::test_referral_is_followed`, `::test_ignored_question_rerouted`, `::test_owner_not_default_target`, `::test_quiet_hours_per_timezone`, `::test_alias_match_for_suggested_person`.

**F4 — Reply matching and chat safety.** Store and use a conversation reference **only** when the Teams conversation type is personal (`inbound.py:237-238`; check in `W/api/teams/bot/messages/route.ts` and enforce again in `proactive/route.ts:140,159`). One window for both "free for a new question" and "reply matches" (`tick.py:48,235` vs `inbound.py:33,303`): a person is not sent a new question while one is pending; a late reply is matched by model judgement against the last 3 asked questions, not by recency. An open volunteered thread does not swallow a reply to a pending question (`inbound.py:274-296`). Profile capture accepts a message only if the judge says it describes a job/department (`inbound.py:262-273`, `profile.py:59`). "stop"-like phrases are recognised by meaning in both languages, and "resume" exists (`inbound.py:47,241`). *Gate:* `T/test_inbound_zh.py`/`T/test_interview.py`: `::test_group_chat_reference_never_stored`, `::test_late_reply_matched_to_right_question`, `::test_thanks_is_not_a_profile`, `::test_stop_variants_and_resume`.

**F5 — Role interview.** A structured sitting, started by admin for a person or automatically for a new directory entry (after 2 weeks in the directory) and for any role with zero knowledge: what you do each day/week, what you receive and from whom, what you hand off and to whom, the systems you use, what goes wrong most, what you wish were different, who covers for you. Spread over several sittings within the weekly cap; each answer feeds the pipeline and E2. *Gate:* `T/test_interview.py::test_role_interview_respects_cap_and_resumes`; fixture role ends with a populated flow.

**F6 — Coverage scorecard.** Per function and per process: number of sources, distinct people heard from, share of steps with performer/owner/order, open gaps, open contradictions, age of newest evidence → one 0–100 coverage score with the reasons. Page `W/map/coverage`; shown on function cards (C5). It is the visible answer to "what does the Oracle not know yet". *Gate:* `T/test_gaps.py::test_coverage_score_components`; Playwright render. **Cut point.**

### Phase G — corrections that stick

**G1 — Corrections.** New table `cmap.correction(id, target_kind entity|relation|flow_step|assignment|source, target_key, action reject|edit|confirm|merge|split|rename|reassign, payload jsonb, reason, by, at, active)`. `target_key` is content-based (e.g. relation = normalised source-entity key + type + target-entity key; entity = canonical key + type), not a row id, so it survives rebuilds. Applied at three points: resolution (merge/split/rename/never-merge pairs), projection (rejected relations excluded, edited ones replaced), and answer/report assembly (confirmed facts ranked first, rejected never shown). Existing `cmap.review_flag` rows gain an action and are migrated to corrections where they name a concrete target; "resolve" on the review page now requires choosing an action. *Gate:* `T/test_corrections.py::test_rejected_relation_gone_after_rebuild`, `::test_correction_survives_full_reread`, `::test_edit_replaces_fact_in_answers`.

**G2 — Merge, split, rename.** Admin actions on `W/map/entity/[id]`: merge into another entity, split (choose which mentions go where), rename, change type, add/remove alias, "these two are never the same". Each writes a correction and triggers a targeted re-projection. *Gate:* `T/test_resolve.py::test_admin_merge_survives_rerun`, `::test_never_merge_respected`, `::test_split_reassigns_mentions`; Playwright merge flow.

**G3 — Identity repair pass.** New periodic job in `B/resolve/`: candidate duplicate pairs across **existing** entities (same type or compatible types, name/alias/embedding similarity, shared neighbours) judged by the existing resolve judge, capped per run; cross-type candidates allowed for known confusions (Role↔Person title, System↔Artifact). Remove the permanent first-name auto-assign (`resolve.py:640-651`): a bare first name resolves by context (same source, same function, neighbours) and is re-judged when a second person with that name appears. Generic Step/Rule/Metric names are scoped to their process/function instead of merging company-wide (`:352-358`). People are anchored to the directory record when one matches. Fix the case-insensitive-match-then-refused path (`:601-602`). *Gate:* `T/test_resolve.py::test_second_john_triggers_rejudge`, `::test_generic_step_scoped_to_process`, `::test_existing_duplicates_merged`, `::test_person_anchored_to_directory`. Live: share of single-source entities before/after.

**G4 — Employee feedback.** Every answer (web and Teams) has "this is wrong / out of date / incomplete" with a free-text note. It creates a review item tied to the cited facts; three independent reports on the same fact, or one from that fact's owner/performer, auto-create a contradiction (D3) and a gap. *Gate:* `T/test_corrections.py::test_feedback_creates_review_item`, `::test_owner_feedback_creates_contradiction`.

### Phase H — trustworthy answers

**H1 — Every sentence supported or marked.** After drafting, split the answer into sentences; for each, a cheap model call (flat seat) checks whether the cited quote(s) support it: supported / partly / not. Unsupported sentences are rewritten once with the evidence, then removed or shown with "(unsupported — my inference)". Sentences with no citation at all are marked the same way (fix `answer.py:276-278`, matching the docstring at `:19-20`). Company-wide mode may cite only sources actually present in the prompt (`:333-359`) and shows the supporting quote, not the nearest chunk (`:360-368`). The supported share is returned and used by B2. *Gate:* `T/test_answer.py::test_unsupported_sentence_marked`, `::test_uncited_sentence_marked`, `::test_global_cannot_cite_unseen_source`.

**H2 — Honest "I don't know".** When routed retrieval finds nothing above the floor, or the support check removes most of the draft, answer plainly that the Oracle does not know yet, say what it does know nearby, and say it has queued the question for the right person — then create an F1 gap of kind `unanswered-question` linked to the asker, and notify the asker when it is filled. Stances are rendered in words ("the written policy says… in practice people report…"); superseded and stale facts are labelled (D2, D4); open contradictions are stated (D3). These are enforced by code assembling labelled context, not by prompt wording alone. *Gate:* `T/test_answer.py::test_unknown_creates_gap_and_declines`, `::test_asker_notified_when_filled`, `::test_policy_practice_labelled`.

**H3 — Ask the Oracle in Teams.** In `W/api/teams/bot/messages/route.ts`: a message in a personal chat that is not a reply to a pending interview question, not "join", and is judged a question → call the brain answer endpoint and reply with the answer, top sources as links to `W/map/source`, and the feedback choices. In group chats it answers only when @mentioned. *Gate:* `T/test_inbound_zh.py::test_question_is_answered_not_treated_as_interview_reply`; web route test for @mention rule; live proof with Albert's own account recorded with a screenshot.

**H4 — Memory and question log.** New tables `cmap.conversation`, `cmap.conversation_turn` (web and Teams; per user; function scope carried). Retrieval uses the conversation's recent turns to resolve "it/that/they". Every question, its routed functions, score of support, and feedback is logged; a weekly job clusters the log to show the owner "what the company keeps asking" and which questions go unanswered (feeds F1 and I4). Retention: keep indefinitely (owner said nothing here is secret); an employee may clear their own history. *Gate:* `T/test_answer.py::test_followup_uses_server_history`, `T/test_conversations.py::test_question_log_written`.

**H5 — Reliability and spend.** `B/llm.py:84-87`: retry with backoff on 429/5xx/timeouts; per-seat ordered fallback list from seat settings (no ids in code); circuit-breaker per provider. A daily spend ceiling in config enforced in `llm.py` (reads usage it already records), with non-interactive jobs pausing first and chat last; a clear banner on the health panel when paused. `requeue_orphans` (`worker.py:114-125`) keys on a per-process instance id + heartbeat so a second replica is safe. *Gate:* `T/test_llm.py::test_retry_then_fallback`, `::test_spend_ceiling_pauses_jobs_not_chat`, `T/test_worker_orphans.py::test_live_sibling_jobs_not_requeued`. **Cut point.**

### Phase I — the consultant layer (improvements the owner did not list)

**I1 — Bottlenecks and single points of failure, computed.** Job after each build, results in `cmap.insight(kind, subject, score, evidence, function_ids, graph_version)`:
- *key-person risk:* people who are the only performer/approver of steps, weighted by how many flows pass through them and whether anyone "covers for" them;
- *approval chokepoints:* approvers/decision steps with the highest flow-through and the most WAITS_FOR/BLOCKED_BY/complaint evidence;
- *system dependence:* systems many flows require, with no named owner or fallback;
- *hand-off hot spots:* function-to-function hand-offs with the most issues attached;
- *undocumented practice:* steps evidenced only by conversation, never by a document (tribal knowledge to write down);
- *policy-practice gaps* (from D3).
Shown on a new `W/map/insights` page and used by reports and recommendations in place of the prompt-only "top 10 issues" (`communities.py:58-61`). *Gate:* `T/test_insights.py` one test per kind on the fixture.

**I2 — Recurring-problem detector.** Cluster Issue entities across functions by meaning (embeddings + judge); a problem appearing in ≥3 functions under different names becomes one "company pattern" insight naming each instance and source. This is the "same problem showing up in different places under different names" promise of the original goal, now computed. *Gate:* `T/test_insights.py::test_same_problem_three_departments_grouped`.

**I3 — Recommendation follow-through.** Extend `cmap.recommendation`: owner, decided_by/at, decision note, target date, expected effect (which metric or insight should move), status history table, linked insight(s) and flow step(s), every option and the experiment carry citations (`recommend.py:82-90`). Rank by insight score × breadth × effort estimate rather than source count (`B/api/recommend.py:87`). Duplicate recommendations for one insight are merged. When a recommendation is marked implemented, a check is scheduled (30/60/90 days): has the related issue evidence, gap count or metric (J3) changed? The result is written back. *Gate:* `T/test_recommend.py::test_every_option_cited`, `::test_one_recommendation_per_insight`, `::test_followup_check_scheduled_and_recorded`.

**I4 — Weekly owner briefing.** Monday 8:00 AM New York time, to Albert in Teams and on `W/map/briefing`: what the Oracle learned this week (new sources, interviews, flows completed), what changed (superseded procedures), new contradictions and policy-practice gaps, top risks that moved, recommendations awaiting a decision and results of past ones, what the company asked most, coverage by function with the biggest holes and whom it is asking. One screen, every line clickable. Sending uses the existing proactive route; a global switch and an "only on the site" option exist. *Gate:* `T/test_briefing.py::test_contents_from_fixture_week`, `::test_switch_off_sends_nothing`; live: first briefing delivered and screenshot saved. **Owner look #3.**

**I5 — "What if" impact tracing.** Question types answered by graph traversal over flows and dependencies (`B/graph/query.py` finally gets callers): "what breaks if this person is out / this system is down / this vendor is late / we remove this approval step?" Returns affected flows, downstream steps, who is waiting, and existing workarounds, each cited. *Gate:* `T/test_answer.py::test_what_if_person_absent_lists_downstream`.

**I6 — Role playbooks.** For any role or person: an auto-written, always-current "how this job works here" page — responsibilities, the flows they take part in and their steps, who they receive from and hand to, systems, rules and exceptions that apply, known problems, open unknowns. Exportable as a document for onboarding. Also generates "process is written nowhere" document drafts for undocumented-practice insights so tribal knowledge becomes a procedure someone can approve. *Gate:* `T/test_playbook.py::test_role_page_contents_cited`; Playwright render and export.

**I7 — Meeting follow-through.** From meeting transcripts (already ingested; the triage plan grows the corpus): extract decisions and action items with owner and date into `cmap.commitment`; later transcripts and interviews are checked for whether each was done; overdue or forgotten commitments appear in the briefing and on the owner's page. *Gate:* `T/test_commitments.py::test_action_item_extracted_with_owner`, `::test_later_meeting_closes_item`, `::test_overdue_in_briefing`.

### Phase J — operational numbers

**J1 — Design and first feed.** The consultant cannot size a problem without numbers. Add a read-only metrics store: `cmap.metric_def(key, name, unit, function_id, definition, source_system)` and `cmap.metric_value(key, period, dims jsonb, value, loaded_at)`. First feed is the owner's choice (§13 Q3); recommended: order-to-ship lead times and late shipments, or licensing approval turnaround, whichever the company already has in a table or export. Ingestion paths, in preference order: (a) a scheduled read-only query against a system the brain is already allowed to read (the DesignFlow directory connection pattern in `B/directory_sync.py` is the template; any new database access needs its own read-only credential stored in 1Password and is a separate, explicitly reported step); (b) an admin upload of a spreadsheet export mapped to a metric on a `W/map/metrics` page. No writing to any business system, ever. Metric entities already extracted from documents (108 exist) are linked to `metric_def` rows where they match. *Gate:* `T/test_metrics.py::test_upload_maps_to_metric`, `::test_bad_rows_rejected_with_report`, `::test_no_write_path_exists`.

**J2 — Numbers in answers and recommendations.** Answers may quote a number only from `metric_value`, with period and source system stated; the existing scrubber for invented figures stays (`recommend.py:76-79`). Insights (I1) are re-scored with real volumes and delays where a metric is linked. *Gate:* `T/test_answer.py::test_number_only_from_metric_store`, `T/test_recommend.py::test_recommendation_sized_when_metric_exists`.

**J3 — Measured before/after.** The I3 follow-up check uses the linked metric: value in the period before the decision vs after, shown on the recommendation and in the briefing. *Gate:* `T/test_recommend.py::test_before_after_recorded`.

### Adversarial-cases table (trust boundaries)

| External input | Hostile / broken case | Test that proves it is handled |
|---|---|---|
| Uploaded Office file | zip bomb; path traversal member; external relationship pointing at a URL | existing checks in `T/test_read.py` + `::test_external_relationship_never_fetched` (A4) |
| Uploaded spreadsheet / CSV | 1M rows; formula cells; a row longer than a passage | `T/test_read.py::test_large_sheet_streamed`, `::test_csv_rows_never_split` (A5) |
| Any document text | text that instructs the model ("ignore your rules…") | existing prompt-marking tests in `T/test_prompts.py`; add `::test_new_prompts_mark_source_as_data` for every prompt added by this plan |
| Teams message | sent in a group/meeting chat | `::test_group_chat_reference_never_stored` (F4) |
| Teams message | unrelated chatter while a question is pending; reply-judge model down | `::test_judge_down_holds_reply` (F2), `::test_late_reply_matched_to_right_question` (F4) |
| Teams message | "stop" phrased differently / in Chinese | `::test_stop_variants_and_resume` (F4) |
| Teams question (H3) | non-employee or unknown sender | `T/test_inbound_zh.py::test_unknown_sender_gets_no_answer` (H3) |
| Interview answer | deliberately false or joking answer | `::test_interview_answer_contradicting_doc_creates_gap` (D3) — never silently overrides a document |
| Admin correction | merges two real different people | `::test_split_reassigns_mentions`, corrections are reversible (`active=false`) — `::test_correction_can_be_undone` (G1) |
| Employee feedback (G4) | one person spamming "wrong" | `::test_feedback_needs_three_independent_or_owner` (G4) |
| Metric upload (J1) | wrong columns, text in number fields, duplicate periods | `::test_bad_rows_rejected_with_report` (J1) |
| Brain API | call without the shared token | existing `T/test_health.py`/deps tests; add one per new endpoint: `T/test_api_auth.py::test_new_endpoints_require_token` |
| Eval gate endpoint | repeated triggering to burn spend | `T/test_llm.py::test_spend_ceiling_pauses_jobs_not_chat` (H5) |

## 10. Tests required

- Every `T/…::test_…` named in §9 and in the adversarial table must exist and pass; names are binding so reviewers can find them.
- New test files: `test_functions.py`, `test_dates.py`, `test_versions.py`, `test_contradictions.py`, `test_flows.py`, `test_gaps.py`, `test_corrections.py`, `test_conversations.py`, `test_insights.py`, `test_briefing.py`, `test_playbook.py`, `test_commitments.py`, `test_metrics.py`, `test_api_auth.py`.
- Must stay green throughout: `cd apps/brain && uv run ruff check . && uv run pytest` (needs Postgres with pgvector and FalkorDB — `apps/brain/compose.dev.yaml` provides both); the Playwright suite `apps/web/tests/map.spec.ts` (config `apps/web/playwright.map.config.ts`); `pnpm lint && pnpm typecheck` for web changes.
- `T/test_schema.py::test_migrate_runs_twice_without_error` must pass after every new SQL file.
- The live eval (B3) is the regression measure for every step from B3 onward: record mean before and after in the step's verification file.

## 11. Constraints, standing rules, gotchas

- Run `ai-task-gates start --class code` (or the stronger class a step needs: `deployment`, `production`) before editing; never work around a refusal.
- Never push to `main`; branch + PR; the AI merges its own PR (Albert does not merge). Reviews are advisory and never block. Sign everything posted to GitHub with `$AI_GH_SIGNATURE`.
- One worktree per write-capable task; keep the canonical checkout landing-only.
- `cmap` changes are new idempotent files in `B/sql/` applied by `B/migrate.py` on start-up. Do **not** route them through `popcre/shared-db` (that is the shared company database, a different project) and do not hand-edit generated Drizzle files under `packages/db/migrations/0*.sql`.
- No model ids in code. No silent fallbacks: every fallback is logged and visible on the health panel.
- Production is read-only by default for the AI; state changes happen through the deployed application's own actions (re-read, rebuild, eval), never by manual SQL.
- Repair, never remove: do not disable ScaleDown, the weekly cap, quote validation, or any guard to make a test pass.
- UI work is verified visually (Playwright screenshots under `apps/web/tests/__screenshots__/map/`).
- The repo is public: no employee-private content, secrets, or LAN addresses in fixtures, tests or docs. Fixtures use the existing synthetic company in `T/fixtures/`.
- Times shown to people are New York time, labelled EST/EDT.
- Gotchas specific to this work: (1) reports are reused across versions by key — any change to keys (C3) must migrate or regenerate, never orphan recommendations/flags; (2) FalkorDB is dropped and rebuilt on every projection (`project.py:271`) — never store anything only there; (3) the interview bot is OFF in production (`cmap.interview_setting.enabled=false`) and stays off until issue #518 says otherwise — F-phase live proofs use Albert's own account via the admin "route to me" action; (4) Chinese employees: every new employee-facing string goes through `B/interview/strings.py` and `B/translate.py`; (5) the per-job model-call cap `BRAIN_MAX_FRONTIER_CALLS_PER_JOB` must be sized for A8's re-read or the job stops early.

## 12. Access and environment

- GitHub: `gh` authenticated as `u2giants`. Repo `u2giants/theoracle`.
- Database (read-only inspection): Supabase MCP server `supabase-oracle` (`execute_sql`); schema `cmap`.
- Deploy: push to `main` → `brain-image.yml` builds GHCR image → Coolify redeploys `oracle-brain`; web deploys on Vercel. Verify with `.github/workflows/verify-live-version.yml` and `GET https://oracle-brain.designflow.app/health` (expects `{"ok":true,"db":true,"graph":true}`). Use the `deploy-and-verify` skill.
- Secrets: 1Password vault `vibe_coding` (never values in chat, code, logs): OpenRouter key (item `62ieeyycs4ierflalbbbt5pq5i`), brain shared token (`BRAIN_SHARED_TOKEN`, used by the web proxy and by B3's workflow as a GitHub Actions secret — check `gh secret list` before adding), Supabase and Teams bot credentials. Load the `secrets-to-1password` skill before any secret handling.
- Local run: `cd apps/brain && docker compose -f compose.dev.yaml up -d && uv sync && uv run python -m brain` ; web: `pnpm --filter web dev`. Tests as in §10.
- Environment variables are documented in `docs/configuration.md` and `plan_oracle_company_map.md` §12; every variable this plan adds (`BRAIN_ANSWER_CONTEXT_TOKENS`, spend ceiling, staleness horizons, briefing switch) must be added to `B/config.py`, `apps/brain/deploy/compose.coolify.yaml`, and `docs/configuration.md` in the same PR.
- Other MCP servers available: `trigger` (legacy workers; not used by this plan), `recall-ai` (meeting bot, read-only).

---

# Part 4 — Landing it

## 13. Definition of done, risks, open questions

**Done when all are true:**
- Every STATUS row is ✅ with an openable artifact; issue #520's checklist is ticked with a link per phase.
- Owner-approved eval set (≥30 questions) scores mean ≥ 0.6 on two consecutive nightly runs, with zero errors, and the release gate has caught at least one deliberately introduced regression.
- A function-scoped question's context contains no other function's material (C4 test + live sample of 10 questions saved to verification).
- The end-to-end flow page shows the company's main flow in order with sources, and its gaps are listed.
- A correction made by the owner is still in force after a full re-read and rebuild.
- Interview sittings follow up, follow referrals, and never post to group chats (tests + one live sitting with Albert's account).
- The Monday briefing has been delivered at least once.
- Code committed, PRs merged, CI green, deployed version verified, `docs/architecture.md`, `docs/configuration.md`, `docs/agents/03-documentation-map.md` and `docs/agents/15-pending-work.md` updated, handoff retired under the successor rule.

**Risks and rollback:**
- *A1 pruning deletes a report something links to* → the step checks references first; prune is a soft step behind a config flag for the first run; restore from Supabase point-in-time if needed.
- *A8 re-read costs more than expected* → throttled, resumable, under the daily spend ceiling; can be paused from the health panel.
- *C3 changes report identity* → recommendations and flags are re-pointed in the same migration; verified by row counts before/after.
- *F-phase sends unwanted messages* → bot stays off; all live proofs target the owner; sittings count against the unchanged weekly cap.
- *H1 doubles answer latency* → sentence checks run in parallel on the cheap seat; if p95 exceeds ~12 s, check only sentences with numbers, names or negations first and the rest asynchronously (mark "verifying").
- *Model cost growth from new passes (C2, D3, E2, H1)* → each runs incrementally (changed sources only) and on the flat/cheap seat except D3/E2.
- Every step is independently revertable by reverting its PR; SQL files are additive.

**Open questions for the owner (business meaning only; each has a default so work never waits):**
1. *The list of business functions (C1).* Default: the 13 proposed in C1, shown on the site for him to rename/merge. Changes nothing irreversible.
2. *Who is the licensing team* (carried from issue #474; F3 no longer needs the answer to route correctly, but it speeds up the first interviews). Default: derive from the directory and documents.
3. *Which operational numbers come first (J1), and from which system.* Default recommendation: order-to-ship lead time and late shipments. **This is the only item that blocks a step (J1).**
4. *Whether the Monday briefing goes to anyone besides Albert.* Default: Albert only.
5. *How old is "possibly out of date" (D4).* Default: 18 months for who-does-what, 36 months for rules.

**Genuinely uncertain (decide by measurement):** whether A1–A7 alone reach 0.6 (measure at A8); the right similarity floor and context ceiling in C4 (tune on the approved set); window size in E1.

---

## Self-audit (2026-11-11)

1. *Could a brand-new session execute this without asking anything?* Yes for every unblocked step: §2 defines the application, vocabulary and pipeline; §5 maps every defect to file:line and the step that fixes it; §9 gives per-step files, behaviour and named tests; §11–§12 give rules and access. Gap found while auditing: the reuse-stamping behaviour of `graph_version` was not verified — A1 now instructs the implementer to confirm it first and states the intended behaviour. J1 is honestly marked blocked on one owner choice with a default.
2. *Does it carry all the background and reasoning, including what was ruled out?* Yes: §6 root causes, §7 twelve rejected approaches with reasons (including the 2026-11-10 quota flood and the two model bake-offs), §8 locked vs open decisions with dates, plus the audit file as evidence.
3. *Is the goal clear enough to steer by when a step is wrong?* Yes: §1 states the seven owner goals verbatim, a concrete picture of success, and "the goal wins" with the three inherited prohibitions.
