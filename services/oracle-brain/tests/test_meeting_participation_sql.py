"""Actual owned synthetic SQL/privatebytes proof. Observation facts INVENTED.

No provider/Teams/employee/business acceptance is established by this fixture.
Canonical001..014+frozen020+021 runs once in the exact-owned fresh UUID wrapper.
"""
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from hashlib import sha256
from pathlib import Path
from uuid import UUID,uuid4
import json,os,time

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.meeting_capture_v1 import MeetingCaptureConfigV1,MeetingCaptureFactoryV1,load_meeting_capture_settings_v1
from oracle_brain.hosting.meeting_participation_v1 import MeetingParticipationConfigV1,MeetingParticipationFactoryV1,load_meeting_participation_settings_v1
from oracle_brain.meetings.participation_authority_v1 import ParticipationAuthorityV1,ParticipationSQLBindingV1,CAPABILITIES,ParticipationOutcomeUnknown
from oracle_brain.meetings.participant_epoch import LiveParticipantEpochV1,LiveParticipantLinkV1
from oracle_brain.meetings import participation_runtime_v1
from test_replacement_requester_sql import configured_settings
from test_hosting_boundary import certificates, WORKER


def deadline():return datetime.now(timezone.utc)+timedelta(seconds=20)


@pytest.fixture(autouse=True)
def original_request_fence():
    from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
    with _request_fence_v1(float(time.monotonic()+29)):
        yield


@contextmanager
def admin(x):
    owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],x['admin'])
    with psycopg.connect(x['admin']) as c:
        assert c.pgconn.ssl_in_use
        assert c.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',psycopg.conninfo.conninfo_to_dict(x['admin'])['dbname'])
        yield c


def insert(c,table,value):
    # Test-only exact table names are call-site constants, never HTTP input.
    names=tuple(value)
    c.execute(sql.SQL('INSERT INTO oracle2.{} ({}) VALUES ({})').format(sql.Identifier(table),
        sql.SQL(',').join(map(sql.Identifier,names)),sql.SQL(',').join(sql.Placeholder() for _ in names)),
        tuple(Jsonb(v) if type(v) is dict else v for v in value.values()))


def private(path,raw):
    path.write_bytes(raw);path.chmod(0o600);return sha256(raw).hexdigest()


