"""Different invented phase principals preserve actual historical extraction seals."""
from uuid import uuid4
import pytest
from test_assembly_context import context
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.purpose_assembly_v2 import AssemblyJobContextV2,CompilerExtractionHandoffV2
from oracle_brain.operating_model.semantic_acceptance import sealed


def make_v2(context):
    old,model,now=context
    handoff=CompilerExtractionHandoffV2(workspace_id=old.job.workspace_id,compiler_actor=uuid4(),
        compiler_login='compiler_fixture',compiler_runtime_hash='a'*64,compiler_authority_receipt_hash='b'*64,
        source_registry_hash=old.source_registry_hash,source_refs=tuple(r.ref for r in old.receipts),
        extractions=old.extractions,issued_at=now,expires_at=old.expires_at)
    # A DIFFERENT current assembly permission; immutable extraction seals retained.
    job=old.job.model_copy(update={'permission_hash':'9'*64})
    new=AssemblyJobContextV2(actor_id=old.actor_id,provider_login='assembly_fixture',
        runtime_hash=old.runtime_hash,source_registry_hash=old.source_registry_hash,
        compiler_digest=old.compiler_digest,parent_registry_hash=old.parent_registry_hash,
        expected_handoff_hash=sealed(handoff),job=job,receipts=old.receipts,handoff=handoff,
        census=old.census,reviewed_inventories={},model_id=old.model_id,model_version=1,expires_at=old.expires_at)
    return new,model,now


def test_v2_assembly_uses_own_permission_and_keeps_historical_extraction_seals(context):
    new,model,now=make_v2(context)
    historical=[e.manifest.permission_digest for e in new.extractions]
    assert all(p!=new.job.permission_hash for p in historical)
    payload,_=new.validate_candidate(model.model_dump_json(),now=now)
    assert payload['operating_models'][0]['model_id']==str(model.model_id)
    assert [e.manifest.permission_digest for e in new.extractions]==historical


@pytest.mark.parametrize('damage',('handoff','omitted','reordered','historical-permission','payload','new-permission','model-id'))
def test_v2_separation_never_weakens_exact_historical_handoff_binding(context,damage):
    new,model,now=make_v2(context)
    if damage=='handoff':new=new.model_copy(update={'expected_handoff_hash':'f'*64})
    elif damage=='omitted':new=new.model_copy(update={'receipts':new.receipts[:-1]})
    elif damage=='reordered':new=new.model_copy(update={'receipts':tuple(reversed(new.receipts))})
    elif damage=='historical-permission':
        e=new.handoff.extractions[0]
        changed=e.model_copy(update={'manifest':e.manifest.model_copy(update={'permission_digest':'f'*64})})
        new=new.model_copy(update={'handoff':new.handoff.model_copy(update={'extractions':(changed,*new.extractions[1:])})})
    elif damage=='payload':new.extractions[0].payload['findings'].append({'text':'unsealed'})
    elif damage=='new-permission':
        # Current permission is qualified externally in the purpose descriptor;
        # it cannot overwrite a historical extraction's seal to make them equal.
        e=new.handoff.extractions[0]
        new=new.model_copy(update={'handoff':new.handoff.model_copy(update={'extractions':(
            e.model_copy(update={'manifest':e.manifest.model_copy(update={'permission_digest':new.job.permission_hash})}),
            *new.extractions[1:])})})
    elif damage=='model-id':new=new.model_copy(update={'model_id':uuid4()})
    with pytest.raises((PermissionError,ValueError)):
        new.validate_candidate(model.model_dump_json(),now=now)


def test_rich_fixture_builders_use_actual_observations_and_retain_conflict_unknowns():
    import hashlib,json
    from types import SimpleNamespace
    from oracle_brain.operating_model.source_receipts import SourceReceipt,SourceRef
    from oracle_brain.operating_model.extraction import validate_response
    from oracle_brain.operating_model.pipeline import assembly_inputs,assembly_candidate_payload
    from oracle_brain.operating_model.acceptance_profiles import AssessmentPayload,CensusPayload
    from oracle_brain.operating_model.coverage import validate_coverage
    from oracle_brain.operating_model.native_factory import validate_embedding_response
    from purpose_journey_fixture_models import (RICH_SOURCE_TEXTS,PRIVATE_MARKERS,extraction_json,
        census_json,model_json,assessment_json,embedding_response)
    workspace=uuid4();receipts=[];payloads=[]
    for text in RICH_SOURCE_TEXTS:
        sha=hashlib.sha256(text.encode()).hexdigest()
        r=SourceReceipt(ref=SourceRef(workspace_id=workspace,source_id=uuid4(),revision=1,
            original_sha256=sha,reading_sha256=sha,parser_id='invented-test'),reading=text,display_revision='r1')
        raw=extraction_json(r);response,observations=validate_response(r,raw)
        payloads.append({'source_refs':[r.ref.model_dump(mode='json')],
            'observations':[o.model_dump(mode='json') for o in observations],
            'findings':[f.model_dump(mode='json') for f in response.findings]})
        receipts.append(r)
    refs,observations,findings=assembly_inputs(payloads,enforce_unique_sources=True)
    model_id=uuid4();raw=model_json(payloads,source_refs=tuple(refs),model_id=model_id)
    payload,evidence=assembly_candidate_payload(raw,workspace_id=workspace,refs=refs,observations=observations,findings=findings)
    assert len(observations)==3 and len(findings)==3
    assert {f['kind'] for f in findings.values()}=={'source_conflict','missing_information'}
    model=payload['operating_models'][0]
    assert model['completeness']=='conflicted' and model['workflows'][0]['status']=='reported'
    assert len(model['workflows'][0]['handoffs'])==2
    assert set(model['finding_ids'])==set(findings)
    assert all(marker not in json.dumps(payload) for marker in PRIVATE_MARKERS)
    census=CensusPayload.model_validate_json(census_json(SimpleNamespace(scope=SimpleNamespace(receipts=receipts))))
    assessment=AssessmentPayload.model_validate_json(assessment_json(SimpleNamespace(census=census,object_evidence=evidence)))
    coverage=validate_coverage(census.obligations,assessment.coverage,object_evidence=evidence,
        independent_inventory_hash=digest({'obligations':[o.model_dump(mode='json') for o in census.obligations]}))
    assert coverage['essential_represented']==3 and coverage['essential_unresolved']==3
    vectors=embedding_response(7)
    validate_embedding_response(vectors,count=7)
    assert len({tuple(v['embedding']) for v in vectors['data']})==7
    with pytest.raises(ValueError,match='exact three'):
        model_json(payloads[:-1],source_refs=tuple(refs),model_id=model_id)
    damaged=[dict(p) for p in payloads];damaged[0]['observations']=[]
    with pytest.raises(ValueError,match='exact three'):
        model_json(damaged,source_refs=tuple(refs),model_id=model_id)
    omitted=SimpleNamespace(census=census,object_evidence={k:v for k,v in evidence.items() if k not in findings})
    with pytest.raises(ValueError,match='omitted'):
        assessment_json(omitted)
    for count in (0,True,10001):
        with pytest.raises(ValueError):embedding_response(count)
