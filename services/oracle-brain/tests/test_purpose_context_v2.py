"""Invented pure metadata tests; no issuer, SQL authority or provider is created."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.purpose_context import (
    PHASE_CONTRACTS, ParentPopulationAdmissionV2, PurposeDispatchV2,
    PurposeRunDescriptorV2, PurposeMetadataProjectionV2, PurposeAuthorityProofV2,
    source_population_digest, verify_purpose_authority_proof_v2,
)
from oracle_brain.operating_model.source_receipts import SourceRef


def records(phase='census'):
    workspace=uuid4();now=datetime.now(timezone.utc);expiry=now+timedelta(minutes=1)
    refs=tuple(SourceRef(workspace_id=workspace,source_id=uuid4(),revision=1,
        original_sha256='a'*64,reading_sha256='b'*64,parser_id='c'*64) for _ in range(3))
    purpose,operation,model=PHASE_CONTRACTS[phase]
    dispatch=PurposeDispatchV2(dispatch_id=uuid4(),source_refs=refs,model=model,
        **{name:'d'*64 for name in ('job_hash','request_hash','permission_hash','context_hash',
        'processing_request_hash','account_policy_hash','terms_hash','pricing_hash','register_hash',
        'approvals_hash','budget_identity_hash','ledger_registry_hash','key_coverage_hash')})
    descriptor=PurposeRunDescriptorV2(run_id=uuid4(),workspace_id=workspace,actor_id=uuid4(),
        provider_login='provider_fixture',worker_uri='spiffe://oracle/purpose-worker',phase=phase,
        purpose=purpose,operation=operation,runtime_hash='e'*64,source_registry_hash='f'*64,
        parent_registry_sha256='1'*64,population_admission_sha256='2'*64,phase_registry_sha256='3'*64,
        population_digest=source_population_digest(refs),source_refs=refs,dispatches=(dispatch,),
        issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=expiry)
    projection=PurposeMetadataProjectionV2(descriptor=descriptor,
        descriptor_sha256=digest(descriptor.model_dump(mode='json')))
    return descriptor,dispatch,projection,now


def valid_proof(d,j,p,now,*,caller='provider_fixture',profile='source-reader'):
    return PurposeAuthorityProofV2(run_id=d.run_id,workspace_id=d.workspace_id,actor_id=d.actor_id,
        admitted_provider_login=d.provider_login,actual_caller_login=caller,dispatch_id=j.dispatch_id,
        phase=d.phase,purpose=d.purpose,operation=d.operation,source_refs=d.source_refs,
        population_digest=d.population_digest,runtime_hash=d.runtime_hash,source_registry_hash=d.source_registry_hash,
        descriptor_sha256=digest(d.model_dump(mode='json')),parent_registry_sha256=d.parent_registry_sha256,
        population_admission_sha256=d.population_admission_sha256,phase_registry_sha256=d.phase_registry_sha256,
        projection_sha256=digest(p.model_dump(mode='json')),dispatch_hash=digest(j.model_dump(mode='json')),
        job_hash=j.job_hash,request_hash=j.request_hash,permission_hash=j.permission_hash,
        session_role=caller,profile=profile,checked_at=now,expires_at=d.expires_at)


@pytest.mark.parametrize('phase',tuple(PHASE_CONTRACTS))
def test_fixed_phase_metadata_has_three_exact_originals_and_no_private_payload(phase):
    d,j,p,_=records(phase)
    assert len(d.source_refs)==3 and d.dispatch(j.dispatch_id)==j
    assert j.source_refs==d.source_refs
    assert d.purpose==PHASE_CONTRACTS[phase][0]
    raw=p.model_dump(mode='json')
    assert not any(word in json.dumps(raw) for word in ('reading"','private_object_key','messages','candidate','inventories'))
    assert PurposeMetadataProjectionV2.model_validate_json(p.model_dump_json())==p


@pytest.mark.parametrize('damage',('omitted','reordered','duplicate','workspace','model','purpose','operation','issuer','self-issuer','extra'))
def test_descriptor_refuses_filtered_or_relabelled_population(damage):
    d,_,_,_=records();raw=d.model_dump(mode='json')
    if damage=='omitted':raw['dispatches'][0]['source_refs'].pop()
    elif damage=='reordered':raw['dispatches'][0]['source_refs'].reverse()
    elif damage=='duplicate':raw['source_refs'].append(raw['source_refs'][0])
    elif damage=='workspace':raw['workspace_id']=str(uuid4())
    elif damage=='model':raw['dispatches'][0]['model']='openai/gpt-6-astra'
    elif damage=='purpose':raw['purpose']='operating-audit'
    elif damage=='operation':raw['operation']='embedding'
    elif damage=='issuer':raw['reviewer_actor']=raw['issuer_actor']
    elif damage=='self-issuer':raw['issuer_actor']=raw['actor_id']
    else:raw['request']={'raw':'not a metadata field'}
    with pytest.raises((ValueError,ValidationError)):
        PurposeRunDescriptorV2.model_validate_json(json.dumps(raw))


def test_population_admission_is_strict_but_does_not_create_authority():
    d,_,_,_=records()
    fields={k:getattr(d,k) for k in ('workspace_id','parent_registry_sha256','runtime_hash','source_registry_hash',
        'source_refs','population_digest','issuer_actor','reviewer_actor','expires_at')}
    admitted=ParentPopulationAdmissionV2(**fields)
    assert admitted.source_refs==d.source_refs
    with pytest.raises(ValidationError):ParentPopulationAdmissionV2(**fields,reading='raw')
    with pytest.raises(ValueError):ParentPopulationAdmissionV2(**{**fields,'source_refs':d.source_refs[:-1]})
    with pytest.raises(ValueError):ParentPopulationAdmissionV2(**{**fields,'reviewer_actor':d.issuer_actor})
    with pytest.raises(ValidationError):admitted.runtime_hash='0'*64


@pytest.mark.parametrize('caller,profile,phase,allowed',(
    ('provider_fixture','source-reader','census',True),
    ('own_gateway','gateway-metadata','census',True),
    ('borrowed','source-reader','census',False),
    ('provider_fixture','source-reader','embedding',False),
    ('provider_fixture','gateway-metadata','embedding',True),
    ('other_gateway','gateway-metadata','embedding',False),
))
def test_actual_caller_and_admitted_provider_are_named_separately(caller,profile,phase,allowed):
    d,j,p,now=records(phase)
    if not allowed:
        with pytest.raises(ValueError):valid_proof(d,j,p,now,caller=caller,profile=profile)
    else:
        proof=valid_proof(d,j,p,now,caller=caller,profile=profile)
        assert proof.actual_caller_login==caller and proof.admitted_provider_login==d.provider_login
        assert verify_purpose_authority_proof_v2(proof,d,j,projection_sha256=digest(p.model_dump(mode='json')),
            actual_caller_login=caller,profile=profile,now=now) is None


@pytest.mark.parametrize('damage',('future','stale','expired','later-horizon','dispatch','parent','projection','provider','caller','population','bool','none'))
def test_proof_consistency_refuses_stale_forged_or_wrong_dispatch(damage):
    d,j,p,now=records();proof=valid_proof(d,j,p,now);raw=proof.model_dump(mode='json');clock=now
    if damage=='future':raw['checked_at']=(now+timedelta(seconds=1)).isoformat()
    elif damage=='stale':clock=now+timedelta(seconds=6)
    elif damage=='expired':clock=d.expires_at
    elif damage=='later-horizon':raw['expires_at']=(d.expires_at+timedelta(seconds=1)).isoformat()
    elif damage=='dispatch':raw['dispatch_id']=str(uuid4())
    elif damage=='parent':raw['parent_registry_sha256']='0'*64
    elif damage=='projection':raw['projection_sha256']='0'*64
    elif damage=='provider':raw['admitted_provider_login']='forged_provider'
    elif damage=='caller':raw['actual_caller_login']='forged_caller'
    elif damage=='population':raw['source_refs'].pop()
    elif damage=='bool':proof=True
    elif damage=='none':proof=None
    with pytest.raises((ValueError,PermissionError)):
        if damage not in {'bool','none'}:proof=PurposeAuthorityProofV2.model_validate_json(json.dumps(raw))
        verify_purpose_authority_proof_v2(proof,d,j,projection_sha256=digest(p.model_dump(mode='json')),
            actual_caller_login='provider_fixture',profile='source-reader',now=clock)
