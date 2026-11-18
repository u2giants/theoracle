"""Postgres access for the brain service."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

import psycopg
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool

from brain.config import Settings, get_settings

_pool: ConnectionPool | None = None


def get_pool(settings: Settings | None = None) -> ConnectionPool:
    """Return the process-wide connection pool, creating it on first use."""
    global _pool
    if _pool is None:
        cfg = settings if settings is not None else get_settings()
        if cfg.database_url is None:
            raise RuntimeError("DATABASE_URL is not set")
        pool = ConnectionPool(
            conninfo=cfg.database_url, min_size=1, max_size=10, open=True
        )
        _pool = pool
    return _pool


def check_database(settings: Settings | None = None) -> bool:
    """Return True when Postgres answers SELECT 1."""
    cfg = settings if settings is not None else get_settings()
    if cfg.database_url is None:
        return False
    try:
        with psycopg.connect(cfg.database_url, connect_timeout=3) as conn:
            conn.execute("SELECT 1")
    except Exception:
        return False
    return True


def run_sql(path: str | Path, settings: Settings | None = None) -> None:
    """Execute one SQL file against the database (used by migrations)."""
    cfg = settings if settings is not None else get_settings()
    sql = Path(path).read_text(encoding="utf-8")
    pool = get_pool(cfg)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


# Interview fast lane (issue #604). A job inherits the lane of the code that
# queues it, but only the kinds that process one interview answer may enter
# the interview lane; global rebuilds (resolve, project, communities, ...)
# always go to the main lane.
MAIN_LANE = "main"
INTERVIEW_LANE = "interview"
LANE_KINDS = frozenset(
    {"read_source", "classify_extract", "relations", "interview_reply"}
)
current_lane: ContextVar[str] = ContextVar("current_lane", default=MAIN_LANE)


def lane_for(kind: str, lane: str | None = None) -> str:
    """The lane a job of ``kind`` goes to: explicit, else inherited, else main."""
    chosen = lane or current_lane.get()
    return chosen if kind in LANE_KINDS else MAIN_LANE


def enqueue_job(
    kind: str,
    payload: dict,
    settings: Settings | None = None,
    lane: str | None = None,
) -> str:
    """Insert one queued job and return its id."""
    pool = get_pool(settings)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cmap.job (kind, payload, lane) VALUES (%s, %s, %s) RETURNING id",
                (kind, Json(payload), lane_for(kind, lane)),
            )
            row = cur.fetchone()
        conn.commit()
    return str(row[0])