@pytest.fixture
def participation_sql(tmp_path,request):
    now=datetime.now(timezone.utc)
    options=getattr(request,'param',{})
    capture_seconds=options.get('capture_seconds',25) if type(options) is dict else 25
    assert type(capture_seconds) is int and 10<=capture_seconds<=110
    x=dict(admin=os.environ['ORACLE2_TEST_ADMIN_URL'],workspace=uuid4(),owner=uuid4(),root=uuid4(),meeting=uuid4(),
        account='invented-'+uuid4().hex,bot=uuid4(),runtime='a'*64,registry='b'*64,until=now+timedelta(minutes=2),capture_until=now+timedelta(seconds=capture_seconds))
    common=tmp_path/'private';common.mkdir(mode=0o700);info=common.stat();x['private']=common
    with admin(x) as c:
        insert(c,'appointments',dict(appointment_id=x['root'],workspace_id=x['workspace'],actor_id=x['owner'],scope='root',granted_by=uuid4(),expires_at=x['until']))
    epoch=LiveParticipantEpochV1(purpose='meeting-live-participant-epoch-v1',epoch_id=uuid4(),epoch_revision=1,
        workspace_id=x['workspace'],meeting_id=x['meeting'],provider='recall',provider_account=x['account'],tenant_id='invented-tenant',provider_meeting_id='invented-meeting',bot_id=str(x['bot']),
        provider_participant_ids=('1',),participant_set_sha256=digest({'provider_participant_ids':['1']}),
        links=(LiveParticipantLinkV1(provider_participant_id='1',attribution='workspace_actor',actor_id=x['owner'],employee_uuid_metadata=None,mapping_evidence_sha256='c'*64),),
        issuer_actor=uuid4(),reviewer_actor=uuid4(),capture_until=x['capture_until'],valid_from=now-timedelta(seconds=1),expires_at=x['capture_until'],original_horizon=x['until'])
    x['epoch']=epoch
    with admin(x) as c:insert(c,'meeting_participant_epochs_v1',dict(epoch_id=epoch.epoch_id,workspace_id=x['workspace'],meeting_id=x['meeting'],epoch_revision=1,epoch_sha256=epoch.sha256,epoch_payload=epoch.model_dump(mode='json')))
    for name,channel,actions in [('host','employee-control',['invite','status']),('ingress','provider-ingress',['ingress','status','outbox']),('sender','worker',['process','status','participant_turn','outbox'])]:
        role='part_'+uuid4().hex[:16];actor=uuid4();leaf=uuid4();admission=uuid4();seal=sha256(str(admission).encode()).hexdigest();issuer,reviewer=uuid4(),uuid4()
        with admin(x) as c:
            c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal('invented-participation-only')))
            c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(role)))
            c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(role,x['runtime'],x['registry'],x['until']))
            c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(role,actor,x['workspace'],x['runtime'],x['registry'],x['until']))
            insert(c,'appointments',dict(appointment_id=leaf,workspace_id=x['workspace'],actor_id=actor,scope='meeting-capture',granted_by=x['owner'],parent_id=x['root'],expires_at=x['until']))
            insert(c,'meeting_capture_admissions_v1',dict(admission_id=admission,admission_sha256=seal,workspace_id=x['workspace'],meeting_id=x['meeting'],principal_id=actor,role_name=role,leaf_appointment_id=leaf,
                provider='recall',provider_account=x['account'],tenant_id='invented-tenant',provider_meeting_id='invented-meeting',bot_id=str(x['bot']),verifier_secret_sha256='d'*64,consent_packet_sha256='e'*64,runtime_hash=x['runtime'],registry_hash=x['registry'],actions=actions,issuer_actor=issuer,reviewer_actor=reviewer,
                participant_epoch_id=epoch.epoch_id if name=='sender' else None,participant_epoch_sha256=epoch.sha256 if name=='sender' else None,
                stop_valid_from=now-timedelta(seconds=1),stop_until=x['until'],scheduler_poll_seconds=1,stop_request_seconds=3,safety_allowance_seconds=1,stop_margin_seconds=5,stop_mapping_sha256='f'*64,
                capture_until=x['capture_until'],valid_from=now-timedelta(seconds=1),original_horizon=x['until'],expires_at=x['until']))
        url=psycopg.conninfo.make_conninfo(x['admin'],user=role,password='invented-participation-only',hostaddr='127.0.0.1')
        child=x|dict(login=role,actor=actor,url=url,leaf=leaf,admission=admission,seal=seal,issuer=issuer,reviewer=reviewer)
        folder=tmp_path/name;folder.mkdir(mode=0o700);host=configured_settings(folder,child)
        cfg=host.config.model_copy(update=dict(storage_root=str(common),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid))
        cseal=private(host.config_path,canonical_bytes(cfg.model_dump(mode='json')))
        apt=host.appointment.model_copy(update={'config_sha256':cseal});aseal=private(host.appointment_path,canonical_bytes(apt.model_dump(mode='json')))
        host=load_original_intake_settings_v1(host.config_path,cseal,host.appointment_path,aseal,host.expected_issuer_actor,host.expected_reviewer_actor)
        epoch_fields={}
        if name=='sender':
            ep=folder/'epoch';private(ep,canonical_bytes(epoch.model_dump(mode='json')));epoch_fields=dict(participant_epoch_file=str(ep),participant_epoch_sha256=epoch.sha256)
        cfg=MeetingCaptureConfigV1(purpose='meeting-capture-consumer-v1',host_config_sha256=host.config_sha256,host_appointment_sha256=host.appointment_sha256,
            admission_id=admission,admission_sha256=seal,meeting_id=x['meeting'],consent_packet_sha256='e'*64,capture_until=x['capture_until'],provider='recall',provider_account=x['account'],tenant_id='invented-tenant',provider_meeting_id='invented-meeting',bot_id=str(x['bot']),verifier_secret_sha256='d'*64,channel=channel,issuer_actor=issuer,reviewer_actor=reviewer,valid_from=now-timedelta(seconds=1),expires_at=host.config.expires_at,original_horizon=host.config.original_horizon,**epoch_fields)
        p=folder/'capture';seal_config=private(p,canonical_bytes(cfg.model_dump(mode='json')))
        settings=load_meeting_capture_settings_v1(host,p,seal_config)
        child.update(settings=settings,capture=MeetingCaptureFactoryV1(settings),folder=folder);x[name]=child
    x['host']['capture'].transition_v1(expected_head=0,operation_id=uuid4(),action='invite',payload={'consent_packet_sha256':'e'*64},caller_deadline=deadline())
    first_word,second_word=options.get('words',('Oracle,','<exact>&')) if type(options) is dict else options
    raw=canonical_bytes({'event':'transcript.data','data':{'bot':{'id':str(x['bot'])},'data':{'words':[{'text':first_word,'start_timestamp':{'relative':0},'end_timestamp':None},{'text':second_word,'start_timestamp':{'relative':1},'end_timestamp':None}],'participant':{'id':1,'name':'Untrusted display label'},'language_code':'en'}}})
    receipt=x['ingress']['capture'].retain_ingress_v1(raw=raw,provider_event_id='invented-'+uuid4().hex,bot_id=str(x['bot']),event_kind='transcript.data',verifier_secret_sha256='d'*64,expected_head=1,caller_deadline=deadline())
    x.update(raw=raw,event=receipt.event_id,composer=sha256(Path(participation_runtime_v1.__file__).read_bytes()).hexdigest())
    with admin(x) as c:
        catalog=tuple((signature,c.execute("SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid=to_regprocedure(%s)",(signature,)).fetchone()[0]) for signature in CAPABILITIES)
    for kind,source in [('host',x['host']),('sender',x['sender']),('observer',x['sender'])]:
        admission,leaf=uuid4(),uuid4();seal=sha256(str(admission).encode()).hexdigest();issuer,reviewer=uuid4(),uuid4()
        actions={'host':['enable','disable','status'],'sender':['prepare','claim','receipt','status'],'observer':['observe','status']}[kind]
        with admin(x) as c:
            insert(c,'appointments',dict(appointment_id=leaf,workspace_id=x['workspace'],actor_id=source['actor'],scope='meeting-participation-'+kind,granted_by=x['owner'],parent_id=x['root'],expires_at=x['until']))
            insert(c,'meeting_participation_admissions_v1',dict(admission_id=admission,admission_sha256=seal,workspace_id=x['workspace'],meeting_id=x['meeting'],principal_id=source['actor'],role_name=source['login'],kind=kind,leaf_appointment_id=leaf,
                capture_admission_id=source['admission'],capture_admission_sha256=source['seal'],provider='recall',platform='microsoft_teams',provider_account=x['account'],tenant_id='invented-tenant',provider_meeting_id='invented-meeting',bot_id=x['bot'],runtime_hash=x['runtime'],registry_hash=x['registry'],observation_owner_sha256='1'*64,composer_sha256=x['composer'],actions=actions,issuer_actor=issuer,reviewer_actor=reviewer,valid_from=now-timedelta(seconds=1),expires_at=x['until'],original_horizon=x['until']))
        cfg=MeetingParticipationConfigV1(schema_version=1,purpose='meeting-participation-factory-v1',host_config_sha256=source['settings'].host.config_sha256,host_appointment_sha256=source['settings'].host.appointment_sha256,capture_config_sha256=source['settings'].config_sha256,admission_id=admission,admission_sha256=seal,principal_id=source['actor'],workspace_id=x['workspace'],meeting_id=x['meeting'],kind=kind,runtime_hash=x['runtime'],registry_hash=x['registry'],composer_sha256=x['composer'],observation_owner_sha256='1'*64,capability_hashes=catalog,issuer_actor=issuer,reviewer_actor=reviewer,valid_from=now-timedelta(seconds=1),expires_at=source['settings'].host.config.expires_at,original_horizon=source['settings'].host.config.original_horizon)
        path=source['folder']/('participation-'+kind);seal_config=private(path,canonical_bytes(cfg.model_dump(mode='json')))
        settings=load_meeting_participation_settings_v1(source['settings'],path,seal_config,issuer,reviewer)
        factory=MeetingParticipationFactoryV1(settings,source['capture'])
        x[kind+'-participation']=dict(admission=admission,seal=seal,leaf=leaf,factory=factory,source=source)
    yield x


