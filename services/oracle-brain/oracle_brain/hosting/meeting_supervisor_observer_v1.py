"""Separately installed Linux meeting supervisor observer, not an issuer.

This source observes concrete processes and its own current durable queue.
Only this separately appointed process reads the independently installed signer.
A creator verifies this NEW signed purpose; it cannot run the signing owner.
Actual installation and provider STOP acceptance remain independent holds.
"""
from datetime import datetime,timedelta,timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid5,NAMESPACE_URL
import base64,hashlib,json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding,PublicFormat
from pydantic import AwareDatetime,Field,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.artifact_storage import _write_private_at
from oracle_brain.meetings.supervisor_process import InstalledSupervisorProcessV1,observe_supervisor_process_v1,InstalledSupervisorProcessV2,observe_supervisor_process_v2
from .parent_observer_v2 import MeetingSupervisorAdmissionV1,MeetingSupervisorWitnessV1,MEETING_SUPERVISOR_DOMAIN,MeetingSupervisorAdmissionV2,MeetingSupervisorWitnessV2,MEETING_SUPERVISOR_DOMAIN_V2
from .original_intake_v1 import ProtectedInputV1,_pinned,_parse
from .meeting_capture_v1 import MeetingCaptureSettingsV1,MeetingCaptureFactoryV1
from ._protected_control_listener_v1 import request_remaining_v1,_protected_control_listener_v1
from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
HASH=r'^[a-f0-9]{64}$'
class MeetingSupervisorObserverConfigV1(StrictRecord):
    purpose:Literal['meeting-supervisor-observer-owner-v1']
    meeting_config_sha256:str=Field(pattern=HASH)
    observer_admission:ProtectedInputV1
    scheduler_process:ProtectedInputV1
    stop_worker_process:ProtectedInputV1
    signing_key:ProtectedInputV1
class MeetingSupervisorRequestV1(StrictRecord):
    purpose:Literal['meeting-supervisor-currentness-v1']
    challenge:str=Field(pattern=HASH)
    caller_deadline:AwareDatetime

class MeetingSupervisorObserverConfigV2(MeetingSupervisorObserverConfigV1):
    schema_version:Literal[2]=2
    purpose:Literal['meeting-supervisor-observer-owner-v2']
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,value):
        if type(value) is not int or value!=2:raise ValueError('exact v2 observer configuration required')
        return value

class MeetingSupervisorRequestV2(MeetingSupervisorRequestV1):
    schema_version:Literal[2]=2
    purpose:Literal['meeting-supervisor-currentness-v2']
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,value):
        if type(value) is not int or value!=2:raise ValueError('exact v2 observer request required')
        return value

def parse_supervisor_request_v1(raw):return _parse(MeetingSupervisorRequestV1,raw)
def parse_supervisor_request_v2(raw):return _parse(MeetingSupervisorRequestV2,raw)

def supervision_queue_commitment_v1(head):
    """Same operational queue identity for observer, scheduler and STOP worker."""
    return digest(dict(meeting_id=str(head.meeting_id),capture_until=head.capture_until.astimezone(timezone.utc).isoformat(),version=head.version,state=head.state,pending_ingress=[str(x) for x in head.pending_ingress],supervision_binding=head.supervision_binding))

def supervisor_receipt_binding_v1(raw,witness):
    """Deterministic descriptive selector. Actual independent SQL row decides."""
    seal=hashlib.sha256(raw).hexdigest();scope=witness.scope
    event=uuid5(NAMESPACE_URL,'oracle-meeting-supervisor:'+witness.admission_hash+':'+witness.challenge)
    payload=dict(scope_sha256=digest(scope.model_dump(mode='json')),create_operation_id=str(scope.create_operation_id),request_sha256=scope.create_request_sha256,witness_sha256=seal,witness_object_key=f'meeting-supervisor/{scope.workspace_id}/{scope.meeting_id}/{seal}.bin',nonce=witness.challenge,observed_at=witness.checked_at.isoformat(),valid_until=witness.expires_at.isoformat(),scheduler_observation_sha256=witness.scheduler_observation_sha256)
    event_sha=digest(dict(action='supervised',body=payload))
    return event,event_sha,payload

