#!/usr/bin/env python3
"""Staged synthetic proof. Missing tests and skips fail; acceptance stays separate."""
import argparse,hashlib,json,os,stat,subprocess,sys,tempfile,time
import psutil
from importlib.metadata import version,PackageNotFoundError
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parents[2]
DOCUMENTARY=('operating_model_verifier','operating_model_boundary','operating_model_coverage','source_receipts','observation_identity','workflow_findings','artifact_storage','operating_model_extraction','operating_model_adapters','process_model','process_coverage','business_operating_model','workflow_lineage','operating_model_sdk','operating_model_retrieval','process_consult','operating_model_cutover','operating_model_restore','operating_model_pipeline','operating_model_native_provider','operating_model_answer','operating_model_summaries','operating_model_comparison','operating_model_retirement','operating_model_actions','operating_model_report_store','workflow_authorization','native_alternate','acceptance_profiles','semantic_acceptance','semantic_runtime','key_coverage','hosting_boundary','hosting_job_authority','hosting_startup','native_factory','provider_runtime','hosting_candidate_permissions','hosting_runtime_permissions','hosting_source_binding','hosting_readonly_projection','synthetic_control_fixtures','hosting_bootstrap','hosting_synthetic_fixture','hosting_result','hosting_synthetic_project','hosting_platform_translation','hosting_executor_jobs','hosting_forward_fixture','hosting_restore_receipts','hosting_forward_recovery','minimized_observations')
DOCUMENTARY += ('replacement_documentary_journey', 'processing_context', 'processing_profile',
                'assembly_context','assembly_qualification','observed_assembly_capture',
                'source_processing_qualification','processing_compiler_capabilities',
                'processing_projection_leases','processing_documentary_journey')
PURPOSE_V2_SUITES=('purpose_context_v2','parent_observer_v2','purpose_profiles_v2',
    'purpose_assembly_v2','purpose_capture_v2','purpose_qualification_v3','purpose_receipts_v2',
    'purpose_runtime_v2','purpose_source_authority','purpose_transport','purpose_transport_startup',
    'purpose_shared_budget','purpose_allocation_budget','semantic_registry_v3',
    'processing_extraction_runtime_v2','extraction_connection_authority','purpose_native_census_startup','purpose_journey','purpose_worker_startup','paid_sdk_embeddings_v3')
DOCUMENTARY += PURPOSE_V2_SUITES
DOCUMENTARY += ('falkordb_coolify_plan','native_page_alternate','native_alternate_operator','native_alternate_chain_operator','hosting_restore_platform')
SYNTHETIC_MIGRATIONS=('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql',
    '006_hosting_gateway_authority.sql','007_hosting_candidate_permissions.sql',
    '008_hosting_runtime_permissions.sql','009_hosting_result_permissions.sql',
    '010_hosting_job_permissions.sql','011_hosting_source_processing_permissions.sql',
    '012_processing_compiler_capabilities.sql','013_processing_purpose_permissions.sql')
EVENT=('operational_event_store','operational_export','process_analysis','pm4py_adapter','pm4py_integration','derived_event_lineage','analytical_source_packets')
PUBLIC_CHAIN=('scripts/oracle2/native_alternate_operator.py','scripts/oracle2/native_alternate_chain_operator.py','scripts/oracle2/contracts/native_alternate_serialization.json','scripts/oracle2/contracts/native_alternate_chain_v2.json')
PUBLIC_SOURCE_LIMIT=8*1024**2

def source_stat(info):
    return tuple(getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))