def invent_observation(x,*,chat=True,complete=True,seconds=15):
    # EXPLICIT INVENTED finite facts. No provider capability/roster producer exists.
    worker=x['sender-participation']['factory'];capture=worker._capture.read_current_participant_turn_v1(x['event'],caller_deadline=deadline()).capture
    now=datetime.now(timezone.utc);until=min(x['capture_until'],now+timedelta(seconds=seconds))
    payload=dict(observation_owner_sha256='1'*64,provider_observation_sha256='2'*64,capture_event_id=str(capture.capture_event_id),capture_sha256=capture.capture_event_sha256,capture_revision=capture.capture_revision,
        platform='microsoft_teams',channel_meeting=False,chat_available=chat,audience_complete=complete,participants=[dict(provider_participant_id='1',actor_id=str(x['owner']))],observed_at=now.isoformat(),valid_until=until.isoformat())
    selected=x['observer-participation']['factory']._authority
    status=selected.status_v1(None,deadline=deadline())
    return selected.observe_audience_v1(expected_revision=status['observation_revision'],observation_id=uuid4(),observation=payload,deadline=deadline())


def enable(x,*,proactive=False):
    f=x['host-participation']['factory'];s=f.status_v1(caller_deadline=deadline())
    return f.control_v1(expected_head=s['head_revision'],operation=uuid4(),enabled=True,proactive_enabled=proactive,caller_deadline=deadline())


def test_actual_current_source_intent_once_claim_wire_custody_and_restart(participation_sql):
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory']
    from oracle_brain.meetings.participation_authority_v1 import participation_operation_policy_sha256_v1
    assert f.operation_policy_sha256==participation_operation_policy_sha256_v1(x['composer'],f.settings.config.capability_hashes)
    prepared=f.prepare_latest_v1(caller_deadline=deadline());intent=UUID(prepared['intent_id'])
    claim=f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    assert claim.body==canonical_bytes({'message':'You asked: Oracle, &lt;exact&gt;&amp;','to':'everyone'}) and claim.bot_id==x['bot']
    assert claim.metadata['state']=='inflight' and claim.metadata['outcome']=='UNKNOWN' and not claim.metadata['executable']
    f.current_claim_v1(intent,UUID(claim.metadata['claim_event_id']),claim.metadata['request_sha256'],caller_deadline=deadline())
    wire=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}'
    operation=uuid4();observed=f.receipt_v1(intent,claim_event_id=UUID(claim.metadata['claim_event_id']),operation=operation,raw_wire=wire,caller_deadline=deadline())
    assert observed['state']=='provider-response-observed' and not observed['remote_stop_proven'] and not observed['visible_message_proven']
    assert list(x['private'].glob('meeting-participation/**/provider-response.wire'))[0].read_bytes()==wire
    fresh=MeetingParticipationFactoryV1(f.settings,x['sender']['capture'])
    assert fresh.status_latest_v1(caller_deadline=deadline())['state']=='provider-response-observed'
    assert fresh.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline()).body is None
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_intents_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(2,)
        assert c.execute('SELECT count(*) FROM oracle2.accepted WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def prepared_claim(x,*,seconds=None):
    invent_observation(x);enable(x);f=x['sender-participation']['factory']
    prepared=f.prepare_latest_v1(caller_deadline=deadline());intent=UUID(prepared['intent_id'])
    claim=f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline() if seconds is None else datetime.now(timezone.utc)+timedelta(seconds=seconds))
    assert claim.body is not None
    return f,intent,claim


