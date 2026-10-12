"""Real owned Postgres preflight; all provider responses are invented locally."""
import hashlib
import json
import os
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.key_coverage import VerifiedKeyCoverage
from oracle_brain.operating_model.native_factory import LedgerRegistry,NativeDispatchJob,NativeBrokerEgress,ledger_namespace_hash,verify_ledger
from oracle_brain.operating_model.native_provider import NativeOpenRouter,current_pricing
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval

KEY='invented-factory-key'
FP=hashlib.sha256(KEY.encode()).hexdigest()
MODELS={'data':[{'id':'openai/gpt-6.1-sol','context_length':8192,'pricing':{'prompt':'0.0000001','completion':'0.0000001'},'top_provider':{'max_completion_tokens':8192,'context_length':8192}}]}

@pytest.fixture
def actual_ledger():
 base=psycopg.conninfo.conninfo_to_dict(os.environ['ORACLE2_TEST_ADMIN_URL'])
 if base.get('host') not in {'127.0.0.1','localhost'} or not base.get('dbname','').startswith('oracle_operating_model_test_'):
  raise PermissionError('exact owned synthetic Postgres required')
 base['dbname']='postgres';name='oracle_operating_model_test_factory_'+uuid4().hex[:12];role='oracle_billing_'+uuid4().hex[:12]
 role_password=uuid4().hex
 with psycopg.connect(**base,autocommit=True) as conn:
  conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
  conn.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role),sql.Literal(role_password)))
 admin=psycopg.conninfo.make_conninfo(**{**base,'dbname':name})
 try:
  with psycopg.connect(admin) as conn:
   for migration in ('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql'):
    conn.execute((Path(__file__).parents[1]/'sql'/migration).read_text())
   conn.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(role)))
   conn.execute(sql.SQL('GRANT SELECT,INSERT ON oracle2.operating_dispatch_reservations,oracle2.operating_dispatch_receipts,oracle2.operating_dispatch_diagnoses TO {}').format(sql.Identifier(role)))
   conn.execute(sql.SQL('GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO {}').format(sql.Identifier(role)))
   cluster=conn.execute('SELECT system_identifier::text FROM pg_catalog.pg_control_system()').fetchone()[0]
   namespace=ledger_namespace_hash(conn)
  url=psycopg.conninfo.make_conninfo(**{**base,'dbname':name,'user':role,'password':role_password})
  registry=LedgerRegistry(key_fingerprint=FP,host=base['host'],port=int(base.get('port','5432')),database=name,role=role,
   cluster_identifier=cluster,namespace_hash=namespace,transport='owned-synthetic-loopback',transport_receipt_hash='a'*64,
   dedicated_single_key=True,issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=datetime.now(timezone.utc)+timedelta(hours=1))
  yield url,registry,admin
 finally:
  with psycopg.connect(**base,autocommit=True) as conn:
   conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s',(name,))
   conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
   conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))

def job():
 now=datetime.now(timezone.utc)
 request={'model':'openai/gpt-6.1-sol','messages':[{'role':'user','content':'invented fixture only'}],
  'max_tokens':100,'response_format':{'type':'json_object'},'store':False,'stream':False,
  'provider':{'only':['openai'],'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'}}
 processing=ProcessingRequest(provider='openrouter',account='key-sha256:'+FP,endpoint='https://openrouter.ai/api/v1',
  data_classes=frozenset({'synthetic'}),purpose='source-extraction',terms_hash='b'*64)
 approval=ProcessingApproval(**processing.model_dump(),expires_at=now+timedelta(hours=1),register_ref='invented-factory-admission')
 return NativeDispatchJob(dispatch_id=uuid4(),workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose='source-extraction',
  attempt=1,request=request,request_hash=hashlib.sha256(canonical_bytes(request)).hexdigest(),permission_hash='c'*64,
  processing_request=processing,approvals=(approval,),pricing=current_pricing(MODELS,model=request['model'],max_output_tokens=100,register_hash='d'*64,now=now),
  register_hash='d'*64,input_tokens_upper_bound=len(canonical_bytes(request))+1024)

