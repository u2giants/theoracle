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
    # Synthetic fixture dates (D1): the transcript fixture is the
    # teams-approval-2026-03-14 meeting; the document fixtures carry a
    # document-text date. Real origins are proven in tests/test_dates.py.
    fixture_date, fixture_origin = (
        ("2026-03-14", "meeting_start") if kind == "transcript" else ("2025-12-01", "document_text")
    )
    row = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes, "
        "effective_date, date_origin) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            kind,
            f"flat-test {filename}",
            f"test/{filename}",
            hashlib.sha256(data).hexdigest(),
            len(data),
            fixture_date,
            fixture_origin,
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


def test_frontier_prompt_uses_classify_rubrics() -> None:
    """Both classify paths read the same rubric text (review finding #339)."""
    from brain.extract.flat import CLASSIFY_LABELS, load_flat_prompt

    prompt = load_flat_prompt()
    assert "{{classify_labels}}" not in prompt
    assert "{{chunk_text}}" in prompt
    for label in CLASSIFY_LABELS:
        assert f"- {label['name']}: {label['rubric']}" in prompt


def test_one_bad_chunk_does_not_lose_the_source(
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """Repair A2: one failed model call costs one passage, not the source.

    The model fails for one passage on every try. The other passage's
    mentions are stored, the bad one is recorded with its error, the chain
    continues, and the source ends ``partial`` — never ``read``. When the
    model recovers, a retry reads the missing passage and the source is
    ``read``.
    """
    from conftest import fake_relations

    from brain.extract import flat as flat_mod
    from brain.extract.relations import handle_relations
    from brain.read import state as state_mod

    monkeypatch.setattr(state_mod, "BACKOFF_SECONDS", 0.0)
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "false")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    good_calls = fake_frontier(monkeypatch, "frontier_flat.json")
    good = flat_mod._post_chat
    broken = {"on": True}
    bad_tries: list[int] = []

    def _post_chat(messages: list[dict[str, Any]], settings: Any) -> dict[str, Any]:
        if broken["on"] and "POISON" in str(messages[-1]["content"]):
            bad_tries.append(1)
            raise flat_mod.FlatError("provider returned 502")
        return good(messages, settings)

    monkeypatch.setattr(flat_mod, "_post_chat", _post_chat)
    source_id = _seed_text(
        db, "Marco: Jessica is the only licensing manager we have.", "bad-chunk"
    )
    db.execute(
        "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, 1, '{}', 'POISON Marco: Jessica is the only licensing manager we have.', 12)",
        (source_id,),
    )
    db.execute(
        "UPDATE cmap.source SET read_state = 'extracting' WHERE id = %s", (source_id,)
    )
    db.commit()
    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload, state) VALUES ('classify_extract', %s, 'running') "
        "RETURNING id",
        (Json({"source_id": source_id}),),
    ).fetchone()[0]
    db.commit()

    handle_classify_extract({"id": job_id, "payload": {"source_id": source_id}})

    assert len(bad_tries) == 3, "the failing passage is retried three times"
    assert _mentions(db, source_id), "the good passage's mentions are kept"
    errors = db.execute(
        "SELECT c.ordinal, e.error FROM cmap.extraction e "
        "JOIN cmap.chunk c ON c.id = e.chunk_id "
        "WHERE c.source_id = %s AND e.error IS NOT NULL",
        (source_id,),
    ).fetchall()
    assert [(ordinal, "502" in error) for ordinal, error in errors] == [(1, True)]
    assert (
        db.execute(
            "SELECT count(*) FROM cmap.job WHERE kind = 'relations' AND state = 'queued'"
        ).fetchone()[0]
        == 1
    ), "the chain continues"

    fake_relations(monkeypatch)
    handle_relations({"payload": {"source_id": source_id}})
    state, error = db.execute(
        "SELECT read_state, read_error FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    assert state == "partial"
    assert error.startswith("1 of 2 passages")

    # The model recovers: a retry reads only the missing passage.
    broken["on"] = False
    before = len(good_calls)
    handle_classify_extract({"payload": {"source_id": source_id}})
    assert len(good_calls) == before + 1
    handle_relations({"payload": {"source_id": source_id}})
    state, error = db.execute(
        "SELECT read_state, read_error FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    assert (state, error) == ("read", None)
    get_settings.cache_clear()


def test_prompt_change_replaces_not_duplicates(
    monkeypatch: pytest.MonkeyPatch,
    db: Any,
) -> None:
    """Repair A8: re-extracting after a prompt change replaces the chunk's
    mentions and relations instead of adding a second copy."""
    from conftest import fake_relations

    from brain.extract import flat as flat_mod
    from brain.extract import relations as relations_mod
    from brain.extract.relations import handle_relations

    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "false")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    get_settings.cache_clear()
    fake_embeddings(monkeypatch)
    fake_frontier(monkeypatch, "frontier_flat.json")
    rel = fake_relations(monkeypatch)
    source_id = _seed_text(
        db, "Marco: Jessica is the only licensing manager we have.", "prompt-change"
    )

    def _counts() -> tuple[int, int, int, int]:
        db.commit()
        row = db.execute(
            "SELECT (SELECT count(*) FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id "
            "        WHERE c.source_id = %(s)s), "
            "(SELECT count(*) FROM cmap.relation r JOIN cmap.chunk c ON c.id = r.chunk_id "
            "        WHERE c.source_id = %(s)s), "
            "(SELECT count(*) FROM cmap.extraction e JOIN cmap.chunk c ON c.id = e.chunk_id "
            "        WHERE c.source_id = %(s)s AND e.stage = 'flat'), "
            "(SELECT count(*) FROM cmap.extraction e JOIN cmap.chunk c ON c.id = e.chunk_id "
            "        WHERE c.source_id = %(s)s AND e.stage = 'relations')",
            {"s": source_id},
        ).fetchone()
        return int(row[0]), int(row[1]), int(row[2]), int(row[3])

    def _run() -> None:
        handle_classify_extract({"payload": {"source_id": source_id}})
        mentions = [
            name
            for _type, name, _norm, _quote in _mentions(db, source_id)
        ]
        first, second = sorted(set(mentions))[:2]
        rel.override = {
            "relations": [
                {
                    "from": "m1",
                    "to": "m2",
                    "type": "DEPENDS_ON",
                    "description": f"{first} relates to {second}",
                    "stance": "report",
                    "confidence": 0.8,
                    "quote": "Jessica is the only licensing manager we have",
                }
            ]
        }
        handle_relations({"payload": {"source_id": source_id}})

    _run()
    first = _counts()
    assert first[0] >= 2 and first[1] == 1 and first[2] == 1 and first[3] == 1

    # Same prompts: nothing is extracted again.
    _run()
    assert _counts() == first

    # The flat prompt changes: the chunk is extracted again and replaced.
    monkeypatch.setattr(flat_mod, "frontier_prompt_hash", lambda: "new-flat-prompt")
    _run()
    assert _counts() == first

    # The relations prompt changes: its relations are replaced.
    monkeypatch.setattr(relations_mod, "relations_prompt_hash", lambda: "new-relations-prompt")
    _run()
    assert _counts() == first
    get_settings.cache_clear()
