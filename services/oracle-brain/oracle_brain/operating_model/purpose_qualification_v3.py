"""Explicit schema3 qualification: current compiler, historical paid phase seals.

No issuer or trust registry is created. The existing externally trusted semantic
admission registry must explicitly admit this schema/protocol and every exact
phase commit. Historical phase grants need not stay active after authorized
response commit; current compiler/source/admission authority remains mandatory.
"""
from datetime import datetime
import json
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator

from .assembly_qualification import (
    CapturedAssemblySemanticAdmission,FinalAssemblyLineage,QualifiedAssemblyReadGuard,
    _qualified_content_core,_verify_final_assembly_lineage)
from .contracts import StrictRecord,digest
from .purpose_context import HASH,LOGIN
from .purpose_capture_v2 import (
    CapturedAssemblyCandidateV2,CapturedConsolidationCandidateV1,ObservedConsolidationProtocolV1,ObservedAssemblyProtocolV2,ObservedAssemblyWireV2,
    captured_assembly_candidate_v2)
from .purpose_profiles_v2 import PurposePrivateContextV2
from .purpose_receipts_v2 import PhaseResponseCommitV2
from .semantic_acceptance import sealed,_validate_semantic_bindings,_validate_semantic_evidence
from .semantic_runtime import ledger_object_evidence


class PurposeSemanticAdmissionV3(CapturedAssemblySemanticAdmission):
    schema_version: Literal[3]=3
    qualification_purpose: Literal['captured-assembly-semantic-admission-v3']='captured-assembly-semantic-admission-v3'
    workspace_id: UUID
    compiler_profile: Literal['candidate-compiler']='candidate-compiler'
    issuer_actor: UUID
    reviewer_actor: UUID
    context_schema: Literal['purpose-assembly-context-v2','purpose-consolidation-context-v1']='purpose-assembly-context-v2'
    context_hash: str=Field(pattern=HASH)
    handoff_hash: str=Field(pattern=HASH)
    captured_schema: Literal['purpose-captured-assembly-v2','purpose-captured-consolidation-v1']='purpose-captured-assembly-v2'
    compiler_actor: UUID
    compiler_login: str=Field(pattern=LOGIN)
    compiler_permission_hash: str=Field(pattern=HASH)
    assembly_permission_hash: str=Field(pattern=HASH)
    assembly_runtime_hash: str=Field(pattern=HASH)
    assessment_runtime_hash: str=Field(pattern=HASH)
    census_commit_hash: str=Field(pattern=HASH)
    assembly_commit_hash: str=Field(pattern=HASH)
    assessment_commit_hash: str=Field(pattern=HASH)

    @model_validator(mode='after')
    def independent_qualification(self):
        if (self.context_schema=='purpose-consolidation-context-v1') != (self.captured_schema=='purpose-captured-consolidation-v1'):
            raise PermissionError('explicit consolidation context/capture pair required')
        if (self.issuer_actor==self.reviewer_actor or self.compiler_actor==self.assessor_actor
                or {self.issuer_actor,self.reviewer_actor}&{self.compiler_actor,self.implementer_actor,self.assessor_actor}):
            raise PermissionError('actual separately appointed independent issuer/reviewer required')
        return self


class PurposeFinalLineageV3(FinalAssemblyLineage):
    schema_version: Literal[3]=3
    kind: Literal['purpose-captured-assembly-qualified-content-v3']='purpose-captured-assembly-qualified-content-v3'
    context_hash: str=Field(pattern=HASH)
    handoff_hash: str=Field(pattern=HASH)
    census_commit_hash: str=Field(pattern=HASH)
    assembly_commit_hash: str=Field(pattern=HASH)
    assessment_commit_hash: str=Field(pattern=HASH)


class PurposeAssemblyQualificationV3(StrictRecord):
    schema_version: Literal[3]=3
    admission: PurposeSemanticAdmissionV3


def _phase_commits(commits):
    if (type(commits) is not tuple or len(commits)!=3
            or any(type(c) is not PhaseResponseCommitV2 for c in commits)
            or {c.phase for c in commits}!={'census','assembly','assessment'}):
        raise PermissionError('three exact observed authorized paid phase commits required')
    return {c.phase:c for c in commits}


