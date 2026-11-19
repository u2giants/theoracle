# ruff: noqa: F811  (pytest fixtures imported from test_interview)
"""Serial interview conversations (issue #604, plan Steps 3-9).

The Teams send is a recorder at ``tick._post_proactive`` that also hands out
Teams message ids; the composer's model call is replaced at ``converse._call``.
Everything else runs against the real test database.
"""

from __future__ import annotations

from itertools import count
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_interview import (  # noqa: F401, F811 - shared fixtures and helpers
    CONVERSATION_REF,
    EMPLOYEE_EMAIL,
    EMPLOYEE_ID,
    EMPLOYEE_NAME,
    _clean_interviews,
    _connect,
    _office_hours,
    _person,
    _question,
    _states,
    enabled,  # noqa: F811
)

from brain.db import INTERVIEW_LANE, MAIN_LANE, current_lane, enqueue_job
from brain.interview import conversation as conv_mod
from brain.interview import converse
from brain.interview import inbound as inbound_mod
from brain.interview import tick as tick_mod
from brain.interview.converse import run_interview_reply
from brain.interview.inbound import handle_inbound
from brain.interview.strings import strings
from brain.interview.tick import run_interview_tick
from brain.worker import claim_next_job

OTHER_ID = "00000000-0000-4000-8000-0000000000b2"
_ids = count(1731000000001)


@pytest.fixture()
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record sends; each gets a fresh Teams message id."""
    calls: list[dict[str, Any]] = []

    def _record(
        employee_id: str, text: str, settings: Any, typing: bool = False
    ) -> str:
        del settings, typing
        activity = str(next(_ids))
        calls.append(
            {"employee_id": employee_id, "text": text, "activity_id": activity}
        )
        return activity

    monkeypatch.setattr(tick_mod, "_post_proactive", _record)
    return calls


@pytest.fixture()
def model(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Queue composer outputs; an empty queue means the model failed."""
    outputs: list[dict[str, Any]] = []

    def _call(
        prompt: str, settings: Any, max_tokens: int, label: str
    ) -> dict[str, Any]:
        del prompt, settings, max_tokens, label
        return outputs.pop(0) if outputs else {}

    monkeypatch.setattr(converse, "_call", _call)
    return outputs


