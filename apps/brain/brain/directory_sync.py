"""DesignFlow people/roles directory sync (DECISIONS.md
D-dflow-directory-source-of-truth).

DesignFlow's ``dflow_prod`` user directory on the shared company Supabase is the
master list of company people and their DesignFlow roles. A recurring brain job
mirrors it read-only into Oracle: upsert ``public.employees`` matched by
``lower(btrim(email))`` and replace that person's ``employee_directory_roles``
rows. Oracle-only fields (``is_admin``, ``locale``, ``departments``/``department``,
``role``, identity rows, claim-review groups, ``cmap.employee_flags``) are never
written; employees are never deleted.

Gated by ``DFLOW_DIRECTORY_SYNC_ENABLED`` and ``DFLOW_DIRECTORY_DATABASE_URL``;
a missing flag or URL is a logged no-op. Runnable one-shot as
``python -m brain.directory_sync``.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

import psycopg
from psycopg.rows import dict_row

from brain.config import Settings, get_settings
from brain.db import get_pool

logger = logging.getLogger(__name__)

DIRECTORY_SYNC_INTERVAL_SECONDS = 900

# The shared-db side exposes this as a set-returning function (columns: user_id
# integer, email text, name text, lastname text, status text, level text,
# office_location text, roles text[]).
DIRECTORY_QUERY = "SELECT * FROM api.oracle_user_directory()"


def fetch_directory_rows(conn: psycopg.Connection) -> list[dict[str, Any]]:
    """Read every directory row from the shared company database."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(DIRECTORY_QUERY)
        return [dict(row) for row in cur.fetchall()]


def apply_directory(
    conn: psycopg.Connection,
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, int]:
    """Upsert Oracle employees and their DesignFlow roles from directory rows.

    Match key is ``lower(btrim(email))``; rows with an empty email are skipped.
    Never deletes employees and never writes Oracle-only fields (see module
    docstring). Does not commit — the caller owns the transaction.
    """
    created = 0
    updated = 0
    skipped = 0
    for row in rows:
        email = str(row.get("email") or "").strip()
        if not email:
            skipped += 1
            continue
        display = f"{row.get('name') or ''} {row.get('lastname') or ''}".strip()
        status = str(row.get("status") or "").strip().lower()
        roles = row.get("roles") or []
        existing = conn.execute(
            "SELECT id, name FROM public.employees WHERE lower(btrim(email)) = %s",
            (email.lower(),),
        ).fetchone()
        if existing is None:
            employee_id = uuid4()
            name = display or email.split("@", 1)[0]
            conn.execute(
                "INSERT INTO public.employees (id, email, name, role, disabled_at) "
                "VALUES (%s, %s, %s, '', CASE WHEN %s THEN now() ELSE NULL END)",
                (employee_id, email, name, bool(status and status != "active")),
            )
            created += 1
        else:
            employee_id = existing[0]
            sets: list[str] = []
            params: list[Any] = []
            if display:
                sets.append("name = %s")
                params.append(display)
            elif not (existing[1] or "").strip():
                sets.append("name = %s")
                params.append(email.split("@", 1)[0])
            if status == "active":
                sets.append("disabled_at = NULL")
            elif status:
                sets.append("disabled_at = COALESCE(disabled_at, now())")
            if sets:
                conn.execute(
                    f"UPDATE public.employees SET {', '.join(sets)} WHERE id = %s",
                    (*params, employee_id),
                )
            updated += 1
        conn.execute(
            "DELETE FROM public.employee_directory_roles WHERE employee_id = %s",
            (employee_id,),
        )
        for role in roles:
            role_name = str(role or "").strip()
            if not role_name:
                continue
            conn.execute(
                "INSERT INTO public.employee_directory_roles (employee_id, role_name) "
                "VALUES (%s, %s) ON CONFLICT (employee_id, role_name) DO NOTHING",
                (employee_id, role_name),
            )
    return {"created": created, "updated": updated, "skipped": skipped}


def run_directory_sync(settings: Settings | None = None) -> dict[str, Any]:
    """Fetch the DesignFlow directory and mirror it into Oracle; return counts."""
    cfg = settings if settings is not None else get_settings()
    result: dict[str, Any] = {"enabled": False, "created": 0, "updated": 0, "skipped": 0}
    if not cfg.dflow_directory_sync_enabled:
        logger.info("directory_sync skipped: DFLOW_DIRECTORY_SYNC_ENABLED is not on")
        return result
    if not cfg.dflow_directory_database_url:
        logger.info("directory_sync skipped: DFLOW_DIRECTORY_DATABASE_URL is not set")
        return result
    result["enabled"] = True
    with psycopg.connect(cfg.dflow_directory_database_url, connect_timeout=10) as dflow:
        rows = fetch_directory_rows(dflow)
    pool = get_pool(cfg)
    with pool.connection() as conn:
        counts = apply_directory(conn, rows)
        conn.commit()
    result.update(counts)
    return result


def handle_directory_sync(job: dict[str, Any]) -> None:
    """Worker handler for ``directory_sync`` jobs."""
    result = run_directory_sync()
    logger.info("directory_sync %s: %s", job.get("id"), result)


def maybe_queue_directory_sync(settings: Settings | None = None) -> bool:
    """Queue one ``directory_sync`` when the last one finished over 15 minutes ago.

    Does nothing while the sync is disabled or the directory URL is unset, so
    the job table stays quiet until the sync is configured.
    """
    cfg = settings if settings is not None else get_settings()
    if not cfg.dflow_directory_sync_enabled or not cfg.dflow_directory_database_url:
        return False
    pool = get_pool(cfg)
    with pool.connection() as conn:
        row = conn.execute(
            "INSERT INTO cmap.job (kind, payload) SELECT 'directory_sync', '{}'::jsonb "
            "WHERE NOT EXISTS (SELECT 1 FROM cmap.job WHERE kind = 'directory_sync' "
            "AND (state IN ('queued', 'running') "
            "OR finished_at > now() - make_interval(secs => %s))) RETURNING id",
            (DIRECTORY_SYNC_INTERVAL_SECONDS,),
        ).fetchone()
        conn.commit()
    return row is not None


def main() -> None:
    """Run one sync pass and print the counts."""
    logging.basicConfig(level=logging.INFO)
    print(f"directory_sync: {run_directory_sync()}")


if __name__ == "__main__":
    main()
