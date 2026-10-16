"""Maintenance freshness DTOs for industry sources. Pure; clocks are injected by callers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .registry import CADENCES


class Freshness(str, Enum):
    NEVER = 'never'
    FRESH = 'fresh'
    DUE = 'due'
    OVERDUE = 'overdue'


@dataclass(frozen=True)
class FreshnessStatus:
    source_id: str
    freshness: Freshness
    last_success: datetime | None
    next_due: datetime | None
    review_due: datetime | None
    attempts: int
    cadence: str


@dataclass(frozen=True)
class RefreshReceipt:
    source_id: str
    run_id: str
    ok: bool
    at: datetime
    attempts_after: int
    next_due: datetime | None


def interval_for(cadence: str) -> timedelta:
    try:
        return CADENCES[cadence]
    except KeyError as exc:
        raise ValueError(f'unknown cadence {cadence!r}') from exc


def due_after_success(cadence: str, at: datetime) -> datetime:
    return at + interval_for(cadence)


def review_due_from(cadence: str, at: datetime) -> datetime:
    """Stable frameworks review quarterly; frequently changing sources review weekly."""
    return at + interval_for(cadence)


def assess(
    *,
    source_id: str,
    cadence: str,
    now: datetime,
    last_success: datetime | None,
    next_due: datetime | None,
    attempts: int = 0,
    overdue_after: timedelta | None = None,
) -> FreshnessStatus:
    """Classify freshness from recorded state only. No clock reads, no I/O."""
    interval = interval_for(cadence)
    if last_success is None and next_due is None:
        freshness = Freshness.NEVER
    elif next_due is not None and next_due <= now:
        grace = overdue_after if overdue_after is not None else interval
        freshness = Freshness.OVERDUE if next_due + grace <= now else Freshness.DUE
    else:
        freshness = Freshness.FRESH
    review_at = last_success if last_success is not None else now
    return FreshnessStatus(
        source_id=source_id,
        freshness=freshness,
        last_success=last_success,
        next_due=next_due,
        review_due=review_due_from(cadence, review_at),
        attempts=attempts,
        cadence=cadence,
    )


def receipt(
    *,
    source_id: str,
    run_id: str,
    ok: bool,
    at: datetime,
    attempts_after: int,
    cadence: str,
) -> RefreshReceipt:
    if type(ok) is not bool:
        raise ValueError('ok must be a bool')
    if attempts_after < 0:
        raise ValueError('attempts_after must be >= 0')
    return RefreshReceipt(
        source_id=source_id,
        run_id=run_id,
        ok=ok,
        at=at,
        attempts_after=attempts_after,
        next_due=due_after_success(cadence, at) if ok else None,
    )
