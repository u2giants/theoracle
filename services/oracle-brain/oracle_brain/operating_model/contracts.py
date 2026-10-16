"""Canonical, versioned artifact bytes; no narrative is authority."""
import hashlib
import json
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from .source_receipts import SourceRef

class StrictRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    schema_version: Literal[1] = 1

def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')

def digest(payload: dict) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()

PROCESSING_ARTIFACT_KINDS = frozenset({
    'processing_extraction_v1','processing_failed_extraction_v1',
    'processing_qualified_model_v1','processing_summary_v1','processing_failed_assembly_v1',
})

class ArtifactManifest(StrictRecord):
    workspace_id: UUID
    artifact_id: UUID
    version: int = Field(strict=True, ge=1)
    kind: Literal['extraction', 'operating_model', 'workflow', 'summary', 'analysis', 'report', 'failed_extraction','failed_assembly','event_import', 'processing_extraction_v1', 'processing_failed_extraction_v1', 'processing_qualified_model_v1', 'processing_summary_v1', 'processing_failed_assembly_v1']
    input_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    compiler_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    dependency_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    private_object_key: str
    state: Literal['ready', 'failed']


class ProcessingExtractionSeal(StrictRecord):
    """Current immutable extraction identity, never a private-body capability."""
    workspace_id: UUID
    artifact_id: UUID
    version: int = Field(strict=True, ge=1)
    kind: Literal['processing_extraction_v1']
    state: Literal['ready']
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    input_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    compiler_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    manifest_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    dependency_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)


class ProcessingQualifiedProjectionSealV2(StrictRecord):
    """Embedding eligibility metadata; never a manifest or private-body grant."""
    schema_version: Literal[2] = 2
    workspace_id: UUID
    artifact_id: UUID
    version: int = Field(strict=True, ge=1)
    kind: Literal['processing_qualified_model_v1']
    state: Literal['ready']
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    input_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    compiler_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    dependency_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    manifest_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    extraction_seals: tuple[ProcessingExtractionSeal, ...] = Field(min_length=1)


class ProcessingProjectionDeliverySealV3(StrictRecord):
    """Current SQL-acknowledged delivery metadata, never paid/private contents."""
    schema_version: Literal[3] = 3
    workspace_id: UUID
    artifact_id: UUID
    version: int = Field(strict=True, ge=1)
    event_id: UUID
    kind: Literal['processing_qualified_model_v1']
    state: Literal['ready']
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    graph_name: str
    record_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    sdk_version: Literal['1.4.0']
    projection_schema: Literal['qualified-evidence-projection-v1']
    projection_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_protocol: Literal['paid-sdk-embedding-v3']
    embedding_inventory_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_context_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_native_receipt_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_wire_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_commit_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_vectors_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_coverage_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    receipt_body_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    checked_at: 'AwareDatetime'
    valid_until: 'AwareDatetime'


class ProcessingProjectionReceiptBodyV3(StrictRecord):
    """Exact immutable signed ACK body; no paid response or signing authority."""
    schema_version: Literal[3] = 3
    event_id: str
    workspace_id: str
    artifact_id: str
    version: int = Field(strict=True,ge=1)
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    graph_name: str
    record_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    sdk_version: Literal['1.4.0']
    projector_id: str = Field(min_length=1)
    lease_role: str
    lease_token: str
    lease_attempt: int = Field(strict=True,ge=1)
    lease_until: str
    projection_schema: Literal['qualified-evidence-projection-v1']
    projection_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_protocol: Literal['paid-sdk-embedding-v3']
    embedding_inventory_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_context_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_native_receipt_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_wire_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_commit_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_vectors_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    embedding_coverage_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class ProcessingProjectionReceiptV3(StrictRecord):
    """Own compiler SQL readback; signing key remains protected startup state."""
    schema_version: Literal[3] = 3
    receipt: ProcessingProjectionReceiptBodyV3
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_refs: tuple[SourceRef,...] = Field(min_length=1)
    checked_at: AwareDatetime
    valid_until: AwareDatetime


class _ReplacementMetadataV1(StrictRecord):
    @model_validator(mode='before')
    @classmethod
    def exact_integer_schema(cls,value):
        if isinstance(value,dict) and 'schema_version' in value and type(value['schema_version']) is not int:
            raise ValueError('replacement metadata schema version must be an exact integer')
        return value


class ReplacementConfirmationTargetV1(_ReplacementMetadataV1):
    workflow_id: str = Field(min_length=1,max_length=200)
    version: int = Field(strict=True,ge=1)
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    eligible: bool


class ReplacementSummaryTargetV1(_ReplacementMetadataV1):
    summary_artifact_id: UUID
    summary_version: int = Field(strict=True,ge=1)
    summary_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    qualified_parent_id: UUID
    qualified_parent_version: int = Field(strict=True,ge=1)
    qualified_parent_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class ReplacementExecutorTargetV1(_ReplacementMetadataV1):
    """Authenticated SQL control metadata only; never semantic/read authority."""
    run_id: UUID
    journey_revision: int = Field(strict=True,ge=1)
    state: Literal['pending','processing','delivered','revision_pending','cancelled','error']
    answer_hold: bool
    cancelled: bool
    population_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    requester_principal_id: UUID
    workspace_id: UUID
    model_id: UUID
    model_version: int = Field(strict=True,ge=1)
    model_content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    ack_event_id: UUID
    projection_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_refs: tuple[SourceRef,...] = Field(min_length=1,max_length=4096)
    current_confirmation: ReplacementConfirmationTargetV1 | None
    summary_targets: tuple[ReplacementSummaryTargetV1,...] = Field(max_length=64)
    checked_at: AwareDatetime
    valid_until: AwareDatetime

    @model_validator(mode='after')
    def exact_target_metadata(self):
        if (self.checked_at>=self.valid_until or len(set(self.source_refs))!=len(self.source_refs)
                or len({ref.source_id for ref in self.source_refs})!=len(self.source_refs)
                or any(ref.workspace_id!=self.workspace_id for ref in self.source_refs)
                or self.cancelled!=(self.state=='cancelled')):
            raise ValueError('exact finite current replacement target metadata required')
        identities=[(s.summary_artifact_id,s.summary_version) for s in self.summary_targets]
        if (len(set(identities))!=len(identities) or any(
                (s.qualified_parent_id,s.qualified_parent_version,s.qualified_parent_content_hash)!=
                (self.model_id,self.model_version,self.model_content_hash) for s in self.summary_targets)):
            raise ValueError('registered summaries must bind exact qualified target')
        c=self.current_confirmation
        if c is not None and c.eligible and (self.answer_hold or self.cancelled or self.state!='delivered'
                or (c.version,c.content_hash)!=(self.model_version,self.model_content_hash)):
            raise ValueError('current confirmation cannot survive a held or changed target')
        return self
