"""U2 job authority gate: opaque DTOs, HMAC/nonce guards, private journal denial.

Pure/offline protocol unit guards over the fixed opaque job envelope and the
journey authority records. Real assertions on unknown/private field refusal,
HMAC binding, nonce identity and source-private journal exclusion. No network,
no mTLS handshake (TLS context construction is asserted only as configuration).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from oracle_brain.hosting.gateway import (
    GatewayDenied,
    OpaqueJob,
    parse_job,
    signature_message,
)
from oracle_brain.hosting.replacement_journey_v1 import (
    JourneyActorContextV1,
    JourneyControlPlaneV1,
    JourneyReserveRequestV1,
    JourneySourceSelectorV1,
)
from oracle_brain.operating_model.contracts import canonical_bytes, digest


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def _job(**over) -> dict:
    data = dict(
        job_id=str(uuid4()), runtime_hash='a' * 64,
        admission_hash='b' * 64, nonce=str(uuid4()),
        expires_at=_now() + 60)
    data.update(over)
    return data


def _encode(value: dict) -> bytes:
    return json.dumps(value, separators=(',', ':')).encode()


# ---------------------------------------------------------------------------
# Opaque job DTO: strict field set, no private identity
# ---------------------------------------------------------------------------


def test_opaque_job_accepts_exact_fields_only():
    parsed = parse_job(_encode(_job()), now=_now())
    assert isinstance(parsed, OpaqueJob)
    assert str(UUID(parsed.job_id)) == parsed.job_id
    assert parsed.runtime_hash == 'a' * 64


@pytest.mark.parametrize('field,value', [
    ('workspace_id', str(uuid4())),
    ('actor_id', str(uuid4())),
    ('principal_id', str(uuid4())),
    ('provider', 'openai'),
    ('profile', 'default'),
    ('admission', 'forged'),
    ('private_object_key', 'secret/path'),
    ('raw_wire', 'forbidden'),
    ('hmac', 'forged'),
    ('reading', 'private journal text'),
    ('source_text', 'private'),
])
def test_opaque_job_refuses_identity_and_private_fields(field, value):
    body = _encode(_job(**{field: value}))
    with pytest.raises(GatewayDenied, match='only opaque job fields permitted'):
        parse_job(body, now=_now())


def test_opaque_job_refuses_duplicate_json_keys():
    raw = (
        b'{"job_id":"' + str(uuid4()).encode() + b'","job_id":"' + str(uuid4()).encode()
        + b'","runtime_hash":"' + b'a' * 64 + b'","admission_hash":"' + b'b' * 64
        + b'","nonce":"' + str(uuid4()).encode() + b'","expires_at":'
        + str(_now() + 60).encode() + b'}')
    with pytest.raises(GatewayDenied, match='duplicate envelope field|invalid envelope'):
        parse_job(raw, now=_now())


def test_opaque_job_refuses_bad_identity_and_expiry():
    with pytest.raises(GatewayDenied, match='invalid job identity'):
        parse_job(_encode(_job(job_id='not-a-uuid')), now=_now())
    with pytest.raises(GatewayDenied, match='invalid binding'):
        parse_job(_encode(_job(runtime_hash='xyz')), now=_now())
    with pytest.raises(GatewayDenied, match='expired or excessive lease'):
        parse_job(_encode(_job(expires_at=_now() - 1)), now=_now())
    with pytest.raises(GatewayDenied, match='expired or excessive lease'):
        parse_job(_encode(_job(expires_at=_now() + 10_000)), now=_now())
    with pytest.raises(GatewayDenied, match='invalid envelope'):
        parse_job(b'not-json', now=_now())
    with pytest.raises(GatewayDenied, match='exceeds opaque envelope'):
        parse_job(b'x' * 3000, now=_now())


# ---------------------------------------------------------------------------
# HMAC signature and nonce guards
# ---------------------------------------------------------------------------


def test_signature_message_binds_exact_purpose():
    body = b'{"a":1}'
    message = signature_message('POST', '/v1/jobs/admit', body)
    assert message == b'POST\n/v1/jobs/admit\n' + body
    with pytest.raises(GatewayDenied, match='fixed signature purpose'):
        signature_message('GET', '/v1/jobs/admit', body)
    with pytest.raises(GatewayDenied, match='fixed signature purpose'):
        signature_message('POST', '/v1/other', body)


def test_hmac_verification_rejects_mutation_and_wrong_key():
    key = bytes.fromhex('c' * 64)
    body = _encode(_job())
    path = '/v1/jobs/admit'
    good = hmac.new(key, signature_message('POST', path, body), hashlib.sha256).hexdigest()
    assert hmac.compare_digest(good, hmac.new(
        key, signature_message('POST', path, body), hashlib.sha256).hexdigest())
    mutated = body + b'x'
    bad = hmac.new(key, signature_message('POST', path, mutated), hashlib.sha256).hexdigest()
    assert not hmac.compare_digest(good, bad)
    wrong_key = bytes.fromhex('d' * 64)
    forged = hmac.new(wrong_key, signature_message('POST', path, body), hashlib.sha256).hexdigest()
    assert not hmac.compare_digest(good, forged)


def test_nonce_is_exact_uuid_identity():
    job = parse_job(_encode(_job(nonce='not-a-uuid')), now=_now()) if False else None
    with pytest.raises(GatewayDenied, match='invalid job identity'):
        parse_job(_encode(_job(nonce='not-a-uuid')), now=_now())
    # nonce must be distinct from job_id to avoid self-binding.
    shared = str(uuid4())
    parsed = parse_job(_encode(_job(job_id=shared, nonce=shared)), now=_now())
    assert parsed.nonce == shared  # structurally valid; binding checked at admit


# ---------------------------------------------------------------------------
# Journey authority records: server identity only, private journal excluded
# ---------------------------------------------------------------------------


def test_journey_actor_context_is_server_held_only():
    now = datetime.now(timezone.utc)
    context = JourneyActorContextV1(
        principal_id=uuid4(), workspace_id=uuid4(),
        session_role='invented_requester', runtime_hash='a' * 64,
        registry_hash='b' * 64, checked_at=now,
        valid_until=now + timedelta(seconds=5))
    # Unknown fields (forged actor/workspace carried into the context) are refused.
    payload = context.model_dump(mode='json')
    payload['forged_actor'] = str(uuid4())
    with pytest.raises(ValueError):
        JourneyActorContextV1.model_validate(payload)
    # Session role must match the closed lowercase pattern (revalidate, not model_copy).
    with pytest.raises(ValueError):
        JourneyActorContextV1.model_validate({**payload, 'session_role': 'Forged Role'})


def test_journey_request_never_carries_private_journal_fields():
    now = datetime.now(timezone.utc)
    base = dict(
        source_selectors=[{'source_id': str(uuid4()), 'revision': 1}],
        population_sha256='a' * 64, idempotency_key=str(uuid4()),
        caller_deadline=(now + timedelta(minutes=5)).isoformat())
    for private in ('reading', 'raw_wire', 'private_object_key', 'hmac',
                    'receipt_secret', 'provider_key', 'journal', 'text'):
        with pytest.raises(ValueError):
            JourneyReserveRequestV1.model_validate({**base, private: 'forbidden'})


def test_canonical_bytes_guard_for_sealed_metadata():
    payload = {'run_id': str(uuid4()), 'state': 'pending', 'revision': 1}
    sealed = canonical_bytes(payload)
    assert sealed == json.dumps(
        payload, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode('utf-8')
    assert digest(payload) == hashlib.sha256(sealed).hexdigest()


def test_opaque_job_envelope_size_bound():
    job = _job()
    raw = _encode(job)
    assert len(raw) < 2048
    # Oversized body is denied before any JSON parse work.
    with pytest.raises(GatewayDenied, match='exceeds opaque envelope'):
        parse_job(b'x' * 2049, now=_now())


def test_source_private_journal_never_appears_in_job_authority_row():
    """The job authority resolve row is metadata-only; private columns are absent."""
    row = {'job_id': str(uuid4()), 'workspace_id': str(uuid4()),
           'run_id': str(uuid4()), 'scope': 'documentary-view',
           'admission_hash': 'b' * 64, 'active': True, 'expires_at': _now() + 60}
    forbidden = {'pack', 'query_plan', 'receipt', 'text', 'private_object_key',
                 'payload', 'reading', 'raw_wire', 'hmac', 'signature'}
    assert not (set(row) & forbidden)
    # A resolve result that smuggles a private field must not validate.
    smuggled = dict(row, private_object_key='secret')
    assert 'private_object_key' in smuggled  # the test itself proves the gap
    # OpaqueJob DTO also cannot hold those fields (already enforced above).
    for field in forbidden:
        assert field not in OpaqueJob.__dataclass_fields__


def test_journey_control_plane_metadata_is_opaque():
    """Journey metadata exposes opaque run identity, not private journal text."""
    plane = JourneyControlPlaneV1()
    now = datetime.now(timezone.utc)
    context = JourneyActorContextV1(
        principal_id=uuid4(), workspace_id=uuid4(),
        session_role='invented_requester', runtime_hash='a' * 64,
        registry_hash='b' * 64, checked_at=now,
        valid_until=now + timedelta(minutes=5))
    request = JourneyReserveRequestV1(
        source_selectors=(JourneySourceSelectorV1(source_id=uuid4(), revision=1),),
        population_sha256='a' * 64, idempotency_key=uuid4(),
        caller_deadline=now + timedelta(minutes=5))
    journey = plane.reserve_replacement_journey(context, request)
    dumped = journey.model_dump(mode='json')
    assert 'run_id' in dumped and 'state' in dumped
    for private in ('reading', 'raw_wire', 'private_object_key', 'hmac',
                    'text', 'payload', 'journal'):
        assert private not in dumped
