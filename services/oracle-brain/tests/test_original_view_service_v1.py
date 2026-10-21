"""Actual loopback mTLS to real viewer factory and private bytes; recording SQL."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import http.client
import json
from pathlib import Path
import ssl
import threading
import time
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.hosting.original_view_service_v1 import protected_original_view_server_v1, PATH
from oracle_brain.hosting.original_view_v1 import OriginalViewerFactoryV1, OriginalViewerUnavailable, FUNCTIONS, OWNER_QUERY
from test_hosting_boundary import certificates
from test_original_view_settings_v1 import configured_viewer, PDF


def client(server, certificates, identity='worker', trusted=True):
    context=ssl.create_default_context(cafile=str(certificates/('ca.pem' if trusted else 'other.pem')))
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    if identity: context.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
    return http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=4)


def wire(f,seconds=10,**changes):
    r=f.settings.config.sources[0]
    return canonical_bytes(dict(schema_version=1,source_id=str(r.source_id),revision=r.revision,
        caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=seconds)).isoformat().replace('+00:00','Z'))|changes)


def send(server,certificates,raw,*,identity='worker',route=PATH,headers=None):
    connection=client(server,certificates,identity)
    try:
        connection.request('POST',route,body=raw,headers={'Content-Type':'application/json'}|(headers or {}))
        response=connection.getresponse()
        return response.status,response.read(),dict(response.getheaders())
    finally: connection.close()


def recording_sql(f,monkeypatch):
    f.connections=[];f.queries=[];f.caps=0;f.close_error=False;f.wrong_owner=False;f.wrong_login=False
    f.extra_group=False;f.no_ssl=False;f.cap_changes={};f.after_close=None
    c=f.settings.config;r=c.sources[0]
    class Connection:
        def __init__(self):
            self.number=len(f.connections)+1;f.connections.append(self);self.closed=False;self.committed=False
            self.info=SimpleNamespace(get_parameters=lambda:dict(f.target),port=int(f.target.get('port',5432)),hostaddr=f.target['host'])
            self.pgconn=SimpleNamespace(ssl_in_use=not f.no_ssl)
        def __enter__(self): return self
        def __exit__(self,*args):
            self.closed=True
            if f.close_error:raise RuntimeError('invented uncertain connection close')
            if f.after_close:f.after_close(self.number)
        def commit(self):self.committed=True
        def execute(self,q,args=None):self.q=q;f.queries.append((q,args));return self
        def fetchall(self):
            if self.q==OWNER_QUERY:
                return [(name,'oracle2',name,'wrong_owner' if f.wrong_owner else c.expected_owner_role,True) for name,_ in FUNCTIONS]
            if 'SELECT rolname::text' in self.q:
                return [(c.expected_session_role,),('oracle2_source_original_viewer',)]+([('oracle2_source_original_reader',)] if f.extra_group else [])
            raise AssertionError(self.q)
        def fetchone(self):
            if self.q.startswith('SELECT session_user'):
                login='wrong_login' if f.wrong_login else c.expected_session_role
                return (login,login,True,False,False,False,False,False)
            if self.q.startswith('SELECT rolcanlogin'):return (False,)*7
            if self.q.startswith('SELECT r.rolname'):return (c.expected_owner_role,False)
            if self.q.startswith('SELECT oracle2.original_revision_view_v1'):
                f.caps+=1;now=datetime.now(timezone.utc)
                return (dict(schema_version=1,workspace_id=str(c.workspace_id),source_id=str(r.source_id),revision=r.revision,
                    principal_id=str(c.principal_id),original_sha256=r.original_sha256,byte_count=r.byte_count,media_type=r.media_type,
                    private_object_key=f'source-originals/{c.workspace_id}/{r.source_id}/{r.revision}/{r.reservation_id}',
                    runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,population_id=None,
                    valid_until=c.expires_at.isoformat(),checked_at=now.isoformat())|f.cap_changes,)
            raise AssertionError(self.q)
    def connect(raw,**kwargs):
        assert 1<=kwargs['connect_timeout']<=5 and kwargs['tcp_user_timeout']<=30000
        return Connection()
    monkeypatch.setattr('psycopg.connect',connect)


@contextmanager
def running(f):
    server=protected_original_view_server_v1(f.settings)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    try:yield server
    finally:
        server.shutdown();server.server_close();thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno()==-1


def test_actual_mtls_realfactory_pdf_two_closed_currentness_passes(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:
        status,data,headers=send(server,certificates,wire(f))
    assert status==200 and data==PDF
    assert headers['Content-Type']=='application/pdf' and headers['Cache-Control']=='no-store, private'
    assert headers['Content-Length']==str(len(PDF)) and headers['X-Content-Type-Options']=='nosniff'
    assert f.caps==4 and len(f.connections)==2 and all(c.closed and c.committed for c in f.connections)
    assert not any('INSERT' in q or 'UPDATE' in q for q,_ in f.queries)


@pytest.mark.parametrize('headers',[{'Range':'bytes=0-10'},{'If-Range':'x'},{'Content-Encoding':'gzip'},
    {'Transfer-Encoding':'chunked'},{'If-None-Match':'x'},{'Content-Type':'text/plain'},{'Expect':'100-continue'}])
def test_transport_refuses_without_sql(tmp_path,certificates,monkeypatch,headers):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:assert send(server,certificates,wire(f),headers=headers)[:2]==(503,b'')
    assert not f.connections


@pytest.mark.parametrize('change',[dict(actor=str(uuid4())),dict(role='oracle2_source_original_reader'),dict(path='/tmp/x'),
    dict(workspace_id=str(uuid4())),dict(revision=True),dict(revision=0),dict(source_id=str(uuid4())),
    dict(caller_deadline='2026-01-01T00:00:00Z'),dict(caller_deadline='2099-01-01T00:00:00Z')])
def test_unknown_selector_or_authority_and_bad_deadline_denied(tmp_path,certificates,monkeypatch,change):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:assert send(server,certificates,wire(f,**change))[:2]==(503,b'')
    assert not f.connections


@pytest.mark.parametrize('kind',['noncanonical','duplicate','missing','oversize','unknownroute','wrongpeer'])
def test_malformed_or_unpinned_peer_denied_before_sql(tmp_path,certificates,monkeypatch,kind):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch);raw=wire(f);options={}
    if kind=='noncanonical':raw=b' '+raw
    if kind=='duplicate':raw=raw[:-1]+b',"revision":1}'
    if kind=='missing':raw=b'{}'
    if kind=='oversize':raw=b'x'*4097
    if kind=='unknownroute':options['route']=PATH+'?source=x'
    if kind=='wrongpeer':options['identity']='other'
    with running(f) as server:assert send(server,certificates,raw,**options)[:2]==(503,b'')
    assert not f.connections


@pytest.mark.parametrize('fault',['wrong_owner','wrong_login','extra_group','no_ssl','close_error'])
def test_sql_identity_or_uncertain_close_never_returns_bytes(tmp_path,certificates,monkeypatch,fault):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch);setattr(f,fault,True)
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert len(f.connections)==1


@pytest.mark.parametrize('changes',[dict(population_id=str(uuid4())),dict(private_object_key='../../other'),
    dict(principal_id=str(uuid4())),dict(runtime_hash='e'*64),dict(registry_hash='e'*64),dict(byte_count=len(PDF)+1),
    dict(media_type='text/plain'),dict(original_sha256='d'*64),dict(revision=2),dict(unknown=True),
    dict(valid_until='2000-01-01T00:00:00Z'),dict(checked_at='2000-01-01T00:00:00Z')])
def test_sql_capability_or_locator_mismatch_denied(tmp_path,certificates,monkeypatch,changes):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch);f.cap_changes=changes
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')


def test_fresh_second_sql_pass_denies_changed_current_source(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    f.after_close=lambda phase:f.cap_changes.update(original_sha256='d'*64) if phase==1 else None
    with running(f) as server:assert send(server,certificates,wire(f))[:2]==(503,b'')
    assert len(f.connections)==2 and all(c.closed for c in f.connections)


@pytest.mark.parametrize('which',['bytes','custody','root','pin'])
def test_private_custody_or_startup_drift_denies_pdf(tmp_path,certificates,monkeypatch,which):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch);r=f.settings.config.sources[0]
    if which=='bytes':
        path=next((f.root/'source-originals').rglob(str(r.reservation_id)));path.write_bytes(b'x'*len(PDF))
    elif which=='custody':(f.root/'intake-observations'/str(r.reservation_id)/'custody.json').write_bytes(b'{}')
    with running(f) as server:
        if which=='root':f.root.chmod(0o755)
        if which=='pin':Path(f.settings.config_input.path).write_bytes(b'{}')
        assert send(server,certificates,wire(f))[:2]==(503,b'')


def test_late_private_read_stops_before_second_getter_or_sql_pass(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    original=FileBlobStore._read_original_bytes
    def late(self,ref):time.sleep(1.35);return original(self,ref)
    monkeypatch.setattr(FileBlobStore,'_read_original_bytes',late)
    with running(f) as server:assert send(server,certificates,wire(f,seconds=1.25))[:2]==(503,b'')
    assert len(f.connections)==1 and f.caps==1


def test_one_active_read_slot_and_client_drop_preserve_server(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    reached=threading.Event();release=threading.Event();original=FileBlobStore._read_original_bytes
    def paused(self,ref):reached.set();assert release.wait(2);return original(self,ref)
    monkeypatch.setattr(FileBlobStore,'_read_original_bytes',paused)
    with running(f) as server:
        result=[];thread=threading.Thread(target=lambda:result.append(send(server,certificates,wire(f))))
        thread.start();assert reached.wait(2)
        try:assert send(server,certificates,wire(f))[:2]==(503,b'')
        finally:release.set();thread.join(3)
        assert result[0][:2]==(200,PDF)
        connection=client(server,certificates);connection.request('POST',PATH,body=wire(f),headers={'Content-Type':'application/json'});connection.close()
        assert send(server,certificates,wire(f))[0] in {200,503}


def test_untrusted_or_missing_tls_certificate_fails_before_sql(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:
        connection=client(server,certificates,identity=None)
        with pytest.raises((ssl.SSLError,ConnectionError)):connection.request('POST',PATH,body=wire(f),headers={'Content-Type':'application/json'});connection.getresponse()
        connection.close()
    assert not f.connections


def test_sql_horizon_is_returned_narrowed_never_reset_for_network(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    original_end=datetime.now(timezone.utc)+timedelta(seconds=8)
    f.cap_changes={'valid_until':original_end.isoformat()}
    result=OriginalViewerFactoryV1(f.settings).read_pdf_v1(f.settings.config.sources[0].source_id,1,
        caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
    assert result.valid_until==original_end and result.data==PDF


def test_actual_duplicate_http_headers_refused_before_sql(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch);raw=wire(f)
    with running(f) as server:
        for duplicate in ['Content-Length','Content-Type']:
            connection=client(server,certificates)
            try:
                connection.putrequest('POST',PATH)
                connection.putheader('Content-Type','application/json');connection.putheader('Content-Length',str(len(raw)))
                connection.putheader(duplicate,str(len(raw)) if duplicate=='Content-Length' else 'application/json')
                connection.endheaders(raw);response=connection.getresponse()
                assert response.status==503 and response.read()==b''
            finally:connection.close()
    assert not f.connections


def test_actual_slow_body_never_extends_original_request_deadline(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch);raw=wire(f,seconds=.15)
    with running(f) as server:
        connection=client(server,certificates)
        try:
            connection.putrequest('POST',PATH);connection.putheader('Content-Type','application/json')
            connection.putheader('Content-Length',str(len(raw)));connection.endheaders();connection.send(raw[:1])
            time.sleep(.2);connection.send(raw[1:]);response=connection.getresponse()
            assert response.status==503 and response.read()==b''
        finally:connection.close()
    assert not f.connections


def test_wrong_ca_prevents_tls_before_sql(tmp_path,certificates,monkeypatch):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:
        connection=client(server,certificates,trusted=False)
        try:
            with pytest.raises(ssl.SSLError):connection.request('POST',PATH,body=wire(f),headers={'Content-Type':'application/json'})
        finally:connection.close()
    assert not f.connections


def test_correct_pinned_der_with_wrong_client_uri_is_denied(tmp_path,certificates,monkeypatch):
    import hashlib
    from cryptography import x509
    from cryptography.hazmat.primitives.serialization import Encoding
    other=x509.load_pem_x509_certificate((certificates/'other.pem').read_bytes()).public_bytes(Encoding.DER)
    f=configured_viewer(tmp_path,certificates,peer_changes={'client_certificate_sha256':hashlib.sha256(other).hexdigest()})
    recording_sql(f,monkeypatch)
    with running(f) as server:assert send(server,certificates,wire(f),identity='other')[:2]==(503,b'')
    assert not f.connections


def test_actual_expired_client_certificate_is_denied_at_tls(tmp_path,certificates,monkeypatch):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID
    from test_hosting_boundary import WORKER
    ca=x509.load_pem_x509_certificate((certificates/'ca.pem').read_bytes())
    key=serialization.load_pem_private_key((certificates/'ca.key').read_bytes(),None)
    worker=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes())
    now=datetime.now(timezone.utc)
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
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    with running(f) as server:
        connection=client(server,certificates,identity='expired')
        try:
            with pytest.raises((ssl.SSLError,ConnectionError)):
                connection.request('POST',PATH,body=wire(f),headers={'Content-Type':'application/json'});connection.getresponse()
        finally:connection.close()
    assert not f.connections
