"""Open-question queue and Teams interviews (plan step 12).

The proactive Teams send is replaced by a recorder at the ``_post_proactive``
seam; everything else (routing, cap, stop, answer-to-source, read pipeline)
runs against the real test database.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from conftest import fake_embeddings

from brain.config import get_settings
from brain.interview import intake
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
        "cmap.interview_send, cmap.teams_intake"
    )
    db.execute("UPDATE cmap.interview_setting SET enabled = true")
    # The standing test employee already told the bot who they are; the
    # profile tests clear this row to exercise the question.
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department, job_title, profile_answer, "
        "profile_asked_at) VALUES (%s, 'Design', 'Designer', 'Designer in Design', now())",
        (EMPLOYEE_ID,),
    )
    db.commit()


@pytest.fixture(autouse=True)
def _office_hours(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Tick tests run as if during office hours whatever the wall clock says."""
    if request.node.name == "test_quiet_hours_window":
        return
    monkeypatch.setattr(tick_mod, "in_quiet_hours", lambda now=None: False)


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
    monkeypatch.setattr(tick_mod, "in_quiet_hours", lambda now=None: False)


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


def _evidence(
    db: Any,
    employee_id: str,
    employee_name: str,
    mentions: dict[str, str],
) -> str:
    """One closed Teams contribution from the employee, naming the entities."""
    sid = str(uuid4())
    db.execute(
        "INSERT INTO cmap.source (id, kind, title, storage_path, sha256, bytes) "
        "VALUES (%s, 'transcript', %s, 'x', %s, 1)",
        (sid, f"Teams contribution — {employee_name} — 2026-01-02", sid),
    )
    chunk = db.execute(
        "INSERT INTO cmap.chunk (source_id, ordinal, locator, text, token_count) "
        "VALUES (%s, 0, '{}'::jsonb, 'seed', 1) RETURNING id",
        (sid,),
    ).fetchone()[0]
    for entity_id, name in mentions.items():
        db.execute(
            "INSERT INTO cmap.mention (chunk_id, entity_type, surface_name, "
            "normalized_name, quote, entity_id) VALUES (%s, 'X', %s, %s, 'seed', %s)",
            (chunk, name, name.casefold(), entity_id),
        )
    db.execute(
        "INSERT INTO cmap.teams_intake (employee_id, state, turns, source_id, closed_at) "
        "VALUES (%s, 'closed', '[]'::jsonb, %s, now())",
        (employee_id, sid),
    )
    db.commit()
    return sid


