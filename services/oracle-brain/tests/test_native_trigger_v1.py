"""Fresh invented permission/one-use SQL tests; never an old live job replay."""
from oracle_brain.private_targets import read_private_target
import base64,hashlib,json,os
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import UUID
import pytest
from oracle_brain.hosting.native_trigger_v1 import decode_bundle,validate_payload,database_url,SCENARIO
from oracle_brain.hosting.synthetic_fixture import fixed_scenario,fixture,NATIVE_TRIGGER_SCENARIO,LEGACY_SCENARIO,FORWARD_SCENARIO


def sealed(body):
 raw=json.dumps(body,separators=(',',':')).encode();return raw,hashlib.sha256(raw).hexdigest()


def bundle():
 return {'schema_version':1,'purpose':NATIVE_TRIGGER_SCENARIO,'issued_at':1000,'expires_at':4600,
   'runtime_hash':'a'*64,'review_hash':'b'*64,'source_role_registry_hash':'c'*64,
   'files':{k:base64.b64encode(b'invented').decode() for k in ('database_url','database_ca','graph_url','graph_ca','graph_cert','graph_key')}}


def test_new_native_test_has_no_historical_identifiers_or_sources():
 new=fixed_scenario(NATIVE_TRIGGER_SCENARIO)
 for old_id in (LEGACY_SCENARIO,FORWARD_SCENARIO):
  old=fixed_scenario(old_id)
  assert not set((new.workspace,new.actor,new.owner,new.artifact,new.generation,new.release,new.run,new.root_appointment,new.grantor)) & set((old.workspace,old.actor,old.owner,old.artifact,old.generation,old.release,old.run,old.root_appointment,old.grantor))
  assert not {s[0] for s in new.sources}&{s[0] for s in old.sources}
  assert new.worker_uri!=old.worker_uri
 _,_,payload,manifest,release=fixture('a'*64,'b'*64,NATIVE_TRIGGER_SCENARIO)
 assert release.graph_name.endswith(new.generation.hex)
 assert all('violet envelopes' in o['value'] for o in payload['observations'])


@pytest.mark.parametrize('mutation',[
 lambda b:b.update(purpose=LEGACY_SCENARIO),lambda b:b.update(expires_at=4601),
 lambda b:b.update(issued_at=2001),lambda b:b.update(runtime_hash='z'*64),
 lambda b:b['files'].update(admin_key='aW52ZW50ZWQ='),lambda b:b['files'].update(graph_key=''),
])
def test_new_native_permission_refuses_bad_scope_or_capability(mutation):
 b=bundle();mutation(b)
 with pytest.raises((PermissionError,ValueError)):decode_bundle(*sealed(b),now=2000)


def test_new_native_permission_denies_expiry_and_tampered_seal():
 raw,seal=sealed(bundle());assert decode_bundle(raw,seal,now=2000)[0]['expires_at']==4600
 with pytest.raises(PermissionError):decode_bundle(raw,seal,now=4600)
 with pytest.raises(PermissionError):decode_bundle(raw+b' ',seal,now=2000)


@pytest.mark.parametrize('payload',[{'jobId':'77777777-7777-4777-8777-777777777777','workspaceId':str(SCENARIO.workspace)},
 {'jobId':str(SCENARIO.run),'workspaceId':str(SCENARIO.workspace),'endpoint':'https://foreign.invalid'},
 {'jobId':str(SCENARIO.run),'workspaceId':'11111111-1111-4111-8111-111111111111'}])
def test_old_or_caller_selected_native_authority_denied(payload):
 with pytest.raises(PermissionError):validate_payload(payload)


def test_native_database_target_isolated_and_tls_fixed():
 url=(b'postgresql://oracle_synthetic_executor.'+read_private_target('native_supabase_project').encode()+b':invented@aws-0-us-east-1.pooler.supabase.com:5432/oracle_native_proof_v1')
 result=database_url(url,Path('/private/invented-ca'))
 assert 'sslmode=verify-full' in result and 'sslrootcert=' in result
 for wrong in (url.replace(b'oracle_native_proof_v1',b'postgres'),url+b'?sslmode=disable',url.replace(b'aws-0-us-east-1',b'aws-0-us-west-1')):
  with pytest.raises(PermissionError):database_url(wrong,Path('/private/ca'))


