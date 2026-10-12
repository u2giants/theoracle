"""Public invented browser diagnostic tails remain bounded on failure/timeout."""
import importlib.util,os,sys
from pathlib import Path
import subprocess
import pytest
ROOT=Path(__file__).resolve().parents[3]
def helper():
 spec=importlib.util.spec_from_file_location('browser_custody',ROOT/'scripts/oracle2/verify_holistic_browser.py')
 value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def test_browser_failure_bounded_tail_retained():
 result=helper()._browser_run([sys.executable,'-c',"import sys; print('x'*300000); print('invented assertion failed'); sys.exit(1)"],cwd=ROOT,env=os.environ,timeout=10)
 assert result.returncode==1 and len(result.stdout.encode())<=262144
 assert result.stdout.endswith('invented assertion failed\n')

def test_browser_timeout_preserves_output_and_stops_owned_process():
 with pytest.raises(subprocess.TimeoutExpired) as error:
  helper()._browser_run([sys.executable,'-u','-c',"import time; print('invented timeout evidence'); time.sleep(30)"],cwd=ROOT,env=os.environ,timeout=.2)
 assert error.value.stdout==b'invented timeout evidence\n'

def test_diagnostics_redact_credentials_bound_and_exclude_environment(tmp_path):
 import hashlib,json,stat
 scratch=tmp_path/'scratch';scratch.mkdir()
 secret='invented-generated-secret'
 (scratch/'fixture.env').write_text('PRIVATE_ENV='+secret)
 for name in ('fixture.log','web.log','browser.log'):
  (scratch/name).write_text('x'*300000+' postgresql://user:password@localhost/db '+secret+'\n')
 result=tmp_path/'result.json'
 receipts=helper()._retain_diagnostics(scratch,result,{'ORACLE2_PILOT_TOKEN':secret})
 assert set(receipts)=={'fixture.log','web.log','browser.log'}
 for receipt in receipts.values():
  target=tmp_path/receipt['file'];data=target.read_bytes()
  assert secret.encode() not in data and b'user:password' not in data
  assert b'[redacted]' in data and len(data)<=262144
  assert stat.S_IMODE(target.stat().st_mode)==0o600
  assert receipt['bytes']==len(data) and receipt['sha256']==hashlib.sha256(data).hexdigest()
 assert not any('env' in value['file'] for value in receipts.values())
