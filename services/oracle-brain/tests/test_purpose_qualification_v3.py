"""Injected phase/admission seals prove source consistency, not paid/live quality."""
from datetime import timedelta
from uuid import uuid4
import hashlib,json
import pytest
from test_assembly_context import context
from test_purpose_assembly_v2 import make_v2
from oracle_brain.operating_model.contracts import canonical_bytes,digest,ProcessingExtractionSeal
from oracle_brain.operating_model.assembly_context import assembly_messages
from oracle_brain.operating_model.purpose_context import PHASE_CONTRACTS,source_population_digest
from oracle_brain.operating_model.purpose_profiles_v2 import PurposePrivateContextV2
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.operating_model.purpose_capture_v2 import (
    ObservedAssemblyProtocolV2,AssemblyObserverContextV2,ObservedAssemblyWireV2,captured_assembly_candidate_v2)
from oracle_brain.operating_model.purpose_qualification_v3 import (
    PurposeSemanticAdmissionV3,PurposeAssemblyQualificationV3,purpose_qualified_content_core_v3,
    verify_purpose_final_assembly_v3,compile_purpose_assembly_v3)
from oracle_brain.operating_model.semantic_acceptance import CRITERIA,CriterionReview,IndependentAssessment,sealed
from oracle_brain.operating_model.coverage import CoverageRecord


def phase_commit(phase,ctx,*,actor,login,runtime,permission,context_hash,job_hash,request_hash,raw_hash,at):
    return PhaseResponseCommitV2(phase=phase,operation='chat',processing_purpose=PHASE_CONTRACTS[phase][0],
        dispatch_id=ctx.job.dispatch_id if phase=='assembly' else uuid4(),workspace_id=ctx.job.workspace_id,actor_id=actor,provider_login=login,
        actual_caller_login=login,runtime_hash=runtime,descriptor_hash='a'*64,operation_approval_hash='b'*64,
        source_refs=tuple(r.ref for r in ctx.receipts),population_digest=source_population_digest(tuple(r.ref for r in ctx.receipts)),
        context_hash=context_hash,parent_registry_hash=ctx.parent_registry_hash,current_proof_hash='c'*64,
        parent_witness_hash='d'*64,account_policy_hash='e'*64,model=PHASE_CONTRACTS[phase][2],
        valid_until=at+timedelta(seconds=1),job_hash=job_hash,request_hash=request_hash,permission_hash=permission,
        budget_identity_hash='f'*64,raw_response_hash=raw_hash,native_custody_receipt_hash='0'*64,committed_at=at)


