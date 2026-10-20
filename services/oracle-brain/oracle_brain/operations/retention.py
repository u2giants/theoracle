"""Retention decisions: tombstones win, legal holds block purge, TTLs are explicit."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class RetentionRule:
    kind: str
    ttl: timedelta | None  # None means keep until explicitly deleted


@dataclass(frozen=True)
class Record:
    kind: str
    created_at: datetime
    tombstoned: bool = False
    legal_hold: bool = False


def decide(record: Record, rules: dict[str, RetentionRule], now: datetime) -> str:
    """Return 'hide', 'purge' or 'keep'. Unknown kinds fail closed."""
    if now.tzinfo is None or record.created_at.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    if record.tombstoned:
        # Deleted evidence is never readable, even without a rule for its kind;
        # a hold only defers physical purge.
        return "hide" if record.legal_hold else "purge"
    rule = rules.get(record.kind)
    if rule is None:
        raise KeyError(f"no retention rule for {record.kind!r}")
    if record.legal_hold or rule.ttl is None:
        return "keep"
    return "purge" if now - record.created_at >= rule.ttl else "keep"
