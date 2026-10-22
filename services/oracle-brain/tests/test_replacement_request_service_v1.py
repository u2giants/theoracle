"""Actual loopback mTLS/HTTP with real requester factory, recording SQL only."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
from pathlib import Path
import shutil
import socket
import ssl
import threading
import time

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
import pytest

from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.replacement_request_service_v1 import (
    RequesterPeerProfileV1, protected_replacement_request_server_v1,
)
from test_hosting_boundary import certificates, WORKER
from test_replacement_requester_v1 import fixture as database_fixture, request as control_request


def profile_fixture(tmp_path, monkeypatch, certificates, **changes):
    directory = tmp_path / 'database'; directory.mkdir()
    f = database_fixture(directory, monkeypatch)
    copied = tmp_path / 'tls'; copied.mkdir(mode=0o700)
    for filename in ('server.pem', 'server.key', 'ca.pem'):
        shutil.copyfile(certificates / filename, copied / filename)
        (copied / filename).chmod(0o600)
    def seal(name): return hashlib.sha256((copied / name).read_bytes()).hexdigest()
    worker = x509.load_pem_x509_certificate((certificates / 'worker.pem').read_bytes()).public_bytes(Encoding.DER)
    c = f.s.config; now = datetime.now(timezone.utc)
    body = dict(schema_version=1, purpose='replacement-requester-peer-v1',
        intake_config_sha256=f.s.config_sha256, intake_appointment_sha256=f.s.appointment_sha256,
        principal_id=str(c.principal_id), workspace_id=str(c.workspace_id), runtime_hash=c.runtime_hash, registry_hash=c.registry_hash,
        client_uri=WORKER, client_certificate_sha256=hashlib.sha256(worker).hexdigest(),
        listen_host='127.0.0.1', listen_port=0, server_hostname='localhost',
        server_certificate_file=str(copied / 'server.pem'), server_certificate_sha256=seal('server.pem'),
        server_key_file=str(copied / 'server.key'), server_key_sha256=seal('server.key'),
        client_ca_file=str(copied / 'ca.pem'), client_ca_sha256=seal('ca.pem'),
        issuer_actor=str(f.s.expected_issuer_actor), reviewer_actor=str(f.s.expected_reviewer_actor),
        valid_from=(now - timedelta(seconds=1)).isoformat(), expires_at=(now + timedelta(seconds=10)).isoformat(),
        original_horizon=c.original_horizon.isoformat())
    body.update(changes)
    # Use the canonical model encoding that startup rereads exactly.
    profile = RequesterPeerProfileV1.model_validate_json(json.dumps(body))
    path = tmp_path / 'peer-profile'
    raw = canonical_bytes(profile.model_dump(mode='json')); path.write_bytes(raw); path.chmod(0o600)
    return f, path, hashlib.sha256(raw).hexdigest(), copied


@contextmanager
def running(tmp_path, monkeypatch, certificates, **changes):
    f, path, seal, tls = profile_fixture(tmp_path, monkeypatch, certificates, **changes)
    server = protected_replacement_request_server_v1(f.s, path, seal)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01}, daemon=False)
    thread.start()
    try: yield f, path, tls, server
    finally:
        server.shutdown(); server.server_close(); thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno() == -1


def client(server, certificates, identity='worker', trusted=True):
    context = ssl.create_default_context(cafile=str(certificates / 'ca.pem')) if trusted else ssl.create_default_context()
    if identity:
        context.load_cert_chain(str(certificates / (identity + '.pem')), str(certificates / (identity + '.key')))
    return http.client.HTTPSConnection('localhost', server.server_port, context=context, timeout=2)


def body(f, deadline=5, **changes):
    return control_request(f, caller_deadline=(datetime.now(timezone.utc) + timedelta(seconds=deadline)).isoformat(), **changes)


def send(server, certificates, payload, *, identity='worker', path='/v1/replacement/control', headers=None, method='POST'):
    connection = client(server, certificates, identity)
    try:
        connection.request(method, path, body=payload, headers=headers or {'Content-Type': 'application/json'})
        response = connection.getresponse(); return response.status, response.read(), dict(response.getheaders())
    finally: connection.close()


def test_actual_mtls_real_factory_returns_only_control_metadata(tmp_path, monkeypatch, certificates):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        status, raw, headers = send(server, certificates, body(f))
        assert status == 200 and f.connects == 1
        value = json.loads(raw)
        assert raw == canonical_bytes(value)
        assert set(value) == {'runId', 'journeyRevision', 'controlState', 'populationSha256',
                              'cancelRequested', 'remoteStopProven', 'resultAvailable'}
        assert value['remoteStopProven'] is False and value['resultAvailable'] is False
        assert headers['Cache-Control'] == 'no-store' and int(headers['Content-Length']) == len(raw)
        assert headers['Content-Type'] == 'application/json'
        assert headers['Connection'] == 'close'


@pytest.mark.parametrize('identity', ['other', None])
def test_wrong_or_missing_actual_client_identity_never_reaches_sql(tmp_path, monkeypatch, certificates, identity):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        try:
            result = send(server, certificates, body(f), identity=identity)
            assert result[0] == 503
        except (ssl.SSLError, ConnectionResetError, BrokenPipeError): pass
        assert f.connects == 0


def test_wrong_actual_server_ca_denies_tls_before_sql(tmp_path, monkeypatch, certificates):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        connection = client(server, certificates, trusted=False)
        try:
            with pytest.raises(ssl.SSLError):
                connection.request('POST', '/v1/replacement/control', body=body(f))
        finally: connection.close()
        assert f.connects == 0


def test_pinned_client_der_cannot_replace_exact_peer_uri(tmp_path, monkeypatch, certificates):
    with running(tmp_path, monkeypatch, certificates, client_uri='spiffe://oracle/foreign') as (f, path, tls, server):
        assert send(server, certificates, body(f))[0] == 503
        assert f.connects == 0


@pytest.mark.parametrize('attack', ['encoding', 'wrongtype', 'otherpath', 'querypath', 'get', 'large', 'unknownfields', 'duplicatejson', 'noncanonical', 'excessive-deadline', 'excessive-profile-window', 'expired-deadline'])
def test_actual_http_cannot_expand_control_scope_or_window(tmp_path, monkeypatch, certificates, attack):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        payload = body(f); headers = {'Content-Type': 'application/json'}; route = '/v1/replacement/control'; method = 'POST'
        if attack == 'encoding': headers['Content-Encoding'] = 'identity'
        elif attack == 'wrongtype': headers['Content-Type'] = 'text/plain'
        elif attack == 'otherpath': route = '/originals'
        elif attack == 'querypath': route += '?operation=advance'
        elif attack == 'get': method = 'GET'
        elif attack == 'large': payload = b' ' * 65537
        elif attack == 'unknownfields': payload = body(f, actor='forged')
        elif attack == 'duplicatejson': payload = payload[:-1] + b',"operation":"reserve"}'
        elif attack == 'noncanonical': payload = b' ' + payload
        elif attack == 'excessive-deadline': payload = body(f, deadline=31)
        elif attack == 'excessive-profile-window': payload = body(f, deadline=11)
        elif attack == 'expired-deadline': payload = body(f, deadline=-1)
        status, raw, _ = send(server, certificates, payload, path=route, method=method, headers=headers)
        assert status in (404, 503) and raw == b'' and f.connects == 0


@pytest.mark.parametrize('header', ['Content-Length', 'Content-Type', 'Transfer-Encoding'])
def test_duplicate_or_chunked_http_headers_deny_without_sql(tmp_path, monkeypatch, certificates, header):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        payload = body(f); connection = client(server, certificates)
        try:
            connection.putrequest('POST', '/v1/replacement/control')
            connection.putheader('Content-Type', 'application/json')
            connection.putheader('Content-Length', str(len(payload)))
            connection.putheader(header, {'Content-Length': str(len(payload)), 'Content-Type': 'application/json', 'Transfer-Encoding': 'chunked'}[header])
            connection.endheaders(payload)
            response = connection.getresponse()
            assert response.status == 503 and response.read() == b'' and f.connects == 0
        finally: connection.close()


@pytest.mark.parametrize('attack', ['profile', 'tls-key', 'appointment'])
def test_changed_pins_refuse_before_body_or_sql(tmp_path, monkeypatch, certificates, attack):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        target = {'profile': path, 'tls-key': tls / 'server.key', 'appointment': f.s.appointment_path}[attack]
        target.write_bytes(b'changed invented pin')
        assert send(server, certificates, body(f))[0] == 503 and f.connects == 0


@pytest.mark.parametrize('attack', ['principal', 'workspace', 'runtime', 'registry', 'issuer', 'expired', 'hash'])
def test_startup_profile_must_match_existing_independent_appointment(tmp_path, monkeypatch, certificates, attack):
    from uuid import uuid4
    changes = {}
    if attack in ('principal', 'workspace'): changes[attack + '_id'] = str(uuid4())
    elif attack in ('runtime', 'registry'): changes[attack + '_hash'] = 'f' * 64
    elif attack == 'issuer': changes['issuer_actor'] = str(uuid4())
    elif attack == 'expired': changes['expires_at'] = (datetime.now(timezone.utc) - timedelta(seconds=.1)).isoformat()
    f, path, seal, tls = profile_fixture(tmp_path, monkeypatch, certificates, **changes)
    with pytest.raises((ValueError, PermissionError)):
        protected_replacement_request_server_v1(f.s, path, '0' * 64 if attack == 'hash' else seal)
    assert f.connects == 0


def test_slow_actual_body_cannot_reset_profile_deadline(tmp_path, monkeypatch, certificates):
    expiry = (datetime.now(timezone.utc) + timedelta(seconds=.25)).isoformat()
    with running(tmp_path, monkeypatch, certificates, expires_at=expiry) as (f, path, tls, server):
        payload = body(f); connection = client(server, certificates)
        try:
            connection.putrequest('POST', '/v1/replacement/control')
            connection.putheader('Content-Type', 'application/json'); connection.putheader('Content-Length', str(len(payload)))
            connection.endheaders(payload[:1]); time.sleep(.3)
            response = connection.getresponse()
            assert response.status == 503 and response.read() == b'' and f.connects == 0
        finally: connection.close()


@pytest.mark.parametrize('attack', ['late', 'uncertain-close', 'profile-after-sql'])
def test_actual_http_withholds_success_after_late_or_uncertain_sql(tmp_path, monkeypatch, certificates, attack):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        seconds = 5
        if attack == 'late': f.on_commit = lambda: time.sleep(.12); seconds = .08
        elif attack == 'uncertain-close': f.close_error = True
        else: f.on_close = lambda: path.write_bytes(b'changed profile after SQL')
        status, raw, _ = send(server, certificates, body(f, deadline=seconds))
        assert status == 503 and raw == b'' and f.connects == 1
        assert f.events.count('commit') == 1


def test_full_connection_capacity_refusal_leaves_no_owned_handler(tmp_path, monkeypatch, certificates):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        for _ in range(32): assert server._connections.acquire(blocking=False)
        try:
            with pytest.raises((ssl.SSLError, ConnectionResetError, http.client.RemoteDisconnected, BrokenPipeError)):
                send(server, certificates, body(f))
            assert not server._active and f.connects == 0
        finally:
            for _ in range(32): server._connections.release()


def test_actual_expired_client_certificate_denied_even_when_der_and_uri_are_pinned(tmp_path, monkeypatch, certificates):
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    ca = x509.load_pem_x509_certificate((certificates / 'ca.pem').read_bytes())
    issuer = serialization.load_pem_private_key((certificates / 'ca.key').read_bytes(), password=None)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    expired = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'expired invented client')]))
        .issuer_name(ca.subject).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2)).not_valid_after(now - timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.UniformResourceIdentifier(WORKER)]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(issuer, hashes.SHA256()))
    pem = tmp_path / 'expired.pem'; pem.write_bytes(expired.public_bytes(Encoding.PEM)); pem.chmod(0o600)
    private = tmp_path / 'expired.key'
    private.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())); private.chmod(0o600)
    with running(tmp_path, monkeypatch, certificates,
                 client_certificate_sha256=hashlib.sha256(expired.public_bytes(Encoding.DER)).hexdigest()) as (f, path, tls, server):
        context = ssl.create_default_context(cafile=str(certificates / 'ca.pem'))
        context.load_cert_chain(str(pem), str(private))
        connection = http.client.HTTPSConnection('localhost', server.server_port, context=context, timeout=2)
        try:
            with pytest.raises((ssl.SSLError, ConnectionResetError, BrokenPipeError)):
                connection.request('POST', '/v1/replacement/control', body=body(f), headers={'Content-Type': 'application/json'})
                connection.getresponse()
        finally: connection.close()
        assert f.connects == 0


def test_idle_untrusted_tcp_does_not_hold_sql_or_block_valid_tls(tmp_path, monkeypatch, certificates):
    with running(tmp_path, monkeypatch, certificates) as (f, path, tls, server):
        idle = socket.create_connection(('127.0.0.1', server.server_port), timeout=2)
        try:
            assert send(server, certificates, body(f))[0] == 200
            assert f.connects == 1
        finally: idle.close()


def test_partial_success_write_closes_without_appending_second_http_response(tmp_path, monkeypatch, certificates):
    import socketserver
    original_write = socketserver._SocketWriter.write
    def interrupted_write(writer, data):
        if data.startswith(b'{'):
            original_write(writer, data[:8])
            raise OSError('invented partial transport write')
        return original_write(writer, data)
    monkeypatch.setattr(socketserver._SocketWriter, 'write', interrupted_write)
    with running(tmp_path, monkeypatch, certificates) as (f, _, _, server):
        connection = client(server, certificates)
        connection._create_connection = lambda address, timeout, source_address: socket.create_connection(
            ('127.0.0.1', address[1]), timeout, source_address)
        try:
            connection.request('POST', '/v1/replacement/control', body=body(f), headers={'Content-Type':'application/json'})
            response = connection.getresponse()
            assert response.status == 200
            with pytest.raises(http.client.IncompleteRead) as failure:
                response.read()
            assert failure.value.partial.startswith(b'{')
            assert b'HTTP/' not in failure.value.partial
        finally:
            connection.close()
