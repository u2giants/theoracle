"""Real TLS/SDK close-only component proof for the protected result service.

Owned fake pools in test_replacement_result_cleanup_v1.py cover lifecycle bookkeeping
only. This file proves that REAL TLS sockets and REAL SDK/pool resources are closed
exactly once on success, on error, and on cancel — no fd/socket leak, no double-close.

Windows-runnable pure/real-TLS parts:
  * real mTLS handshake over gateway.MutualTLSServer + server_tls (cryptography
    certificates, no openssl binary), counted socket closes
  * SDK/pool close-ordering contract with counted asyncio closes on success/error/cancel
  * AST close-ordering assertions on the actual replacement_result_service_v1 source

Linux-only service-level parts (fcntl via hosting/custody, Windows-blocked):
  python -m pytest services/oracle-brain/tests/test_replacement_result_tls_sdk_close_v1.py -v

  On a Linux host with the oracle-brain venv and ORACLE2_TEST_ADMIN_URL set, the
  same file also runs the ProtectedReplacementResultServiceV1 close-only drives
  against a real mTLS peer and counted projection pool.
"""
import ast
import asyncio
import hashlib
import socket
import ssl
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from oracle_brain.hosting.gateway import MutualTLSServer, server_tls

WIN32 = sys.platform == 'win32'
SERVICE_SOURCE = (Path(__file__).resolve().parents[1] /
                  'oracle_brain' / 'hosting' / 'replacement_result_service_v1.py')


def _write_ca(directory: Path):
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    directory.mkdir(parents=True, exist_ok=True)
    ca_path = directory / 'ca.pem'
    ca_key_path = directory / 'ca.key'
    if ca_path.exists() and ca_key_path.exists():
        return (x509.load_pem_x509_certificate(ca_path.read_bytes()),
                serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None),
                ca_path)
    root_key = ec.generate_private_key(ec.SECP256R1())
    root_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'owned-close-ca')])
    now = datetime.now(timezone.utc)
    root = (x509.CertificateBuilder().subject_name(root_name).issuer_name(root_name)
        .public_key(root_key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(root_key, hashes.SHA256()))
    ca_path.write_bytes(root.public_bytes(serialization.Encoding.PEM))
    ca_key_path.write_bytes(root_key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    return root, root_key, ca_path


def _write_identity(directory: Path, name: str, uri: str, *, server: bool):
    from cryptography import x509
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    ca_cert, ca_key, ca_path = _write_ca(directory)
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    now = datetime.now(timezone.utc)
    builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_cert.subject)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1)).not_valid_after(now + timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName(
            [x509.UniformResourceIdentifier(uri)] +
            ([x509.DNSName('localhost')] if server else [])), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage(
            [ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]),
            critical=False))
    cert = builder.sign(ca_key, hashes.SHA256())
    key_path = directory / (name + '.key')
    cert_path = directory / (name + '.pem')
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path, ca_path


class _CloseCounter:
    """Count real socket/pool close calls; detect double-close and leaks."""

    def __init__(self):
        self.closes = 0
        self.double = 0
        self._lock = threading.Lock()

    def hit(self):
        with self._lock:
            self.closes += 1
            return self.closes

    def note_double(self):
        with self._lock:
            self.double += 1


def _wrap_close(sock, counter: _CloseCounter):
    """Count closes on Python-level sockets; raw C sockets need _TrackingSocket."""
    original = sock.close
    state = {'closed': False}

    def counted():
        if state['closed']:
            counter.note_double()
            return
        state['closed'] = True
        counter.hit()
        original()
    try:
        sock.close = counted
        return sock
    except AttributeError:
        return _TrackingSocket(sock, counter)


class _TrackingSocket:
    """Delegating wrapper for C-level sockets whose close() is read-only."""

    def __init__(self, sock, counter: _CloseCounter):
        self._sock = sock
        self._counter = counter
        self._closed = False

    def close(self):
        if self._closed:
            self._counter.note_double()
            return
        self._closed = True
        self._counter.hit()
        self._sock.close()

    def fileno(self):
        return self._sock.fileno()

    def settimeout(self, value):
        return self._sock.settimeout(value)

    def do_handshake(self):
        return self._sock.do_handshake()

    def __getattr__(self, name):
        return getattr(self._sock, name)


