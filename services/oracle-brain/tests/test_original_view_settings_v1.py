"""Viewer-specific protected consumers and private synthetic custody."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
from types import SimpleNamespace
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.artifact_storage import FileBlobStore, OriginalObjectRefV1, ReservationOriginalObjectRefV1, _write_private_at
from oracle_brain.hosting.original_view_settings_v1 import (
    OriginalViewerConfigV1, OriginalViewerAppointmentV1, OriginalViewerPeerProfileV1,
    load_original_viewer_settings_v1,
)
from test_hosting_boundary import certificates, WORKER

PDF = b'%PDF-1.7\nInvented viewer framing only\n%%EOF\n'


def pinned(path, data):
    path.write_bytes(data); path.chmod(0o600)
    return dict(path=str(path), sha256=hashlib.sha256(data).hexdigest())


def configured_viewer(tmp_path, certificates, *, data=PDF, original=None, sql_target=None, owner='oracle2_owner',
                      login='invented_viewer', principal=None, workspace=None, runtime='a'*64, registry='b'*64,
                      config_changes=None, appointment_changes=None, peer_changes=None, storage_root=None):
    now = datetime.now(timezone.utc)
    root = Path(storage_root) if storage_root else tmp_path / 'private-originals'
    if not storage_root: root.mkdir(mode=0o700)
    principal = principal or uuid4(); workspace = workspace or uuid4()
    issuer, reviewer = uuid4(), uuid4()
    if original is None:
        source, reservation = uuid4(), uuid4()
        ref = ReservationOriginalObjectRefV1(OriginalObjectRefV1(workspace, source, 1,
            hashlib.sha256(data).hexdigest(), len(data), 'application/pdf', 'c'*64), reservation)
        store = FileBlobStore._from_provisioned_original_root(root, (root.stat().st_dev, root.stat().st_ino, root.stat().st_uid))
        store._put_original_bytes(ref, data)
        observation = dict(schema_version=1, purpose='original-intake-byte-custody-v1', reservation_id=str(reservation),
            source_id=str(source), workspace_id=str(workspace), revision=1, private_object_key=ref.key,
            original_sha256=ref.original_sha256, byte_count=ref.byte_count, storage_profile_hash='c'*64)
        raw = canonical_bytes(observation)
        _write_private_at(root, ['intake-observations', str(reservation), 'custody.json'], raw,
                          expected_root=(root.stat().st_dev, root.stat().st_ino, root.stat().st_uid))
        original = dict(source_id=str(source), revision=1, original_sha256=ref.original_sha256,
            byte_count=ref.byte_count, media_type='application/pdf', reservation_id=str(reservation),
            custody_seal_sha256=hashlib.sha256(raw).hexdigest())
    dbca = pinned(tmp_path/'db-ca', (certificates/'ca.pem').read_bytes())
    target = sql_target or dict(host='127.0.0.1', port='5432', dbname='invented_viewer_db', user=login,
                               password='invented-only', sslmode='verify-full', sslrootcert=dbca['path'])
    target = dict(target, sslrootcert=dbca['path'])
    import psycopg
    db = pinned(tmp_path/'db-url', psycopg.conninfo.make_conninfo(**target).encode())
    info = root.stat(); until = now+timedelta(seconds=60)
    config = dict(schema_version=1, purpose='original-revision-view-v1', principal_id=str(principal), workspace_id=str(workspace),
        expected_session_role=login, expected_owner_role=owner, runtime_hash=runtime, registry_hash=registry,
        database_url=db, database_ca=dbca, storage_root=str(root), storage_device=info.st_dev, storage_inode=info.st_ino,
        storage_uid=info.st_uid, storage_profile_hash='c'*64, sources=[original],
        original_horizon=until.isoformat(), expires_at=until.isoformat())
    config.update(config_changes or {})
    c = OriginalViewerConfigV1.model_validate_json(json.dumps(config))
    ci = pinned(tmp_path/'viewer-config', canonical_bytes(c.model_dump(mode='json')))
    der = x509.load_pem_x509_certificate((certificates/'worker.pem').read_bytes()).public_bytes(Encoding.DER)
    peer = dict(schema_version=1, purpose='original-revision-view-peer-v1', config_sha256=ci['sha256'],
        principal_id=str(principal), workspace_id=str(workspace), client_uri=WORKER,
        client_certificate_sha256=hashlib.sha256(der).hexdigest(), listen_host='127.0.0.1', listen_port=0,
        server_hostname='localhost', server_certificate=pinned(tmp_path/'server-cert', (certificates/'server.pem').read_bytes()),
        server_key=pinned(tmp_path/'server-key', (certificates/'server.key').read_bytes()),
        client_ca=pinned(tmp_path/'client-ca', (certificates/'ca.pem').read_bytes()),
        valid_from=(now-timedelta(seconds=1)).isoformat(), expires_at=until.isoformat(), original_horizon=until.isoformat())
    peer.update(peer_changes or {})
    p = OriginalViewerPeerProfileV1.model_validate_json(json.dumps(peer))
    pi = pinned(tmp_path/'viewer-peer', canonical_bytes(p.model_dump(mode='json')))
    appointment = dict(schema_version=1, purpose='original-revision-view-v1', config_sha256=ci['sha256'], peer_profile_sha256=pi['sha256'],
        principal_id=str(principal), workspace_id=str(workspace), expected_session_role=login, runtime_hash=runtime,
        registry_hash=registry, issuer_actor=str(issuer), reviewer_actor=str(reviewer),
        valid_from=(now-timedelta(seconds=1)).isoformat(), expires_at=until.isoformat(), original_horizon=until.isoformat())
    appointment.update(appointment_changes or {})
    a = OriginalViewerAppointmentV1.model_validate_json(json.dumps(appointment))
    ai = pinned(tmp_path/'viewer-appointment', canonical_bytes(a.model_dump(mode='json')))
    args = (ci['path'],ci['sha256'],ai['path'],ai['sha256'],pi['path'],pi['sha256'])
    settings = load_original_viewer_settings_v1(*args, issuer_actor=issuer, reviewer_actor=reviewer)
    return SimpleNamespace(settings=settings, args=args, issuer=issuer, reviewer=reviewer, root=root, data=data, target=target)


def test_separate_viewer_consumers_bind_external_pins_and_custody(tmp_path, certificates):
    f=configured_viewer(tmp_path, certificates)
    assert f.settings.current()>datetime.now(timezone.utc)
    assert f.settings.config.sources[0].byte_count==len(f.data)
    with pytest.raises(PermissionError):
        load_original_viewer_settings_v1(*f.args, issuer_actor=uuid4(), reviewer_actor=f.reviewer)


@pytest.mark.parametrize('name', ['config_input','appointment_input','peer_input'])
def test_any_startup_pin_drift_denied(tmp_path, certificates, name):
    f=configured_viewer(tmp_path,certificates)
    path=Path(getattr(f.settings,name).path);path.write_bytes(path.read_bytes()+b' ')
    with pytest.raises(PermissionError): f.settings.current()


@pytest.mark.parametrize('changes', [dict(expected_owner_role='invented_viewer'), dict(sources=[]),
    dict(runtime_hash='bad'),dict(unknown=True)])
def test_invalid_closed_config_refused(tmp_path, certificates, changes):
    with pytest.raises(ValueError): configured_viewer(tmp_path,certificates,config_changes=changes)


@pytest.mark.parametrize('changes', [dict(expected_session_role='another'),dict(config_sha256='0'*64),
    dict(peer_profile_sha256='0'*64),dict(expires_at=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat())])
def test_appointment_mismatch_or_expiry_refused(tmp_path, certificates, changes):
    with pytest.raises((ValueError,PermissionError)): configured_viewer(tmp_path,certificates,appointment_changes=changes)


@pytest.mark.parametrize('changes', [dict(server_hostname='wrong.example'),dict(config_sha256='0'*64),
    dict(principal_id=str(uuid4()))])
def test_peer_identity_mismatch_denied(tmp_path, certificates, changes):
    with pytest.raises(PermissionError): configured_viewer(tmp_path,certificates,peer_changes=changes)


def test_root_custody_and_permissions_remain_current(tmp_path,certificates):
    f=configured_viewer(tmp_path,certificates);f.root.chmod(0o755)
    with pytest.raises(PermissionError): f.settings.current()
