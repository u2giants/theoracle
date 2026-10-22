"""Actual mTLS→fixed confirmation factory→owned UUID TLS SQL durable event.

The retained ready_model fixture host-prepares a legacy artifact and paid-ACK
CONTROL. This is NOT native generation, graph operational or browser proof.
Only fixture administration creates the existing admissions/appointments.
"""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver
from oracle_brain.hosting.replacement_confirmation_v1 import ReplacementConfirmationFactoryV1, ConfirmationConflictV1
from test_replacement_source_intake_sql import requester,call
from test_original_population_sql import raw_reader
from test_replacement_qualification_sql import qualified_pair,grant_requester,request_for,ready_model
from test_source_processing_qualification import processing
from test_processing_projection_leases import delivery_reader
from test_hosting_boundary import certificates
from test_replacement_confirmation_settings_v1 import intake_target,configured_confirmation
from test_replacement_confirmation_service_v1 import running,send,wire,FIELDS

pytestmark=pytest.mark.parametrize('raw_reader',['native-utf8'],indirect=True)


@pytest.fixture
def admin_url(admin_url):
    owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],admin_url)
    assert psycopg.conninfo.conninfo_to_dict(admin_url)['dbname'].startswith('oracle_operating_model_test_')
    return admin_url


@contextmanager
def owned_admin(x):
    owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],x['admin'])
    with psycopg.connect(x['admin']) as conn:
        assert conn.pgconn.ssl_in_use
        name=psycopg.conninfo.conninfo_to_dict(x['admin'])['dbname']
        assert conn.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',name)
        yield conn


@pytest.fixture
def actual_confirmation(qualified_pair,processing,tmp_path,certificates):
    x=qualified_pair;r=grant_requester(x)
    reserved=call(r,'reserve_replacement_journey',Jsonb(request_for(x)),uuid4());run=reserved['run_id']
    call(r,'compare_and_advance_replacement_journey',run,1,Jsonb({'target_state':'processing'}),uuid4())
    reading,review=x['commit_pair']();call(x['review_x'],'finalize_original_reading_qualification_v1',reading,review,x['reading_text'])
    captured=[]
    def prepare_processing():
        f=processing();captured.append(f);return f
    # Explicit retained host-prepared generated-artifact/ACK control, not an
    # intake→native provider→qualified generation claim or runtime admission.
    binding=ready_model(x,r,prepare_processing,tmp_path,run)
    component=captured[0]
    component=component|dict(workspace=x['workspace'],source=x['ref'].source_id,actor=r['actor'],root=x['root'],
        reading=x['reading_text'],expiry=x['until'],original_sha256=x['ref'].original_sha256,
        binding=replace(component['binding'],principal=r['actor']))
    with owned_admin(x) as conn:
        owner=conn.execute("SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='oracle2'").fetchone()[0]
    folder=tmp_path/'confirmation-intake';folder.mkdir(mode=0o700)
    intake=intake_target(folder,url=r['url'],ca=Path(os.environ['ORACLE2_TEST_TLS_ROOT']).read_bytes(),updates=dict(
        principal_id=r['actor'],workspace_id=x['workspace'],expected_session_role=r['login'],expected_owner_role=owner,
        runtime_hash=r['runtime'],registry_hash=r['registry']))
    peer=tmp_path/'confirmation-peer';peer.mkdir(mode=0o700)
    f=configured_confirmation(peer,certificates,intake=intake)
    f.x=x;f.r=r;f.run=UUID(run);f.revision=2;f.model=UUID(binding['model_id']);f.ack=UUID(binding['ack_event_id'])
    f.binding=binding;f.component=component;f.processing=processing;f.path=tmp_path
    return f


def actual_wire(f,**changes):
    return wire(f,version=f.binding['version'],content_hash=f.binding['content_hash'],workflow_id=f.binding['workflow_id'],**changes)


def state(f):
    with owned_admin(f.x) as conn:
        row=conn.execute('SELECT journey_revision,state,answer_hold,current_model_id,current_model_version,current_model_content_hash FROM oracle2.processing_journey_runs_v1 WHERE run_id=%s',(f.run,)).fetchone()
        events=conn.execute("SELECT payload,idempotency_key FROM oracle2.replacement_journey_events WHERE run_id=%s AND action='confirm' AND payload->>'target_state'='delivered'",(f.run,)).fetchall()
    return row,events


