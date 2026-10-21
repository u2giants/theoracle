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
    tls = server_tls(certfile=profile.server_certificate_file, keyfile=profile.server_key_file,
                     cafile=profile.client_ca_file)
    # Loading TLS bytes cannot silently select changed inputs.
    settings.current()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            self.original_start = datetime.now(timezone.utc)
            self.original_monotonic_start = time.monotonic()
            super().setup()

        def log_message(self, *args):
            pass

        def _deny(self, status=503):
            self.close_connection = True
            try:
                self.connection.settimeout(1)
                self.send_response(status)
                self.send_header('Content-Length', '0')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
            except Exception:
                pass

        def send_error(self, code, message=None, explain=None):
            self._deny()

        def do_GET(self):
            self._deny(404)

        def do_POST(self):
            started = False
            self.close_connection = True
            try:
                if self.server.closing or self.headers.get_all('Content-Encoding', []) != []:
                    raise PermissionError('fixed requester lifecycle/framing required')
                length = fixed_request_length_v1(self, path=PATH, content_type='application/json', maximum_bytes=65536)
                # Prove actual externally pinned peer BEFORE body read or SQL.
                peer_der_v1(self.connection, expected_uri=profile.client_uri,
                            expected_der_sha256=profile.client_certificate_sha256)
                bound = settings.current()
                original_end = min(self.original_monotonic_start + 30,
                    time.monotonic() + max(0, (bound - datetime.now(timezone.utc)).total_seconds()))
                raw_request = read_request_body_v1(self, length, absolute_monotonic_deadline=original_end)
                request = parse_requester_request_v1(raw_request)
                if not datetime.now(timezone.utc) < request.caller_deadline <= min(
                        self.original_start + timedelta(seconds=30), bound):
                    raise PermissionError('original requester window expired or excessive')
                original_end = min(original_end, self.original_monotonic_start +
                    (request.caller_deadline - self.original_start).total_seconds())
                if self.server.closing or time.monotonic() >= original_end:
                    raise PermissionError('original requester deadline elapsed')
                settings.current()
                value = factory.execute_v1(raw_request)
                # Factory checked actual SQL context, commit and close; metadata
                # is still withheld on any peer/profile/deadline/lifecycle drift.
                peer_der_v1(self.connection, expected_uri=profile.client_uri,
                            expected_der_sha256=profile.client_certificate_sha256)
                settings.current()
                if self.server.closing or time.monotonic() >= original_end:
                    raise PermissionError('original requester reply expired')
                if type(value) is not RequesterControlMetadataV1:
                    raise PermissionError('fixed requester control metadata required')
                encoded = canonical_bytes(value.model_dump(mode='json'))
                checked = RequesterControlMetadataV1.model_validate_json(encoded)
                if checked.resultAvailable is not False or checked.remoteStopProven is not False or len(encoded) > 4096:
                    raise PermissionError('control metadata cannot grant result or remote stop')
                self.connection.settimeout(max(.001, min(5, original_end - time.monotonic())))
                self.close_connection = True
                started = True
                self.send_response(200)
                self.send_header('Connection', 'close')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(encoded)
            except Exception:
                if not started:
                    self._deny()

    class RequesterServer(MutualTLSServer):
        daemon_threads = False
        block_on_close = False

        def __init__(self):
            self.closing = False
            self._active = set()
            self._active_condition = threading.Condition()
            super().__init__((profile.listen_host, profile.listen_port), Handler, tls=tls)

        def process_request(self, request, address):
            # Same fixed 32-connection admission as MutualTLSServer, tracked
            # atomically before the standard request-thread launcher is called.
            with self._active_condition:
                if self.closing or not self._connections.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                self._active.add(request)
            try:
                ThreadingHTTPServer.process_request(self, request, address)
            except BaseException:
                self._connections.release()
                with self._active_condition:
                    self._active.discard(request)
                    self._active_condition.notify_all()
                raise

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                with self._active_condition:
                    self._active.discard(request)
                    self._active_condition.notify_all()

        def server_close(self):
            with self._active_condition:
                self.closing = True
            super().server_close()
            # Fixed SQL statements and sockets are bounded. Never discard an
            # actual unfinished worker or call an uncertain shutdown successful.
            end = time.monotonic() + 40
            with self._active_condition:
                while self._active and time.monotonic() < end:
                    self._active_condition.wait(max(0, end - time.monotonic()))
                if self._active:
                    raise PermissionError('owned requester handlers remain active')

    server = RequesterServer()
    try:
        settings.current()
        return server
    except BaseException:
        server.server_close()
        raise
