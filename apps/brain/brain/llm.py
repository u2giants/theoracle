"""Shared chat-completions call with per-provider routing and empty-content rescue.

Reasoning-flagged models can spend the whole ``max_tokens`` budget on thinking
and come back with ``content: null`` (measured 2026-10-30: claude-haiku-5.5
answers returned no message content on 2 of 5 eval questions; deepseek and
qwen reasoning tiers broke the relations stage the same way). One rescue retry
doubles the token budget and asks for low hidden reasoning; a second empty
response raises the caller's error class.

Provider routing (issue #426): model ids starting with ``meta-model-api/``
go to Meta's direct API with ``BRAIN_META_API_KEY``; everything else goes
to OpenRouter with ``OPENROUTER_API_KEY``.
"""

from __future__ import annotations

from typing import Any

import httpx

from brain.config import Settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
META_BASE_URL = "https://api.meta.ai/v1"
_META_PROVIDER_PREFIX = "meta-model-api/"

# Sent only on the rescue retry, so first-attempt behaviour — including the
# frozen eval grader — is never changed by this module.
_RESCUE_REASONING: dict[str, Any] = {"effort": "low", "exclude": True}
_MIN_RESCUE_MAX_TOKENS = 4000


def resolve_provider(model: str | None, settings: Settings) -> tuple[str, str | None]:
    """Return ``(base_url, api_key)`` for the model's provider."""
    if model and model.startswith(_META_PROVIDER_PREFIX):
        return META_BASE_URL, settings.brain_meta_api_key
    return OPENROUTER_BASE_URL, settings.openrouter_api_key


def strip_provider_prefix(model: str) -> str:
    """Strip the ``meta-model-api/`` prefix so the API sees its own model name."""
    if model.startswith(_META_PROVIDER_PREFIX):
        return model[len(_META_PROVIDER_PREFIX):]
    return model


def message_content(body: dict[str, Any]) -> str:
    """The first choice's message content as text (``""`` when it is empty)."""
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(content, list):
        return "".join(
            str(part.get("text", "")) for part in content if isinstance(part, dict)
        )
    if isinstance(content, str):
        return content
    return ""


def post_chat_with_rescue(
    payload: dict[str, Any],
    *,
    settings: Settings,
    timeout: float,
    error_cls: type[Exception],
    label: str,
) -> dict[str, Any]:
    """POST one chat-completions payload; retry once when content is empty."""
    model = str(payload.get("model") or "")
    base_url, api_key = resolve_provider(model, settings)
    if api_key is None:
        raise error_cls(f"{label}: no API key for model {model!r}")
    body = dict(payload)
    body["model"] = strip_provider_prefix(model)
    for attempt in range(2):
        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
            timeout=timeout,
        )
        if response.status_code != 200:
            raise error_cls(
                f"{label} call failed: {response.status_code} {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise error_cls(f"{label} response is not JSON") from exc
        if message_content(data):
            return data
        if attempt == 0:
            rescue = dict(body)
            budget = int(body.get("max_tokens") or 0) * 2
            rescue["max_tokens"] = max(budget, _MIN_RESCUE_MAX_TOKENS)
            # ``reasoning`` is an OpenRouter parameter; Meta's direct API
            # rejects it with a 400, which turned every empty reply into a
            # failed passage (seen in production 2026-11-11).
            if base_url == OPENROUTER_BASE_URL:
                rescue.setdefault("reasoning", dict(_RESCUE_REASONING))
            body = rescue
    raise error_cls(f"{label} response has no message content")
