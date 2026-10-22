"""Qualified documentary temporal core; decisions remain separately authorized events.

No clock, source receipt, role, review appointment, or serving authority is issued
here. Unknown applicability is intentionally distinct from all-business scope.
"""
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, model_validator
from .contracts import StrictRecord, digest
from .model import BusinessOperatingModel

HASH = r'^[0-9a-f]{64}$'
CONTRACT = 'qualified-consolidation-core-v1'


class ScopeDimensionV1(StrictRecord):
    mode: Literal['unknown', 'all', 'exact']
    identities: tuple[UUID, ...] = ()

    @model_validator(mode='after')
    def closed_scope(self):
        if (bool(self.identities) != (self.mode == 'exact')
                or len(set(self.identities)) != len(self.identities)
                or tuple(sorted(self.identities, key=str)) != self.identities):
            raise ValueError('explicit canonical scope identities required')
        return self


class AssertionScopeV1(StrictRecord):
    process: ScopeDimensionV1
    customer: ScopeDimensionV1
    product: ScopeDimensionV1
    region: ScopeDimensionV1


class AssertionRevisionV1(StrictRecord):
    assertion_id: UUID
    revision: int = Field(strict=True, ge=1)
    predecessor_hash: str | None = Field(default=None, pattern=HASH)
    subject_id: UUID
    predicate: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    unit: str | None = Field(default=None, min_length=1, max_length=100)
    provenance: Literal['employee_account', 'documented_process', 'reported_policy', 'unknown']
    scope: AssertionScopeV1
    valid_time: Literal['unknown', 'evidenced']
    valid_from: AwareDatetime | None = None
    valid_to: AwareDatetime | None = None
    supporting_observations: tuple[str, ...] = ()
    opposing_observations: tuple[str, ...] = ()
    unknown_finding_ids: tuple[str, ...] = ()
    temporal_observations: tuple[str, ...] = ()

    @model_validator(mode='after')
    def documentary_only(self):
        if (self.revision == 1) != (self.predecessor_hash is None):
            raise ValueError('exact assertion predecessor required')
        if (self.valid_time == 'unknown' and any((self.valid_from, self.valid_to, self.temporal_observations))
                or self.valid_time == 'evidenced' and (self.valid_from is None or not self.temporal_observations)
                or self.valid_to is not None and (self.valid_from is None or self.valid_to <= self.valid_from)):
            raise ValueError('evidenced half-open validity or explicit unknown required')
        groups=(self.supporting_observations,self.opposing_observations,self.unknown_finding_ids,self.temporal_observations)
        if (not any(groups[:3]) or any(len(set(g))!=len(g) for g in groups)
                or set(self.supporting_observations)&set(self.opposing_observations)):
            raise ValueError('distinct supporting/opposing/unknown evidence required')
        return self


class ConsolidationCoreV1(StrictRecord):
    contract: Literal['qualified-consolidation-core-v1'] = CONTRACT
    model: BusinessOperatingModel
    expected_predecessor_version: int = Field(strict=True, ge=0)
    expected_predecessor_hash: str | None = Field(default=None, pattern=HASH)
    correction_source_ids: tuple[UUID, ...] = ()
    assertions: tuple[AssertionRevisionV1, ...] = Field(min_length=1, max_length=2048)

    @model_validator(mode='after')
    def coherent_revision(self):
        if (self.model.version != self.expected_predecessor_version + 1
                or (self.expected_predecessor_version == 0) != (self.expected_predecessor_hash is None)
                or len({a.assertion_id for a in self.assertions}) != len(self.assertions)
                or len(set(self.correction_source_ids)) != len(self.correction_source_ids)
                or not set(self.correction_source_ids) <= {r.source_id for r in self.model.source_refs}
                or self.model.version > 1 and not self.correction_source_ids):
            raise ValueError('coherent consecutive qualified model revision required')
        return self


