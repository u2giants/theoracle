from uuid import uuid4

import pytest

from oracle_brain.storage import bind_checkpoint, postgres_checkpointer


def test_checkpoint_scope_survives_new_connection(admin_url):
    extract_url = admin_url.replace("oracle2_admin:oracle2_local_admin_only",
                                    "oracle2_extract:oracle2_local_extract_only")
    workspace, user, other = uuid4(), uuid4(), uuid4()
    thread = str(uuid4())
    assert bind_checkpoint(extract_url, thread_id=thread, workspace_id=workspace,
                           user_id=user) == thread
    with pytest.raises(PermissionError):
        bind_checkpoint(extract_url, thread_id=thread, workspace_id=workspace,
                        user_id=other)
    with pytest.raises(PermissionError):
        bind_checkpoint(extract_url, thread_id=thread, workspace_id=other,
                        user_id=user)
    with postgres_checkpointer(extract_url, thread_id=thread,
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
