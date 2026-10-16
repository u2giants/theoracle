"""Fake-clock refresh scheduler tests; no network or worker."""
from datetime import datetime, timedelta, timezone
from itertools import count
from pathlib import Path

from oracle_brain.research.refresh import Scheduler
from oracle_brain.research.registry import Source, load_register

T0 = datetime(2026, 10, 15, 12, tzinfo=timezone.utc)
WEEKLY = Source('w', 'Pub', 'https://pub.example/w', 'US', 'retail', 'public', 'weekly')
QUARTERLY = Source('q', 'Pub', 'https://pub.example/q', 'US', 'framework', 'public', 'quarterly')
DISABLED = Source('d', 'Pub', 'https://pub.example/d', 'US', 'x', 'public', 'weekly', enabled=False)
UNLICENSED = Source('l', 'Pub', 'https://pub.example/l', 'US', 'x', 'licensed', 'weekly')


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now


def make(*sources):
    clock, ids = Clock(), count()
    return Scheduler(sources, clock, new_run_id=lambda: f'run-{next(ids)}'), clock


def run_all(sched, ok=True):
    runs = sched.dispatch()
    for sid, rid in runs:
        sched.complete(sid, rid, ok)
    return [sid for sid, _ in runs]


def test_weekly_and_quarterly_due_dates():
    sched, clock = make(WEEKLY, QUARTERLY)
    assert run_all(sched) == ['w', 'q']
    assert sched.state['w'].next_due == T0 + timedelta(days=7)
    assert sched.state['q'].next_due == T0 + timedelta(days=91)
    clock.now = T0 + timedelta(days=6)
    assert run_all(sched) == []
    clock.now = T0 + timedelta(days=7)
    assert run_all(sched) == ['w']
    clock.now = T0 + timedelta(days=91)
    assert sorted(run_all(sched)) == ['q', 'w']


def test_concurrent_dispatch_is_deduplicated():
    sched, _ = make(WEEKLY)
    assert len(sched.dispatch()) == 1 and sched.dispatch() == []
    sched.complete('w', 'stale-run', True)
    assert sched.state['w'].last_success is None


def test_expired_lease_redispatches():
    sched, clock = make(WEEKLY)
    sched.dispatch()
    clock.now = T0 + timedelta(hours=2)
    assert [s for s, _ in sched.dispatch()] == ['w']


def test_retry_backoff_then_success():
    sched, clock = make(WEEKLY)
    run_all(sched, ok=False)
    assert sched.state['w'].next_due == T0 + timedelta(minutes=15)
    clock.now += timedelta(minutes=15)
    run_all(sched, ok=False)
    assert sched.state['w'].next_due == clock.now + timedelta(hours=1)
    clock.now += timedelta(hours=1)
    run_all(sched)
    assert sched.state['w'].attempts == 0 and sched.state['w'].last_success == clock.now


def test_disabled_and_unlicensed_sources_are_skipped():
    sched, _ = make(DISABLED, UNLICENSED, WEEKLY)
    assert run_all(sched) == ['w']


def test_missed_runs_catch_up_once():
    sched, clock = make(WEEKLY)
    run_all(sched)
    clock.now = T0 + timedelta(days=40)
    assert run_all(sched) == ['w']
    assert sched.state['w'].next_due == clock.now + timedelta(days=7)
    assert run_all(sched) == []


def test_force_due_before_time_sensitive_recommendation():
    sched, clock = make(QUARTERLY)
    run_all(sched)
    clock.now += timedelta(days=1)
    sched.force_due('q')
    assert run_all(sched) == ['q']


def test_shipped_register_loads():
    path = Path(__file__).resolve().parents[3] / 'config' / 'oracle2' / 'industry-sources.yaml'
    sources = load_register(path)
    assert 'cpsc-recalls' in {s.source_id for s in sources}
    assert not next(s for s in sources if s.source_id == 'astm-f963').authorized


def test_failures_exhaust_budget_until_next_regular_refresh():
    sched, clock = make(WEEKLY)
    for delay in (timedelta(minutes=15), timedelta(hours=1), timedelta(hours=6)):
        assert run_all(sched, ok=False) == ['w']
        assert sched.dispatch() == []
        clock.now += delay
    assert run_all(sched, ok=False) == ['w']
    state = sched.state['w']
    assert state.attempts == 4 and state.exhausted
    due = clock.now + WEEKLY.interval
    assert state.next_due == due
    sched.force_due('w')
    assert state.next_due == due and sched.dispatch() == []
    clock.now = due
    assert run_all(sched) == ['w']
    assert state.attempts == 0 and not state.exhausted


def test_lost_worker_receipts_cannot_bypass_retry_budget():
    sched, clock = make(WEEKLY)
    runs = []
    for _ in range(4):
        runs += sched.dispatch()
        clock.now += timedelta(hours=2)
    assert sched.dispatch() == []
    state = sched.state['w']
    assert state.exhausted and state.attempts == 4
    sched.complete(*runs[-1], True)
    assert state.last_success is None and state.exhausted
