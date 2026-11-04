"""Re-embed every stored vector after the embeddings seat changes.

Vectors from two embedding models live in different spaces, so retrieval,
dedupe and the resolve cosine bands are only meaningful when every chunk,
mention and entity vector comes from the seated model. The texts match what
each stage embedded originally:

- a chunk: its text;
- a mention: ``surface — quote`` (relations and flat extraction);
- a described entity (``described_at_count`` set): ``name — description``,
  as ``_describe`` writes it;
- an entity never described: the vector of one of its mentions, as
  ``_create_entity`` seeds it. No embedding call is spent on these.

Rows are read in keyset batches (never the whole corpus at once). After each
batch the job payload records a cursor, so a failed run is requeued once per
attempt (up to ``MAX_ATTEMPTS``) and resumes where it stopped instead of
starting over. A job whose ``model`` no longer matches the seat is skipped: a
newer reembed job for the newer seat is already queued.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from psycopg.types.json import Json

from brain.config import Settings, get_settings
from brain.db import get_pool
from brain.embed import EMBED_BATCH, embed_texts, vector_literal
from brain.seats import stage_model

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3
NIL_ID = "00000000-0000-0000-0000-000000000000"

# (table, keyset select) — each select takes (after_id, limit) and returns
# (id, text) ordered by id.
TABLES = (
    (
        "chunk",
        "SELECT id::text, text FROM cmap.chunk WHERE text <> '' AND id > %s::uuid "
        "ORDER BY id LIMIT %s",
    ),
    (
        "mention",
        "SELECT id::text, surface_name || ' — ' || COALESCE(quote, '') "
        "FROM cmap.mention WHERE id > %s::uuid ORDER BY id LIMIT %s",
    ),
    (
        "entity",
        "SELECT id::text, canonical_name || ' — ' || COALESCE(description, '') "
        "FROM cmap.entity WHERE described_at_count IS NOT NULL AND id > %s::uuid "
        "ORDER BY id LIMIT %s",
    ),
)

# Undescribed entities carry their seed mention's vector; mentions are already
# re-embedded by the time this runs.
COPY_UNDESCRIBED = """
UPDATE cmap.entity e SET embedding = m.embedding
FROM (
  SELECT DISTINCT ON (m.entity_id) m.entity_id, m.embedding
  FROM cmap.mention m JOIN cmap.chunk c ON c.id = m.chunk_id
  WHERE m.entity_id IS NOT NULL
  ORDER BY m.entity_id, c.source_id, c.ordinal, m.id
) m
WHERE e.id = m.entity_id AND e.described_at_count IS NULL
"""

Cursor = dict[str, str]


def run_reembed(
    settings: Settings | None = None,
    cursor: Cursor | None = None,
    save_cursor: Any = None,
) -> dict[str, int]:
    """Rewrite every embedding with the seated model; return counts and usage.

    ``cursor`` (``{"table": ..., "after": id}``) resumes a stopped run;
    ``save_cursor(cursor)`` is called after every committed batch.
    """
    cfg = settings if settings is not None else get_settings()
    usage: dict[str, int] = {}
    counts: dict[str, int] = {}
    pool = get_pool()
    names = [table for table, _ in TABLES]
    start_index = (
        names.index(cursor["table"]) if cursor and cursor.get("table") in names else 0
    )
    for index, (table, select) in enumerate(TABLES):
        if index < start_index:
            continue
        after = cursor["after"] if cursor and index == start_index else NIL_ID
        done = 0
        while True:
            with pool.connection() as conn:
                rows = conn.execute(select, (after, EMBED_BATCH)).fetchall()
            if not rows:
                break
            vectors = embed_texts([str(row[1]) for row in rows], cfg, usage)
            with pool.connection() as conn:
                for (row_id, _text), vector in zip(rows, vectors, strict=True):
                    conn.execute(
                        f"UPDATE cmap.{table} SET embedding = %s::vector WHERE id = %s",
                        (vector_literal(vector), row_id),
                    )
                conn.commit()
            after = str(rows[-1][0])
            done += len(rows)
            if save_cursor is not None:
                save_cursor({"table": table, "after": after})
        counts[table] = done
        logger.info("reembed: %s %d rows", table, done)
    with pool.connection() as conn:
        copied = conn.execute(COPY_UNDESCRIBED).rowcount
        conn.commit()
    counts["entity_copied"] = max(copied, 0)
    return {**counts, **usage}


def _merge_payload(job_id: Any, extra: dict[str, Any]) -> None:
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.job SET payload = payload || %s::jsonb WHERE id = %s",
            (json.dumps(extra), job_id),
        )
        conn.commit()


def handle_reembed(job: dict[str, Any]) -> None:
    """Worker entry point for a ``reembed`` job; resumes and requeues on failure."""
    payload = dict(job.get("payload") or {})
    settings = get_settings()
    seated = stage_model(settings, "embed")
    wanted = payload.get("model")
    if wanted is not None and wanted != seated:
        logger.info(
            "reembed: job for %s superseded by seat %s; skipped", wanted, seated
        )
        _merge_payload(job["id"], {"skipped": f"seat is now {seated}"})
        return
    cursor: Cursor | None = payload.get("cursor")

    def save(next_cursor: Cursor) -> None:
        nonlocal cursor
        cursor = next_cursor
        _merge_payload(job["id"], {"cursor": next_cursor})

    try:
        stats = run_reembed(settings, cursor, save)
    except Exception:
        attempt = int(payload.get("attempt") or 1)
        if attempt < MAX_ATTEMPTS:
            retry = {**payload, "attempt": attempt + 1, "cursor": cursor}
            retry.pop("stats", None)
            with get_pool().connection() as conn:
                conn.execute(
                    "INSERT INTO cmap.job (kind, payload) VALUES ('reembed', %s)",
                    (Json(retry),),
                )
                conn.commit()
            logger.warning(
                "reembed: attempt %d failed; resume queued at %s", attempt, cursor
            )
        raise
    _merge_payload(job["id"], {"stats": stats})
