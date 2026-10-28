"""PREPARED ONLY; exact reviewed runner/source/approval and root release required."""
import hashlib,importlib.util,json,os,re,stat,subprocess,sys,time
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path('/tmp/oracle-parent24-wy02uT/workspace-preauth-current')
HEAD='7defd1eeeaccad46ba04b96952c439305065c796'
SCRATCH=Path('/tmp/oracle-parent24-wy02uT/s12-current-preauth-owned-proof-04')
BASE_PROJECT='oracle2-synthetic-s12c04'
LABEL='documentary-99'
EXPECTED_MANIFEST=Path('/tmp/oracle-parent24-wy02uT/s12-current-preauth-reviewed-source.json')
EXPECTED_MANIFEST_BYTES=215406
EXPECTED_MANIFEST_SHA='06e8b1ce008d8d23d305f75c58d7417a9e3d401e22b35a9158f3049a8e220e5f'

def output(args,**kwargs):return subprocess.check_output(args,text=True,timeout=15,**kwargs).strip()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def complete_sources():
    names=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=ROOT).split(b'\0')
    result={}
    for encoded in sorted(set(names)):
        if not encoded:continue
        name=os.fsdecode(encoded);path=ROOT/name
        if not path.is_file() or path.is_symlink():raise PermissionError('complete regular source census required')
        result[name]=sha(path)
    return result

def retained_owner():
    path=SCRATCH/'worker/ownership.json';s=path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_nlink!=1 or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o600 or s.st_size>8192:
        raise PermissionError('actual retained private ownership receipt required')
    value=json.loads(path.read_bytes())
    if (type(value) is not dict or set(value)!={'project','container_id','port','worker','synthetic_only'}
        or type(value['project']) is not str or re.fullmatch(re.escape(BASE_PROJECT)+r'-w[0-9a-f]{12}',value['project']) is None
        or type(value['container_id']) is not str or re.fullmatch(r'[0-9a-f]{64}',value['container_id']) is None
        or type(value['port']) is not int or not 1<=value['port']<=65535 or value['worker']!=LABEL or value['synthetic_only'] is not True):
        raise PermissionError('actual retained fixed worker identity differs')
    return value

