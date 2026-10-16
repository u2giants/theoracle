"""Strict historical-reader metadata getter DTOs; no SQL, body or private path.

The current historical-reader metadata getter returns a closed metadata record.
These pure contracts pin its exact shape: paid transport carries every paid seal
or none (native UTF8), horizons stay finite and ordered, and versions are exact
integers. They never attest model semantics or grant authority.
"""
from datetime import datetime, timezone, timedelta
import json
from uuid import UUID

import pytest

from oracle_brain.operating_model.original_source_authority_v1 import (
    OriginalReadingCommitMetadataV1,
    OriginalResponseRegistrationV1,
)

NOW = datetime(2026, 10, 16, 12, 0, 0, tzinfo=timezone.utc)


def raw_ref():
    return dict(schema_version=1, workspace_id=str(UUID(int=1)), source_id=str(UUID(int=20)),
                revision=1, original_sha256='a' * 64, byte_count=7, media_type='application/pdf',
                filename='invented.pdf', custody_locator_seal_sha256='b' * 64)


PAID_KEYS = ('native_phase_commit_hash', 'native_dispatch_id', 'native_job_hash', 'request_hash',
             'permission_hash', 'raw_wire_hash', 'model_content_hash', 'native_custody_receipt_hash',
             'model_id', 'pricing_quote_hash', 'current_sql_receipt_hash', 'observer_witness_hash')


def paid_values():
    vals = dict(native_phase_commit_hash='1' * 64, native_dispatch_id=str(UUID(int=30)),
                native_job_hash='2' * 64, request_hash='3' * 64, permission_hash='4' * 64,
                raw_wire_hash='5' * 64, model_content_hash='6' * 64, native_custody_receipt_hash='7' * 64,
                model_id='openai/gpt-6.1-sol', pricing_quote_hash='8' * 64,
                current_sql_receipt_hash='9' * 64, observer_witness_hash='0' * 64)
    return vals


def base(transport='paid-native-v1'):
    value = dict(
        schema_version=1, reading_commit_hash='c' * 64, transport=transport, raw_ref=raw_ref(),
        reader_principal_id=str(UUID(int=2)), reader_session_role='reader-login',
        reader_runtime_hash='d' * 64, reader_source_registry_hash='e' * 64,
        reader_population_id=str(UUID(int=40)), reader_operation_registry_hash='f' * 64,
        original_root_hash='1' * 64, population_digest='2' * 64, allocation_hash='3' * 64,
        original_horizon=(NOW + timedelta(minutes=30)).isoformat(),
        context_hash='4' * 64, reading_sha256='5' * 64, parser_id='6' * 64,
        view_manifest_hash='7' * 64, locator_map_hash='8' * 64, reading_body_hash='9' * 64,
        response_committed_at=NOW.isoformat(),
        authorized_commit_at=(NOW + timedelta(seconds=1)).isoformat(),
        checked_at=(NOW + timedelta(seconds=2)).isoformat(),
        valid_until=(NOW + timedelta(minutes=10)).isoformat(),
        native_phase_commit_hash=None, native_dispatch_id=None, native_job_hash=None,
        request_hash=None, permission_hash=None, raw_wire_hash=None, model_content_hash=None,
        native_custody_receipt_hash=None, model_id=None, pricing_quote_hash=None,
        current_sql_receipt_hash=None, observer_witness_hash=None,
    )
    if transport == 'paid-native-v1':
        value.update(paid_values())
    return value


def test_paid_native_metadata_accepts_complete_paid_seals():
    parsed = OriginalReadingCommitMetadataV1.model_validate_json(json.dumps(base('paid-native-v1')))
    assert parsed.transport == 'paid-native-v1' and parsed.model_id == 'openai/gpt-6.1-sol'
    assert all(getattr(parsed, k) is not None for k in PAID_KEYS)


def test_native_utf8_metadata_requires_all_paid_fields_null():
    parsed = OriginalReadingCommitMetadataV1.model_validate_json(json.dumps(base('native-utf8-byte-roundtrip-v1')))
    assert parsed.transport == 'native-utf8-byte-roundtrip-v1'
    assert all(getattr(parsed, k) is None for k in PAID_KEYS)


@pytest.mark.parametrize('key', ['native_job_hash', 'request_hash', 'raw_wire_hash', 'model_id'])
def test_paid_metadata_rejects_missing_paid_seal(key):
    value = base('paid-native-v1')
    value[key] = None
    with pytest.raises(ValueError):
        OriginalReadingCommitMetadataV1.model_validate_json(json.dumps(value))


@pytest.mark.parametrize('key', ['native_job_hash', 'model_id'])
def test_native_utf8_metadata_rejects_present_paid_seal(key):
    value = base('native-utf8-byte-roundtrip-v1')
    value[key] = '2' * 64 if key != 'model_id' else 'openai/gpt-6.1-sol'
    with pytest.raises(ValueError):
        OriginalReadingCommitMetadataV1.model_validate_json(json.dumps(value))


def test_metadata_rejects_valid_until_beyond_original_horizon():
    value = base('paid-native-v1')
    value['valid_until'] = (NOW + timedelta(hours=2)).isoformat()
    value['original_horizon'] = (NOW + timedelta(minutes=30)).isoformat()
    with pytest.raises(ValueError):
        OriginalReadingCommitMetadataV1.model_validate_json(json.dumps(value))


def test_metadata_rejects_disordered_commit_review_clocks():
    value = base('paid-native-v1')
    value['response_committed_at'] = (NOW + timedelta(minutes=5)).isoformat()
    value['authorized_commit_at'] = (NOW + timedelta(seconds=1)).isoformat()
    with pytest.raises(ValueError):
        OriginalReadingCommitMetadataV1.model_validate_json(json.dumps(value))


@pytest.mark.parametrize('bad', [True, 1.0, '1'])
def test_metadata_schema_version_is_exact_integer(bad):
    value = base('paid-native-v1')
    value['schema_version'] = bad
    with pytest.raises(ValueError):
        OriginalReadingCommitMetadataV1.model_validate_json(json.dumps(value))


def test_registration_accepts_finite_window():
    reg = OriginalResponseRegistrationV1.model_validate_json(json.dumps(dict(
        commit_sha256='a' * 64, principal_id=str(UUID(int=2)), session_role='reader-login',
        runtime_hash='d' * 64, population_id=str(UUID(int=40)), operation_registry_hash='f' * 64,
        checked_at=NOW.isoformat(), valid_until=(NOW + timedelta(seconds=5)).isoformat())))
    assert reg.session_role == 'reader-login'


@pytest.mark.parametrize('delta', [0, -1])
def test_registration_rejects_nonfinite_window(delta):
    with pytest.raises(ValueError):
        OriginalResponseRegistrationV1.model_validate_json(json.dumps(dict(
            commit_sha256='a' * 64, principal_id=str(UUID(int=2)), session_role='reader-login',
            runtime_hash='d' * 64, population_id=str(UUID(int=40)), operation_registry_hash='f' * 64,
            checked_at=NOW.isoformat(), valid_until=(NOW + timedelta(seconds=delta)).isoformat())))
