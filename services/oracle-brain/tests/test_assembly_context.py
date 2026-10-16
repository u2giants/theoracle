"""Invented-data assembly request proof; never provider/runtime admission."""
import json
import pytest
from test_business_operating_model import observation, model
from oracle_brain.operating_model.pipeline import assembly_inputs, assembly_candidate_payload


def invented_inputs():
    observations = (observation(4, 'Design sends ART to Supplier'),
                    observation(5, 'Supplier receives packet'))
    payloads = tuple({'source_refs': [o.ref.model_dump(mode='json')],
                      'observations': [o.model_dump(mode='json')], 'findings': []}
                     for o in observations)
    return observations, payloads


def test_pure_candidate_keeps_actual_ids_and_no_generator_coverage():
    observations, payloads = invented_inputs()
    refs, actual, findings = assembly_inputs(payloads)
    candidate, evidence = assembly_candidate_payload(model(observations).model_dump_json(),
        workspace_id=observations[0].ref.workspace_id, refs=refs,
        observations=actual, findings=findings)
    assert candidate['source_refs'] == [o.ref.model_dump(mode='json') for o in observations]
    assert evidence['p1'] == observations[0].evidence
    assert 'coverage' not in candidate
    assert candidate['raw_response'] == model(observations).model_dump_json()


def test_pure_candidate_rejects_self_coverage_and_duplicate_source_input():
    observations, payloads = invented_inputs()
    refs, actual, findings = assembly_inputs(payloads)
    raw = model(observations).model_dump(mode='json')
    raw['coverage_records'] = []
    with pytest.raises(ValueError):
        assembly_candidate_payload(json.dumps(raw), workspace_id=observations[0].ref.workspace_id,
            refs=refs, observations=actual, findings=findings)
    with pytest.raises(ValueError, match='duplicate'):
        assembly_inputs((*payloads, payloads[0]), enforce_unique_sources=True)


@pytest.fixture
def context():
    from datetime import datetime, timedelta, timezone
    from uuid import uuid4
    from test_native_factory import job
    from oracle_brain.operating_model.assembly_context import AssemblyJobContext, SealedAssemblyExtraction, assembly_messages
    from oracle_brain.operating_model.contracts import ArtifactManifest, digest
    from oracle_brain.operating_model.coverage import Obligation
    from oracle_brain.operating_model.semantic_acceptance import FrozenCensus, SourceRegion
    from oracle_brain.operating_model.source_receipts import SourceReceipt
    observations, payloads = invented_inputs()
    now = datetime.now(timezone.utc)-timedelta(seconds=3)
    receipts = tuple(SourceReceipt(ref=o.ref, reading=o.value, display_revision='r1') for o in observations)
    m = model(observations)
    j = job()
    processing = j.processing_request.model_copy(update={'purpose':'operating-audit'})
    approval = j.approvals[0].model_copy(update={'purpose':'operating-audit'})
    extractions = tuple(SealedAssemblyExtraction(manifest=ArtifactManifest(
        workspace_id=m.workspace_id, artifact_id=uuid4(), version=1, kind='extraction',
        input_digest='a'*64, source_digest=digest({'refs':p['source_refs']}),
        permission_digest=j.permission_hash, compiler_digest='b'*64, dependency_digest='c'*64,
        content_hash=digest(p), private_object_key='invented', state='ready'), payload=p) for p in payloads)
    census = FrozenCensus(workspace_id=m.workspace_id, source_refs=tuple(r.ref for r in receipts),
        regions=tuple(SourceRegion(region_id=str(i),kind='section',evidence=o.evidence[0]) for i,o in enumerate(observations)),
        obligations=tuple(Obligation(obligation_id=str(i),priority='essential',expected='represented',evidence=o.evidence[0],reason='invented') for i,o in enumerate(observations)),
        source_only_context_hash='d'*64,source_only_dispatch_hash='e'*64,
        frozen_at=now-timedelta(seconds=1),census_model='openai/gpt-6.1-sol')
    request={**j.request,'messages':assembly_messages(receipts=receipts,extractions=extractions,census=census,model_id=m.model_id,version=1)}
    j=j.model_copy(update={'workspace_id':m.workspace_id,'artifact_id':m.model_id,'purpose':'operating-audit',
        'processing_request':processing,'approvals':(approval,),'request':request,'request_hash':digest(request),
        'input_tokens_upper_bound':len(json.dumps(request).encode())+2048})
    ctx=AssemblyJobContext(actor_id=uuid4(),runtime_hash='1'*64,source_registry_hash='2'*64,
        compiler_digest='b'*64,parent_registry_hash='3'*64,envelope_hash='4'*64,job=j,receipts=receipts,
        extractions=extractions,census=census,reviewed_inventories={},model_id=m.model_id,model_version=1,
        issuer_actor=uuid4(),reviewer_actor=uuid4(),expires_at=now+timedelta(seconds=30))
    return ctx,m,now