def original_qualified_fixture_v3(context,*,admission_lifetime_seconds):
    if type(admission_lifetime_seconds) is not int or admission_lifetime_seconds not in (25,115):
        raise ValueError("fixed fresh invented semantic lifetimes only")
    ctx,model,now=make_v2(context)
    census_commit=phase_commit('census',ctx,actor=uuid4(),login='census_fixture',runtime='3'*64,
        permission='4'*64,context_hash='5'*64,job_hash='6'*64,request_hash='7'*64,raw_hash='8'*64,at=ctx.census.frozen_at)
    census=ctx.census.model_copy(update={'source_only_context_hash':census_commit.context_hash,
        'source_only_dispatch_hash':sealed(census_commit)})
    request={**ctx.job.request,'messages':assembly_messages(receipts=ctx.receipts,extractions=ctx.extractions,
        census=census,model_id=ctx.model_id,version=ctx.model_version)}
    ctx=ctx.model_copy(update={'census':census,'job':ctx.job.model_copy(update={'request':request,'request_hash':digest(request)})})
    protocol=ObservedAssemblyProtocolV2()
    raw=canonical_bytes({'model':ctx.job.request['model'],'choices':[{'index':0,'finish_reason':'stop',
        'message':{'role':'assistant','content':model.model_dump_json()}}]})
    observer=AssemblyObserverContextV2(custodian_id=uuid4(),custodian_config_hash='a'*64,custodian_session_hash='b'*64,
        runtime_hash=ctx.runtime_hash,census_hash=sealed(census),protocol_hash=sealed(protocol),dispatch_id=ctx.job.dispatch_id,
        job_hash=sealed(ctx.job),request_hash=ctx.job.request_hash,key_fingerprint='c'*64,ledger_identity_hash='d'*64,
        expires_at=ctx.expires_at,assembly_context_hash=sealed(ctx),handoff_hash=sealed(ctx.handoff))
    observed=ObservedAssemblyWireV2(observer_context_hash=sealed(observer),assembly_context_hash=sealed(ctx),
        handoff_hash=sealed(ctx.handoff),dispatch_id=ctx.job.dispatch_id,reservation_id=uuid4(),job_hash=sealed(ctx.job),
        request_hash=ctx.job.request_hash,raw_sha256=hashlib.sha256(raw).hexdigest(),captured_bytes=len(raw),observed_at=now)
    wire=dict(context=ctx,observer=observer,expected_observer_context_hash=sealed(observer),protocol=protocol,
        expected_protocol_hash=sealed(protocol),observed=observed,raw=raw,now=now+timedelta(milliseconds=100))
    captured,evidence=captured_assembly_candidate_v2(**wire)
    assembly_commit=phase_commit('assembly',ctx,actor=ctx.actor_id,login=ctx.provider_login,runtime=ctx.runtime_hash,
        permission=ctx.job.permission_hash,context_hash=sealed(PurposePrivateContextV2(phase='assembly',job=ctx.job,assembly=ctx)),
        job_hash=sealed(ctx.job),request_hash=ctx.job.request_hash,raw_hash=observed.raw_sha256,
        at=now+timedelta(milliseconds=100))
    assessor=uuid4()
    assessment_commit=phase_commit('assessment',ctx,actor=assessor,login='assessor_fixture',runtime='6'*64,
        permission='7'*64,context_hash='8'*64,job_hash='9'*64,request_hash='a'*64,raw_hash='b'*64,
        at=now+timedelta(milliseconds=200))
    assessment=IndependentAssessment(workspace_id=model.workspace_id,census_hash=sealed(census),candidate_hash=captured.candidate_hash,
        permission_hash=assessment_commit.permission_hash,protocol_hash=sealed(protocol),assessor_actor=assessor,
        assessor_model='openai/gpt-6-astra',assessed_at=assessment_commit.committed_at,
        dispatch_receipt_hash=sealed(assessment_commit),raw_response_hash=assessment_commit.raw_response_hash,
        coverage=tuple(CoverageRecord(obligation_id=o.obligation_id,disposition='represented',object_ids=('p'+str(i+1),),
            reason='Injected exact support') for i,o in enumerate(census.obligations)),
        criteria=tuple(CriterionReview(criterion=k,verdict='pass',explanation='Injected assessment',
            evidence=tuple(r.evidence for r in census.regions),object_ids=('p1','p2')) for k in sorted(CRITERIA)))
    commits=(census_commit,assembly_commit,assessment_commit)
    core=purpose_qualified_content_core_v3(captured,census=census,assessment=assessment,phase_commits=commits)
    admission=PurposeSemanticAdmissionV3(workspace_id=ctx.job.workspace_id,issuer_actor=uuid4(),reviewer_actor=uuid4(),
        protocol_hash=sealed(protocol),runtime_hash=ctx.compiler_digest,source_region_register_hash=digest({'regions':[r.model_dump(mode='json') for r in census.regions]}),
        census_hash=sealed(census),assessment_hash=sealed(assessment),candidate_hash=captured.candidate_hash,
        permission_hash=assessment.permission_hash,reviewer_report_hash='c'*64,object_evidence_hash=captured.object_evidence_hash,
        candidate_created_at=observed.observed_at,implementer_actor=ctx.actor_id,assessor_actor=assessor,candidate_model='openai/gpt-6.1-sol',
        purpose='independent-source-semantic-acceptance',expires_at=now+timedelta(seconds=admission_lifetime_seconds),final_envelope_hash=digest(core),
        context_hash=sealed(ctx),handoff_hash=sealed(ctx.handoff),compiler_actor=uuid4(),compiler_login='compiler_fixture',
        compiler_permission_hash='d'*64,assembly_permission_hash=ctx.job.permission_hash,assembly_runtime_hash=ctx.runtime_hash,
        assessment_runtime_hash=assessment_commit.runtime_hash,census_commit_hash=sealed(census_commit),
        assembly_commit_hash=sealed(assembly_commit),assessment_commit_hash=sealed(assessment_commit))
    from oracle_brain.operating_model.purpose_qualification_v3 import _verify_phase_bindings
    _verify_phase_bindings(ctx,captured,assessment,admission,{c.phase:c for c in commits})
    payload={**core,'assembly_qualification':PurposeAssemblyQualificationV3(admission=admission).model_dump(mode='json')}
    manifest=ctx.extractions[0].manifest.model_copy(update={'artifact_id':model.model_id,'kind':'processing_qualified_model_v1',
        'permission_digest':admission.compiler_permission_hash,'content_hash':digest(payload),
        'source_digest':digest({'refs':[r.ref.model_dump(mode='json') for r in ctx.receipts]})})
    seals={(e.manifest.artifact_id,e.manifest.version):ProcessingExtractionSeal.model_validate_json(canonical_bytes(
        {k:v for k,v in e.manifest.model_dump(mode='json').items() if k!='private_object_key'}|
        {'manifest_hash':sealed(e.manifest),'source_refs':e.payload['source_refs']})) for e in ctx.extractions}
    refs={r.ref.source_id:r.ref for r in ctx.receipts}
    return dict(manifest=manifest,payload=payload,principal=uuid4(),now=now+timedelta(seconds=5),
        trusted_admission_hashes=frozenset({sealed(admission)}),runtime_hash=admission.runtime_hash,
        current_source_identity=lambda w,p,s:refs[s],current_extraction_seal=lambda w,p,a,v:seals[(a,v)],
        admission=admission,commits=commits,wire=wire,assessment=assessment)


@pytest.fixture
def qualified_v3(context):
    return original_qualified_fixture_v3(context,admission_lifetime_seconds=25)

def serving(q):
    return {k:v for k,v in q.items() if k not in {'admission','commits','wire','assessment'}}


