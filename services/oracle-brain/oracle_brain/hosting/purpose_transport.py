"""Opt-in fixed mTLS metadata transport; never a provider-content endpoint."""
from __future__ import annotations

import http.client
import json
import math
import re
import ssl
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID
from cryptography import x509
from cryptography.x509.oid import ExtensionOID

from .gateway import GatewayDenied, unique_object
from .parent_observer_v2 import ParentObserverTransportV2
from .egress import EgressServer, _EgressHandler


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
    client_uri: str
    ca_file: Path
    certificate_file: Path
    key_file: Path
    timeout: float = 5.0

    def __post_init__(self):
        if (not isinstance(self.hostname, str)
                or re.fullmatch(r"[A-Za-z0-9.-]+", self.hostname) is None
                or type(self.port) is not int or not 0 < self.port < 65536
                or any(not isinstance(uri, str) or re.fullmatch(
                    r"spiffe://oracle/[A-Za-z0-9._/-]+", uri) is None
                    for uri in (self.server_uri, self.client_uri))
                or type(self.timeout) not in (int, float)
                or not math.isfinite(self.timeout) or not 0 < self.timeout <= 90):
            raise GatewayDenied("fixed purpose TLS pins required")
        for path in (self.ca_file, self.certificate_file, self.key_file):
            if (not isinstance(path, Path) or not path.is_absolute() or path.is_symlink()
                    or not path.is_file() or path.stat().st_mode & 0o077):
                raise GatewayDenied("protected TLS material required")
        try:
            certificate = x509.load_pem_x509_certificate(self.certificate_file.read_bytes())
            identities = certificate.extensions.get_extension_for_oid(
                ExtensionOID.SUBJECT_ALTERNATIVE_NAME).value.get_values_for_type(
                    x509.UniformResourceIdentifier)
            if identities != [self.client_uri]:
                raise ValueError
        except (ValueError, x509.ExtensionNotFound):
            raise GatewayDenied("fixed purpose client certificate identity required") from None


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

    def _post(self, route: str, value: dict, limit: int, *, valid_until: datetime | None = None) -> bytes:
        duration = self.binding.timeout
        if valid_until is not None:
            if not isinstance(valid_until, datetime) or valid_until.tzinfo is None or valid_until.utcoffset() is None:
                raise GatewayDenied("aware trusted RPC horizon required")
            duration = min(duration, (valid_until-datetime.now(timezone.utc)).total_seconds())
        if duration <= 0:
            raise GatewayDenied("purpose RPC horizon elapsed")
        deadline = time.monotonic() + duration
        conn = http.client.HTTPSConnection(self.binding.hostname, self.binding.port,
            timeout=duration, context=self._tls)
        timer = None
        try:
            conn.connect()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GatewayDenied("purpose transport deadline elapsed")
            # Socket idle timeouts alone permit unbounded trickled headers/body.
            # This one request owns its socket; abort it at the total deadline.
            active_socket = conn.sock
            def abort():
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            timer = threading.Timer(remaining, abort)
            timer.daemon = True
            timer.start()
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
            if time.monotonic() >= deadline or len(raw) != int(lengths[0]):
                raise GatewayDenied("purpose response length mismatch")
            return raw
        finally:
            if timer is not None:
                timer.cancel()
            conn.close()


class ParentObserverClientV2(_FixedTLSClientV2, ParentObserverTransportV2):
    """Consumer transport only; signature/currentness validation belongs to R3."""
    def __init__(self, binding: PurposeTLSBindingV2):
        if type(binding) is not PurposeTLSBindingV2 or binding.timeout > 5:
            raise GatewayDenied("parent observer total deadline must not exceed five seconds")
        super().__init__(binding)

    def fetch_current(self, challenge: str) -> bytes:
        if not _hex(challenge):
            raise GatewayDenied("fresh canonical observer challenge required")
        raw = self._post("/v2/parent/current", {"schema_version": 2,
            "purpose": "complete-parent-currentness-v2", "challenge": challenge}, 100_000)
        _object(raw, {"witness", "signature"})
        return raw

    current = fetch_current


