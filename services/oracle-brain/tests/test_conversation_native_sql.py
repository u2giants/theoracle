"""Actual worker/thread SQL + same real Budget; only provider wire invented.

Recording opener exercises actual fixed native transport and custody. This never
contacts a provider, authenticates an employee, or installs production admission.
"""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4,UUID
import copy,json,hashlib
import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.native_factory import NativeBrokerEgress,EmployeeConversationDispatchJobV1,LedgerRegistry
from oracle_brain.operating_model.key_coverage import VerifiedKeyCoverage
from oracle_brain.operating_model.provider_adapter import AdmittedAllocationLimitV2
from oracle_brain.provider_policy import ProcessingRequest,ProcessingApproval
from oracle_brain.hosting.conversation_control_v1 import ConversationControlV1,load_conversation_settings_v1,ConversationUnknown
from oracle_brain.hosting.conversation_native_v1 import ProtectedConversationFactoryV1,conversation_request_v1
from oracle_brain.hosting.original_intake_v1 import ProtectedInputV1
from test_conversation_processing_sql import processing_worker
from test_durable_interview_sql import conversation,command
from test_replacement_source_intake_sql import requester
from test_replacement_requester_sql import owned_admin
from test_protected_raw_original_factory_sql import actual_factory_ledger
from test_conversation_text_pricing_v1 import scenario
KEY='invented-conversation-only-key';FP=hashlib.sha256(KEY.encode()).hexdigest()

def save(path,value):
 raw=canonical_bytes(value.model_dump(mode='json'));path.write_bytes(raw);path.chmod(0o600)
 return ProtectedInputV1(path=str(path),sha256=hashlib.sha256(raw).hexdigest())

