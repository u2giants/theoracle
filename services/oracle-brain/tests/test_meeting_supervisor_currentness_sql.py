"""Actual same-intent fresh supervisor SQL; signed producer proof is separate."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib,time
import psycopg
import pytest
from test_meeting_delivery_sql import delivery,meeting_sql,original_fence,prepare,claim
from test_meeting_capture_sql import admin,deadline


def fresh(x,seconds=2):
    now=datetime.now(timezone.utc);observer=x['observer'];f=observer['factory']
    h=f.supervision_head_v1(caller_deadline=deadline());seal=hashlib.sha256(uuid4().bytes).hexdigest()
    return f.transition_v1(expected_head=h.version,operation_id=uuid4(),action='supervised',payload=dict(
        scope_sha256='e'*64,create_operation_id=str(x['operation']),request_sha256=x['sha'],
        witness_sha256=seal,witness_object_key=f'meeting-supervisor/{x["workspace"]}/{x["meeting"]}/{seal}.bin',
        nonce=hashlib.sha256(uuid4().bytes).hexdigest(),observed_at=now.isoformat(),
        valid_until=min(now+timedelta(seconds=seconds),x['capture_until']).isoformat(),
        scheduler_observation_sha256='c'*64),caller_deadline=deadline())


def test_current_fresh_receipt_does_not_replace_original_intent_or_renew_claim(delivery):
    x=delivery;fresh(x);prepared=prepare(x);end=min(deadline(),x['capture_until'])
    with admin(x) as c:
        original=c.execute("SELECT payload FROM oracle2.meeting_capture_events_v1 WHERE event_id=%s",(prepared.intent_event_id,)).fetchone()[0]
    time.sleep(2.05)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):claim(x,caller_deadline=end)
    fresh(x);claimed=claim(x,caller_deadline=end)
    assert claimed.fresh_claim and claimed.claim_original_deadline==end
    time.sleep(2.05)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['creator']['factory']._worker_delivery_v1('current',operation_id=x['operation'],claim_id=claimed.claim_id,caller_deadline=end)
    fresh(x)
    current=x['creator']['factory']._worker_delivery_v1('current',operation_id=x['operation'],claim_id=claimed.claim_id,caller_deadline=end)
    assert current.claim_id==claimed.claim_id and current.claim_original_deadline==end
    with admin(x) as c:
        assert c.execute('SELECT payload FROM oracle2.meeting_capture_events_v1 WHERE event_id=%s',(prepared.intent_event_id,)).fetchone()==(original,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_fresh_observation_cannot_reopen_cancelled_or_reset_spent_scope(delivery):
    x=delivery;fresh(x);prepare(x);end=min(deadline(),x['capture_until']);one=claim(x,caller_deadline=end)
    control=x['employee-control']['factory'];h=control.head_v1(caller_deadline=end)
    control.transition_v1(expected_head=h.version,operation_id=uuid4(),action='cancel',payload={},caller_deadline=end)
    with pytest.raises(psycopg.errors.RaiseException,match='terminal meeting cannot resume'):fresh(x)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['creator']['factory']._worker_delivery_v1('current',operation_id=x['operation'],claim_id=one.claim_id,caller_deadline=end)
    with admin(x) as c:
        assert c.execute('SELECT state,capture_open FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()==('cancelled',False)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
