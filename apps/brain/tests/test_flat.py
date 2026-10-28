"""Flat stage: passage classification and extraction (plan step 4).

Recorded ScaleDown responses live in ``tests/fixtures/recorded/scaledown/``
and are replayed through the HTTP seams; the frontier fallback is mocked the
same way. No test calls a real model.
"""

from __future__ import annotations

import hashlib
from typing import Any

import pytest
from conftest import (
    FIXTURES_DIR,
    fake_embeddings,
    fake_frontier,
    fake_scaledown,
)
from psycopg.types.json import Json

from brain.config import get_settings
from brain.extract.flat import (
    handle_classify_extract,
    mentions_from_entities,
    sentence_containing,
)
from brain.extract.normalize import normalize_name
from brain.read.pipeline import read_chunks

TRANSCRIPT_FIXTURE = "teams-approval-2026-03-14.txt"
PDF_FIXTURE = "licensing-approval-procedure.pdf"

PROCEDURE_STEP_SURFACES = [
    "Design submits the concept package",
    "The Licensing Manager reviews the package",
    "The Licensing Manager submits the package to the licensor",
    "the Licensing Manager records the sign-off",
    "Design releases the artwork to QA and to the buyer",
    "The Buyer may create the purchase order",
]


@pytest.fixture()
def scaledown_on(monkeypatch: pytest.MonkeyPatch):
    """Route the flat stage to ScaleDown (as a deployed run would)."""
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _seed_fixture(db: Any, filename: str, kind: str) -> str:
    """Insert one fixture file as a source with its chunks; return the id."""
    data = (FIXTURES_DIR / filename).read_bytes()
    chunks = read_chunks(kind, data)
    row = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (
            kind,
            f"flat-test {filename}",
            f"test/{filename}",
            hashlib.sha256(data).hexdigest(),
            len(data),
        ),
    ).fetchone()
    db.commit()
    source_id = str(row[0])
    for ordinal, chunk in enumerate(chunks):
        db.execute(
            "INSERT INTO cmap.chunk "
            "(source_id, ordinal, locator, text, token_count) "
            "VALUES (%s, %s, %s, %s, %s)",
            (source_id, ordinal, Json(chunk.locator), chunk.text, chunk.token_count),
        )
    db.commit()
    return source_id


def _seed_text(db: Any, text: str, tag: str) -> str:
    """Insert a single-chunk source holding ``text``; return the id."""
    row = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
        "VALUES ('text', %s, %s, %s, %s) "
        "RETURNING id",
        (
            f"flat-test single chunk {tag}",
            f"test/single-{tag}.txt",
            hashlib.sha256(f"{tag}:{text}".encode()).hexdigest(),
            len(text),
        ),
    ).fetchone()
    db.commit()
    source_id = str(row[0])
    db.execute(
        "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, 0, %s, %s, %s)",
        (source_id, Json({}), text, 10),
    )
    db.commit()
    return source_id


def _mentions(db: Any, source_id: str) -> list[tuple[str, str, str, str]]:
    rows = db.execute(
        "SELECT m.entity_type, m.surface_name, m.normalized_name, m.quote "
        "FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
        "WHERE c.source_id = %s",
        (source_id,),
    ).fetchall()
    return [(str(a), str(b), str(c), str(d)) for a, b, c, d in rows]


def test_normalize_name_rules() -> None:
    """Normalisation: casefold, punctuation, leading 'the' and honorifics."""
    assert normalize_name("  Jessica's  Approval ", "Process") == "jessica approval"
    assert normalize_name("The Licensor Sign-off", "Process") == "licensor signoff"
    assert normalize_name("Mr. Smith", "Person") == "smith"
    assert normalize_name("Exceptions", "Exception") == "exception"
    assert normalize_name("Licensing Manager", "Role") == "licensing manager"
    assert normalize_name("Process", "Process") == "process"
    assert normalize_name("Jessica", "Person") == "jessica"


def test_sentence_containing_and_span_repair() -> None:
    """Quotes are the containing sentence; bad spans are repaired by search."""
    text = "Marco: First sentence. Second sentence holds a name."
    start = text.find("Second")
    assert sentence_containing(text, start, start + 6) == "Second sentence holds a name."
    mentions = mentions_from_entities(
        text,
        [
            {"text": "a name", "type": "Artifact", "confidence": 0.9, "start": 0, "end": 2},
            {"text": "a name", "type": "Artifact", "confidence": 0.4},
            {"text": "not in the text", "type": "Artifact", "confidence": 0.9},
        ],
    )
    assert len(mentions) == 1
    assert mentions[0].quote == "Second sentence holds a name."


