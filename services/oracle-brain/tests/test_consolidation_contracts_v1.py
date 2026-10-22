"""Invented response-contract proof; no source/native/business authority."""
import json
from datetime import timedelta
from uuid import uuid4
import pytest
from test_assembly_context import context
from test_purpose_assembly_v2 import make_v2
from test_purpose_capture_v2 import wire_v2
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.consolidation_contracts_v1 import (
    AssertionScopeV1,ConsolidationCoreV1,validate_successor,readable_diff,applicable_assertions)
from oracle_brain.operating_model.purpose_assembly_v2 import ConsolidationAssemblyJobContextV1
from oracle_brain.operating_model.purpose_capture_v2 import (
    ObservedConsolidationProtocolV1,ObservedAssemblyProtocolV2,captured_assembly_candidate_v2,CapturedConsolidationCandidateV1)
from oracle_brain.operating_model.assembly_context import assembly_messages
from oracle_brain.operating_model.pipeline import assembly_candidate_payload,assembly_inputs
from oracle_brain.operating_model.semantic_acceptance import sealed


def core_fixture(context):
    ctx,model,now=make_v2(context)
    observations=ctx.extractions[0].payload['observations']
    scope={key:{'mode':'all','identities':[]} for key in ('process','customer','product','region')}
    raw={'contract':'qualified-consolidation-core-v1','model':model.model_dump(mode='json'),
         'expected_predecessor_version':0,'expected_predecessor_hash':None,'correction_source_ids':[],
         'assertions':[{'assertion_id':str(uuid4()),'revision':1,'subject_id':str(uuid4()),'predicate':'reported_step',
           'value':'invented documentary account','provenance':'employee_account','scope':scope,
           'valid_time':'evidenced','valid_from':now.isoformat(),'valid_to':None,
           'supporting_observations':[observations[0]['observation_id']],
           'temporal_observations':[observations[0]['observation_id']]}]}
    return ctx,ConsolidationCoreV1.model_validate_json(json.dumps(raw)),now


def test_core_requires_explicit_decoder_and_preserves_old_response(context):
    ctx,core,now=core_fixture(context)
    refs,observations,findings=assembly_inputs(tuple(e.payload for e in ctx.extractions))
    kwargs=dict(workspace_id=ctx.job.workspace_id,refs=refs,observations=observations,findings=findings)
    with pytest.raises(ValueError):assembly_candidate_payload(core.model_dump_json(),**kwargs)
    payload,evidence=assembly_candidate_payload(core.model_dump_json(),**kwargs,candidate_contract=core.contract)
    assert payload['consolidation_core']==core.model_dump(mode='json')
    assert any(k.startswith('assertion:') for k in evidence)
    old,_=assembly_candidate_payload(core.model.model_dump_json(),**kwargs)
    assert 'consolidation_core' not in old


@pytest.mark.parametrize('damage',('unknown-date','missing-date-evidence','same-opposition','skipped-version','no-correction','invented-approval','unknown-field','bad-scope'))
def test_closed_temporal_documentary_contract(context,damage):
    ctx,core,now=core_fixture(context);raw=core.model_dump(mode='json');a=raw['assertions'][0]
    if damage=='unknown-date':a['valid_time']='unknown'
    elif damage=='missing-date-evidence':a['temporal_observations']=[]
    elif damage=='same-opposition':a['opposing_observations']=a['supporting_observations']
    elif damage=='skipped-version':raw['model']['version']=3
    elif damage=='no-correction':raw['model']['version']=2;raw['expected_predecessor_version']=1;raw['expected_predecessor_hash']='a'*64
    elif damage=='invented-approval':a['confirmed']=True
    elif damage=='unknown-field':raw['recorded_at']=now.isoformat()
    elif damage=='bad-scope':a['scope']['customer']['identities']=[str(uuid4())]
    with pytest.raises(ValueError):ConsolidationCoreV1.model_validate_json(json.dumps(raw))