@pytest.fixture
def native_conversation(processing_worker,actual_factory_ledger,tmp_path,monkeypatch):
 x=processing_worker;url,role,cluster,namespace=actual_factory_ledger;parts=psycopg.conninfo.conninfo_to_dict(url)
 registry=LedgerRegistry(key_fingerprint=FP,host=parts['host'],port=int(parts['port']),database=parts['dbname'],role=role,cluster_identifier=cluster,namespace_hash=namespace,transport='verify-full-tls',transport_receipt_hash='a'*64,dedicated_single_key=True,issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=x['until'])
 rh=digest(registry.model_dump(mode='json'));m,e,q,b,_=scenario(key=FP,ledger=rh,input_tokens=12000)
 q=q.model_copy(update={'expires_at':x['until']});b=b.model_copy(update={'expires_at':x['until']})
 s=x['snapshot'];event=s['events'][-1];dispatch=x['worker_config'].dispatch_id
 processing=ProcessingRequest(provider='openrouter',account='key-sha256:'+FP,endpoint='https://openrouter.ai/api/v1',data_classes=frozenset({'synthetic'}),purpose='employee-conversation',terms_hash=q.terms_hash)
 approval=ProcessingApproval(**processing.model_dump(),expires_at=x['until'],register_ref='invented-independent-conversation-processing-only')
 j=EmployeeConversationDispatchJobV1(dispatch_id=dispatch,artifact_id=dispatch,workspace_id=x['workspace'],batch_id=uuid4(),purpose='employee-conversation',attempt=1,request={},request_hash=digest({}),permission_hash='f'*64,processing_request=processing,approvals=(approval,),pricing=q,register_hash=q.admitted_register_hash,input_tokens_upper_bound=q.input_tokens_upper_bound,thread_id=UUID(s['thread_id']),thread_revision=s['revision'],employee_event_id=UUID(event['event_id']),original_sha256=event['original_sha256'],billing_bounds_sha256=digest(b.model_dump(mode='json')),pending_question_id=UUID(s['pending_question_id']) if s['pending_question_id'] else None,qualified_population=(),qualified_population_sha256=digest({'source_refs':[]}))
 body=conversation_request_v1(s,j,qualified_readings=());j=j.model_copy(update={'request':body,'request_hash':digest(body)})
 config=x['control'].settings.config.model_copy(update={'response_job':save(tmp_path/'conversation-job',j),'billing_bounds':save(tmp_path/'conversation-billing',b),'processing_config':x['worker_pin']})
 old=x['control'].settings;cp=save(old.config_path,config);appt=old.appointment.model_copy(update={'config_sha256':cp.sha256});ap=save(old.appointment_path,appt)
 control=ConversationControlV1(load_conversation_settings_v1(old.config_path,cp.sha256,old.appointment_path,ap.sha256,old.expected_issuer_actor,old.expected_reviewer_actor))
 root=tmp_path/'conversation-private';root.mkdir(mode=0o700)
 def authorize_job(candidate):
  # Actual current SQL worker/thread/admission, not callback=True fixture authority.
  if candidate!=j:return False
  return x['worker'].current_for_job_v1(candidate).dispatch_id==j.dispatch_id
 coverage=lambda:VerifiedKeyCoverage(admission_hash='e'*64,key_fingerprint=FP,ledger_identity_hash=rh,observed_at=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=x['until'])
 allocation=AdmittedAllocationLimitV2(batch_id=j.batch_id,allocation_hash='a'*64,original_receipt_hash='b'*64,ceiling_usd=Decimal('.5'),expires_at=x['until'])
 broker=NativeBrokerEgress(api_key=KEY,ledger_url=url,registry=registry,trusted_registry_hash=rh,coverage_receipt=coverage,trusted_coverage_hash='e'*64,resolve_job=lambda identity:j if identity==j.dispatch_id else None,authorize_current_job=authorize_job,validate_response=lambda job,content:json.loads(content),private_receipts=root,admitted_allocation=allocation)
 state=dict(calls=[],models=m,endpoints=e,wire=dict(model=j.pricing.model,choices=[dict(finish_reason='stop',message=dict(role='assistant',content='{"display_text":"Qualified evidence is missing."}'))],usage=dict(cost='.003',is_byok=False,cost_details={'upstream_inference_cost':'0'})),post_hook=None,metadata_hook=None)
 class Response:
  status=200
  def __init__(self,target,raw):self.target=target;self.raw=raw
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def geturl(self):return self.target
  def getheader(self,name):return str(len(self.raw)) if name=='Content-Length' else None
  def read(self,n=-1):return self.raw if n<0 else self.raw[:n]
 class Opener:
  def open(self,request,timeout):
   target=request.full_url;path=target.removeprefix('https://openrouter.ai/api/v1');state['calls'].append(path)
   assert request.get_header('Authorization')=='Bearer '+KEY and timeout==60
   if path=='/models':
    if state['metadata_hook']:state['metadata_hook']()
    data=state['models']
   elif path.endswith('/endpoints'):data=state['endpoints']
   elif path=='/key':data={'data':{'usage_daily':'0','byok_usage_daily':'0','usage_monthly':'0','byok_usage_monthly':'0','limit':'25','limit_remaining':'25','is_free_tier':False}}
   elif path=='/chat/completions':
    with psycopg.connect(url) as c:assert c.execute("SELECT pg_try_advisory_xact_lock(hashtext('oracle-operating-budget'))").fetchone()==(True,)
    with psycopg.connect(url) as c:assert c.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s))",('oracle2-authz:'+str(x['workspace']),)).fetchone()==(True,)
    if state['post_hook']:state['post_hook']()
    data=state['wire']
   else:raise AssertionError('unadmitted native path')
   return Response(target,canonical_bytes(data))
 monkeypatch.setattr('urllib.request.build_opener',lambda *a:Opener())
 return x|dict(control=control,factory=ProtectedConversationFactoryV1(control,broker),job=j,native_state=state,broker=broker,ledger_url=url)

def settlement(x):
 with psycopg.connect(x['ledger_url']) as c:
  return c.execute('SELECT r.reserved_usd,s.actual_usd,s.status,s.response_hash,s.failure_kind FROM oracle2.operating_dispatch_reservations r JOIN oracle2.operating_dispatch_receipts s USING(reservation_id) WHERE r.artifact_id=%s',(x['job'].artifact_id,)).fetchall()

