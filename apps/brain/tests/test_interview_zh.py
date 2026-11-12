"""Step 2.3 gate: interview questions arrive in the employee's language."""

from __future__ import annotations

from typing import Any

import pytest

from brain.config import get_settings
from brain.interview import tick as tick_mod
from brain.interview.inbound import handle_inbound
from brain.interview.strings import strings
from brain.interview.tick import run_interview_tick

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
        "cmap.interview_send, cmap.teams_intake, cmap.translation"
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


@pytest.fixture()
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []

    def _record(employee_id: str, text: str, settings: Any) -> None:
        del settings
        calls.append((employee_id, text))

    monkeypatch.setattr(tick_mod, "_post_proactive", _record)
    return calls


@pytest.fixture()
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "brain_interview_enabled", True)
    monkeypatch.setattr(get_settings(), "brain_interview_weekly_cap", 2)
    monkeypatch.setattr(tick_mod, "in_quiet_hours", lambda now=None: False)


def _set_locale(db: Any, locale: str | None) -> None:
    db.execute(
        "UPDATE public.employees SET locale = %s WHERE id = %s",
        (locale, EMPLOYEE_ID),
    )
    db.commit()


def _question(db: Any, text: str) -> str:
    person = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name) VALUES ('Person', %s) "
        "RETURNING id",
        ("Test Employee",),
    ).fetchone()[0]
    row = db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids, priority) "
        "VALUES (%s, 'test', %s, 3) RETURNING id::text",
        (text, [person]),
    ).fetchone()
    db.commit()
    return str(row[0])


def test_question_translated_once_and_cached(
    db: Any, enabled: None, sent: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_locale(db, "zh-CN")
    calls: list[str] = []

    def _fake_translate(question: str, settings: Any) -> str:
        del settings
        calls.append(question)
        return "谁签署授权方审批表？"

    monkeypatch.setattr(tick_mod, "_translate_question", _fake_translate)
    qid = _question(db, "Who signs the licensor approval form?")
    assert run_interview_tick()["asked"] == 1
    assert calls == ["Who signs the licensor approval form?"]
    assert sent and sent[0][0] == EMPLOYEE_ID
    assert "谁签署授权方审批表？" in sent[0][1]
    assert "跳过" in sent[0][1]  # zh command hints in the template

    db.execute("UPDATE cmap.open_question SET state = 'open', asked_at = NULL WHERE id = %s", (qid,))
    db.execute("DELETE FROM cmap.interview_send")
    db.commit()
    sent.clear()
    assert run_interview_tick()["asked"] == 1
    assert calls == ["Who signs the licensor approval form?"]  # cached, not re-translated
    assert "谁签署授权方审批表？" in sent[0][1]


def test_en_question_unaffected(
    db: Any, enabled: None, sent: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_locale(db, None)
    calls: list[str] = []
    monkeypatch.setattr(
        tick_mod,
        "_translate_question",
        lambda question, settings: calls.append(question) or "",
    )
    text = "Who signs the licensor approval form?"
    _question(db, text)
    assert run_interview_tick()["asked"] == 1
    assert calls == []  # no translation for English employees
    assert sent and text in sent[0][1]
    assert sent[0][1] == strings("en").message_template.format(question=text)


def test_answer_becomes_source_zh(
    db: Any,
    enabled: None,
    sent: list[tuple[str, str]],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from conftest import fake_embeddings

    from brain.interview import inbound as inbound_mod

    fake_embeddings(monkeypatch)
    monkeypatch.setattr(inbound_mod, "classify_reply", lambda question, reply: "answer")
    _set_locale(db, "zh-CN")
    qid = _question(db, "谁签署授权方审批表？")
    db.execute(
        "UPDATE cmap.open_question SET state = 'asked', target_employee_id = %s, "
        "asked_at = now() WHERE id = %s",
        (EMPLOYEE_ID, qid),
    )
    db.commit()
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="李四签署审批表，但要先等王五确认样稿。",
    )
    assert reply["reply"] == strings("zh-CN").reply_answered
    assert reply["source_id"]
    row = db.execute(
        "SELECT state, answer FROM cmap.open_question WHERE id = %s", (qid,)
    ).fetchone()
    assert row[0] == "answered"
    assert "李四" in str(row[1])
