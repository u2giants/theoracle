"""Postgres access for the brain service."""

from __future__ import annotations

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
        pool = ConnectionPool(conninfo=cfg.database_url, min_size=1, max_size=5, open=True)
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


def enqueue_job(kind: str, payload: dict, settings: Settings | None = None) -> str:
    """Insert one queued job and return its id."""
    pool = get_pool(settings)
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO cmap.job (kind, payload) VALUES (%s, %s) RETURNING id",
                (kind, Json(payload)),
            )
            row = cur.fetchone()
        conn.commit()
    return str(row[0])
