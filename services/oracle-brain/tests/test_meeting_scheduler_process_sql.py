"""Actual independently pinned Linux scheduler and own-role SQL queue; no STOP/Create effect proof."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import hashlib,json,os,sys,subprocess,tempfile,shutil,time,socket
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
def actual_scheduler(meeting_sql,tmp_path):
    x=meeting_sql;roles={}
    from oracle_brain.hosting.meeting_scheduler_process_v1 import MeetingSchedulerRuntimeV1
    from oracle_brain.meetings.supervisor_process import InstalledSupervisorProcessV2
    from pathlib import Path
    private=tempfile.TemporaryDirectory(prefix='s07-sched-');short=Path(private.name);short.chmod(0o700)
    runtime=short/'scheduler.py';runtime.write_bytes(Path(__import__('oracle_brain.hosting.meeting_scheduler_process_v1',fromlist=['__file__']).__file__).read_bytes());runtime.chmod(0o600)
    runtime_sha=hashlib.sha256(runtime.read_bytes()).hexdigest();socket_path=short/'scheduler.sock'
    executable=short/'python';shutil.copyfile(os.readlink('/proc/self/exe'),executable);executable.chmod(0o700)
    process=None
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
    create_operation=uuid4()
    for kind,own in roles.items():
        host=own['host'];cfg=x['worker']['settings'].config.model_copy(update=dict(host_config_sha256=host.config_sha256,host_appointment_sha256=host.appointment_sha256,admission_id=own['admission'],admission_sha256=own['seal'],expires_at=x['until'],original_horizon=x['until']))
        cp,ch=pinned(own['dir'],'capture',cfg);own['capture_settings']=load_meeting_capture_settings_v1(host,cp,ch)
    own=roles['scheduler'];host=own['host'];capture=own['capture_settings']
    config=MeetingSchedulerRuntimeV1(purpose='meeting-scheduler-runtime-v1',workspace_id=x['workspace'],meeting_id=x['meeting'],provider_account=x['account'],create_operation_id=create_operation,create_request_sha256='a'*64,capture_until=x['capture_until'],stop_valid_from=datetime.fromisoformat(original['stop_valid_from']),stop_until=x['until'],original_horizon=x['until'],scheduler_poll_seconds=1,stop_request_seconds=3,safety_allowance_seconds=1,stop_margin_seconds=5,socket_file=str(socket_path),observer_uid=os.getuid(),host_config=dict(path=str(host.config_path),sha256=host.config_sha256),host_appointment=dict(path=str(host.appointment_path),sha256=host.appointment_sha256),capture_config=dict(path=str(capture.config_path),sha256=capture.config_sha256),expected_issuer_actor=host.expected_issuer_actor,expected_reviewer_actor=host.expected_reviewer_actor,valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=x['capture_until'])
    scheduler_config,scheduler_sha=pinned(short,'scheduler-config.json',config);runtime_config=config
    scope=MeetingSupervisorScopeV1(workspace_id=x['workspace'],meeting_id=x['meeting'],provider_account=x['account'],create_operation_id=create_operation,create_request_sha256='a'*64,
        scheduler_id=roles['scheduler']['actor'],scheduler_runtime_sha256=runtime_sha,scheduler_config_sha256=scheduler_sha,
        stop_owner_id=roles['stop']['actor'],stop_runtime_sha256='d'*64,stop_config_sha256='e'*64,capture_until=x['capture_until'],
        stop_valid_from=datetime.fromisoformat(original['stop_valid_from']),stop_until=x['until'],original_horizon=x['until'],scheduler_poll_seconds=1,stop_request_seconds=3,safety_allowance_seconds=1,stop_margin_seconds=5)
    relation=CreateOperationStopRelationV1(purpose='meeting-create-operation-stop-relation-v1',mapping_id=uuid4(),provider='recall',tenant_id='tenant1',provider_meeting_id='meeting1',supervision_scope_sha256=digest(scope.model_dump(mode='json')),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=scope.stop_valid_from,expires_at=scope.stop_until,
        **{k:getattr(scope,k) for k in ('workspace_id','meeting_id','provider_account','create_operation_id','create_request_sha256','scheduler_id','scheduler_runtime_sha256','scheduler_config_sha256','stop_owner_id','stop_runtime_sha256','stop_config_sha256','capture_until','stop_valid_from','stop_until','original_horizon')})
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_create_stop_relations_v1(mapping_id,workspace_id,meeting_id,mapping_sha256,mapping_payload) VALUES(%s,%s,%s,%s,%s)',(relation.mapping_id,x['workspace'],x['meeting'],relation.sha256,Jsonb(relation.model_dump(mode='json'))))
    for kind,own in roles.items():
        row=dict(original,admission_id=str(own['admission']),admission_sha256=own['seal'],role_name=own['role'],principal_id=str(own['actor']),leaf_appointment_id=str(own['leaf']),actions=['supervise','status'],
            supervision_scope_sha256=relation.supervision_scope_sha256,stop_relation_id=str(relation.mapping_id),stop_mapping_sha256=relation.sha256)
        with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
        host=own['host'];capture=own['capture_settings'];ch=capture.config_sha256
        config=MeetingSupervisionConfigV1(purpose='meeting-supervision-queue-consumer-v1',capture_config_sha256=ch,process_purpose='meeting-scheduler-process-v1' if kind=='scheduler' else 'meeting-stop-worker-process-v1',scope=scope,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=scope.capture_until if kind=='scheduler' else scope.stop_until)
        cp,ch=pinned(own['dir'],'supervision',config);own['settings']=load_meeting_supervision_settings_v1(capture,cp,ch)
        own['factory']=MeetingSupervisionFactoryV1(own['settings'])
    import site
    env={**os.environ,'PYTHONHOME':sys.base_prefix,'PYTHONPATH':':'.join(str(value) for value in sys.path if value),'ORACLE2_MEETING_SCHEDULER_CONFIG_FILE':str(scheduler_config),'ORACLE2_MEETING_SCHEDULER_CONFIG_SHA256':scheduler_sha,'ORACLE2_MEETING_SCHEDULER_RUNTIME_SHA256':runtime_sha,'ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_FILE':roles['scheduler']['settings'].path,'ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_SHA256':roles['scheduler']['settings'].sha256}
    import pydantic
    (tmp_path/'runtime-identity.json').write_text(json.dumps({'python':sys.version,'parent_executable':sys.executable,'parent_paths':sys.path,'pydantic_version':pydantic.__version__,'pydantic_file':pydantic.__file__,'psycopg_version':psycopg.__version__,'psycopg_file':psycopg.__file__}))
    process=subprocess.Popen([str(executable),str(runtime),str(scheduler_config)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        end=time.monotonic()+5
        while not socket_path.exists() and process.poll() is None and time.monotonic()<end:time.sleep(.01)
        if not socket_path.exists():
            process.terminate();process.wait(timeout=3);raise AssertionError('actual scheduler startup failed: '+process.stderr.read())
        stat=socket_path.stat();proc=Path('/proc')/str(process.pid);record=(proc/'stat').read_text();start=record[record.rfind(')')+2:].split()[19]
        profile=InstalledSupervisorProcessV2(schema_version=2,observation_protocol='meeting-process-currentness-v2',purpose='meeting-scheduler-process-v1',scope=scope,socket_file=str(socket_path),socket_device=stat.st_dev,socket_inode=stat.st_ino,peer_pid=process.pid,peer_uid=os.getuid(),process_start_ticks=start,executable_file=str(executable),executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),command_sha256=hashlib.sha256((proc/'cmdline').read_bytes()).hexdigest(),runtime_file=str(runtime),runtime_sha256=runtime_sha,config_file=str(scheduler_config),config_sha256=scheduler_sha,issuer_actor='independent-installer',reviewer_actor='independent-reviewer',valid_from=runtime_config.valid_from,expires_at=runtime_config.expires_at)
        # Exact actual PID/socket/runtime/config independently pinned BEFORE
        # invitation; no post-create installation or process assertion row.
        pinned(short,'installed-process.json',profile)
        invite(x)
        yield x,roles,scope,relation,process,profile,short
    finally:
        if process.poll() is None:process.terminate()
        process.wait(timeout=4);process.stdout.close();process.stderr.close()
        socket_absent_before_directory_removal=not socket_path.exists()
        (tmp_path/'process-cleanup.json').write_text(json.dumps({'process_returncode':process.returncode,'socket_absent_before_directory_removal':socket_absent_before_directory_removal}))
        private.cleanup();assert not short.exists()
        assert socket_absent_before_directory_removal,'scheduler must remove its own socket before fixture directory cleanup'




def read_actual(profile):
    from oracle_brain.meetings.supervisor_process import observe_supervisor_process_v2
    return observe_supervisor_process_v2(profile,challenge=hashlib.sha256(uuid4().bytes).hexdigest(),deadline=min(datetime.now(timezone.utc)+timedelta(seconds=5),profile.expires_at))


def test_actual_linux_scheduler_loop_observes_own_SQL_and_independent_profile_before_invite(actual_scheduler):
    x,roles,scope,relation,process,profile,short=actual_scheduler
    with pytest.raises(PermissionError,match='two-second connection bound'):roles['scheduler']['factory'].current_queue_v1(caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=2))
    end=time.monotonic()+4;proof=None;errors=[]
    while time.monotonic()<end:
        try:proof=read_actual(profile);break
        except (PermissionError,ConnectionResetError,BrokenPipeError):errors.append(1);time.sleep(.05)
    assert proof is not None and process.poll() is None
    current=roles['scheduler']['factory'].current_queue_v1(caller_deadline=min(deadline(),scope.capture_until))
    assert proof.queue_observation_sha256==current.queue_observation_sha256 and proof.config_sha256==profile.config_sha256
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT stop_intent_id FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()==(None,)
    process.terminate();process.wait(timeout=3)
    with pytest.raises((PermissionError,FileNotFoundError,ProcessLookupError)):read_actual(profile)


def test_actual_scheduler_revocation_removes_health_before_any_effect(actual_scheduler):
    x,roles,scope,relation,process,profile,_short=actual_scheduler
    end=time.monotonic()+4
    while True:
        try:read_actual(profile);break
        except (PermissionError,ConnectionResetError,BrokenPipeError):
            if time.monotonic()>=end:raise
            time.sleep(.05)
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_create_stop_relation_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),relation.mapping_id,'b'*64))
    with pytest.raises((PermissionError,ConnectionResetError)):read_actual(profile)
    assert process.poll() is None
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_delayed_IPC_body_cannot_renew_original_observer_deadline_or_create_effect(actual_scheduler):
    x,roles,scope,relation,process,profile,_short=actual_scheduler
    end=time.monotonic()+4
    while True:
        try:read_actual(profile);break
        except (PermissionError,ConnectionResetError,BrokenPipeError):
            if time.monotonic()>=end:raise
            time.sleep(.05)
    # Same real scheduler/socket, exact schema2 request, independently fixed
    # original caller end. A late final byte cannot earn a fresh window.
    original=datetime.now(timezone.utc)+timedelta(milliseconds=100)
    body=canonical_bytes({'schema_version':2,'purpose':'meeting-process-currentness-v2','challenge':hashlib.sha256(uuid4().bytes).hexdigest(),'scope_sha256':digest(scope.model_dump(mode='json')),'caller_deadline':original.isoformat().replace('+00:00','Z')})
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
        connection.settimeout(1);connection.connect(profile.socket_file)
        connection.sendall(len(body).to_bytes(4,'big')+body[:-1]);time.sleep(.2)
        connection.sendall(body[-1:]);assert connection.recv(1)==b''
    assert process.poll() is None
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT stop_intent_id FROM oracle2.meeting_capture_heads_v1 WHERE workspace_id=%s AND meeting_id=%s',(x['workspace'],x['meeting'])).fetchone()==(None,)
    assert read_actual(profile).queue_observation_sha256
