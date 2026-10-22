"""Real own SQL/intake through protected mTLS; invented service installation."""
from datetime import datetime,timedelta,timezone
import hashlib,json,socket,ssl,threading
import psycopg
import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_normalization_v1 import MeetingNormalizationFactoryV1
from oracle_brain.hosting.meeting_normalization_service_v1 import (MeetingNormalizationPeerProfileV1,
    protected_meeting_normalization_server_v1)
from test_meeting_normalization_sql import normalized,meeting_sql,original_request_fence
from test_meeting_capture_sql import admin
from test_hosting_boundary import certificates,WORKER


def server_for(f,certificates,tmp_path):
    s=f.settings;b=s.capture.host.config;now=datetime.now(timezone.utc)
    pin=lambda name:hashlib.sha256((certificates/name).read_bytes()).hexdigest()
    cert=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes())
    profile=MeetingNormalizationPeerProfileV1(schema_version=1,purpose='meeting-normalization-worker-peer-v1',meeting_id=s.capture.config.meeting_id,normalization_config_sha256=s.config_sha256,normalization_admission_sha256=s.capture.config.admission_sha256,
        intake_config_sha256=s.capture.host.config_sha256,intake_appointment_sha256=s.capture.host.appointment_sha256,principal_id=b.principal_id,workspace_id=b.workspace_id,runtime_hash=b.runtime_hash,registry_hash=b.registry_hash,
        client_uri=WORKER,client_certificate_sha256=hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest(),listen_host='127.0.0.1',listen_port=0,server_hostname='localhost',
        server_certificate_file=str(certificates/'server.pem'),server_certificate_sha256=pin('server.pem'),server_key_file=str(certificates/'server.key'),server_key_sha256=pin('server.key'),client_ca_file=str(certificates/'ca.pem'),client_ca_sha256=pin('ca.pem'),
        issuer_actor=s.capture.host.expected_issuer_actor,reviewer_actor=s.capture.host.expected_reviewer_actor,valid_from=now-timedelta(seconds=1),expires_at=min(s.config.expires_at,b.expires_at,b.original_horizon),original_horizon=b.original_horizon)
    raw=canonical_bytes(profile.model_dump(mode='json'));path=tmp_path/'normalization-peer';path.write_bytes(raw);path.chmod(0o600)
    return protected_meeting_normalization_server_v1(s,path,hashlib.sha256(raw).hexdigest())


def request(server,certificates,q,identity='worker'):
    ctx=ssl.create_default_context(cafile=str(certificates/'ca.pem'));ctx.verify_flags|=ssl.VERIFY_X509_STRICT
    ctx.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
    body=canonical_bytes(q);wire=b'POST /v1/replacement/meetings/normalize HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
    with socket.create_connection(('127.0.0.1',server.server_port),timeout=3) as tcp:
        with ctx.wrap_socket(tcp,server_hostname='localhost') as tls:
            tls.settimeout(3);tls.sendall(wire);parts=[]
            while True:
                part=tls.recv(65536)
                if not part:break
                parts.append(part)
    header,data=b''.join(parts).split(b'\r\n\r\n',1);status=int(header.split(b' ')[1])
    if status==200:assert b'Connection: close' in header
    else:assert status==503 and data==b''
    return status,json.loads(data) if data else None


def test_real_normalization_mtls_current_SQL_custody_and_private_closed_response(normalized,certificates,tmp_path):
    x,f,event,_=normalized;server=server_for(f,certificates,tmp_path)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    q=dict(schema_version=1,ingress_event_id=str(event),caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z'))
    try:
        assert request(server,certificates,q,identity='other')[0]==503
        with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        status,value=request(server,certificates,q);assert status==200
        assert set(value)=={'schema_version','principal_id','workspace_id','meeting_id','ingress_event_id','state','valid_until','source_binding','qualification','source_read_permission','observation_only'}
        assert set(value['source_binding'])=={'source_id','revision','original_sha256','byte_count'}
        assert value['state']=='awaiting_independently_installed_exact_reading_review'
        assert value['qualification'] is False and value['source_read_permission'] is False and value['observation_only'] is True
        assert request(server,certificates,q)[1]['source_binding']==value['source_binding']
        assert request(server,certificates,q|dict(actor_id=str(x['owner'])))[0]==503
        with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        (tmp_path/'actual-normalization-response.json').write_bytes(canonical_bytes(value))
    finally:
        server.shutdown();server.server_close();thread.join(2);assert not thread.is_alive() and not server._active


def test_immutable_startup_is_allowed_but_missing_request_fence_has_zero_SQL_or_original_bytes(normalized,monkeypatch):
    from oracle_brain.operating_model.request_deadline_v1 import _request_end_v1
    import oracle_brain.hosting.meeting_capture_v1 as capture_module
    x,old,event,_=normalized;calls=[];reads=[]
    original_connect=psycopg.connect;original_read=capture_module._read_private_at
    monkeypatch.setattr(psycopg,'connect',lambda *a,**k:(calls.append(1),original_connect(*a,**k))[1])
    monkeypatch.setattr(capture_module,'_read_private_at',lambda *a,**k:(reads.append(1),original_read(*a,**k))[1])
    token=_request_end_v1.set(None)
    try:
        f=MeetingNormalizationFactoryV1(old.settings)
        for action in (f.normalize_v1,f.status_v1,f.reconcile_v1):
            with pytest.raises(PermissionError,match='original protected request fence'):action(event,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
        assert calls==[] and reads==[]
    finally:_request_end_v1.reset(token)
