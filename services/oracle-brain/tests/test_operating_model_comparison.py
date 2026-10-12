from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
import psycopg
from test_operating_model_adapters import test_database
from oracle_brain.operating_model.comparison import ComparisonLedger, checkpoint_due
from oracle_brain.operating_model.contracts import digest

NOW = datetime(2026, 10, 10, 18, tzinfo=timezone.utc)

def event(kind, at=NOW, run_id=None, decision=None):
    return dict(kind=kind, at=at.isoformat(), release_hash='a'*64, evidence_hash='b'*64,
                run_id=str(run_id) if run_id else None, decision=decision)

def append(ledger, w, c, payload):
    return ledger.append(w,c,**{**payload,'run_id': __import__('uuid').UUID(payload['run_id']) if payload['run_id'] else None},admitted_hashes=frozenset({digest(payload)}))

def test_calendar_bound_uses_new_york_dates_and_never_accepts():
    start=datetime(2026,10,10,23,59,tzinfo=__import__('zoneinfo').ZoneInfo('America/New_York'))
    events=[event('begun',start)]
    assert checkpoint_due(events,datetime(2026,10,17,0,0,tzinfo=start.tzinfo))
    with pytest.raises(ValueError,match='timezone'):
        checkpoint_due(events,datetime(2026,10,17))

def test_real_append_only_three_runs_and_checkpoint(test_database):
    ledger=ComparisonLedger(test_database); w=uuid4();c=uuid4()
    append(ledger,w,c,event('begun'))
    for i in range(3):
        payload=event('run',NOW+timedelta(minutes=i+1),uuid4())
        assert append(ledger,w,c,payload)==i+1
        assert append(ledger,w,c,payload)==i+1
    with pytest.raises(PermissionError,match='checkpoint'):
        append(ledger,w,c,event('run',NOW+timedelta(minutes=5),uuid4()))
    with pytest.raises(PermissionError,match='accepted'):
        ledger.require_accepted(w,c,'a'*64)
    append(ledger,w,c,event('checkpoint',NOW+timedelta(minutes=6),decision='blocked'))
    with pytest.raises(PermissionError,match='closed'):
        append(ledger,w,c,event('run',NOW+timedelta(minutes=7),uuid4()))
    with psycopg.connect(test_database) as conn:
        with pytest.raises(psycopg.Error):
            conn.execute('DELETE FROM oracle2.operating_comparison_events WHERE workspace_id=%s',(w,))

def test_exact_event_admission_and_release_acceptance(test_database):
    ledger=ComparisonLedger(test_database);w=uuid4();c=uuid4()
    with pytest.raises(PermissionError,match='independent admission'):
        ledger.append(w,c,kind='begun',at=NOW,release_hash='a'*64,evidence_hash='b'*64,admitted_hashes=frozenset())
    append(ledger,w,c,event('begun'))
    append(ledger,w,c,event('checkpoint',NOW+timedelta(minutes=1),decision='accept'))
    assert ledger.require_accepted(w,c,'a'*64)['decision']=='accept'
    with pytest.raises(PermissionError):ledger.require_accepted(w,c,'c'*64)

def test_seven_day_boundary_blocks_fourth_or_first_run(test_database):
    ledger=ComparisonLedger(test_database);w=uuid4();c=uuid4();append(ledger,w,c,event('begun'))
    with pytest.raises(PermissionError,match='checkpoint'):
        append(ledger,w,c,event('run',NOW+timedelta(days=7),uuid4()))
    assert len(ledger.read(w,c))==1
