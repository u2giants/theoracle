"""S05 offline gate: Graphiti candidate store cannot mutate confirmed state.

Real assertions against the candidate-only boundary on main
(oracle_brain.graph.graphiti_candidates + contracts.CandidateBundle).
Invented/synthetic only.
"""
from __future__ import annotations

from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from oracle_brain.contracts import CandidateAssertion, CandidateBundle, SourceSpan
from oracle_brain.graph.graphiti_candidates import ExtractedRelation, candidate_bundle

WS = uuid4()
RUN = uuid4()
SRC = uuid4()
TEXT = "Intake Lead sends the packet to Review Team."
QUOTE = "sends the packet"
START = TEXT.index(QUOTE)
END = START + len(QUOTE)


def _rel(**over):
    base = dict(
        subject="Intake Lead", predicate="sends", object="packet",
        quote=QUOTE, start=START, end=END, confidence=0.9,
    )
    base.update(over)
    return ExtractedRelation(**base)


def test_candidate_bundle_requires_exact_source_span():
    with pytest.raises(ValueError, match="exact source-span"):
        candidate_bundle(
            workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=1,
            source_text=TEXT, relations=[_rel(quote="invented quote")],
        )


def test_candidate_bundle_rejects_unanchored_graphiti_style_fact():
    with pytest.raises(ValueError, match="exact source-span"):
        candidate_bundle(
            workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=1,
            source_text=TEXT,
            relations=[_rel(quote=QUOTE, start=0, end=len(QUOTE))],
        )


def test_candidate_bundle_rejects_inverted_or_out_of_range_spans():
    for start, end in ((END, START), (-1, 5), (0, len(TEXT) + 1), (5, 5)):
        with pytest.raises(ValueError, match="exact source-span"):
            candidate_bundle(
                workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=1,
                source_text=TEXT, relations=[_rel(start=start, end=end)],
            )


def test_candidate_assertion_carries_no_write_path_to_confirmed_graph():
    bundle = candidate_bundle(
        workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=1,
        source_text=TEXT, relations=[_rel()],
    )
    assert isinstance(bundle, CandidateBundle)
    assert bundle.workspace_id == WS
    assert all(isinstance(a, CandidateAssertion) for a in bundle.assertions)
    for forbidden in ("promote", "confirm", "project", "mutate", "write_confirmed"):
        assert not hasattr(bundle, forbidden)
        assert not any(hasattr(a, forbidden) for a in bundle.assertions)


def test_extracted_relation_exposes_no_graphiti_edge_internals():
    rel = _rel()
    data = rel.model_dump()
    assert set(data) == {"subject", "predicate", "object", "quote", "start", "end", "confidence"}
    for forbidden in ("fact", "episodes", "uuid", "edge_id", "valid_at", "invalid_at"):
        assert forbidden not in data


def test_candidate_assertion_ids_are_deterministic_and_source_bound():
    first = candidate_bundle(
        workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=1,
        source_text=TEXT, relations=[_rel()],
    )
    second = candidate_bundle(
        workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=1,
        source_text=TEXT, relations=[_rel()],
    )
    assert first.assertions[0].assertion_id == second.assertions[0].assertion_id
    expected = uuid5(NAMESPACE_URL, f"{WS}/{SRC}/1/0/{QUOTE}")
    assert first.assertions[0].assertion_id == expected
    other_rev = candidate_bundle(
        workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=2,
        source_text=TEXT, relations=[_rel()],
    )
    assert other_rev.assertions[0].assertion_id != first.assertions[0].assertion_id


def test_candidate_span_never_claims_a_different_source():
    bundle = candidate_bundle(
        workspace_id=WS, run_id=RUN, source_id=SRC, source_revision=3,
        source_text=TEXT, relations=[_rel()],
    )
    span = bundle.assertions[0].span
    assert isinstance(span, SourceSpan)
    assert span.source_id == SRC
    assert span.source_revision == 3
    assert TEXT[span.start:span.end] == span.quote
