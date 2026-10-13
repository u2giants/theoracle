"""mTLS ingress accepts opaque jobs only; custody and dispatch stay internal."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import ssl
import time
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from contextlib import AbstractContextManager
from uuid import UUID


class GatewayDenied(ValueError):
    pass


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GatewayDenied("duplicate envelope field")
        result[key] = value
    return result


@dataclass(frozen=True)
class OpaqueJob:
    job_id: str
    runtime_hash: str
    admission_hash: str
    nonce: str
    expires_at: int


def parse_job(body: bytes, *, now: int) -> OpaqueJob:
    if len(body) > 2048:
        raise GatewayDenied("request exceeds opaque envelope")
    try:
        obj = json.loads(body, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError):
        raise GatewayDenied("invalid envelope") from None
    if not isinstance(obj, dict) or set(obj) != set(OpaqueJob.__dataclass_fields__):
        raise GatewayDenied("only opaque job fields permitted")
    for field in ("job_id", "nonce"):
        value = obj[field]
        if not isinstance(value, str):
            raise GatewayDenied("invalid job identity")
        try:
            if str(UUID(value)) != value:
                raise ValueError
        except ValueError:
            raise GatewayDenied("invalid job identity") from None
    for field in ("runtime_hash", "admission_hash"):
        if not isinstance(obj[field], str) or not re.fullmatch(r"[a-f0-9]{64}", obj[field]):
            raise GatewayDenied("invalid binding")
    expiry = obj["expires_at"]
    if type(expiry) is not int or not now < expiry <= now + 120:
        raise GatewayDenied("expired or excessive lease")
    return OpaqueJob(**obj)


def signature_message(method: str, path: str, body: bytes) -> bytes:
    if method != 'POST' or path not in {'/v1/jobs/admit','/v1/jobs/result'}:
        raise GatewayDenied('fixed signature purpose required')
    return method.encode()+b'\n'+path.encode()+b'\n'+body


@dataclass(frozen=True)
class ResultLease:
    status: int
    body: bytes
    before_write: Callable[[], None]


def server_tls(*, certfile: str, keyfile: str, cafile: str) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_3
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_cert_chain(certfile, keyfile)
    context.load_verify_locations(cafile=cafile)
    return context


class MutualTLSServer(ThreadingHTTPServer):
    """Bounded handshakes happen in request threads, not the accept loop."""
    daemon_threads = True

    def __init__(self, address, handler, *, tls):
        self.tls = tls
        self._connections = threading.BoundedSemaphore(32)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self._connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._connections.release()
            raise

    def get_request(self):
        raw, address = self.socket.accept()
        raw.settimeout(5)
        try:
            wrapped = self.tls.wrap_socket(raw, server_side=True, do_handshake_on_connect=False)
        except Exception:
            raw.close()
            raise
        return wrapped, address

    def process_request_thread(self, request, client_address):
        try:
            request.do_handshake()
            self.finish_request(request, client_address)
        except (ssl.SSLError, OSError):
            pass
        finally:
            self.shutdown_request(request)
            self._connections.release()


class OpaqueGateway(MutualTLSServer):
    """Admission callback atomically verifies custody, nonce and revocation.

    The callback returns no data. It must persist an accepted job or raise.
    It rechecks admission/worker revocation for every request, including an
    already established TLS session. No default callback or permissive mode.
    """

    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, tls: ssl.SSLContext,
                 worker_uri: str, signing_key: bytes,
                 admit: Callable[[OpaqueJob, str], None],
                 clock: Callable[[], float] = time.time,
                 result: Callable[[OpaqueJob, str], AbstractContextManager[ResultLease]] | None = None):
        if tls.verify_mode != ssl.CERT_REQUIRED or len(signing_key) < 32:
            raise GatewayDenied("mutual TLS and strong job authentication required")
        if not worker_uri.startswith("spiffe://oracle/") or not callable(admit):
            raise GatewayDenied("bound worker and custody callback required")
        self.worker_uri, self.signing_key = worker_uri, signing_key
        self.admit, self.clock, self.result = admit, clock, result
        super().__init__(address, _Handler, tls=tls)


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *_args):
        # Requests contain custody identifiers and are never logged verbatim.
        pass

    def _reply(self, status: int, body: bytes = b""):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply(404)

    do_CONNECT = do_GET
    do_PUT = do_GET
    do_PATCH = do_GET
    do_DELETE = do_GET

    def do_POST(self):
        self.connection.settimeout(5)
        if self.path not in {"/v1/jobs/admit", "/v1/jobs/result"}:
            return self._reply(404)
        if self.headers.get("Transfer-Encoding") is not None:
            return self._reply(403 if self.path=="/v1/jobs/result" else 400)
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            return self._reply(403 if self.path=="/v1/jobs/result" else 400)
        length = int(lengths[0])
        if not 0 < length <= 2048:
            return self._reply(403 if self.path=="/v1/jobs/result" else 413)
        if self.headers.get_content_type() != "application/json":
            return self._reply(403 if self.path=="/v1/jobs/result" else 415)
        signatures = self.headers.get_all("X-Oracle-Job-Signature", [])
        if len(signatures) != 1:
            return self._reply(403)
        body = self.rfile.read(length)
        if len(body) != length:
            return self._reply(403 if self.path=="/v1/jobs/result" else 400)
        server: OpaqueGateway = self.server
        certificate = self.connection.getpeercert()
        uris = [value for kind, value in certificate.get("subjectAltName", ()) if kind == "URI"]
        signature = hmac.new(server.signing_key, signature_message("POST",self.path,body), hashlib.sha256).hexdigest()
        if uris != [server.worker_uri] or not hmac.compare_digest(signature, signatures[0]):
            return self._reply(403)
        try:
            job = parse_job(body, now=int(server.clock()))
            if self.path == '/v1/jobs/result':
                if server.result is None: raise GatewayDenied('result authority unavailable')
                deadline=time.monotonic()+5
                with server.result(job,server.worker_uri) as lease:
                    if (not isinstance(lease,ResultLease) or lease.status not in {200,202}
                            or not isinstance(lease.body,bytes) or len(lease.body)>131072):
                        raise GatewayDenied('bounded result lease required')
                    lease.before_write()
                    if server.clock()>=job.expires_at or time.monotonic()>=deadline:
                        raise GatewayDenied('result lease expired')
                    self.connection.settimeout(max(.001,deadline-time.monotonic()))
                    response=(f'HTTP/1.0 {lease.status} OK\r\nContent-Type: application/json\r\n'
                              f'Content-Length: {len(lease.body)}\r\nCache-Control: no-store\r\n\r\n').encode()+lease.body
                    self._result_started=True
                    self.connection.sendall(response)
                return
            server.admit(job, server.worker_uri)
        except Exception:
            # Callback failure, revoke, drift and unavailable custody fail closed.
            if getattr(self,'_result_started',False):
                self.close_connection=True
                return
            return self._reply(403)
        receipt = json.dumps({"job_id": job.job_id, "request_hash": hashlib.sha256(body).hexdigest(),
                              "state": "accepted"}, separators=(",", ":")).encode()
        self._reply(202, receipt)
