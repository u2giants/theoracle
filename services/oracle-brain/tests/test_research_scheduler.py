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


def test_expired_lease_retains_unknown_without_redispatch():
    sched, clock = make(WEEKLY)
    original=sched.dispatch()[0]
    clock.now = T0 + timedelta(hours=2)
    assert sched.dispatch()==[]
    state=sched.state['w']
    assert state.uncertain and state.in_flight==original[1] and state.attempts==1
    assert sched.force_due('w')=='UNKNOWN' and sched.dispatch()==[]


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


def test_lost_worker_receipt_preserves_original_unknown_without_budget_reset():
    sched, clock = make(WEEKLY)
    original=sched.dispatch()[0]
    for delay in (timedelta(hours=2),timedelta(days=8),timedelta(days=365)):
        clock.now+=delay
        assert sched.dispatch()==[] and sched.force_due('w')=='UNKNOWN'
    state=sched.state['w']
    assert state.uncertain and state.in_flight==original[1] and state.attempts==1
    assert not state.exhausted and state.last_success is None
    assert sched.complete('w','unrelated-run',True)=='stale'
    assert state.in_flight==original[1] and state.last_success is None


def test_actual_simultaneous_threads_claim_once_on_shared_instance():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier,Event,Lock
    start=Barrier(3);entered=Event();release=Event();second_generator=Event();guard=Lock();calls=[]
    def next_id():
        with guard:
            index=len(calls);calls.append(index)
        if index==0:
            entered.set()
            assert release.wait(2),'test failed to release owned factory'
        else:second_generator.set()
        return f'owned-{index}'
    sched=Scheduler((WEEKLY,),Clock(),new_run_id=next_id)
    def dispatch():
        start.wait(timeout=2)
        return sched.dispatch()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(dispatch);second=pool.submit(dispatch)
        start.wait(timeout=2)
        try:
            assert entered.wait(2)
            assert not second_generator.wait(.05)
        finally:release.set()
        results=[first.result(timeout=2),second.result(timeout=2)]
    assert sorted(map(len,results))==[0,1] and calls==[0]
    assert sched.state['w'].attempts==1


def test_matching_current_terminal_observation_resolves_unknown_and_preserves_backoff():
    sched,clock=make(WEEKLY);source,run=sched.dispatch()[0]
    clock.now+=timedelta(hours=2)
    assert sched.due()==[] and sched.state[source].uncertain
    assert sched.complete(source,run,False)=='recorded'
    state=sched.state[source]
    assert not state.uncertain and state.in_flight is None and state.attempts==1
    assert state.next_due==clock.now+timedelta(minutes=15)
    assert sched.complete(source,run,False)=='duplicate'
    import pytest
    with pytest.raises(ValueError,match='conflicting'):sched.complete(source,run,True)
    clock.now=state.next_due
    _,retry=sched.dispatch()[0]
    assert retry!=run and state.attempts==2
    assert sched.complete(source,run,False)=='duplicate' and state.in_flight==retry
    assert sched.complete(source,retry,True)=='recorded'
    assert state.last_success==clock.now and state.attempts==0
    # An older unretained result is explicit stale, not a claim of success.
    assert sched.complete(source,run,True)=='stale'


def test_completion_needs_current_rights_even_for_exact_uncertain_attempt():
    import pytest
    sched,clock=make(WEEKLY);source,run=sched.dispatch()[0]
    clock.now+=timedelta(hours=2);sched.due()
    from dataclasses import replace
    sched.sources=(replace(WEEKLY,enabled=False),)
    with pytest.raises(PermissionError):sched.complete(source,run,True)
    state=sched.state[source]
    assert state.uncertain and state.in_flight==run and state.last_success is None
    assert sched.dispatch()==[]


def test_single_observed_clock_sample_for_each_transition():
    class CountedClock:
        def __init__(self):self.calls=0
        def __call__(self):self.calls+=1;return T0
    clock=CountedClock();sched=Scheduler((WEEKLY,),clock)
    _,run=sched.dispatch()[0];assert clock.calls==1
    sched.due();assert clock.calls==2
    sched.complete('w',run,True);assert clock.calls==3
    sched.force_due('w');assert clock.calls==4


def test_duplicate_and_stale_receipts_cannot_advance_observed_success():
    sched,clock=make(WEEKLY);_,run=sched.dispatch()[0]
    assert sched.complete('w',run,True)=='recorded'
    state=sched.state['w'];first_success=state.last_success
    clock.now+=timedelta(days=1)
    assert sched.complete('w',run,True)=='duplicate'
    assert sched.complete('w','stale-run',True)=='stale'
    assert state.last_success==first_success and state.next_due==T0+timedelta(days=7)


def test_unknown_identity_and_nonboolean_completion_never_create_or_mutate_state():
    import pytest
    from dataclasses import asdict
    sched,_=make(WEEKLY);_,run=sched.dispatch()[0]
    original=asdict(sched.state['w'])
    for source,identity,ok in [('missing',run,True),('w','',True),('w',run,1),('w','bad id',False)]:
        with pytest.raises(ValueError):sched.complete(source,identity,ok)
        assert asdict(sched.state['w'])==original and set(sched.state)=={'w'}
    with pytest.raises(ValueError):sched.force_due('missing')
    assert set(sched.state)=={'w'}


