# S13 Runner 10 — minimum actual SQL repair proof

**Date:** 2026-10-27 (EDT)
**Session:** ses_ffe5e8085a0c2ffedMyHk2RNZm on edge-dev
**Class:** shared-db (declared before writes)
**Branch:** `mimo/parent24-s13-sql-repair-20261027`
**HEAD:** `489dd987f96d613be9e0546d4a772ab665b584a4` (current upstream main)

## Composition

The 2633 additive delta (c187bfc3..2633c53b, 30 files +7866/-34) is already merged
into current upstream main through prior PRs. Verified: all 30 files exist in main
at HEAD. No B+C subsets or inverse old-main diffs were applied.

## Two ratified SQL defects — both already fixed in main

1. **Receipts census workspace join** — `meeting_capture_worker_receipts_v1` census
   now joins `meeting_capture_worker_claims_v1 own ON own.claim_id=t.claim_id
   WHERE own.workspace_id=ANY($1)` (line 536). No bogus `t.workspace_id` column.

2. **Scope SRF alias qualification** — `AS recovery_scope_item(value)` with
   qualified `recovery_scope_item.value` at both sites (lines 629, 706). No naked
   `jsonb_array_elements(...scope_coverage) scope` remains.

## 56/75-query audit

Full audit: `docs/verification/oracle2/s13-sql-repair-audit.json`
- 75/75 census queries PASS
- 18/18 DECLARE-collision sites PASS
- 0 additional defects found

## Static tests (4 defect-catching)

All 4 pass on current main:
- `test_worker_receipts_census_joins_claims_owner_workspace_not_bogus_column`
- `test_no_naked_scope_alias_on_scope_coverage_array_elements`
- `test_claim_recovery_phase_uses_explicit_recovery_scope_item_value`
- `test_all_census_queries_workspace_scope_or_owner_join`

Note: 1 pre-existing failure (`test_frozen_processing_successor_complete_rows_and_exact_parent_custody_are_mandatory`)
is a stale hash pin on 020 (updated by PR #193). Unrelated to the two ratified defects.

## Gate chain

### 1. Muse SOURCE + resource-plan assessment (APPROVE)

- Run ID: `20261027T230844-2914762-18052`
- Reviewed commit: `489dd987f96d613be9e0546d4a772ab665b584a4`
- Source digest: `f19b93827024959c354cfd473f8f4f3e05b56f174b366b65e63a83af70972161`
- Verdict: **APPROVE** (minor findings, no blocking defects)
- Report: `.ai/reviews/muse-final-check-20261027T230844-2914762-18052.md`
- Dispatched via `C:\Program Files\Git\bin\bash.exe` from worktree with
  `AI_POOL_CALLER=mimo AI_IMPLEMENTER_ENGINE=mimo`

### 2. Database gate (edge-dev3)

- pglast v8.7 parse of `026_operational_recovery.sql`: **PARSE OK: 18 statements**
- Python: `/tmp/pglast-venv-20261023/bin/python3`
- Invented project prefix: `s13r-parent24`

### 3. ONE fresh release execution — Runner 10

- **Project:** `oracle2-synthetic-s13r-parent24-wc75207e07411`
- **Container:** `379c59df2320a742a1f9047a13432c0b865382f8e78f9939c5bb99100b44954e`
- **Port:** 33472
- **Runner:** `/tmp/runner10.py` on edge-dev3
- **Venv:** `services/oracle-brain/.venv` (uv sync --frozen --extra test --extra process-analysis)
- **JUnit:** `docs/verification/oracle2/s13r-runner10-pytest.xml`

**Result: 27 passed, 0 failures, 0 errors, 0 skipped, 38.776s**

## Gate verification

- ✅ All 27 actual PASS
- ✅ 0 errors / 0 skips
- ✅ Current catalog / permission / revocation / direct-entry negatives all meaningful
- ✅ Complete source unchanged during run (source-before/after equal at `489dd987`)
- ✅ Exact owned resources absent afterward (Docker project/container/network/volumes cleaned)
- ✅ 25 failure histories from run 09 preserved in closeout evidence (not erased)
- ✅ New identities (not replaying spent 09: `oracle_operating_model_test_4ed140d77ea54ee88b7cace48d560a13` / `oracle2-synthetic-p24rec-01a16013-w5673ca72552d`)

## Where we stop

Metadata success is NOT full restore. The remaining S13 recovery work continues:
- Full fresh backup/restore/quarantine/current denials
- Private/vector/license/once/cost tails
- 019 paused checkpoint
- Fresh-instance measured RTO/RPO
- All-writer cut and company acceptance

## Evidence files

- `docs/verification/oracle2/s13r-runner10-pytest.xml` — JUnit XML (27/27)
- `docs/verification/oracle2/s13-sql-repair-audit.json` — 75-query audit (prior)
- `docs/verification/oracle2/s13-sql-repair-evidence.md` — composition evidence (prior)
- `.ai/reviews/muse-final-check-20261027T230844-2914762-18052.md` — Muse APPROVE

Posted by MiMo chat ses_ffe5e8085a0c2ffedMyHk2RNZm on edge-dev.
