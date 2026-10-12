"""Preserved reported issues, separated from policy and derived diagnostics."""
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from .source_receipts import SourceRef, EvidenceRef, SourceReceipt, _StrictModel, validate_evidence
from .contracts import digest

class CoverageRef(_StrictModel):
    inventory_id: str
    inventory_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    required_slot: str

class OpposedAssertion(_StrictModel):
    question_key: str = Field(min_length=1)
    asserted_value: str = Field(min_length=1)
    evidence: EvidenceRef

class Finding(_StrictModel):
    schema_version: Literal[1] = 1
    finding_id: str = Field(min_length=1)
    kind: Literal['missing_information', 'source_conflict', 'model_incomplete']
    workspace_id: UUID
    source_refs: tuple[SourceRef, ...]
    affected_object_ids: tuple[str, ...] = ()
    process_id: str | None = None
    scope: str = Field(min_length=1)
    text: str = Field(min_length=1)
    status: Literal['unresolved', 'resolved_by_authorized_review', 'superseded', 'withdrawn', 'needs_evidence'] = 'unresolved'
    origin: Literal['source_reported', 'reported_conflict_unverified', 'coverage_inference', 'legacy_unverified', 'structural_diagnostic']
    evidence_refs: tuple[EvidenceRef, ...] = ()
    coverage_ref: CoverageRef | None = None
    supersedes: tuple[str, ...] = ()
    opposed_assertions: tuple[OpposedAssertion, ...] = ()
    schema_revision: Literal[1] = 1

    @model_validator(mode='after')
    def shape(self):
        if any(r.workspace_id != self.workspace_id for r in self.source_refs):
            raise ValueError('finding crosses workspace')
        if any(e.ref not in self.source_refs for e in self.evidence_refs):
            raise ValueError('evidence not in source manifest')
        if self.origin == 'legacy_unverified':
            if self.status != 'needs_evidence' or self.evidence_refs or self.coverage_ref:
                raise ValueError('legacy text must remain unverified without fabricated support')
        elif self.origin == 'coverage_inference':
            if self.coverage_ref is None or self.evidence_refs:
                raise ValueError('coverage gap needs inventory, not absence quotation')
        elif self.origin != 'structural_diagnostic' and not self.evidence_refs:
            raise ValueError('reported issue requires exact evidence')
        if self.status == 'resolved_by_authorized_review':
            raise ValueError('resolution requires separate authority event, never model output')
        if self.kind == 'source_conflict' and self.origin == 'source_reported':
            sides = self.opposed_assertions
            if len(sides) < 2 or len({a.question_key for a in sides}) != 1 or len({a.asserted_value for a in sides}) < 2:
                raise ValueError('conflict requires explicitly opposed assertions')
            if any(a.evidence not in self.evidence_refs for a in sides) or len({(a.evidence.ref.source_id,a.evidence.start,a.evidence.end) for a in sides}) < 2:
                raise ValueError('single reported conflict must remain unverified')
        return self

def validate_finding(finding: Finding, receipts: dict[str, SourceReceipt], *, inventories: dict[str, dict] | None = None) -> Finding:
    for ref in finding.source_refs:
        current = receipts.get(str(ref.source_id))
        if current is None or current.ref != ref:
            raise PermissionError('finding source is not current and accessible')
    for evidence in finding.evidence_refs:
        validate_evidence(receipts[str(evidence.ref.source_id)], evidence)
    if finding.coverage_ref:
        inventory = (inventories or {}).get(finding.coverage_ref.inventory_id)
        if not inventory or inventory.get('independent_review') != 'APPROVE' or inventory.get('complete') is not True:
            raise ValueError('coverage inventory is not independently complete')
        if digest(inventory) != finding.coverage_ref.inventory_hash or finding.coverage_ref.required_slot not in inventory.get('required_slots', ()):
            raise ValueError('coverage inventory identity/slot mismatch')
    return finding

def answer_eligible(finding: Finding) -> bool:
    return finding.origin != 'legacy_unverified' and finding.status not in {'needs_evidence', 'withdrawn', 'superseded'}

def import_legacy(*, workspace_id: UUID, refs: tuple[SourceRef, ...], scope: str, texts: list[str]) -> tuple[Finding, ...]:
    return tuple(Finding(finding_id=digest({'workspace':str(workspace_id),'refs':[r.model_dump(mode='json') for r in refs],'scope':scope,'text':text}),kind='missing_information', workspace_id=workspace_id,source_refs=refs,scope=scope,text=text,status='needs_evidence',origin='legacy_unverified') for text in texts if text.strip())
