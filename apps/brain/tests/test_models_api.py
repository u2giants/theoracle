"""GET /models reports the env-configured model seats to the admin model page."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from conftest import TEST_TOKEN
from fastapi.testclient import TestClient

from brain.config import get_settings

SEAT_KEYS = (
    "vision",
    "embed",
    "embed_dims",
    "flat_fallback",
    "relations",
    "resolve",
    "reports",
    "answer",
    "recommend",
    "grade",
    "scaledown_enabled",
)


@pytest.fixture()
def fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Rebuild the settings cache around each test so env edits land."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_models_requires_the_token(client: TestClient) -> None:
    assert client.get("/models").status_code == 401
    assert (
        client.get("/models", headers={"x-brain-token": "wrong"}).status_code == 401
    )


def test_models_reports_env_seats(
    client: TestClient, fresh_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN_VISION_MODEL", "openai/test-vision")
    monkeypatch.setenv("BRAIN_EMBED_MODEL", "openai/test-embed")
    monkeypatch.setenv("BRAIN_EMBED_DIMS", "1024")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "anthropic/test-frontier")
    monkeypatch.setenv("BRAIN_CHAT_MODEL", "anthropic/test-chat")
    monkeypatch.setenv("BRAIN_EVAL_MODEL", "anthropic/test-eval")
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    get_settings.cache_clear()

    response = client.get("/models", headers={"x-brain-token": TEST_TOKEN})
    assert response.status_code == 200
    models = response.json()["models"]
    assert set(models) == set(SEAT_KEYS)
    assert models["vision"] == "openai/test-vision"
    assert models["embed"] == "openai/test-embed"
    assert models["embed_dims"] == 1024
    assert models["flat_fallback"] == "anthropic/test-frontier"
    assert models["relations"] == "anthropic/test-frontier"
    assert models["resolve"] == "anthropic/test-frontier"
    assert models["reports"] == "anthropic/test-frontier"
    assert models["answer"] == "anthropic/test-chat"
    assert models["recommend"] == "anthropic/test-frontier"
    assert models["grade"] == "anthropic/test-eval"
    assert models["scaledown_enabled"] is True


def test_models_chat_and_eval_fall_back_to_frontier(
    client: TestClient, fresh_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "anthropic/test-frontier")
    monkeypatch.delenv("BRAIN_CHAT_MODEL", raising=False)
    monkeypatch.delenv("BRAIN_EVAL_MODEL", raising=False)
    get_settings.cache_clear()

    response = client.get("/models", headers={"x-brain-token": TEST_TOKEN})
    assert response.status_code == 200
    models = response.json()["models"]
    assert models["answer"] == "anthropic/test-frontier"
    assert models["grade"] == "anthropic/test-frontier"


def test_models_reports_nulls_when_unset(
    client: TestClient, fresh_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key in (
        "BRAIN_VISION_MODEL",
        "BRAIN_EMBED_MODEL",
        "BRAIN_FRONTIER_MODEL",
        "BRAIN_CHAT_MODEL",
        "BRAIN_EVAL_MODEL",
        "BRAIN_SCALEDOWN_ENABLED",
    ):
        monkeypatch.delenv(key, raising=False)
    get_settings.cache_clear()

    response = client.get("/models", headers={"x-brain-token": TEST_TOKEN})
    assert response.status_code == 200
    models = response.json()["models"]
    assert models["vision"] is None
    assert models["embed"] is None
    assert models["flat_fallback"] is None
    assert models["relations"] is None
    assert models["answer"] is None
    assert models["grade"] is None
    assert models["scaledown_enabled"] is False
    assert models["embed_dims"] == 1024
