"""D3 gate: contradictions across sources are detected and queued.

Five binding gates (plan Phase D3): two owners flagged, a date change is not a
contradiction, a policy-vs-practice gap is recorded, an interview answer that
contradicts a document creates a gap immediately, and a PRECEDES cycle is
flagged. The classifier seam is ``brain.contradictions._post_chat``; the date
rule (dates differ -> not a conflict) runs in code and never reaches a model.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from brain import contradictions as cx
from brain.config import get_settings


@pytest.fixture()
def frontier_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """The contradictions seat must name a model for classifier calls."""
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeClassifier:
    """Replay the contradiction classifier; records every prompt."""

    def __init__(self, classification: str, summary: str = "sources make opposing claims") -> None:
        self.classification = classification
        self.summary = summary
        self.prompts: list[str] = []

    def __call__(self, messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        del settings
        self.prompts.append(str(messages[-1]["content"]))
        payload = {"classification": self.classification, "summary": self.summary}
        return {
            "choices": [{"message": {"content": json.dumps(payload)}}],
            "usage": {"total_tokens": 10},
        }


def _fake_classifier(monkeypatch: pytest.MonkeyPatch, classification: str) -> FakeClassifier:
    fake = FakeClassifier(classification)
    monkeypatch.setattr(cx, "_post_chat", fake)
    return fake


def _seed_entity(db: Any, name: str, entity_type: str = "Process") -> str:
    row = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name) "
        "VALUES (%s, %s) RETURNING id::text",
        (entity_type, name),
    ).fetchone()
    db.commit()
    return str(row[0])


def _seed_source(db: Any, title: str, effective_date: str, kind: str = "text") -> str:
    row = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, "
        "effective_date, read_state) VALUES (%s, %s, %s, %s, 10, %s, 'read') "
        "RETURNING id::text",
        (kind, title, f"cmap/test/{title}", f"sha-{title}", effective_date),
    ).fetchone()
    db.commit()
    return str(row[0])


def _seed_relation(
    db: Any,
    source_id: str,
    from_entity: str,
    to_entity: str,
    description: str,
    quote: str,
    *,
    rel_type: str = "OWNS",
    stance: str = "practice",
) -> str:
    ordinal = int(
        db.execute(
            "SELECT count(*) FROM cmap.chunk WHERE source_id = %s::uuid", (source_id,)
        ).fetchone()[0]
    )
    chunk_id = str(
        db.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
            "VALUES (%s::uuid, %s, %s::jsonb, %s, 20) RETURNING id::text",
            (source_id, ordinal, json.dumps({"page": ordinal + 1}), quote),
        ).fetchone()[0]
    )
    from_m = str(
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) "
            "VALUES (%s::uuid, 'Process', 'from', 'from', %s, %s::uuid) RETURNING id::text",
            (chunk_id, quote, from_entity),
        ).fetchone()[0]
    )
    to_m = str(
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) "
            "VALUES (%s::uuid, 'Process', 'to', 'to', %s, %s::uuid) RETURNING id::text",
            (chunk_id, quote, to_entity),
        ).fetchone()[0]
    )
    rel_id = str(
        db.execute(
            "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, "
            "rel_type, description, stance, confidence, quote) "
            "VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, 0.9, %s) "
            "RETURNING id::text",
            (chunk_id, from_m, to_m, rel_type, description, stance, quote),
        ).fetchone()[0]
    )
    db.commit()
    return rel_id


def _contradictions(db: Any) -> list[tuple[str, str, str]]:
    return [
        (str(row[0]), str(row[1]), str(row[2]))
        for row in db.execute(
            "SELECT kind, status, summary FROM cmap.contradiction ORDER BY kind"
        ).fetchall()
    ]


def _gap_rows(db: Any) -> list[tuple[Any, ...]]:
    return db.execute(
        "SELECT question, why, entity_ids, department, suggested_person, "
        "target_employee_id::text FROM cmap.open_question "
        "WHERE why LIKE 'Sources disagree:%'"
    ).fetchall()


# ------------------------------------------------------------- the named gates


def test_two_owners_flagged(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two OWNS statements from two sources about one entity pair are flagged."""
    person = _seed_entity(db, "Jessica")
    project = _seed_entity(db, "Licensing approval")
    first = _seed_source(db, "Ownership policy", "2026-03-01")
    second = _seed_source(db, "Team notes", "2026-03-01")
    rel_a = _seed_relation(
        db, first, person, project, "Jessica owns the licensing approval.",
        "Jessica owns sign-off.", rel_type="OWNS", stance="practice",
    )
    rel_b = _seed_relation(
        db, second, person, project, "Ilona owns the licensing approval, not Jessica.",
        "Ilona owns sign-off, not Jessica.", rel_type="OWNS", stance="practice",
    )
    fake = _fake_classifier(monkeypatch, "true contradiction")
    stats = cx.run_contradictions()
    assert stats["conflicts"] == 1 and stats["gaps"] == 1
    assert len(fake.prompts) == 1
    rows = _contradictions(db)
    assert rows == [("true_contradiction", "open", "sources make opposing claims")]
    stored = db.execute(
        "SELECT relation_a::text, relation_b::text FROM cmap.contradiction"
    ).fetchone()
    assert {str(stored[0]), str(stored[1])} == {rel_a, rel_b}
    gaps = _gap_rows(db)
    assert len(gaps) == 1
    question, why, entity_ids, department, suggested_person, target = gaps[0]
    assert "Which statement is correct" in str(question)
    assert str(why) == "Sources disagree: sources make opposing claims"
    assert set(str(item) for item in entity_ids) == {person, project}
    assert department is None and suggested_person is None and target is None


