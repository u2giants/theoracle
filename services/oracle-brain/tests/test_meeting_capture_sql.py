"""Own isolated SQL proof. Canonical migrations run ONCE in the wrapper, not here."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4,uuid5,NAMESPACE_URL
import hashlib,json,os,time
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1
from oracle_brain.hosting.meeting_capture_v1 import MeetingCaptureConfigV1,load_meeting_capture_settings_v1,MeetingCaptureFactoryV1
from test_replacement_requester_sql import configured_settings

@pytest.fixture(autouse=True)
def original_request_fence():
    from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
    with _request_fence_v1(float(time.monotonic()+25)):
        yield

@contextmanager
def admin(x):
    owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],x['admin'])
    with psycopg.connect(x['admin']) as c:
        assert c.pgconn.ssl_in_use
        assert c.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',psycopg.conninfo.conninfo_to_dict(x['admin'])['dbname'])
        yield c
@pytest.fixture
def meeting_sql(tmp_path,request):
    x=dict(admin=os.environ['ORACLE2_TEST_ADMIN_URL'],account='account_'+uuid4().hex,workspace=uuid4(),owner=uuid4(),root=uuid4(),meeting=uuid4(),runtime='a'*64,registry='b'*64,until=datetime.now(timezone.utc)+timedelta(minutes=3))
    with admin(x) as c:c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,expires_at) VALUES(%s,%s,%s,'root',%s,%s)",(x['root'],x['workspace'],x['owner'],uuid4(),x['until']))
    x['verifier_secret']=getattr(request,'param',{}).get('verifier_secret')
    x['verifier_seal']=hashlib.sha256(x['verifier_secret'].encode()).hexdigest() if x['verifier_secret'] else 'c'*64
    x['capture_until']=datetime.now(timezone.utc)+timedelta(seconds=getattr(request,'param',{}).get('capture_seconds',20))
    if getattr(request,'param',{}).get('participant_turn'):
        from oracle_brain.meetings.participant_epoch import LiveParticipantEpochV1,LiveParticipantLinkV1
        from oracle_brain.operating_model.contracts import digest
        epoch=LiveParticipantEpochV1(purpose='meeting-live-participant-epoch-v1',epoch_id=uuid4(),epoch_revision=1,workspace_id=x['workspace'],meeting_id=x['meeting'],provider='recall',provider_account=x['account'],tenant_id='tenant1',provider_meeting_id='meeting1',bot_id='bot1',provider_participant_ids=('1',),participant_set_sha256=digest({'provider_participant_ids':['1']}),links=(LiveParticipantLinkV1(provider_participant_id='1',attribution='workspace_actor',actor_id=x['owner'],employee_uuid_metadata=uuid4(),mapping_evidence_sha256='8'*64),),issuer_actor=uuid4(),reviewer_actor=uuid4(),capture_until=x['capture_until'],valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=x['capture_until'],original_horizon=x['until'])
        x['epoch']=epoch
        with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_participant_epochs_v1 VALUES(%s,%s,%s,%s,%s,%s)',(epoch.epoch_id,x['workspace'],x['meeting'],epoch.epoch_revision,epoch.sha256,Jsonb(epoch.model_dump(mode='json'))))
    common=tmp_path/'shared-private-root';common.mkdir(mode=0o700);info=common.stat()
    for channel in ('employee-control','provider-ingress','worker'):
        role='meeting_'+uuid4().hex[:16];actor=uuid4();leaf=uuid4();admission=uuid4();seal=hashlib.sha256(str(admission).encode()).hexdigest();issuer,reviewer=uuid4(),uuid4()
        actions={'employee-control':['invite','status','cancel','review','create_intent','create_observed','create_unknown'],'provider-ingress':['ingress','status','outbox'],'worker':['process','status','normalized','outbox']}[channel]
        if channel=='worker' and getattr(request,'param',{}).get('participant_turn'):actions=actions+['participant_turn']
        if channel=='worker' and getattr(request,'param',{}).get('supervise'):actions=actions+['supervise','stop_intent','stop_observed','stop_unknown']
        with admin(x) as c:
            c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(role),sql.Literal('invented-meeting-only')))
            c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(role)))
            c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(role,x['runtime'],x['registry'],x['until']))
            c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(role,actor,x['workspace'],x['runtime'],x['registry'],x['until']))
            c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'meeting-capture',%s,%s,%s)",(leaf,x['workspace'],actor,x['owner'],x['root'],x['until']))
            c.execute('''INSERT INTO oracle2.meeting_capture_admissions_v1(admission_id,admission_sha256,workspace_id,meeting_id,principal_id,role_name,leaf_appointment_id,provider,provider_account,tenant_id,provider_meeting_id,bot_id,verifier_secret_sha256,consent_packet_sha256,runtime_hash,registry_hash,actions,issuer_actor,reviewer_actor,participant_epoch_id,participant_epoch_sha256,stop_valid_from,stop_until,scheduler_poll_seconds,stop_request_seconds,safety_allowance_seconds,stop_margin_seconds,stop_mapping_sha256,capture_until,valid_from,original_horizon,expires_at)
            VALUES(%s,%s,%s,%s,%s,%s,%s,'recall',%s,'tenant1','meeting1','bot1',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(admission,seal,x['workspace'],x['meeting'],actor,role,leaf,x['account'],x['verifier_seal'],'d'*64,x['runtime'],x['registry'],actions,issuer,reviewer,x['epoch'].epoch_id if channel=='worker' and 'epoch'in x else None,x['epoch'].sha256 if channel=='worker' and 'epoch'in x else None,datetime.now(timezone.utc)-timedelta(minutes=1),x['until'],getattr(request,'param',{}).get('scheduler_poll_seconds',1),getattr(request,'param',{}).get('stop_request_seconds',3),1,getattr(request,'param',{}).get('stop_margin_seconds',5),'f'*64,x['capture_until'],datetime.now(timezone.utc)-timedelta(seconds=1),x['until'],x['until']))
        url=psycopg.conninfo.make_conninfo(x['admin'],user=role,password='invented-meeting-only')
        child=x|dict(login=role,actor=actor,url=url,leaf=leaf,admission=admission,seal=seal,channel=channel,issuer=issuer,reviewer=reviewer)
        d=tmp_path/channel;d.mkdir(mode=0o700);host=configured_settings(d,child)
        cfg=host.config.model_copy(update=dict(storage_root=str(common),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid))
        craw=canonical_bytes(cfg.model_dump(mode='json'));host.config_path.write_bytes(craw);cseal=hashlib.sha256(craw).hexdigest()
        apt=host.appointment.model_copy(update=dict(config_sha256=cseal));araw=canonical_bytes(apt.model_dump(mode='json'));host.appointment_path.write_bytes(araw)
        host=load_original_intake_settings_v1(host.config_path,cseal,host.appointment_path,hashlib.sha256(araw).hexdigest(),host.expected_issuer_actor,host.expected_reviewer_actor)
        epoch_files={}
        if channel=='worker' and 'epoch'in x:
            epoch_path=d/'participant-epoch';epoch_raw=canonical_bytes(x['epoch'].model_dump(mode='json'));epoch_path.write_bytes(epoch_raw);epoch_path.chmod(0o600);epoch_files=dict(participant_epoch_file=str(epoch_path),participant_epoch_sha256=x['epoch'].sha256)
        config=MeetingCaptureConfigV1(purpose='meeting-capture-consumer-v1',host_config_sha256=host.config_sha256,host_appointment_sha256=host.appointment_sha256,admission_id=admission,admission_sha256=seal,meeting_id=x['meeting'],consent_packet_sha256='d'*64,capture_until=x['capture_until'],provider='recall',provider_account=x['account'],tenant_id='tenant1',provider_meeting_id='meeting1',bot_id='bot1',verifier_secret_sha256=x['verifier_seal'],channel=channel,issuer_actor=issuer,reviewer_actor=reviewer,valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=host.config.expires_at,original_horizon=host.config.original_horizon,**epoch_files)
        path=d/'meeting-config';raw=canonical_bytes(config.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
        settings=load_meeting_capture_settings_v1(host,path,hashlib.sha256(raw).hexdigest());child.update(settings=settings,factory=MeetingCaptureFactoryV1(settings));x[channel]=child
    yield x
    # Immutable operational history retained until the exact owned cluster cleanup.

def deadline():return datetime.now(timezone.utc)+timedelta(seconds=20)
def invite(x):
    f=x['employee-control']['factory'];return f.transition_v1(expected_head=0,operation_id=uuid4(),action='invite',payload={'consent_packet_sha256':'d'*64},caller_deadline=deadline())
DEFAULT_RAW=b'{"event":"transcript.data","data":{"bot":{"id":"bot1"},"data":{"words":[{"text":"Original","start_timestamp":{"relative":0},"end_timestamp":null}],"participant":{"id":1,"name":"Untrusted label"},"language_code":"en"}}}'
def ingest(x,raw=DEFAULT_RAW,event_id='msg_one',head=1,**changes):
    v=dict(raw=raw,provider_event_id=event_id,bot_id='bot1',event_kind='transcript.data',verifier_secret_sha256=x['verifier_seal'],expected_head=head,caller_deadline=deadline());v.update(changes)
    return x['provider-ingress']['factory'].retain_ingress_v1(**v)
def test_actual_invitation_receipt_raw_replay_restart_and_worker_current_read(meeting_sql):
    x=meeting_sql;invite(x);first=ingest(x);again=ingest(x)
    assert first.created and not again.created and first.event_id==again.event_id and again.version==2
    fresh=MeetingCaptureFactoryV1(x['worker']['settings']);raw,receipt=fresh.reopen_raw_v1(first.event_id,caller_deadline=deadline())
    assert raw==DEFAULT_RAW and receipt.event_id==first.event_id
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(2,)
        assert c.execute('SELECT count(*) FROM oracle2.accepted WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert c.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
def test_actual_denial_before_private_write_and_collision_no_extra_bytes(meeting_sql,monkeypatch):
    import oracle_brain.hosting.meeting_capture_v1 as module
    x=meeting_sql;writes=[];original=module._write_private_at
    monkeypatch.setattr(module,'_write_private_at',lambda *a,**k:(writes.append(a),original(*a,**k))[1])
    with pytest.raises(PermissionError):ingest(x)
    assert not writes
    invite(x);first=ingest(x);assert len(writes)==1
    with pytest.raises(ValueError,match='identity conflicts'):ingest(x,raw=DEFAULT_RAW.replace(b'Original',b'Changed'))
    assert len(writes)==1
    for changes in ({'bot_id':'foreign'},{'verifier_secret_sha256':'e'*64}):
        with pytest.raises(PermissionError):ingest(x,event_id='new',head=2,**changes)
    assert len(writes)==1
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_capture_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),x['provider-ingress']['admission'],'f'*64))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):ingest(x,event_id='new',head=2)
    assert len(writes)==1
    # Worker is separately appointed, yet withdrawal of its own permission also refuses.
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_capture_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),x['worker']['admission'],'f'*64))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['worker']['factory'].reopen_raw_v1(first.event_id,caller_deadline=deadline())
def test_actual_separate_role_foreign_admission_immutable_events_and_cas(meeting_sql):
    x=meeting_sql;v=invite(x);s=x['provider-ingress'];employee=x['employee-control']
    with psycopg.connect(s['url']) as c:
        c.execute("SET LOCAL statement_timeout='5s'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.meeting_capture_read_v1(%s,%s,%s,%s)',(employee['admission'],employee['seal'],'status',deadline()))
    with pytest.raises(psycopg.Error):employee['factory'].transition_v1(expected_head=0,operation_id=uuid4(),action='cancel',payload={},caller_deadline=deadline())
    with admin(x) as c:
        with pytest.raises(psycopg.Error):c.execute("UPDATE oracle2.meeting_capture_events_v1 SET payload='{}' WHERE event_id=%s",(v.event_id,))
    f=employee['factory'];intent=uuid4()
    # A caller's invitation or local claim cannot stand in for an actual
    # independently observed active scheduler/STOP-owner installation.
    with pytest.raises(psycopg.Error):f.transition_v1(expected_head=1,operation_id=intent,action='create_intent',payload={'request_sha256':'e'*64},caller_deadline=deadline())
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.transition_v1(expected_head=1,operation_id=intent,action='create_intent',payload={'request_sha256':'e'*64,'supervisor_event_id':str(uuid4()),'supervisor_event_sha256':'f'*64,'supervisor_witness_sha256':'9'*64},caller_deadline=deadline())
    assert f.head_v1(caller_deadline=deadline()).state=='invited'

@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':7}],indirect=True)
def test_actual_immutable_capture_end_refuses_new_ingress_but_predeclared_processing_remains(meeting_sql,monkeypatch):
    import oracle_brain.hosting.meeting_capture_v1 as module
    x=meeting_sql;invite(x);first=ingest(x);writes=[];original=module._write_private_at
    monkeypatch.setattr(module,'_write_private_at',lambda *a,**k:(writes.append(a),original(*a,**k))[1])
    time.sleep(max(0,(x['capture_until']-datetime.now(timezone.utc)).total_seconds())+.03)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):ingest(x,event_id='after_end',head=2)
    assert writes==[]
    # Processing was independently installed BEFORE capture, with its own
    # original finite horizon. It does not reopen capture or authorize viewing.
    raw,receipt=x['worker']['factory'].reopen_raw_v1(first.event_id,caller_deadline=deadline())
    assert raw==DEFAULT_RAW and receipt.capture_until==x['capture_until']
    # A late independently inserted admission with a later end cannot renew
    # the immutable capture head, even for the same role and rooted leaf.
    selected=uuid4();seal='9'*64
    with admin(x) as c:
        row=c.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(x['provider-ingress']['admission'],)).fetchone()[0]
        row.update(admission_id=str(selected),admission_sha256=seal,capture_until=(x['capture_until']+timedelta(seconds=10)).isoformat())
        c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
    with psycopg.connect(x['provider-ingress']['url']) as c:
        c.execute("SET LOCAL statement_timeout='5s'")
        with pytest.raises(psycopg.errors.InsufficientPrivilege,match='capture end cannot change'):
            c.execute('SELECT oracle2.meeting_capture_read_v1(%s,%s,%s,%s)',(selected,seal,'ingress',deadline()))

from test_hosting_boundary import certificates,WORKER
@pytest.mark.parametrize('meeting_sql',[{'capture_seconds':25,'verifier_secret':'whsec_'+__import__('base64').b64encode(bytes([7])*32).decode()}],indirect=True)
def test_actual_python_mtls_sql_and_shared_web_route_ingress_conformance(meeting_sql,tmp_path,certificates):
    """Actual SQL/TLS/production web source; auth imports explicitly invented."""
    import subprocess,threading,shutil
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    from oracle_brain.hosting.meeting_capture_service_v1 import (MeetingControlPeerProfileV1,MeetingIngressPeerProfileV1,protected_meeting_control_server_v1,protected_meeting_ingress_server_v1)
    x=meeting_sql;servers=[];threads=[];meta=dict(scratch=str(tmp_path),meeting_id=str(x['meeting']),provider_account=x['account'],operation_id=str(uuid4()))
    secret=tmp_path/'verifier.secret';secret.write_text(x['verifier_secret']);secret.chmod(0o600);meta['verifier_secret_file']=str(secret)
    try:
        for name,channel,client,profile_type,constructor in [('control','employee-control','worker',MeetingControlPeerProfileV1,protected_meeting_control_server_v1),('ingress','provider-ingress','other',MeetingIngressPeerProfileV1,protected_meeting_ingress_server_v1)]:
            settings=x[channel]['settings'];c=settings.host.config;d=tmp_path/('tls-'+name);d.mkdir(mode=0o700)
            for f in ('server.pem','server.key','ca.pem'):shutil.copyfile(certificates/f,d/f);(d/f).chmod(0o600)
            ext=d/'server.ext';ext.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
            subprocess.run(['openssl','x509','-req','-in',str(certificates/'server.csr'),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',str(d/'server.pem'),'-days','1','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            leaf=x509.load_pem_x509_certificate((certificates/(client+'.pem')).read_bytes());client_uri=leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.UniformResourceIdentifier)[0]
            now=datetime.now(timezone.utc)
            value=dict(schema_version=1,purpose='replacement-meeting-'+name+'-peer-v1',intake_config_sha256=settings.host.config_sha256,intake_appointment_sha256=settings.host.appointment_sha256,meeting_config_sha256=settings.config_sha256,meeting_id=str(x['meeting']),principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,client_uri=client_uri,client_certificate_sha256=hashlib.sha256(leaf.public_bytes(Encoding.DER)).hexdigest(),listen_host='127.0.0.1',listen_port=0,server_hostname='localhost.localdomain',server_certificate_file=str(d/'server.pem'),server_certificate_sha256=hashlib.sha256((d/'server.pem').read_bytes()).hexdigest(),server_key_file=str(d/'server.key'),server_key_sha256=hashlib.sha256((d/'server.key').read_bytes()).hexdigest(),client_ca_file=str(d/'ca.pem'),client_ca_sha256=hashlib.sha256((d/'ca.pem').read_bytes()).hexdigest(),issuer_actor=str(settings.host.expected_issuer_actor),reviewer_actor=str(settings.host.expected_reviewer_actor),valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=(now+timedelta(seconds=20)).isoformat(),original_horizon=c.original_horizon.isoformat())
            if name=='ingress':value.update(provider_account=x['account'],verifier_secret_sha256=x['verifier_seal'])
            profile=profile_type.model_validate_json(json.dumps(value));raw=canonical_bytes(profile.model_dump(mode='json'));path=d/'peer-profile';path.write_bytes(raw);path.chmod(0o600);seal=hashlib.sha256(raw).hexdigest()
            server=constructor(settings,path,seal);servers.append(server);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start();threads.append(thread)
            meta[name]=value|dict(profile_sha256=seal,backend_origin='https://localhost.localdomain:'+str(server.server_port),client_certificate_file=str(certificates/(client+'.pem')),client_key_file=str(certificates/(client+'.key')))
            if name=='control':meta.update(project_url=c.auth_issuer.removesuffix('/auth/v1'),auth_user_id=str(c.auth_user_id),employee_id=str(c.employee_id))
        path=tmp_path/'meeting-peer-meta.json';path.write_text(json.dumps(meta));path.chmod(0o600);repo=Path(__file__).resolve().parents[3]
        result=subprocess.run(['pnpm','--filter','@oracle/web','exec','node','--dns-result-order=ipv4first','--import','tsx','tests/oracle2/meeting-peer-proof.ts',str(path)],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=20)
        (tmp_path/'meeting-peer-process.txt').write_text(result.stdout);assert result.returncode==0,result.stdout[-5000:]
        proof=json.loads((tmp_path/'meeting-conformance.json').read_text());assert proof['retained']==dict(status=202,opaque_acknowledgement=True)
        head=x['worker']['factory'].head_v1(caller_deadline=deadline(),processing=True);assert len(head.pending_ingress)==1;event=head.pending_ingress[0]
        raw,receipt=x['worker']['factory'].reopen_raw_v1(event,caller_deadline=deadline());assert hashlib.sha256(raw).hexdigest()==proof['raw_sha256']
        with admin(x) as conn:
            assert conn.execute('SELECT count(*) FROM oracle2.meeting_capture_events_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(2,)
            assert conn.execute('SELECT count(*) FROM oracle2.accepted WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
    finally:
        for server in servers:server.shutdown();server.server_close()
        for thread in threads:thread.join(2);assert not thread.is_alive()
        assert all(not server._active for server in servers)

@pytest.mark.parametrize('meeting_sql',[{'participant_turn':True}],indirect=True)
def test_actual_current_participant_consumer_requires_fresh_capture_exact_epoch_and_no_employee_or_shared_grant(meeting_sql,monkeypatch):
    import oracle_brain.hosting.meeting_capture_v1 as module
    x=meeting_sql;invite(x);first=ingest(x);current=x['worker']['factory']
    turn=current.read_current_participant_turn_v1(first.event_id,caller_deadline=deadline())
    assert turn.text=='Original' and turn.attribution=='workspace_actor' and turn.actor_id==x['owner'] and turn.employee_identity_verified is False
    assert 'employee_id' not in turn.model_dump() and turn.capture.capture_event_id==first.event_id and turn.reported_only is True and turn.qualification is False and turn.shared_source_permission is False
    assert turn.participant_epoch_id==x['epoch'].epoch_id and turn.participant_epoch_sha256==x['epoch'].sha256
    reads=[];original=module._read_private_at;monkeypatch.setattr(module,'_read_private_at',lambda *a,**k:(reads.append(a),original(*a,**k))[1])
    changed=ingest(x,event_id='newer-current',head=2)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):current.read_current_participant_turn_v1(first.event_id,caller_deadline=deadline())
    assert reads==[]
    # A finite epoch supports distinct current raw events, without installing
    # a new identity mapping for every word. Raw SHA/current event stay exact.
    assert current.read_current_participant_turn_v1(changed.event_id,caller_deadline=deadline()).capture.capture_event_id==changed.event_id
    reads.clear();Path(current.settings.config.participant_epoch_file).write_bytes(b'changed epoch')
    with pytest.raises((PermissionError,ValueError)):current.read_current_participant_turn_v1(changed.event_id,caller_deadline=deadline())
    assert reads==[]

@pytest.mark.parametrize('meeting_sql',[{'participant_turn':True}],indirect=True)
def test_actual_superseded_epoch_or_contradictory_hosting_principal_denies_before_bytes(meeting_sql,monkeypatch):
    import oracle_brain.hosting.meeting_capture_v1 as module
    x=meeting_sql;invite(x);first=ingest(x);reads=[]
    monkeypatch.setattr(module,'_read_private_at',lambda *a,**k:reads.append(a))
    e=x['epoch'];new=e.model_copy(update=dict(epoch_id=uuid4(),epoch_revision=2))
    with admin(x) as c:c.execute('INSERT INTO oracle2.meeting_participant_epochs_v1 VALUES(%s,%s,%s,%s,%s,%s)',(new.epoch_id,x['workspace'],x['meeting'],new.epoch_revision,new.sha256,Jsonb(new.model_dump(mode='json'))))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):x['worker']['factory'].read_current_participant_turn_v1(first.event_id,caller_deadline=deadline())
    assert reads==[]

@pytest.mark.parametrize('meeting_sql',[{'participant_turn':True}],indirect=True)
def test_actual_existing_expired_workspace_actor_principal_binding_is_not_ignored(meeting_sql,monkeypatch):
    import oracle_brain.hosting.meeting_capture_v1 as module
    x=meeting_sql;invite(x);first=ingest(x);reads=[]
    monkeypatch.setattr(module,'_read_private_at',lambda *a,**k:reads.append(a))
    role='participant_'+uuid4().hex[:16]
    with admin(x) as c:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(role)))
        c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(role,x['runtime'],x['registry'],x['until']))
        c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(role,x['owner'],x['workspace'],x['runtime'],x['registry'],datetime.now(timezone.utc)-timedelta(seconds=1)))
    with pytest.raises(psycopg.errors.InsufficientPrivilege,match='contradictory current participant'):x['worker']['factory'].read_current_participant_turn_v1(first.event_id,caller_deadline=deadline())
    assert reads==[]


def test_actual_invitation_refuses_uninstalled_or_insufficient_stop_margin(meeting_sql):
    x=meeting_sql;s=x['employee-control']
    for changes in ({'stop_margin_seconds':4},{'stop_until':None},{'stop_mapping_sha256':None},{'stop_margin_seconds':120}):
        selected=uuid4();seal=hashlib.sha256(str(selected).encode()).hexdigest()
        with admin(x) as c:
            row=c.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(s['admission'],)).fetchone()[0]
            row.update(admission_id=str(selected),admission_sha256=seal,**changes)
            c.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
        with psycopg.connect(s['url']) as c:
            c.execute("SET LOCAL statement_timeout='5s'")
            with pytest.raises(psycopg.errors.InsufficientPrivilege,match='STOP-only'):
                c.execute('SELECT oracle2.meeting_capture_transition_v1(%s,%s,0,%s,%s,%s,%s)',(selected,seal,uuid4(),'invite',Jsonb({'consent_packet_sha256':'d'*64}),deadline()))
    assert s['factory'].head_v1(caller_deadline=deadline()).state=='not_invited'

@pytest.mark.parametrize('meeting_sql',[{'supervise':True}],indirect=True)
def test_actual_due_stop_queue_is_installed_and_current_without_claiming_remote_stop(meeting_sql):
    x=meeting_sql;invite(x);f=x['worker']['factory'];q=f.due_stop_v1(caller_deadline=deadline())
    assert q.meeting_id==x['meeting'] and q.stop_until==x['until'] and q.capture_until<q.stop_until
    assert q.due_at==q.capture_until-timedelta(seconds=5) and q.stop_margin_seconds==q.scheduler_poll_seconds+q.stop_request_seconds+q.safety_allowance_seconds
    assert not q.due and q.stop_state=='not_attempted' and q.create_intent_id is None and q.created_bot is None
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        f.transition_v1(expected_head=1,operation_id=uuid4(),action='stop_intent',payload={'create_intent_id':str(uuid4()),'bot_id':str(uuid4()),'create_receipt_sha256':'a'*64,'stop_mapping_sha256':'f'*64,'metadata_sha256':'b'*64},caller_deadline=deadline())
    assert f.due_stop_v1(caller_deadline=deadline()).stop_state=='not_attempted'

def test_actual_final_workspace_mapping_current_before_after_raw_and_revocation(meeting_sql,tmp_path,monkeypatch):
    """Independent invented installer rows; actual SQL and private byte consumer."""
    from oracle_brain.meetings.final_mapping import FinalWorkspaceSpeakerMappingV1,FinalWorkspaceSpeakerLinkV1
    from oracle_brain.meetings.capture_contracts import InstalledFinalArtifactV1
    from oracle_brain.operating_model.artifact_storage import _write_private_at
    from oracle_brain.hosting.meeting_capture_v1 import MeetingCaptureFactoryV1
    import oracle_brain.hosting.meeting_capture_v1 as module
    x=meeting_sql;invite(x);s=x['worker'];old=s['settings'];h=old.host.config;c=old.config;now=datetime.now(timezone.utc)
    raw=b'[{"participant":{"id":1,"name":"Untrusted CEO"},"language_code":"en","words":[{"text":"Exact original","start_timestamp":{"relative":0},"end_timestamp":null}]}]'
    rawsha=hashlib.sha256(raw).hexdigest()
    mapping=FinalWorkspaceSpeakerMappingV1(purpose='meeting-final-workspace-mapping-v1',mapping_id=uuid4(),mapping_revision=1,workspace_id=x['workspace'],meeting_id=x['meeting'],provider='recall',provider_account=x['account'],tenant_id='tenant1',provider_meeting_id='meeting1',raw_sha256=rawsha,language='en',links=(FinalWorkspaceSpeakerLinkV1(provider_speaker_id='1',attribution='workspace_actor',actor_id=x['owner'],mapping_evidence_sha256='a'*64),),issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=min(x['until'],c.original_horizon),original_horizon=min(x['until'],c.original_horizon))
    selection=InstalledFinalArtifactV1(purpose='meeting-final-artifact-selection-v1',workspace_id=x['workspace'],meeting_id=x['meeting'],provider='recall',provider_account=x['account'],tenant_id='tenant1',provider_meeting_id='meeting1',bot_id='bot1',recording_id='recording1',transcript_id='transcript1',provider_revision='r1',provider_finality_receipt_sha256='9'*64,original_sha256=rawsha,byte_count=len(raw),media_type='application/json',download_url='https://cdn.example.invalid/final.json',ca_file=h.database_ca.path,ca_sha256=h.database_ca.sha256,server_der_sha256='8'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),valid_from=now-timedelta(seconds=1),expires_at=min(x['until'],c.original_horizon),original_horizon=min(x['until'],c.original_horizon))
    files={}
    for name,record in [('mapping',mapping),('selection',selection)]:
        data=canonical_bytes(record.model_dump(mode='json'));path=tmp_path/(name+'.json');path.write_bytes(data);path.chmod(0o600);files[name]=(str(path),hashlib.sha256(data).hexdigest())
    admission=uuid4();seal=hashlib.sha256(str(admission).encode()).hexdigest()
    with admin(x) as conn:
        conn.execute('INSERT INTO oracle2.meeting_final_mappings_v1 VALUES(%s,%s,%s,%s,%s,%s,%s)',(mapping.mapping_id,x['workspace'],x['meeting'],1,rawsha,mapping.sha256,Jsonb(mapping.model_dump(mode='json'))))
        row=conn.execute('SELECT to_jsonb(a) FROM oracle2.meeting_capture_admissions_v1 a WHERE admission_id=%s',(s['admission'],)).fetchone()[0]
        row.update(admission_id=str(admission),admission_sha256=seal,final_mapping_id=str(mapping.mapping_id),final_mapping_sha256=mapping.sha256,final_artifact_sha256=files['selection'][1],actions=row['actions']+['final_artifact'])
        conn.execute('INSERT INTO oracle2.meeting_capture_admissions_v1 SELECT (jsonb_populate_record(NULL::oracle2.meeting_capture_admissions_v1,%s)).*',(Jsonb(row),))
    cfg=c.model_copy(update=dict(admission_id=admission,admission_sha256=seal,final_mapping_id=mapping.mapping_id,speaker_mapping_file=files['mapping'][0],speaker_mapping_sha256=files['mapping'][1],final_artifact_file=files['selection'][0],final_artifact_sha256=files['selection'][1]))
    data=canonical_bytes(cfg.model_dump(mode='json'));path=tmp_path/'final-consumer.json';path.write_bytes(data);path.chmod(0o600)
    settings=load_meeting_capture_settings_v1(old.host,path,hashlib.sha256(data).hexdigest());f=MeetingCaptureFactoryV1(settings)
    parts=['meeting-raw',str(x['workspace']),str(x['meeting']),rawsha+'.bin'];_write_private_at(Path(h.storage_root),parts,raw,expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
    event=uuid4();f.transition_v1(expected_head=1,operation_id=event,action='final_artifact',payload=dict(selection_sha256=files['selection'][1],provider_event_id='final-fixture',raw_sha256=rawsha,byte_count=len(raw),raw_object_key='/'.join(parts),event_kind='recall.final'),caller_deadline=deadline())
    text,derivation=f.prepare_reported_text_v1(event,caller_deadline=deadline())
    assert text==b'Exact original' and derivation.reported_only is True and derivation.qualification is False
    reads=[];original=module._read_private_at;monkeypatch.setattr(module,'_read_private_at',lambda *a,**k:(reads.append(a),original(*a,**k))[1])
    with admin(x) as conn:conn.execute('INSERT INTO oracle2.meeting_final_mapping_revocations_v1 VALUES(%s,%s,clock_timestamp(),%s)',(uuid4(),mapping.mapping_id,'f'*64))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):f.prepare_reported_text_v1(event,caller_deadline=deadline())
    assert reads==[]
    with admin(x) as conn:
        assert conn.execute('SELECT count(*) FROM oracle2.accepted WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert conn.execute('SELECT count(*) FROM oracle2.source_reading_qualifications WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
