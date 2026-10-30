"""Background job loop over ``cmap.job``."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from brain.db import get_pool
from brain.eval.run import handle_evaluate
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.graph.communities import handle_communities
from brain.graph.project import handle_project
from brain.interview.tick import handle_interview_tick, maybe_queue_interview_tick
from brain.read.pipeline import handle_read_source
from brain.resolve.resolve import handle_resolve

logger = logging.getLogger(__name__)

POLL_SECONDS = 2.0
SCHEDULE_CHECK_SECONDS = 60.0

Handler = Callable[[dict[str, Any]], None]

HANDLERS: dict[str, Handler] = {
    "read_source": handle_read_source,
    "classify_extract": handle_classify_extract,
    "relations": handle_relations,
    "resolve": handle_resolve,
    "project": handle_project,
    "communities": handle_communities,
    "evaluate": handle_evaluate,
    "interview_tick": handle_interview_tick,
}


def claim_next_job() -> dict[str, Any] | None:
    """Take the oldest queued job, or None when the queue is empty."""
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, kind, payload FROM cmap.job "
                "WHERE state = 'queued' "
                "ORDER BY created_at "
                "FOR UPDATE SKIP LOCKED "
                "LIMIT 1"
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                return None
            job_id, kind, payload = row
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
    }
    return job


def run_handler(job: dict[str, Any]) -> None:
    """Run the handler registered for this job kind."""
    handler = HANDLERS.get(job["kind"])
    if handler is None:
        raise ValueError(f"no handler for job kind {job['kind']!r}")
    handler(job)


def finish_job(job_id: Any, error: str | None) -> None:
    """Mark a job done, or failed with its error text."""
    state = "failed"
    if error is None:
        state = "done"
    pool = get_pool()
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cmap.job SET state = %s, error = %s, finished_at = now() WHERE id = %s",
                (state, error, job_id),
            )
        conn.commit()


def run_worker(stop: threading.Event) -> None:
    """Claim, run and record jobs until ``stop`` is set; sleep 2 s when idle.

    About once a minute it also queues the hourly ``interview_tick`` (a no-op
    while ``BRAIN_INTERVIEW_ENABLED`` is false).
    """
    last_schedule_check = 0.0
    while not stop.is_set():
        now = time.monotonic()
        if now - last_schedule_check >= SCHEDULE_CHECK_SECONDS:
            last_schedule_check = now
            try:
                maybe_queue_interview_tick()
            except Exception as exc:
                logger.warning("interview tick scheduling failed: %s", exc)
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
        try:
            finish_job(job["id"], error)
        except Exception as exc:
            logger.warning("could not record job %s result: %s", job["id"], exc)
