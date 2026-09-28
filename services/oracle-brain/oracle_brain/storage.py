"""Postgres authority ledger and user/workspace-bound checkpoints."""

from __future__ import annotations

from pathlib import Path
from contextlib import contextmanager
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
                "SELECT workspace_id,user_id FROM oracle2.checkpoint_owners WHERE thread_id=%s",
                (thread_id,),
            )
            owner = cursor.fetchone()
            if owner != {"workspace_id": workspace_id, "user_id": user_id}:
                raise PermissionError("checkpoint belongs to a different principal")
    return thread_id


def _thread_id(config: dict) -> str:
    if not isinstance(config, dict):
        raise PermissionError("checkpoint configuration required")
    thread_id = config.get("configurable", {}).get("thread_id")
    if not isinstance(thread_id, str):
        raise PermissionError("checkpoint thread ID required")
    return thread_id


def postgres_checkpointer(database_url: str, *, thread_id: str, workspace_id: UUID,
                          user_id: UUID):
    """A scoped LangGraph Postgres saver that rechecks every read and write."""
    bind_checkpoint(database_url, thread_id=thread_id, workspace_id=workspace_id,
                    user_id=user_id)
    from langgraph.checkpoint.postgres import PostgresSaver

    class ScopedPostgresSaver(PostgresSaver):
        def setup(self):
            raise PermissionError("checkpoint schema setup is bootstrap-only")

        def _check(self, config: dict) -> None:
            if _thread_id(config) != thread_id:
                raise PermissionError("checkpoint thread differs from bound thread")
            bind_checkpoint(database_url, thread_id=thread_id,
                            workspace_id=workspace_id, user_id=user_id)

        def get_tuple(self, config):
            self._check(config)
            return super().get_tuple(config)

        def list(self, config, *, filter=None, before=None, limit=None):
            self._check(config)
            if before is not None:
                self._check(before)
            return super().list(config, filter=filter, before=before, limit=limit)

        def put(self, config, checkpoint, metadata, new_versions):
            self._check(config)
            return super().put(config, checkpoint, metadata, new_versions)

        def put_writes(self, config, writes, task_id, task_path=""):
            self._check(config)
            return super().put_writes(config, writes, task_id, task_path)

        def get_delta_channel_history(self, *, config, channels):
            self._check(config)
            return super().get_delta_channel_history(config=config, channels=channels)

        def delete_thread(self, target_thread_id):
            self._check({"configurable": {"thread_id": target_thread_id}})
            return super().delete_thread(target_thread_id)

        def prune(self, thread_ids, *, strategy="keep_latest"):
            for target_thread_id in thread_ids:
                self._check({"configurable": {"thread_id": target_thread_id}})
            return super().prune(thread_ids, strategy=strategy)

        def copy_thread(self, source_thread_id, target_thread_id):
            self._check({"configurable": {"thread_id": source_thread_id}})
            self._check({"configurable": {"thread_id": target_thread_id}})
            return super().copy_thread(source_thread_id, target_thread_id)

        def delete_for_runs(self, run_ids):
            raise PermissionError("run ID deletion is not scoped to a checkpoint thread")

        async def aget_tuple(self, config):
            raise PermissionError("async checkpoint access requires a scoped async saver")

        async def alist(self, config, *, filter=None, before=None, limit=None):
            raise PermissionError("async checkpoint access requires a scoped async saver")
            yield  # pragma: no cover - preserves async iterator interface

        async def aput(self, config, checkpoint, metadata, new_versions):
            raise PermissionError("async checkpoint access requires a scoped async saver")

        async def aput_writes(self, config, writes, task_id, task_path=""):
            raise PermissionError("async checkpoint access requires a scoped async saver")

        async def aget_delta_channel_history(self, *, config, channels):
            raise PermissionError("async checkpoint access requires a scoped async saver")

        async def adelete_thread(self, target_thread_id):
            raise PermissionError("async checkpoint access requires a scoped async saver")

        async def aprune(self, thread_ids, *, strategy="keep_latest"):
            raise PermissionError("async checkpoint access requires a scoped async saver")

        async def acopy_thread(self, source_thread_id, target_thread_id):
            raise PermissionError("async checkpoint access requires a scoped async saver")

        async def adelete_for_runs(self, run_ids):
            raise PermissionError("async checkpoint access requires a scoped async saver")

    @contextmanager
    def scoped():
        with psycopg.connect(database_url, autocommit=True) as connection:
            yield ScopedPostgresSaver(connection)

    return scoped()
