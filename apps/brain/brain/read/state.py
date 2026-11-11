"""A source's reading state across the whole chain (repair plan A2).

``queued`` -> ``reading`` (read_source running) -> ``extracting`` (passages
stored, flat and relationship extraction under way) -> ``read``, or
``partial`` when some passages could not be extracted, or ``failed``.
A passage whose model call failed after its retries is recorded in
``cmap.extraction`` with ``prompt_hash = 'failed'`` and the error text, so
the loss is counted and visible instead of silent.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from brain.db import get_pool

logger = logging.getLogger(__name__)

FAILED_HASH = "failed"
MAX_ERROR_CHARS = 2000
NO_CONTENT_ERROR = "no readable content"
CHUNK_ATTEMPTS = 3
BACKOFF_SECONDS = 1.0



def with_retries[T](
    call: Callable[[], T],
    label: str,
    fatal: tuple[type[BaseException], ...] = (),
) -> T:
    """Run ``call`` up to three times with exponential backoff.

    Exceptions in ``fatal`` (the per-job call cap) are never retried.
    """
    for attempt in range(1, CHUNK_ATTEMPTS + 1):
        try:
            return call()
        except fatal:
            raise
        except Exception as exc:
            if attempt == CHUNK_ATTEMPTS:
                raise
            logger.warning("%s failed (%s); retry %d", label, exc, attempt)
            time.sleep(BACKOFF_SECONDS * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


def set_read_state(source_id: str, state: str, error: str | None) -> None:
    """Record where the source stands and, when it matters, why."""
    with get_pool().connection() as conn:
        conn.execute(
            "UPDATE cmap.source SET read_state = %s, read_error = %s WHERE id = %s",
            (state, error[:MAX_ERROR_CHARS] if error else None, source_id),
        )
        conn.commit()


def record_chunk_failure(chunk_id: str, stage: str, error: str) -> None:
    """Note that this passage's extraction failed after its retries."""
    with get_pool().connection() as conn:
        conn.execute(
            "INSERT INTO cmap.extraction (chunk_id, stage, prompt_hash, model, payload, error) "
            "VALUES (%s, %s, %s, '-', '{}'::jsonb, %s) "
            "ON CONFLICT (chunk_id, stage, prompt_hash) DO UPDATE "
            "SET error = EXCLUDED.error, created_at = now()",
            (chunk_id, stage, FAILED_HASH, error[:MAX_ERROR_CHARS]),
        )
        conn.commit()


def clear_chunk_failure(conn: Any, chunk_id: str, stage: str) -> None:
    """Forget an earlier failure once the passage has been extracted."""
    conn.execute(
        "DELETE FROM cmap.extraction WHERE chunk_id = %s AND stage = %s AND prompt_hash = %s",
        (chunk_id, stage, FAILED_HASH),
    )


def failed_chunk_count(conn: Any, source_id: str) -> tuple[int, int]:
    """``(passages with a recorded failure, passages)`` for one source."""
    row = conn.execute(
        "SELECT count(DISTINCT e.chunk_id), "
        "(SELECT count(*) FROM cmap.chunk WHERE source_id = %s) "
        "FROM cmap.extraction e JOIN cmap.chunk c ON c.id = e.chunk_id "
        "WHERE c.source_id = %s AND e.error IS NOT NULL",
        (source_id, source_id),
    ).fetchone()
    return int(row[0]), int(row[1])


def finish_source(source_id: str) -> str:
    """Set the final state after relationship extraction; return it."""
    with get_pool().connection() as conn:
        failed, total = failed_chunk_count(conn, source_id)
    if total == 0:
        set_read_state(source_id, "failed", NO_CONTENT_ERROR)
        return "failed"
    if failed:
        set_read_state(
            source_id,
            "partial",
            f"{failed} of {total} passages could not be read; retry to try them again",
        )
        return "partial"
    set_read_state(source_id, "read", None)
    return "read"
