"""Immutable release identity; a pointer alone cannot make a projection authoritative."""
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from .source_receipts import _StrictModel,SourceRef
from .contracts import digest

class ReleaseManifest(_StrictModel):
    schema_version:Literal[1]=1
    release_id:UUID
    workspace_id:UUID
    artifact_id:UUID
    artifact_version:int=Field(strict=True,ge=1)
    artifact_content_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    runtime_digest:str=Field(pattern=r'^[0-9a-f]{64}$')
    schema_revision:Literal[4]=4
    permission_digest:str=Field(pattern=r'^[0-9a-f]{64}$')
    source_refs:tuple[SourceRef,...]=Field(min_length=1)
    graph_generation:UUID
    graph_name:str=Field(pattern=r'^oracle_operating_model_v1_')
    graph_record_digest:str=Field(pattern=r'^[0-9a-f]{64}$')
    summary_hashes:tuple[str,...]=()
    analytical_capability:bool=False
    analytical_qualification_hash:str|None=None
    actual_event_acceptance:Literal['unavailable','synthetic','accepted']='unavailable'
    acceptance_state:Literal['synthetic','hosted_preview','admitted_hosted']
    independent_review_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    documentary_gate_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    restricted_hosting_hash:str|None=None
    restore_proof_hash:str|None=None
    source_inventory_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    ledger_watermark:int=Field(strict=True,ge=0)

    @model_validator(mode='after')
    def gates(self):
        if any(r.workspace_id!=self.workspace_id for r in self.source_refs):raise ValueError('cross-workspace release')
        if self.analytical_capability and not self.analytical_qualification_hash:raise ValueError('analytical qualification missing')
        if self.acceptance_state in {'hosted_preview','admitted_hosted'} and not self.restricted_hosting_hash:raise ValueError('restricted hosting missing')
        if self.acceptance_state=='admitted_hosted' and not self.restore_proof_hash:raise ValueError('fresh-instance restore proof missing')
        return self

    def content_hash(self):return digest(self.model_dump(mode='json'))