def test_schema3_serves_minimized_current_metadata_after_historical_phase_expiry(qualified_v3):
    q=qualified_v3
    assert all(c.valid_until<q['now'] for c in q['commits'])
    assert q['admission'].compiler_permission_hash!=q['admission'].permission_hash
    assert verify_purpose_final_assembly_v3(**serving(q)) is None
    from oracle_brain.operating_model.assembly_qualification import verify_final_assembly_lineage
    with pytest.raises(ValueError):verify_final_assembly_lineage(**serving(q))


@pytest.mark.parametrize('damage',('trust','expiry','permission','source','handoff','context','phase','workspace'))
def test_schema3_never_borrows_legacy_or_changed_current_qualification(qualified_v3,damage):
    q=serving(qualified_v3)
    if damage=='trust':q['trusted_admission_hashes']=frozenset()
    elif damage=='expiry':q['now']=qualified_v3['admission'].expires_at
    elif damage=='permission':q['manifest']=q['manifest'].model_copy(update={'permission_digest':qualified_v3['admission'].permission_hash})
    elif damage=='source':q['current_source_identity']=lambda *_:None
    elif damage in {'handoff','context','phase'}:
        key={'handoff':'handoff_hash','context':'context_hash','phase':'assessment_commit_hash'}[damage]
        q['payload']=__import__('copy').deepcopy(q['payload']);q['payload']['qualified_lineage'][key]='f'*64
    elif damage=='workspace':q['manifest']=q['manifest'].model_copy(update={'workspace_id':uuid4()})
    with pytest.raises((PermissionError,ValueError,KeyError)):verify_purpose_final_assembly_v3(**q)


def test_no_typed_or_boolean_fake_compiler_can_trigger_private_compile_parsing(qualified_v3):
    q=qualified_v3
    with pytest.raises(PermissionError,match='actual explicit compiler'):
        compile_purpose_assembly_v3(compiler_ledger=True,**{k:v for k,v in q['wire'].items() if k!='now'},
            assessment=q['assessment'],admission=q['admission'],trusted_admission_hashes=q['trusted_admission_hashes'],
            source_regions=q['wire']['context'].census.regions,phase_commits=q['commits'],
            census_private_context=None,assessment_private_context=None,census_raw=b'',assessment_raw=b'',now=q['now'])


def test_explicit_embedding_metadata_bridge_uses_typed_seal_without_blob_location(qualified_v3):
    from oracle_brain.operating_model.contracts import ProcessingQualifiedProjectionSealV2
    from oracle_brain.operating_model.assembly_qualification import _verify_final_assembly_lineage
    from oracle_brain.operating_model.purpose_qualification_v3 import PurposeFinalLineageV3,_serve_schema3
    q=qualified_v3;m=q['manifest'];refs=tuple(r.ref for r in q['wire']['context'].receipts)
    extractions=tuple(q['current_extraction_seal'](m.workspace_id,q['principal'],e.manifest.artifact_id,e.manifest.version)
        for e in q['wire']['context'].extractions)
    fields=m.model_dump(mode='python');fields.pop('private_object_key');fields['schema_version']=2
    seal=ProcessingQualifiedProjectionSealV2(**fields,manifest_hash=sealed(m),source_refs=refs,extraction_seals=extractions)
    assert 'private_object_key' not in seal.model_dump() and not isinstance(seal,type(m))
    def check(actual,payload=q['payload'],trust=q['trusted_admission_hashes']):
        return _verify_final_assembly_lineage(actual,payload,q['principal'],q['now'],
            trusted_admission_hashes=trust,runtime_hash=q['runtime_hash'],
            current_source_identity=q['current_source_identity'],current_extraction_seal=q['current_extraction_seal'],
            qualification_model=PurposeAssemblyQualificationV3,lineage_model=PurposeFinalLineageV3,
            protocol_model=ObservedAssemblyProtocolV2,wire_model=ObservedAssemblyWireV2,
            permission_field='compiler_permission_hash',additional_check=_serve_schema3,
            metadata_model=ProcessingQualifiedProjectionSealV2)
    assert check(seal) is None
    with pytest.raises(Exception):check(m)
    with pytest.raises(Exception):check(seal,trust=frozenset())
    for field in ('content_hash','source_digest','permission_digest','compiler_digest'):
        with pytest.raises(Exception):check(seal.model_copy(update={field:'f'*64}))


def test_independent_assessor_cannot_be_current_compiler_actor_or_login(qualified_v3):
    q=qualified_v3;admission=q['admission']
    with pytest.raises(PermissionError):
        PurposeSemanticAdmissionV3.model_validate(admission.model_copy(update={'compiler_actor':admission.assessor_actor}).model_dump(mode='python'))
    from oracle_brain.operating_model.purpose_qualification_v3 import _verify_phase_bindings
    commits={c.phase:c for c in q['commits']}
    altered=admission.model_copy(update={'compiler_login':commits['assessment'].provider_login})
    captured,_=captured_assembly_candidate_v2(**q['wire'])
    with pytest.raises(PermissionError):_verify_phase_bindings(q['wire']['context'],captured,q['assessment'],altered,commits)
