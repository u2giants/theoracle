"""Open-question queue and Teams interviews (plan step 12).

The proactive Teams send is replaced by a recorder at the ``_post_proactive``
seam; everything else (routing, cap, stop, answer-to-source, read pipeline)
runs against the real test database.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from conftest import fake_embeddings

from brain.config import get_settings
from brain.interview import tick as tick_mod
from brain.interview.inbound import REPLY_ANSWERED, REPLY_STOPPED, handle_inbound
from brain.interview.tick import (
    MESSAGE_TEMPLATE,
    maybe_queue_interview_tick,
    run_interview_tick,
)
from brain.read.pipeline import handle_read_source

EMPLOYEE_ID = "00000000-0000-4000-8000-0000000000b1"
EMPLOYEE_EMAIL = "employee@test.invalid"
EMPLOYEE_NAME = "Test Employee"
ADMIN_ID = "00000000-0000-4000-8000-0000000000a1"
CONVERSATION_REF = {
    "conversation": {"id": "a:test-conversation"},
    "serviceUrl": "https://smba.trafficmanager.net/test/",
    "user": {"id": "29:test-user"},
}


@pytest.fixture(autouse=True)
def _clean_interviews(db: Any) -> None:
    db.execute(
        "TRUNCATE cmap.open_question, cmap.teams_conversation, cmap.employee_flags, "
        "cmap.interview_send"
    )
    db.execute("UPDATE cmap.interview_setting SET enabled = true")
    db.commit()


@pytest.fixture()
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Record proactive sends instead of calling the Next.js route."""
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


def _person(db: Any, name: str) -> str:
    row = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name) VALUES ('Person', %s) RETURNING id::text",
        (name,),
    ).fetchone()
    db.commit()
    return str(row[0])


def _thing(db: Any, name: str) -> str:
    row = db.execute(
        "INSERT INTO cmap.entity (entity_type, canonical_name) VALUES ('Process', %s) RETURNING id::text",
        (name,),
    ).fetchone()
    db.commit()
    return str(row[0])


def _relate(db: Any, a: str, b: str, sources: int) -> None:
    """Link two entities with one relation in each of ``sources`` sources."""
    for _ in range(sources):
        sid = str(uuid4())
        db.execute(
            "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes) "
            "VALUES (%s, 'text', 'seed', 'x', %s, 1)",
            (sid, sid),
        )
        chunk = db.execute(
            "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
            "VALUES (%s, 0, '{}'::jsonb, 'seed', 1) RETURNING id",
            (sid,),
        ).fetchone()[0]
        mentions = []
        for entity in (a, b):
            mentions.append(
                db.execute(
                    "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
                    "normalized_name, quote, entity_id) VALUES (%s, 'X', 'x', 'x', 'seed', %s) "
                    "RETURNING id",
                    (chunk, entity),
                ).fetchone()[0]
            )
        db.execute(
            "INSERT INTO cmap.relation (chunk_id, from_mention_id, to_mention_id, rel_type, "
            "description, stance, confidence, quote) "
            "VALUES (%s, %s, %s, 'OWNS', 'seed', 'report', 0.9, 'seed')",
            (chunk, mentions[0], mentions[1]),
        )
    db.commit()


def _question(db: Any, text: str, entity_ids: list[str]) -> str:
    row = db.execute(
        "INSERT INTO cmap.open_question (question, why, entity_ids) VALUES (%s, 'test', %s) "
        "RETURNING id::text",
        (text, entity_ids),
    ).fetchone()
    db.commit()
    return str(row[0])


def _connect(email: str = EMPLOYEE_EMAIL) -> dict[str, Any]:
    """The employee messages the bot for the first time."""
    return handle_inbound(email=email, conversation_ref=CONVERSATION_REF, text="hello")


def _states(db: Any) -> dict[str, str]:
    return {
        str(qid): str(state)
        for qid, state in db.execute("SELECT id::text, state FROM cmap.open_question").fetchall()
    }


def test_weekly_cap(db: Any, enabled: None, sent: list[tuple[str, str]]) -> None:
    person = _person(db, EMPLOYEE_NAME)
    licensing = _thing(db, "Licensing approval")
    _relate(db, person, licensing, sources=2)
    ids = [_question(db, f"Who signs off step {n}?", [licensing]) for n in range(3)]
    assert _connect()["handled"] is False

    first = run_interview_tick()
    assert first["asked"] == 2
    assert first["unrouted"] == 1
    assert [employee for employee, _ in sent] == [EMPLOYEE_ID, EMPLOYEE_ID]
    assert sent[0][1] == MESSAGE_TEMPLATE.format(question="Who signs off step 0?")
    states = _states(db)
    assert [states[qid] for qid in ids] == ["asked", "asked", "open"]

    second = run_interview_tick()
    assert second["asked"] == 0
    assert len(sent) == 2

    db.execute("UPDATE cmap.interview_send SET sent_at = now() - interval '8 days'")
    db.commit()
    third = run_interview_tick()
    assert third["asked"] == 1
    assert _states(db)[ids[2]] == "asked"


