"""Empty-content rescue for reasoning models that burn the token budget."""

from __future__ import annotations

import json
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


# ------------------------------------------------- per-provider gating (#590)


def test_provider_gate_strips_openrouter_only_params_for_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that rejects a parameter never receives it.

    OpenRouter-only body keys (``reasoning``, ``provider`` routing) are
    dropped from every Meta payload before the call, whatever caller added
    them — the production ``unknown parameter: reasoning`` trap.
    """
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append({"url": url, "json": kw["json"]})
        return _Resp(_body('{"ok": true}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    llm.post_chat_with_rescue(
        {
            "model": "meta-model-api/muse-spark-1.3",
            "messages": [],
            "max_tokens": 100,
            "response_format": {"type": "json_object"},
            "reasoning": {"effort": "low"},
            "provider": {"sort": "price"},
        },
        settings=_settings(),
        timeout=5.0,
        error_cls=_Boom,
        label="unit",
    )
    assert seen[0]["url"] == f"{llm.META_BASE_URL}/chat/completions"
    sent = seen[0]["json"]
    assert "reasoning" not in sent
    assert "provider" not in sent
    assert sent["model"] == "muse-spark-1.3"
    assert sent["max_tokens"] == 100
    assert sent["response_format"] == {"type": "json_object"}


def test_provider_gate_keeps_openrouter_params_on_openrouter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenRouter understands its own extensions; they are sent untouched."""
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append({"url": url, "json": kw["json"]})
        return _Resp(_body('{"ok": true}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    llm.post_chat_with_rescue(
        {
            "model": "anthropic/claude-some-model",
            "messages": [],
            "max_tokens": 100,
            "reasoning": {"effort": "low"},
        },
        settings=_settings(),
        timeout=5.0,
        error_cls=_Boom,
        label="unit",
    )
    assert seen[0]["url"] == f"{llm.OPENROUTER_BASE_URL}/chat/completions"
    assert seen[0]["json"]["reasoning"] == {"effort": "low"}


def test_api_error_names_provider_and_http_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An API error surfaces the provider and the HTTP status (#592 diagnosis)."""

    def fake_post(url: str, **kw: Any) -> _Resp:
        return _Resp({"error": {"message": "unknown parameter: reasoning"}}, 400)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(_Boom, match=r"provider meta returned HTTP 400"):
        llm.post_chat_with_rescue(
            {"model": "meta-model-api/muse-spark-1.3", "messages": [], "max_tokens": 10},
            settings=_settings(),
            timeout=5.0,
            error_cls=_Boom,
            label="unit",
        )


def test_non_json_http_body_names_provider_and_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 200 with a non-JSON body names the provider too, not just 'not JSON'."""

    class _Text:
        status_code = 200
        text = "<html>gateway error page</html>"

        def json(self) -> dict[str, Any]:
            raise ValueError("not json")

    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: _Text())
    with pytest.raises(_Boom, match=r"provider openrouter returned HTTP 200"):
        llm.post_chat_with_rescue(
            {"model": "m", "messages": [], "max_tokens": 10},
            settings=_settings(),
            timeout=5.0,
            error_cls=_Boom,
            label="unit",
        )


def test_no_content_error_names_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(llm.httpx, "post", lambda url, **kw: _Resp(_body(None)))
    with pytest.raises(_Boom, match="provider openrouter"):
        llm.post_chat_with_rescue(
            {"model": "m", "messages": [], "max_tokens": 10},
            settings=_settings(),
            timeout=5.0,
            error_cls=_Boom,
            label="unit",
        )


# ---------------------------------------------- bounded JSON repair (#592)


def test_parse_json_reply_tolerates_fences_and_framing_prose() -> None:
    assert llm.parse_json_reply('{"a": 1}') == {"a": 1}
    assert llm.parse_json_reply('```json\n{"a": 1}\n```') == {"a": 1}
    assert llm.parse_json_reply('Sure! Here it is: {"a": 1} — done.') == {"a": 1}
    with pytest.raises(ValueError):
        llm.parse_json_reply("no json anywhere at all")


class _StageError(RuntimeError):
    pass


def _parse_or_raise(content: str) -> dict[str, Any]:
    """A stage-shaped parse: JSON object or the stage error class."""
    try:
        value = json.loads(content)
    except ValueError as exc:
        raise _StageError("stage response is not JSON") from exc
    if not isinstance(value, dict):
        raise _StageError("stage response is not a JSON object")
    return value


def test_stage_json_repair_retries_once_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-JSON stage reply triggers one repair re-ask and then parses."""
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append(kw["json"])
        if len(seen) == 1:
            return _Resp(_body("Here is the flow you asked for — hope it helps!"))
        return _Resp(_body('{"steps": [], "title": "ok"}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.post_chat_json_body(
        {
            "model": "m",
            "messages": [{"role": "user", "content": "extract the flow"}],
            "max_tokens": 2000,
        },
        settings=_settings(),
        timeout=5.0,
        error_cls=_StageError,
        label="unit stage",
        parse=_parse_or_raise,
    )
    assert json.loads(llm.message_content(out)) == {"steps": [], "title": "ok"}
    assert len(seen) == 2, "exactly one repair re-ask"
    repair_messages = seen[1]["messages"]
    assert repair_messages[0] == {"role": "user", "content": "extract the flow"}
    assert repair_messages[-2]["role"] == "assistant"
    assert repair_messages[-2]["content"].startswith("Here is the flow")
    assert repair_messages[-1]["role"] == "user"
    assert "ONLY the JSON object" in repair_messages[-1]["content"]
    assert seen[1]["max_tokens"] == 4000, "a truncated object gets room to finish"


def test_stage_json_repair_fires_on_prose_wrapped_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prose the stage parser cannot slice itself still repairs via re-ask."""
    seen: list[dict[str, Any]] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        seen.append(kw["json"])
        if len(seen) == 1:
            return _Resp(_body("I will do this in three parts, first ..."))
        return _Resp(_body('{"classification": "same"}'))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.post_chat_json_body(
        {"model": "m", "messages": [{"role": "user", "content": "classify"}], "max_tokens": 500},
        settings=_settings(),
        timeout=5.0,
        error_cls=_StageError,
        label="unit stage",
        parse=_parse_or_raise,
    )
    assert json.loads(llm.message_content(out)) == {"classification": "same"}
    assert len(seen) == 2


def test_stage_json_repair_persistent_failure_is_bounded_and_names_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A persistently non-JSON reply fails the job with a provider-bearing error."""
    calls: list[int] = []

    def fake_post(url: str, **kw: Any) -> _Resp:
        calls.append(1)
        return _Resp(_body("I would rather explain in prose."))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(
        _StageError,
        match=r"response is not JSON after one repair retry \(provider openrouter, model 'm'\)",
    ) as excinfo:
        llm.post_chat_json_body(
            {
                "model": "m",
                "messages": [{"role": "user", "content": "extract"}],
                "max_tokens": 2000,
            },
            settings=_settings(),
            timeout=5.0,
            error_cls=_StageError,
            label="unit stage",
            parse=_parse_or_raise,
        )
    assert "prose" in str(excinfo.value), "the error carries a content excerpt"
    assert len(calls) == 2, "bounded: first call plus one repair re-ask, no more"
