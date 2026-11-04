"""Per-stage model seats chosen on the admin page override the env seats."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from conftest import TEST_TOKEN
from fastapi.testclient import TestClient

from brain.config import get_settings
from brain.resolve.resolve import _Frontier
from brain.seats import STAGES, stage_model


@pytest.fixture()
def env_seats(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier")
    monkeypatch.setenv("BRAIN_CHAT_MODEL", "test/chat")
    monkeypatch.delenv("BRAIN_EVAL_MODEL", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_env_seats_apply_without_page_choices(env_seats: None) -> None:
    settings = get_settings()
    assert stage_model(settings, "relations") == "test/frontier"
    assert stage_model(settings, "answer") == "test/chat"
    assert stage_model(settings, "grade") == "test/frontier"


def test_unknown_stage_is_rejected(env_seats: None) -> None:
    with pytest.raises(ValueError):
        stage_model(get_settings(), "nonsense")


def test_page_seat_overrides_one_stage_only(
    client: TestClient, env_seats: None, admin_headers: dict[str, str]
) -> None:
    response = client.put(
        "/models/reports", json={"model": "test/reports"}, headers=admin_headers
    )
    assert response.status_code == 200
    assert response.json()["reembed_queued"] is False
    settings = get_settings()
    assert stage_model(settings, "reports") == "test/reports"
    assert stage_model(settings, "resolve") == "test/frontier"

    body = client.get("/models", headers={"x-brain-token": TEST_TOKEN}).json()
    assert body["models"]["reports"] == "test/reports"
    assert body["models"]["resolve"] == "test/frontier"
    assert body["seats"]["reports"]["source"] == "page"
    assert body["seats"]["resolve"]["source"] == "env"
    assert set(body["seats"]) == set(STAGES)


def test_frontier_client_calls_its_own_stage_seat(
    client: TestClient,
    env_seats: None,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from brain.resolve import resolve as resolve_mod

    client.put(
        "/models/recommend", json={"model": "test/recommend"}, headers=admin_headers
    )
    seen: list[str | None] = []

    def fake(
        messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del messages
        seen.append(settings.brain_frontier_model)
        return {
            "choices": [{"message": {"content": "{}"}}],
            "usage": {"total_tokens": 1},
        }

    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    _Frontier(get_settings(), "recommend").ask("x")
    _Frontier(get_settings()).ask("x")
    assert seen == ["test/recommend", "test/frontier"]


def test_changing_embeddings_queues_a_reembed(
    client: TestClient, env_seats: None, admin_headers: dict[str, str], db: Any
) -> None:
    response = client.put(
        "/models/embed", json={"model": "test/embed-2"}, headers=admin_headers
    )
    assert response.json()["reembed_queued"] is True
    kinds = [row[0] for row in db.execute("SELECT kind FROM cmap.job").fetchall()]
    assert kinds == ["reembed"]


def test_seating_needs_an_admin(
    client: TestClient, env_seats: None, user_headers: dict[str, str]
) -> None:
    response = client.put("/models/answer", json={"model": "x/y"}, headers=user_headers)
    assert response.status_code == 403


def test_unknown_stage_put_is_404(
    client: TestClient, env_seats: None, admin_headers: dict[str, str]
) -> None:
    response = client.put(
        "/models/nonsense", json={"model": "x/y"}, headers=admin_headers
    )
    assert response.status_code == 404


# --- #359 review findings -------------------------------------------------


def test_embed_seat_rolls_back_when_reembed_job_insert_fails(
    client: TestClient,
    env_seats: None,
    admin_headers: dict[str, str],
    db: Any,
) -> None:
    """Finding 2: the seat and its reembed job are one transaction."""
    db.execute(
        "ALTER TABLE cmap.job ADD CONSTRAINT t359_no_reembed CHECK (kind <> 'reembed')"
    )
    db.commit()
    try:
        failing = TestClient(client.app, raise_server_exceptions=False)
        response = failing.put(
            "/models/embed", json={"model": "test/embed-2"}, headers=admin_headers
        )
        assert response.status_code == 500
        assert db.execute("SELECT count(*) FROM cmap.model_seat").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM cmap.job").fetchone()[0] == 0
    finally:
        db.execute("ALTER TABLE cmap.job DROP CONSTRAINT t359_no_reembed")
        db.commit()


def test_seat_read_failure_is_not_cached_as_no_seats(
    client: TestClient,
    env_seats: None,
    admin_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 4: a DB blip keeps the last good seats and is retried, not cached."""
    from brain import seats as seats_mod

    client.put("/models/reports", json={"model": "test/reports"}, headers=admin_headers)
    settings = get_settings()
    assert stage_model(settings, "reports") == "test/reports"  # cached now

    real_pool = seats_mod.get_pool

    class Broken:
        def connection(self) -> Any:
            raise RuntimeError("db blip")

    monkeypatch.setattr(seats_mod, "_cache_at", 0.0)  # expire the cache
    monkeypatch.setattr(seats_mod, "get_pool", lambda: Broken())
    assert stage_model(settings, "reports") == "test/reports"  # last good seat
    assert seats_mod._cache_at == 0.0  # the failure was not cached

    monkeypatch.setattr(seats_mod, "get_pool", real_pool)
    assert stage_model(settings, "reports") == "test/reports"
    assert seats_mod._cache_at > 0.0
