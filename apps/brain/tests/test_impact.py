"""I5 impact answers through the regular entry point with a real graph."""

import pytest
from test_flat import _seed_text

from brain.answer import answer as answer_mod
from brain.answer.answer import answer_question
from brain.graph.project import run_project


def _seed_impact(db):
    quotes = [
        "Alice Chen performs the artwork approval.",
        "The artwork approval hands off to PO release.",
        "Finance releases the purchase order.",
        "When artwork approval is unavailable, a delegate can do the backup review.",
        "The approval portal handles artwork approval.",
        "Artwork approval waits for Ocean Vendor.",
        "An unrelated step comes before artwork approval.",
        "Finance sends the confirmed purchase order.",
        "Finance owns the purchase order release.",
    ]
    source_id = _seed_text(db, " ".join(quotes), "impact")
    (chunk_id,) = db.execute(
        "SELECT id FROM cmap.chunk WHERE source_id = %s", (source_id,)
    ).fetchone()
    evidence = {}
    entities = {}
    for name, kind, quote in zip(
        (
            "Alice Chen",
            "Artwork approval",
            "PO release",
            "Backup review",
            "Approval Portal",
            "Ocean Vendor",
            "Gather forms",
            "Send PO",
            "Finance",
        ),
        (
            "Person",
            "Step",
            "Step",
            "Exception",
            "System",
            "Vendor",
            "Step",
            "Step",
            "Role",
        ),
        quotes,
        strict=True,
    ):
        (entity_id,) = db.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name) VALUES (%s, %s) RETURNING id",
            (kind, name),
        ).fetchone()
        (mention_id,) = db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, normalized_name, "
            "quote, entity_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (chunk_id, kind, name, name.lower(), quote, entity_id),
        ).fetchone()
        entities[name] = entity_id
        evidence[name] = mention_id
    db.execute(
        "INSERT INTO cmap.entity_alias VALUES (%s, 'Person', 'al chen')",
        (entities["Alice Chen"],),
    )
    for start, end, kind, quote in (
        ("Alice Chen", "Artwork approval", "PERFORMS", quotes[0]),
        ("Artwork approval", "PO release", "HANDS_OFF_TO", quotes[1]),
        ("Artwork approval", "Backup review", "EXCEPT_WHEN", quotes[3]),
        ("Artwork approval", "Approval Portal", "USES", quotes[4]),
        ("Artwork approval", "Ocean Vendor", "DEPENDS_ON", quotes[5]),
        ("Gather forms", "Artwork approval", "PRECEDES", quotes[6]),
    ):
        db.execute(
            "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, "
            "rel_type, description, stance, confidence, quote) "
            "VALUES (%s, %s, %s, %s, %s, 'policy', 1, %s)",
            (chunk_id, evidence[start], evidence[end], kind, quote, quote),
        )
    for title, steps in (
        ("Licensing workflow", ("Gather forms", "Artwork approval")),
        ("Purchasing workflow", ("PO release", "Send PO")),
    ):
        (process,) = db.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name) "
            "VALUES ('Process', %s) RETURNING id",
            (title,),
        ).fetchone()
        (flow_id,) = db.execute(
            "INSERT INTO cmap.process_flow (process_entity_id, title) VALUES (%s, %s) RETURNING id",
            (process, title),
        ).fetchone()
        for ordinal, name in enumerate(steps, 1):
            db.execute(
                "INSERT INTO cmap.flow_step (flow_id, ordinal, step_entity_id, performer_entity_id, "
                "system_entity_id, evidence_relation_ids) VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    flow_id,
                    ordinal,
                    entities[name],
                    {
                        "Artwork approval": entities["Alice Chen"],
                        "Send PO": entities["Finance"],
                    }.get(name),
                    entities["Approval Portal"] if name == "Artwork approval" else None,
                    [evidence[name]],
                ),
            )
    db.commit()
    run_project()
    return source_id, chunk_id


@pytest.mark.parametrize(
    "question",
    [
        "What breaks if Alice Chen is out?",
        "What if Al Chen is unavailable?",
        "What happens if the Approval Portal is down?",
        "What breaks if Ocean Vendor is late?",
        "What happens if we remove the artwork approval step?",
    ],
)
def test_what_if_person_absent_lists_downstream(db, monkeypatch, question):
    source_id, chunk_id = _seed_impact(db)
    monkeypatch.setattr(
        answer_mod,
        "_run_checks",
        lambda rows, settings: (
            {index: "supported" for index, _, _ in rows},
            0,
        ),
    )
    result = answer_question(question)
    assert result["unknowns"] == []
    assert result["supported_share"] > 0
    answer = result["answer_md"]
    assert (
        "Purchasing workflow: Send PO, handled by Finance (later step to check)"
        in answer
    )
    assert "Gather forms" not in answer
    assert "Backup review" in answer
    assert result["citations"]
    for citation in result["citations"]:
        assert citation["source_id"] == str(source_id)
        assert citation["chunk_id"] == str(chunk_id)
        text, locator = db.execute(
            "SELECT text, locator FROM cmap.chunk WHERE id = %s", (chunk_id,)
        ).fetchone()
        assert citation["quote"] in text
        assert citation["locator"] == locator


def test_impact_declines_missing_or_ambiguous_subject(db):
    _, chunk_id = _seed_impact(db)
    (other_id,) = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name) "
        "VALUES ('Role', 'Alice Chen') RETURNING id"
    ).fetchone()
    db.execute(
        "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, normalized_name, "
        "quote, entity_id) VALUES (%s, 'Role', 'Alice Chen', 'alice chen', 'Alice Chen', %s)",
        (chunk_id, other_id),
    )
    db.commit()
    for subject in ("Alice Chen", "Unlisted employee"):
        result = answer_question(f"What breaks if {subject} is out?")
        assert "Please name one" in result["answer_md"]
        assert result["citations"] == []


def test_flow_performer_can_seed_graph_handoff_without_performs_edge(db, monkeypatch):
    _seed_impact(db)
    db.execute("DELETE FROM cmap.relation WHERE rel_type = 'PERFORMS'")
    db.commit()
    run_project()
    monkeypatch.setattr(
        answer_mod,
        "_run_checks",
        lambda rows, settings: (
            {index: "supported" for index, _, _ in rows},
            0,
        ),
    )
    result = answer_question("What would break if Alice Chen is absent?")
    assert "Artwork approval hands off to PO release" in result["answer_md"]
    assert "Purchasing workflow: Send PO" in result["answer_md"]


def test_impact_declines_superseded_evidence_even_before_graph_rebuild(db):
    source_id, _ = _seed_impact(db)
    replacement = _seed_text(db, "Replacement source", "replacement")
    db.execute(
        "INSERT INTO cmap.source_version (source_id, supersedes_source_id, origin, decided_at) "
        "VALUES (%s, %s, 'admin', now())",
        (replacement, source_id),
    )
    db.commit()
    result = answer_question("What breaks if Alice Chen is out?")
    assert result["unknowns"]
    assert result["citations"] == []