def test_actual_unknown_chat_declines_before_privatebytes_and_capture_continues(participation_sql,monkeypatch):
    from oracle_brain.meetings.participation_runtime_v1 import ParticipationDeclined
    x=participation_sql;f=x['sender-participation']['factory'];reads=[]
    with monkeypatch.context() as patch:
        patch.setattr(f._capture,'_read_raw_receipt_bytes_v1',lambda *a,**k:reads.append(a))
        with pytest.raises(ParticipationDeclined):f.prepare_latest_v1(caller_deadline=deadline())
    assert reads==[]
    invent_observation(x,chat=None)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):enable(x)
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_intents_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(2,)
    assert f._capture.read_current_participant_turn_v1(x['event'],caller_deadline=deadline()).text=='Oracle, <exact>&'


def test_actual_selected_host_root_revocation_not_rescued_by_alternate_leaf(participation_sql,monkeypatch):
    from oracle_brain.meetings.participation_runtime_v1 import ParticipationDeclined
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory'];reads=[]
    with admin(x) as c:
        c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['host-participation']['leaf'],))
        insert(c,'appointments',dict(appointment_id=uuid4(),workspace_id=x['workspace'],actor_id=x['host']['actor'],scope='meeting-participation-host',granted_by=x['owner'],parent_id=x['root'],expires_at=x['until']))
    with monkeypatch.context() as patch:
        patch.setattr(f._capture,'_read_raw_receipt_bytes_v1',lambda *a,**k:reads.append(a))
        with pytest.raises(ParticipationDeclined):f.prepare_latest_v1(caller_deadline=deadline())
    assert reads==[]
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_intents_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_actual_observer_revocation_denies_claim_before_bytes(participation_sql,monkeypatch):
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory'];p=f.prepare_latest_v1(caller_deadline=deadline());reads=[]
    with admin(x) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['observer-participation']['leaf'],))
    with monkeypatch.context() as patch:
        patch.setattr(f._capture,'_read_raw_receipt_bytes_v1',lambda *a,**k:reads.append(a))
        with pytest.raises(PermissionError):f.claim_v1(UUID(p['intent_id']),expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    assert reads==[]
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(UUID(p['intent_id']),)).fetchone()==(0,)


def test_actual_unknown_receipt_and_host_toggles_cannot_resend_same_turn(participation_sql):
    x=participation_sql;f,intent,claim=prepared_claim(x)
    unknown=f.receipt_v1(intent,claim_event_id=UUID(claim.metadata['claim_event_id']),operation=uuid4(),raw_wire=b'partial observed bytes',error='network',caller_deadline=deadline())
    assert unknown['state']=='UNKNOWN'
    host=x['host-participation']['factory'];head=host.status_v1(caller_deadline=deadline())
    host.control_v1(expected_head=head['head_revision'],operation=uuid4(),enabled=False,caller_deadline=deadline())
    enable(x)
    repeated=f.prepare_latest_v1(caller_deadline=deadline())
    assert repeated['intent_id']==str(intent) and repeated['state']=='UNKNOWN'
    assert f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline()).body is None
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_intents_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(2,)


def test_actual_forensic_receipt_after_host_disable_never_restores_send(participation_sql):
    x=participation_sql;f,intent,claim=prepared_claim(x);host=x['host-participation']['factory']
    head=host.status_v1(caller_deadline=deadline());host.control_v1(expected_head=head['head_revision'],operation=uuid4(),enabled=False,caller_deadline=deadline())
    with pytest.raises(PermissionError):f.current_claim_v1(intent,UUID(claim.metadata['claim_event_id']),claim.metadata['request_sha256'],caller_deadline=deadline())
    observed=f.receipt_v1(intent,claim_event_id=UUID(claim.metadata['claim_event_id']),operation=uuid4(),raw_wire=b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n',caller_deadline=deadline())
    assert observed['state']=='provider-response-observed' and observed['claim_current'] is False
    assert f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline()).body is None
    assert f._capture.read_current_participant_turn_v1(x['event'],caller_deadline=deadline()).text=='Oracle, <exact>&'


def test_actual_original_claim_deadline_cannot_be_renewed_by_fresh_request(participation_sql):
    x=participation_sql;f,intent,claim=prepared_claim(x,seconds=3)
    time.sleep(max(0,(claim.valid_until-datetime.now(timezone.utc)).total_seconds())+.02)
    with pytest.raises(PermissionError):f.current_claim_v1(intent,UUID(claim.metadata['claim_event_id']),claim.metadata['request_sha256'],caller_deadline=deadline())
    status=f.status_latest_v1(caller_deadline=deadline())
    assert status['state']=='inflight' and status['outcome']=='UNKNOWN' and not status['claim_current']
    receipt=f.receipt_v1(intent,claim_event_id=UUID(claim.metadata['claim_event_id']),operation=uuid4(),raw_wire=b'',error='timeout',caller_deadline=deadline())
    assert receipt['state']=='UNKNOWN' and not receipt['claim_current']
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(2,)


