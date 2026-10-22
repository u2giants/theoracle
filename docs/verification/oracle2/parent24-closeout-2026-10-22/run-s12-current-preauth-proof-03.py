"""PREPARED ONLY: root must release exact frozen source before any effect."""
import hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path
from xml.etree import ElementTree as ET
ROOT=Path('/tmp/oracle-parent24-wy02uT/workspace-preauth-current')
HEAD='7defd1eeeaccad46ba04b96952c439305065c796'
SCRATCH=Path('/tmp/oracle-parent24-wy02uT/s12-current-preauth-owned-proof-03')

def output(args,**kwargs):return subprocess.check_output(args,text=True,**kwargs).strip()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def complete_source_hashes():
    names=output(['git','ls-files'],cwd=ROOT).splitlines()
    return {name:sha(ROOT/name) for name in names if (ROOT/name).is_file()}

def main():
    if sys.argv[1:]!=['--execute-reviewed-head',HEAD]:raise PermissionError('exact frozen source invocation required')
    os.umask(0o077);assert output(['git','rev-parse','HEAD'],cwd=ROOT)==HEAD and not output(['git','status','--porcelain'],cwd=ROOT)
    SCRATCH.mkdir(mode=0o700)
    with (SCRATCH/'database-gate.txt').open('w') as log:subprocess.run(['ai-task-gates','check','--before','database'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
    sys.path[:0]=[str(ROOT),str(ROOT/'services/oracle-brain')]
    from dev.oracle2.test_worker_postgres_fixture import worker_postgres,owned_worker_database
    from dev.oracle2.test_readonly_graph_fixture import owned_target
    spec=importlib.util.spec_from_file_location('exact_verifier',ROOT/'scripts/oracle2/verify_workflow_integrity.py');verifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(verifier)
    complete_before=complete_source_hashes();(SCRATCH/'complete-source-before.json').write_text(json.dumps(complete_before,sort_keys=True,indent=2)+'\n')
    before=verifier.source_input_hashes();(SCRATCH/'source-before.json').write_text(json.dumps(before,sort_keys=True,indent=2)+'\n')
    (SCRATCH/'canonical-inventory.json').write_text(json.dumps({'head':HEAD,'migrations':verifier.SYNTHETIC_MIGRATIONS,'migration_sha256':{name:sha(ROOT/'services/oracle-brain/sql'/name) for name in verifier.SYNTHETIC_MIGRATIONS},'context_seconds':120,'admission_seconds':115,'request_max_seconds':30,'test_deadline_seconds':120,'canonical_owner':'dev.oracle2.test_canonical_schema','phase_owner':'owned_phase_database'},indent=2)+'\n')
    identity=None;result=None
    environment={k:os.environ[k] for k in ('PATH','HOME','TMPDIR','LANG','SHELL','PNPM_HOME','XDG_CACHE_HOME') if k in os.environ}
    try:
        with worker_postgres({**environment,'COMPOSE_PROJECT_NAME':'oracle2-synthetic-s12c03'},SCRATCH/'worker','documentary-99') as (tls,identity):
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
        (SCRATCH/'failure.json').write_text(json.dumps({'error_type':type(error).__name__,'message':str(error),'source_head':HEAD},indent=2)+'\n');raise
    finally:
        after=verifier.source_input_hashes();(SCRATCH/'source-after.json').write_text(json.dumps(after,sort_keys=True,indent=2)+'\n')
        if identity is None and (SCRATCH/'worker/ownership.json').exists():identity=json.loads((SCRATCH/'worker/ownership.json').read_text())
        if identity:
            remaining={kind:output(command+['--filter','label=com.docker.compose.project='+identity['project']]) for kind,command in [('containers',['docker','ps','-aq']),('networks',['docker','network','ls','-q']),('volumes',['docker','volume','ls','-q'])]}
            (SCRATCH/'cleanup.json').write_text(json.dumps({'identity':identity,'remaining':remaining,'absent':not any(remaining.values())},indent=2)+'\n')
            assert not any(remaining.values()),'owned cleanup not proven'
        complete_after=complete_source_hashes();(SCRATCH/'complete-source-after.json').write_text(json.dumps(complete_after,sort_keys=True,indent=2)+'\n')
        assert complete_before==complete_after,'complete tracked source drift'
        assert before==after,'complete executed source drift; preserve failed proof'
if __name__=='__main__':main()