def test_consecutive_immutable_assertions_diff_and_unknown_dates(context):
    ctx,core,now=core_fixture(context);raw=core.model_dump(mode='json')
    raw['model']['version']=2;raw['expected_predecessor_version']=1;raw['expected_predecessor_hash']='b'*64
    raw['model']['source_refs'][0]['revision']+=1
    raw['correction_source_ids']=[str(core.model.source_refs[0].source_id)]
    a=raw['assertions'][0];a['revision']=2;a['predecessor_hash']=digest(core.assertions[0].model_dump(mode='json'));a['value']='corrected account'
    current=ConsolidationCoreV1.model_validate_json(json.dumps(raw));validate_successor(core,current)
    assert readable_diff(core,current)[0]['change']=='changed'
    query={k:{'mode':'exact','identities':[str(uuid4())]} for k in ('process','customer','product','region')}
    scope=AssertionScopeV1.model_validate_json(json.dumps(query))
    assert applicable_assertions(current,valid_at=now-timedelta(seconds=1),scope=scope)==()
    assert len(applicable_assertions(current,valid_at=now,scope=scope))==1
    a['valid_time']='unknown';a['valid_from']=None;a['temporal_observations']=[]
    unknown=ConsolidationCoreV1.model_validate_json(json.dumps(raw))
    assert applicable_assertions(unknown,valid_at=now,scope=scope)==()


