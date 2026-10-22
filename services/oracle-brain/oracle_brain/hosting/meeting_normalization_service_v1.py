"""Distinct fixed processing-service boundary; no employee/provider adaptation."""
from dataclasses import dataclass
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from .replacement_public_view_v1 import Public
from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
from .original_intake_v1 import _parse
from .meeting_normalization_v1 import MeetingNormalizationSettingsV1,MeetingNormalizationFactoryV1
from ._protected_control_listener_v1 import _protected_control_listener_v1,request_remaining_v1


class MeetingNormalizationRequestV1(StrictRecord):
    ingress_event_id:UUID
    caller_deadline:AwareDatetime
    @field_validator('schema_version',mode='before')
    @classmethod
    def integer_schema(cls,value):
        if type(value) is not int or value!=1:raise ValueError('actual normalization schema required')
        return value


class NormalizationSourceLinkV1(Public):
    source_id:UUID
    revision:int=Field(ge=1)
    original_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    byte_count:int=Field(ge=1,le=1048576)


class MeetingNormalizationPacketV1(StrictRecord):
    principal_id:UUID
    workspace_id:UUID
    meeting_id:UUID
    ingress_event_id:UUID
    state:Literal['final_artifact_pending','intake_claimed','UNKNOWN','awaiting_independently_installed_exact_reading_review','source_unavailable']
    valid_until:AwareDatetime
    source_binding:NormalizationSourceLinkV1|None
    qualification:Literal[False]
    source_read_permission:Literal[False]
    observation_only:Literal[True]
    @field_validator('schema_version','qualification','source_read_permission','observation_only',mode='before')
    @classmethod
    def actual_flags(cls,value,info):
        if info.field_name=='schema_version':
            if type(value) is not int or value!=1:raise ValueError('actual schema required')
        elif type(value) is not bool:raise ValueError('literal observation flags required')
        return value
    @model_validator(mode='after')
    def pending_only(self):
        if (self.state=='awaiting_independently_installed_exact_reading_review')!=(self.source_binding is not None):
            raise ValueError('exact pending opaque source linkage required')
        return self


class MeetingNormalizationPeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['meeting-normalization-worker-peer-v1']
    meeting_id:UUID
    normalization_config_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    normalization_admission_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


@dataclass(frozen=True)
class _NormalizationPeerSettings:
    normalization:MeetingNormalizationSettingsV1
    peer:object
    @property
    def profile(self):return self.peer.profile
    def current(self):
        end=min(self.normalization.current(),self.peer.current())
        p=self.profile;s=self.normalization
        if (type(p) is not MeetingNormalizationPeerProfileV1
                or p.meeting_id!=s.capture.config.meeting_id
                or p.normalization_config_sha256!=s.config_sha256
                or p.normalization_admission_sha256!=s.capture.config.admission_sha256):
            raise PermissionError('exact independent normalization service installation differs')
        return end


class _NormalizationAdapter:
    def __init__(self,settings):
        if type(settings) is not _NormalizationPeerSettings:raise PermissionError('fixed separately installed normalization service required')
        self.settings=settings
        self.factory=MeetingNormalizationFactoryV1(settings.normalization)
    def execute_v1(self,raw):
        request_remaining_v1(required=True)
        q=_parse(MeetingNormalizationRequestV1,raw);s=self.settings;end=s.current()
        if not datetime.now(timezone.utc)<q.caller_deadline<=end or (q.caller_deadline-datetime.now(timezone.utc)).total_seconds()>30:
            raise PermissionError('original normalization request window required')
        result=self.factory.process_ingress_v1(q.ingress_event_id,caller_deadline=q.caller_deadline)
        request_remaining_v1(required=True);s.current()
        c=s.normalization.capture;source=result.source_binding
        return MeetingNormalizationPacketV1(principal_id=c.host.config.principal_id,
            workspace_id=c.host.config.workspace_id,meeting_id=c.config.meeting_id,
            ingress_event_id=result.ingress_event_id,state=result.state,
            valid_until=min(result.valid_until,q.caller_deadline,s.current()),
            source_binding=None if source is None else NormalizationSourceLinkV1(
                source_id=source.source_id,revision=source.revision,original_sha256=source.original_sha256,byte_count=source.byte_count),
            qualification=False,source_read_permission=False,observation_only=True)


def protected_meeting_normalization_server_v1(settings,path,sha256):
    if type(settings) is not MeetingNormalizationSettingsV1:raise PermissionError('same fixed installed normalization owner required')
    peer=_load_peer_settings_v1(settings.capture.host,path,sha256,MeetingNormalizationPeerProfileV1)
    fixed=_NormalizationPeerSettings(settings,peer);fixed.current()
    return _protected_control_listener_v1(fixed,_NormalizationAdapter(fixed),path='/v1/replacement/meetings/normalize',
        parse_request=lambda raw:_parse(MeetingNormalizationRequestV1,raw),
        encode_response=lambda result:canonical_bytes(result.model_dump(mode='json')),
        maximum_request_bytes=4096,maximum_response_bytes=4096)