@pytest.fixture(scope='module')
def native_sql(tmp_path_factory):
 import psycopg
 from dev.oracle2.test_worker_postgres_fixture import worker_postgres
 from oracle_brain.hosting.synthetic_seed import compile_seed
 base=tmp_path_factory.mktemp('native-trigger-cluster')
 env={**os.environ,'COMPOSE_PROJECT_NAME':'oracle2-synthetic-native-trigger'}
 with worker_postgres(env,base/'owned','documentary-01') as (settings,_):
  admin=settings['ORACLE2_TEST_ADMIN_URL'];parameters=psycopg.conninfo.conninfo_to_dict(admin)
  with psycopg.connect(admin,autocommit=True) as c:c.execute('CREATE DATABASE oracle_native_proof_v1')
  db=psycopg.conninfo.make_conninfo(admin,dbname='oracle_native_proof_v1')
  scripts=Path(__file__).resolve().parents[1]/'sql'
  with psycopg.connect(db) as c:
   for n in ('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql','006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql','008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql','010_hosting_job_permissions.sql','015_native_trigger_proof.sql'):c.execute((scripts/n).read_text())
   # Verifiers use real SCRAM, not test-only trust or superuser SET ROLE.
   p={k:'a'*64 for k in ('runtime_hash','source_role_registry_hash','review_hash')}
   p.update(expires_at=(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),synthetic_scenario=NATIVE_TRIGGER_SCENARIO,synthetic_scenario_seal=SCENARIO.seal())
   import hashlib,hmac,secrets
   def scram(password):
    salt=secrets.token_bytes(16);v=hashlib.pbkdf2_hmac('sha256',password.encode(),salt,4096)
    stored=hashlib.sha256(hmac.new(v,b'Client Key',hashlib.sha256).digest()).digest();server=hmac.new(v,b'Server Key',hashlib.sha256).digest()
    return 'SCRAM-SHA-256$4096:'+base64.b64encode(salt).decode()+'$'+base64.b64encode(stored).decode()+':'+base64.b64encode(server).decode()
   p.update({r+'_scram':scram('invented-native-test-only') for r in ('gateway','executor','projector')})
   seed=compile_seed(p)[0];c.execute(seed)
  gateway=psycopg.conninfo.make_conninfo(db,user='oracle_synthetic_gateway',password='invented-native-test-only',options='-c role=oracle2_gateway_metadata')
  executor=psycopg.conninfo.make_conninfo(db,user='oracle_synthetic_executor',password='invented-native-test-only',options='-c role=oracle2_documentary_executor')
  projector=psycopg.conninfo.make_conninfo(db,user='oracle_synthetic_projector',password='invented-native-test-only',options='-c role=oracle2_documentary_executor')
  yield db,gateway,executor,projector,fixture('a'*64,'a'*64,NATIVE_TRIGGER_SCENARIO)[-1]


