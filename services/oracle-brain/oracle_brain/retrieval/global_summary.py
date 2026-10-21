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
from .packing import (CoverageBounds, SpanCandidate, SourceDependency, CurrentSourceReader,
                      current_supported_spans, coverage_after_access, dependency_for)
from .planner import AccessBounds

GlobalState = Literal["answered", "abstained"]


class GlobalSupport(_StrictModel):
    """One evidence span supporting a company-wide claim."""
    schema_version: Literal[1] = 1
    span_id: str = Field(min_length=1, max_length=200)
    source_id: UUID
    workspace_id: UUID
    quote: str = Field(min_length=1)
    roles: tuple[str, ...] = Field(min_length=1)
    revision: int = Field(strict=True, ge=1)


class GlobalClaim(_StrictModel):
    """One company-wide claim carrying revision and support spans."""
    schema_version: Literal[1] = 1
    claim: str = Field(min_length=1, max_length=4000)
    revision: int = Field(strict=True, ge=1)
    support: tuple[GlobalSupport, ...] = ()
    dependencies: tuple[SourceDependency, ...] = ()


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


def _reject_unsupported(claims, access, current_source_reader):
    accepted, rejected = [], []
    for index, claim in enumerate(claims):
        spans = tuple(SpanCandidate(span_id=s.span_id, source_id=s.source_id,
                                   workspace_id=s.workspace_id, revision=s.revision,
                                   quote=s.quote, roles=s.roles) for s in claim.support)
        current = (() if access is None else
                   current_supported_spans(spans, access, current_source_reader))
        if not current:
            # Never echo rejected/denied caller claim text in metadata either.
            rejected.append(f'claim-{index}')
            continue
        accepted.append(GlobalClaim(
            claim="\n".join(span.quote for span, _ in current),
            revision=max(span.revision for span, _ in current),
            support=tuple(GlobalSupport(span_id=span.span_id, source_id=span.source_id,
                                       workspace_id=span.workspace_id, revision=span.revision,
                                       quote=span.quote, roles=(access.role,))
                          for span, _ in current),
            dependencies=tuple(dep for _, dep in current)))
    return tuple(accepted), tuple(rejected)


def build_global_summary(
    *,
    question: str,
    claims: tuple[GlobalClaim, ...] | list[GlobalClaim],
    coverage: CoverageBounds | None,
    access: AccessBounds | None = None,
    current_source_reader: CurrentSourceReader | None = None,
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
            rejected_claims=tuple(f'claim-{i}' for i, _ in enumerate(claims)),
        )

    accepted, rejected = _reject_unsupported(tuple(claims), access, current_source_reader)
    required = tuple(dependency_for(SpanCandidate(
        span_id=s.span_id, source_id=s.source_id, workspace_id=s.workspace_id,
        revision=s.revision, quote=s.quote, roles=s.roles))
        for claim in claims for s in claim.support)
    authorized = tuple(dep for claim in accepted for dep in claim.dependencies)
    coverage = coverage_after_access(coverage, required, authorized,
                                     missing_support=bool(rejected) or not accepted)

    labels: list[str] = []
    caveats: list[str] = []
    if not coverage.complete:
        labels.append("partial_coverage")
        if coverage.represented is None:
            caveats.append("Represented population is UNKNOWN after unavailable source support; "
                           "source dependency counts do not determine business population coverage.")
        caveats.append(
            f"Coverage is partial ({coverage.represented if coverage.represented is not None else 'UNKNOWN'} of "
            f"{coverage.declared_population} in the declared population); "
            "this is not a complete aggregate total."
        )
    else:
        labels.append("complete_coverage")
        caveats.append(
            f"Coverage bounds: {coverage.represented} of "
            f"{coverage.declared_population} in the declared population."
        )

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
