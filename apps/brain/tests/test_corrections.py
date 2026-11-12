"""Corrections that stick (repair plan G1, issue #520).

A human correction is keyed by content — never a row id — so it survives a
full re-read re-creating every entity under new ids (plan Phase A drift note).
The named gate is the three done-when tests below: a rejected relation is gone
after a graph rebuild, a correction survives a full re-read, and an edit
replaces the fact in answers. No test calls a real model.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import fake_embeddings
from test_answer import _direction, fake_answer, fake_embeds
from test_flat import _seed_text
from test_project import _entity, _mention, _relation
from test_resolve import _fake, _unit
from test_resolve import _mention as _unresolved_mention

from brain.answer.answer import answer_question
from brain.config import get_settings
from brain.corrections import (
    entity_key,
    migrate_review_flags,
    record_correction,
    relation_key,
)
from brain.embed import vector_literal
from brain.graph import project as project_mod
from brain.graph.project import run_project
from brain.read.pipeline import _store_chunks
from brain.resolve.resolve import run_resolve

PERFORMS_KEY = relation_key(
    "Jessica Smith", "Person", "PERFORMS", "approval step", "Step"
)
CAUSES_KEY = relation_key(
    "Jessica Smith", "Person", "CAUSES", "the sign-off stall", "Issue"
)


def _seed_map(db: Any, tag: str) -> dict[str, Any]:
    """One source naming Jessica, the approval step and the stall it causes.

    Every call inserts the same names under new row ids — the state a full
    re-read leaves behind — so content keys match across calls while ids do not.
    """
    source = _seed_text(db, "The Licensing Manager reviews the package.", tag)
    jessica = _entity(db, "Person", "Jessica Smith", description="Licensing manager.")
    step = _entity(db, "Step", "approval step")
    issue = _entity(db, "Issue", "the sign-off stall", description="A bottleneck.")
    j_m = _mention(db, source, "Person", "Jessica Smith", jessica)
    s_m = _mention(db, source, "Step", "approval step", step)
    i_m = _mention(db, source, "Issue", "the sign-off stall", issue)
    quote = "The Licensing Manager reviews the package."
    _relation(
        db,
        source,
        j_m,
        s_m,
        "PERFORMS",
        "Jessica reviews the package",
        stance="policy",
        quote=quote,
    )
    _relation(
        db,
        source,
        j_m,
        i_m,
        "CAUSES",
        "Jessica's step is the stall",
        stance="report",
        quote=quote,
    )
    return {
        "source": source,
        "entities": {jessica, step, issue},
    }


def _write(
    db: Any,
    *,
    target_kind: str,
    target_key: str,
    action: str,
    payload: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Record one correction (the writer the API uses) and commit it."""
    corr = record_correction(
        db,
        target_kind=target_kind,
        target_key=target_key,
        action=action,
        payload=payload,
        reason=reason,
        by="test-admin",
    )
    db.commit()
    return corr


def _projected_edges() -> list[tuple[str, str, str]]:
    """The projected ``company`` graph's edge triples (names + rel type)."""
    graph = project_mod.connect(get_settings())
    rows = graph.query(
        "MATCH (a:Entity)-[r]->(b:Entity) RETURN a.name, type(r), b.name"
    ).result_set
    return sorted((str(a), str(rel), str(b)) for a, rel, b in rows)


def _point_embeddings(db: Any) -> None:
    """Pin entity and chunk embeddings so retrieval is deterministic."""
    for (entity_id,) in db.execute("SELECT id FROM cmap.entity").fetchall():
        db.execute(
            "UPDATE cmap.entity SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_direction(0.05)), entity_id),
        )
    for (chunk_id,) in db.execute("SELECT id FROM cmap.chunk").fetchall():
        db.execute(
            "UPDATE cmap.chunk SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_direction(0.0)), chunk_id),
        )
    db.commit()


# --------------------------------------------------------- the named gate


def test_rejected_relation_gone_after_rebuild(db: Any) -> None:
    """A rejected relation is excluded from the graph and stays gone on every
    full rebuild (projection point, plan Phase G)."""
    _seed_map(db, "g1reject")
    run_project()
    edges = _projected_edges()
    assert ("Jessica Smith", "PERFORMS", "approval step") in edges
    assert ("Jessica Smith", "CAUSES", "the sign-off stall") in edges

    _write(
        db,
        target_kind="relation",
        target_key=PERFORMS_KEY,
        action="reject",
        reason="She does not perform this step",
    )
    stats = run_project()
    edges = _projected_edges()
    assert ("Jessica Smith", "PERFORMS", "approval step") not in edges
    # the rest of the map survives
    assert ("Jessica Smith", "CAUSES", "the sign-off stall") in edges
    assert stats["edges"] == 1

    again = run_project()
    edges = _projected_edges()
    assert ("Jessica Smith", "PERFORMS", "approval step") not in edges
    assert again["edges"] == 1


