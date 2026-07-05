# AGENT_ERROR_LOG.md — runtime failures for a coding agent to fix

## What this file is (read first)

This is the **designated place where runtime failures are written so a coding AI agent (or human) can act on them.** The Oracle's background workers run on Trigger.dev and cannot write into this repo, so a failure that only lands in Trigger.dev's dashboard or a `model_run_attempts` row is, in practice, **failing silently** — nobody and no agent is watching those. This file is the durable, in-repo, agent-readable digest.

**Hard rule (design phase):** if a worker/run fails, it must end up here, in a form specific enough to change code from — exact error signature, where it surfaced, root cause with `file:line`, evidence (run IDs / DB counts), the fix, and status. `HANDOFF.md` links here so every session sees it.

### How entries get here (until fully automated)

1. **Now (manual/session):** when a run is found failed (Trigger MCP `list_runs`/`get_run_details`, or DB `job_runs`/`model_run_attempts`), append/refresh an entry below.
2. **Export helper:** the macro/coverage/outline workers write `job_runs` rows and a document-level `macro_health` status. `scripts/export-worker-failures.mjs` can query recent failed `job_runs` + `model_run_attempts` and print an agent-readable digest. **Absence of an entry here still does NOT prove absence of failure — check Trigger.dev and DB counts too.**

### Entry status legend

- **OPEN** — still failing in the current deployed worker.
- **MITIGATED** — a code/config change addresses it but is not yet verified in prod (needs deploy/migration/re-run).
- **DEPLOYED** — code/migration reached prod, but the specific scenario still needs an end-to-end rerun.
- **FIXED** — verified not failing after the change (record the evidence).

---

## Open / recent failures

### ERR-001 — Macro & coverage workers hard-fail: `AllCandidatesFailedError`  — ✅ FIXED & VERIFIED IN PROD (2026-07-03)

**RESOLUTION (verified 2026-07-03, worker `20260703.4`):** macro + coverage now succeed in prod — `macro_relationships` inserted, `source_coverage_findings = 4`, `documents.macro_health = complete`, macro attempt `success openai/gpt-4.1-mini primary=true`. Two things had to be fixed together:
1. The model route (below) — moved off the Qwen `general` slot to a dedicated `macro` slot **with a fallback pool**.
2. **A second, hidden discovery from the fallback logs: Gemini also can't do it.** `google/gemini-2.5-flash` AND `gemini-2.5-pro` both reject the nested macro schemas with `400 "The specified schema produces a constraint that is too complex"`. So the *first* seeded primary (Gemini) would have hard-failed too — the fallback pool saved the run by falling through to `openai/gpt-4.1-mini`, which handles strict complex schemas. **The primary was corrected to `openai/gpt-4.1-mini`** (settings, migration 83/84, seed). Lesson: for the macro schemas, use an **OpenAI** strict-json-schema model; Gemini is only safe for the simpler source-outline schema.
This is also the proof that the fallback-pool design (below) is load-bearing, not optional — both the Qwen primary and the Gemini primary failed; only the pool made the layer resilient.

<details><summary>Original diagnosis (kept for history)</summary>

- **Symptom:** `macro-relationship-extraction` and `source-coverage-audit` **failed on every run** for document `9d09fa89-3a46-465e-a98b-837287c9e22a`, so the holistic layer produced `macro_relationships = 0` and `source_coverage_findings = 0` while the document still showed `complete`.
- **Where it surfaced:** Trigger.dev prod, project `proj_wgpzsvhmsopqhvwqaycn`, worker `20260703.2`. Evidence runs: `run_cmr4bxmwi64y00un5c6a7nne0` (macro), `run_cmr4bxqat68b40uof9kxb3bts` (coverage). Both retried 3× and failed identically (~3.7–4.6m, ~$0.008).
- **Exact error:**
  ```
  AllCandidatesFailedError: All model candidates failed for general:
    qwen_3_7_max_extraction_eval (qwen/qwen3.7-max):
    [{ "code":"invalid_type", "path":["relationships"], "message":"expected array, received undefined" }]
  ```
  (coverage identical at `path: ["findings", 0, …]`).
