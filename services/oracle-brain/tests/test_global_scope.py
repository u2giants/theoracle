"""S09 offline gate: company-wide/global scope answers.

Invented/synthetic only. No employees, no company data.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from oracle_brain.retrieval.global_summary import (
    GlobalClaim,
    GlobalSummary,
    GlobalSupport,
    build_global_summary,
)
from oracle_brain.retrieval.packing import CoverageBounds


@pytest.fixture()
def source_id():
    return uuid4()


def _support(span_id: str = "s1", source_id=None, revision: int = 1) -> GlobalSupport:
    return GlobalSupport(
        span_id=span_id,
        source_id=source_id or uuid4(),
        revision=revision,
    )


def test_no_company_wide_claim_without_coverage(source_id):
    claim = GlobalClaim(
        claim="Every process uses the warehouse lead.",
        revision=2,
        support=(_support(source_id=source_id),),
    )
    summary = build_global_summary(
        question="Company-wide, who releases kits?",
        claims=(claim,),
        coverage=None,
    )
    assert summary.state == "abstained"
    assert summary.coverage is None and summary.claims == ()
    assert any("explicit coverage bounds" in c for c in summary.caveats)
    assert summary.rejected_claims == ("Every process uses the warehouse lead.",)


def test_partial_coverage_labeled_and_never_complete(source_id):
    coverage = CoverageBounds(declared_population=4, represented=2, complete=False)
    claim = GlobalClaim(
        claim="Two processes use kits.",
        revision=3,
        support=(_support("s1", source_id=source_id, revision=3),),
    )
    summary = build_global_summary(
        question="Company-wide, how many processes use kits?",
        claims=(claim,),
        coverage=coverage,
    )
    assert summary.state == "answered"
    assert summary.coverage == coverage
    assert "partial_coverage" in summary.labels
    assert "complete_coverage" not in summary.labels
    assert any("not a complete aggregate total" in c for c in summary.caveats)
    assert any("2 of 4" in c for c in summary.caveats)


def test_complete_coverage_states_bounds(source_id):
    coverage = CoverageBounds(declared_population=2, represented=2, complete=True)
    claim = GlobalClaim(
        claim="Both processes use kits.",
        revision=1,
        support=(_support(source_id=source_id),),
    )
    summary = build_global_summary(
        question="Company-wide, how many processes use kits?",
        claims=(claim,),
        coverage=coverage,
    )
    assert summary.state == "answered"
    assert "complete_coverage" in summary.labels
    assert "partial_coverage" not in summary.labels
    assert any("Coverage bounds: 2 of 2" in c for c in summary.caveats)


def test_published_claims_retain_revision_and_support(source_id):
    coverage = CoverageBounds(declared_population=2, represented=2, complete=True)
    support = _support("s9", source_id=source_id, revision=5)
    claim = GlobalClaim(
        claim="Both processes use kits.",
        revision=5,
        support=(support,),
    )
    summary = build_global_summary(
        question="Company-wide, how many processes use kits?",
        claims=(claim,),
        coverage=coverage,
    )
    assert summary.claims[0].revision == 5
    assert summary.claims[0].support[0].span_id == "s9"
    assert summary.claims[0].support[0].revision == 5
    assert summary.claims[0].support[0].source_id == source_id


def test_unsupported_claim_is_rejected():
    coverage = CoverageBounds(declared_population=2, represented=2, complete=True)
    bare = GlobalClaim(claim="Invented total.", revision=1, support=())
    summary = build_global_summary(
        question="Company-wide, totals?",
        claims=(bare,),
        coverage=coverage,
    )
    assert summary.state == "abstained"
    assert summary.claims == ()
    assert summary.rejected_claims == ("Invented total.",)
    assert any("No supported company-wide claim." in c for c in summary.caveats)


def test_mixed_claims_keep_only_supported(source_id):
    coverage = CoverageBounds(declared_population=3, represented=1, complete=False)
    supported = GlobalClaim(
        claim="One process uses kits.",
        revision=2,
        support=(_support(source_id=source_id),),
    )
    bare = GlobalClaim(claim="Three processes use kits.", revision=2, support=())
    summary = build_global_summary(
        question="Company-wide, how many processes use kits?",
        claims=(supported, bare),
        coverage=coverage,
    )
    assert summary.state == "answered"
    assert len(summary.claims) == 1
    assert summary.claims[0].claim == "One process uses kits."
    assert summary.rejected_claims == ("Three processes use kits.",)


def test_empty_question_raises():
    with pytest.raises(ValueError):
        build_global_summary(question="  ", claims=(), coverage=None)


def test_summary_shape():
    assert issubclass(GlobalSummary, object)