def purpose_qualified_content_core_v3(captured,*,census,assessment,phase_commits):
    if type(captured) not in {CapturedAssemblyCandidateV2,CapturedConsolidationCandidateV1}:
        raise PermissionError('exact purpose V2 capture required for schema3')
    commits=_phase_commits(phase_commits)
    return _qualified_content_core(captured,census=census,assessment=assessment,
        lineage_model=PurposeFinalLineageV3,lineage_extra={
            'context_hash':captured.context_hash,'handoff_hash':captured.handoff_hash,
            **{phase+'_commit_hash':sealed(commit) for phase,commit in commits.items()}})


def _verify_phase_bindings(context,captured,assessment,admission,commits):
    refs=tuple(r.ref for r in context.receipts)
    census,assembly,assessor=(commits[k] for k in ('census','assembly','assessment'))
    expected_private=PurposePrivateContextV2(phase='assembly',job=context.job,assembly=context)
    if (any(c.workspace_id!=context.job.workspace_id or c.source_refs!=refs for c in commits.values())
            or census.context_hash!=context.census.source_only_context_hash
            or sealed(census)!=context.census.source_only_dispatch_hash
            or not census.committed_at==context.census.frozen_at<captured.observed_wire.observed_at
            or assembly.actor_id!=context.actor_id or assembly.provider_login!=context.provider_login
            or assembly.runtime_hash!=admission.assembly_runtime_hash
            or assembly.permission_hash!=admission.assembly_permission_hash
            or assembly.dispatch_id!=context.job.dispatch_id
            or assembly.job_hash!=sealed(context.job) or assembly.request_hash!=context.job.request_hash
            or assembly.context_hash!=sealed(expected_private)
            or assembly.raw_response_hash!=captured.observed_wire.raw_sha256
            or not captured.observed_wire.observed_at<=assembly.committed_at
            or assessor.actor_id!=admission.assessor_actor or assessor.actor_id==assembly.actor_id
            or assessor.provider_login in {assembly.provider_login,admission.compiler_login}
            or assessor.runtime_hash!=admission.assessment_runtime_hash
            or assessor.permission_hash!=admission.permission_hash
            or assessor.raw_response_hash!=assessment.raw_response_hash
            or sealed(assessor)!=assessment.dispatch_receipt_hash
            or not assembly.committed_at<=assessor.committed_at==assessment.assessed_at
            or context.actor_id!=admission.implementer_actor
            or context.runtime_hash!=admission.assembly_runtime_hash
            or context.job.permission_hash!=admission.assembly_permission_hash
            or captured.context_hash!=admission.context_hash or captured.handoff_hash!=admission.handoff_hash
            or any(sealed(c)!=getattr(admission,phase+'_commit_hash') for phase,c in commits.items())):
        raise PermissionError('schema3 must bind actual independent historical phase commits and separate authorities')


def _verify_historical_private_phase(private,commit):
    """Pure replay of exact admitted historical request, never current authority."""
    from .acceptance_profiles import validate_context
    from oracle_brain.provider_policy import authorize
    if (type(private) is not PurposePrivateContextV2 or private.phase!=commit.phase
            or sealed(private)!=commit.context_hash or sealed(private.job)!=commit.job_hash
            or private.job.dispatch_id!=commit.dispatch_id
            or private.job.request_hash!=commit.request_hash or private.job.permission_hash!=commit.permission_hash
            or private.context.actor_id!=commit.actor_id or private.context.runtime_hash!=commit.runtime_hash):
        raise PermissionError('historical phase private input differs from actual admitted commit')
    type(private).model_validate(private.model_dump(mode='python'))
    approval=authorize(private.job.processing_request,list(private.job.approvals),now=commit.committed_at)
    if commit.committed_at>=private.job.pricing.expires_at:
        raise PermissionError('historical phase committed after original pricing horizon')
    validate_context(private.context,private.job.request,
        trusted_context_hash=sealed(private.context),runtime_hash=commit.runtime_hash,
        permission_hash=commit.permission_hash,now=commit.committed_at)