def test_date_change_is_not_contradiction(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same claim at different source dates: recorded for D2, never a conflict."""
    person = _seed_entity(db, "Jessica")
    project = _seed_entity(db, "Licensing approval")
    old = _seed_source(db, "Ownership policy", "2026-01-01")
    new = _seed_source(db, "Ownership policy v2", "2026-03-01")
    _seed_relation(
        db, old, person, project, "Jessica owns the licensing approval.",
        "Jessica owns sign-off.", rel_type="OWNS", stance="practice",
    )
    _seed_relation(
        db, new, person, project, "Ilona owns the licensing approval.",
        "Ilona owns sign-off.", rel_type="OWNS", stance="practice",
    )
    # The date rule wins in code: a model call would be a wasted frontier call.
    fake = FakeClassifier("true contradiction")
    monkeypatch.setattr(cx, "_post_chat", fake)
    stats = cx.run_contradictions()
    assert fake.prompts == []
    assert stats["changed_over_time"] == 1 and stats["conflicts"] == 0
    rows = _contradictions(db)
    assert rows and rows[0][0] == "changed_over_time"
    assert rows[0][1] == "explained"
    resolution = db.execute("SELECT resolution FROM cmap.contradiction").fetchone()
    assert "timeline change" in str(resolution[0])
    assert _gap_rows(db) == []


def test_policy_vs_practice_recorded(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A policy stance vs a practice stance is stored as a gap, even across dates."""
    person = _seed_entity(db, "Jessica")
    project = _seed_entity(db, "Licensing approval")
    policy_doc = _seed_source(db, "Approval procedure", "2026-01-01")
    meeting = _seed_source(db, "March standup", "2026-03-14")
    _seed_relation(
        db, policy_doc, person, project,
        "The policy says the VP approves every licensing package.",
        "The VP approves every licensing package.", rel_type="APPROVES", stance="policy",
    )
    _seed_relation(
        db, meeting, person, project,
        "In practice Jessica signs off on licensing packages herself.",
        "We sign off ourselves.", rel_type="APPROVES", stance="practice",
    )
    fake = _fake_classifier(monkeypatch, "policy-vs-practice gap")
    stats = cx.run_contradictions()
    assert len(fake.prompts) == 1, "the date rule must not swallow stance pairs"
    assert stats["conflicts"] == 1 and stats["gaps"] == 1
    rows = _contradictions(db)
    assert rows == [("policy_vs_practice", "open", "sources make opposing claims")]
    gaps = _gap_rows(db)
    assert len(gaps) == 1
    assert "Why does practice differ" in str(gaps[0][0])


def test_interview_answer_contradicting_doc_creates_gap(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An interview answer contradicting a document triggers the same path now."""
    person = _seed_entity(db, "Jessica")
    project = _seed_entity(db, "Licensing approval")
    doc = _seed_source(db, "Approval procedure", "2026-01-01")
    _seed_relation(
        db, doc, person, project, "Jessica owns the licensing approval.",
        "Jessica owns sign-off.", rel_type="OWNS", stance="policy",
    )
    answer_source = _seed_source(
        db, "Interview answer — Test Employee — 2026-03-14",
        "2026-03-14", kind="transcript",
    )
    _seed_relation(
        db, answer_source, person, project, "Ilona owns the licensing approval.",
        "Ilona owns sign-off.", rel_type="OWNS", stance="practice",
    )
    db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids, state, "
        "answer, answer_source_id) VALUES (%s, %s, %s, 'answered', %s, %s::uuid)",
        ("Who owns sign-off?", "answered question", [person], "Ilona does.",
         answer_source),
    )
    db.commit()
    # The relations hook queues an immediate scoped scan for an interview
    # answer — and only for one.
    cx.after_source_relations(answer_source)
    cx.after_source_relations(doc)
    jobs = db.execute(
        "SELECT payload->>'source_id' FROM cmap.job WHERE kind = 'contradictions'"
    ).fetchall()
    assert [str(row[0]) for row in jobs] == [answer_source]
    job = db.execute(
        "SELECT id, payload FROM cmap.job WHERE kind = 'contradictions'"
    ).fetchone()
    fake = _fake_classifier(monkeypatch, "true contradiction")
    cx.handle_contradictions({"id": job[0], "kind": "contradictions", "payload": job[1]})
    assert len(fake.prompts) == 1
    assert _contradictions(db) == [("true_contradiction", "open", "sources make opposing claims")]
    gaps = _gap_rows(db)
    assert len(gaps) == 1
    assert str(gaps[0][1]) == "Sources disagree: sources make opposing claims"


def test_precedes_cycle_flagged(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PRECEDES cycle among current relations is flagged without a model call."""
    step_a = _seed_entity(db, "Draft package", "Step")
    step_b = _seed_entity(db, "Send to licensor", "Step")
    step_c = _seed_entity(db, "Record approval", "Step")
    source = _seed_source(db, "Process notes", "2026-03-01")
    _seed_relation(
        db, source, step_a, step_b, "Drafting precedes sending.",
        "Draft first.", rel_type="PRECEDES", stance="practice",
    )
    _seed_relation(
        db, source, step_b, step_c, "Sending precedes recording.",
        "Send before recording.", rel_type="PRECEDES", stance="practice",
    )
    _seed_relation(
        db, source, step_c, step_a, "Recording precedes drafting the next one.",
        "Recording comes before the next draft.", rel_type="PRECEDES", stance="practice",
    )
    fake = FakeClassifier("true contradiction")
    monkeypatch.setattr(cx, "_post_chat", fake)
    stats = cx.run_contradictions()
    assert fake.prompts == []
    assert stats["cycles"] == 1 and stats["gaps"] == 1
    rows = _contradictions(db)
    assert rows[0][:2] == ("precedes_cycle", "open")
    assert rows[0][2].startswith("PRECEDES cycle: ")
    gaps = _gap_rows(db)
    assert len(gaps) == 1
    assert "In what order" in str(gaps[0][0])


# ------------------------------------------------------- storage and surfacing


def test_gap_addresses_the_function_most_relevant_role(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The F1 gap row routes to the function's most relevant role."""
    person = _seed_entity(db, "Jessica")
    project = _seed_entity(db, "Licensing approval")
    first = _seed_source(db, "Ownership policy", "2026-03-01")
    second = _seed_source(db, "Team notes", "2026-03-01")
    _seed_relation(
        db, first, person, project, "Jessica owns sign-off.", "Jessica owns sign-off.",
        rel_type="OWNS", stance="practice",
    )
    _seed_relation(
        db, second, person, project, "Ilona owns sign-off.", "Ilona owns sign-off.",
        rel_type="OWNS", stance="practice",
    )
    function_id = str(
        db.execute(
            "INSERT INTO cmap.function (key, name, description, aliases, sort) "
            "VALUES ('licensing', 'Licensing', 'Approvals', "
            "ARRAY['Licensing']::text[], 10) RETURNING id::text"
        ).fetchone()[0]
    )
    db.execute(
        "INSERT INTO cmap.entity_function (entity_id, function_id, weight, origin) "
        "VALUES (%s::uuid, %s::uuid, 1.0, 'auto')",
        (project, function_id),
    )
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department, job_title) "
        "VALUES ('00000000-0000-4000-8000-0000000000a1', 'Licensing', "
        "'Licensing Manager')",
    )
    db.commit()
    _fake_classifier(monkeypatch, "true contradiction")
    cx.run_contradictions()
    gaps = _gap_rows(db)
    assert len(gaps) == 1
    _, _, _, department, suggested_person, target = gaps[0]
    assert str(department) == "Licensing"
    assert str(suggested_person) == "Licensing Manager"
    assert str(target) == "00000000-0000-4000-8000-0000000000a1"


def test_same_pair_recorded_once_and_never_reclassified(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A same/refinement verdict is the pair's record: no gap, no second call."""
    person = _seed_entity(db, "Jessica")
    project = _seed_entity(db, "Licensing approval")
    first = _seed_source(db, "Ownership policy", "2026-03-01")
    second = _seed_source(db, "Team notes", "2026-03-01")
    _seed_relation(
        db, first, person, project, "Jessica owns sign-off.", "Jessica owns sign-off.",
        rel_type="OWNS", stance="practice",
    )
    _seed_relation(
        db, second, person, project, "Jessica owns the licensing sign-off.",
        "Jessica owns the licensing sign-off.", rel_type="OWNS", stance="practice",
    )
    fake = _fake_classifier(monkeypatch, "same")
    cx.run_contradictions()
    assert len(fake.prompts) == 1
    rows = _contradictions(db)
    assert rows == [("same", "explained", "sources make opposing claims")]
    assert _gap_rows(db) == []
    cx.run_contradictions()
    assert len(fake.prompts) == 1, "the recorded pair is never re-classified"


def test_entity_and_answers_surface_the_conflict(
    db: Any, frontier_env: None, monkeypatch: pytest.MonkeyPatch,
    client: Any, user_headers: dict[str, str],
) -> None:
    """The entity payload and the answer context both carry the labelled conflict."""
    person = _seed_entity(db, "Jessica")
    project = _seed_entity(db, "Licensing approval")
    first = _seed_source(db, "Ownership policy", "2026-03-01")
    second = _seed_source(db, "Team notes", "2026-03-01")
    _seed_relation(
        db, first, person, project, "Jessica owns sign-off.", "Jessica owns sign-off.",
        rel_type="OWNS", stance="practice",
    )
    _seed_relation(
        db, second, person, project, "Ilona owns sign-off.", "Ilona owns sign-off.",
        rel_type="OWNS", stance="practice",
    )
    _fake_classifier(monkeypatch, "true contradiction")
    cx.run_contradictions()
    body = client.get(f"/entities/{person}", headers=user_headers).json()
    assert len(body["contradictions"]) == 1
    item = body["contradictions"][0]
    assert item["kind"] == "true_contradiction"
    assert item["status"] == "open"
    assert item["summary"] == "sources make opposing claims"
    assert item["resolution"] is None
    assert item["source_a_title"] == "Ownership policy"
    assert item["source_b_title"] == "Team notes"
    listed = client.get("/contradictions", headers=user_headers).json()["contradictions"]
    assert len(listed) == 1
    assert listed[0]["relation_a"]["quote"] == "Jessica owns sign-off."
    assert {e["id"] for e in listed[0]["entities"]} == {person, project}
    lines = cx.disagreement_lines(db, [person])
    assert lines == [
        "sources disagree: sources make opposing claims "
        "(Ownership policy vs Team notes)"
    ]
