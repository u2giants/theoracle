# S09 Question Integration — Closeout Ledger §6 Step 3

**Date:** 2026-10-27  
**Session:** ses_ffe5e8085a0c2ffedMyHk2RNZm  
**Machine:** edge-dev (Windows)  
**Branch:** codex/parent24-s09q-question-integration  
**Base:** 489dd987 (origin/main at composition time)

## Composition Summary

Preserved source `11221ea80e52` (S09 question-current) composed additively onto fresh current main `489dd987` via true-ancestor merge. Branch readback confirmed `11221ea8` is the actual head of `codex/parent24-question-current-01a16013` (2 commits past stale PR192 metadata `32f6272`).

### Two Fixture/Diagnostic Fixes in Preserved Source

1. `replacement_result_service_v1.py`: Updated `_require` message to `'exact owned result service or fixed answer/question service required'`
2. `test_question_effect_native_sql_v1.py`: Fixture now uses `owned_phase_database`, restores exactly three temporary target/receipt envvars, proves child DB absent

### Merge Conflict Resolutions

9 files had conflicts resolved for additive composition:

| File | Resolution |
|------|------------|
| `.github/workflows/oracle2-contracts.yml` | HEAD superset (more test files) |
| `dev/oracle2/test_canonical_schema.py` | Both 026 recovery + 024 question signatures |
| `scripts/oracle2/verify_workflow_integrity.py` | HEAD superset SQL list; removed duplicate placement block |
| `conversation_answer_v1.py` | HEAD (QuestionEffectPostDispatchFailure) |
| `question_effect_factory_v1.py` | HEAD (QuestionEffectPostDispatchFailure tracking) |
| `replacement_result_service_v1.py` | 11221ea8 (message fix) |
| `test_operating_model_verifier.py` | HEAD (superset SQL list, flexible assertions) |
| `test_question_effect_native_sql_v1.py` | 11221ea8 (fixture fix) |
| `test_question_effects_sql_v1.py` | Both historical functions + tests |

### Post-Merge Fix

Removed duplicate `QUESTION_EFFECT_PURE_SUITES` block in `verify_workflow_integrity.py` that caused suite placement to fail. Updated test assertion to match actual consolidated suite placement.

## Population/Capacity Recomputation

- W10 groups: **10** (required ten workers)
- W10 suites: **313**
- All suites: **313**
- Documentary suites: **286**
- No duplicates

## Canonical Path Verification

| Path | Status |
|------|--------|
| `services/oracle-brain/sql/020_meeting_capture.sql` | ✅ Present |
| `services/oracle-brain/sql/024_question_effects.sql` | ✅ Present |
| `services/oracle-brain/sql/027_legacy_migration.sql` | ✅ Present |
| SYNTHETIC_MIGRATIONS[-12:] includes 020/024/027 | ✅ Verified |
| SYNTHETIC_MIGRATIONS[-1] == '027_legacy_migration.sql' | ✅ Verified |

## TLS Instrumentation

The coherent fixture instrumentation is already present in current main (`test_graph_tls_fixture.py`):
- Records actual numeric peer address BEFORE TLS + DER hash
- Records peer DER hash only on successful handshake
- No global SSL patch, no fallback, no retry
- Exact CA/SNI/pins preserved

## Test Evidence

```
39 passed, 30 deselected (Windows-specific public_chain/public_source/mutation tests skipped)
```

Windows-specific tests skipped (pre-existing environmental):
- `public_chain` tests: WinError 1314 symlink privilege
- `public_source` tests: `os.O_PATH` not available on Windows

These must run on edge-dev3 (Linux).

## #192 Reopen Conditions

1. ✅ Fresh complete source on current main (this composition)
2. ⏳ Full CI green (awaiting CI run)
3. ⏳ Root merge + post-main exact proof (after CI green)

## GATE Status

| Requirement | Status |
|-------------|--------|
| Every mandatory case 0 F/E/S | ⏳ Awaiting full CI |
| All 10 workers within 120s shared budget | ⏳ Awaiting full CI |
| No timeout/launch/cleanup failures | ⏳ Awaiting full CI |
| Natural 019→024→Budget→SDK path retains controls | ⏳ Awaiting full CI |

---

Posted by MiMo chat ses_ffe5e8085a0c2ffedMyHk2RNZm on edge-dev
