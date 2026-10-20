"""Alarm evaluation over stage measures; pure and offline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class StageHealth:
    stage: str
    backlog: int
    oldest_pending_at: datetime | None
    failures: int
    cost_usd: float


@dataclass(frozen=True)
class Thresholds:
    max_pending_age: timedelta = timedelta(minutes=30)
    max_failures: int = 3
    cost_cap_usd: float = 50.0


def alarms(stages: list[StageHealth], now: datetime,
           limits: Thresholds = Thresholds()) -> list[str]:
    """Return sorted alarm codes such as 'stuck:ingest' or 'cost_cap'."""
    found: set[str] = set()
    for stage in stages:
        if stage.oldest_pending_at and now - stage.oldest_pending_at > limits.max_pending_age:
            found.add(f"stuck:{stage.stage}")
        if stage.failures >= limits.max_failures:
            found.add(f"failing:{stage.stage}")
    if sum(stage.cost_usd for stage in stages) >= limits.cost_cap_usd:
        found.add("cost_cap")
    return sorted(found)