def compile_purpose_assembly_v3(*,compiler_ledger,context,observer,expected_observer_context_hash,
        protocol,expected_protocol_hash,observed,raw,assessment,admission,trusted_admission_hashes,
        source_regions,phase_commits,census_private_context,assessment_private_context,census_raw,assessment_raw,now):
    """Actual compiler-only original validation; never impersonate an assessor.

    The R5 worker must additionally hold its actual private-custody appointment
    before reading the supplied phase copies/wire. This function checks current
    compiler source authority before parsing any candidate bytes and again after
    pure validation. Existing external admission is consumed, never manufactured.
    """
    import psycopg
    from .processing_ledger import require_explicit_compiler_ledger_v3
    require_explicit_compiler_ledger_v3(compiler_ledger)
    if type(admission) is not PurposeSemanticAdmissionV3:
        raise PermissionError('actual compiler ledger and explicitly admitted semantic schema3 required')
    b=compiler_ledger.processing_sources.binding
    if (sealed(admission) not in trusted_admission_hashes or now>=admission.expires_at
            or compiler_ledger.principal!=admission.compiler_actor or b.principal!=admission.compiler_actor
            or b.expected_session_role!=admission.compiler_login or b.runtime_hash!=admission.runtime_hash
            or context.job.workspace_id!=admission.workspace_id):
        raise PermissionError('current actual compiler/external schema3 qualification differs')
    refs=tuple(r.ref for r in context.receipts)
    def current_compiler():
        with psycopg.connect(compiler_ledger.url) as conn:
            compiler_ledger.processing_sources._check(conn)
            row=conn.execute('SELECT session_user,clock_timestamp()').fetchone()
            if row[0]!=admission.compiler_login or row[1]>=min(admission.expires_at,b.expires_at):
                raise PermissionError('actual current compiler login/expiry unavailable')
        return compiler_ledger.authorize_refs(refs,context.job.workspace_id)
    receipts=current_compiler()
    commits=_phase_commits(phase_commits)
    # Historical context validation is bound to the ACTUAL admitted response
    # commit, not a caller-invented clock or renewal of that phase's permission.
    captured,evidence=captured_assembly_candidate_v2(context=context,observer=observer,
        expected_observer_context_hash=expected_observer_context_hash,protocol=protocol,
        expected_protocol_hash=expected_protocol_hash,observed=observed,raw=raw,
        now=commits['assembly'].committed_at)
    _verify_phase_bindings(context,captured,assessment,admission,commits)
    _verify_historical_private_phase(census_private_context,commits['census'])
    _verify_historical_private_phase(assessment_private_context,commits['assessment'])
    assessor_context=assessment_private_context.assessment
    if (census_private_context.census.scope.receipts!=context.receipts
            or assessor_context.scope.receipts!=context.receipts
            or assessor_context.census!=context.census
            or assessor_context.candidate!=captured.candidate
            or assessor_context.candidate_hash!=captured.candidate_hash
            or assessor_context.candidate_created_at!=observed.observed_at):
        raise PermissionError('historical independently paid inputs differ from exact source/candidate')
    # Actual complete paid wire, not an independently rewritten assessment body.
    import hashlib
    from .captured_assembly import _observed_model_content
    from .acceptance_profiles import CensusPayload,AssessmentPayload
    from .native_factory import _unique_object,_deny_constant
    for phase,wire,model in (('census',census_raw,CensusPayload),('assessment',assessment_raw,AssessmentPayload)):
        if type(wire) is not bytes or hashlib.sha256(wire).hexdigest()!=commits[phase].raw_response_hash:
            raise PermissionError('historical actual paid phase wire differs from its qualified custody')
        content=_observed_model_content(wire,commits[phase].model)
        decoded=json.loads(content,object_pairs_hook=_unique_object,parse_constant=_deny_constant)
        parsed=model.model_validate_json(canonical_bytes(decoded))
        if phase=='census':
            if parsed.obligations!=context.census.obligations or census_private_context.census.scope.regions!=context.census.regions:
                raise PermissionError('frozen census differs from actual source-only generated payload')
        else:
            expected={k:getattr(assessment,k) for k in ('coverage','criteria','detail_gap_ids','detail_gap_owners')}
            if parsed!=AssessmentPayload.model_validate(expected):
                raise PermissionError('independent assessment differs from actual paid content')
    actual=ledger_object_evidence(captured.candidate,workspace_id=context.job.workspace_id,
        receipts={str(k):v for k,v in receipts.items()},inventories=context.reviewed_inventories)
    if actual!=evidence:
        raise PermissionError('current compiler originals differ from historical captured support')
    _validate_semantic_bindings(census=context.census,assessment=assessment,admission=admission,
        trusted_admission_hashes=trusted_admission_hashes,source_regions=source_regions,
        candidate=captured.candidate,object_evidence=actual,runtime_hash=b.runtime_hash,
        permission_hash=assessment.permission_hash,candidate_created_at=observed.observed_at,now=now)
    _validate_semantic_evidence(census=context.census,assessment=assessment,source_regions=source_regions,
        object_evidence=actual,receipts={receipt.ref:receipt for receipt in receipts.values()})
    core=purpose_qualified_content_core_v3(captured,census=context.census,assessment=assessment,phase_commits=phase_commits)
    if digest(core)!=admission.final_envelope_hash:
        raise PermissionError('external schema3 does not admit exact minimized final core')
    current_compiler()
    return {**core,'assembly_qualification':PurposeAssemblyQualificationV3(admission=admission).model_dump(mode='json')}


