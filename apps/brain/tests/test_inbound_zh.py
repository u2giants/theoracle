"""Step 0.3 gate: Chinese commands are recognised in inbound messages."""

from __future__ import annotations

from typing import Any

import pytest
from conftest import fake_embeddings

from brain.interview.followup import invented_names
from brain.interview.inbound import handle_inbound
from brain.interview.strings import strings

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
    assert reply == {
        "handled": True,
        "reply": strings("zh-CN").reply_stopped,
        "employee_id": EMPLOYEE_ID,
    }
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
    assert reply["reply"] == strings("zh-CN").reply_skipped

    first = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="我负责跨境采购审批流程的日常跟进，从供应商确认到入库都由我跟进。",
    )
    assert first["handled"] is True
    assert "intake_id" in first
    done = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="完成")
    assert done["reply"] == strings("zh-CN").reply_done
    assert "source_id" in done


def test_command_word_inside_sentence_ignored(db: Any) -> None:
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="这个流程需要停止后重启，我来继续跟进后续的入库确认。",
    )
    assert reply["reply"] not in (strings("zh-CN").reply_stopped, strings("en").reply_stopped)
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


def test_stop_variants_and_resume(db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """F4: stop-like phrases are recognised by meaning in both languages, and resume exists."""
    from brain.interview import inbound as inbound_mod

    real_judge_intent = inbound_mod._judge_intent

    def _paused() -> bool:
        row = db.execute(
            "SELECT interviews_paused FROM cmap.employee_flags WHERE employee_id = %s",
            (EMPLOYEE_ID,),
        ).fetchone()
        return bool(row[0]) if row else False

    def _judge(text: str) -> str:
        folded = text.casefold()
        if "stop" in folded or "别再问" in text or "不要再" in text:
            return "stop"
        if "resume" in folded or "继续" in text or "恢复" in text:
            return "resume"
        return "other"

    monkeypatch.setattr(inbound_mod, "_judge_intent", _judge)

    reply = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="please stop asking me questions",
    )
    assert reply["reply"] == strings("en").reply_stopped
    assert _paused() is True

    reply = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="别再问我问题了"
    )
    assert reply["reply"] == strings("zh-CN").reply_stopped
    assert _paused() is True

    reply = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="actually, you can resume"
    )
    assert reply["reply"] == strings("en").reply_resumed
    assert _paused() is False

    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="继续吧")
    assert reply["reply"] == strings("zh-CN").reply_resumed
    assert _paused() is False

    # Judge down: a variant is never accepted as a command (never-accept)...
    monkeypatch.setattr(inbound_mod, "_judge_intent", real_judge_intent)
    monkeypatch.setattr(inbound_mod, "stage_model", lambda settings, stage: None)
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="please stop sending me anything"
    )
    assert reply["reply"] != strings("en").reply_stopped
    assert _paused() is False
    # ...while the literal commands still work.
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="stop")
    assert reply["reply"] == strings("en").reply_stopped
    assert _paused() is True
