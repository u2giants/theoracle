#!/usr/bin/env python3
"""W01: distinguish old list loss from infrastructure failure on owned stores."""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import time
import re
import xml.etree.ElementTree as ET
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BASELINES = {'main':'3bad33583787316d9fdddc3fd45a737b1236b4b1',
             'recovery':'36e91038ee6b1126f9d9c27adce7583a6b74c654'}
IMAGE = 'falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--result',type=Path,required=True);args=parser.parse_args()
    python=ROOT/'services/oracle-brain/.venv/bin/python'
    if not python.is_file(): parser.error('frozen environment required')
    receipt={'schema_version':1,'baselines':BASELINES,'image':IMAGE,'operator_attestation':{'paid_calls':0,'private_state_changed':False},'results':{}}
    with tempfile.TemporaryDirectory(prefix='oracle-w01-',dir=os.getenv('TMPDIR')) as scratch:
        scratch=Path(scratch);name='oracle-w01-'+uuid4().hex[:12];created=False
        try:
            subprocess.run(['docker','run','-d','--name',name,'--label','oracle.w01.synthetic=true','--memory','2g','--cpus','1','-p','127.0.0.1::6379','-e','FALKORDB_ARGS=--requirepass synthetic_w01_only',IMAGE],check=True,capture_output=True);created=True
            info=json.loads(subprocess.check_output(['docker','inspect',name]))[0]
            ports=info['NetworkSettings']['Ports']['6379/tcp']
            port=next(p['HostPort'] for p in ports if p['HostIp']=='127.0.0.1')
            for _ in range(40):
                p=subprocess.run(['docker','exec',name,'redis-cli','-a','synthetic_w01_only','ping'],capture_output=True,text=True)
                if p.returncode==0 and 'PONG' in p.stdout: break
                time.sleep(.25)
            else: raise RuntimeError('W01_INFRA_FAILURE: store readiness')
            for label,ref in BASELINES.items():
                target=scratch/label;target.mkdir()
                archive=subprocess.check_output(['git','archive',ref,'services/oracle-brain'],cwd=ROOT)
                with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(target,filter='data')
                env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','BASELINE_ROOT':str(target),'PYTHONPATH':str(target/'services/oracle-brain'),
                     'ORACLE2_TEST_FALKORDB_URL':f'redis://:synthetic_w01_only@127.0.0.1:{port}','W01_OWNED_CONTAINER':name}
                probe=ROOT/'evals/oracle2/workflow/legacy_loss_probe.py'
                p=subprocess.run([str(python),'-m','pytest',str(probe),'-q','-s','--tb=short'],cwd=target,env=env,capture_output=True,text=True)
                output=p.stdout+p.stderr
                loss=re.search(r'W01_EXPECTED_LOSS: actual SDK finalize/reload findings=(\d+)',output)
                verified=p.returncode==1 and bool(loss) and int(loss.group(1))==0 and 'W01_INFRA_FAILURE' not in output
                receipt['results'][label]={'exit':p.returncode,'expected_loss_verified':verified,'preserved_findings':int(loss.group(1)) if loss else None,'unexpected_pass':p.returncode==0 and 'W01_UNEXPECTED_PASS' in output,'output_sha256':hashlib.sha256(output.encode()).hexdigest(),'graph_scope':re.search(r'W01_GRAPH_SCOPE: ([^\n]+)',output).group(1) if re.search(r'W01_GRAPH_SCOPE: ([^\n]+)',output) else None,'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest()}
                if not verified:
                    if receipt['results'][label]['unexpected_pass']:raise RuntimeError('W01_UNEXPECTED_PASS: baseline changed')
                    raise RuntimeError('W01_INFRA_FAILURE: expected loss proof not obtained')
            assert receipt['results']['main']['graph_scope'] != receipt['results']['recovery']['graph_scope'], 'baseline graph namespaces overlap'
            recovery=scratch/'recovery';env['BASELINE_ROOT']=str(recovery);env['PYTHONPATH']=str(recovery/'services/oracle-brain')
            suites=['test_holistic_graphrag.py','test_holistic_graphrag_integration.py']
            p=subprocess.run([str(python),'-m','pytest',*[str(recovery/'services/oracle-brain/tests'/t) for t in suites],'-q','--tb=short','--junitxml='+str(scratch/'recovery.xml')],cwd=recovery,env=env,capture_output=True,text=True)
            output=p.stdout+p.stderr
            cases=list(ET.parse(scratch/'recovery.xml').getroot().iter('testcase'))
            skipped=sum(c.find('skipped') is not None for c in cases)
            failures=sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
            green=p.returncode==0 and bool(cases) and skipped==0 and failures==0
            receipt['results']['recovery_invariants']={'exit':p.returncode,'passed':green,'tests':suites,'passed_count':len(cases)-skipped-failures,'skipped_count':skipped,'test_names':[c.attrib['name'] for c in cases],'output_sha256':hashlib.sha256(output.encode()).hexdigest()}
            if not green:raise RuntimeError('W01_INFRA_FAILURE: recovery invariants failed')
            env['PYTHONPATH']=str(ROOT/'services/oracle-brain')
            boundary_suites=['test_operating_model_boundary.py','test_operating_model_coverage.py']
            p=subprocess.run([str(python),'-m','pytest',*[str(ROOT/'services/oracle-brain/tests'/f) for f in boundary_suites],'-q','--junitxml='+str(scratch/'boundary.xml')],cwd=ROOT,env=env,capture_output=True,text=True)
            cases=list(ET.parse(scratch/'boundary.xml').getroot().iter('testcase'))
            skipped=sum(c.find('skipped') is not None for c in cases)
            failures=sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
            receipt['boundary_tests']={'exit':p.returncode,'passed_count':len(cases)-skipped-failures,'skipped_count':skipped,'test_names':[c.attrib['name'] for c in cases],'output_sha256':hashlib.sha256((p.stdout+p.stderr).encode()).hexdigest()}
            if p.returncode or skipped or failures or not cases:raise RuntimeError('W01 boundary tests failed')
            receipt['passed']=True
        except Exception as exc:
            receipt.update(passed=False,failure=type(exc).__name__,failure_category='unexpected_pass' if 'W01_UNEXPECTED_PASS' in str(exc) else 'infra_or_gate_failure')
        finally:
            if created:
                cleanup=subprocess.run(['docker','rm','-f',name],capture_output=True,check=False)
                receipt['cleanup_passed']=cleanup.returncode==0
                if cleanup.returncode:receipt['passed']=False
    receipt['lock_sha256']=hashlib.sha256((ROOT/'services/oracle-brain/uv.lock').read_bytes()).hexdigest()
    receipt['executed_file_hashes']={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__),ROOT/'evals/oracle2/workflow/legacy_loss_probe.py',*[ROOT/'services/oracle-brain/tests'/n for n in ('test_operating_model_boundary.py','test_operating_model_coverage.py')],ROOT/'services/oracle-brain/oracle_brain/operating_model/boundary.py']}
    receipt['python']=subprocess.check_output([str(python),'--version'],text=True).strip()
    args.result.parent.mkdir(parents=True,exist_ok=True);args.result.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'passed':receipt['passed'],'expected_red_baselines':sum(r.get('expected_loss_verified',False) for r in receipt['results'].values()),'private_state_changed':False}))
    return 0 if receipt['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
