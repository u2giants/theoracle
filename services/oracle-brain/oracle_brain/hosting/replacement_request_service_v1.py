"""Uninstalled, fixed mTLS CONTROL metadata listener. Consumes existing pins only.

No user identity, role, appointment, deadline or result authority is issued here.
An uncertain/late SQL outcome is refused without retry. Actual installation and
browser authentication remain independently controlled obligations.
"""
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
from pathlib import Path
import threading
import time
from typing import Literal
from uuid import UUID

from cryptography import x509
from pydantic import AwareDatetime, Field, field_validator, model_validator

from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes
from .gateway import MutualTLSServer, server_tls
from .original_intake_v1 import OriginalIntakeSettingsV1, _pinned
from .replacement_requester_v1 import (
    ReplacementRequesterFactoryV1, RequesterControlMetadataV1, parse_requester_request_v1,
)
from .replacement_transport_v1 import fixed_request_length_v1, read_request_body_v1, peer_der_v1

HASH = r'^[a-f0-9]{64}$'
PATH = '/v1/replacement/control'


class RequesterPeerProfileV1(StrictRecord):
    """Installation input, not a new grant/issuer or authority source."""
    purpose: Literal['replacement-requester-peer-v1']
    intake_config_sha256: str = Field(pattern=HASH)
    intake_appointment_sha256: str = Field(pattern=HASH)
    principal_id: UUID
    workspace_id: UUID
    runtime_hash: str = Field(pattern=HASH)
    registry_hash: str = Field(pattern=HASH)
    client_uri: str = Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    client_certificate_sha256: str = Field(pattern=HASH)
    listen_host: str
    listen_port: int = Field(strict=True, ge=0, le=65535)
    server_hostname: str = Field(pattern=r'^[a-zA-Z0-9.-]{1,253}$')
    server_certificate_file: str
    server_certificate_sha256: str = Field(pattern=HASH)
    server_key_file: str
    server_key_sha256: str = Field(pattern=HASH)
    client_ca_file: str
    client_ca_sha256: str = Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @field_validator('schema_version', mode='before')
    @classmethod
    def version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('exact requester profile version required')
        return value

    @model_validator(mode='after')
    def closed(self):
        ipaddress.ip_address(self.listen_host)
        if (not self.valid_from < self.expires_at <= self.original_horizon
                or len({self.principal_id, self.issuer_actor, self.reviewer_actor}) != 3):
            raise ValueError('finite distinct requester peer profile required')
        paths = (self.server_certificate_file, self.server_key_file, self.client_ca_file)
        if len(set(paths)) != 3 or any(not Path(p).is_absolute() or '..' in Path(p).parts for p in paths):
            raise ValueError('separate exact requester TLS paths required')
        return self


@dataclass(frozen=True)
class _PeerSettings:
    intake: OriginalIntakeSettingsV1
    profile: RequesterPeerProfileV1
    path: str
    sha256: str

    def current(self):
        raw = _pinned(self.path, self.sha256)
        value = type(self.profile).model_validate_json(raw)
        if canonical_bytes(value.model_dump(mode='json')) != raw or value != self.profile:
            raise PermissionError('requester peer profile changed')
        c = self.intake.config
        p = self.profile
        bound = self.intake.current()
        if ((p.intake_config_sha256, p.intake_appointment_sha256) !=
                (self.intake.config_sha256, self.intake.appointment_sha256)
                or any(getattr(p, key) != getattr(c, key) for key in (
                    'principal_id', 'workspace_id', 'runtime_hash', 'registry_hash', 'original_horizon'))
                or (p.issuer_actor, p.reviewer_actor) !=
                (self.intake.expected_issuer_actor, self.intake.expected_reviewer_actor)):
            raise PermissionError('existing requester appointment differs')
        now = datetime.now(timezone.utc)
        if not p.valid_from <= now < p.expires_at <= bound:
            raise PermissionError('requester peer profile expired or excessive')
        cert = _pinned(p.server_certificate_file, p.server_certificate_sha256, 131072)
        _pinned(p.server_key_file, p.server_key_sha256, 131072)
        _pinned(p.client_ca_file, p.client_ca_sha256, 131072)
        leaf = x509.load_pem_x509_certificate(cert)
        names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        if p.server_hostname not in names or not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
            raise PermissionError('requester server certificate differs or expired')
        return min(bound, p.expires_at)


def load_requester_peer_settings_v1(intake, peer_profile_path, expected_peer_profile_sha256):
    """Consume the same exact externally selected peer profile; issues no scope."""
    return _load_peer_settings_v1(intake, peer_profile_path, expected_peer_profile_sha256, RequesterPeerProfileV1)


def _load_peer_settings_v1(intake, peer_profile_path, expected_peer_profile_sha256, profile_type):
    """Internal exact server-selected profile type; never selected by a request."""
    if type(intake) is not OriginalIntakeSettingsV1:
        raise TypeError('existing exact intake settings required')
    raw = _pinned(peer_profile_path, expected_peer_profile_sha256)
    profile = profile_type.model_validate_json(raw)
    settings = _PeerSettings(intake, profile, str(peer_profile_path), expected_peer_profile_sha256)
    settings.current()
    return settings


def protected_replacement_request_server_v1(intake, peer_profile_path, expected_peer_profile_sha256):
    """Only startup selects the fixed peer, TLS material and existing factory."""
    settings = load_requester_peer_settings_v1(intake, peer_profile_path, expected_peer_profile_sha256)
    profile = settings.profile
    factory = ReplacementRequesterFactoryV1(intake)
    from ._protected_control_listener_v1 import _protected_control_listener_v1
    def encode_response(value):
        if type(value) is not RequesterControlMetadataV1:raise PermissionError('fixed requester control metadata required')
        encoded=canonical_bytes(value.model_dump(mode='json'))
        checked=RequesterControlMetadataV1.model_validate_json(encoded)
        if checked.resultAvailable is not False or checked.remoteStopProven is not False or len(encoded)>4096:raise PermissionError('control metadata cannot grant result or remote stop')
        return encoded
    return _protected_control_listener_v1(settings,factory,path=PATH,parse_request=parse_requester_request_v1,encode_response=encode_response)