def test_correction_survives_full_reread(db: Any) -> None:
    """The correction still bites after a full re-read re-creates every entity
    under new row ids — it keys on content, never on ids (Phase A drift)."""
    first = _seed_map(db, "g1reread1")
    _write(
        db,
        target_kind="relation",
        target_key=PERFORMS_KEY,
        action="reject",
        reason="She does not perform this step",
    )
    run_project()
    assert ("Jessica Smith", "PERFORMS", "approval step") not in _projected_edges()

    # What a re-read does first: replace the passages, dropping entities that
    # nothing mentions any more (repair A7) — then the same content is read
    # back: same names, every row id new.
    _store_chunks(first["source"], [])
    db.commit()
    assert (
        db.execute("SELECT count(*) FROM cmap.entity").fetchone()[0] == 0
    ), "re-read must have re-created entities, not kept the old rows"
    second = _seed_map(db, "g1reread2")
    assert first["entities"].isdisjoint(second["entities"])

    run_project()
    edges = _projected_edges()
    assert ("Jessica Smith", "PERFORMS", "approval step") not in edges
    assert ("Jessica Smith", "CAUSES", "the sign-off stall") in edges

    # The correction is what removes the edge: undo it and the edge is back.
    db.execute("UPDATE cmap.correction SET active = false")
    db.commit()
    run_project()
    assert ("Jessica Smith", "PERFORMS", "approval step") in _projected_edges()


