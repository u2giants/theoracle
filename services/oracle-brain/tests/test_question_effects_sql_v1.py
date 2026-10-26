"""Owned actual SQL024 operational proof. Synthetic jobs are NOT paid authority."""
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
from uuid import uuid4,UUID
import hashlib,time
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.question_effects_v1 import PUBLIC_QUESTION_SIGNATURES_V1,PRIVATE_QUESTION_SIGNATURES_V1
from test_consolidation_sql_v1 import sql_qualified_v3,prepared_qualified_model,RUNTIME,REGISTRY
from test_connected_answer_sql_v1 import own_history,acknowledge
from test_conversation_answer_v1 import installed_conversation

@pytest.fixture
def question_case(admin_url,sql_qualified_v3,tmp_path,request):
 needs_graph=getattr(request,'param',False) in (True,'interview-graph')
 if needs_graph:request.getfixturevalue('bound_tls')
 state=prepared_qualified_model(admin_url,sql_qualified_v3,tmp_path,return_fixture=True);f=state['f'];m=state['manifest']
 if not needs_graph:acknowledge(f,m)
 worker,authority=own_history(admin_url,f);employee,employee_authority=own_history(admin_url,f)
 end=f['expiry'];issuer,reviewer=uuid4(),uuid4()
 settings=SimpleNamespace(config=SimpleNamespace(original_horizon=end,history=SimpleNamespace(runtime_hash=RUNTIME,registry_hash=REGISTRY,ca_path=authority.binding.ca_path,ca_sha256=authority.binding.ca_sha256,expected_owner=authority.binding.expected_owner)),peer=SimpleNamespace(issuer_actor=issuer,reviewer_actor=reviewer))
 control=installed_conversation(admin_url,state,employee,settings,tmp_path/'employee')
 deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
 with _request_fence_v1(time.monotonic()+30):
  thread=control.execute_v1(canonical_bytes(dict(schema_version=1,command_id=str(uuid4()),caller_deadline=deadline.isoformat(),mode='interview' if getattr(request,'param',False)=='interview-graph' else 'ordinary',topic='Invented business question',language='en')))
  snapshot=control.execute_v1(canonical_bytes(dict(schema_version=1,command_id=str(uuid4()),caller_deadline=deadline.isoformat(),thread_id=thread['thread_id'],expected_revision=thread['revision'],operation='employee_turn',turn_id=str(uuid4()),text='What is reported across all processes?',language='en')))
 event=snapshot['recap']['events'][-1];admission=uuid4();purpose='qualified-query-embedding-v1';batch=uuid4();pricing={'model':'openai/text-embedding-3-small','purpose':'invented-SQL-test-no-paid-quote'};approvals=[]
 with psycopg.connect(admin_url) as c:
  c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(worker['login'],RUNTIME,REGISTRY,end))
  owner=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
  for scope in ['question-effect-thread:'+snapshot['thread_id']+':'+purpose,*[purpose+':'+str(ref.source_id) for ref in f['all_refs']]]:
   c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],worker['actor'],scope,owner,f['root'],end))
  catalog={sig:c.execute("SELECT encode(sha256(convert_to(prosrc,'UTF8')),'hex') FROM pg_proc WHERE oid=to_regprocedure(%s)",(sig,)).fetchone()[0] for sig in PUBLIC_QUESTION_SIGNATURES_V1+PRIVATE_QUESTION_SIGNATURES_V1}
  for sig in PUBLIC_QUESTION_SIGNATURES_V1:c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION '+sig+' TO {}').format(sql.Identifier(worker['login'])))
  row=dict(admission_id=admission,role_name=worker['login'],worker_principal_id=worker['actor'],enduser_role=control.settings.config.expected_session_role,enduser_principal_id=employee['actor'],workspace_id=f['workspace'],thread_id=UUID(snapshot['thread_id']),model_id=m.artifact_id,worker_history_admission=worker['aid'],enduser_history_admission=employee['aid'],effect_purpose=purpose,provider_model='openai/text-embedding-3-small',runtime_hash=RUNTIME,registry_hash=REGISTRY,config_sha256='1'*64,catalog=Jsonb(catalog),account='key-sha256:'+'2'*64,key_fingerprint='2'*64,ledger_registry_hash='3'*64,terms_hash='4'*64,register_hash='5'*64,billing_bounds_sha256='6'*64,pricing_sha256=digest(pricing),approval_packet_sha256=digest(approvals),source_export_scope_sha256='7'*64,allocation_batch=batch,allocation_hash='8'*64,allocation_receipt_hash='9'*64,allocation_ceiling_usd='0.25',issuer_actor=issuer,reviewer_actor=reviewer,issued_at=datetime.now(timezone.utc)-timedelta(seconds=1),expires_at=end,original_horizon=end,cost_settlement_sha256='a'*64,cost_settlement_expires_at=end)
  c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['workspace'],worker['actor'],'question-effect-cost-settlement:'+str(admission),owner,f['root'],end))
  c.execute(sql.SQL('INSERT INTO oracle2.question_effect_admissions_v1 ({}) VALUES ({})').format(sql.SQL(',').join(map(sql.Identifier,row)),sql.SQL(',').join(sql.Placeholder() for _ in row)),tuple(row.values()))
 return dict(employee_authority=employee_authority,needs_graph=needs_graph,authority=authority,admin=admin_url,state=state,f=f,m=m,worker=worker,employee=employee,control=control,snapshot=snapshot,event=event,admission=admission,row=row,pricing=pricing,approvals=approvals)