def test_actual_source_grant_withdrawal_blocks_claim_but_not_ingress(participation_sql):
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory'];p=f.prepare_latest_v1(caller_deadline=deadline())
    with admin(x) as c:insert(c,'meeting_capture_revocations_v1',dict(revocation_id=uuid4(),admission_id=x['sender']['admission'],revoked_at=datetime.now(timezone.utc),reason_sha256='3'*64))
    with pytest.raises(PermissionError):f.claim_v1(UUID(p['intent_id']),expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    ingress=x['ingress']['capture'];head=ingress.head_v1(caller_deadline=deadline())
    retained=ingress.retain_ingress_v1(raw=x['raw'],provider_event_id='invented-independent-'+uuid4().hex,bot_id=str(x['bot']),event_kind='transcript.data',verifier_secret_sha256='d'*64,expected_head=head.version,caller_deadline=deadline())
    assert retained.created
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(UUID(p['intent_id']),)).fetchone()==(0,)


def test_actual_wrong_login_tls_and_owner_fail_closed(participation_sql):
    from dataclasses import replace
    x=participation_sql;f=x['sender-participation']['factory'];a=f._authority
    wrong=ParticipationAuthorityV1(psycopg.conninfo.make_conninfo(a._url,user=x['host']['login']),binding=replace(a.binding,session_login=x['host']['login']))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):wrong.status_v1(None,deadline=deadline())
    with pytest.raises(psycopg.OperationalError):
        with psycopg.connect(x['sender']['url'],sslmode='disable',connect_timeout=2):pass
    signature='oracle2.meeting_participation_status_v1(uuid,text,uuid,timestamp with time zone)';new_owner='owner_'+uuid4().hex[:16]
    with admin(x) as c:
        original=c.execute('SELECT proowner,proacl,proconfig,prosrc FROM pg_proc WHERE oid=to_regprocedure(%s)',(signature,)).fetchone()
        c.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(new_owner)))
        c.execute(sql.SQL('ALTER FUNCTION oracle2.meeting_participation_status_v1(uuid,text,uuid,timestamptz) OWNER TO {}').format(sql.Identifier(new_owner)))
    try:
        with pytest.raises(PermissionError):a.status_v1(None,deadline=deadline())
    finally:
        with admin(x) as c:
            c.execute('ALTER FUNCTION oracle2.meeting_participation_status_v1(uuid,text,uuid,timestamptz) OWNER TO oracle2_admin')
            assert c.execute('SELECT proowner,proacl,proconfig,prosrc FROM pg_proc WHERE oid=to_regprocedure(%s)',(signature,)).fetchone()==original


def test_actual_concurrent_claims_release_exactly_one_body(participation_sql):
    from concurrent.futures import ThreadPoolExecutor
    from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory'];p=f.prepare_latest_v1(caller_deadline=deadline());intent=UUID(p['intent_id'])
    end=deadline();original_end=float(time.monotonic()+min(20,(end-datetime.now(timezone.utc)).total_seconds()))
    def run():
        with _request_fence_v1(original_end):return f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=end)
    with ThreadPoolExecutor(max_workers=2) as executor:results=list(executor.map(lambda _:run(),range(2)))
    assert sum(result.body is not None for result in results)==1
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(1,)


def test_actual_committed_claim_then_readback_loss_unknown_no_automatic_retry(participation_sql,monkeypatch):
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory'];p=f.prepare_latest_v1(caller_deadline=deadline());intent=UUID(p['intent_id'])
    real_connect=psycopg.connect;real_execute=psycopg.Connection.execute;state={'claim':False,'losses':0}
    def execute(connection,query,params=None,**kwargs):
        result=real_execute(connection,query,params,**kwargs)
        if str(query).startswith('SELECT oracle2.meeting_participation_claim_v1('):state['claim']=True
        return result
    def connect(url,*args,**kwargs):
        if state['claim'] and psycopg.conninfo.conninfo_to_dict(url).get('user')==x['sender']['login']:
            state['losses']+=1;raise psycopg.OperationalError('invented postcommit independent connection loss')
        return real_connect(url,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Connection,'execute',execute);patch.setattr(psycopg,'connect',connect)
        with pytest.raises(ParticipationOutcomeUnknown):f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    assert state['losses']==1
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(1,)
    assert f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline()).body is None


