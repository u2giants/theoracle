"""Actual own-role SQL/private-wire custody, invented fixture installation.

No Trigger/provider request, real key, actual task/employee/live proof.
"""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,time
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_capture_v1 import load_meeting_capture_settings_v1
from oracle_brain.hosting.meeting_queue_v1 import (MeetingQueueConfigV1,load_meeting_queue_settings_v1,MeetingQueueFactoryV1)
from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
from oracle_brain.meetings.queue_contracts import observe_queue_wire_v1
from test_meeting_capture_sql import meeting_sql,admin,ingest,invite,deadline,original_request_fence
from test_replacement_requester_sql import configured_settings


def pinned(tmp,name,value):
    data=canonical_bytes(value.model_dump(mode='json'));p=tmp/name;p.write_bytes(data);p.chmod(0o600);return p,hashlib.sha256(data).hexdigest()

@pytest.fixture
def queue(meeting_sql,tmp_path):
    x=meeting_sql;invite(x);event=ingest(x).event_id;actor=uuid4();role='meeting_queue_'+uuid4().hex[:12];leaf=uuid4();selected=uuid4();seal=hashlib.sha256(selected.bytes).hexdigest()
    with admin(x) as c:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal('invented-queue-only')))
        c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(role)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(role,x['runtime'],x['registry'],x['until']))
        c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(role,actor,x['workspace'],x['runtime'],x['registry'],x['until']))
        c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'meeting-capture',%s,%s,%s)",(leaf,x['workspace'],actor,x['owner'],x['root'],x['until']))
    own=x|dict(login=role,actor=actor,url=psycopg.conninfo.make_conninfo(x['admin'],user=role,password='invented-queue-only'))
    d=tmp_path/'queue';d.mkdir(mode=0o700);host=configured_settings(d,own)
    pins=dict(queue_project_ref='invented-meetings-project',queue_environment_id='invented-meetings-environment',queue_account_id='invented-independent-account',queue_task_id='oracle2-meeting-ingress-normalize-v1',queue_credential_sha256='1'*64,queue_installation_receipt_sha256='2'*64,queue_target_descriptor_sha256='3'*64)
    with admin(x) as c:
        row=c.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(x['worker']['admission'],)).fetchone()[0]
        row.update(admission_id=str(selected),admission_sha256=seal,principal_id=str(actor),role_name=role,leaf_appointment_id=str(leaf),actions=['outbox','status'],**pins)
        c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
    cfg=x['worker']['settings'].config.model_copy(update=dict(host_config_sha256=host.config_sha256,host_appointment_sha256=host.appointment_sha256,admission_id=selected,admission_sha256=seal));p,h=pinned(d,'capture',cfg);capture=load_meeting_capture_settings_v1(host,p,h)
    now=datetime.now(timezone.utc);config=MeetingQueueConfigV1(purpose='meeting-ingress-queue-consumer-v1',capture_config_sha256=capture.config_sha256,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=x['until'],original_processing_horizon=x['until'],**pins)
    p,h=pinned(d,'queue-config',config);f=MeetingQueueFactoryV1(load_meeting_queue_settings_v1(capture,p,h,config.issuer_actor,config.reviewer_actor))
    return x,f,event,own,row


def wire(body=b'{"id":"run_invented_123"}',status=200):
    return f'HTTP/1.1 {status} OK\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n'.encode()+body


