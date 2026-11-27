"""Shared chat-completions call with per-provider routing and empty-content rescue.

Reasoning-flagged models can spend the whole ``max_tokens`` budget on thinking
and come back with ``content: null`` (measured 2026-10-30: claude-haiku-5.5
answers returned no message content on 2 of 5 eval questions; deepseek and
qwen reasoning tiers broke the relations stage the same way). One rescue retry
doubles the token budget and asks for low hidden reasoning; a second empty
response raises the caller's error class.

Provider routing (issue #426):
- ``meta-model-api/*`` goes to Meta's direct API with ``BRAIN_META_API_KEY``.
- ``openai-api/*`` goes to OpenAI's direct API with ``BRAIN_OPENAI_API_KEY`` / ``OPENAI_API_KEY``.
- ``openai/*`` goes to OpenRouter with ``OPENROUTER_API_KEY``, falling back to OpenAI direct.
- ``anthropic/*`` and ``claude-*`` (plus ``scaledown/*`` or unset) go to OpenRouter with ``OPENROUTER_API_KEY``.
- Everything else (GLM, DeepSeek, Qwen, Gemini, etc.) goes to Straitly with ``BRAIN_STRAITLY_API_KEY`` / ``STRAITLY_API_KEY``.

Per-provider parameter gating (issues #590, #592): every payload passes
``gate_payload_for_provider`` before it is sent, so only request parameters
the active provider understands are sent — OpenRouter extensions such as
``reasoning`` never reach Meta's direct API, which rejects unknown body keys
with a 400 and thereby turns one bad parameter into a failed job.

Bounded JSON repair (issue #592): stage replies that must be JSON go through
``post_chat_json_body``, which parses the content and, when it does not
parse, makes exactly one repair re-ask with a JSON-only instruction before
raising an error that names the provider, the model and a content excerpt.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

import httpx

from brain.config import Settings, openai_api_key, straitly_api_key

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
META_BASE_URL = "https://api.meta.ai/v1"
OPENAI_BASE_URL = "https://api.openai.com/v1"
STRAITLY_BASE_URL = "https://api.straitly.ai/v1"
_META_PROVIDER_PREFIX = "meta-model-api/"
_OPENAI_PROVIDER_PREFIX = "openai-api/"
_OPENAI_OPENROUTER_PREFIX = "openai/"
_ANTHROPIC_PREFIXES = ("anthropic/", "claude-")
_SCALEDOWN_PREFIX = "scaledown/"

_PROVIDER_NAMES: dict[str, str] = {
    OPENROUTER_BASE_URL: "openrouter",
    META_BASE_URL: "meta",
    OPENAI_BASE_URL: "openai",
    STRAITLY_BASE_URL: "straitly",
}

# Body keys Meta's and OpenAI's direct APIs understand. OpenRouter accepts the
# chat-completions surface plus its own extensions (``reasoning``, ``provider``
# routing, ``transforms``), so direct-provider payloads are filtered against an
# allowlist so an OpenRouter-only parameter never causes a 400
# (production 2026-11-11: ``unknown parameter: reasoning``, issue #590).
_META_ALLOWED_PARAMS = frozenset(
    {
        "model",
        "messages",
        "temperature",
        "top_p",
        "max_tokens",
        "stream",
        "stop",
        "seed",
        "user",
        "response_format",
    }
)
_OPENAI_ALLOWED_PARAMS = frozenset(
    {
        *_META_ALLOWED_PARAMS,
        "max_completion_tokens",
        "reasoning_effort",
        "store",
    }
)

# Sent only on the rescue retry, so first-attempt behaviour — including the
# frozen eval grader — is never changed by this module.
_RESCUE_REASONING: dict[str, Any] = {"effort": "low", "exclude": True}
_MIN_RESCUE_MAX_TOKENS = 4000

# The one repair instruction appended when a stage reply is not JSON: bounded
# (a single re-ask) and model-agnostic.
_JSON_ONLY_INSTRUCTION = (
    "Your previous reply could not be parsed as JSON. Reply again with ONLY the "
    "JSON object requested earlier: no prose before or after it, no markdown "
    "fences, no comments — the raw JSON object and nothing else."
)

# A fence at either end of an otherwise bare JSON reply.
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def resolve_provider(model: str | None, settings: Settings) -> tuple[str, str | None]:
    """Return ``(base_url, api_key)`` for the model's provider.

    Routing order:
    - ``meta-model-api/*`` routes directly to ``META_BASE_URL``.
    - ``openai-api/*`` always routes directly to ``OPENAI_BASE_URL`` with
      ``openai_api_key(settings)``.
    - ``openai/*`` routes to ``OPENROUTER_BASE_URL`` whenever
      ``settings.openrouter_api_key`` is set (matching ``plan_pm_message_intake.md``
      step 2.4). When ``settings.openrouter_api_key`` is unset and
      ``openai_api_key(settings)`` is set, it falls back directly to
      ``OPENAI_BASE_URL`` with ``openai/`` stripped by ``strip_provider_prefix``.
    - ``anthropic/*``, ``claude-*``, ``scaledown/*``, and empty/``None`` models
      route to ``OPENROUTER_BASE_URL``.
    - All other models (e.g. ``z-ai/*``, ``deepseek/*``, ``qwen/*``,
      ``google/*``, ``meta-llama/*``) route to ``STRAITLY_BASE_URL`` with
      ``straitly_api_key(settings)``.
    """
    if model and model.startswith(_META_PROVIDER_PREFIX):
        return META_BASE_URL, settings.brain_meta_api_key
    if model and model.startswith(_OPENAI_PROVIDER_PREFIX):
        return OPENAI_BASE_URL, openai_api_key(settings)
    if model and model.startswith(_OPENAI_OPENROUTER_PREFIX):
        if not settings.openrouter_api_key and (direct_key := openai_api_key(settings)):
            return OPENAI_BASE_URL, direct_key
        return OPENROUTER_BASE_URL, settings.openrouter_api_key
    if (
        not model
        or model.startswith(_ANTHROPIC_PREFIXES)
        or model.startswith(_SCALEDOWN_PREFIX)
    ):
        return OPENROUTER_BASE_URL, settings.openrouter_api_key
    return STRAITLY_BASE_URL, straitly_api_key(settings)


def has_provider_key(model: str | None, settings: Settings) -> bool:
    """True when ``model`` is set and its resolved provider has an API key."""
    return bool(model and resolve_provider(model, settings)[1])


def strip_provider_prefix(model: str, base_url: str | None = None) -> str:
    """Strip ``meta-model-api/``, ``openai-api/``, or (on direct OpenAI) ``openai/``."""
    if model.startswith(_META_PROVIDER_PREFIX):
        return model[len(_META_PROVIDER_PREFIX) :]
    if model.startswith(_OPENAI_PROVIDER_PREFIX):
        return model[len(_OPENAI_PROVIDER_PREFIX) :]
    if base_url == OPENAI_BASE_URL and model.startswith(_OPENAI_OPENROUTER_PREFIX):
        return model[len(_OPENAI_OPENROUTER_PREFIX) :]
    return model


def provider_name(base_url: str) -> str:
    """Human-facing provider label for a resolved base URL."""
    return _PROVIDER_NAMES.get(base_url, base_url)


def gate_payload_for_provider(payload: dict[str, Any], base_url: str) -> dict[str, Any]:
    """Drop request parameters the provider does not understand.

    Only parameters the active provider understands are sent: OpenRouter
    payloads pass through untouched (its extension parameters stay), while
    direct Meta and OpenAI payloads are filtered against their allowlists.
    """
    if base_url == META_BASE_URL:
        allowed = _META_ALLOWED_PARAMS
    elif base_url == OPENAI_BASE_URL:
        allowed = _OPENAI_ALLOWED_PARAMS
    else:
        return payload
    dropped = sorted(key for key in payload if key not in allowed)
    if dropped:
        logger.warning(
            "dropping request parameters %s's API does not accept: %s",
            provider_name(base_url),
            dropped,
        )
    return {key: value for key, value in payload.items() if key in allowed}


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


def parse_json_reply(content: str) -> Any:
    """Parse a model reply into JSON, tolerating fences and framing prose.

    A model asked for JSON still sometimes wraps the object in a markdown
    fence or a sentence of prose. Try the raw text, then the fence-stripped
    text, then the substring from the first ``{`` to the last ``}``; anything
    else raises ``ValueError`` for the caller's stage error.
    """
    raw = (content or "").strip()
    for candidate in (raw, _FENCE_RE.sub("", raw).strip()):
        try:
            return json.loads(candidate)
        except ValueError:
            continue
    fenced = _FENCE_RE.sub("", raw).strip()
    start, end = fenced.find("{"), fenced.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(fenced[start : end + 1])
        except ValueError:
            pass
    raise ValueError("reply is not JSON")


def classify_call_error(exc: BaseException | None, status: int | None) -> str | None:
    """Bucket a failed provider call for the ``openrouter-call`` log line."""
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if exc is not None:
        return "invalid_json" if isinstance(exc, ValueError) else "other"
    if status == 429:
        return "http_429"
    if status is not None and 500 <= status < 600:
        return "http_5xx"
    if status is not None and status != 200:
        return "other"
    return None


def log_openrouter_call(
    *,
    model: str,
    caller: str,
    started: float,
    response: httpx.Response | None = None,
    data: Any = None,
    error_class: str | None = None,
) -> None:
    """Emit one structured ``openrouter-call`` JSON log line (#1493)."""
    host = "unknown"
    if isinstance(data, dict) and isinstance(data.get("provider"), str):
        host = data["provider"] or "unknown"
    record = {
        "event": "openrouter-call",
        "model": model,
        "host": host,
        "ok": error_class is None,
        "latency_ms": int((time.monotonic() - started) * 1000),
        "http_status": response.status_code if response is not None else None,
        "error_class": error_class,
        "caller": caller,
    }
    try:
        logger.info("openrouter-call %s", json.dumps(record, sort_keys=True))
    except Exception:  # noqa: BLE001 - logging must never break a call
        pass


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
    provider = provider_name(base_url)
    if api_key is None:
        raise error_cls(f"{label}: no API key for provider {provider} model {model!r}")
    body = dict(payload)
    body["model"] = strip_provider_prefix(model, base_url)
    body = gate_payload_for_provider(body, base_url)
    for attempt in range(2):
        started = time.monotonic()
        try:
            response = httpx.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=body,
                timeout=timeout,
            )
        except httpx.HTTPError as exc:
            log_openrouter_call(
                model=model,
                caller=label,
                started=started,
                error_class=classify_call_error(exc, None),
            )
            raise
        if response.status_code != 200:
            log_openrouter_call(
                model=model,
                caller=label,
                started=started,
                response=response,
                error_class=classify_call_error(None, response.status_code),
            )
            raise error_cls(
                f"{label} call failed: provider {provider} returned "
                f"HTTP {response.status_code}: {response.text[:200]}"
            )
        try:
            data = response.json()
        except ValueError as exc:
            log_openrouter_call(
                model=model,
                caller=label,
                started=started,
                response=response,
                error_class="invalid_json",
            )
            raise error_cls(
                f"{label} response is not JSON: provider {provider} returned "
                f"HTTP {response.status_code} with a non-JSON body: "
                f"{response.text[:200]}"
            ) from exc
        has_content = bool(message_content(data))
        log_openrouter_call(
            model=model,
            caller=label,
            started=started,
            response=response,
            data=data,
            error_class=None if has_content else "empty",
        )
        if has_content:
            return data
        if attempt == 0:
            rescue = dict(body)
            budget = int(body.get("max_tokens") or 0) * 2
            rescue["max_tokens"] = max(budget, _MIN_RESCUE_MAX_TOKENS)
            # ``reasoning`` is an OpenRouter parameter; Meta's direct API
            # rejects it with a 400, which turned every empty reply into a
            # failed passage (seen in production 2026-11-11). The gate above
            # strips it again for Meta, keeping one seam for every parameter.
            rescue.setdefault("reasoning", dict(_RESCUE_REASONING))
            body = gate_payload_for_provider(rescue, base_url)
    raise error_cls(
        f"{label} response has no message content (provider {provider}, "
        f"model {model!r})"
    )


def post_chat_json_body(
    payload: dict[str, Any],
    *,
    settings: Settings,
    timeout: float,
    error_cls: type[Exception],
    label: str,
    parse: Callable[[str], Any],
) -> dict[str, Any]:
    """POST one chat-completions payload whose reply content must be JSON.

    ``parse`` turns the reply content into the stage payload and raises
    ``error_cls`` when the reply is not the JSON the prompt asked for. When
    the first reply does not parse, exactly one repair re-ask is made — the
    offending reply quoted back with a JSON-only instruction and a doubled
    token budget, so a truncated object also gets room to finish — and the
    body whose content parsed is returned. When the repair also fails,
    ``error_cls`` is raised naming the provider, the model and a content
    excerpt (issue #592: one malformed reply must not read as a bare
    "not JSON" failure, and must not burn a whole job attempt on its own).
    """
    model = str(payload.get("model") or "")
    base_url, _api_key = resolve_provider(model, settings)
    provider = provider_name(base_url)
    body = post_chat_with_rescue(
        payload,
        settings=settings,
        timeout=timeout,
        error_cls=error_cls,
        label=label,
    )
    content = message_content(body)
    try:
        parse(content)
        return body
    except error_cls:
        logger.warning(
            "%s: reply is not JSON (provider %s, model %s); making one repair re-ask",
            label,
            provider,
            model,
        )
    repair = dict(payload)
    repair["messages"] = [
        *(payload.get("messages") or []),
        {"role": "assistant", "content": content[:2000]},
        {"role": "user", "content": _JSON_ONLY_INSTRUCTION},
    ]
    budget = int(payload.get("max_tokens") or 0) * 2
    if budget:
        repair["max_tokens"] = budget
    retry_body = post_chat_with_rescue(
        repair,
        settings=settings,
        timeout=timeout,
        error_cls=error_cls,
        label=label,
    )
    retry_content = message_content(retry_body)
    try:
        parse(retry_content)
        return retry_body
    except error_cls as exc:
        raise error_cls(
            f"{label} response is not JSON after one repair retry "
            f"(provider {provider}, model {model!r}): {retry_content[:300]!r}"
        ) from exc
