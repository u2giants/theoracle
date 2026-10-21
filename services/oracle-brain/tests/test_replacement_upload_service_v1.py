"""Actual local mTLS/HTTP and private bytes, real intake factory, recording SQL."""
import base64
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import http.client
import json
from pathlib import Path
from types import SimpleNamespace
import threading
import time
from uuid import uuid4

import pytest

from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1
from oracle_brain.hosting.replacement_upload_service_v1 import (
    protected_replacement_upload_server_v1, parse_upload_metadata_v1, METADATA_HEADER,
)
from test_hosting_boundary import certificates
from test_replacement_request_service_v1 import profile_fixture, client

PDF = b'%PDF-1.7\nInvented custody-only bytes\n%%EOF\n'


def metadata(f, data=PDF, seconds=5, **changes):
    body = dict(schema_version=1, source_id=None, expected_head=0, idempotency_key=str(uuid4()),
        filename='invented.pdf', original_sha256=hashlib.sha256(data).hexdigest(), byte_count=len(data),
        caller_deadline=(datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat())
    return body | changes


def header(body):
    return base64.urlsafe_b64encode(canonical_bytes(body)).decode('ascii').rstrip('=')


def recording_intake(f, monkeypatch):
    f.source = uuid4(); f.reservation = uuid4(); f.intake_calls = []; f.deadlines = []
    f.finalize_error = False; f.finalize_close_error = False; f.visible = False
    f.finalize_commit = None
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, arguments=None):
            f.events.append((query, arguments)); self.query = query
            if query.startswith('SELECT oracle2.reserve_source_revision_v1'):
                f.intake_calls.append('reserve'); f.reserve_intake = json.loads(arguments[1]); f.deadlines.append(f.reserve_intake['caller_deadline'])
            elif query.startswith('SELECT oracle2.finalize_source_revision_v1'):
                f.intake_calls.append('finalize'); f.finalize_args = json.loads(arguments[2]); f.deadlines.append(f.finalize_args['caller_deadline'])
                if f.finalize_error: raise PermissionError('invented revoked finalization')
        def fetchall(self): return [(f.s.config.expected_owner_role, True)] * 2
        def fetchone(self):
            if 'SESSION_USER::text' in self.query: return f.login
            if self.query.startswith('SELECT oracle2.reserve_source_revision_v1'):
                revision = 1
                return (dict(schema_version=1, context=f.context, reservation=dict(reservation_id=str(f.reservation),
                    source_id=str(f.source), revision=revision, expires_at=f.s.config.expires_at.isoformat(),
                    private_object_key=f'source-originals/{f.s.config.workspace_id}/{f.source}/{revision}/{f.reservation}')),)
            if self.query.startswith('SELECT oracle2.finalize_source_revision_v1'):
                return (dict(schema_version=1, context=f.context, snapshot=dict(sourceId=str(f.source), revision=1,
                    originalSha256=f.finalize_args['original_sha256'], byteCount=f.finalize_args['byte_count'],
                    mediaType='application/pdf', filename=f.reserve_intake['filename'], state='awaiting_original_reading', qualifiedSourceRef=None)),)
            raise AssertionError('unexpected fixture query')
    class Connection:
        def __init__(self): self.cur = Cursor()
        info = property(lambda self: f.actual)
        pgconn = property(lambda self: SimpleNamespace(ssl_in_use=True))
        def __enter__(self): return self
        def __exit__(self, *args):
            if self.cur.query.startswith('SELECT oracle2.finalize_source_revision_v1') and f.finalize_close_error:
                raise RuntimeError('invented uncertain SQL close')
        def cursor(self): return self.cur
        def commit(self):
            f.events.append('commit')
            if self.cur.query.startswith('SELECT oracle2.finalize_source_revision_v1'):
                f.visible = True
                if f.finalize_commit: f.finalize_commit()
    def connect(*args, **kwargs):
        f.connects += 1
        assert 1 <= kwargs['connect_timeout'] <= 5
        return Connection()
    monkeypatch.setattr('psycopg.connect', connect)


@contextmanager
def running_upload(tmp_path, monkeypatch, certificates):
    f, profile, seal, tls = profile_fixture(tmp_path, monkeypatch, certificates)
    recording_intake(f, monkeypatch)
    server = protected_replacement_upload_server_v1(f.s, profile, seal)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    try: yield f, profile, tls, server
    finally:
        server.shutdown(); server.server_close(); thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno() == -1


def send_upload(server, certificates, data, body, *, identity='worker', route='/v1/replacement/upload', extra=None):
    connection = client(server, certificates, identity=identity)
    try:
        headers = {'Content-Type': 'application/pdf', METADATA_HEADER: header(body)}
        headers.update(extra or {})
        connection.request('POST', route, body=data, headers=headers)
        response = connection.getresponse()
        return response.status, response.read(), dict(response.getheaders())
    finally: connection.close()


def private_bytes(f):
    return list((Path(f.s.config.storage_root) / 'source-originals').rglob('*')) if (Path(f.s.config.storage_root) / 'source-originals').exists() else []


