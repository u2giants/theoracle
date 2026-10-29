"""Community detection and hierarchical reports (plan step 8).

Seeds projected maps straight into Postgres, runs the ``communities`` job with
replayed frontier reports and asserts the Leiden grouping, the small-community
merge and the finding/source rules from the step's done-when. No test calls a
real model.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import fake_embeddings, fake_relations, fake_scaledown
from test_flat import PDF_FIXTURE, TRANSCRIPT_FIXTURE, _seed_fixture, _seed_text
from test_project import _entity, _mention, _relation, _seed_approval_map
from test_resolve import _fake as _fake_resolve

from brain.config import get_settings
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.graph.communities import run_communities
from brain.graph.project import run_project
from brain.resolve import resolve as resolve_mod
from brain.resolve.resolve import run_resolve


class FakeReport:
    """Replay one canned community report for every frontier call."""

    def __init__(
        self,
        title: str = "Licensing approval hand-off",
        findings: list[dict[str, Any]] | None = None,
        open_questions: list[str] | None = None,
    ) -> None:
        self.title = title
        self.findings = findings if findings is not None else []
        self.open_questions = open_questions if open_questions is not None else []
        self.prompts: list[str] = []

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        self.prompts.append(str(messages[-1]["content"]))
        answer = {
            "title": self.title,
            "summary": (
                "The approval moves from Design to Licensing and stalls at sign-off."
            ),
            "findings": self.findings,
            "open_questions": self.open_questions,
        }
        return {
            "choices": [{"message": {"content": json.dumps(answer)}}],
            "usage": {"total_tokens": 50},
        }


def _fake(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> FakeReport:
    fake = FakeReport(**kwargs)
    monkeypatch.setattr(resolve_mod, "_post_chat", fake)
    return fake


def _community_of(db: Any, entity_name: str) -> str:
    row = db.execute(
        "SELECT c.id FROM cmap.community c "
        "JOIN cmap.entity e ON e.id = ANY(c.entity_ids) "
        "WHERE c.level = 0 AND e.canonical_name = %s",
        (entity_name,),
    ).fetchone()
    return str(row[0])


def _seed_second_cluster(db: Any) -> None:
    """A vendor/customer pair far away from the approval cluster."""
    source = _seed_text(db, "The vendor ships to the customer.", "vendor")
    vendor = _entity(db, "Vendor", "Acme Factory", mentions=2, sources=1)
    customer = _entity(db, "Customer", "Big Box", mentions=2, sources=1)
    v_m = _mention(db, source, "Vendor", "Acme Factory", vendor)
    c_m = _mention(db, source, "Customer", "Big Box", customer)
    _relation(db, source, v_m, c_m, "PRODUCES", "the factory ships", confidence=0.9)


def test_leiden_groups_fixture_approval_nodes_together(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """The approval entities land in one level-0 community, apart from the rest."""
    _seed_approval_map(db)
    _seed_second_cluster(db)
    run_project()
    _fake(monkeypatch)
    run_communities()
    jessica = _community_of(db, "Jessica Smith (Licensing Manager)")
    assert jessica == _community_of(db, "approval step")
    assert jessica == _community_of(db, "the approval step is the bottleneck")
    assert jessica != _community_of(db, "Acme Factory")


def test_second_pass_reuses_stored_reports(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """A rerun over the same graph reuses every report and asks nothing."""
    _seed_approval_map(db)
    run_project()
    fake = _fake(monkeypatch)
    first = run_communities()
    prompts_after_first = len(fake.prompts)
    rows_after_first = db.execute(
        "SELECT count(*) FROM cmap.community"
    ).fetchone()[0]
    second = run_communities()
    assert len(fake.prompts) == prompts_after_first
    assert (
        db.execute("SELECT count(*) FROM cmap.community").fetchone()[0]
        == rows_after_first
    )
    assert first["reports"] == rows_after_first
    assert second["reports_reused"] == second["reports"]
    assert second["reports_failed"] == 0
    assert second.get("frontier_calls", 0) == 0


def test_small_communities_merged(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    """A 2-entity community with only one neighbour folds into it."""
    source = _seed_text(db, "cluster seed", "clusters")
    big = [
        _entity(db, "Step", f"Big step {index}", mentions=1, sources=1)
        for index in range(4)
    ]
    big_mentions = [
        _mention(db, source, "Step", f"Big step {index}", entity_id)
        for index, entity_id in enumerate(big)
    ]
    for first, second in ((0, 1), (1, 2), (2, 3), (3, 0), (0, 2)):
        _relation(
            db,
            source,
            big_mentions[first],
            big_mentions[second],
            "PRECEDES",
            "chain",
            confidence=0.9,
        )
    small_a = _entity(db, "Rule", "Tiny rule A", mentions=1, sources=1)
    small_b = _entity(db, "Rule", "Tiny rule B", mentions=1, sources=1)
    sa = _mention(db, source, "Rule", "Tiny rule A", small_a)
    sb = _mention(db, source, "Rule", "Tiny rule B", small_b)
    _relation(db, source, sa, sb, "APPLIES_TO", "tiny pair", confidence=0.9)
    _relation(db, source, sa, big_mentions[0], "APPLIES_TO", "bridge", confidence=0.9)
    run_project()
    _fake(monkeypatch)
    run_communities()
    communities = db.execute(
        "SELECT cardinality(entity_ids) FROM cmap.community WHERE level = 0"
    ).fetchall()
    assert all(size >= 3 for (size,) in communities)
    assert _community_of(db, "Tiny rule A") == _community_of(db, "Big step 0")


def test_report_findings_cite_sources(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    """Findings without a real source_id never reach the stored report."""
    fake_embeddings(monkeypatch)
    _seed_approval_map(db)
    real_source = str(
        db.execute("SELECT id FROM cmap.source ORDER BY title LIMIT 1").fetchone()[0]
    )
    run_project()
    fake = _fake(
        monkeypatch,
        findings=[
            {
                "text": "The sign-off stalls the release.",
                "kind": "bottleneck",
                "stance": "report",
                "entity_ids": [],
                "source_ids": [real_source],
            },
            {
                "text": "An uncited claim.",
                "kind": "rule",
                "stance": "policy",
                "entity_ids": [],
                "source_ids": [],
            },
            {
                "text": "A claim citing nothing real.",
                "kind": "rule",
                "stance": "policy",
                "entity_ids": [],
                "source_ids": ["00000000-0000-4000-8000-0000000000ff"],
            },
        ],
        open_questions=["Who owns the sign-off?"],
    )
    stats = run_communities()
    assert stats["findings_dropped"] == 2 * stats["reports"]
    rows = db.execute("SELECT findings FROM cmap.community").fetchall()
    for (findings,) in rows:
        for finding in findings:
            assert finding["source_ids"]
            assert all(
                source_id != "00000000-0000-4000-8000-0000000000ff"
                for source_id in finding["source_ids"]
            )
    questions = db.execute(
        "SELECT question, why, state FROM cmap.open_question"
    ).fetchall()
    assert questions == [
        ("Who owns the sign-off?", "Licensing approval hand-off", "open")
    ]
    company_prompt = fake.prompts[-1]
    assert "Top 10 cross-department issues" in company_prompt
    assert "the whole company" in company_prompt
    level0_prompts = [
        prompt
        for prompt in fake.prompts
        if "one area of how a company operates" in prompt
    ]
    assert level0_prompts


def test_fixture_report_context_covers_pdf_and_transcript(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Done-when shape: one community's context carries both real sources."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "transcript.json", "pdf.json")
    fake_relations(monkeypatch)
    transcript = _seed_fixture(db, TRANSCRIPT_FIXTURE, "transcript")
    pdf = _seed_fixture(db, PDF_FIXTURE, "pdf")
    handle_classify_extract({"payload": {"source_id": transcript}})
    handle_classify_extract({"payload": {"source_id": pdf}})
    handle_relations({"payload": {"source_id": transcript}})
    handle_relations({"payload": {"source_id": pdf}})
    _fake_resolve(monkeypatch)
    run_resolve()
    run_project()
    fake = _fake(monkeypatch)
    run_communities()
    transcript_ids = [
        str(row[0])
        for row in db.execute(
            "SELECT id FROM cmap.source WHERE title LIKE '%teams-approval%'"
        ).fetchall()
    ]
    pdf_ids = [
        str(row[0])
        for row in db.execute(
            "SELECT id FROM cmap.source WHERE title LIKE '%licensing-approval-procedure%'"
        ).fetchall()
    ]
    assert transcript_ids and pdf_ids
    level0_prompts = [
        prompt
        for prompt in fake.prompts
        if "one area of how a company operates" in prompt
    ]
    assert any(
        any(source_id in prompt for source_id in transcript_ids)
        and any(source_id in prompt for source_id in pdf_ids)
        for prompt in level0_prompts
    ), "no level-0 community sees both the transcript and the PDF procedure"
    assert "Top 10 cross-department issues" in fake.prompts[-1]