def _question(
    db: Any,
    text: str,
    entity_ids: list[str],
    *,
    priority: int | None = 3,
    person: str | None = None,
    department: str | None = None,
) -> str:
    row = db.execute(
        "INSERT INTO cmap.open_question "
        "(question, why, entity_ids, priority, suggested_person, department) "
        "VALUES (%s, 'test', %s, %s, %s, %s) RETURNING id::text",
        (text, entity_ids, priority, person, department),
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


def test_one_question_in_flight_per_person(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """Owner 2026-11-10: a person gets one question, and the next only after replying."""
    person = _person(db, EMPLOYEE_NAME)
    ids = [_question(db, f"Who signs off step {n}?", [person]) for n in range(3)]
    assert _connect()["reply"] == intake.REPLY_INTRO

    first = run_interview_tick()
    assert first["asked"] == 1
    assert sent == [(EMPLOYEE_ID, MESSAGE_TEMPLATE.format(question="Who signs off step 0?"))]

    assert run_interview_tick()["asked"] == 0
    assert len(sent) == 1

    db.execute("UPDATE cmap.open_question SET state = 'answered' WHERE id = %s", (ids[0],))
    db.commit()
    assert run_interview_tick()["asked"] == 1
    assert sent[1][1] == MESSAGE_TEMPLATE.format(question="Who signs off step 1?")


def test_daily_cap(
    db: Any, enabled: None, sent: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    for n in range(5):
        _question(db, f"Question {n}?", [person])
    _connect()
    monkeypatch.setattr(get_settings(), "brain_interview_weekly_cap", 10)
    for _ in range(5):
        run_interview_tick()
        db.execute("UPDATE cmap.open_question SET state = 'answered' WHERE state = 'asked'")
        db.commit()
    assert len(sent) == tick_mod.DAILY_CAP


def test_loosely_connected_person_is_not_asked(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """Owner 2026-11-10: only someone the question names is asked, not whoever is nearby."""
    _person(db, EMPLOYEE_NAME)
    admin = _person(db, "Test Admin")
    licensing = _thing(db, "Licensing approval")
    _relate(db, admin, licensing, sources=3)
    _question(db, "Why does licensing approval stall?", [licensing])
    _connect()
    handle_inbound(email="admin@test.invalid", conversation_ref=CONVERSATION_REF, text="hi")

    result = run_interview_tick()
    assert sent == []
    assert result["unrouted"] == 1


def test_evidence_contributor_beats_most_connected_person(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """A famous-but-uninvolved person loses to whoever contributed the evidence."""
    famous = _person(db, "Test Admin")
    owner = _person(db, EMPLOYEE_NAME)
    topic = _thing(db, "Licensing approval")
    _relate(db, famous, topic, sources=5)
    _relate(db, owner, topic, sources=1)
    _evidence(db, EMPLOYEE_ID, EMPLOYEE_NAME, {topic: "Licensing approval"})
    _question(db, "Why does licensing approval stall?", [famous, topic])
    _connect()

    result = run_interview_tick()
    assert [employee for employee, _ in sent] == [EMPLOYEE_ID]
    assert result["asked"] == 1


def test_contributor_found_from_question_text_when_ids_are_dangling(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """Question entity_ids may not resolve; the question text still finds the owner."""
    topic = _thing(db, "Licensing approval")
    _evidence(db, EMPLOYEE_ID, EMPLOYEE_NAME, {topic: "Licensing approval"})
    _question(db, "Why does the licensing approval stall?", [str(uuid4())])
    _connect()

    result = run_interview_tick()
    assert [employee for employee, _ in sent] == [EMPLOYEE_ID]
    assert result["asked"] == 1


def test_vetted_question_without_a_pick_falls_back_to_the_contributor(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """Vetting named a department but nobody: its evidence owner is asked.

    Never the bystander with the highest edge weight. A BLANK department is a
    different rule — PR #514's "empty department means nobody" — and is gated
    by test_blank_department_with_no_suggested_person_returns_none (the old
    blank-department fixture here was the scatter this pool fix removes).
    """
    bystander = _person(db, "Test Admin")
    topic = _thing(db, "Licensing approval")
    _relate(db, bystander, topic, sources=5)
    _evidence(db, EMPLOYEE_ID, EMPLOYEE_NAME, {topic: "Licensing approval"})
    _question(db, "Who signs licensing approvals?", [bystander, topic], department="Design")

    result = run_interview_tick()
    assert [employee for employee, _ in sent] == [EMPLOYEE_ID]
    assert result["asked"] == 1


def test_department_question_defers_when_the_only_member_is_at_weekly_cap(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """The department's one member already got their weekly question: the
    question waits for a later tick — never the evidence-owning bystander."""
    bystander = _person(db, "Test Admin")
    topic = _thing(db, "Licensing approval")
    _evidence(db, ADMIN_ID, "Test Admin", {topic: "Licensing approval"})
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department) VALUES (%s, 'Licensing') "
        "ON CONFLICT (employee_id) DO UPDATE SET department = 'Licensing'",
        (EMPLOYEE_ID,),
    )
    for _ in range(2):
        db.execute("INSERT INTO cmap.interview_send (employee_id) VALUES (%s)", (EMPLOYEE_ID,))
    db.commit()
    _question(db, "Who signs licensing approvals?", [bystander, topic], department="Licensing")

    result = run_interview_tick()
    assert sent == []
    assert result["unrouted"] == 1


def test_famous_bystander_is_never_chosen_when_the_department_pool_is_exhausted(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """A famous named bystander (highest edge weight) is never picked for a
    department question — when the department's people are busy, it waits."""
    bystander = _person(db, "Test Admin")
    topic = _thing(db, "Licensing approval")
    _relate(db, bystander, topic, sources=5)
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department) VALUES (%s, 'Licensing') "
        "ON CONFLICT (employee_id) DO UPDATE SET department = 'Licensing'",
        (EMPLOYEE_ID,),
    )
    for _ in range(2):
        db.execute("INSERT INTO cmap.interview_send (employee_id) VALUES (%s)", (EMPLOYEE_ID,))
    db.commit()
    _question(db, "Who signs licensing approvals?", [bystander, topic], department="Licensing")

    result = run_interview_tick()
    assert sent == []
    assert result["unrouted"] == 1


def test_blank_department_with_no_suggested_person_returns_none(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """PR #514's rule: an empty department means nobody — the question waits
    for manual routing; the evidence fallback must not scatter it."""
    owner = _person(db, EMPLOYEE_NAME)
    topic = _thing(db, "Licensing approval")
    _evidence(db, EMPLOYEE_ID, EMPLOYEE_NAME, {topic: "Licensing approval"})
    _question(db, "Who signs licensing approvals?", [owner, topic], department="")

    result = run_interview_tick()
    assert sent == []
    assert result["unrouted"] == 1


def test_department_member_with_own_evidence_beats_the_less_involved_member(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """Within the department pool, own evidence about the question's entities
    wins over a less-involved member — evidence owners first."""
    other_id = str(uuid4())
    db.execute(
        "INSERT INTO public.employees (id, email, name) "
        "VALUES (%s, %s, 'Less Involved')",
        (other_id, f"{uuid4().hex[:12]}@test.invalid"),
    )
    for employee_id in (EMPLOYEE_ID, other_id):
        db.execute(
            "INSERT INTO cmap.employee_flags (employee_id, department) VALUES (%s, 'Licensing') "
            "ON CONFLICT (employee_id) DO UPDATE SET department = 'Licensing'",
            (employee_id,),
        )
    db.execute("INSERT INTO cmap.interview_send (employee_id) VALUES (%s)", (EMPLOYEE_ID,))
    db.commit()
    owner = _person(db, EMPLOYEE_NAME)
    topic = _thing(db, "Licensing approval")
    _evidence(db, EMPLOYEE_ID, EMPLOYEE_NAME, {topic: "Licensing approval"})
    _question(db, "Who signs licensing approvals?", [owner, topic], department="Licensing")

    result = run_interview_tick()
    assert [employee for employee, _ in sent] == [EMPLOYEE_ID]
    assert result["asked"] == 1


def test_bot_entity_is_never_routed(db: Any, enabled: None, sent: list[tuple[str, str]]) -> None:
    """The bot's own Person entity is never a target, however the question names it."""
    bot_id = str(uuid4())
    db.execute(
        "INSERT INTO public.employees (id, email, name) VALUES (%s, 'bot@test.invalid', 'The Oracle')",
        (bot_id,),
    )
    db.commit()
    bot = _person(db, "The Oracle")
    _question(db, "What should the oracle be asked next?", [bot])
    _connect()

    result = run_interview_tick()
    assert sent == []
    assert result["unrouted"] == 1
    db.execute("DELETE FROM public.employees WHERE id = %s", (bot_id,))
    db.commit()


def test_weekly_cap(db: Any, enabled: None, sent: list[tuple[str, str]]) -> None:
    """Owner 2026-11-10: the weekly per-person quota stays on top of the pacing."""
    person = _person(db, EMPLOYEE_NAME)
    for n in range(4):
        _question(db, f"Question {n}?", [person])
    _connect()
    for _ in range(4):
        run_interview_tick()
        db.execute("UPDATE cmap.open_question SET state = 'answered' WHERE state = 'asked'")
        db.commit()
    assert len(sent) == 2


def test_unvetted_question_is_never_sent(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    _question(db, "Never checked?", [person], priority=None)
    _connect()
    assert run_interview_tick()["asked"] == 0
    assert sent == []


def test_vetted_question_goes_to_its_department_not_a_bystander(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """Owner 2026-11-10: licensing questions go to Licensing, not whoever is in the area."""
    bystander = _person(db, "Test Admin")
    db.execute(
        "INSERT INTO cmap.employee_flags (employee_id, department) VALUES (%s, 'Licensing') "
        "ON CONFLICT (employee_id) DO UPDATE SET department = 'Licensing'",
        (EMPLOYEE_ID,),
    )
    db.commit()
    _question(db, "Who signs licensing approvals?", [bystander], department="licensing")
    _question(db, "Nobody fits this one?", [bystander], department="")
    _connect()
    handle_inbound(email="admin@test.invalid", conversation_ref=CONVERSATION_REF, text="hi")

    result = run_interview_tick()
    assert [employee for employee, _ in sent] == [EMPLOYEE_ID]
    assert result["unrouted"] == 1


def test_more_important_question_goes_first(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    _question(db, "Minor detail?", [person], priority=3)
    _question(db, "Core gap?", [person], priority=5)
    _connect()
    run_interview_tick()
    assert sent == [(EMPLOYEE_ID, MESSAGE_TEMPLATE.format(question="Core gap?"))]


def test_unrelated_reply_is_not_saved_as_the_answer(
    db: Any, enabled: None, sent: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner 2026-11-10: a reply about something else must not become the answer."""
    from brain.interview import inbound as inbound_mod

    person = _person(db, EMPLOYEE_NAME)
    qid = _question(db, "Who approves samples?", [person])
    _connect()
    run_interview_tick()
    monkeypatch.setattr(inbound_mod, "classify_reply", lambda question, reply: "other")
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="thanks")
    assert _states(db)[qid] == "asked"

    monkeypatch.setattr(inbound_mod, "classify_reply", lambda question, reply: "dont_know")
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="No idea, not my area."
    )
    assert reply["reply"] == inbound_mod.REPLY_SKIPPED
    assert _states(db)[qid] == "open"


def test_late_reply_matched_to_right_question(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F4: model judgement picks the question a late reply answers, not recency.

    Also: an open volunteered thread never swallows that reply, and a reply
    whose judging fails is held (question stays pending) instead of being
    filed as the answer.
    """
    from brain.interview import inbound as inbound_mod

    real_classify_reply = inbound_mod.classify_reply
    person = _person(db, EMPLOYEE_NAME)
    older = _question(db, "Who signs the licensor approval form?", [person])
    newer = _question(db, "Who packs the sample boxes?", [person])
    # Both sit in the asked state (legacy multi-pending data): the reply below
    # belongs to the OLDER question, so recency alone would file it wrong.
    db.execute(
        "UPDATE cmap.open_question SET state = 'asked', target_employee_id = %s, "
        "asked_at = now() - make_interval(days => 2) WHERE id = %s",
        (EMPLOYEE_ID, older),
    )
    db.execute(
        "UPDATE cmap.open_question SET state = 'asked', target_employee_id = %s, "
        "asked_at = now() - make_interval(days => 1) WHERE id = %s",
        (EMPLOYEE_ID, newer),
    )
    db.commit()

    def _match(questions: list[str], reply: str) -> int | None:
        key = "licensor" if "Jessica" in reply else "sample" if "Marcus" in reply else ""
        if not key:
            return None
        for i, question in enumerate(questions):
            if key in question:
                return i
        return None

    monkeypatch.setattr(inbound_mod, "match_reply", _match)
    monkeypatch.setattr(
        inbound_mod, "classify_reply", lambda question, reply: "answer" if "Jessica" in reply else "other"
    )
    # An open volunteered thread is waiting; it must not swallow the reply.
    opened = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    assert "intake_id" in opened

    reply = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="Jessica signs the licensor approval form.",
    )
    assert reply["handled"] is True
    assert reply["reply"] == REPLY_ANSWERED
    assert reply["question_id"] == older
    assert _states(db) == {older: "answered", newer: "asked"}
    (turns,) = db.execute(
        "SELECT turns FROM cmap.teams_intake WHERE id = %s", (opened["intake_id"],)
    ).fetchone()
    assert all("Jessica" not in str(turn.get("text", "")) for turn in turns)

    # The reply judge being down holds the reply: nothing is filed as an answer.
    monkeypatch.setattr(inbound_mod, "classify_reply", real_classify_reply)
    monkeypatch.setattr(inbound_mod, "stage_model", lambda settings, stage: None)
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="Marcus packs the sample boxes.",
    )
    assert reply.get("question_id") is None
    assert reply.get("source_id") is None
    assert _states(db) == {older: "answered", newer: "asked"}


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
    """F4: a judged answer becomes a transcript source in the read pipeline."""
    from brain.interview import inbound as inbound_mod

    fake_embeddings(monkeypatch)
    monkeypatch.setattr(inbound_mod, "classify_reply", lambda question, reply: "answer")
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
    assert [speaker for speaker, _ in chunks] == [
        "The Oracle", EMPLOYEE_NAME, "The Oracle", EMPLOYEE_NAME
    ]
    assert "job title" in chunks[0][1]
    assert "Designer in Design" in chunks[1][1]
    assert "licensor approval form" in chunks[2][1]
    assert answer in chunks[3][1]

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
    assert set(_states(db).values()) == {"open"}


def test_never_messaged_employee_is_still_asked(
    db: Any, enabled: None, sent: list[tuple[str, str]]
) -> None:
    """No stored conversation no longer hides the employee from the tick.

    Measured 2026-11-04: 11 Teams-licensed employees (Violette Avouac
    among them) kept the Oracle app but never got a question because
    their install conversation update never arrived. The web layer now
    opens the 1:1 chat itself at first send.
    """
    person = _person(db, EMPLOYEE_NAME)
    _question(db, "Who approves samples?", [person])
    result = run_interview_tick()
    assert result == {"enabled": True, "asked": 1, "unrouted": 0, "failed": 0}
    assert [employee_id for employee_id, _ in sent] == [EMPLOYEE_ID]
    assert set(_states(db).values()) == {"asked"}


def test_unreachable_target_moves_the_question_on(
    db: Any, enabled: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target the bot cannot open any Teams chat for never blocks a question."""
    sent: list[tuple[str, str]] = []

    def _post(employee_id: str, text: str, settings: Any) -> None:
        del settings
        if employee_id == EMPLOYEE_ID:
            raise tick_mod.InterviewUnreachableError("no Teams chat")
        sent.append((employee_id, text))

    monkeypatch.setattr(tick_mod, "_post_proactive", _post)
    person = _person(db, EMPLOYEE_NAME)
    admin = _person(db, "Test Admin")
    _relate(db, person, admin, sources=2)
    qid = _question(db, "Why does approval stall between these two?", [person, admin])
    _connect()
    handle_inbound(email="admin@test.invalid", conversation_ref=CONVERSATION_REF, text="hi")

    first = run_interview_tick()
    skipped = db.execute(
        "SELECT skipped_by FROM cmap.open_question WHERE id = %s", (qid,)
    ).fetchone()
    if first["failed"]:
        assert EMPLOYEE_ID in [str(item) for item in (skipped[0] or [])]
        second = run_interview_tick()
        assert second["asked"] == 1
    assert [employee_id for employee_id, _ in sent] == [ADMIN_ID]


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


def test_work_email_matches_identity_row(db: Any) -> None:
    """A Teams message from the work address matches via employee_identities.

    Measured 2026-11-02: the owner's "hi" from Teams carried the work
    address while employees.email held a personal one, so the intake
    matched nobody and recorded nothing.
    """
    row = db.execute(
        "SELECT id::text FROM public.employees WHERE email = %s",
        (EMPLOYEE_EMAIL,),
    ).fetchone()
    employee_id = str(row[0])
    db.execute(
        "INSERT INTO public.employee_identities (id, employee_id, auth_user_id, email) "
        "VALUES ('00000000-0000-4000-8000-0000000000c3', %s, "
        "'00000000-0000-4000-8000-0000000000c2', 'Work.User@corp.test') "
        "ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email",
        (employee_id,),
    )
    db.execute("DELETE FROM cmap.teams_conversation")
    db.commit()

    result = handle_inbound(
        email="work.user@corp.test", conversation_ref=CONVERSATION_REF, text="hi"
    )
    assert result["reply"] == intake.REPLY_INTRO
    assert result["employee_id"] == employee_id
    stored = db.execute("SELECT count(*) FROM cmap.teams_conversation").fetchone()[0]
    assert stored == 1

def test_tenant_sender_auto_registers(db: Any) -> None:
    """A first Teams message from an unknown @popcre.com sender registers them.

    Owner ruling 2026-11-02: every employee in the M365 tenant can feed
    information in.
    """
    result = handle_inbound(
        email="new.person@popcre.com",
        name="New Person",
        conversation_ref=CONVERSATION_REF,
        text="hi",
    )
    assert result["reply"].startswith(intake.REPLY_INTRO_SHORT)
    row = db.execute(
        "SELECT id::text, name FROM public.employees WHERE lower(email) = %s",
        ("new.person@popcre.com",),
    ).fetchone()
    assert row is not None
    assert result["employee_id"] == str(row[0])
    assert row[1] == "New Person"
    stored = db.execute(
        "SELECT count(*) FROM cmap.teams_conversation WHERE employee_id = %s",
        (row[0],),
    ).fetchone()[0]
    assert stored == 1


def test_personal_sender_is_not_auto_registered(db: Any) -> None:
    """Non-tenant addresses never auto-register (identity hygiene, not auth)."""
    result = handle_inbound(
        email="someone@gmail.com",
        conversation_ref=CONVERSATION_REF,
        text="hi",
    )
    assert result["handled"] is False
    assert result["employee_id"] is None
    stored = db.execute(
        "SELECT count(*) FROM public.employees WHERE lower(email) = %s",
        ("someone@gmail.com",),
    ).fetchone()[0]
    assert stored == 0


def test_conversation_lookup_works_while_interviews_off(
    db: Any, client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The write-back lookup is not gated on the interviews switch.

    The owner's two-way Teams test (2026-11-02) needed the bot to answer
    while outbound interviews stay off; the ask tick gates itself.
    """
    from conftest import TEST_TOKEN

    monkeypatch.setattr(get_settings(), "brain_interview_enabled", False)
    _connect()
    response = client.get(
        f"/interview/teams/conversation/{EMPLOYEE_ID}",
        headers={"x-brain-token": TEST_TOKEN},
    )
    assert response.status_code == 200
    assert response.json()["conversation_ref"]


def test_lookup_carries_identity_without_a_conversation(client: Any) -> None:
    """The lookup returns identity and a null reference when no chat is stored.

    The web layer needs the emails to open the 1:1 chat itself, and the
    tenant service URL to open it on the right Bot Connector endpoint.
    """
    from conftest import TEST_TOKEN

    headers = {"x-brain-token": TEST_TOKEN}
    body = client.get(
        f"/interview/teams/conversation/{EMPLOYEE_ID}", headers=headers
    ).json()
    assert body["conversation_ref"] is None
    assert body["name"] == EMPLOYEE_NAME
    assert body["emails"][0] == EMPLOYEE_EMAIL
    assert body["service_url"] is None

    stored = client.post(
        "/interview/teams/conversation",
        json={"employee_id": EMPLOYEE_ID, "conversation_ref": CONVERSATION_REF},
        headers=headers,
    )
    assert stored.status_code == 200
    body = client.get(
        f"/interview/teams/conversation/{EMPLOYEE_ID}", headers=headers
    ).json()
    assert body["conversation_ref"] == CONVERSATION_REF
    assert body["service_url"] == CONVERSATION_REF["serviceUrl"]

    assert (
        client.post(
            "/interview/teams/conversation",
            json={"employee_id": EMPLOYEE_ID, "conversation_ref": CONVERSATION_REF},
        ).status_code
        == 401
    )
    assert (
        client.get("/interview/teams/conversation/00000000-0000-4000-8000-0000000000ff", headers=headers).status_code
        == 404
    )


VOLUNTEERED = (
    "When a licensor sends back artwork comments I log them in the tracker "
    "and pass the file to Dana in production for the revision."
)


def test_greeting_gets_intro(db: Any) -> None:
    """A bare greeting gets a one-line intro that invites a contribution."""
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Hi!")
    assert reply["handled"] is True
    assert reply["reply"] == intake.REPLY_INTRO
    assert db.execute("SELECT count(*) FROM cmap.teams_intake").fetchone()[0] == 0


def test_short_non_greeting_falls_through(db: Any) -> None:
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="what can you do")
    assert reply["handled"] is False


def test_join_still_reaches_meeting_helper(db: Any) -> None:
    """Join requests fall through to the meeting helper, even mid-thread."""
    join = "join https://teams.microsoft.com/l/meetup-join/abc please and thank you very much indeed friend"
    assert handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=join)[
        "handled"
    ] is False
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    assert handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="join")[
        "handled"
    ] is False


def test_group_chat_is_not_intake(db: Any) -> None:
    ref = {**CONVERSATION_REF, "conversation": {"id": "19:x", "conversationType": "groupChat"}}
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=ref, text=VOLUNTEERED)
    assert reply["handled"] is False


def test_group_chat_reference_never_stored(db: Any) -> None:
    """F4: only a personal chat may become the bot's write-back target."""
    group = {**CONVERSATION_REF, "conversation": {"id": "19:x", "conversationType": "groupChat"}}
    meeting = {**CONVERSATION_REF, "conversation": {"id": "19:y", "conversationType": "channel"}}
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=group, text="hi")
    assert db.execute("SELECT count(*) FROM cmap.teams_conversation").fetchone()[0] == 0

    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="hi")
    row = db.execute(
        "SELECT conversation_ref->'conversation'->>'id' FROM cmap.teams_conversation "
        "WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone()
    assert row == ("a:test-conversation",)

    # A later group/meeting message must never overwrite the personal chat.
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=group, text=VOLUNTEERED)
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=meeting, text=VOLUNTEERED)
    row = db.execute(
        "SELECT conversation_ref->'conversation'->>'id' FROM cmap.teams_conversation "
        "WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone()
    assert row == ("a:test-conversation",)


def test_volunteer_becomes_source(db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Volunteered messages buffer into one thread; "done" ingests one transcript."""
    fake_embeddings(monkeypatch)
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    assert first["handled"] is True
    assert first["reply"] == intake.REPLY_ACK
    second = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Dana usually turns it in two days."
    )
    assert second["handled"] is True
    assert second["intake_id"] == first["intake_id"]
    done = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Done.")
    assert done["reply"] == intake.REPLY_DONE
    source_id = done["source_id"]
    title, kind = db.execute(
        "SELECT title, kind FROM cmap.source WHERE id = %s", (source_id,)
    ).fetchone()
    assert kind == "transcript"
    assert title.startswith(f"Teams contribution — {EMPLOYEE_NAME} — ")
    state = db.execute(
        "SELECT state, source_id::text FROM cmap.teams_intake WHERE id = %s", (first["intake_id"],)
    ).fetchone()
    assert state == ("closed", source_id)
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
    assert {speaker for speaker, _ in chunks} == {EMPLOYEE_NAME, "The Oracle"}
    hint = db.execute("SELECT department_hint FROM cmap.source WHERE id = %s", (source_id,)).fetchone()
    assert hint == ("Design",)
    joined = " ".join(text for _, text in chunks)
    assert "licensor sends back artwork" in joined
    assert "two days" in joined


def test_silent_thread_closes(db: Any, storage: Any) -> None:
    """After 20 quiet minutes the worker sweep ingests the thread."""
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    assert intake.close_stale_threads() == []
    db.execute(
        "UPDATE cmap.teams_intake SET last_at = now() - interval '21 minutes' WHERE id = %s",
        (first["intake_id"],),
    )
    db.commit()
    closed = intake.close_stale_threads()
    assert len(closed) == 1
    assert intake.close_stale_threads() == []
    assert db.execute("SELECT count(*) FROM cmap.source").fetchone()[0] == 1


def test_failed_ingest_retries_then_succeeds(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient ingest failure is retried by the sweep and then becomes one source."""
    calls = {"n": 0}
    real_ingest = intake.ingest_bytes

    def flaky(**kwargs: Any) -> dict[str, Any]:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("The read operation timed out")
        return real_ingest(**kwargs)

    monkeypatch.setattr(intake, "ingest_bytes", flaky)
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    db.execute(
        "UPDATE cmap.teams_intake SET last_at = now() - interval '21 minutes' WHERE id = %s",
        (first["intake_id"],),
    )
    db.commit()
    assert intake.close_stale_threads() == []
    state, attempts, error, next_retry_at = db.execute(
        "SELECT state, retry_count, error, next_retry_at FROM cmap.teams_intake WHERE id = %s",
        (first["intake_id"],),
    ).fetchone()
    assert state == "failed"
    assert attempts == 1
    assert "timed out" in error
    assert next_retry_at is not None
    assert intake.close_stale_threads() == []
    db.execute("UPDATE cmap.teams_intake SET next_retry_at = now() WHERE id = %s", (first["intake_id"],))
    db.commit()
    closed = intake.close_stale_threads()
    assert len(closed) == 1
    row = db.execute(
        "SELECT state, retry_count, source_id::text, error FROM cmap.teams_intake WHERE id = %s",
        (first["intake_id"],),
    ).fetchone()
    assert row == ("closed", 2, closed[0], None)
    assert calls["n"] == 2
    assert db.execute("SELECT count(*) FROM cmap.source").fetchone()[0] == 1
    assert intake.close_stale_threads() == []
    assert db.execute("SELECT count(*) FROM cmap.source").fetchone()[0] == 1


def test_permanent_ingest_failure_is_not_retried(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-transient ingest failure is left ``failed`` at once, with no retry."""

    def boom(**kwargs: Any) -> dict[str, Any]:
        raise ValueError("bad contribution payload")

    monkeypatch.setattr(intake, "ingest_bytes", boom)
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    db.execute(
        "UPDATE cmap.teams_intake SET last_at = now() - interval '21 minutes' WHERE id = %s",
        (first["intake_id"],),
    )
    db.commit()
    assert intake.close_stale_threads() == []
    state, attempts, error, next_retry_at = db.execute(
        "SELECT state, retry_count, error, next_retry_at FROM cmap.teams_intake WHERE id = %s",
        (first["intake_id"],),
    ).fetchone()
    assert state == "failed"
    assert attempts == 1
    assert "bad contribution payload" in error
    assert next_retry_at is None
    assert intake.close_stale_threads() == []


def test_retry_budget_ends_failed_with_last_error(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Five transient failures leave the thread ``failed`` with the last error."""

    def boom(**kwargs: Any) -> dict[str, Any]:
        raise httpx.ReadTimeout("The read operation timed out")

    monkeypatch.setattr(intake, "ingest_bytes", boom)
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    for _ in range(intake.MAX_ATTEMPTS):
        db.execute(
            "UPDATE cmap.teams_intake SET last_at = now() - interval '21 minutes', "
            "next_retry_at = now() WHERE id = %s",
            (first["intake_id"],),
        )
        db.commit()
        assert intake.close_stale_threads() == []
    state, attempts, error, next_retry_at = db.execute(
        "SELECT state, retry_count, error, next_retry_at FROM cmap.teams_intake WHERE id = %s",
        (first["intake_id"],),
    ).fetchone()
    assert state == "failed"
    assert attempts == intake.MAX_ATTEMPTS
    assert "timed out" in error
    assert next_retry_at is None
    assert intake.close_stale_threads() == []


@pytest.fixture()
def stub_model(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace the conversation model; tests set ``reply`` and read ``prompts``."""
    from brain.interview import followup

    state: dict[str, Any] = {"reply": "Who do you hand the revised file to?", "prompts": []}

    def _fake(messages: list[dict[str, str]]) -> str:
        state["prompts"].append(messages[-1]["content"])
        return str(state["reply"])

    monkeypatch.setattr(followup, "_call_model", _fake)
    return state


def test_followups_capped_at_two(db: Any, storage: Any, stub_model: dict[str, Any]) -> None:
    """At most two follow-ups per thread; they are kept in the transcript."""
    from brain.interview import followup

    replies = [
        handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=text)["reply"]
        for text in (VOLUNTEERED, "Production gets it next.", "It takes two days usually.")
    ]
    assert "Who do you hand the revised file to?" in replies[0]
    assert "Who do you hand the revised file to?" in replies[1]
    assert replies[2] == intake.REPLY_ACK
    assert len(stub_model["prompts"]) == 2
    done = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="done")
    turns = db.execute(
        "SELECT turns FROM cmap.teams_intake WHERE source_id = %s", (done["source_id"],)
    ).fetchone()[0]
    speakers = [turn["speaker"] for turn in turns]
    assert speakers == [EMPLOYEE_NAME, followup.ORACLE_SPEAKER, EMPLOYEE_NAME,
                        followup.ORACLE_SPEAKER, EMPLOYEE_NAME]


def test_followup_cites_no_invented_names(db: Any, stub_model: dict[str, Any]) -> None:
    """Judge check: a follow-up naming someone absent from the chat and Map is dropped."""
    from brain.interview import followup

    dana = _person(db, "Dana")
    tracker = _thing(db, "Artwork Tracker")
    _relate(db, dana, tracker, 1)

    stub_model["reply"] = "Does Dana hand it to Marcus afterwards?"
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    assert first["reply"] == intake.REPLY_ACK
    assert "Dana (Person)" in stub_model["prompts"][0]
    assert "Dana OWNS Artwork Tracker" in stub_model["prompts"][0]

    stub_model["reply"] = "Does Dana record the revision in the Artwork Tracker?"
    second = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Dana then starts the revision."
    )
    assert "Artwork Tracker" in second["reply"]
    allowed = VOLUNTEERED + " Dana then starts the revision. " + "\n".join(stub_model["prompts"])
    assert followup.invented_names(second["reply"], allowed) == set()


def test_followup_model_failure_still_acknowledges(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    from brain.interview import followup

    def _boom(messages: list[dict[str, str]]) -> str:
        raise RuntimeError("model down")

    monkeypatch.setattr(followup, "_call_model", _boom)
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    assert reply["reply"] == intake.REPLY_ACK
def test_overview_lists_contributions(
    db: Any, client: Any, storage: Any, admin_headers: dict[str, str]
) -> None:
    """Phase 5: the admin page lists Teams contributions with their source link."""
    text = (
        "When a licensor sends back artwork comments I log them in the tracker "
        "and pass the file to production for the revision."
    )
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=text)
    done = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="done")
    body = client.get("/interview/overview", headers=admin_headers).json()
    [item] = body["contributions"]
    assert item["id"] == first["intake_id"]
    assert item["name"] == EMPLOYEE_NAME
    assert item["state"] == "closed"
    assert item["turns"] == 1
    assert item["source_id"] == done["source_id"]
    assert item["preview"].startswith("When a licensor")
def test_quiet_hours_window() -> None:
    """Phase 3: nights 8 PM–8 AM New York time and weekends are quiet."""
    from datetime import datetime

    from brain.interview.tick import EASTERN, in_quiet_hours

    def at(day: int, hour: int) -> datetime:
        return datetime(2026, 11, day, hour, 30, tzinfo=EASTERN)  # 2 Nov 2026 is a Monday

    assert in_quiet_hours(at(3, 7)) is True
    assert in_quiet_hours(at(3, 8)) is False
    assert in_quiet_hours(at(3, 19)) is False
    assert in_quiet_hours(at(3, 20)) is True
    assert in_quiet_hours(at(7, 12)) is True  # Saturday
    assert in_quiet_hours(at(8, 12)) is True  # Sunday


def test_tick_sends_nothing_in_quiet_hours(
    db: Any, enabled: None, sent: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    person = _person(db, EMPLOYEE_NAME)
    _question(db, "Who approves samples?", [person])
    _connect()
    monkeypatch.setattr(tick_mod, "in_quiet_hours", lambda now=None: True)
    result = run_interview_tick()
    assert result["quiet_hours"] is True
    assert sent == []



def _forget_profile(db: Any) -> None:
    db.execute("DELETE FROM cmap.employee_flags WHERE employee_id = %s", (EMPLOYEE_ID,))
    db.commit()


def test_first_greeting_asks_department_and_title(
    db: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Owner direction 2026-11-03: the bot asks department and job title first."""
    from brain.interview import profile

    _forget_profile(db)
    monkeypatch.setattr(profile, "is_profile_answer", lambda text: True)
    monkeypatch.setattr(profile, "_split", lambda text: ("Licensing", "Licensing Coordinator"))
    hello = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="hi")
    assert profile.PROFILE_QUESTION in hello["reply"]
    answer = handle_inbound(
        email=EMPLOYEE_EMAIL,
        conversation_ref=CONVERSATION_REF,
        text="I'm a licensing coordinator in the licensing team",
    )
    assert answer["profile"] is True
    assert "Licensing Coordinator, Licensing" in answer["reply"]
    row = db.execute(
        "SELECT department, job_title, profile_answer FROM cmap.employee_flags WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone()
    assert row == ("Licensing", "Licensing Coordinator", "I'm a licensing coordinator in the licensing team")
    again = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="hi")
    assert again["reply"] == intake.REPLY_INTRO


def test_profile_kept_raw_when_model_unavailable(db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from brain.interview import profile

    _forget_profile(db)
    monkeypatch.setattr(profile, "is_profile_answer", lambda text: True)
    monkeypatch.setattr(profile, "_split", lambda text: (None, None))
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="hello")
    reply = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Sales, account manager")
    assert reply["reply"] == profile.REPLY_PROFILE_THANKS_RAW
    assert profile.department_hint(EMPLOYEE_ID) == "Sales, account manager"


def test_first_contribution_asks_profile_and_keeps_content(
    db: Any, storage: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first message of real content is kept and the profile question follows."""
    from brain.interview import profile

    _forget_profile(db)
    monkeypatch.setattr(profile, "is_profile_answer", lambda text: "planner" in text.casefold())
    monkeypatch.setattr(profile, "_split", lambda text: ("Production", "Planner"))
    first = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text=VOLUNTEERED)
    assert profile.PROFILE_QUESTION in first["reply"]
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="Production planner")
    done = handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="done")
    hint = db.execute(
        "SELECT department_hint FROM cmap.source WHERE id = %s", (done["source_id"],)
    ).fetchone()
    assert hint == ("Production",)


def test_thanks_is_not_a_profile(db: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """F4: only a judge-confirmed job/department becomes the profile."""
    from brain.interview import profile

    real_is_profile_answer = profile.is_profile_answer
    _forget_profile(db)
    monkeypatch.setattr(
        profile,
        "is_profile_answer",
        lambda text: "coordinator" in text.casefold() or "manager" in text.casefold(),
    )
    monkeypatch.setattr(profile, "_split", lambda text: ("Licensing", "Licensing Coordinator"))
    handle_inbound(email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="hi")

    reply = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="thanks, that helps!"
    )
    assert reply.get("profile") is not True
    assert reply["reply"] != profile.REPLY_PROFILE_THANKS
    assert reply["reply"] != profile.REPLY_PROFILE_THANKS_RAW
    assert db.execute(
        "SELECT department, job_title, profile_answer FROM cmap.employee_flags "
        "WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone() == (None, None, None)

    # Unjudged (the judging model is down) is never accepted as a profile.
    monkeypatch.setattr(profile, "is_profile_answer", real_is_profile_answer)
    monkeypatch.setattr(profile, "stage_model", lambda settings, stage: None)
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="sales manager"
    )
    assert reply.get("profile") is not True

    # A real job line is accepted.
    monkeypatch.setattr(profile, "is_profile_answer", lambda text: True)
    reply = handle_inbound(
        email=EMPLOYEE_EMAIL, conversation_ref=CONVERSATION_REF, text="licensing coordinator"
    )
    assert reply["profile"] is True
    assert db.execute(
        "SELECT department, job_title FROM cmap.employee_flags WHERE employee_id = %s",
        (EMPLOYEE_ID,),
    ).fetchone() == ("Licensing", "Licensing Coordinator")
