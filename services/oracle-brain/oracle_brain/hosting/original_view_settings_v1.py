"""Externally pinned, separate original-viewer consumers. Never issues authority."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import ipaddress
import os
import stat
from typing import Literal
from uuid import UUID

from cryptography import x509
from pydantic import AwareDatetime, Field, model_validator
from oracle_brain.operating_model.contracts import StrictRecord
from .original_intake_v1 import ProtectedInputV1, _pinned, _parse

HASH = r'^[a-f0-9]{64}$'
ROLE = r'^[a-z][a-z0-9_]{0,62}$'
MAX_BYTES = 25 * 1024 * 1024


class ViewerSourceV1(StrictRecord):
    source_id: UUID
    revision: int = Field(strict=True, ge=1, le=9007199254740991)
    original_sha256: str = Field(pattern=HASH)
    byte_count: int = Field(strict=True, ge=1, le=MAX_BYTES)
    media_type: Literal['application/pdf']
    reservation_id: UUID
    custody_seal_sha256: str = Field(pattern=HASH)


class OriginalViewerConfigV1(StrictRecord):
    schema_version: Literal[1]
    purpose: Literal['original-revision-view-v1']
    principal_id: UUID
    workspace_id: UUID
    expected_session_role: str = Field(pattern=ROLE)
    expected_owner_role: str = Field(pattern=ROLE)
    runtime_hash: str = Field(pattern=HASH)
    registry_hash: str = Field(pattern=HASH)
    database_url: ProtectedInputV1
    database_ca: ProtectedInputV1
    storage_root: str
    storage_device: int = Field(strict=True, ge=0)
    storage_inode: int = Field(strict=True, gt=0)
    storage_uid: int = Field(strict=True, ge=0)
    storage_profile_hash: str = Field(pattern=HASH)
    sources: tuple[ViewerSourceV1, ...] = Field(min_length=1, max_length=64)
    original_horizon: AwareDatetime
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def closed(self):
        if (self.expected_session_role == self.expected_owner_role
                or len({(r.source_id, r.revision) for r in self.sources}) != len(self.sources)
                or not self.expires_at <= self.original_horizon):
            raise ValueError('separate finite viewer identity and source pins required')
        return self


class OriginalViewerAppointmentV1(StrictRecord):
    schema_version: Literal[1]
    purpose: Literal['original-revision-view-v1']
    config_sha256: str = Field(pattern=HASH)
    peer_profile_sha256: str = Field(pattern=HASH)
    principal_id: UUID
    workspace_id: UUID
    expected_session_role: str = Field(pattern=ROLE)
    runtime_hash: str = Field(pattern=HASH)
    registry_hash: str = Field(pattern=HASH)
    issuer_actor: UUID
    reviewer_actor: UUID
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def independent(self):
        if (len({self.principal_id, self.issuer_actor, self.reviewer_actor}) != 3
                or not self.valid_from < self.expires_at <= self.original_horizon):
            raise ValueError('independent finite viewer appointment required')
        return self


class OriginalViewerPeerProfileV1(StrictRecord):
    schema_version: Literal[1]
    purpose: Literal['original-revision-view-peer-v1']
    config_sha256: str = Field(pattern=HASH)
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
            raise ValueError('finite separate viewer TLS files required')
        return self


@dataclass(frozen=True)
class OriginalViewerSettingsV1:
    config: OriginalViewerConfigV1
    appointment: OriginalViewerAppointmentV1
    peer: OriginalViewerPeerProfileV1
    config_input: ProtectedInputV1
    appointment_input: ProtectedInputV1
    peer_input: ProtectedInputV1
    issuer_actor: UUID
    reviewer_actor: UUID

    def current(self):
        c = _parse(OriginalViewerConfigV1, _pinned(self.config_input.path, self.config_input.sha256))
        a = _parse(OriginalViewerAppointmentV1, _pinned(self.appointment_input.path, self.appointment_input.sha256))
        p = _parse(OriginalViewerPeerProfileV1, _pinned(self.peer_input.path, self.peer_input.sha256))
        if (c != self.config or a != self.appointment or p != self.peer
                or a.config_sha256 != self.config_input.sha256 or p.config_sha256 != self.config_input.sha256
                or a.peer_profile_sha256 != self.peer_input.sha256
                or (a.issuer_actor, a.reviewer_actor) != (self.issuer_actor, self.reviewer_actor)):
            raise PermissionError('viewer startup pins differ')
        for key in ('principal_id', 'workspace_id', 'expected_session_role', 'runtime_hash', 'registry_hash', 'original_horizon'):
            if getattr(c, key) != getattr(a, key):
                raise PermissionError('viewer appointment identity differs')
        if ((p.principal_id, p.workspace_id, p.original_horizon) != (c.principal_id, c.workspace_id, c.original_horizon)
                or p.expires_at > a.expires_at):
            raise PermissionError('viewer peer appointment differs')
        now = datetime.now(timezone.utc)
        horizon = min(c.expires_at, a.expires_at, p.expires_at, c.original_horizon)
        if not max(a.valid_from, p.valid_from) <= now < horizon:
            raise PermissionError('viewer appointment expired')
        root = Path(c.storage_root)
        if not root.is_absolute() or root.resolve() != root:
            raise PermissionError('canonical preexisting viewer root required')
        info = root.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid()
                or (info.st_dev, info.st_ino, info.st_uid) != (c.storage_device, c.storage_inode, c.storage_uid)):
            raise PermissionError('viewer root identity differs')
        cert = _pinned(p.server_certificate.path, p.server_certificate.sha256, 131072)
        _pinned(p.server_key.path, p.server_key.sha256, 131072)
        _pinned(p.client_ca.path, p.client_ca.sha256, 131072)
        _pinned(c.database_url.path, c.database_url.sha256, 16384)
        _pinned(c.database_ca.path, c.database_ca.sha256, 131072)
        leaf = x509.load_pem_x509_certificate(cert)
        names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName)
        now = datetime.now(timezone.utc)
        if now >= horizon or p.server_hostname not in names or not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
            raise PermissionError('viewer TLS identity expired or different')
        return horizon


def load_original_viewer_settings_v1(config_path, config_sha256, appointment_path, appointment_sha256,
                                     peer_path, peer_sha256, *, issuer_actor, reviewer_actor):
    if type(issuer_actor) is not UUID or type(reviewer_actor) is not UUID or issuer_actor == reviewer_actor:
        raise PermissionError('external distinct viewer issuer pins required')
    ci = ProtectedInputV1(path=str(config_path), sha256=config_sha256)
    ai = ProtectedInputV1(path=str(appointment_path), sha256=appointment_sha256)
    pi = ProtectedInputV1(path=str(peer_path), sha256=peer_sha256)
    s = OriginalViewerSettingsV1(_parse(OriginalViewerConfigV1, _pinned(ci.path, ci.sha256)),
        _parse(OriginalViewerAppointmentV1, _pinned(ai.path, ai.sha256)),
        _parse(OriginalViewerPeerProfileV1, _pinned(pi.path, pi.sha256)), ci, ai, pi, issuer_actor, reviewer_actor)
    s.current()
    return s
