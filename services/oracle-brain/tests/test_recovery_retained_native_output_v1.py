"""Actual invented file effects with recording subprocess, never Docker proof."""
import hashlib,os,subprocess,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from oracle_brain.hosting import forward_recovery as native
from oracle_brain.operating_model.recovery_contracts_v1 import RecoveryPrivateFileV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1


def staging(tmp_path):
 path=tmp_path/'invented.dump'
 fd=os.open(path,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600);s=os.fstat(fd)
 pin=RecoveryPrivateFileV1(path=str(path),sha256=hashlib.sha256(b'').hexdigest(),device=s.st_dev,inode=s.st_ino,uid=s.st_uid,mode=384)
 return path,fd,pin

@pytest.mark.parametrize('outcome',['timeout','nonzero','zero'])
def test_actual_partial_native_output_remains_in_exact_private_file(tmp_path,monkeypatch,outcome):
 path,fd,pin=staging(tmp_path);calls=[]
 def execute(args,**kwargs):
  calls.append((args,{k:v for k,v in kwargs.items() if k!='stdout'}));kwargs['stdout'].write(b'PGDMP-invented-partial')
  if outcome=='timeout':raise subprocess.TimeoutExpired('fixed native recording seam',1)
  return SimpleNamespace(returncode=0 if outcome=='zero' else 7)
 monkeypatch.setattr(subprocess,'run',execute)
 try:
  with _request_fence_v1(time.monotonic()+20):result=native._bounded_docker_to_retained_fd_v1(['exec','recording-owned-container','pg_dump'],output_fd=fd,expected_file=pin,bound=native.MAX_FILE,timeout=1)
 finally:os.close(fd)
 assert path.read_bytes()==b'PGDMP-invented-partial' and path.stat().st_mode&0o777==0o600
 assert result['automatic_retry_allowed'] is False and len(calls)==1
 assert result['transport_status']==('process-exited-zero' if outcome=='zero' else 'UNKNOWN')
 assert result['timed_out']==(outcome=='timeout')
 assert 'PATH' in calls[0][1]['env'] and calls[0][1]['stderr']==subprocess.DEVNULL

@pytest.mark.parametrize('attack',['nonempty','wrong-path','symlink','hardlink','public-mode','missing-fence'])
def test_foreign_or_reused_staging_refuses_before_subprocess(tmp_path,monkeypatch,attack):
 path,fd,pin=staging(tmp_path);calls=[]
 monkeypatch.setattr(subprocess,'run',lambda *a,**kw:calls.append((a,kw)))
 if attack=='nonempty':os.write(fd,b'already retained')
 elif attack=='wrong-path':
  other=tmp_path/'other';other.write_bytes(b'');other.chmod(0o600);pin=pin.model_copy(update={'path':str(other)})
 elif attack=='symlink':
  alias=tmp_path/'alias';alias.symlink_to(path);pin=pin.model_copy(update={'path':str(alias)})
 elif attack=='hardlink':os.link(path,tmp_path/'alias')
 elif attack=='public-mode':path.chmod(0o644)
 try:
  if attack=='missing-fence':
   with pytest.raises(PermissionError):native._bounded_docker_to_retained_fd_v1([],output_fd=fd,expected_file=pin,bound=native.MAX_FILE,timeout=1)
  else:
   with _request_fence_v1(time.monotonic()+20),pytest.raises(PermissionError):native._bounded_docker_to_retained_fd_v1([],output_fd=fd,expected_file=pin,bound=native.MAX_FILE,timeout=1)
 finally:os.close(fd)
 assert calls==[] and path.exists()


