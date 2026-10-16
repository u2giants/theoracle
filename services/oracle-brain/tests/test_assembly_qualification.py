"""Injected independent admission fixtures, not real assessor quality or role proof."""
from datetime import timedelta
from uuid import uuid4

import pytest
from test_assembly_context import context, wire_case
from oracle_brain.operating_model.captured_assembly import captured_assembly_candidate
from oracle_brain.operating_model.contracts import digest,ProcessingExtractionSeal
from oracle_brain.operating_model.coverage import CoverageRecord
from oracle_brain.operating_model.semantic_acceptance import (
    CRITERIA, CriterionReview, IndependentAssessment, SemanticAdmission, sealed,
)
from oracle_brain.operating_model.assembly_qualification import (
    CapturedAssemblySemanticAdmission,qualified_content_core,
    verify_captured_assembly_semantic_acceptance, final_assembly_envelope,
    verify_final_assembly_lineage,
)


@pytest.fixture
def qualified(context):
    wire=wire_case(context)
    ctx,model,now=context
    captured,evidence=captured_assembly_candidate(**wire)
    assessment=IndependentAssessment(workspace_id=model.workspace_id,census_hash=sealed(ctx.census),
        candidate_hash=captured.candidate_hash,permission_hash=ctx.job.permission_hash,
        protocol_hash=wire['observer'].protocol_hash,assessor_actor=uuid4(),assessor_model='openai/gpt-6-astra',
        assessed_at=now+timedelta(seconds=1),dispatch_receipt_hash='9'*64,raw_response_hash='a'*64,
        coverage=tuple(CoverageRecord(obligation_id=o.obligation_id,disposition='represented',
            object_ids=('p'+str(i+1),),reason='Invented exact support') for i,o in enumerate(ctx.census.obligations)),
        criteria=tuple(CriterionReview(criterion=k,verdict='pass',explanation='Injected fixture assessment',
            evidence=tuple(r.evidence for r in ctx.census.regions),object_ids=('p1','p2')) for k in sorted(CRITERIA)))
    admission=CapturedAssemblySemanticAdmission(final_envelope_hash=digest(qualified_content_core(captured,census=ctx.census,assessment=assessment)),protocol_hash=assessment.protocol_hash,runtime_hash=ctx.runtime_hash,
        source_region_register_hash=digest({'regions':[r.model_dump(mode='json') for r in ctx.census.regions]}),
        census_hash=sealed(ctx.census),assessment_hash=sealed(assessment),candidate_hash=captured.candidate_hash,
        permission_hash=ctx.job.permission_hash,reviewer_report_hash='b'*64,
        object_evidence_hash=captured.object_evidence_hash,candidate_created_at=now,
        implementer_actor=ctx.actor_id,assessor_actor=assessment.assessor_actor,
        candidate_model='openai/gpt-6.1-sol',purpose='independent-source-semantic-acceptance',expires_at=now+timedelta(seconds=25))
    receipts={r.ref.source_id:r for r in ctx.receipts}
    checked=verify_captured_assembly_semantic_acceptance(**{**wire,'now':now+timedelta(seconds=2)},
        assessment=assessment,admission=admission,trusted_admission_hashes=frozenset({sealed(admission)}),
        source_regions=ctx.census.regions,current_source=lambda w,s:receipts[s],can_read=lambda *_:True)
    payload=final_assembly_envelope(checked,census=ctx.census,assessment=assessment,admission=admission)
    # New kind literals are owned by the independently reviewed Ledger lane.
    # This fixture copies metadata solely to exercise its future guard contract.
    manifest=ctx.extractions[0].manifest.model_copy(update={'artifact_id':model.model_id,
        'kind':'processing_qualified_model_v1','content_hash':digest(payload),
        'source_digest':digest({'refs':[r.ref.model_dump(mode='json') for r in ctx.receipts]})})
    manifests={(e.manifest.artifact_id,e.manifest.version):ProcessingExtractionSeal.model_validate_json(__import__('json').dumps(
        {k:v for k,v in e.manifest.model_dump(mode='json').items() if k!='private_object_key'} |
        {'manifest_hash':sealed(e.manifest),'source_refs':e.payload['source_refs']})) for e in ctx.extractions}
    return dict(manifest=manifest,payload=payload,principal=uuid4(),now=now+timedelta(seconds=2),
        trusted_admission_hashes=frozenset({sealed(admission)}),runtime_hash=ctx.runtime_hash,
        current_source_identity=lambda w,p,s:receipts[s].ref,
        current_extraction_seal=lambda w,p,a,v:manifests[(a,v)])


