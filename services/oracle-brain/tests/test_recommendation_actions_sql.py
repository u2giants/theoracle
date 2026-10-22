"""Actual exact-owned SQL/private bytes; injected full census is NOT native proof."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
import hashlib,json,os
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest
from test_consolidation_sql_v1 import sql_qualified_v3,sql_qualified_serving_v3,prepared_qualified_model,RUNTIME,REGISTRY
from test_recommendation_contract import recommendation
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.consolidation_contracts_v1 import ConsolidationCoreV1
from oracle_brain.operating_model.consolidation_recommendations_v1 import consulting_evidence_revision_v2
from oracle_brain.operating_model.consultant.recommendations import recommendation_to_payload
from oracle_brain.operating_model.consultant.recommendation_actions_v1 import QualifiedConsultingRecommendationsV2,RecommendationSelectorV1,FeedbackCommandV1
from oracle_brain.operating_model.consultant.recommendation_authority_v1 import RecommendationBindingV1,RecommendationAuthorityV1,RecommendationOutcomeUnknown,FUNCTIONS,PUBLIC
from oracle_brain.operating_model.consultant.recommendation_compiler_v1 import compile_recommendation_actions_v1
from oracle_brain.operating_model.processing_ledger import PurposeProcessingCompilerLedgerV3
from oracle_brain.operating_model.purpose_qualification_v3 import PurposeQualifiedAssemblyReadGuardV3
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
import time

ROOT=Path(__file__).resolve().parents[1]
@contextmanager
def admin(url):
 from dev.oracle2.test_worker_postgres_fixture import owned_worker_database
 owned_worker_database(os.environ['ORACLE2_SYNTHETIC_POSTGRES_CONTAINER'],url)
 with psycopg.connect(url) as connection:
  assert connection.pgconn.ssl_in_use
  assert connection.execute('SELECT SESSION_USER,current_database()').fetchone()==('oracle2_admin',psycopg.conninfo.conninfo_to_dict(url)['dbname'])
  yield connection

@pytest.fixture(scope='module')
def recommendation_schema(admin_url):
 return _assert_recommendation_schema_v1(admin_url)


def _assert_recommendation_schema_v1(admin_url):
 # The existing canonical session bootstrap owns the COMPLETE024→025 inventory
 # once per fresh owned UUID DB. This fixture asserts, never replays or repairs.
 with admin(admin_url) as connection:
  rows=connection.execute("SELECT p.prosecdef,p.proconfig FROM pg_proc p WHERE p.oid IN (SELECT to_regprocedure(x) FROM unnest(%s::text[]) x)",(['oracle2.'+signature for signature in FUNCTIONS],)).fetchall()
  assert len(rows)==len(FUNCTIONS), 'complete current canonical025 prerequisite required; no autoapply'
  assert all(security and settings==['search_path=pg_catalog, oracle2'] for security,settings in rows)
 return admin_url


def pins(connection):
 rows=connection.execute('''SELECT p.proname,encode(sha256(convert_to(p.prosrc,'UTF8')),'hex'),
 encode(sha256(convert_to(coalesce((SELECT string_agg(grantee::text||':'||privilege_type||':'||is_grantable::text,',' ORDER BY grantee,privilege_type,is_grantable)
 FROM aclexplode(coalesce(p.proacl,acldefault('f',p.proowner)))),'') ,'UTF8')),'hex')
 FROM pg_proc p WHERE p.oid IN(SELECT to_regprocedure(x) FROM unnest(%s::text[]) x)''',(['oracle2.'+s for s in FUNCTIONS],)).fetchall()
 assert len(rows)==len(FUNCTIONS)
 return tuple(sorted(rows))


def _install_advice_rows_v1(connection,stage,operation,login,aid,membership):
 f=stage['f']
 if operation!='register':
  connection.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD {}').format(sql.Identifier(login),sql.Literal('invented-advice-only')))
  connection.execute(sql.SQL('GRANT USAGE ON SCHEMA oracle2 TO {}').format(sql.Identifier(login)))
 owner=connection.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
 connection.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(membership,f['workspace'],f['actor'],'recommendation-'+operation+':'+str(f['model']),owner,f['root'],f['expiry']))
 connection.execute('INSERT INTO oracle2.recommendation_action_admissions_v1 VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,clock_timestamp(),%s,%s)',(aid,login,f['actor'],f['workspace'],f['model'],operation,RUNTIME,REGISTRY,'f'*64,membership,Jsonb([r.model_dump(mode='json') for r in f['all_refs']]),uuid4(),uuid4(),f['expiry'],f['expiry']))
 for signature in FUNCTIONS:
  if signature.startswith(PUBLIC[operation]+'(') or operation=='read' and signature.startswith('list_recommendation_actions_v1(') or operation!='read' and signature.startswith('reconcile_recommendation_action_v1('):
   connection.execute(sql.SQL('GRANT EXECUTE ON FUNCTION oracle2.'+signature+' TO {}').format(sql.Identifier(login)))


def _installed_advice_authority_v1(stage,operation,login,aid,fingerprints):
 f=stage['f']
 parts=psycopg.conninfo.conninfo_to_dict(f['url']);ca=parts['sslrootcert']
 url=psycopg.conninfo.make_conninfo(f['url'],hostaddr='127.0.0.1',user=login,password='invented-compiler-only' if operation=='register' else 'invented-advice-only')
 binding=RecommendationBindingV1(aid,f['actor'],f['workspace'],f['model'],operation,login,stage['schema_owner'],RUNTIME,REGISTRY,'f'*64,ca,hashlib.sha256(Path(ca).read_bytes()).hexdigest(),f['expiry'],fingerprints)
 return RecommendationAuthorityV1(url,binding=binding)


def install(admin_url,stage,operation,*,login=None):
 f=stage['f'];aid=uuid4();membership=uuid4();login=login or 'advice_'+operation+'_'+uuid4().hex[:10]
 with admin(admin_url) as connection:
  _install_advice_rows_v1(connection,stage,operation,login,aid,membership)
  fingerprints=pins(connection)
 return _installed_advice_authority_v1(stage,operation,login,aid,fingerprints)


def _install_all_advice_authorities_v1(admin_url,stage):
 # Fixed TEST SETUP ONLY population; every role/admission remains independent.
 identities=[('register',stage['login'],uuid4(),uuid4())]
 identities.extend((operation,'advice_'+operation+'_'+uuid4().hex[:10],uuid4(),uuid4())
  for operation in ('read','feedback','measurement'))
 assert len({login for _,login,_,_ in identities})==4
 assert len({aid for _,_,aid,_ in identities})==4
 assert len({membership for _,_,_,membership in identities})==4
 with admin(admin_url) as connection:
  for operation,login,aid,membership in identities:
   _install_advice_rows_v1(connection,stage,operation,login,aid,membership)
  # Exact existing complete catalog AFTER ALL grants, before actual commit/close.
  fingerprints=pins(connection)
 # No authority is constructed/returned until the same owner has committed/closed.
 return tuple(_installed_advice_authority_v1(stage,operation,login,aid,fingerprints)
  for operation,login,aid,_ in identities)


def repin(admin_url,authorities):
 with admin(admin_url) as connection:fingerprints=pins(connection)
 return tuple(RecommendationAuthorityV1(a.url,binding=replace(a.binding,capability_fingerprints=fingerprints)) for a in authorities)


def actual_proposal(stage,lens='approval_exception'):
 parent=stage['manifest'];payload=stage['q']['payload'];core=ConsolidationCoreV1.model_validate_json(canonical_bytes(payload['consolidation_core']))
 evidence=consulting_evidence_revision_v2(core,parent,payload);rid=uuid4();scope=core.assertions[0].scope
 known={'assertion:'+str(a.assertion_id)+':'+str(a.revision):a for a in core.assertions}
 refs=tuple(k for k,a in known.items() if a.scope==scope);opposed=tuple(k for k,a in known.items() if a.scope==scope and a.opposing_observations)
 template=recommendation(lens=lens,opposing_evidence=(),opposing_unknown=True)
 advice=replace(template,recommendation_id=str(rid),evidence=evidence,opposing_evidence=opposed,opposing_unknown=not bool(opposed),options=tuple(replace(o,evidence_refs=(refs[0],)) for o in template.options))
 raw=dict(schema_version=1,contract='qualified-consulting-recommendations-v2',parent_model_id=str(parent.artifact_id),parent_version=parent.version,parent_content_hash=parent.content_hash,repair_of_event=None,recommendations=[dict(schema_version=1,recommendation_id=str(rid),advice=recommendation_to_payload(advice),scope=scope.model_dump(mode='json'),problem='Invented reported approval delay',competing_explanations=['Missing information may explain the delay'],effort='Unmeasured',risks=['Downstream effort unmeasured'],owner_role_description='Description only; no appointment',review_due='2026-10-20T00:00:00Z',experiments=[dict(schema_version=1,experiment_id=str(uuid4()),option_id='opt:1',metric_id=str(core.assertions[0].subject_id),unit='money',currency='USD',period='per_week',population_id=str(uuid4()),baseline_start='2026-10-01T00:00:00Z',baseline_end='2026-10-08T00:00:00Z',followup_start='2026-10-08T00:00:00Z',followup_end='2026-10-15T00:00:00Z',success_metric='Source-supported observed difference if later available',reversible_step='Stop the invented trial')])])
 from oracle_brain.operating_model.consultant.measurement_evidence_v1 import measurement_from_assertion_v1
 measured=[measurement_from_assertion_v1(a) for a in core.assertions]
 if len(measured)==2 and all(m is not None for m in measured):
  baseline,followup=measured;plan=raw['recommendations'][0]['experiments'][0]
  plan.update(metric_id=str(core.assertions[0].subject_id),unit=baseline.unit,currency=baseline.currency,period=baseline.period,population_id=str(baseline.population_id),baseline_start=baseline.window_start.isoformat().replace('+00:00','Z'),baseline_end=baseline.window_end.isoformat().replace('+00:00','Z'),followup_start=followup.window_start.isoformat().replace('+00:00','Z'),followup_end=followup.window_end.isoformat().replace('+00:00','Z'))
 return QualifiedConsultingRecommendationsV2.model_validate_json(canonical_bytes(raw))

def build_advice(stage,recommendation_schema):
 from oracle_brain.operating_model.authority_adapter import ProcessingArtifactResolver
 source=ProcessingArtifactResolver(psycopg.conninfo.make_conninfo(stage['url'],hostaddr='127.0.0.1'),binding=stage['source'].binding);q=stage['q']
 compiler=PurposeProcessingCompilerLedgerV3(source.url,stage['blobs'],principal=stage['actor'],processing_sources=source,
   processing_compile_guard=stage['guard'],processing_read_guard=stage['guard'])
 guard=PurposeQualifiedAssemblyReadGuardV3.for_full_compiler_parent_v3(trusted_admissions=lambda:q['trusted_admission_hashes'],runtime_hash=RUNTIME,
   current_source_identity=lambda workspace,principal,s:source.identity(workspace,s),current_extraction_seal=lambda workspace,principal,a,v:source.extraction_seal(workspace,a,v),qualified_parent_reader=compiler.read_validated_qualified_parent_v3)
 class InjectedFixtureFullValidation:
  # Fixture host supplies the captured qualification, not a production hosting
  # appointment. This adapter runs the ACTUAL complete canonical guard once.
  def validate_current(self,manifest,payload,principal,now):
   return guard.valid_until(manifest,payload,principal,now)
 compiler.processing_compile_guard=InjectedFixtureFullValidation();compiler.processing_read_guard=compiler.processing_compile_guard
 register,read,feedback,measurement=_install_all_advice_authorities_v1(recommendation_schema,stage)
 proposal=actual_proposal(stage);deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
 with _request_fence_v1(float(time.monotonic()+25)):
  manifest,receipt=compile_recommendation_actions_v1(compiler,register,workspace_id=stage['w'],artifact_id=uuid4(),version=1,recommendations=proposal,permission_digest=q['admission'].compiler_permission_hash,caller_deadline=deadline)
 selector=RecommendationSelectorV1(artifact_id=manifest.artifact_id,artifact_version=1,artifact_sha256=manifest.content_hash,recommendation_id=proposal.recommendations[0].recommendation_id)
 return dict(stage=stage,compiler=compiler,register=register,read=read,feedback=feedback,measurement=measurement,proposal=proposal,manifest=manifest,receipt=receipt,selector=selector,admin_url=recommendation_schema)


@pytest.fixture
def advice_fixture(recommendation_schema,sql_qualified_v3,tmp_path):
 stage=prepared_qualified_model(recommendation_schema,sql_qualified_v3,tmp_path,return_fixture=True)
 return build_advice(stage,recommendation_schema)


def command(f,*,head=0,decision='accept',command_id=None):
 return FeedbackCommandV1(selector=f['selector'],expected_head=head,command_id=command_id or uuid4(),decision=decision,option_id='opt:1' if decision=='accept' else None,reason='Invented personal preference; not policy or fact rejection',caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=15))


def test_actual_canonical_producer_registration_and_separate_personal_feedback(advice_fixture):
 f=advice_fixture;q=command(f)
 with _request_fence_v1(float(time.monotonic()+20)):
  before=f['read'].read_v1(f['selector'],deadline=q.caller_deadline)
  event=f['feedback'].feedback_v1(q,canonical_bytes(q.model_dump(mode='json')))
  after=f['read'].read_v1(f['selector'],deadline=q.caller_deadline)
 assert before['head_revision']==0 and after['head_revision']==1 and after['events'][0]['event_id']==event['event_id']
 assert after['events'][0]['payload']['decision']=='accept'
 assert all(after[k] is False for k in ('policy_accepted','effect_executed','causal_savings','realized_savings_verified','business_acceptance'))
 with admin(f['admin_url']) as c:
  assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1
  assert c.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s AND artifact_id=%s',(f['stage']['w'],f['manifest'].artifact_id)).fetchone()[0]==1


def test_actual_accept_reject_defer_append_cas_and_same_command_receipt_replay(advice_fixture):
 f=advice_fixture;events=[]
 with _request_fence_v1(float(time.monotonic()+25)):
  for head,decision in enumerate(('accept','reject','defer')):
   q=command(f,head=head,decision=decision);raw=canonical_bytes(q.model_dump(mode='json'))
   events.append(f['feedback'].feedback_v1(q,raw))
  assert f['feedback'].feedback_v1(q,raw)==events[-1]
  stale=command(f,head=0)
  with pytest.raises(psycopg.errors.SerializationFailure):f['feedback'].feedback_v1(stale,canonical_bytes(stale.model_dump(mode='json')))
  status=f['read'].read_v1(f['selector'],deadline=q.caller_deadline)
 assert [e['payload']['decision'] for e in status['events']]==['accept','reject','defer']
 assert status['head_revision']==3


@pytest.mark.parametrize('fault',['source-withdraw','root-revoke','read-admission','feedback-admission','expired-feedback'])
def test_actual_current_permission_loss_denies_writes_and_redacts_only_source_history(advice_fixture,fault):
 f=advice_fixture;q=command(f)
 with _request_fence_v1(float(time.monotonic()+20)):
  event=f['feedback'].feedback_v1(q,canonical_bytes(q.model_dump(mode='json')))
 with admin(f['admin_url']) as c:
  if fault=='source-withdraw':c.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['stage']['w'],f['stage']['sources'][0].source_id,f['stage']['sources'][0].original_sha256,f['stage']['actor'],f['stage']['login'],RUNTIME,'invented source withdrawal',uuid4(),'a'*64))
  elif fault=='root-revoke':c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['stage']['root'],))
  elif fault.endswith('admission'):
   a=f['read' if fault=='read-admission' else 'feedback'].binding.appointment_id
   c.execute('INSERT INTO oracle2.recommendation_action_revocations_v1(admission_id) VALUES(%s)',(a,))
  else:
   # A selected expired immutable admission is a new fixture fact, not mutation
   # of the append-only appointment. A real expiry is independently checked.
   pass
 if fault=='expired-feedback':
  expired=replace(f['feedback'].binding,original_horizon=datetime.now(timezone.utc)-timedelta(seconds=1))
  f['feedback']=RecommendationAuthorityV1(f['feedback'].url,binding=expired)
 newer=command(f,head=1)
 with _request_fence_v1(float(time.monotonic()+20)):
  if fault!='read-admission':
   with pytest.raises(PermissionError if fault=='expired-feedback' else psycopg.errors.InsufficientPrivilege):
    f['feedback'].feedback_v1(newer,canonical_bytes(newer.model_dump(mode='json')))
  if fault=='source-withdraw':
   redacted=f['read'].read_v1(f['selector'],deadline=newer.caller_deadline)
   assert redacted['redacted'] and redacted['stale'] and redacted['context'] is None
   assert redacted['events']==[dict(event_id=event['event_id'],sequence=1,kind='feedback',recorded_at=event['recorded_at'],payload=None)]
  elif fault=='read-admission':
   with pytest.raises(psycopg.errors.InsufficientPrivilege):f['read'].read_v1(f['selector'],deadline=newer.caller_deadline)
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1


@pytest.mark.parametrize('fault',['owner','fingerprint','ca','role'])
def test_actual_catalog_and_exact_installed_target_refusals_before_mutation(advice_fixture,fault):
 f=advice_fixture;a=f['feedback'];b=a.binding
 if fault=='owner':b=replace(b,expected_owner='wrong_invented_owner')
 elif fault=='fingerprint':b=replace(b,capability_fingerprints=tuple((name,'0'*64,acl) for name,body,acl in b.capability_fingerprints))
 elif fault=='ca':b=replace(b,ca_sha256='0'*64)
 else:b=replace(b,session_login=f['read'].binding.session_login)
 with _request_fence_v1(float(time.monotonic()+20)):
  with pytest.raises(PermissionError):
   altered=RecommendationAuthorityV1(a.url,binding=b);q=command(f)
   altered.feedback_v1(q,canonical_bytes(q.model_dump(mode='json')))
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==0


def test_actual_private_helpers_and_other_operation_ungranted(advice_fixture):
 f=advice_fixture
 for a in (f['read'],f['feedback'],f['measurement']):
  with psycopg.connect(a.url) as c:
   with pytest.raises(psycopg.errors.InsufficientPrivilege):
    c.execute('SELECT oracle2._recommendation_action_context_v1(%s,%s,%s,%s,%s,%s)',(a.binding.appointment_id,a.binding.operation,RUNTIME,REGISTRY,'f'*64,datetime.now(timezone.utc)+timedelta(seconds=10)))
 with psycopg.connect(f['read'].url) as c:
  q=command(f)
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.record_recommendation_feedback_v1(%s,%s,%s,%s,%s,%s)',(canonical_bytes(q.model_dump(mode='json')),f['read'].binding.appointment_id,RUNTIME,REGISTRY,'f'*64,q.caller_deadline))


def test_actual_concurrent_feedback_has_one_durable_cas_winner(advice_fixture):
 from concurrent.futures import ThreadPoolExecutor
 f=advice_fixture;commands=(command(f),command(f,decision='defer'));end=float(time.monotonic()+20)
 def submit(q):
  with _request_fence_v1(end):
   try:return f['feedback'].feedback_v1(q,canonical_bytes(q.model_dump(mode='json')))
   except psycopg.errors.SerializationFailure:return 'conflict'
 with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(submit,commands))
 assert sum(r=='conflict' for r in results)==1
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1


@pytest.mark.parametrize('fault',['fresh-loss','fresh-revoke','fresh-close'])
def test_actual_committed_feedback_readback_uncertainty_is_unknown_once(advice_fixture,monkeypatch,fault):
 f=advice_fixture;a=f['feedback'];q=command(f);original=a.reconcile_v1;calls=[]
 def fail(*args,**kwargs):
  calls.append(args)
  if fault=='fresh-loss':raise psycopg.OperationalError('invented read-only connection loss after write close')
  if fault=='fresh-revoke':
   with admin(f['admin_url']) as c:c.execute('INSERT INTO oracle2.recommendation_action_revocations_v1(admission_id) VALUES(%s)',(a.binding.appointment_id,))
  value=original(*args,**kwargs)
  if fault=='fresh-close':raise OSError('invented fresh close ACK loss after actual read')
  return value
 monkeypatch.setattr(a,'reconcile_v1',fail)
 with _request_fence_v1(float(time.monotonic()+20)),pytest.raises(RecommendationOutcomeUnknown):a.feedback_v1(q,canonical_bytes(q.model_dump(mode='json')))
 assert len(calls)==1
 with admin(f['admin_url']) as c:
  rows=c.execute('SELECT command_id,sequence FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchall()
  assert rows==[(q.command_id,1)]

@pytest.fixture
def measurement_advice(recommendation_schema,sql_qualified_v3,tmp_path,monkeypatch):
 return _measurement_advice_v1(recommendation_schema,tmp_path,monkeypatch,serving=False)


@pytest.fixture
def measurement_serving_advice(recommendation_schema,sql_qualified_serving_v3,tmp_path,monkeypatch):
 # New named120/115 fixture is selected BEFORE actual source capture/census;
 # old30/25 fixtures and every individual request's30s limit stay unchanged.
 return _measurement_advice_v1(recommendation_schema,tmp_path,monkeypatch,serving=True)


def _measurement_advice_v1(recommendation_schema,tmp_path,monkeypatch,*,serving):
 import test_assembly_context as foundation
 from test_purpose_qualification_v3 import qualified_v3
 from test_measurement_evidence_v1 import record,assertion,ID
 from oracle_brain.operating_model.source_receipts import SourceReceipt,EvidenceRef
 from oracle_brain.operating_model.observations import create_observation
 records=(record(),record(amount='10',window_start='2026-10-08T00:00:00Z',window_end='2026-10-15T00:00:00Z',observed_through='2026-10-15T00:00:00Z'))
 from qualified_source_fixture_v1 import qualified_two_source_fixture_v1,qualified_two_source_serving_fixture_v1
 texts=tuple(canonical_bytes({'metric_id':str(ID),'scope':assertion().scope.model_dump(mode='json'),'measurement':value}).decode() for value in records)
 fresh=(qualified_two_source_serving_fixture_v1 if serving else qualified_two_source_fixture_v1)(monkeypatch,texts)
 def assertions(ctx):
  result=[]
  for index,(extraction,recorded) in enumerate(zip(ctx.extractions,records,strict=True)):
   observation=extraction.payload['observations'][0];value=assertion(recorded,assertion_id=str(uuid4()),supporting_observations=[observation['observation_id']],temporal_observations=[observation['observation_id']],valid_from=recorded['window_start'],valid_to=recorded['window_end'])
   assert json.loads(observation['value'])['measurement']==recorded
   result.append(value.model_dump(mode='json'))
  return result
 stage=prepared_qualified_model(recommendation_schema,fresh,tmp_path,return_fixture=True,assertion_factory=assertions)
 return build_advice(stage,recommendation_schema)


def test_actual_qualified_source_measurements_are_derived_not_caller_numbers(measurement_advice):
 from oracle_brain.operating_model.consultant.recommendation_actions_v1 import MeasurementCommandV1,source_bound_measurement_v1,observed_difference_v1
 from oracle_brain.operating_model.consultant.measurement_evidence_v1 import MeasurementEvidenceV1
 f=measurement_advice;item=f['proposal'].recommendations[0];core=ConsolidationCoreV1.model_validate_json(canonical_bytes(f['stage']['q']['payload']['consolidation_core']))
 with _request_fence_v1(float(time.monotonic()+25)):
  for index,phase in enumerate(('baseline','followup')):
   q=MeasurementCommandV1(selector=f['selector'],expected_head=index,command_id=uuid4(),experiment_id=item.experiments[0].experiment_id,phase=phase,assertion_id=core.assertions[index].assertion_id,assertion_revision=1,caller_deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
   selected=source_bound_measurement_v1(core,item,q,now=datetime.now(timezone.utc))
   f['measurement'].measurement_v1(q,canonical_bytes(q.model_dump(mode='json')),canonical_bytes(selected['assertion']))
  status=f['read'].read_v1(f['selector'],deadline=q.caller_deadline)
 values=[MeasurementEvidenceV1.model_validate_json(canonical_bytes(e['payload']['measurement'])) for e in status['events']]
 difference=observed_difference_v1(*values,now=datetime.now(timezone.utc))
 assert difference['observed_difference']=='2.5' and difference['causal_savings'] is False and difference['realized_savings_verified'] is False
 assert [v.amount for v in values]==['12.5','10']
 assert all('command_id' not in e['payload'] for e in status['events'])


from test_hosting_boundary import certificates

@contextmanager
def advice_listener(f,tmp_path,certificates,*,peer_changes=None,web=False):
 from dataclasses import asdict
 from cryptography import x509
 from cryptography.hazmat.primitives.serialization import Encoding
 from test_hosting_boundary import WORKER
 from oracle_brain.hosting.recommendation_actions_settings_v1 import RecommendationConfigV1,RecommendationPeerV1,RecommendationSettingsV1
 from oracle_brain.hosting.recommendation_actions_service_v1 import protected_recommendation_actions_server_v1,protected_recommendation_web_server_v1
 import shutil,threading
 folder=tmp_path/'listener';folder.mkdir(mode=0o700)
 def save(name,data):
  path=folder/name;path.write_bytes(data);path.chmod(0o600)
  return dict(schema_version=1,path=str(path),sha256=hashlib.sha256(data).hexdigest())
 tls={name:save(name,(certificates/name).read_bytes()) for name in ('ca.pem','server.pem','server.key')}
 consumers={}
 for name in ('read','feedback','measurement'):
  a=f[name];data=json.loads(json.dumps(asdict(a.binding),default=str));data['schema_version']=1
  data['database_url']=save(name+'-sql',a.url.encode());consumers[name]=data
 root=f['stage']['blobs'].root;info=root.stat();now=datetime.now(timezone.utc)
 config=RecommendationConfigV1.model_validate_json(canonical_bytes(dict(schema_version=1,purpose='qualified-recommendation-actions-v1',principal_id=str(f['stage']['actor']),workspace_id=str(f['stage']['w']),model_id=str(f['stage']['f']['model']),**consumers,storage_root=str(root),storage_device=info.st_dev,storage_inode=info.st_ino,storage_uid=info.st_uid,storage_profile_hash='a'*64,original_horizon=f['stage']['expiry'].isoformat(),expires_at=(now+timedelta(seconds=90)).isoformat())))
 cp=save('config',canonical_bytes(config.model_dump(mode='json')))
 issuer,reviewer=uuid4(),uuid4()
 der=x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(Encoding.DER)
 peer=RecommendationPeerV1.model_validate_json(canonical_bytes(dict(schema_version=1,purpose='qualified-recommendation-actions-peer-v1',config_sha256=cp['sha256'],principal_id=str(config.principal_id),workspace_id=str(config.workspace_id),model_id=str(config.model_id),read_appointment_id=str(config.read.appointment_id),feedback_appointment_id=str(config.feedback.appointment_id),measurement_appointment_id=str(config.measurement.appointment_id),issuer_actor=str(issuer),reviewer_actor=str(reviewer),client_certificate_sha256=hashlib.sha256(der).hexdigest(),client_uri=WORKER,client_ca=tls['ca.pem'],server_certificate=tls['server.pem'],server_key=tls['server.key'],listen_host='127.0.0.1',listen_port=0,valid_from=(now-timedelta(seconds=1)).isoformat(),expires_at=(now+timedelta(seconds=90)).isoformat(),original_horizon=f['stage']['expiry'].isoformat())))
 if peer_changes:
  peer=RecommendationPeerV1.model_validate_json(canonical_bytes(peer.model_dump(mode='json')|peer_changes))
 pp=save('peer',canonical_bytes(peer.model_dump(mode='json')))
 settings=RecommendationSettingsV1.load(config_path=cp['path'],config_sha256=cp['sha256'],peer_path=pp['path'],peer_sha256=pp['sha256'],expected_issuer_actor=issuer,expected_reviewer_actor=reviewer)
 server=(protected_recommendation_web_server_v1 if web else protected_recommendation_actions_server_v1)(settings);thread=threading.Thread(target=server.serve_forever);thread.start()
 try:yield server,settings
 finally:
  server.shutdown();thread.join(timeout=3);server.server_close();assert not thread.is_alive()


def tls_request(server,certificates,value,*,identity='worker',route='/v1/replacement/recommendation-actions',headers=None):
 import http.client,ssl
 context=ssl.create_default_context(cafile=str(certificates/'ca.pem'))
 if identity:context.load_cert_chain(str(certificates/(identity+'.pem')),str(certificates/(identity+'.key')))
 connection=http.client.HTTPSConnection('localhost',server.server_port,context=context,timeout=5)
 try:
  body=canonical_bytes(value) if type(value) is dict else value
  connection.request('POST',route,body=body,headers=headers or {'Content-Type':'application/json'})
  response=connection.getresponse();return response.status,response.read()
 finally:connection.close()


def test_actual_mtls_factory_private_bytes_ownsql_accept_then_source_redaction(advice_fixture,tmp_path,certificates,monkeypatch):
 f=advice_fixture
 from oracle_brain.hosting.recommendation_actions_v1 import RecommendationFactoryV1
 original=RecommendationFactoryV1._body;reads=[]
 def closed_body(self,manifest):
  with admin(f['admin_url']) as c:
   assert c.execute('SELECT count(*) FROM pg_stat_activity WHERE application_name=%s',(f['stage']['app_name'],)).fetchone()[0]==0
  reads.append(manifest.artifact_id)
  return original(self,manifest)
 monkeypatch.setattr(RecommendationFactoryV1,'_body',closed_body)
 with advice_listener(f,tmp_path,certificates) as (server,settings):
  inspect=dict(schema_version=1,operation='inspect',selector=f['selector'].model_dump(mode='json'),caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z'))
  status,body=tls_request(server,certificates,inspect)
  assert status==200;view=json.loads(body)
  assert view['recommendation']['problem']=='Invented reported approval delay' and view['head_revision']==0
  assert view['evidence']['supporting'] and not view['measurement_sources']
  code,index=tls_request(server,certificates,dict(schema_version=1,operation='list',caller_deadline=inspect['caller_deadline']))
  assert code==200;index=json.loads(index)
  assert index['entries'][0]['selector']==f['selector'].model_dump(mode='json') and index['entries'][0]['label']=='Invented reported approval delay'
  assert index['list_complete'] and not index['coverage_gap']
  assert all(key not in body.decode() for key in ('private_object_key','session_login','appointment_id','database_url','context'))
  q=command(f);status,body=tls_request(server,certificates,canonical_bytes(q.model_dump(mode='json')))
  assert status==200 and json.loads(body)['head_revision']==1
  reconcile=dict(schema_version=1,operation='reconcile-feedback',selector=f['selector'].model_dump(mode='json'),command_id=str(q.command_id),caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z'))
  code,raw=tls_request(server,certificates,reconcile);assert code==200;receipt=json.loads(raw)
  assert receipt['command_id']==str(q.command_id) and receipt['receipt_read_only'] and not receipt['write_authorized'] and not receipt['dispatch_authorized']
  assert all(k not in receipt for k in ('events','payload','context','recommendation'))
  with admin(f['admin_url']) as c:c.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['stage']['w'],f['stage']['sources'][0].source_id,f['stage']['sources'][0].original_sha256,f['stage']['actor'],f['stage']['login'],RUNTIME,'invented source withdrawal',uuid4(),'a'*64))
  inspect['caller_deadline']=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z')
  status,body=tls_request(server,certificates,inspect);assert status==200;view=json.loads(body)
  assert view['redacted'] and view['recommendation'] is None and view['events'][0]['payload'] is None
  assert q.reason not in body.decode()
  assert not view['measurement_sources'] and all(not v for v in view['evidence'].values())
  code,denied=tls_request(server,certificates,dict(schema_version=1,operation='list',caller_deadline=inspect['caller_deadline']))
  assert code!=200 and b'Invented reported approval delay' not in denied
  assert len(reads)>=4


@pytest.mark.parametrize('fault',['unknown-field','unknown-route','encoding','wrong-peer','wrong-uri','changed-pin','expired-deadline'])
def test_actual_mtls_strict_refusals_do_not_write(advice_fixture,tmp_path,certificates,fault):
 f=advice_fixture
 with advice_listener(f,tmp_path,certificates,peer_changes={'client_uri':'spiffe://oracle/unrelated'} if fault=='wrong-uri' else None) as (server,settings):
  q=command(f);value=q.model_dump(mode='json');kwargs={}
  if fault=='unknown-field':value['actor_id']=str(uuid4())
  elif fault=='unknown-route':kwargs['route']='/v1/replacement/other'
  elif fault=='encoding':kwargs['headers']={'Content-Type':'application/json','Content-Encoding':'gzip'}
  elif fault=='wrong-peer':kwargs['identity']='other'
  elif fault=='wrong-uri':pass
  elif fault=='changed-pin':Path(settings.config_path).write_bytes(b'changed')
  elif fault=='expired-deadline':value['caller_deadline']='2026-01-01T00:00:00Z'
  try:status,body=tls_request(server,certificates,value,**kwargs);assert status!=200
  except OSError:
   if fault!='wrong-peer':raise
   assert (certificates/'other.pem').is_file()
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==0


def test_actual_two_artifact_admission_first_bind_race_has_one_stable_identity(advice_fixture):
 from concurrent.futures import ThreadPoolExecutor
 f=advice_fixture;stage=f['stage'];other=install(f['admin_url'],stage,'register',login=stage['login'])
 first,second=repin(f['admin_url'],(f['register'],other))
 original=f['proposal'].model_dump(mode='json');rid=str(uuid4())
 original['recommendations'][0]['recommendation_id']=rid;original['recommendations'][0]['advice']['recommendation_id']=rid
 proposal=QualifiedConsultingRecommendationsV2.model_validate_json(canonical_bytes(original))
 deadline=datetime.now(timezone.utc)+timedelta(seconds=25);end=float(time.monotonic()+25);artifacts=(uuid4(),uuid4())
 payload={'source_refs':stage['q']['payload']['source_refs'],'findings':[],'recommendations':proposal.model_dump(mode='json')}
 from oracle_brain.operating_model.contracts import SourceRef
 refs=tuple(SourceRef.model_validate_json(canonical_bytes(r)) for r in payload['source_refs']);manifests=[]
 # Retained private-byte fixture checks one request's sockets. Prepare each
 # actual canonical candidate sequentially; race ONLY the actual first-bind
 # registration mutations under distinct installed admissions/artifact UUIDs.
 with _request_fence_v1(end):
  for artifact in artifacts:
   manifests.append(f['compiler'].persist(workspace_id=stage['w'],artifact_id=artifact,version=1,kind='processing_recommendation_v1',payload=payload,refs=refs,permission_digest=stage['q']['admission'].compiler_permission_hash,compiler_digest=RUNTIME,dependencies=(('artifact',str(stage['manifest'].artifact_id),'1'),),caller_deadline=deadline))
 def register(args):
  authority,manifest=args
  with _request_fence_v1(end):
   try:return authority.register_v1(manifest,canonical_bytes(payload),canonical_bytes(stage['q']['payload']),deadline=deadline)
   except psycopg.errors.SerializationFailure:return 'conflict'
 with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(register,zip((first,second),manifests)))
 assert sum(r=='conflict' for r in results)==1
 with admin(f['admin_url']) as c:
  rows=c.execute('SELECT artifact_id FROM oracle2.recommendation_registrations_v1 WHERE workspace_id=%s AND recommendation_index @> %s',(stage['w'],Jsonb([{'recommendation_id':rid}]))).fetchall()
  assert len(rows)==1 and rows[0][0] in artifacts
  # The losing canonical candidate can exist, but has NO registered lifecycle
  # identity or permission from registration failure. No writer is retried.
  assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(stage['w'],)).fetchone()[0]==0


def test_actual_repair_is_next_same_artifact_version_and_never_inherits_feedback(advice_fixture):
 f=advice_fixture;q=command(f,decision='reject');deadline=datetime.now(timezone.utc)+timedelta(seconds=25)
 with _request_fence_v1(float(time.monotonic()+25)):
  rejection=f['feedback'].feedback_v1(q,canonical_bytes(q.model_dump(mode='json')))
  body=f['proposal'].model_dump(mode='json');body['repair_of_event']=rejection['event_id'];body['recommendations'][0]['problem']='Bounded evidence-preserving repair after personal rejection'
  proposal=QualifiedConsultingRecommendationsV2.model_validate_json(canonical_bytes(body))
  manifest,receipt=compile_recommendation_actions_v1(f['compiler'],f['register'],workspace_id=f['stage']['w'],artifact_id=f['manifest'].artifact_id,version=2,recommendations=proposal,permission_digest=f['stage']['q']['admission'].compiler_permission_hash,caller_deadline=deadline)
  selected=f['selector'].model_copy(update={'artifact_version':2,'artifact_sha256':manifest.content_hash})
  fresh=f['read'].read_v1(selected,deadline=deadline);old=f['read'].read_v1(f['selector'],deadline=deadline)
 assert fresh['head_revision']==0 and fresh['events']==[] and not fresh['redacted']
 assert old['redacted'] and old['events'][0]['payload'] is None
 with admin(f['admin_url']) as c:
  assert c.execute('SELECT count(*) FROM oracle2.recommendation_repairs_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1
  assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1


def test_actual_source_measurement_tampering_wrong_phase_and_caller_number_are_refused(measurement_advice):
 from copy import deepcopy
 from oracle_brain.operating_model.consultant.recommendation_actions_v1 import MeasurementCommandV1
 f=measurement_advice;item=f['proposal'].recommendations[0];core=ConsolidationCoreV1.model_validate_json(canonical_bytes(f['stage']['q']['payload']['consolidation_core']))
 base=dict(schema_version=1,operation='measurement',selector=f['selector'].model_dump(mode='json'),expected_head=0,command_id=str(uuid4()),experiment_id=str(item.experiments[0].experiment_id),phase='baseline',assertion_id=str(core.assertions[0].assertion_id),assertion_revision=1,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z'))
 with _request_fence_v1(float(time.monotonic()+25)):
  for field,replacement in (('amount','999'),('currency','CAD'),('period','per_month'),('population_id',str(uuid4()))):
   raw=deepcopy(core.assertions[0].model_dump(mode='json'));value=json.loads(raw['value']);value[field]=replacement;raw['value']=canonical_bytes(value).decode()
   q=MeasurementCommandV1.model_validate_json(canonical_bytes(base))
   with pytest.raises(psycopg.errors.InsufficientPrivilege):f['measurement'].measurement_v1(q,canonical_bytes(q.model_dump(mode='json')),canonical_bytes(raw))
  q=MeasurementCommandV1.model_validate_json(canonical_bytes(base|{'assertion_id':str(core.assertions[1].assertion_id)}))
  with pytest.raises(psycopg.errors.InsufficientPrivilege):f['measurement'].measurement_v1(q,canonical_bytes(q.model_dump(mode='json')),canonical_bytes(core.assertions[1].model_dump(mode='json')))
  q=base|{'amount':'12.5'}
  with psycopg.connect(f['measurement'].url) as c,pytest.raises(psycopg.errors.InvalidParameterValue):
   c.execute('SELECT oracle2.record_recommendation_measurement_v1(%s,%s,%s,%s,%s,%s,%s)',(canonical_bytes(q),canonical_bytes(core.assertions[0].model_dump(mode='json')),f['measurement'].binding.appointment_id,RUNTIME,REGISTRY,'f'*64,datetime.fromisoformat(base['caller_deadline'].replace('Z','+00:00'))))
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==0


def test_actual_global_command_survives_reinstall_and_exact_receipt_ignores_unrelated_command(advice_fixture):
 f=advice_fixture;first=command(f);a=f['feedback'];new_id=uuid4()
 with _request_fence_v1(float(time.monotonic()+25)):
  receipt=a.feedback_v1(first,canonical_bytes(first.model_dump(mode='json')))
 with admin(f['admin_url']) as c:
  c.execute('INSERT INTO oracle2.recommendation_action_admissions_v1 SELECT %s,role_name,principal_id,workspace_id,model_id,operation,runtime_hash,registry_hash,config_hash,membership_appointment,source_refs,issuer_actor,reviewer_actor,issued_at,expires_at,original_horizon FROM oracle2.recommendation_action_admissions_v1 WHERE admission_id=%s',(new_id,a.binding.appointment_id))
 new=RecommendationAuthorityV1(a.url,binding=replace(a.binding,appointment_id=new_id))
 with _request_fence_v1(float(time.monotonic()+25)):
  assert new.feedback_v1(first,canonical_bytes(first.model_dump(mode='json')))==receipt
  collision=first.model_copy(update={'reason':'different bytes cannot reuse global command'})
  with pytest.raises(psycopg.errors.UniqueViolation):new.feedback_v1(collision,canonical_bytes(collision.model_dump(mode='json')))
  second=command(f,head=1,decision='defer');new.feedback_v1(second,canonical_bytes(second.model_dump(mode='json')))
  exact=new.reconcile_v1(f['manifest'].artifact_id,1,f['selector'].recommendation_id,first.command_id,deadline=first.caller_deadline)
 assert exact['command_id']==str(first.command_id) and exact['event_id']==receipt['event_id'] and exact['sequence']==1
 assert 'payload' not in exact and 'events' not in exact and 'context' not in exact
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==2


def test_actual_expired_original_window_readonly_reconciliation_never_renews_or_resends(advice_fixture):
 f=advice_fixture;a=f['feedback'];q=command(f).model_copy(update={'caller_deadline':datetime.now(timezone.utc)+timedelta(seconds=3)})
 with _request_fence_v1(float(time.monotonic()+3)):
  original=a.feedback_v1(q,canonical_bytes(q.model_dump(mode='json')))
 original_until=datetime.fromisoformat(original['original_operation_valid_until'])
 assert original_until<=q.caller_deadline
 fresh_id=uuid4()
 with admin(f['admin_url']) as c:
  c.execute('INSERT INTO oracle2.recommendation_action_revocations_v1(admission_id) VALUES(%s)',(a.binding.appointment_id,))
  c.execute('INSERT INTO oracle2.recommendation_action_admissions_v1 SELECT %s,role_name,principal_id,workspace_id,model_id,operation,runtime_hash,registry_hash,config_hash,membership_appointment,source_refs,issuer_actor,reviewer_actor,issued_at,expires_at,original_horizon FROM oracle2.recommendation_action_admissions_v1 WHERE admission_id=%s',(fresh_id,a.binding.appointment_id))
  for signature in FUNCTIONS:
   if signature.startswith('record_recommendation_feedback_v1('):c.execute(sql.SQL('REVOKE EXECUTE ON FUNCTION oracle2.'+signature+' FROM {}').format(sql.Identifier(a.binding.session_login)))
  fingerprints=pins(c)
 readonly=RecommendationAuthorityV1(a.url,binding=replace(a.binding,appointment_id=fresh_id,capability_fingerprints=fingerprints))
 # Bounded source-only observation of actual expiry. No writer is repeated.
 delay=(original_until-datetime.now(timezone.utc)).total_seconds()+.05
 if delay>0:time.sleep(delay)
 deadline=datetime.now(timezone.utc)+timedelta(seconds=12)
 with _request_fence_v1(float(time.monotonic()+12)):
  receipt=readonly.reconcile_v1(f['manifest'].artifact_id,1,f['selector'].recommendation_id,q.command_id,deadline=deadline)
  assert receipt['original_operation_valid_until']==original['original_operation_valid_until']
  assert receipt['original_operation_window_unexpired'] is False and receipt['receipt_read_only'] is True
  assert receipt['write_authorized'] is False and receipt['dispatch_authorized'] is False
  assert datetime.fromisoformat(receipt['valid_until'])>original_until
  new_command=command(f,head=1)
  with pytest.raises(psycopg.errors.InsufficientPrivilege):readonly.feedback_v1(new_command,canonical_bytes(new_command.model_dump(mode='json')))
 with admin(f['admin_url']) as c:
  for signature in FUNCTIONS:
   if signature.startswith('reconcile_recommendation_action_v1('):c.execute(sql.SQL('REVOKE EXECUTE ON FUNCTION oracle2.'+signature+' FROM {}').format(sql.Identifier(a.binding.session_login)))
  fingerprints=pins(c)
 denied=RecommendationAuthorityV1(a.url,binding=replace(readonly.binding,capability_fingerprints=fingerprints))
 with _request_fence_v1(float(time.monotonic()+12)),pytest.raises(psycopg.errors.InsufficientPrivilege):
  denied.reconcile_v1(f['manifest'].artifact_id,1,f['selector'].recommendation_id,q.command_id,deadline=deadline)
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1


def test_actual_current_list_empty_then_registered_and_wrong_operation_denied(recommendation_schema,sql_qualified_v3,tmp_path):
 stage=prepared_qualified_model(recommendation_schema,sql_qualified_v3,tmp_path,return_fixture=True)
 read=install(recommendation_schema,stage,'read')
 with _request_fence_v1(float(time.monotonic()+25)):
  result=read.list_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert result['selectors']==[] and result['list_complete'] and not result['coverage_gap']
 f=build_advice(stage,recommendation_schema)
 with _request_fence_v1(float(time.monotonic()+25)):
  result=f['read'].list_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
  assert result['selectors']==[f['selector'].model_dump(mode='json')]
  with pytest.raises(PermissionError):f['feedback'].list_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=15))


@pytest.mark.parametrize('fault',['public-acl','body','source-grant'])
def test_actual_list_catalog_and_source_denial_has_no_selector_leak(advice_fixture,fault):
 f=advice_fixture
 with admin(f['admin_url']) as c:
  if fault=='public-acl':c.execute('GRANT EXECUTE ON FUNCTION oracle2.list_recommendation_actions_v1(uuid,text,text,text,timestamptz) TO PUBLIC')
  elif fault=='body':c.execute("ALTER FUNCTION oracle2.list_recommendation_actions_v1(uuid,text,text,text,timestamptz) SET search_path=public")
  else:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['stage']['root'],))
 try:
  with _request_fence_v1(float(time.monotonic()+20)):
   with pytest.raises((PermissionError,psycopg.errors.InsufficientPrivilege)):
    f['read'].list_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=15))
 finally:
  if fault!='source-grant':
   with admin(f['admin_url']) as c:
    if fault=='public-acl':c.execute('REVOKE EXECUTE ON FUNCTION oracle2.list_recommendation_actions_v1(uuid,text,text,text,timestamptz) FROM PUBLIC')
    else:c.execute('ALTER FUNCTION oracle2.list_recommendation_actions_v1(uuid,text,text,text,timestamptz) SET search_path=pg_catalog,oracle2')


def test_actual_mtls_qualified_measurement_selectors_and_quotes(measurement_advice,tmp_path,certificates):
 f=measurement_advice
 with advice_listener(f,tmp_path,certificates) as (server,settings):
  request=dict(schema_version=1,operation='inspect',selector=f['selector'].model_dump(mode='json'),caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z'))
  code,raw=tls_request(server,certificates,request);assert code==200
  view=json.loads(raw);choices=view['measurement_sources']
  assert len(choices)==2 and {c['phase'] for c in choices}=={'baseline','followup'}
  assert {c['measurement']['amount'] for c in choices}=={'12.5','10'}
  assert all(c['reported_only'] and not c['causal_savings'] for c in choices)
  assert view['evidence']['supporting'] and not view['measurement_coverage_gap']


@pytest.mark.parametrize('operation',['inspect','list'])
def test_actual_mtls_withdrawal_during_private_bytes_withholds_entire_response(advice_fixture,tmp_path,certificates,monkeypatch,operation):
 from oracle_brain.hosting.recommendation_actions_v1 import RecommendationFactoryV1
 f=advice_fixture;original=RecommendationFactoryV1._body;changed=False
 def withdrawing_body(self,manifest):
  nonlocal changed
  value=original(self,manifest)
  if not changed:
   changed=True
   with admin(f['admin_url']) as c:
    assert c.execute('SELECT count(*) FROM pg_stat_activity WHERE application_name=%s',(f['stage']['app_name'],)).fetchone()[0]==0
    c.execute('INSERT INTO oracle2.source_original_withdrawals_v1(event_id,workspace_id,source_id,revision,original_sha256,principal_id,session_role,runtime_hash,reason,idempotency_key,request_sha256) VALUES(%s,%s,%s,1,%s,%s,%s,%s,%s,%s,%s)',(uuid4(),f['stage']['w'],f['stage']['sources'][0].source_id,f['stage']['sources'][0].original_sha256,f['stage']['actor'],f['stage']['login'],RUNTIME,'invented source withdrawal during bytes',uuid4(),'a'*64))
  return value
 monkeypatch.setattr(RecommendationFactoryV1,'_body',withdrawing_body)
 with advice_listener(f,tmp_path,certificates) as (server,settings):
  request=dict(schema_version=1,operation=operation,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z'))
  if operation=='inspect':request['selector']=f['selector'].model_dump(mode='json')
  code,raw=tls_request(server,certificates,request)
  assert changed and code!=200 and b'Invented reported approval delay' not in raw and b'evidence' not in raw


def additional_advice(f,deadline,*,count=1):
 proposal=actual_proposal(f['stage']);raw=proposal.model_dump(mode='json');prototype=raw['recommendations'][0]
 raw['recommendations']=[]
 for _ in range(count):
  item=json.loads(json.dumps(prototype));rid=str(uuid4());item['recommendation_id']=rid;item['advice']['recommendation_id']=rid
  raw['recommendations'].append(item)
 proposal=QualifiedConsultingRecommendationsV2.model_validate_json(canonical_bytes(raw))
 return compile_recommendation_actions_v1(f['compiler'],f['register'],workspace_id=f['stage']['w'],artifact_id=uuid4(),version=1,recommendations=proposal,permission_digest=f['stage']['q']['admission'].compiler_permission_hash,caller_deadline=deadline)


def test_actual_list_more_than_64_qualified_recommendations_has_explicit_gap(advice_fixture):
 f=advice_fixture
 with _request_fence_v1(float(time.monotonic()+25)):
  deadline=datetime.now(timezone.utc)+timedelta(seconds=20)
  additional_advice(f,deadline,count=64)
  index=f['read'].list_v1(deadline=deadline)
  repeated=f['read'].list_v1(deadline=deadline)
 assert len(index['selectors'])==64 and index['coverage_gap'] and not index['list_complete']
 assert index['selectors']==repeated['selectors']
 assert len({(v['artifact_id'],v['recommendation_id']) for v in index['selectors']})==64


def test_actual_mtls_new_registration_between_list_passes_withholds_index(advice_fixture,tmp_path,certificates,monkeypatch):
 from oracle_brain.hosting.recommendation_actions_v1 import RecommendationFactoryV1
 f=advice_fixture;original=RecommendationFactoryV1._read;changed=False
 def changed_read(self,read,selector,deadline,leases):
  nonlocal changed
  value=original(self,read,selector,deadline,leases)
  if not changed:
   changed=True;additional_advice(f,deadline)
  return value
 monkeypatch.setattr(RecommendationFactoryV1,'_read',changed_read)
 with advice_listener(f,tmp_path,certificates) as (server,settings):
  code,raw=tls_request(server,certificates,dict(schema_version=1,operation='list',caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat().replace('+00:00','Z')))
  assert changed and code!=200 and b'Invented reported approval delay' not in raw
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_registrations_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==2



def test_actual_web_envelope_binds_same_current_identity_exact_request_and_committed_action(advice_fixture,tmp_path,certificates):
 f=advice_fixture
 with advice_listener(f,tmp_path,certificates,web=True) as (server,settings):
  for request in (dict(schema_version=1,operation='list',caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z')),command(f).model_dump(mode='json')):
   raw=canonical_bytes(request);code,body=tls_request(server,certificates,raw);assert code==200
   packet=json.loads(body);assert canonical_bytes(packet)==body
   assert packet['principal_id']==str(settings.config.principal_id) and packet['workspace_id']==str(settings.config.workspace_id) and packet['model_id']==str(settings.config.model_id)
   assert packet['request_sha256']==hashlib.sha256(raw).hexdigest() and packet['operation']==request['operation']
   assert packet['command_id']==request.get('command_id') and packet['expected_head']==request.get('expected_head')
   if request['operation']=='feedback':
    assert packet['result']['head_revision']==1 and packet['result']['events'][0]['payload']['reason']==request['reason']
   else:assert packet['result']['kind']=='recommendation-index-v1'
   assert datetime.fromisoformat(packet['result']['valid_until'])<=datetime.fromisoformat(request['caller_deadline'].replace('Z','+00:00'))
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1


@pytest.mark.parametrize('fault',['principal','model','command','expired'])
def test_actual_web_envelope_refuses_caller_identity_or_command_selectors(advice_fixture,tmp_path,certificates,fault):
 f=advice_fixture;request=dict(schema_version=1,operation='list',caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=15)).isoformat().replace('+00:00','Z'))
 if fault=='expired':request['caller_deadline']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat().replace('+00:00','Z')
 else:request[{'principal':'principal_id','model':'model_id','command':'command_id'}[fault]]=str(uuid4())
 with advice_listener(f,tmp_path,certificates,web=True) as (server,settings):
  code,body=tls_request(server,certificates,request);assert code!=200 and not body
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==0


def test_actual_web_envelope_post_write_revocation_retains_one_write_unknown(advice_fixture,tmp_path,certificates,monkeypatch):
 from oracle_brain.hosting.recommendation_actions_v1 import RecommendationFactoryV1
 f=advice_fixture;original=RecommendationFactoryV1._read;reads=0
 def revoked_read(self,reader,selector,deadline,leases):
  nonlocal reads
  reads+=1
  if reads==2:
   with admin(f['admin_url']) as c:c.execute('INSERT INTO oracle2.recommendation_action_revocations_v1(admission_id) VALUES(%s)',(f['read'].binding.appointment_id,))
  return original(self,reader,selector,deadline,leases)
 monkeypatch.setattr(RecommendationFactoryV1,'_read',revoked_read)
 with advice_listener(f,tmp_path,certificates,web=True) as (server,settings):
  code,body=tls_request(server,certificates,canonical_bytes(command(f).model_dump(mode='json')))
  assert reads==2 and code!=200 and not body
 with admin(f['admin_url']) as c:assert c.execute('SELECT count(*) FROM oracle2.recommendation_action_events_v1 WHERE workspace_id=%s',(f['stage']['w'],)).fetchone()[0]==1
