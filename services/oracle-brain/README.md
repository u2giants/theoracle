# Oracle 2 foundation (S02)

This service is an isolated, synthetic-only foundation. Postgres owns accepted
assertions, appointments, checkpoints, outbox events and receipts. FalkorDB is
a replaceable projection. No business procedure is accepted from Graphiti or
the graph without a separately authorized review transaction.

## Local / CI setup

Use a host with Docker Compose. No production credentials are needed.

```bash
docker compose -f dev/oracle2/compose.yaml up -d --wait
uv sync --project services/oracle-brain --frozen --extra test
export ORACLE2_TEST_ADMIN_URL=postgresql://oracle2_admin:oracle2_local_admin_only@127.0.0.1:55432/oracle2
export ORACLE2_TEST_CANDIDATE_URL=redis://:oracle2_candidate_local_only@127.0.0.1:56379
export ORACLE2_TEST_CONFIRMED_URL=redis://:oracle2_confirmed_local_only@127.0.0.1:56380
export ORACLE2_TEST_BLOB_ENDPOINT=http://127.0.0.1:54566
services/oracle-brain/.venv/bin/python scripts/oracle2/init_local_stores.py
python3 scripts/oracle2/verify_phase.py S02 --mode offline
docker compose -f dev/oracle2/compose.yaml down --volumes
```

These passwords are fixed synthetic test fixtures, valid only for loopback
services. The compose volumes are isolated from the legacy Oracle database.
Checkpoint tables use a third local database role (`oracle2_checkpoint`) for
the trusted conversation gateway. The extraction and projection roles cannot
read checkpoint rows or receive that role's credential.

The Python lock targets Python 3.12. The Trigger Python extension uses the
hash-pinned exported worker requirements. Regenerate it after a lock change:

```bash
uv export --project services/oracle-brain --frozen --format requirements-txt --no-dev --no-emit-project --emit-index-url --output-file apps/workers/oracle2-requirements.txt
```

The existing Trigger project must never receive Oracle 2 tasks. Separate
extractor and projector configs require distinct project references and
separately scoped credentials before an isolated preview build. These preview
projects are unprovisioned in S02 until their exact targets receive the
required independent infrastructure approval. The full dependency bundle is
not yet qualified for Trigger cold start or cancellation.
