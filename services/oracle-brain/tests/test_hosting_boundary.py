"""Invented jobs only: actual mutual TLS ingress and fail-closed egress."""
import hashlib
import hmac
import json
import ssl
import subprocess
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from uuid import uuid4

import pytest

from oracle_brain.hosting.gateway import GatewayDenied, OpaqueGateway, parse_job, server_tls
from oracle_brain.hosting.egress import EgressServer, PROVIDER_POLICY, ReservedEgress, request_bytes

WORKER = "spiffe://oracle/dedicated-trigger"
KEY = b"invented-public-fixture-32-byte-signing-key"


def job(**changes):
    return {"job_id": str(uuid4()), "nonce": str(uuid4()), "runtime_hash": "a" * 64,
            "admission_hash": "b" * 64, "expires_at": 1050, **changes}


@pytest.fixture(scope="module")
def certificates(tmp_path_factory):
    root = tmp_path_factory.mktemp("synthetic-hosting-tls")
    def run(*args):
        subprocess.run(["openssl", *args], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run("req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", "ca.key",
        "-out", "ca.pem", "-days", "1", "-subj", "/CN=Invented Oracle Test CA",
        "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    for name, san, purpose in [("server", "DNS:localhost", "serverAuth"),
                               ("worker", "URI:" + WORKER, "clientAuth"),
                               ("other", "URI:spiffe://oracle/unrelated", "clientAuth")]:
        run("req", "-newkey", "rsa:2048", "-nodes", "-keyout", name + ".key",
            "-out", name + ".csr", "-subj", "/CN=" + name)
        (root / (name + ".ext")).write_text("subjectAltName=" + san + "\nextendedKeyUsage=" + purpose
            + "\nbasicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment"
            + "\nsubjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer")
        run("x509", "-req", "-in", name + ".csr", "-CA", "ca.pem", "-CAkey", "ca.key",
            "-CAcreateserial", "-out", name + ".pem", "-days", "1", "-extfile", name + ".ext")
    for p in root.iterdir():
        p.chmod(0o600)
    return root


@pytest.fixture
def gateway(certificates):
    accepted, revoked, seen = [], [False], set()
    def admit(value, actor):
        if revoked[0] or value.nonce in seen or value.runtime_hash != "a" * 64:
            raise PermissionError("revoked, replay or runtime drift")
        seen.add(value.nonce)
        accepted.append((value, actor))
    root = certificates
    tls = server_tls(certfile=str(root / "server.pem"), keyfile=str(root / "server.key"),
                     cafile=str(root / "ca.pem"))
    server = OpaqueGateway(("127.0.0.1", 0), tls=tls, worker_uri=WORKER,
                           signing_key=KEY, admit=admit, clock=lambda: 1000)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server, accepted, revoked
    server.shutdown()
    server.server_close()
    thread.join(2)


def send(gateway, certificates, obj=None, *, identity="worker", path="/v1/jobs/admit", signed=True):
    context = ssl.create_default_context(cafile=str(certificates / "ca.pem"))
    context.verify_flags |= ssl.VERIFY_X509_STRICT
    if identity:
        context.load_cert_chain(str(certificates / (identity + ".pem")),
                                str(certificates / (identity + ".key")))
    body = json.dumps(obj or job()).encode()
    signature = hmac.new(KEY, b"POST\n"+path.encode()+b"\n"+body, hashlib.sha256).hexdigest() if signed else "0" * 64
    request = urllib.request.Request("https://localhost:" + str(gateway[0].server_port) + path,
        data=body, headers={"Content-Type": "application/json", "X-Oracle-Job-Signature": signature})
    try:
        with urllib.request.urlopen(request, context=context, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, None


def test_actual_mutual_tls_accepts_only_opaque_job(gateway, certificates):
    status, receipt = send(gateway, certificates)
    assert status == 202 and set(receipt) == {"job_id", "request_hash", "state"}
    assert len(gateway[1]) == 1


def test_no_client_certificate_is_denied_before_http(gateway, certificates):
    with pytest.raises((ssl.SSLError, urllib.error.URLError, ConnectionResetError)):
        send(gateway, certificates, identity=None)
    assert gateway[1] == []


def test_idle_untrusted_tcp_does_not_block_other_tls_requests(gateway, certificates):
    import socket
    raw = socket.create_connection(("127.0.0.1", gateway[0].server_port), timeout=2)
    try:
        assert send(gateway, certificates)[0] == 202
    finally:
        raw.close()


@pytest.mark.parametrize("option", [{"identity": "other"}, {"signed": False},
    {"path": "/originals"}, {"path": "/v1/jobs/admit?url=https://example.com"}])
def test_unrelated_identity_signature_and_general_proxy_routes_denied(gateway, certificates, option):
    assert send(gateway, certificates, **option)[0] in {403, 404}
    assert gateway[1] == []


def test_private_payload_rejected(gateway, certificates):
    assert send(gateway, certificates, job(document="invented confidential source"))[0] == 403
    assert not gateway[1]


def test_replay_revocation_and_runtime_drift(gateway, certificates):
    envelope = job()
    assert send(gateway, certificates, envelope)[0] == 202
    assert send(gateway, certificates, envelope)[0] == 403
    assert send(gateway, certificates, job(runtime_hash="c" * 64))[0] == 403
    gateway[2][0] = True
    assert send(gateway, certificates)[0] == 403
    assert len(gateway[1]) == 1


@pytest.mark.parametrize("changes", [{"expires_at": True}, {"expires_at": 1000},
    {"expires_at": 1121}, {"job_id": "../private"}, {"runtime_hash": "A" * 64},
    {"original": "invented source"}])
def test_strict_opaque_envelope(changes):
    with pytest.raises(GatewayDenied):
        parse_job(json.dumps(job(**changes)).encode(), now=1000)


def test_duplicate_fields_denied():
    body = json.dumps(job()).encode()[:-1] + b',"expires_at":1050}'
    with pytest.raises(GatewayDenied):
        parse_job(body, now=1000)


def provider_envelope(**changes):
    request = {"model": "openai/invented-test", "messages": [{"role": "user", "content": "invented"}],
               "max_completion_tokens": 50, "store": False, "provider": PROVIDER_POLICY, **changes}
    encoded = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    return json.dumps({"reservation_id": str(uuid4()), "request_hash": hashlib.sha256(encoded).hexdigest(),
                       "request": request}).encode()


@pytest.mark.parametrize("changes", [{"url": "http://localhost:8000"}, {"model": "other/model"},
    {"store": True}, {"stream": True}, {"provider": {"allow_fallbacks": True}},
    {"max_completion_tokens": 0}, {"max_completion_tokens": True}])
def test_egress_cannot_proxy_fallback_or_unbound_request(changes):
    with pytest.raises(GatewayDenied):
        request_bytes(provider_envelope(**changes), allowed_models=frozenset({"openai/invented-test"}))


def test_reservation_refusal_prevents_transport():
    calls = []
    @contextmanager
    def reserve(*args):
        raise PermissionError("actual global reservation refused")
        yield  # pragma: no cover
    egress = ReservedEgress(allowed_models=frozenset({"openai/invented-test"}), api_key="invented",
        reserve=reserve, settle=lambda *args: None, transport=lambda raw: calls.append(raw))
    with pytest.raises(PermissionError):
        egress.dispatch(provider_envelope())
    assert calls == []


def test_reservation_settlement_and_single_attempt():
    calls = []
    @contextmanager
    def reserve(identity, digest, encoded):
        calls.append(("reserve", digest))
        yield
    def post(raw):
        calls.append(("post", hashlib.sha256(raw).hexdigest()))
        return b'{"usage":{"total_tokens":1}}'
    def settle(identity, digest, response):
        calls.append(("settle", digest))
    egress = ReservedEgress(allowed_models=frozenset({"openai/invented-test"}), api_key="invented",
                           reserve=reserve, settle=settle, transport=post)
    assert egress.dispatch(provider_envelope())
    assert [x[0] for x in calls] == ["reserve", "post", "settle"]
    assert len({x[1] for x in calls}) == 1


def test_actual_internal_broker_mutual_tls_and_no_proxy(certificates):
    calls = []
    @contextmanager
    def reserve(*args):
        calls.append("reserved")
        yield
    egress = ReservedEgress(allowed_models=frozenset({"openai/invented-test"}), api_key="invented",
        reserve=reserve, settle=lambda *args: calls.append("settled"),
        transport=lambda raw: b'{"usage":{"total_tokens":1}}')
    tls = server_tls(certfile=str(certificates / "server.pem"), keyfile=str(certificates / "server.key"),
                     cafile=str(certificates / "ca.pem"))
    server = EgressServer(("127.0.0.1", 0), tls=tls, executor_uri=WORKER, egress=egress)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        context = ssl.create_default_context(cafile=str(certificates / "ca.pem"))
        context.load_cert_chain(str(certificates / "worker.pem"), str(certificates / "worker.key"))
        base = "https://localhost:" + str(server.server_port)
        request = urllib.request.Request(base + "/v1/provider/chat", data=provider_envelope(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, context=context, timeout=3) as response:
            assert response.status == 200
        assert calls == ["reserved", "settled"]
        calls.clear()
        request = urllib.request.Request(base + "/v1/provider/chat?url=http://localhost:8000",
                                         data=provider_envelope(), headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, context=context, timeout=3)
        assert error.value.code == 404 and not calls
        context.load_cert_chain(str(certificates / "other.pem"), str(certificates / "other.key"))
        request = urllib.request.Request(base + "/v1/provider/chat", data=provider_envelope(),
                                         headers={"Content-Type": "application/json"})
        with pytest.raises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request, context=context, timeout=3)
        assert error.value.code == 403 and not calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_topology_never_gives_executor_gateway_or_host_network():
    from pathlib import Path
    import yaml
    obj = yaml.safe_load((Path(__file__).resolve().parents[3] / "dev/oracle2/hosting/topology.yaml").read_text())
    assert set(obj["services"]["executor"]["networks"]) == {"jobs", "ledger", "candidate", "provider"}
    for name in ("jobs", "ledger", "candidate", "confirmed", "provider"):
        network = obj["networks"][name]
        assert network["internal"] is True
        assert network["driver_opts"]["com.docker.network.bridge.gateway_mode_ipv4"] == "isolated"
        assert network["driver_opts"]["com.docker.network.bridge.gateway_mode_ipv6"] == "isolated"
    for name, service in obj["services"].items():
        assert not service.get("ports") and not service.get("privileged") and not service.get("network_mode")
        assert all("docker.sock" not in volume for volume in service.get("volumes", []))
    assert obj["services"]["confirmed"]["networks"] == ["confirmed"]


def test_missing_result_callback_fails_closed(gateway,certificates):
    assert send(gateway,certificates,path='/v1/jobs/result')[0]==403
