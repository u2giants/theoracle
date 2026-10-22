"""Strict source transport/settings helpers; actual composed SQL/graph test imports."""
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import hashlib,json,ssl,http.client,threading
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.connected_answer_settings_v1 import ConnectedAnswerConfigV1,ConnectedIndustryAnswerConfigV1,ConnectedAnswerPeerV1,ConnectedAnswerSettingsV1
from oracle_brain.hosting.connected_answer_service_v1 import AnswerRequestV1,parse_answer_request_v1,protected_connected_answer_server_v1
from oracle_brain.workflows.answer import AnswerQueryV1
from test_hosting_boundary import WORKER
from test_purpose_transport import SERVER

def install_answer(state,authority,h,readonly,generation,certificates,directory,*,channel='web',peer_certificate=None,peer_key=None,peer_uri=WORKER,server_certificate=None,listen_host='127.0.0.1',actors=None,industry_readers=()):
 directory.mkdir(mode=0o700)
 def protected(name,raw):
  path=directory/name;path.write_bytes(raw);path.chmod(0o600)
  return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())
 def certificate(name):return protected(name,(certificates/name).read_bytes())
 values=asdict(authority.binding);values['retained_semantic_admissions']=tuple(sorted(authority.binding.retained_semantic_admissions))
 values['database_url']=protected('database-url',h['url'].encode());values['delivery_capability_body_hashes']=authority.delivery_capability_body_hashes
 root=state['blobs'].root;root.chmod(0o700);info=root.stat();end=authority.binding.original_horizon
 ca=certificate('ca.pem');worker=certificate('worker.pem');worker_key=certificate('worker.key');server=protected('server.pem',(server_certificate or certificates/'server.pem').read_bytes());server_key=certificate('server.key')
 cls=ConnectedIndustryAnswerConfigV1 if industry_readers else ConnectedAnswerConfigV1
 c=cls.model_validate(dict(principal_id=h['actor'],workspace_id=state['f']['workspace'],model_id=state['manifest'].artifact_id,
  history=values,projections=(dict(version=state['manifest'].version,generation=generation,graph_url=protected('graph-url',readonly.encode())),),
  graph_ca=ca,graph_certificate=worker,graph_key=worker_key,graph_client_uri=WORKER,graph_server_uri=SERVER,**({'industry_readers':industry_readers} if industry_readers else {}),
  storage_root=str(root),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid,storage_profile_hash='a'*64,original_horizon=end,expires_at=end))
 config=protected('answer-config.json',canonical_bytes(c.model_dump(mode='json')));issuer,reviewer=actors or (uuid4(),uuid4())
 p=ConnectedAnswerPeerV1.model_validate(dict(config_sha256=config['sha256'],principal_id=c.principal_id,workspace_id=c.workspace_id,model_id=c.model_id,history_appointment_id=h['aid'],channel=channel,issuer_actor=issuer,reviewer_actor=reviewer,
  client_certificate_sha256=hashlib.sha256(x509.load_pem_x509_certificate((peer_certificate or certificates/'worker.pem').read_bytes()).public_bytes(serialization.Encoding.DER)).hexdigest(),client_uri=peer_uri,client_ca=ca,server_certificate=server,server_key=server_key,listen_host=listen_host,listen_port=0,
  valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=end,original_horizon=end))
 peer=protected('answer-peer.json',canonical_bytes(p.model_dump(mode='json')))
 return ConnectedAnswerSettingsV1.load(config_path=config['path'],config_sha256=config['sha256'],peer_path=peer['path'],peer_sha256=peer['sha256'],expected_issuer_actor=issuer,expected_reviewer_actor=reviewer)

def tls_request(server,certificates,raw,*,client='worker',path='/v1/employee/answer'):
 context=ssl.create_default_context(cafile=str(certificates/'ca.pem'));context.load_cert_chain(str(certificates/(client+'.pem')),str(certificates/(client+'.key')))
 conn=http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=30)
 try:
  conn.request('POST',path,body=raw,headers={'Content-Type':'application/json','Connection':'close'})
  response=conn.getresponse();return response.status,response.read()
 finally:conn.close()

@pytest.mark.parametrize('raw',[b'{}',b'{"schema_version":true}',b'{"schema_version":1,"schema_version":1}',b'{"schema_version":1,"query":{"question":"x","actor":"spoof"}}'])
def test_closed_answer_wire_refuses_missing_coerced_duplicate_or_supplied_authority(raw):
 with pytest.raises(ValueError):parse_answer_request_v1(raw)

def test_canonical_answer_wire_preserves_question_exactly():
 q=AnswerQueryV1(question='不允许未经复核就发货。仅限样品。')
 value=AnswerRequestV1(caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=15),query=q)
 raw=canonical_bytes(value.model_dump(mode='json'))
 assert parse_answer_request_v1(raw)==value
 with pytest.raises(ValueError):parse_answer_request_v1(raw+b' ')


def test_canonical_browser_millisecond_deadline_and_historical_query_are_exact_input():
 q=AnswerQueryV1(question='reported_step',mode='historical',valid_at=datetime.now(timezone.utc),known_at=datetime.now(timezone.utc))
 raw=value=AnswerRequestV1(caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=15),query=q).model_dump(mode='json')
 raw['caller_deadline']='2026-10-21T20:00:00.123Z'
 raw['query']['valid_at']='2026-10-20T20:00:00.123Z';raw['query']['known_at']='2026-10-20T20:00:00.123Z'
 encoded=canonical_bytes(raw);parsed=parse_answer_request_v1(encoded)
 assert parsed.caller_deadline.microsecond==123000 and parsed.query.known_at.microsecond==123000
 # Input canonical JSON bytes remain exact; typed date normalization is not a
 # substitute hash of caller input, nor a protected-record authorization seal.
 assert json.loads(encoded)['query']['known_at']=='2026-10-20T20:00:00.123Z'
