"""Chain healing: the hourly ``ensure_chain`` job (repair plan A2).

The pipeline is a chain of jobs, each queued by the one before it. When a
job is lost or fails for good the chain used to stop until another upload
restarted it. This job looks for work left behind and queues the missing
step:

* a source still ``queued``/``reading`` with no ``read_source`` job;
* a source still ``extracting`` with no extraction job — re-queued, or
  marked ``failed`` with the error when its last job failed for good;
* unresolved mentions with no ``resolve`` job;
* a finished ``resolve`` newer than the last projection;
* a finished ``resolve`` newer than the last function assignment (repair C2);
* a finished projection newer than the last summary build.

A step whose job failed for good in the last few hours is left alone, so a
permanent fault is retried a few times a day, not every hour.
"""

from __future__ import annotations

import logging
from typing import Any

from brain.db import get_pool
from brain.read.state import set_read_state

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 3600
STALE_READ_SECONDS = 600
FAILED_COOLDOWN_SECONDS = 6 * 3600

_ACTIVE = "state IN ('queued', 'running')"


def maybe_queue_ensure_chain() -> bool:
    """Queue one ``ensure_chain`` when none was queued in the last hour."""
    with get_pool().connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'ensure_chain', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'ensure_chain' "
            "AND created_at > now() - make_interval(secs => %s)) RETURNING id",
            (INTERVAL_SECONDS,),
        ).fetchone()
        conn.commit()
    return row is not None


def _queue(conn: Any, kind: str, payload: str = "{}") -> None:
    conn.execute(
        "INSERT INTO cmap.job (kind, payload) VALUES (%s, %s::jsonb)", (kind, payload)
    )


def _recently_failed(conn: Any, kind: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM cmap.job WHERE kind = %s AND state = 'failed' "
        "AND finished_at > now() - make_interval(secs => %s) LIMIT 1",
        (kind, FAILED_COOLDOWN_SECONDS),
    ).fetchone()
    return row is not None


def _active(conn: Any, kind: str) -> bool:
    row = conn.execute(
        f"SELECT 1 FROM cmap.job WHERE kind = %s AND {_ACTIVE} LIMIT 1", (kind,)
    ).fetchone()
    return row is not None


def _heal_sources(conn: Any, stats: dict[str, int]) -> None:
    unread = conn.execute(
        "SELECT s.id::text FROM cmap.source s "
        "WHERE s.read_state IN ('queued', 'reading') "
        "AND s.created_at < now() - make_interval(secs => %s) "
        "AND NOT EXISTS (SELECT 1 FROM cmap.job j WHERE j.kind = 'read_source' "
        f"  AND j.payload->>'source_id' = s.id::text AND j.{_ACTIVE} ) "
        "AND NOT EXISTS (SELECT 1 FROM cmap.job j WHERE j.kind = 'read_source' "
        "  AND j.payload->>'source_id' = s.id::text AND j.state = 'failed' "
        "  AND j.finished_at > now() - make_interval(secs => %s))",
        (STALE_READ_SECONDS, FAILED_COOLDOWN_SECONDS),
    ).fetchall()
    for (source_id,) in unread:
        conn.execute(
            "INSERT INTO cmap.job (kind, payload) "
            "VALUES ('read_source', jsonb_build_object('source_id', %s::text))",
            (source_id,),
        )
        stats["read_source"] += 1
    stalled = conn.execute(
        "SELECT s.id::text, "
        "(SELECT j.state || '|' || COALESCE(j.error, '') FROM cmap.job j "
        "  WHERE j.kind IN ('classify_extract', 'relations') "
        "  AND j.payload->>'source_id' = s.id::text "
        "  ORDER BY j.created_at DESC LIMIT 1) "
        "FROM cmap.source s WHERE s.read_state = 'extracting' "
        "AND NOT EXISTS (SELECT 1 FROM cmap.job j "
        "  WHERE j.kind IN ('classify_extract', 'relations') "
        f"  AND j.payload->>'source_id' = s.id::text AND j.{_ACTIVE})"
    ).fetchall()
    conn.commit()
    for source_id, last in stalled:
        state, _, error = str(last or "").partition("|")
        if state == "failed":
            # Its retries are spent: say so instead of looping for ever. An
            # admin retry (re-read) starts it again.
            set_read_state(source_id, "failed", error or "extraction failed")
            stats["marked_failed"] += 1
            continue
        conn.execute(
            "INSERT INTO cmap.job (kind, payload) "
            "VALUES ('classify_extract', jsonb_build_object('source_id', %s::text))",
            (source_id,),
        )
        stats["classify_extract"] += 1
    conn.commit()


def _heal_graph(conn: Any, stats: dict[str, int]) -> None:
    unresolved = conn.execute(
        "SELECT 1 FROM cmap.mention WHERE entity_id IS NULL LIMIT 1"
    ).fetchone()
    if unresolved and not _active(conn, "resolve") and not _recently_failed(conn, "resolve"):
        _queue(conn, "resolve")
        stats["resolve"] += 1
        conn.commit()
        return
    for kind, before in (
        ("project", "resolve"),
        ("function_assign", "resolve"),
        ("communities", "project"),
    ):
        behind = conn.execute(
            "SELECT (SELECT max(finished_at) FROM cmap.job WHERE kind = %s AND state = 'done') "
            "> COALESCE((SELECT max(started_at) FROM cmap.job "
            "            WHERE kind = %s AND state = 'done'), '-infinity'::timestamptz)",
            (before, kind),
        ).fetchone()[0]
        if not behind:
            continue
        if _active(conn, kind) or _active(conn, before) or _recently_failed(conn, kind):
            continue
        _queue(conn, kind)
        stats[kind] += 1
        conn.commit()
        return


def run_ensure_chain() -> dict[str, int]:
    """Queue whatever step of the chain was left behind; return the counts."""
    stats = {
        "read_source": 0,
        "classify_extract": 0,
        "marked_failed": 0,
        "resolve": 0,
        "project": 0,
        "function_assign": 0,
        "communities": 0,
    }
    with get_pool().connection() as conn:
        _heal_sources(conn, stats)
        _heal_graph(conn, stats)
        conn.commit()
    return stats


def handle_ensure_chain(job: dict[str, Any]) -> None:
    """Job ``ensure_chain``: heal a stalled pipeline."""
    del job
    stats = run_ensure_chain()
    if any(stats.values()):
        logger.warning("ensure_chain healed stalled work: %s", stats)
