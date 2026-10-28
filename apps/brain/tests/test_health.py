"""Step 0 gate: the health endpoint reports the database."""

from __future__ import annotations

from fastapi.testclient import TestClient

from brain.main import app


def test_health_reports_db() -> None:
    """GET /health must report ok true and db true against a live Postgres."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"] is True
    assert "graph" in body