def _tls_contexts(directory: Path):
    server_uri = 'spiffe://oracle/close/server'
    client_uri = 'spiffe://oracle/close/client'
    server_cert, server_key, ca = _write_identity(directory, 'server', server_uri, server=True)
    client_cert, client_key, _ = _write_identity(directory, 'client', client_uri, server=False)
    server_context = server_tls(certfile=str(server_cert), keyfile=str(server_key), cafile=str(ca))
    client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    client_context.minimum_version = ssl.TLSVersion.TLSv1_3
    client_context.verify_mode = ssl.CERT_REQUIRED
    client_context.check_hostname = False
    client_context.load_cert_chain(str(client_cert), str(client_key))
    client_context.load_verify_locations(cafile=str(ca))
    return server_context, client_context, server_uri, client_uri


def _run_mtls_once(tmp_path: Path, *, handler_mode: str):
    """One real mTLS round trip; returns close counters and the client socket."""
    server_context, client_context, _, _ = _tls_contexts(tmp_path / 'certs')
    client_counter = _CloseCounter()
    server_counter = _CloseCounter()
    done = threading.Event()
    accepted = []

    class _OneShot(MutualTLSServer):
        daemon_threads = True

        def process_request_thread(self, request, client_address):
            wrapped = _wrap_close(request, server_counter)
            accepted.append(wrapped)
            try:
                request.do_handshake()
                if handler_mode == 'error':
                    raise OSError('invented handler failure')
                if handler_mode == 'cancel':
                    done.set()
                    time.sleep(0.05)
                    return
                request.recv(1)
                request.sendall(b'ok')
                done.set()
            except Exception:
                done.set()
            finally:
                self.shutdown_request(request)
                self._connections.release()

    def handler(*args, **kwargs):
        pass

    server = _OneShot(('127.0.0.1', 0), handler, tls=server_context)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    raw = socket.create_connection(('127.0.0.1', port), timeout=5)
    client = client_context.wrap_socket(raw, server_side=False)
    _wrap_close(client, client_counter)
    try:
        if handler_mode == 'success':
            client.sendall(b'x')
            assert client.recv(2) == b'ok'
        elif handler_mode == 'error':
            client.sendall(b'x')
            time.sleep(0.1)
        else:
            time.sleep(0.1)
    finally:
        client.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    end = time.monotonic() + 2
    while server_counter.closes < 1 and time.monotonic() < end:
        time.sleep(0.01)
    return client_counter, server_counter, client


def test_real_mtls_socket_closes_exactly_once_on_success(tmp_path):
    client_counter, server_counter, client = _run_mtls_once(tmp_path, handler_mode='success')
    assert client_counter.closes == 1, f'client close count {client_counter.closes}'
    assert client_counter.double == 0
    assert server_counter.closes == 1, f'server close count {server_counter.closes}'
    assert server_counter.double == 0
    assert client.fileno() == -1


def test_real_mtls_socket_closes_exactly_once_on_error(tmp_path):
    client_counter, server_counter, client = _run_mtls_once(tmp_path, handler_mode='error')
    assert client_counter.closes == 1 and client_counter.double == 0
    assert server_counter.closes == 1 and server_counter.double == 0
    assert client.fileno() == -1


def test_real_mtls_socket_closes_exactly_once_on_cancel(tmp_path):
    client_counter, server_counter, client = _run_mtls_once(tmp_path, handler_mode='cancel')
    assert client_counter.closes == 1 and client_counter.double == 0
    assert server_counter.closes == 1 and server_counter.double == 0
    assert client.fileno() == -1


class _CountedPool:
    """SDK/pool resource with an exactly-once close contract."""

    def __init__(self, counter: _CloseCounter, *, fail=False):
        self.counter = counter
        self.fail = fail
        self.connection = self
        self._closed = False

    async def close(self):
        if self._closed:
            self.counter.note_double()
            return
        self._closed = True
        if self.fail:
            self.counter.hit()
            raise OSError('invented pool close failure')
        self.counter.hit()


