"""Invented external appointment fixtures, never actual issuer/runtime authority."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest

from oracle_brain.operating_model.contracts import canonical_bytes, digest
from oracle_brain.operating_model.semantic_registry_v3 import (
    CurrentSemanticAdmissionsV3, SemanticRegistryAppointmentV3)


@pytest.fixture
def registry(tmp_path):
    now = datetime.now(timezone.utc)
    start, end = now - timedelta(minutes=1), now + timedelta(minutes=5)
    appointment = SemanticRegistryAppointmentV3(uuid4(), 'a' * 64, 'candidate-compiler',
        uuid4(), uuid4(), start, end)
    scope = appointment.scope()
    item = dict(schema_version=3, admission_hash='b' * 64, revoked=False,
                valid_from=start.isoformat(), expires_at=end.isoformat(), **scope)
    item['record_seal'] = digest(item)
    row = dict(schema_version=3, revoked=False, valid_from=start.isoformat(),
               expires_at=end.isoformat(), admissions=[item], **scope)
    path = tmp_path / 'external-registry.json'
    def publish(value=row, raw=None):
        data = canonical_bytes(value) if raw is None else raw
        path.write_bytes(data); path.chmod(0o600)
        return CurrentSemanticAdmissionsV3(path, hashlib.sha256(data).hexdigest(), appointment=appointment)
    return now, appointment, row, path, publish


def test_current_metadata_only_and_no_auto_adoption(registry):
    now, _, row, path, publish = registry
    consumer = publish()
    assert consumer.current(now) == frozenset({'b' * 64})
    row['admissions'][0]['admission_hash'] = 'c' * 64
    publish()
    with pytest.raises(PermissionError, match='hash changed'): consumer.current(now)
    assert not any('private' in k or 'candidate' in k for k in row)


def test_actual_current_trust_horizon_rereads_same_pinned_registry(registry):
    now, appointment, row, path, publish = registry
    item = row['admissions'][0]
    item['expires_at'] = (now + timedelta(seconds=20)).isoformat()
    item['record_seal'] = digest({k: v for k, v in item.items() if k != 'record_seal'})
    consumer = publish()
    assert consumer.valid_until(now) == now + timedelta(seconds=20)
    assert consumer.valid_until(now) < appointment.expires_at
    with pytest.raises(PermissionError): consumer.valid_until(now + timedelta(seconds=21))
    row['revoked'] = True
    publish()
    with pytest.raises(PermissionError, match='hash changed'): consumer.valid_until(now)


@pytest.mark.parametrize('field,value', [
    ('schema_version', 2), ('schema_version', True), ('revoked', True),
    ('qualification_purpose', 'other'), ('workspace_id', str(uuid4())),
    ('runtime_hash', 'd' * 64), ('compiler_profile', 'executor'),
    ('issuer_actor', str(uuid4())), ('reviewer_actor', str(uuid4())),
    ('expires_at', '2000-01-01T00:00:00+00:00'), ('private_path', '/invented/private')])
def test_wrong_external_registry_scope_rejected(registry, field, value):
    now, _, row, _, publish = registry
    row[field] = value
    with pytest.raises(PermissionError): publish().current(now)


@pytest.mark.parametrize('kind', ['schema2', 'duplicate', 'revoked', 'seal', 'expired', 'issuer', 'raw'])
def test_wrong_record_rejected(registry, kind):
    now, _, row, _, publish = registry
    item = row['admissions'][0]
    if kind == 'schema2': item['schema_version'] = 2
    elif kind == 'duplicate': row['admissions'].append(item.copy())
    elif kind == 'revoked': item['revoked'] = True
    elif kind == 'seal': item['record_seal'] = 'e' * 64
    elif kind == 'expired': item['expires_at'] = (now - timedelta(seconds=1)).isoformat()
    elif kind == 'issuer': item['issuer_actor'] = str(uuid4())
    else: item['raw_candidate'] = 'never allowed'
    if kind != 'seal': item['record_seal'] = digest({k: v for k, v in item.items() if k != 'record_seal'})
    with pytest.raises(PermissionError): publish().current(now)


@pytest.mark.parametrize('raw', [b'{bad', b'{"schema_version":3,"schema_version":3}', b'{"x":NaN}'])
def test_strict_json(registry, raw):
    now, _, _, _, publish = registry
    with pytest.raises(PermissionError): publish(raw=raw).current(now)


def test_appointment_and_files_fail_closed(registry):
    now, appointment, _, path, publish = registry
    consumer = publish()
    with pytest.raises(PermissionError): consumer.current(now + timedelta(minutes=6))
    with pytest.raises(PermissionError): consumer.current(now.replace(tzinfo=None))
    consumer.appointment = replace(appointment, issuer_actor=appointment.reviewer_actor)
    with pytest.raises(PermissionError): consumer.current(now)
    consumer = publish()
    path.chmod(0o644)
    with pytest.raises(PermissionError): consumer.current(now)
    path.chmod(0o600)
    linked = path.with_name('hardlink'); os.link(path, linked)
    with pytest.raises(PermissionError): consumer.current(now)
    linked.unlink()
    moved = path.with_name('moved'); path.rename(moved); path.symlink_to(moved)
    with pytest.raises(OSError): consumer.current(now)
    path.unlink(); moved.unlink()
    with pytest.raises(FileNotFoundError): consumer.current(now)