def test_most_connected_person_is_chosen(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    employee = _person(db, EMPLOYEE_NAME)
    admin = _person(db, "Test Admin")
    licensing = _thing(db, "Licensing approval")
    _relate(db, employee, licensing, sources=1)
    _relate(db, admin, licensing, sources=3)
    _question(db, "Why does licensing approval stall?", [licensing])
    _connect()
    handle_inbound(email="admin@test.invalid", conversation_ref=CONVERSATION_REF, text="hi")

    run_interview_tick()
    assert [employee_id for employee_id, _ in sent] == [ADMIN_ID]


def test_stop_pauses(db: Any, enabled: None, sent: list[tuple[str, str]]) -> None:
    person = _person(db, EMPLOYEE_NAME)
    _question(db, "Who approves samples?", [person])
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Stop.")
    assert reply == {"handled": True, "reply": REPLY_STOPPED, "employee_id": EMPLOYEE_ID}
    paused = db.execute(
        "SELECT interviews_paused FROM cmap.employee_flags WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone()
    assert paused == (True,)

    result = run_interview_tick()
    assert sent == []
    assert result["asked"] == 0
    assert set(_states(db).values()) == {"open"}


def test_answer_becomes_source(
    db: Any,
    enabled: None,
    sent: list[tuple[str, str]],
    storage: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_embeddings(monkeypatch)
    person = _person(db, EMPLOYEE_NAME)
    qid = _question(db, "Who signs the licensor approval form?", [person])
    _connect()
    assert run_interview_tick()["asked"] == 1

    answer = "Jessica signs it, but only after Ilona checks the artwork."
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=answer)
    assert reply["handled"] is True
    assert reply["reply"] == REPLY_ANSWERED
    source_id = reply["source_id"]

    row = db.execute(
        "SELECT state, answer, answer_source_id::text FROM cmap.open_question WHERE id = %s",
        (qid,),
    ).fetchone()
    assert row == ("answered", answer, source_id)
    kind, title = db.execute(
        "SELECT kind, title FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    assert kind == "transcript"
    assert title.startswith(f"Interview answer — {EMPLOYEE_NAME} — ")
    job = db.execute(
        "SELECT id, kind, payload FROM cmap.job WHERE kind = 'read_source' "
        "AND payload->>'source_id' = %s",
        (source_id,),
    ).fetchone()
    assert job is not None

    handle_read_source({"id": job[0], "kind": job[1], "payload": job[2]})
    chunks = db.execute(
        "SELECT locator->>'speaker', text FROM cmap.chunk WHERE source_id = %s ORDER BY ordinal",
        (source_id,),
    ).fetchall()
    assert [speaker for speaker, _ in chunks] == ["The Oracle", EMPLOYEE_NAME]
    assert "licensor approval form" in chunks[0][1]
    assert answer in chunks[1][1]

    later = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="join")
    assert later["handled"] is False


def test_skip_reopens_for_someone_else(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    qid = _question(db, "Who approves samples?", [person])
    _connect()
    run_interview_tick()
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="skip")
    assert reply["handled"] is True
    assert _states(db)[qid] == "open"
    run_interview_tick()
    assert len(sent) == 1


def test_disabled_sends_nothing(
    db: Any, sent: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    _question(db, "Who approves samples?", [person])
    _connect()
    monkeypatch.setattr(get_settings(), "brain_interview_enabled", False)
    db.execute("DELETE FROM cmap.job")
    db.commit()

    assert maybe_queue_interview_tick() is False
    assert db.execute("SELECT count(*) FROM cmap.job").fetchone() == (0,)
    assert run_interview_tick()["enabled"] is False
    assert sent == []

    # Enabled, but the page switch is off: still nothing.
    monkeypatch.setattr(get_settings(), "brain_interview_enabled", True)
    db.execute("UPDATE cmap.interview_setting SET enabled = false")
    db.commit()
    assert run_interview_tick()["asked"] == 0
    assert sent == []

    # Enabled everywhere, but this employee never messaged the bot: nothing.
    db.execute("UPDATE cmap.interview_setting SET enabled = true")
    db.execute("TRUNCATE cmap.teams_conversation")
    db.commit()
    result = run_interview_tick()
    assert result == {"enabled": True, "asked": 0, "unrouted": 1, "failed": 0}
    assert sent == []
    assert set(_states(db).values()) == {"open"}


def test_service_routes_need_token(client: Any) -> None:
    from conftest import TEST_TOKEN

    body = {"email": EMPLOYEE_EMAIL, "text": "hello"}
    assert client.post("/interview/teams/inbound", json=body).status_code == 401
    ok = client.post("/interview/teams/inbound", json=body, headers={"x-brain-token": TEST_TOKEN})
    assert ok.status_code == 200
    assert client.get(f"/interview/teams/conversation/{EMPLOYEE_ID}").status_code == 401


def test_admin_overview_pause_and_route(
    db: Any, client: Any, admin_headers: dict[str, str], user_headers: dict[str, str]
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    qid = _question(db, "Who approves samples?", [person])
    _connect()
    assert client.get("/interview/overview", headers=user_headers).status_code == 403
    body = client.get("/interview/overview", headers=admin_headers).json()
    question = next(item for item in body["questions"] if item["id"] == qid)
    assert question["next_target"] == {"employee_id": EMPLOYEE_ID, "name": EMPLOYEE_NAME}
    assert body["env_enabled"] is False

    paused = client.post(
        f"/interview/employees/{EMPLOYEE_ID}/pause", json={"paused": True}, headers=admin_headers
    )
    assert paused.status_code == 200
    body = client.get("/interview/overview", headers=admin_headers).json()
    question = next(item for item in body["questions"] if item["id"] == qid)
    assert question["next_target"] is None

    routed = client.post(
        f"/interview/questions/{qid}/route", json={"employee_id": ADMIN_ID}, headers=admin_headers
    )
    assert routed.status_code == 200
    assert client.post(
        "/interview/settings", json={"enabled": False}, headers=admin_headers
    ).json() == {"switch_enabled": False}


def test_skipped_questions_still_count_toward_cap(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    for n in range(5):
        _question(db, f"Question {n}?", [person])
    _connect()
    for _ in range(5):
        run_interview_tick()
        handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="skip")
    assert len(sent) == 2
