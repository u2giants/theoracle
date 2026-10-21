"""Uninstalled upload-only mTLS custody listener. Never reads/qualifies a PDF.

A PDF signature/media frame is not readability or encryption validation. Only
existing externally appointed intake capability is consumed. No automatic retry,
job, grant, viewer, provider, model or result operation exists here.
"""
import base64
import hashlib
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
import time
from typing import Literal

from pydantic import AwareDatetime, field_validator

from oracle_brain.operating_model.contracts import canonical_bytes
from .gateway import MutualTLSServer, server_tls
from .original_intake_v1 import (
    OriginalIntakeFactoryV1, OriginalIntakeRequestV1, OriginalIntakeSnapshotV1, _pinned,
)
from .replacement_request_service_v1 import load_requester_peer_settings_v1
from .replacement_transport_v1 import fixed_request_length_v1, read_request_body_v1, peer_der_v1

PATH = '/v1/replacement/upload'
METADATA_HEADER = 'X-Oracle-Upload-Metadata'
MAX_BYTES = 25 * 1024 * 1024


class OriginalUploadMetadataV1(OriginalIntakeRequestV1):
    schema_version: Literal[1]
    caller_deadline: AwareDatetime

    @field_validator('schema_version', mode='before')
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError('exact upload metadata version required')
        return value


def parse_upload_metadata_v1(value: str) -> OriginalUploadMetadataV1:
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,8192}', value):
        raise PermissionError('bounded canonical upload metadata required')
    try:
        raw = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
        if not 0 < len(raw) <= 4096 or base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=') != value:
            raise ValueError('canonical upload encoding required')
        def unique(pairs):
            result = {}
            for key, item in pairs:
                if key in result:
                    raise ValueError('duplicate upload metadata field')
                result[key] = item
            return result
        decoded = json.loads(raw, object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('finite upload metadata required')))
        if type(decoded) is not dict or canonical_bytes(decoded) != raw:
            raise ValueError('canonical upload metadata object required')
        return OriginalUploadMetadataV1.model_validate_json(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise PermissionError('invalid fixed upload metadata') from None


def protected_replacement_upload_server_v1(intake, peer_profile_path, expected_peer_profile_sha256):
    settings = load_requester_peer_settings_v1(intake, peer_profile_path, expected_peer_profile_sha256)
    profile = settings.profile
    factory = OriginalIntakeFactoryV1(intake)
    slot = threading.BoundedSemaphore(1)

    def current():
        bound = settings.current()
        for pin, limit in ((intake.config.database_url, 16384), (intake.config.database_ca, 131072)):
            _pinned(pin.path, pin.sha256, limit)
        return bound

    current()
    tls = server_tls(certfile=profile.server_certificate_file, keyfile=profile.server_key_file,
                     cafile=profile.client_ca_file)
    current()

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
            acquired = False
            started = False
            try:
                if self.server.closing or self.headers.get_all('Content-Encoding', []) != []:
                    raise PermissionError('fixed upload framing required')
                length = fixed_request_length_v1(self, path=PATH, content_type='application/pdf', maximum_bytes=MAX_BYTES)
                peer_der_v1(self.connection, expected_uri=profile.client_uri,
                            expected_der_sha256=profile.client_certificate_sha256)
                bound = current()
                values = self.headers.get_all(METADATA_HEADER, [])
                if len(values) != 1:
                    raise PermissionError('one exact upload metadata header required')
                metadata = parse_upload_metadata_v1(values[0])
                original_deadline = metadata.caller_deadline
                if (metadata.byte_count != length or not datetime.now(timezone.utc) < original_deadline <=
                        min(bound, self.original_start + timedelta(seconds=30))):
                    raise PermissionError('fixed original upload bound required')
                if not slot.acquire(blocking=False):
                    raise PermissionError('upload already active; no queued body accepted')
                acquired = True
                original_end = min(self.original_monotonic_start + 30,
                    self.original_monotonic_start + (original_deadline - self.original_start).total_seconds())
                raw = read_request_body_v1(self, length, absolute_monotonic_deadline=original_end)
                # Framing only; parsing/visual reading is a separately granted
                # capability. Neither signature nor custody proves PDF quality.
                if not raw.startswith(b'%PDF-') or hashlib.sha256(raw).hexdigest() != metadata.original_sha256:
                    raise PermissionError('observed original upload bytes differ')
                current()
                if self.server.closing or time.monotonic() >= original_end:
                    raise PermissionError('original upload expired before intake')
                snapshot = factory.intake_pdf_v1(source_id=metadata.source_id, expected_head=metadata.expected_head,
                    idempotency_key=metadata.idempotency_key, filename=metadata.filename,
                    original_sha256=metadata.original_sha256, data=raw, caller_deadline=original_deadline)
                peer_der_v1(self.connection, expected_uri=profile.client_uri,
                            expected_der_sha256=profile.client_certificate_sha256)
                current()
                if self.server.closing or time.monotonic() >= original_end:
                    raise PermissionError('original upload response expired')
                if type(snapshot) is not OriginalIntakeSnapshotV1:
                    raise PermissionError('fixed original custody snapshot required')
                encoded = canonical_bytes(snapshot.model_dump(mode='json'))
                OriginalIntakeSnapshotV1.model_validate_json(encoded)
                if len(encoded) > 4096:
                    raise PermissionError('bounded public original custody required')
                self.connection.settimeout(max(.001, min(5, original_end - time.monotonic())))
                self.close_connection = True
                started = True
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(encoded)
            except Exception:
                if not started:
                    self._deny()
                else:
                    self.close_connection = True
            finally:
                if acquired:
                    slot.release()

    class UploadServer(MutualTLSServer):
        daemon_threads = False
        block_on_close = False

        def __init__(self):
            self.closing = False
            self._active = set()
            self._active_condition = threading.Condition()
            super().__init__((profile.listen_host, profile.listen_port), Handler, tls=tls)

        def process_request(self, request, address):
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
            # A blocked synchronous filesystem operation is not killed/dropped.
            # Retain actual ownership and refuse to claim cleanup if it remains.
            end = time.monotonic() + 40
            with self._active_condition:
                while self._active and time.monotonic() < end:
                    self._active_condition.wait(max(0, end - time.monotonic()))
                if self._active:
                    raise PermissionError('owned upload handlers remain active')

    server = UploadServer()
    try:
        current()
        return server
    except BaseException:
        server.server_close()
        raise
