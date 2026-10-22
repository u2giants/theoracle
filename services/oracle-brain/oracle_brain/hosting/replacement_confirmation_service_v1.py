"""Uninstalled fixed mTLS exact-map confirmation; seven control fields only.

No business policy, confirmed model, eligible badge or delivery grant is issued.
A lost/late acknowledgment never causes an automatic write retry.
"""
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import time

from cryptography import x509
from oracle_brain.operating_model.contracts import canonical_bytes
from .replacement_confirmation_settings_v1 import ConfirmationSettingsV1
from .replacement_confirmation_v1 import (ReplacementConfirmationFactoryV1, ConfirmationObservationV1,
    ConfirmationConflictV1, parse_confirmation_request_v1)
from .gateway import MutualTLSServer, server_tls
from .replacement_transport_v1 import fixed_request_length_v1, read_request_body_v1, peer_der_v1

PATH = '/v1/replacement/confirm'


def protected_replacement_confirmation_server_v1(settings):
    if type(settings) is not ConfirmationSettingsV1:
        raise TypeError('fixed independently appointed confirmation settings required')
    settings.current()
    profile = settings.peer
    factory = ReplacementConfirmationFactoryV1(settings)
    tls = server_tls(certfile=profile.server_certificate.path, keyfile=profile.server_key.path,
                     cafile=profile.client_ca.path)
    settings.current()
    slot = threading.Lock()

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

        def _current_peer(self):
            der = peer_der_v1(self.connection, expected_uri=profile.client_uri,
                              expected_der_sha256=profile.client_certificate_sha256)
            leaf = x509.load_der_x509_certificate(der)
            now = datetime.now(timezone.utc)
            if not leaf.not_valid_before_utc <= now < leaf.not_valid_after_utc:
                raise PermissionError('confirmation client certificate expired')
            return leaf.not_valid_after_utc

        def do_POST(self):
            acquired = False
            started = False
            self.close_connection = True
            try:
                if self.server.closing or any(self.headers.get_all(k, []) for k in (
                        'Content-Encoding', 'Range', 'If-Range', 'If-Match', 'If-None-Match',
                        'If-Modified-Since', 'If-Unmodified-Since', 'Expect')):
                    raise PermissionError('fixed confirmation transport required')
                length = fixed_request_length_v1(self, path=PATH, content_type='application/json', maximum_bytes=8192)
                horizon = min(self._current_peer(), settings.current())
                if not slot.acquire(blocking=False):
                    raise PermissionError('confirmation already active')
                acquired = True
                transport_end = min(self.original_start + timedelta(seconds=30), horizon)
                raw = read_request_body_v1(self, length,
                    absolute_monotonic_deadline=self.original_monotonic_start + max(0, (transport_end-self.original_start).total_seconds()))
                request = parse_confirmation_request_v1(raw)
                if not datetime.now(timezone.utc) < request.caller_deadline <= transport_end:
                    raise PermissionError('original absolute confirmation deadline required')
                monotonic_end = self.original_monotonic_start + (request.caller_deadline-self.original_start).total_seconds()
                result = factory.execute_v1(raw, original_start=self.original_start)
                if type(result) is not ConfirmationObservationV1:
                    raise PermissionError('actual confirmed control observation required')
                payload = canonical_bytes(result.metadata.model_dump(mode='json'))
                if len(payload)>4096:
                    raise PermissionError('bounded control metadata required')
                end = min(request.caller_deadline, result.valid_until, self._current_peer(), settings.current())
                monotonic_end = min(monotonic_end, self.original_monotonic_start + (end-self.original_start).total_seconds())
                if datetime.now(timezone.utc) >= end or time.monotonic() >= monotonic_end:
                    raise PermissionError('original delivery window elapsed')
                self.connection.settimeout(max(.001, min((end-datetime.now(timezone.utc)).total_seconds(), monotonic_end-time.monotonic())))
                started = True
                self.send_response(200)
                self.send_header('Connection', 'close')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store, private')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                for offset in range(0, len(payload), 65536):
                    bound = min(end, self._current_peer(), settings.current())
                    remaining = min((bound-datetime.now(timezone.utc)).total_seconds(), monotonic_end-time.monotonic())
                    if remaining <= 0:
                        raise PermissionError('original delivery window elapsed')
                    self.connection.settimeout(remaining)
                    self.wfile.write(payload[offset:offset+65536])
                # Socket delivery is never an acknowledgment of browser receipt.
            except ConfirmationConflictV1:
                if not started:
                    self._deny(409)
            except Exception:
                if not started:
                    self._deny()
                else:
                    self.close_connection = True
            finally:
                if acquired:
                    slot.release()

    class ConfirmationServer(MutualTLSServer):
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
            end = time.monotonic() + 40
            with self._active_condition:
                while self._active and time.monotonic() < end:
                    self._active_condition.wait(max(0, end-time.monotonic()))
                if self._active:
                    raise PermissionError('owned confirmation handlers remain active; delivery unproved')

    server = ConfirmationServer()
    try:
        settings.current()
        return server
    except BaseException:
        server.server_close()
        raise
