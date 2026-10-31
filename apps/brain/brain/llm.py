"""Shared OpenRouter chat-completions call with an empty-content rescue.

Reasoning-flagged models can spend the whole ``max_tokens`` budget on thinking
and come back with ``content: null`` (measured 2026-10-30: claude-haiku-5.5
answers returned no message content on 2 of 5 eval questions; deepseek and
qwen reasoning tiers broke the relations stage the same way). One rescue retry
doubles the token budget and asks for low hidden reasoning; a second empty
response raises the caller's error class.
"""

from __future__ import annotations

from typing import Any

import httpx

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Sent only on the rescue retry, so first-attempt behaviour — including the
# frozen eval grader — is never changed by this module.
_RESCUE_REASONING: dict[str, Any] = {"effort": "low", "exclude": True}
_MIN_RESCUE_MAX_TOKENS = 4000


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
    api_key: str,
    timeout: float,
    error_cls: type[Exception],
    label: str,
) -> dict[str, Any]:
    """POST one chat-completions payload; retry once when content is empty."""
    body = dict(payload)
    for attempt in range(2):
        response = httpx.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
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
            rescue.setdefault("reasoning", dict(_RESCUE_REASONING))
            body = rescue
    raise error_cls(f"{label} response has no message content")
