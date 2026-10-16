"""Opt-in fixed mTLS metadata transport; never a provider-content endpoint."""
from __future__ import annotations

import http.client
import json
import math
import re
import ssl
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from .gateway import GatewayDenied, unique_object
from .parent_observer_v2 import ParentObserverTransportV2
from .egress import EgressServer


def _hex(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _object(raw, fields):
    try:
        value = json.loads(raw, object_pairs_hook=unique_object)
        if not isinstance(value, dict) or set(value) != fields:
            raise ValueError
        return value
    except (ValueError, TypeError, UnicodeError):
        raise GatewayDenied("invalid purpose metadata envelope") from None


@dataclass(frozen=True)
class PurposeTLSBindingV2:
    """Trusted startup pins, not authority inferred from an HTTP body."""
    hostname: str
    port: int
    server_uri: str
    ca_file: Path
    certificate_file: Path
    key_file: Path
    timeout: float = 5.0

    def __post_init__(self):
        if (not isinstance(self.hostname, str) or not self.hostname
                or any(c in self.hostname for c in "/:@?#\\\t\r\n ")
                or type(self.port) is not int or not 0 < self.port < 65536
                or not isinstance(self.server_uri, str)
                or not self.server_uri.startswith("spiffe://oracle/")
                or any(c.isspace() for c in self.server_uri)
                or type(self.timeout) not in (int, float)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 5):
            raise GatewayDenied("fixed purpose TLS pins required")
        for path in (self.ca_file, self.certificate_file, self.key_file):
            if (not isinstance(path, Path) or not path.is_absolute() or path.is_symlink()
                    or not path.is_file() or path.stat().st_mode & 0o077):
                raise GatewayDenied("protected TLS material required")


class _FixedTLSClientV2:
    def __init__(self, binding: PurposeTLSBindingV2):
        if type(binding) is not PurposeTLSBindingV2:
            raise GatewayDenied("typed fixed TLS binding required")
        self.binding = binding
        # No system trust, environment proxy, redirects, or caller-supplied URL.
        self._tls = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self._tls.minimum_version = ssl.TLSVersion.TLSv1_2
        self._tls.load_verify_locations(cadata=binding.ca_file.read_text())
        self._tls.load_cert_chain(binding.certificate_file, binding.key_file)

    def _post(self, route: str, value: dict, limit: int) -> bytes:
        conn = http.client.HTTPSConnection(self.binding.hostname, self.binding.port,
            timeout=self.binding.timeout, context=self._tls)
        try:
            conn.connect()
            uris = [v for k, v in conn.sock.getpeercert().get("subjectAltName", ()) if k == "URI"]
            if uris != [self.binding.server_uri]:
                raise GatewayDenied("purpose server identity mismatch")
            body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
            conn.request("POST", route, body, {"Content-Type": "application/json"})
            response = conn.getresponse()
            lengths = response.headers.get_all("Content-Length", [])
            if (response.status != 200 or response.headers.get("Transfer-Encoding") is not None
                    or len(lengths) != 1 or not lengths[0].isdigit()
                    or not 0 < int(lengths[0]) <= limit
                    or response.headers.get_content_type() != "application/json"):
                raise GatewayDenied("purpose response refused")
            raw = response.read(limit + 1)
            if len(raw) != int(lengths[0]):
                raise GatewayDenied("purpose response length mismatch")
            return raw
        finally:
            conn.close()


class ParentObserverClientV2(_FixedTLSClientV2, ParentObserverTransportV2):
    """Consumer transport only; signature/currentness validation belongs to R3."""
    def fetch_current(self, challenge: str) -> bytes:
        if not _hex(challenge):
            raise GatewayDenied("fresh canonical observer challenge required")
        raw = self._post("/v2/parent/current", {"schema_version": 2,
            "purpose": "complete-parent-currentness-v2", "challenge": challenge}, 100_000)
        _object(raw, {"witness", "signature"})
        return raw

    current = fetch_current


class PurposeProviderClientV2(_FixedTLSClientV2):
    def dispatch(self, dispatch_id: UUID, request_hash: str, phase_registry_sha256: str) -> dict:
        if type(dispatch_id) is not UUID or not _hex(request_hash) or not _hex(phase_registry_sha256):
            raise GatewayDenied("canonical purpose dispatch identity required")
        request = {"dispatch_id": str(dispatch_id), "request_hash": request_hash,
                   "phase_registry_sha256": phase_registry_sha256}
        result = _object(self._post("/v1/provider/chat", request, 4096),
            set(request) | {"raw_response_hash", "receipt_hash"})
        if (any(result[k] != v for k, v in request.items())
                or not _hex(result["raw_response_hash"]) or not _hex(result["receipt_hash"])):
            raise GatewayDenied("unbound purpose receipt metadata")
        return result


class PurposeIngressBridgeV2:
    """EgressServer adapter; its worker URI must equal the server's TLS pin."""
    def __init__(self, ingress, worker_uri: str):
        if not callable(getattr(ingress, "dispatch", None)) or not worker_uri.startswith("spiffe://oracle/"):
            raise GatewayDenied("fixed purpose ingress required")
        self._ingress, self.worker_uri = ingress, worker_uri

    def dispatch(self, raw: bytes) -> bytes:
        request = _object(raw, {"dispatch_id", "request_hash", "phase_registry_sha256"})
        try:
            if str(UUID(request["dispatch_id"])) != request["dispatch_id"]:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise GatewayDenied("invalid dispatch identity") from None
        if not _hex(request["request_hash"]) or not _hex(request["phase_registry_sha256"]):
            raise GatewayDenied("invalid dispatch seal")
        result = self._ingress.dispatch(self.worker_uri, request)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        receipt = _object(encoded, set(request) | {"raw_response_hash", "receipt_hash"})
        if (any(receipt[k] != v for k, v in request.items())
                or not _hex(receipt["raw_response_hash"]) or not _hex(receipt["receipt_hash"])
                or len(encoded) > 4096):
            raise GatewayDenied("private content or unbound receipt refused")
        return encoded


def purpose_ingress_server_v2(address: tuple[str, int], *, tls: ssl.SSLContext,
                              worker_uri: str, ingress) -> EgressServer:
    """One constructor binds the verified TLS peer and reconstructed job caller."""
    return EgressServer(address, tls=tls, executor_uri=worker_uri,
        egress=PurposeIngressBridgeV2(ingress, worker_uri))
