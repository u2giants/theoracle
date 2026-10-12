"""Canonical, versioned artifact bytes; no narrative is authority."""
import hashlib
import json
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class StrictRecord(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    schema_version: Literal[1] = 1

def canonical_bytes(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
                      allow_nan=False).encode('utf-8')

def digest(payload: dict) -> str:
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()

class ArtifactManifest(StrictRecord):
    workspace_id: UUID
    artifact_id: UUID
    version: int = Field(strict=True, ge=1)
    kind: Literal['extraction', 'operating_model', 'workflow', 'summary', 'analysis', 'report', 'failed_extraction','failed_assembly','event_import']
    input_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    compiler_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    dependency_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    private_object_key: str
    state: Literal['ready', 'failed']
