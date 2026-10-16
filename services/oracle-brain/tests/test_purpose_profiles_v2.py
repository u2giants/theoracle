"""Invented private inputs; no provider or external qualification is issued."""
import hashlib
from datetime import datetime,timedelta,timezone
from uuid import uuid4

import pytest

from oracle_brain.operating_model.acceptance_profiles import CensusContext,OriginalScope,request_for
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.purpose_context import PurposeDispatchV2,PurposeRunDescriptorV2,source_population_digest
from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2,DerivedEmbeddingContextV2
from oracle_brain.operating_model.semantic_acceptance import SourceRegion
from oracle_brain.operating_model.source_receipts import SourceReceipt,SourceRef,EvidenceRef
from test_native_factory import job


def census_case():
    now=datetime.now(timezone.utc);workspace=uuid4();actor=uuid4()
    receipts=[];regions=[]
    for i in range(3):
        text=f'Invented distinct original {i} assigns release approval to role {i}.'
        ref=SourceRef(workspace_id=workspace,source_id=uuid4(),revision=1,
            original_sha256=hashlib.sha256(text.encode()).hexdigest(),
            reading_sha256=hashlib.sha256(text.encode()).hexdigest(),parser_id='a'*64)
        receipts.append(SourceReceipt(ref=ref,reading=text,display_revision='r1'))
        regions.append(SourceRegion(region_id=str(i),kind='section',
            evidence=EvidenceRef(ref=ref,start=0,end=len(text),quote=text)))
    scope=OriginalScope(workspace_id=workspace,receipts=tuple(receipts),regions=tuple(regions),
        source_region_register_hash=digest({'regions':[r.model_dump(mode='json') for r in regions]}))
    c=CensusContext(scope=scope,actor_id=actor,runtime_hash='b'*64,permission_hash='c'*64,
        protocol_hash='d'*64,request_hash='e'*64)
    request=request_for(c);c=c.model_copy(update={'request_hash':digest(request)})
    j=job();processing=j.processing_request.model_copy(update={'purpose':'source-census'})
    j=j.model_copy(update={'workspace_id':workspace,'purpose':'source-census','request':request,
        'request_hash':digest(request),'permission_hash':c.permission_hash,'processing_request':processing,
        'approvals':(j.approvals[0].model_copy(update={'purpose':'source-census'}),)})
    private=PurposePrivateContextV2(phase='census',job=j,census=c)
    policy=processing.model_dump(mode='json');refs=tuple(r.ref for r in receipts)
    dispatch=PurposeDispatchV2(dispatch_id=j.dispatch_id,source_refs=refs,job_hash=digest(j.model_dump(mode='json')),
        request_hash=j.request_hash,permission_hash=j.permission_hash,context_hash=digest(private.model_dump(mode='json')),
        model=request['model'],processing_request_hash=digest(policy),
        account_policy_hash=digest({k:v for k,v in policy.items() if k!='terms_hash'}),terms_hash=policy['terms_hash'],
        pricing_hash=digest(j.pricing.model_dump(mode='json')),register_hash=j.register_hash,
        approvals_hash=digest({'approvals':[a.model_dump(mode='json') for a in j.approvals]}),
        budget_identity_hash='1'*64,ledger_registry_hash='2'*64,key_coverage_hash='3'*64)
    d=PurposeRunDescriptorV2(run_id=uuid4(),workspace_id=workspace,actor_id=actor,provider_login='census_provider',
        worker_uri='spiffe://oracle/census-worker',phase='census',purpose='source-census',operation='chat',
        runtime_hash=c.runtime_hash,source_registry_hash='4'*64,parent_registry_sha256='5'*64,
        population_admission_sha256='6'*64,phase_registry_sha256='7'*64,
        population_digest=source_population_digest(refs),source_refs=refs,dispatches=(dispatch,),
        issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=now+timedelta(seconds=20))
    return private,d,dispatch,now


def test_private_census_native_request_has_all_originals_before_any_candidate():
    private,d,dispatch,now=census_case()
    assert private.validate_current(d,dispatch,now=now)==private.job
    assert len(private.census.scope.receipts)==3
    assert private.assembly is private.assessment is private.embedding is None
    assert 'candidate' not in private.job.request['messages'][1]['content']


@pytest.mark.parametrize('damage',('omitted','reordered','request','actor','runtime','permission','approval','expired'))
def test_private_profile_cannot_borrow_qualified_context_or_silently_filter_originals(damage):
    private,d,dispatch,now=census_case()
    if damage in {'omitted','reordered'}:
        refs=d.source_refs[:-1] if damage=='omitted' else tuple(reversed(d.source_refs))
        d=d.model_copy(update={'source_refs':refs})
    elif damage=='request':private.job.request['messages'][1]['content']='other input'
    elif damage=='actor':d=d.model_copy(update={'actor_id':uuid4()})
    elif damage=='runtime':d=d.model_copy(update={'runtime_hash':'f'*64})
    elif damage=='permission':dispatch=dispatch.model_copy(update={'permission_hash':'f'*64})
    elif damage=='approval':private.job.approvals[0].expires_at=now-timedelta(seconds=1)
    elif damage=='expired':now=d.expires_at
    with pytest.raises((PermissionError,ValueError)):
        private.validate_current(d,dispatch,now=now)


def test_embedding_private_context_refuses_raw_original_scope_or_arbitrary_projection():
    private,d,dispatch,now=census_case()
    with pytest.raises(ValueError):
        DerivedEmbeddingContextV2(actor_id=d.actor_id,workspace_id=d.workspace_id,runtime_hash=d.runtime_hash,
            permission_hash=dispatch.permission_hash,qualified_artifact_id=uuid4(),qualified_artifact_version=1,
            qualified_content_hash='a'*64,projection_digest='b'*64,source_refs=d.source_refs,
            projection={'reading':private.census.scope.receipts[0].reading},scope=private.census.scope)


from test_assembly_qualification import qualified
from test_assembly_context import context


def test_derived_embedding_uses_only_exact_current_qualified_projection(qualified):
    import json
    from oracle_brain.operating_model.sdk_projection import ProcessingSDKProjection
    payload=qualified['payload'];view=ProcessingSDKProjection.projection_view(payload)
    embedding=DerivedEmbeddingContextV2(actor_id=uuid4(),workspace_id=qualified['manifest'].workspace_id,
        runtime_hash='a'*64,permission_hash='b'*64,qualified_artifact_id=qualified['manifest'].artifact_id,
        qualified_artifact_version=qualified['manifest'].version,qualified_content_hash=digest(payload),
        projection_digest=digest(view),source_refs=tuple(SourceRef.model_validate_json(json.dumps(r)) for r in view['source_refs']),
        projection=view)
    request=embedding.request()
    assert request['input']==[d['text'] for d in view['documents']]
    assert request['dimensions']==256 and request['model']=='openai/text-embedding-3-small'
    assert 'scope' not in embedding.model_dump(mode='json')
    altered=__import__('copy').deepcopy(view);altered['documents'][0]['text']+=' uncited private original'
    with pytest.raises(PermissionError):
        DerivedEmbeddingContextV2.model_validate({**embedding.model_dump(mode='python'),'projection':altered})