def test_actual_complete_wire_consolidation_capture_and_protocol_separation(context):
    ctx,core,now=core_fixture(context)
    args=wire_v2(context);ctx=args['context']
    # Fixture independently rebuilds exact request/context pins; no live admission.
    request=dict(ctx.job.request);request['messages']=assembly_messages(receipts=ctx.receipts,extractions=ctx.extractions,
        census=ctx.census,model_id=ctx.model_id,version=ctx.model_version,candidate_contract=core.contract)
    job=ctx.job.model_copy(update={'request':request,'request_hash':digest(request)})
    data=ctx.model_dump(mode='python');data.update(context_schema='purpose-consolidation-context-v1',job=job)
    fresh=ConsolidationAssemblyJobContextV1.model_validate(data)
    protocol=ObservedConsolidationProtocolV1()
    # Core model must belong to THIS exact fixture's sealed response intent/population.
    rawcore=core.model_dump(mode='json');rawcore['model']=context[1].model_dump(mode='json') if isinstance(context,tuple) else rawcore['model']
    # make_v2(context) is deterministic for original fixture model; use matching ctx model identity.
    rawcore['model']['model_id']=str(ctx.model_id);rawcore['model']['workspace_id']=str(ctx.job.workspace_id)
    rawcore['model']['source_refs']=[r.ref.model_dump(mode='json') for r in ctx.receipts]
    raw=canonical_bytes({'model':job.request['model'],'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(rawcore)}}]})
    import hashlib
    observer=args['observer'].model_copy(update={'protocol_hash':sealed(protocol),'assembly_context_hash':sealed(fresh),'job_hash':sealed(job),'request_hash':job.request_hash})
    wire=args['observed'].model_copy(update={'observer_context_hash':sealed(observer),'assembly_context_hash':sealed(fresh),'job_hash':sealed(job),'request_hash':job.request_hash,'raw_sha256':hashlib.sha256(raw).hexdigest(),'captured_bytes':len(raw)})
    args.update(context=fresh,protocol=protocol,expected_protocol_hash=sealed(protocol),observer=observer,
                expected_observer_context_hash=sealed(observer),observed=wire,raw=raw)
    captured,evidence=captured_assembly_candidate_v2(**args)
    assert type(captured) is CapturedConsolidationCandidateV1
    assert captured.candidate['consolidation_core']['contract']==core.contract
    args['protocol']=ObservedAssemblyProtocolV2()
    with pytest.raises(PermissionError):captured_assembly_candidate_v2(**args)


from test_purpose_qualification_v3 import qualified_v3,serving


def temporal_qualified_fixture(q,*,predecessor=None,assertions=None):
    """Fresh injected capture/assessment/admission chain; never operational authority."""
    from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
    from oracle_brain.operating_model.purpose_qualification_v3 import (
        PurposeSemanticAdmissionV3,PurposeAssemblyQualificationV3,purpose_qualified_content_core_v3)
    from oracle_brain.operating_model.captured_assembly import _observed_model_content
    import hashlib
    original=q['wire'];ctx=original['context'];model=json.loads(_observed_model_content(original['raw'],ctx.job.request['model']))
    observations=ctx.extractions[0].payload['observations']
    body={'contract':'qualified-consolidation-core-v1','model':model,'expected_predecessor_version':model['version']-1,
      'expected_predecessor_hash':digest(predecessor) if predecessor is not None else None,'correction_source_ids':[str(r.ref.source_id) for r in ctx.receipts] if predecessor is not None else [],
      'assertions':[{'assertion_id':str(uuid4()),'revision':1,'subject_id':str(uuid4()),'predicate':'reported_step','value':'documentary fixture',
        'provenance':'employee_account','scope':{key:{'mode':'unknown','identities':[]} for key in ('process','customer','product','region')},
        'valid_time':'unknown','supporting_observations':[observations[0]['observation_id']]}]}
    if predecessor is not None:
        prior=ConsolidationCoreV1.model_validate_json(canonical_bytes(predecessor['consolidation_core']))
        a=body['assertions'][0];a.update(assertion_id=str(prior.assertions[0].assertion_id),revision=prior.assertions[0].revision+1,
            predecessor_hash=digest(prior.assertions[0].model_dump(mode='json')),value='documentary correction fixture')
    if assertions is not None:body['assertions']=assertions
    core=ConsolidationCoreV1.model_validate_json(json.dumps(body))
    request=dict(ctx.job.request);request['messages']=assembly_messages(receipts=ctx.receipts,extractions=ctx.extractions,
      census=ctx.census,model_id=ctx.model_id,version=ctx.model_version,candidate_contract=core.contract)
    job=ctx.job.model_copy(update={'request':request,'request_hash':digest(request)})
    data=ctx.model_dump(mode='python');data.update(context_schema='purpose-consolidation-context-v1',job=job)
    ctx=ConsolidationAssemblyJobContextV1.model_validate(data);protocol=ObservedConsolidationProtocolV1()
    raw=canonical_bytes({'model':job.request['model'],'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':core.model_dump_json()}}]})
    observer=original['observer'].model_copy(update={'protocol_hash':sealed(protocol),'assembly_context_hash':sealed(ctx),'handoff_hash':sealed(ctx.handoff),'job_hash':sealed(job),'request_hash':job.request_hash})
    observed=original['observed'].model_copy(update={'observer_context_hash':sealed(observer),'assembly_context_hash':sealed(ctx),'handoff_hash':sealed(ctx.handoff),'job_hash':sealed(job),'request_hash':job.request_hash,'raw_sha256':hashlib.sha256(raw).hexdigest(),'captured_bytes':len(raw)})
    wire={**original,'context':ctx,'protocol':protocol,'expected_protocol_hash':sealed(protocol),'observer':observer,'expected_observer_context_hash':sealed(observer),'observed':observed,'raw':raw}
    captured,evidence=captured_assembly_candidate_v2(**wire)
    assessment=q['assessment'].model_copy(update={'candidate_hash':captured.candidate_hash,'protocol_hash':sealed(protocol)})
    from oracle_brain.operating_model.acceptance_profiles import AssessmentPayload
    assessed=AssessmentPayload(**{k:getattr(assessment,k) for k in ('coverage','criteria','detail_gap_ids','detail_gap_owners')})
    assessed_raw=canonical_bytes({'model':'openai/gpt-6-astra','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':assessed.model_dump_json()}}]})
    assessment=assessment.model_copy(update={'raw_response_hash':hashlib.sha256(assessed_raw).hexdigest()})
    commits=tuple(c.model_copy(update=({'raw_response_hash':hashlib.sha256(raw).hexdigest(),'job_hash':sealed(job),'request_hash':job.request_hash,'context_hash':sealed(PurposePrivateContextV2(phase='assembly',job=job,assembly=ctx))} if c.phase=='assembly' else {'raw_response_hash':hashlib.sha256(assessed_raw).hexdigest()} if c.phase=='assessment' else {})) for c in q['commits'])
    assessment=assessment.model_copy(update={'dispatch_receipt_hash':sealed(next(c for c in commits if c.phase=='assessment'))})
    final=purpose_qualified_content_core_v3(captured,census=ctx.census,assessment=assessment,phase_commits=commits)
    admission=q['admission'].model_copy(update={'protocol_hash':sealed(protocol),'context_schema':ctx.context_schema,'captured_schema':captured.candidate_schema,
        'context_hash':sealed(ctx),'handoff_hash':sealed(ctx.handoff),'assessment_hash':sealed(assessment),'candidate_hash':captured.candidate_hash,'object_evidence_hash':captured.object_evidence_hash,
        'final_envelope_hash':digest(final),**{c.phase+'_commit_hash':sealed(c) for c in commits}})
    admission=PurposeSemanticAdmissionV3.model_validate(admission.model_dump(mode='python'))
    from oracle_brain.operating_model.purpose_qualification_v3 import _verify_phase_bindings
    _verify_phase_bindings(ctx,captured,assessment,admission,{c.phase:c for c in commits})
    payload={**final,'assembly_qualification':PurposeAssemblyQualificationV3(admission=admission).model_dump(mode='json')}
    manifest=q['manifest'].model_copy(update={'content_hash':digest(payload)})
    return {**q,'manifest':manifest,'payload':payload,'admission':admission,'wire':wire,'assessment':assessment,'commits':commits,'trusted_admission_hashes':frozenset({sealed(admission)})}