def public_source_parent(relative):
    if relative not in PUBLIC_CHAIN:raise RuntimeError('unknown public chain source')
    path=ROOT/relative
    if not path.is_absolute() or '..' in path.parts:raise RuntimeError('noncanonical public source root')
    fd=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_PATH|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        info=os.stat(path.name,dir_fd=fd,follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<info.st_size<=PUBLIC_SOURCE_LIMIT:
            raise RuntimeError('public chain member must be bounded regular unaliased source')
        return fd,path.name,info
    except BaseException:
        os.close(fd);raise

def required_public_chain_hashes():
    """All four members pass metadata-only preflight before any byte hashing."""
    prepared={};hashes={}
    try:
        for relative in PUBLIC_CHAIN:prepared[relative]=public_source_parent(relative)
        for relative,(parent,name,before) in prepared.items():
            fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent)
            try:
                if source_stat(os.fstat(fd))!=source_stat(before):raise RuntimeError('public source changed before hashing')
                digest=hashlib.sha256();remaining=before.st_size
                while remaining:
                    chunk=os.read(fd,min(65536,remaining))
                    if not chunk:raise RuntimeError('public source truncated while hashing')
                    digest.update(chunk);remaining-=len(chunk)
                if os.read(fd,1) or source_stat(os.fstat(fd))!=source_stat(before) or source_stat(os.stat(name,dir_fd=parent,follow_symlinks=False))!=source_stat(before):
                    raise RuntimeError('public source changed during hashing')
                hashes[relative]=digest.hexdigest()
            finally:os.close(fd)
        return hashes
    finally:
        for parent,_,_ in prepared.values():os.close(parent)
EVENT += ('analytical_associations',)

