# ruff: noqa: F811  (pytest fixtures imported from the conversation tests)
"""Plan gates for the interview rebuild (#604): send-once, the lane switch,
the entity-write lock, and resolve-before-reply."""

from __future__ import annotations

import threading
from typing import Any

import psycopg
import pytest
from test_interview_conversation import (  # noqa: F401 - shared fixtures
    _clean_interviews,
    _conv,
    _kind,
    _office_hours,
    _open,
    _say,
    enabled,
    model,
    no_ingest,
    sent,
)

from brain import db as db_mod
from brain.config import get_settings
from brain.db import (
    INTERVIEW_LANE,
    MAIN_LANE,
    lane_for,
    lock_entity_writes,
    release_entity_write_lock,
    try_entity_write_lock,
)
from brain.extract import relations as relations_mod
from brain.interview import conversation as conv_mod
from brain.interview import converse
from brain.interview import tick as tick_mod
from brain.resolve import resolve as resolve_mod


def _out_turns(db: Any) -> list[tuple[str, str | None]]:
    return [
        (str(r[0]), r[1])
        for r in db.execute(
            "SELECT send_state, send_key FROM cmap.interview_turn "
            "WHERE direction = 'out' ORDER BY seq"
        ).fetchall()
    ]


# ------------------------------------------------------------------ send once


def test_opening_records_a_sent_turn_with_its_key(
    db: Any, enabled: None, sent: list[dict[str, Any]]
) -> None:
    _open(db, sent)
    cid = _conv(db)[0]
    assert _out_turns(db) == [("sent", f"{cid}:open")]


def test_retried_reply_never_sends_twice(
    db: Any, enabled: None, sent: list[dict[str, Any]],
) -> None:
    _open(db, sent)
    cid = _conv(db)[0]
    conv = conv_mod.get_conversation(db, cid)
    cfg = get_settings()
    first = converse._send(db, conv, "followup", "Who sends the form?", cfg)
    db.commit()
    again = converse._send(db, conv, "followup", "Who sends the form?", cfg)
    db.commit()
    assert first is not None and again is None
    assert [c["text"] for c in sent].count("Who sends the form?") == 1


def test_failed_send_is_recorded_and_not_retried(
    db: Any, enabled: None, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    cid = _conv(db)[0]
    conv = conv_mod.get_conversation(db, cid)

    def _boom(*args: Any, **kw: Any) -> str:
        raise RuntimeError("teams down")

    monkeypatch.setattr(tick_mod, "_post_proactive", _boom)
    with pytest.raises(RuntimeError):
        converse._send(db, conv, "followup", "Who sends the form?", get_settings())
    db.commit()
    assert _out_turns(db)[-1][0] == "failed"
    assert _conv(db)[1] == "closed"


def test_sweep_marks_a_lost_send_failed(
    db: Any, enabled: None, sent: list[dict[str, Any]]
) -> None:
    _open(db, sent)
    db.execute(
        "UPDATE cmap.interview_turn SET send_state = 'sending', "
        "created_at = now() - interval '1 hour' WHERE direction = 'out'"
    )
    db.commit()
    assert conv_mod.sweep_conversations()["send_failed"] == 1
    assert _out_turns(db)[-1][0] == "failed"
    assert _conv(db)[1] == "closed"


# ------------------------------------------------------------------ lane switch


def test_lane_switch_off_sends_everything_to_main(monkeypatch: pytest.MonkeyPatch) -> None:
    assert lane_for("interview_reply", INTERVIEW_LANE) == INTERVIEW_LANE
    off = get_settings().model_copy(update={"brain_interview_lane_enabled": False})
    monkeypatch.setattr(db_mod, "get_settings", lambda: off)
    assert lane_for("interview_reply", INTERVIEW_LANE) == MAIN_LANE


def test_pool_size_is_a_setting() -> None:
    assert get_settings().brain_db_pool_size >= 4


# ------------------------------------------------------------------ entity lock


def _second() -> psycopg.Connection:
    return psycopg.connect(get_settings().database_url, connect_timeout=5)


def test_cleanup_and_resolve_never_interleave(db: Any) -> None:
    other = _second()
    try:
        lock_entity_writes(db)  # a cleanup transaction is open
        assert not try_entity_write_lock(other, 0.6)
        db.commit()  # cleanup done
        assert try_entity_write_lock(other, 0.6)
        waited = threading.Event()

        def _cleanup() -> None:
            with _second() as c:
                lock_entity_writes(c)
                waited.set()
                c.commit()

        t = threading.Thread(target=_cleanup)
        t.start()
        t.join(0.8)
        assert not waited.is_set()  # cleanup waits for resolve
        release_entity_write_lock(other)
        t.join(5)
        assert waited.is_set()
    finally:
        other.close()
        db.rollback()


def test_source_resolve_skips_when_lock_busy(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(resolve_mod, "SOURCE_RESOLVE_LOCK_WAIT_SECONDS", 0.5)
    lock_entity_writes(db)
    try:
        assert resolve_mod.resolve_source("00000000-0000-4000-8000-00000000ffff") is None
    finally:
        db.rollback()
    assert resolve_mod.resolve_source("00000000-0000-4000-8000-00000000ffff") is not None


# ------------------------------------------------------------------ resolve before reply


def test_answer_is_resolved_before_the_reply(
    db: Any, enabled: None, sent: list[dict[str, Any]], no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Maria signs it after Ilona checks the artwork.")
    (source_id,) = db.execute(
        "SELECT source_id::text FROM cmap.interview_turn WHERE source_id IS NOT NULL"
    ).fetchone()
    assert relations_mod._resolve_interview_answer(
        "00000000-0000-4000-8000-00000000ffff"
    ) is None
    calls: list[str] = []
    monkeypatch.setattr(resolve_mod, "resolve_source", lambda sid: calls.append(sid))
    note = relations_mod._resolve_interview_answer(source_id)
    assert calls == [source_id] and note == "skipped"
    assert conv_mod.source_chain_ended(source_id, failed=False, resolve=note)
    (meta,) = db.execute(
        "SELECT meta FROM cmap.interview_turn WHERE source_id = %s", (source_id,)
    ).fetchone()
    assert meta["resolve"] == "skipped"


# ------------------------------------------------------------------ clarify


def test_clarify_retries_once_when_a_name_is_flagged_and_sees_the_reply(
    db: Any, enabled: None, sent: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    cid = _conv(db)[0]
    (qid,) = db.execute(
        "SELECT question_id::text FROM cmap.interview_turn WHERE conversation_id = %s "
        "AND kind = 'question'", (cid,),
    ).fetchone()
    prompts: list[str] = []
    outputs = [
        {"text": "Zorblax wants to know who signs."},
        {"text": "Which person signs off this step? For example: the team lead signs."},
    ]

    def _call(prompt: str, settings: Any, max_tokens: int, label: str) -> dict[str, Any]:
        prompts.append(prompt)
        return outputs.pop(0)

    monkeypatch.setattr(converse, "_call", _call)
    text = converse._clarified(db, qid, "en", get_settings(), "that's vague")
    assert text.startswith("Which person signs off")
    assert len(prompts) == 2 and "that's vague" in prompts[0]