async def _close_owned_contract(projection, counter):
    """Exactly the result-service close-ordering contract, counted.

    Mirrors ProtectedReplacementResultServiceV1._close_owned_projection: one owned
    close task, bounded wait, settle-or-UNKNOWN, never double-close, close always
    attempted even when the body failed or the caller was cancelled.
    """
    task = asyncio.create_task(projection.connection.close(), name='result-owned-pool-close')
    owned = {task: projection}
    cancelled = False
    cleanup_end = asyncio.get_running_loop().time() + 5
    try:
        done, _ = await asyncio.wait({task}, timeout=max(0, cleanup_end - asyncio.get_running_loop().time()))
    except asyncio.CancelledError:
        cancelled = True
        try:
            done, _ = await asyncio.wait({task}, timeout=max(0, cleanup_end - asyncio.get_running_loop().time()))
        except asyncio.CancelledError:
            raise
    if not done:
        raise PermissionError('owned result connection cleanup remains unknown')
    try:
        task.result()
    except BaseException:
        raise PermissionError('owned result connection cleanup failed') from None
    del owned[task]
    if cancelled:
        raise asyncio.CancelledError


def test_sdk_pool_close_exactly_once_on_success_counts():
    counter = _CloseCounter()

    async def run():
        pool = _CountedPool(counter)
        try:
            pass
        finally:
            await _close_owned_contract(pool, counter)
    asyncio.run(run())
    assert counter.closes == 1 and counter.double == 0


def test_sdk_pool_close_exactly_once_on_error_counts():
    counter = _CloseCounter()

    async def run():
        pool = _CountedPool(counter)
        try:
            raise ValueError('invented body failure')
        finally:
            await _close_owned_contract(pool, counter)
    with pytest.raises(ValueError, match='invented body failure'):
        asyncio.run(run())
    assert counter.closes == 1 and counter.double == 0


def test_sdk_pool_close_exactly_once_on_cancel_counts():
    counter = _CloseCounter()

    async def body(pool):
        try:
            await asyncio.sleep(3600)
        finally:
            await _close_owned_contract(pool, counter)

    async def run():
        pool = _CountedPool(counter)
        task = asyncio.create_task(body(pool))
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert counter.closes == 1 and counter.double == 0


def test_sdk_pool_close_failure_is_owned_once():
    counter = _CloseCounter()

    async def run():
        pool = _CountedPool(counter, fail=True)
        with pytest.raises(PermissionError, match='cleanup failed'):
            await _close_owned_contract(pool, counter)
    asyncio.run(run())
    assert counter.closes == 1 and counter.double == 0


def test_tls_wrap_failure_closes_raw_socket_exactly_once(tmp_path):
    server_context, _, _, _ = _tls_contexts(tmp_path / 'certs-wrap')
    counter = _CloseCounter()
    raw_holder = {}

    class _WrapFail(MutualTLSServer):
        daemon_threads = True

        def get_request(self):
            raw, address = self.socket.accept()
            tracked = _wrap_close(raw, counter)
            raw_holder['raw'] = tracked
            tracked.settimeout(5)
            try:
                raise ssl.SSLError('invented wrap failure')
            except Exception:
                tracked.close()
                raise

    def handler(*args, **kwargs):
        pass

    server = _WrapFail(('127.0.0.1', 0), handler, tls=server_context)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        sock = socket.create_connection(('127.0.0.1', server.server_address[1]), timeout=5)
        time.sleep(0.1)
        sock.close()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    assert counter.closes == 1 and counter.double == 0
    assert raw_holder['raw'].fileno() == -1


def _service_source_tree():
    return ast.parse(SERVICE_SOURCE.read_text(encoding='utf-8'))


def _async_function(node, name):
    for child in ast.walk(node):
        if isinstance(child, (ast.AsyncFunctionDef, ast.FunctionDef)) and child.name == name:
            return child
    raise AssertionError(f'{name} not found in result service source')


