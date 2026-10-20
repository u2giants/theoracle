# Offline acceptance receipts — W01/W02/W05/W07/W09

Recorded October 19, 2026. Offline/synthetic acceptance only. Private, hosted,
live, business, and elapsed gates remain open on #27/#58 under #24. No stage is
fully accepted. No private/hosted/business claim is made.

Flag convention: `offline_accepted: true` means the offline/synthetic
verification obligations for that W-row are met with linked artifacts. Private,
hosted, live, business, and elapsed acceptance flags remain false.

## W01 — boundary register/fixtures/review

- **offline_accepted**: true
- **Artifacts**: [W01-approval.md](W01-approval.md) (Muse APPROVE, commit `2b54c65e`),
  [W01-execution.json](W01-execution.json), [W01-baseline.md](W01-baseline.md),
  [W01-replacement-boundary.md](W01-replacement-boundary.md),
  [boundary-register.json](boundary-register.json)
- **Offline scope**: evidence freeze, keep/replace/retire boundary, frozen
  synthetic fixtures (checksums immutable), independent obligation inventory,
  import-boundary tests (5 passed).
- **Remaining open**: private-store adoption/write; full caller census completed
  2026-10-19 in [W12-import-job-route-writer-census.json](W12-import-job-route-writer-census.json).

## W02 — ledger core

- **offline_accepted**: true
- **Artifacts**: [W02-findings.md](W02-findings.md)
- **Offline scope**: strict source receipts, occurrence-preserving observations,
  typed findings, Postgres atomic manifest/dependency/outbox, crash/replay,
  source-access revocation, tampering, unsupported conflicts, failed-receipt
  reload, current authority, bounded provider adapters — all verified synthetically.
- **Remaining open**: private extraction audit, production roles/races, hosted recovery.

## W05 — lineage

- **offline_accepted**: true
- **Artifacts**: [W05-lineage.md](W05-lineage.md),
  `services/oracle-brain/tests/test_workflow_lineage.py`
- **Offline scope**: transitive denial, queued recomputation, signed SDK delivery,
  fresh synthetic restore, dependency self-cycle rejection, outbox lease/replay,
  stale-version denial — verified synthetically.
- **Remaining open**: hosted scheduling/provider admission, private backup/restore.

## W07 — synthetic import

- **offline_accepted**: true
- **Artifacts**: [W07-operational-import.md](W07-operational-import.md),
  `services/oracle-brain/tests/test_operational_export.py`
- **Offline scope**: synthetic event import/review, CSV/XES limits, duplicate
  quarantine, censoring, scoped import denial, raw-export replay, authenticated
  invented CSV import path, atomic import manifest/index/outbox — verified.
- **Remaining open**: private ledger intake/mapping. Actual ClickUp observation
  export (816 observations, 360 cases, 531 links, 285 unknown predecessors) is
  quarantined custody, not accepted application-ledger ingestion.

## W09 — consulting roles

- **offline_accepted**: true
- **Artifacts**: [W09-consulting.md](W09-consulting.md),
  `services/oracle-brain/tests/test_process_consult.py`
- **Offline scope**: LangGraph four-role synthetic measured preview, persisted
  report with documentary/measured variants, role receipts, source-revocation
  denial, immutable release reference binding — verified.
- **Remaining open**: company generation and grading paused; private provider
  integration/admission for company reports; independent semantic/actual-event
  acceptance. No business acceptance.

---

All five rows are offline/synthetic accepted only. Private, hosted, live,
business, and elapsed acceptance remain false and open on #27/#58 under #24.