def test_invalid_clock_state_and_boolean_access_denied_before_claim():
    import pytest
    from oracle_brain.research.refresh import SourceState
    for stamp in (T0.replace(tzinfo=None),'not-a-clock'):
        sched=Scheduler((WEEKLY,),lambda:stamp)
        with pytest.raises(ValueError):sched.dispatch()
        assert sched.state=={}
    sched,clock=make(WEEKLY);sched.due();clock.now-=timedelta(seconds=1)
    with pytest.raises(ValueError):sched.dispatch()
    assert sched.state=={}
    with pytest.raises(ValueError):SourceState(attempts=True)
    with pytest.raises(ValueError):SourceState(in_flight='run',attempts=1)
    with pytest.raises(ValueError):SourceState(uncertain=True)
    with pytest.raises(ValueError):SourceState(exhausted=True)
    from dataclasses import replace
    damaged=replace(WEEKLY);object.__setattr__(damaged,'rights_confirmed',1)
    with pytest.raises(ValueError):Scheduler((damaged,),Clock())
    with pytest.raises(ValueError):Scheduler((WEEKLY,WEEKLY),Clock())
    with pytest.raises(ValueError):Scheduler((WEEKLY,),Clock(),state={'foreign':SourceState()})


def test_failed_or_colliding_run_factory_leaves_entire_claim_batch_unmodified():
    import pytest
    def failed():raise RuntimeError('invented generator outage')
    sched=Scheduler((WEEKLY,),Clock(),new_run_id=failed)
    with pytest.raises(RuntimeError):sched.dispatch()
    assert sched.state=={}
    for bad in ('',True,'has space'):
        sched=Scheduler((WEEKLY,),Clock(),new_run_id=lambda:bad)
        with pytest.raises(ValueError):sched.dispatch()
        assert sched.state=={}
    sched=Scheduler((WEEKLY,QUARTERLY),Clock(),new_run_id=lambda:'same-run')
    with pytest.raises(ValueError,match='collision'):sched.dispatch()
    assert sched.state=={}


def test_previous_issued_run_id_cannot_be_reused_in_later_cadence():
    import pytest
    sched=Scheduler((WEEKLY,),Clock(),new_run_id=lambda:'same-run')
    _,run=sched.dispatch()[0];sched.complete('w',run,True)
    sched.force_due('w')
    with pytest.raises(ValueError,match='collision'):sched.dispatch()
    assert sched.state['w'].attempts==0 and sched.state['w'].in_flight is None


def test_current_external_state_damage_does_not_bypass_validation():
    import pytest
    sched,clock=make(WEEKLY);_,run=sched.dispatch()[0]
    sched.state['w'].attempts=0
    with pytest.raises(ValueError):sched.complete('w',run,False)
    assert sched.state['w'].in_flight==run


def test_matching_late_success_is_explicit_observation_not_lease_inference():
    sched,clock=make(WEEKLY);_,run=sched.dispatch()[0]
    clock.now+=timedelta(days=10)
    assert sched.dispatch()==[] and sched.state['w'].last_success is None
    assert sched.complete('w',run,True)=='recorded'
    state=sched.state['w']
    assert state.last_success==clock.now and state.next_due==clock.now+timedelta(days=7)


def test_separate_instances_are_explicitly_not_durable_or_cross_process_claims():
    first,_=make(WEEKLY);second,_=make(WEEKLY)
    assert len(first.dispatch())==1 and len(second.dispatch())==1
    assert first.state is not second.state  # no cross-instance guarantee claimed


def test_denied_late_receipt_still_preserves_observed_unknown_identity():
    import pytest
    from dataclasses import replace
    sched,clock=make(WEEKLY);_,run=sched.dispatch()[0]
    clock.now+=timedelta(hours=2)
    sched.sources=(replace(WEEKLY,enabled=False),)
    with pytest.raises(PermissionError):sched.complete('w',run,True)
    assert sched.state['w'].uncertain and sched.state['w'].in_flight==run
    assert sched.state['w'].last_success is None and sched.state['w'].attempts==1


def test_concurrent_force_and_terminal_observation_dont_duplicate_claim():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    sched,clock=make(WEEKLY);_,run=sched.dispatch()[0]
    start=Barrier(3)
    def finish():start.wait(timeout=2);return sched.complete('w',run,True)
    def force():start.wait(timeout=2);return sched.force_due('w')
    with ThreadPoolExecutor(max_workers=2) as pool:
        completed=pool.submit(finish);forced=pool.submit(force)
        start.wait(timeout=2)
        assert completed.result(timeout=2)=='recorded'
        assert forced.result(timeout=2) in {'in_flight','due'}
    # If force followed the receipt it may request one NEW known-terminal run;
    # it cannot duplicate the completed attempt or leave two current attempts.
    runs=sched.dispatch()
    assert len(runs)<=1 and all(identity!=run for _,identity in runs)
    assert sched.state['w'].attempts in (0,1)


def test_timestamp_overflow_denies_before_claim_or_terminal_mutation():
    import pytest
    extreme=datetime.max.replace(tzinfo=timezone.utc)
    sched=Scheduler((WEEKLY,),lambda:extreme)
    with pytest.raises(ValueError,match='scheduling bounds'):sched.dispatch()
    assert sched.state=={}
    sched,clock=make(WEEKLY);_,run=sched.dispatch()[0]
    clock.now=extreme
    with pytest.raises(ValueError,match='scheduling bounds'):sched.complete('w',run,True)
    state=sched.state['w']
    assert state.in_flight==run and state.attempts==1 and state.last_completed_run is None
    assert state.last_success is None and state.uncertain