def main():
    os.umask(0o077);SCRATCH.mkdir(mode=0o700)
    before=None;identity=None;result=None;verifier=None
    try:
        if len(sys.argv)!=3 or sha(__file__)!=sys.argv[2]:raise PermissionError('exact review receipt and reviewed runner digest required')
        review=Path(sys.argv[1]);review_sha=sha(review)
        if output(['git','rev-parse','HEAD'],cwd=ROOT)!=HEAD or output(['git','status','--porcelain','--untracked-files=all'],cwd=ROOT):
            raise PermissionError('clean exact frozen source required')
        with EXPECTED_MANIFEST.open('rb') as source:raw=source.read(EXPECTED_MANIFEST_BYTES+1)
        if len(raw)!=EXPECTED_MANIFEST_BYTES or hashlib.sha256(raw).hexdigest()!=EXPECTED_MANIFEST_SHA:
            raise PermissionError('independently frozen source manifest bytes changed')
        expected=json.loads(raw);before=complete_sources()
        (SCRATCH/'complete-source-before.json').write_text(json.dumps(before,sort_keys=True,indent=2)+'\n')
        if before!=expected:raise PermissionError('complete source differs from reviewed manifest')
        (SCRATCH/'reviewed-inputs.json').write_text(json.dumps({'head':HEAD,'runner_sha256':sys.argv[2],'manifest_sha256':EXPECTED_MANIFEST_SHA,'manifest_bytes':EXPECTED_MANIFEST_BYTES,'review_receipt_sha256':review_sha},indent=2)+'\n')
        with (SCRATCH/'database-gate.txt').open('w') as log:
            subprocess.run(['ai-task-gates','check','--before','database','--reviewer-approval',str(review)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        if sha(review)!=review_sha:raise PermissionError('actual review receipt changed at gate')
        sys.path[:0]=[str(ROOT),str(ROOT/'services/oracle-brain')]
        from dev.oracle2.test_worker_postgres_fixture import worker_postgres,owned_worker_database
        from dev.oracle2.test_readonly_graph_fixture import owned_target
        spec=importlib.util.spec_from_file_location('exact_verifier',ROOT/'scripts/oracle2/verify_workflow_integrity.py');verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
        (SCRATCH/'canonical-inventory.json').write_text(json.dumps({'head':HEAD,'migrations':verifier.SYNTHETIC_MIGRATIONS,'migration_sha256':{name:sha(ROOT/'services/oracle-brain/sql'/name) for name in verifier.SYNTHETIC_MIGRATIONS},'context_seconds':120,'admission_seconds':115,'request_max_seconds':30,'test_deadline_seconds':120,'canonical_owner':'dev.oracle2.test_canonical_schema','phase_owner':'owned_phase_database'},indent=2)+'\n')
        environment={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','LANG','SHELL','PNPM_HOME','XDG_CACHE_HOME') if k in os.environ}
        with worker_postgres({**environment,'COMPOSE_PROJECT_NAME':BASE_PROJECT},SCRATCH/'worker',LABEL) as (tls,identity):
            owned_worker_database(identity['container_id'],tls['ORACLE2_TEST_ADMIN_URL'])
            env={**environment,**tls,'COMPOSE_PROJECT_NAME':identity['project'],'ORACLE2_CANDIDATE_PORT':'0','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(ROOT/'services/oracle-brain')+':'+str(ROOT/'services/oracle-brain/tests')+':'+str(ROOT),'GRAPHITI_TELEMETRY_ENABLED':'false','ORACLE2_TELEMETRY_MODE':'off','OPENBLAS_NUM_THREADS':'1','OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','NUMEXPR_NUM_THREADS':'1'}
            compose=['docker','compose','-f',str(ROOT/'dev/oracle2/compose.yaml'),'-p',identity['project']]
            with (SCRATCH/'graph-setup.txt').open('w') as log:subprocess.run([*compose,'up','-d','--wait','falkor-candidate'],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=60,check=True)
            graph_container=output([*compose,'ps','-q','falkor-candidate'],env=env)
            details=json.loads(output(['docker','inspect',graph_container]))[0];ports=details['NetworkSettings']['Ports']['6379/tcp']
            assert details['Id']==graph_container and details['Config']['Labels']['com.docker.compose.project']==identity['project'] and details['Config']['Labels']['com.docker.compose.service']=='falkor-candidate'
            assert set(details['NetworkSettings']['Networks'])=={identity['project']+'_default'} and len(ports)==1 and ports[0]['HostIp']=='127.0.0.1'
            graph='redis://:oracle2_candidate_local_only@127.0.0.1:'+ports[0]['HostPort'];env['ORACLE2_OPERATING_TEST_GRAPH_URL']=graph
            prior=os.environ.get('COMPOSE_PROJECT_NAME');os.environ['COMPOSE_PROJECT_NAME']=identity['project']
            try:owned_target(graph_container,graph)
            finally:
                if prior is None:os.environ.pop('COMPOSE_PROJECT_NAME',None)
                else:os.environ['COMPOSE_PROJECT_NAME']=prior
            command=[sys.executable,'-m','pytest','services/oracle-brain/tests/test_workspace_next_recipients_sql_v1.py','-q','--tb=short','--basetemp='+str(SCRATCH/'pytest-owned'),'--junitxml='+str(SCRATCH/'workspace-two-recipients.xml')]
            jobs=[{'name':'workspace-two-recipients','command':command,'env':env}]
            # SAME existing absolute group owner handles process groups/timeout;
            # this is a focused9-case proof, not a full W10 acceptance claim.
            results,cleanup=verifier.run_test_groups(jobs,SCRATCH,deadline=time.monotonic()+120)
            aggregate=verifier.aggregate_evidence(jobs,results,SCRATCH)
            result={'identity':identity,'graph_container':graph_container,'workers':results,'worker_cleanup':cleanup,'aggregate':aggregate}
            (SCRATCH/'result.json').write_text(json.dumps(result,indent=2)+'\n')
            totals={key:sum(int(s.get(key,'0')) for s in ET.parse(SCRATCH/'workspace-two-recipients.xml').getroot().iter('testsuite')) for key in ('tests','failures','errors','skipped')}
            assert totals=={'tests':9,'failures':0,'errors':0,'skipped':0},totals
            assert aggregate['exit_code']==0 and not cleanup,result
    except BaseException as error:
        (SCRATCH/'failure.json').write_text(json.dumps({'error_type':type(error).__name__,'source_head':HEAD},indent=2)+'\n')
        raise
    finally:
        errors=[];after=None
        try:
            after=complete_sources();(SCRATCH/'complete-source-after.json').write_text(json.dumps(after,sort_keys=True,indent=2)+'\n')
        except BaseException as error:
            errors.append('source-after:'+type(error).__name__)
            (SCRATCH/'complete-source-after-unknown.json').write_text(json.dumps({'observation':'UNKNOWN','error_type':type(error).__name__})+'\n')
        cleanup={'observation':'UNKNOWN','absence_proven':False,'source_manifest_unchanged':before is not None and before==after}
        try:
            retained=retained_owner()
            if identity is not None and identity!=retained:raise PermissionError('yielded/retained actual worker ownership differs')
            remaining={kind:output(command+['--filter','label=com.docker.compose.project='+retained['project']]) for kind,command in [('containers',['docker','ps','-aq']),('networks',['docker','network','ls','-q']),('volumes',['docker','volume','ls','-q'])]}
            cleanup.update(identity=retained,remaining=remaining,observation='observed',absence_proven=not any(remaining.values()))
            if not cleanup['absence_proven']:errors.append('actual owned resources remain')
        except BaseException as error:
            errors.append('ownership/absence:'+type(error).__name__)
        (SCRATCH/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
        if before is None or after!=before:errors.append('complete reviewed source equality not proven')
        if errors:raise PermissionError('proof unverified: '+';'.join(errors))
if __name__=='__main__':main()