@pytest.fixture()
def no_ingest(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record answers handed to the read pipeline instead of storing bytes."""
    calls: list[dict[str, Any]] = []

    def _ingest(
        conversation_id: str,
        employee_id: str,
        employee_name: str,
        question: str,
        answer: str,
        turn_ids: list[str],
        question_id: str | None,
    ) -> str:
        from brain.db import get_pool

        calls.append(
            {"answer": answer, "question": question, "question_id": question_id}
        )
        with get_pool().connection() as conn:
            sid = conn.execute(
                "INSERT INTO cmap.source (kind, title, storage_path, sha256, bytes) "
                "VALUES ('transcript', 't', 'x', gen_random_uuid()::text, 1) RETURNING id::text"
            ).fetchone()[0]
            conn.execute(
                "UPDATE cmap.interview_turn SET source_id = %s, kind = CASE WHEN kind = 'held' "
                "THEN 'answer' ELSE kind END WHERE id = ANY(%s::uuid[])",
                (sid, turn_ids),
            )
            conn.commit()
            conv_mod.set_state(conn, conversation_id, "processing")
        return str(sid)

    monkeypatch.setattr(converse, "ingest_answer", _ingest)
    return calls


def _say(text: str, **kw: Any) -> dict[str, Any]:
    return handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text=text,
        activity_id=kw.pop("activity_id", str(next(_ids))),
        **kw,
    )


def _kind(monkeypatch: pytest.MonkeyPatch, kind: str) -> None:
    monkeypatch.setattr(inbound_mod, "classify_reply", lambda question, reply: kind)


def _open(db: Any, sent: list[dict[str, Any]], n: int = 3) -> list[str]:
    person = _person(db, EMPLOYEE_NAME)
    ids = [
        _question(db, f"Who signs off step {i}?", [person], priority=9 - i)
        for i in range(n)
    ]
    _connect()
    assert run_interview_tick()["asked"] == 1
    return ids


def _conv(db: Any) -> tuple[str, str, int]:
    row = db.execute(
        "SELECT id::text, state, exchanges FROM cmap.interview_conversation "
        "ORDER BY opened_at DESC LIMIT 1"
    ).fetchone()
    return str(row[0]), str(row[1]), int(row[2])


def _finish_chain(db: Any) -> None:
    """The answer's relations step finished: the chain end queues the reply."""
    (source_id,) = db.execute(
        "SELECT source_id::text FROM cmap.interview_turn WHERE source_id IS NOT NULL "
        "ORDER BY created_at DESC, seq DESC LIMIT 1"
    ).fetchone()
    assert conv_mod.source_chain_ended(source_id, failed=False)


# ------------------------------------------------------------------ schema


def test_conversation_schema_one_open_per_employee(db: Any) -> None:
    first = conv_mod.open_conversation(db, EMPLOYEE_ID, "en")
    assert first is not None
    assert conv_mod.open_conversation(db, EMPLOYEE_ID, "en") is None
    conv_mod.close_conversation(db, first, "done")
    assert conv_mod.open_conversation(db, EMPLOYEE_ID, "en") is not None


def test_job_lane_column_defaults_to_main(db: Any) -> None:
    job_id = enqueue_job("read_source", {"source_id": "x"})
    (lane,) = db.execute(
        "SELECT lane FROM cmap.job WHERE id = %s", (job_id,)
    ).fetchone()
    assert lane == MAIN_LANE


# ------------------------------------------------------------------ lanes


def test_worker_lanes_chain_inherits_interview_lane(db: Any) -> None:
    token = current_lane.set(INTERVIEW_LANE)
    try:
        chain = enqueue_job("classify_extract", {"source_id": "x"})
        other = enqueue_job("graph_project", {})
    finally:
        current_lane.reset(token)
    lanes = dict(db.execute("SELECT id::text, lane FROM cmap.job").fetchall())
    assert lanes[str(chain)] == INTERVIEW_LANE
    assert lanes[str(other)] == MAIN_LANE  # global rebuilds never enter the fast lane
    job = claim_next_job(INTERVIEW_LANE)
    assert job is not None and job["kind"] == "classify_extract"
    assert claim_next_job(INTERVIEW_LANE) is None
    assert claim_next_job(MAIN_LANE)["kind"] == "graph_project"


# ------------------------------------------------------------------ the conversation


def test_answer_waits_for_processing_then_next_message_reflects_it(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    model: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    reply = _say("Maria signs it after Ilona checks the artwork.")
    assert reply["reply"] is None  # nothing is answered before processing
    assert no_ingest[0]["question"] == "Who signs off step 0?"
    cid, state, _ = _conv(db)
    assert state == "processing"
    _finish_chain(db)
    (n,) = db.execute(
        "SELECT count(*) FROM cmap.job WHERE kind = 'interview_reply' AND lane = %s",
        (INTERVIEW_LANE,),
    ).fetchone()
    assert n == 1
    model.append(
        {
            "reflect": "So Maria signs once Ilona has checked the artwork.",
            "action": "followup",
            "text": "Who sends Maria the form?",
            "question_index": None,
        }
    )
    result = run_interview_reply(cid)
    assert result["action"] == "followup"
    assert sent[-1]["text"].startswith("So Maria signs once Ilona")
    assert _conv(db)[1] == "awaiting_answer"


def test_invented_name_in_followup_falls_back_to_queued_question(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    model: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Maria signs it after the artwork check.")
    cid = _conv(db)[0]
    bad = {
        "reflect": "Maria signs it.",
        "action": "followup",
        "text": "Does Jonathan approve it too?",
        "question_index": None,
    }
    model.extend([bad, bad])
    _finish_chain(db)
    result = run_interview_reply(cid)
    assert result["path"] == "fallback"
    assert "Who signs off step 1?" in sent[-1]["text"]
    assert "Jonathan" not in sent[-1]["text"]
    assert _states(db)[_question_id(db, "Who signs off step 1?")] == "asked"


def test_next_question_must_contain_the_stored_question(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    model: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Maria signs it after the artwork check.")
    cid = _conv(db)[0]
    model.append(
        {
            "reflect": "Maria signs it.",
            "action": "next_question",
            "text": "Moving on, who handles it later?",
            "question_index": 1,
        }
    )
    _finish_chain(db)
    run_interview_reply(cid)
    assert "Who signs off step 1?" in sent[-1]["text"]


def test_messages_during_processing_are_combined(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    model: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Maria signs it after the artwork check.")
    cid = _conv(db)[0]
    assert _say("Also Ilona keeps a copy.")["reply"] is None
    assert _say("In the shared drive.")["reply"] is None
    assert len(no_ingest) == 1  # nothing new is processed while busy
    _finish_chain(db)
    assert run_interview_reply(cid)["reason"] == "ingesting_held"
    assert no_ingest[1]["answer"] == "Also Ilona keeps a copy.\nIn the shared drive."
    assert len(sent) == 1  # still one Oracle message out: strict alternation


def test_teams_redelivery_is_ignored(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Maria signs it after the artwork check.", activity_id="555")
    again = _say("Maria signs it after the artwork check.", activity_id="555")
    assert again["reply"] is None
    assert len(no_ingest) == 1


def test_quoted_id_from_another_employees_chat_is_ignored(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    other_conv = conv_mod.open_conversation(db, OTHER_ID, "en")
    other_q = _question(db, "Who pays the freight invoice?", [], priority=1)
    conv_mod.add_turn(
        db,
        other_conv,
        "out",
        "question",
        "Who pays the freight invoice?",
        teams_activity_id="999",
        question_id=other_q,
    )
    _kind(monkeypatch, "answer")
    _say("Maria signs it after the artwork check.", quoted_ids=["999"])
    assert no_ingest[0]["question"] == "Who signs off step 0?"


def test_unclear_gets_one_clarification_then_is_dropped(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    model: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _open(db, sent)
    _kind(monkeypatch, "unclear")
    reply = _say("What do you mean?")
    model.append({"text": "Who gives the final yes on step 0 of the approval?"})
    run_interview_reply(reply["conversation_id"])
    assert sent[-1]["text"] == strings("en").clarify.format(
        question="Who gives the final yes on step 0 of the approval?"
    )
    _say("Still not sure what you mean.")
    run_interview_reply(reply["conversation_id"])
    assert _states(db)[ids[0]] == "dismissed"
    assert sent[-1]["text"].startswith(strings("en").unclear_dropped)
    assert "Who signs off step 1?" in sent[-1]["text"]


def test_dont_know_asks_who_would_know_then_moves_on(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _open(db, sent)
    reply = _say("skip")
    run_interview_reply(reply["conversation_id"])
    assert sent[-1]["text"] == strings("en").who_would_know
    assert _states(db)[ids[0]] == "open"
    _kind(monkeypatch, "answer")
    _say("Ask Maria in licensing.")
    assert no_ingest[0]["question"] == strings("en").who_would_know
    assert no_ingest[0]["question_id"] is None


def test_request_gets_capabilities_and_the_question_again(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "request")
    reply = _say("Can you send me last month's sales numbers?")
    run_interview_reply(reply["conversation_id"])
    assert strings("en").capabilities in sent[-1]["text"]
    assert "Who signs off step 0?" in sent[-1]["text"]


def test_long_flowing_conversation_is_not_cut_off(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    model: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner ruling L9: no exchange count ever closes a sitting."""
    _open(db, sent, n=22)
    _kind(monkeypatch, "answer")
    for i in range(1, 21):
        _say(f"Maria signs step {i - 1} after the artwork check.")
        cid = _conv(db)[0]
        _finish_chain(db)
        model.append(
            {
                "reflect": "Thanks.",
                "action": "next_question",
                "text": f"Thanks. Who signs off step {i}?",
                "question_index": 1,
            }
        )
        assert run_interview_reply(cid)["action"] == "next_question"
        assert _conv(db)[1] == "awaiting_answer"
        db.execute(
            "DELETE FROM cmap.job WHERE kind = 'interview_reply'"
        )  # the worker's claim
        db.commit()
    assert _conv(db)[2] >= 20
    assert run_interview_tick()["asked"] == 0  # still one sitting per day


def test_two_unusable_replies_close_the_sitting(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "other")
    assert "Who signs off step 0?" in _say("hmm")["reply"]
    assert _say("whatever")["reply"] == strings("en").close
    assert _conv(db)[1] == "closed"


def test_resume_words_inside_a_conversation_are_not_a_command(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """'keep going' while not paused must reach the conversation, not 'welcome back'."""
    _open(db, sent)
    monkeypatch.setattr(inbound_mod, "_judge_intent", lambda text: "resume")
    _kind(monkeypatch, "other")
    reply = _say("keep going")
    assert reply["reply"] != strings("en").reply_resumed
    assert "Who signs off step 0?" in reply["reply"]


def test_processing_failure_still_moves_on(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Maria signs it after the artwork check.")
    cid = _conv(db)[0]
    (source_id,) = db.execute(
        "SELECT source_id::text FROM cmap.interview_turn WHERE source_id IS NOT NULL"
    ).fetchone()
    assert conv_mod.source_chain_ended(source_id, failed=True)
    run_interview_reply(cid, processing_failed=True)
    assert sent[-1]["text"].startswith(strings("en").processing_failed)
    assert "Who signs off step 1?" in sent[-1]["text"]


def test_stop_closes_and_returns_the_question(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
) -> None:
    ids = _open(db, sent)
    _say("stop")
    assert _conv(db)[1] == "closed"
    assert _states(db)[ids[0]] == "open"


def test_sweep_closes_idle_and_heals_stuck(
    db: Any, enabled: None, sent: list[dict[str, Any]]
) -> None:
    ids = _open(db, sent)
    cid = _conv(db)[0]
    db.execute(
        "UPDATE cmap.interview_conversation SET last_activity_at = now() - interval '2 days'"
    )
    db.commit()
    assert conv_mod.sweep_conversations()["closed_idle"] == 1
    assert _states(db)[ids[0]] == "open"
    stuck = conv_mod.open_conversation(db, OTHER_ID, "en")
    db.execute(
        "UPDATE cmap.interview_conversation SET state = 'processing', "
        "processing_since = now() - interval '1 hour' WHERE id = %s",
        (stuck,),
    )
    db.commit()
    assert conv_mod.sweep_conversations()["healed"] == 1
    del cid


def test_group_chat_never_advances_a_conversation(
    db: Any,
    storage: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    group = {
        **CONVERSATION_REF,
        "conversation": {"id": "19:group", "conversationType": "groupChat"},
    }
    handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=group,
        text="Maria signs it after the artwork check.",
        activity_id="777",
    )
    assert no_ingest == []


# ------------------------------------------------------------------ zh-CN


def test_converse_zh_fallback_uses_chinese_strings(
    db: Any,
    enabled: None,
    sent: list[dict[str, Any]],
    model: list[dict[str, Any]],
    no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db.execute(
        "UPDATE public.employees SET locale = 'zh-CN' WHERE id = %s", (EMPLOYEE_ID,)
    )
    db.commit()
    monkeypatch.setattr(tick_mod, "_translate_question", lambda q, s: f"译:{q}")
    try:
        _open(db, sent)
        _kind(monkeypatch, "answer")
        _say("玛丽亚在检查完图稿后签字。")
        cid = _conv(db)[0]
        _finish_chain(db)
        run_interview_reply(cid)
        assert sent[-1]["text"] == strings("zh-CN").next_question.format(
            question="译:Who signs off step 1?"
        )
    finally:
        db.execute(
            "UPDATE public.employees SET locale = NULL WHERE id = %s", (EMPLOYEE_ID,)
        )
        db.commit()


def test_every_new_string_exists_in_both_languages() -> None:
    for field in (
        "next_question",
        "restate",
        "clarify",
        "who_would_know",
        "capabilities",
        "unclear_dropped",
        "processing_failed",
        "close",
    ):
        assert getattr(strings("en"), field).strip()
        assert getattr(strings("zh-CN"), field).strip()
        assert getattr(strings("en"), field) != getattr(strings("zh-CN"), field)


# ------------------------------------------------------------------ API


def test_interview_api_drops_bad_teams_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from brain.api import interview as api_mod

    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        api_mod, "handle_inbound", lambda **kw: seen.update(kw) or {"handled": False}
    )
    from conftest import TEST_TOKEN as token

    response = client.post(
        "/interview/teams/inbound",
        json={
            "email": EMPLOYEE_EMAIL,
            "text": "hi",
            "activity_id": "12;DROP",
            "reply_to_id": "1731",
            "quoted_ids": ["1", "x", "2", "1", "3", "4", "5", "6"],
        },
        headers={"x-brain-token": token},
    )
    assert response.status_code == 200, response.text
    assert seen["activity_id"] is None
    assert seen["reply_to_id"] == "1731"
    assert seen["quoted_ids"] == ["1", "2", "3", "4", "5"]


def _question_id(db: Any, text: str) -> str:
    (qid,) = db.execute(
        "SELECT id::text FROM cmap.open_question WHERE question = %s", (text,)
    ).fetchone()
    return str(qid)
