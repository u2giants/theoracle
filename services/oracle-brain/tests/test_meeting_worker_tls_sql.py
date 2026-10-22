"""Actual protected Python mTLS→current SQL, invented installation only."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import base64,hashlib,json,socket,ssl,threading
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_worker_service_v1 import CaptureWorkerPeerProfileV1,protected_meeting_create_worker_server_v1
from test_meeting_delivery_sql import delivery,meeting_sql,original_fence,worker_factory
from test_meeting_create_forensic_sql import response
from test_meeting_capture_sql import admin
from test_hosting_boundary import certificates,WORKER


def worker_server(factory,certificates,tmp_path):
    s=factory.settings;b=s.capture.host.config;now=datetime.now(timezone.utc)
    leaf=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes())
    sha=lambda name:hashlib.sha256((certificates/name).read_bytes()).hexdigest()
    value=dict(schema_version=1,purpose='replacement-meeting-capture-worker-peer-v1',effect_purpose='capture-create',retrieve_stage=None,worker_id=str(s.config.worker_id),meeting_id=str(s.capture.config.meeting_id),provider_account=s.capture.config.provider_account,worker_config_sha256=s.sha256,worker_admission_sha256=s.capture.config.admission_sha256,operation_policy_sha256=s.config.operation_policy_sha256,intake_config_sha256=s.capture.host.config_sha256,intake_appointment_sha256=s.capture.host.appointment_sha256,principal_id=str(b.principal_id),workspace_id=str(b.workspace_id),runtime_hash=b.runtime_hash,registry_hash=b.registry_hash,client_uri=WORKER,client_certificate_sha256=hashlib.sha256(leaf.public_bytes(Encoding.DER)).hexdigest(),listen_host='127.0.0.1',listen_port=0,server_hostname='localhost',server_certificate_file=str(certificates/'server.pem'),server_certificate_sha256=sha('server.pem'),server_key_file=str(certificates/'server.key'),server_key_sha256=sha('server.key'),client_ca_file=str(certificates/'ca.pem'),client_ca_sha256=sha('ca.pem'),issuer_actor=str(s.capture.host.expected_issuer_actor),reviewer_actor=str(s.capture.host.expected_reviewer_actor),valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=s.config.expires_at.isoformat(),original_horizon=b.original_horizon.isoformat())
    profile=CaptureWorkerPeerProfileV1.model_validate_json(json.dumps(value));raw=canonical_bytes(profile.model_dump(mode='json'));path=tmp_path/'worker-peer';path.write_bytes(raw);path.chmod(0o600)
    return protected_meeting_create_worker_server_v1(s,path,hashlib.sha256(raw).hexdigest())


def request(server,certificates,body,identity='worker'):
    context=ssl.create_default_context(cafile=str(certificates/'ca.pem'));context.verify_flags|=ssl.VERIFY_X509_STRICT
    context.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
    raw=canonical_bytes(body);packet=b'POST /v1/replacement/meetings/worker HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw
    # Exact IPv4 fixture target; TLS identity remains localhost, independently
    # verified. No localhost IPv6 lookup can reach another process's port.
    with socket.create_connection(('127.0.0.1',server.server_port),timeout=3) as connected:
        with context.wrap_socket(connected,server_hostname='localhost') as tls:
            tls.settimeout(3);tls.sendall(packet);parts=[]
            while True:
                part=tls.recv(65536)
                if not part:break
                parts.append(part)
    wire=b''.join(parts);header,data=wire.split(b'\r\n\r\n',1);status=int(header.split(b' ')[1]);headers=dict((k.lower(),v.strip()) for k,v in (line.split(b':',1) for line in header.split(b'\r\n')[1:]))
    assert len(data)==int(headers[b'content-length'])
    if status==200:assert headers[b'connection']==b'close'
    if status!=200:assert status==503 and data==b''
    return status,json.loads(data) if data else None,wire


def test_missing_supervisor_pins_fixed_mtls_startup_refuses_and_direct_compatibility_remains(delivery,tmp_path,certificates):
    import pytest
    x=delivery;f=worker_factory(x,x['creator'],tmp_path)
    # The fixed unattended endpoint cannot borrow a manually supplied SQL
    # observation. The retained direct factory remains an explicit API.
    with pytest.raises(PermissionError,match='concrete independently installed supervisor consumer required'):
        worker_server(f,certificates,tmp_path)
    with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
    end=min(datetime.now(timezone.utc)+timedelta(seconds=15),x['capture_until'])
    prepared=f.prepare_v1(caller_deadline=end);assert prepared.state=='prepared' and not prepared.fresh_claim
    claimed,body=f.claim_v1(x['operation'],caller_deadline=end);assert claimed.state=='claimed' and body==x['body']
    current=f.current_v1(x['operation'],claimed.claim_id,caller_deadline=end);assert current.state=='inflight' and not current.fresh_claim
    raw=response(body={'id':str(uuid4())});observed=f.observe_v1(x['operation'],claimed.claim_id,raw,caller_deadline=end)
    assert observed.state=='observed'
    repeated,repeated_body=f.claim_v1(x['operation'],caller_deadline=end);assert repeated_body is None and not repeated.fresh_claim
    with admin(x) as c:
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_worker_receipts_v1 r JOIN oracle2.meeting_capture_worker_claims_v1 c USING(claim_id) WHERE c.workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