class PurposeProviderClientV2(_FixedTLSClientV2):
    def dispatch(self, dispatch_id: UUID, request_hash: str, phase_registry_sha256: str,
                 *, deadline: datetime | None = None) -> dict:
        if type(dispatch_id) is not UUID or not _hex(request_hash) or not _hex(phase_registry_sha256):
            raise GatewayDenied("canonical purpose dispatch identity required")
        request = {"dispatch_id": str(dispatch_id), "request_hash": request_hash,
                   "phase_registry_sha256": phase_registry_sha256}
        result = _object(self._post("/v1/provider/chat", request, 4096, valid_until=deadline),
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


class ExtractionProviderClientV2(_FixedTLSClientV2):
    """Distinct extraction qualification field/domain; no purpose-mode switch."""
    def dispatch(self, dispatch_id: UUID, request_hash: str, extraction_qualification_sha256: str,
                 *, deadline: datetime | None = None) -> dict:
        if (type(dispatch_id) is not UUID or not _hex(request_hash)
                or not _hex(extraction_qualification_sha256)):
            raise GatewayDenied("canonical extraction dispatch identity required")
        request = {"dispatch_id": str(dispatch_id), "request_hash": request_hash,
                   "extraction_qualification_sha256": extraction_qualification_sha256}
        result = _object(self._post("/v2/extraction/chat", request, 4096, valid_until=deadline),
            set(request) | {"raw_response_hash", "receipt_hash"})
        if (any(result[k] != v for k, v in request.items())
                or not _hex(result["raw_response_hash"]) or not _hex(result["receipt_hash"])):
            raise GatewayDenied("unbound extraction receipt metadata")
        return result


class ExtractionIngressBridgeV2:
    def __init__(self, ingress, worker_uri: str):
        if not callable(getattr(ingress, "dispatch", None)) or not worker_uri.startswith("spiffe://oracle/"):
            raise GatewayDenied("fixed extraction ingress required")
        self._ingress, self.worker_uri = ingress, worker_uri

    def dispatch(self, raw: bytes) -> bytes:
        request = _object(raw, {"dispatch_id", "request_hash", "extraction_qualification_sha256"})
        try:
            if str(UUID(request["dispatch_id"])) != request["dispatch_id"]:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise GatewayDenied("invalid extraction dispatch identity") from None
        if not _hex(request["request_hash"]) or not _hex(request["extraction_qualification_sha256"]):
            raise GatewayDenied("invalid extraction qualification seal")
        result = self._ingress.dispatch(self.worker_uri, request)
        encoded = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        receipt = _object(encoded, set(request) | {"raw_response_hash", "receipt_hash"})
        if (any(receipt[k] != v for k, v in request.items())
                or not _hex(receipt["raw_response_hash"]) or not _hex(receipt["receipt_hash"])
                or len(encoded) > 4096):
            raise GatewayDenied("private extraction response refused")
        return encoded


class _ExtractionHandlerV2(_EgressHandler):
    def do_POST(self):
        # Exact external route is authenticated by its own listener/peer pin and
        # distinct qualification-field contract before the retained parser runs.
        self.external_path = self.path
        if self.external_path != "/v2/extraction/chat":
            return self._reply(404)
        try:
            self.path = "/v1/provider/chat"
            super().do_POST()
        finally:
            self.path = self.external_path


def extraction_ingress_server_v2(address: tuple[str, int], *, tls: ssl.SSLContext,
                                 worker_uri: str, ingress) -> EgressServer:
    server = EgressServer(address, tls=tls, executor_uri=worker_uri,
        egress=ExtractionIngressBridgeV2(ingress, worker_uri))
    server.RequestHandlerClass = _ExtractionHandlerV2
    return server


def purpose_ingress_server_v2(address: tuple[str, int], *, tls: ssl.SSLContext,
                              worker_uri: str, ingress) -> EgressServer:
    """One constructor binds the verified TLS peer and reconstructed job caller."""
    return EgressServer(address, tls=tls, executor_uri=worker_uri,
        egress=PurposeIngressBridgeV2(ingress, worker_uri))


def main(argv=None):
    """Explicit opt-in startup; the protected loader owns all authority/schema."""
    import argparse
    from .gateway import server_tls
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("extraction", "census", "assembly", "assessment", "embedding"), required=True)
    parser.add_argument("--role", choices=("provider", "metadata"), required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--config-sha256", required=True)
    args = parser.parse_args(argv)
    if args.phase == "extraction":
        from .processing_extraction_runtime_v2 import (load_extraction_runtime_settings_v2,
            build_extraction_broker_v2, build_extraction_metadata_v2)
        settings = load_extraction_runtime_settings_v2(args.config, args.config_sha256,
            expected_role=args.role)
        build_provider, build_metadata = build_extraction_broker_v2, build_extraction_metadata_v2
        build_server = extraction_ingress_server_v2
    else:
        from .purpose_runtime import (load_purpose_runtime_settings_v2,
            build_purpose_broker_v2, build_purpose_metadata_v2)
        settings = load_purpose_runtime_settings_v2(args.config, args.config_sha256,
            expected_phase=args.phase, expected_role=args.role)
        build_provider, build_metadata = build_purpose_broker_v2, build_purpose_metadata_v2
        build_server = purpose_ingress_server_v2
    if settings.phase != args.phase or settings.role != args.role:
        raise GatewayDenied("fixed startup phase/profile mismatch")
    ingress = build_provider(settings) if args.role == "provider" else build_metadata(settings)
    tls = server_tls(certfile=str(settings.server_certificate),
        keyfile=str(settings.server_key), cafile=str(settings.client_ca))
    with build_server((settings.bind_host, settings.bind_port),
            tls=tls, worker_uri=settings.worker_uri, ingress=ingress) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
