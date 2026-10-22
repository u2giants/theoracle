"""Closed installed meeting listeners sharing the retained lifecycle owner.

Separate service identities are selected by server startup, never a request.
No profile grants capture, source access, employee identity or provider effects.
"""
from dataclasses import dataclass
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
from .meeting_capture_v1 import (MeetingCaptureSettingsV1,MeetingCaptureFactoryV1,
    parse_meeting_control_v1,parse_meeting_ingress_v1)
from ._protected_control_listener_v1 import _protected_control_listener_v1
HASH=r'^[a-f0-9]{64}$'

class MeetingControlPeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['replacement-meeting-control-peer-v1']
    meeting_config_sha256:str=Field(pattern=HASH)
    meeting_id:UUID
class MeetingIngressPeerProfileV1(RequesterPeerProfileV1):
    purpose:Literal['replacement-meeting-ingress-peer-v1']
    meeting_config_sha256:str=Field(pattern=HASH)
    meeting_id:UUID
    provider_account:str=Field(min_length=1,max_length=256)
    verifier_secret_sha256:str=Field(pattern=HASH)

class MeetingPublicMetadataV1(StrictRecord):
    meeting_id:UUID
    version:int=Field(ge=0,le=16384)
    state:Literal['not_invited','invited','joining','pending_mapping','waiting_room','recording_permission_pending','recording_permission_denied','capturing','capture_ended','processing','final_artifact_pending','capture_status_unknown','review','failed','UNKNOWN','cancelled']
    event_id:UUID|None
    ingress_id:UUID|None
    pending_count:int=Field(ge=0,le=4096)
    valid_until:AwareDatetime
    qualification:Literal[False]
    remote_stop_proven:Literal[False]
    observation_only:Literal[True]
    @field_validator('qualification','remote_stop_proven','observation_only',mode='before')
    @classmethod
    def actual_bool(cls,v):
        if type(v) is not bool:raise ValueError('actual observation flags required')
        return v

def _encode(value):
    # Preserve exact backend UTC wire representation; no inference of ready data.
    raw=canonical_bytes(value);MeetingPublicMetadataV1.model_validate_json(raw)
    return raw
@dataclass(frozen=True)
class _MeetingPeerSettings:
    meeting:MeetingCaptureSettingsV1
    peer:object
    @property
    def profile(self):return self.peer.profile
    def current(self):
        end=min(self.meeting.current(),self.peer.current());p=self.profile;c=self.meeting.config
        if p.meeting_config_sha256!=self.meeting.config_sha256 or p.meeting_id!=c.meeting_id:raise PermissionError('exact installed meeting peer differs')
        if type(p) is MeetingIngressPeerProfileV1 and (p.provider_account!=c.provider_account or p.verifier_secret_sha256!=c.verifier_secret_sha256):raise PermissionError('installed provider account differs')
        return end

def protected_meeting_control_server_v1(settings,peer_profile_path,peer_profile_sha256):
    if type(settings) is not MeetingCaptureSettingsV1 or settings.config.channel!='employee-control':raise PermissionError('fixed independently installed employee control required')
    peer=_load_peer_settings_v1(settings.host,peer_profile_path,peer_profile_sha256,MeetingControlPeerProfileV1)
    installed=_MeetingPeerSettings(settings,peer);installed.current()
    return _protected_control_listener_v1(installed,MeetingCaptureFactoryV1(settings),path='/v1/replacement/meetings/control',parse_request=parse_meeting_control_v1,encode_response=_encode,maximum_request_bytes=16384,maximum_response_bytes=16384)

def protected_meeting_ingress_server_v1(settings,peer_profile_path,peer_profile_sha256):
    if type(settings) is not MeetingCaptureSettingsV1 or settings.config.channel!='provider-ingress':raise PermissionError('fixed independently installed provider ingress required')
    peer=_load_peer_settings_v1(settings.host,peer_profile_path,peer_profile_sha256,MeetingIngressPeerProfileV1)
    installed=_MeetingPeerSettings(settings,peer);installed.current()
    return _protected_control_listener_v1(installed,MeetingCaptureFactoryV1(settings),path='/v1/replacement/meetings/ingress',parse_request=parse_meeting_ingress_v1,encode_response=_encode,maximum_request_bytes=1400000,maximum_response_bytes=16384)
