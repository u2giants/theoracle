"""Linux-only independently installed process observation, never installation.

Only the observer runs these reads. Runtime callers cannot select a socket,
PID, executable, command, runtime, configuration or signing identity. Unsupported
platforms and missing/moved/restarted processes refuse before witness signing.
"""
from datetime import datetime,timezone
import hashlib,json,os,socket,stat,struct,sys,time
from pathlib import Path
from typing import Literal
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.hosting.original_intake_v1 import _pinned
from oracle_brain.hosting.gateway import unique_object
from oracle_brain.hosting._protected_control_listener_v1 import request_remaining_v1
from oracle_brain.hosting.parent_observer_v2 import MeetingSupervisorScopeV1
HASH=r'^[a-f0-9]{64}$'
class InstalledSupervisorProcessV1(StrictRecord):
    purpose:Literal['meeting-scheduler-process-v1','meeting-stop-worker-process-v1']
    scope:MeetingSupervisorScopeV1
    socket_file:str=Field(min_length=1,max_length=103)
    socket_device:int=Field(ge=0)
    socket_inode:int=Field(ge=1)
    peer_pid:int=Field(ge=2,le=2147483647)
    peer_uid:int=Field(ge=0,le=2147483647)
    process_start_ticks:str=Field(pattern=r'^[1-9][0-9]{0,31}$')
    executable_file:str=Field(min_length=1,max_length=2048)
    executable_sha256:str=Field(pattern=HASH)
    command_sha256:str=Field(pattern=HASH)
    runtime_file:str=Field(min_length=1,max_length=2048)
    runtime_sha256:str=Field(pattern=HASH)
    config_file:str=Field(min_length=1,max_length=2048)
    config_sha256:str=Field(pattern=HASH)
    issuer_actor:str=Field(min_length=1,max_length=256)
    reviewer_actor:str=Field(min_length=1,max_length=256)
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        for value in (self.socket_file,self.executable_file,self.runtime_file,self.config_file):
            if not Path(value).is_absolute() or str(Path(value).resolve())!=value:raise ValueError('canonical installed process paths required')
        end=self.scope.capture_until if self.purpose=='meeting-scheduler-process-v1' else self.scope.stop_until
        if self.issuer_actor==self.reviewer_actor or not self.scope.stop_valid_from<=self.valid_from<self.expires_at<=end:raise ValueError('independent original process window required')
        expected=(self.scope.scheduler_runtime_sha256,self.scope.scheduler_config_sha256) if self.purpose=='meeting-scheduler-process-v1' else (self.scope.stop_runtime_sha256,self.scope.stop_config_sha256)
        if (self.runtime_sha256,self.config_sha256)!=expected:raise ValueError('exact installed supervisor process scope required')
        return self

class SupervisorProcessObservationV1(StrictRecord):
    purpose:Literal['meeting-process-currentness-v1']
    process_purpose:Literal['meeting-scheduler-process-v1','meeting-stop-worker-process-v1']
    challenge:str=Field(pattern=HASH)
    scope_sha256:str=Field(pattern=HASH)
    runtime_sha256:str=Field(pattern=HASH)
    config_sha256:str=Field(pattern=HASH)
    queue_observation_sha256:str=Field(pattern=HASH)
    sequence:int=Field(ge=1)
    checked_at:AwareDatetime
    expires_at:AwareDatetime


class InstalledSupervisorProcessV2(InstalledSupervisorProcessV1):
    schema_version:Literal[2]=2
    observation_protocol:Literal['meeting-process-currentness-v2']
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,value):
        if type(value) is not int or value!=2:raise ValueError('actual v2 process installation required')
        return value

class SupervisorProcessObservationV2(SupervisorProcessObservationV1):
    schema_version:Literal[2]=2
    purpose:Literal['meeting-process-currentness-v2']
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,value):
        if type(value) is not int or value!=2:raise ValueError('actual v2 process observation required')
        return value

def _remaining(deadline,expires):
    remaining=min(request_remaining_v1(required=True),(deadline-datetime.now(timezone.utc)).total_seconds(),(expires-datetime.now(timezone.utc)).total_seconds())
    if remaining<=0:raise PermissionError('original supervisor observation end elapsed')
    return remaining