def envelope(j):
 return canonical_bytes({'dispatch_id':str(j.dispatch_id),'request_hash':j.request_hash,'request':j.request})

def broker(actual_ledger,tmp_path,j,*,authorize_current=lambda _:True,validator=lambda job,content:None):
 url,registry,_=actual_ledger;registry_hash=digest(registry.model_dump(mode='json'));now=datetime.now(timezone.utc)
 receipts=tmp_path/'private';receipts.mkdir(mode=0o700)
 proof=VerifiedKeyCoverage(admission_hash='e'*64,key_fingerprint=FP,ledger_identity_hash=registry_hash,observed_at=now,expires_at=now+timedelta(hours=1))
 return NativeBrokerEgress(api_key=KEY,ledger_url=url,registry=registry,trusted_registry_hash=registry_hash,
  coverage_receipt=lambda:proof,trusted_coverage_hash='e'*64,resolve_job=lambda identity:j if identity==j.dispatch_id else None,
  authorize_current_job=authorize_current,validate_response=validator,private_receipts=receipts),receipts

def fake_native(monkeypatch,*,response=None):
 calls=[]
 response=response or {'id':'invented-response','model':'openai/gpt-6.1-sol','choices':[{'finish_reason':'stop','message':{'content':'{"invented":true}'}}], 'usage':{'cost':'0.00001'}}
 def request(self,path,body=None):
  calls.append(path)
  if path=='/models':return MODELS
  if path=='/key':return {'data':{'usage_daily':'0','byok_usage_daily':'0','usage_monthly':'0','byok_usage_monthly':'0','limit':25,'limit_remaining':25,'is_free_tier':False}}
  if path=='/chat/completions':self._receive_paid_wire(json.dumps(response).encode(),complete=True);self.last_response_text=json.dumps(response);return response
  raise AssertionError('unadmitted path')
 monkeypatch.setattr(NativeOpenRouter,'_request',request)
 return calls

def test_preflight_verifies_actual_least_privileged_db_and_namespace(actual_ledger):
 url,registry,_=actual_ledger
 assert verify_ledger(url,registry,trusted_registry_hash=digest(registry.model_dump(mode='json')),key_fingerprint=FP,now=datetime.now(timezone.utc))==digest(registry.model_dump(mode='json'))

@pytest.mark.parametrize('field,value',[('database','wrong-database'),('role','wrong-role'),('cluster_identifier','123'),('namespace_hash','f'*64),('key_fingerprint','f'*64)])
def test_actual_identity_or_registry_drift_denies(actual_ledger,field,value):
 url,registry,_=actual_ledger;changed=registry.model_copy(update={field:value})
 with pytest.raises(PermissionError):verify_ledger(url,changed,trusted_registry_hash=digest(changed.model_dump(mode='json')),key_fingerprint=FP,now=datetime.now(timezone.utc))

def test_production_never_accepts_plain_loopback_pg(actual_ledger):
 url,registry,_=actual_ledger;changed=registry.model_copy(update={'transport':'verify-full-tls'});url=psycopg.conninfo.make_conninfo(url,sslmode='disable')
 with pytest.raises((PermissionError,psycopg.OperationalError)):verify_ledger(url,changed,trusted_registry_hash=digest(changed.model_dump(mode='json')),key_fingerprint=FP,now=datetime.now(timezone.utc))

@pytest.mark.parametrize('privilege',['CREATEROLE','private-table-select','billing-update'])
def test_actual_role_privilege_drift_denies(actual_ledger,privilege):
 url,registry,admin=actual_ledger
 with psycopg.connect(admin) as conn:
  if privilege=='CREATEROLE':conn.execute(sql.SQL('ALTER ROLE {} CREATEROLE').format(sql.Identifier(registry.role)))
  elif privilege=='private-table-select':conn.execute(sql.SQL('GRANT SELECT ON oracle2.artifact_manifests TO {}').format(sql.Identifier(registry.role)))
  else:conn.execute(sql.SQL('GRANT UPDATE ON oracle2.operating_dispatch_reservations TO {}').format(sql.Identifier(registry.role)))
 with pytest.raises(PermissionError):verify_ledger(url,registry,trusted_registry_hash=digest(registry.model_dump(mode='json')),key_fingerprint=FP,now=datetime.now(timezone.utc))

