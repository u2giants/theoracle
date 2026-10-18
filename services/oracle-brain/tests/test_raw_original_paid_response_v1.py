"""Strict paid lineage shape only; immutable producer/SQL authentication separate."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from oracle_brain.operating_model.raw_original_paid_response_v1 import RawOriginalPaidResponseCommitV1
from test_original_native_jobs_v1 import original_job

def record():
    j=original_job();now=datetime.now(timezone.utc)
    fields={k:'a'*64 for k in RawOriginalPaidResponseCommitV1.model_fields if k.endswith('_hash') or k.endswith('_digest')}
    fields.update(schema_version=1,purpose=j.purpose,dispatch_id=j.dispatch_id,raw_ref=j.raw_ref,population_id=j.population_id,
        reservation_id=uuid4(),native_failed=False,wire_complete=True,model_id=j.pricing.model,committed_at=now,original_horizon=now+timedelta(seconds=60))
    return RawOriginalPaidResponseCommitV1.model_validate(fields)

def test_byte_only_paid_commit_has_no_future_source_or_authority_fields():
    r=record();assert RawOriginalPaidResponseCommitV1.model_validate_json(r.model_dump_json())==r
    for key in ('source_ref','issuer_actor','authorized_phase_commit_hash','reading_sha256','actual_spend_usd'):
        with pytest.raises(ValueError):RawOriginalPaidResponseCommitV1.model_validate({**r.model_dump(),key:'forbidden'})

@pytest.mark.parametrize('damage',[{'schema_version':True},{'schema_version':1.0},{'wire_complete':1},
    {'wire_complete':False},{'native_failed':0},{'native_failed':True},{'purpose':'source-extraction'},
    {'transport':'native-utf8-byte-roundtrip-v1'},{'model_id':'foreign/model'}])
def test_paid_phase_is_closed_and_never_normalizes_status(damage):
    r=record()
    with pytest.raises(ValueError):RawOriginalPaidResponseCommitV1.model_validate({**r.model_dump(),**damage})

def test_no_utf8_paid_record_or_late_commit():
    r=record();body=r.model_dump()
    body['raw_ref']['media_type']='text/plain'
    with pytest.raises(ValueError):RawOriginalPaidResponseCommitV1.model_validate(body)
    with pytest.raises(ValueError):RawOriginalPaidResponseCommitV1.model_validate({**r.model_dump(),'committed_at':r.original_horizon})

@pytest.mark.parametrize('field',['native_failed','wire_complete','current_sql_receipt_hash','observer_witness_hash'])
def test_paid_response_never_fills_missing_proof_status(field):
    body=record().model_dump();del body[field]
    with pytest.raises(ValueError):RawOriginalPaidResponseCommitV1.model_validate(body)
