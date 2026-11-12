"""D2 gate: newer versions supersede older ones.

The three named gates are ``test_revised_policy_supersedes_old_rule``,
``test_fact_also_in_live_source_stays_current`` and
``test_history_question_can_still_reach_old_version``. Facts are seeded as
relation rows keyed by (entity pair, rel_type) across sources — the computed
fact-level status is exercised — while intake and detection run through the
real upload path. No test calls a real model.
"""

from __future__ import annotations

import json
from typing import Any

import psycopg
import pytest
from conftest import fake_embeddings
from fastapi.testclient import TestClient
from psycopg.types.json import Json

from brain.answer import answer as answer_mod
from brain.answer.answer import answer_question
from brain.config import get_settings
from brain.embed import vector_literal
from brain.graph.project import connect as connect_graph
from brain.graph.project import run_project
from brain.read.pipeline import handle_read_source
from brain.versions import (
    ORIGIN_ADMIN,
    ORIGIN_AUTO_SIMILARITY,
    ORIGIN_AUTO_TITLE,
    recompute_relation_status,
    title_key,
)

OLD_RULE_SENTENCE = "Widget purchase orders above 500 dollars require Finance approval."
NEW_RULE_SENTENCE = "Widget purchase orders above 1000 dollars require VP approval."
LIVE_SENTENCE = "The sign-off stalls when Finance approval for widget purchase orders is missing."


def _unit_vector() -> list[float]:
    """All-equal unit vector: parallel to the fake question embedding."""
    size = get_settings().brain_embed_dims
    return [1.0 / (size**0.5)] * size


def _upload(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    data: bytes,
    *,
    title: str | None = None,
    effective_date: str | None = None,
) -> dict[str, Any]:
    form: dict[str, str] = {}
    if title is not None:
        form["title"] = title
    if effective_date is not None:
        form["effective_date"] = effective_date
    response = client.post(
        "/sources",
        headers=headers,
        files={"file": (name, data, "application/octet-stream")},
        data=form,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _run_read(db: Any, monkeypatch: pytest.MonkeyPatch, source_id: str) -> None:
    """Run the queued ``read_source`` job for one source."""
    fake_embeddings(monkeypatch)
    job = db.execute(
        "SELECT id, kind, payload FROM cmap.job WHERE kind = 'read_source' "
        "AND payload->>'source_id' = %s",
        (source_id,),
    ).fetchone()
    assert job is not None, f"no read_source job queued for {source_id}"
    handle_read_source({"id": job[0], "kind": job[1], "payload": job[2]})


def _seed_entities(db: Any) -> dict[str, str]:
    """Entities shared across sources; one Rule per fact so keys differ.

    ``rule_old`` and ``rule_new`` are two different rules (the revision
    replaced one with the other); ``process`` is the thing they apply to.
    """
    ids: dict[str, str] = {}
    for name, etype, description in (
        ("rule_old", "Rule", "POs above 500 need Finance approval."),
        ("rule_new", "Rule", "POs above 1000 need VP approval."),
        ("process", "Process", "The widget purchasing process."),
    ):
        row = db.execute(
            "INSERT INTO cmap.entity (entity_type, canonical_name, description, "
            "mention_count, source_count) VALUES (%s, %s, %s, 1, 1) RETURNING id",
            (etype, name, description),
        ).fetchone()
        ids[name] = str(row[0])
        db.execute(
            "UPDATE cmap.entity SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_unit_vector()), ids[name]),
        )
    db.commit()
    return ids


def _seed_fact(
    db: Any,
    source_id: str,
    from_entity: str,
    to_entity: str,
    text: str,
    description: str,
    *,
    rel_type: str = "APPLIES_TO",
    with_embedding: bool = False,
) -> str:
    """One chunk carrying a ``rel_type`` fact between two entities; return its id."""
    ordinal = int(
        db.execute(
            "SELECT count(*) FROM cmap.chunk WHERE source_id = %s", (source_id,)
        ).fetchone()[0]
    )
    chunk_id = str(
        db.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (source_id, ordinal, Json({"page": ordinal + 1}), text, 30),
        ).fetchone()[0]
    )
    if with_embedding:
        db.execute(
            "UPDATE cmap.chunk SET embedding = %s::vector WHERE id = %s",
            (vector_literal(_unit_vector()), chunk_id),
        )
    from_m = str(
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) "
            "VALUES (%s, 'Rule', 'rule', 'rule', %s, %s) RETURNING id",
            (chunk_id, text, from_entity),
        ).fetchone()[0]
    )
    to_m = str(
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) "
            "VALUES (%s, 'Process', 'process', 'process', %s, %s) RETURNING id",
            (chunk_id, text, to_entity),
        ).fetchone()[0]
    )
    rel_id = str(
        db.execute(
            "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, "
            "rel_type, description, stance, confidence, quote) "
            "VALUES (%s, %s, %s, %s, %s, 'policy', 0.9, %s) RETURNING id",
            (chunk_id, from_m, to_m, rel_type, description, text),
        ).fetchone()[0]
    )
    db.commit()
    return rel_id


