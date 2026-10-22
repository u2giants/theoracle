"""Typed documentary metadata inside the existing qualified assertion envelope.

These records issue no source, review, access, policy or fetching authority.
The original and quote-level evidence stay in the canonical qualified model.
"""
from datetime import date
from uuid import UUID
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from .contracts import StrictRecord, canonical_bytes
from .source_receipts import SourceRef

TOKEN = r'^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$'
REFERENCE_PREDICATE = 'industry:reference:v1'
CONTEXT_PREDICATE = 'company:decision-context:v1'


class IndustryReferenceEvidenceV1(StrictRecord):
    purpose: Literal['qualified-industry-reference-evidence-v1']
    reference_id: UUID
    registered_source_id: UUID
    original: SourceRef
    source_version: str | None = Field(default=None, pattern=TOKEN)
    publication_date: date | None = None
    effective_date: date | None = None
    jurisdiction: str | None = Field(default=None, pattern=TOKEN)
    product_scope: str | None = Field(default=None, pattern=TOKEN)
    channel_scope: str | None = Field(default=None, pattern=TOKEN)
    license_permission: str | None = Field(default=None, min_length=1, max_length=500)
    reviewed_at: AwareDatetime | None = None
    review_due: AwareDatetime | None = None

    @model_validator(mode='after')
    def explicit_review(self):
        if self.license_permission is not None and not self.license_permission.strip():
            raise ValueError('license metadata cannot be blank')
        if self.review_due is not None and (self.reviewed_at is None or self.review_due <= self.reviewed_at):
            raise ValueError('review due requires an earlier actual review')
        return self


class CompanyDecisionContextEvidenceV1(StrictRecord):
    purpose: Literal['qualified-company-decision-context-v1']
    decision_id: UUID
    jurisdiction: str | None = Field(default=None, pattern=TOKEN)
    product_scope: str | None = Field(default=None, pattern=TOKEN)
    channel_scope: str | None = Field(default=None, pattern=TOKEN)
    required_review_after: AwareDatetime | None = None


def parse_industry_assertion_v1(assertion):
    """Recognized discriminators cannot be accepted as opaque malformed text."""
    variants = {
        REFERENCE_PREDICATE: (IndustryReferenceEvidenceV1, 'canonical-industry-reference-v1'),
        CONTEXT_PREDICATE: (CompanyDecisionContextEvidenceV1, 'canonical-decision-context-v1'),
    }
    selected = variants.get(assertion.predicate)
    if selected is None:
        return None
    record, unit = selected
    value = record.model_validate_json(assertion.value)
    if assertion.unit != unit or canonical_bytes(value.model_dump(mode='json')).decode('utf-8') != assertion.value:
        raise ValueError('exact canonical typed industry metadata required')
    if not assertion.supporting_observations:
        raise ValueError('typed industry metadata needs actual supporting observations')
    return value
