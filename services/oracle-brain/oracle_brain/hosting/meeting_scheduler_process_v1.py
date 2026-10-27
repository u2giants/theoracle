"""Separately installed local Linux scheduler; no provider client or issuer.

The process config has fixed values, never its own hash or a circular Scope.
Independent installation later pins actual runtime/config/PID/socket and the
same original SQL STOP relation. Starting this source grants nothing.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID,uuid5,NAMESPACE_URL
import json,os,socket,stat,struct,sys,threading,time,signal
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.protected_inputs_v1 import ProtectedInputV1
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1,request_remaining_v1
from oracle_brain.hosting.original_intake_v1 import _pinned,_parse,load_original_intake_settings_v1
from oracle_brain.hosting.meeting_capture_v1 import load_meeting_capture_settings_v1,MeetingCaptureFactoryV1
from oracle_brain.hosting.meeting_supervision_service_v1 import load_meeting_supervision_settings_v1,MeetingSupervisionFactoryV1
HASH=r'^[a-f0-9]{64}$'
# A refused READ tick (another reader serializing the same queue read, or the
# queue advancing between this tick's own reads) is not a broken loop; only real
# install/SQL failures may flip the health flag that gates later observations.
_TRANSIENT_READ_REFUSALS=frozenset({'scheduler observation already running','actual queue changed during scheduler observation'})

class MeetingSchedulerRuntimeV1(StrictRecord):
    purpose:Literal['meeting-scheduler-runtime-v1']
    workspace_id:UUID
    meeting_id:UUID
    provider_account:str=Field(min_length=1,max_length=256)
    create_operation_id:UUID
    create_request_sha256:str=Field(pattern=HASH)
    capture_until:AwareDatetime
    stop_valid_from:AwareDatetime
    stop_until:AwareDatetime
    original_horizon:AwareDatetime
    scheduler_poll_seconds:int=Field(ge=1,le=30)
    stop_request_seconds:int=Field(ge=1,le=30)
    safety_allowance_seconds:int=Field(ge=1,le=60)
    stop_margin_seconds:int=Field(ge=3,le=120)
    socket_file:str=Field(min_length=1,max_length=103)
    observer_uid:int=Field(ge=0,le=2147483647)
    host_config:ProtectedInputV1
    host_appointment:ProtectedInputV1
    capture_config:ProtectedInputV1
    expected_issuer_actor:UUID
    expected_reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @model_validator(mode='after')
    def original(self):
        if (not self.stop_valid_from<=self.valid_from<self.expires_at<=self.capture_until<=self.stop_until<=self.original_horizon
            or self.stop_margin_seconds<self.scheduler_poll_seconds+self.stop_request_seconds+self.safety_allowance_seconds
            or self.expected_issuer_actor==self.expected_reviewer_actor or self.provider_account!=self.provider_account.strip()
            or any(ord(x)<32 or ord(x)==127 for x in self.provider_account)
            or not Path(self.socket_file).is_absolute() or str(Path(self.socket_file).resolve())!=self.socket_file):
            raise ValueError('independently installed original scheduler values required')
        return self

class SupervisorProcessRequestV2(StrictRecord):
    schema_version:Literal[2]=2
    purpose:Literal['meeting-process-currentness-v2']
    challenge:str=Field(pattern=HASH)
    scope_sha256:str=Field(pattern=HASH)
    caller_deadline:AwareDatetime
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,value):
        if type(value) is not int or value!=2:raise ValueError('exact original v2 process request required')
        return value

class _InstalledSchedulerV1:
    def __init__(self):
        if sys.platform!='linux' or not hasattr(socket,'SO_PEERCRED'):raise PermissionError('installed Linux scheduler required')
        self.path=os.environ['ORACLE2_MEETING_SCHEDULER_CONFIG_FILE'];self.sha=os.environ['ORACLE2_MEETING_SCHEDULER_CONFIG_SHA256']
        self.runtime=str(Path(__file__).resolve());self.runtime_sha=os.environ['ORACLE2_MEETING_SCHEDULER_RUNTIME_SHA256']
        if sys.argv!=[self.runtime,self.path]:raise PermissionError('fixed installed scheduler command required')
        self.config=_parse(MeetingSchedulerRuntimeV1,_pinned(self.path,self.sha))
        c=self.config
        self.host=load_original_intake_settings_v1(c.host_config.path,c.host_config.sha256,c.host_appointment.path,c.host_appointment.sha256,c.expected_issuer_actor,c.expected_reviewer_actor)
        self.capture_settings=load_meeting_capture_settings_v1(self.host,c.capture_config.path,c.capture_config.sha256)
        self.supervision_path=os.environ['ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_FILE'];self.supervision_sha=os.environ['ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_SHA256']
        settings=load_meeting_supervision_settings_v1(self.capture_settings,self.supervision_path,self.supervision_sha)
        if settings.config.process_purpose!='meeting-scheduler-process-v1':raise PermissionError('fixed separately appointed scheduler purpose required')
        self.queue=MeetingSupervisionFactoryV1(settings);self.capture=MeetingCaptureFactoryV1(self.capture_settings)
        self.lock=threading.Lock();self.stop=threading.Event();self.loop=None;self.last_success=0.;self.next_poll=0.;self.error=True;self.mutation_uncertain=False
        self.current()
    def current(self):
        c=self.config
        if (os.environ.get('ORACLE2_MEETING_SCHEDULER_CONFIG_FILE')!=self.path or os.environ.get('ORACLE2_MEETING_SCHEDULER_CONFIG_SHA256')!=self.sha
            or os.environ.get('ORACLE2_MEETING_SCHEDULER_RUNTIME_SHA256')!=self.runtime_sha
            or os.environ.get('ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_FILE')!=self.supervision_path or os.environ.get('ORACLE2_MEETING_SCHEDULER_SUPERVISION_SETTINGS_SHA256')!=self.supervision_sha
            or _parse(MeetingSchedulerRuntimeV1,_pinned(self.path,self.sha))!=c):raise PermissionError('installed scheduler moved or changed')
        _pinned(self.runtime,self.runtime_sha,16*1024*1024);end=min(self.queue.settings.current(),self.capture_settings.current(),c.expires_at,c.capture_until)
        scope=self.queue.settings.config.scope
        for name in ('workspace_id','meeting_id','provider_account','create_operation_id','create_request_sha256','capture_until','stop_valid_from','stop_until','original_horizon','scheduler_poll_seconds','stop_request_seconds','safety_allowance_seconds','stop_margin_seconds'):
            if getattr(c,name)!=getattr(scope,name):raise PermissionError('actual independently installed scheduler scope differs')
        if scope.scheduler_runtime_sha256!=self.runtime_sha or scope.scheduler_config_sha256!=self.sha or scope.scheduler_id!=self.host.config.principal_id:
            raise PermissionError('actual scheduler runtime/config/role differs')
        if not c.valid_from<=datetime.now(timezone.utc)<end:raise PermissionError('original scheduler end elapsed')
        return end
    def fresh(self,deadline):
        request_remaining_v1(required=True);self.current()
        packet=self.queue.current_queue_v1(caller_deadline=deadline)
        if packet.runtime_sha256!=self.runtime_sha or packet.config_sha256!=self.sha:raise PermissionError('actual queue does not pin this scheduler')
        due=self.capture.due_stop_v1(caller_deadline=deadline)
        head=self.capture.supervision_head_v1(caller_deadline=deadline)
        from oracle_brain.hosting.meeting_supervisor_observer_v1 import supervision_queue_commitment_v1
        if packet.queue_observation_sha256!=supervision_queue_commitment_v1(head) or packet.version!=due.version:raise PermissionError('actual queue changed during scheduler observation')
        self.current();request_remaining_v1(required=True);return packet,due
    def _poll(self):
        c=self.config
        while not self.stop.is_set():
            wall=datetime.now(timezone.utc);tick=time.monotonic();self.next_poll=tick+c.scheduler_poll_seconds
            deadline=min(wall+timedelta(seconds=c.stop_request_seconds),c.expires_at,c.capture_until)
            try:
                with _request_fence_v1(float(tick+min(c.stop_request_seconds,(deadline-wall).total_seconds()))):
                    if not self.lock.acquire(blocking=False):raise PermissionError('scheduler observation already running')
                    try:
                        self.current();packet,due=self.fresh(deadline)
                        if due.due and due.stop_intent_id is None and due.pre_stop_observation is not None and not self.mutation_uncertain:
                            # ONE existing deterministic business intent, no provider
                            # request/claim and no invented metadata/created bot.
                            receipt=due.pre_stop_observation
                            if due.created_bot is None or str(receipt.bot_id)!=due.created_bot.get('bot_id'):raise PermissionError('actual linked created bot differs')
                            operation=uuid5(NAMESPACE_URL,f'oracle-meeting-scheduled-stop-v1/{c.workspace_id}/{c.meeting_id}/{c.create_operation_id}')
                            self.mutation_uncertain=True
                            self.capture.transition_v1(expected_head=due.version,operation_id=operation,action='stop_intent',payload=dict(create_intent_id=str(c.create_operation_id),bot_id=str(receipt.bot_id),create_receipt_sha256=due.created_bot['receipt_sha256'],stop_mapping_sha256=due.stop_mapping_sha256,metadata_sha256=receipt.metadata_sha256),caller_deadline=deadline)
                            self.mutation_uncertain=False
                        self.last_success=time.monotonic();self.error=False
                    finally:self.lock.release()
            except Exception as error:
                if type(error) is not PermissionError or str(error) not in _TRANSIENT_READ_REFUSALS:self.error=True
            if datetime.now(timezone.utc)>=min(c.capture_until,c.expires_at):self.stop.set();break
            self.stop.wait(max(0,self.next_poll-time.monotonic()))
    def observe(self,connection):
        # Original start exists before any config pin or body read. The client
        # supplies only narrowing; no process, scope or SQL authority is minted.
        wall=datetime.now(timezone.utc);tick=time.monotonic();end=tick+min(30,max(0,(self.config.expires_at-wall).total_seconds()))
        with _request_fence_v1(float(end)):
            self.current();connection.settimeout(min(30,request_remaining_v1()))
            def exact(size):
                data=bytearray()
                while len(data)<size:
                    connection.settimeout(request_remaining_v1());part=connection.recv(size-len(data))
                    if not part:raise PermissionError('short bounded process request')
                    data.extend(part)
                return bytes(data)
            count=struct.unpack('!I',exact(4))[0]
            if not 0<count<=4096:raise PermissionError('bounded v2 observer request required')
            q=_parse(SupervisorProcessRequestV2,exact(count))
            if not wall<q.caller_deadline<=min(wall+timedelta(seconds=30),self.config.expires_at):raise PermissionError('original observer end excessive or expired')
            end=min(end,tick+(q.caller_deadline-wall).total_seconds())
            with _request_fence_v1(float(end)):
                if (self.stop.is_set() or self.loop is None or not self.loop.is_alive() or self.error or self.mutation_uncertain
                    or not 0<=time.monotonic()-self.last_success<=self.config.scheduler_poll_seconds+2
                    or self.next_poll<time.monotonic()-self.config.scheduler_poll_seconds):raise PermissionError('actual scheduler loop unavailable')
                if not self.lock.acquire(timeout=max(0.,min(2.,request_remaining_v1(required=True)))):raise PermissionError('scheduler current read busy')
                try:packet,_due=self.fresh(q.caller_deadline)
                finally:self.lock.release()
                if packet.scope_sha256!=q.scope_sha256:raise PermissionError('actual observer and queue scope differ')
                self.current();request_remaining_v1();now=datetime.now(timezone.utc);until=min(now+timedelta(seconds=2),q.caller_deadline,packet.valid_until,self.config.capture_until)
                if until<=now:raise PermissionError('original observer end elapsed')
                value=dict(schema_version=2,purpose='meeting-process-currentness-v2',process_purpose='meeting-scheduler-process-v1',challenge=q.challenge,scope_sha256=packet.scope_sha256,runtime_sha256=self.runtime_sha,config_sha256=self.sha,queue_observation_sha256=packet.queue_observation_sha256,sequence=packet.version,checked_at=now.isoformat(),expires_at=until.isoformat())
                from oracle_brain.meetings.supervisor_process import SupervisorProcessObservationV2
                raw=canonical_bytes(SupervisorProcessObservationV2.model_validate_json(canonical_bytes(value)).model_dump(mode='json'))
                connection.settimeout(request_remaining_v1());connection.sendall(struct.pack('!I',len(raw))+raw)
    def run(self):
        c=self.config;path=Path(c.socket_file);parent=path.parent.lstat()
        if c.observer_uid!=os.getuid() or not stat.S_ISDIR(parent.st_mode) or parent.st_mode&0o077 or parent.st_uid!=os.getuid() or path.exists():raise PermissionError('independently provisioned unused private scheduler socket required')
        # No mkdir, untrusted stale unlink, receipt/replay initialization or grant.
        server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);identity=None
        try:
            server.bind(str(path));os.chmod(path,0o600);info=path.lstat();identity=(info.st_dev,info.st_ino);server.listen(4);server.settimeout(.2)
            self.loop=threading.Thread(target=self._poll,name='oracle-meeting-scheduler',daemon=True);self.loop.start()
            while not self.stop.is_set():
                try:connection,_=server.accept()
                except socket.timeout:continue
                with connection:
                    try:self.observe(connection)
                    except Exception:pass
        finally:
            self.stop.set();server.close()
            if self.loop is not None:self.loop.join(timeout=31)
            if self.loop is not None and self.loop.is_alive():raise PermissionError('scheduler cleanup unresolved')
            if identity is not None:
                current=path.lstat()
                if (current.st_dev,current.st_ino)!=identity:raise PermissionError('owned scheduler socket changed')
                path.unlink()


def run_installed_meeting_scheduler_v1():
    installed=_InstalledSchedulerV1()
    def stop(_signal,_frame):installed.stop.set()
    prior={value:signal.signal(value,stop) for value in (signal.SIGTERM,signal.SIGINT)}
    try:installed.run()
    finally:
        for value,handler in prior.items():signal.signal(value,handler)

if __name__=='__main__':run_installed_meeting_scheduler_v1()