def _relation_status(db: Any, rel_id: str) -> str:
    row = db.execute(
        "SELECT status FROM cmap.relation WHERE id = %s", (rel_id,)
    ).fetchone()
    assert row is not None
    return str(row[0])


def _version_row(db: Any, newer_id: str, older_id: str) -> tuple[str, Any] | None:
    row = db.execute(
        "SELECT origin, decided_at FROM cmap.source_version "
        "WHERE source_id = %s AND supersedes_source_id = %s",
        (newer_id, older_id),
    ).fetchone()
    if row is None:
        return None
    return str(row[0]), row[1]


class FakePrompt:
    """Answer seam: record each prompt and return a canned, citation-free reply."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def __call__(
        self, messages: list[dict[str, Any]], settings: Any
    ) -> dict[str, Any]:
        del settings
        self.prompts.append(str(messages[-1]["content"]))
        payload = {
            "answer_md": "The rule is documented in the purchase order policy.",
            "citations": [],
            "unknowns": [],
        }
        return {
            "choices": [{"message": {"content": json.dumps(payload)}}],
            "usage": {"total_tokens": 10},
        }


# --------------------------------------------------------- the named gates


def test_revised_policy_supersedes_old_rule(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    db: Any,
) -> None:
    """A revised policy with the same title and a later date auto-supersedes.

    The revision replaces the old rule with a different one: the old rule's
    fact lives only in the superseded policy and goes to history.
    """
    entities = _seed_entities(db)
    old = _upload(
        client,
        admin_headers,
        "widget-policy.txt",
        OLD_RULE_SENTENCE.encode(),
        title="Widget Policy",
        effective_date="2025-01-15",
    )
    old_rel = _seed_fact(
        db,
        old["id"],
        entities["rule_old"],
        entities["process"],
        OLD_RULE_SENTENCE,
        OLD_RULE_SENTENCE,
    )
    assert _relation_status(db, old_rel) == "current"

    revised = _upload(
        client,
        admin_headers,
        "widget-policy.txt",
        NEW_RULE_SENTENCE.encode(),
        title="Widget Policy",
        effective_date="2025-06-01",
    )
    assert revised["id"] != old["id"]
    assert revised.get("duplicate") is False
    assert len(revised["versions"]) == 1
    proposal = revised["versions"][0]
    assert proposal["supersedes_source_id"] == old["id"]
    assert proposal["origin"] == ORIGIN_AUTO_TITLE
    assert proposal["decided_at"] is not None

    decision = _version_row(db, revised["id"], old["id"])
    assert decision is not None
    origin, decided_at = decision
    assert origin == ORIGIN_AUTO_TITLE
    assert decided_at is not None

    # The old rule's fact is supported only by the superseded source now.
    assert _relation_status(db, old_rel) == "superseded"

    new_rel = _seed_fact(
        db,
        revised["id"],
        entities["rule_new"],
        entities["process"],
        NEW_RULE_SENTENCE,
        NEW_RULE_SENTENCE,
    )
    recompute_relation_status(db)
    db.commit()
    assert _relation_status(db, new_rel) == "current"

    # Both documents stay fully queued for reading: supersession marks,
    # it never blocks ingestion or reading.
    assert old["read_state"] == "queued"
    assert revised["read_state"] == "queued"


def test_fact_also_in_live_source_stays_current(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    db: Any,
) -> None:
    """A fact also in a live source is current everywhere; only-source facts go."""
    entities = _seed_entities(db)
    old = _upload(
        client,
        admin_headers,
        "widget-policy.txt",
        OLD_RULE_SENTENCE.encode(),
        title="Widget Policy",
        effective_date="2025-01-15",
    )
    # The fact also stated by the live meeting below…
    shared_rel = _seed_fact(
        db,
        old["id"],
        entities["rule_old"],
        entities["process"],
        OLD_RULE_SENTENCE,
        OLD_RULE_SENTENCE,
    )
    # …and the fact the old policy alone states.
    only_old_rel = _seed_fact(
        db,
        old["id"],
        entities["rule_new"],
        entities["process"],
        NEW_RULE_SENTENCE,
        NEW_RULE_SENTENCE,
    )

    live = _upload(
        client,
        admin_headers,
        "licensing-sync.txt",
        LIVE_SENTENCE.encode(),
        title="Licensing sync",
        effective_date="2025-07-01",
    )
    live_rel = _seed_fact(
        db,
        live["id"],
        entities["rule_old"],
        entities["process"],
        LIVE_SENTENCE,
        LIVE_SENTENCE,
    )

    revised = _upload(
        client,
        admin_headers,
        "widget-policy.txt",
        NEW_RULE_SENTENCE.encode(),
        title="Widget Policy",
        effective_date="2025-06-01",
    )
    assert revised["versions"], "the revised policy should propose supersession"

    # The fact shared with the live source keeps status 'current' on every row.
    assert _relation_status(db, shared_rel) == "current"
    assert _relation_status(db, live_rel) == "current"
    # A fact whose only source is the old policy is superseded.
    assert _relation_status(db, only_old_rel) == "superseded"

    # Projection keeps the shared fact (both its rows count) and drops the
    # superseded-only one, so its weight cannot reach the map.
    run_project()
    graph = connect_graph()
    rows = graph.query(
        "MATCH (a:Entity)-[r]->(b:Entity) RETURN type(r), r.weight"
    ).result_set
    assert len(rows) == 1
    rel_type, weight = rows[0]
    assert str(rel_type) == "APPLIES_TO"
    assert int(weight) == 2


def test_history_question_can_still_reach_old_version(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """A question about the past surfaces the superseded version (labelled)."""
    entities = _seed_entities(db)
    old = _upload(
        client,
        admin_headers,
        "widget-policy.txt",
        OLD_RULE_SENTENCE.encode(),
        title="Widget Policy",
        effective_date="2025-01-15",
    )
    _seed_fact(
        db,
        old["id"],
        entities["rule_old"],
        entities["process"],
        OLD_RULE_SENTENCE,
        OLD_RULE_SENTENCE,
        with_embedding=True,
    )
    revised = _upload(
        client,
        admin_headers,
        "widget-policy.txt",
        NEW_RULE_SENTENCE.encode(),
        title="Widget Policy",
        effective_date="2025-06-01",
    )
    new_rel = _seed_fact(
        db,
        revised["id"],
        entities["rule_new"],
        entities["process"],
        NEW_RULE_SENTENCE,
        NEW_RULE_SENTENCE,
        with_embedding=True,
    )
    assert revised["versions"], "the revised policy should auto-supersede"
    recompute_relation_status(db)
    db.commit()
    assert _relation_status(db, new_rel) == "current"

    fake_embeddings(monkeypatch)
    fake = FakePrompt()
    monkeypatch.setattr(answer_mod, "_post_chat", fake)

    result = answer_question(
        "Until March 2025, what was the purchase order approval rule?", "local", []
    )
    assert result["mode_used"] == "local"
    history_prompt = fake.prompts[-1]
    # The superseded rule is reachable and labelled as history…
    assert "500 dollars" in history_prompt
    assert "[SUPERSEDED VERSION" in history_prompt
    # …and history mode adds, it does not replace: the current rule is there too.
    assert "1000 dollars" in history_prompt

    answer_question("What is the purchase order approval rule now?", "local", [])
    current_prompt = fake.prompts[-1]
    assert "1000 dollars" in current_prompt
    assert "500 dollars" not in current_prompt
    assert "[SUPERSEDED VERSION" not in current_prompt


# ------------------------------------------------------- detection behaviour


def test_similarity_hit_proposes_one_click_confirm(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """First-3-chunk similarity ≥ 0.9 with a different hash ⇒ one-click confirm."""
    entities = _seed_entities(db)
    first = _upload(
        client,
        admin_headers,
        "onboarding-runbook.txt",
        b"Alpha onboarding steps for new hires and managers alike.",
        title="Onboarding runbook",
        effective_date="2025-01-10",
    )
    _run_read(db, monkeypatch, first["id"])
    old_rel = _seed_fact(
        db,
        first["id"],
        entities["rule_old"],
        entities["process"],
        OLD_RULE_SENTENCE,
        OLD_RULE_SENTENCE,
    )

    second = _upload(
        client,
        admin_headers,
        "vendor-playbook.txt",
        b"Beta vendor escalation steps for new partners and managers alike.",
        title="Vendor escalation playbook",
        effective_date="2025-02-02",
    )
    assert second["versions"] == [], "different titles propose nothing at upload"
    _run_read(db, monkeypatch, second["id"])

    decision = _version_row(db, second["id"], first["id"])
    assert decision is not None, "similarity detection should propose a version"
    origin, decided_at = decision
    assert origin == ORIGIN_AUTO_SIMILARITY
    assert decided_at is None, "similarity alone is never auto-accepted"

    response = client.post(
        f"/sources/{second['id']}/supersession/confirm",
        headers=admin_headers,
        json={"supersedes_source_id": first["id"]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["origin"] == ORIGIN_ADMIN
    assert body["decided_at"] is not None

    decision = _version_row(db, second["id"], first["id"])
    assert decision is not None
    assert decision[0] == ORIGIN_ADMIN
    assert decision[1] is not None
    assert _relation_status(db, old_rel) == "superseded"


def test_single_word_title_is_only_proposed(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    db: Any,
) -> None:
    """One-word titles collide ("Transcript"): never auto-accepted, only proposed."""
    first = _upload(
        client,
        admin_headers,
        "transcript-1.txt",
        b"Ilona: Morning all, let us start the meeting.",
        title="Transcript",
        effective_date="2025-01-05",
    )
    second = _upload(
        client,
        admin_headers,
        "transcript-2.txt",
        b"Ilona: Morning all, let us start the next meeting.",
        title="Transcript",
        effective_date="2025-01-12",
    )
    assert second["versions"], "same title still proposes a newer version"
    entry = second["versions"][0]
    assert entry["supersedes_source_id"] == first["id"]
    assert entry["decided_at"] is None
    decision = _version_row(db, second["id"], first["id"])
    assert decision is not None
    assert decision[1] is None


def test_detection_failure_never_blocks_ingestion(
    client: TestClient,
    admin_headers: dict[str, str],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """Supersession marks; a detection failure must never stop an upload."""

    def _boom(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        del args, kwargs
        raise RuntimeError("detection exploded")

    monkeypatch.setattr("brain.versions.detect_title", _boom)
    body = _upload(
        client,
        admin_headers,
        "standalone.txt",
        b"A document with no versioning problems at all.",
        title="Standalone note",
        effective_date="2025-03-03",
    )
    assert body["id"]
    assert body["versions"] == []
    row = db.execute(
        "SELECT title FROM cmap.source WHERE id = %s", (body["id"],)
    ).fetchone()
    assert row is not None and str(row[0]) == "Standalone note"


def test_relation_status_cannot_be_hand_set(db: Any) -> None:
    """The SQL guard rejects any UPDATE touching status outside the recompute."""
    entities = _seed_entities(db)
    source_id = "00000000-0000-4000-8000-000000000001"
    db.execute(
        "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes) "
        "VALUES (%s, 'text', 'Guard check', 'test/guard.txt', 'guard-sha', 1)",
        (source_id,),
    )
    db.commit()
    rel_id = _seed_fact(
        db,
        source_id,
        entities["rule_old"],
        entities["process"],
        OLD_RULE_SENTENCE,
        OLD_RULE_SENTENCE,
    )
    with pytest.raises(psycopg.Error, match="cannot be hand-set"):
        db.execute(
            "UPDATE cmap.relation SET status = 'superseded' WHERE id = %s", (rel_id,)
        )
    db.rollback()
    assert _relation_status(db, rel_id) == "current"


def test_title_key_folds_extensions_and_case() -> None:
    """Same normalised title for the revision cases detection must catch."""
    assert title_key("Widget Policy.pdf") == title_key("WIDGET POLICY")
    assert title_key("Widget Policy.docx") == title_key("widget policy")
    assert title_key("Q3.report") != title_key("Q3")
