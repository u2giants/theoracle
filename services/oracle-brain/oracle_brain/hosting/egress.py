"""Fixed OpenRouter egress; no URL, proxy, retry or unreserved dispatch mode."""
from __future__ import annotations

import hashlib
import json
import ssl
import urllib.request
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler
from typing import Callable
from uuid import UUID

from .gateway import GatewayDenied, MutualTLSServer, unique_object

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
PROVIDER_POLICY = {"only": ["openai"], "allow_fallbacks": False,
                   "require_parameters": True, "data_collection": "deny"}


def request_bytes(body: bytes, *, allowed_models: frozenset[str]) -> tuple[str, str, bytes]:
    """Validate fixed chat envelope; canonical hash binds the actual request."""
    if len(body) > 2_000_000:
        raise GatewayDenied("egress envelope too large")
    try:
        obj = json.loads(body, object_pairs_hook=unique_object)
        if not isinstance(obj, dict) or set(obj) != {"reservation_id", "request_hash", "request"}:
            raise ValueError
        identity = obj["reservation_id"]
        if not isinstance(identity, str) or str(UUID(identity)) != identity:
            raise ValueError
        request = obj["request"]
        if not isinstance(request, dict):
            raise ValueError
        permitted = {"model", "messages", "response_format", "max_completion_tokens",
                     "temperature", "store", "provider", "stream"}
        if set(request) - permitted or request.get("model") not in allowed_models:
            raise ValueError
        if request.get("provider") != PROVIDER_POLICY or request.get("store") is not False:
            raise ValueError
        if request.get("stream", False) is not False:
            raise ValueError
        cap = request.get("max_completion_tokens")
        if type(cap) is not int or not 0 < cap <= 32768:
            raise ValueError
        if not isinstance(request.get("messages"), list) or not request["messages"]:
            raise ValueError
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"),
                             allow_nan=False).encode()
        digest = hashlib.sha256(encoded).hexdigest()
        if obj["request_hash"] != digest:
            raise ValueError
        return identity, digest, encoded
    except (ValueError, TypeError, UnicodeError):
        raise GatewayDenied("invalid or unbound provider request") from None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise GatewayDenied("provider redirects are forbidden")


def provider_post(encoded: bytes, *, api_key: str) -> bytes:
    # Disable environment proxies and redirects; normal hostname/CA validation.
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context), _NoRedirect())
    request = urllib.request.Request(ENDPOINT, data=encoded, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + api_key})
    with opener.open(request, timeout=90) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise GatewayDenied("provider response too large")
    return raw


class ReservedEgress:
    """Trusted reservation context owns atomic dispatch intent and settlement.

    reserve must verify actual current global ledger/price/permission inputs,
    reject reused dispatch intent, and retain ambiguous failures. It receives
    the canonical request hash and bytes, not caller-supplied cost claims.
    settle verifies response usage. Their absence is a startup failure.
    """

    def __init__(self, *, allowed_models: frozenset[str], api_key: str,
                 reserve: Callable[[str, str, bytes], AbstractContextManager],
                 settle: Callable[[str, str, bytes], None],
                 transport: Callable[[bytes], bytes] | None = None):
        if (not allowed_models or any(not x.startswith("openai/") or ":" in x for x in allowed_models)
                or not api_key or not callable(reserve) or not callable(settle)):
            raise GatewayDenied("bound provider reservation and settlement required")
        self.allowed_models, self.reserve, self.settle = allowed_models, reserve, settle
        self.transport = transport or (lambda raw: provider_post(raw, api_key=api_key))

    def dispatch(self, body: bytes) -> bytes:
        identity, digest, encoded = request_bytes(body, allowed_models=self.allowed_models)
        with self.reserve(identity, digest, encoded):
            raw = self.transport(encoded)
            self.settle(identity, digest, raw)
        return raw


class EgressServer(MutualTLSServer):
    """Internal-only mTLS executor ingress. Never publish this service's port."""
    daemon_threads = True

    def __init__(self, address: tuple[str, int], *, tls: ssl.SSLContext,
                 executor_uri: str, egress: ReservedEgress):
        if tls.verify_mode != ssl.CERT_REQUIRED or not executor_uri.startswith("spiffe://oracle/"):
            raise GatewayDenied("bound executor mutual TLS required")
        self.executor_uri, self.egress = executor_uri, egress
        super().__init__(address, _EgressHandler, tls=tls)


class _EgressHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *_args):
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
        if self.path != "/v1/provider/chat":
            return self._reply(404)
        if self.headers.get("Transfer-Encoding") is not None:
            return self._reply(400)
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            return self._reply(400)
        length = int(lengths[0])
        if not 0 < length <= 2_000_000:
            return self._reply(413)
        if self.headers.get_content_type() != "application/json":
            return self._reply(415)
        uris = [value for kind, value in self.connection.getpeercert().get("subjectAltName", ()) if kind == "URI"]
        if uris != [self.server.executor_uri]:
            return self._reply(403)
        raw = self.rfile.read(length)
        if len(raw) != length:
            return self._reply(400)
        try:
            result = self.server.egress.dispatch(raw)
        except Exception:
            return self._reply(403)
        self._reply(200, result)