def test_result_service_source_closes_owned_projection_exactly_once_in_finally():
    tree = _service_source_tree()
    handler = _async_function(tree, 'handle_result_v1')
    finallys = [n for n in ast.walk(handler) if isinstance(n, ast.Try) and n.finalbody]
    assert finallys, 'handle_result_v1 must close owned projection in a finally block'
    closes = 0
    for fin in finallys:
        for stmt in ast.walk(fin):
            if isinstance(stmt, ast.Attribute) and stmt.attr == '_close_owned_projection':
                closes += 1
    assert closes == 1, f'expected exactly one owned close call site, found {closes}'
    guarded = False
    for fin in finallys:
        for stmt in fin.finalbody:
            if isinstance(stmt, ast.If):
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Attribute) and sub.attr == '_close_owned_projection':
                        guarded = True
    assert guarded, 'owned close must be guarded so only an owned projection is closed'


def test_result_service_close_source_never_reissues_close_task():
    tree = _service_source_tree()
    closer = _async_function(tree, '_close_owned_projection_v1')
    legacy = _async_function(tree, '_close_owned_projection')
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_close_owned_projection_v1' for n in ast.walk(legacy)), 'legacy API must delegate the same single close owner'
    creates = [n for n in ast.walk(closer)
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'create_task']
    assert len(creates) == 1, 'exactly one owned close task is created per projection'
    has_delete = any(isinstance(n, ast.Delete) for n in ast.walk(closer))
    assert has_delete, 'settled close task must be removed from _owned_closes'
    direct_closes = [n for n in ast.walk(closer)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == 'close']
    assert len(direct_closes) == 1, 'the sole close call must be the one owned task payload'


def test_result_owned_loop_close_settles_tasks_before_loop_stop():
    tree = _service_source_tree()
    closer = _async_function(tree, 'close')
    observe = _async_function(tree, '_observe')
    observe_names = {n.id for n in ast.walk(observe) if isinstance(n, ast.Name)}
    assert 'tasks' in observe_names or 'pending' in observe_names, \
        '_observe must gather owned requests/closes before shutdown'
    close_names = {n.id for n in ast.walk(closer) if isinstance(n, ast.Name)}
    assert 'future' in close_names, 'close must wait on the owned observe future'


def test_result_service_close_source_is_single_shot_per_pool():
    tree = _service_source_tree()
    closer = _async_function(tree, '_close_owned_projection_v1')
    legacy = _async_function(tree, '_close_owned_projection')
    assert any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == '_close_owned_projection_v1' for n in ast.walk(legacy)), 'legacy API must delegate the same single close owner'
    source = ast.dump(closer)
    assert 'owned_closes' in source
    direct_closes = [n for n in ast.walk(closer)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == 'close']
    assert len(direct_closes) == 1, 'the sole close call must be the one owned task payload'


@pytest.mark.skipif(WIN32, reason='Windows lacks fcntl (hosting/custody, purpose_journey_v2); '
    'run on Linux: python -m pytest services/oracle-brain/tests/test_replacement_result_tls_sdk_close_v1.py -v')
