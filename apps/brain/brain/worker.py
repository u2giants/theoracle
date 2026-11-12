"""Background job loop over ``cmap.job``."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from brain.chain import handle_ensure_chain, maybe_queue_ensure_chain
from brain.db import get_pool
from brain.directory_sync import handle_directory_sync, maybe_queue_directory_sync
from brain.eval.run import handle_evaluate
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.graph.communities import handle_communities
from brain.graph.project import handle_project
from brain.interview.intake import close_stale_threads
from brain.interview.tick import handle_interview_tick, maybe_queue_interview_tick
from brain.read.dates import handle_backfill_dates
from brain.read.pipeline import handle_read_source
from brain.recommend.recommend import handle_recommend
from brain.reembed import handle_reembed
from brain.resolve.resolve import handle_resolve

logger = logging.getLogger(__name__)

POLL_SECONDS = 2.0
SCHEDULE_CHECK_SECONDS = 60.0

Handler = Callable[[dict[str, Any]], None]

HANDLERS: dict[str, Handler] = {
    "read_source": handle_read_source,
    "backfill_dates": handle_backfill_dates,
    "classify_extract": handle_classify_extract,
    "relations": handle_relations,
    "resolve": handle_resolve,
    "project": handle_project,
    "communities": handle_communities,
    "recommend": handle_recommend,
    "evaluate": handle_evaluate,
    "interview_tick": handle_interview_tick,
    "reembed": handle_reembed,
    "directory_sync": handle_directory_sync,
    "ensure_chain": handle_ensure_chain,
}


def claim_next_job() -> dict[str, Any] | None:
    """Take the oldest queued job, or None when the queue is empty."""
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, kind, payload, attempts FROM cmap.job "
                "WHERE state = 'queued' AND run_after <= now() "
                "ORDER BY created_at "
                "FOR UPDATE SKIP LOCKED "
                "LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return None
            job_id, kind, payload, attempts = row
            cur.execute(
                "UPDATE cmap.job "
                "SET state = 'running', attempts = attempts + 1, started_at = now() "
                "WHERE id = %s",
                (job_id,),
            )
        conn.commit()
    job = {
        "id": job_id,
        "kind": kind,
        "payload": payload,
        "attempts": int(attempts) + 1,
    }
    return job


def run_handler(job: dict[str, Any]) -> None:
    """Run the handler registered for this job kind."""
    handler = HANDLERS.get(job["kind"])
    if handler is None:
        raise ValueError(f"no handler for job kind {job['kind']!r}")
    handler(job)


MAX_ATTEMPTS = 3
RETRY_BASE_SECONDS = 300.0


def finish_job(job_id: Any, error: str | None) -> str:
    """Mark a job done; on error retry it with backoff, then mark it failed.

    A failed job goes back to the queue until it has been tried
    ``MAX_ATTEMPTS`` times, waiting 5 minutes x 4^(tries so far - 1) first
    (5 min, then 20 min). Its error text is kept either way. Returns the
    state written.
    """
    pool = get_pool()
    with pool.connection() as conn:
        if error is None:
            conn.execute(
                "UPDATE cmap.job SET state = 'done', error = NULL, finished_at = now() "
                "WHERE id = %s",
                (job_id,),
            )
            conn.commit()
            return "done"
        row = conn.execute(
            "UPDATE cmap.job SET "
            "state = CASE WHEN attempts < %s THEN 'queued' ELSE 'failed' END, "
            "run_after = CASE WHEN attempts < %s "
            "  THEN now() + make_interval(secs => %s * power(4, GREATEST(attempts, 1) - 1)) "
            "  ELSE run_after END, "
            "started_at = CASE WHEN attempts < %s THEN NULL ELSE started_at END, "
            "finished_at = CASE WHEN attempts < %s THEN NULL ELSE now() END, "
            "error = %s WHERE id = %s RETURNING state",
            (MAX_ATTEMPTS, MAX_ATTEMPTS, RETRY_BASE_SECONDS, MAX_ATTEMPTS, MAX_ATTEMPTS, error, job_id),
        ).fetchone()
        conn.commit()
    return str(row[0]) if row else "failed"


FINISH_ATTEMPTS = 3


def record_result(job_id: Any, error: str | None) -> None:
    """Write the job's result, retrying a failed write (repair plan A7).

    If every try fails the job stays ``running`` and the orphan sweep puts it
    back on the queue at the next start.
    """
    for attempt in range(1, FINISH_ATTEMPTS + 1):
        try:
            finish_job(job_id, error)
            return
        except Exception as exc:
            logger.warning(
                "could not record job %s result (try %d): %s", job_id, attempt, exc
            )
            time.sleep(min(2.0 * attempt, 5.0))


# A restart (every deploy) kills the job in flight and leaves it 'running'
# forever. Once the previous container is certainly gone, jobs that were
# already running before this process started go back to the queue.
ORPHAN_GRACE_SECONDS = 180.0


def boot_time() -> Any:
    """The database clock now; jobs started before it belong to a dead process."""
    with get_pool().connection() as conn:
        return conn.execute("SELECT now()").fetchone()[0]


def requeue_orphans(started_before: Any) -> int:
    """Requeue jobs left 'running' by a process that no longer exists."""
    with get_pool().connection() as conn:
        rows = conn.execute(
            "UPDATE cmap.job SET state = 'queued', started_at = NULL "
            "WHERE state = 'running' AND started_at < %s RETURNING id",
            (started_before,),
        ).fetchall()
        conn.commit()
    if rows:
        logger.warning("requeued %d job(s) orphaned by a restart", len(rows))
    return len(rows)


def run_worker(stop: threading.Event) -> None:
    """Claim, run and record jobs until ``stop`` is set; sleep 2 s when idle.

    A job that raises is retried with backoff before it is marked failed.
    About once a minute it also queues the hourly ``ensure_chain`` (heals work
    left behind), queues the hourly ``interview_tick`` (a no-op
    while ``BRAIN_INTERVIEW_ENABLED`` is false), queues ``directory_sync`` when
    configured, and closes Teams intake threads quiet for 20 minutes.
    """
    last_schedule_check = 0.0
    started = time.monotonic()
    booted_at: Any = None
    orphans_swept = False
    while not stop.is_set():
        now = time.monotonic()
        if not orphans_swept:
            try:
                if booted_at is None:
                    booted_at = boot_time()
                if now - started >= ORPHAN_GRACE_SECONDS:
                    requeue_orphans(booted_at)
                    orphans_swept = True
            except Exception as exc:
                logger.warning("orphaned job sweep failed: %s", exc)
        if now - last_schedule_check >= SCHEDULE_CHECK_SECONDS:
            last_schedule_check = now
            try:
                maybe_queue_interview_tick()
            except Exception as exc:
                logger.warning("interview tick scheduling failed: %s", exc)
            try:
                maybe_queue_directory_sync()
            except Exception as exc:
                logger.warning("directory sync scheduling failed: %s", exc)
            try:
                maybe_queue_ensure_chain()
            except Exception as exc:
                logger.warning("chain healing scheduling failed: %s", exc)
            try:
                close_stale_threads()
            except Exception as exc:
                logger.warning("teams intake sweep failed: %s", exc)
        try:
            job = claim_next_job()
        except Exception as exc:
            logger.warning("job claim failed: %s", exc)
            stop.wait(POLL_SECONDS)
            continue
        if job is None:
            stop.wait(POLL_SECONDS)
            continue
        error: str | None = None
        try:
            run_handler(job)
        except Exception as exc:
            logger.exception("job %s failed", job["id"])
            error = str(exc)
        record_result(job["id"], error)