def _identity(profile,deadline):
    if sys.platform!='linux' or not hasattr(socket,'SO_PEERCRED'):raise PermissionError('installed Linux process observation unsupported')
    _remaining(deadline,profile.expires_at)
    _pinned(profile.runtime_file,profile.runtime_sha256,16*1024*1024)
    _pinned(profile.config_file,profile.config_sha256,1024*1024)
    proc=Path('/proc')/str(profile.peer_pid)
    # /proc stat's parenthesized command may contain spaces or parentheses.
    status=(proc/'stat').read_text();fields=status[status.rfind(')')+2:].split()
    if len(fields)<20 or fields[0]=='Z' or fields[19]!=profile.process_start_ticks:raise PermissionError('installed process instance changed')
    command=(proc/'cmdline').read_bytes()
    if not 0<len(command)<=16384 or hashlib.sha256(command).hexdigest()!=profile.command_sha256:raise PermissionError('actual installed process command differs')
    argv=command.rstrip(b'\0').split(b'\0')
    if profile.runtime_file.encode() not in argv or profile.config_file.encode() not in argv:raise PermissionError('actual process does not use pinned runtime and config')
    if os.readlink(proc/'exe')!=profile.executable_file:raise PermissionError('actual process executable differs')
    # Executables are public OS metadata, not private credentials. This narrow
    # bounded read never alters the retained private-file rules.
    fd=os.open(profile.executable_file,os.O_RDONLY|os.O_NOFOLLOW)
    try:
        before=os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_mode&0o022 or before.st_size>256*1024*1024:raise PermissionError('unsafe actual process executable')
        hash=hashlib.sha256();size=0
        while True:
            _remaining(deadline,profile.expires_at);part=os.read(fd,65536)
            if not part:break
            hash.update(part);size+=len(part)
        after=os.fstat(fd)
        if any(getattr(before,k)!=getattr(after,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_size','st_mtime_ns','st_ctime_ns')) or size!=before.st_size or hash.hexdigest()!=profile.executable_sha256:raise PermissionError('actual process executable changed')
    finally:os.close(fd)
    info=Path(profile.socket_file).lstat()
    if not stat.S_ISSOCK(info.st_mode) or info.st_mode&0o077 or (info.st_dev,info.st_ino,info.st_uid)!=(profile.socket_device,profile.socket_inode,profile.peer_uid):raise PermissionError('installed private process socket differs')
    parent=Path(profile.socket_file).parent
    while str(parent) not in ('/','/tmp'):
        info=parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_mode&0o022:raise PermissionError('unsafe process socket parent')
        parent=parent.parent

def observe_supervisor_process_v1(profile,*,challenge,deadline):
    """Retained exact v1 exchange; never upgraded by caller-controlled fields."""
    if type(profile) is not InstalledSupervisorProcessV1:raise PermissionError('exact installed v1 process profile required')
    return _observe_supervisor_process(profile,challenge=challenge,deadline=deadline)

def observe_supervisor_process_v2(profile,*,challenge,deadline):
    """Original observer end is propagated unchanged to the pinned v2 process."""
    if type(profile) is not InstalledSupervisorProcessV2:raise PermissionError('exact installed v2 process profile required')
    return _observe_supervisor_process(profile,challenge=challenge,deadline=deadline)

def _observe_supervisor_process(profile,*,challenge,deadline):
    v2=type(profile) is InstalledSupervisorProcessV2
    profile=type(profile).model_validate(profile.model_dump(mode='python'))
    if type(deadline) is not datetime or deadline.tzinfo is None:raise PermissionError('original aware observer deadline required')
    if not profile.valid_from<=datetime.now(timezone.utc)<profile.expires_at:raise PermissionError('installed process observation expired')
    if type(challenge) is not str or len(challenge)!=64 or any(c not in '0123456789abcdef' for c in challenge):raise PermissionError('fresh canonical observer nonce required')
    _identity(profile,deadline);scope_sha=digest(profile.scope.model_dump(mode='json'))
    value=dict(schema_version=2 if v2 else 1,purpose='meeting-process-currentness-v2' if v2 else 'meeting-process-currentness-v1',challenge=challenge,scope_sha256=scope_sha)
    if v2:value['caller_deadline']=deadline.astimezone(timezone.utc).isoformat().replace('+00:00','Z')
    request=canonical_bytes(value)
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        client.settimeout(_remaining(deadline,profile.expires_at));client.connect(profile.socket_file)
        pid,uid,_gid=struct.unpack('3i',client.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,struct.calcsize('3i')))
        if (pid,uid)!=(profile.peer_pid,profile.peer_uid):raise PermissionError('actual supervisor peer process differs')
        _identity(profile,deadline);client.settimeout(_remaining(deadline,profile.expires_at));client.sendall(struct.pack('!I',len(request))+request)
        def exact(n):
            parts=bytearray()
            while len(parts)<n:
                client.settimeout(_remaining(deadline,profile.expires_at));part=client.recv(n-len(parts))
                if not part:raise PermissionError('incomplete actual process observation')
                parts.extend(part)
            return bytes(parts)
        count=struct.unpack('!I',exact(4))[0]
        if not 0<count<=16384:raise PermissionError('bounded process observation required')
        raw=exact(count);client.settimeout(_remaining(deadline,profile.expires_at))
        if client.recv(1):raise PermissionError('extra actual process observation bytes')
        value=json.loads(raw,object_pairs_hook=unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite process observation')))
        observed=(SupervisorProcessObservationV2 if v2 else SupervisorProcessObservationV1).model_validate_json(canonical_bytes(value));now=datetime.now(timezone.utc)
        if (canonical_bytes(value)!=raw or observed.challenge!=challenge or observed.process_purpose!=profile.purpose or observed.scope_sha256!=scope_sha
            or observed.runtime_sha256!=profile.runtime_sha256 or observed.config_sha256!=profile.config_sha256
            or not profile.valid_from<=observed.checked_at<=now<observed.expires_at<=min(profile.expires_at,profile.scope.capture_until if profile.purpose=='meeting-scheduler-process-v1' else profile.scope.stop_until)
            or (v2 and observed.expires_at>deadline)
            or (now-observed.checked_at).total_seconds()>2 or (observed.expires_at-observed.checked_at).total_seconds()>2):
            raise PermissionError('foreign stale process or queue observation')
        _identity(profile,deadline);return observed
    finally:client.close()
