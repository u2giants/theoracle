"""Empty-content rescue for reasoning models that burn the token budget."""

from __future__ import annotations

from typing import Any

import pytest

from brain import llm
from brain.config import Settings


class _Resp:
    def __init__(self, body: dict[str, Any], status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


class _Boom(Exception):
    pass


def _body(content: Any) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 5}}


def _settings() -> Settings:
    return Settings(openrouter_api_key="k", brain_meta_api_key="mk")


def test_message_content_normalises_shapes() -> None:
    assert llm.message_content(_body("hi")) == "hi"
    assert llm.message_content(_body([{"text": "a"}, {"text": "b"}])) == "ab"
    assert llm.message_content(_body(None)) == ""
    assert llm.message_content(_body(7)) == ""
    assert llm.message_content({"choices": []}) == ""


def test_resolve_provider_routes_meta_models() -> None:
    s = _settings()
    base, key = llm.resolve_provider("meta-model-api/muse-spark-1.3", s)
    assert base == llm.META_BASE_URL
    assert key == "mk"


def test_resolve_provider_routes_openrouter_by_default() -> None:
    s = _settings()
    base, key = llm.resolve_provider("z-ai/glm-5.3", s)
    assert base == llm.OPENROUTER_BASE_URL
    assert key == "k"
    base, key = llm.resolve_provider(None, s)
    assert base == llm.OPENROUTER_BASE_URL


def test_strip_provider_prefix() -> None:
    assert llm.strip_provider_prefix("meta-model-api/muse-spark-1.3") == "muse-spark-1.3"
    assert llm.strip_provider_prefix("z-ai/glm-5.3") == "z-ai/glm-5.3"


def test_first_attempt_untouched_when_content_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append({"url": url, "json": kw["json"]})
        return _Resp(_body('{"ok": true}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.post_chat_with_rescue(
        {"model": "m", "messages": [], "max_tokens": 4000},
        settings=_settings(),
        timeout=5.0,
        error_cls=_Boom,
        label="unit",
    )
    assert llm.message_content(out) == '{"ok": true}'
    assert len(seen) == 1
    assert "reasoning" not in seen[0]["json"]


def test_meta_model_routes_to_meta_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append({"url": url, "json": kw["json"]})
        return _Resp(_body('{"ok": true}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    llm.post_chat_with_rescue(
        {"model": "meta-model-api/muse-spark-1.3", "messages": [], "max_tokens": 4000},
        settings=_settings(),
        timeout=5.0,
        error_cls=_Boom,
        label="unit",
    )
    assert seen[0]["url"] == f"{llm.META_BASE_URL}/chat/completions"
    assert seen[0]["json"]["model"] == "muse-spark-1.3"


def test_empty_content_rescued_with_bigger_budget_and_hidden_reasoning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The recorded failure shape: ``content: null`` after thinking ate the cap."""
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append(kw["json"])
        if len(seen) == 1:
            return _Resp(_body(None))
        return _Resp(_body('{"answer_md": "ok", "citations": []}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.post_chat_with_rescue(
        {"model": "m", "messages": [], "max_tokens": 4000},
        settings=_settings(),
        timeout=5.0,
        error_cls=_Boom,
        label="unit",
    )
    assert llm.message_content(out) == '{"answer_md": "ok", "citations": []}'
    assert len(seen) == 2
    assert seen[0]["max_tokens"] == 4000
    assert seen[1]["max_tokens"] == 8000
    assert seen[1]["reasoning"] == {"effort": "low", "exclude": True}


def test_rescue_budget_never_drops_below_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append(kw["json"])
        return _Resp(_body("")) if len(seen) == 1 else _Resp(_body("ok"))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    llm.post_chat_with_rescue(
        {"model": "m", "messages": [], "max_tokens": 800},
        settings=_settings(),
        timeout=5.0,
        error_cls=_Boom,
        label="unit",
    )
    assert seen[1]["max_tokens"] == 4000


def test_second_empty_content_raises_with_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, **kw: Any) -> _Resp:
        return _Resp(_body(None))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(_Boom, match="unit response has no message content"):
        llm.post_chat_with_rescue(
            {"model": "m", "messages": [], "max_tokens": 4000},
            settings=_settings(),
            timeout=5.0,
            error_cls=_Boom,
            label="unit",
        )


def test_no_api_key_raises_for_meta_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    s = Settings(openrouter_api_key="k")  # no meta key
    with pytest.raises(_Boom, match="no API key"):
        llm.post_chat_with_rescue(
            {"model": "meta-model-api/muse-spark-1.3", "messages": [], "max_tokens": 4000},
            settings=s,
            timeout=5.0,
            error_cls=_Boom,
            label="unit",
        )


def test_rescue_for_meta_model_sends_no_reasoning_parameter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Meta's direct API rejects ``reasoning`` with a 400; the rescue retry for
    a Meta model only raises the budget (production 2026-11-11)."""
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append(kw["json"])
        if "reasoning" in kw["json"]:
            return _Resp({"error": {"message": "unknown parameter `reasoning`"}}, 400)
        return _Resp(_body(None if len(seen) == 1 else "ok"))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.post_chat_with_rescue(
        {"model": "meta-model-api/some-model", "messages": [], "max_tokens": 4000},
        settings=_settings(),
        timeout=5.0,
        error_cls=_Boom,
        label="unit",
    )
    assert llm.message_content(out) == "ok"
    assert seen[1]["max_tokens"] == 8000 and "reasoning" not in seen[1]
