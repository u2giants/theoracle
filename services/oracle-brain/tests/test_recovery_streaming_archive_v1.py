"""Actual invented retained files; no recovery or SQL authority."""
import hashlib,os,tracemalloc
from datetime import datetime,timedelta,timezone
import pytest
from oracle_brain.hosting.forward_recovery import _verify_replacement_archive_fd_v1,pack_replacement_archive_v1
from oracle_brain.operating_model.recovery_contracts_v1 import RecoveryPrivateFileV1
from test_replacement_recovery_archive_v1 import inventory,tar


def retained(tmp_path,raw,flags=os.O_RDONLY):
 path=tmp_path/'archive.tar';path.write_bytes(raw);path.chmod(0o600);s=path.stat()
 pin=RecoveryPrivateFileV1(path=str(path),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=0o600,sha256=hashlib.sha256(raw).hexdigest())
 return path,os.open(path,flags),pin


def test_actual_large_archive_verifies_without_retaining_member_payload(tmp_path):
 files={'originals/invented.bin':b'x'*(4*1024**2)};value=inventory(files)
 raw=pack_replacement_archive_v1(files,value);path,fd,pin=retained(tmp_path,raw)
 try:
  tracemalloc.start()
  result=_verify_replacement_archive_fd_v1(fd,pin,value,archive_bound=len(raw))
  _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
 finally:os.close(fd)
 assert result['file_count']==1 and result['total_bytes']==len(files['originals/invented.bin'])
 assert peak<1024**2 # regression check only, not a general resource admission
 assert result['serving_authorized'] is result['dispatch_authorized'] is False
 assert path.read_bytes()==raw

@pytest.mark.parametrize('attack',['writable','hash','size','symlink-member','hardlink-file','public-mode','missing','extra','duplicate','truncated'])
def test_streaming_same_policy_refuses_hostile_or_drifted_retained_input(tmp_path,attack):
 import tarfile
 files={'originals/a.bin':b'invented'};value=inventory(files);raw=tar(files)
 if attack=='symlink-member':raw=tar(files,kind=tarfile.SYMTYPE)
 elif attack=='missing':raw=tar({})
 elif attack=='extra':raw=tar(files|{'originals/b.bin':b'foreign'})
 elif attack=='duplicate':raw=tar(files,duplicate=True)
 elif attack=='truncated':raw=raw[:515]
 path,fd,pin=retained(tmp_path,raw,os.O_RDWR if attack=='writable' else os.O_RDONLY)
 if attack=='hash':pin=pin.model_copy(update={'sha256':'a'*64})
 elif attack=='hardlink-file':os.link(path,tmp_path/'alias')
 elif attack=='public-mode':path.chmod(0o644)
 try:
  with pytest.raises((PermissionError,ValueError)):_verify_replacement_archive_fd_v1(fd,pin,value,archive_bound=len(raw)-1 if attack=='size' else len(raw))
 finally:os.close(fd)
 assert path.exists() # no deletion/retry/overwrite follows refusal


def test_same_archive_writer_streams_actual_pinned_files_and_retains_exact_format(tmp_path):
 import time
 from oracle_brain.hosting.forward_recovery import _write_replacement_archive_fds_v1,unpack_replacement_archive_v1
 from oracle_brain.hosting.restore_receipts import ReplacementArchiveInventoryV1
 from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
 files={'originals/a.bin':b'a'*200000,'originals/b.bin':b'b'*200000};raw_value=inventory(files).model_dump()
 for seal in raw_value['files'].values():seal['runtime_uid']=os.getuid()
 value=ReplacementArchiveInventoryV1.model_validate(raw_value)
 sources={};fds=[]
 for i,(name,data) in enumerate(files.items()):
  p=tmp_path/f'source{i}';p.write_bytes(data);p.chmod(0o600);s=p.stat();fd=os.open(p,os.O_RDONLY);fds.append(fd)
  sources[name]=(fd,RecoveryPrivateFileV1(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=0o600,sha256=hashlib.sha256(data).hexdigest()))
 output=tmp_path/'output.tar';fd=os.open(output,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with _request_fence_v1(time.monotonic()+20):result=_write_replacement_archive_fds_v1(fd,dict(reversed(tuple(sources.items()))),value,archive_bound=1024**2,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 finally:
  os.close(fd)
  for source_fd in fds:os.close(source_fd)
 assert output.read_bytes()==pack_replacement_archive_v1(files,value)
 assert unpack_replacement_archive_v1(output.read_bytes(),value)[0]==files
 assert result['bytes']==len(output.read_bytes()) and result['dispatch_authorized'] is False


def test_streaming_writer_refuses_unrepresentable_or_over_bound_before_output(tmp_path):
 import time
 from oracle_brain.hosting.forward_recovery import _write_replacement_archive_fds_v1
 from oracle_brain.hosting.restore_receipts import ReplacementArchiveInventoryV1
 from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
 data=b'original';value=inventory({'originals/a.bin':data}).model_dump();value['files']['originals/a.bin']['runtime_uid']=os.getuid();value=ReplacementArchiveInventoryV1.model_validate(value)
 p=tmp_path/'input';p.write_bytes(data);p.chmod(0o600);s=p.stat();source_fd=os.open(p,os.O_RDONLY)
 pin=RecoveryPrivateFileV1(path=str(p),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=0o600,sha256=hashlib.sha256(data).hexdigest())
 output=tmp_path/'output';fd=os.open(output,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
 try:
  with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):_write_replacement_archive_fds_v1(fd,{'originals/a.bin':(source_fd,pin)},value,archive_bound=1,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 finally:os.close(fd);os.close(source_fd)
 assert output.read_bytes()==b'' and p.read_bytes()==data


def test_streaming_expiry_retains_partial_without_any_later_write(tmp_path,monkeypatch):
 from types import SimpleNamespace
 from oracle_brain.hosting.forward_recovery import _write_replacement_archive_fds_v1
 from oracle_brain.hosting.restore_receipts import ReplacementArchiveInventoryV1
 from oracle_brain.operating_model import request_deadline_v1 as fence
 from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1
 clock=[0.0];monkeypatch.setattr(fence,'time',SimpleNamespace(monotonic=lambda:clock[0]))
 data=b'x'*100000;value=inventory({'originals/a.bin':data}).model_dump();value['files']['originals/a.bin']['runtime_uid']=os.getuid();value=ReplacementArchiveInventoryV1.model_validate(value)
 path=tmp_path/'input';path.write_bytes(data);path.chmod(0o600);s=path.stat();source_fd=os.open(path,os.O_RDONLY)
 pin=RecoveryPrivateFileV1(path=str(path),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=0o600,sha256=hashlib.sha256(data).hexdigest())
 output=tmp_path/'output';fd=os.open(output,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);writes=[];actual_write=os.write
 def first_write_then_expire(target,raw):
  count=actual_write(target,raw);writes.append(count);clock[0]=20.0;return count
 monkeypatch.setattr(os,'write',first_write_then_expire)
 try:
  with _request_fence_v1(10.0),pytest.raises(PermissionError):_write_replacement_archive_fds_v1(fd,{'originals/a.bin':(source_fd,pin)},value,archive_bound=1024**2,deadline=datetime.now(timezone.utc)+timedelta(seconds=20))
 finally:os.close(fd);os.close(source_fd)
 assert len(writes)==1 and output.stat().st_size==writes[0]>0 and output.stat().st_size<len(data)
 assert path.read_bytes()==data # no delete/rollback/retry after partial effect
