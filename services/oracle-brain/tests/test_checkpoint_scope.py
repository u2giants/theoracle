from uuid import uuid4

import pytest
import psycopg

from oracle_brain.storage import bind_checkpoint, postgres_checkpointer


def test_checkpoint_scope_survives_new_connection(admin_url):
    extract_url = admin_url.replace("oracle2_admin:oracle2_local_admin_only",
                                    "oracle2_extract:oracle2_local_extract_only")
    project_url = admin_url.replace("oracle2_admin:oracle2_local_admin_only",
                                    "oracle2_project:oracle2_local_project_only")
    checkpoint_url = admin_url.replace("oracle2_admin:oracle2_local_admin_only",
                                       "oracle2_checkpoint:oracle2_local_checkpoint_only")
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
