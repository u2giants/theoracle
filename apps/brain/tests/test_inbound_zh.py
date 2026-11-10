"""Step 0.3 gate: Chinese commands are recognised in inbound messages."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import fake_embeddings

from brain.interview import intake
from brain.interview.followup import invented_names
from brain.interview.inbound import REPLY_SKIPPED, REPLY_STOPPED, handle_inbound

EMPLOYEE_ID = "00000000-0000-4000-8000-0000000000b1"
EMPLOYEE_EMAIL = "employee@test.invalid"
CONVERSATION_REF = {
    "conversation": {"id": "a:test-conversation"},
    "serviceUrl": "https://smba.trafficmanager.net/test/",
    "user": {"id": "29:test-user"},
}


@pytest.fixture(autouse=True)
def _clean_interviews(db: Any) -> None:
    db.execute(
        "TRUNCATE cmap.open_question, cmap.teams_conversation, cmap.employee_flags, "
        "cmap.interview_send, cmap.teams_intake"
    )
    db.execute("UPDATE cmap.interview_setting SET enabled = true")
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department, job_title, profile_answer, "
        "profile_asked_at) VALUES (%s, 'Design', 'Designer', 'Designer in Design', now())",
        (EMPLOYEE_ID,),
    )
    db.commit()


def test_zh_stop_skip_done_commands(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_embeddings(monkeypatch)
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="停止")
    assert reply == {"handled": True, "reply": REPLY_STOPPED, "employee_id": EMPLOYEE_ID}
    paused = db.execute(
        "SELECT interviews_paused FROM cmap.employee_flags WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone()
    assert paused == (True,)

    db.execute(
        "UPDATE cmap.employee_flags SET interviews_paused = false WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    )
    db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids, state, "
        "target_employee_id, asked_at) VALUES ('谁负责审批？', 'test', '{}', 'asked', %s, now())",
        (EMPLOYEE_ID,),
    )
    db.commit()
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="跳过")
    assert reply["handled"] is True
    assert reply["reply"] == REPLY_SKIPPED

    first = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="我负责跨境采购审批流程的日常跟进，从供应商确认到入库都由我跟进。",
    )
    assert first["handled"] is True
    assert "intake_id" in first
    done = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="完成")
    assert done["reply"] == intake.REPLY_DONE
    assert "source_id" in done


def test_command_word_inside_sentence_ignored(db: Any) -> None:
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="这个流程需要停止后重启，我来继续跟进后续的入库确认。",
    )
    assert reply["reply"] != REPLY_STOPPED
    paused = db.execute(
        "SELECT interviews_paused FROM cmap.employee_flags WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone()
    assert not paused[0]


def test_cjk_name_guard() -> None:
    allowed = "Marco does the artwork. 王五 handles the 宁波 sign-off."
    assert invented_names("张三丰 handles this?", allowed) == {"张三丰"}
    assert invented_names("王五 handles this?", allowed) == set()
    assert invented_names("还有哪些部门参与审批？", "Marco does the artwork.") == set()
