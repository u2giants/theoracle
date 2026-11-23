"""Step 0 gate: the health endpoint reports the database."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from brain import main as main_mod
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


def test_check_graph_uses_bounded_socket_timeout(monkeypatch: Any) -> None:
    """Advisory /health FalkorDB probe never blocks without a socket timeout."""
    seen: dict[str, Any] = {}

    class _FakeClient:
        def execute_command(self, cmd: str) -> str:
            seen["cmd"] = cmd
            return "PONG"

    def _fake_from_url(url: str, **kwargs: Any) -> _FakeClient:
        seen["url"] = url
        seen["kwargs"] = kwargs
        return _FakeClient()

    monkeypatch.setattr(main_mod.FalkorDB, "from_url", _fake_from_url)
    assert main_mod.check_graph() is True
    assert seen["cmd"] == "PING"
    assert seen["kwargs"]["socket_timeout"] == 2.0
    assert seen["kwargs"]["socket_connect_timeout"] == 2.0
