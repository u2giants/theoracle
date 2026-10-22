"""Concrete queue custody in the SAME capture owner; no provider client/issuer.

Independent installation supplies exact key/project/environment/account pins.
Raw wire arrives only over the separate fixed service peer. It is retained before
interpretation and is observation, never task/source/remote-stop proof.
"""
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from typing import Literal
from uuid import UUID
import hashlib
from pydantic import AwareDatetime,Field,model_validator
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.operating_model.artifact_storage import _write_private_at
from oracle_brain.meetings.queue_contracts import QUEUE_PIN_FIELDS_V1,TASK,MAX_QUEUE_WIRE_V1,observe_queue_wire_v1
from .meeting_capture_v1 import MeetingCaptureSettingsV1,MeetingCaptureFactoryV1
from .original_intake_v1 import _pinned,_parse
from ._protected_control_listener_v1 import request_remaining_v1
HASH=r'^[a-f0-9]{64}$'

class MeetingQueueConfigV1(StrictRecord):
    purpose:Literal['meeting-ingress-queue-consumer-v1']
    capture_config_sha256:str=Field(pattern=HASH)
    queue_project_ref:str=Field(min_length=1,max_length=256)
    queue_environment_id:str=Field(min_length=1,max_length=256)
    queue_account_id:str=Field(min_length=1,max_length=256)
    queue_task_id:Literal['oracle2-meeting-ingress-normalize-v1']
    queue_credential_sha256:str=Field(pattern=HASH)
    queue_installation_receipt_sha256:str=Field(pattern=HASH)
    queue_target_descriptor_sha256:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_processing_horizon:AwareDatetime
    @model_validator(mode='after')
    def installed(self):
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.original_processing_horizon:raise ValueError('independent finite queue installation required')
        for name in ('queue_project_ref','queue_environment_id','queue_account_id'):
            value=getattr(self,name)
            if value!=value.strip() or any(ord(x)<32 or ord(x)==127 for x in value):raise ValueError('canonical installed queue identity required')
        return self

@dataclass(frozen=True)
class MeetingQueueSettingsV1:
    capture:MeetingCaptureSettingsV1
    config:MeetingQueueConfigV1
    path:Path
    sha256:str
    issuer_actor:UUID
    reviewer_actor:UUID
    def current(self):
        request_remaining_v1(required=False);c=self.config
        if (_parse(MeetingQueueConfigV1,_pinned(self.path,self.sha256))!=c or c.capture_config_sha256!=self.capture.config_sha256
            or c.issuer_actor!=self.issuer_actor or c.reviewer_actor!=self.reviewer_actor
            or self.capture.host.config.principal_id in (c.issuer_actor,c.reviewer_actor) or self.capture.config.channel!='worker'):
            raise PermissionError('independently installed own queue scope changed')
        end=min(self.capture.current(),c.expires_at,c.original_processing_horizon)
        if not c.valid_from<=datetime.now(timezone.utc)<end:raise PermissionError('original queue horizon elapsed')
        return end

def load_meeting_queue_settings_v1(capture,path,sha256,issuer,reviewer):
    if type(capture) is not MeetingCaptureSettingsV1:raise TypeError('exact separately installed capture owner settings required')
    s=MeetingQueueSettingsV1(capture,_parse(MeetingQueueConfigV1,_pinned(path,sha256)),Path(path),sha256,issuer,reviewer);s.current();return s

class MeetingQueueFactoryV1:
    def __init__(self,settings):
        if type(settings) is not MeetingQueueSettingsV1:raise TypeError('fixed separately installed queue settings required')
        settings.current();self.settings=settings;self.capture=MeetingCaptureFactoryV1(settings.capture)
    def _call(self,command,ingress,deadline,wire=None):
        request_remaining_v1(required=True);s=self.settings;s.current()
        result=self.capture._enqueue_binding_v1(command,ingress,caller_deadline=deadline,wire_receipt=wire)
        expected={name:getattr(s.config,name) for name in QUEUE_PIN_FIELDS_V1}
        if result.queue_pins!=expected or result.original_processing_horizon!=s.config.original_processing_horizon:
            raise PermissionError('actual independently installed queue commitment differs')
        s.current();request_remaining_v1(required=True);return result
    def pending_v1(self,*,caller_deadline):return self._call('pending',None,caller_deadline)
    def claim_v1(self,ingress,*,caller_deadline):return self._call('claim',ingress,caller_deadline)
    def status_v1(self,ingress,*,caller_deadline):return self._call('status',ingress,caller_deadline)
    def current_claim_v1(self,ingress,claim,request_sha256,*,caller_deadline):
        if type(ingress) is not UUID or type(claim) is not UUID or type(request_sha256) is not str:raise ValueError('exact immutable queue claim required')
        status=self.status_v1(ingress,caller_deadline=caller_deadline)
        if status.claim_id!=claim or status.request_sha256!=request_sha256 or status.original_effect_deadline is None:raise PermissionError('actual original queue claim differs')
        result=self._call('current',ingress,min(caller_deadline,status.original_effect_deadline))
        if result.claim_id!=claim or result.request_sha256!=request_sha256 or result.state!='inflight':raise PermissionError('spent queue claim cannot execute')
        return result
    def receipt_v1(self,ingress,claim,request_sha256,raw_wire,*,error=None,caller_deadline):
        if type(raw_wire) is not bytes or len(raw_wire)>MAX_QUEUE_WIRE_V1 or error is not None and error not in ('network','timeout','framing','expired','unknown'):raise ValueError('bounded actual full queue wire required')
        prior=self.status_v1(ingress,caller_deadline=caller_deadline)
        if prior.claim_id!=claim or prior.request_sha256!=request_sha256 or prior.original_effect_deadline is None:raise PermissionError('actual retained own queue receipt claim required')
        actual=self._call('current',ingress,min(caller_deadline,prior.original_effect_deadline));s=self.settings;h=s.capture.host.config
        if actual.claim_id!=claim or actual.request_sha256!=request_sha256 or actual.fresh_claim or actual.body is not None:raise PermissionError('queue observation cannot reclaim body')
        deadline=min(caller_deadline,actual.original_effect_deadline);request_remaining_v1(required=True);s.current()
        parts=['meeting-queue',str(h.workspace_id),str(s.capture.config.meeting_id),str(ingress),str(claim),'trigger-response.wire']
        _write_private_at(Path(h.storage_root),parts,raw_wire,expected_root=(h.storage_device,h.storage_inode,h.storage_uid))
        # SAME immutable private wire is persisted BEFORE semantic observation.
        current=self._call('current',ingress,deadline)
        if current.claim_id!=claim or current.request_sha256!=request_sha256:raise PermissionError('actual retained queue claim changed')
        observation=observe_queue_wire_v1(raw_wire,error=error)
        wire=dict(claim_id=str(claim),request_sha256=request_sha256,raw_object_key='/'.join(parts),raw_sha256=hashlib.sha256(raw_wire).hexdigest(),raw_byte_count=len(raw_wire),observation=observation)
        return self._call('record',ingress,deadline,wire)
