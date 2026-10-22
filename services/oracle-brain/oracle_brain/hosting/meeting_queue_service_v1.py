"""Fixed separately appointed queue mTLS custody; no task/provider authority.

Raw Trigger response headers can contain x-trigger-jwt, a run capability. They
remain private wire custody only: never returned, logged or reused as authority.
https://trigger.dev/docs/management/tasks/trigger
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from oracle_brain.meetings.queue_contracts import MAX_QUEUE_WIRE_V1
from .meeting_queue_v1 import MeetingQueueSettingsV1,MeetingQueueFactoryV1
from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
from .original_intake_v1 import _parse
from ._protected_control_listener_v1 import _protected_control_listener_v1,request_remaining_v1
HASH=r'^[a-f0-9]{64}$'

class MeetingQueueRequestV1(StrictRecord):
    operation:Literal['pending','claim','current','observe','status']
    ingress_event_id:UUID|None
    claim_id:UUID|None
    request_sha256:str|None=Field(pattern=HASH)
    raw_wire_hex:str|None=Field(max_length=MAX_QUEUE_WIRE_V1*2,pattern=r'^(?:[a-f0-9]{2})*$')
    error:Literal['network','timeout','framing','expired','unknown']|None
    caller_deadline:AwareDatetime
    @field_validator('schema_version',mode='before')
    @classmethod
    def schema(cls,value):
        if type(value) is not int or value!=1:raise ValueError('actual queue schema required')
        return value
    @model_validator(mode='after')
    def shape(self):
        if (self.operation!='pending')!=(self.ingress_event_id is not None):raise ValueError('closed opaque queue selector required')
        claimed=self.operation in ('current','observe')
        if claimed!=(self.claim_id is not None) or claimed!=(self.request_sha256 is not None):raise ValueError('exact queue claim required')
        if (self.operation=='observe')!=(self.raw_wire_hex is not None) or self.operation!='observe' and self.error is not None:raise ValueError('wire belongs only to own claim observation')
        return self

class MeetingQueuePacketV1(StrictRecord):
    purpose:Literal['meeting-ingress-queue-v1']
    principal_id:UUID
    workspace_id:UUID
    meeting_id:UUID
    ingress_event_id:UUID|None
    claim_id:UUID|None
    request_sha256:str|None=Field(pattern=HASH)
    state:Literal['idle','claimed','inflight','observed','UNKNOWN']
    fresh_claim:bool
    body:dict|None
    queue_pins:dict
    original_effect_deadline:AwareDatetime|None
    valid_until:AwareDatetime
    run_id:str|None=Field(min_length=1,max_length=256)
    pending_count:int=Field(ge=0,le=4096)
    unresolved_count:int=Field(ge=0,le=4096)
    qualification:Literal[False]
    task_completed_proven:Literal[False]
    remote_stop_proven:Literal[False]
    observation_only:Literal[True]
    @field_validator('fresh_claim','qualification','task_completed_proven','remote_stop_proven','observation_only',mode='before')
    @classmethod
    def flags(cls,value):
        if type(value) is not bool:raise ValueError('literal observation flags required')
        return value
    @model_validator(mode='after')
    def fresh_only(self):
        if self.fresh_claim!=(self.state=='claimed') or self.fresh_claim!=(self.body is not None):raise ValueError('fresh first claim alone carries body')
        return self

class MeetingQueuePeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['meeting-ingress-queue-peer-v1']
    meeting_id:UUID
    queue_config_sha256:str=Field(pattern=HASH)
    queue_admission_sha256:str=Field(pattern=HASH)

@dataclass(frozen=True)
class _QueuePeerSettings:
    queue:MeetingQueueSettingsV1
    peer:object
    @property
    def profile(self):return self.peer.profile
    def current(self):
        end=min(self.queue.current(),self.peer.current());p=self.profile;s=self.queue
        if (type(p) is not MeetingQueuePeerProfileV1 or p.meeting_id!=s.capture.config.meeting_id
            or p.queue_config_sha256!=s.sha256 or p.queue_admission_sha256!=s.capture.config.admission_sha256):
            raise PermissionError('exact independently installed queue peer required')
        return end

class _QueueAdapter:
    def __init__(self,settings):
        if type(settings) is not _QueuePeerSettings:raise PermissionError('fixed queue service required')
        self.settings=settings;self.factory=MeetingQueueFactoryV1(settings.queue)
    def execute_v1(self,raw):
        request_remaining_v1(required=True);q=_parse(MeetingQueueRequestV1,raw);s=self.settings
        now=datetime.now(timezone.utc)
        if not now<q.caller_deadline<=s.current() or (q.caller_deadline-now).total_seconds()>30:raise PermissionError('original queue request window required')
        f=self.factory;kw=dict(caller_deadline=q.caller_deadline)
        if q.operation=='pending':r=f.pending_v1(**kw)
        elif q.operation=='claim':r=f.claim_v1(q.ingress_event_id,**kw)
        elif q.operation=='status':r=f.status_v1(q.ingress_event_id,**kw)
        elif q.operation=='current':r=f.current_claim_v1(q.ingress_event_id,q.claim_id,q.request_sha256,**kw)
        else:r=f.receipt_v1(q.ingress_event_id,q.claim_id,q.request_sha256,bytes.fromhex(q.raw_wire_hex),error=q.error,**kw)
        request_remaining_v1(required=True);s.current();h=s.queue.capture.host.config
        return MeetingQueuePacketV1(purpose='meeting-ingress-queue-v1',principal_id=h.principal_id,workspace_id=h.workspace_id,
            **{name:getattr(r,name) for name in ('meeting_id','ingress_event_id','claim_id','request_sha256','state','fresh_claim','body','queue_pins','original_effect_deadline','run_id','pending_count','unresolved_count')},
            valid_until=min(r.valid_until,q.caller_deadline,s.current()),qualification=False,task_completed_proven=False,remote_stop_proven=False,observation_only=True)

def protected_meeting_queue_server_v1(settings,path,sha256):
    if type(settings) is not MeetingQueueSettingsV1:raise PermissionError('exact independently installed queue settings required')
    peer=_load_peer_settings_v1(settings.capture.host,path,sha256,MeetingQueuePeerProfileV1)
    fixed=_QueuePeerSettings(settings,peer);fixed.current()
    return _protected_control_listener_v1(fixed,_QueueAdapter(fixed),path='/v1/replacement/meetings/queue',
        parse_request=lambda raw:_parse(MeetingQueueRequestV1,raw),encode_response=lambda value:canonical_bytes(value.model_dump(mode='json')),
        maximum_request_bytes=65536,maximum_response_bytes=4096)