def test_actual_committed_claim_then_selected_admission_revoked_unknown(participation_sql,monkeypatch):
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory']
    prepared=f.prepare_latest_v1(caller_deadline=deadline());intent=UUID(prepared['intent_id'])
    real_connect=psycopg.connect;real_execute=psycopg.Connection.execute;state={'claim':False,'revoked':False}
    def execute(connection,query,params=None,**kwargs):
        result=real_execute(connection,query,params,**kwargs)
        if str(query).startswith('SELECT oracle2.meeting_participation_claim_v1('):state['claim']=True
        return result
    def connect(url,*args,**kwargs):
        if state['claim'] and not state['revoked'] and psycopg.conninfo.conninfo_to_dict(url).get('user')==x['sender']['login']:
            state['revoked']=True
            with admin(x) as c:
                insert(c,'meeting_participation_revocations_v1',dict(revocation_id=uuid4(),admission_id=x['sender-participation']['admission'],revoked_at=datetime.now(timezone.utc),reason_sha256='3'*64))
        return real_connect(url,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(psycopg.Connection,'execute',execute);patch.setattr(psycopg,'connect',connect)
        with pytest.raises(ParticipationOutcomeUnknown):f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    assert state['revoked']
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(1,)
        assert c.execute('SELECT state FROM oracle2.meeting_participation_delivery_heads_v1 WHERE intent_id=%s',(intent,)).fetchone()==('inflight',)


def test_actual_every_runtime_login_denied_private_helpers_and_tables(participation_sql):
    from oracle_brain.meetings.participation_authority_v1 import _PRIVATE
    x=participation_sql
    for name in ('host','ingress','sender'):
        with psycopg.connect(x[name]['url']) as c:
            assert c.pgconn.ssl_in_use
            for signature in _PRIVATE:
                assert c.execute("SELECT has_function_privilege(SESSION_USER,to_regprocedure(%s),'EXECUTE')",('oracle2.'+signature,)).fetchone()==(False,)
            assert c.execute("SELECT has_table_privilege(SESSION_USER,'oracle2.meeting_participation_intents_v1','SELECT')").fetchone()==(False,)
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with psycopg.connect(x[name]['url']) as c:c.execute('SELECT * FROM oracle2.meeting_participation_intents_v1')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with psycopg.connect(x[name]['url']) as c:c.execute('SELECT oracle2._meeting_participation_admission_v1(%s,%s,%s,%s)',(x['sender-participation']['admission'],x['sender-participation']['seal'],'status',deadline()))


def test_actual_host_cas_concurrent_enable_has_one_committed_event(participation_sql):
    from concurrent.futures import ThreadPoolExecutor
    from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
    x=participation_sql;invent_observation(x);f=x['host-participation']['factory']
    end=deadline();original_end=float(time.monotonic()+19)
    def run():
        with _request_fence_v1(original_end):
            try:return f.control_v1(expected_head=0,operation=uuid4(),enabled=True,caller_deadline=end)
            except (psycopg.errors.SerializationFailure,psycopg.errors.RaiseException,ParticipationOutcomeUnknown) as error:return error
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
    assert sum(isinstance(result,dict) for result in results)==1
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_events_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT version,generation,enabled FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,1,True)


@contextmanager
def actual_host_listener(x,tmp_path,certificates,*,seconds=15,listen_host='127.0.0.1'):
    import shutil,threading,subprocess
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from oracle_brain.hosting.meeting_participation_service_v1 import protected_meeting_participation_server_v1
    f=x['host-participation']['factory'];s=f.settings.capture_settings.host;c=s.config
    tls=tmp_path/'host-listener-tls';tls.mkdir(mode=0o700)
    for name in ('server.pem','server.key','ca.pem'):
        shutil.copyfile(certificates/name,tls/name);(tls/name).chmod(0o600)
    extensions=tls/'server.ext';extensions.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
    subprocess.run(['openssl','x509','-req','-in',str(certificates/'server.csr'),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',str(tls/'server.pem'),'-days','1','-extfile',str(extensions)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    peer=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(Encoding.DER)
    now=datetime.now(timezone.utc)
    body=dict(schema_version=1,purpose='meeting-participation-host-peer-v1',
        intake_config_sha256=s.config_sha256,intake_appointment_sha256=s.appointment_sha256,
        participation_config_sha256=f.settings.config_sha256,capture_config_sha256=f.settings.capture_settings.config_sha256,
        principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,
        client_uri=WORKER,client_certificate_sha256=sha256(peer).hexdigest(),listen_host=listen_host,listen_port=0,server_hostname='localhost',
        server_certificate_file=str(tls/'server.pem'),server_certificate_sha256=sha256((tls/'server.pem').read_bytes()).hexdigest(),
        server_key_file=str(tls/'server.key'),server_key_sha256=sha256((tls/'server.key').read_bytes()).hexdigest(),
        client_ca_file=str(tls/'ca.pem'),client_ca_sha256=sha256((tls/'ca.pem').read_bytes()).hexdigest(),
        issuer_actor=str(s.expected_issuer_actor),reviewer_actor=str(s.expected_reviewer_actor),
        valid_from=(now-timedelta(seconds=1)).isoformat().replace('+00:00','Z'),expires_at=(now+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z'),
        original_horizon=c.original_horizon.isoformat().replace('+00:00','Z'))
    path=tmp_path/'host-peer';seal=private(path,canonical_bytes(body))
    server=protected_meeting_participation_server_v1(f,path,seal)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=False);thread.start()
    try:yield server,path
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1


def host_wire(server,certificates,payload,*,identity='worker',path='/v1/replacement/meetings/participation/control',headers=None):
    import http.client,ssl
    context=ssl.create_default_context(cafile=str(certificates/'ca.pem'))
    if identity:context.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
    connection=http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=3)
    try:
        connection.request('POST',path,body=payload,headers=headers or {'Content-Type':'application/json'})
        response=connection.getresponse();return response.status,response.read(),dict(response.getheaders())
    finally:connection.close()


def test_actual_host_mtls_real_sql_enable_privatebytes_and_closed_denials(participation_sql,tmp_path,certificates):
    x=participation_sql;invent_observation(x)
    with actual_host_listener(x,tmp_path,certificates) as (server,peer):
        status_body=canonical_bytes(dict(schema_version=1,operation='status',caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=5)).isoformat().replace('+00:00','Z')))
        code,raw,headers=host_wire(server,certificates,status_body)
        assert code==200 and headers['Connection']=='close' and headers['Cache-Control']=='no-store'
        value=json.loads(raw);assert raw==canonical_bytes(value)
        assert set(value)=={'meeting_id','head_revision','generation','host_enabled','proactive_enabled','proactive_count','visible_message_proven','remote_stop_proven','executable','valid_until'}
        assert not value['host_enabled'] and not value['visible_message_proven'] and not value['remote_stop_proven'] and not value['executable']
        for bad,kwargs in [(status_body,dict(identity='other')),(status_body,dict(path='/v1/replacement/meetings/worker')),
            (canonical_bytes(dict(json.loads(status_body),chat_available=True)),{}),
            (status_body,dict(headers={'Content-Type':'application/json','Content-Encoding':'identity'}))]:
            assert host_wire(server,certificates,bad,**kwargs)[0] in (404,503)
        control=canonical_bytes(dict(schema_version=1,operation='control',expected_head=0,command_id=str(uuid4()),enabled=True,
            proactive_enabled=False,cooldown_seconds=120,max_proactive=3,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=5)).isoformat().replace('+00:00','Z')))
        code,raw,_=host_wire(server,certificates,control);assert code==200 and json.loads(raw)['host_enabled']
        f=x['sender-participation']['factory'];prepared=f.prepare_latest_v1(caller_deadline=deadline())
        claim=f.claim_v1(UUID(prepared['intent_id']),expected_revision=0,operation=uuid4(),caller_deadline=deadline())
        assert claim.body==canonical_bytes({'message':'You asked: Oracle, &lt;exact&gt;&amp;','to':'everyone'})
        peer.write_bytes(peer.read_bytes()+b' ')
        assert host_wire(server,certificates,status_body)[0]==503
        with admin(x) as c:
            assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_events_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(2,)
            assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(UUID(prepared['intent_id']),)).fetchone()==(1,)


