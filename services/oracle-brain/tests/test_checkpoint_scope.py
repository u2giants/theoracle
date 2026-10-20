from urllib.parse import quote
from uuid import uuid4

import pytest
import psycopg

from oracle_brain.storage import bind_checkpoint, postgres_checkpointer


def _as_role(url: str, user: str, password: str) -> str:
    """Rebuild a conninfo as a postgresql:// URI with substituted credentials.

    Must return URI form: Settings.from_env() runs urlparse().hostname against
    the value and rejects anything whose host is outside the isolated-network
    allowlist.  psycopg.conninfo.make_conninfo emits keyword-value form
    (user=... password=...) whose urlparse().hostname is None, which trips
    that guard.  A URI satisfies both psycopg.connect and urlparse.
    """
    params = psycopg.conninfo.conninfo_to_dict(url)
    host = params.get("host") or "localhost"
    port = params.get("port") or "5432"
    dbname = params.get("dbname") or "postgres"
    extra = {k: v for k, v in params.items()
             if k not in {"host", "port", "user", "password", "dbname"} and v is not None}
    query = "&".join(f"{quote(k)}={quote(str(v))}" for k, v in sorted(extra.items()))
    uri = f"postgresql://{quote(user)}:{quote(password)}@{host}:{port}/{quote(dbname)}"
    return uri + ("?" + query if query else "")


def test_checkpoint_scope_survives_new_connection(admin_url):
    extract_url = _as_role(admin_url, "oracle2_extract", "oracle2_local_extract_only")
    project_url = _as_role(admin_url, "oracle2_project", "oracle2_local_project_only")
    checkpoint_url = _as_role(admin_url, "oracle2_checkpoint", "oracle2_local_checkpoint_only")
    # W10 creates a fresh database and runs SYNTHETIC_MIGRATIONS; the
    # grant-postgres.sql that provisions these roles is only applied to the
    # Docker-init database.  Seed the minimal grants this test needs so the
    # restricted identities can actually reach their own tables, then verify
    # they cannot reach anyone else's.
    with psycopg.connect(admin_url, autocommit=True) as conn:
        conn.execute("GRANT USAGE ON SCHEMA oracle2 TO oracle2_extract, oracle2_project, oracle2_checkpoint")
        conn.execute("GRANT SELECT, INSERT ON oracle2.checkpoint_owners TO oracle2_checkpoint")
        # Create the LangGraph checkpoint tables so saver.list() can query
        # them (the scoped saver blocks setup(), but the tables must exist).
        from langgraph.checkpoint.postgres import PostgresSaver
        for migration in PostgresSaver.MIGRATIONS:
            conn.execute(migration)
        # The scoped saver runs as oracle2_checkpoint; it needs read access to
        # the checkpoint tables it owns the lifecycle for.
        conn.execute("GRANT SELECT ON checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations TO oracle2_checkpoint")
    for worker_url in (extract_url, project_url):
        for table in ("public.checkpoints", "public.checkpoint_blobs",
                      "public.checkpoint_writes", "oracle2.checkpoint_owners"):
            with psycopg.connect(worker_url) as connection:
                with pytest.raises(psycopg.Error):
                    connection.execute(f"SELECT * FROM {table} LIMIT 1")
    workspace, user, other = uuid4(), uuid4(), uuid4()
    thread = str(uuid4())
    assert bind_checkpoint(checkpoint_url, thread_id=thread, workspace_id=workspace,
                           user_id=user) == thread
    with pytest.raises(PermissionError):
        bind_checkpoint(checkpoint_url, thread_id=thread, workspace_id=workspace,
                        user_id=other)
    with pytest.raises(PermissionError):
        bind_checkpoint(checkpoint_url, thread_id=thread, workspace_id=other,
                        user_id=user)
    with postgres_checkpointer(checkpoint_url, thread_id=thread,
                               workspace_id=workspace, user_id=user) as saver:
        with pytest.raises(PermissionError):
            saver.setup()
        with pytest.raises(PermissionError):
            saver.get_tuple({"configurable": {"thread_id": str(uuid4())}})
        with pytest.raises(PermissionError):
            saver.get_delta_channel_history(config={"configurable": {"thread_id": str(uuid4())}},
                                            channels=["messages"])
        with pytest.raises(PermissionError):
            saver.delete_thread(str(uuid4()))
        with pytest.raises(PermissionError):
            list(saver.list(None))
        assert list(saver.list({"configurable": {"thread_id": thread}})) == []
