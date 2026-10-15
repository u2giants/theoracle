"""S03 graph answer path: scoped retrieval, exact citations, explicit no-evidence."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

import pytest

from oracle_brain.graph.evidence_answer import (
    NO_EVIDENCE, FalkorEvidenceGraph, answer_from_graph)

ROOT = Path(__file__).resolve().parents[3]


def _url() -> str:
    url = os.environ.get("ORACLE2_TEST_FALKORDB_URL")
    if not url:
        pytest.skip("set ORACLE2_TEST_FALKORDB_URL to an approved loopback FalkorDB port")
    return url


def _block(key: str, text: str, title: str) -> dict:
    return {"block_id": uuid5(NAMESPACE_URL, key + ":b"), "source_id": uuid5(NAMESPACE_URL, key),
            "span_start": 0, "span_end": len(text), "text": text, "title": title}


@pytest.fixture()
def graph():
    g = FalkorEvidenceGraph(_url(), f"oracle2_evidence_test_{uuid4().hex[:12]}")
    g.reset()
    g.ingest([
        _block("kit", "The sample coordinator signs the color proof. The warehouse lead "
               "releases the kit after the signed proof appears in the release queue.",
               "Sample kit release"),
        _block("photo", "The studio editor marks the image approved. The catalog producer "
               "owns the approved asset and uploads it to the product page.",
               "Photo asset handoff"),
        _block("art", "Design signs the visual proof. The approval matrix lists a final "
               "approval field but leaves the owner blank.", "Packaging artwork"),
    ])
    yield g
    g.graph.delete()


def test_cites_only_the_relevant_source(graph):
    answer = answer_from_graph("Who releases a sample kit?",
                               graph.retrieve("Who releases a sample kit?"))
    assert answer.is_established_fact
    assert [c.source_id for c in answer.citations] == [uuid5(NAMESPACE_URL, "kit")]
    assert "warehouse lead releases the kit" in answer.answer_text
    assert all(c.quote in answer.answer_text for c in answer.citations)


def test_unrelated_question_says_no_evidence(graph):
    question = "What is the travel reimbursement limit for trade shows?"
    answer = answer_from_graph(question, graph.retrieve(question))
    assert answer.answer_text == NO_EVIDENCE
    assert answer.citations == [] and not answer.is_established_fact


def test_unresolved_owner_abstains_with_cited_gap(graph):
    question = "Who approves final packaging artwork?"
    answer = answer_from_graph(question, graph.retrieve(question))
    assert answer.answer_text.startswith("No source evidence resolves this question")
    assert "leaves the owner blank" in answer.answer_text
    assert not answer.is_established_fact
    assert [c.source_id for c in answer.citations] == [uuid5(NAMESPACE_URL, "art")]


def test_synthetic_rubric_meets_threshold():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "oracle2" / "score_s03_synthetic_rubric.py"),
         "--falkordb-url", _url()],
        capture_output=True, text=True, check=True)
    result = json.loads(completed.stdout)
    assert result["engine"] == "graph"
    assert result["passed"] >= 19, result["dimension_totals"]
    assert result["meets_threshold"] is True
    assert result["business_accepted"] is False