@pytest.mark.parametrize('participation_sql',[('Please','clarify')],indirect=True)
def test_actual_proactive_off_cooldown_and_lifetime_count_survives_toggle(participation_sql):
    from oracle_brain.meetings.participation_runtime_v1 import ParticipationDeclined
    x=participation_sql;invent_observation(x);enable(x);f=x['sender-participation']['factory']
    with pytest.raises(ParticipationDeclined):f.prepare_latest_v1(caller_deadline=deadline())
    enable(x,proactive=True)
    p=f.prepare_latest_v1(caller_deadline=deadline());intent=UUID(p['intent_id'])
    claim=f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    assert claim.body==canonical_bytes({'message':'Could you clarify: Please clarify','to':'everyone'})
    f.receipt_v1(intent,claim_event_id=UUID(claim.metadata['claim_event_id']),operation=uuid4(),raw_wire=b'',error='network',caller_deadline=deadline())
    # An actual new captured turn, not a host-supplied body or identifier.
    raw=json.loads(x['raw']);raw['data']['data']['words'][1]['text']='again'
    receipt=x['ingress']['capture'].retain_ingress_v1(raw=canonical_bytes(raw),provider_event_id='invented-'+uuid4().hex,
        bot_id=str(x['bot']),event_kind='transcript.data',verifier_secret_sha256='d'*64,expected_head=2,caller_deadline=deadline())
    x['event']=receipt.event_id;invent_observation(x);enable(x,proactive=True)
    p2=f.prepare_latest_v1(caller_deadline=deadline());intent2=UUID(p2['intent_id'])
    # Actual first claim consumed cooldown despite its UNKNOWN outcome.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.claim_v1(intent2,expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    with admin(x) as c:
        assert c.execute('SELECT proactive_count,cooldown_seconds,max_proactive FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,120,3)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent2,)).fetchone()==(0,)
    # Explicit invented already-exhausted prior count tests the durable cap.
    # This setup is not three observed provider sends or elapsed time.
    with admin(x) as c:c.execute('UPDATE oracle2.meeting_participation_heads_v1 SET proactive_count=3 WHERE workspace_id=%s',(x['workspace'],))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.claim_v1(intent2,expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent2,)).fetchone()==(0,)
        c.execute('UPDATE oracle2.meeting_participation_heads_v1 SET proactive_count=1 WHERE workspace_id=%s',(x['workspace'],))
    host=x['host-participation']['factory'];current=host.status_v1(caller_deadline=deadline())
    host.control_v1(expected_head=current['head_revision'],operation=uuid4(),enabled=False,caller_deadline=deadline());enable(x,proactive=True)
    with admin(x) as c:assert c.execute('SELECT proactive_count FROM oracle2.meeting_participation_heads_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


def test_actual_late_private_wire_finishes_as_orphan_without_sql_receipt(participation_sql,monkeypatch):
    from oracle_brain.operating_model import artifact_storage
    x=participation_sql;f,intent,claim=prepared_claim(x)
    raw=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}'
    original=artifact_storage._write_private_at;writes=[]
    def finish_late(*args,**kwargs):
        result=original(*args,**kwargs);writes.append(True);time.sleep(3.1);return result
    with monkeypatch.context() as patch:
        patch.setattr(artifact_storage,'_write_private_at',finish_late)
        with pytest.raises(ParticipationOutcomeUnknown):
            f.receipt_v1(intent,claim_event_id=UUID(claim.metadata['claim_event_id']),operation=uuid4(),raw_wire=raw,
                caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=3))
    assert writes==[True]
    assert list(x['private'].glob('meeting-participation/**/provider-response.wire'))[0].read_bytes()==raw
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(1,)
        assert c.execute('SELECT state FROM oracle2.meeting_participation_delivery_heads_v1 WHERE intent_id=%s',(intent,)).fetchone()==('inflight',)