def test_compile_then_final_serve_verifies_using_only_current_metadata(qualified):
    assert verify_final_assembly_lineage(**qualified) is None
    candidate={k:v for k,v in qualified['payload'].items() if k not in {'coverage','qualified_lineage','assembly_qualification'}}
    assert digest(candidate)!=digest(qualified['payload'])
    assert digest(candidate)==qualified['payload']['qualified_lineage']['candidate_hash']


@pytest.mark.parametrize('change',('trust','expired','runtime','source','extraction','body','coverage','lineage','actor'))
def test_final_serve_refuses_missing_or_changed_current_seals(qualified,change):
    q=qualified
    if change=='trust':q['trusted_admission_hashes']=frozenset()
    elif change=='expired':q['now']+=timedelta(minutes=1)
    elif change=='runtime':q['runtime_hash']='f'*64
    elif change=='source':q['current_source_identity']=lambda *_:None
    elif change=='extraction':q['current_extraction_seal']=lambda *_:None
    elif change=='actor':q['principal']=None
    else:
        if change=='body':q['payload']['raw_response']='{}'
        elif change=='coverage':q['payload']['coverage']['essential_total']=999
        else:q['payload']['qualified_lineage']['capture_hash']='e'*64
        # Even a newly sealed final artifact cannot replace trusted admission.
        q['manifest']=q['manifest'].model_copy(update={'content_hash':digest(q['payload'])})
    with pytest.raises((ValueError,PermissionError)):
        verify_final_assembly_lineage(**q)


def read_guard(q):
    from oracle_brain.operating_model.assembly_qualification import QualifiedAssemblyReadGuard
    return QualifiedAssemblyReadGuard(trusted_admissions=lambda:q['trusted_admission_hashes'],
        runtime_hash=q['runtime_hash'],current_source_identity=q['current_source_identity'],
        current_extraction_seal=q['current_extraction_seal'],
        qualified_parent_reader=lambda *_:(q['manifest'],q['payload']))


class MetadataLedger:
    def __init__(self,q):self.q=q;self.principal=q['principal']
    def read_with_manifest(self,*args):return self.q['manifest'],self.q['payload']
    def read(self,*args):return self.q['payload']


def test_default_summary_and_sdk_refuse_new_kind_even_with_authorized_ledger(qualified):
    import asyncio
    from oracle_brain.operating_model.summaries import summarize_from_ledger
    from oracle_brain.operating_model.sdk_projection import SDKProjection
    from oracle_brain.operating_model.retrieval import QueryPlan
    from oracle_brain.operating_model.assembly_qualification import read_documentary_artifact
    q=qualified;l=MetadataLedger(q);m=q['manifest']
    args=(l,m.workspace_id,m.artifact_id,m.version)
    plan=QueryPlan(view='company_overview',question='Invented',max_bytes=128*1024,page=0,page_size=25)
    with pytest.raises(PermissionError,match='explicit current'):
        summarize_from_ledger(*args,plan)
    projection=SDKProjection.__new__(SDKProjection);projection.qualification_guard=None
    with pytest.raises(PermissionError,match='explicit current'):
        asyncio.run(projection.load(*args))
    assert read_documentary_artifact(*args,qualification_guard=read_guard(q))==q['payload']
    summary=summarize_from_ledger(*args,plan,qualification_guard=read_guard(q))
    assert summary.pack.artifact_hash==m.content_hash
    q['trusted_admission_hashes']=frozenset()
    with pytest.raises(PermissionError):summary.recheck(l,qualification_guard=read_guard(q))


