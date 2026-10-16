# S05 confirmation admission draft verification

Status: source-only draft; S05 and parent #24 remain unaccepted. No live proof is claimed.

Base: `ac7b5d2f24fb0ec94e70a584b2c88f2275f5b3da` (PR141 historical GLM-approved draft head), preserved as the starting point rather than treated as current acceptance. This candidate adds only offline-testable confirmation admission and versioning.

## What this piece covers

Pure DTO/logic in `oracle_brain/knowledge/admission.py` (existing `admit_document` retained unchanged in behavior; its authority import is now lazy so the module stays free of database clients at import time):

- A single employee confirms their own account only; another employee cannot confirm it.
- Company-policy confirmation and promotion respect process-owner authority.
- Unknown ownership is an explicit kind with no owner and blocks confirmation and promotion until established.
- Review submissions carry `based_on_version`; a stale submission returns a `ReviewConflict` with a readable content diff and does not mutate state.
- Correcting an assertion bumps its version, keeps prior versions in history for as-of recovery, and marks only dependent recommendations `stale`.

## Offline verification

`uv run pytest -q tests/test_admission.py tests/test_identity_resolution.py tests/test_temporal_facts.py tests/test_summary_invalidation.py` from `services/oracle-brain`: **20 passed, 0 failed, 0 skipped** (11 admission, 2 identity, 4 temporal, 3 summary invalidation). Execution used an ephemeral `pytest` + `pydantic` + `psycopg[binary]` environment with `PYTHONPATH` set to the package root because the full `uv sync` build fails on this Windows host (`hnswlib` requires MSVC build tools; failure is environmental, not a test failure). Import purity check: loading `oracle_brain.knowledge.admission` does not load `psycopg` or `oracle_brain.authz`.

Invented data only. No provider calls, credentials, employee contact, production or database actions.

## Remaining before #29 can close

`projection.py`, `oracle_brain/workflows/consolidate.py`, `test_graphiti_isolation.py`, review API/UI (`apps/web/app/api/consultant/reviews/[id]/route.ts`, `apps/web/components/consultant/review-bundle.tsx`), offline `test_review_concurrency.py` (existing version needs live Postgres), preview `tests/oracle2/correction.spec.ts`, artifact `docs/verification/oracle2/S05-correction.md`, and the full live acceptance of the temporal operating model. Existing live-proof checklist stays on #29. This draft is not acceptance and requests no stage merge.
