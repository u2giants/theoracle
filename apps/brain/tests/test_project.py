"""Graph projection into FalkorDB (plan step 7).

Seeds entities, mentions and source-level relations straight into Postgres,
rebuilds the ``company`` graph and reads it back through the exact query the
step's done-when names. One test runs the whole fixture pipeline (flat,
relations, resolve) before projecting. No test calls a real model.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from conftest import fake_embeddings, fake_relations, fake_scaledown
from test_flat import TRANSCRIPT_FIXTURE, _seed_fixture, _seed_text
from test_resolve import _fake, _unit
from test_resolve import _mention as _unresolved_mention

from brain.config import get_settings
from brain.embed import vector_literal
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.graph import project as project_mod
from brain.graph import query as query_mod
from brain.graph.project import ProjectionError, handle_project, run_project
from brain.resolve.resolve import handle_resolve


def _chunk_of(db: Any, source_id: str) -> str:
    return str(
        db.execute(
            "SELECT id FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal LIMIT 1",
            (source_id,),
        ).fetchone()[0]
    )


def _entity(
    db: Any,
    entity_type: str,
    name: str,
    *,
    description: str = "",
    mentions: int = 1,
    sources: int = 1,
) -> str:
    row = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name, description, "
        "mention_count, source_count) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (entity_type, name, description, mentions, sources),
    ).fetchone()
    db.commit()
    return str(row[0])


def _mention(
    db: Any,
    source_id: str,
    entity_type: str,
    surface: str,
    entity_id: str,
) -> str:
    row = db.execute(
        "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
        "normalized_name, quote, entity_id) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (
            _chunk_of(db, source_id),
            entity_type,
            surface,
            surface.lower().strip(),
            f"{surface} was mentioned.",
            entity_id,
        ),
    ).fetchone()
    db.commit()
    return str(row[0])


def _relation(
    db: Any,
    source_id: str,
    from_mention: str,
    to_mention: str,
    rel_type: str,
    description: str,
    *,
    stance: str = "practice",
    confidence: float = 0.9,
    quote: str = "quoted line",
) -> None:
    db.execute(
        "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, "
        "rel_type, description, stance, confidence, quote) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            _chunk_of(db, source_id),
            from_mention,
            to_mention,
            rel_type,
            description,
            stance,
            confidence,
            quote,
        ),
    )
    db.commit()


def _seed_approval_map(db: Any) -> dict[str, str]:
    """Two sources naming the same approval, one Person, one Step, one Issue."""
    procedure = _seed_text(db, "The Licensing Manager reviews the package.", "proc")
    transcript = _seed_text(db, "Jessica files the sign-off after the review.", "tx")
    jessica = _entity(
        db,
        "Person",
        "Jessica Smith (Licensing Manager)",
        description="Licensing manager.",
        mentions=2,
        sources=2,
    )
    step = _entity(db, "Step", "approval step", mentions=2, sources=2)
    issue = _entity(
        db, "Issue", "the approval step is the bottleneck", mentions=1, sources=1
    )
    j_m1 = _mention(db, procedure, "Person", "Jessica Smith", jessica)
    j_m2 = _mention(db, transcript, "Person", "Jessica", jessica)
    s_m1 = _mention(db, procedure, "Step", "approval step", step)
    s_m2 = _mention(db, transcript, "Step", "the approval step", step)
    i_m1 = _mention(db, transcript, "Issue", "the approval step is the bottleneck", issue)
    _relation(
        db,
        procedure,
        j_m1,
        s_m1,
        "PERFORMS",
        "Jessica reviews the package",
        stance="policy",
        confidence=0.9,
        quote="The Licensing Manager reviews the package.",
    )
    _relation(
        db,
        transcript,
        j_m2,
        s_m2,
        "PERFORMS",
        "Jessica records the sign-off",
        stance="practice",
        confidence=0.8,
        quote="Jessica files the sign-off after the review.",
    )
    _relation(
        db,
        transcript,
        j_m2,
        i_m1,
        "CAUSES",
        "Jessica's step is the stall",
        stance="report",
        confidence=0.75,
        quote="Jessica files the sign-off after the review.",
    )
    _relation(
        db,
        transcript,
        i_m1,
        s_m2,
        "BLOCKED_BY",
        "the bottleneck is the approval step",
        stance="report",
        confidence=0.7,
        quote="Jessica files the sign-off after the review.",
    )
    return {"jessica": jessica, "step": step, "issue": issue}


def test_rebuild_is_idempotent(db: Any) -> None:
    """A second rebuild replaces the graph; counts match the first pass."""
    _seed_approval_map(db)
    first = run_project()
    second = run_project()
    assert first["nodes"] == second["nodes"] == 3
    assert first["edges"] == second["edges"] == 3
    assert second["version"] == first["version"] + 1
    graph = project_mod.connect(get_settings())
    counts = graph.query(
        "MATCH (n:Entity) WITH count(n) AS nodes "
        "MATCH ()-[r]->() RETURN nodes, count(r)"
    ).result_set
    assert counts == [[3, 3]]


def test_edge_weight_counts_distinct_sources(db: Any) -> None:
    """Weight is the number of distinct sources behind the projected edge."""
    _seed_approval_map(db)
    run_project()
    graph = project_mod.connect(get_settings())
    result = graph.query(
        "MATCH (a:Entity)-[r:PERFORMS]->(b:Entity) RETURN r.weight, "
        "r.descriptions, r.stances, r.confidence_max, r.source_refs"
    ).result_set
    assert len(result) == 1
    weight, descriptions, stances, confidence_max, source_refs = result[0]
    assert weight == 2
    assert sorted(descriptions) == [
        "Jessica records the sign-off",
        "Jessica reviews the package",
    ]
    assert json.loads(stances) == {"practice": 1, "policy": 1}
    assert confidence_max == pytest.approx(0.9)
    refs = json.loads(source_refs)
    assert len(refs) == 2
    # Two relations in one source still weigh one.
    extra = _seed_text(db, "extra", "extra")
    jessica = str(
        db.execute(
            "SELECT id FROM cmap.entity WHERE canonical_name LIKE 'Jessica%'"
        ).fetchone()[0]
    )
    step = str(
        db.execute("SELECT id FROM cmap.entity WHERE entity_type = 'Step'").fetchone()[0]
    )
    m1 = _mention(db, extra, "Person", "Jessica Smith", jessica)
    m2 = _mention(db, extra, "Step", "approval step", step)
    _relation(db, extra, m1, m2, "USES", "extra one")
    _relation(db, extra, m1, m2, "USES", "extra two")
    run_project()
    weight = graph.query(
        "MATCH (:Entity)-[r:USES]->(:Entity) RETURN r.weight"
    ).result_set
    assert [row[0] for row in weight] == [1]


def test_fixture_approval_neighborhood(db: Any) -> None:
    """Done-when: the named query returns the approval step and the Issue."""
    _seed_approval_map(db)
    run_project()
    graph = project_mod.connect(get_settings())
    rows = graph.query(
        "MATCH (p:Person {name:'Jessica Smith (Licensing Manager)'})-[r]-(x) "
        "RETURN type(r), x.name"
    ).result_set
    assert sorted(rows) == [
        ["CAUSES", "the approval step is the bottleneck"],
        ["PERFORMS", "approval step"],
    ]


def test_projects_transcript_fixture_graph(monkeypatch: pytest.MonkeyPatch, db: Any) -> None:
    """The full fixture pipeline projected: Jessica keeps her corpus links.

    The frozen step-4/5 recordings put the Issue one hop further from Jessica
    (Issue -BLOCKED_BY-> approval step, Person -PERFORMS-> Process/Role), so
    this asserts the corpus graph's real one-hop neighborhood while
    ``test_fixture_approval_neighborhood`` covers the done-when query itself.
    """
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "transcript.json")
    fake_relations(monkeypatch)
    transcript = _seed_fixture(db, TRANSCRIPT_FIXTURE, "transcript")
    handle_classify_extract({"payload": {"source_id": transcript}})
    handle_relations({"payload": {"source_id": transcript}})
    # Same embedding placement as test_resolve's fixture join, so the
    # resolved Person is the one the done-when query names.
    for (mention_id,) in db.execute("SELECT id FROM cmap.mention").fetchall():
        db.execute(
            "UPDATE cmap.mention SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_unit(str(mention_id))), mention_id),
        )
    db.commit()
    flowchart = _seed_text(
        db,
        'FLOWCHART. n4 "Record sign-off (Jessica)". Licensing approval is recorded by J. '
        "Jessica Smith owns the licensing manager's sign-off.",
        "flowchart",
    )
    _unresolved_mention(db, flowchart, "Person", "Jessica Smith", _unit("jessica smith"))
    _unresolved_mention(db, flowchart, "Person", "J.", _unit("j initial"))
    _fake(monkeypatch, names={"Person": "Jessica Smith (Licensing Manager)"})
    handle_resolve({"payload": {}})
    stats = run_project()
    assert stats["nodes"] >= 3
    assert stats["edges"] >= 2
    graph = project_mod.connect(get_settings())
    rows = graph.query(
        "MATCH (p:Person {name:'Jessica Smith (Licensing Manager)'})-[r]-(x) "
        "RETURN DISTINCT x.name"
    ).result_set
    names = sorted(str(row[0]) for row in rows)
    assert any("approval" in name.lower() for name in names), names
    assert any("licensing manager" in name.lower() for name in names), names


def test_project_rejects_unknown_labels(db: Any) -> None:
    """Ontology-unlisted entity and relation types never reach Cypher labels."""
    source = _seed_text(db, "bogus", "bogus")
    bad = _entity(db, "Wizard", "Gandalf")
    _mention(db, source, "Wizard", "Gandalf", bad)
    with pytest.raises(ProjectionError, match="unknown entity type"):
        run_project()
    db.execute("UPDATE cmap.entity SET entity_type = 'Person'")
    db.commit()
    good = _entity(db, "Person", "Frodo")
    m1 = _mention(db, source, "Person", "Gandalf", bad)
    m2 = _mention(db, source, "Person", "Frodo", good)
    _relation(db, source, m1, m2, "AVERTS", "bogus relation")
    with pytest.raises(ProjectionError, match="unknown relation type"):
        run_project()


def test_handle_project_records_usage_and_queues_communities(db: Any) -> None:
    """The job wrapper stores counts on the job row and queues step 8."""
    _seed_approval_map(db)
    row = db.execute(
        "INSERT INTO cmap.job (kind, payload, state) "
        "VALUES ('project', '{}', 'running') RETURNING id"
    ).fetchone()
    job_id = str(row[0])
    db.commit()
    handle_project({"id": job_id, "payload": {}})
    payload = db.execute(
        "SELECT payload->'usage' FROM cmap.job WHERE id = %s", (job_id,)
    ).fetchone()[0]
    assert payload["nodes"] == 3
    assert payload["edges"] == 3
    assert isinstance(payload["version"], int)
    queued = db.execute(
        "SELECT count(*) FROM cmap.job WHERE kind = 'communities' AND state = 'queued'"
    ).fetchone()[0]
    assert queued == 1


def test_query_templates(db: Any) -> None:
    """neighbors, path, by_type and search_name answer over the projected graph."""
    ids = _seed_approval_map(db)
    run_project()
    found = query_mod.search_name("Jessica")
    assert [node["name"] for node in found] == ["Jessica Smith (Licensing Manager)"]
    nearby = query_mod.neighbors(ids["jessica"], depth=1)
    assert "approval step" in [node["name"] for node in nearby]
    routes = query_mod.path(ids["jessica"], ids["issue"], max_len=4)
    assert routes and routes[0]["names"][0] == "Jessica Smith (Licensing Manager)"
    assert routes[0]["names"][-1] == "the approval step is the bottleneck"
    people = query_mod.by_type("Person")
    assert [node["name"] for node in people] == ["Jessica Smith (Licensing Manager)"]
    with pytest.raises(ValueError, match="unknown entity type"):
        query_mod.by_type("Wizard")
