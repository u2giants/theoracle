"""Issue #365: dense chunks must not be cut off at the old 2,000-token cap."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from brain.extract import relations


def _body(content: str, finish: str) -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
    }


def _counters() -> Any:
    return relations._Counters(SimpleNamespace(brain_max_frontier_calls_per_job=None))


def test_first_call_budget_is_above_old_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[int] = []

    def fake(messages: Any, settings: Any, max_tokens: int = relations.MAX_TOKENS) -> Any:
        seen.append(max_tokens)
        return _body(json.dumps({"relations": [], "new_mentions": []}), "stop")

    monkeypatch.setattr(relations, "_post_chat", fake)
    counters = _counters()
    relations._call_model("prompt", counters)
    assert seen == [relations.MAX_TOKENS]
    assert relations.MAX_TOKENS >= 8000
    assert "frontier_truncated" not in counters.usage


def test_truncated_reply_is_retried_with_larger_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full = {"relations": [{"from": "m1", "to": "m2"}] * 3, "new_mentions": []}
    seen: list[int] = []

    def fake(messages: Any, settings: Any, max_tokens: int = relations.MAX_TOKENS) -> Any:
        seen.append(max_tokens)
        if len(seen) == 1:
            return _body('{"relations": [{"from": "m1", "to": "m2"}, {"fr', "length")
        return _body(json.dumps(full), "stop")

    monkeypatch.setattr(relations, "_post_chat", fake)
    counters = _counters()
    parsed = relations._call_model("prompt", counters)
    assert seen == [relations.MAX_TOKENS, relations.TRUNCATION_RETRY_MAX_TOKENS]
    assert len(parsed["relations"]) == 3
    assert counters.usage["frontier_calls"] == 2
    assert counters.usage["frontier_truncation_retries"] == 1
    assert "frontier_truncated" not in counters.usage
    assert counters.usage["frontier_completion_tokens"] == 40
