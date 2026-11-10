"""Step 0.3/2.1 gate: Chinese commands, contribution counting and zh replies."""

from __future__ import annotations

from typing import Any

import pytest

from brain.interview import intake
from brain.interview.inbound import handle_inbound
from brain.interview.strings import strings
from brain.text_util import fold_key

EMPLOYEE_ID = "00000000-0000-4000-8000-0000000000b1"
EMPLOYEE_EMAIL = "employee@test.invalid"
CONVERSATION_REF = {
    "conversation": {"id": "a:test-conversation"},
    "serviceUrl": "https://smba.trafficmanager.net/test/",
    "user": {"id": "29:test-user"},
}
VOLUNTEERED_ZH = "我负责跨境采购审批流程的日常跟进，从供应商确认到入库都由我跟进。"


def test_nihao_greets() -> None:
    assert intake.is_greeting(fold_key("你好！")) is True
    assert intake.is_greeting(fold_key("您好")) is True
    assert intake.is_greeting(fold_key("在吗？")) is True
    assert intake.is_greeting(fold_key("hello")) is True


def test_wancheng_is_done() -> None:
    assert intake.is_done(fold_key("完成")) is True
    assert intake.is_done(fold_key("好了。")) is True
    assert intake.is_done(fold_key("说完了")) is True
    assert intake.is_done(fold_key("就这些")) is True
    assert intake.is_done(fold_key("done")) is True
    assert intake.is_done(fold_key("还没说完")) is False


def test_cjk_contribution_accepted() -> None:
    text = "我负责跨境采购审批流程的日常跟进工作"
    assert intake.word_count(text) >= intake.MIN_CONTRIBUTION_WORDS
    assert intake.word_count(text) != 1


def test_zh_join_request() -> None:
    assert intake.is_join_request("加入会议") is True
    assert intake.is_join_request("拉我进会议室") is True
    assert intake.is_join_request("join the call") is True


@pytest.fixture()
def _clean_bot(db: Any):
    db.execute(
        "TRUNCATE cmap.open_question, cmap.teams_conversation, cmap.employee_flags, "
        "cmap.interview_send, cmap.teams_intake"
    )
    db.execute("UPDATE cmap.interview_setting SET enabled = true")
    db.execute("UPDATE public.employees SET locale = NULL")
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department, job_title, profile_answer, "
        "profile_asked_at) VALUES (%s, 'Design', 'Designer', 'Designer in Design', now())",
        (EMPLOYEE_ID,),
    )
    db.commit()
    yield
    db.execute("UPDATE public.employees SET locale = NULL")
    db.commit()


def _set_locale(db: Any, locale: str | None) -> None:
    db.execute(
        "UPDATE public.employees SET locale = %s WHERE id = %s",
        (locale, EMPLOYEE_ID),
    )
    db.commit()


def test_zh_employee_gets_zh_replies(db: Any, storage: Any, _clean_bot: None) -> None:
    _set_locale(db, "zh-CN")
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="你好")
    assert reply["handled"] is True
    assert reply["reply"] == strings("zh-CN").reply_intro
    first = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED_ZH
    )
    assert first["reply"] == strings("zh-CN").reply_ack
    done = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="完成")
    assert done["reply"] == strings("zh-CN").reply_done


def test_en_employee_unaffected(db: Any, _clean_bot: None) -> None:
    _set_locale(db, None)
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Hi!")
    assert reply["reply"] == strings("en").reply_intro
    first = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="I handle the purchasing approvals and pass them to Dana in production.",
    )
    assert first["reply"] == strings("en").reply_ack


def test_thread_language_pin(db: Any, _clean_bot: None) -> None:
    _set_locale(db, None)  # English locale employee
    first = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED_ZH
    )
    assert first["handled"] is True
    assert first["reply"] == strings("zh-CN").reply_ack  # Chinese opening pins the thread
    pinned = db.execute(
        "SELECT lang FROM cmap.teams_intake WHERE id = %s", (first["intake_id"],)
    ).fetchone()
    assert pinned == ("zh-CN",)
    later = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="Dana usually turns it in two days.",
    )
    assert later["reply"] == strings("zh-CN").reply_ack  # pinned thread stays Chinese
