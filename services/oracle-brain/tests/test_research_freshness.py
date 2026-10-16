"""Pure maintenance freshness DTOs. Fake clock only; no network or worker."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from oracle_brain.research.freshness import (
    Freshness,
    FreshnessStatus,
    RefreshReceipt,
    assess,
    due_after_success,
    interval_for,
    receipt,
    review_due_from,
)

T0 = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
WEEK = timedelta(days=7)
QUARTER = timedelta(days=91)


def test_interval_for_known_cadences():
    assert interval_for('weekly') == WEEK
    assert interval_for('quarterly') == QUARTER
    with pytest.raises(ValueError, match='unknown cadence'):
        interval_for('daily')


def test_due_after_success_and_review_due_follow_cadence():
    assert due_after_success('weekly', T0) == T0 + WEEK
    assert due_after_success('quarterly', T0) == T0 + QUARTER
    assert review_due_from('weekly', T0) == T0 + WEEK
    assert review_due_from('quarterly', T0) == T0 + QUARTER


def test_assess_never_when_no_recorded_state():
    status = assess(
        source_id='s', cadence='weekly', now=T0, last_success=None, next_due=None, attempts=0
    )
    assert status.freshness is Freshness.NEVER
    assert status.review_due == T0 + WEEK
    assert status.attempts == 0


def test_assess_fresh_before_next_due():
    status = assess(
        source_id='s',
        cadence='weekly',
        now=T0 + timedelta(days=3),
        last_success=T0,
        next_due=T0 + WEEK,
        attempts=0,
    )
    assert status.freshness is Freshness.FRESH
    assert status.next_due == T0 + WEEK
    assert status.review_due == T0 + WEEK


def test_assess_due_at_and_just_after_next_due():
    at_due = assess(
        source_id='s', cadence='weekly', now=T0 + WEEK, last_success=T0, next_due=T0 + WEEK
    )
    assert at_due.freshness is Freshness.DUE
    after = assess(
        source_id='s',
        cadence='weekly',
        now=T0 + WEEK + timedelta(hours=1),
        last_success=T0,
        next_due=T0 + WEEK,
    )
    assert after.freshness is Freshness.DUE


def test_assess_overdue_once_grace_passes():
    status = assess(
        source_id='s',
        cadence='weekly',
        now=T0 + WEEK + WEEK + timedelta(minutes=1),
        last_success=T0,
        next_due=T0 + WEEK,
        attempts=2,
    )
    assert status.freshness is Freshness.OVERDUE
    assert status.attempts == 2


def test_assess_respects_explicit_overdue_after():
    status = assess(
        source_id='s',
        cadence='quarterly',
        now=T0 + QUARTER + timedelta(hours=2),
        last_success=T0,
        next_due=T0 + QUARTER,
        overdue_after=timedelta(hours=1),
    )
    assert status.freshness is Freshness.OVERDUE


def test_receipt_success_sets_next_due_and_counts_attempts():
    r = receipt(
        source_id='s', run_id='run-1', ok=True, at=T0, attempts_after=0, cadence='weekly'
    )
    assert r == RefreshReceipt('s', 'run-1', True, T0, 0, T0 + WEEK)


def test_receipt_failure_leaves_next_due_unset():
    r = receipt(
        source_id='s', run_id='run-2', ok=False, at=T0, attempts_after=3, cadence='quarterly'
    )
    assert r.next_due is None
    assert r.attempts_after == 3
    assert r.ok is False


def test_receipt_rejects_non_boolean_ok_and_negative_attempts():
    with pytest.raises(ValueError, match='ok must be a bool'):
        receipt(source_id='s', run_id='r', ok=1, at=T0, attempts_after=0, cadence='weekly')
    with pytest.raises(ValueError, match='attempts_after'):
        receipt(source_id='s', run_id='r', ok=True, at=T0, attempts_after=-1, cadence='weekly')


def test_freshness_status_is_immutable_dto():
    status = assess(
        source_id='s', cadence='weekly', now=T0, last_success=None, next_due=None
    )
    assert isinstance(status, FreshnessStatus)
    with pytest.raises(Exception):
        status.freshness = Freshness.FRESH  # type: ignore[misc]