def badge_reader(f):
    # Independent test-only executor appointment, never borrowed by requester.
    source=f.component
    reader,grant=delivery_reader(f.x['admin'],f.processing,source)
    with owned_admin(f.x) as conn:
        conn.execute('UPDATE oracle2.hosting_role_source_admissions SET principal_id=%s WHERE role_name=%s',(f.r['actor'],reader.binding.expected_session_role))
        conn.execute('UPDATE oracle2.appointments SET actor_id=%s WHERE appointment_id=%s',(f.r['actor'],grant))
    reader=ProcessingArtifactResolver(reader.url,binding=replace(reader.binding,principal=f.r['actor']))
    seal=reader.projection_delivery_seal(f.x['workspace'],f.model,1)
    with owned_admin(f.x) as conn:
        population=conn.execute('SELECT population_sha256 FROM oracle2.processing_journey_runs_v1 WHERE run_id=%s',(f.run,)).fetchone()[0]
        conn.execute('INSERT INTO oracle2.hosting_replacement_executor_runs_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s,%s,%s,%s)',
            (reader.binding.expected_session_role,f.run,f.x['workspace'],f.r['actor'],reader.binding.runtime_hash,
             reader.binding.source_registry_hash,population,f.model,f.binding['content_hash'],f.ack,
             seal.projection_digest,digest([]),f.x['until']))
    return reader


def test_actual_mtls_durable_exact_confirmation_and_independent_badge_refresh(actual_confirmation,certificates):
    f=actual_confirmation;request=actual_wire(f)
    with running(f) as server:
        status,raw,_=send(server,certificates,request);assert status==200
        value=json.loads(raw);assert set(value)==FIELDS and value['controlState']=='delivered'
        assert value['resultAvailable'] is False and value['remoteStopProven'] is False
        assert send(server,certificates,request)[:2]==(409,b'')
    row,events=state(f);assert row[:3]==(3,'delivered',False) and len(events)==1
    assert all(events[0][0][key]==value for key,value in f.binding.items())
    assert row[3:]==(f.model,1,f.binding['content_hash'])
    # Listener restart does not recreate or forget authoritative events.
    with running(f) as server:assert send(server,certificates,request)[:2]==(409,b'')
    assert len(state(f)[1])==1
    reader=badge_reader(f)
    current=reader.replacement_executor_target_v1(f.run)
    assert current.current_confirmation is not None and current.current_confirmation.eligible
    assert (current.current_confirmation.workflow_id,current.current_confirmation.version,current.current_confirmation.content_hash)==(f.binding['workflow_id'],1,f.binding['content_hash'])
    with owned_admin(f.x) as conn:
        conn.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope='process-confirm'",(f.x['workspace'],f.r['actor']))
    assert reader.replacement_executor_target_v1(f.run).current_confirmation is None
    assert len(state(f)[1])==1


@pytest.mark.parametrize('fault',['no_confirm','confirm_expired','root_revoked','source_revoked','source_revision','withdrawn',
    'model','version','hash','ack','workflow','unacked','qualification','extra_role','owner','wrong_login','wrong_tls','missing_run','stale_cas'])
