# S08 participation source composition on current main — evidence note

Recorded: 2026-10-22 2:35 PM EST. Branch `parent24-s08-compose-81742134` from origin/main bf788080.
Task class `code` declared before writes. No actual 21 SQL execution, no browser journey,
no real Teams, no production, no company data, no paid providers.

## Composition inventory

Parked head `81742134d6cb753d5bef4d0372eeea2117192e8b` composed additively. Eight effective
files, all staged blobs byte-identical to that commit:

| File | Action |
|---|---|
| hosting/meeting_participation_service_v1.py | added |
| meetings/participation_authority_v1.py | updated (inherited authority repair) |
| meetings/participation_control_contracts_v1.py | added |
| sql/021_meeting_participation.sql | added |
| tests/test_meeting_participation_control_v1.py | added |
| tests/test_meeting_participation_sql.py | added |
| tests/test_meeting_participation_v1.py | added |
| tests/test_meeting_participation_wire_v1.py | added |

Current-main owners retained unchanged (byte-identical to both main and parked):
hosting/meeting_participation_v1.py, meetings/participation.py,
meetings/participation_runtime_v1.py, meetings/participation_wire_v1.py,
tests/test_meeting_participation.py.

Authority repair preserves: explicit password/port in the fixed URL guard, numeric pin and
PG* deny in `protected_sql_connection_v1._connection_v1`, original deadline and prearmed
timeouts via `request_deadline_v1.sql_execute_v1` for all five sends, guarded BEGIN/COMMIT
and post-close currentness. Mutation is marked attempted BEFORE the guarded send;
after-I/O refusal/commit/close uncertainty remains typed UNKNOWN with read-only
reconciliation and no resend.

Connector/common-password ownership audit: `_connection_v1` is the single connection owner
(no raw `psycopg.connect` in the authority); `sql_execute_v1` is the single send owner
(no raw `connection.execute` in the authority). Explicit password is required by the
authority URL guard before connect; port is required by both. Canonical 021 SHA-256 is
`959a77553849616eee1d7b4eba4ed8a3bc146aaa432b7e0e2ca8d83ff17b2f7c` (63753 bytes, LF).

## Registration

- `SYNTHETIC_MIGRATIONS` in `scripts/oracle2/verify_workflow_integrity.py`: `021_meeting_participation.sql`
  inserted after `020_meeting_capture.sql`, before `022_consolidated_answer_delivery.sql` (20 entries).
- Four mandatory suites registered: `meeting_participation_control_v1`, `meeting_participation_v1`,
  `meeting_participation_wire_v1` in DOCUMENTARY; `meeting_participation_sql` in EVENT.
- `scripts/oracle2/verify_phase.py` S08_TESTS extended with the four new test modules.
- `dev/oracle2/test_canonical_schema.py` `_catalog` conditional for 021 public function signatures.
- `services/oracle-brain/tests/test_operating_model_verifier.py` SYNTHETIC_MIGRATIONS assertions updated
  (`[-8:]` → `[-9:]`); the three registration assertions pass.

## Pure results (this Windows host)

| Suite | Passed | Failed | Errors | Note |
|---|---|---|---|---|
| test_meeting_participation_control_v1.py | all | 0 | 0 | clean |
| test_meeting_participation_wire_v1.py | all | 0 | 2 | errors are Windows env-var length on one huge parametrized id |
| test_meeting_participation_v1.py | 31 | 57 | 2 | failures are `os.getuid()` absent on Windows (CA ownership check); errors same env-var limit |
| test_meeting_participation_sql.py | — | — | — | 21 cases collected, NOT executed |

Historical 256 pure / 21 SQL was a Linux run and is not re-claimed here. SQL021 bytes and
all 21 SQL case bytes unchanged from the parked source. Registration assertions and all
edited modules compile clean.

## Remaining gate (source preservation is not acceptance)

1. Fresh-current complete composition review on a Linux host (full 256 pure).
2. Actual 21 SQL against an owned synthetic database under the canonical 001–021 chain.
3. Browser → current-turn → sender → provider fixture → receipt path.
4. Full installed invitation / supervision / audience-currentness proof.
5. Revocation, lost-ACK, cooldown, cap, global-once, current-audience negatives.
6. Real Teams chat/audience producer remains UNQUALIFIED; ACK never equals visible message
   or provider idempotency. Business-acceptance hold stays separate and closed.
