# S13 full-recovery synthetic DR exercise — evidence

**Date:** 2026-10-26 (EDT)
**Branch:** `codex/parent24-s13-full-recovery-20261026`
**Base:** `4e365535f294c28a804827bd9293885bd09b9e6c`
**Class:** code (offline synthetic DB)
**Host:** edge-dev3

## JUnit

**11 passed, 0 failed, 0 errors, 0 skipped** (4.257s).

| Artifact | SHA-256 |
|----------|---------|
| `s13-full-recovery-junit.xml` | `0070bccae6de7bf145ef5ddb836db98941e1d3493d4184e48651339c667d18bf` |
| `dr-result.json` | `f3080cb60932db8b8c951b4f8c9dd8cc3f6e4b13be6881b6ea9186f9bb3fed0f` |

## Measured

- RTO: 1.275 s (target <= 3600 s)
- Backup: 0.212 s (target <= 900 s)
- RPO exposure: 0.0 s (exercise-specific; production RPO depends on backup cadence)
- Scale: 25 events, 8 artifacts, 5 conversation events, 1 once-intent, 1 cost observation
- Dump: 1,249,718 bytes, 120 tables restored
- Archive: 20,480 bytes, 9 files

## Files

- `s13-full-recovery-junit.xml` — exact JUnit XML
- `dr-result.json` — full measured gate results
- `runner-result.json` — runner identity and elapsed

## Cleanup

Owned synthetic worker project `oracle2-synthetic-p24full-mimo-*` torn down
(`docker compose down -v`). Databases dropped in fixture finally block.
No production, shared-db, or company resources touched.

## Not proven

See S13-recovery.md "UNPROVEN gates (exact) after this exercise".
