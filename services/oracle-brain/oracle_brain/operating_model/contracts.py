"""Canonical, versioned artifact bytes; no narrative is authority."""
import hashlib
import json
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
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
