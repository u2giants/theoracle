"""Opt-in original extraction runtime; V1 refusal/defaults are unchanged.

The operation companion is an externally reviewed canonical-JSON receipt, not a
new issuer. Compiler custody appointments and promotion belong to the R5 worker.
Pure paid-wire validation below issues no read/compile/serving authority.
"""
from datetime import datetime,timezone
from typing import Literal
from uuid import UUID
import hashlib,json
from pydantic import AwareDatetime,Field,model_validator

from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes,digest
from oracle_brain.operating_model.purpose_context import HASH,LOGIN,WORKER,ParentPopulationAdmissionV2,source_population_digest
from oracle_brain.operating_model.purpose_receipts_v2 import PhaseResponseCommitV2
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.semantic_acceptance import sealed
from .provider_runtime import JobContext


class ExtractionTargetV2(StrictRecord):
    dispatch_id: UUID
    artifact_id: UUID
    artifact_version: int=Field(strict=True,ge=1)
    source_ref: SourceRef
    native_job_hash: str=Field(pattern=HASH)
    context_hash: str=Field(pattern=HASH)


class ExtractionOperationQualificationV2(StrictRecord):
    schema_version: Literal[2]=2
    qualification_purpose: Literal['source-extraction-operation-qualification-v2']='source-extraction-operation-qualification-v2'
    purpose: Literal['source-extraction']='source-extraction'
    operation: Literal['chat']='chat'
    model: Literal['openai/gpt-6.1-sol']='openai/gpt-6.1-sol'
    workspace_id: UUID
    actor_id: UUID
    provider_login: str=Field(pattern=LOGIN)
    worker_uri: str=Field(pattern=WORKER)
    runtime_hash: str=Field(pattern=HASH)
    source_registry_hash: str=Field(pattern=HASH)
    parent_registry_sha256: str=Field(pattern=HASH)
    envelope_sha256: str=Field(pattern=HASH)
    source_qualification_sha256: str=Field(pattern=HASH)
    descriptor_sha256: str=Field(pattern=HASH)
    projection_sha256: str=Field(pattern=HASH)
    population_admission_sha256: str=Field(pattern=HASH)
    budget_allocation_projection_sha256: str=Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]=Field(min_length=1)
    population_digest: str=Field(pattern=HASH)
    targets: tuple[ExtractionTargetV2,...]=Field(min_length=1)
    issuer_actor: UUID
    reviewer_actor: UUID
    expires_at: AwareDatetime

    @model_validator(mode='after')
    def exact_new_original_extraction(self):
        if (len({self.actor_id,self.issuer_actor,self.reviewer_actor})!=3
                or any(r.workspace_id!=self.workspace_id for r in self.source_refs)
                or len({r.source_id for r in self.source_refs})!=len(self.source_refs)
                or self.population_digest!=source_population_digest(self.source_refs)
                or tuple(t.source_ref for t in self.targets)!=self.source_refs
                or len({t.dispatch_id for t in self.targets})!=len(self.targets)
                or len({(t.artifact_id,t.artifact_version) for t in self.targets})!=len(self.targets)):
            raise PermissionError('independently qualified exact ordered extraction population required')
        return self

    def target(self,dispatch_id):
        matches=[t for t in self.targets if t.dispatch_id==dispatch_id]
        if len(matches)!=1:raise PermissionError('exact qualified extraction target required')
        return matches[0]


class ExtractionResponseCommitV2(PhaseResponseCommitV2):
    purpose: Literal['observed-authorized-extraction-response-commit-v2']='observed-authorized-extraction-response-commit-v2'
    phase: Literal['extraction']='extraction'
    extraction_source_ref: SourceRef
    model_content_hash: str=Field(pattern=HASH)

    @model_validator(mode='after')
    def actual_single_original(self):
        if self.extraction_source_ref not in self.source_refs:
            raise PermissionError('extraction cannot borrow another dispatch source')
        return self


class VerifiedExtractionWitnessV2(StrictRecord):
    """Pure immutable consistency witness; never an appointment or compiler grant."""
    schema_version: Literal[2]=2
    workspace_id: UUID
    source_ref: SourceRef
    artifact_id: UUID
    artifact_version: int=Field(strict=True,ge=1)
    native_dispatch_id: UUID
    native_job_hash: str=Field(pattern=HASH)
    parent_registry_hash: str=Field(pattern=HASH)
    envelope_hash: str=Field(pattern=HASH)
    descriptor_hash: str=Field(pattern=HASH)
    extraction_qualification_hash: str=Field(pattern=HASH)
    raw_wire_hash: str=Field(pattern=HASH)
    model_content_hash: str=Field(pattern=HASH)
    phase_commit_hash: str=Field(pattern=HASH)
    native_custody_receipt_hash: str=Field(pattern=HASH)
    population_digest: str=Field(pattern=HASH)
    source_refs: tuple[SourceRef,...]