def test_versioned_assembly_context_uses_all_originals_and_exact_ids(context):
    ctx,m,now=context
    payload,evidence=ctx.validate_candidate(m.model_dump_json(),now=now)
    assert payload['operating_models']==[m.model_dump(mode='json')]
    assert set(evidence)=={'p1','p2','artifact'}
    body=json.loads(ctx.job.request['messages'][1]['content'])
    assert len(body['originals'])==len(body['extractions'])==2
    assert all(r.reading in ctx.job.request['messages'][1]['content'] for r in ctx.receipts)


@pytest.mark.parametrize('change', ('omitted','borrowed','seal','self_review','purpose','wrong_output','expired'))
def test_assembly_context_refuses_unbound_or_stale_inputs(context,change):
    from datetime import timedelta
    ctx,m,now=context
    if change=='omitted':ctx=ctx.model_copy(update={'extractions':ctx.extractions[:1]})
    elif change=='borrowed':ctx.job.request['messages'][1]['content']='borrowed source'
    elif change=='seal':ctx.extractions[0].payload['findings']=[{}]
    elif change=='self_review':ctx=ctx.model_copy(update={'reviewer_actor':ctx.issuer_actor})
    elif change=='purpose':ctx=ctx.model_copy(update={'job':ctx.job.model_copy(update={'purpose':'source-extraction'})})
    elif change=='wrong_output':m=m.model_copy(update={'version':2})
    else:now=now+timedelta(minutes=1)
    with pytest.raises((ValueError,PermissionError)):
        ctx.validate_candidate(m.model_dump_json(),now=now)


def wire_case(context):
    import hashlib
    from datetime import timedelta
    from uuid import uuid4
    from oracle_brain.operating_model.captured_assembly import AssemblyObserverContext, ObservedAssemblyWire, ObservedAssemblyProtocol
    from oracle_brain.operating_model.semantic_acceptance import sealed
    ctx,m,now=context
    raw=json.dumps({'id':'invented','model':ctx.job.request['model'],
        'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':m.model_dump_json()}}],
        # Deliberately untrusted provider creation timestamp is not observed time.
        'created':1}).encode()
    protocol=ObservedAssemblyProtocol()
    observer=AssemblyObserverContext(custodian_id=uuid4(),custodian_config_hash='5'*64,custodian_session_hash='9'*64,
        runtime_hash=ctx.runtime_hash,census_hash=sealed(ctx.census),protocol_hash=sealed(protocol),
        dispatch_id=ctx.job.dispatch_id,job_hash=sealed(ctx.job),request_hash=ctx.job.request_hash,
        key_fingerprint='7'*64,ledger_identity_hash='8'*64,expires_at=now+timedelta(seconds=30))
    observed=ObservedAssemblyWire(time_basis='complete-wire-before-local-consumer-v1',
        observer_context_hash=sealed(observer),dispatch_id=ctx.job.dispatch_id,reservation_id=uuid4(),
        job_hash=sealed(ctx.job),request_hash=ctx.job.request_hash,raw_sha256=hashlib.sha256(raw).hexdigest(),
        captured_bytes=len(raw),observed_at=now)
    return dict(context=ctx,observer=observer,expected_observer_context_hash=sealed(observer),
                protocol=protocol,expected_protocol_hash=sealed(protocol),
                observed=observed,raw=raw,now=now)