def _serve_schema3(capture,lineage,admission,principal):
    if (any(ref.workspace_id!=admission.workspace_id for ref in lineage.source_refs)
            or capture.get('context_schema')!=admission.context_schema
            or capture.get('candidate_schema')!=admission.captured_schema
            or capture.get('assembly_context_hash')!=admission.context_hash
            or capture.get('handoff_hash')!=admission.handoff_hash
            or capture.get('observed_wire',{}).get('assembly_context_hash')!=admission.context_hash
            or capture.get('observed_wire',{}).get('handoff_hash')!=admission.handoff_hash
            or lineage.context_hash!=admission.context_hash or lineage.handoff_hash!=admission.handoff_hash
            or any(getattr(lineage,p+'_commit_hash')!=getattr(admission,p+'_commit_hash')
                   for p in ('census','assembly','assessment'))):
        raise PermissionError('current schema3 context/handoff/paid-phase lineage differs')


def verify_purpose_final_assembly_v3(manifest,payload,principal,now,*,trusted_admission_hashes,
        runtime_hash,current_source_identity,current_extraction_seal):
    return _verify_final_assembly_lineage(manifest,payload,principal,now,
        trusted_admission_hashes=trusted_admission_hashes,runtime_hash=runtime_hash,
        current_source_identity=current_source_identity,current_extraction_seal=current_extraction_seal,
        qualification_model=PurposeAssemblyQualificationV3,lineage_model=PurposeFinalLineageV3,
        protocol_model=(ObservedConsolidationProtocolV1 if payload.get('assembly_capture',{}).get('candidate_schema')=='purpose-captured-consolidation-v1' else ObservedAssemblyProtocolV2),wire_model=ObservedAssemblyWireV2,
        permission_field='compiler_permission_hash',additional_check=_serve_schema3)


