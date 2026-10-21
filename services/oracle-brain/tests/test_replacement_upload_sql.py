"""Actual upload mTLS→intake→owned TLS SQL→private immutable original bytes."""
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
from pathlib import Path
import shutil
import threading
import time
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
import psycopg
from psycopg.types.json import Jsonb
import pytest

from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.artifact_storage import FileBlobStore
from oracle_brain.hosting.replacement_request_service_v1 import RequesterPeerProfileV1
from oracle_brain.hosting.replacement_upload_service_v1 import protected_replacement_upload_server_v1, METADATA_HEADER
from test_hosting_boundary import certificates, WORKER
from test_replacement_source_intake_sql import requester, call
from test_replacement_requester_sql import admin_url, owned_admin, configured_settings
from test_replacement_upload_service_v1 import send_upload, header
from test_replacement_request_service_v1 import client


def actual_pdf():
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument.new(); page = pdf.new_page(160, 90); page.gen_content()
    output = io.BytesIO(); pdf.save(output); page.close(); pdf.close()
    return output.getvalue()


def peer_profile(tmp_path, settings, certificates):
    tls = tmp_path / 'listener-tls'; tls.mkdir(mode=0o700)
    def pin(name):
        output = tls / name; shutil.copyfile(certificates / name, output); output.chmod(0o600)
        return str(output), hashlib.sha256(output.read_bytes()).hexdigest()
    cert, cert_hash = pin('server.pem'); key, key_hash = pin('server.key'); ca, ca_hash = pin('ca.pem')
    der = x509.load_pem_x509_certificate((certificates / 'worker.pem').read_bytes()).public_bytes(Encoding.DER)
    c = settings.config; now = datetime.now(timezone.utc)
    body = dict(schema_version=1, purpose='replacement-requester-peer-v1',
        intake_config_sha256=settings.config_sha256, intake_appointment_sha256=settings.appointment_sha256,
        principal_id=str(c.principal_id), workspace_id=str(c.workspace_id), runtime_hash=c.runtime_hash, registry_hash=c.registry_hash,
        client_uri=WORKER, client_certificate_sha256=hashlib.sha256(der).hexdigest(),
        listen_host='127.0.0.1', listen_port=0, server_hostname='localhost',
        server_certificate_file=cert, server_certificate_sha256=cert_hash, server_key_file=key, server_key_sha256=key_hash,
        client_ca_file=ca, client_ca_sha256=ca_hash,
        issuer_actor=str(settings.expected_issuer_actor), reviewer_actor=str(settings.expected_reviewer_actor),
        valid_from=(now - timedelta(seconds=1)).isoformat(), expires_at=(now + timedelta(seconds=25)).isoformat(),
        original_horizon=c.original_horizon.isoformat())
    profile = RequesterPeerProfileV1.model_validate_json(json.dumps(body))
    raw = canonical_bytes(profile.model_dump(mode='json')); path = tmp_path / 'actual-peer-profile'; path.write_bytes(raw); path.chmod(0o600)
    return path, hashlib.sha256(raw).hexdigest()


@pytest.fixture
def actual_upload(requester, tmp_path, certificates):
    x = requester; settings = configured_settings(tmp_path, x)
    path, seal = peer_profile(tmp_path, settings, certificates)
    server = protected_replacement_upload_server_v1(settings, path, seal)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
    thread.start()
    try: yield x | dict(settings=settings, server=server, data=actual_pdf())
    finally:
        server.shutdown(); server.server_close(); thread.join(2)
        assert not thread.is_alive() and not server._active and server.socket.fileno() == -1


