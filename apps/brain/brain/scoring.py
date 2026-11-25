"""Evidence scoring for source authority, ideal-vs-practice role, and recency."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

SOURCE_ROLES = ("ideal_policy", "observed_practice", "reference")
DEFAULT_SOURCE_ROLE = "observed_practice"

AUTHORITY_TIERS = ("authoritative", "standard")
DEFAULT_AUTHORITY_TIER = "standard"

AUTHORITATIVE_MULTIPLIER = 8.0
STANDARD_MULTIPLIER = 1.0
RECENCY_HALF_LIFE_DAYS = 180.0
RECENCY_FLOOR = 0.35
UNKNOWN_DATE_FACTOR = 0.75

_ROLE_LABELS = {
    "ideal_policy": "IDEAL POLICY",
    "observed_practice": "OBSERVED PRACTICE",
    "reference": "REFERENCE",
}


def validate_source_role(value: str | None) -> str:
    """Validate and normalize ``source_role``; defaults to ``observed_practice``."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT_SOURCE_ROLE
    if cleaned not in SOURCE_ROLES:
        raise ValueError(
            f"source_role must be one of {', '.join(SOURCE_ROLES)}; got {value!r}"
        )
    return cleaned


def validate_authority_tier(value: str | None) -> str:
    """Validate and normalize ``authority_tier``; defaults to ``standard``."""
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return DEFAULT_AUTHORITY_TIER
    if cleaned not in AUTHORITY_TIERS:
        raise ValueError(
            f"authority_tier must be one of {', '.join(AUTHORITY_TIERS)}; got {value!r}"
        )
    return cleaned


def authority_multiplier(authority_tier: str | None) -> float:
    """Return the multiplier for ``authority_tier``."""
    if (authority_tier or "").strip().lower() == "authoritative":
        return AUTHORITATIVE_MULTIPLIER
    return STANDARD_MULTIPLIER


def _coerce_date(value: date | datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def recency_multiplier(
    effective_date: date | datetime | str | None,
    *,
    today: date | None = None,
) -> float:
    """Half-life recency multiplier floored at ``RECENCY_FLOOR``."""
    parsed = _coerce_date(effective_date)
    if parsed is None:
        return UNKNOWN_DATE_FACTOR
    ref = today or datetime.now(UTC).date()
    age_days = max(0, (ref - parsed).days)
    decayed = 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
    return max(RECENCY_FLOOR, float(decayed))


def effective_stance(raw_stance: str | None, source_role: str | None) -> str:
    """Promote ``report``/``practice`` stances from ``ideal_policy`` sources to ``policy``."""
    stance = (raw_stance or "report").strip().lower() or "report"
    if (source_role or "").strip().lower() == "ideal_policy" and stance in (
        "report",
        "practice",
    ):
        return "policy"
    return stance


def source_weight(
    authority_tier: str | None,
    effective_date: date | datetime | str | None,
    *,
    confidence: float | Any = 1.0,
    today: date | None = None,
) -> float:
    """Combined authority * recency * bounded confidence score for one evidence item."""
    try:
        conf = float(confidence if confidence is not None else 1.0)
    except (TypeError, ValueError):
        conf = 1.0
    bounded_conf = max(0.2, min(1.5, conf))
    return (
        authority_multiplier(authority_tier)
        * recency_multiplier(effective_date, today=today)
        * bounded_conf
    )


def format_source_tag(
    source_role: str | None,
    authority_tier: str | None,
    effective_date: date | datetime | str | None = None,
) -> str:
    """Compact label surfacing ideal-vs-practice role, authority tier, and date."""
    role_key = (source_role or DEFAULT_SOURCE_ROLE).strip().lower()
    parts = [_ROLE_LABELS.get(role_key, "OBSERVED PRACTICE")]
    if (authority_tier or "").strip().lower() == "authoritative":
        parts.append("AUTHORITATIVE")
    parsed_date = _coerce_date(effective_date)
    if parsed_date is not None:
        parts.append(parsed_date.isoformat())
    return "[" + " — ".join(parts) + "]"
