"""Actual independently appointed own-role queue reads; not process liveness."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib,json
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.meeting_capture_v1 import MeetingCaptureConfigV1,load_meeting_capture_settings_v1
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.parent_observer_v2 import MeetingSupervisorScopeV1
from oracle_brain.hosting.meeting_supervision_service_v1 import (MeetingSupervisionConfigV1,
    MeetingSupervisionFactoryV1,load_meeting_supervision_settings_v1)
from oracle_brain.meetings.create_stop_relation import CreateOperationStopRelationV1
from test_meeting_capture_sql import meeting_sql,admin,original_request_fence,invite,deadline
from test_replacement_requester_sql import configured_settings


def pinned(tmp_path,name,record):
    path=tmp_path/name;raw=canonical_bytes(record.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
    return path,hashlib.sha256(raw).hexdigest()


@pytest.fixture
def supervision_queue(meeting_sql,tmp_path):
    x=meeting_sql;roles={}
    for kind in ('scheduler','stop'):
        role='supervision_'+uuid4().hex[:12];actor=uuid4();leaf=uuid4();admission=uuid4();seal=hashlib.sha256(admission.bytes).hexdigest()
        with admin(x) as c:
            c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal('invented-supervision-only')))
            c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(role)))
            c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(role,x['runtime'],x['registry'],x['until']))
            c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(role,actor,x['workspace'],x['runtime'],x['registry'],x['until']))
            c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'meeting-capture',%s,%s,%s)",(leaf,x['workspace'],actor,x['owner'],x['root'],x['until']))
        d=tmp_path/kind;d.mkdir(mode=0o700)
        own=x|dict(login=role,actor=actor,url=psycopg.conninfo.make_conninfo(x['admin'],user=role,password='invented-supervision-only'))
        host=configured_settings(d,own)
        # All these explicit independent installation pins precede invitation.
        cfg=host.config.model_copy(update=dict(expires_at=x['until'],original_horizon=x['until']))
        cp,ch=pinned(d,'long-original-config',cfg)
        apt=host.appointment.model_copy(update=dict(config_sha256=ch,expires_at=x['until'],original_horizon=x['until']))
        ap,ah=pinned(d,'long-original-appointment',apt)
        host=load_original_intake_settings_v1(cp,ch,ap,ah,host.expected_issuer_actor,host.expected_reviewer_actor)
        roles[kind]=dict(host=host,role=role,actor=actor,leaf=leaf,admission=admission,seal=seal,dir=d)
    with admin(x) as c:
        original=c.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(x['worker']['admission'],)).fetchone()[0]
    scope=MeetingSupervisorScopeV1(workspace_id=x['workspace'],meeting_id=x['meeting'],provider_account=x['account'],create_operation_id=uuid4(),create_request_sha256='a'*64,
        scheduler_id=roles['scheduler']['actor'],scheduler_runtime_sha256='b'*64,scheduler_config_sha256='c'*64,
        stop_owner_id=roles['stop']['actor'],stop_runtime_sha256='d'*64,stop_config_sha256='e'*64,capture_until=x['capture_until'],
        stop_valid_from=datetime.fromisoformat(original['stop_valid_from']),stop_until=x['until'],original_horizon=x['until'],scheduler_poll_seconds=1,stop_request_seconds=3,safety_allowance_seconds=1,stop_margin_seconds=5)
    relation=CreateOperationStopRelationV1(purpose='meeting-create-operation-stop-relation-v1',mapping_id=uuid4(),provider='recall',tenant_id='tenant1',provider_meeting_id='meeting1',supervision_scope_sha256=digest(scope.model_dump(mode='json')),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=scope.stop_valid_from,expires_at=scope.stop_until,
        **{k:getattr(scope,k) for k in ('workspace_id','meeting_id','provider_account','create_operation_id','create_request_sha256','scheduler_id','scheduler_runtime_sha256','scheduler_config_sha256','stop_owner_id','stop_runtime_sha256','stop_config_sha256','capture_until','stop_valid_from','stop_until','original_horizon')})
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_create_stop_relations_v1(mapping_id,workspace_id,meeting_id,mapping_sha256,mapping_payload) VALUES(%s,%s,%s,%s,%s)',(relation.mapping_id,x['workspace'],x['meeting'],relation.sha256,Jsonb(relation.model_dump(mode='json'))))
    for kind,own in roles.items():
        row=dict(original,admission_id=str(own['admission']),admission_sha256=own['seal'],role_name=own['role'],principal_id=str(own['actor']),leaf_appointment_id=str(own['leaf']),actions=['supervise','status'],
            supervision_scope_sha256=relation.supervision_scope_sha256,stop_relation_id=str(relation.mapping_id),stop_mapping_sha256=relation.sha256)
        with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
        host=own['host'];cfg=x['worker']['settings'].config.model_copy(update=dict(host_config_sha256=host.config_sha256,host_appointment_sha256=host.appointment_sha256,admission_id=own['admission'],admission_sha256=own['seal'],expires_at=x['until'],original_horizon=x['until']))
        cp,ch=pinned(own['dir'],'capture',cfg);capture=load_meeting_capture_settings_v1(host,cp,ch)
        config=MeetingSupervisionConfigV1(purpose='meeting-supervision-queue-consumer-v1',capture_config_sha256=ch,process_purpose='meeting-scheduler-process-v1' if kind=='scheduler' else 'meeting-stop-worker-process-v1',scope=scope,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=scope.capture_until if kind=='scheduler' else scope.stop_until)
        cp,ch=pinned(own['dir'],'supervision',config);own['settings']=load_meeting_supervision_settings_v1(capture,cp,ch)
        own['factory']=MeetingSupervisionFactoryV1(own['settings'])
    invite(x)
    return x,roles,scope,relation


def test_actual_distinct_scheduler_and_STOP_roles_observe_same_current_owned_queue(supervision_queue):
    x,roles,scope,_=supervision_queue;end=min(deadline(),scope.capture_until)
    scheduler=roles['scheduler']['factory'].current_queue_v1(caller_deadline=end)
    stop=roles['stop']['factory'].current_queue_v1(caller_deadline=end)
    assert scheduler.queue_observation_sha256==stop.queue_observation_sha256
    assert scheduler.scope_sha256==stop.scope_sha256==digest(scope.model_dump(mode='json'))
    assert scheduler.principal_id!=stop.principal_id
    assert scheduler.process_purpose=='meeting-scheduler-process-v1' and stop.process_purpose=='meeting-stop-worker-process-v1'
    assert scheduler.observation_only is True and scheduler.remote_stop_proven is False
    assert stop.runtime_sha256==scope.stop_runtime_sha256 and stop.config_sha256==scope.stop_config_sha256
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_actual_revocation_and_missing_original_context_refuse_without_queue_authority(supervision_queue,monkeypatch):
    from oracle_brain.operating_model.request_deadline_v1 import _request_end_v1
    x,roles,scope,relation=supervision_queue;factory=roles['stop']['factory'];calls=[];real=psycopg.connect
    monkeypatch.setattr(psycopg,'connect',lambda *a,**k:(calls.append(1),real(*a,**k))[1])
    token=_request_end_v1.set(None)
    try:
        MeetingSupervisionFactoryV1(roles['stop']['settings'])
        with pytest.raises(PermissionError,match='original protected request fence'):factory.current_queue_v1(caller_deadline=deadline())
        assert calls==[]
    finally:_request_end_v1.reset(token)
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_create_stop_relation_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),relation.mapping_id,'f'*64))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):factory.current_queue_v1(caller_deadline=min(deadline(),scope.capture_until))
