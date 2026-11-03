"""Re-embed every stored vector after the embeddings seat changes.

Vectors from two embedding models live in different spaces, so retrieval,
dedupe and the resolve cosine bands are only meaningful when every chunk,
mention and entity vector comes from the seated model. The texts match what
each stage embedded originally: the chunk text, ``surface — quote`` for a
mention, and ``name — description`` for an entity.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from brain.config import get_settings
from brain.db import get_pool
from brain.embed import EMBED_BATCH, embed_texts, vector_literal

logger = logging.getLogger(__name__)

TABLES = (
    ("chunk", "SELECT id::text, text FROM cmap.chunk WHERE text <> '' ORDER BY id"),
    (
        "mention",
        "SELECT id::text, surface_name || ' — ' || COALESCE(quote, '') "
        "FROM cmap.mention ORDER BY id",
    ),
    (
        "entity",
        "SELECT id::text, canonical_name || ' — ' || COALESCE(description, '') "
        "FROM cmap.entity ORDER BY id",
    ),
)


def run_reembed() -> dict[str, int]:
    """Rewrite every embedding with the seated model; return counts and usage."""
    settings = get_settings()
    usage: dict[str, int] = {}
    counts: dict[str, int] = {}
    pool = get_pool()
    for table, select in TABLES:
        with pool.connection() as conn:
            rows = conn.execute(select).fetchall()
        for start in range(0, len(rows), EMBED_BATCH):
            batch = rows[start : start + EMBED_BATCH]
            vectors = embed_texts([str(row[1]) for row in batch], settings, usage)
            with pool.connection() as conn:
                for (row_id, _text), vector in zip(batch, vectors, strict=True):
                    conn.execute(
                        f"UPDATE cmap.{table} SET embedding = %s::vector WHERE id = %s",
                        (vector_literal(vector), row_id),
                    )
                conn.commit()
        counts[table] = len(rows)
        logger.info("reembed: %s %d rows", table, len(rows))
    return {**counts, **usage}


def handle_reembed(job: dict[str, Any]) -> None:
    """Worker entry point for a ``reembed`` job."""
    stats = run_reembed()
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.job SET payload = payload || jsonb_build_object('stats', %s::jsonb) "
            "WHERE id = %s",
            (json.dumps(stats), job["id"]),
        )
        conn.commit()
