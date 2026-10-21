"""Offline target commitments retain exact identity without worker metadata files."""
import hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
import pytest
from oracle_brain.private_targets import TARGET_PINS,database_tenant,is_pinned_target,read_private_target
ROOT=Path(__file__).resolve().parents[3]

def test_public_registry_and_fixed_identity_parity():
 assert dict(TARGET_PINS)==json.loads((ROOT/'dev/oracle2/public-target-pins.json').read_text())['targets']
 from oracle_brain.operating_model.native_proof_v2_identity import IDENTITY
 assert IDENTITY['project_sha256']==TARGET_PINS['native_trigger_project']
 assert 'project' not in IDENTITY

def test_actual_private_profile_and_runtime_login():
 tenant=read_private_target('native_supabase_project')
 assert database_tenant('oracle_synthetic_executor.'+tenant,'oracle_synthetic_executor')==tenant
 assert database_tenant('oracle_synthetic_executor%2E'+tenant,'oracle_synthetic_executor')==tenant
 for login in ('postgres.'+tenant,'oracle_synthetic_executor.'+'z'*20,'oracle_synthetic_executor.'+tenant+'.extra','oracle_synthetic_executor.'):
  with pytest.raises(PermissionError):database_tenant(login,'oracle_synthetic_executor')

def test_profile_selector_and_private_custody(tmp_path,monkeypatch):
 source=Path.home()/'.config/oracle/targets.json';folder=tmp_path/'private';folder.mkdir(mode=0o700);path=folder/'targets.json'
 path.write_bytes(source.read_bytes());path.chmod(0o600)
 monkeypatch.setenv('ORACLE_TARGET_PROFILE_PATH',str(path));assert is_pinned_target('native_supabase_project',read_private_target('native_supabase_project'))
 for selected in ('','relative.json'):
  monkeypatch.setenv('ORACLE_TARGET_PROFILE_PATH',selected)
  with pytest.raises(PermissionError):read_private_target('native_supabase_project')
 monkeypatch.setenv('ORACLE_TARGET_PROFILE_PATH',str(path))
 body=json.loads(path.read_bytes());body['targets']['native_supabase_project']='z'*20;path.write_text(json.dumps(body))
 with pytest.raises(PermissionError):read_private_target('native_supabase_project')
 path.write_bytes(source.read_bytes());path.chmod(0o644)
 with pytest.raises(PermissionError):read_private_target('native_supabase_project')
 path.chmod(0o600);link=folder/'link';link.symlink_to(path)
 with pytest.raises(PermissionError):read_private_target('native_supabase_project',link)
 path.write_text('{malformed')
 with pytest.raises((PermissionError,ValueError)):read_private_target('native_supabase_project')

def test_packaged_python_has_no_repository_registry_dependency(tmp_path):
 package=tmp_path/'oracle_brain';package.mkdir();(package/'__init__.py').touch()
 shutil.copy(ROOT/'services/oracle-brain/oracle_brain/private_targets.py',package/'private_targets.py')
 result=subprocess.run([sys.executable,'-c',"from oracle_brain.private_targets import TARGET_PINS,is_pinned_target;assert len(TARGET_PINS)==5;assert not is_pinned_target('native_supabase_project','foreign')"],cwd=tmp_path,env={'PYTHONPATH':str(tmp_path)},capture_output=True)
 assert result.returncode==0
