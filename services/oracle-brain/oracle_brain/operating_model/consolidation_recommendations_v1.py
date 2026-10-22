"""Qualified-model documentary recommendations; benefits are explicitly unmeasured."""
from typing import Literal
from uuid import UUID
from pydantic import Field,model_validator
from .contracts import StrictRecord,ArtifactManifest,canonical_bytes,digest
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
    body=parse_qualified_recommendations(payload['recommendations'])
    core=ConsolidationCoreV1.model_validate_json(canonical_bytes(parent_payload['consolidation_core']))
    if (manifest.kind!='processing_recommendation_v1' or parent.kind!='processing_qualified_model_v1'
            or manifest.workspace_id!=parent.workspace_id
            or (body.parent_model_id,body.parent_version,body.parent_content_hash)!=(parent.artifact_id,parent.version,parent.content_hash)
            or payload['source_refs']!=parent_payload['source_refs']
            or set(payload)!={'source_refs','findings','recommendations'} or payload['findings']!=[]):
        raise PermissionError('truthful recommendations require exact qualified model evidence')
    if type(body) is QualifiedRecommendationsV1:
        known={a.assertion_id for a in core.assertions}
        if any(not set(r.assertion_ids)<=known for r in body.recommendations):raise PermissionError('recommendation references absent qualified assertion')
    else:
        validate_consulting_recommendations_v2(body,core,parent,parent_payload)
    return body


def parse_qualified_recommendations(raw):
    """Closed additive branch, never fallback or retrofit of the v1 body."""
    if type(raw) is not dict:raise ValueError('explicit canonical recommendation object required')
    if raw.get('contract')=='qualified-documentary-recommendations-v1':
        return QualifiedRecommendationsV1.model_validate_json(canonical_bytes(raw))
    if raw.get('contract')=='qualified-consulting-recommendations-v2':
        from .consultant.recommendation_actions_v1 import QualifiedConsultingRecommendationsV2
        return QualifiedConsultingRecommendationsV2.model_validate_json(canonical_bytes(raw))
    raise ValueError('unknown explicit qualified recommendation protocol')


def consulting_evidence_revision_v2(core,parent,parent_payload):
    from .consultant.recommendations import EvidenceRevision
    refs=tuple(sorted('assertion:'+str(a.assertion_id)+':'+str(a.revision) for a in core.assertions))
    return EvidenceRevision(parent.content_hash,refs,digest({'qualified_parent_manifest':parent.model_dump(mode='json'),
        'source_refs':parent_payload['source_refs']}))


def validate_consulting_recommendations_v2(body,core,parent,parent_payload):
    from .consultant.recommendations import recommendation_from_payload
    from .consultant.measurement_evidence_v1 import measurement_from_assertion_v1
    expected=consulting_evidence_revision_v2(core,parent,parent_payload)
    known={'assertion:'+str(a.assertion_id)+':'+str(a.revision):a for a in core.assertions}
    for item in body.recommendations:
        advice=recommendation_from_payload(item.advice)
        if advice.evidence!=expected:raise PermissionError('recommendation evidence seal differs from exact complete qualified parent')
        used=set(ref for option in advice.options for ref in option.evidence_refs)|set(advice.opposing_evidence)
        if any(ref not in known or known[ref].scope!=item.scope for ref in used):
            raise PermissionError('recommendation cannot widen qualified assertion scope')
        opposed={ref for ref,a in known.items() if a.scope==item.scope and a.opposing_observations}
        if set(advice.opposing_evidence)!=opposed or advice.opposing_unknown!=(not bool(opposed)):
            raise PermissionError('actual scoped opposing evidence or honest unknown required')
        for option in advice.options:
            measured=[measurement_from_assertion_v1(known[ref]) for ref in option.evidence_refs]
            for cost in (*option.downstream_costs,*option.measured_basis):
                if cost.kind=='actual_cost' and not any(m is not None and m.complete and not m.censored
                        and m.measurement()==cost.measure for m in measured):
                    raise PermissionError('actual cost requires exact complete qualified measured evidence')