def test_actual_upload_realfactory_private_bytes_and_original_deadline(tmp_path, monkeypatch, certificates):
    with running_upload(tmp_path, monkeypatch, certificates) as (f, profile, tls, server):
        body = metadata(f)
        status, raw, headers = send_upload(server, certificates, PDF, body)
        assert status == 200 and raw == canonical_bytes(json.loads(raw))
        result = json.loads(raw)
        assert set(result) == {'sourceId', 'revision', 'originalSha256', 'byteCount', 'mediaType', 'filename', 'state', 'qualifiedSourceRef'}
        assert result['state'] == 'awaiting_original_reading' and result['qualifiedSourceRef'] is None
        assert result['originalSha256'] == hashlib.sha256(PDF).hexdigest() and result['byteCount'] == len(PDF)
        assert headers['Cache-Control'] == 'no-store'
        assert f.intake_calls == ['reserve', 'finalize'] and f.connects == 2 and f.visible
        assert f.deadlines == [body['caller_deadline']] * 2
        objects = [p for p in private_bytes(f) if p.is_file()]
        assert len(objects) == 1 and objects[0].read_bytes() == PDF
        custody = list((Path(f.s.config.storage_root) / 'intake-observations').rglob('custody.json'))
        assert len(custody) == 1
        value = json.loads(custody[0].read_bytes())
        assert value['original_sha256'] == result['originalSha256'] and value['byte_count'] == len(PDF)


@pytest.mark.parametrize('attack', ['identity', 'hash', 'count', 'signature', 'encoding', 'chunked',
    'media', 'path', 'deadline', 'missing-source', 'stale-source-shape', 'filename', 'duplicate-metadata'])
def test_actual_upload_refuses_before_any_reservation(tmp_path, monkeypatch, certificates, attack):
    with running_upload(tmp_path, monkeypatch, certificates) as (f, profile, tls, server):
        body = metadata(f); data = PDF; extra = {}; route = '/v1/replacement/upload'
        if attack == 'identity': body['actor_id'] = str(uuid4())
        elif attack == 'hash': body['original_sha256'] = 'f' * 64
        elif attack == 'count': body['byte_count'] += 1
        elif attack == 'signature': data = b'PK invent'; body = metadata(f, data)
        elif attack == 'encoding': extra['Content-Encoding'] = 'gzip'
        elif attack == 'chunked': extra['Transfer-Encoding'] = 'chunked'
        elif attack == 'media': extra['Content-Type'] = 'application/json'
        elif attack == 'path': route = '/v1/replacement/control'
        elif attack == 'deadline': body = metadata(f, seconds=31)
        elif attack == 'missing-source': body['expected_head'] = 1
        elif attack == 'stale-source-shape': body['source_id'] = str(uuid4())
        elif attack == 'filename': body['filename'] = '../original.pdf'
        if attack == 'duplicate-metadata':
            connection = client(server, certificates)
            try:
                connection.putrequest('POST', route)
                connection.putheader('Content-Type', 'application/pdf'); connection.putheader('Content-Length', str(len(data)))
                connection.putheader(METADATA_HEADER, header(body)); connection.putheader(METADATA_HEADER, header(body))
                connection.endheaders(data); response = connection.getresponse(); status = response.status; response.read()
            finally: connection.close()
        else: status = send_upload(server, certificates, data, body, route=route, extra=extra)[0]
        assert status == 503 and f.connects == 0 and f.intake_calls == [] and private_bytes(f) == []


@pytest.mark.parametrize('encoding', ['padded', 'noncanonical', 'duplicate', 'invalid', 'boolean-version', 'nonfinite'])
def test_upload_metadata_is_closed_canonical_before_factory(tmp_path, monkeypatch, certificates, encoding):
    f, _, _, _ = profile_fixture(tmp_path, monkeypatch, certificates)
    value = metadata(f); raw = canonical_bytes(value)
    if encoding == 'padded': encoded = header(value) + '='
    elif encoding == 'invalid': encoded = '!private'
    else:
        if encoding == 'noncanonical': raw = b' ' + raw
        elif encoding == 'duplicate': raw = raw[:-1] + b',"byte_count":1}'
        elif encoding == 'boolean-version': value['schema_version'] = True; raw = canonical_bytes(value)
        elif encoding == 'nonfinite': raw = b'{"n":NaN}'
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip('=')
    with pytest.raises(PermissionError): parse_upload_metadata_v1(encoded)
    assert f.connects == 0


