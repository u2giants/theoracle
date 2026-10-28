"""Embedding batches land in ``cmap.chunk.embedding`` (plan step 3)."""

from __future__ import annotations

import pytest
from conftest import fake_embeddings

from brain.embed import EMBED_BATCH, EmbedError, embed_and_store, embed_texts


def test_embed_batches_64_per_call(monkeypatch) -> None:
    """Embedding sends at most 64 texts per API call, in order."""
    calls = fake_embeddings(monkeypatch)
    texts = [f"chunk number {index}" for index in range(130)]
    vectors = embed_texts(texts)
    assert [len(batch) for batch in calls] == [64, 64, 2]
    assert [batch[0] for batch in calls] == [texts[0], texts[64], texts[128]]
    assert len(vectors) == 130
    assert all(len(vector) == 1024 for vector in vectors)


def test_embed_and_store_writes_vector(monkeypatch, db) -> None:
    """embed_and_store writes a 1024-dimension pgvector for every chunk."""
    fake_embeddings(monkeypatch)
    source_id = db.execute(
        "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
        "VALUES ('text', 'embed test', 'cmap/embed-test/a.txt', 'sha-embed', 10) "
        "RETURNING id::text"
    ).fetchone()[0]
    chunk_id = db.execute(
        "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, 0, '{}'::jsonb, 'the buyer waits on sign-off', 5) "
        "RETURNING id::text",
        (source_id,),
    ).fetchone()[0]
    db.commit()

    embed_and_store([(chunk_id, "the buyer waits on sign-off")])

    row = db.execute(
        "SELECT vector_dims(embedding), embedding::text FROM cmap.chunk WHERE id = %s",
        (chunk_id,),
    ).fetchone()
    assert row[0] == 1024
    assert row[1].startswith("[")


def test_embed_rejects_wrong_dims(monkeypatch) -> None:
    """A provider returning the wrong dimension count is an error."""
    from brain import embed as embed_mod

    def _post_embeddings(texts, settings):
        del settings
        return [[0.0] for _ in texts], {}

    monkeypatch.setattr(embed_mod, "_post_embeddings", _post_embeddings)
    with pytest.raises(EmbedError):
        embed_texts(["one chunk"])


def test_embed_batch_constant() -> None:
    """The plan's 64-chunks-per-call batch is what the code uses."""
    assert EMBED_BATCH == 64
