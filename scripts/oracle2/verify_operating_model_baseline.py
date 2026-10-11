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
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
BASELINES = {'main':'3bad33583787316d9fdddc3fd45a737b1236b4b1',
             'recovery':'36e91038ee6b1126f9d9c27adce7583a6b74c654'}
IMAGE = 'falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--result',type=Path,required=True);args=parser.parse_args()
    python=ROOT/'services/oracle-brain/.venv/bin/python'
    if not python.is_file(): parser.error('frozen environment required')
    receipt={'schema_version':1,'baselines':BASELINES,'image':IMAGE,'paid_calls':0,'private_state_changed':False,'results':{}}
    with tempfile.TemporaryDirectory(prefix='oracle-w01-',dir=os.getenv('TMPDIR')) as scratch:
        scratch=Path(scratch);name='oracle-w01-'+uuid4().hex[:12];created=False
        try:
            subprocess.run(['docker','run','-d','--name',name,'--label','oracle.w01.synthetic=true','--memory','2g','--cpus','1','-p','127.0.0.1::6379','-e','FALKORDB_ARGS=--requirepass synthetic_w01_only',IMAGE],check=True,capture_output=True);created=True
            port=subprocess.check_output(['docker','port',name,'6379/tcp'],text=True).strip().split(':')[-1]
            for _ in range(40):
                p=subprocess.run(['docker','exec',name,'redis-cli','-a','synthetic_w01_only','ping'],capture_output=True,text=True)
                if p.returncode==0 and 'PONG' in p.stdout: break
                time.sleep(.25)
            else: raise RuntimeError('W01_INFRA_FAILURE: store readiness')
            for label,ref in BASELINES.items():
                target=scratch/label;target.mkdir()
                archive=subprocess.check_output(['git','archive',ref,'services/oracle-brain'],cwd=ROOT)
                with tarfile.open(fileobj=io.BytesIO(archive)) as tar:tar.extractall(target,filter='data')
                env={**os.environ,'BASELINE_ROOT':str(target),'PYTHONPATH':str(target/'services/oracle-brain'),
                     'ORACLE2_TEST_FALKORDB_URL':f'redis://:synthetic_w01_only@127.0.0.1:{port}','W01_OWNED_CONTAINER':name}
                probe=ROOT/'evals/oracle2/workflow/legacy_loss_probe.py'
                p=subprocess.run([str(python),'-m','pytest',str(probe),'-q','-s','--tb=short'],cwd=target,env=env,capture_output=True,text=True)
                output=p.stdout+p.stderr
                verified=p.returncode==1 and 'W01_EXPECTED_LOSS: actual SDK finalize/reload findings=0' in output and 'W01_INFRA_FAILURE' not in output
                receipt['results'][label]={'exit':p.returncode,'expected_loss_verified':verified,'output_sha256':hashlib.sha256(output.encode()).hexdigest(),'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest()}
                if not verified:raise RuntimeError('W01_INFRA_FAILURE: expected loss proof not obtained')
            recovery=scratch/'recovery';env['BASELINE_ROOT']=str(recovery);env['PYTHONPATH']=str(recovery/'services/oracle-brain')
            suites=['test_holistic_graphrag.py','test_holistic_graphrag_integration.py']
            p=subprocess.run([str(python),'-m','pytest',*[str(recovery/'services/oracle-brain/tests'/t) for t in suites],'-q','--tb=short'],cwd=recovery,env=env,capture_output=True,text=True)
            output=p.stdout+p.stderr
            green=p.returncode==0 and '34 passed' in output and 'skipped' not in output
            receipt['results']['recovery_invariants']={'exit':p.returncode,'passed':green,'tests':suites,'passed_count':34 if green else None,'skipped_count':0 if green else None,'output_sha256':hashlib.sha256(output.encode()).hexdigest()}
            if not green:raise RuntimeError('W01_INFRA_FAILURE: recovery invariants failed')
            receipt['passed']=True
        except Exception as exc:
            receipt.update(passed=False,failure=type(exc).__name__)
        finally:
            if created:subprocess.run(['docker','rm','-f',name],capture_output=True,check=True)
    receipt['lock_sha256']=hashlib.sha256((ROOT/'services/oracle-brain/uv.lock').read_bytes()).hexdigest()
    receipt['python']=subprocess.check_output([str(python),'--version'],text=True).strip()
    args.result.parent.mkdir(parents=True,exist_ok=True);args.result.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'passed':receipt['passed'],'expected_red_baselines':sum(r.get('expected_loss_verified',False) for r in receipt['results'].values()),'private_state_changed':False}))
    return 0 if receipt['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