@dataclass(frozen=True)
class MeetingSupervisorObserverSettingsV1:
    meeting:MeetingCaptureSettingsV1
    config:MeetingSupervisorObserverConfigV1
    path:str
    sha256:str
    def current(self):
        request_remaining_v1(required=True)
        if _parse(type(self.config),_pinned(self.path,self.sha256))!=self.config or self.config.meeting_config_sha256!=self.meeting.config_sha256:raise PermissionError('installed observer owner changed')
        return self.meeting.current()

def load_meeting_supervisor_observer_settings_v1(meeting,path,sha256):
    if type(meeting) is not MeetingCaptureSettingsV1 or meeting.config.channel!='worker':raise PermissionError('separately installed observer service settings required')
    config=_parse(MeetingSupervisorObserverConfigV1,_pinned(path,sha256))
    if config.meeting_config_sha256!=meeting.config_sha256:raise PermissionError('exact observer meeting settings required')
    return MeetingSupervisorObserverSettingsV1(meeting,config,str(path),sha256)


@dataclass(frozen=True)
class MeetingSupervisorObserverSettingsV2(MeetingSupervisorObserverSettingsV1):
    config:MeetingSupervisorObserverConfigV2

def load_meeting_supervisor_observer_settings_v2(meeting,path,sha256):
    if type(meeting) is not MeetingCaptureSettingsV1 or meeting.config.channel!='worker':raise PermissionError('separately installed v2 observer service settings required')
    config=_parse(MeetingSupervisorObserverConfigV2,_pinned(path,sha256))
    if config.meeting_config_sha256!=meeting.config_sha256:raise PermissionError('exact v2 observer meeting settings required')
    return MeetingSupervisorObserverSettingsV2(meeting,config,str(path),sha256)

