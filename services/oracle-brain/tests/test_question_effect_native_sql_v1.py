"""Actual SQL024 + existing native/central Budget, invented recording wire only.

The SQL017/022 ACK is synthetic contract evidence; this suite does not claim
actual paid graph/semantic qualification or actual SDK vector serving.
"""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from uuid import uuid4,UUID
import hashlib,json,time
from pathlib import Path
from urllib.parse import urlsplit
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from oracle_brain.operating_model.question_effects_v1 import ProtectedQuestionEffectsV1,QuestionEffectConfigV1
from oracle_brain.operating_model.question_cost_settlement_v1 import OriginalQuestionCostScopeV1,ProtectedQuestionCostSettlementV1
from oracle_brain.operating_model.native_factory import NativeBrokerEgress,LedgerRegistry,QualifiedQueryEmbeddingDispatchJobV1
from oracle_brain.operating_model.provider_adapter import Budget,AdmittedAllocationLimitV2
from oracle_brain.operating_model.key_coverage import VerifiedKeyCoverage
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval
from test_question_effects_sql_v1 import question_case,sql_qualified_v3,claim_for,job_for,input_for
from test_protected_raw_original_factory_sql import actual_factory_ledger as _canonical_actual_factory_ledger
from test_question_effect_pricing_v1 import scenario
from test_purpose_transport import bound_tls,certificates,SERVER
from test_hosting_boundary import WORKER
KEY='invented-question-only-key';FP=hashlib.sha256(KEY.encode()).hexdigest()

def save(path,value):
 raw=value if type(value) is bytes else canonical_bytes(value.model_dump(mode='json') if hasattr(value,'model_dump') else value)
 path.write_bytes(raw);path.chmod(0o600)
 return ProtectedInputV1(path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest())

@pytest.fixture
def actual_factory_ledger(admin_url,tmp_path,monkeypatch):
 # Every case remains a separate invented account installation/universe. The
 # SAME canonical owner binds its fresh UUID receipt; outer receipt never
 # authorizes another target, no migration replay or cost-row reset.
 import os
 from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
 from dev.oracle2.test_canonical_schema import owned_phase_database
 container=os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER']
 keys=('ORACLE2_TEST_ADMIN_URL','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT','ORACLE2_TEST_CANONICAL_SCHEMA_RECEIPT_SHA256')
 original={key:os.environ.get(key) for key in keys};database=None
 directory=tmp_path/'question-cost-phase';directory.mkdir(mode=0o700)
 try:
  with owned_phase_database(admin_url,container,directory) as environment:
   target=environment['ORACLE2_TEST_ADMIN_URL'];database=psycopg.conninfo.conninfo_to_dict(target)['dbname']
   with monkeypatch.context() as current:
    for key in keys:current.setenv(key,environment[key])
    owned_worker_database(container,target)
    try:yield from _canonical_actual_factory_ledger.__wrapped__(target)
    finally:owned_worker_database(container,target)
 finally:
  owned_worker_database(container,admin_url)
  assert all(os.environ.get(key)==value for key,value in original.items())
  if database is not None:
   with psycopg.connect(admin_url) as connection:
    assert connection.execute('SELECT datname FROM pg_database WHERE datname=%s',(database,)).fetchall()==[]
   (tmp_path/'question-cost-phase-cleanup.json').write_bytes(canonical_bytes(dict(database=database,absent=True,outer_environment_restored=True)))