def test_fresh_temporal_core_is_in_schema3_capture_assessment_and_serving(qualified_v3):
    from oracle_brain.operating_model.purpose_qualification_v3 import verify_purpose_final_assembly_v3
    q=temporal_qualified_fixture(qualified_v3)
    assert verify_purpose_final_assembly_v3(**serving(q)) is None
    assert q['payload']['consolidation_core']['contract']=='qualified-consolidation-core-v1'
    assert q['payload']['assembly_capture']['candidate_schema']=='purpose-captured-consolidation-v1'
    old=serving(q);old['trusted_admission_hashes']=qualified_v3['trusted_admission_hashes']
    with pytest.raises(PermissionError):verify_purpose_final_assembly_v3(**old)


@pytest.mark.parametrize('damage',('sibling-only','changed-scope','changed-opposition','old-protocol','old-context','forged-assessment'))
def test_temporal_core_cannot_be_attached_or_changed_after_qualification(qualified_v3,damage):
    from oracle_brain.operating_model.purpose_qualification_v3 import verify_purpose_final_assembly_v3
    import copy
    q=serving(temporal_qualified_fixture(qualified_v3));payload=copy.deepcopy(q['payload'])
    if damage=='sibling-only':payload['consolidation_core']=qualified_v3['payload']['operating_models'][0]
    elif damage=='changed-scope':payload['consolidation_core']['assertions'][0]['scope']['customer']['mode']='all'
    elif damage=='changed-opposition':payload['consolidation_core']['assertions'][0]['opposing_observations']=['fabricated']
    elif damage=='old-protocol':payload['assembly_capture']['protocol']=ObservedAssemblyProtocolV2().model_dump(mode='json')
    elif damage=='old-context':payload['assembly_capture']['context_schema']='purpose-assembly-context-v2'
    elif damage=='forged-assessment':payload['qualified_lineage']['assessment_hash']='0'*64
    q['payload']=payload;q['manifest']=q['manifest'].model_copy(update={'content_hash':digest(payload)})
    with pytest.raises((PermissionError,ValueError)):verify_purpose_final_assembly_v3(**q)