- **Root cause:**
  1. Both workers resolved the model via the **`general` auxiliary slot** (`resolveRouteCandidates(db, 'general')`), which in prod pointed at **`qwen/qwen3.7-max`**. NOTE: this is a *separate* setting from the Extraction and Vision model pickers — changing those in Admin → Settings did **not** change what the macro layer used.
  2. Qwen uses `response_format: json_object` + Zod (**not** strict json-schema; see `DECISIONS.md` D12 / `docs/architecture.md`). On the deep nested `MacroRelationshipOutputSchema` / `CoverageAuditOutputSchema` it omits the required top-level array → Zod `invalid_type`.
  3. The `general` slot is **single-pick with no working fallback** (`PROVIDER UNAVAILABLE: "deepseek" ... DEEPSEEK_API_KEY is not set`), so one malformed response fails the whole task.
- **Fix applied (this change, 2026-07-03):**
  - Added a dedicated **`macro` auxiliary slot** with its own admin picker `default_macro_route` (Admin → Settings → "Macro understanding model"), a `requiredCapability: 'structuredOutputs'` filter, and a "Copy job brief" that spells out strict-json-schema as a hard requirement.
    - `packages/ai/src/routes/{errors,defaults,auxiliary,capability-requirements}.ts`, `apps/web/app/admin/settings/page.tsx`.
  - Repointed `source-outline`, `macro-relationship-extraction`, `source-coverage-audit` from `'general'` → `'macro'`.
  - Seeded `default_macro_route = google/gemini-2.5-flash` (native `responseJsonSchema`, proven prod model): `packages/db/migrations/sql/83_macro_route_setting.sql` + `packages/db/src/seed.ts`.
- **Fix applied — batch 2 (2026-07-03):**
  - **Fallback pool added:** the `macro` slot is no longer single-pick. New `model_pool_macro = [google/gemini-2.5-flash, google/gemini-2.5-pro, openai/gpt-4.1-mini]` (all strict-schema) is wired through the existing pool machinery (`packages/ai/src/routes/{defaults,candidates}.ts`, migration `84`, seed). One bad response now falls through to the next candidate instead of zeroing the layer.
  - **Visibility:** `macro-relationship-extraction` and `source-coverage-audit` now write `job_runs` rows (running → complete/failed) and update `documents.macro_health` (migration `85`, `apps/workers/src/lib/macro-health.ts`). A failed macro layer now downgrades `macro_health` to `degraded`/`failed` — it can no longer masquerade as a green `complete` document at the data layer.
- **Hardening added locally/deployed 2026-07-04:** macro relationship and coverage validation failures now get a one-shot strict OpenAI schema-repair pass before the worker fails the run.
- **Still OPEN (do next):**
  - Set `DEEPSEEK_API_KEY` in the worker env or stop advertising deepseek as a phantom fallback.
- **Verification (DONE 2026-07-03):** migrations `83/84/85` applied to prod; workers deployed (`20260703.4`); verified `macro_relationships` inserted (run `run_cmr5gu7lx…`), `source_coverage_findings=4` (run `run_cmr5guyry…`), and `documents.macro_health=complete` (clean run `run_cmr5h0izj…`).

</details>

### ERR-002 — Support-claim SQL queries fail: `42P10 SELECT DISTINCT / ORDER BY`  — ✅ FIXED & VERIFIED (2026-07-03)

- **Symptom:** `macro-relationship-extraction` (and `source-coverage-audit` when a document was linked) failed fast, before the model call, with `Error: Failed query:`.
- **Root cause (reproduced directly against prod):** `42P10 — for SELECT DISTINCT, ORDER BY expressions must appear in select list`. **Three** queries used `SELECT DISTINCT … ORDER BY c.created_at` (cross-source also `ORDER BY CASE …`) without those in the select list: the cross-source CTE and single-source query in `macro-relationship-extraction.ts`, and the claim query in `source-coverage-audit.ts`. So the document-scoped macro path was **always** broken, independent of ERR-001. (My earlier "likely fixed in `.2`" guess was wrong — it only "reached the model" on runs where `documentId` was null and the query was skipped.)
- **Fix:** cross-source → drop the redundant outer `DISTINCT` (the `IN`-subquery already yields unique ids); single-source + coverage → add `c.created_at` to the select list (JOINs can duplicate, so `DISTINCT` stays). All three corrected forms verified against prod (40/40/80 rows) before patching, then verified live (post-fix macro/coverage runs completed — see ERR-001).
- **Do next (optional):** a DB-touching smoke test that runs all three queries against a seeded fixture so this class can't silently regress.

