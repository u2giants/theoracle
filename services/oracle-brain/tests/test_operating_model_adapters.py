import json
import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from oracle_brain.operating_model.provider_adapter import AdmittedProvider, Budget, Pricing
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest




@pytest.fixture
def test_database():
    admin_url = os.environ['ORACLE2_TEST_ADMIN_URL']
    target = psycopg.conninfo.conninfo_to_dict(admin_url)
    if target.get('host') not in {'127.0.0.1','localhost'} or not target.get('dbname','').startswith('oracle_operating_model_test_'):
        raise PermissionError('adapter tests require exact session-owned synthetic Postgres')
    name = f'oracle_operating_model_test_{uuid4().hex[:16]}'
    base = psycopg.conninfo.conninfo_to_dict(admin_url)
    base['dbname'] = 'postgres'
    with psycopg.connect(**base, autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    db_url = psycopg.conninfo.make_conninfo(**{**base, 'dbname': name})
    root = Path(__file__).parents[1]
    with psycopg.connect(db_url) as conn:
        for migration in ('001_foundation.sql', '002_pilot.sql', '003_pilot_authority_notes.sql', '004_workflow_integrity.sql'):
            conn.execute((root / 'sql' / migration).read_text())
    yield db_url
    with psycopg.connect(**base, autocommit=True) as conn:
        conn.execute('SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s', (name,))
        conn.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(name)))


@pytest.fixture
def adapter(test_database):
    now = datetime.now(timezone.utc)
    request = ProcessingRequest(provider='openai', account='synthetic', endpoint='https://api.openai.com/v1',
                                data_classes=frozenset({'synthetic'}), purpose='source-extraction', terms_hash='a' * 64)
    approval = ProcessingApproval(**request.model_dump(), expires_at=now + timedelta(hours=1), register_ref='test')
    pricing = Pricing(provider='openai', model='gpt-4o-mini', input_per_million_usd=Decimal('0.10'),
                      output_per_million_usd=Decimal('0.10'), max_output_tokens=100,
                      expires_at=now + timedelta(hours=1), admitted_register_hash='b' * 64)
    calls = []
    def sender(**kwargs):
        calls.append(kwargs)
        return {'ok': True}, Decimal('0.000001')
    return AdmittedProvider(request=request, approvals=[approval], pricing=pricing,
                            budget=Budget(test_database), sender=sender,admitted_register_hash='b'*64,remaining_daily_allowance=lambda:Decimal('25')), calls


def ids():
    return uuid4(), uuid4(), uuid4()


def test_budget_rejects_unadmitted_purpose_and_cost(test_database):
    budget = Budget(test_database)
    w, a, b = ids()
    with pytest.raises(PermissionError):
        budget.reserve(workspace_id=w, artifact_id=a, batch_id=b, purpose='company-question', attempt=1, maximum=Decimal('.01'), pricing_hash='a'*64)
    with pytest.raises(PermissionError):
        budget.reserve(workspace_id=w, artifact_id=uuid4(), batch_id=b, purpose='report', attempt=1, maximum=Decimal('.01'), pricing_hash='a'*64)
    for amount in (Decimal('0'), Decimal('1.000001')):
        with pytest.raises(PermissionError):
            budget.reserve(workspace_id=w, artifact_id=uuid4(), batch_id=b, purpose='source-extraction', attempt=1, maximum=amount, pricing_hash='a'*64)


