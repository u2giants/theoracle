"""Prepared source-only; invocation requires exact independent review and root go."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
from uuid import uuid4
root=Path('/tmp/oracle-parent24-wy02uT/recovery-startup-intent')
scratch=Path('/tmp/oracle-parent24-wy02uT/recovery-metadata-owned-sql-09')
sys.path.insert(0,str(root))

def complete_sources():
 paths=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root).split(b'\0')
 result={}
 for encoded in sorted(set(paths)):
  if not encoded:continue
  name=os.fsdecode(encoded);p=root/name
  if p.is_file():result[name]=hashlib.sha256(p.read_bytes()).hexdigest()
 result['EXTERNAL_FIXED_PROOF_HARNESS']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 return result

# Expected source is frozen BEFORE gate; root's independently reviewed
# invocation supplies the exact sibling harness SHA to avoid a self-hash cycle.
EXPECTED_HEAD='2633c53baadec2d2bbde586a4a13e1b2ba9e79fd'
EXPECTED_REPOSITORY_MANIFEST='/tmp/oracle-parent24-wy02uT/s13-startup-repository-manifest.json'
EXPECTED_REPOSITORY_MANIFEST_SHA='2f391577624bf8f619f0437cafd73eb75604c35e49952186abfba2290fa8adaf'
EXPECTED_REPOSITORY_MANIFEST_BYTES=218010
if len(sys.argv)!=3:raise PermissionError('exact review receipt and reviewed harness digest required')
if hashlib.sha256(Path(__file__).read_bytes()).hexdigest()!=sys.argv[2]:raise PermissionError('reviewed fixed harness bytes changed')
if subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()!=EXPECTED_HEAD:raise PermissionError('exact frozen recovery proof HEAD required')
if subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True).strip():raise PermissionError('clean exact recovery proof source required')
with open(EXPECTED_REPOSITORY_MANIFEST,'rb') as f:expected_raw=f.read(EXPECTED_REPOSITORY_MANIFEST_BYTES+1)
if len(expected_raw)!=EXPECTED_REPOSITORY_MANIFEST_BYTES or hashlib.sha256(expected_raw).hexdigest()!=EXPECTED_REPOSITORY_MANIFEST_SHA:raise PermissionError('independently reviewed complete source manifest changed')
expected=json.loads(expected_raw)
actual=complete_sources();actual.pop('EXTERNAL_FIXED_PROOF_HARNESS')
if actual!=expected:raise PermissionError('complete source differs from frozen reviewed manifest')

os.umask(0o077);scratch.mkdir(mode=0o700)
manifest=complete_sources();(scratch/'complete-source-manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n')
with (scratch/'database-gate.txt').open('w') as f:
 subprocess.run(['ai-task-gates','check','--before','database','--reviewer-approval',sys.argv[1]],cwd=root,stdout=f,stderr=subprocess.STDOUT,check=True)
# No Docker/SQL/resource effect is started until that exact genuine gate ALLOW.
from dev.oracle2.test_worker_postgres_fixture import worker_postgres,owned_worker_database,worker_startup_intent
import psycopg
from psycopg import sql
identity=None
try:
 with worker_postgres({**os.environ,'COMPOSE_PROJECT_NAME':'oracle2-synthetic-p24rec-01a16013'},scratch/'worker','documentary-01') as (tls,identity):
  base=tls['ORACLE2_TEST_ADMIN_URL'];owned_worker_database(identity['container_id'],base)
  name='oracle_operating_model_test_'+uuid4().hex
  with psycopg.connect(base,autocommit=True,connect_timeout=2,options='-c statement_timeout=5000 -c lock_timeout=2000') as c:
   c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
  url=psycopg.conninfo.make_conninfo(base,dbname=name);owned_worker_database(identity['container_id'],url)
  env={**os.environ,**tls,'COMPOSE_PROJECT_NAME':identity['project'],'ORACLE2_TEST_ADMIN_URL':url,'ORACLE2_WORKER_CONTAINER_ID':identity['container_id'],'ORACLE2_SYNTHETIC_POSTGRES_CONTAINER':identity['container_id'],'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(root/'services/oracle-brain')+':'+str(root/'services/oracle-brain/tests')+':'+str(root)}
  # Session admin fixture invokes ONE canonical owner/bootstrap on fresh UUID DB.
  # No parent migration loop, fixture replay, bare-oracle2 shortcut or graph ACK.
  args=[sys.executable,'-m','pytest','services/oracle-brain/tests/test_recovery_authority_sql_v1.py','-q','--tb=short','-p','no:cacheprovider','--basetemp='+str(scratch/'pytest-owned'),'--junitxml='+str(scratch/'pytest.xml')]
  with (scratch/'pytest.txt').open('w') as f:result=subprocess.run(args,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=120)
  unchanged=manifest==complete_sources()
  (scratch/'result.json').write_text(json.dumps({'returncode':result.returncode,'database':name,'source_manifest_unchanged':unchanged,'metadata_only':True,'native_dump_restore':False,'archive_child':False,'provider':False,'identity':identity},indent=2)+'\n')
  assert unchanged,'complete source changed during actual proof'
  assert result.returncode==0,'actual proof failed; retain private receipt'
  import xml.etree.ElementTree as ET
  totals={k:sum(int(s.get(k,0)) for s in ET.parse(scratch/'pytest.xml').getroot().iter('testsuite')) for k in ('tests','failures','errors','skipped')}
  assert totals['tests']==27 and all(totals[k]==0 for k in ('failures','errors','skipped')),totals
  print('EXACT_JUNIT',totals)
finally:
 # Capture every public tracked/untracked source plus this harness on startup
 # failures too. No successful yield is needed to retain the exact project owner.
 after=complete_sources()
 (scratch/'complete-source-after.json').write_text(json.dumps(after,sort_keys=True,indent=2)+'\n')
 try:
  retained=worker_startup_intent(scratch/'worker','oracle2-synthetic-p24rec-01a16013','documentary-01')
  if identity is not None and retained['project']!=identity['project']:
   raise PermissionError('yielded and retained worker ownership differ')
  project=retained['project']
  remains={kind:bool(subprocess.check_output(cmd+['--filter','label=com.docker.compose.project='+project],text=True).strip()) for kind,cmd in [('containers',['docker','ps','-aq']),('networks',['docker','network','ls','-q']),('volumes',['docker','volume','ls','-q'])]}
 except BaseException:
  (scratch/'cleanup.json').write_text(json.dumps({'observation':'UNKNOWN','absence_proven':False,'source_manifest_unchanged':manifest==after})+'\n')
  raise
 (scratch/'cleanup.json').write_text(json.dumps({'project':project,'retained_startup_owner':True,'remaining':remains,'absence_proven':not any(remains.values()),'source_manifest_unchanged':manifest==after})+'\n')
 print('EXACT_OWNED_CLEANUP',not any(remains.values()))
 assert not any(remains.values()),'owned resources remain'
 assert manifest==after,'complete source changed during actual proof'