def input_for(x):
 with psycopg.connect(x['worker']['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  return c.execute('SELECT oracle2.question_effect_input_v1(%s,%s,NULL,NULL,%s)',(x['admission'],x['event']['event_id'],datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]

def historical_input_for(x,valid_at,known_at):
 with psycopg.connect(x['worker']['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  return c.execute('SELECT oracle2.question_effect_input_v1(%s,%s,%s,%s,%s)',(x['admission'],x['event']['event_id'],valid_at,known_at,datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]

def historical_claim_for(x,job,valid_at,known_at):
 with psycopg.connect(x['worker']['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  return c.execute('SELECT oracle2.claim_question_effect_v1(%s,%s,%s,%s,%s,%s)',(x['admission'],x['event']['event_id'],valid_at,known_at,canonical_bytes(job),datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]

def test_actual_question_owner_has_no_runtime_grants_or_issued_admissions(admin_url):
 with psycopg.connect(admin_url) as c:
  assert c.execute('SELECT count(*) FROM oracle2.question_effect_admissions_v1').fetchone()==(0,)
  for sig in PUBLIC_QUESTION_SIGNATURES_V1+PRIVATE_QUESTION_SIGNATURES_V1:
   assert c.execute("SELECT p.proowner=n.nspowner,p.prosecdef,p.provolatile,NOT EXISTS(SELECT 1 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE a.grantee<>p.proowner) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE p.oid=to_regprocedure(%s)",(sig,)).fetchone()==(True,True,'v',True)

def test_actual_question_current_immutable_employee_and_both_complete_source_scopes(question_case):
 x=question_case;context=input_for(x)
 assert context['original_text']==x['event']['original_text'] and context['employee_event_id']==x['event']['event_id']
 assert context['enduser_principal_id']==str(x['employee']['actor']) and context['worker_principal_id']==str(x['worker']['actor'])
 assert context['delivery']['retained_receipt']['event_id'] and context['source_refs']==context['delivery']['source_refs']
 with psycopg.connect(x['admin']) as c:
  c.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope LIKE 'source-read:%%'",(x['f']['workspace'],x['employee']['actor']))
 with pytest.raises(psycopg.errors.InsufficientPrivilege):input_for(x)

@pytest.mark.parametrize('damage',['foreign-event','worker-revoked','employee-revoked','purpose-revoked','unsafe-grant','private-grant'])
def test_actual_question_denies_foreign_revoked_or_unsafe_grants_before_claim(question_case,damage):
 x=question_case;input_for(x)
 with psycopg.connect(x['admin']) as c:
  if damage=='foreign-event':x['event']=dict(x['event'],event_id=str(uuid4()))
  elif damage=='worker-revoked':c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1(admission_id) VALUES(%s)',(x['worker']['aid'],))
  elif damage=='employee-revoked':c.execute('INSERT INTO oracle2.processing_model_admission_revocations_v1(admission_id) VALUES(%s)',(x['employee']['aid'],))
  elif damage=='purpose-revoked':c.execute('INSERT INTO oracle2.question_effect_admission_revocations_v1(admission_id) VALUES(%s)',(x['admission'],))
  elif damage=='unsafe-grant':c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION '+PUBLIC_QUESTION_SIGNATURES_V1[0]+' TO PUBLIC'))
  elif damage=='private-grant':c.execute(sql.SQL('GRANT EXECUTE ON FUNCTION '+PRIVATE_QUESTION_SIGNATURES_V1[0]+' TO {}').format(sql.Identifier(x['worker']['login'])))
 with pytest.raises(psycopg.errors.InsufficientPrivilege):input_for(x)
 with psycopg.connect(x['admin']) as c:assert c.execute('SELECT count(*) FROM oracle2.question_effect_operations_v1').fetchone()==(0,)

 # Restore only this invented negative fixture's exact global ACL mutation.
 with psycopg.connect(x['admin']) as c:
  if damage=='unsafe-grant':c.execute(sql.SQL('REVOKE EXECUTE ON FUNCTION '+PUBLIC_QUESTION_SIGNATURES_V1[0]+' FROM PUBLIC'))
  elif damage=='private-grant':c.execute(sql.SQL('REVOKE EXECUTE ON FUNCTION '+PRIVATE_QUESTION_SIGNATURES_V1[0]+' FROM {}').format(sql.Identifier(x['worker']['login'])))

def job_for(x,context=None):
 context=context or input_for(x);identifier=str(uuid4());a=context['admission'];request=dict(model=a['provider_model'],input=[context['original_text']],dimensions=256,encoding_format='float',store=False,provider={'only':['openai'],'allow_fallbacks':False,'require_parameters':True,'data_collection':'deny'})
 return dict(schema_version=1,job_schema='qualified-query-embedding-dispatch-v1',dispatch_id=identifier,workspace_id=context['workspace_id'],artifact_id=identifier,batch_id=a['allocation_batch'],purpose=a['effect_purpose'],attempt=1,request=request,request_hash=digest(request),permission_hash='c'*64,processing_request={'purpose':a['effect_purpose'],'account':a['account'],'terms_hash':a['terms_hash']},approvals=x['approvals'],pricing=x['pricing'],register_hash=a['register_hash'],input_tokens_upper_bound=4096,admission_id=context['admission_id'],thread_id=context['thread_id'],thread_revision=context['thread_revision'],employee_event_id=context['employee_event_id'],original_sha256=context['original_sha256'],query_sha256=context['query_sha256'],qualified_model_id=context['model_id'],model_version=context['model_version'],model_content_hash=context['model_content_hash'],accepted_projection_event_id=context['delivery']['retained_receipt']['event_id'],accepted_receipt_body_sha256=context['delivery']['retained_receipt_body_sha256'],qualified_population=context['source_refs'],qualified_population_sha256=digest({'source_refs':context['source_refs']}),billing_bounds_sha256=a['billing_bounds_sha256'],approval_packet_sha256=a['approval_packet_sha256'],source_export_scope_sha256=a['source_export_scope_sha256'],grounding_sha256='d'*64)

def claim_for(x,job):
 with psycopg.connect(x['worker']['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  return c.execute('SELECT oracle2.claim_question_effect_v1(%s,%s,NULL,NULL,%s,%s)',(x['admission'],x['event']['event_id'],canonical_bytes(job),datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]

def test_actual_simultaneous_once_claim_and_global_reinstall_cannot_reset_UNKNOWN(question_case):
 from concurrent.futures import ThreadPoolExecutor
 x=question_case;job=job_for(x)
 with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:claim_for(x,job),range(2)))
 assert sorted(r['dispatch_allowed'] for r in results)==[False,True]
 assert claim_for(x,job)['dispatch_allowed'] is False
 changed=dict(job,dispatch_id=str(uuid4()));changed['artifact_id']=changed['dispatch_id']
 with pytest.raises(psycopg.errors.UniqueViolation):claim_for(x,changed)
 row=dict(x['row']);row['admission_id']=uuid4();row['allocation_batch']=uuid4()
 with psycopg.connect(x['admin']) as c:c.execute(sql.SQL('INSERT INTO oracle2.question_effect_admissions_v1 ({}) VALUES ({})').format(sql.SQL(',').join(map(sql.Identifier,row)),sql.SQL(',').join(sql.Placeholder() for _ in row)),tuple(row.values()))
 x['admission']=row['admission_id'];replacement=dict(changed,admission_id=str(row['admission_id']),batch_id=str(row['allocation_batch']))
 with pytest.raises(psycopg.errors.UniqueViolation):claim_for(x,replacement)
 with psycopg.connect(x['admin']) as c:assert c.execute('SELECT count(*) FROM oracle2.question_effect_operations_v1 WHERE thread_id=%s',(x['snapshot']['thread_id'],)).fetchone()==(1,)

@pytest.mark.parametrize('field',['original_sha256','query_sha256','qualified_model_id','model_content_hash','accepted_receipt_body_sha256','employee_event_id','attempt','qualified_population','pricing'])
def test_actual_claim_refuses_changed_original_scope_receipt_or_price_before_mutation(question_case,field):
 x=question_case;job=job_for(x);job[field]={'attempt':True,'qualified_population':[],'pricing':{'model':'foreign'},'qualified_model_id':str(uuid4()),'employee_event_id':str(uuid4())}.get(field,'a'*64)
 with pytest.raises(psycopg.errors.InsufficientPrivilege):claim_for(x,job)
 with psycopg.connect(x['admin']) as c:assert c.execute('SELECT count(*) FROM oracle2.question_effect_operations_v1 WHERE thread_id=%s',(x['snapshot']['thread_id'],)).fetchone()==(0,)


def cost_check(x,operation,observation=None):
 body=observation or dict(schema_version=1,protocol='question-effect-cost-check-v1',operation_id=operation)
 with psycopg.connect(x['worker']['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  return c.execute('SELECT oracle2.record_question_effect_observation_v1(%s,%s,%s)',(operation,canonical_bytes(body),datetime.now(timezone.utc)+timedelta(seconds=10))).fetchone()[0]

def test_actual_cost_scope_survives_source_loss_without_original_or_retry_permission(question_case):
 x=question_case;job=job_for(x);claim_for(x,job);operation=job['dispatch_id']
 before=cost_check(x,operation)
 assert before['state']=='unknown' and before['dispatch_allowed'] is False
 assert not {'original_text','job_utf8','source_refs','delivery'} & set(before['cost_context'])
 with psycopg.connect(x['admin']) as c:
  c.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE workspace_id=%s AND actor_id=%s AND scope LIKE 'source-read:%%'",(x['f']['workspace'],x['employee']['actor']))
 with pytest.raises(psycopg.errors.InsufficientPrivilege):input_for(x)
 assert cost_check(x,operation)['cost_context']['job_sha256']==digest(job)
 with psycopg.connect(x['admin']) as c:
  assert c.execute('SELECT count(*) FROM oracle2.question_effect_observations_v1 WHERE operation_id=%s',(operation,)).fetchone()==(0,)
  c.execute("UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE scope=%s",('question-effect-cost-settlement:'+str(x['admission']),))
 with pytest.raises(psycopg.errors.InsufficientPrivilege):cost_check(x,operation)

def test_actual_cost_observation_exact_idempotency_collision_and_append_only(question_case):
 x=question_case;job=job_for(x);claim_for(x,job)
 body=dict(schema_version=1,protocol='question-effect-observation-v1',observation_id=str(uuid4()),operation_id=job['dispatch_id'],outcome='unknown',reservation_id=str(uuid4()),wire_sha256='a'*64,native_receipt_sha256='b'*64,settled_response_sha256=None)
 assert cost_check(x,job['dispatch_id'],body)['state']=='unknown'
 assert cost_check(x,job['dispatch_id'],body)['state']=='unknown'
 with pytest.raises(psycopg.errors.UniqueViolation):cost_check(x,job['dispatch_id'],dict(body,wire_sha256='c'*64))
 with psycopg.connect(x['admin']) as c:
  assert c.execute('SELECT count(*) FROM oracle2.question_effect_observations_v1 WHERE operation_id=%s',(job['dispatch_id'],)).fetchone()==(1,)
 with pytest.raises(psycopg.errors.RaiseException):
  with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.question_effect_admissions_v1 SET cost_settlement_sha256=%s WHERE admission_id=%s',('d'*64,x['admission']))

@pytest.mark.parametrize('field',['wire_sha256','native_receipt_sha256','reservation_id','observation_id','outcome'])
def test_actual_cost_observation_null_fields_refuse_before_append(question_case,field):
 x=question_case;job=job_for(x);claim_for(x,job)
 body=dict(schema_version=1,protocol='question-effect-observation-v1',observation_id=str(uuid4()),operation_id=job['dispatch_id'],outcome='unknown',reservation_id=str(uuid4()),wire_sha256='a'*64,native_receipt_sha256='b'*64,settled_response_sha256=None);body[field]=None
 with pytest.raises((psycopg.errors.InsufficientPrivilege,psycopg.errors.NotNullViolation)):cost_check(x,job['dispatch_id'],body)
 with psycopg.connect(x['admin']) as c:assert c.execute('SELECT count(*) FROM oracle2.question_effect_observations_v1 WHERE operation_id=%s',(job['dispatch_id'],)).fetchone()==(0,)

@pytest.mark.parametrize('field',['job_schema','permission_hash','grounding_sha256'])
def test_actual_claim_null_discriminants_refuse_before_operation(question_case,field):
 x=question_case;job=job_for(x);job[field]=None
 with pytest.raises(psycopg.errors.InsufficientPrivilege):claim_for(x,job)
 with psycopg.connect(x['admin']) as c:assert c.execute('SELECT count(*) FROM oracle2.question_effect_operations_v1 WHERE thread_id=%s',(x['snapshot']['thread_id'],)).fetchone()==(0,)

def test_actual_original_operation_deadline_is_immutable_and_never_renewed_by_read_or_reinstall(question_case):
 x=question_case;job=job_for(x);deadline=datetime.now(timezone.utc)+timedelta(seconds=1)
 with psycopg.connect(x['worker']['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  claimed=c.execute('SELECT oracle2.claim_question_effect_v1(%s,%s,NULL,NULL,%s,%s)',(x['admission'],x['event']['event_id'],canonical_bytes(job),deadline)).fetchone()[0]
 original=datetime.fromisoformat(claimed['operation_deadline']);assert original<=deadline
 with psycopg.connect(x['admin']) as c:
  assert c.execute('SELECT operation_deadline FROM oracle2.question_effect_operations_v1 WHERE operation_id=%s',(job['dispatch_id'],)).fetchone()==(original,)
 with pytest.raises(psycopg.errors.RaiseException):
  with psycopg.connect(x['admin']) as c:c.execute('UPDATE oracle2.question_effect_operations_v1 SET operation_deadline=clock_timestamp()+interval \'1 hour\' WHERE operation_id=%s',(job['dispatch_id'],))
 time.sleep(max(0,(original-datetime.now(timezone.utc)).total_seconds()+.02))
 assert input_for(x)['original_sha256']==job['original_sha256'] # read scope stays current
 with pytest.raises(psycopg.errors.InsufficientPrivilege):
  with psycopg.connect(x['worker']['url']) as c:
   c.execute("SET LOCAL statement_timeout='5s'")
   c.execute('SELECT oracle2.question_effect_status_v1(%s,%s)',(job['dispatch_id'],datetime.now(timezone.utc)+timedelta(seconds=10)))
 repeated=claim_for(x,job);assert repeated['dispatch_allowed'] is False and datetime.fromisoformat(repeated['operation_deadline'])==original
 financial=cost_check(x,job['dispatch_id'])
 assert datetime.fromisoformat(financial['cost_context']['original_operation_deadline'])==original
 assert datetime.fromisoformat(financial['cost_context']['valid_until'])>datetime.now(timezone.utc)
 assert not {'original_text','job_utf8','source_refs','delivery'}&set(financial['cost_context'])
def test_historical_dated_input_exercises_historical_model_switch(question_case):
 x=question_case
 now=datetime.now(timezone.utc)
 # Positive: known_at after the model revision was recorded (fixture just ran).
 context=historical_input_for(x,valid_at=now-timedelta(days=1),known_at=now)
 assert context['original_text']==x['event']['original_text']
 assert context['employee_event_id']==x['event']['event_id']
 assert context['model_version']>=1
 assert context['model_content_hash']

def test_historical_dated_input_rejects_future_known_at(question_case):
 x=question_case
 future=datetime.now(timezone.utc)+timedelta(hours=1)
 with pytest.raises(psycopg.errors.InsufficientPrivilege):
  historical_input_for(x,valid_at=future-timedelta(days=1),known_at=future)

def test_historical_dated_input_rejects_mismatched_null_dates(question_case):
 x=question_case
 now=datetime.now(timezone.utc)
 with pytest.raises(psycopg.errors.InsufficientPrivilege):
  historical_input_for(x,valid_at=now,known_at=None)
 with pytest.raises(psycopg.errors.InsufficientPrivilege):
  historical_input_for(x,valid_at=None,known_at=now)

def test_historical_switch_taken_not_current_model(question_case):
 x=question_case
 # known_at BEFORE the model revision was recorded: historical raises no_data_found,
 # while current model would succeed. This proves the historical switch is exercised.
 past=datetime.now(timezone.utc)-timedelta(days=365)
 with pytest.raises(Exception) as exc_info:
  historical_input_for(x,valid_at=past,known_at=past)
 assert 'no registered committed knowledge' in str(exc_info.value).lower() or 'no_data' in str(exc_info.value).lower() or isinstance(exc_info.value,psycopg.errors.NoDataFound)

def test_historical_dated_claim_and_status(question_case):
 x=question_case
 now=datetime.now(timezone.utc)
 context=historical_input_for(x,valid_at=now-timedelta(days=1),known_at=now)
 job=job_for(x,context)
 claimed=historical_claim_for(x,job,valid_at=now-timedelta(days=1),known_at=now)
 assert claimed['dispatch_allowed'] is True
 assert claimed['operation_deadline']
 # Status re-enters the historical path via stored valid_at/known_at.
 with psycopg.connect(x['worker']['url']) as c:
  c.execute("SET LOCAL statement_timeout='5s'")
  status=c.execute('SELECT oracle2.question_effect_status_v1(%s,%s)',(job['dispatch_id'],datetime.now(timezone.utc)+timedelta(seconds=15))).fetchone()[0]
 assert status['state']=='unknown'
 assert status['dispatch_allowed'] is False
