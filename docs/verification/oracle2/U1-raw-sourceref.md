# U1 raw→SourceRef — offline evidence

Status: offline gate evidence stub (synthetic/invented only).
Recorded: 2026-10-20 (S03 U1 raw→SourceRef e2e offline chain).

## Offline tests

test_replacement_original_lifecycle.py, test_original_qualification_runtime.py
(18 passed, 1 skipped — PDF-render happy path skips on Windows where
oracle_brain.hosting cannot import fcntl; pure chain always runs).

Retained component suites in the same named set:
test_original_qualification_v1.py, test_raw_original_views_v1.py,
test_raw_original_native_provider_v1.py (79 passed, 34 skipped overall when
hosting imports are Windows-blocked; 11 test_replacement_source_intake_sql.py
errors require a real local Postgres (ORACLE2_TEST_ADMIN_URL) and are not an
offline claim).

## What is proven

1. Raw original bytes → genuine complete all-view PNG image parts → admitted
   raw quote binding (byte sizes from actual decoded PNG payloads) is re-proved
   before either dispatch.
2. Same central Budget/native wire reserve/finish hooks run once for the
   reading phase and once for the independent review phase (in-process fake
   sender; no network, no live provider).
3. Closed canonical reading and review response commits parse through
   parse_original_response_commit_v1 and seal as distinct phase commits.
4. Qualification finalize INSERTs into source_reading_qualifications exactly
   once under late independent reviewer authority (distinct principal, role and
   model from the reader). A second finalize is denied (QualificationConflict).
5. First SourceRef (workspace_id, source_id, revision, original_sha256,
   reading_sha256, parser_id) exists only after that finalize; nothing is
   invented before it.
6. Denial paths held: omitted PNG part, substituted image, same reviewer as
   reader, same reviewer model, missing review commit, second qualification
   INSERT.

## SQL custody

sql/014_replacement_source_custody.sql gains
oracle2.finalize_original_reading_qualification_v1(text,text,text): requires
both response commits, distinct reviewer/reader, agreeing custody seals, the
exact immutable original revision, and current late-reviewer admission; then
INSERTs source_reading_qualifications once and materializes
operating_model_source_receipts so replacement_source_head_v1 can build
qualifiedSourceRef. GRANT EXECUTE to oracle2_source_original_reviewer only.

## Linux-only remaining cases

test_replacement_original_lifecycle.py::test_raw_pdf_all_png_views_flow_into_qualified_source_ref
and test_raw_original_views_v1.py hosting cases render an actual PDF through
render_raw_pdf_views_v1 and run the same chain with real view/locator seals.
They skip on Windows (fcntl). Run them on a POSIX host to close that bit.

## Not accepted

Not accepted: no private originals, no employees, no company data, no live
provider call, no production deployment, no browser/native U1 stage closure.
This stub does not close the U1 stage while browser/native acceptance remains
open. S14/S15/S16 business and live acceptance stay closed.