def test_replay_and_correction_require_failed_first_receipt(test_database,monkeypatch):
    budget = Budget(test_database)
    w, a, b = ids()
    with pytest.raises(PermissionError):
        budget.reserve(workspace_id=w, artifact_id=a, batch_id=b, purpose='source-extraction', attempt=2, maximum=Decimal('.01'), pricing_hash='a'*64)
    rid = budget.reserve(workspace_id=w, artifact_id=a, batch_id=b, purpose='source-extraction', attempt=1, maximum=Decimal('.01'), pricing_hash='a'*64)
    with pytest.raises(PermissionError):
        budget.reserve(workspace_id=w, artifact_id=a, batch_id=b, purpose='source-extraction', attempt=1, maximum=Decimal('.01'), pricing_hash='a'*64)
    budget.finish(rid, actual_usd=Decimal('.01'), failed=True, response_hash=None)
    with pytest.raises(PermissionError):
        budget.reserve(workspace_id=w,artifact_id=a,batch_id=b,purpose='source-extraction',attempt=2,maximum=Decimal('.01'),pricing_hash='a'*64)
    with pytest.raises(PermissionError):
        budget.diagnose(reservation_id=rid,actor_id=uuid4(),failure_kind='invalid_output',correction_hash='c'*64,diagnosis_hash='d'*64)
    from oracle_brain.authz import appoint_owner
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    owner,appointment=uuid4(),uuid4();key=Ed25519PrivateKey.generate()
    monkeypatch.setenv('ORACLE2_OWNER_PUBLIC_KEY',key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex())
    appoint_owner(test_database,workspace_id=w,owner_id=owner,appointed_by=uuid4(),appointment_id=appointment,owner_signature_hex=key.sign(f'oracle2-owner-appointment-v1:{w}:{owner}:{appointment}'.encode()).hex())
    budget.diagnose(reservation_id=rid,actor_id=owner,failure_kind='invalid_output',correction_hash='c'*64,diagnosis_hash='d'*64)
    assert budget.reserve(workspace_id=w, artifact_id=a, batch_id=b, purpose='source-extraction', attempt=2, maximum=Decimal('.01'), pricing_hash='a'*64,correction_hash='c'*64)

def rooted_budget(test_database, monkeypatch):
    from oracle_brain.authz import appoint_owner
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives import serialization
    budget=Budget(test_database); w,a,b=ids(); owner=uuid4(); appointment=uuid4(); key=Ed25519PrivateKey.generate()
    monkeypatch.setenv('ORACLE2_OWNER_PUBLIC_KEY',key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw).hex())
    appoint_owner(test_database,workspace_id=w,owner_id=owner,appointed_by=uuid4(),appointment_id=appointment,owner_signature_hex=key.sign(f'oracle2-owner-appointment-v1:{w}:{owner}:{appointment}'.encode()).hex())
    rid=budget.reserve(workspace_id=w,artifact_id=a,batch_id=b,purpose='source-extraction',attempt=1,maximum=Decimal('.01'),pricing_hash='a'*64); budget.finish(rid,actual_usd=Decimal('.01'),failed=True,response_hash=None)
    return budget,w,a,b,owner,rid

def test_rooted_quota_exhausted_diagnosis_denies_matching_retry(test_database,monkeypatch):
    budget,w,a,b,owner,rid=rooted_budget(test_database,monkeypatch); budget.diagnose(reservation_id=rid,actor_id=owner,failure_kind='quota_exhausted',correction_hash='c'*64,diagnosis_hash='d'*64)
    with pytest.raises(PermissionError): budget.reserve(workspace_id=w,artifact_id=a,batch_id=b,purpose='source-extraction',attempt=2,maximum=Decimal('.01'),pricing_hash='a'*64,correction_hash='c'*64)

def test_rooted_invalid_output_requires_matching_correction_hash(test_database,monkeypatch):
    budget,w,a,b,owner,rid=rooted_budget(test_database,monkeypatch)
    budget.diagnose(reservation_id=rid,actor_id=owner,failure_kind='invalid_output',correction_hash='c'*64,diagnosis_hash='d'*64)
    with pytest.raises(PermissionError): budget.reserve(workspace_id=w,artifact_id=a,batch_id=b,purpose='source-extraction',attempt=2,maximum=Decimal('.01'),pricing_hash='a'*64,correction_hash='wrong')
    assert budget.reserve(workspace_id=w,artifact_id=a,batch_id=b,purpose='source-extraction',attempt=2,maximum=Decimal('.01'),pricing_hash='a'*64,correction_hash='c'*64)
    with pytest.raises(PermissionError): budget.reserve(workspace_id=w,artifact_id=a,batch_id=b,purpose='source-extraction',attempt=3,maximum=Decimal('.01'),pricing_hash='a'*64,correction_hash='c'*64)

def test_rooted_diagnosis_is_immutable(test_database,monkeypatch):
    budget,w,a,b,owner,rid=rooted_budget(test_database,monkeypatch); budget.diagnose(reservation_id=rid,actor_id=owner,failure_kind='invalid_output',correction_hash='c'*64,diagnosis_hash='d'*64)
    with psycopg.connect(test_database) as conn:
        with pytest.raises(psycopg.errors.RaiseException): conn.execute("UPDATE oracle2.operating_dispatch_diagnoses SET failure_kind='quota_exhausted' WHERE reservation_id=%s",(rid,))


