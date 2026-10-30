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