def parse_options(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--stage',choices=('documentary','event','all',*(f'W{i:02d}' for i in range(1,13))),required=True)
    parser.add_argument('--mode',choices=('synthetic','private-audit'),default='synthetic')
    parser.add_argument('--result',default='out/oracle2/workflow-integrity.json')
    return parser.parse_args(argv)

def required_suites(stage):
    if stage in {'documentary','W02','W03','W05','W06'}:return DOCUMENTARY
    if stage in {'event','W04','W07','W08'}:return EVENT
    return DOCUMENTARY+EVENT

def test_groups(stage):
    required=required_suites(stage)
    groups=(('documentary',DOCUMENTARY),('event',EVENT)) if required==DOCUMENTARY+EVENT else (('required',required),)
    flattened=tuple(suite for _,suites in groups for suite in suites)
    if flattened!=required or len(set(flattened))!=len(flattened):
        raise RuntimeError('required suite population is duplicated or omitted')
    return groups


def stop_owned_workers(workers):
    """Only children of Popen handles created by this verifier are signalled."""
    errors=[];owned=[]
    for worker in workers:
        if worker.poll() is not None:continue
        try:
            parent=psutil.Process(worker.pid)
            owned.extend(reversed(parent.children(recursive=True)));owned.append(parent)
        except psutil.NoSuchProcess:pass
        except psutil.Error:errors.append('owned worker tree inspection failed')
    for process in owned:
        try:process.terminate()
        except psutil.NoSuchProcess:pass
        except psutil.Error:errors.append('owned worker termination failed')
    _,alive=psutil.wait_procs(owned,timeout=2)
    for process in alive:
        try:process.kill()
        except psutil.NoSuchProcess:pass
        except psutil.Error:errors.append('owned worker kill failed')
    _,alive=psutil.wait_procs(alive,timeout=2)
    if alive:errors.append('owned worker survived cleanup')
    for worker in workers:
        try:worker.wait(timeout=2)
        except subprocess.TimeoutExpired:errors.append('owned worker was not reaped')
    return errors


def run_test_groups(jobs,directory,*,deadline):
    """All workers share the one caller-owned monotonic test deadline."""
    workers=[];streams=[];results=[];cleanup=[];launch_error=False
    try:
        for job in jobs:
            path=directory/(job['name']+'.stdout')
            stream=path.open('xb');path.chmod(0o600);streams.append(stream)
            try:
                worker=subprocess.Popen(job['command'],cwd=ROOT,env=job['env'],stdout=stream,
                    stderr=subprocess.STDOUT,start_new_session=True)
            except OSError:
                launch_error=True;break
            workers.append(worker)
        timed_out=False
        if launch_error:cleanup.extend(stop_owned_workers(workers))
        for worker in workers:
            remaining=max(0,deadline-time.monotonic())
            try:worker.wait(timeout=remaining)
            except subprocess.TimeoutExpired:timed_out=True;break
        if time.monotonic()>deadline:timed_out=True
        if timed_out:cleanup.extend(stop_owned_workers(workers))
        for index,job in enumerate(jobs):
            worker=workers[index] if index<len(workers) else None
            results.append({'name':job['name'],'exit_code':worker.returncode if worker else None,
                'timed_out':timed_out,'launch_error':launch_error})
        return results,cleanup
    finally:
        if any(worker.poll() is None for worker in workers):cleanup.extend(stop_owned_workers(workers))
        for stream in streams:stream.close()


def aggregate_evidence(jobs,results,directory):
    combined=ET.Element('testsuites');tests=skips=failures=0;invalid=[]
    if len(results)!=len(jobs):invalid.append('worker population incomplete')
    for job,result in zip(jobs,results):
        output=directory/(job['name']+'.stdout');junit=directory/(job['name']+'.xml')
        result['stdout_sha256']=hashlib.sha256(output.read_bytes()).hexdigest() if output.is_file() else None
        if not output.is_file():invalid.append('required worker output missing')
        result['junit_present']=junit.is_file()
        if result['timed_out'] or result.get('launch_error') or result['exit_code']!=0:invalid.append('worker did not complete successfully')
        if not junit.is_file():invalid.append('required junit evidence missing');continue
        junit.chmod(0o600);raw=junit.read_bytes();result['junit_sha256']=hashlib.sha256(raw).hexdigest()
        try:root=ET.fromstring(raw)
        except ET.ParseError:invalid.append('required junit evidence malformed');continue
        cases=root.findall('.//testcase')
        if not cases:invalid.append('required worker cases missing')
        count_skips=sum(c.find('skipped') is not None for c in cases)
        count_failures=sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
        tests+=len(cases);skips+=count_skips;failures+=count_failures
        result.update(tests=len(cases),skipped=count_skips,failures=count_failures)
        combined.append(root)
    if skips or failures:invalid.append('required synthetic gate failed or skipped')
    return {'tests':tests,'skipped':skips,'failures':failures,'exit_code':int(bool(invalid)),
        'junit_sha256':hashlib.sha256(ET.tostring(combined)).hexdigest(),'worker_results':results,
        'evidence_errors':invalid}


def cleanup_test_databases(admin,parts,owned):
    errors=[]
    for name in owned:
        try:
            with psycopg.connect(admin,autocommit=True) as conn:
                if conn.execute('SELECT current_database()').fetchone()[0]!=parts.get('dbname','postgres'):
                    raise PermissionError('actual cleanup administrator target differs')
                conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s',(name,))
                conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        except Exception:errors.append({'database':name,'reason':'owned database cleanup failed'})
    return errors



SOURCE_INPUT_PATHS=('services/oracle-brain/oracle_brain','services/oracle-brain/tests','services/oracle-brain/sql','dev/oracle2/compose.yaml','dev/oracle2/test_tls_bootstrap.py','dev/oracle2/test_readonly_graph_fixture.py','dev/oracle2/test_graph_tls_fixture.py','scripts/oracle2/verify_workflow_integrity.py','dev/oracle2/hosting/validate_falkordb_plan.py','dev/oracle2/hosting/golden','docs/implementation/falkordb-coolify-deploy-plan.md','scripts/oracle2/validate_analytical_associations.py','scripts/oracle2/contracts/analytical_source_associations.json','scripts/oracle2/analytical_source_packets.py','scripts/oracle2/test_analytical_source_packets.py','scripts/oracle2/test_validate_analytical_packet.py','dev/oracle2/analytics')



def source_input_hashes():
    """Deterministic owned source inventory; ignored caches/private inputs stay out."""
    tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z',
        *SOURCE_INPUT_PATHS],cwd=ROOT).split(b'\0')
    hashes={}
    for encoded in sorted(set(tracked)):
        if not encoded:continue
        relative=os.fsdecode(encoded);path=ROOT/relative
        if (any(p in {'__pycache__','.cache','.ai'} for p in Path(relative).parts)
                or path.suffix in {'.pyc','.pyo'} or path.name.startswith('.env')):continue
        if path.is_file():hashes[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes

def main(argv=None):
    args=parse_options(argv)
    if args.mode!='synthetic':
        raise PermissionError('Independent private-audit admission is unavailable; synthetic proof cannot establish private semantic acceptance')
    required=required_suites(args.stage);groups=test_groups(args.stage)
    paths=[ROOT/'services/oracle-brain/tests'/f'test_{name}.py' for name in required]
    missing=[p.name for p in paths if not p.is_file()]
    if missing:raise RuntimeError('required tests missing: '+','.join(missing))
    public_hashes=required_public_chain_hashes()
    admin=os.environ['ORACLE2_TEST_ADMIN_URL'];parts=psycopg.conninfo.conninfo_to_dict(admin)
    if parts.get('host') not in {'localhost','127.0.0.1'}:raise PermissionError('synthetic loopback proof required')
    destination=ROOT/args.result;destination.parent.mkdir(parents=True,exist_ok=True)
    evidence=Path(tempfile.mkdtemp(prefix='workflow-evidence-',dir=destination.parent));evidence.chmod(0o700)
    report={'schema_version':1,'stage':args.stage,'mode':args.mode,'success':False,'synthetic':True,'business_accepted':False,'private_source_acceptance':'open','independent_semantic_acceptance':'open','actual_event_acceptance':'unavailable','analytical_runtime_qualified':False,'required_tests':[p.name for p in paths],'worker_evidence':str(evidence),'cleanup_errors':[]}
    owned=[]
    try:
        jobs=[]
        # Setup remains outside the existing 120-second TEST budget. Every group
        # gets its own proven fresh DB before any worker starts; EVENT has no
        # fixed-role mutations, shared advisory locks or graph operations.
        for label,suites in groups:
            name='oracle_operating_model_test_'+uuid4().hex
            with psycopg.connect(admin,autocommit=True) as conn:
                if conn.execute('SELECT current_database()').fetchone()[0]!=parts.get('dbname','postgres'):
                    raise PermissionError('actual synthetic administrator target differs')
                conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
            owned.append(name);target=psycopg.conninfo.make_conninfo(**{**parts,'dbname':name})
            with psycopg.connect(target) as conn:
                if conn.execute('SELECT current_database()').fetchone()[0]!=name:
                    raise PermissionError('actual fresh synthetic target differs')
                for migration in SYNTHETIC_MIGRATIONS:conn.execute((ROOT/'services/oracle-brain/sql'/migration).read_text())
            command=[sys.executable,'-m','pytest',*[str(ROOT/'services/oracle-brain/tests'/f'test_{n}.py') for n in suites],'-q','--tb=short',f'--junitxml={evidence/(label+".xml")}']
            jobs.append({'name':label,'command':command,'env':{**os.environ,'ORACLE2_TEST_ADMIN_URL':target,'PYTHONPATH':str(ROOT/'services/oracle-brain')}})
        results,worker_cleanup=run_test_groups(jobs,evidence,deadline=time.monotonic()+120)
        report['cleanup_errors'].extend(worker_cleanup)
        report.update(aggregate_evidence(jobs,results,evidence))
        report['versions']={package:version(package) for package in ('graphrag-sdk','langgraph','pydantic','psycopg')}
        report['head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        hashes=source_input_hashes()
        current_public_hashes=required_public_chain_hashes()
        if current_public_hashes!=public_hashes:raise RuntimeError('required public source changed during tests')
        hashes.update(current_public_hashes)
        report['input_hash']=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
        report['success']=report['exit_code']==0 and not report['cleanup_errors']
    finally:
        report['owned_databases']=owned
        report['cleanup_errors'].extend(cleanup_test_databases(admin,parts,owned))
        if report['cleanup_errors']:report['success']=False
        destination.write_text(json.dumps(report,indent=2)+'\n');destination.chmod(0o600)
    print(json.dumps({k:report.get(k) for k in ('stage','success','tests','skipped','business_accepted','analytical_runtime_qualified')}))
    return 0 if report['success'] else 1

if __name__=='__main__':raise SystemExit(main())