def test_actual_worker_native_wire_central_budget_display_only_and_no_resend(native_conversation):
 x=native_conversation;s=x['factory'].respond_v1(x['job'].thread_id)
 assert s['events'][-1]['origin']=='display' and s['events'][-1]['payload']['display_text']=='Qualified evidence is missing.'
 assert s['source_qualified'] is False and s['company_policy_confirmed'] is False
 assert settlement(x)[0][1:3]==(Decimal('.003000'),'completed')
 with pytest.raises((PermissionError,ConversationUnknown)):x['factory'].respond_v1(x['job'].thread_id)
 assert x['native_state']['calls'].count('/chat/completions')==1

@pytest.mark.parametrize('drift',['endpoint','request','cache','context','upstream'])
def test_changed_current_quote_or_route_refuses_before_any_paid_post(native_conversation,drift):
 x=native_conversation;state=x['native_state']
 if drift=='endpoint':state['endpoints']['data']['endpoints'][0]['tag']='foreign'
 elif drift=='request':state['endpoints']['data']['endpoints'][0]['pricing']['request']='1'
 elif drift=='cache':state['endpoints']['data']['endpoints'][0]['pricing']['input_cache_write']='.001'
 elif drift=='context':state['endpoints']['data']['endpoints'][0]['context_length']=1000
 else:Path(x['control'].settings.config.billing_bounds.path).write_bytes(b'{}')
 with pytest.raises((PermissionError,ConversationUnknown)):x['factory'].respond_v1(x['job'].thread_id)
 assert '/chat/completions' not in state['calls'] and settlement(x)==[]



def test_metadata_change_after_reservation_cannot_reach_paid_post(native_conversation):
 x=native_conversation;state=x['native_state'];count=[0]
 def change():
  count[0]+=1
  if count[0]==2:state['endpoints']['data']['endpoints'][0]['pricing']['request']='1'
 state['metadata_hook']=change
 with pytest.raises(ConversationUnknown):x['factory'].respond_v1(x['job'].thread_id)
 assert '/chat/completions' not in state['calls']
 row=settlement(x)[0];assert row[0]==row[1] and row[2]=='failed' and row[3] is None


def test_actual_native_assistant_display_is_excluded_from_employee_original_registration(native_conversation):
 from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1
 from oracle_brain.workflows.interview import InterviewWorkflowV1
 x=native_conversation;s=x['factory'].respond_v1(x['job'].thread_id);event=s['events'][-1]
 assert event['origin']=='display'
 with pytest.raises(PermissionError):
  InterviewWorkflowV1(x['control']).register_original_v1(x['job'].thread_id,UUID(event['event_id']),OriginalIntakeFactoryV1(x['intake_settings']))
 assert x['native_state']['calls'].count('/chat/completions')==1

@pytest.mark.parametrize('drift',['route','missing-route','authority','metadata','content','upstream-overrun'])
def test_paid_wire_failure_retains_real_receipt_liability_and_never_resends(native_conversation,drift):
 x=native_conversation;state=x['native_state']
 if drift=='route':state['wire']['usage']['is_byok']=True
 elif drift=='missing-route':state['wire']['usage'].pop('is_byok')
 elif drift=='upstream-overrun':state['wire']['usage']['cost_details']['upstream_inference_cost']='2'
 elif drift=='authority':
  def revoke():
   with owned_admin(x) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['worker_leaf'],))
  state['post_hook']=revoke
 elif drift=='metadata':state['post_hook']=lambda:state['endpoints']['data']['endpoints'][0]['pricing'].update(request='1')
 else:state['wire']['choices'][0]['message']['content']='{"display_text":false}'
 with pytest.raises(ConversationUnknown):x['factory'].respond_v1(x['job'].thread_id)
 row=settlement(x)[0]
 if drift=='content':assert row[1]==Decimal('.003') and row[2]=='failed' and row[4]=='invalid_output'
 else:assert row[1]>=row[0] and row[3] is None and row[4]=='transport_failure'
 if drift=='upstream-overrun':assert row[1]==Decimal('2.003') and row[2]=='overrun'
 assert (x['broker']._receipts/(str(x['job'].dispatch_id)+'.wire')).is_file()
 with pytest.raises((PermissionError,ConversationUnknown)):x['factory'].respond_v1(x['job'].thread_id)
 assert state['calls'].count('/chat/completions')==1
