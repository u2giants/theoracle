"""Private protected control transport/lifecycle owner. No identity or authority.

Only fixed server startup modules select the protected purpose/settings/parser.
HTTP input cannot choose any callback, URL, class, key, role or permission.
"""
from datetime import datetime,timezone,timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading,time,socket,ipaddress
from .gateway import MutualTLSServer,server_tls
from .replacement_transport_v1 import fixed_request_length_v1,read_request_body_v1,peer_der_v1

from ..operating_model.request_deadline_v1 import request_remaining_v1,_request_fence_v1


def _protected_control_listener_v1(settings,factory,*,path,parse_request,encode_response,maximum_request_bytes=65536,maximum_response_bytes=4096):
    profile=settings.profile
    settings.current()
    tls=server_tls(certfile=profile.server_certificate_file,keyfile=profile.server_key_file,cafile=profile.client_ca_file)
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
                length = fixed_request_length_v1(self, path=path, content_type='application/json', maximum_bytes=maximum_request_bytes)
                # Prove actual externally pinned peer BEFORE body read or SQL.
                peer_der_v1(self.connection, expected_uri=profile.client_uri,
                            expected_der_sha256=profile.client_certificate_sha256)
                bound = settings.current()
                original_end = min(self.original_monotonic_start + 30,
                    time.monotonic() + max(0, (bound - datetime.now(timezone.utc)).total_seconds()))
                raw_request = read_request_body_v1(self, length, absolute_monotonic_deadline=original_end)
                request = parse_request(raw_request)
                if not datetime.now(timezone.utc) < request.caller_deadline <= min(
                        self.original_start + timedelta(seconds=30), bound):
                    raise PermissionError('original requester window expired or excessive')
                original_end = min(original_end, self.original_monotonic_start +
                    (request.caller_deadline - self.original_start).total_seconds())
                if self.server.closing or time.monotonic() >= original_end:
                    raise PermissionError('original requester deadline elapsed')
                with _request_fence_v1(float(original_end)):
                    settings.current()
                    value = factory.execute_v1(raw_request)
                    # Factory checked actual SQL context, commit and close; metadata
                    # is still withheld on any peer/profile/deadline/lifecycle drift.
                    peer_der_v1(self.connection, expected_uri=profile.client_uri,
                                expected_der_sha256=profile.client_certificate_sha256)
                    settings.current()
                    if self.server.closing or time.monotonic() >= original_end:
                        raise PermissionError('original requester reply expired')
                encoded = encode_response(value)
                if type(encoded) is not bytes or not 0<len(encoded)<=maximum_response_bytes:
                    raise PermissionError('fixed bounded protected metadata required')
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
            except Exception as exc:
                import sys,traceback
                with open('/tmp/backend-diag.log','a') as _f:
                    _f.write('ORACLE-DIAG-BACKEND-EXC type=%s msg=%s started=%s\n'%(type(exc).__name__,exc,started))
                    traceback.print_exc(file=_f)
                if not started:
                    self._deny()

    class RequesterServer(MutualTLSServer):
        address_family=socket.AF_INET6 if ipaddress.ip_address(profile.listen_host).version==6 else socket.AF_INET
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