def test_already_open_native_output_finishing_late_stays_unknown_and_retained(tmp_path,monkeypatch):
 from oracle_brain.operating_model import request_deadline_v1 as fence
 clock=[0.0];monkeypatch.setattr(fence,'time',SimpleNamespace(monotonic=lambda:clock[0]))
 path,fd,pin=staging(tmp_path)
 def execute(args,**kwargs):
  kwargs['stdout'].write(b'PGDMP-completed-after-original-fence');clock[0]=20.0
  return SimpleNamespace(returncode=0)
 monkeypatch.setattr(subprocess,'run',execute)
 try:
  with _request_fence_v1(10.0):result=native._bounded_docker_to_retained_fd_v1([],output_fd=fd,expected_file=pin,bound=native.MAX_FILE,timeout=1)
 finally:os.close(fd)
 assert result['transport_status']=='UNKNOWN' and result['returncode']==0 and result['automatic_retry_allowed'] is False
 assert path.read_bytes()==b'PGDMP-completed-after-original-fence'


def test_zero_exit_over_bound_is_never_accepted_or_truncated(tmp_path,monkeypatch):
 path,fd,pin=staging(tmp_path)
 # Recording seam deliberately ignores the real subprocess RLIMIT. The owner
 # must still refuse acceptance and retain actual observed bytes without clipping.
 data=b'x'*(1024**2+1)
 def execute(args,**kwargs):kwargs['stdout'].write(data);return SimpleNamespace(returncode=0)
 monkeypatch.setattr(subprocess,'run',execute)
 try:
  with _request_fence_v1(time.monotonic()+20):result=native._bounded_docker_to_retained_fd_v1([],output_fd=fd,expected_file=pin,bound=1024**2,timeout=1)
 finally:os.close(fd)
 assert result['transport_status']=='UNKNOWN' and path.stat().st_size==len(data)


def test_same_exclusive_creator_preserves_partial_uuid_pending_file(tmp_path):
 from datetime import datetime,timedelta,timezone
 tmp_path.chmod(0o700);name='00000000-0000-0000-0000-000000000001/pending/00000000-0000-0000-0000-000000000002.dump'
 with _request_fence_v1(time.monotonic()+20):
  with pytest.raises(RuntimeError):
   with native._exclusive_output_v1(tmp_path,name,readwrite=True,deadline=datetime.now(timezone.utc)+timedelta(seconds=20)) as (fd,parent):
    os.write(fd,b'actual invented partial');os.fsync(fd);os.fsync(parent)
    raise RuntimeError('observed interrupted staging')
 path=tmp_path/name
 assert path.read_bytes()==b'actual invented partial' and path.stat().st_nlink==1 and path.stat().st_mode&0o777==0o600
 with _request_fence_v1(time.monotonic()+20),pytest.raises(FileExistsError):
  with native._exclusive_output_v1(tmp_path,name,readwrite=True,deadline=datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert path.read_bytes()==b'actual invented partial'


def test_new_staging_creator_missing_original_fence_never_creates(tmp_path):
 from datetime import datetime,timedelta,timezone
 tmp_path.chmod(0o700)
 with pytest.raises(PermissionError):
  with native._exclusive_output_v1(tmp_path,'operation/pending/participant.dump',readwrite=True,deadline=datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert list(tmp_path.iterdir())==[]


def test_expired_staging_creator_stops_before_later_directory_or_file(tmp_path,monkeypatch):
 from datetime import datetime,timedelta,timezone
 from oracle_brain.operating_model import request_deadline_v1 as fence
 tmp_path.chmod(0o700);clock=[0.0];actual_mkdir=os.mkdir
 monkeypatch.setattr(fence,'time',SimpleNamespace(monotonic=lambda:clock[0]))
 def first_then_expire(*args,**kwargs):
  result=actual_mkdir(*args,**kwargs);clock[0]=20.0;return result
 monkeypatch.setattr(os,'mkdir',first_then_expire)
 with _request_fence_v1(10.0),pytest.raises(PermissionError):
  with native._exclusive_output_v1(tmp_path,'operation/pending/participant.dump',readwrite=True,deadline=datetime.now(timezone.utc)+timedelta(seconds=20)):pass
 assert (tmp_path/'operation').is_dir() and not (tmp_path/'operation/pending').exists()
 assert list((tmp_path/'operation').iterdir())==[] # retained partial, no deletion