def test_broker_reserves_sends_settles_actual_wire_and_denies_replay(actual_ledger,tmp_path,monkeypatch):
 j=job();b,receipts=broker(actual_ledger,tmp_path,j);calls=fake_native(monkeypatch)
 raw=b.dispatch(envelope(j));assert json.loads(raw)['id']=='invented-response'
 assert calls.count('/chat/completions')==1
 with psycopg.connect(actual_ledger[2]) as conn:
  assert conn.execute('SELECT actual_usd,status FROM oracle2.operating_dispatch_receipts').fetchall()==[(Decimal('0.000010'),'completed')]
 assert json.loads((receipts/(str(j.dispatch_id)+'.json')).read_text())['raw_response']==raw.decode()
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls.count('/chat/completions')==1

def test_substitution_or_revoked_admission_denies_before_any_provider_read(actual_ledger,tmp_path,monkeypatch):
 j=job();b,_=broker(actual_ledger,tmp_path,j);calls=fake_native(monkeypatch)
 forged=json.loads(envelope(j));forged['request']['messages'][0]['content']='substituted';forged['request_hash']=hashlib.sha256(canonical_bytes(forged['request'])).hexdigest()
 with pytest.raises(PermissionError):b.dispatch(canonical_bytes(forged))
 j.approvals[0].expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls==[]

def test_revocation_after_paid_call_retains_cost_and_raw_but_returns_no_data(actual_ledger,tmp_path,monkeypatch):
 j=job();checks=[]
 def authorize_now(_):checks.append(True);return len(checks)<4
 b,receipts=broker(actual_ledger,tmp_path,j,authorize_current=authorize_now);calls=fake_native(monkeypatch)
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls.count('/chat/completions')==1
 assert json.loads((receipts/(str(j.dispatch_id)+'.json')).read_text())['raw_response']
 with psycopg.connect(actual_ledger[2]) as conn:assert conn.execute('SELECT count(*) FROM oracle2.operating_dispatch_receipts').fetchone()[0]==1