def test_batch_cap_rejects_sixth_one_dollar_reservation(test_database):
    budget = Budget(test_database); w, b = uuid4(), uuid4()
    for _ in range(5):
        budget.reserve(workspace_id=w, artifact_id=uuid4(), batch_id=b, purpose='source-extraction', attempt=1, maximum=Decimal('1'), pricing_hash='a'*64)
    with pytest.raises(PermissionError):
        budget.reserve(workspace_id=w, artifact_id=uuid4(), batch_id=b, purpose='source-extraction', attempt=1, maximum=Decimal('1'), pricing_hash='a'*64)


def test_expired_or_mismatched_admission_denies_before_sender(adapter):
    provider, calls = adapter
    for update in ({'purpose': 'report'}, {'endpoint': 'https://wrong.example'}, {'fallback': True},
                   {'expires_at': datetime.now(timezone.utc) - timedelta(seconds=1)}):
        changed = provider.request.model_copy(update={k: v for k, v in update.items() if k in {'purpose', 'endpoint', 'fallback'}})
        approvals = [provider.approvals[0].model_copy(update=update)] if 'expires_at' in update else provider.approvals
        denied = AdmittedProvider(request=changed, approvals=approvals, pricing=provider.pricing,
                                  budget=provider.budget, sender=provider.sender,admitted_register_hash='b'*64,remaining_daily_allowance=lambda:Decimal('25'))
        with pytest.raises(PermissionError):
            denied.extract(workspace_id=uuid4(), artifact_id=uuid4(), batch_id=uuid4(), purpose='source-extraction', attempt=1, input_tokens_upper_bound=1, messages=[])
    assert calls == []


def test_sender_receives_output_cap_and_tampering_is_rejected(adapter):
    provider, calls = adapter
    provider.extract(workspace_id=uuid4(), artifact_id=uuid4(), batch_id=uuid4(), purpose='source-extraction', attempt=1, input_tokens_upper_bound=2048, messages=[{'role': 'user'}])
    assert calls[0]['max_output_tokens'] == 100
    rid = provider.budget.reserve(workspace_id=uuid4(), artifact_id=uuid4(), batch_id=uuid4(), purpose='source-extraction', attempt=1, maximum=Decimal('.01'), pricing_hash='a'*64)
    provider.budget.finish(rid, actual_usd=Decimal('.001'), failed=False, response_hash='a'*64)
    with pytest.raises(ValueError, match='tampering'):
        provider.budget.finish(rid, actual_usd=Decimal('.002'), failed=False, response_hash='b'*64)


def test_actual_overrun_is_recorded_and_raises(adapter):
    provider, _ = adapter
    rid = provider.budget.reserve(workspace_id=uuid4(), artifact_id=uuid4(), batch_id=uuid4(), purpose='source-extraction', attempt=1, maximum=Decimal('.01'), pricing_hash='a'*64)
    with pytest.raises(RuntimeError, match='overrun'):
        provider.budget.finish(rid, actual_usd=Decimal('.02'), failed=False, response_hash='a'*64)
    with psycopg.connect(provider.budget.url) as conn:
        assert conn.execute('SELECT status FROM oracle2.operating_dispatch_receipts WHERE reservation_id=%s', (rid,)).fetchone()[0] == 'overrun'


def test_register_mismatch_denies_before_dispatch(adapter):
    provider,calls=adapter;provider.admitted_register_hash='c'*64
    with pytest.raises(PermissionError,match='register'):
        provider.extract(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose='source-extraction',attempt=1,input_tokens_upper_bound=2048,messages=[{'role':'user'}])
    assert calls==[]

def test_account_allowance_includes_pending_local_reservations(test_database):
    budget=Budget(test_database)
    budget.reserve(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose='source-extraction',attempt=1,maximum=Decimal('1'),pricing_hash='a'*64,account_remaining=Decimal('1.5'))
    with pytest.raises(PermissionError,match='ceiling'):
        budget.reserve(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose='source-extraction',attempt=1,maximum=Decimal('1'),pricing_hash='a'*64,account_remaining=Decimal('1.5'))