def test_actual_new_native_roles_dispatch_claim_sessions_and_duplicate_denials(native_sql):
 import psycopg
 admin,gateway,executor,projector,release=native_sql
 with psycopg.connect(gateway) as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_dispatch(%s,%s,%s)',(SCENARIO.run,'a'*64,release.documentary_gate_hash))
 with psycopg.connect(executor) as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(SCENARIO.run,))
 with psycopg.connect(projector) as c:c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(SCENARIO.run,))
 with psycopg.connect(projector) as c:
  with pytest.raises(psycopg.errors.UniqueViolation):c.execute('SELECT oracle2.native_trigger_projection(%s,false)',(SCENARIO.run,))
 with psycopg.connect(projector) as c:c.execute('SELECT oracle2.native_trigger_projection(%s,true)',(SCENARIO.run,))
 with psycopg.connect(gateway) as c:
  assert c.execute('SELECT session_user,current_user').fetchone()==('oracle_synthetic_gateway','oracle2_gateway_metadata')
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT text FROM oracle2.source_blocks')
 with psycopg.connect(gateway) as c:
  c.execute('SELECT oracle2.native_trigger_dispatch(%s,%s,%s)',(SCENARIO.run,'a'*64,release.documentary_gate_hash))
 with psycopg.connect(gateway) as c:
  with pytest.raises(psycopg.errors.UniqueViolation):c.execute('SELECT oracle2.native_trigger_dispatch(%s,%s,%s)',(SCENARIO.run,'a'*64,release.documentary_gate_hash))
 with psycopg.connect(executor) as c:c.execute('SELECT oracle2.native_trigger_claim(%s,%s)',(SCENARIO.run,'run_inventedNativeAttempt01'))
 with psycopg.connect(executor) as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_claim(%s,%s)',(SCENARIO.run,'run_inventedNativeAttempt01'))
 with psycopg.connect(gateway) as c:
  c.execute('SELECT oracle2.native_trigger_bind(%s,%s)',(SCENARIO.run,'run_inventedNativeAttempt01'))
  assert c.execute('SELECT oracle2.native_trigger_run(%s)',(SCENARIO.run,)).fetchone()[0]=='run_inventedNativeAttempt01'
  c.execute('SELECT oracle2.native_trigger_session_create(%s,%s,%s)',('1'*64,'2'*64,'3'*64))
  assert c.execute('SELECT oracle2.native_trigger_session_live(%s,%s,%s)',('1'*64,'2'*64,'3'*64)).fetchone()[0] is True
  assert c.execute('SELECT oracle2.native_trigger_session_live(%s,%s,%s)',('1'*64,'2'*64,'4'*64)).fetchone()[0] is False
  c.execute('SELECT oracle2.native_trigger_session_revoke(%s)',('1'*64,))
  assert c.execute('SELECT oracle2.native_trigger_session_live(%s,%s,%s)',('1'*64,'2'*64,'3'*64)).fetchone()[0] is False
 with psycopg.connect(executor) as c:
  with pytest.raises(psycopg.errors.InsufficientPrivilege):c.execute('SELECT oracle2.native_trigger_dispatch(%s,%s,%s)',(SCENARIO.run,'a'*64,release.documentary_gate_hash))


def test_actual_native_source_role_rejects_elevated_drift(native_sql):
 import psycopg
 from oracle_brain.hosting.native_trigger_v1 import NativeSourceRoleBindingV1
 admin,_,executor,_,_=native_sql
 binding=NativeSourceRoleBindingV1('a'*64,'a'*64,synthetic=True)
 binding.check_url(executor)
 try:
  with psycopg.connect(admin) as c:c.execute('ALTER ROLE oracle_synthetic_executor CREATEDB')
  with pytest.raises(PermissionError,match='privileges changed'):binding.check_url(executor)
 finally:
  with psycopg.connect(admin) as c:c.execute('ALTER ROLE oracle_synthetic_executor NOCREATEDB')
 binding.check_url(executor)


def test_native_tls_adapter_fixed_ids_match_new_fixture_without_hosting_import(monkeypatch):
 from oracle_brain.operating_model.sdk_projection import SDKProjection,NativeInventedTLSProjectionV1
 captured={}
 def capture(self,graph_url,**kwargs):captured.update(kwargs)
 monkeypatch.setattr(SDKProjection,'__init__',capture)
 NativeInventedTLSProjectionV1('rediss://oracle_native_proof_executor_v1:invented@oracle-graph.designflow.app:16391',connection_config=object())
 assert (captured['workspace_id'],captured['artifact_id'],captured['artifact_version'],captured['generation'])==(SCENARIO.workspace,SCENARIO.artifact,1,SCENARIO.generation)
 assert captured['read_only'] is True


