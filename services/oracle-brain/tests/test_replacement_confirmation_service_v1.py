"""Real mTLS/HTTP, actual fixed confirmation factory; recording SQL boundary."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import http.client
import json
from pathlib import Path
import ssl
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.replacement_confirmation_service_v1 import protected_replacement_confirmation_server_v1, PATH
from oracle_brain.hosting.replacement_confirmation_v1 import (
    ReplacementConfirmationFactoryV1, ConfirmationOutcomeUnknownV1, ConfirmationUnavailableV1,
    FUNCTIONS, OWNER_QUERY,
)
from test_replacement_confirmation_settings_v1 import configured_confirmation
from test_hosting_boundary import certificates

FIELDS={'runId','journeyRevision','controlState','populationSha256','cancelRequested','remoteStopProven','resultAvailable'}


def client(server,certificates,identity='worker',trusted=True):
    context=ssl.create_default_context(cafile=str(certificates/('ca.pem' if trusted else 'other.pem')))
    context.verify_flags|=ssl.VERIFY_X509_STRICT
    if identity:context.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
    return http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=5)


def wire(f,seconds=10,**changes):
    value=dict(schema_version=1,run_id=str(f.run),expected_journey_revision=f.revision,model_id=str(f.model),version=1,
        content_hash='d'*64,ack_event_id=str(f.ack),workflow_id='invented-flow',idempotency_key=str(uuid4()),
        caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z'))
    return canonical_bytes(value|changes)


def send(server,certificates,raw,*,identity='worker',route=PATH,headers=None):
    conn=client(server,certificates,identity)
    try:
        conn.request('POST',route,body=raw,headers={'Content-Type':'application/json'}|(headers or {}))
        response=conn.getresponse();return response.status,response.read(),dict(response.getheaders())
    finally:conn.close()


@contextmanager
def running(f):
    server=protected_replacement_confirmation_server_v1(f.settings)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    try:yield server
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1


def recording_sql(f,monkeypatch):
    f.run=uuid4();f.model=uuid4();f.ack=uuid4();f.revision=2;f.connections=[];f.events=[];f.attempts=0
    f.metadata_changes={};f.envelope_changes={};f.wrong_owner=False;f.extra_role=False;f.wrong_login=False;f.no_ssl=False
    f.cas=False;f.commit_error=False;f.after_close=None;f.before_return=None
    c=f.intake.config
    def context():
        now=datetime.now(timezone.utc)
        return dict(schema_version=1,principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),session_role=c.expected_session_role,
            runtime_hash=c.runtime_hash,source_registry_hash=c.registry_hash,checked_at=now.isoformat(),valid_until=c.expires_at.isoformat())
    class Connection:
        def __init__(self):
            f.connections.append(self);self.closed=False;self.committed=False
            self.info=SimpleNamespace(get_parameters=lambda:dict(f.target),port=int(f.target.get('port',5432)),hostaddr=f.target['host'])
            self.pgconn=SimpleNamespace(ssl_in_use=not f.no_ssl)
        def __enter__(self):return self
        def __exit__(self,*args):
            self.closed=True
            if f.after_close:f.after_close()
        def commit(self):
            self.committed=True;f.events.append('commit')
            if f.commit_error:raise psycopg.OperationalError('invented lost actual write acknowledgment')
        def execute(self,q,args=None):
            self.q=q;f.events.append((q,args))
            if q.startswith('SELECT oracle2.compare_and_advance_replacement_journey'):
                f.attempts+=1
                assert set(json.loads(args[2]))=={'target_state','model_id','version','content_hash','ack_event_id','workflow_id'}
                assert json.loads(args[2])['target_state']=='delivered'
                if f.cas:raise psycopg.errors.SerializationFailure('invented stale CAS')
                if f.before_return:f.before_return()
            return self
        def fetchall(self):
            if self.q==OWNER_QUERY:return [(n,'oracle2',n,'wrong' if f.wrong_owner else c.expected_owner_role,True) for n,_ in FUNCTIONS]
            if 'SELECT rolname::text' in self.q:return [(c.expected_session_role,),('oracle2_replacement_requester',)]+([('oracle2_source_original_reader',)] if f.extra_role else [])
            raise AssertionError(self.q)
        def fetchone(self):
            if self.q.startswith('SELECT session_user'):
                role='wrong' if f.wrong_login else c.expected_session_role
                return (role,role,True,False,False,False,False,False)
            if self.q.startswith('SELECT rolcanlogin'):return (False,)*7
            if self.q.startswith('SELECT r.rolname'):return (c.expected_owner_role,False)
            if self.q.startswith('SELECT oracle2.compare_and_advance'):
                return (dict(schema_version=1,run_id=str(f.run),journey_revision=f.revision+1,state='delivered',population_sha256='e'*64,context=context())|f.envelope_changes,)
            if self.q.startswith('SELECT oracle2.current_replacement_journey_metadata'):
                return (dict(schema_version=1,run_id=str(f.run),journey_revision=f.revision+1,state='delivered',population_sha256='e'*64,
                    cancel_requested=False,paid_cost_retained=True,context=context())|f.metadata_changes,)
            raise AssertionError(self.q)
    def connect(url,**kwargs):
        assert 1<=kwargs['connect_timeout']<=5 and kwargs['tcp_user_timeout']<=30000
        return Connection()
    monkeypatch.setattr('psycopg.connect',connect)


def test_actual_mtls_fixed_sql_and_fresh_public_seven_metadata_only(tmp_path,certificates,monkeypatch):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:status,raw,headers=send(server,certificates,wire(f))
    value=json.loads(raw)
    assert status==200 and set(value)==FIELDS and raw==canonical_bytes(value)
    assert value['controlState']=='delivered' and not value['remoteStopProven'] and not value['resultAvailable']
    assert headers['Content-Type']=='application/json' and headers['Cache-Control']=='no-store, private'
    assert headers['Connection']=='close'
    assert f.attempts==1 and len(f.connections)==1 and f.connections[0].committed and f.connections[0].closed


@pytest.mark.parametrize('change',[dict(actor=str(uuid4())),dict(workspace_id=str(uuid4())),dict(target_state='processing'),dict(role='owner'),
    dict(path='/private'),dict(operation='withdraw'),dict(expected_journey_revision=True),dict(version=0),dict(content_hash='bad'),
    dict(caller_deadline='2099-01-01T00:00:00Z'),dict(caller_deadline='2000-01-01T00:00:00Z')])
def test_closed_request_refuses_before_sql(tmp_path,certificates,monkeypatch,change):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:assert send(server,certificates,wire(f,**change))[:2]==(503,b'')
    assert f.attempts==0 and not f.connections


@pytest.mark.parametrize('kind',['duplicate','noncanonical','oversize','wrongroute','wrongpeer','contentencoding','transferencoding','range','missing'])
def test_fixed_transport_before_sql(tmp_path,certificates,monkeypatch,kind):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch);raw=wire(f);options={}
    if kind=='missing':raw=b'{}'
    elif kind=='duplicate':raw=raw[:-1]+b',"version":1}'
    elif kind=='noncanonical':raw=b' '+raw
    elif kind=='oversize':raw=b'x'*8193
    elif kind=='wrongroute':options['route']=PATH+'?actor=x'
    elif kind=='wrongpeer':options['identity']='other'
    elif kind=='contentencoding':options['headers']={'Content-Encoding':'gzip'}
    elif kind=='transferencoding':options['headers']={'Transfer-Encoding':'chunked'}
    elif kind=='range':options['headers']={'Range':'bytes=0-10'}
    with running(f) as server:assert send(server,certificates,raw,**options)[:2]==(503,b'')
    assert not f.connections


@pytest.mark.parametrize('fault',['wrong_owner','wrong_login','extra_role','no_ssl'])
def test_actual_caller_owner_tls_denial_before_mutation(tmp_path,certificates,monkeypatch,fault):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch);setattr(f,fault,True)
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert f.attempts==0


@pytest.mark.parametrize('change',[dict(run_id=str(uuid4())),dict(journey_revision=99),dict(state='processing'),dict(population_sha256='f'*64),dict(cancel_requested=True),dict(unknown=True)])
def test_fresh_metadata_mismatch_never_commits_or_returns_success(tmp_path,certificates,monkeypatch,change):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch);f.metadata_changes=change
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert f.attempts==1 and not f.connections[0].committed


def test_cas_conflict_and_lost_ack_are_not_retried(tmp_path,certificates,monkeypatch):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch);f.cas=True
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(409,b'')
    assert f.attempts==1 and not f.connections[0].committed
    f.cas=False;f.commit_error=True
    with pytest.raises(ConfirmationOutcomeUnknownV1):ReplacementConfirmationFactoryV1(f.settings).execute_v1(wire(f),original_start=datetime.now(timezone.utc))
    assert f.attempts==2 and len(f.connections)==2


@pytest.mark.parametrize('when',['before_commit','after_close'])
def test_original_deadline_cannot_extend_at_sql_or_close(tmp_path,certificates,monkeypatch,when):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch)
    if when=='before_commit':f.before_return=lambda:time.sleep(1.25)
    else:f.after_close=lambda:time.sleep(1.25)
    raw=wire(f,seconds=1.15)
    with running(f) as server:assert send(server,certificates,raw)[:2]==(503,b'')
    assert f.attempts==1 and f.connections[0].committed==(when=='after_close')


def test_one_active_confirmation_and_changed_pin_refuse(tmp_path,certificates,monkeypatch):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch)
    entered=threading.Event();release=threading.Event()
    def pause():entered.set();assert release.wait(2)
    f.before_return=pause
    with running(f) as server:
        outcomes=[];worker=threading.Thread(target=lambda:outcomes.append(send(server,certificates,wire(f))))
        worker.start();assert entered.wait(2)
        try:assert send(server,certificates,wire(f))[:2]==(503,b'')
        finally:release.set();worker.join(3)
        assert outcomes[0][0]==200 and f.attempts==1
        Path(f.settings.appointment_input.path).write_bytes(b'{}')
        assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert f.attempts==1


def test_actual_wrong_ca_missing_client_and_duplicate_headers_before_sql(tmp_path,certificates,monkeypatch):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch);raw=wire(f)
    with running(f) as server:
        for identity,trusted in [(None,True),('worker',False)]:
            conn=client(server,certificates,identity,trusted)
            try:
                with pytest.raises((ssl.SSLError,ConnectionError)):
                    conn.request('POST',PATH,body=raw,headers={'Content-Type':'application/json'});conn.getresponse()
            finally:conn.close()
        conn=client(server,certificates)
        try:
            conn.putrequest('POST',PATH);conn.putheader('Content-Type','application/json')
            conn.putheader('Content-Length',str(len(raw)));conn.putheader('Content-Length',str(len(raw)));conn.endheaders(raw)
            response=conn.getresponse();assert response.status==503 and response.read()==b''
        finally:conn.close()
    assert not f.connections


def test_changed_appointment_after_committed_close_never_returns_success(tmp_path,certificates,monkeypatch):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch)
    f.after_close=lambda:Path(f.settings.appointment_input.path).write_bytes(b'{}')
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert f.attempts==1 and f.connections[0].committed and f.connections[0].closed


def test_actual_slow_body_client_drop_and_peer_uri_refuse_without_retry(tmp_path,certificates,monkeypatch):
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:
        raw=wire(f,seconds=.15);conn=client(server,certificates)
        try:
            conn.putrequest('POST',PATH);conn.putheader('Content-Type','application/json');conn.putheader('Content-Length',str(len(raw)))
            conn.endheaders();conn.send(raw[:1]);time.sleep(.2);conn.send(raw[1:]);response=conn.getresponse()
            assert response.status==503 and response.read()==b''
        finally:conn.close()
        assert f.attempts==0
        entered=threading.Event();release=threading.Event();closed=threading.Event()
        f.before_return=lambda:(entered.set(),release.wait(2));f.after_close=closed.set
        conn=client(server,certificates);conn.request('POST',PATH,body=wire(f),headers={'Content-Type':'application/json'})
        assert entered.wait(2);conn.close();release.set();assert closed.wait(2)
    assert f.attempts==1 and f.connections[0].committed
    other=tmp_path/'wrong-uri';other.mkdir(mode=0o700)
    f=configured_confirmation(other,certificates,peer_changes={'client_uri':'spiffe://oracle/wrong'});recording_sql(f,monkeypatch)
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert not f.connections


def test_actual_expired_client_cert_rejected_before_sql(tmp_path,certificates,monkeypatch):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID
    from test_hosting_boundary import WORKER
    ca=x509.load_pem_x509_certificate((certificates/'ca.pem').read_bytes())
    key=serialization.load_pem_private_key((certificates/'ca.key').read_bytes(),None)
    worker=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes());now=datetime.now(timezone.utc)
    cert=(x509.CertificateBuilder().subject_name(worker.subject).issuer_name(ca.subject).public_key(worker.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=2)).not_valid_after(now-timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
        .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,None,None),critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier(WORKER)]),critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]),critical=False)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(worker.public_key()),critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca.public_key()),critical=False)
        .sign(key,hashes.SHA256()))
    (certificates/'expired.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM));(certificates/'expired.pem').chmod(0o600)
    (certificates/'expired.key').write_bytes((certificates/'worker.key').read_bytes());(certificates/'expired.key').chmod(0o600)
    f=configured_confirmation(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:
        conn=client(server,certificates,'expired')
        try:
            with pytest.raises((ssl.SSLError,ConnectionError)):
                conn.request('POST',PATH,body=wire(f),headers={'Content-Type':'application/json'});conn.getresponse()
        finally:conn.close()
    assert not f.connections
