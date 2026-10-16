"""Expertise claim provenance: every industry claim cites primary external references.

New industry material may suggest a comparison; it never overwrites company policy.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from .registry import ACCESS

HTTPS = 'https://'


@dataclass(frozen=True)
class ExternalReference:
    """One external industry reference with full bibliographic provenance."""

    reference_id: str
    publisher: str
    original_url: str
    jurisdiction: str
    product_scope: str
    channel_scope: str
    access: str
    license_permission: str
    source_version: str
    publication_date: date | None = None
    effective_date: date | None = None
    retrieval_date: date | None = None
    refresh_due: datetime | None = None
    review_due: datetime | None = None

    def __post_init__(self) -> None:
        for field in (
            'reference_id',
            'publisher',
            'jurisdiction',
            'product_scope',
            'channel_scope',
            'license_permission',
            'source_version',
        ):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{field} must be a nonempty string')
        if not self.original_url.startswith(HTTPS):
            raise ValueError('original_url must be https')
        if self.access not in ACCESS:
            raise ValueError(f'unknown access {self.access!r}')


@dataclass(frozen=True)
class ExpertiseClaim:
    """An industry statement backed by at least one primary reference.

    Claims are always suggestion-grade: they may recommend a comparison and
    never replace an approved company policy.
    """

    claim_id: str
    statement: str
    reference_ids: tuple[str, ...]
    suggests_comparison_only: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, str) or not self.claim_id.strip():
            raise ValueError('claim_id must be a nonempty string')
        if not isinstance(self.statement, str) or not self.statement.strip():
            raise ValueError('statement must be a nonempty string')
        if not self.reference_ids:
            raise ValueError('claim must cite at least one reference')
        if not all(isinstance(rid, str) and rid.strip() for rid in self.reference_ids):
            raise ValueError('reference_ids must be nonempty strings')
        if type(self.suggests_comparison_only) is not bool:
            raise ValueError('suggests_comparison_only must be a bool')
        if not self.suggests_comparison_only:
            raise ValueError('industry claims never overwrite company policy')


def bind_claims(
    claims: tuple[ExpertiseClaim, ...],
    references: tuple[ExternalReference, ...],
) -> tuple[ExpertiseClaim, ...]:
    """Every cited reference id must exist in the reference set."""
    known = {ref.reference_id for ref in references}
    for claim in claims:
        missing = sorted(set(claim.reference_ids) - known)
        if missing:
            raise ValueError(f'claim {claim.claim_id!r} cites unknown references: {missing}')
    return claims