@pytest.fixture
def native_question(question_case,actual_factory_ledger,tmp_path,monkeypatch,request):
 x=question_case
 if x['needs_graph']:request.getfixturevalue('question_graph')
 url,role,cluster,namespace=actual_factory_ledger;parts=psycopg.conninfo.conninfo_to_dict(url)
 url=psycopg.conninfo.make_conninfo(url,hostaddr=parts['host'])
 until=min(x['f']['expiry'],datetime.now(timezone.utc)+timedelta(minutes=4))
 registry=LedgerRegistry(key_fingerprint=FP,host=parts['host'],port=int(parts['port']),database=parts['dbname'],role=role,cluster_identifier=cluster,namespace_hash=namespace,transport='verify-full-tls',transport_receipt_hash='a'*64,dedicated_single_key=True,issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=until)
 rh=digest(registry.model_dump(mode='json'));synthesis=getattr(request,'param',None)=='factory-synthesis'
 if synthesis:
  from test_conversation_text_pricing_v1 import scenario as text_scenario
  from oracle_brain.operating_model.provider_adapter import QualifiedAnswerTextPricingV1
  from oracle_brain.operating_model.raw_endpoint_inventory_v1 import synthesis_text_policy_hash_v1
  models,endpoints,original,b,_=text_scenario(key=FP,ledger=rh,input_tokens=80000)
  q=QualifiedAnswerTextPricingV1.model_validate_json(canonical_bytes(original.model_dump(mode='json')|{'quote_schema':'qualified-answer-synthesis-text-pricing-v1','pricing_policy_sha256':synthesis_text_policy_hash_v1()}))
 else:models,endpoints,q,b,_=scenario()
 q=q.model_copy(update=dict(account='key-sha256:'+FP,key_fingerprint=FP,ledger_registry_hash=rh,expires_at=until))
 b=b.model_copy(update=dict(account=q.account,key_fingerprint=FP,ledger_registry_hash=rh,terms_hash=q.terms_hash,expires_at=until))
 purpose='qualified-answer-synthesis-v1' if synthesis else 'qualified-query-embedding-v1';admission=uuid4();batch=uuid4();issuer,reviewer=x['row']['issuer_actor'],x['row']['reviewer_actor']
 processing=ProcessingRequest(provider='openrouter',account=q.account,endpoint='https://openrouter.ai/api/v1',data_classes=frozenset({'synthetic'}),purpose=purpose,terms_hash=q.terms_hash)
 approvals=(ProcessingApproval(**processing.model_dump(),expires_at=until,register_ref='invented-installed-query-only'),)
 scope=OriginalQuestionCostScopeV1(admission_id=admission,workspace_id=x['f']['workspace'],worker_principal_id=x['worker']['actor'],effect_purpose=purpose,account=q.account,key_fingerprint=FP,ledger_registry_hash=rh,terms_hash=q.terms_hash,allocation_batch=batch,allocation_hash='8'*64,issuer_actor=issuer,reviewer_actor=reviewer,valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=until,original_horizon=until)
 c=QuestionEffectConfigV1(admission_id=admission,workspace_id=x['f']['workspace'],worker_principal_id=x['worker']['actor'],enduser_principal_id=x['employee']['actor'],thread_id=UUID(x['snapshot']['thread_id']),model_id=x['m'].artifact_id,worker_history_admission=x['worker']['aid'],effect_purpose=purpose,issuer_actor=issuer,reviewer_actor=reviewer,database_url=save(tmp_path/'url',x['authority'].url.encode()),database_ca=ProtectedInputV1(path=x['authority'].binding.ca_path,sha256=x['authority'].binding.ca_sha256),billing_bounds=save(tmp_path/'billing',b),pricing=save(tmp_path/'pricing',q),approvals=save(tmp_path/'approvals',[a.model_dump(mode='json') for a in approvals]),cost_settlement=save(tmp_path/'cost',scope),processing_request=processing,source_export_scope=tuple(__import__('oracle_brain.operating_model.source_receipts',fromlist=['SourceRef']).SourceRef.model_validate_json(canonical_bytes(r)) for r in input_for(x)['source_refs']),original_horizon=until,expires_at=until,catalog=x['row']['catalog'].obj)
 pin=save(tmp_path/'config',c);row=dict(x['row']);row.update(admission_id=admission,effect_purpose=purpose,provider_model=q.model,allocation_ceiling_usd='.5' if synthesis else '.25',config_sha256=pin.sha256,account=q.account,key_fingerprint=FP,ledger_registry_hash=rh,terms_hash=q.terms_hash,register_hash=q.admitted_register_hash,billing_bounds_sha256=c.billing_bounds.sha256,pricing_sha256=c.pricing.sha256,approval_packet_sha256=c.approvals.sha256,source_export_scope_sha256=digest({'source_refs':[r.model_dump(mode='json') for r in c.source_export_scope]}),allocation_batch=batch,cost_settlement_sha256=c.cost_settlement.sha256,cost_settlement_expires_at=until,expires_at=until,original_horizon=until)
 with psycopg.connect(x['admin']) as connection:
  connection.execute(sql.SQL('INSERT INTO oracle2.question_effect_admissions_v1 ({}) VALUES ({})').format(sql.SQL(',').join(map(sql.Identifier,row)),sql.SQL(',').join(sql.Placeholder() for _ in row)),tuple(row.values()))
  owner=connection.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(x['f']['root'],)).fetchone()[0]
  if synthesis:
   for leaf in ['question-effect-thread:'+str(c.thread_id)+':'+purpose,*[purpose+':'+str(r.source_id) for r in c.source_export_scope]]:
    connection.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),c.workspace_id,c.worker_principal_id,leaf,owner,x['f']['root'],until))
  connection.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),c.workspace_id,c.worker_principal_id,'question-effect-cost-settlement:'+str(admission),owner,x['f']['root'],until))
 x['admission']=admission;x['pricing']=q.model_dump(mode='json');x['approvals']=[a.model_dump(mode='json') for a in approvals]
 root=tmp_path/'native';root.mkdir(mode=0o700)
 allocation=AdmittedAllocationLimitV2(batch_id=batch,allocation_hash='8'*64,original_receipt_hash='9'*64,ceiling_usd=Decimal('.5' if synthesis else '.25'),expires_at=until)
 def unavailable(*_):raise AssertionError('new purpose must not borrow generic job/authority/validator')
 coverage=lambda:VerifiedKeyCoverage(admission_hash='e'*64,key_fingerprint=FP,ledger_identity_hash=rh,observed_at=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=until)
 broker=NativeBrokerEgress(api_key=KEY,ledger_url=url,registry=registry,trusted_registry_hash=rh,coverage_receipt=coverage,trusted_coverage_hash='e'*64,resolve_job=unavailable,authorize_current_job=unavailable,validate_response=unavailable,private_receipts=root,admitted_allocation=allocation)
 state=dict(calls=[],post_hook=None,models=models,endpoints=endpoints,wire=dict(object='list',model=q.model,data=[dict(object='embedding',index=0,embedding=[1.]+[0.]*255)],usage=dict(prompt_tokens=10,total_tokens=10,cost='.00005',is_byok=False,cost_details=dict(upstream_inference_cost='0'))))
 class Response:
  status=200
  def __init__(self,target,raw):self.target=target;self.raw=raw;self.length=len(raw)
  def __enter__(self):return self
  def __exit__(self,*_):pass
  def geturl(self):return self.target
  def getheader(self,name):return str(self.length) if name=='Content-Length' else None
  def read(self,limit=-1):raw=self.raw[:limit] if limit>=0 else self.raw;self.raw=self.raw[len(raw):];return raw
 class Opener:
  def open(self,request,timeout):
   path=urlsplit(request.full_url).path.removeprefix('/api/v1');state['calls'].append(path)
   if path in ('/embeddings/models','/models'):data=state['models']
   elif path=='/models/'+q.model+'/endpoints':data=state['endpoints']
   elif path=='/key':data=dict(data=dict(is_management_key=False,is_provisioning_key=False,usage_daily='0',byok_usage_daily='0',usage_monthly='0',byok_usage_monthly='0',limit='25',limit_remaining='25',is_free_tier=False))
   elif path in('/embeddings','/chat/completions'):
    with psycopg.connect(url) as connection:assert connection.execute("SELECT pg_try_advisory_xact_lock(hashtext('oracle-operating-budget'))").fetchone()==(True,)
    if state['post_hook']:state['post_hook']()
    if synthesis:
     payload=json.loads(request.data);requirements=json.loads(payload['messages'][-1]['content'])
     content=dict(schema_version=1,protocol='qualified-answer-synthesis-output-v1',factual_groups=[dict(schema_version=1,**group) for group in requirements['required_groups']],gap_codes=requirements['required_gap_codes'],unverified_interpretation=None)
     data=dict(model=q.model,choices=[dict(finish_reason='stop',message=dict(role='assistant',content=canonical_bytes(content).decode()))],usage=dict(prompt_tokens=10,completion_tokens=20,total_tokens=30,cost='.00005',is_byok=False,cost_details=dict(upstream_inference_cost='0')))
    else:data=state['wire']
   else:raise AssertionError('unadmitted native path')
   return Response(request.full_url,canonical_bytes(data))
 monkeypatch.setattr('urllib.request.build_opener',lambda *_:Opener())
 with _request_fence_v1(time.monotonic()+40):
  control=ProtectedQuestionEffectsV1(x['authority'],pin,expected_issuer_actor=issuer,expected_reviewer_actor=reviewer)
  context=input_for(x);raw=job_for(x,context);raw.update(processing_request=processing.model_dump(mode='json'),approvals=x['approvals'],pricing=q.model_dump(mode='json'),input_tokens_upper_bound=q.input_tokens_upper_bound,permission_hash=digest({'processing_request':processing.model_dump(mode='json'),'approvals':x['approvals'],'admission_id':str(admission),'source_export_scope_sha256':row['source_export_scope_sha256']}))
  job=None if synthesis else QualifiedQueryEmbeddingDispatchJobV1.model_validate_json(canonical_bytes(raw));deadline=datetime.now(timezone.utc)+timedelta(seconds=30);control._active_deadline=deadline
  if getattr(request,'param',None) not in('factory','factory-synthesis'):control.claim_v1(job.employee_event_id,job,deadline=deadline)
  yield x,control,job,broker,state,url

