"""Allowlisted provider transport settings for paid model calls."""
from __future__ import annotations

from .provider_policy import ProcessingRequest

OPENAI_ENDPOINT = "https://api.openai.com/v1"
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1"


def transport_options(request: ProcessingRequest, model: str, *, operation: str) -> dict:
    """Validate an admitted request and return only fixed SDK transport options."""
    endpoints = {"openai": OPENAI_ENDPOINT, "openrouter": OPENROUTER_ENDPOINT}
    if request.provider not in endpoints or request.endpoint != endpoints[request.provider]:
        raise PermissionError("provider endpoint is not allowlisted")
    if request.fallback:
        raise PermissionError("provider fallback is not permitted")
    if not model.strip():
        raise ValueError("provider model is required")
    if request.provider == "openrouter":
        if operation not in {"chat", "embedding"} or not model.startswith("openai/") or ":" in model:
            raise PermissionError("OpenRouter model is not an allowlisted OpenAI model")
        return {"extra_body": {"provider": {"only": ["openai"],
                                               "allow_fallbacks": False,
                                               "require_parameters": True,
                                               "data_collection": "deny"}}}
    if operation not in {"chat", "embedding"}:
        raise ValueError("unsupported provider operation")
    return {}