def test_transcript_finds_jessica_role_process_and_stall_issue(
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
    scaledown_on,
) -> None:
    """Done-when, transcript side: Person, Role, Process and Issue mentions."""
    fake_embeddings(monkeypatch)
    fake = fake_scaledown(monkeypatch, "transcript.json")
    source_id = _seed_fixture(db, TRANSCRIPT_FIXTURE, "transcript")
    handle_classify_extract({"payload": {"source_id": source_id}})
    mentions = _mentions(db, source_id)
    surfaces = [(kind.lower(), surface.lower()) for kind, surface, _, _ in mentions]
    assert ("person", "jessica") in surfaces
    assert ("role", "licensing manager") in surfaces
    assert any(kind == "process" and "licens" in surface for kind, surface in surfaces)
    assert any(kind == "issue" and "bottleneck" in surface for kind, surface in surfaces)
    for _, surface, normalized, quote in mentions:
        assert surface.lower() in quote.lower()
        assert normalized
    models = {
        row[0]
        for row in db.execute(
            "SELECT e.model FROM cmap.extraction e "
            "JOIN cmap.chunk c ON c.id = e.chunk_id WHERE c.source_id = %s",
            (source_id,),
        ).fetchall()
    }
    assert models == {"scaledown/classify", "scaledown/extract"}
    assert fake.extract_calls
    kinds = {
        row[0]: row[1]
        for row in db.execute(
            "SELECT passage_kind, count(*) FROM cmap.chunk "
            "WHERE source_id = %s GROUP BY passage_kind",
            (source_id,),
        ).fetchall()
    }
    assert kinds.get("chatter", 0) > 0
    assert kinds.get("process", 0) > 0


def test_pdf_yields_a_step_for_each_procedure_step(
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
    scaledown_on,
) -> None:
    """Done-when, PDF side: one Step mention for each procedure step."""
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "pdf.json")
    source_id = _seed_fixture(db, PDF_FIXTURE, "pdf")
    handle_classify_extract({"payload": {"source_id": source_id}})
    mentions = _mentions(db, source_id)
    step_surfaces = {
        surface.lower()
        for kind, surface, _, _ in mentions
        if kind == "Step"
    }
    for expected in PROCEDURE_STEP_SURFACES:
        assert expected.lower() in step_surfaces
    procedure_kind = db.execute(
        "SELECT passage_kind FROM cmap.chunk "
        "WHERE source_id = %s AND text LIKE %s",
        (source_id, "%4.1 Design submits%"),
    ).fetchone()[0]
    assert procedure_kind == "process"


def test_chatter_chunks_skip_extraction(
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
    scaledown_on,
) -> None:
    """A chatter chunk at score >= 0.8 is classified but never extracted."""
    fake_embeddings(monkeypatch)
    fake = fake_scaledown(monkeypatch, "transcript.json")
    source_id = _seed_fixture(db, TRANSCRIPT_FIXTURE, "transcript")
    handle_classify_extract({"payload": {"source_id": source_id}})
    row = db.execute(
        "SELECT id, passage_kind FROM cmap.chunk "
        "WHERE source_id = %s AND text LIKE %s",
        (source_id, "Ilona: Morning Marco%"),
    ).fetchone()
    chunk_id, passage_kind = str(row[0]), row[1]
    assert passage_kind == "chatter"
    assert not any("Morning Marco" in text for text in fake.extract_calls)
    mentions = db.execute(
        "SELECT count(*) FROM cmap.mention WHERE chunk_id = %s",
        (chunk_id,),
    ).fetchone()[0]
    assert mentions == 0


def test_flat_fallback_matches_shape(
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """The frontier fallback yields the same mentions and label as ScaleDown.

    Both paths run over the same chunk text; the ScaleDown path replays
    ``transcript.json`` and the fallback replays ``frontier_flat.json``, whose
    entities are the same extraction in the frontier prompt's JSON shape.
    """
    text = "Marco: Jessica is the only licensing manager we have."
    fake_embeddings(monkeypatch)
    fake_scaledown(monkeypatch, "transcript.json")
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    get_settings.cache_clear()
    scaledown_source = _seed_text(db, text, "scaledown")
    handle_classify_extract({"payload": {"source_id": scaledown_source}})
    scaledown_mentions = _mentions(db, scaledown_source)

    fake_frontier(monkeypatch, "frontier_flat.json")
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "false")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "")
    get_settings.cache_clear()
    frontier_source = _seed_text(db, text, "frontier")
    handle_classify_extract({"payload": {"source_id": frontier_source}})
    frontier_mentions = _mentions(db, frontier_source)

    assert scaledown_mentions == frontier_mentions
    assert scaledown_mentions
    labels = {
        row[0]
        for row in db.execute(
            "SELECT passage_kind FROM cmap.chunk WHERE source_id IN (%s, %s)",
            (scaledown_source, frontier_source),
        ).fetchall()
    }
    assert labels == {"responsibility"}
    models = {
        row[0]
        for row in db.execute(
            "SELECT e.model FROM cmap.extraction e "
            "JOIN cmap.chunk c ON c.id = e.chunk_id WHERE c.source_id = %s",
            (frontier_source,),
        ).fetchall()
    }
    assert len(models) == 1
    assert "scaledown" not in models.pop()
