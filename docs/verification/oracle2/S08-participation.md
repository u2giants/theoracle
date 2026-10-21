# S08 meeting participation — offline evidence

Status: offline building-block leaf landed (synthetic/invented only).
Recorded: 2026-10-20 (S08/S12 offline leaf landing).

## Offline tests

test_meeting_participation.py, test_outbound_replay.py (23 passed, 0 skipped)

## Landed modules

- services/oracle-brain/oracle_brain/meetings/__init__.py
- services/oracle-brain/oracle_brain/meetings/participation.py
- services/oracle-brain/oracle_brain/meetings/delivery.py
- services/oracle-brain/oracle_brain/workflows/meeting_turn.py

Import guards no longer trigger; named tests activate and pass without skip.
Pure/deterministic only — no provider, no network, no DB.

## Notes

Ported from origin/claude/s08-meeting-participation. verify_phase.py S08 --mode
offline requires ORACLE2_TEST_ADMIN_URL / ORACLE2_TEST_CONFIRMED_URL (isolated
Postgres/FalkorDB); those were absent so the phase script could not run. Pure
pytest run covers both named files.

R8 trust model: authority is the Ed25519 signature alone — no mutable
in-process mint registry. Credential proofs
(`sender-credential:v1`), delivery actions (`delivery-action:v1`) and
participation enable (`participation-enable:v1`) each require a
host-issued Ed25519 seal over the purpose-tagged field wire.
`mark_sent`/`mark_failed` verify a signature over the exact action
payload (intent id, status, timestamp) — registry membership is not
proof and no WeakSet/id-registry remains to mutate through
`__closure__`. The signer (`oracle_brain.seal_signer`) signs only
structured `{"purpose", "fields"}` requests whose purpose is on a fixed
allowlist; unknown purpose, free-form payload bytes and malformed
requests are refused before any key use. Signing runs only as a process
entrypoint (`python -m oracle_brain.seal_signer`) with a one-shot
stdin/stdout handshake. The verify path (`oracle_brain.seal`) holds only
the public key and cannot sign. The parent process never holds private
key material or `ORACLE2_SEAL_PRIVATE_KEY*` environment variables —
only the key-file path (`ORACLE2_SEAL_SIGNER_KEY_FILE`). The signer
child is spawned with an explicit scrubbed environment. Tests produce
host-issued seals via the signer CLI (`tests/seal_testkit.py`).

Remaining trust boundary (honest): the key file is readable by the same
OS user that runs the signer process. Restricting file ACLs or running
the signer under a separate OS user is a host-wiring concern outside
this offline leaf and is not claimed here. No secret is committed.

## Live acceptance

Not accepted / business and live acceptance stay closed.
This does not close #32. No employees, no company data, no production actions.
