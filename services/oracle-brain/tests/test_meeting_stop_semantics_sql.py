"""Actual owned SQL and retained invented wire; no live remote-stop claim."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib,json,time
import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_capture_worker_v1 import load_capture_worker_settings_v1,CaptureWorkerFactoryV1
from test_meeting_delivery_sql import delivery,meeting_sql,original_fence,clone,worker_factory
from test_meeting_create_forensic_sql import begin,cancel,response,head_state
from test_meeting_capture_sql import admin


def worker(x,owner,tmp_path,effect,stage=None,operation=None):
    template=worker_factory(x,x['creator'],tmp_path).settings.config
    with admin(x) as c:identity=c.execute('SELECT worker_id,stop_mapping_sha256 FROM oracle2.meeting_capture_admissions_v1 WHERE admission_id=%s',(owner['admission'],)).fetchone()
    identity,mapping_sha=identity
    config=template.model_copy(update=dict(capture_config_sha256=owner['settings'].config_sha256,worker_id=identity,effect=effect,create_operation_id=None,create_body=None,retrieve_stage=stage,retrieve_operation_id=operation,stop_mapping_sha256=mapping_sha,expires_at=owner['settings'].config.expires_at,original_horizon=owner['settings'].config.original_horizon))
    raw=canonical_bytes(config.model_dump(mode='json'));path=tmp_path/uuid4().hex;path.write_bytes(raw);path.chmod(0o600)
    return CaptureWorkerFactoryV1(load_capture_worker_settings_v1(owner['settings'],path,hashlib.sha256(raw).hexdigest()))


def setup_stop(x,tmp_path,*,closed=True,claim_first=True):
    creator,original,claim=begin(x,tmp_path);bot=uuid4()
    if closed:cancel(x,original)
    raw=response(body={'id':str(bot)});creator.observe_v1(x['operation'],claim.claim_id,raw,caller_deadline=original)
    owner=clone(x,x['worker'],dict(actions=['supervise','stop_intent','stop_observed','stop_unknown','status'],bot_id=str(bot),worker_id=str(uuid4()),worker_effect='capture-leave',worker_policy_sha256='d'*64))
    due=owner['factory'].due_stop_v1(caller_deadline=original)
    time.sleep(max(0,(due.due_at-datetime.now(timezone.utc)).total_seconds()+0.02))
    h=owner['factory'].head_v1(caller_deadline=original);stop_id=uuid4()
    owner['factory'].transition_v1(expected_head=h.version,operation_id=stop_id,action='stop_intent',payload=dict(create_intent_id=str(x['operation']),bot_id=str(bot),create_receipt_sha256=hashlib.sha256(raw).hexdigest(),stop_mapping_sha256='f'*64,metadata_sha256='e'*64),caller_deadline=original)
    leave=worker(x,owner,tmp_path,'capture-leave');claimed=None
    if claim_first:
        claimed,body=leave.claim_v1(stop_id,caller_deadline=original);assert body==b''
    return original,bot,owner,leave,claimed,stop_id


def get_owner(x,bot,tmp_path,stage):
    operation=uuid4();owner=clone(x,x['worker'],dict(actions=['stop_reconciled','status'],bot_id=str(bot),worker_id=str(uuid4()),worker_effect='capture-retrieve',worker_policy_sha256='d'*64,worker_retrieve_stage=stage,worker_retrieve_operation_id=str(operation)))
    return owner,worker(x,owner,tmp_path,'capture-retrieve',stage,operation),operation


def metadata(bot,code='done',stamp=None):
    return response(200,dict(id=str(bot),status_changes=[dict(code=code,created_at=stamp or (datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())]))


def stop_state(x):
    with admin(x) as c:return c.execute('SELECT state,capture_open,stop_state FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()


@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
@pytest.mark.parametrize('terminal',['call_ended','done','fatal'])
def test_actual_leave_ACK_only_then_exact_post_stop_terminal_retained_receipt(delivery,tmp_path,terminal):
    x=delivery;original,bot,owner,leave,claimed,stop_id=setup_stop(x,tmp_path)
    ack=b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 0\r\n\r\n'
    leave.observe_v1(stop_id,claimed.claim_id,ack,caller_deadline=original)
    assert stop_state(x)==('cancelled',False,'observed')
    owner,post,op=get_owner(x,bot,tmp_path,'post-stop-terminal');claim,body=post.claim_v1(op,caller_deadline=original);assert body==b''
    raw=metadata(bot,terminal);observed=post.observe_v1(op,claim.claim_id,raw,caller_deadline=original)
    assert stop_state(x)==('cancelled',False,'terminal_observed')
    with admin(x) as c:
        event=c.execute("SELECT payload FROM oracle2.meeting_capture_events_v1 WHERE event_id=%s AND action='stop_reconciled'",(observed.receipt_id,)).fetchone()[0]
    assert event==dict(stop_intent_id=str(stop_id),metadata_sha256=hashlib.sha256(raw.split(b'\r\n\r\n',1)[1]).hexdigest(),terminal_event_id=str(observed.receipt_id))
    before=head_state(x);assert post.observe_v1(op,claim.claim_id,raw,caller_deadline=original).receipt_id==observed.receipt_id and head_state(x)==before
    with pytest.raises(psycopg.Error):owner['factory'].transition_v1(expected_head=before[3],operation_id=uuid4(),action='stop_reconciled',payload=dict(stop_intent_id=str(stop_id),metadata_sha256='e'*64,terminal_event_id=str(observed.receipt_id)),caller_deadline=original)
    assert 'remote_stop_proven' not in observed.observation


@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
@pytest.mark.parametrize('failure',['partial','nonterminal','future','ambiguous','foreign'])
def test_actual_uncertain_leave_and_nonterminal_or_invalid_post_metadata_never_prove_stop(delivery,tmp_path,failure):
    x=delivery;original,bot,owner,leave,claimed,stop_id=setup_stop(x,tmp_path)
    leave.observe_v1(stop_id,claimed.claim_id,b'HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n{}',caller_deadline=original)
    assert stop_state(x)==('cancelled',False,'UNKNOWN')
    owner,post,op=get_owner(x,bot,tmp_path,'post-stop-terminal');claim,_=post.claim_v1(op,caller_deadline=original)
    raw=metadata(bot)
    if failure=='partial':raw=raw[:-1]
    elif failure=='nonterminal':raw=metadata(bot,'in_call_recording')
    elif failure=='future':raw=metadata(bot,stamp=(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat())
    elif failure=='foreign':raw=metadata(uuid4())
    else:
        at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat();raw=response(200,dict(id=str(bot),status_changes=[dict(code='done',created_at=at),dict(code='in_call_recording',created_at=at)]))
    observed=post.observe_v1(op,claim.claim_id,raw,caller_deadline=original)
    assert stop_state(x)==('cancelled',False,'UNKNOWN')
    assert observed.observation['kind']==('metadata-observed' if failure=='nonterminal' else 'UNKNOWN')
    with pytest.raises(psycopg.Error):owner['factory'].transition_v1(expected_head=head_state(x)[3],operation_id=uuid4(),action='stop_reconciled',payload=dict(stop_intent_id=str(stop_id),metadata_sha256='e'*64,terminal_event_id=str(observed.receipt_id)),caller_deadline=original)


@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
def test_actual_pre_stop_terminal_metadata_is_consistency_only_and_cannot_reconcile(delivery,tmp_path):
    x=delivery;creator,original,claim=begin(x,tmp_path);bot=uuid4();creator.observe_v1(x['operation'],claim.claim_id,response(body={'id':str(bot)}),caller_deadline=original)
    owner,pre,op=get_owner(x,bot,tmp_path,'pre-stop-consistency');claim,_=pre.claim_v1(op,caller_deadline=original)
    receipt=pre.observe_v1(op,claim.claim_id,metadata(bot),caller_deadline=original)
    assert stop_state(x)[2]=='not_attempted'
    with pytest.raises(psycopg.Error):owner['factory'].transition_v1(expected_head=head_state(x)[3],operation_id=uuid4(),action='stop_reconciled',payload=dict(stop_intent_id=str(uuid4()),metadata_sha256=receipt.observation['metadata_sha256'],terminal_event_id=str(receipt.receipt_id)),caller_deadline=original)


@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
def test_actual_late_cancel_and_forged_future_receipt_cannot_reopen_or_prove_stop(delivery,tmp_path):
    x=delivery;original,bot,owner,leave,claimed,stop_id=setup_stop(x,tmp_path,closed=False)
    leave.observe_v1(stop_id,claimed.claim_id,b'HTTP/1.1 200 OK\r\nConnection: close\r\nContent-Length: 0\r\n\r\n',caller_deadline=original)
    cancel(x,original);assert stop_state(x)==('cancelled',False,'observed')
    owner,post,op=get_owner(x,bot,tmp_path,'post-stop-terminal');claim,_=post.claim_v1(op,caller_deadline=original)
    raw=metadata(bot);sha=hashlib.sha256(raw).hexdigest()
    # A direct false DTO cannot evade the SQL server's own clock even if its
    # complete/kind labels claim success. The transaction leaves no receipt.
    forged=dict(wire_object_key=f'meeting-worker/{x["workspace"]}/{x["meeting"]}/{claim.claim_id}/{sha}.wire',wire_sha256=sha,wire_byte_count=len(raw),observation=dict(kind='metadata-observed',bot_id=str(bot),latest_status=dict(code='done',created_at=(datetime.now(timezone.utc)+timedelta(seconds=10)).isoformat()),complete=True,metadata_sha256=hashlib.sha256(raw.split(b'\r\n\r\n',1)[1]).hexdigest()))
    with pytest.raises(psycopg.Error):owner['factory']._worker_delivery_v1('observe',operation_id=op,claim_id=claim.claim_id,wire=forged,caller_deadline=original)
    assert stop_state(x)==('cancelled',False,'observed')
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_receipts_v1 WHERE claim_id=%s',(claim.claim_id,)).fetchone()==(0,)
    with pytest.raises(PermissionError):post.observe_v1(op,claim.claim_id,raw,caller_deadline=datetime.now(timezone.utc)-timedelta(seconds=1))
    actual=post.observe_v1(op,claim.claim_id,raw,caller_deadline=original)
    assert stop_state(x)==('cancelled',False,'terminal_observed')
    before=head_state(x)
    with pytest.raises(psycopg.Error):post.observe_v1(op,claim.claim_id,metadata(bot,'fatal'),caller_deadline=original)
    assert head_state(x)==before and post.status_v1(caller_deadline=original).receipt_id==actual.receipt_id
