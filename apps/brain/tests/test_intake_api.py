"""Step 1.5: admin-only thread listing, never message text."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient


def test_listing_is_admin_only_and_has_no_text(
    client: TestClient,
    user_headers: dict[str, str],
    admin_headers: dict[str, str],
    db: Any,
) -> None:
    db.execute(
        "INSERT INTO cmap.intake_thread (origin, thread_key, title, verdict) "
        "VALUES ('email', 'api-k1', 'synthetic', 'kept') ON CONFLICT DO NOTHING"
    )
    db.commit()
    assert client.get("/intake/threads").status_code == 401
    assert client.get("/intake/threads", headers=user_headers).status_code == 403
    r = client.get("/intake/threads?verdict=kept", headers=admin_headers)
    assert r.status_code == 200
    rows = [x for x in r.json() if x["title"] == "synthetic"]
    assert rows and "body_text" not in rows[0] and "thread_key" not in rows[0]
    assert (
        client.get("/intake/threads?verdict=bad", headers=admin_headers).status_code
        == 422
    )
