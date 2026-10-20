"""Log-safe event shaping: measures and trace IDs only, never raw payloads."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

# Only these keys may reach logs; every other field is dropped, not masked.
ALLOWED_KEYS = frozenset({
    "trace_id", "stage", "status", "latency_ms", "cost_usd", "error_code",
    "attempt", "workspace_id", "source_id", "event_id", "count", "bytes",
})
_SECRETISH = re.compile(
    r"(?i)(bearer\s+\S+|sk-[A-Za-z0-9_-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_.-]+)")
_MAX_SCALAR = 128


def fingerprint(value: Any) -> str:
    """Stable, non-reversible reference to a payload for correlation."""
    return "sha256:" + hashlib.sha256(repr(value).encode()).hexdigest()[:16]


def _scalar(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if len(value) > _MAX_SCALAR or _SECRETISH.search(value):
            return fingerprint(value)
        return value
    return fingerprint(value)


def redact(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return a log-safe copy; unknown keys and nested payloads never pass."""
    safe = {key: _scalar(value) for key, value in event.items() if key in ALLOWED_KEYS}
    dropped = sorted(key for key in event if key not in ALLOWED_KEYS)
    if dropped:
        safe["redacted_fields"] = dropped
    return safe
