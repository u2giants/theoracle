# S08 participation source composition on current main — evidence note

Recorded: 2026-10-22 2:35 PM EST. Branch `parent24-s08-compose-81742134` from origin/main bf788080.
Updated: 2026-10-25 EDT (round-3 review fixes). Task class `code` declared before writes.
No actual 21 SQL execution, no browser journey, no real Teams, no production,
no company data, no paid providers.

## Composition inventory

Parked head `81742134d6cb753d5bef4d0372eeea2117192e8b` composed additively. Eight effective
files. Byte-identity to the parked commit holds for the **added-and-unchanged** files only.
Two files are **updated** on this branch and are therefore NOT byte-identical to the
parked blob. Byte-identity pins are git blob bytes (`git show HEAD:path | sha256sum`),
never working-tree bytes (CRLF hosts diverge).

| File | Action | Byte-identical to parked `81742134…` | Git-blob SHA-256 at current HEAD |
|---|---|---|---|
| hosting/meeting_participation_service_v1.py | added | yes | `b3d8ae221fcfeb9b80c79c8b012f04f85341da3d8e6f154d0bd13377d242866b` |
| meetings/participation_authority_v1.py | updated (inherited authority repair) | **no** | `61d43aa171f91ab84fbf3f4518f7c77b52d591f07c1e3a673b2d73c1de1d62fa` |
| meetings/participation_control_contracts_v1.py | added | yes | `77c134400a6ee4192cfa58a81ef1b5cfa2d1f18c3feb8294022e4c764bfa440c` |
| sql/021_meeting_participation.sql | added | yes | `959a77553849616eee1d7b4eba4ed8a3bc146aaa432b7e0e2ca8d83ff17b2f7c` |
| tests/test_meeting_participation_control_v1.py | added | yes | `4444447c9618d51e983fac655d8e546dea16879982f301a4f1273aea9e4ec8fd` |
| tests/test_meeting_participation_sql.py | **updated (C-B docstring correction + L5 pins on this branch)** | **no** | `ad079a98f08e8f0d72fa41754de6cbf01cdd8e1328609c52c5b518e4ca3fb619` |
| tests/test_meeting_participation_v1.py | added | yes | `bff51a304e07462d528c4b1df3669e109a67166bead635954802b50c213303dc` |
| tests/test_meeting_participation_wire_v1.py | added | yes | `27fd04a6238652aff6da82ca95913885c8040bf084647f6700f62184eb19bebd` |

Current-main owners retained unchanged (byte-identical to both main and parked):
hosting/meeting_participation_v1.py, meetings/participation.py,
meetings/participation_runtime_v1.py, meetings/participation_wire_v1.py,
tests/test_meeting_participation.py.

Per-file git-blob SHA-256 pins are computed via
`git show HEAD:<path> | sha256sum` and recorded in **this evidence document**
(not in the review receipt — the receipt binds only the four artifact SHAs
and the head). The byte-identity column above states which files match the
parked blob; it does not claim byte-identity for files updated on this branch.

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
| test_outbound_replay.py | **not measured**; **expected to RUN** — `oracle_brain.meetings.delivery` exists at this head and base (`delivery.py` exports `DELIVERY_ACTION_PURPOSE` / `SenderCredentialProof`), so `find_spec` succeeds. Real skip condition (delivery absent, `test_outbound_replay.py:11-20`) does not hold. | record collect/run disposition (expected: run), not skip |

**Disposition for `test_outbound_replay.py`:** the module performs a
module-level `pytest.skip` only when `oracle_brain.meetings.delivery` is
absent. That module **exists at this head and base**
(`services/oracle-brain/oracle_brain/meetings/delivery.py` exports
`DELIVERY_ACTION_PURPOSE` and `SenderCredentialProof`), so on Linux
`importlib.util.find_spec` succeeds and the module is **expected to RUN**
(collect and execute) — not skip. Under the "skips fail" verifier
(`verify_workflow_integrity.py:2`) a skip would **not** be a green case — it is
a disposition that must be reported. The Linux rerun records the actual
disposition (**expected: run**). `test_meeting_participation.py` is likewise
unreported on this host.

## Sequencing — 21 SQL before the journey (M-E/H4)

The 21 SQL cases must go green against an owned synthetic database under the
sealed bootstrap **before** the journey one-shot runs. The runner enforces this
by invoking pytest on the SQL module after bootstrap and refusing unless
`21 passed` is observed (H4). Failure attribution: red 21 SQL + failed journey
stage = backend failure; green 21 SQL + failed journey stage = journey-adapter
failure. The 021 blob pin above remains a **git-blob** pin
(`git show HEAD:… | sha256sum`), never working-tree bytes.

## Remaining gate (source preservation is not acceptance)

1. Fresh-current complete composition review on a Linux host. **Per-suite
   collect-only counts for the six S08 gate modules are to be measured on that
   rerun** (four measured above + `test_meeting_participation.py` +
   `test_outbound_replay.py` unreported). No historical pure total is demanded
   or claimed.
2. Actual 21 SQL against an owned synthetic database under the **sealed
   20-entry `SYNTHETIC_MIGRATIONS` inventory** (omits 003/005; includes
   017/018/019/022/023/027) — **not** a contiguous 001–021 chain. The 21 SQL
   must go green before the journey runs (enforced in the runner, H4).
3. Browser → current-turn → sender → provider fixture → receipt path.
4. Full installed invitation / supervision / audience-currentness proof.
5. **Journey-orphaned negatives only** (M4): HTTP 201/429/5xx network
   negatives, exactly-one-network-invocation, host-disable-between-prepare-
   and-claim zero-network, observation-commit ACK loss as a journey sequence,
   permission-expiry before/after close matrix as a journey executor.
   Backend-covered negatives (revocation, lost-ACK, cooldown, cap, global-once,
   current-audience) are exercised by the 21 SQL and are **not** remaining
   gates — they are listed under the plan's backend-covered map (M4).
6. Real Teams chat/audience producer remains UNQUALIFIED; ACK never equals visible message
   or provider idempotency. Business-acceptance hold stays separate and closed.
7. mTLS stage-1 prerequisites (H8): peer-file minting, seals, openssl re-sign,
   certificates/WORKER fixtures, closed-denial matrix, peer-tamper → 503.
