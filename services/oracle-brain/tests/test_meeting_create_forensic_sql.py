"""Owned SQL + actual retained invented wire, not real provider installation."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import json,time
import psycopg
from psycopg.types.json import Jsonb
import pytest
from test_meeting_delivery_sql import delivery,meeting_sql,original_fence,worker_factory,clone,prepare,claim
from test_meeting_capture_sql import admin,deadline

def response(status=201,body=None):
    raw=json.dumps(body or {'id':str(uuid4())},separators=(',',':')).encode()
    return b'HTTP/1.1 '+str(status).encode()+b' OK\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw

def cancel(x,original):
    owner=x['employee-control']['factory'];head=owner.head_v1(caller_deadline=original)
    return owner.transition_v1(expected_head=head.version,operation_id=uuid4(),action='cancel',payload={},caller_deadline=original)

def begin(x,tmp_path):
    f=worker_factory(x,x['creator'],tmp_path);original=min(deadline(),x['capture_until']);f.prepare_v1(caller_deadline=original)
    claimed,body=f.claim_v1(x['operation'],caller_deadline=original);assert body==x['body'];return f,original,claimed

def head_state(x):
    with admin(x) as c:return c.execute('SELECT state,capture_open,capture_until,version FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()

@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
def test_actual_complete_create_after_cancel_retains_exact_relation_for_separate_STOP_without_reopening(delivery,tmp_path):
    x=delivery;f,original,claimed=begin(x,tmp_path);closed=cancel(x,original);bot=uuid4();raw=response(body={'id':str(bot)})
    receipt=f.observe_v1(x['operation'],claimed.claim_id,raw,caller_deadline=original);assert receipt.state=='observed'
    state=head_state(x);assert state[:3]==('cancelled',False,x['capture_until']) and state[3]==closed.version+1
    # A lost successful handoff can be reconciled read-only; duplicate receipt
    # cannot mint another event, new intent or executable body.
    assert worker_factory(x,x['creator'],tmp_path).status_v1(caller_deadline=original).receipt_id==receipt.receipt_id
    repeated=f.observe_v1(x['operation'],claimed.claim_id,raw,caller_deadline=original);assert repeated.receipt_id==receipt.receipt_id and head_state(x)==state
    with admin(x) as c:
        events=c.execute("SELECT action,payload FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='create_observed_after_close'",(x['workspace'],)).fetchall();assert len(events)==1
        payload=events[0][1];assert payload['bot_id']==str(bot) and payload['claim_id']==str(claimed.claim_id) and payload['intent_id']==str(x['operation']) and payload['request_sha256']==x['sha']
    # The independent fixture installer explicitly supplies the exact bot map;
    # the creation receipt never installs that mapping or grants a STOP role.
    stop=clone(x,x['worker'],dict(actions=['supervise','stop_intent','stop_observed','stop_unknown','status'],bot_id=str(bot)))
    due=stop['factory'].due_stop_v1(caller_deadline=original);assert due.created_bot['bot_id']==str(bot)
    time.sleep(max(0,(due.due_at-datetime.now(timezone.utc)).total_seconds()+0.05))
    h=stop['factory'].head_v1(caller_deadline=original)
    stopped=stop['factory'].transition_v1(expected_head=h.version,operation_id=uuid4(),action='stop_intent',payload=dict(create_intent_id=str(x['operation']),bot_id=str(bot),create_receipt_sha256=payload['receipt_sha256'],stop_mapping_sha256='f'*64,metadata_sha256='e'*64),caller_deadline=original)
    assert stopped.state=='cancelled' and head_state(x)[1] is False

@pytest.mark.parametrize('raw',[response(200),b'HTTP/1.1 201 OK\r\nContent-Length: 10\r\n\r\n{}',response(201,{'id':'not-a-bot'})])
def test_actual_closed_head_partial_status200_or_malformed_wire_stays_unknown_without_guessed_bot(delivery,tmp_path,raw):
    x=delivery;f,original,claimed=begin(x,tmp_path);cancel(x,original);before=head_state(x)
    observed=f.observe_v1(x['operation'],claimed.claim_id,raw,caller_deadline=original)
    assert observed.state=='UNKNOWN' and head_state(x)==before
    with admin(x) as c:assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='create_observed_after_close'",(x['workspace'],)).fetchone()==(0,)

def test_actual_after_close_event_is_not_an_old_API_or_direct_table_capability(delivery,tmp_path):
    x=delivery;f,original,claimed=begin(x,tmp_path);cancel(x,original);before=head_state(x)
    with pytest.raises(psycopg.Error):x['creator']['factory'].transition_v1(expected_head=before[3],operation_id=uuid4(),action='create_observed_after_close',payload={},caller_deadline=original)
    with psycopg.connect(x['creator']['url']) as c:
        assert c.execute("SELECT has_function_privilege(SESSION_USER,'oracle2._meeting_created_bot_v1(oracle2.meeting_capture_admissions_v1)','EXECUTE')").fetchone()==(False,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute("INSERT INTO oracle2.meeting_capture_events_v1(event_id) VALUES(%s)",(uuid4(),))
    assert head_state(x)==before

def test_actual_expired_window_and_forged_complete_receipt_refuse_without_closed_head_change(delivery,tmp_path):
    x=delivery;f,original,claimed=begin(x,tmp_path);cancel(x,original);before=head_state(x)
    with pytest.raises(PermissionError):f.observe_v1(x['operation'],claimed.claim_id,response(),caller_deadline=datetime.now(timezone.utc)-timedelta(seconds=1))
    import hashlib
    raw=response();sha=hashlib.sha256(raw).hexdigest();wire=dict(wire_object_key=f'meeting-worker/{x["workspace"]}/{x["meeting"]}/{claimed.claim_id}/{sha}.wire',wire_sha256=sha,wire_byte_count=len(raw),observation=dict(kind='create-observed',bot_id=str(uuid4()),latest_status=None,complete=False))
    with pytest.raises(psycopg.Error):x['creator']['factory']._worker_delivery_v1('observe',operation_id=x['operation'],claim_id=claimed.claim_id,wire=wire,caller_deadline=original)
    with psycopg.connect(x['creator']['url']) as c:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.meeting_capture_worker_v1(%s,%s,%s,%s,%s,%s,%s,%s)',(x['creator']['admission'],x['creator']['seal'],'observe',x['operation'],claimed.claim_id,None,Jsonb(wire),datetime.now(timezone.utc)-timedelta(seconds=1)))
    assert head_state(x)==before
