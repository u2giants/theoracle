#!/usr/bin/env python3
"""Staged synthetic proof. Missing tests and skips fail; acceptance stays separate."""
import argparse,hashlib,json,os,stat,subprocess,sys,tempfile
from importlib.metadata import version,PackageNotFoundError
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parents[2]
DOCUMENTARY=('operating_model_verifier','operating_model_boundary','operating_model_coverage','source_receipts','observation_identity','workflow_findings','artifact_storage','operating_model_extraction','operating_model_adapters','process_model','process_coverage','business_operating_model','workflow_lineage','operating_model_sdk','operating_model_retrieval','process_consult','operating_model_cutover','operating_model_restore','operating_model_pipeline','operating_model_native_provider','operating_model_answer','operating_model_summaries','operating_model_comparison','operating_model_retirement','operating_model_actions','operating_model_report_store','workflow_authorization','native_alternate','acceptance_profiles','semantic_acceptance','semantic_runtime','key_coverage','hosting_boundary','hosting_job_authority','hosting_startup','native_factory','provider_runtime','hosting_candidate_permissions','hosting_runtime_permissions','hosting_source_binding','hosting_readonly_projection','synthetic_control_fixtures','hosting_bootstrap','hosting_synthetic_fixture','hosting_result','hosting_synthetic_project','hosting_platform_translation','hosting_executor_jobs','hosting_forward_fixture','hosting_restore_receipts','hosting_forward_recovery','minimized_observations')
DOCUMENTARY += ('falkordb_coolify_plan','native_page_alternate','native_alternate_operator','native_alternate_chain_operator','hosting_restore_platform')
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

def main(argv=None):
    args=parse_options(argv)
    if args.mode!='synthetic':
        raise PermissionError('Independent private-audit admission is unavailable; synthetic proof cannot establish private semantic acceptance')
    required=required_suites(args.stage)
    paths=[ROOT/'services/oracle-brain/tests'/f'test_{name}.py' for name in required]
    missing=[p.name for p in paths if not p.is_file()]
    if missing:raise RuntimeError('required tests missing: '+','.join(missing))
    public_hashes=required_public_chain_hashes()
    admin=os.environ['ORACLE2_TEST_ADMIN_URL'];parts=psycopg.conninfo.conninfo_to_dict(admin)
    if parts.get('host') not in {'localhost','127.0.0.1'}:raise PermissionError('synthetic loopback proof required')
    name='oracle_operating_model_test_'+uuid4().hex
    with psycopg.connect(admin,autocommit=True) as conn:conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    target=psycopg.conninfo.make_conninfo(**{**parts,'dbname':name})
    report={'schema_version':1,'stage':args.stage,'mode':args.mode,'success':False,'synthetic':True,'business_accepted':False,'private_source_acceptance':'open','independent_semantic_acceptance':'open','actual_event_acceptance':'unavailable','analytical_runtime_qualified':False,'required_tests':[p.name for p in paths]}
    try:
        with psycopg.connect(target) as conn:
            for migration in ('001_foundation.sql','002_pilot.sql','004_workflow_integrity.sql'):conn.execute((ROOT/'services/oracle-brain/sql'/migration).read_text())
        with tempfile.TemporaryDirectory(prefix='oracle-workflow-proof-',dir=os.getenv('TMPDIR')) as tmp:
            junit=Path(tmp)/'junit.xml'
            env={**os.environ,'ORACLE2_TEST_ADMIN_URL':target,'PYTHONPATH':str(ROOT/'services/oracle-brain')}
            completed=subprocess.run([sys.executable,'-m','pytest',*map(str,paths),'-q','--tb=short',f'--junitxml={junit}'],cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=120)
            if not junit.exists():raise RuntimeError('required junit evidence missing')
            cases=ET.parse(junit).findall('.//testcase');skipped=sum(c.find('skipped') is not None for c in cases)
            failures=sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
            report.update(tests=len(cases),skipped=skipped,failures=failures,exit_code=completed.returncode)
            if completed.returncode or skipped or not cases or failures:
                print(completed.stdout[-6000:]);raise RuntimeError('required synthetic gate failed or skipped')
            report['versions']={package:version(package) for package in ('graphrag-sdk','langgraph','pydantic','psycopg')}
            report['head']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
            tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','services/oracle-brain/oracle_brain/operating_model','services/oracle-brain/tests','scripts/oracle2/verify_workflow_integrity.py','dev/oracle2/hosting/validate_falkordb_plan.py','dev/oracle2/hosting/golden','docs/implementation/falkordb-coolify-deploy-plan.md','scripts/oracle2/validate_analytical_associations.py','scripts/oracle2/contracts/analytical_source_associations.json','scripts/oracle2/analytical_source_packets.py','scripts/oracle2/test_analytical_source_packets.py','scripts/oracle2/validate_analytical_packet.py','scripts/oracle2/test_validate_analytical_packet.py','dev/oracle2/analytics'],cwd=ROOT,text=True).splitlines()
            hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in tracked if (ROOT/p).is_file()}
            current_public_hashes=required_public_chain_hashes()
            if current_public_hashes!=public_hashes:raise RuntimeError('required public source changed during tests')
            hashes.update(current_public_hashes)
            report['input_hash']=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()
            report['junit_sha256']=hashlib.sha256(junit.read_bytes()).hexdigest();report['success']=True
    finally:
        with psycopg.connect(admin,autocommit=True) as conn:
            conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s',(name,))
            conn.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        destination=ROOT/args.result;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text(json.dumps(report,indent=2)+'\n');destination.chmod(0o600)
    print(json.dumps({k:report[k] for k in ('stage','success','tests','skipped','business_accepted','analytical_runtime_qualified')}))
    return 0

if __name__=='__main__':raise SystemExit(main())