class PurposeQualifiedAssemblyReadGuardV3(QualifiedAssemblyReadGuard):
    """Explicit schema3 only; inherited summary replay rechecks this exact parent."""
    @classmethod
    def for_full_compiler_parent_v3(cls,*,trusted_admissions,runtime_hash,current_source_identity,
            current_extraction_seal,qualified_parent_reader):
        from .processing_ledger import PurposeProcessingCompilerLedgerV3
        if (cls is not PurposeQualifiedAssemblyReadGuardV3
                or type(getattr(qualified_parent_reader,'__self__',None)) is not PurposeProcessingCompilerLedgerV3
                or getattr(qualified_parent_reader,'__func__',None) is not
                    PurposeProcessingCompilerLedgerV3.read_validated_qualified_parent_v3):
            raise PermissionError('exact completed full compiler parent boundary required')
        guard=cls(trusted_admissions=trusted_admissions,runtime_hash=runtime_hash,
            current_source_identity=current_source_identity,current_extraction_seal=current_extraction_seal,
            qualified_parent_reader=qualified_parent_reader)
        guard._full_parent_v3=qualified_parent_reader
        return guard

    def _validated_summary_parent_v3(self,manifest,payload,principal,now):
        from .processing_ledger import PurposeProcessingCompilerLedgerV3,ValidatedQualifiedParentV3
        from .summaries import DocumentarySummary
        from .retrieval import build_pack
        parent_reader=self._full_parent_v3
        if (type(getattr(parent_reader,'__self__',None)) is not PurposeProcessingCompilerLedgerV3
                or getattr(parent_reader,'__func__',None) is not
                    PurposeProcessingCompilerLedgerV3.read_validated_qualified_parent_v3
                or parent_reader.__self__.principal!=principal):
            raise PermissionError('exact current compiler parent method required')
        summary=DocumentarySummary.model_validate_json(canonical_bytes(payload['summary']));pack=summary.pack
        if (manifest.kind!='processing_summary_v1' or manifest.state!='ready'
                or digest(payload)!=manifest.content_hash or pack.workspace_id!=manifest.workspace_id
                or pack.artifact_id==manifest.artifact_id
                or summary.summary_hash!=digest(pack.model_dump(mode='json'))
                or payload['source_refs']!=[r.model_dump(mode='json') for r in pack.source_refs]):
            raise PermissionError('qualified summary envelope or parent identity differs')
        result=parent_reader(pack.workspace_id,pack.artifact_id,pack.version)
        if type(result) is not ValidatedQualifiedParentV3:
            raise PermissionError('actual completed parent result required')
        parent=result.manifest;body=json.loads(result.canonical_body)
        if (parent.kind!='processing_qualified_model_v1' or parent.state!='ready'
                or parent.workspace_id!=pack.workspace_id or parent.artifact_id!=pack.artifact_id
                or parent.version!=pack.version or parent.content_hash!=pack.artifact_hash
                or digest(body)!=parent.content_hash or body['source_refs']!=payload['source_refs']
                or result.valid_until<=now):
            raise PermissionError('qualified summary requires exact current immutable parent')
        if build_pack(body,pack.plan)!=pack.contents:
            raise PermissionError('qualified summary content differs from current admitted parent')
        if result.valid_until<=parent_reader.__self__.clock():
            raise PermissionError('parent authority expired during summary validation')
        return result.valid_until

    def _validated_recommendation_parent_v1(self,manifest,payload,principal,now):
        from .consolidation_recommendations_v1 import QualifiedRecommendationsV1,validate_recommendation_parent
        from .processing_ledger import PurposeProcessingCompilerLedgerV3,ValidatedQualifiedParentV3
        reader=getattr(self,'_full_parent_v3',None)
        if (type(getattr(reader,'__self__',None)) is not PurposeProcessingCompilerLedgerV3
                or getattr(reader,'__func__',None) is not PurposeProcessingCompilerLedgerV3.read_validated_qualified_parent_v3
                or reader.__self__.principal!=principal):
            raise PermissionError('exact current canonical qualified parent owner required')
        body=QualifiedRecommendationsV1.model_validate_json(canonical_bytes(payload['recommendations']))
        result=reader(manifest.workspace_id,body.parent_model_id,body.parent_version)
        if type(result) is not ValidatedQualifiedParentV3:raise PermissionError('validated immutable parent required')
        import json
        validate_recommendation_parent(manifest,payload,result.manifest,json.loads(result.canonical_body))
        return result.valid_until

    def __call__(self,manifest,payload,principal,now):
        if manifest.kind=='processing_recommendation_v1':
            self._validated_recommendation_parent_v1(manifest,payload,principal,now)
            return None
        if manifest.kind=='processing_summary_v1' and hasattr(self,'_full_parent_v3'):
            self._validated_summary_parent_v3(manifest,payload,principal,now)
            return None
        if manifest.kind=='processing_qualified_model_v1':
            return verify_purpose_final_assembly_v3(manifest,payload,principal,now,
                trusted_admission_hashes=self._trust(),runtime_hash=self._runtime,
                current_source_identity=self._source,current_extraction_seal=self._extraction)
        return super().__call__(manifest,payload,principal,now)

    def valid_until(self,manifest,payload,principal,now):
        if manifest.kind=='processing_recommendation_v1':
            return self._validated_recommendation_parent_v1(manifest,payload,principal,now)
        if manifest.kind=='processing_summary_v1' and hasattr(self,'_full_parent_v3'):
            return self._validated_summary_parent_v3(manifest,payload,principal,now)
        if manifest.kind!='processing_qualified_model_v1':
            return super().valid_until(manifest,payload,principal,now)
        self(manifest,payload,principal,now)
        return PurposeAssemblyQualificationV3.model_validate_json(
            canonical_bytes(payload['assembly_qualification'])).admission.expires_at


