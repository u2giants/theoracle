"""Postgres authority ledger and user/workspace-bound checkpoints."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row


SCHEMA_FILE = Path(__file__).resolve().parents[1] / "sql" / "001_foundation.sql"


def install_schema(admin_url: str) -> None:
    with psycopg.connect(admin_url, autocommit=True) as connection:
        connection.execute(SCHEMA_FILE.read_text())


def bind_checkpoint(database_url: str, *, thread_id: str, workspace_id: UUID,
                    user_id: UUID) -> str:
    """Bind once; refuse cross-user/workspace reuse before LangGraph access."""
    if not thread_id or len(thread_id) > 200:
        raise ValueError("invalid checkpoint thread")
    with psycopg.connect(database_url) as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """INSERT INTO oracle2.checkpoint_owners(thread_id,workspace_id,user_id)
                   VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                (thread_id, workspace_id, user_id),
            )
            cursor.execute(
                "SELECT workspace_id,user_id FROM oracle2.checkpoint_owners WHERE thread_id=%s FOR UPDATE",
                (thread_id,),
            )
            owner = cursor.fetchone()
            if owner != {"workspace_id": workspace_id, "user_id": user_id}:
                raise PermissionError("checkpoint belongs to a different principal")
    return thread_id


def postgres_checkpointer(database_url: str, *, thread_id: str, workspace_id: UUID,
                          user_id: UUID):
    """Return a real PostgresSaver after the scope guard, never a raw shared saver."""
    bind_checkpoint(database_url, thread_id=thread_id, workspace_id=workspace_id, user_id=user_id)
    from langgraph.checkpoint.postgres import PostgresSaver
    return PostgresSaver.from_conn_string(database_url)
