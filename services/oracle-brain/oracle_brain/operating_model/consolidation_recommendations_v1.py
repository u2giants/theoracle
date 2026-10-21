"""Qualified-model documentary recommendations; benefits are explicitly unmeasured."""
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from .contracts import StrictRecord,ArtifactManifest,canonical_bytes
from .consolidation_contracts_v1 import ConsolidationCoreV1


class DocumentaryRecommendationV1(StrictRecord):
    recommendation_id: UUID
    proposal: str=Field(min_length=1,max_length=4000)
    assertion_ids: tuple[UUID,...]=Field(min_length=1,max_length=64)
    unknowns: tuple[str,...]=Field(min_length=1,max_length=64)
    measured_benefit: Literal['unknown']='unknown'
    policy_accepted: Literal[False]=False

    @model_validator(mode='after')
    def exact_evidence(self):
        if len(set(self.assertion_ids))!=len(self.assertion_ids):raise ValueError('unique assertion evidence required')
        return self


class QualifiedRecommendationsV1(StrictRecord):
    contract: Literal['qualified-documentary-recommendations-v1']='qualified-documentary-recommendations-v1'
    parent_model_id: UUID
    parent_version: int=Field(strict=True,ge=1)
    parent_content_hash: str=Field(pattern=r'^[0-9a-f]{64}$')
    recommendations: tuple[DocumentaryRecommendationV1,...]=Field(min_length=1,max_length=128)


def validate_recommendation_parent(manifest,payload,parent,parent_payload):
    body=QualifiedRecommendationsV1.model_validate_json(canonical_bytes(payload['recommendations']))
    core=ConsolidationCoreV1.model_validate_json(canonical_bytes(parent_payload['consolidation_core']))
    if (manifest.kind!='processing_recommendation_v1' or parent.kind!='processing_qualified_model_v1'
            or manifest.workspace_id!=parent.workspace_id
            or (body.parent_model_id,body.parent_version,body.parent_content_hash)!=(parent.artifact_id,parent.version,parent.content_hash)
            or payload['source_refs']!=parent_payload['source_refs']
            or set(payload)!={'source_refs','findings','recommendations'} or payload['findings']!=[]):
        raise PermissionError('truthful recommendations require exact qualified model evidence')
    known={a.assertion_id for a in core.assertions}
    if any(not set(r.assertion_ids)<=known for r in body.recommendations):raise PermissionError('recommendation references absent qualified assertion')
    return body
