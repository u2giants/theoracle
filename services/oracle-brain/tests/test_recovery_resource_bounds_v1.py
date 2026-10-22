"""Invented metadata and observed local capacity only; no native/SQL effects."""
import pytest
from pydantic import ValidationError
from oracle_brain.hosting.restore_receipts import parse_replacement_archive_inventory_v1
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.recovery_contracts_v1 import RecoveryPhysicalResourceV1,parse_replacement_backup_manifest_v1
from test_recovery_backup_custody_v1 import custody,backup_manifest
from test_recovery_contracts_v1 import H,change
from test_replacement_recovery_archive_v1 import inventory


def test_full_supported_inventory_can_exceed_legacy_decoder_without_widening_default():
 files={'originals/'+('/'.join(['x'*190]*5))+f'/{n:04d}.bin':b'x' for n in range(1200)}
 value=inventory(files);raw=canonical_bytes(value.model_dump(mode='json'))
 assert 1048576<len(raw)<2*1048576
 with pytest.raises(PermissionError):parse_replacement_archive_inventory_v1(raw)
 assert parse_replacement_archive_inventory_v1(raw,metadata_bound=2*1048576)==value
 with pytest.raises(PermissionError):parse_replacement_archive_inventory_v1(raw,metadata_bound=len(raw)-1)

@pytest.mark.parametrize('bound',[True,0,-1,1073741825,1.0,'1048576',None])
def test_both_decoders_refuse_coerced_or_unbounded_metadata_limits(bound):
 with pytest.raises(PermissionError):parse_replacement_archive_inventory_v1(b'{}',metadata_bound=bound)
 with pytest.raises(ValueError):parse_replacement_backup_manifest_v1(b'{}',metadata_bound=bound)


def test_manifest_explicit_bound_does_not_change_canonical_or_complete_checks():
 m=backup_manifest();raw=canonical_bytes(m.model_dump(mode='json'))
 assert parse_replacement_backup_manifest_v1(raw,metadata_bound=len(raw))==m
 with pytest.raises(ValueError):parse_replacement_backup_manifest_v1(raw,metadata_bound=len(raw)-1)
 with pytest.raises(ValueError):parse_replacement_backup_manifest_v1(raw+b' ',metadata_bound=len(raw)+1)
 for patch in [{'native_staging':m.native_staging[:1]},{'native_staging':tuple(reversed(m.native_staging))}]:
  with pytest.raises(ValidationError):change(m,**patch)
 with pytest.raises(ValidationError):change(m.native_staging[0],participant_id=m.original_capture_operation_id)


def resource(d,p,**patch):
 return RecoveryPhysicalResourceV1(filesystem_id=1,filesystem_device=p.root_identity.device,physical_byte_limit=2*d.archive_limits.maximum_total_bytes+4096,headroom_bytes=4096,resource_evidence_sha256=H,**patch)


def test_explicit_physical_allowance_preserves_logical_limits_and_never_is_authority():
 d,p=custody();v=resource(d,p)
 assert v.required_bytes_v1(d,p.root_identity)==2*d.archive_limits.maximum_total_bytes+4096
 assert p.physical_resource is None # old read-only profile remains usable
 for patch in [{'physical_byte_limit':2*d.archive_limits.maximum_total_bytes},{'filesystem_device':p.root_identity.device+1}]:
  with pytest.raises(PermissionError):change(v,**patch).required_bytes_v1(d,p.root_identity)
 for field,bad in [('filesystem_id',True),('filesystem_device',-1),('physical_byte_limit',True),('headroom_bytes',0),('resource_evidence_sha256','not-authority')]:
  with pytest.raises(ValidationError):change(v,**{field:bad})


def test_actual_local_resource_identity_and_capacity_observation_is_not_a_grant(tmp_path,monkeypatch):
 import os
 from types import SimpleNamespace
 from oracle_brain.hosting.forward_recovery import _observe_capture_resource_v1
 d,p=custody();tmp_path.chmod(0o700);st=tmp_path.stat()
 root=change(p.root_identity,path=str(tmp_path),device=st.st_dev,inode=st.st_ino,uid=st.st_uid,mode=0o700)
 fd=os.open(tmp_path,os.O_RDONLY|os.O_DIRECTORY)
 try:
  fs=os.fstatvfs(fd)
  profile=RecoveryPhysicalResourceV1(filesystem_id=fs.f_fsid,filesystem_device=st.st_dev,physical_byte_limit=2*d.archive_limits.maximum_total_bytes+4096,headroom_bytes=4096,resource_evidence_sha256=H)
  p=change(p,root_identity=root,physical_resource=profile)
  # Root UUID and installed rooted leaves remain exact; no fresh role/grant.
  result=_observe_capture_resource_v1(fd,p,d)
  assert result['required_bytes']==2*d.archive_limits.maximum_total_bytes+4096
  assert result['memory_verified'] is result['quota_verified'] is result['dispatch_authorized'] is False
  for changes in [{'f_fsid':fs.f_fsid+1},{'f_bavail':0},{'f_favail':0}]:
   fake={name:getattr(fs,name) for name in ('f_fsid','f_frsize','f_bavail','f_favail')};fake.update(changes)
   monkeypatch.setattr(os,'fstatvfs',lambda _:SimpleNamespace(**fake))
   with pytest.raises(PermissionError):_observe_capture_resource_v1(fd,p,d)
  with pytest.raises(PermissionError):_observe_capture_resource_v1(fd,change(p,physical_resource=None),d)
 finally:os.close(fd)