from .contracts import canonical_bytes


def _verify_embedding_projection(*,resolver,context,semantic_registry,now,connection,context_type):
    """Actual own-role metadata eligibility; no raw getter or fake manifest.

    The current SQL seal authenticates relational currentness and private blob
    hash, not its body semantics. Exact externally admitted schema3 plus the
    immutable body/projection hashes supply those separate checks.
    """
    from .authority_adapter import PurposeSourceResolverV2
    from .contracts import ProcessingQualifiedProjectionSealV2
    from .semantic_registry_v3 import CurrentSemanticAdmissionsV3
    if (type(resolver) is not PurposeSourceResolverV2 or type(context) is not context_type
            or type(semantic_registry) is not CurrentSemanticAdmissionsV3
            or resolver.binding.phase!='embedding' or resolver.binding.caller_kind!='provider'
            or resolver.binding.source.profile!='gateway-metadata'
            or resolver.binding.source.principal!=context.actor_id):
        raise PermissionError('actual own-login embedding metadata capability required')
    def current():
        return resolver.embedding_eligibility_seal(context.workspace_id,context.qualified_artifact_id,
            context.qualified_artifact_version,connection=connection)
    seal=current()
    if (type(seal) is not ProcessingQualifiedProjectionSealV2 or seal.content_hash!=context.qualified_content_hash
            or seal.source_refs!=context.source_refs or semantic_registry.appointment.workspace_id!=context.workspace_id):
        raise PermissionError('exact current qualified projection eligibility differs')
    def identity(workspace,principal,source):
        if workspace!=context.workspace_id or principal!=context.actor_id:
            raise PermissionError('embedding cannot borrow another source-reading actor')
        matches=[ref for ref in seal.source_refs if ref.source_id==source]
        if len(matches)!=1:raise PermissionError('qualified source metadata missing')
        return matches[0]
    def extraction(workspace,principal,artifact,version):
        if workspace!=context.workspace_id or principal!=context.actor_id:
            raise PermissionError('embedding cannot borrow compiler or executor credentials')
        matches=[item for item in seal.extraction_seals if (item.artifact_id,item.version)==(artifact,version)]
        if len(matches)!=1:raise PermissionError('qualified extraction metadata missing')
        return matches[0]
    _verify_final_assembly_lineage(seal,context.qualified_payload,context.actor_id,now,
        trusted_admission_hashes=semantic_registry.current(now),runtime_hash=semantic_registry.appointment.runtime_hash,
        current_source_identity=identity,current_extraction_seal=extraction,
        qualification_model=PurposeAssemblyQualificationV3,lineage_model=PurposeFinalLineageV3,
        protocol_model=(ObservedConsolidationProtocolV1 if context.qualified_payload.get('assembly_capture',{}).get('candidate_schema')=='purpose-captured-consolidation-v1' else ObservedAssemblyProtocolV2),wire_model=ObservedAssemblyWireV2,
        permission_field='compiler_permission_hash',additional_check=_serve_schema3,
        metadata_model=ProcessingQualifiedProjectionSealV2)
    type(context).model_validate(context.model_dump(mode='python'))
    if current()!=seal:
        raise PermissionError('embedding eligibility changed during pure semantic validation')
    admission=PurposeAssemblyQualificationV3.model_validate_json(
        canonical_bytes(context.qualified_payload['assembly_qualification'])).admission
    return min(semantic_registry.valid_until(now),admission.expires_at,resolver.binding.source.expires_at)


def verify_embedding_projection_v3(*,resolver,context,semantic_registry,now,connection=None):
    from .purpose_profiles_v2 import DerivedEmbeddingContextV2
    return _verify_embedding_projection(resolver=resolver,context=context,semantic_registry=semantic_registry,
        now=now,connection=connection,context_type=DerivedEmbeddingContextV2)


def verify_sdk_embedding_projection_v3(*,resolver,context,semantic_registry,now,connection=None):
    from .purpose_profiles_v2 import DerivedSDKEmbeddingContextV3
    return _verify_embedding_projection(resolver=resolver,context=context,semantic_registry=semantic_registry,
        now=now,connection=connection,context_type=DerivedSDKEmbeddingContextV3)
