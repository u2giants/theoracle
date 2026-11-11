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
        self.answered: list[str] = []
        self.importance: dict[str, int] = {}
        self.department = ""

    @staticmethod
    def _candidates(prompt: str) -> list[str]:
        body = prompt.split("CANDIDATES:\n<<<", 1)[1].rsplit(">>>", 1)[0]
        return [block.split("\n", 1)[0] for block in body.strip().split("\n\n")]

    def __call__(
        self, messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        self.prompts.append(prompt)
        if prompt.startswith("QUESTION VETTING"):
            results = [
                {
                    "n": n,
                    "answered": any(a in line for a in self.answered),
                    "importance": next(
                        (v for k, v in self.importance.items() if k in line), 4
                    ),
                    "person": "",
                    "department": self.department,
                }
                for n, line in enumerate(self._candidates(prompt), start=1)
            ]
            return {
                "choices": [{"message": {"content": json.dumps({"results": results})}}],
                "usage": {"total_tokens": 5},
            }
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
    """A vendor/customer/factory trio far away from the approval cluster."""
    source = _seed_text(db, "The vendor ships to the customer.", "vendor")
    vendor = _entity(db, "Vendor", "Acme Factory", mentions=2, sources=1)
    customer = _entity(db, "Customer", "Big Box", mentions=2, sources=1)
    factory = _entity(db, "System", "Line 7", mentions=2, sources=1)
    v_m = _mention(db, source, "Vendor", "Acme Factory", vendor)
    c_m = _mention(db, source, "Customer", "Big Box", customer)
    f_m = _mention(db, source, "System", "Line 7", factory)
    _relation(db, source, v_m, c_m, "PRODUCES", "the factory ships", confidence=0.9)
    _relation(db, source, f_m, v_m, "DEPENDS_ON", "the line feeds the vendor", confidence=0.9)


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


def test_question_the_brain_can_answer_is_not_stored(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Owner 2026-11-10: if the brain already knows the answer, there is no question."""
    from brain.config import get_settings
    from brain.graph import communities as comm
    from brain.resolve.resolve import _Frontier

    fake_embeddings(monkeypatch)

    fake = _fake(monkeypatch)
    fake.answered = ["Who owns the sign-off?"]
    report = {"title": "r", "open_questions": ["Who owns the sign-off?", "When is the cutoff?"]}
    written = comm._store_open_questions(
        db, report, [], _Frontier(get_settings(), "reports"), get_settings(), set()
    )
    db.commit()
    rows = [r[0] for r in db.execute("SELECT question FROM cmap.open_question").fetchall()]
    assert written == 1
    assert rows == ["When is the cutoff?"]


def test_only_the_few_important_questions_are_kept(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Owner 2026-11-10: not a question for every small gap — the few that matter."""
    from brain.config import get_settings
    from brain.graph import communities as comm
    from brain.resolve.resolve import _Frontier

    fake_embeddings(monkeypatch)
    fake = _fake(monkeypatch)
    fake.importance = {"trivia": 2, "core": 5}
    fake.department = ""
    report = {
        "title": "r",
        "open_questions": ["trivia one?", "ok a?", "ok b?", "ok c?", "core gap?"],
    }
    written = comm._store_open_questions(
        db, report, [], _Frontier(get_settings(), "reports"), get_settings(), set()
    )
    db.commit()
    rows = db.execute(
        "SELECT question, priority, department FROM cmap.open_question ORDER BY priority DESC"
    ).fetchall()
    assert written == comm.MAX_QUESTIONS_PER_AREA == len(rows)
    assert rows[0] == ("core gap?", 5, "")
    assert all("trivia" not in row[0] for row in rows)


def test_failed_knowledge_check_stores_nothing(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    from brain.config import get_settings
    from brain.graph import communities as comm
    from brain.resolve.resolve import _Frontier

    fake_embeddings(monkeypatch)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("model down")

    monkeypatch.setattr(resolve_mod, "_post_chat", _boom)
    report = {"title": "r", "open_questions": ["When is the cutoff?"]}
    written = comm._store_open_questions(
        db, report, [], _Frontier(get_settings(), "reports"), get_settings(), set()
    )
    assert written == 0


def test_rerun_retires_answered_and_replaced_questions(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Old unasked questions go when their area is rebuilt or the brain learns the answer."""
    from brain.config import get_settings
    from brain.graph import communities as comm
    from brain.resolve.resolve import _Frontier

    fake_embeddings(monkeypatch)

    fake = _fake(monkeypatch)
    kept = "00000000-0000-4000-8000-000000000001"
    for text, ids in (
        ("Rebuilt area question?", ["00000000-0000-4000-8000-000000000002"]),
        ("Now answered question?", [kept]),
        ("Still unknown question?", [kept]),
    ):
        db.execute(
            "INSERT INTO cmap.open_question (question, why, entity_ids, created_at) "
            "VALUES (%s, 'old', %s, now() - interval '1 day')",
            (text, ids),
        )
    db.commit()
    fake.answered = ["Now answered question?"]
    retired = comm._refresh_open_questions(
        db,
        db.execute("SELECT now()").fetchone()[0],
        {frozenset([kept])},
        _Frontier(get_settings(), "reports"),
        get_settings(),
    )
    states = dict(db.execute("SELECT question, state FROM cmap.open_question").fetchall())
    assert retired == 2
    assert states == {
        "Rebuilt area question?": "dismissed",
        "Now answered question?": "dismissed",
        "Still unknown question?": "open",
    }