def validate_core_evidence(core, observations, findings):
    if type(core) is not ConsolidationCoreV1:
        raise PermissionError('explicit qualified consolidation contract required')
    evidence={}
    for assertion in core.assertions:
        support=set(assertion.supporting_observations)
        oppose=set(assertion.opposing_observations)
        temporal=set(assertion.temporal_observations)
        if (not support|oppose|temporal <= observations.keys()
                or not set(assertion.unknown_finding_ids) <= findings.keys()):
            raise ValueError('assertion evidence absent from admitted extraction')
        # Opposing and unknown evidence participates in the exact assessment hash.
        refs=tuple(e for oid in sorted(support|oppose|temporal) for e in observations[oid].evidence)
        for fid in assertion.unknown_finding_ids:
            from .source_receipts import EvidenceRef
            import json
            refs += tuple(EvidenceRef.model_validate_json(json.dumps(e)) for e in findings[fid]['evidence_refs'])
        if not refs:
            raise ValueError('assertion has no quote-level documentary evidence')
        from .industry_reference_v1 import parse_industry_assertion_v1, IndustryReferenceEvidenceV1
        typed = parse_industry_assertion_v1(assertion)
        if isinstance(typed, IndustryReferenceEvidenceV1) and (typed.original not in core.model.source_refs
                or not any(e.ref == typed.original for oid in support for e in observations[oid].evidence)):
            raise ValueError('industry metadata needs the exact qualified original and supporting quote')
        evidence['assertion:'+str(assertion.assertion_id)+':'+str(assertion.revision)]=refs
    return evidence


def validate_successor(prior, current):
    if type(prior) is not ConsolidationCoreV1 or type(current) is not ConsolidationCoreV1:
        raise PermissionError('qualified immutable cores required')
    if (prior.model.model_id != current.model.model_id or prior.model.workspace_id != current.model.workspace_id
            or current.expected_predecessor_version != prior.model.version):
        raise ValueError('same stable model consecutive version required')
    if not any(ref.source_id in current.correction_source_ids and ref not in prior.model.source_refs for ref in current.model.source_refs):
        raise ValueError('new qualified original revision required for correction')
    old={a.assertion_id:a for a in prior.assertions}
    for assertion in current.assertions:
        previous=old.get(assertion.assertion_id)
        if previous is None:
            if assertion.revision != 1:raise ValueError('new assertion must start at one')
        elif assertion != previous and (assertion.revision != previous.revision+1 or assertion.predecessor_hash != digest(previous.model_dump(mode='json'))):
            raise ValueError('immutable exact assertion correction lineage required')


def readable_diff(prior, current):
    """Only call after BOTH bodies are currently permitted; grants never inferred."""
    if current.model.version==prior.model.version+1:validate_successor(prior,current)
    elif (prior.model.workspace_id,prior.model.model_id)!=(current.model.workspace_id,current.model.model_id) or current.model.version<=prior.model.version:
        raise ValueError('same registered model increasing diff endpoints required')
    before={a.assertion_id:a for a in prior.assertions};after={a.assertion_id:a for a in current.assertions}
    return tuple({'assertionId':str(key),'change':('added' if key not in before else 'retired' if key not in after else 'changed'),
                  'before':before[key].model_dump(mode='json') if key in before else None,
                  'after':after[key].model_dump(mode='json') if key in after else None}
                 for key in sorted(before.keys()|after.keys(),key=str) if before.get(key)!=after.get(key))


def applicable_assertions(core, *, valid_at: datetime, scope: AssertionScopeV1):
    """Documentary selection only; never policy acceptance or a historical grant."""
    if valid_at.tzinfo is None or valid_at.utcoffset() is None or type(scope) is not AssertionScopeV1:
        raise ValueError('aware explicit business time and typed scope required')
    def dimension(offer,query):
        return offer.mode=='all' and query.mode in ('all','exact') or query.mode=='exact' and offer.mode=='exact' and set(query.identities)<=set(offer.identities)
    return tuple(a for a in core.assertions if a.valid_time=='evidenced' and a.valid_from<=valid_at
                 and (a.valid_to is None or valid_at<a.valid_to)
                 and all(dimension(getattr(a.scope,k),getattr(scope,k)) for k in ('process','customer','product','region')))
