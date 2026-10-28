"""Chunk embeddings via the OpenRouter embeddings endpoint (plan step 3).

Batches of 64 chunk texts per call; every vector is written to
``cmap.chunk.embedding``. The model id comes from ``BRAIN_EMBED_MODEL`` and
never from this code (plan §8).
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx

from brain.config import Settings, get_settings
from brain.db import get_pool

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
EMBED_BATCH = 64


class EmbedError(RuntimeError):
    """Raised when the embeddings endpoint cannot embed a batch."""


def _vector_literal(vector: Sequence[float]) -> str:
    """Return the pgvector text form of one embedding."""
    return "[" + ",".join(f"{value:.8g}" for value in vector) + "]"


def _post_embeddings(
    texts: list[str],
    settings: Settings,
) -> tuple[list[list[float]], dict[str, int]]:
    """POST one embeddings batch and return vectors plus token usage."""
    if settings.openrouter_api_key is None:
        raise EmbedError("OPENROUTER_API_KEY is not set")
    if settings.brain_embed_model is None:
        raise EmbedError("BRAIN_EMBED_MODEL is not set")
    response = httpx.post(
        f"{OPENROUTER_BASE_URL}/embeddings",
        headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
        json={"model": settings.brain_embed_model, "input": texts},
        timeout=120.0,
    )
    if response.status_code != 200:
        raise EmbedError(
            f"embeddings call failed: {response.status_code} {response.text[:200]}"
        )
    body = response.json()
    data = body.get("data")
    if not isinstance(data, list) or len(data) != len(texts):
        raise EmbedError("embeddings response does not cover every input")
    ordered = sorted(data, key=lambda item: item.get("index", 0))
    vectors: list[list[float]] = []
    for item in ordered:
        vector = item.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise EmbedError("embeddings response item has no vector")
        vectors.append([float(value) for value in vector])
    reported = body.get("usage") or {}
    tokens = reported.get("total_tokens")
    usage: dict[str, int] = {}
    if isinstance(tokens, int):
        usage["embedding_tokens"] = tokens
    return vectors, usage


def embed_texts(
    texts: Sequence[str],
    settings: Settings | None = None,
    usage: dict[str, int] | None = None,
) -> list[list[float]]:
    """Embed every text, 64 per API call, in order."""
    cfg = settings if settings is not None else get_settings()
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = list(texts[start : start + EMBED_BATCH])
        batch_vectors, batch_usage = _post_embeddings(batch, cfg)
        dims = cfg.brain_embed_dims
        for vector in batch_vectors:
            if len(vector) != dims:
                raise EmbedError(
                    f"embedding has {len(vector)} dimensions, expected {dims}"
                )
        vectors.extend(batch_vectors)
        if usage is not None:
            usage["embedding_batches"] = usage.get("embedding_batches", 0) + 1
            for key, value in batch_usage.items():
                usage[key] = usage.get(key, 0) + value
    return vectors


def embed_and_store(
    chunks: Sequence[tuple[str, str]],
    settings: Settings | None = None,
    usage: dict[str, int] | None = None,
) -> None:
    """Embed ``(chunk_id, text)`` pairs and write ``cmap.chunk.embedding``."""
    if not chunks:
        return
    cfg = settings if settings is not None else get_settings()
    vectors = embed_texts([text for _, text in chunks], cfg, usage)
    pool = get_pool()
    with pool.connection() as conn:
        for (chunk_id, _), vector in zip(chunks, vectors, strict=True):
            conn.execute(
                "UPDATE cmap.chunk SET embedding = %s::vector WHERE id = %s",
                (_vector_literal(vector), chunk_id),
            )
        conn.commit()
