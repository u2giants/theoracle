# S08 participation source composition on current main — evidence note

Recorded: 2026-10-22 2:35 PM EST. Branch `parent24-s08-compose-81742134` from origin/main bf788080.
Task class `code` declared before writes. No actual 21 SQL execution, no browser journey,
no real Teams, no production, no company data, no paid providers.

## Composition inventory

Parked head `81742134d6cb753d5bef4d0372eeea2117192e8b` composed additively. Eight effective
files. Byte-identity to the parked commit holds for the seven **added** files only;
`participation_authority_v1.py` is **updated** (inherited authority repair) and is
therefore NOT byte-identical to the parked blob. Byte-identity pins are git blob
bytes (`git show HEAD:path | sha256sum`), never working-tree bytes (CRLF hosts diverge):

| File | Action | Byte-identical to parked `81742134…` |
|---|---|---|
| hosting/meeting_participation_service_v1.py | added | yes |
| meetings/participation_authority_v1.py | updated (inherited authority repair) | **no** |
| meetings/participation_control_contracts_v1.py | added | yes |
| sql/021_meeting_participation.sql | added | yes |
| tests/test_meeting_participation_control_v1.py | added | yes |
| tests/test_meeting_participation_sql.py | added | yes |
| tests/test_meeting_participation_v1.py | added | yes |
| tests/test_meeting_participation_wire_v1.py | added | yes |

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
This pin is **git blob bytes** (`git show HEAD:services/oracle-brain/sql/021_meeting_participation.sql | sha256sum`),
not working-tree bytes; a CRLF checkout measures differently and must not be quoted as the pin.

## Registration

- `SYNTHETIC_MIGRATIONS` in `scripts/oracle2/verify_workflow_integrity.py`: `021_meeting_participation.sql`
  inserted after `020_meeting_capture.sql`, before `022_consolidated_answer_delivery.sql` (20 entries).
- Four mandatory suites registered: `meeting_participation_control_v1`, `meeting_participation_v1`,
  `meeting_participation_wire_v1` in DOCUMENTARY; `meeting_participation_sql` in EVENT.
- `scripts/oracle2/verify_phase.py` S08_TESTS extended with the four new test modules.
- `dev/oracle2/test_canonical_schema.py` `_catalog` conditional for 021 public function signatures.
- `services/oracle-brain/tests/test_operating_model_verifier.py` SYNTHETIC_MIGRATIONS assertions updated
  (`[-8:]` → `[-9:]`); the three registration assertions pass.

## Migration inventory (actual sealed fact — no contiguous chain)

There is **no contiguous `001–021` chain**. The sealed inventory is
`SYNTHETIC_MIGRATIONS` in `scripts/oracle2/verify_workflow_integrity.py:112-117`:

`001, 002, 004, 006, 007, 008, 009, 010, 011, 012, 013, 014, 017, 018, 019, 020, 021, 022, 023, 027`

(20 entries; **omits `003` and `005`; includes `017/018/019/022/023/027`**). The
journey and the 21 SQL use the sealed bootstrap
(`dev/oracle2/test_canonical_schema.py` `bootstrap_canonical_test_schema`), not a
custom contiguous chain.

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

## S08 gate files — all six (M-A)

`scripts/oracle2/verify_phase.py:96-103` gates **six** modules. Disposition at
this head:

| Module | This host | Linux rerun target |
|---|---|---|
| test_meeting_participation.py | **not measured** | collect-only count to be measured |
| test_meeting_participation_control_v1.py | clean (all pass) | reconcile |
| test_meeting_participation_sql.py | 21 collected, NOT executed | must go green before the journey runs |
| test_meeting_participation_v1.py | 31 passed / 57 failed / 2 errors (Windows `os.getuid()`) | reconcile on Linux |
| test_meeting_participation_wire_v1.py | all pass / 2 errors (env-var length) | reconcile on Linux |
| test_outbound_replay.py | **not measured**; module-skips when `oracle_brain.meetings.delivery` is absent (`test_outbound_replay.py:11-20`) | record skip-vs-pass explicitly |

**Skip-vs-pass for `test_outbound_replay.py`:** the module performs a
module-level `pytest.skip` when `oracle_brain.meetings.delivery` is absent (not
built on main). Under the "skips fail" verifier
(`verify_workflow_integrity.py:2`) a skip is **not** a green case — it is a
disposition that must be reported. The Linux rerun records whether the module
skipped or ran. `test_meeting_participation.py` is likewise unreported on this
host.

## Sequencing — 21 SQL before the journey (M-E)

The 21 SQL cases must go green against an owned synthetic database under the
sealed bootstrap **before** the journey one-shot runs. Failure attribution:
red 21 SQL + failed journey stage = backend failure; green 21 SQL + failed
journey stage = journey-adapter failure. The 021 blob pin above remains a
**git-blob** pin (`git show HEAD:… | sha256sum`), never working-tree bytes.

## Remaining gate (source preservation is not acceptance)

1. Fresh-current complete composition review on a Linux host. **Per-suite
   collect-only counts for the six S08 gate modules are to be measured on that
   rerun** (four measured above + `test_meeting_participation.py` +
   `test_outbound_replay.py` unreported). No "full 256 pure" figure is demanded
   or claimed.
2. Actual 21 SQL against an owned synthetic database under the **sealed
   20-entry `SYNTHETIC_MIGRATIONS` inventory** (omits 003/005; includes
   017/018/019/022/023/027) — **not** a contiguous 001–021 chain. The 21 SQL
   must go green before the journey runs.
3. Browser → current-turn → sender → provider fixture → receipt path.
4. Full installed invitation / supervision / audience-currentness proof.
5. Revocation, lost-ACK, cooldown, cap, global-once, current-audience negatives.
6. Real Teams chat/audience producer remains UNQUALIFIED; ACK never equals visible message
   or provider idempotency. Business-acceptance hold stays separate and closed.