def metadata(x, *, data=None, seconds=20, **changes):
    data = x['data'] if data is None else data
    body = dict(schema_version=1, source_id=None, expected_head=0, idempotency_key=str(uuid4()), filename='invented-valid.pdf',
        original_sha256=hashlib.sha256(data).hexdigest(), byte_count=len(data),
        caller_deadline=(datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat())
    return body | changes


def upload(x, certificates, value, data=None):
    return send_upload(x['server'], certificates, x['data'] if data is None else data, value)


def rows(x):
    with owned_admin(x) as connection:
        originals = connection.execute('SELECT source_id,revision,original_sha256,byte_count,private_object_key FROM oracle2.source_original_revisions WHERE workspace_id=%s ORDER BY revision', (x['workspace'],)).fetchall()
        reservations = connection.execute('SELECT reservation_id,finalized_at FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s', (x['workspace'],)).fetchall()
        source_grants = connection.execute("SELECT count(*) FROM oracle2.appointments WHERE workspace_id=%s AND scope LIKE 'source-read:%%'", (x['workspace'],)).fetchone()[0]
        qualified = connection.execute('SELECT count(*) FROM oracle2.operating_model_source_receipts WHERE workspace_id=%s', (x['workspace'],)).fetchone()[0]
        models = connection.execute('SELECT count(*) FROM oracle2.artifact_manifests WHERE workspace_id=%s', (x['workspace'],)).fetchone()[0]
    return dict(originals=originals, reservations=reservations, source_grants=source_grants, qualified=qualified, models=models)


def test_actual_tls_upload_matches_original_sql_private_bytes_and_same_key_replay(actual_upload, certificates):
    x = actual_upload; value = metadata(x)
    status, body, _ = upload(x, certificates, value)
    assert status == 200
    result = json.loads(body)
    assert result['state'] == 'awaiting_original_reading' and result['qualifiedSourceRef'] is None
    current = rows(x); original = current['originals'][0]
    assert (str(original[0]), original[1], original[2], original[3]) == (result['sourceId'], result['revision'], result['originalSha256'], result['byteCount'])
    private = Path(x['settings'].config.storage_root) / original[4]
    assert private.read_bytes() == x['data'] and hashlib.sha256(private.read_bytes()).hexdigest() == original[2]
    before = (private.stat().st_ino, private.stat().st_mtime_ns)
    assert upload(x, certificates, value)[:2] == (200, body)
    assert (private.stat().st_ino, private.stat().st_mtime_ns) == before
    again = rows(x)
    assert len(again['originals']) == len(again['reservations']) == 1
    assert again['source_grants'] == again['qualified'] == again['models'] == 0


def test_actual_idempotency_refuses_changed_bytes_and_changed_deadline(actual_upload, certificates):
    x = actual_upload; value = metadata(x)
    assert upload(x, certificates, value)[0] == 200
    changed = x['data'][:-1] + bytes([x['data'][-1] ^ 1])
    value_changed = dict(value, original_sha256=hashlib.sha256(changed).hexdigest())
    assert upload(x, certificates, value_changed, changed)[0] == 503
    renewed = dict(value, caller_deadline=(datetime.fromisoformat(value['caller_deadline']) + timedelta(seconds=1)).isoformat())
    assert upload(x, certificates, renewed)[0] == 503
    current = rows(x); assert len(current['originals']) == len(current['reservations']) == 1
    assert current['reservations'][0][1] is not None
    assert (Path(x['settings'].config.storage_root) / current['originals'][0][4]).read_bytes() == x['data']


def test_actual_replacement_cas_preserves_historical_original_and_denies_stale_head(actual_upload, certificates):
    x = actual_upload
    status, raw, _ = upload(x, certificates, metadata(x)); assert status == 200
    source = json.loads(raw)['sourceId']
    with owned_admin(x) as connection:
        connection.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',
            (uuid4(), x['workspace'], x['actor'], 'source-read:' + source, x['owner'], x['root'], x['until']))
    changed = x['data'] + b'\n'
    value = metadata(x, data=changed, source_id=source, expected_head=1)
    status, raw, _ = upload(x, certificates, value, changed)
    assert status == 200 and json.loads(raw)['revision'] == 2
    assert upload(x, certificates, metadata(x, source_id=source, expected_head=1))[0] == 503
    current = rows(x); assert len(current['originals']) == len(current['reservations']) == 2
    assert [(Path(x['settings'].config.storage_root) / row[4]).read_bytes() for row in current['originals']] == [x['data'], changed]


def test_actual_revoked_intake_scope_denies_upload_before_private_write(actual_upload, certificates):
    x = actual_upload
    with owned_admin(x) as connection:
        connection.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s', (x['leaf'],))
    assert upload(x, certificates, metadata(x))[0] == 503
    assert rows(x)['originals'] == [] and rows(x)['reservations'] == []
    assert not (Path(x['settings'].config.storage_root) / 'source-originals').exists()


def test_actual_sql_reservation_survives_late_write_without_finalize(actual_upload, certificates, monkeypatch):
    x = actual_upload; value = metadata(x, seconds=1.3)
    original = FileBlobStore._put_original_bytes; deadline = datetime.fromisoformat(value['caller_deadline'])
    def delayed(store, ref, data):
        outcome = original(store, ref, data)
        time.sleep(max(0, (deadline - datetime.now(timezone.utc)).total_seconds()) + .02)
        return outcome
    monkeypatch.setattr(FileBlobStore, '_put_original_bytes', delayed)
    assert upload(x, certificates, value)[0] == 503
    current = rows(x)
    assert current['originals'] == [] and len(current['reservations']) == 1 and current['reservations'][0][1] is None
    stored = list((Path(x['settings'].config.storage_root) / 'source-originals').rglob('*'))
    assert [p.read_bytes() for p in stored if p.is_file()] == [x['data']]
    assert len(list(Path(x['settings'].config.storage_root).rglob('*.orphan.json'))) == 1


def test_actual_lost_upload_reply_is_observed_without_another_upload(actual_upload, certificates, monkeypatch):
    x = actual_upload; value = metadata(x); entered = threading.Event(); release = threading.Event()
    original = FileBlobStore._put_original_bytes
    def held(store, ref, data):
        outcome = original(store, ref, data); entered.set(); assert release.wait(2); return outcome
    monkeypatch.setattr(FileBlobStore, '_put_original_bytes', held)
    connection = client(x['server'], certificates)
    try:
        connection.request('POST', '/v1/replacement/upload', body=x['data'],
            headers={'Content-Type': 'application/pdf', METADATA_HEADER: header(value)})
        assert entered.wait(1)
    finally:
        connection.close(); release.set()
    # This is bounded observation of this exact admitted handler, not a retry.
    with x['server']._active_condition:
        assert x['server']._active_condition.wait_for(lambda: not x['server']._active, timeout=3)
    # App reconciliation requires a separately existing source-read scope; a
    # lost reply cannot mint that scope. Only the owned fixture admin observes.
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        call(x, 'reconcile_source_intake_v1', value['idempotency_key'])
    current = rows(x); assert len(current['originals']) == len(current['reservations']) == 1
    assert current['reservations'][0][1] is not None
    assert (Path(x['settings'].config.storage_root) / current['originals'][0][4]).read_bytes() == x['data']
