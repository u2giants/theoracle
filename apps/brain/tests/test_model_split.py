"""Conversation, heavy-work and grader models are separate env settings."""

from __future__ import annotations

from typing import Any

import pytest

from brain.answer import answer as answer_mod
from brain.config import Settings, chat_model, eval_model
from brain.eval import run as eval_mod


class _Resp:
    status_code = 200

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "{}"}}]}


def _settings(**kw: Any) -> Settings:
    base = {"openrouter_api_key": "k", "brain_frontier_model": "heavy/model"}
    base.update(kw)
    return Settings(**base)


def test_chat_and_eval_fall_back_to_frontier() -> None:
    s = _settings()
    assert chat_model(s) == "heavy/model"
    assert eval_model(s) == "heavy/model"


def test_answers_use_chat_model_and_grader_uses_eval_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append(kw["json"]["model"])
        return _Resp()

    monkeypatch.setattr(answer_mod.httpx, "post", fake_post)
    monkeypatch.setattr(eval_mod.httpx, "post", fake_post)
    s = _settings(brain_chat_model="chat/model", brain_eval_model="grade/model")
    answer_mod._post_chat([{"role": "user", "content": "x"}], s)
    eval_mod._post_chat([{"role": "user", "content": "x"}], s)
    assert seen == ["chat/model", "grade/model"]


def test_flat_model_extracts_while_scaledown_classifies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from brain.config import flat_model
    from brain.extract import flat

    paths: list[str] = []
    models: list[str] = []

    def fake_scaledown(path: str, body: dict[str, Any], settings: Settings) -> dict[str, Any]:
        paths.append(path)
        return {"top_label": "process", "scores": {"process": 0.9}}

    def fake_chat(payload: dict[str, Any], **kw: Any) -> dict[str, Any]:
        models.append(payload["model"])
        content = (
            '{"top_label": "rule", "scores": {}, "entities": '
            '[{"text": "Dana", "type": "Person", "confidence": 0.9}]}'
        )
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(flat, "_post_scaledown", fake_scaledown)
    monkeypatch.setattr(flat, "post_chat_with_rescue", fake_chat)
    s = _settings(
        brain_flat_model="flat/model", scaledown_api_key="sd", brain_scaledown_enabled=True
    )
    assert flat_model(s) == "flat/model"
    outcome = flat._process_chunk("c1", "Dana approves the order.", flat._CallCounters(s), None)
    assert paths == ["/classify"]
    assert models == ["flat/model"]
    assert outcome.passage_kind == "process"
    assert [m.surface_name for m in outcome.mentions] == ["Dana"]


def test_flat_model_unset_keeps_scaledown_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.config import flat_model
    from brain.extract import flat

    paths: list[str] = []

    def fake_scaledown(path: str, body: dict[str, Any], settings: Settings) -> dict[str, Any]:
        paths.append(path)
        return {"top_label": "process", "scores": {}, "entities": []}

    monkeypatch.setattr(flat, "_post_scaledown", fake_scaledown)
    s = _settings(scaledown_api_key="sd", brain_scaledown_enabled=True)
    assert flat_model(s) == "heavy/model"
    flat._process_chunk("c1", "Dana approves the order.", flat._CallCounters(s), None)
    assert paths == ["/classify", "/extract"]
