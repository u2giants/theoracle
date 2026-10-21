"""Actual new protected mTLS purpose→same canonical owned SQL store."""
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
from pathlib import Path
import hashlib,json,shutil,threading,subprocess
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.conversation_service_v1 import protected_conversation_server_v1,ConversationPeerProfileV1
from test_hosting_boundary import certificates,WORKER
from test_durable_interview_sql import conversation
from test_replacement_request_service_v1 import send

@contextmanager
def listener(x,tmp_path,certificates,*,browser=False):
 s=x['control'].settings;c=s.config;folder=tmp_path/'conversation-tls';folder.mkdir(mode=0o700)
 def pin(name):
  p=folder/name;shutil.copyfile(certificates/name,p);p.chmod(0o600);return str(p),hashlib.sha256(p.read_bytes()).hexdigest()
 cert,ch=pin('server.pem');key,kh=pin('server.key');ca,ah=pin('ca.pem')
 if browser:
  ext=folder/'browser-server.ext';ext.write_text('subjectAltName=DNS:localhost,DNS:localhost.localdomain\nextendedKeyUsage=serverAuth\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer')
  subprocess.run(['openssl','x509','-req','-in',str(certificates/'server.csr'),'-CA',str(certificates/'ca.pem'),'-CAkey',str(certificates/'ca.key'),'-CAcreateserial','-out',cert,'-days','1','-extfile',str(ext)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  ch=hashlib.sha256(Path(cert).read_bytes()).hexdigest()
 der=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(Encoding.DER)
 now=datetime.now(timezone.utc);body=dict(schema_version=1,purpose='employee-conversation-peer-v1',conversation_config_sha256=s.config_sha256,
 conversation_appointment_sha256=s.appointment_sha256,principal_id=str(c.principal_id),workspace_id=str(c.workspace_id),runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,
 client_uri=WORKER,client_certificate_sha256=hashlib.sha256(der).hexdigest(),listen_host='::1' if browser else '127.0.0.1',listen_port=0,server_hostname='localhost.localdomain' if browser else 'localhost',
 server_certificate_file=cert,server_certificate_sha256=ch,server_key_file=key,server_key_sha256=kh,client_ca_file=ca,client_ca_sha256=ah,
 issuer_actor=str(s.expected_issuer_actor),reviewer_actor=str(s.expected_reviewer_actor),valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=(now+timedelta(seconds=25)).isoformat(),original_horizon=c.original_horizon.isoformat())
 value=ConversationPeerProfileV1.model_validate_json(json.dumps(body));raw=canonical_bytes(value.model_dump(mode='json'));path=tmp_path/'conversation-peer';path.write_bytes(raw);path.chmod(0o600)
 server=protected_conversation_server_v1(s,path,hashlib.sha256(raw).hexdigest());thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});thread.start()
 try:yield server
 finally:
  server.shutdown();server.server_close();thread.join(2)
  assert not thread.is_alive() and not server._active and server.socket.fileno()==-1

def request(server,certificates,q):return send(server,certificates,canonical_bytes(q),path='/v1/employee/conversation')
def creation():
 from uuid import uuid4
 return dict(schema_version=1,command_id=str(uuid4()),caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat(),mode='interview',topic='Invented assembly',language='zh-Hans')

def test_actual_mutual_tls_create_original_pause_and_restart_readback(conversation,tmp_path,certificates):
 from uuid import uuid4
 x=conversation
 with listener(x,tmp_path,certificates) as server:
  q=creation();status,raw,_=request(server,certificates,q);assert status==200
  s=json.loads(raw);assert s['question']=='Please describe one recent example of this work.'
  q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat(),thread_id=s['thread_id'],expected_revision=1,operation='employee_turn',turn_id=str(uuid4()),text='不允许未经复核就发货。',language='zh-Hans')
  status,raw,_=request(server,certificates,q);assert status==200;s=json.loads(raw);assert s['events'][-1]['original_text']==q['text']
  observe=dict(schema_version=1,operation='snapshot',thread_id=s['thread_id'],caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat())
  assert json.loads(request(server,certificates,observe)[1])['revision']==2
 # Fresh listener/control instance reads same actual SQL history.
 second=tmp_path/'restarted';second.mkdir(mode=0o700)
 with listener(x,second,certificates) as server:
  observed=json.loads(request(server,certificates,observe)[1]);assert observed['events'][-1]['original_text']==q['text'] and observed['question_count']==2

@pytest.mark.parametrize('attack',['caller-role','duplicate','foreign-path','wrong-peer','old-purpose'])
def test_actual_conversation_tls_cannot_expand_own_purpose(conversation,tmp_path,certificates,attack):
 with listener(conversation,tmp_path,certificates) as server:
  q=creation();data=canonical_bytes(q);path='/v1/employee/conversation';identity='worker'
  if attack=='caller-role':q['role']='assistant';data=canonical_bytes(q)
  if attack=='duplicate':data=data[:-1]+b',"mode":"ordinary"}'
  if attack=='foreign-path':path+='?actor=foreign'
  if attack=='wrong-peer':identity='other'
  if attack=='old-purpose':path='/v1/replacement/control'
  assert (certificates/(identity+'.pem')).is_file()
  status,raw,_=send(server,certificates,data,path=path,identity=identity)
  assert status in (200,404,503)
  if status==200:assert json.loads(raw)['state']=='DENIED'
  else:assert raw==b''

from test_replacement_source_intake_sql import requester

def test_delayed_body_and_utc_rollback_cannot_renew_original_fence_or_write_sql(conversation,tmp_path,certificates,monkeypatch):
 from types import SimpleNamespace
 from oracle_brain.hosting import _protected_control_listener_v1 as owner
 from test_replacement_requester_sql import owned_admin
 import time
 x=conversation;tick=[time.monotonic()];wall=[datetime.now(timezone.utc)]
 class Clock(datetime):
  @classmethod
  def now(cls,tz=None):return wall[0]
 original=owner.read_request_body_v1
 def delayed(*a,**kw):
  raw=original(*a,**kw);tick[0]+=31;wall[0]-=timedelta(hours=1);return raw
 with listener(x,tmp_path,certificates) as server:
  monkeypatch.setattr(owner,'time',SimpleNamespace(monotonic=lambda:tick[0]))
  monkeypatch.setattr(owner,'datetime',Clock)
  monkeypatch.setattr(owner,'read_request_body_v1',delayed)
  status,raw,_=request(server,certificates,creation())
  assert status==503 and raw==b''
 with owned_admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.conversation_threads_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)


def test_expired_request_context_prevents_actual_next_sql_effect(conversation,monkeypatch):
 from oracle_brain.hosting import _protected_control_listener_v1 as owner
 from test_replacement_requester_sql import owned_admin
 from types import SimpleNamespace
 import time
 x=conversation;end=time.monotonic()+1;tick=[end-1]
 monkeypatch.setattr(owner,'time',SimpleNamespace(monotonic=lambda:tick[0]))
 with owner._request_fence_v1(float(end)):
  tick[0]=end
  with pytest.raises(PermissionError):x['control'].execute_v1(canonical_bytes(creation()))
 with owned_admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.conversation_threads_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(0,)