def test_actual_separate_queue_role_first_claim_body_once_and_retained_observation(queue):
    x,f,event,own,row=queue;end=deadline();pending=f.pending_v1(caller_deadline=end)
    assert pending.ingress_event_id==event and pending.body is None and pending.state=='idle'
    first=f.claim_v1(event,caller_deadline=end)
    assert first.fresh_claim and first.body['payload']=={'ingress_event_id':str(event)}
    assert hashlib.sha256(canonical_bytes(first.body)).hexdigest()==first.request_sha256
    again=f.claim_v1(event,caller_deadline=end);assert again.state=='UNKNOWN' and again.body is None and not again.fresh_claim
    assert f.pending_v1(caller_deadline=end).ingress_event_id is None
    current=f.current_claim_v1(event,first.claim_id,first.request_sha256,caller_deadline=end);assert current.state=='inflight'
    run_id='run_'+'a'*252;response=wire(canonical_bytes({'id':run_id}))
    result=f.receipt_v1(event,first.claim_id,first.request_sha256,response,caller_deadline=end)
    assert result.state=='observed' and result.run_id==run_id and result.body is None and result.remote_stop_proven is False and result.unresolved_count==0
    assert f.receipt_v1(event,first.claim_id,first.request_sha256,response,caller_deadline=end).state=='observed'
    with pytest.raises(ValueError):f.receipt_v1(event,first.claim_id,first.request_sha256,wire(b'{"id":"run_altered"}'),caller_deadline=end)
    with pytest.raises(PermissionError):f.current_claim_v1(event,first.claim_id,first.request_sha256,caller_deadline=end)
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_enqueue_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_enqueue_receipts_v1 r JOIN oracle2.meeting_capture_enqueue_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute("SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s AND action='outbox'",(x['workspace'],)).fetchone()==(1,)
    with psycopg.connect(own['url']) as c:
        c.execute("SET LOCAL statement_timeout='5s'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT * FROM oracle2.meeting_capture_enqueue_claims_v1')


def test_actual_uncertainty_is_terminal_no_current_effect_or_reinstalled_body(queue,tmp_path):
    x,f,event,_own,row=queue;end=deadline();first=f.claim_v1(event,caller_deadline=end)
    result=f.receipt_v1(event,first.claim_id,first.request_sha256,b'HTTP/1.1 200 incomplete',error='framing',caller_deadline=end)
    assert result.state=='UNKNOWN' and result.run_id is None and result.unresolved_count==1
    with pytest.raises(PermissionError):f.current_claim_v1(event,first.claim_id,first.request_sha256,caller_deadline=end)
    selected=uuid4();seal=hashlib.sha256(selected.bytes).hexdigest();new=dict(row,admission_id=str(selected),admission_sha256=seal)
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(new),))
    cfg=f.settings.capture.config.model_copy(update=dict(admission_id=selected,admission_sha256=seal));p,h=pinned(tmp_path,'reinstalled-capture',cfg);capture=load_meeting_capture_settings_v1(f.settings.capture.host,p,h)
    qc=f.settings.config.model_copy(update=dict(capture_config_sha256=capture.config_sha256));p,h=pinned(tmp_path,'reinstalled-queue',qc);other=MeetingQueueFactoryV1(load_meeting_queue_settings_v1(capture,p,h,qc.issuer_actor,qc.reviewer_actor))
    again=other.claim_v1(event,caller_deadline=end);assert again.state=='UNKNOWN' and again.body is None and again.claim_id==first.claim_id
    with pytest.raises(psycopg.errors.InsufficientPrivilege):other.current_claim_v1(event,first.claim_id,first.request_sha256,caller_deadline=end)


def test_concurrent_actual_queue_claims_return_executable_body_once(queue):
    x,f,event,_own,_row=queue;end=deadline()
    def claim():
        with _request_fence_v1(float(time.monotonic()+max(0,(end-datetime.now(timezone.utc)).total_seconds()))):return f.claim_v1(event,caller_deadline=end)
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim(),range(2)))
    assert sum(r.fresh_claim for r in results)==1 and sum(r.body is not None for r in results)==1


def test_old_null_admission_and_wrong_claim_cannot_issue_queue_effect(queue):
    x,f,event,_own,_row=queue
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['worker']['factory']._enqueue_binding_v1('pending',None,caller_deadline=deadline())
    first=f.claim_v1(event,caller_deadline=deadline())
    with pytest.raises(PermissionError):f.current_claim_v1(event,uuid4(),first.request_sha256,caller_deadline=deadline())
    with pytest.raises(PermissionError):f.current_claim_v1(event,first.claim_id,'f'*64,caller_deadline=deadline())


@pytest.mark.parametrize('raw',[wire(status=202),wire(b'{"id":"run_a","role":"admin"}'),wire(b'{"id":"run_a","id":"run_b"}'),wire()+b'EXTRA',wire()[:-1],wire(b'{"id":NaN}'),wire(b'{"id":true}'),wire(canonical_bytes({'id':'a'*257}))])
def test_closed_queue_wire_cannot_invent_observed_task(raw):
    assert observe_queue_wire_v1(raw)['kind']=='UNKNOWN'