def verify_extraction_paid_response_v2(context,commit,raw,qualification,population,*,
        expected_qualification_hash,artifact_version):
    """Pure exact paid-content validator; actual compiler/custody checks are R5.

    Qualification's protocol mandates canonical JSON bytes, so its canonical
    hash is also the independently pinned operation receipt's byte SHA. Neither
    that hash nor this returned witness creates authority to read or persist.
    """
    from oracle_brain.operating_model.captured_assembly import _observed_model_content
    from oracle_brain.operating_model.extraction import validate_response
    from oracle_brain.operating_model.pipeline import extraction_messages
    from oracle_brain.provider_policy import authorize
    if (type(context) is not JobContext or type(commit) is not ExtractionResponseCommitV2
            or type(qualification) is not ExtractionOperationQualificationV2
            or type(population) is not ParentPopulationAdmissionV2
            or type(raw) is not bytes or len(raw)>16*1024*1024
            or sealed(qualification)!=expected_qualification_hash):
        raise PermissionError('exact externally qualified extraction paid-custody inputs required')
    qualification=ExtractionOperationQualificationV2.model_validate(qualification.model_dump(mode='python'))
    commit=ExtractionResponseCommitV2.model_validate(commit.model_dump(mode='python'))
    job=context.job;target=qualification.target(job.dispatch_id)
    if (commit.operation_approval_hash!=expected_qualification_hash
            or commit.descriptor_hash!=qualification.descriptor_sha256
            or commit.parent_registry_hash!=qualification.parent_registry_sha256
            or population.workspace_id!=qualification.workspace_id
            or population.runtime_hash!=qualification.runtime_hash
            or population.source_registry_hash!=qualification.source_registry_hash
            or commit.budget_identity_hash!=qualification.budget_allocation_projection_sha256
            or population.parent_registry_sha256!=qualification.parent_registry_sha256
            or sealed(population)!=qualification.population_admission_sha256
            or population.source_refs!=qualification.source_refs or commit.source_refs!=qualification.source_refs
            or commit.population_digest!=qualification.population_digest
            or commit.actor_id!=qualification.actor_id or context.actor_id!=qualification.actor_id
            or commit.provider_login!=qualification.provider_login or commit.runtime_hash!=qualification.runtime_hash
            or commit.dispatch_id!=job.dispatch_id or target.artifact_id!=job.artifact_id
            or target.artifact_version!=artifact_version or target.source_ref!=context.receipt.ref
            or commit.extraction_source_ref!=target.source_ref
            or target.native_job_hash!=sealed(job) or commit.job_hash!=sealed(job)
            or context.job_hash!=sealed(job) or target.context_hash!=sealed(context)
            or commit.context_hash!=target.context_hash or job.request_hash!=digest(job.request)
            or context.permission_hash!=job.permission_hash or commit.permission_hash!=job.permission_hash
            or commit.request_hash!=job.request_hash or job.workspace_id!=qualification.workspace_id
            or commit.workspace_id!=qualification.workspace_id
            or job.purpose!='source-extraction' or job.processing_request.purpose!='source-extraction'
            or job.request.get('model')!=qualification.model or commit.model!=qualification.model
            or job.pricing.model!=qualification.model or job.pricing.admitted_register_hash!=job.register_hash
            or commit.account_policy_hash!=digest({k:v for k,v in job.processing_request.model_dump(mode='json').items() if k!='terms_hash'})
            or job.request.get('messages')!=extraction_messages(context.receipt)
            or set(job.request)!={'model','messages','max_tokens','response_format','store','stream','provider'}
            or hashlib.sha256(raw).hexdigest()!=commit.raw_response_hash
            or commit.committed_at>=min(qualification.expires_at,population.expires_at)):
        raise PermissionError('paid extraction/context/target/source/population differs from qualified operation')
    authorize(job.processing_request,list(job.approvals),now=commit.committed_at)
    if commit.committed_at>=job.pricing.expires_at:
        raise PermissionError('extraction committed after original actual pricing horizon')
    content=_observed_model_content(raw,qualification.model)
    content_hash=hashlib.sha256(content.encode()).hexdigest()
    if content_hash!=commit.model_content_hash:
        raise PermissionError('model-only extraction content differs from actual paid wire')
    response,_=validate_response(context.receipt,content,inventories=context.inventories)
    witness=VerifiedExtractionWitnessV2(workspace_id=qualification.workspace_id,source_ref=context.receipt.ref,
        artifact_id=target.artifact_id,artifact_version=artifact_version,native_dispatch_id=job.dispatch_id,
        native_job_hash=sealed(job),parent_registry_hash=qualification.parent_registry_sha256,
        envelope_hash=qualification.envelope_sha256,descriptor_hash=qualification.descriptor_sha256,
        extraction_qualification_hash=expected_qualification_hash,raw_wire_hash=commit.raw_response_hash,
        model_content_hash=content_hash,phase_commit_hash=sealed(commit),native_custody_receipt_hash=commit.native_custody_receipt_hash,
        population_digest=qualification.population_digest,source_refs=qualification.source_refs)
    return response,witness
