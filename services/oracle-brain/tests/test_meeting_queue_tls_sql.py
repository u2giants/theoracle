"""Actual own SQL/private custody over mTLS; invented identity, no Trigger call."""
from datetime import datetime,timedelta,timezone
import hashlib,json,socket,ssl,threading
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_queue_service_v1 import MeetingQueuePeerProfileV1,protected_meeting_queue_server_v1
from test_meeting_queue_sql import queue,meeting_sql,configured_settings,original_request_fence,wire
from test_meeting_capture_sql import admin
from test_hosting_boundary import certificates,WORKER

def server_for(f,certificates,tmp_path):
    s=f.settings;b=s.capture.host.config;now=datetime.now(timezone.utc)
    pin=lambda name:hashlib.sha256((certificates/name).read_bytes()).hexdigest()
    cert=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes())
    profile=MeetingQueuePeerProfileV1(schema_version=1,purpose='meeting-ingress-queue-peer-v1',meeting_id=s.capture.config.meeting_id,queue_config_sha256=s.sha256,queue_admission_sha256=s.capture.config.admission_sha256,
        intake_config_sha256=s.capture.host.config_sha256,intake_appointment_sha256=s.capture.host.appointment_sha256,principal_id=b.principal_id,workspace_id=b.workspace_id,runtime_hash=b.runtime_hash,registry_hash=b.registry_hash,
        client_uri=WORKER,client_certificate_sha256=hashlib.sha256(cert.public_bytes(Encoding.DER)).hexdigest(),listen_host='127.0.0.1',listen_port=0,server_hostname='localhost',
        server_certificate_file=str(certificates/'server.pem'),server_certificate_sha256=pin('server.pem'),server_key_file=str(certificates/'server.key'),server_key_sha256=pin('server.key'),client_ca_file=str(certificates/'ca.pem'),client_ca_sha256=pin('ca.pem'),
        issuer_actor=s.capture.host.expected_issuer_actor,reviewer_actor=s.capture.host.expected_reviewer_actor,valid_from=now-timedelta(seconds=1),expires_at=min(s.config.expires_at,b.expires_at,b.original_horizon),original_horizon=b.original_horizon)
    raw=canonical_bytes(profile.model_dump(mode='json'));path=tmp_path/'queue-peer';path.write_bytes(raw);path.chmod(0o600)
    return protected_meeting_queue_server_v1(s,path,hashlib.sha256(raw).hexdigest())

def request(server,certificates,q,identity='worker'):
    ctx=ssl.create_default_context(cafile=str(certificates/'ca.pem'));ctx.verify_flags|=ssl.VERIFY_X509_STRICT
    ctx.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
    body=canonical_bytes(q);wire=b'POST /v1/replacement/meetings/queue HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: '+str(len(body)).encode()+b'\r\n\r\n'+body
    with socket.create_connection(('127.0.0.1',server.server_port),timeout=3) as tcp:
        with ctx.wrap_socket(tcp,server_hostname='localhost') as tls:
            tls.settimeout(3);tls.sendall(wire);parts=[]
            while True:
                part=tls.recv(65536)
                if not part:break
                parts.append(part)
    header,data=b''.join(parts).split(b'\r\n\r\n',1);status=int(header.split(b' ')[1])
    if status==200:assert b'Connection: close' in header and len(data)<=4096
    else:assert status==503 and data==b''
    return status,json.loads(data) if data else None,data

def test_actual_queue_mtls_once_SQL_private_capability_wire_and_no_task_claim(queue,certificates,tmp_path):
    x,f,event,_own,_row=queue;server=server_for(f,certificates,tmp_path)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
    q=dict(schema_version=1,operation='pending',ingress_event_id=None,claim_id=None,request_sha256=None,raw_wire_hex=None,error=None,
        caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=25)).isoformat().replace('+00:00','Z'))
    try:
        assert request(server,certificates,q,identity='other')[0]==503
        assert request(server,certificates,q|dict(actor_id=str(x['owner'])))[0]==503
        with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_enqueue_claims_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
        assert request(server,certificates,q)[1]['ingress_event_id']==str(event)
        q=q|dict(operation='claim',ingress_event_id=str(event));status,first,_=request(server,certificates,q)
        assert status==200 and first['fresh_claim'] and first['body']['payload']=={'ingress_event_id':str(event)}
        assert request(server,certificates,q)[1]['state']=='UNKNOWN'
        q=q|dict(operation='current',claim_id=first['claim_id'],request_sha256=first['request_sha256'])
        assert request(server,certificates,q)[1]['state']=='inflight'
        raw=wire().replace(b'Connection: close\r\n',b'Connection: close\r\nx-trigger-jwt: invented-run-capability-not-authority\r\n')
        q=q|dict(operation='observe',raw_wire_hex=raw.hex());status,result,public=request(server,certificates,q)
        assert status==200 and result['state']=='observed' and not result['fresh_claim'] and result['body'] is None
        assert result['qualification'] is False and result['task_completed_proven'] is False and result['remote_stop_proven'] is False
        assert b'invented-run-capability' not in public and b'x-trigger-jwt' not in public and b'raw_wire' not in public
        assert request(server,certificates,q)[1]['state']=='observed'
        assert request(server,certificates,q|dict(operation='current',raw_wire_hex=None))[0]==503
        path=__import__('pathlib').Path(f.settings.capture.host.config.storage_root)/'meeting-queue'/str(x['workspace'])/str(x['meeting'])/str(event)/first['claim_id']/'trigger-response.wire'
        assert path.read_bytes()==raw and path.stat().st_mode&0o777==0o600
        with admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.meeting_capture_enqueue_receipts_v1 r JOIN oracle2.meeting_capture_enqueue_claims_v1 q USING(claim_id) WHERE q.workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
        (tmp_path/'actual-queue-response.json').write_bytes(public)
    finally:
        server.shutdown();server.server_close();thread.join(2);assert not thread.is_alive() and not server._active
