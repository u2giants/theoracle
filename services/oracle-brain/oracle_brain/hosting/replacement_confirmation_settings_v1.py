"""Separate externally appointed exact-map confirmation consumer; no issuer."""
from dataclasses import dataclass
from datetime import datetime, timezone
import ipaddress
from typing import Literal
from uuid import UUID

from cryptography import x509
from pydantic import AwareDatetime, Field, model_validator
from oracle_brain.operating_model.contracts import StrictRecord
from .original_intake_v1 import OriginalIntakeSettingsV1, ProtectedInputV1, _pinned, _parse

HASH = r'^[a-f0-9]{64}$'


class ConfirmationAppointmentV1(StrictRecord):
    purpose: Literal['replacement-exact-map-confirm-v1']
    operation: Literal['exact-map-confirm']
    intake_config_sha256: str = Field(pattern=HASH)
    intake_appointment_sha256: str = Field(pattern=HASH)
    peer_profile_sha256: str = Field(pattern=HASH)
    principal_id: UUID
    workspace_id: UUID
    expected_session_role: str = Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    runtime_hash: str = Field(pattern=HASH)
    registry_hash: str = Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def closed(self):
        if (len({self.principal_id, self.issuer_actor, self.reviewer_actor}) != 3
                or not self.valid_from < self.expires_at <= self.original_horizon):
            raise ValueError('independent finite confirmation appointment required')
        return self


class ConfirmationPeerProfileV1(StrictRecord):
    purpose: Literal['replacement-confirmation-peer-v1']
    intake_config_sha256: str = Field(pattern=HASH)
    intake_appointment_sha256: str = Field(pattern=HASH)
    principal_id: UUID
    workspace_id: UUID
    client_uri: str = Field(pattern=r'^spiffe://oracle/[a-zA-Z0-9/_-]+$')
    client_certificate_sha256: str = Field(pattern=HASH)
    listen_host: str
    listen_port: int = Field(strict=True, ge=0, le=65535)
    server_hostname: str = Field(pattern=r'^[a-zA-Z0-9.-]{1,253}$')
    server_certificate: ProtectedInputV1
    server_key: ProtectedInputV1
    client_ca: ProtectedInputV1
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def closed(self):
        ipaddress.ip_address(self.listen_host)
        if (not self.valid_from < self.expires_at <= self.original_horizon
                or len({self.server_certificate.path, self.server_key.path, self.client_ca.path}) != 3):
            raise ValueError('fixed finite confirmation peer required')
        return self


@dataclass(frozen=True)
class ConfirmationSettingsV1:
    intake: OriginalIntakeSettingsV1
    appointment: ConfirmationAppointmentV1
    peer: ConfirmationPeerProfileV1
    appointment_input: ProtectedInputV1
    peer_input: ProtectedInputV1
    issuer_actor: UUID
    reviewer_actor: UUID

    def current(self):
        s = self.intake
        horizon = s.current()
        a = _parse(ConfirmationAppointmentV1, _pinned(self.appointment_input.path, self.appointment_input.sha256))
        p = _parse(ConfirmationPeerProfileV1, _pinned(self.peer_input.path, self.peer_input.sha256))
        c = s.config
        if (a != self.appointment or p != self.peer or a.peer_profile_sha256 != self.peer_input.sha256
                or (a.issuer_actor, a.reviewer_actor) != (self.issuer_actor, self.reviewer_actor)
                or (self.issuer_actor, self.reviewer_actor) != (s.expected_issuer_actor, s.expected_reviewer_actor)):
            raise PermissionError('independently pinned confirmation appointment changed')
        for record in (a, p):
            if ((record.intake_config_sha256, record.intake_appointment_sha256) !=
                    (s.config_sha256, s.appointment_sha256)
                    or (record.principal_id, record.workspace_id, record.original_horizon) !=
                    (c.principal_id, c.workspace_id, c.original_horizon)):
                raise PermissionError('exact existing confirmation requester differs')
        if any(getattr(a, key) != getattr(c, key) for key in ('expected_session_role', 'runtime_hash', 'registry_hash')):
            raise PermissionError('confirmation requester context differs')
        if p.expires_at > a.expires_at:
            raise PermissionError('confirmation peer exceeds appointment')
        leaf = x509.load_pem_x509_certificate(_pinned(p.server_certificate.path, p.server_certificate.sha256, 131072))
        _pinned(p.server_key.path, p.server_key.sha256, 131072)
        _pinned(p.client_ca.path, p.client_ca.sha256, 131072)
        _pinned(c.database_url.path, c.database_url.sha256, 16384)
        _pinned(c.database_ca.path, c.database_ca.sha256, 131072)
        names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        bound = min(horizon, a.expires_at, p.expires_at, a.original_horizon)
        now = datetime.now(timezone.utc)
        if (not max(a.valid_from, p.valid_from, leaf.not_valid_before_utc) <= now < min(bound, leaf.not_valid_after_utc)
                or p.server_hostname not in names):
            raise PermissionError('confirmation appointment or TLS identity expired')
        return min(bound, leaf.not_valid_after_utc)


def load_confirmation_settings_v1(intake, appointment_path, appointment_sha256, peer_path, peer_sha256,
                                   *, issuer_actor, reviewer_actor):
    if type(intake) is not OriginalIntakeSettingsV1:
        raise TypeError('actual existing requester intake identity required')
    if type(issuer_actor) is not UUID or type(reviewer_actor) is not UUID or issuer_actor == reviewer_actor:
        raise PermissionError('external independent confirmation issuer pins required')
    ai = ProtectedInputV1(path=str(appointment_path), sha256=appointment_sha256)
    pi = ProtectedInputV1(path=str(peer_path), sha256=peer_sha256)
    settings = ConfirmationSettingsV1(intake,
        _parse(ConfirmationAppointmentV1, _pinned(ai.path, ai.sha256)),
        _parse(ConfirmationPeerProfileV1, _pinned(pi.path, pi.sha256)), ai, pi, issuer_actor, reviewer_actor)
    settings.current()
    return settings
