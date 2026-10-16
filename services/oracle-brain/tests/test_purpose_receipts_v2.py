"""Pure invented custody metadata; a type alone never proves actual execution."""
from datetime import timedelta
import pytest
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from test_purpose_context_v2 import records


def commit():
    d,j,_,now=records()
    return PhaseResponseCommitV2(phase=d.phase,operation=d.operation,processing_purpose=d.purpose,
        dispatch_id=j.dispatch_id,workspace_id=d.workspace_id,actor_id=d.actor_id,provider_login=d.provider_login,
        actual_caller_login=d.provider_login,runtime_hash=d.runtime_hash,descriptor_hash='1'*64,
        operation_approval_hash=d.phase_registry_sha256,population_digest=d.population_digest,source_refs=d.source_refs,
        context_hash=j.context_hash,parent_registry_hash=d.parent_registry_sha256,current_proof_hash='2'*64,
        parent_witness_hash='3'*64,account_policy_hash=j.account_policy_hash,model=j.model,valid_until=d.expires_at,
        job_hash=j.job_hash,request_hash=j.request_hash,permission_hash=j.permission_hash,
        budget_identity_hash=j.budget_identity_hash,raw_response_hash='4'*64,native_custody_receipt_hash='5'*64,
        committed_at=now)


def test_local_commit_basis_never_claims_provider_creation_or_historical_earliest():
    c=commit()
    assert c.time_basis=='local-source-guarded-response-commit-v2'
    assert c.committed_at<c.valid_until
    assert 'raw_response' not in c.model_dump() and 'reading' not in c.model_dump()


@pytest.mark.parametrize('damage',('caller','expiry','source','phase','model','unknown-time'))
def test_commit_metadata_refuses_relabelled_or_unbounded_own_authority(damage):
    c=commit();raw=c.model_dump(mode='python')
    if damage=='caller':raw['actual_caller_login']='another_login'
    elif damage=='expiry':raw['valid_until']=c.committed_at
    elif damage=='source':raw['source_refs']=raw['source_refs'][:-1]
    elif damage=='phase':raw['phase']='assessment'
    elif damage=='model':raw['model']='openai/gpt-6-astra'
    elif damage=='unknown-time':raw['provider_created_at']=c.committed_at
    with pytest.raises((PermissionError,ValueError)):PhaseResponseCommitV2.model_validate(raw)
