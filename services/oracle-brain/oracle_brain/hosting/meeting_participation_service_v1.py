"""Fixed host control mTLS listener; no sender body/observer/worker endpoint.

Shares the existing protected peer/framing/lifecycle owner. It is not installed
or selected automatically and cannot appoint a host, sender or observer.
"""
from dataclasses import dataclass
from typing import Literal

from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes
from oracle_brain.meetings.participation_control_contracts_v1 import (
    ParticipationControlV1,parse_participation_control_v1,
)


def _host_metadata(value):
    # Internal SQL observation and source selectors are never browser authority.
    keys=('meeting_id','head_revision','generation','host_enabled','proactive_enabled','proactive_count',
          'visible_message_proven','remote_stop_proven','executable','valid_until')
    return {key:value[key] for key in keys}


def protected_meeting_participation_server_v1(factory,peer_profile_path,expected_peer_profile_sha256):
    from pydantic import Field
    from .meeting_participation_v1 import MeetingParticipationFactoryV1
    from .replacement_request_service_v1 import RequesterPeerProfileV1,_load_peer_settings_v1
    from ._protected_control_listener_v1 import _protected_control_listener_v1

    if type(factory) is not MeetingParticipationFactoryV1 or factory.settings.config.kind!='host':
        raise PermissionError('exact installed host participation owner required')

    class HostParticipationPeerV1(RequesterPeerProfileV1):
        purpose: Literal['meeting-participation-host-peer-v1']
        participation_config_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
        capture_config_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    peer=_load_peer_settings_v1(factory.settings.capture_settings.host,peer_profile_path,
                                expected_peer_profile_sha256,HostParticipationPeerV1)

    @dataclass(frozen=True)
    class BoundHostPeer:
        profile: object = peer.profile

        def current(self):
            p=self.profile;s=factory.settings
            if (p.participation_config_sha256!=s.config_sha256
                    or p.capture_config_sha256!=s.capture_settings.config_sha256):
                raise PermissionError('exact installed host peer/participation pins changed')
            return min(peer.current(),s.current())

    class HostControl:
        def execute_v1(self,raw):
            request=parse_participation_control_v1(raw)
            if type(request) is ParticipationControlV1:
                value=factory.control_v1(expected_head=request.expected_head,operation=request.command_id,
                    enabled=request.enabled,proactive_enabled=request.proactive_enabled,
                    cooldown_seconds=request.cooldown_seconds,max_proactive=request.max_proactive,
                    caller_deadline=request.caller_deadline)
            else:
                value=factory.status_v1(caller_deadline=request.caller_deadline)
            return _host_metadata(value)

    return _protected_control_listener_v1(BoundHostPeer(),HostControl(),
        path='/v1/replacement/meetings/participation/control',parse_request=parse_participation_control_v1,
        encode_response=canonical_bytes,maximum_request_bytes=65536,maximum_response_bytes=4096)
