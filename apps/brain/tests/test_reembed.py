"""Reembed after an embeddings seat change (#359 findings 3 and 5)."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import fake_embeddings
from psycopg.types.json import Json

from brain import embed as embed_mod
from brain import reembed as reembed_mod
from brain.config import get_settings
from brain.reembed import handle_reembed, run_reembed


def _seed(db: Any, chunks: int = 5) -> dict[str, str]:
    src = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
        "VALUES ('text', 't', 'k', 'h', 1) RETURNING id"
    ).fetchone()[0]
    ids: dict[str, str] = {}
    for n in range(chunks):
        cid = db.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
            "VALUES (%s, %s, '{}', %s, 1) RETURNING id",
            (src, n, f"chunk text {n}"),
        ).fetchone()[0]
        ids[f"chunk{n}"] = str(cid)
    described = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name, description, described_at_count) "
        "VALUES ('Org', 'Acme', 'a toy maker', 3) RETURNING id"
    ).fetchone()[0]
    plain = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name, description) "
        "VALUES ('Person', 'Ilona', 'runs licensing') RETURNING id"
    ).fetchone()[0]
    db.execute(
        "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, normalized_name, quote, "
        "entity_id) VALUES (%s, 'Person', 'Ilona', 'ilona', 'Ilona signs off', %s)",
        (ids["chunk0"], plain),
    )
    db.commit()
    return {**ids, "described": str(described), "plain": str(plain)}


def test_reembed_uses_each_stage_text_and_copies_undescribed_entities(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 3: an undescribed entity keeps its seed mention's vector, not name — description."""
    ids = _seed(db, chunks=1)
    calls = fake_embeddings(monkeypatch)
    stats = run_reembed(get_settings())
    texts = [text for batch in calls for text in batch]
    assert "Acme — a toy maker" in texts
    assert "Ilona — Ilona signs off" in texts  # the mention text
    assert not any(text.startswith("Ilona — runs licensing") for text in texts)
    assert stats["entity"] == 1 and stats["entity_copied"] == 1
    mention_vec, entity_vec = db.execute(
        "SELECT m.embedding::text, e.embedding::text FROM cmap.mention m "
        "JOIN cmap.entity e ON e.id = m.entity_id WHERE e.id = %s",
        (ids["plain"],),
    ).fetchone()
    assert entity_vec == mention_vec


def test_reembed_reads_in_batches(db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 5: keyset batches, never the whole table in one fetch."""
    _seed(db, chunks=5)
    monkeypatch.setattr(reembed_mod, "EMBED_BATCH", 2)
    calls = fake_embeddings(monkeypatch)
    stats = run_reembed(get_settings())
    assert stats["chunk"] == 5
    assert [len(batch) for batch in calls][:3] == [2, 2, 1]


def test_failed_reembed_requeues_and_resumes_from_cursor(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 5: a mid-run failure queues a resume at the saved cursor."""
    _seed(db, chunks=5)
    monkeypatch.setattr(reembed_mod, "EMBED_BATCH", 2)
    calls = fake_embeddings(monkeypatch)
    real = embed_mod._post_embeddings
    state = {"n": 0}

    def flaky(texts: list[str], settings: Any) -> Any:
        state["n"] += 1
        if state["n"] == 2:
            raise RuntimeError("provider blip")
        return real(texts, settings)

    monkeypatch.setattr(embed_mod, "_post_embeddings", flaky)
    seated = get_settings().brain_embed_model
    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload) VALUES ('reembed', %s) RETURNING id",
        (Json({"model": seated}),),
    ).fetchone()[0]
    db.commit()
    with pytest.raises(RuntimeError):
        handle_reembed({"id": job_id, "kind": "reembed", "payload": {"model": seated}})
    retry = db.execute(
        "SELECT id, payload FROM cmap.job WHERE id <> %s AND kind = 'reembed'",
        (job_id,),
    ).fetchone()
    assert retry is not None
    retry_id, payload = retry
    assert payload["attempt"] == 2
    assert payload["cursor"]["table"] == "chunk"
    first_batch = calls[0]

    calls.clear()
    handle_reembed({"id": retry_id, "kind": "reembed", "payload": payload})
    resumed = [text for batch in calls for text in batch]
    assert not set(first_batch) & set(resumed)  # resumed after the cursor
    assert sum(1 for text in resumed if text.startswith("chunk text")) == 3
    stats = db.execute(
        "SELECT payload->'stats' FROM cmap.job WHERE id = %s", (retry_id,)
    ).fetchone()[0]
    assert stats["chunk"] == 3


def test_superseded_reembed_job_is_skipped(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 5: the payload model must match the seat."""
    _seed(db, chunks=1)
    calls = fake_embeddings(monkeypatch)
    job_id = db.execute(
        "INSERT INTO cmap.job (kind, payload) VALUES ('reembed', %s) RETURNING id",
        (Json({"model": "old/model"}),),
    ).fetchone()[0]
    db.commit()
    handle_reembed({"id": job_id, "kind": "reembed", "payload": {"model": "old/model"}})
    assert calls == []
