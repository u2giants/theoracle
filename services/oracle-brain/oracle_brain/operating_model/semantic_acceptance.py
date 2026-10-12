"""Read-only independent source acceptance. No provider dispatch or self-admission.

Trusted admissions are supplied separately by the release coordinator. Every
private receipt must be independently admitted; protocol approval alone never
admits an inventory, an assessment, a company answer, or a hosted release.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field

from .contracts import StrictRecord, digest
from .coverage import Obligation, CoverageRecord, validate_coverage
from .source_receipts import SourceRef, EvidenceRef, SourceReceipt, validate_evidence

Hash = str
CRITERIA = frozenset({
    'roles', 'artifacts', 'interfaces', 'exceptions', 'conflicts', 'gaps',
    'scope_and_unsupported_claims',
})


class SourceRegion(StrictRecord):
    """Source-only section/cell/diagram census, frozen before model access."""
    region_id: str = Field(min_length=1)
    kind: Literal['section', 'table_cell', 'diagram_region']
    evidence: EvidenceRef


class FrozenCensus(StrictRecord):
    workspace_id: UUID
    source_refs: tuple[SourceRef, ...] = Field(min_length=1)
    regions: tuple[SourceRegion, ...] = Field(min_length=1)
    obligations: tuple[Obligation, ...] = Field(min_length=1)
    source_only_context_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_only_dispatch_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    frozen_at: AwareDatetime
    census_model: Literal['openai/gpt-6.1-sol']
    # This pass is diagnostic until a separately admitted assessor accepts it.
    candidate_visible: Literal[False] = False


class CriterionReview(StrictRecord):
    criterion: str
    verdict: Literal['pass', 'fail']
    explanation: str = Field(min_length=1)
    evidence: tuple[EvidenceRef, ...] = ()
    object_ids: tuple[str, ...] = ()
    # Absence claims cite the complete inventory, never a fabricated quote.
    absence_inventory_hash: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


class IndependentAssessment(StrictRecord):
    workspace_id: UUID
    census_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    protocol_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    assessor_actor: UUID
    assessor_model: Literal['openai/gpt-6-astra']
    assessed_at: AwareDatetime
    dispatch_receipt_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    raw_response_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    coverage: tuple[CoverageRecord, ...] = Field(min_length=1)
    criteria: tuple[CriterionReview, ...] = Field(min_length=7, max_length=7)
    detail_gap_ids: tuple[str, ...] = ()
    detail_gap_owners: dict[str, UUID] = Field(default_factory=dict)


class SemanticAdmission(StrictRecord):
    """Independent trusted registry; never read from the candidate packet."""
    protocol_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    runtime_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_region_register_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    census_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    assessment_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    reviewer_report_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    object_evidence_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    candidate_created_at: AwareDatetime
    implementer_actor: UUID
    assessor_actor: UUID
    # Frozen candidate provenance, independently checked at admission.
    candidate_model: Literal['openai/gpt-6.1-sol']
    purpose: Literal['independent-source-semantic-acceptance']
    expires_at: AwareDatetime


def sealed(record):
    return digest(record.model_dump(mode='json'))


def verify_semantic_acceptance(*, census: FrozenCensus,
                               assessment: IndependentAssessment,
                               admission: SemanticAdmission,
                               trusted_admission_hashes: frozenset[Hash],
                               source_regions: tuple[SourceRegion, ...],
                               candidate: dict, object_evidence: dict,
                               runtime_hash: Hash, permission_hash: Hash,
                               candidate_created_at: datetime, now: datetime,
                               current_source, can_read) -> dict:
    """Validate independently admitted evidence against current original receipts.

    The coordinator derives candidate/object_evidence from the sealed ledger,
    and source_regions from the independent original register. Neither is a
    provider assertion. Current-source and permission callbacks are mandatory.
    Returns acceptance for this documentary artifact only, never serving rights.
    """
    if sealed(admission) not in trusted_admission_hashes:
        raise PermissionError('independent semantic admission unavailable')
    if any(t.tzinfo is None or t.utcoffset() is None for t in (now, candidate_created_at)):
        raise ValueError('semantic timestamps require a timezone')
    if admission.expires_at <= now:
        raise PermissionError('semantic admission expired')
    if admission.assessor_actor == admission.implementer_actor:
        raise PermissionError('implementer cannot independently assess its own work')
    if assessment.assessor_actor != admission.assessor_actor:
        raise PermissionError('assessor identity differs from admission')
    if not census.frozen_at < candidate_created_at <= assessment.assessed_at <= now:
        raise PermissionError('source census was not frozen before candidate access')
    if candidate_created_at != admission.candidate_created_at:
        raise PermissionError('candidate creation time differs from admitted provenance')
    if census.workspace_id != assessment.workspace_id:
        raise PermissionError('cross-workspace semantic assessment')
    matches = (
        (sealed(census), admission.census_hash),
        (sealed(assessment), admission.assessment_hash),
        (digest(candidate), admission.candidate_hash),
        (assessment.candidate_hash, admission.candidate_hash),
        (assessment.census_hash, admission.census_hash),
        (assessment.protocol_hash, admission.protocol_hash),
        (assessment.permission_hash, admission.permission_hash),
        (permission_hash, admission.permission_hash),
        (runtime_hash, admission.runtime_hash),
        (digest({k: [e.model_dump(mode='json') for e in v]
                 for k, v in object_evidence.items()}), admission.object_evidence_hash),
    )
    if any(actual != expected for actual, expected in matches):
        raise PermissionError('semantic admission does not bind exact current inputs')
    register_hash = digest({'regions': [r.model_dump(mode='json') for r in source_regions]})
    if register_hash != admission.source_region_register_hash or census.regions != source_regions:
        raise ValueError('source section/cell/diagram census is incomplete or changed')
    region_ids = [r.region_id for r in source_regions]
    if len(set(region_ids)) != len(region_ids):
        raise ValueError('duplicate source region')
    refs = census.source_refs
    if len(set(refs)) != len(refs) or any(r.workspace_id != census.workspace_id for r in refs):
        raise ValueError('duplicate or cross-workspace original identity')
    if {r.evidence.ref for r in source_regions} != set(refs):
        raise ValueError('source region register omits an original')
    if candidate.get('source_refs') != [r.model_dump(mode='json') for r in refs]:
        raise ValueError('candidate source population differs from independent census')
    receipts = {}

    def resolve():
        for ref in refs:
            # Permission is checked before requesting a private reading.
            if not can_read(census.workspace_id, admission.assessor_actor, ref.source_id):
                raise PermissionError('current source access denied')
            receipt = current_source(ref.workspace_id, ref.source_id)
            if not isinstance(receipt, SourceReceipt) or receipt.ref != ref:
                raise PermissionError('original reading changed or withdrawn')
            receipts[ref] = receipt

    resolve()

    def evidence_check(evidence):
        if evidence.ref not in receipts:
            raise ValueError('semantic evidence outside source census')
        validate_evidence(receipts[evidence.ref], evidence)

    for region in source_regions:
        evidence_check(region.evidence)
    for obligation in census.obligations:
        if obligation.priority == 'essential' and obligation.expected not in {'represented', 'unresolved'}:
            raise ValueError('essential obligations cannot be unsupported or inapplicable')
        evidence_check(obligation.evidence)
        if not any(r.evidence.ref == obligation.evidence.ref and
                   r.evidence.start <= obligation.evidence.start and
                   r.evidence.end >= obligation.evidence.end for r in source_regions):
            raise ValueError('obligation has no original section/cell/diagram locator')
    # Every original reading character must occur in the original-region census.
    # Whitespace can be included in adjacent region spans; never silently dropped.
    for ref, receipt in receipts.items():
        end = 0
        for region in sorted((r for r in source_regions if r.evidence.ref == ref),
                             key=lambda r: r.evidence.start):
            if region.evidence.start > end:
                raise ValueError('source region census leaves an unread interval')
            end = max(end, region.evidence.end)
        if end != len(receipt.reading):
            raise ValueError('source region census leaves an unread suffix')
    for items in object_evidence.values():
        for evidence in items:
            evidence_check(evidence)
    inventory_hash = digest({'obligations': [o.model_dump(mode='json') for o in census.obligations]})
    coverage = validate_coverage(census.obligations, assessment.coverage,
                                object_evidence=object_evidence,
                                independent_inventory_hash=inventory_hash)
    if not coverage['essential_total']:
        raise ValueError('semantic inventory has no essential obligations')
    names = [c.criterion for c in assessment.criteria]
    if set(names) != CRITERIA or len(set(names)) != len(names):
        raise ValueError('missing, duplicated or unknown semantic criterion')
    for criterion in assessment.criteria:
        if criterion.verdict != 'pass':
            raise ValueError('independent assessment rejected semantic criterion')
        if any(i not in object_evidence for i in criterion.object_ids):
            raise ValueError('semantic assessment refers to absent model object')
        if criterion.absence_inventory_hash is not None:
            if criterion.absence_inventory_hash != inventory_hash or criterion.evidence:
                raise ValueError('absence must bind the complete independent inventory')
        elif not criterion.evidence:
            raise ValueError('semantic criterion lacks original support or inventory')
        for evidence in criterion.evidence:
            evidence_check(evidence)
    detail_gaps = {r.obligation_id for r in assessment.coverage
                   if r.disposition != 'represented' and
                   next(o for o in census.obligations if o.obligation_id == r.obligation_id).priority == 'detail'}
    if set(assessment.detail_gap_ids) != detail_gaps or len(set(assessment.detail_gap_ids)) != len(assessment.detail_gap_ids):
        raise ValueError('detail omissions lack visible dispositions')
    if set(assessment.detail_gap_owners) != detail_gaps:
        raise ValueError('detail omissions lack named disposition owners')
    # Recheck after evaluation, before returning a receipt. Serving still needs
    # its own current ledger/access/hosted/review gates on every read.
    resolve()
    return {**coverage, 'schema_version': 1, 'semantic_accepted': True,
            'assessment_hash': sealed(assessment), 'admission_hash': sealed(admission),
            'candidate_hash': admission.candidate_hash, 'protocol_hash': admission.protocol_hash,
            'detail_gap_count': len(detail_gaps), 'business_accepted': False,
            'actual_event_accepted': False, 'hosted_accepted': False,
            'serving_authorized': False, 'company_generation_authorized': False}