def dispatch(control,job,broker):return broker.dispatch(canonical_bytes(dict(dispatch_id=str(job.dispatch_id),request_hash=job.request_hash,request=job.request)),_question_control=control,_question_job=job)

def test_actual_question_native_once_budget_custody_and_settled_readback(native_question):
 x,control,job,broker,state,url=native_question
 raw=dispatch(control,job,broker)
 receipt=control.read_effect_receipt_v1(job,broker)
 assert receipt['raw']==raw and receipt['settled_response_sha256']==hashlib.sha256(raw).hexdigest()
 assert state['calls'].count('/embeddings')==1
 with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):dispatch(control,job,broker)
 assert state['calls'].count('/embeddings')==1
 with psycopg.connect(url) as connection:
  assert connection.execute('SELECT s.status,s.actual_usd FROM oracle2.operating_dispatch_receipts s JOIN oracle2.operating_dispatch_reservations r USING(reservation_id) WHERE r.artifact_id=%s',(job.artifact_id,)).fetchone()==('completed',Decimal('.00005'))

def test_actual_question_wire_revocation_failed_settlement_restart_blocks_legacy_and_no_resend(native_question,monkeypatch):
 x,control,job,broker,state,url=native_question
 real_finish=Budget.finish
 def revoke():
  with psycopg.connect(x['admin']) as connection:connection.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope LIKE 'source-read:%%'",(x['f']['workspace'],x['employee']['actor']))
 state['post_hook']=revoke
 def lost_finish(*_,**__):raise PermissionError('invented unavailable original settlement window')
 monkeypatch.setattr(Budget,'finish',lost_finish)
 with pytest.raises(PermissionError):dispatch(control,job,broker)
 monkeypatch.setattr(Budget,'finish',real_finish)
 assert state['calls'].count('/embeddings')==1 and (broker._receipts/(str(job.dispatch_id)+'.wire')).exists()
 with pytest.raises(PermissionError,match='unsettled question liability'):
  Budget(url).reserve(workspace_id=job.workspace_id,artifact_id=uuid4(),batch_id=uuid4(),purpose='source-census',attempt=1,maximum=Decimal('.001'),pricing_hash='f'*64)
 with pytest.raises(psycopg.errors.InsufficientPrivilege):control.read_effect_receipt_v1(job,broker)
 # New process-shaped financial owner uses original independently installed
 # cost scope; it cannot read source/job or dispatch, and performs no POST.
 with _request_fence_v1(time.monotonic()+25):
  finance=ProtectedQuestionCostSettlementV1(x['authority'],control.pin,expected_issuer_actor=control.expected_issuer_actor,expected_reviewer_actor=control.expected_reviewer_actor)
  result=finance.reconcile_unknown_v1(job.dispatch_id,broker,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
  assert result['state']=='unknown' and result['dispatch_allowed'] is False
  finance.reconcile_unknown_v1(job.dispatch_id,broker,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
  with pytest.raises(PermissionError):finance.status_v1(job.dispatch_id,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 with psycopg.connect(url) as connection:
  row=connection.execute('SELECT r.reserved_usd,s.actual_usd,s.response_hash,s.failure_kind FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.artifact_id=%s',(job.artifact_id,)).fetchone()
  assert row[1]>=max(row[0],Decimal('.00005')) and row[2:]==(None,'transport_failure')
 assert state['calls'].count('/embeddings')==1
 with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):dispatch(control,job,broker)
 assert state['calls'].count('/embeddings')==1

@pytest.mark.parametrize('route',[True,None])
def test_actual_question_unknown_route_retains_maximum_and_never_serves_or_retries(native_question,route):
 x,control,job,broker,state,url=native_question
 if route is None:state['wire']['usage'].pop('is_byok')
 else:state['wire']['usage']['is_byok']=route
 with pytest.raises(RuntimeError):dispatch(control,job,broker)
 with psycopg.connect(url) as connection:
  row=connection.execute('SELECT r.reserved_usd,s.actual_usd,s.response_hash,s.failure_kind FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.artifact_id=%s',(job.artifact_id,)).fetchone()
  assert row[1]>=row[0] and row[2:]==(None,'transport_failure')
 assert state['calls'].count('/embeddings')==1
 with pytest.raises(PermissionError):dispatch(control,job,broker)
 assert state['calls'].count('/embeddings')==1

def test_actual_question_known_invalid_vector_keeps_known_cost_and_no_answer(native_question):
 x,control,job,broker,state,url=native_question;state['wire']['data'][0]['embedding']=[1.]
 with pytest.raises(ValueError):dispatch(control,job,broker)
 with psycopg.connect(url) as connection:
  row=connection.execute('SELECT s.status,s.actual_usd,s.failure_kind FROM oracle2.operating_dispatch_receipts s JOIN oracle2.operating_dispatch_reservations r USING(reservation_id) WHERE r.artifact_id=%s',(job.artifact_id,)).fetchone()
  assert row==('failed',Decimal('.00005'),'invalid_output')
 with pytest.raises(PermissionError):control.read_effect_receipt_v1(job,broker)
 assert state['calls'].count('/embeddings')==1

def test_actual_question_upstream_overrun_is_not_capped_or_double_added(native_question):
 x,control,job,broker,state,url=native_question
 state['wire']['usage'].update(is_byok=True,cost='.01',cost_details=dict(upstream_inference_cost='.02'))
 with pytest.raises(RuntimeError):dispatch(control,job,broker)
 with psycopg.connect(url) as connection:
  row=connection.execute('SELECT s.status,s.actual_usd,s.response_hash FROM oracle2.operating_dispatch_receipts s JOIN oracle2.operating_dispatch_reservations r USING(reservation_id) WHERE r.artifact_id=%s',(job.artifact_id,)).fetchone()
  assert row==('overrun',Decimal('.03'),None)
 assert state['calls'].count('/embeddings')==1

def test_actual_question_changed_metadata_denies_before_reservation_or_POST(native_question):
 x,control,job,broker,state,url=native_question;state['endpoints']['data']['endpoints'][0]['pricing']['request']='1'
 with pytest.raises(PermissionError):dispatch(control,job,broker)
 assert '/embeddings' not in state['calls']
 with psycopg.connect(url) as connection:assert connection.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations WHERE artifact_id=%s',(job.artifact_id,)).fetchone()==(0,)


@pytest.fixture
def question_graph(question_case,bound_tls,certificates,tmp_path):
 """Existing actual SDK owners, invented ingestion vectors, real retained ACK."""
 import os,asyncio
 from dataclasses import replace
 from urllib.parse import urlunsplit
 from graphrag_sdk import ConnectionConfig
 from oracle_brain.operating_model.sdk_projection import PaidConsolidationSDKProjectionV1
 from oracle_brain.operating_model.paid_sdk_embeddings_v3 import PaidProjectionEmbedderV3,verify_paid_sdk_embedding_v3
 from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
 from oracle_brain.operating_model.projection_delivery import signature
 from dev.oracle2.test_readonly_graph_fixture import processing_writer,processing_reader_scope,owned_target
 from dev.oracle2.test_graph_tls_fixture import owned_graph_tls,verify_graph_tls_peer
 from test_paid_sdk_embeddings_v3 import paid_case_for
 from test_consolidation_sql_v1 import RUNTIME,REGISTRY
 x=question_case;state=x['state'];m=x['m'];payload=state['q']['payload'];f=x['f']
 old=x['authority'];x['authority']=ConsolidationAuthorityV1(old.url,binding=replace(old.binding,retained_semantic_admissions=state['q']['trusted_admission_hashes']),delivery_capability_body_hashes=old.delivery_capability_body_hashes)
 graph=os.environ['ORACLE2_OPERATING_TEST_GRAPH_URL'];container=os.environ['COMPOSE_PROJECT_NAME']+'-falkor-candidate-1';owned_target(container,graph)
 generation=uuid4();name=f'oracle_processing_v1_{m.workspace_id.hex}_{m.artifact_id.hex}_{m.version}_{generation.hex}';tls,_=bound_tls
 def config(url):return ConnectionConfig.from_url(url,graph_name=name,ssl=True,ssl_check_hostname=True,ssl_cert_reqs='required',ssl_ca_certs=str(certificates/'ca.pem'),ssl_certfile=str(certificates/'worker.pem'),ssl_keyfile=str(certificates/'worker.key'),query_timeout_ms=3000,retry_count=1,pool_timeout=1)
 with processing_writer(container,graph,tmp_path/'graph-writer',workspace_id=m.workspace_id,artifact_id=m.artifact_id,version=m.version,generation=generation) as writer:
  with owned_graph_tls(container,graph,server_context=tls,expected_client_uri=WORKER) as port:
   verify_graph_tls_peer(port,ca_file=certificates/'ca.pem',certificate_file=certificates/'worker.pem',key_file=certificates/'worker.key',expected_server_uri=SERVER)
   def tls_url(url):
    parsed=urlsplit(url);return urlunsplit(('rediss',parsed.netloc.rsplit('@',1)[0]+'@localhost:'+str(port),'','',''))
   writable=tls_url(writer.environment['ORACLE2_TEST_PROCESSING_WRITER_GRAPH_URL'])
   def projection():return PaidConsolidationSDKProjectionV1(writable,workspace_id=m.workspace_id,artifact_id=m.artifact_id,artifact_version=m.version,generation=generation,embedder=PaidProjectionEmbedderV3(verify_paid_sdk_embedding_v3(**paid_case_for(payload,m))),qualification_guard=state['guard'],connection_config=config(writable))
   async def build():
    p=projection()
    try:return await p.build(state['ledger'],m.workspace_id,m.artifact_id,m.version)
    finally:await p.close()
   built=asyncio.run(build())
   with psycopg.connect(f['url']) as c:
    c.execute("SET LOCAL statement_timeout='5s'");lease=c.execute('SELECT oracle2.lease_processing_projection(%s,%s,%s,30)',(m.workspace_id,RUNTIME,REGISTRY)).fetchone()[0]
   body=dict(schema_version=3,event_id=lease['event_id'],workspace_id=str(m.workspace_id),artifact_id=str(m.artifact_id),version=m.version,content_hash=m.content_hash,source_digest=m.source_digest,permission_digest=m.permission_digest,graph_name=name,record_digest=built['record_digest'],sdk_version='1.4.0',projector_id='invented-query-wire-real-SDK-SQL-proof',lease_role=f['login'],lease_token=lease['lease_token'],lease_attempt=lease['attempts'],lease_until=lease['lease_until'],projection_schema=built['projection_schema'],projection_digest=built['projection_digest'],embedding_protocol='paid-sdk-embedding-v3',**{k:v for k,v in built['paid_embedding'].items() if k not in('schema_version','embedding_protocol')})
   secret=b'invented-query-vector-graph-signature';seal=signature(secret,body)
   with psycopg.connect(f['url']) as c:
    c.execute("SET LOCAL statement_timeout='5s'");assert c.execute('SELECT oracle2.ack_processing_projection(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(lease['event_id'],m.workspace_id,lease['lease_token'],lease['attempts'],Jsonb(body),seal,RUNTIME,REGISTRY,datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]['receipt']==body
   def actual_delivery(event):
    value=state['source'].projection_receipt_v3(m.workspace_id,m.artifact_id,m.version);assert str(value.receipt.event_id)==str(event)
    return value.receipt.model_dump(mode='json')|{'signature':value.signature}
   with processing_reader_scope(container,graph,tmp_path/'graph-reader',receipt=body|{'signature':seal},secret=secret,current_delivery=actual_delivery) as reader:
    readonly=tls_url(reader['ORACLE2_TEST_PROCESSING_READONLY_GRAPH_URL'])
    x['graph']=dict(url=readonly,config=config(readonly),generation=generation,writer=projection,payload=payload)
    yield x['graph']

@pytest.mark.parametrize('question_case',[True],indirect=True)
def test_actual_once_query_native_receipt_to_readonly_SDK_vector_union_and_denial(native_question):
 import asyncio
 from oracle_brain.operating_model.sdk_projection import ConsolidatedMetadataSDKProjectionV1
 from oracle_brain.operating_model.artifact_storage import FileBlobStore
 x,owner,job,broker,state,url=native_question;g=x['graph'];dispatch(owner,job,broker)
 async def exercise():
  projection=ConsolidatedMetadataSDKProjectionV1(g['url'],authority=owner.authority,blobs=FileBlobStore(x['state']['blobs'].root),model_id=job.qualified_model_id,version=job.model_version,generation=g['generation'],connection_config=g['config'],deadline=owner._active_deadline)
  try:
   await projection.load()
   answer=await projection.answer_with_question_vector_v1(owner,job.dispatch_id,broker=broker)
   assert answer.query_embedding_used is True and answer.provider_generation_used is False and answer.records
   assert answer.model_content_hash==job.model_content_hash and answer.coverage.entire_company_verified is False
   with pytest.raises(Exception):await projection.connection.query('CREATE (:Forbidden)')
   writable=g['writer']()
   try:await writable.connection.query("MATCH (e:__Entity__) SET e.embedding=vecf32([1.0])")
   finally:await writable.close()
   with pytest.raises((PermissionError,ValueError)):await projection.answer_with_question_vector_v1(owner,job.dispatch_id,broker=broker)
   with psycopg.connect(x['admin']) as c:c.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE actor_id=%s AND workspace_id=%s AND scope LIKE 'source-read:%%'",(x['employee']['actor'],job.workspace_id))
   with pytest.raises(psycopg.errors.InsufficientPrivilege):await projection.answer_with_question_vector_v1(owner,job.dispatch_id,broker=broker)
  finally:await projection.close()
 asyncio.run(exercise());assert state['calls'].count('/embeddings')==1


@pytest.mark.parametrize('question_case',['interview-graph'],indirect=True)
@pytest.mark.parametrize('native_question',['factory','factory-synthesis'],indirect=True)
def test_actual_SQL019_to_optional_conversation_factory_owned_loop_query_answer_no_extra_question(native_question,tmp_path,certificates,monkeypatch):
 from dataclasses import replace
 from oracle_brain.operating_model.consolidation_authority_v1 import ConsolidationAuthorityV1
 from oracle_brain.hosting.question_effect_factory_v1 import ProtectedQuestionEffectFactoryV1
 from oracle_brain.hosting.conversation_answer_v1 import ConversationAnswerV1
 from test_connected_answer_service_v1 import install_answer
 x,worker,_,broker,state,url=native_question;g=x['graph']
 employee=x['employee_authority'];employee=ConsolidationAuthorityV1(employee.url,binding=replace(employee.binding,retained_semantic_admissions=x['state']['q']['trusted_admission_hashes']),delivery_capability_body_hashes=employee.delivery_capability_body_hashes)
 recipient=install_answer(x['state'],employee,x['employee'],g['url'],g['generation'],certificates,tmp_path/'employee-answer')
 worker_settings=install_answer(x['state'],worker.authority,x['worker'],g['url'],g['generation'],certificates,tmp_path/'worker-answer')
 effect=ProtectedQuestionEffectFactoryV1(worker_settings,worker,broker)
 original_respond=ProtectedQuestionEffectFactoryV1.respond_v1
 async def positive(factory,*args):
  try:return await original_respond(factory,*args)
  except Exception as error:
   from oracle_brain.hosting.question_effect_factory_v1 import QuestionEffectUnknown
   if isinstance(error,QuestionEffectUnknown):raise
   raise AssertionError('actual installed positive effect refused: '+type(error).__name__+': '+str(error)) from error
 monkeypatch.setattr(ProtectedQuestionEffectFactoryV1,'respond_v1',positive)
 presenter=ConversationAnswerV1(x['control'],recipient,effects=effect)
 try:
  before=x['control'].snapshot_v1(UUID(x['snapshot']['thread_id']))
  shown=presenter.present_turn_v1(before,x['event']['turn_id'])
  (tmp_path/'actual-question-effect-response.json').write_bytes(canonical_bytes(shown));(tmp_path/'actual-question-effect-response.json').chmod(0o600)
  actual=shown['qualified_effect']
  assert actual['state']=='observed' and actual['answer']['records']
  synthesis=worker.config.effect_purpose=='qualified-answer-synthesis-v1'
  assert actual['answer']['query_embedding_used'] is (not synthesis) and actual['answer']['provider_generation_used'] is synthesis
  if synthesis:assert actual['synthesis']['interpretation'] is None and actual['synthesis']['semantic_entailment_verified'] is False
  assert shown['qualified_answer'] is None and shown['company_policy_confirmed'] is False
  assert shown['question_id']==before['pending_question_id'] and shown['question_count']==before['question_count']==1
  after=x['control'].snapshot_v1(UUID(before['thread_id']))
  assert after['revision']==before['revision'] and after['recap']==before['recap'] and after['pending_question_id']==before['pending_question_id']
  paid='/chat/completions' if synthesis else '/embeddings'
  assert state['calls'].count(paid)==1
  # Same actual committed event cannot create a new native identity on redisplay.
  again=presenter.present_turn_v1(after,x['event']['turn_id'])
  (tmp_path/'actual-question-effect-unknown.json').write_bytes(canonical_bytes(again));(tmp_path/'actual-question-effect-unknown.json').chmod(0o600)
  assert again['qualified_effect']['state']=='unknown' and again['qualified_answer'] is None
  assert state['calls'].count(paid)==1 and again['question_count']==1 and again['question_id']==before['pending_question_id']
 finally:presenter.close()
 assert not presenter.owned.thread.is_alive() and not presenter.effect_owned.thread.is_alive()

def test_actual_question_expired_original_fence_retains_wire_unsettled_blocks_spend_and_financial_only_reconciles(native_question):
 from oracle_brain.operating_model.request_deadline_v1 import _request_end_v1
 x,owner,job,broker,state,url=native_question;tokens=[]
 def expire():tokens.append(_request_end_v1.set(float(time.monotonic()-1)))
 state['post_hook']=expire
 try:
  with pytest.raises(PermissionError):dispatch(owner,job,broker)
 finally:
  for token in reversed(tokens):_request_end_v1.reset(token)
 with psycopg.connect(url) as c:
  assert c.execute('SELECT count(*) FROM oracle2.operating_dispatch_receipts s JOIN oracle2.operating_dispatch_reservations r USING(reservation_id) WHERE r.artifact_id=%s',(job.artifact_id,)).fetchone()==(0,)
  assert c.execute('SELECT count(*) FROM oracle2.operating_dispatch_reservations WHERE artifact_id=%s',(job.artifact_id,)).fetchone()==(1,)
 assert (broker._receipts/(str(job.dispatch_id)+'.wire')).exists() and (broker._receipts/(str(job.dispatch_id)+'.json')).exists()
 with pytest.raises(PermissionError,match='unsettled question liability'):Budget(url).reserve(workspace_id=job.workspace_id,artifact_id=uuid4(),batch_id=uuid4(),purpose='source-census',attempt=1,maximum=Decimal('.001'),pricing_hash='f'*64)
 with _request_fence_v1(float(time.monotonic()+25)):
  financial=ProtectedQuestionCostSettlementV1(owner.authority,owner.pin,expected_issuer_actor=owner.expected_issuer_actor,expected_reviewer_actor=owner.expected_reviewer_actor)
  assert financial.reconcile_unknown_v1(job.dispatch_id,broker,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))['state']=='unknown'
 assert state['calls'].count('/embeddings')==1
 with pytest.raises(PermissionError):dispatch(owner,job,broker)
 assert state['calls'].count('/embeddings')==1