def test_captured_candidate_binds_complete_api_wire_and_model_only_content(context):
    from oracle_brain.operating_model.captured_assembly import captured_assembly_candidate
    case=wire_case(context)
    captured,evidence=captured_assembly_candidate(**case)
    assert captured.candidate['assembly_capture']['observed_wire']['observed_at']==case['now'].isoformat().replace('+00:00','Z')
    assert captured.candidate['raw_response']==context[1].model_dump_json()
    assert 'coverage' not in captured.candidate and evidence['p1']


@pytest.mark.parametrize('change',('wire','observer','length','choice','model','census_after_capture','future'))
def test_captured_candidate_refuses_unobserved_or_changed_wire(context,change):
    from datetime import timedelta
    import hashlib
    from oracle_brain.operating_model.captured_assembly import captured_assembly_candidate
    case=wire_case(context)
    if change=='observer':case['expected_observer_context_hash']='f'*64
    elif change=='wire':case['raw']+=b' '
    elif change=='census_after_capture':case['observed']=case['observed'].model_copy(update={'observed_at':case['context'].census.frozen_at})
    elif change=='future':case['observed']=case['observed'].model_copy(update={'observed_at':case['now']+timedelta(seconds=1)})
    else:
        wire=json.loads(case['raw'])
        if change=='length':wire['choices'][0]['finish_reason']='length'
        elif change=='choice':wire['choices']*=2
        else:wire['model']='openai/gpt-6-astra'
        case['raw']=json.dumps(wire).encode()
        case['observed']=case['observed'].model_copy(update={'raw_sha256':hashlib.sha256(case['raw']).hexdigest(),'captured_bytes':len(case['raw'])})
    with pytest.raises((ValueError,PermissionError)):
        captured_assembly_candidate(**case)


@pytest.mark.parametrize('value',('processing-v1',True,None,'operating_model'))
def test_extraction_profile_cannot_be_selected_from_untrusted_mode(value):
    from oracle_brain.operating_model.extraction import extraction_artifact_kinds
    with pytest.raises(PermissionError):extraction_artifact_kinds(value)


def test_explicit_processing_extraction_reuses_validator_and_exact_payload(context):
    from types import SimpleNamespace
    from oracle_brain.operating_model.extraction import persist_response, ExtractionPersistenceProfile
    from uuid import uuid4
    ctx,_,_=context;receipt=ctx.receipts[0];calls=[]
    ledger=SimpleNamespace(reviewed_inventories={},persist=lambda **kw:calls.append(kw) or kw)
    raw=json.dumps({'schema_version':1,'source_id':str(receipt.ref.source_id),
        'source_revision':receipt.ref.revision,'complete':True,'observations':[],'findings':[],'unresolved_items':[]})
    kwargs=dict(artifact_id=uuid4(),version=1,permission_digest='a'*64,compiler_digest='b'*64)
    old=persist_response(ledger,receipt,raw,**kwargs)
    new=persist_response(ledger,receipt,raw,**kwargs,persistence_profile=ExtractionPersistenceProfile.PROCESSING_V1)
    assert old['kind']=='extraction' and new['kind']=='processing_extraction_v1'
    assert old['payload']==new['payload'] and old['refs']==new['refs']
    with pytest.raises(ValueError,match='preserved'):
        persist_response(ledger,receipt,'{}',**kwargs,persistence_profile=ExtractionPersistenceProfile.PROCESSING_V1)
    assert calls[-1]['kind']=='processing_failed_extraction_v1' and calls[-1]['failed']