@pytest.mark.parametrize('damage',[None,'graph_name','content_hash','record_digest','sdk_version','unexpected_key'])
def test_projector_consumes_real_sdk_build_mapping_once_and_finishes_only_matching_result(tmp_path,monkeypatch,damage):
 import asyncio,importlib.util,time
 from types import SimpleNamespace
 import psycopg
 from oracle_brain.operating_model import sdk_projection,assembly_qualification,authority_adapter,ledger
 from oracle_brain.hosting import job_authority
 path=Path(__file__).resolve().parents[3]/'dev/oracle2/hosting/project_native_trigger.py'
 spec=importlib.util.spec_from_file_location('native_projector_operator_contract',path)
 operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
 body={'runtime_hash':'a'*64,'review_hash':'b'*64,'source_role_registry_hash':'c'*64,'expires_at':int(time.time())+3600}
 _,_,payload,manifest,release=fixture(body['runtime_hash'],body['review_hash'],NATIVE_TRIGGER_SCENARIO)
 events=[];claims=[]
 class Database:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def execute(self,sql,params):
   assert sql in ('SELECT oracle2.native_trigger_projection(%s,false)','SELECT oracle2.native_trigger_projection(%s,true)')
   assert params==(SCENARIO.run,)
   claims.append(sql.endswith('true)'));events.append(('claim',claims[-1]))
 class Binding:
  def __init__(self,*args,**kwargs):pass
  def check_url(self,url):events.append(('binding',url))
 class Authority:
  def __init__(self,*args,**kwargs):pass
  def resolve(self,*args):return {'expires_at':body['expires_at']}
  def __call__(self,row):events.append(('authority',True))
 class Finalized:
  def model_dump(self,**kwargs):return {'indexes':{'invented':True}}
 class Connection:
  async def query(self,query,params):events.append(('snapshot',params))
 class Projection:
  records=staticmethod(sdk_projection.SDKProjection.records)
  read_only=False;workspace_id=SCENARIO.workspace;graph_name=release.graph_name;qualification_guard=None
  connection=Connection()
  async def _build_graph_payload(self,*args):
   events.append(('build',True));return self.records(payload),Finalized()
  async def verify(self,actual):assert actual==payload;events.append(('verify',True))
  async def close(self):events.append(('close',True))
  async def build(self,*args):
   result=await sdk_projection.SDKProjection.build(self,*args)
   assert isinstance(result,dict) and len(result)==5
   if damage:result[damage]='wrong'
   return result
 monkeypatch.setattr(psycopg,'connect',lambda *args,**kwargs:Database())
 monkeypatch.setattr(operator,'database_url',lambda *args,**kwargs:'invented://projector')
 monkeypatch.setattr(operator,'tls_config',lambda *args,**kwargs:('invented://new-graph',object()))
 monkeypatch.setattr(operator,'NativeSourceRoleBindingV1',Binding)
 monkeypatch.setattr(job_authority,'PostgresJobAuthority',Authority)
 monkeypatch.setattr(authority_adapter,'PostgresSources',lambda *args,**kwargs:SimpleNamespace(can_read=lambda *a:True,current=lambda *a:None))
 monkeypatch.setattr(ledger,'Ledger',lambda *args,**kwargs:object())
 monkeypatch.setattr(assembly_qualification,'read_documentary_artifact',lambda *args,**kwargs:payload)
 monkeypatch.setattr(sdk_projection,'NativeInventedTLSProjectionV1',lambda *args,**kwargs:Projection())
 if damage:
  with pytest.raises(PermissionError,match='SDK build result differs'):asyncio.run(operator.project(body,{'database_url':b'invented','database_ca':b'invented','graph_url':b'invented'},tmp_path))
  assert claims==[False]
 else:
  result=asyncio.run(operator.project(body,{'database_url':b'invented','database_ca':b'invented','graph_url':b'invented'},tmp_path))
  assert result=={'state':'completed','job_id':str(SCENARIO.run),'graph_name':release.graph_name,'artifact_hash':manifest.content_hash,'records':3,'sdk_version':'1.4.0'}
  assert claims==[False,True]
 assert events[0][0]=='binding'
 assert events.index(('claim',False))<events.index(('build',True))
 assert sum(name=='build' for name,_ in events)==1
 assert sum(name=='snapshot' for name,_ in events)==1
 assert events[-1]==('close',True)