def test_actual_sql_current_permission_custody_and_exact_selection_denials(actual_confirmation,certificates,fault):
    f=actual_confirmation;x=f.x;changes={};restore=None
    with owned_admin(x) as conn:
        if fault=='no_confirm':conn.execute("DELETE FROM oracle2.appointments WHERE workspace_id=%s AND actor_id=%s AND scope='process-confirm'",(x['workspace'],f.r['actor']))
        elif fault=='confirm_expired':conn.execute("UPDATE oracle2.appointments SET expires_at=clock_timestamp()-interval '1 second' WHERE workspace_id=%s AND actor_id=%s AND scope='process-confirm'",(x['workspace'],f.r['actor']))
        elif fault=='root_revoked':conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['root'],))
        elif fault=='source_revoked':conn.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope=%s',(x['workspace'],f.r['actor'],'source-read:'+str(x['ref'].source_id)))
        elif fault=='source_revision':conn.execute('UPDATE oracle2.sources SET revision=2 WHERE workspace_id=%s AND source_id=%s',(x['workspace'],x['ref'].source_id))
        elif fault=='withdrawn':
            conn.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',
                (uuid4(),x['workspace'],x['ref'].source_id,x['ref'].original_sha256,f.r['actor'],f.r['login'],f.r['runtime'],'Invented withdrawal',uuid4(),'0'*64))
        elif fault=='unacked':conn.execute('UPDATE oracle2.outbox SET delivered_at=NULL WHERE event_id=%s',(f.ack,))
        elif fault=='qualification':conn.execute('DELETE FROM oracle2.source_reading_qualifications WHERE workspace_id=%s AND source_id=%s',(x['workspace'],x['ref'].source_id))
        elif fault=='extra_role':conn.execute(sql.SQL('GRANT oracle2_source_original_reader TO {}').format(sql.Identifier(f.r['login'])))
        elif fault=='owner':
            foreign='confirm_owner_'+uuid4().hex[:10];restore=f.intake.config.expected_owner_role
            conn.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(foreign)))
            conn.execute(sql.SQL('ALTER FUNCTION oracle2.compare_and_advance_replacement_journey(uuid,integer,jsonb,uuid) OWNER TO {}').format(sql.Identifier(foreign)))
    if fault=='missing_run':changes['run_id']=str(uuid4())
    elif fault=='stale_cas':changes['expected_journey_revision']=1
    elif fault=='model':changes['model_id']=str(uuid4())
    elif fault=='version':changes['version']=2
    elif fault=='hash':changes['content_hash']='0'*64
    elif fault=='ack':changes['ack_event_id']=str(uuid4())
    elif fault=='workflow':changes['workflow_id']='not-in-sealed-model'
    if fault in {'wrong_login','wrong_tls'}:
        directory=f.path/'wrong-target';directory.mkdir(mode=0o700)
        url=x['url'] if fault=='wrong_login' else psycopg.conninfo.make_conninfo(f.r['url'],sslmode='require')
        login=x['login'] if fault=='wrong_login' else f.r['login']
        intake=intake_target(directory,url=url,ca=Path(os.environ['ORACLE2_TEST_TLS_ROOT']).read_bytes(),updates=dict(
            principal_id=f.r['actor'],workspace_id=x['workspace'],expected_session_role=login,expected_owner_role=f.intake.config.expected_owner_role,
            runtime_hash=f.r['runtime'],registry_hash=f.r['registry']))
        directory=f.path/'wrong-peer';directory.mkdir(mode=0o700)
        f.settings=configured_confirmation(directory,certificates,intake=intake).settings
    try:
        request=json.loads(actual_wire(f));request.update(changes)
        from oracle_brain.operating_model.contracts import canonical_bytes
        with running(f) as server:assert send(server,certificates,canonical_bytes(request))[:2]==(409 if fault=='stale_cas' else 503,b'')
        row,events=state(f);assert row[:3]==(2,'processing',True) and events==[]
    finally:
        if restore:
            with owned_admin(x) as conn:conn.execute(sql.SQL('ALTER FUNCTION oracle2.compare_and_advance_replacement_journey(uuid,integer,jsonb,uuid) OWNER TO {}').format(sql.Identifier(restore)))


def test_actual_concurrent_confirmations_commit_one_event_only(actual_confirmation):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    f=actual_confirmation;barrier=threading.Barrier(2)
    def confirm():
        factory=ReplacementConfirmationFactoryV1(f.settings);request=actual_wire(f);barrier.wait(2)
        try:return factory.execute_v1(request,original_start=datetime.now(timezone.utc)).metadata.controlState
        except ConfirmationConflictV1:return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:confirm(),range(2)))
    assert sorted(results)==['conflict','delivered'] and len(state(f)[1])==1


def test_actual_committed_close_ack_loss_is_unknown_without_retry(actual_confirmation,certificates,monkeypatch):
    f=actual_confirmation;connect=psycopg.connect;execute=psycopg.Connection.execute;attempts=[]
    def observed_execute(self,query,*args,**kwargs):
        if self.info.user==f.r['login'] and isinstance(query,str) and query.startswith('SELECT oracle2.compare_and_advance_replacement_journey'):
            attempts.append('one actual mutation')
        return execute(self,query,*args,**kwargs)
    @contextmanager
    def lost_close(url,*args,**kwargs):
        selected=psycopg.conninfo.conninfo_to_dict(url).get('user')==f.r['login']
        with connect(url,*args,**kwargs) as conn:yield conn
        if selected:raise psycopg.OperationalError('invented lost committed close acknowledgment')
    monkeypatch.setattr(psycopg.Connection,'execute',observed_execute)
    monkeypatch.setattr(psycopg,'connect',lost_close)
    with running(f) as server:assert send(server,certificates,actual_wire(f))[:2]==(503,b'')
    assert attempts==['one actual mutation']
    row,events=state(f);assert row[:3]==(3,'delivered',False) and len(events)==1


def test_actual_original_deadline_while_waiting_lock_rolls_back_no_success(actual_confirmation,certificates):
    f=actual_confirmation
    with owned_admin(f.x) as blocker:
        blocker.execute('SELECT pg_advisory_xact_lock(hashtext(%s))',('oracle2-authz:'+str(f.x['workspace']),))
        with running(f) as server:assert send(server,certificates,actual_wire(f,seconds=1.25))[:2]==(503,b'')
    row,events=state(f);assert row[:3]==(2,'processing',True) and events==[]
