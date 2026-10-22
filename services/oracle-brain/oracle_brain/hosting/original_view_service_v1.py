"""Uninstalled fixed mTLS original-PDF listener; no browser identity issuance.

Current authorization is checked before delivery. Changes after the final SQL
check and partial client delivery cannot be undone or represented as proven.
"""
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
import socket
import time
from uuid import UUID

from cryptography import x509
from pydantic import AwareDatetime, Field
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.operating_model.request_deadline_v1 import _request_fence_v1, request_remaining_v1
from .original_intake_v1 import _parse
from .original_view_settings_v1 import OriginalViewerSettingsV1
from .original_view_v1 import OriginalViewerFactoryV1, ViewedOriginalV1
from .gateway import MutualTLSServer, server_tls
from .replacement_transport_v1 import fixed_request_length_v1, read_request_body_v1, peer_der_v1

PATH = '/v1/replacement/original'


class OriginalViewRequestV1(StrictRecord):
    source_id: UUID
    revision: int = Field(strict=True, ge=1, le=9007199254740991)
    caller_deadline: AwareDatetime


def protected_original_view_server_v1(settings):
    if type(settings) is not OriginalViewerSettingsV1:
        raise TypeError('fixed independently appointed viewer settings required')
    settings.current()
    profile = settings.peer
    factory = OriginalViewerFactoryV1(settings)
    tls = server_tls(certfile=profile.server_certificate.path, keyfile=profile.server_key.path,
                     cafile=profile.client_ca.path)
    # Immutable startup horizon can only narrow the original30s transport.
    installed_end = settings.current()
    slot = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            # Captured by this server before the request thread/TLS handshake.
            # Never start a replacement clock after handshake or body reading.
            self.original_start = self.request._oracle_view_original_wall_v1
            self.original_monotonic_start = self.request._oracle_view_original_mono_v1
            request_remaining_v1()
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
                length = fixed_request_length_v1(self, path=PATH, content_type='application/json', maximum_bytes=4096)
                horizon = min(self._current_peer(), settings.current())
                if not slot.acquire(blocking=False):
                    raise PermissionError('original read already active')
                acquired = True
                transport_end = min(self.original_start + timedelta(seconds=30), horizon)
                raw = read_request_body_v1(self, length,
                    absolute_monotonic_deadline=self.original_monotonic_start + max(0, (transport_end-self.original_start).total_seconds()))
                request = _parse(OriginalViewRequestV1, raw)
                if not datetime.now(timezone.utc) < request.caller_deadline <= transport_end:
                    raise PermissionError('original absolute viewer deadline required')
                monotonic_end = self.original_monotonic_start + (request.caller_deadline-self.original_start).total_seconds()
                # The caller value can only narrow the pre-handshake fence.
                with _request_fence_v1(float(monotonic_end)):
                    request_remaining_v1()
                    pins = [r for r in settings.config.sources if (r.source_id,r.revision)==(request.source_id,request.revision)]
                    if len(pins)!=1:raise PermissionError('exact installed original media required')
                    pin=pins[0]
                    read = factory.read_pdf_v1 if pin.media_type=='application/pdf' else factory.read_original_v1
                    result = read(request.source_id, request.revision, caller_deadline=request.caller_deadline)
                    if type(result) is not ViewedOriginalV1 or type(result.data) is not bytes or result.media_type!=pin.media_type:
                        raise PermissionError('actual original bytes required')
                    end = min(request.caller_deadline, result.valid_until, self._current_peer(), settings.current())
                    monotonic_end = min(monotonic_end, self.original_monotonic_start + (end-self.original_start).total_seconds())
                    if datetime.now(timezone.utc) >= end or time.monotonic() >= monotonic_end:
                        raise PermissionError('original delivery window elapsed')
                    self.connection.settimeout(max(.001, min((end-datetime.now(timezone.utc)).total_seconds(), monotonic_end-time.monotonic())))
                    started = True
                    self.send_response(200)
                    self.send_header('X-Oracle-Original-Valid-Until', end.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'))
                    self.send_header('Connection', 'close')
                    self.send_header('Content-Type', 'application/pdf' if pin.media_type=='application/pdf' else 'text/plain; charset=utf-8')
                    self.send_header('Content-Length', str(len(result.data)))
                    self.send_header('Content-Disposition', 'inline; filename="original.pdf"' if pin.media_type=='application/pdf' else 'inline; filename="original.txt"')
                    self.send_header('Cache-Control', 'no-store, private')
                    self.send_header('X-Content-Type-Options', 'nosniff')
                    self.end_headers()
                    for offset in range(0, len(result.data), 65536):
                        bound = min(end, self._current_peer(), settings.current())
                        remaining = min((bound-datetime.now(timezone.utc)).total_seconds(), monotonic_end-time.monotonic())
                        if remaining <= 0:
                            raise PermissionError('original delivery window elapsed')
                        self.connection.settimeout(remaining)
                        self.wfile.write(result.data[offset:offset+65536])
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
        daemon_threads = False
        block_on_close = False

        def __init__(self):
            self.closing = False
            self._active = set()
            self._active_condition = threading.Condition()
            super().__init__((profile.listen_host, profile.listen_port), Handler, tls=tls)

        def process_request(self, request, address):
            # No peer, settings or body work precedes this original capture.
            request._oracle_view_original_wall_v1 = datetime.now(timezone.utc)
            request._oracle_view_original_mono_v1 = time.monotonic()
            request._oracle_view_original_end_v1 = min(
                request._oracle_view_original_mono_v1 + 30,
                request._oracle_view_original_mono_v1 + max(0,
                    (installed_end-request._oracle_view_original_wall_v1).total_seconds()))
            with self._active_condition:
                if self.closing or not self._connections.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                self._active.add(request)
            def expire_owned_socket():
                # No selector, authority or retry: only this accepted socket.
                try:
                    request.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                finally:
                    request.close()
            timer = threading.Timer(max(0, request._oracle_view_original_end_v1-time.monotonic()),
                                    expire_owned_socket)
            timer.name = 'oracle-original-view-deadline'
            timer.daemon = True
            request._oracle_view_deadline_timer_v1 = timer
            try:
                timer.start()
                ThreadingHTTPServer.process_request(self, request, address)
            except BaseException:
                timer.cancel()
                if timer.ident is not None:
                    timer.join(timeout=1)
                self.shutdown_request(request)
                if timer.is_alive():
                    raise PermissionError('owned viewer dispatch timer cleanup remains unknown')
                self._connections.release()
                with self._active_condition:
                    self._active.discard(request)
                    self._active_condition.notify_all()
                raise

        def process_request_thread(self, request, address):
            try:
                # SAME thread/context covers the retained actual TLS handshake,
                # HTTP parsing, current peer/settings, body, SQL and delivery.
                with _request_fence_v1(float(request._oracle_view_original_end_v1)):
                    super().process_request_thread(request, address)
            finally:
                timer = request._oracle_view_deadline_timer_v1
                timer.cancel()
                timer.join(timeout=1)
                if timer.is_alive():
                    raise PermissionError('owned viewer socket timer cleanup remains unknown')
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
                    raise PermissionError('owned viewer handlers remain active; delivery unproved')

    server = ViewerServer()
    try:
        settings.current()
        return server
    except BaseException:
        server.server_close()
        raise
