from uuid import uuid4

import pytest
import psycopg

from oracle_brain.storage import bind_checkpoint, postgres_checkpointer


def _as_role(url: str, user: str, password: str) -> str:
    """Rebuild a conninfo with substituted credentials.

    The W10 runner rebuilds ORACLE2_TEST_ADMIN_URL via psycopg make_conninfo,
    which emits keyword-value form (user=... password=...) rather than a
    postgresql:// URI. A literal 'user:password' replace silently no-ops there,
    leaving the admin identity in place. Parse and rebuild instead.
    """
    params = psycopg.conninfo.conninfo_to_dict(url)
    params["user"] = user
    params["password"] = password
    return psycopg.conninfo.make_conninfo(**params)


def test_checkpoint_scope_survives_new_connection(admin_url):
    extract_url = _as_role(admin_url, "oracle2_extract", "oracle2_local_extract_only")
    project_url = _as_role(admin_url, "oracle2_project", "oracle2_local_project_only")
    checkpoint_url = _as_role(admin_url, "oracle2_checkpoint", "oracle2_local_checkpoint_only")
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
