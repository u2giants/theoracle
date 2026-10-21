"""Actual Python TLS peers→shared TypeScript consumer; invented auth imports."""
import base64,hashlib,json,subprocess,threading
from datetime import datetime,timezone,timedelta
from pathlib import Path
from uuid import uuid4
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.replacement_request_service_v1 import protected_replacement_request_server_v1,RequesterPeerProfileV1
from oracle_brain.hosting.original_view_service_v1 import protected_original_view_server_v1
from oracle_brain.hosting.original_view_settings_v1 import OriginalViewerPeerProfileV1,load_original_viewer_settings_v1
from test_hosting_boundary import certificates
from test_replacement_request_service_v1 import profile_fixture
from test_original_view_settings_v1 import configured_viewer,PDF
from test_original_view_service_v1 import recording_sql


def dual_san(certificates,cert,key,hostname):
    ext=Path(cert).parent/'dual-san.ext';ext.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
    subprocess.run(['openssl','x509','-req','-in',str(certificates/'server.csr'),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',str(cert),'-days','1','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return hashlib.sha256(Path(cert).read_bytes()).hexdigest()


def node_proof(server,meta,tmp_path):
    meta.update(scratch=str(tmp_path),backend_origin='https://localhost.localdomain:'+str(server.server_port))
    path=tmp_path/'peer-meta.json';path.write_text(json.dumps(meta));path.chmod(0o600)
    repo=Path(__file__).resolve().parents[3]
    result=subprocess.run(['pnpm','--filter','@oracle/web','exec','node','--dns-result-order=ipv4first','--import','tsx','tests/oracle2/protected-peer-proof.ts',str(path)],cwd=repo,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=20)
    (tmp_path/'peer-process.txt').write_text(result.stdout)
    assert result.returncode==0,result.stdout[-5000:]
    return json.loads((tmp_path/'peer-conformance.json').read_text())


def test_actual_python_control_shared_web_client(tmp_path,monkeypatch,certificates):
    f,path,seal,tls=profile_fixture(tmp_path,monkeypatch,certificates)
    p=json.loads(path.read_bytes());p['server_certificate_sha256']=dual_san(certificates,p['server_certificate_file'],p['server_key_file'],'localhost.localdomain');p['server_hostname']='localhost.localdomain';raw=canonical_bytes(RequesterPeerProfileV1.model_validate_json(json.dumps(p)).model_dump(mode='json'));path.write_bytes(raw);seal=hashlib.sha256(raw).hexdigest()
    server=protected_replacement_request_server_v1(f.s,path,seal);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    c=f.s.config;deadline=(datetime.now(timezone.utc)+timedelta(seconds=5)).isoformat().replace('+00:00','Z');body=dict(schema_version=1,operation='status',run_id=str(f.run),caller_deadline=deadline)
    meta=dict(kind='control',common=c.model_dump(mode='json'),project_url=c.auth_issuer.removesuffix('/auth/v1'),auth_user_id=str(c.auth_user_id),employee_id=str(c.employee_id),intake_appointment_sha256=f.s.appointment_sha256,peer_profile_sha256=seal,request_wire_base64=base64.b64encode(canonical_bytes(body)).decode(),client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),**{k:p[k] for k in ('server_certificate_file','client_ca_file','client_uri','issuer_actor','reviewer_actor','valid_from','expires_at','original_horizon')})
    try:assert node_proof(server,meta,tmp_path)['kind']=='control'
    finally:server.shutdown();server.server_close();thread.join(2);assert not thread.is_alive() and not server._active


def test_actual_python_viewer_shared_web_client(tmp_path,monkeypatch,certificates):
    f=configured_viewer(tmp_path,certificates);recording_sql(f,monkeypatch)
    s=f.settings;p=s.peer.model_dump(mode='json')
    p['server_certificate']['sha256']=dual_san(certificates,p['server_certificate']['path'],p['server_key']['path'],'localhost.localdomain');p['server_hostname']='localhost.localdomain'
    raw=canonical_bytes(OriginalViewerPeerProfileV1.model_validate_json(json.dumps(p)).model_dump(mode='json'));Path(s.peer_input.path).write_bytes(raw);peer_sha=hashlib.sha256(raw).hexdigest()
    appointment=s.appointment.model_copy(update={'peer_profile_sha256':peer_sha});raw=canonical_bytes(appointment.model_dump(mode='json'));Path(s.appointment_input.path).write_bytes(raw)
    settings=load_original_viewer_settings_v1(s.config_input.path,s.config_input.sha256,s.appointment_input.path,hashlib.sha256(raw).hexdigest(),s.peer_input.path,peer_sha,issuer_actor=s.issuer_actor,reviewer_actor=s.reviewer_actor)
    server=protected_original_view_server_v1(settings);thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    c=settings.config;r=c.sources[0];deadline=(datetime.now(timezone.utc)+timedelta(seconds=5)).isoformat().replace('+00:00','Z');body=dict(schema_version=1,source_id=str(r.source_id),revision=r.revision,caller_deadline=deadline)
    meta=dict(kind='viewer',common=c.model_dump(mode='json'),project_url='https://invented-auth.example.test',auth_user_id=str(uuid4()),employee_id=str(uuid4()),viewer_config_sha256=settings.config_input.sha256,viewer_appointment_sha256=settings.appointment_input.sha256,peer_profile_sha256=settings.peer_input.sha256,storage_profile_hash=c.storage_profile_hash,sources=[dict(schema_version=1,**{k:v for k,v in x.model_dump(mode='json').items() if k!='schema_version'}) for x in c.sources],expected_byte_count=len(PDF),expected_sha256=hashlib.sha256(PDF).hexdigest(),request_wire_base64=base64.b64encode(canonical_bytes(body)).decode(),client_certificate_file=str(certificates/'worker.pem'),client_key_file=str(certificates/'worker.key'),server_certificate_file=p['server_certificate']['path'],client_ca_file=p['client_ca']['path'],client_uri=p['client_uri'],issuer_actor=str(s.issuer_actor),reviewer_actor=str(s.reviewer_actor),**{k:p[k] for k in ('valid_from','expires_at','original_horizon')})
    try:assert node_proof(server,meta,tmp_path)['kind']=='viewer'
    finally:server.shutdown();server.server_close();thread.join(2);assert not thread.is_alive() and not server._active