class MeetingSupervisorObserverFactoryV1:
    def __init__(self,settings):
        v2=type(self) is MeetingSupervisorObserverFactoryV2
        if type(self) not in (MeetingSupervisorObserverFactoryV1,MeetingSupervisorObserverFactoryV2) or type(settings) is not (MeetingSupervisorObserverSettingsV2 if v2 else MeetingSupervisorObserverSettingsV1):raise PermissionError('exact installed observer owner required')
        self.settings=settings;self.capture=MeetingCaptureFactoryV1(settings.meeting)
    def execute_v1(self,raw):
        v2=type(self) is MeetingSupervisorObserverFactoryV2
        q=(parse_supervisor_request_v2 if v2 else parse_supervisor_request_v1)(raw);s=self.settings;c=s.config
        request_remaining_v1(required=True);end=s.current()
        if not datetime.now(timezone.utc)<q.caller_deadline<=end:raise PermissionError('original observer request window required')
        admission=_parse(MeetingSupervisorAdmissionV2 if v2 else MeetingSupervisorAdmissionV1,_pinned(c.observer_admission.path,c.observer_admission.sha256))
        scheduler=_parse(InstalledSupervisorProcessV2 if v2 else InstalledSupervisorProcessV1,_pinned(c.scheduler_process.path,c.scheduler_process.sha256))
        stop=_parse(InstalledSupervisorProcessV2 if v2 else InstalledSupervisorProcessV1,_pinned(c.stop_worker_process.path,c.stop_worker_process.sha256))
        scope=admission.scope;host=s.meeting.host.config
        if (admission.principal_id!=host.principal_id or scope.workspace_id!=host.workspace_id or scope.meeting_id!=s.meeting.config.meeting_id
            or scope.provider_account!=s.meeting.config.provider_account or scope.capture_until!=s.meeting.config.capture_until
            or scheduler.scope!=scope or stop.scope!=scope or scheduler.purpose!='meeting-scheduler-process-v1' or stop.purpose!='meeting-stop-worker-process-v1'
            or scheduler.peer_pid==stop.peer_pid or c.observer_admission.sha256!=digest(admission.model_dump(mode='json'))):raise PermissionError('independent exact active supervisor topology required')
        if v2 and (admission.scheduler_process_sha256!=c.scheduler_process.sha256 or admission.stop_process_sha256!=c.stop_worker_process.sha256
            or digest(scheduler.model_dump(mode='json'))!=c.scheduler_process.sha256 or digest(stop.model_dump(mode='json'))!=c.stop_worker_process.sha256):
            raise PermissionError('actual independently pinned v2 process profile bytes differ')
        queue=self.capture.due_stop_v1(caller_deadline=q.caller_deadline)
        from oracle_brain.meetings.create_stop_relation import CreateOperationStopRelationV1
        if queue.stop_relation is None:raise PermissionError('independently installed unattended STOP relation missing')
        relation=CreateOperationStopRelationV1.model_validate_json(canonical_bytes(queue.stop_relation))
        for field in ('workspace_id','meeting_id','provider_account','create_operation_id','create_request_sha256','scheduler_id','stop_owner_id','scheduler_runtime_sha256','scheduler_config_sha256','stop_runtime_sha256','stop_config_sha256','capture_until','stop_valid_from','stop_until','original_horizon'):
            if getattr(relation,field)!=getattr(scope,field):raise PermissionError('actual unattended STOP relation differs from observed installed process scope')
        if relation.sha256!=queue.stop_mapping_sha256 or relation.supervision_scope_sha256!=digest(scope.model_dump(mode='json')) or relation.expires_at<scope.stop_until:
            raise PermissionError('exact independent STOP relation scope and digest required')
        for field in ('capture_until','stop_valid_from','stop_until','original_horizon','scheduler_poll_seconds','stop_request_seconds','safety_allowance_seconds','stop_margin_seconds'):
            if getattr(queue,field)!=getattr(scope,field):raise PermissionError('actual independently installed STOP queue window differs')
        if datetime.now(timezone.utc)>=queue.due_at or stop.expires_at<scope.stop_until:raise PermissionError('full original STOP margin and active post-capture STOP owner required')
        before=self.capture.supervision_head_v1(caller_deadline=q.caller_deadline);binding=before.supervision_binding
        if before.version<1 or type(binding) is not dict or binding.get('scope_sha256')!=digest(scope.model_dump(mode='json')) or binding.get('stop_relation_sha256')!=relation.sha256:raise PermissionError('actual independently installed durable queue missing')
        if binding.get('create_operation_id') not in (None,str(scope.create_operation_id)) or binding.get('create_request_sha256') not in (None,scope.create_request_sha256):raise PermissionError('actual create operation differs')
        expected_queue=supervision_queue_commitment_v1(before)
        observe=observe_supervisor_process_v2 if v2 else observe_supervisor_process_v1
        scheduled=observe(scheduler,challenge=q.challenge,deadline=q.caller_deadline)
        stopped=observe(stop,challenge=q.challenge,deadline=q.caller_deadline)
        if scheduled.queue_observation_sha256!=expected_queue or stopped.queue_observation_sha256!=expected_queue:raise PermissionError('actual scheduler STOP queue differs')
        after=self.capture.supervision_head_v1(caller_deadline=q.caller_deadline)
        if supervision_queue_commitment_v1(after)!=expected_queue:raise PermissionError('actual queue changed during observation')
        request_remaining_v1(required=True);s.current();now=datetime.now(timezone.utc)
        expires=min(admission.expires_at,scope.capture_until,scheduled.expires_at,stopped.expires_at,after.valid_until,q.caller_deadline,now+timedelta(seconds=admission.max_age_seconds))
        if expires<=now:raise PermissionError('actual supervisor observation expired')
        witness=(MeetingSupervisorWitnessV2 if v2 else MeetingSupervisorWitnessV1)(**(dict(schema_version=2,scheduler_process_sha256=c.scheduler_process.sha256,stop_process_sha256=c.stop_worker_process.sha256) if v2 else {}),purpose='meeting-supervisor-currentness-v2' if v2 else 'meeting-supervisor-currentness-v1',admission_hash=c.observer_admission.sha256,scope=scope,principal_id=admission.principal_id,observer_uri=admission.observer_uri,client_uri=admission.client_uri,challenge=q.challenge,sequence=after.version+1,scheduler_observation_sha256=digest(dict(scheduler=scheduled.model_dump(mode='json'),stop_worker=stopped.model_dump(mode='json'),queue=expected_queue)),checked_at=now,expires_at=expires)
        if v2:
            for record,ref in ((scheduler,c.scheduler_process),(stop,c.stop_worker_process)):
                if _parse(InstalledSupervisorProcessV2,_pinned(ref.path,ref.sha256))!=record:raise PermissionError('v2 process profile changed during actual observation')
        keybytes=_pinned(c.signing_key.path,c.signing_key.sha256,32)
        if len(keybytes)!=32:raise PermissionError('exact independently installed observer signer required')
        key=Ed25519PrivateKey.from_private_bytes(keybytes)
        if key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw).hex()!=admission.signing_public_key:raise PermissionError('independent observer signer differs')
        value=witness.model_dump(mode='json');signature=base64.b64encode(key.sign((MEETING_SUPERVISOR_DOMAIN_V2 if v2 else MEETING_SUPERVISOR_DOMAIN)+canonical_bytes(value))).decode();signed=canonical_bytes(dict(witness=value,signature=signature))
        event,_event_sha,payload=supervisor_receipt_binding_v1(signed,witness)
        request_remaining_v1(required=True);s.current()
        h=s.meeting.host.config
        _write_private_at(Path(h.storage_root),payload['witness_object_key'].split('/'),signed,expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
        receipt=self.capture.transition_v1(expected_head=after.version,operation_id=event,action='supervised',payload=payload,caller_deadline=q.caller_deadline)
        if receipt.event_id!=event or receipt.version!=witness.sequence:raise PermissionError('actual immutable supervisor receipt differs')
        request_remaining_v1(required=True);s.current();return signed

class MeetingSupervisorObserverFactoryV2(MeetingSupervisorObserverFactoryV1):
    """Same observation/signing owner; closed v2 constructor only."""

class MeetingSupervisorPeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['meeting-supervisor-peer-v1']
    observer_config_sha256:str=Field(pattern=HASH)
@dataclass(frozen=True)
class _ObserverPeerSettings:
    observer:MeetingSupervisorObserverSettingsV1
    peer:object
    @property
    def profile(self):return self.peer.profile
    def current(self):
        # Startup has no operational request context; only immutable installation
        # reads happen there. Every actual effect still requires the fence.
        if self.profile.observer_config_sha256!=self.observer.sha256:raise PermissionError('actual observer peer differs')
        return min(self.peer.current(),self.observer.meeting.current())
def protected_meeting_supervisor_server_v1(settings,path,sha256):
    if type(settings) is not MeetingSupervisorObserverSettingsV1:raise PermissionError('exact separate observer installation required')
    peer=_load_peer_settings_v1(settings.meeting.host,path,sha256,MeetingSupervisorPeerProfileV1);installed=_ObserverPeerSettings(settings,peer);installed.current()
    def encode(value):
        if type(value) is not bytes or not 0<len(value)<=16384:raise PermissionError('bounded signed supervisor response required')
        return value
    return _protected_control_listener_v1(installed,MeetingSupervisorObserverFactoryV1(settings),path='/v1/meetings/supervisor/current',parse_request=parse_supervisor_request_v1,encode_response=encode,maximum_request_bytes=4096,maximum_response_bytes=16384)


class MeetingSupervisorPeerProfileV2(MeetingSupervisorPeerProfileV1):
    schema_version:Literal[2]=2
    purpose:Literal['meeting-supervisor-peer-v2']
    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,value):
        if type(value) is not int or value!=2:raise ValueError('exact v2 observer peer required')
        return value

def protected_meeting_supervisor_server_v2(settings,path,sha256):
    if type(settings) is not MeetingSupervisorObserverSettingsV2:raise PermissionError('exact separate v2 observer installation required')
    peer=_load_peer_settings_v1(settings.meeting.host,path,sha256,MeetingSupervisorPeerProfileV2);installed=_ObserverPeerSettings(settings,peer);installed.current()
    def encode(value):
        if type(value) is not bytes or not 0<len(value)<=16384:raise PermissionError('bounded signed supervisor response required')
        return value
    return _protected_control_listener_v1(installed,MeetingSupervisorObserverFactoryV2(settings),path='/v2/meetings/supervisor/current',parse_request=parse_supervisor_request_v2,encode_response=encode,maximum_request_bytes=4096,maximum_response_bytes=16384)