def test_actual_sdk_inventory_includes_complete_assertion_scope_time_opposition(qualified_v3):
    from oracle_brain.operating_model.sdk_projection import SDKProjection,ProcessingSDKProjection,PaidConsolidationSDKProjectionV1
    from oracle_brain.operating_model.paid_sdk_embeddings_v3 import processing_embedding_inventory_v3
    import copy
    q=temporal_qualified_fixture(qualified_v3);payload=q['payload'];core=payload['consolidation_core']
    a=core['assertions'][0];identifier='assertion:'+a['assertion_id']+':'+str(a['revision'])
    records=SDKProjection.records(payload);nodes,_=SDKProjection.semantic_projection(payload)
    assert records[identifier]==('temporal_assertion',digest(a))
    assert nodes[identifier][0]=='ReportedAssertion' and json.loads(nodes[identifier][1])==a
    assert PaidConsolidationSDKProjectionV1.ontology_labels[:-1]==SDKProjection.ontology_labels
    before=processing_embedding_inventory_v3(payload)
    assert any(identifier in item.usage_keys[0] or identifier in item.text for item in before.inputs)
    view=ProcessingSDKProjection.projection_view(payload)
    assert all(json.loads(d['text'])['qualified_consolidation_core']==core for d in view['documents'])
    old=qualified_v3['payload'];assert all('qualified_consolidation_core' not in json.loads(d['text']) for d in ProcessingSDKProjection.projection_view(old)['documents'])
    for key,value in [('provenance','unknown'),('value','changed source account')]:
        changed=copy.deepcopy(payload);changed['consolidation_core']['assertions'][0][key]=value
        assert processing_embedding_inventory_v3(changed)!=before
    changed=copy.deepcopy(payload);changed['consolidation_core']['assertions'][0]['opposing_observations']=[payload['observations'][1]['observation_id']]
    after=processing_embedding_inventory_v3(changed)
    assert after!=before
    assert SDKProjection.semantic_projection(changed)[0][identifier][3]!=nodes[identifier][3]


def test_successor_rejects_relabelled_predecessor_original(context):
    _,core,_=core_fixture(context)
    raw=core.model_dump(mode='json');raw['model']['version']=2
    raw['expected_predecessor_version']=1;raw['expected_predecessor_hash']='b'*64
    raw['correction_source_ids']=[str(core.model.source_refs[0].source_id)]
    with pytest.raises(ValueError,match='new qualified original'):
        validate_successor(core,ConsolidationCoreV1.model_validate_json(json.dumps(raw)))


def test_qualified_sdk_embedding_context_preserves_core_and_refuses_legacy_or_model_mismatch(qualified_v3):
    from copy import deepcopy
    from oracle_brain.operating_model.purpose_profiles_v2 import DerivedEmbeddingContextV2
    from test_paid_sdk_embeddings_v3 import paid_case_for
    q=temporal_qualified_fixture(qualified_v3)
    case=paid_case_for(q['payload'],q['manifest'])
    context=case['private'].embedding
    assert context.qualified_payload['consolidation_core']==q['payload']['consolidation_core']
    raw={k:v for k,v in context.model_dump(mode='python').items() if k!='inventory'}|{'schema_version':2}
    with pytest.raises(PermissionError,match='explicit qualified consolidation SDK context'):
        DerivedEmbeddingContextV2.model_validate(raw)
    changed=deepcopy(q['payload']);changed['consolidation_core']['model']['model_id']=str(uuid4())
    with pytest.raises(PermissionError,match='differs'):
        paid_case_for(changed,q['manifest'])
    with pytest.raises(PermissionError,match='differs from exact SDK artifact'):
        type(context).model_validate(context.model_dump(mode='python')|{'qualified_artifact_id':uuid4()})