def test_summary_guard_rechecks_exact_qualified_parent_without_raw_original(qualified):
    from oracle_brain.operating_model.summaries import summarize_from_ledger
    from oracle_brain.operating_model.retrieval import QueryPlan
    q=qualified;l=MetadataLedger(q);m=q['manifest'];guard=read_guard(q)
    summary=summarize_from_ledger(l,m.workspace_id,m.artifact_id,m.version,
        QueryPlan(view='company_overview',question='Invented',max_bytes=128*1024,page=0,page_size=25),qualification_guard=guard)
    payload={'source_refs':q['payload']['source_refs'],'summary':summary.model_dump(mode='json')}
    manifest=m.model_copy(update={'artifact_id':uuid4(),'kind':'processing_summary_v1','content_hash':digest(payload)})
    assert guard(manifest,payload,q['principal'],q['now']) is None
    q['trusted_admission_hashes']=frozenset()
    with pytest.raises(PermissionError):guard(manifest,payload,q['principal'],q['now'])


@pytest.mark.parametrize('change',('ok','absent','expired','revoked','parent'))
def test_answer_rechecks_current_qualification_without_original_reader(qualified,change):
    from oracle_brain.operating_model.summaries import summarize_from_ledger
    from oracle_brain.operating_model.retrieval import QueryPlan
    from oracle_brain.operating_model.answer import answer_from_summary
    from oracle_brain.operating_model.assembly_qualification import QualifiedAssemblyReadGuard
    q=qualified;l=MetadataLedger(q);m=q['manifest'];guard=read_guard(q)
    summary=summarize_from_ledger(l,m.workspace_id,m.artifact_id,m.version,
        QueryPlan(view='company_overview',question='Invented',max_bytes=128*1024,page=0,page_size=25),qualification_guard=guard)
    if change=='absent':guard=None
    elif change=='expired':
        admission=q['payload']['assembly_qualification']['admission']
        admission['expires_at']=(q['now']-timedelta(seconds=1)).isoformat()
        q['manifest']=m.model_copy(update={'content_hash':digest(q['payload'])})
    elif change=='revoked':
        guard=QualifiedAssemblyReadGuard(trusted_admissions=lambda:q['trusted_admission_hashes'],
            runtime_hash=q['runtime_hash'],current_source_identity=lambda *_:None,
            current_extraction_seal=q['current_extraction_seal'],qualified_parent_reader=lambda *_:None)
    elif change=='parent':q['payload']['raw_response']='{}'
    if change=='ok':
        answer=answer_from_summary(l,summary,intent='overview',qualification_guard=guard)
        assert answer.state=='answered' and answer.citations and len(answer.records)==2
    else:
        with pytest.raises((ValueError,PermissionError)):
            answer_from_summary(l,summary,intent='overview',qualification_guard=guard)


def test_compile_deadline_is_actual_current_semantic_admission_not_summary_claim(qualified):
    q=qualified;guard=read_guard(q)
    deadline=guard.valid_until(q['manifest'],q['payload'],q['principal'],q['now'])
    assert deadline.isoformat().replace('+00:00','Z')==q['payload']['assembly_qualification']['admission']['expires_at']
    q['trusted_admission_hashes']=frozenset()
    with pytest.raises(PermissionError):guard.valid_until(q['manifest'],q['payload'],q['principal'],q['now'])


def test_processing_projection_requires_explicit_guard_and_separate_namespace():
    from oracle_brain.operating_model.sdk_projection import SDKProjection,ProcessingSDKProjection
    assert ProcessingSDKProjection.graph_prefix=='oracle_processing_v1_'
    assert SDKProjection.graph_prefix=='oracle_operating_model_v1_'
    with pytest.raises(PermissionError):ProcessingSDKProjection(qualification_guard=None)


def test_legacy_v1_admission_cannot_authorize_new_qualified_content(qualified):
    import json
    q=qualified;raw=q['payload']['assembly_qualification']['admission']
    legacy=SemanticAdmission.model_validate_json(json.dumps({k:v for k,v in raw.items() if k!='final_envelope_hash'} | {'schema_version':1}))
    q['payload']['assembly_qualification']['admission']=legacy.model_dump(mode='json')
    q['trusted_admission_hashes']=frozenset({sealed(legacy)})
    q['manifest']=q['manifest'].model_copy(update={'content_hash':digest(q['payload'])})
    with pytest.raises((ValueError,PermissionError)):verify_final_assembly_lineage(**q)
