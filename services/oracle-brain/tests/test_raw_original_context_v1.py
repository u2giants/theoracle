"""Pure context transplants fail; no raw SQL/observer/credential authority."""
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.original_qualification_v1 import RawOriginalPopulationV1
from oracle_brain.operating_model.raw_original_context_v1 import RawOriginalPhaseContextV1
from test_original_native_jobs_v1 import original_job

def context(review=False):
    j=original_job(review);q=j.pricing
    pop=RawOriginalPopulationV1(population_id=j.population_id,workspace_id=j.workspace_id,
        original_root_hash=q.original_root_hash,operation_registry_hash=j.operation_registry_hash,
        runtime_hash='1'*64,source_registry_hash='2'*64,raw_refs=(j.raw_ref,),
        population_digest=digest({'raw_refs':[j.raw_ref.model_dump(mode='json')]}),
        issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=q.expires_at)
    return RawOriginalPhaseContextV1(actor_id=uuid4(),expected_session_role='invented_original_phase',
        population=pop,job=j,original_allocation_hash=q.original_allocation_hash,original_horizon=q.original_horizon,
        pricing_quote_hash=digest(q.model_dump(mode='json')),view_policy_hash='3'*64,
        vision_token_policy_hash=q.vision_token_policy_sha256,phase_expires_at=q.expires_at)

@pytest.mark.parametrize('review',[False,True])
def test_complete_single_original_phase_context_has_no_future_source_ref(review):
    c=context(review);assert RawOriginalPhaseContextV1.model_validate_json(c.model_dump_json())==c
    assert len(c.population.raw_refs)==1 and not hasattr(c,'source_refs')

@pytest.mark.parametrize('change',['population','registry','root','allocation','horizon','quote','policy','actor','version','future'])
def test_context_crossoperation_or_future_source_transplant_denies(change):
    c=context();body=c.model_dump(mode='python')
    if change=='population':body['population']['population_id']=uuid4()
    elif change=='registry':body['population']['operation_registry_hash']='0'*64
    elif change=='root':body['population']['original_root_hash']='0'*64
    elif change=='allocation':body['original_allocation_hash']='0'*64
    elif change=='horizon':body['phase_expires_at']=c.original_horizon
    elif change=='quote':body['pricing_quote_hash']='0'*64
    elif change=='policy':body['vision_token_policy_hash']='0'*64
    elif change=='actor':body['actor_id']=c.population.issuer_actor
    elif change=='version':body['schema_version']=True
    else:body['source_refs']=[]
    with pytest.raises(ValueError):RawOriginalPhaseContextV1.model_validate(body)