def test_unknown_transport_failure_holds_full_reservation(actual_ledger,tmp_path,monkeypatch):
 j=job();b,receipts=broker(actual_ledger,tmp_path,j);original=fake_native(monkeypatch)
 fake=NativeOpenRouter._request
 def fail(self,path,body=None):
  if path=='/chat/completions':raise RuntimeError('invented unknown transport failure')
  return fake(self,path,body)
 monkeypatch.setattr(NativeOpenRouter,'_request',fail)
 with pytest.raises(RuntimeError):b.dispatch(envelope(j))
 with psycopg.connect(actual_ledger[2]) as conn:
  maximum,actual,status,kind=conn.execute('SELECT r.reserved_usd,s.actual_usd,s.status,s.failure_kind FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchone()
 assert maximum==actual and status=='failed' and kind=='transport_failure'
 assert json.loads((receipts/(str(j.dispatch_id)+'.json')).read_text())['failed'] is True

def test_authority_callback_cannot_mutate_sealed_request(actual_ledger,tmp_path,monkeypatch):
 j=job()
 def mutate(pinned):pinned.request['messages'][0]['content']='forged';return True
 b,_=broker(actual_ledger,tmp_path,j,authorize_current=mutate);calls=fake_native(monkeypatch)
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls==[]

def test_permission_revoked_during_free_reads_stops_private_post(actual_ledger,tmp_path,monkeypatch):
 j=job();checks=[]
 def authorize_now(_):checks.append(True);return len(checks)<3
 b,receipts=broker(actual_ledger,tmp_path,j,authorize_current=authorize_now);calls=fake_native(monkeypatch)
 with pytest.raises(RuntimeError):b.dispatch(envelope(j))
 assert '/chat/completions' not in calls
 assert json.loads((receipts/(str(j.dispatch_id)+'.json')).read_text())['failed'] is True

def test_owned_synthetic_factory_cannot_process_company_originals(actual_ledger,tmp_path,monkeypatch):
 j=job();j.processing_request.data_classes=frozenset({'company-originals'})
 j.approvals[0].data_classes=frozenset({'company-originals'})
 b,_=broker(actual_ledger,tmp_path,j);calls=fake_native(monkeypatch)
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls==[]

def test_actual_model_context_shortfall_denies_before_charge(actual_ledger,tmp_path,monkeypatch):
 j=job();b,_=broker(actual_ledger,tmp_path,j);calls=fake_native(monkeypatch)
 monkeypatch.setitem(MODELS['data'][0]['top_provider'],'context_length',1024)
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls==['/models']
 with psycopg.connect(actual_ledger[2]) as conn:assert conn.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations').fetchone()[0]==0


def test_missing_validator_denies_before_provider_reads(actual_ledger,tmp_path,monkeypatch):
 j=job();calls=fake_native(monkeypatch)
 with pytest.raises(PermissionError):broker(actual_ledger,tmp_path,j,validator=None)
 assert calls==[]

def test_rejected_output_retains_actual_charge_and_wire_without_retry(actual_ledger,tmp_path,monkeypatch):
 j=job()
 def reject(pinned,content):
  assert pinned.dispatch_id==j.dispatch_id and content=='{"invented":true}'
  raise ValueError('invented semantic failure')
 b,receipts=broker(actual_ledger,tmp_path,j,validator=reject);calls=fake_native(monkeypatch)
 with pytest.raises(ValueError):b.dispatch(envelope(j))
 with psycopg.connect(actual_ledger[2]) as conn:
  assert conn.execute('SELECT actual_usd,status,failure_kind FROM oracle2.operating_dispatch_receipts').fetchall()==[(Decimal('0.000010'),'failed','invalid_output')]
 saved=json.loads((receipts/(str(j.dispatch_id)+'.json')).read_text())
 assert saved['failed'] and saved['raw_response']
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls.count('/chat/completions')==1


def embedding_job():
 j=job();request={'model':'openai/text-embedding-3-small','input':['invented vector source'],'dimensions':256,'encoding_format':'float','store':False,
  'provider':{'only':['openai'],'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'}}
 models={'data':[{'id':request['model'],'pricing':{'prompt':'0.00000002'},'context_length':8192}]}
 pricing=current_pricing(models,model=request['model'],max_output_tokens=1,register_hash=j.register_hash,now=datetime.now(timezone.utc))
 j=j.model_copy(update={'request':request,'request_hash':hashlib.sha256(canonical_bytes(request)).hexdigest(),'input_tokens_upper_bound':len(canonical_bytes(request))+1024,'pricing':pricing})
 return j,models

def fake_embedding(monkeypatch,models,response):
 calls=[]
 def request(self,path,body=None):
  calls.append(path)
  if path=='/embeddings/models':return models
  if path=='/key':return {'data':{'usage_daily':0,'byok_usage_daily':0,'usage_monthly':0,'byok_usage_monthly':0,'limit':25,'limit_remaining':25,'is_free_tier':False}}
  if path=='/embeddings':
   assert body['dimensions']==256 and body['store'] is False and body['provider']['only']==['openai']
   self._receive_paid_wire(json.dumps(response).encode(),complete=True);self.last_response_text=json.dumps(response);return response
  raise AssertionError(path)
 monkeypatch.setattr(NativeOpenRouter,'_request',request);return calls

def vector_response():
 return {'model':'openai/text-embedding-3-small','object':'list','data':[{'object':'embedding','index':0,'embedding':[0.25]*256}],'usage':{'cost':'0.00001'}}

def test_embedding_broker_reserves_fixed_native_operation_and_settles(actual_ledger,tmp_path,monkeypatch):
 j,models=embedding_job();response=vector_response();calls=fake_embedding(monkeypatch,models,response);b,_=broker(actual_ledger,tmp_path,j)
 assert json.loads(b.dispatch(envelope(j)))==response
 assert calls.count('/embeddings')==1 and '/chat/completions' not in calls
 with psycopg.connect(actual_ledger[2]) as conn:assert conn.execute('SELECT actual_usd,status FROM oracle2.operating_dispatch_receipts').fetchall()==[(Decimal('0.000010'),'completed')]

@pytest.mark.parametrize('malformation',['dimension','count','index','finite','model','boolean'])
def test_embedding_invalid_vectors_retain_known_charge(actual_ledger,tmp_path,monkeypatch,malformation):
 j,models=embedding_job();response=vector_response()
 if malformation=='dimension':response['data'][0]['embedding'].pop()
 if malformation=='count':response['data']=[]
 if malformation=='index':response['data'][0]['index']=1
 if malformation=='finite':response['data'][0]['embedding'][0]=float('inf')
 if malformation=='model':response['model']='wrong'
 if malformation=='boolean':response['data'][0]['embedding'][0]=True
 calls=fake_embedding(monkeypatch,models,response);b,receipts=broker(actual_ledger,tmp_path,j)
 with pytest.raises(ValueError):b.dispatch(envelope(j))
 with psycopg.connect(actual_ledger[2]) as conn:assert conn.execute('SELECT actual_usd,status,failure_kind FROM oracle2.operating_dispatch_receipts').fetchall()==[(Decimal('0.000010'),'failed','invalid_output')]
 assert json.loads((receipts/(str(j.dispatch_id)+'.json')).read_text())['raw_response']
 assert calls.count('/embeddings')==1


def test_embedding_unknown_transport_holds_entire_reservation(actual_ledger,tmp_path,monkeypatch):
 j,models=embedding_job();fake_embedding(monkeypatch,models,vector_response());original=NativeOpenRouter._request
 def fail(self,path,body=None):
  if path=='/embeddings':raise RuntimeError('invented ambiguous transport')
  return original(self,path,body)
 monkeypatch.setattr(NativeOpenRouter,'_request',fail);b,_=broker(actual_ledger,tmp_path,j)
 with pytest.raises(RuntimeError):b.dispatch(envelope(j))
 with psycopg.connect(actual_ledger[2]) as conn:
  reserved,actual,status=conn.execute('SELECT r.reserved_usd,s.actual_usd,s.status FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchone()
 assert reserved==actual and status=='failed'

def test_embedding_real_decimal_vectors_validated_and_wire_hashed(actual_ledger,tmp_path,monkeypatch):
 j,models=embedding_job();response=vector_response();response['data'][0]['embedding']=[Decimal('.25')]*256
 calls=fake_embedding(monkeypatch,models,vector_response());fake=NativeOpenRouter._request
 def decimals(self,path,body=None):
  result=fake(self,path,body)
  return response if path=='/embeddings' else result
 monkeypatch.setattr(NativeOpenRouter,'_request',decimals);b,_=broker(actual_ledger,tmp_path,j)
 raw=b.dispatch(envelope(j))
 with psycopg.connect(actual_ledger[2]) as conn:
  assert conn.execute('SELECT response_hash FROM oracle2.operating_dispatch_receipts').fetchone()[0]==hashlib.sha256(raw).hexdigest()


def test_embedding_missing_actual_cost_retains_liability(actual_ledger,tmp_path,monkeypatch):
 j,models=embedding_job();response=vector_response();response['usage']={'prompt_tokens':4,'total_tokens':4}
 calls=fake_embedding(monkeypatch,models,response);b,_=broker(actual_ledger,tmp_path,j)
 with pytest.raises(RuntimeError):b.dispatch(envelope(j))
 with psycopg.connect(actual_ledger[2]) as conn:
  reserved,actual,status=conn.execute('SELECT r.reserved_usd,s.actual_usd,s.status FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchone()
 assert reserved==actual and status=='failed' and calls.count('/embeddings')==1


def real_wire_transport(monkeypatch, *, paid_raw, http_error=False, embedding_models=None, incomplete=False):
 import io
 import urllib.request
 import urllib.error
 calls=[]
 class Response:
  def __init__(self,raw,partial=False):self.raw=raw;self.partial=partial
  def read(self,limit):
   if self.partial:
    import http.client
    raise http.client.IncompleteRead(self.raw,1)
   return self.raw[:limit]
  def __enter__(self):return self
  def __exit__(self,*args):pass
 class Opener:
  def open(self,request,timeout):
   path=request.full_url.removeprefix('https://openrouter.ai/api/v1');calls.append(path)
   if path=='/models':return Response(json.dumps(MODELS).encode())
   if path=='/embeddings/models':return Response(json.dumps(embedding_models).encode())
   if path=='/key':return Response(json.dumps({'data':{'usage_daily':0,'byok_usage_daily':0,'usage_monthly':0,'byok_usage_monthly':0,'limit':25,'limit_remaining':25,'is_free_tier':False}}).encode())
   if path in {'/chat/completions','/embeddings'}:
    if http_error:raise urllib.error.HTTPError(request.full_url,500,'synthetic error',{},io.BytesIO(paid_raw))
    return Response(paid_raw,partial=incomplete)
   raise AssertionError(path)
 monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
 return calls

def test_actual_transport_durable_wire_precedes_validation_and_settlement(actual_ledger,tmp_path,monkeypatch):
 from oracle_brain.operating_model.provider_adapter import Budget
 j=job();raw=json.dumps({'model':'openai/gpt-6.1-sol','choices':[{'finish_reason':'stop','message':{'content':'{}'}}],'usage':{'cost':'0.00001'}}).encode()
 b,receipts=broker(actual_ledger,tmp_path,j)
 calls=real_wire_transport(monkeypatch,paid_raw=raw);original=Budget.finish;observed=[]
 def finish(self,*args,**kwargs):
  assert (receipts/(str(j.dispatch_id)+'.wire')).read_bytes()==raw
  metadata=json.loads((receipts/(str(j.dispatch_id)+'.wire.json')).read_bytes())
  assert metadata['complete'] is True and metadata['raw_sha256']==hashlib.sha256(raw).hexdigest()
  assert metadata['reservation_id']==str(args[0]);observed.append(True)
  return original(self,*args,**kwargs)
 monkeypatch.setattr(Budget,'finish',finish)
 assert b.dispatch(envelope(j))==raw and observed==[True]
 assert calls.count('/chat/completions')==1
 assert (receipts/(str(j.dispatch_id)+'.wire')).stat().st_mode & 0o777==0o600
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls.count('/chat/completions')==1

@pytest.mark.parametrize('raw,http_error',[(b'not JSON',False),(b'\xffinvalid UTF8',False),(b'{"error":"synthetic HTTP error"}',True),(b'x'*(16*1024*1024+1),False)],ids=['malformed-json','invalid-utf8','http-error','oversized'])
def test_actual_malformed_error_or_oversize_wire_preserved_with_full_hold(actual_ledger,tmp_path,monkeypatch,raw,http_error):
 j=job();b,receipts=broker(actual_ledger,tmp_path,j);calls=real_wire_transport(monkeypatch,paid_raw=raw,http_error=http_error)
 with pytest.raises(RuntimeError):b.dispatch(envelope(j))
 assert (receipts/(str(j.dispatch_id)+'.wire')).read_bytes()==raw[:16*1024*1024]
 metadata=json.loads((receipts/(str(j.dispatch_id)+'.wire.json')).read_bytes())
 assert metadata['complete']==(len(raw)<=16*1024*1024) and metadata['truncated']==(len(raw)>16*1024*1024)
 with psycopg.connect(actual_ledger[2]) as conn:
  reserved,actual,status=conn.execute('SELECT r.reserved_usd,s.actual_usd,s.status FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchone()
 assert reserved==actual and status=='failed'
 with pytest.raises(PermissionError):b.dispatch(envelope(j))
 assert calls.count('/chat/completions')==1

@pytest.mark.parametrize('failure',['write','fsync'])
def test_wire_custody_failure_holds_unknown_cost(actual_ledger,tmp_path,monkeypatch,failure):
 import os
 j=job();b,receipts=broker(actual_ledger,tmp_path,j);raw=json.dumps({'usage':{'cost':'0.00001'}}).encode();real_wire_transport(monkeypatch,paid_raw=raw)
 if failure=='write':
  original=os.open
  def fail(path,*args,**kwargs):
   if str(path).endswith('.wire'):raise OSError('synthetic disk failure')
   return original(path,*args,**kwargs)
  monkeypatch.setattr(os,'open',fail)
 else:
  original=os.fsync;calls=[]
  def fail(fd):
   calls.append(fd)
   if len(calls)==1:raise OSError('synthetic fsync failure')
   return original(fd)
  monkeypatch.setattr(os,'fsync',fail)
 with pytest.raises(RuntimeError):b.dispatch(envelope(j))
 with psycopg.connect(actual_ledger[2]) as conn:
  reserved,actual,status=conn.execute('SELECT r.reserved_usd,s.actual_usd,s.status FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchone()
 assert reserved==actual and status=='failed'


def test_actual_embedding_wire_persisted_before_known_charge_settlement(actual_ledger,tmp_path,monkeypatch):
 from oracle_brain.operating_model.provider_adapter import Budget
 j,models=embedding_job();raw=json.dumps(vector_response()).encode();b,receipts=broker(actual_ledger,tmp_path,j)
 calls=real_wire_transport(monkeypatch,paid_raw=raw,embedding_models=models);original=Budget.finish
 def finish(self,*args,**kwargs):
  assert (receipts/(str(j.dispatch_id)+'.wire')).read_bytes()==raw
  assert json.loads((receipts/(str(j.dispatch_id)+'.wire.json')).read_bytes())['reservation_id']==str(args[0])
  assert kwargs['actual_usd']==Decimal('.00001')
  return original(self,*args,**kwargs)
 monkeypatch.setattr(Budget,'finish',finish)
 assert b.dispatch(envelope(j))==raw and calls.count('/embeddings')==1

def test_paid_native_operation_requires_custodian_before_network(monkeypatch):
 native=NativeOpenRouter(KEY,coverage_receipt=lambda:None,trusted_coverage_hash='e'*64,ledger_identity_hash='f'*64)
 monkeypatch.setattr(native,'_request',lambda *args,**kw:pytest.fail('network should not be reached'))
 with pytest.raises(PermissionError):native.send(messages=[],model='openai/gpt-6.1-sol',max_output_tokens=1,store=False,extra_body={})
 with pytest.raises(PermissionError):native.embed(input=['synthetic'],model='openai/text-embedding-3-small',dimensions=256,store=False,extra_body={})


def test_interrupted_http_read_retains_partial_wire_without_known_charge(actual_ledger,tmp_path,monkeypatch):
 j=job();b,receipts=broker(actual_ledger,tmp_path,j);raw=b'{"incomplete":'
 real_wire_transport(monkeypatch,paid_raw=raw,incomplete=True)
 with pytest.raises(RuntimeError):b.dispatch(envelope(j))
 assert (receipts/(str(j.dispatch_id)+'.wire')).read_bytes()==raw
 assert json.loads((receipts/(str(j.dispatch_id)+'.wire.json')).read_bytes())['complete'] is False
 with psycopg.connect(actual_ledger[2]) as conn:
  reserved,actual=conn.execute('SELECT r.reserved_usd,s.actual_usd FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id)').fetchone()
 assert reserved==actual


def test_actual_native_ledger_tls_preflight_uses_libpq_and_verified_ca(actual_ledger):
 import os
 ca=os.environ.get('ORACLE2_TEST_TLS_ROOT')
 if not ca:pytest.fail('owned actual TLS fixture CA required')
 url,registry,_=actual_ledger
 url=psycopg.conninfo.make_conninfo(url,sslmode='verify-full',sslrootcert=ca)
 with psycopg.connect(url) as connection:assert connection.pgconn.ssl_in_use is True
 changed=registry.model_copy(update={'transport':'verify-full-tls'})
 identity=digest(changed.model_dump(mode='json'))
 assert verify_ledger(url,changed,trusted_registry_hash=identity,key_fingerprint=FP,now=datetime.now(timezone.utc))==identity
