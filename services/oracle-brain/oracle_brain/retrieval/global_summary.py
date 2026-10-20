"""Company-wide summary with explicit coverage, revision and support; pure.

No company-wide claim is published without explicit coverage bounds. Partial
coverage is labeled and never sold as a complete aggregate total. Every
retained claim carries its revision and its support spans. Unsupported claims
are rejected. No company data, no employees, no provider calls.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field

from ..operating_model.source_receipts import _StrictModel
from .packing import CoverageBounds

GlobalState = Literal["answered", "abstained"]


class GlobalSupport(_StrictModel):
    """One evidence span supporting a company-wide claim."""
    schema_version: Literal[1] = 1
    span_id: str = Field(min_length=1, max_length=200)
    source_id: UUID
    revision: int = Field(strict=True, ge=1)


class GlobalClaim(_StrictModel):
    """One company-wide claim carrying revision and support spans."""
    schema_version: Literal[1] = 1
    claim: str = Field(min_length=1, max_length=4000)
    revision: int = Field(strict=True, ge=1)
    support: tuple[GlobalSupport, ...] = ()


class GlobalSummary(_StrictModel):
    """Coverage-honest company-wide summary."""
    schema_version: Literal[1] = 1
    state: GlobalState
    question: str = Field(min_length=1, max_length=4000)
    coverage: CoverageBounds | None = None
    claims: tuple[GlobalClaim, ...] = ()
    labels: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    rejected_claims: tuple[str, ...] = ()


def _reject_unsupported(
    claims: tuple[GlobalClaim, ...] | list[GlobalClaim],
) -> tuple[tuple[GlobalClaim, ...], tuple[str, ...]]:
    accepted = tuple(claim for claim in claims if claim.support)
    rejected = tuple(claim.claim for claim in claims if not claim.support)
    return accepted, rejected


def build_global_summary(
    *,
    question: str,
    claims: tuple[GlobalClaim, ...] | list[GlobalClaim],
    coverage: CoverageBounds | None,
) -> GlobalSummary:
    """Assemble a company-wide summary under explicit coverage bounds.

    Without coverage bounds the summary abstains and publishes no claim.
    Partial coverage is labeled partial_coverage with a never-complete-total
    caveat. Complete coverage states the bounds. Every published claim retains
    its revision and support. Claims lacking support never construct.
    """
    if not question.strip():
        raise ValueError("question must be non-empty")

    if coverage is None:
        return GlobalSummary(
            state="abstained",
            question=question,
            coverage=None,
            claims=(),
            labels=(),
            caveats=(
                "No company-wide claim without explicit coverage bounds.",
                "Missing evidence must abstain.",
            ),
            rejected_claims=tuple(claim.claim for claim in claims),
        )

    labels: list[str] = []
    caveats: list[str] = []
    if not coverage.complete:
        labels.append("partial_coverage")
        caveats.append(
            f"Coverage is partial ({coverage.represented} of "
            f"{coverage.declared_population} in the declared population); "
            "this is not a complete aggregate total."
        )
    else:
        labels.append("complete_coverage")
        caveats.append(
            f"Coverage bounds: {coverage.represented} of "
            f"{coverage.declared_population} in the declared population."
        )

    accepted, rejected = _reject_unsupported(tuple(claims))

    if not accepted:
        return GlobalSummary(
            state="abstained",
            question=question,
            coverage=coverage,
            claims=(),
            labels=tuple(labels),
            caveats=tuple(caveats) + ("No supported company-wide claim.",),
            rejected_claims=rejected,
        )

    return GlobalSummary(
        state="answered",
        question=question,
        coverage=coverage,
        claims=accepted,
        labels=tuple(labels),
        caveats=tuple(caveats),
        rejected_claims=rejected,
    )