def test_actual_short_observation_clips_claim_and_cannot_renew(participation_sql):
    x=participation_sql;invent_observation(x,seconds=4);enable(x);f=x['sender-participation']['factory']
    p=f.prepare_latest_v1(caller_deadline=deadline());intent=UUID(p['intent_id'])
    claim=f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline())
    assert claim.body is not None
    with admin(x) as c:
        until=c.execute('SELECT valid_until FROM oracle2.meeting_participation_observations_v1 WHERE observation_id=%s',(UUID(claim.metadata['observation_id']),)).fetchone()[0]
    assert claim.valid_until<=until
    time.sleep(max(0,(until-datetime.now(timezone.utc)).total_seconds())+.05)
    assert f.status_v1(intent,caller_deadline=deadline())['claim_current'] is False
    with pytest.raises(PermissionError):f.current_claim_v1(intent,UUID(claim.metadata['claim_event_id']),claim.metadata['request_sha256'],caller_deadline=deadline())
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(1,)


def test_actual_foreign_receipt_and_host_borrowing_denied(participation_sql):
    x=participation_sql;f,intent,claim=prepared_claim(x)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.status_v1(uuid4(),caller_deadline=deadline())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['host-participation']['factory'].status_v1(intent,caller_deadline=deadline())
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(1,)


def test_actual_immutable_receipt_bot_identity_after_host_off_no_send_authority(participation_sql):
    x=participation_sql;f,intent,claim=prepared_claim(x);claim_id=UUID(claim.metadata['claim_event_id'])
    bot,metadata=f.receipt_identity_v1(intent,claim_id,caller_deadline=deadline())
    assert bot==x['bot'] and metadata['claim_current'] is True and 'receipt_bot_id' not in metadata
    host=x['host-participation']['factory'];current=host.status_v1(caller_deadline=deadline())
    host.control_v1(expected_head=current['head_revision'],operation=uuid4(),enabled=False,caller_deadline=deadline())
    bot,metadata=f.receipt_identity_v1(intent,claim_id,caller_deadline=deadline())
    assert bot==x['bot'] and metadata['claim_current'] is False and metadata['executable'] is False and 'receipt_bot_id' not in metadata
    with pytest.raises(PermissionError):f.receipt_identity_v1(intent,uuid4(),caller_deadline=deadline())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.receipt_identity_v1(uuid4(),claim_id,caller_deadline=deadline())
    with pytest.raises(PermissionError):host.receipt_identity_v1(intent,claim_id,caller_deadline=deadline())
    with pytest.raises(PermissionError):f.current_claim_v1(intent,claim_id,claim.metadata['request_sha256'],caller_deadline=deadline())
    assert f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=deadline()).body is None
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(1,)


@pytest.mark.parametrize('participation_sql',[{'capture_seconds':10}],indirect=True)
def test_actual_source_window_expired_own_forensic_receipt_still_no_send(participation_sql):
    x=participation_sql;f,intent,claim=prepared_claim(x);claim_id=UUID(claim.metadata['claim_event_id'])
    time.sleep(max(0,(x['capture_until']-datetime.now(timezone.utc)).total_seconds())+.05)
    end=min(datetime.now(timezone.utc)+timedelta(seconds=10),f.settings.current())
    bot,metadata=f.receipt_identity_v1(intent,claim_id,caller_deadline=end)
    assert bot==x['bot'] and metadata['claim_current'] is False and metadata['executable'] is False
    with pytest.raises(PermissionError):f.current_claim_v1(intent,claim_id,claim.metadata['request_sha256'],caller_deadline=end)
    receipt=f.receipt_v1(intent,claim_event_id=claim_id,operation=uuid4(),raw_wire=b'',error='timeout',caller_deadline=end)
    assert receipt['state']=='UNKNOWN' and receipt['claim_current'] is False
    assert f.claim_v1(intent,expected_revision=0,operation=uuid4(),caller_deadline=end).body is None
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_participation_delivery_events_v1 WHERE intent_id=%s',(intent,)).fetchone()==(2,)