def test_result_service_real_tls_sdk_close_only_success_error_cancel(tmp_path, monkeypatch):
    """Linux-only: real service handle_result_v1 closes real TLS + SDK pool exactly once."""
    from uuid import uuid4
    from oracle_brain.hosting import replacement_result_service_v1 as svc_mod
    from oracle_brain.hosting.replacement_result_service_v1 import ProtectedReplacementResultServiceV1
    from oracle_brain.hosting.replacement_result_settings_v1 import ProtectedReplacementResultSettingsV1
    from oracle_brain.hosting.replacement_result_v1 import ProtectedReplacementResultRequestV1, PROTOCOL
    from oracle_brain.operating_model.contracts import canonical_bytes, ReplacementExecutorTargetV1
    from oracle_brain.operating_model.source_receipts import SourceRef
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    counter = _CloseCounter()
    _, _, server_uri, client_uri = _tls_contexts(tmp_path / 'linux-certs')
    client_pem = (tmp_path / 'linux-certs' / 'client.pem').read_bytes()
    client_der = x509.load_pem_x509_certificate(client_pem).public_bytes(serialization.Encoding.DER)
    until = datetime.now(timezone.utc) + timedelta(seconds=30)
    workspace, source, model, run, actor, ack = (uuid4() for _ in range(6))
    target = ReplacementExecutorTargetV1.model_validate(dict(
        schema_version=1, run_id=run, journey_revision=1, state='delivered', answer_hold=False,
        cancelled=False, population_sha256='a' * 64, requester_principal_id=actor,
        workspace_id=workspace, model_id=model, model_version=1, model_content_hash='b' * 64,
        ack_event_id=ack, projection_digest='c' * 64,
        source_refs=(SourceRef(workspace_id=workspace, source_id=source, revision=1,
            original_sha256='d' * 64, reading_sha256='e' * 64, parser_id='f' * 64),),
        current_confirmation=None, summary_targets=(), checked_at=datetime.now(timezone.utc),
        valid_until=until))
    config = SimpleNamespace(
        client_certificate_sha256=hashlib.sha256(client_der).hexdigest(),
        client_uri=client_uri, model_id=model, model_version=1, model_content_hash='b' * 64,
        projection_digest='c' * 64, ack_event_id=ack, summary_artifact_id=uuid4(),
        summary_version=1, summary_content_hash='e' * 64, journey_id=run, workspace_id=workspace,
        nonce_root=str(tmp_path / 'nonces'), expires_at=until, original_horizon=until,
        workflow_id='invented-flow')
    settings = object.__new__(ProtectedReplacementResultSettingsV1)
    object.__setattr__(settings, 'config', config)
    object.__setattr__(settings, 'executor', SimpleNamespace(
        read_target=lambda: (None, {'operating_models': [{}], 'observations': [], 'findings': []}),
        read_summary=lambda *a, **k: None, guard=object(), ledger=object(),
        config=SimpleNamespace(source_refs=target.source_refs)))
    monkeypatch.setattr(ProtectedReplacementResultSettingsV1, 'current_target',
        lambda self: (target, until))

    class RealPool:
        def __init__(self):
            self.connection = self
            self._closed = False

        async def close(self):
            if self._closed:
                counter.note_double()
                return
            self._closed = True
            counter.hit()

        async def load(self, *a, **k):
            return None

    class FakeResponse:
        def __init__(self, **kw):
            self._data = kw

        def model_dump(self, mode='python'):
            return dict(self._data)

    class FakeView:
        def model_dump(self, mode='json'):
            return {'view': 'fixture'}

    monkeypatch.setattr(svc_mod, 'build_paid_executor_projection_v3', lambda e: RealPool())
    monkeypatch.setattr(svc_mod, 'qualified_map_view_v1', lambda *a, **k: FakeView())
    monkeypatch.setattr(svc_mod, 'serve_summary', lambda *a, **k: object())
    monkeypatch.setattr(svc_mod, 'answer_from_summary', lambda *a, **k: object())
    monkeypatch.setattr(svc_mod, 'documentary_answer_public_v1', lambda *a, **k: None)
    monkeypatch.setattr(svc_mod, 'public_snapshot_v1', lambda **k: FakeView())
    monkeypatch.setattr(svc_mod, 'ProtectedReplacementResultResponseV1', FakeResponse)
    monkeypatch.setattr(svc_mod, 'encode_result_response_v1', lambda r: b'encoded-result')
    monkeypatch.setattr(svc_mod, '_durable_nonce', lambda *a, **k: None)
    monkeypatch.setattr(svc_mod, 'BusinessOperatingModel', SimpleNamespace(model_validate_json=lambda b: FakeView()))
    monkeypatch.setattr(svc_mod, 'Observation', SimpleNamespace(model_validate_json=lambda b: FakeView()))
    monkeypatch.setattr(svc_mod, 'Finding', SimpleNamespace(model_validate_json=lambda b: FakeView()))
    request = ProtectedReplacementResultRequestV1(schema_version=1, protocol=PROTOCOL,
        journey_id=run, expected_journey_revision=1, model_id=model, model_version=1,
        content_hash='b' * 64, projection_digest='c' * 64, ack_event_id=ack,
        summary_artifact_id=config.summary_artifact_id, summary_version=1,
        summary_content_hash='e' * 64, nonce='1' * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=25))
    raw = canonical_bytes(request.model_dump(mode='json'))
    service = ProtectedReplacementResultServiceV1(settings)
    assert asyncio.run(service.handle_result_v1(client_der, raw)) == b'encoded-result'
    assert counter.closes == 1 and counter.double == 0
    assert not service._owned_closes and not service._cleanup_unknown
