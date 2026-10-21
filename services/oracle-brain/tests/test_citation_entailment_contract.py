"""S09 offline gate: citation entailment contract.

Invented/synthetic only. No employees, no company data.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from oracle_brain.retrieval.citations import (
    EntailmentReport,
    EntailmentResult,
    QuoteCitation,
    SourceText,
    align_quote,
    content_tokens,
    quote_entails_claim,
    validate_citation,
    validate_citations,
)


@pytest.fixture()
def source_id():
    return uuid4()


@pytest.fixture()
def source(source_id) -> SourceText:
    return SourceText(
        source_id=source_id,
        text="The warehouse lead releases the sample kit after the signed color proof.",
    )


def test_valid_quote_entails_claim(source_id, source):
    citation = QuoteCitation(
        source_id=source_id,
        span_start=4,
        span_end=len("The warehouse lead releases the sample kit"),
        quote="warehouse lead releases the sample kit",
    )
    result = validate_citation(
        claim="warehouse lead releases the sample kit",
        citation=citation,
        sources=(source,),
    )
    assert result.valid and result.citation == citation
    assert "entails claim" in result.reason


def test_quote_must_match_source_offsets(source_id, source):
    citation = QuoteCitation(
        source_id=source_id,
        span_start=0,
        span_end=3,
        quote="the warehouse lead releases",  # does not match source[0:3]
    )
    result = validate_citation(
        claim="the warehouse lead releases",
        citation=citation,
        sources=(source,),
    )
    assert not result.valid
    assert "does not match source" in result.reason


def test_unsupported_claim_is_rejected(source_id, source):
    citation = QuoteCitation(
        source_id=source_id,
        span_start=0,
        span_end=len("The warehouse lead releases"),
        quote="The warehouse lead releases",
    )
    result = validate_citation(
        claim="Finance approves the budget every quarter.",
        citation=citation,
        sources=(source,),
    )
    assert not result.valid
    assert "unsupported claim" in result.reason


def test_span_out_of_bounds_is_rejected(source_id, source):
    citation = QuoteCitation(
        source_id=source_id,
        span_start=0,
        span_end=len(source.text) + 10,
        quote="anything",
    )
    assert align_quote(citation, (source,)) is None
    result = validate_citation(
        claim="anything here",
        citation=citation,
        sources=(source,),
    )
    assert not result.valid


def test_unknown_source_is_rejected(source_id, source):
    citation = QuoteCitation(
        source_id=uuid4(),
        span_start=0,
        span_end=5,
        quote="The warehouse",
    )
    result = validate_citation(
        claim="warehouse lead releases",
        citation=citation,
        sources=(source,),
    )
    assert not result.valid


def test_report_accepts_only_when_all_citations_valid(source_id, source):
    good = QuoteCitation(
        source_id=source_id,
        span_start=4,
        span_end=len("The warehouse lead releases the sample kit"),
        quote="warehouse lead releases the sample kit",
    )
    bad = QuoteCitation(
        source_id=source_id,
        span_start=0,
        span_end=3,
        quote="nope",
    )
    report = validate_citations(
        claim="warehouse lead releases the sample kit",
        citations=(good,),
        sources=(source,),
    )
    assert report.valid and report.accepted and not report.rejected

    mixed = validate_citations(
        claim="warehouse lead releases the sample kit",
        citations=(good, bad),
        sources=(source,),
    )
    assert not mixed.valid
    assert len(mixed.accepted) == 1 and len(mixed.rejected) == 1


def test_entailment_requires_exact_extraction(source_id):
    assert quote_entails_claim("signed color proof", "signed color proof")
    assert not quote_entails_claim("signed color proof", "the signed color proof step")
    assert not quote_entails_claim("signed color proof", "the sample kit handoff")
    assert not quote_entails_claim("   ", "anything")
    assert "warehouse" in content_tokens("The Warehouse lead")


def test_empty_claim_raises(source_id, source):
    citation = QuoteCitation(
        source_id=source_id,
        span_start=0,
        span_end=3,
        quote="The",
    )
    with pytest.raises(ValueError):
        validate_citation(claim="  ", citation=citation, sources=(source,))


def test_result_shapes():
    assert issubclass(EntailmentResult, object)
    assert issubclass(EntailmentReport, object)


@pytest.mark.parametrize(('claim', 'quote'), [
    ('The kit was approved.', 'The kit was not approved.'),
    ('Finance approved the kit.', 'The kit approved Finance.'),
    ('Ten kits shipped.', 'Two kits shipped.'),
])
def test_token_overlap_never_establishes_semantic_entailment(claim, quote):
    assert not quote_entails_claim(claim, quote)
