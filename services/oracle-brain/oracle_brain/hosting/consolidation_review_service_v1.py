"""Uninstalled fixed mTLS model-review listener; no browser identity issuance.

Current authorization is checked before delivery. Changes after the final SQL
check and partial client delivery cannot be undone or represented as proven.
"""
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import socket
import threading
import time

from cryptography import x509
from .consolidation_review_settings_v1 import ModelReviewSettingsV1
from .consolidation_review_v1 import ModelReviewFactoryV1,MAX_RESPONSE,parse_review_request
from .gateway import MutualTLSServer, server_tls
from .replacement_transport_v1 import fixed_request_length_v1, read_request_body_v1, peer_der_v1

PATH = '/v1/replacement/model-review'


def protected_model_review_server_v1(settings):
    if type(settings) is not ModelReviewSettingsV1:
        raise TypeError('fixed independently appointed viewer settings required')
    settings.current()
    profile = settings.peer
    factory = ModelReviewFactoryV1(settings)
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
                raise PermissionError('viewer client certificate expired')
            return leaf.not_valid_after_utc

        def do_POST(self):
            acquired = False
            started = False
            self.close_connection = True
            try:
                if self.server.closing or any(self.headers.get_all(k, []) for k in (
                        'Content-Encoding', 'Range', 'If-Range', 'If-Match', 'If-None-Match',
                        'If-Modified-Since', 'If-Unmodified-Since', 'Expect')):
                    raise PermissionError('fixed full original transport required')
                length = fixed_request_length_v1(self, path=PATH, content_type='application/json', maximum_bytes=65536)
                horizon = min(self._current_peer(), settings.current())
                if not slot.acquire(blocking=False):
                    raise PermissionError('model review already active')
                acquired = True
                transport_end = min(self.original_start + timedelta(seconds=30), horizon)
                raw = read_request_body_v1(self, length,
                    absolute_monotonic_deadline=self.original_monotonic_start + max(0, (transport_end-self.original_start).total_seconds()))
                request = parse_review_request(raw)
                if not datetime.now(timezone.utc) < request.caller_deadline <= transport_end:
                    raise PermissionError('original absolute viewer deadline required')
                monotonic_end = self.original_monotonic_start + (request.caller_deadline-self.original_start).total_seconds()
                data,valid_until = factory.execute_v1(raw)
                end = min(request.caller_deadline, valid_until, self._current_peer(), settings.current())
                monotonic_end = min(monotonic_end, self.original_monotonic_start + (end-self.original_start).total_seconds())
                if datetime.now(timezone.utc) >= end or time.monotonic() >= monotonic_end:
                    raise PermissionError('original delivery window elapsed')
                self.connection.settimeout(max(.001, min((end-datetime.now(timezone.utc)).total_seconds(), monotonic_end-time.monotonic())))
                started = True
                self.send_response(200)
                self.send_header('X-Oracle-Review-Valid-Until', end.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
                self.send_header('Connection', 'close')
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store, private')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                for offset in range(0, len(data), 65536):
                    bound = min(end, self._current_peer(), settings.current())
                    remaining = min((bound-datetime.now(timezone.utc)).total_seconds(), monotonic_end-time.monotonic())
                    if remaining <= 0:
                        raise PermissionError('original delivery window elapsed')
                    self.connection.settimeout(remaining)
                    self.wfile.write(data[offset:offset+65536])
                # Socket delivery is never an acknowledgment of browser receipt.
            except Exception:
                if not started:
                    self._deny()
                else:
                    self.close_connection = True
            finally:
                if acquired:
                    slot.release()

    class ViewerServer(MutualTLSServer):
        address_family=socket.AF_INET6 if profile.listen_host=='::1' else socket.AF_INET
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
                    raise PermissionError('owned model review handlers remain active; delivery unproved')

    server = ViewerServer()
    try:
        settings.current()
        return server
    except BaseException:
        server.server_close()
        raise