### ERR-003 — Followup fan-out: each lens job re-triggers macro + coverage  — DEPLOYED (needs rerun verification)

- **Symptom:** one `source-outline` run produced **~49 macro + ~50 coverage** runs in ~15 min (`job_runs`). Pre-fix those were failures; post-fix they'd be redundant *successes* over the same claims.
- **Cause:** both `source-outline` AND every `document-lens-extraction` job trigger the two followups on completion. With coverage-first fan-out dispatching up to 16 lens jobs, that's up to ~16× redundant macro/coverage passes (the near-duplicate guard prevents duplicate rows, but the model calls are wasted spend + noise, and they leave `macro_health='degraded'` from any transient failure).
- **Fix applied/deployed:** `document-lens-extraction` no longer triggers macro + coverage directly. Lens jobs now record completed/skipped-existing work, and the final completed lens job claims a one-time `source_outlines.budget_json.macroFollowupsDispatchedAt` latch before triggering `macro-relationship-extraction`. `macro-relationship-extraction` triggers `source-coverage-audit` only after the macro pass finishes, so coverage no longer races ahead of relationship insertion. Deployed in Trigger worker `20260704.2`; verify by rerunning a diagram outline and checking for one macro run plus one coverage run per outline.

### ERR-004 — Workflow structure was not first-class; macro graph stayed invisible behind pending claims — DEPLOYED (needs rerun verification)

- **Symptom:** diagram/SOP sources could still explode into many atomic claims without preserving the underlying process graph. Macro relationships were also born `blocked_pending_support`, so the holistic layer stayed hidden until a noisy claim queue was approved.
- **Fix applied/deployed:** added `source_workflow_maps` with nodes, edges, paths, and coverage metadata; source-outline now persists the graph; document ingestion runs the outline/workflow-map pass before broad extraction; candidates store `workflowTrace` when their quote matches a workflow edge; candidate hashes can use a stable graph edge key for edge-level dedup; macro extraction inserts deterministic path relationships from workflow-map paths; coverage audit inserts missing-edge findings; and generated macro relationships with pending support now enter `pending_review` while read-time Brain/chat helpers still require approved support. Migration `86_source_workflow_maps.sql` applied to prod and Trigger worker `20260704.2` deployed on 2026-07-04.
- **Verification run:** local typechecks/smokes passed; production DB smoke `verify:macro-support-queries` passed; `source_workflow_maps` exists in prod. Still needs a real swimlane/Pop-style document rerun to verify non-empty workflow maps, traces, deterministic relationships, and missing-edge findings.

### ERR-005 — Document-only contradiction watcher inserts fake channel id — DEPLOYED (needs rerun verification)

- **Symptom:** `scripts/export-worker-failures.mjs` found recent `contradiction-watcher` failures inserting `oracle_interventions` with `channel_id=00000000-0000-0000-0000-000000000000`.
- **Root cause:** `oracle_interventions.channel_id` is an FK to `channels.id`; document-only contradictions have no real chat channel, so the fake all-zero placeholder violates the FK.
- **Fix applied/deployed:** `contradiction-watcher` now inserts an `oracle_interventions` row only when a real `channelCtx` exists. Document-only contradictions still persist the contradiction and gap rows. Deployed in Trigger worker `20260704.2`.

---

## Systemic observability gaps that let the above hide (fix so failures can't be silent again)

These are tracked in detail in `fix_enhancement.md` §5 (Bugs C, D, G) and its fix priority. Summarized here because they are the reason ERR-001 went unseen:

- **Macro/coverage workers did not write `job_runs` rows** → FIXED 2026-07-03: both now write `job_runs`. (source-outline already did.)
- **No document-level `macro_health`** → FIXED: `documents.macro_health` is written by the workers (`not_applicable | pending | complete | degraded | failed`) and rendered in Admin → Documents.
- **Followups are fire-and-forget** (`source-outline.ts` `.trigger(...).catch(warn)`) → parent job succeeds regardless. Failure now propagates into `macro_health` (race-tolerant precedence). Coverage is sequenced after macro in source; verify in prod after deploy.

---

## Change log

- **2026-07-03:** File created. Seeded ERR-001 (macro/coverage Qwen schema hard-fail — mitigated by the dedicated `macro` route) and ERR-002 (cross-source SQL failure). Documented the observability gaps that hid them. Referenced from `HANDOFF.md`.
