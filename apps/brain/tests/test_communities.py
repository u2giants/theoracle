"""Community detection and hierarchical reports (plan step 8).

Seeds projected maps straight into Postgres, runs the ``communities`` job with
replayed frontier reports and asserts the Leiden grouping, the small-community
merge and the finding/source rules from the step's done-when. No test calls a
real model.
"""

from __future__ import annotations

import json
from collections.abc import Callable
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

DEFAULT_SUMMARY = "The approval moves from Design to Licensing and stalls at sign-off."


class FakeReport:
    """Replay one canned community report for every frontier call.

    Also answers the map-reduce summarisation prompts (``context_summary.md``)
    and the knowledge-check vetting prompts; pass ``summarise`` to control how
    batches are compressed and ``numbered`` to give every report a distinct
    title (Area 1, Area 2, …).
    """

    def __init__(
        self,
        title: str = "Licensing approval hand-off",
        findings: list[dict[str, Any]] | None = None,
        open_questions: list[str] | None = None,
        summary: str = DEFAULT_SUMMARY,
        numbered: bool = False,
        summarise: Callable[[str], str] | None = None,
    ) -> None:
        self.title = title
        self.findings = findings if findings is not None else []
        self.open_questions = open_questions if open_questions is not None else []
        self.summary = summary
        self.numbered = numbered
        self.summarise = summarise
        self.report_calls = 0
        self.prompts: list[str] = []
        self.answered: list[str] = []
        self.importance: dict[str, int] = {}
        self.department = ""

    @staticmethod
    def _candidates(prompt: str) -> list[str]:
        body = prompt.split("CANDIDATES:\n<<<", 1)[1].rsplit(">>>", 1)[0]
        return [block.split("\n", 1)[0] for block in body.strip().split("\n\n")]

    @staticmethod
    def _default_summarise(prompt: str) -> str:
        body = prompt.split("<<<", 1)[-1].rsplit(">>>", 1)[0]
        titles = [line for line in body.splitlines() if line.startswith("## ")]
        return " ".join(titles) + " | " + " ".join(body.split())[:200]

    def __call__(
        self, messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        del settings
        prompt = str(messages[-1]["content"])
        self.prompts.append(prompt)
        if prompt.startswith("You are compressing"):
            summariser = self.summarise or self._default_summarise
            return {
                "choices": [
                    {"message": {"content": json.dumps({"summary": summariser(prompt)})}}
                ],
                "usage": {"total_tokens": 5},
            }
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
        self.report_calls += 1
        answer = {
            "title": f"Area {self.report_calls}" if self.numbered else self.title,
            "summary": self.summary,
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




def _stale_report(db: Any, version: int, title: str, level: int = 1) -> str:
    row = db.execute(
        "INSERT INTO cmap.community (level, title, report_md, findings, "
        "entity_ids, graph_version) VALUES (%s, %s, '# x', '[]', '{}', %s) RETURNING id",
        (level, title, version),
    ).fetchone()
    db.commit()
    return str(row[0])


def test_old_versions_pruned(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    """Repair A1: a successful build deletes reports older than two versions.

    Reports a recommendation or a review flag still points at are kept, and a
    report left on the current version that this build did not choose stops
    counting as current.
    """
    _seed_approval_map(db)
    for _ in range(3):
        run_project()
    current = db.execute("SELECT MAX(version) FROM cmap.graph_version").fetchone()[0]
    assert current >= 3
    ancient = _stale_report(db, current - 2, "ancient")
    ancient_child = _stale_report(db, current - 2, "ancient child", level=0)
    previous = _stale_report(db, current - 1, "previous")
    recommended = _stale_report(db, current - 2, "has a recommendation")
    flagged = _stale_report(db, current - 2, "has a review flag")
    leftover = _stale_report(db, current, "same version, not chosen")
    db.execute(
        "UPDATE cmap.community SET parent_id = %s WHERE id = %s",
        (ancient, ancient_child),
    )
    db.execute(
        "UPDATE cmap.community SET parent_id = %s WHERE id = %s", (ancient, previous)
    )
    db.execute(
        "INSERT INTO cmap.recommendation (community_id, problem, explanations, "
        "options, experiment) VALUES (%s, 'p', '[]', '[]', '{}')",
        (recommended,),
    )
    db.execute(
        "INSERT INTO cmap.review_flag (item_type, item_id) VALUES ('community', %s)",
        (flagged,),
    )
    db.commit()
    _fake(monkeypatch)
    stats = run_communities()
    left = {
        str(row[0]): int(row[1])
        for row in db.execute("SELECT id, graph_version FROM cmap.community").fetchall()
    }
    assert ancient not in left and ancient_child not in left
    assert stats["communities_pruned"] == 2
    assert left[previous] == current - 1
    assert recommended in left and flagged in left
    assert left[leftover] == current - 1
    built = [version for version in left.values() if version == current]
    assert len(built) == stats["reports"]
    assert (
        db.execute(
            "SELECT parent_id FROM cmap.community WHERE id = %s", (previous,)
        ).fetchone()[0]
        is None
    )


def test_prune_can_be_switched_off(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    """BRAIN_COMMUNITY_PRUNE_ENABLED=false keeps every old report."""
    monkeypatch.setenv("BRAIN_COMMUNITY_PRUNE_ENABLED", "false")
    get_settings.cache_clear()
    try:
        _seed_approval_map(db)
        for _ in range(3):
            run_project()
        current = db.execute("SELECT MAX(version) FROM cmap.graph_version").fetchone()[0]
        ancient = _stale_report(db, current - 2, "ancient")
        _fake(monkeypatch)
        stats = run_communities()
        assert "communities_pruned" not in stats
        assert db.execute(
            "SELECT 1 FROM cmap.community WHERE id = %s", (ancient,)
        ).fetchone()
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# --- Repair C3: clusters inside functions, stable identities ---------------


def _seed_function(db: Any, key: str, name: str) -> str:
    """One curated business function; return its id."""
    row = db.execute(
        "INSERT INTO cmap.function (key, name) VALUES (%s, %s) RETURNING id",
        (key, name),
    ).fetchone()
    db.commit()
    return str(row[0])


def _assign_function(
    db: Any, entity_id: str, function_id: str, weight: float = 1.0
) -> None:
    """Assign one entity to one function (C2's entity_function table)."""
    db.execute(
        "INSERT INTO cmap.entity_function (entity_id, function_id, weight) "
        "VALUES (%s, %s, %s) "
        "ON CONFLICT (entity_id, function_id) DO UPDATE SET weight = EXCLUDED.weight",
        (entity_id, function_id, weight),
    )
    db.commit()


def _entity_id(db: Any, name: str) -> str:
    row = db.execute(
        "SELECT id FROM cmap.entity WHERE canonical_name = %s", (name,)
    ).fetchone()
    return str(row[0])


def _mention_id(db: Any, entity_id: str) -> str:
    row = db.execute(
        "SELECT id FROM cmap.mention WHERE entity_id = %s ORDER BY id LIMIT 1",
        (entity_id,),
    ).fetchone()
    return str(row[0])


def _first_source(db: Any) -> str:
    return str(db.execute("SELECT id FROM cmap.source LIMIT 1").fetchone()[0])


def test_function_report_id_stable_across_rebuilds(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Repair C3: a function report's id IS the function id, for ever.

    A content change regenerates the same row in place, and the title stays
    the function name even when the model offers another one.
    """
    entities = _seed_approval_map(db)
    function_id = _seed_function(db, "licensing", "Licensing")
    for entity_id in entities.values():
        _assign_function(db, entity_id, function_id)
    run_project()
    fake = _fake(monkeypatch)
    run_communities()
    row = db.execute(
        "SELECT id, title, incomplete, content_hash FROM cmap.community WHERE level = 1"
    ).fetchone()
    assert row is not None
    assert str(row[0]) == function_id
    assert row[1] == "Licensing"
    assert row[2] is False
    first_hash = row[3]
    _relation(
        db,
        _first_source(db),
        _mention_id(db, entities["jessica"]),
        _mention_id(db, entities["issue"]),
        "HANDS_OFF_TO",
        "a new hand-off link",
    )
    run_project()
    fake.title = "A different area title"
    run_communities()
    rows = db.execute(
        "SELECT id, title, content_hash FROM cmap.community WHERE level = 1"
    ).fetchall()
    assert len(rows) == 1
    assert str(rows[0][0]) == function_id
    assert rows[0][1] == "Licensing"
    assert rows[0][2] != first_hash
    # A rebuild with no content change reuses every report as it is.
    run_project()
    prompts_before = len(fake.prompts)
    third = run_communities()
    assert third["reports_reused"] == third["reports"]
    assert len(fake.prompts) == prompts_before


def test_cluster_id_reused_on_small_change(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Repair C3: a small membership change keeps the cluster's id and title."""
    entities = _seed_approval_map(db)
    run_project()
    fake = _fake(monkeypatch)
    run_communities()
    before = db.execute(
        "SELECT id, title FROM cmap.community WHERE level = 0"
    ).fetchone()
    cluster_id, title = str(before[0]), before[1]
    # One more entity linked into the same area: Jaccard 3/4 keeps the identity.
    extra = _entity(db, "Step", "second checkpoint", mentions=1, sources=1)
    extra_mention = _mention(db, _first_source(db), "Step", "second checkpoint", extra)
    for key in ("jessica", "step", "issue"):
        _relation(
            db,
            _first_source(db),
            extra_mention,
            _mention_id(db, entities[key]),
            "PRECEDES",
            "linked into the same area",
        )
    run_project()
    fake.title = "A different title entirely"
    run_communities()
    after = db.execute(
        "SELECT c.id, c.title FROM cmap.community c "
        "JOIN cmap.entity e ON e.id = ANY(c.entity_ids) "
        "WHERE c.level = 0 AND e.canonical_name = 'second checkpoint'"
    ).fetchone()
    assert str(after[0]) == cluster_id
    assert after[1] == title
    assert (
        db.execute("SELECT count(*) FROM cmap.community WHERE level = 0").fetchone()[0]
        == 1
    )


def test_new_relation_regenerates_report(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Repair C3: the content hash covers relations, not just the entity set."""
    entities = _seed_approval_map(db)
    run_project()
    _fake(monkeypatch)
    first = run_communities()
    before = db.execute(
        "SELECT id, content_hash FROM cmap.community WHERE level = 0"
    ).fetchone()
    _relation(
        db,
        _first_source(db),
        _mention_id(db, entities["jessica"]),
        _mention_id(db, entities["issue"]),
        "HANDS_OFF_TO",
        "a new hand-off link",
    )
    run_project()
    fake = _fake(monkeypatch)
    second = run_communities()
    after = db.execute(
        "SELECT id, content_hash FROM cmap.community WHERE level = 0"
    ).fetchone()
    assert str(after[0]) == str(before[0])
    assert after[1] != before[1]
    assert second["reports_reused"] == 0
    assert second["reports"] == first["reports"]
    assert len(fake.prompts) == second["reports"]


def test_failed_child_does_not_poison_parent(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Repair C3: a failed child marks its parents incomplete; they regenerate."""
    names = [
        "Jessica Smith (Licensing Manager)",
        "approval step",
        "the approval step is the bottleneck",
    ]
    _seed_approval_map(db)
    _seed_second_cluster(db)
    function_id = _seed_function(db, "ops", "Operations")
    for name in (*names, "Acme Factory", "Big Box", "Line 7"):
        _assign_function(db, _entity_id(db, name), function_id)
    run_project()

    real = FakeReport()

    def _flaky(
        messages: list[dict[str, Any]], settings: Any, max_tokens: int = 4000
    ) -> dict[str, Any]:
        prompt = str(messages[-1]["content"])
        if "Acme Factory" in prompt and "one area of how a company operates" in prompt:
            raise RuntimeError("model down for the vendor area")
        return real(messages, settings, max_tokens)

    monkeypatch.setattr(resolve_mod, "_post_chat", _flaky)
    first = run_communities()
    assert first["reports_failed"] == 1
    l1 = db.execute(
        "SELECT id, title, incomplete FROM cmap.community WHERE level = 1"
    ).fetchone()
    assert str(l1[0]) == function_id
    assert l1[2] is True
    assert db.execute(
        "SELECT incomplete FROM cmap.community WHERE level = 2"
    ).fetchone()[0] is True

    # Same graph: the failed child is retried and both parents regenerate —
    # they are never cached without it.
    fake = _fake(monkeypatch)
    second = run_communities()
    assert second["reports_failed"] == 0
    assert second["reports_reused"] == 1
    assert len(fake.prompts) == 3
    l1b = db.execute(
        "SELECT id, incomplete FROM cmap.community WHERE level = 1"
    ).fetchone()
    assert str(l1b[0]) == function_id
    assert l1b[1] is False
    assert db.execute(
        "SELECT incomplete FROM cmap.community WHERE level = 2"
    ).fetchone()[0] is False


def test_company_input_never_truncated(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Repair C3: over-budget company input is map-reduced, never truncated."""
    from brain.graph import communities as comm

    monkeypatch.setattr(comm, "MAX_CONTEXT_TOKENS", 200)
    _seed_approval_map(db)
    _seed_second_cluster(db)
    run_project()
    fake = _fake(
        monkeypatch,
        summary=("detail-line " * 60) + "UNIQUEMARK",
        numbered=True,
        summarise=lambda prompt: " ".join(
            line for line in prompt.splitlines() if line.startswith("## ")
        )
        or "batch-digest",
    )
    run_communities()
    summarise_prompts = [
        prompt for prompt in fake.prompts if prompt.startswith("You are compressing")
    ]
    assert summarise_prompts
    assert any("UNIQUEMARK" in prompt for prompt in summarise_prompts)
    assert all("context truncated" not in prompt for prompt in fake.prompts)
    company_prompt = fake.prompts[-1]
    assert "Area 1" in company_prompt
    assert "Area 2" in company_prompt


def test_recommendation_and_flag_references_survive_regeneration(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Repair C3 key-change gotcha: reports regenerate in place.

    ``cmap.recommendation`` and ``cmap.review_flag`` keep pointing at the same
    live rows across rebuilds and content changes — nothing is orphaned or
    re-pointed because the stable id never moves.
    """
    entities = _seed_approval_map(db)
    function_id = _seed_function(db, "licensing", "Licensing")
    for entity_id in entities.values():
        _assign_function(db, entity_id, function_id)
    run_project()
    _fake(monkeypatch)
    run_communities()
    l0_id = _community_of(db, "Jessica Smith (Licensing Manager)")
    db.execute(
        "INSERT INTO cmap.recommendation (community_id, problem, explanations, "
        "options, experiment) VALUES (%s, 'the sign-off stalls', '[]', '[]', '{}')",
        (l0_id,),
    )
    db.execute(
        "INSERT INTO cmap.review_flag (item_type, item_id) VALUES ('community', %s)",
        (function_id,),
    )
    db.commit()
    _relation(
        db,
        _first_source(db),
        _mention_id(db, entities["jessica"]),
        _mention_id(db, entities["step"]),
        "HANDS_OFF_TO",
        "a new hand-off link",
    )
    run_project()
    _fake(monkeypatch)
    run_communities()
    assert db.execute(
        "SELECT 1 FROM cmap.community WHERE id = %s", (l0_id,)
    ).fetchone()
    assert db.execute(
        "SELECT 1 FROM cmap.community WHERE id = %s", (function_id,)
    ).fetchone()
    rec = db.execute("SELECT community_id FROM cmap.recommendation").fetchone()
    assert str(rec[0]) == l0_id
    flag = db.execute("SELECT item_id FROM cmap.review_flag").fetchone()
    assert flag[0] == function_id
