"""Bounded local fake fixtures; no live permission, credential custody or platform calls."""
import hashlib,importlib.util,json,os,sys,time
from pathlib import Path
import pytest
from oracle_brain.hosting.native_trigger_v2 import SCENARIO
from oracle_brain.hosting.synthetic_fixture import fixture,NATIVE_TRIGGER_V2_SCENARIO
from oracle_brain.operating_model.native_proof_v2_identity import IDENTITY
ROOT=Path(__file__).resolve().parents[3]
TOOLS=ROOT/'dev/oracle2/hosting'
sys.path.insert(0,str(TOOLS))
def load(name):
 spec=importlib.util.spec_from_file_location(name,TOOLS/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
PREPARE=load('prepare_native_trigger_v2')
INSTALL=load('install_native_trigger_v2')


def test_private_exclusive_writes_deny_replay_and_symlink(tmp_path):
 target=tmp_path/'output';PREPARE.write(tmp_path,'output',b'invented')
 assert target.stat().st_mode&0o777==0o600
 with pytest.raises(FileExistsError):PREPARE.write(tmp_path,'output',b'changed')
 (tmp_path/'link').symlink_to(target)
 with pytest.raises(FileExistsError):PREPARE.write(tmp_path,'link',b'changed')
 assert target.read_bytes()==b'invented'


def test_protected_input_rejects_other_readers_and_symlink(tmp_path):
 p=tmp_path/'fake';p.write_bytes(b'invented');p.chmod(0o644)
 with pytest.raises(PermissionError):PREPARE.protected(p)
 p.chmod(0o600);assert PREPARE.protected(p)==b'invented'
 link=tmp_path/'link';link.symlink_to(p)
 with pytest.raises((PermissionError,OSError)):PREPARE.protected(link)


@pytest.mark.parametrize('field,value',[('source_head','b'*40),('runtime_hash','b'*64),('trigger_status','FAILED'),('trigger_task','oracle2-native-invented-v1'),('vercel_status','BUILDING'),('trigger_deployment_id','other')])
def test_late_issuer_requires_exact_ready_prebuild(field,value):
 r={'source_head':'a'*40,'runtime_hash':'a'*64,'trigger_deployment_id':'deployment_invented','trigger_status':'DEPLOYED','trigger_task':IDENTITY['task'],'vercel_deployment_id':'dpl_Invented','vercel_status':'READY'}
 assert PREPARE.readiness(json.dumps(r).encode(),'a'*40,'a'*64)==r
 r[field]=value
 with pytest.raises(PermissionError):PREPARE.readiness(json.dumps(r).encode(),'a'*40,'a'*64)


@pytest.mark.parametrize('collision',['db','role'])
def test_installer_refuses_any_existing_target_without_writes(collision):
 calls=[]
 class Result:
  def __init__(self,rows):self.rows=rows
  def fetchall(self):return self.rows
 class Connection:
  def execute(self,q,p):
   calls.append(q);assert q.startswith('SELECT ')
   return Result([(1,)] if collision=='db' and 'pg_database' in q else [(IDENTITY['gateway'],)] if collision=='role' and 'pg_roles' in q else [])
 with pytest.raises(PermissionError):INSTALL.collision_check(Connection())
 assert len(calls)==(1 if collision=='db' else 2)


@pytest.mark.parametrize('damage',[None,'graph_name','content_hash','record_digest','sdk_version','unexpected_key','finalized','missing_snapshot','duplicate_snapshot','damaged_snapshot'])
def test_projector_consumes_real_sdk_build_mapping_once_and_finishes_only_matching_result(tmp_path,monkeypatch,damage):
 import asyncio,importlib.util,time
 from types import SimpleNamespace
 import psycopg
 from oracle_brain.operating_model import sdk_projection,assembly_qualification,authority_adapter,ledger
 from oracle_brain.hosting import job_authority
 path=Path(__file__).resolve().parents[3]/'dev/oracle2/hosting/project_native_trigger_v2.py'
 spec=importlib.util.spec_from_file_location('native_projector_operator_contract',path)
 operator=importlib.util.module_from_spec(spec);spec.loader.exec_module(operator)
 body={'runtime_hash':'a'*64,'review_hash':'b'*64,'source_role_registry_hash':'c'*64,'expires_at':int(time.time())+3600}
 _,_,payload,manifest,release=fixture(body['runtime_hash'],body['review_hash'],NATIVE_TRIGGER_V2_SCENARIO)
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
  async def query(self,query,params=None):
   if query.startswith('CREATE '):events.append(('snapshot',params));return
   assert query=='MATCH (s:OperatingModelSnapshot) RETURN s.content_hash,s.record_digest,s.sdk,s.finalized'
   events.append(('read_snapshot',True))
   row=[sdk_projection.digest(payload),sdk_projection.digest({'records':sdk_projection.SDKProjection.records(payload)}),'1.4.0',True]
   rows=[] if damage=='missing_snapshot' else [row,row] if damage=='duplicate_snapshot' else [[*row[:3],False]] if damage=='damaged_snapshot' else [row]
   return SimpleNamespace(result_set=rows)
 class Projection:
  records=staticmethod(sdk_projection.SDKProjection.records)
  _check_graph_snapshot=sdk_projection.SDKProjection._check_graph_snapshot
  read_only=False;workspace_id=SCENARIO.workspace;graph_name=release.graph_name;qualification_guard=None
  connection=Connection()
  async def _build_graph_payload(self,*args):
   events.append(('build',True));return self.records(payload),Finalized()
  async def verify(self,actual):assert actual==payload;events.append(('verify',True))
  async def close(self):events.append(('close',True))
  async def build(self,*args):
   result=await sdk_projection.SDKProjection.build(self,*args)
   assert isinstance(result,dict) and len(result)==5
   if damage and not damage.endswith('_snapshot'):result[damage]='wrong'
   return result
 monkeypatch.setattr(psycopg,'connect',lambda *args,**kwargs:Database())
 monkeypatch.setattr(operator,'database_url',lambda *args,**kwargs:'invented://projector')
 monkeypatch.setattr(operator,'tls_config',lambda *args,**kwargs:('invented://new-graph',object()))
 monkeypatch.setattr(operator,'NativeSourceRoleBindingV2',Binding)
 monkeypatch.setattr(job_authority,'PostgresJobAuthority',Authority)
 monkeypatch.setattr(authority_adapter,'PostgresSources',lambda *args,**kwargs:SimpleNamespace(can_read=lambda *a:True,current=lambda *a:None))
 monkeypatch.setattr(ledger,'Ledger',lambda *args,**kwargs:object())
 monkeypatch.setattr(assembly_qualification,'read_documentary_artifact',lambda *args,**kwargs:payload)
 monkeypatch.setattr(sdk_projection,'NativeInventedTLSProjectionV2',lambda *args,**kwargs:Projection())
 if damage:
  with pytest.raises(ValueError if damage.endswith('_snapshot') else PermissionError,match='sealed finalized snapshot' if damage.endswith('_snapshot') else 'SDK build result differs'):asyncio.run(operator.project(body,{'database_url':b'invented','database_ca':b'invented','graph_url':b'invented'},tmp_path))
  assert claims==[False]
 else:
  result=asyncio.run(operator.project(body,{'database_url':b'invented','database_ca':b'invented','graph_url':b'invented'},tmp_path))
  assert result=={'state':'completed','job_id':str(SCENARIO.run),'graph_name':release.graph_name,'artifact_hash':manifest.content_hash,'records':3,'sdk_version':'1.4.0'}
  assert claims==[False,True]
  assert events.index(('read_snapshot',True))<events.index(('claim',True))
 assert events[0][0]=='binding'
 assert events.index(('claim',False))<events.index(('build',True))
 assert sum(name=='build' for name,_ in events)==1
 assert sum(name=='snapshot' for name,_ in events)==1
 assert events[-1]==('close',True)


from test_native_trigger_v2 import v2_sql,native_sql

def test_installer_verifies_real_new_schema_role_population_and_cross_db_denials(v2_sql):
 import psycopg
 admin,urls,_=v2_sql
 with psycopg.connect(admin) as c:INSTALL.verify_roles(c)
 # Only our disposable new login is temporarily drifted; retained v1 unchanged.
 try:
  with psycopg.connect(admin) as c:c.execute('GRANT oracle_native_v2_documentary_executor TO oracle_native_v2_executor WITH ADMIN OPTION')
  with psycopg.connect(admin) as c:
   with pytest.raises(PermissionError,match='membership differs'):INSTALL.verify_roles(c)
 finally:
  with psycopg.connect(admin) as c:c.execute('REVOKE ADMIN OPTION FOR oracle_native_v2_documentary_executor FROM oracle_native_v2_executor')
 with psycopg.connect(admin) as c:INSTALL.verify_roles(c)


def fake_issuer(tmp_path,monkeypatch):
 from types import SimpleNamespace
 head='a'*40;review=('reviewed commit `'+head+'`\nAPPROVE\n').encode();source=tmp_path/'source-review';source.write_bytes(review)
 action=tmp_path/'action-review';action.write_bytes(b'local fake action\nAPPROVE\n')
 ready=tmp_path/'readiness';ready.write_text(json.dumps({'source_head':head,'runtime_hash':'a'*64,'trigger_deployment_id':'deployment_invented','trigger_status':'DEPLOYED','trigger_task':IDENTITY['task'],'vercel_deployment_id':'dpl_Invented','vercel_status':'READY'}));ready.chmod(0o600);tmp_path.chmod(0o700)
 now=int(time.time());output=tmp_path/'new-permission';intent=tmp_path/'once-intent'
 argv=['issuer','--directory',str(output),'--runtime-hash','a'*64,'--source-review-file',str(source),'--review-hash',hashlib.sha256(review).hexdigest(),'--issued-at',str(now),'--expires-at',str(now+3600),'--readiness-file',str(ready),'--readiness-sha256',hashlib.sha256(ready.read_bytes()).hexdigest(),'--issuance-intent',str(intent),'--action-review-file',str(action),'--action-review-sha256',hashlib.sha256(action.read_bytes()).hexdigest()]
 monkeypatch.setattr(PREPARE.subprocess,'check_output',lambda args,**kw:head+'\n' if 'rev-parse' in args else '')
 monkeypatch.setattr(PREPARE.subprocess,'run',lambda *a,**k:SimpleNamespace(returncode=0))
 monkeypatch.setattr(PREPARE,'native_python_digest',lambda:'a'*64)
 monkeypatch.setattr(PREPARE.secrets,'token_hex',lambda n:'1'*(2*n));monkeypatch.setattr(PREPARE.secrets,'token_bytes',lambda n:b'x'*n)
 for env in ('ORACLE_NATIVE_DATABASE_CA','ORACLE_NATIVE_GRAPH_CA','ORACLE_NATIVE_GRAPH_CERT','ORACLE_NATIVE_GRAPH_KEY','ORACLE_NATIVE_GRAPH_EXECUTOR_PASSWORD'):monkeypatch.setenv(env,'invented-local-fixture-only')
 monkeypatch.setattr(sys,'argv',argv)
 return output,intent,argv


def test_issuer_local_fake_outputs_are_sealed_private_v2_only_and_nonrepeatable(tmp_path,monkeypatch,capsys):
 output,intent,argv=fake_issuer(tmp_path,monkeypatch);PREPARE.main()
 assert intent.exists() and output.stat().st_mode&0o777==0o700
 for p in output.iterdir():assert p.stat().st_mode&0o777==0o600
 receipt=json.loads((output/'permission-receipt.json').read_text());assert receipt['job_id']==IDENTITY['run'] and receipt['purpose']==IDENTITY['purpose'] and receipt['expires_at']-receipt['issued_at']==3600
 seed=(output/'seed.sql').read_text();assert 'oracle_synthetic_' not in seed
 population=seed+'\n'.join(INSTALL.compile_v2_migration(n).decode() for n in INSTALL.MIGRATIONS)
 assert all(role in population for role in INSTALL.ROLES)
 printed=capsys.readouterr().out
 assert '1'*64 not in printed and 'invented-local-fixture-only' not in printed
 # A different output directory still cannot bypass the same durable issuance intent.
 argv[argv.index('--directory')+1]=str(tmp_path/'other-output')
 with pytest.raises(FileExistsError):PREPARE.main()
 assert not (tmp_path/'other-output').exists()


@pytest.mark.parametrize('delta',[-1,1])
def test_issuer_rejects_any_horizon_change_before_output(tmp_path,monkeypatch,delta):
 output,intent,argv=fake_issuer(tmp_path,monkeypatch);i=argv.index('--expires-at')+1;argv[i]=str(int(argv[i])+delta)
 with pytest.raises(PermissionError,match='one-hour'):PREPARE.main()
 assert not intent.exists() and not output.exists()


def test_installer_recomputes_complete_sealed_seed_and_rejects_changed_bytes(tmp_path,monkeypatch):
 output,intent,argv=fake_issuer(tmp_path,monkeypatch);PREPARE.main()
 monkeypatch.setattr(INSTALL,'native_python_digest',lambda:'a'*64)
 # Dependency SQL lives in the separate core worktree during split implementation;
 # integrated source uses this same file layout without an override.
 import oracle_brain.hosting.native_trigger_v2_sql as mapped
 core_root=Path(mapped.__file__).resolve().parents[4]
 monkeypatch.setattr(INSTALL,'__file__',str(core_root/'dev/oracle2/hosting/install_native_trigger_v2.py'))
 r,seed,scripts=INSTALL.compiled_inputs(output,(tmp_path/'source-review').read_bytes())
 assert len(scripts)==9 and r['purpose']==IDENTITY['purpose']
 path=output/'seed.sql';path.write_bytes(seed+b'\n--changed')
 with pytest.raises(PermissionError,match='fixed seed changed'):INSTALL.compiled_inputs(output,(tmp_path/'source-review').read_bytes())
