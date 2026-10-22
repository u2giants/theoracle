"""Actual separate owned Linux IPC processes; queue metadata is invented here.

This packet proves PID/UID/command/file pins and fresh IPC, not installed
scheduler or actual SQL queue admission. The SQL owner is proved separately.
"""
import hashlib,json,os,subprocess,sys,time,shutil,tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
from oracle_brain.meetings.supervisor_process import InstalledSupervisorProcessV1,observe_supervisor_process_v1,InstalledSupervisorProcessV2,observe_supervisor_process_v2
from test_meeting_supervisor_observer import packet
CHILD='''import socket,struct,json,sys,os,hashlib
from datetime import datetime,timedelta,timezone
configraw=open(sys.argv[1],'rb').read();config=json.loads(configraw);runtime_sha=hashlib.sha256(open(sys.argv[0],'rb').read()).hexdigest();config_sha=hashlib.sha256(configraw).hexdigest();server=socket.socket(socket.AF_UNIX);server.bind(sys.argv[2]);os.chmod(sys.argv[2],0o600);server.listen(4)
print('READY',flush=True)
while True:
 conn,_=server.accept()
 with conn:
  def exact(n):
   raw=b''
   while len(raw)<n:
    part=conn.recv(n-len(raw))
    if not part:raise RuntimeError('short')
    raw+=part
   return raw
  n=struct.unpack('!I',exact(4))[0];q=json.loads(exact(n));now=datetime.now(timezone.utc)
  if config.get('mode','').startswith('v2'):
   assert set(q)=={'schema_version','purpose','challenge','scope_sha256','caller_deadline'} and type(q['schema_version']) is int and q['schema_version']==2 and q['purpose']=='meeting-process-currentness-v2'
   end=datetime.fromisoformat(q['caller_deadline'].replace('Z','+00:00'));assert now<end
   open(sys.argv[1]+'.observed','w').write(json.dumps(q))
  value=dict(schema_version=1,purpose='meeting-process-currentness-v1',process_purpose='meeting-scheduler-process-v1',challenge=q['challenge'],scope_sha256=q['scope_sha256'],runtime_sha256=runtime_sha,config_sha256=config_sha,queue_observation_sha256='1'*64,sequence=1,checked_at=now.isoformat(),expires_at=(now+timedelta(seconds=1)).isoformat())
  if config.get('mode','').startswith('v2'):
   value.update(schema_version=2,purpose='meeting-process-currentness-v2',expires_at=min(now+timedelta(seconds=1),end).isoformat())
   if config.get('mode')=='v2_overlong':value['expires_at']=(end+timedelta(seconds=1)).isoformat()
  if config.get('mode')=='old_nonce':value['challenge']='0'*64
  if config.get('mode')=='extra':value['active']=True
  raw=json.dumps(value,sort_keys=True,separators=(',',':')).encode();conn.sendall(struct.pack('!I',len(raw))+raw)
'''
@pytest.fixture
def running_process(tmp_path,request):
    child=tmp_path/'scheduler.py';child.write_text(CHILD);child.chmod(0o600)
    runtime=hashlib.sha256(child.read_bytes()).hexdigest();config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(mode=getattr(request,'param','valid'))));config.chmod(0o600);configsha=hashlib.sha256(config.read_bytes()).hexdigest()
    # The installed uv executable is group-writable. Preserve the process
    # observer's guard: use an exact byte copy as a protected owned fixture,
    # rather than treating that installation as acceptable runtime proof.
    executable=tmp_path/'fixture-python';shutil.copyfile(os.readlink('/proc/self/exe'),executable);executable.chmod(0o700)
    short=tempfile.TemporaryDirectory(prefix='s07-ipc-');os.chmod(short.name,0o700);path=Path(short.name)/'private.sock'
    (tmp_path/'socket-root.json').write_text(json.dumps({'path':short.name,'test_owned':True}))
    p=subprocess.Popen([str(executable),str(child),str(config),str(path)],env={**os.environ,'PYTHONHOME':sys.base_prefix},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        ready=p.stdout.readline().strip()
        if ready!='READY':
            p.wait(timeout=3);diagnostic=p.stderr.read();(tmp_path/'startup-stderr.txt').write_text(diagnostic)
            raise AssertionError('owned process failed before READY: '+diagnostic)
        _sign,args,_w=packet();scope=args['expected_scope'].model_copy(update=dict(scheduler_runtime_sha256=runtime,scheduler_config_sha256=configsha))
        info=path.stat();proc=Path('/proc')/str(p.pid);status=(proc/'stat').read_text();start=status[status.rfind(')')+2:].split()[19];exe=os.readlink(proc/'exe');now=datetime.now(timezone.utc)
        profile=InstalledSupervisorProcessV1(purpose='meeting-scheduler-process-v1',scope=scope,socket_file=str(path),socket_device=info.st_dev,socket_inode=info.st_ino,peer_pid=p.pid,peer_uid=os.getuid(),process_start_ticks=start,executable_file=exe,executable_sha256=hashlib.sha256(Path(exe).read_bytes()).hexdigest(),command_sha256=hashlib.sha256((proc/'cmdline').read_bytes()).hexdigest(),runtime_file=str(child),runtime_sha256=runtime,config_file=str(config),config_sha256=configsha,issuer_actor='independent-installer',reviewer_actor='independent-reviewer',valid_from=now-timedelta(seconds=1),expires_at=scope.capture_until)
        yield p,profile,config
    finally:
        p.terminate();p.wait(timeout=3);p.stdout.close();p.stderr.close();short.cleanup()
        assert not path.parent.exists()
        (tmp_path/'socket-cleanup.json').write_text(json.dumps({'path':str(path.parent),'absent':True,'child_stopped':p.poll() is not None}))

def observe(profile):
    with _request_fence_v1(float(time.monotonic()+3)):
        return observe_supervisor_process_v1(profile,challenge='f'*64,deadline=datetime.now(timezone.utc)+timedelta(seconds=3))

def test_actual_separate_linux_process_identity_and_fresh_nonce(running_process):
    p,profile,_=running_process;proof=observe(profile)
    assert proof.challenge=='f'*64 and proof.scope_sha256==digest(profile.scope.model_dump(mode='json')) and p.poll() is None

@pytest.mark.parametrize('change',[dict(peer_pid=2),dict(peer_uid=2147483646),dict(process_start_ticks='1'),dict(command_sha256='0'*64),dict(socket_inode=1),dict(executable_sha256='0'*64)])
def test_foreign_restarted_changed_process_cannot_be_observed(running_process,change):
    _p,profile,_=running_process
    with pytest.raises((PermissionError,FileNotFoundError)):observe(profile.model_copy(update=change))

def test_runtime_or_config_file_drift_refuses_before_success(running_process):
    _p,profile,_=running_process;Path(profile.runtime_file).write_bytes(b'changed')
    with pytest.raises((PermissionError,ValueError)):observe(profile)

@pytest.mark.parametrize('running_process',['old_nonce','extra'],indirect=True)
def test_old_nonce_and_unknown_reply_fields_refuse(running_process):
    _p,profile,_config=running_process
    with pytest.raises((ValueError,PermissionError)):observe(profile)


@pytest.mark.parametrize('running_process',['v2'],indirect=True)
def test_actual_v2_child_receives_exact_original_deadline(running_process):
    p,old,config=running_process
    value=old.model_dump(mode='python');value.update(schema_version=2,observation_protocol='meeting-process-currentness-v2')
    profile=InstalledSupervisorProcessV2.model_validate(value)
    deadline=datetime.now(timezone.utc)+timedelta(seconds=.8)
    with _request_fence_v1(float(time.monotonic()+.8)):
        proof=observe_supervisor_process_v2(profile,challenge='e'*64,deadline=deadline)
    q=json.loads(Path(str(config)+'.observed').read_text())
    assert q['caller_deadline']==deadline.isoformat().replace('+00:00','Z') and proof.expires_at<=deadline and p.poll() is None
    with _request_fence_v1(float(time.monotonic()+1)):
        with pytest.raises(PermissionError):observe_supervisor_process_v1(profile,challenge='e'*64,deadline=deadline)
        with pytest.raises(PermissionError):observe_supervisor_process_v2(old,challenge='e'*64,deadline=deadline)

@pytest.mark.parametrize('running_process',['v2_overlong'],indirect=True)
def test_v2_child_cannot_extend_original_observer_end(running_process):
    _p,old,_config=running_process
    value=old.model_dump(mode='python');value.update(schema_version=2,observation_protocol='meeting-process-currentness-v2')
    with _request_fence_v1(float(time.monotonic()+1)):
        with pytest.raises(PermissionError):observe_supervisor_process_v2(InstalledSupervisorProcessV2.model_validate(value),challenge='f'*64,deadline=datetime.now(timezone.utc)+timedelta(seconds=.5))

@pytest.mark.parametrize('running_process',['v2'],indirect=True)
def test_v2_dead_process_and_expired_request_cannot_be_observed(running_process):
    p,old,config=running_process
    value=old.model_dump(mode='python');value.update(schema_version=2,observation_protocol='meeting-process-currentness-v2');profile=InstalledSupervisorProcessV2.model_validate(value)
    with _request_fence_v1(float(time.monotonic()+1)):
        with pytest.raises(PermissionError):observe_supervisor_process_v2(profile,challenge='f'*64,deadline=datetime.now(timezone.utc)-timedelta(seconds=1))
    assert not Path(str(config)+'.observed').exists()
    p.terminate();p.wait(timeout=3)
    with _request_fence_v1(float(time.monotonic()+1)):
        with pytest.raises((PermissionError,FileNotFoundError,ProcessLookupError)):observe_supervisor_process_v2(profile,challenge='f'*64,deadline=datetime.now(timezone.utc)+timedelta(seconds=1))
