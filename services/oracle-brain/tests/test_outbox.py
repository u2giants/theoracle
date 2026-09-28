from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Event, Process
import time
from threading import Barrier

import psycopg
import pytest

from oracle_brain.graph.falkor import FalkorGraphStore
from oracle_brain.outbox import enqueue_accepted, lease_next, make_receipt, mark_delivered


def test_concurrent_first_revisions_never_regress(admin_url):
    workspace, assertion = uuid4(), uuid4()
    barrier = Barrier(2)

    def accept(revision):
        barrier.wait()
        try:
            enqueue_accepted(admin_url, workspace_id=workspace,
                             assertion_id=assertion, revision=revision,
                             payload={"revision": revision})
            return "accepted"
        except ValueError as error:
            assert str(error) == "revision must increase"
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(accept, (1, 2)))
    with psycopg.connect(admin_url) as connection:
        accepted = connection.execute(
            "SELECT revision FROM oracle2.accepted WHERE workspace_id=%s AND assertion_id=%s",
            (workspace, assertion),
        ).fetchone()[0]
        outbox_revisions = [row[0] for row in connection.execute(
            "SELECT revision FROM oracle2.outbox WHERE workspace_id=%s AND assertion_id=%s ORDER BY revision",
            (workspace, assertion),
        ).fetchall()]
    assert accepted == 2
    assert results.count("accepted") >= 1
    assert outbox_revisions[-1] == accepted
    assert outbox_revisions in ([2], [1, 2])


def _write_then_wait(url, workspace, assertion, payload, ready):
    FalkorGraphStore(url).project(workspace, assertion, 1, payload)
    ready.set()
    time.sleep(30)


def test_replay_survives_crash_and_receipt_is_authenticated(admin_url, confirmed_url):
    workspace, assertion = uuid4(), uuid4()
    event_id = enqueue_accepted(admin_url, workspace_id=workspace,
                                assertion_id=assertion, revision=1,
                                payload={"synthetic": True})
    # Kill a real process after graph write but before receipt.
    event = lease_next(admin_url, lease_seconds=1)
    assert event and event.event_id == event_id
    ready = Event()
    worker = Process(target=_write_then_wait,
                     args=(confirmed_url, workspace, assertion, event.payload, ready))
    worker.start()
    assert ready.wait(10), "child did not write graph before timeout"
    worker.terminate()
    worker.join(5)
    assert worker.exitcode is not None and worker.exitcode != 0
    graph = FalkorGraphStore(confirmed_url)
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
