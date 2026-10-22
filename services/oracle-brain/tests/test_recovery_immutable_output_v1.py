"""Real invented private file effects with recording SQL; no actual grant proof."""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
import os,time
import pytest
from oracle_brain.hosting.forward_recovery import ProtectedReplacementRecoveryFactoryV1
from oracle_brain.operating_model.recovery_authority_v1 import RecoverySQLAuthorityV1,RecoveryOutcomeUnknownV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from oracle_brain.operating_model.recovery_contracts_v1 import RecoveryClaimV1,RecoveryPhysicalResourceV1
from test_recovery_backup_custody_v1 import custody
from test_recovery_contracts_v1 import change,H


def producer(tmp_path,monkeypatch,*,after_error=False):
 d,p=custody();tmp_path.chmod(0o700);s=tmp_path.stat()
 p=change(p,root_identity=change(p.root_identity,path=str(tmp_path),device=s.st_dev,inode=s.st_ino,uid=s.st_uid),physical_resource=RecoveryPhysicalResourceV1(filesystem_id=os.statvfs(tmp_path).f_fsid,filesystem_device=s.st_dev,physical_byte_limit=2*d.archive_limits.maximum_total_bytes+4096,headroom_bytes=4096,resource_evidence_sha256=H))
 now=datetime.now(timezone.utc)
 claim=RecoveryClaimV1(operation_id=d.operation_id,phase='capture',descriptor_sha256=H,claimed_at=now-timedelta(seconds=1),original_phase_deadline=now+timedelta(seconds=60),fresh=False)
 authority=object.__new__(RecoverySQLAuthorityV1);calls=[]
 def current(self,**kw):
  calls.append('actual-current-seam')
  if after_error and len(calls)>1:raise PermissionError('recorded postwrite currentness refusal')
  return SimpleNamespace(retained_claims=(claim,))
 monkeypatch.setattr(RecoverySQLAuthorityV1,'current_v1',current)
 monkeypatch.setattr(RecoverySQLAuthorityV1,'custody_v1',lambda *a,**kw:(b'protected owned seam bytes',p))
 factory=object.__new__(ProtectedReplacementRecoveryFactoryV1)
 factory.settings=SimpleNamespace(current_v1=lambda:(None,None,d,None,None))
 monkeypatch.setattr(ProtectedReplacementRecoveryFactoryV1,'_source',lambda *a:authority)
 return factory,d,p,calls


def test_actual_immutable_output_uses_only_uuid_scoped_private_exclusive_files(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 with _request_fence_v1(time.monotonic()+20):result=factory._save_capture_output_v1('archive.tar',b'invented archive bytes',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 path=tmp_path/str(d.operation_id)/'archive.tar'
 assert path.read_bytes()==b'invented archive bytes' and path.stat().st_mode&0o777==0o600 and path.parent.stat().st_mode&0o777==0o700
 assert result['member']==str(d.operation_id)+'/archive.tar' and result['bytes']==22 and not result['automatic_retry_allowed']
 with _request_fence_v1(time.monotonic()+20),pytest.raises(RecoveryOutcomeUnknownV1):factory._save_capture_output_v1('archive.tar',b'replacement denied',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert path.read_bytes()==b'invented archive bytes'


def test_postwrite_refusal_preserves_uncertain_file_without_retry_or_deletion(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch,after_error=True)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(RecoveryOutcomeUnknownV1):factory._save_capture_output_v1('manifest.json',b'{}',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert (tmp_path/str(d.operation_id)/'manifest.json').read_bytes()==b'{}'

@pytest.mark.parametrize('leaf',['../escape','foreign','/absolute','x/archive.tar'])
def test_caller_path_cannot_become_capture_output(tmp_path,monkeypatch,leaf):
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):factory._save_capture_output_v1(leaf,b'x',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert list(tmp_path.iterdir())==[] and calls==[]


def test_absent_original_request_fence_has_zero_private_write(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 with pytest.raises(PermissionError):factory._save_capture_output_v1('archive.tar',b'x',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert list(tmp_path.iterdir())==[]


def test_operation_symlink_does_not_redirect_immutable_capture(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 foreign=tmp_path/'foreign';foreign.mkdir(mode=0o700)
 (tmp_path/str(d.operation_id)).symlink_to(foreign,target_is_directory=True)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(RecoveryOutcomeUnknownV1):factory._save_capture_output_v1('archive.tar',b'x',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert list(foreign.iterdir())==[] and (tmp_path/str(d.operation_id)).is_symlink()


def test_existing_output_root_is_never_chmodded_or_recreated(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch);tmp_path.chmod(0o755)
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):factory._save_capture_output_v1('archive.tar',b'x',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert tmp_path.stat().st_mode&0o777==0o755 and list(tmp_path.iterdir())==[]


def test_separately_installed_tighter_archive_limit_is_preserved(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 d=change(d,archive_limits=change(d.archive_limits,maximum_total_bytes=1))
 factory.settings=SimpleNamespace(current_v1=lambda:(None,None,d,None,None))
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):factory._save_capture_output_v1('archive.tar',b'xx',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert list(tmp_path.iterdir())==[]


def test_new_current_output_metadata_is_descriptor_bounded_not_arbitrarily_one_mib(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 raw=b'x'*(1048576+1) # actual invented producer bytes; not a validated manifest
 with _request_fence_v1(time.monotonic()+20):result=factory._save_capture_output_v1('inventory.json',raw,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert result['bytes']==len(raw) and (tmp_path/str(d.operation_id)/'inventory.json').read_bytes()==raw


def test_complete_existing_final_triplet_plus_new_output_cannot_exceed_a(tmp_path,monkeypatch):
 from oracle_brain.hosting.forward_recovery import _check_final_output_aggregate_v1
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 a=20;d=change(d,archive_limits=change(d.archive_limits,maximum_total_bytes=a))
 op=tmp_path/str(d.operation_id);op.mkdir(mode=0o700)
 archive=op/'archive.tar';archive.write_bytes(b'x'*15);archive.chmod(0o600)
 fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
 try:
  with _request_fence_v1(time.monotonic()+20):_check_final_output_aggregate_v1(fd,p,d,5)
  with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):_check_final_output_aggregate_v1(fd,p,d,6)
  unknown=op/'foreign';unknown.write_bytes(b'x');unknown.chmod(0o600)
  with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):_check_final_output_aggregate_v1(fd,p,d,1)
 finally:os.close(fd)
 assert archive.read_bytes()==b'x'*15 and not (op/'inventory.json').exists()


def test_missing_installed_physical_resource_has_zero_new_output(tmp_path,monkeypatch):
 factory,d,p,calls=producer(tmp_path,monkeypatch)
 monkeypatch.setattr(RecoverySQLAuthorityV1,'custody_v1',lambda *a,**kw:(b'actual missing profile seam',change(p,physical_resource=None)))
 with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):factory._save_capture_output_v1('archive.tar',b'x',deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 assert list(tmp_path.iterdir())==[]
