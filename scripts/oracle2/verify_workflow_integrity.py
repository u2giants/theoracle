#!/usr/bin/env python3
"""Staged synthetic proof. Missing tests and skips fail; acceptance stays separate."""
import argparse,hashlib,json,os,subprocess,sys,tempfile
from importlib.metadata import version,PackageNotFoundError
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET
import psycopg
from psycopg import sql

ROOT=Path(__file__).resolve().parents[2]
DOCUMENTARY=('operating_model_verifier','operating_model_boundary','operating_model_coverage','source_receipts','observation_identity','workflow_findings','artifact_storage','operating_model_extraction','operating_model_adapters','process_model','process_coverage','business_operating_model','workflow_lineage','operating_model_sdk','operating_model_retrieval','process_consult','operating_model_cutover','operating_model_restore','operating_model_pipeline','operating_model_native_provider','operating_model_answer','operating_model_summaries','operating_model_comparison','operating_model_retirement','operating_model_actions','operating_model_report_store','workflow_authorization','semantic_acceptance','semantic_runtime','key_coverage','hosting_boundary','hosting_job_authority','hosting_startup','native_factory','provider_runtime','hosting_candidate_permissions','hosting_runtime_permissions','hosting_source_binding')
EVENT=('operational_event_store','operational_export','process_analysis','pm4py_adapter','pm4py_integration')

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
            tracked=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','services/oracle-brain/oracle_brain/operating_model','services/oracle-brain/tests','scripts/oracle2/verify_workflow_integrity.py'],cwd=ROOT,text=True).splitlines()
            hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in tracked if (ROOT/p).is_file()}
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
