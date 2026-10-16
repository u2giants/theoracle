"""Existing V1 extraction authority on one actual connection; no new grants."""
from uuid import uuid4
import psycopg
import pytest
from test_purpose_source_authority import purpose_population
from test_source_processing_qualification import processing
from oracle_brain.operating_model.authority_adapter import BoundProcessingSourceResolver,ProcessingRunBinding
from oracle_brain.operating_model.processing_context import ProcessingDispatch,ProcessingRunDescriptor,ProcessingAuthorityProof
from oracle_brain.operating_model.contracts import digest


def bound(f):
    fields={k:'a'*64 for k in ('job_hash','request_hash','permission_hash','processing_request_hash','account_policy_hash','terms_hash','pricing_hash','register_hash','budget_identity_hash')}
    dispatches=tuple(ProcessingDispatch(dispatch_id=uuid4(),source_ref=r,model='openai/gpt-6.1-sol',**fields) for r in f['refs'])
    d=ProcessingRunDescriptor(run_id=uuid4(),workspace_id=f['workspace'],actor_id=f['actor'],worker_uri='spiffe://oracle/extraction-worker',
        runtime_hash=f['runtime'],source_registry_hash=f['registry'],parent_registry_sha256='1'*64,envelope_sha256='2'*64,
        ledger_registry_hash='3'*64,key_coverage_hash='4'*64,source_refs=f['refs'],dispatches=dispatches,
        issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=f['expiry'])
    pins=ProcessingRunBinding(f['binding'],digest(d.model_dump(mode='json')),d.parent_registry_sha256,d.envelope_sha256)
    return BoundProcessingSourceResolver(f['url'],run_binding=pins),d


def test_three_current_identities_and_dispatch_proof_use_same_actual_session(purpose_population,monkeypatch):
    f=purpose_population('embedding','gateway-metadata');adapter,d=bound(f)
    with psycopg.connect(f['url']) as conn:
        pid=conn.execute('SELECT pg_backend_pid()').fetchone()[0]
        def forbidden(*args,**kwargs):pytest.fail('nested SQL connection attempted inside extraction population hold')
        monkeypatch.setattr(psycopg,'connect',forbidden)
        assert tuple(adapter.identity(f['workspace'],r.source_id,connection=conn) for r in d.source_refs)==d.source_refs
        for dispatch in d.dispatches:
            with adapter.hold(d,dispatch,connection=conn) as proof:
                assert type(proof) is ProcessingAuthorityProof and proof.source_ref==dispatch.source_ref
                assert conn.execute('SELECT pg_backend_pid()').fetchone()[0]==pid


def test_provided_admin_or_other_role_connection_cannot_masquerade_as_source_actor(admin_url,purpose_population):
    f=purpose_population('embedding','gateway-metadata');other=purpose_population('embedding','gateway-metadata');adapter,d=bound(f)
    for url in (admin_url,other['url']):
        with psycopg.connect(url) as conn,pytest.raises(PermissionError):
            with adapter.hold(d,d.dispatches[0],connection=conn):pytest.fail('borrowed identity admitted')


def test_provided_connection_rechecks_revoked_third_source_on_next_boundary(admin_url,purpose_population):
    f=purpose_population('embedding','gateway-metadata');adapter,d=bound(f)
    with psycopg.connect(f['url']) as conn:
        with adapter.hold(d,d.dispatches[2],connection=conn):pass
    with psycopg.connect(admin_url) as owner:
        owner.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(f['grants'][2],))
    with psycopg.connect(f['url']) as conn,pytest.raises(psycopg.errors.InsufficientPrivilege):
        with adapter.hold(d,d.dispatches[2],connection=conn):pytest.fail('revoked third source admitted')
