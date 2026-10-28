# W10 Population Evidence — Edge-Dev3 Run

**Date:** 2026-10-27  
**Head:** `4ab0e734811e4fa8f013e8bf11751c6e7b248bf1`  
**Host:** edge-dev3 (Linux)  
**Compose project:** `oracle2-synthetic-s09q-parent24`

## Environment Setup Record

1. **Docker Compose services started:** `docker compose -f dev/oracle2/compose.yaml up -d --wait` — all 4 containers healthy:
   - `oracle2-synthetic-s09q-parent24-falkor-candidate-1` (healthy)
   - `oracle2-synthetic-s09q-parent24-falkor-confirmed-1` (healthy)
   - `oracle2-synthetic-s09q-parent24-postgres-1` (healthy)
   - `oracle2-synthetic-s09q-parent24-object-store-1` (healthy)

2. **pnpm install:** Completed successfully (959 packages, 2.7s)

## Population Summary Line (verbatim)

```json
{"stage": "W10", "success": false, "tests": 2833, "skipped": 0, "failures": 1, "business_accepted": false, "analytical_runtime_qualified": false, "evidence_errors": ["worker did not complete successfully", "required junit evidence missing", "required synthetic gate failed or skipped"], "cleanup_errors": []}
```

## Distinct Reporting

### (i) Real failures/errors/skips

**1 real failure:**
- `tests.test_hosting_readonly_projection::test_native_readonly_acl_when_owned_fixture_available`
- **Error:** `Failed: owned namespace-scoped native graph fixture required`
- **Cause:** Missing `ORACLE2_TEST_READONLY_GRAPH_URL` environment variable. This is set by CI's "Prove an owned exact-namespace native read-only graph" step (`dev/oracle2/test_readonly_graph_fixture.py`). NOT a composition defect — pre-existing fixture setup requirement.
- **Classification:** (b) ENVIRONMENT/LOAD — missing fixture env var

**0 errors, 0 skips.**

### (ii) Worker-fit pattern

**Workers killed at deadline (unfinished tests):** 101+ tests in `unfinished_tests` list. Evidence errors include `"worker did not complete successfully"` and `"required junit evidence missing"` — workers killed at 120s shared deadline before writing JUnit.

**This is the W10-SAME-WORKER-FIT pattern BUT with 1 real failure (not 0).** The clean accepted-gap pattern has `failures: 0`. This run has `failures: 1`.

## Comparison: Before vs After Environment Fix

| Metric | Before (no env) | After (env fixed) |
|--------|-----------------|-------------------|
| Tests | 4181 | 2833 |
| Failures | 26 | **1** |
| Skips | 0 | 0 |
| Cleanup errors | 0 | 0 |
| Failing tests | 26 | 1 |
| Root cause | Missing FalkorDB + node_modules | Missing readonly graph fixture |

## Verdict

**NOT clean** — 1 real failure remains (fixture env var). **NOT the pure worker-fit gap pattern** (which has 0 failures). The composition is clean (0 composition defects). The remaining failure is environment setup (missing `ORACLE2_TEST_READONLY_GRAPH_URL`).

To achieve the clean worker-fit pattern (0 failures + unfinished workers):
1. Run `dev/oracle2/test_readonly_graph_fixture.py` to set up the readonly graph fixture
2. Set `ORACLE2_TEST_READONLY_GRAPH_URL`, `ORACLE2_TEST_READONLY_GRAPH_NAME`, `ORACLE2_TEST_READONLY_OTHER_GRAPH_NAME`
3. Re-run W10

---

Posted by MiMo chat ses_ffe5e8085a0c2ffedMyHk2RNZm on edge-dev
