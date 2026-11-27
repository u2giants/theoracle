"""The ``openrouter-call`` structured log line (#1493)."""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from brain import embed as embed_mod
from brain import llm
from brain.config import Settings


def _lines(caplog) -> list[dict]:
    return [
        json.loads(r.getMessage().split(" ", 1)[1])
        for r in caplog.records
        if r.getMessage().startswith("openrouter-call ")
    ]


def _settings() -> Settings:
    return Settings(openrouter_api_key="k", straitly_api_key="sk")


def test_chat_success_logs_host(monkeypatch, caplog) -> None:
    body = {"provider": "DeepInfra", "choices": [{"message": {"content": "hi"}}]}
    monkeypatch.setattr(
        llm.httpx, "post", lambda *a, **k: httpx.Response(200, json=body)
    )
    caplog.set_level(logging.INFO, logger="brain.llm")
    llm.post_chat_with_rescue(
        {"model": "m"},
        settings=_settings(),
        timeout=5,
        error_cls=RuntimeError,
        label="answer",
    )
    (line,) = _lines(caplog)
    assert line["host"] == "DeepInfra" and line["ok"] is True
    assert line["caller"] == "answer" and line["http_status"] == 200
    assert line["error_class"] is None and line["model"] == "m"
    assert isinstance(line["latency_ms"], int)


@pytest.mark.parametrize(
    ("status", "expected"), [(429, "http_429"), (503, "http_5xx"), (400, "other")]
)
def test_chat_http_errors(monkeypatch, caplog, status, expected) -> None:
    monkeypatch.setattr(
        llm.httpx, "post", lambda *a, **k: httpx.Response(status, text="no")
    )
    caplog.set_level(logging.INFO, logger="brain.llm")
    with pytest.raises(RuntimeError):
        llm.post_chat_with_rescue(
            {"model": "m"},
            settings=_settings(),
            timeout=5,
            error_cls=RuntimeError,
            label="x",
        )
    (line,) = _lines(caplog)
    assert line["error_class"] == expected and line["host"] == "unknown"


def test_chat_timeout_and_empty(monkeypatch, caplog) -> None:
    def boom(*a, **k):
        raise httpx.ReadTimeout("slow")

    monkeypatch.setattr(llm.httpx, "post", boom)
    caplog.set_level(logging.INFO, logger="brain.llm")
    with pytest.raises(httpx.ReadTimeout):
        llm.post_chat_with_rescue(
            {"model": "m"},
            settings=_settings(),
            timeout=5,
            error_cls=RuntimeError,
            label="x",
        )
    assert _lines(caplog)[-1]["error_class"] == "timeout"
    caplog.clear()
    empty = {"choices": [{"message": {"content": ""}}]}
    monkeypatch.setattr(
        llm.httpx, "post", lambda *a, **k: httpx.Response(200, json=empty)
    )
    with pytest.raises(RuntimeError):
        llm.post_chat_with_rescue(
            {"model": "m"},
            settings=_settings(),
            timeout=5,
            error_cls=RuntimeError,
            label="x",
        )
    assert [ln["error_class"] for ln in _lines(caplog)] == ["empty", "empty"]


def test_embed_logs(monkeypatch, caplog) -> None:
    body = {"provider": "OpenAI", "data": [{"index": 0, "embedding": [0.1]}]}
    monkeypatch.setattr(
        embed_mod.httpx, "post", lambda *a, **k: httpx.Response(200, json=body)
    )
    monkeypatch.setattr(embed_mod, "stage_model", lambda s, stage: "m/embed")
    caplog.set_level(logging.INFO, logger="brain.llm")
    embed_mod._post_embeddings_once(["a"], _settings())
    (line,) = _lines(caplog)
    assert line["caller"] == "embed" and line["host"] == "OpenAI" and line["ok"]
