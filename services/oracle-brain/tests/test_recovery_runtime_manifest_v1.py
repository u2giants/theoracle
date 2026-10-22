"""Actual invented read-only files; no executed runtime or installed authority."""
import hashlib
import os
import time
from datetime import datetime,timedelta,timezone
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.recovery_contracts_v1 import (
 RecoveryRuntimeFileV1,RecoveryRuntimeRootV1,RecoveryRuntimeCensusRecordV1,
 RecoveryArchiveRuntimeManifestV1,RecoveryPrivateFileV1,parse_recovery_archive_runtime_manifest_v1,
 RecoveryStartupConfigV1,parse_recovery_startup_v1)
from oracle_brain.operating_model.recovery_authority_v1 import _observe_installed_runtime_census_v1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
from test_recovery_contracts_v1 import uid,H,change,file


def fixture(tmp_path):
 root=tmp_path/'installed';root.mkdir(mode=0o700)
 def installed(name,kind,mode):
  path=root/name;path.write_bytes((name+' exact retained bytes').encode());path.chmod(mode);s=path.stat()
  return RecoveryRuntimeFileV1(kind=kind,path=str(path),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=mode,size=s.st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
 interpreter=installed('python','interpreter',0o755);entrypoint=installed('entry.py','entrypoint',0o644)
 items=sorted((interpreter,entrypoint),key=lambda v:v.path)
 raw=b''.join(canonical_bytes(RecoveryRuntimeCensusRecordV1(sequence=i+1,file=v).model_dump(mode='json'))+b'\n' for i,v in enumerate(items))
 census=tmp_path/'census.ndjson';census.write_bytes(raw);census.chmod(0o600);s=census.stat();r=root.stat();now=datetime.now(timezone.utc)
 pin=RecoveryPrivateFileV1(path=str(census),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=0o600,sha256=hashlib.sha256(raw).hexdigest())
 m=RecoveryArchiveRuntimeManifestV1(operation_id=uid(1),descriptor_sha256=H,custody_sha256=H,interpreter=interpreter,entrypoint=entrypoint,installed_roots=(RecoveryRuntimeRootV1(path=str(root),device=r.st_dev,inode=r.st_ino,uid=r.st_uid,mode=0o700),),import_paths=(str(root),),interpreter_flags=('-I','-S','-B'),census=pin,census_bytes=len(raw),file_count=2,total_file_bytes=sum(v.size for v in items),memory_limit_bytes=1048576,memory_headroom_bytes=1048576,resource_evidence_sha256=H,issuer_actor=uid(80),reviewer_actor=uid(81),valid_from=now,expires_at=now+timedelta(seconds=30),original_horizon=now+timedelta(seconds=30))
 return m,census,root


def observe(m):
 with _request_fence_v1(time.monotonic()+10.0):
  return _observe_installed_runtime_census_v1(m,deadline=datetime.now(timezone.utc)+timedelta(seconds=10))


def rewrite(m,path,raw):
 path.write_bytes(raw)
 return change(m,census=change(m.census,sha256=hashlib.sha256(raw).hexdigest()),census_bytes=len(raw))


def test_actual_complete_files_never_qualify_loader_or_start_child(tmp_path):
 m,_,_=fixture(tmp_path)
 assert parse_recovery_archive_runtime_manifest_v1(canonical_bytes(m.model_dump(mode='json')))==m
 result=observe(m)
 assert result['listed_files_verified'] and result['file_count']==2
 for key in ('native_loader_enforced','runtime_qualified','child_invocation_authorized','serving_authorized','dispatch_authorized','automatic_retry_allowed'):assert result[key] is False

@pytest.mark.parametrize('mutation',['extra','missing','bytes','mode','link','hardlink','census-bytes','census-mode'])
def test_actual_runtime_population_drift_refuses_whole_census(tmp_path,mutation):
 m,census,root=fixture(tmp_path)
 path=root/'python'
 if mutation=='extra':(root/'extra.py').write_bytes(b'not pinned')
 elif mutation=='missing':path.unlink()
 elif mutation=='bytes':path.write_bytes(b'x'*path.stat().st_size)
 elif mutation=='mode':path.chmod(0o777)
 elif mutation=='link':path.unlink();path.symlink_to(root/'entry.py')
 elif mutation=='hardlink':os.link(path,root/'duplicate')
 elif mutation=='census-bytes':census.write_bytes(census.read_bytes()+b' ')
 elif mutation=='census-mode':census.chmod(0o644)
 with pytest.raises((PermissionError,OSError,ValueError)):observe(m)

@pytest.mark.parametrize('mutation',['duplicate','reverse','sequence','no-newline','crlf','oversize','unknown','noncanonical'])
def test_streamed_records_refuse_malformed_and_partial_population(tmp_path,mutation):
 m,census,_=fixture(tmp_path);lines=census.read_bytes().splitlines(keepends=True)
 if mutation=='duplicate':raw=lines[0]*2
 elif mutation=='reverse':raw=b''.join(reversed(lines))
 elif mutation=='sequence':raw=lines[0].replace(b'"sequence":1',b'"sequence":2')+lines[1]
 elif mutation=='no-newline':raw=b''.join(lines)[:-1]
 elif mutation=='crlf':raw=b''.join(lines).replace(b'\n',b'\r\n')
 elif mutation=='oversize':raw=b' '*65537+b'\n'
 elif mutation=='unknown':raw=lines[0].replace(b'{',b'{"unknown":1,',1)+lines[1]
 else:raw=lines[0].replace(b'{',b'{ ',1)+lines[1]
 m=rewrite(m,census,raw)
 with pytest.raises((PermissionError,ValueError)):observe(m)


def test_missing_or_expired_original_fence_never_reads_runtime(tmp_path):
 m,_,_=fixture(tmp_path)
 with pytest.raises(PermissionError):_observe_installed_runtime_census_v1(m,deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
 with _request_fence_v1(time.monotonic()+10.0):
  with pytest.raises(PermissionError):_observe_installed_runtime_census_v1(m,deadline=datetime.now(timezone.utc)-timedelta(seconds=1))


def test_unavailable_memory_refuses_without_execution(tmp_path,monkeypatch):
 m,_,_=fixture(tmp_path);monkeypatch.setattr(os,'sysconf',lambda key:1)
 with pytest.raises(PermissionError,match='memory'):observe(m)

@pytest.mark.parametrize('patch',[{'interpreter_flags':('-S','-I','-B')},{'file_count':True},{'memory_limit_bytes':True},{'import_paths':('/foreign',)},{'runtime_qualified':True}])
def test_header_has_no_loose_flags_paths_or_authority_fields(tmp_path,patch):
 m,_,_=fixture(tmp_path)
 with pytest.raises(ValueError):change(m,**patch)


def test_old_startup_without_runtime_pointer_preserves_existing_api():
 value=RecoveryStartupConfigV1(descriptor=file(1),postrestore_binding=None,issuer_actor=uid(80),reviewer_actor=uid(81))
 obj=value.model_dump(mode='json');obj.pop('archive_runtime_manifest')
 assert parse_recovery_startup_v1(canonical_bytes(obj)).archive_runtime_manifest is None


@pytest.mark.parametrize('field',['expires_at','original_horizon'])
def test_expired_installed_header_never_observes_bytes(tmp_path,field):
 m,_,_=fixture(tmp_path)
 old=datetime.now(timezone.utc)-timedelta(seconds=60)
 m=change(m,valid_from=old,expires_at=old+timedelta(seconds=1),original_horizon=old+timedelta(seconds=2))
 with pytest.raises(PermissionError,match='runtime window'):observe(m)


def test_header_cannot_pin_its_own_census_or_duplicate_root(tmp_path):
 m,_,root=fixture(tmp_path)
 for patch in ({'census':change(m.census,path=str(root/'census'))},{'installed_roots':m.installed_roots*2},{'entrypoint':change(m.entrypoint,inode=m.interpreter.inode)}):
  with pytest.raises(ValueError):change(m,**patch)


def test_header_bytes_duplicates_and_whitespace_never_reconstruct_pin(tmp_path):
 m,_,_=fixture(tmp_path);raw=canonical_bytes(m.model_dump(mode='json'))
 for bad in (raw+b' ',raw.replace(b'{',b'{"schema_version":1,',1),b' '*65537):
  with pytest.raises(ValueError):parse_recovery_archive_runtime_manifest_v1(bad)


def test_new_census_orchestration_rechecks_same_admission_without_caller_payload(tmp_path,monkeypatch):
 """Recording seams prove call order only, not real SQL/role installation."""
 from types import SimpleNamespace
 import oracle_brain.operating_model.recovery_authority_v1 as owner
 m,_,_=fixture(tmp_path);raw=b'exact actual custody';m=change(m,custody_sha256=hashlib.sha256(raw).hexdigest())
 header=canonical_bytes(m.model_dump(mode='json'));events=[]
 settings=object.__new__(owner.ProtectedRecoverySettingsV1)
 monkeypatch.setattr(settings,'_runtime_manifest_file_v1',lambda:(events.append('header') or (header,m)))
 authority=object.__new__(owner.RecoverySQLAuthorityV1);authority.settings=settings
 custody=object()
 monkeypatch.setattr(authority,'custody_v1',lambda **kw:(events.append('custody') or (raw,custody)))
 current=SimpleNamespace(admission_id=uid(1),descriptor_sha256=H,backup_custody_sha256=m.custody_sha256)
 monkeypatch.setattr(authority,'current_v1',lambda **kw:(events.append('current') or current))
 with _request_fence_v1(time.monotonic()+10.0):
  _,result=authority.runtime_census_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
 assert events==['custody','current','header','current','header','custody']
 assert not result['child_invocation_authorized']


def test_changed_admission_after_byte_observation_refuses_public_result(tmp_path,monkeypatch):
 from types import SimpleNamespace
 import oracle_brain.operating_model.recovery_authority_v1 as owner
 m,_,_=fixture(tmp_path);raw=b'custody';m=change(m,custody_sha256=hashlib.sha256(raw).hexdigest())
 settings=object.__new__(owner.ProtectedRecoverySettingsV1)
 monkeypatch.setattr(settings,'_runtime_manifest_file_v1',lambda:(canonical_bytes(m.model_dump(mode='json')),m))
 authority=object.__new__(owner.RecoverySQLAuthorityV1);authority.settings=settings
 monkeypatch.setattr(authority,'custody_v1',lambda **kw:(raw,None))
 calls=[]
 def current(**kw):
  calls.append(1)
  return SimpleNamespace(admission_id=uid(len(calls)),descriptor_sha256=H,backup_custody_sha256=m.custody_sha256)
 monkeypatch.setattr(authority,'current_v1',current)
 with _request_fence_v1(time.monotonic()+10.0):
  with pytest.raises(PermissionError,match='admission changed'):authority.runtime_census_v1(deadline=datetime.now(timezone.utc)+timedelta(seconds=10))