def test_edit_replaces_fact_in_answers(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """An edited fact replaces the original wherever the answer assembles its
    facts — even before a re-projection (answer point, plan Phase G)."""
    _seed_map(db, "g1edit")
    _point_embeddings(db)
    run_project()
    fake_embeds(monkeypatch, {})
    fake = fake_answer(monkeypatch)

    _write(
        db,
        target_kind="relation",
        target_key=PERFORMS_KEY,
        action="edit",
        payload={"descriptions": ["Jessica approves the package"]},
        reason="She approves, she does not review",
    )
    result = answer_question(
        "Who reviews the licensing package?", mode="local"
    )
    assert result["mode_used"] == "local"
    prompt = fake.prompts[0]
    assert "Jessica approves the package" in prompt
    assert "Jessica reviews the package" not in prompt
    # the fact is still there, just edited — not deleted
    assert "PERFORMS" in prompt


# ------------------------------------------- the three points, beyond the gate


def test_edit_replaces_edge_in_projection(db: Any) -> None:
    """Projection point: an edited relation is replaced by its payload."""
    _seed_map(db, "g1editproj")
    _write(
        db,
        target_kind="relation",
        target_key=PERFORMS_KEY,
        action="edit",
        payload={"descriptions": ["Jessica approves the package"]},
    )
    run_project()
    graph = project_mod.connect(
        __import__("brain.config", fromlist=["get_settings"]).get_settings()
    )
    rows = graph.query(
        "MATCH (:Entity)-[r:PERFORMS]->(:Entity) RETURN r.descriptions"
    ).result_set
    assert rows and list(rows[0][0]) == ["Jessica approves the package"]


def test_never_merge_pair_keeps_names_apart_on_reruns(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Resolution point: a never-merge (reject) pair is respected on re-runs,
    so a name the human separated is never merged again after a rebuild."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    _fake(monkeypatch)
    source = _seed_text(db, "Jessica was mentioned.", "g1nevermerge")
    smith = _entity(db, "Person", "Jessica Smith", mentions=2, sources=1)
    db.execute(
        "UPDATE cmap.entity SET embedding = %s::vector WHERE id = %s",
        (vector_literal(_unit("jessica")), smith),
    )
    db.execute(
        "INSERT INTO cmap.entity_alias "
        "(entity_id, entity_type, normalized_name, lang, source) "
        "VALUES (%s, 'Person', 'jessica', 'en', 'resolve')",
        (smith,),
    )
    db.commit()

    # Control: without corrections the name joins Smith (alias and embedding
    # both match) — so the separation below is the correction's doing.
    control = _unresolved_mention(db, source, "Person", "Jessica", _unit("jessica"))
    run_resolve()
    assert (
        str(
            db.execute(
                "SELECT entity_id FROM cmap.mention WHERE id = %s", (control,)
            ).fetchone()[0]
        )
        == smith
    )
    db.execute("DELETE FROM cmap.mention WHERE id = %s", (control,))
    db.commit()

    _write(
        db,
        target_kind="entity",
        target_key=entity_key("Jessica Smith", "Person"),
        action="reject",
        payload={"pair": entity_key("Jessica", "Person")},
        reason="Two different people",
    )
    for rerun in ("first", "second"):
        mention_id = _unresolved_mention(
            db, source, "Person", "Jessica", _unit("jessica")
        )
        run_resolve()
        owner = str(
            db.execute(
                "SELECT entity_id FROM cmap.mention WHERE id = %s", (mention_id,)
            ).fetchone()[0]
        )
        assert owner != smith, f"never-merge ignored on the {rerun} run"
        # leave nothing behind, as a re-read would before resolution re-runs
        db.execute("DELETE FROM cmap.entity WHERE id = %s", (owner,))
        db.execute("DELETE FROM cmap.mention WHERE id = %s", (mention_id,))
        db.commit()


# ------------------------------------------------------ writer and migration


def test_resolve_writes_content_keyed_correction(
    client: Any, admin_headers: dict[str, str], db: Any
) -> None:
    """The review page's resolve write creates a correction keyed by content."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name) "
            "VALUES ('Person', 'Jessica Vale'), ('Role', 'Licensing Manager') "
            "RETURNING id"
        )
        entity_id, other_id = (str(row[0]) for row in cur.fetchall())
    db.commit()
    relation_id = f"{entity_id}:{other_id}:PERFORMS"
    flag = client.post(
        "/flags",
        headers=admin_headers,
        json={"item_type": "relation", "item_id": relation_id, "note": "Made up"},
    ).json()["flag"]
    body = client.post(
        f"/flags/{flag['id']}/resolve",
        headers=admin_headers,
        json={"action": "reject"},
    )
    assert body.status_code == 200, body.text
    correction = body.json()["correction"]
    assert correction is not None
    assert correction["target_kind"] == "relation"
    assert correction["target_key"] == relation_key(
        "Jessica Vale", "Person", "PERFORMS", "Licensing Manager", "Role"
    )
    assert correction["action"] == "reject"
    assert correction["reason"] == "Made up"
    row = db.execute(
        "SELECT action, resolved_at IS NOT NULL FROM cmap.review_flag WHERE id = %s",
        (flag["id"],),
    ).fetchone()
    db.commit()
    assert row == ("reject", True)


def test_review_flag_migration_backfills_and_is_idempotent(db: Any) -> None:
    """Existing flags that name a concrete target become reject corrections;
    pure notes are skipped and counted; running again changes nothing."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name) "
            "VALUES ('Person', 'Jessica Vale') RETURNING id"
        )
        entity_id = str(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO cmap.community (level, title, entity_ids, graph_version) "
            "VALUES (1, 'Misgrouped', %s::uuid[], 1) RETURNING id",
            ([entity_id],),
        )
        community_id = str(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO cmap.review_flag (item_type, item_id, note, created_by, resolved_at) "
            "VALUES ('entity', %s, 'Wrong person', %s, now()), "
            "('community', %s, 'Misgrouped area', %s, now()), "
            "('relation', '00000000-0000-4000-8000-000000000099:"
            "00000000-0000-4000-8000-000000000098:PERFORMS', 'Gone target', %s, now())",
            (
                entity_id,
                "00000000-0000-4000-8000-0000000000a2",
                community_id,
                "00000000-0000-4000-8000-0000000000a2",
                "00000000-0000-4000-8000-0000000000a2",
            ),
        )
    db.commit()

    counts = migrate_review_flags(db)
    assert counts == {"migrated": 1, "skipped_note": 1, "skipped_target_gone": 1}
    rows = db.execute(
        "SELECT target_kind, target_key, action FROM cmap.correction"
    ).fetchall()
    assert [(str(a), str(b), str(c)) for a, b, c in rows] == [
        ("entity", entity_key("Jessica Vale", "Person"), "reject")
    ]
    actions = {
        item for (item,) in db.execute("SELECT action FROM cmap.review_flag").fetchall()
    }
    assert actions == {"reject", None}

    again = migrate_review_flags(db)
    assert again == {"migrated": 0, "skipped_note": 1, "skipped_target_gone": 1}
    assert db.execute("SELECT count(*) FROM cmap.correction").fetchone()[0] == 1


def test_rejected_entity_never_reaches_answers(
    monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """Answer point: a rejected entity is never shown; a confirmed one ranks
    first in the fact list."""
    _seed_map(db, "g1entans")
    _point_embeddings(db)
    run_project()
    _write(
        db,
        target_kind="entity",
        target_key=entity_key("the sign-off stall", "Issue"),
        action="reject",
    )
    _write(
        db,
        target_kind="entity",
        target_key=entity_key("approval step", "Step"),
        action="confirm",
    )
    fake_embeds(monkeypatch, {})
    fake = fake_answer(monkeypatch)
    answer_question("What is the approval step?", mode="local")
    prompt = fake.prompts[0]
    graph_block = prompt.split("ENTITIES:", 1)[1].split("QUOTES", 1)[0]
    assert "the sign-off stall" not in graph_block
    assert "CAUSES" not in graph_block
    assert "approval step" in graph_block
    # the confirmed fact ranks first in the ENTITIES block
    entities_block = graph_block.split("EDGES:", 1)[0]
    assert entities_block.strip().startswith("- [Step] approval step")
