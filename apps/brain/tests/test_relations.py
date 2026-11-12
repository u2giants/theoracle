"""Relations stage: frontier relationship extraction (plan step 5).

The flat stage runs first on recorded ScaleDown responses, then the relations
stage replays recorded frontier responses from
``tests/fixtures/recorded/frontier/relations.json``. No test calls a real model.
"""

from __future__ import annotations

from typing import Any

import pytest
from conftest import fake_embeddings, fake_relations, fake_scaledown
from psycopg.types.json import Json
from test_flat import PDF_FIXTURE, TRANSCRIPT_FIXTURE, _seed_fixture, _seed_text

from brain.config import get_settings
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import (
    RelationsError,
    handle_relations,
    relations_prompt_hash,
)


@pytest.fixture()
def pipeline_env(monkeypatch: pytest.MonkeyPatch):
    """ScaleDown on for the flat stage; a frontier model id from env."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    yield
    get_settings.cache_clear()


def _flat(monkeypatch: pytest.MonkeyPatch, db: Any, fixture: str, kind: str, rec: str) -> str:
    fake_scaledown(monkeypatch, rec)
    source_id = _seed_fixture(db, fixture, kind)
    handle_classify_extract({"payload": {"source_id": source_id}})
    return source_id


def _relations(db: Any, source_id: str) -> list[tuple[str, str, str, str, str, str]]:
    rows = db.execute(
        "SELECT r.rel_type, fm.entity_type, fm.surface_name, tm.entity_type, "
        "tm.surface_name, r.quote "
        "FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "WHERE c.source_id = %s",
        (source_id,),
    ).fetchall()
    return [tuple(str(value) for value in row) for row in rows]


def test_transcript_issue_blocked_by_approval_step(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """Done-when: BLOCKED_BY or CAUSES from the Issue to the approval step."""
    source_id = _flat(monkeypatch, db, TRANSCRIPT_FIXTURE, "transcript", "transcript.json")
    fake = fake_relations(monkeypatch)
    handle_relations({"payload": {"source_id": source_id}})
    relations = _relations(db, source_id)
    assert any(
        rel in ("BLOCKED_BY", "CAUSES")
        and from_type == "Issue"
        and "approval" in to_name.lower()
        for rel, from_type, _, _, to_name, _ in relations
    )
    texts = {
        row[0]
        for row in db.execute(
            "SELECT c.text FROM cmap.chunk c WHERE c.source_id = %s", (source_id,)
        ).fetchall()
    }
    for *_, quote in relations:
        assert any(quote in text for text in texts)
    # chatter chunks without mentions never reach the model
    assert not any("Morning Marco" in prompt.split("PASSAGE:")[-1] for prompt in fake.prompts)
    prompt = next(p for p in fake.prompts if "only licensing manager" in p.split("PASSAGE:")[-1])
    assert '"key": "m1", "type": "Person", "name": "Jessica"' in prompt
    assert "CONTEXT" in prompt and "Jessica's approval" not in prompt.split("PASSAGE:")[-1]
    models = {
        row[0]
        for row in db.execute(
            "SELECT e.model FROM cmap.extraction e JOIN cmap.chunk c ON c.id = e.chunk_id "
            "WHERE c.source_id = %s AND e.stage = 'relations'",
            (source_id,),
        ).fetchall()
    }
    assert models == {"test/frontier-model"}


def test_pdf_hands_off_and_except_when(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """Done-when: HANDS_OFF_TO design step -> licensing; EXCEPT_WHEN from exceptions."""
    source_id = _flat(monkeypatch, db, PDF_FIXTURE, "pdf", "pdf.json")
    fake_relations(monkeypatch)
    handle_relations({"payload": {"source_id": source_id}})
    relations = _relations(db, source_id)
    assert any(
        rel == "HANDS_OFF_TO" and "design" in f.lower() and "licensing" in t.lower()
        for rel, _, f, _, t, _ in relations
    )
    assert any(rel == "EXCEPT_WHEN" for rel, *_ in relations)
    new = db.execute(
        "SELECT count(*) FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
        "WHERE c.source_id = %s AND m.surface_name = 'licensor style-guide update'",
        (source_id,),
    ).fetchone()[0]
    assert new == 1
    # the relation whose key m20 does not resolve was dropped
    assert sum(1 for rel, *_ in relations if rel == "HANDS_OFF_TO") == 1


def _one_chunk(monkeypatch: pytest.MonkeyPatch, db: Any, text: str, tag: str) -> str:
    fake_scaledown(monkeypatch, "transcript.json")
    source_id = _seed_text(db, text, tag)
    handle_classify_extract({"payload": {"source_id": source_id}})
    return source_id


JESSICA = "Marco: Jessica is the only licensing manager we have."


def _response(**relation: Any) -> dict[str, Any]:
    base = {
        "from": "m1",
        "to": "m2",
        "type": "PERFORMS",
        "description": "Jessica holds the licensing manager role.",
        "stance": "report",
        "confidence": 0.9,
        "quote": "Jessica is the only licensing manager we have.",
    }
    base.update(relation)
    return {"relations": [base], "new_mentions": []}


def test_drops_relation_with_fabricated_quote(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """A quote that is not an exact substring of the passage is dropped."""
    source_id = _one_chunk(monkeypatch, db, JESSICA, "fabricated")
    fake = fake_relations(monkeypatch)
    fake.override = _response(quote="Jessica approves every package personally.")
    handle_relations({"payload": {"source_id": source_id}})
    assert _relations(db, source_id) == []
    stored = db.execute(
        "SELECT count(*) FROM cmap.extraction e JOIN cmap.chunk c ON c.id = e.chunk_id "
        "WHERE c.source_id = %s AND e.stage = 'relations'",
        (source_id,),
    ).fetchone()[0]
    assert stored == 1


def test_rejects_unknown_type(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """A relation type outside the ontology is rejected; a valid one lands."""
    source_id = _one_chunk(monkeypatch, db, JESSICA, "unknown-type")
    fake = fake_relations(monkeypatch)
    good = _response()["relations"][0]
    bad = dict(good, type="MANAGES")
    fake.override = {"relations": [bad, good], "new_mentions": []}
    handle_relations({"payload": {"source_id": source_id}})
    assert [row[0] for row in _relations(db, source_id)] == ["PERFORMS"]


def test_inference_confidence_is_capped(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """Inference stance never lands above confidence 0.6."""
    source_id = _one_chunk(monkeypatch, db, JESSICA, "inference")
    fake = fake_relations(monkeypatch)
    fake.override = _response(stance="inference", confidence=0.95)
    handle_relations({"payload": {"source_id": source_id}})
    confidence = db.execute(
        "SELECT r.confidence FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
        "WHERE c.source_id = %s",
        (source_id,),
    ).fetchone()[0]
    assert confidence == pytest.approx(0.6)


def test_resume_skips_done_chunks(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """A capped job fails clearly, keeps finished chunks, and resumes the rest."""
    source_id = _flat(monkeypatch, db, PDF_FIXTURE, "pdf", "pdf.json")
    fake = fake_relations(monkeypatch)
    monkeypatch.setenv("BRAIN_MAX_FRONTIER_CALLS_PER_JOB", "1")
    get_settings.cache_clear()
    with pytest.raises(RelationsError, match="BRAIN_MAX_FRONTIER_CALLS_PER_JOB"):
        handle_relations({"payload": {"source_id": source_id}})
    done_sql = (
        "SELECT count(*) FROM cmap.extraction e JOIN cmap.chunk c ON c.id = e.chunk_id "
        "WHERE c.source_id = %s AND e.stage = 'relations' AND e.prompt_hash = %s"
    )
    assert db.execute(done_sql, (source_id, relations_prompt_hash())).fetchone()[0] == 1
    first_calls = len(fake.prompts)

    monkeypatch.setenv("BRAIN_MAX_FRONTIER_CALLS_PER_JOB", "100")
    get_settings.cache_clear()
    handle_relations({"payload": {"source_id": source_id}})
    finished = db.execute(done_sql, (source_id, relations_prompt_hash())).fetchone()[0]
    assert finished == 3
    assert len(fake.prompts) == first_calls + 2

    handle_relations({"payload": {"source_id": source_id}})
    assert len(fake.prompts) == first_calls + 2
    relation_count = len(_relations(db, source_id))
    handle_relations({"payload": {"source_id": source_id}})
    assert len(_relations(db, source_id)) == relation_count


def test_truncated_response_keeps_complete_relations() -> None:
    """A response cut off at max_tokens keeps the relations that arrived whole."""
    from brain.extract.relations import parse_relations_json

    content = (
        '```json\n{"relations": [{"from": "m1", "to": "m2", "type": "USES", '
        '"description": "d", "stance": "policy", "confidence": 1, "quote": "q"}, '
        '{"from": "m2", "to": "m3", "ty'
    )
    parsed = parse_relations_json(content)
    assert [item["type"] for item in parsed["relations"]] == ["USES"]
    tabbed = parse_relations_json('{"relations": [{"quote": "PO-1\tMeadow"}]}')
    assert tabbed["relations"][0]["quote"] == "PO-1\tMeadow"
    with pytest.raises(RelationsError):
        parse_relations_json("no json here")


def test_question_and_answer_across_turns_linked(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """Done-when: the reply turn links to the question turn before it (plan E1).

    The question names the licensor sign-off and the reply names Jessica; the
    window covers both turns, so one relation joins them even though each
    mention lives in its own chunk. The quote sits in the question's chunk, so
    the relation stores the quote's true chunk id — not the window's anchor.
    """
    source_id = _flat(monkeypatch, db, TRANSCRIPT_FIXTURE, "transcript", "transcript.json")
    fake_relations(monkeypatch, "relations_windows.json")
    handle_relations({"payload": {"source_id": source_id}})
    question_chunk = str(
        db.execute(
            "SELECT id FROM cmap.chunk WHERE source_id = %s AND text LIKE %s",
            (source_id, "Ilona: Which approval%"),
        ).fetchone()[0]
    )
    rows = db.execute(
        "SELECT r.rel_type, fm.surface_name, tm.surface_name, r.quote, r.chunk_id "
        "FROM cmap.relation r "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "WHERE fm.surface_name = 'Jessica' AND tm.surface_name = 'the licensor sign-off' "
        "AND fm.chunk_id <> tm.chunk_id",
        (),
    ).fetchall()
    assert rows, "the answer's Jessica links to the question's licensor sign-off"
    _rel_type, _frm, _to, quote, chunk_id = rows[0]
    assert quote == "the licensor sign-off"
    assert str(chunk_id) == question_chunk, "the quote's true chunk id is the question's turn"


def test_relation_across_page_break(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """Done-when: a relation links mentions on both sides of a PDF page break."""
    source_id = _flat(monkeypatch, db, PDF_FIXTURE, "pdf", "pdf.json")
    fake_relations(monkeypatch, "relations_windows.json")
    handle_relations({"payload": {"source_id": source_id}})
    rows = db.execute(
        "SELECT r.quote, r.chunk_id, fpc.locator, tpc.locator "
        "FROM cmap.relation r "
        "JOIN cmap.mention fm ON fm.id = r.from_mention_id "
        "JOIN cmap.mention tm ON tm.id = r.to_mention_id "
        "JOIN cmap.chunk fpc ON fpc.id = fm.chunk_id "
        "JOIN cmap.chunk tpc ON tpc.id = tm.chunk_id "
        "WHERE fm.surface_name = 'Reorder SKUs below 5,000 units with unchanged artwork' "
        "AND tm.surface_name = 'The Buyer may create the purchase order'",
        (),
    ).fetchall()
    assert rows, "the exception on one page links to the purchase-order step on another"
    quote, chunk_id, from_page, to_page = rows[0]
    assert quote == "The Buyer may create the purchase order"
    assert from_page["page"] != to_page["page"], "the two ends sit on different pages"
    quote_page = db.execute(
        "SELECT locator FROM cmap.chunk WHERE id = %s", (str(chunk_id),)
    ).fetchone()[0]
    assert quote_page["page"] == to_page["page"], "the quote's true chunk id is its own page"


def test_no_duplicate_from_overlap(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """Done-when: a relation found in two overlapping windows is stored once."""
    text = "Marco: Jessica is the only licensing manager we have."
    fake_scaledown(monkeypatch, "transcript.json")
    row = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
        "VALUES ('text', 'flat-test overlap', 'test/overlap.txt', 'overlap-e1', 48) "
        "RETURNING id",
        (),
    ).fetchone()
    source_id = str(row[0])
    chunk_ids: list[str] = []
    for ordinal in (0, 1):
        chunk_id = str(
            db.execute(
                "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
                "VALUES (%s, %s, %s, %s, 10) RETURNING id",
                (source_id, ordinal, Json({}), text),
            ).fetchone()[0]
        )
        chunk_ids.append(chunk_id)
        db.execute(
            "INSERT INTO cmap.mention "
            "(chunk_id, entity_type, surface_name, normalized_name, quote) VALUES "
            "(%s, 'Person', 'Jessica', 'jessica', %s), "
            "(%s, 'Role', 'licensing manager', 'licensing manager', %s)",
            (chunk_id, text, chunk_id, text),
        )
    db.commit()
    fake = fake_relations(monkeypatch)
    fake.override = _response()
    handle_relations({"payload": {"source_id": source_id}})
    assert len(fake.prompts) == 2, "both windows ran over the shared chunk"
    assert len(_relations(db, source_id)) == 1, "the shared finding is stored once"


def test_drop_reasons_counted(
    monkeypatch: pytest.MonkeyPatch, db: Any, pipeline_env
) -> None:
    """Done-when: dropped items are counted per source in read_notes (plan E1)."""
    source_id = _one_chunk(monkeypatch, db, JESSICA, "drop-reasons")
    fake = fake_relations(monkeypatch)
    good = _response()["relations"][0]
    fake.override = {
        "relations": [
            dict(good, quote="Jessica approves every package personally."),
            dict(good, type="MANAGES"),
            dict(good, description=""),
            good,
        ],
        "new_mentions": [],
    }
    handle_relations({"payload": {"source_id": source_id}})
    notes = db.execute(
        "SELECT read_notes FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()[0]
    assert notes["drop_reasons"] == {
        "quote_mismatch": 1,
        "unknown_type": 1,
        "truncation": 1,
    }
    assert len(_relations(db, source_id)) == 1, "the well-formed relation is kept"
