"""Repair plan: every endpoint the plan adds needs the token and an admin."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from test_flat import _seed_text

NEW_ENDPOINTS = [
    "/sources/reread-all",
    f"/sources/{uuid4()}/reread",
    "/jobs/retry-failed",
]


@pytest.mark.parametrize("path", NEW_ENDPOINTS)
def test_new_endpoints_require_token(
    path: str, client: Any, user_headers: dict[str, str]
) -> None:
    assert client.post(path).status_code == 401
    assert client.post(path, headers={"x-brain-token": "wrong"}).status_code == 401
    assert client.post(path, headers=user_headers).status_code == 403


def test_reread_actions_queue_once(
    db: Any, client: Any, admin_headers: dict[str, str]
) -> None:
    """Re-read queues one job per source, never a second while one waits,
    and retry-failed puts failed jobs back with their retries restored."""
    first = _seed_text(db, "The buyer waits.", "one")
    _seed_text(db, "The vendor ships.", "two")
    db.execute("UPDATE cmap.source SET read_state = 'partial', read_error = 'x'")
    db.commit()
    assert client.post("/sources/reread-all", headers=admin_headers).json() == {
        "sources": 2,
        "queued": 2,
    }
    assert client.post("/sources/reread-all", headers=admin_headers).json()["queued"] == 0
    assert client.post(f"/sources/{first}/reread", headers=admin_headers).json() == {
        "id": first,
        "queued": False,
    }
    assert client.post(f"/sources/{uuid4()}/reread", headers=admin_headers).status_code == 404
    db.commit()
    assert db.execute(
        "SELECT count(*) FROM cmap.source WHERE read_state = 'queued' AND read_error IS NULL"
    ).fetchone()[0] == 2
    db.execute("UPDATE cmap.job SET state = 'failed', attempts = 3, error = 'boom'")
    db.commit()
    body = client.post("/jobs/retry-failed", headers=admin_headers).json()
    assert body == {"requeued": 2, "by_kind": {"read_source": 2}}
    db.commit()
    assert db.execute(
        "SELECT count(*) FROM cmap.job WHERE state = 'queued' AND attempts = 0"
    ).fetchone()[0] == 2
