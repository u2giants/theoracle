from uuid import uuid4

import psycopg
import pytest

from oracle_brain.graph.falkor import FalkorGraphStore
from oracle_brain.outbox import enqueue_accepted, lease_next, make_receipt, mark_delivered


def test_replay_survives_crash_and_receipt_is_authenticated(admin_url, confirmed_url):
    workspace, assertion = uuid4(), uuid4()
    event_id = enqueue_accepted(admin_url, workspace_id=workspace,
                                assertion_id=assertion, revision=1,
                                payload={"synthetic": True})
    # A lease models a worker killed after the graph write but before receipt.
    event = lease_next(admin_url, lease_seconds=1)
    assert event and event.event_id == event_id
    graph = FalkorGraphStore(confirmed_url)
    graph.project(workspace, assertion, 1, event.payload)
    with psycopg.connect(admin_url) as connection:
        connection.execute("UPDATE oracle2.outbox SET lease_until=now()-interval '1 second' WHERE event_id=%s", (event_id,))
    replay = lease_next(admin_url)
    assert replay and replay.event_id == event_id and replay.attempts == 2
    graph.project(workspace, assertion, 1, replay.payload)
    assert graph.query(workspace)[0]["revision"] == 1
    good_key = b"synthetic-projection-key-32-bytes-minimum"
    forged = make_receipt(replay, b"attacker-key-at-least-32-bytes-long", "oracle2-projector")
    with pytest.raises(PermissionError):
        mark_delivered(admin_url, event_id=event_id, receipt=forged, secret=good_key)
    receipt = make_receipt(replay, good_key, "oracle2-projector")
    mark_delivered(admin_url, event_id=event_id, receipt=receipt, secret=good_key)
    with psycopg.connect(admin_url) as connection:
        assert connection.execute("SELECT delivered_at IS NOT NULL FROM oracle2.outbox WHERE event_id=%s", (event_id,)).fetchone()[0]