@pytest.mark.parametrize('attack', ['finalize-revoked', 'finalize-uncertain-close', 'profile-after-sql'])
def test_original_bytes_and_exact_orphan_survive_unaccepted_finalize(tmp_path, monkeypatch, certificates, attack):
    with running_upload(tmp_path, monkeypatch, certificates) as (f, profile, tls, server):
        if attack == 'finalize-revoked': f.finalize_error = True
        elif attack == 'finalize-uncertain-close': f.finalize_close_error = True
        else: f.finalize_commit = lambda: profile.write_bytes(b'changed after SQL')
        status, raw, _ = send_upload(server, certificates, PDF, metadata(f))
        assert status == 503 and raw == b'' and f.intake_calls == ['reserve', 'finalize']
        assert [p.read_bytes() for p in private_bytes(f) if p.is_file()] == [PDF]
        if attack != 'profile-after-sql':
            orphans = list(Path(f.s.config.storage_root).rglob('*.orphan.json'))
            assert len(orphans) == 1
            assert json.loads(orphans[0].read_bytes())['original_sha256'] == hashlib.sha256(PDF).hexdigest()


def test_synchronous_write_may_finish_late_but_no_readback_or_finalize(tmp_path, monkeypatch, certificates):
    with running_upload(tmp_path, monkeypatch, certificates) as (f, profile, tls, server):
        value = metadata(f, seconds=1.3); deadline = datetime.fromisoformat(value['caller_deadline'])
        original = FileBlobStore._put_original_bytes; reads = []
        def delayed(store, ref, data):
            result = original(store, ref, data)
            time.sleep(max(0, (deadline - datetime.now(timezone.utc)).total_seconds()) + .02)
            return result
        monkeypatch.setattr(FileBlobStore, '_put_original_bytes', delayed)
        original_read = FileBlobStore._read_original_bytes
        def read(store, ref): reads.append(ref); return original_read(store, ref)
        monkeypatch.setattr(FileBlobStore, '_read_original_bytes', read)
        status, raw, _ = send_upload(server, certificates, PDF, value)
        assert status == 503 and raw == b'' and f.intake_calls == ['reserve'] and reads == [] and not f.visible
        assert [p.read_bytes() for p in private_bytes(f) if p.is_file()] == [PDF]
        assert len(list(Path(f.s.config.storage_root).rglob('*.orphan.json'))) == 1


def test_single_upload_slot_refuses_second_request_without_queue_or_second_sql(tmp_path, monkeypatch, certificates):
    with running_upload(tmp_path, monkeypatch, certificates) as (f, profile, tls, server):
        entered = threading.Event(); release = threading.Event(); replies = []
        original = FileBlobStore._put_original_bytes
        def held(store, ref, data):
            entered.set(); assert release.wait(2); return original(store, ref, data)
        monkeypatch.setattr(FileBlobStore, '_put_original_bytes', held)
        first = threading.Thread(target=lambda: replies.append(send_upload(server, certificates, PDF, metadata(f))))
        first.start()
        try:
            assert entered.wait(1)
            assert send_upload(server, certificates, PDF, metadata(f))[0] == 503
            assert f.intake_calls == ['reserve']
        finally: release.set(); first.join(2)
        assert not first.is_alive() and replies[0][0] == 200 and f.intake_calls == ['reserve', 'finalize']


def test_legacy_factory_default_preserves_existing_unmodified_api(tmp_path, monkeypatch, certificates):
    f, _, _, _ = profile_fixture(tmp_path, monkeypatch, certificates)
    recording_intake(f, monkeypatch)
    result = OriginalIntakeFactoryV1(f.s).intake_pdf_v1(source_id=None, expected_head=0, idempotency_key=uuid4(),
        filename='invented.pdf', original_sha256=hashlib.sha256(PDF).hexdigest(), data=PDF)
    assert result.state == 'awaiting_original_reading'
    assert f.deadlines == [f.s.config.expires_at.isoformat()] * 2


def test_wrong_actual_peer_refuses_without_waiting_for_original_body(tmp_path, monkeypatch, certificates):
    with running_upload(tmp_path, monkeypatch, certificates) as (f, profile, tls, server):
        connection = client(server, certificates, identity='other')
        try:
            connection.putrequest('POST', '/v1/replacement/upload')
            connection.putheader('Content-Type', 'application/pdf'); connection.putheader('Content-Length', str(len(PDF)))
            connection.putheader(METADATA_HEADER, header(metadata(f))); connection.endheaders()
            # Deliberately send NO body: peer refusal must precede any body read.
            response = connection.getresponse()
            assert response.status == 503 and response.read() == b''
        finally: connection.close()
        assert f.connects == 0 and private_bytes(f) == []


@pytest.mark.parametrize('length', ['0', str(25 * 1024 * 1024 + 1)])
def test_unbounded_pdf_framing_denies_without_body_or_sql(tmp_path, monkeypatch, certificates, length):
    with running_upload(tmp_path, monkeypatch, certificates) as (f, profile, tls, server):
        connection = client(server, certificates)
        try:
            connection.putrequest('POST', '/v1/replacement/upload')
            connection.putheader('Content-Type', 'application/pdf'); connection.putheader('Content-Length', length)
            connection.putheader(METADATA_HEADER, header(metadata(f))); connection.endheaders()
            response = connection.getresponse()
            assert response.status == 503 and response.read() == b''
        finally: connection.close()
        assert f.connects == 0 and private_bytes(f) == []
