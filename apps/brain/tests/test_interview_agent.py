# ruff: noqa: F811  (pytest fixtures imported from the conversation tests)
"""The interview agent reads what a reply means and acts on it (plan_interview_agent.md).

The model is a queue of outputs at ``converse._call``; the directory lookup,
the referral and the colleague's opening message run on the real test database.
"""

from __future__ import annotations

from typing import Any

import pytest
from test_interview import (  # noqa: F401 - shared fixtures and helpers
    EMPLOYEE_ID,
    _clean_interviews,
    _office_hours,
    _states,
    enabled,
)
from test_interview_conversation import (  # noqa: F401
    _conv,
    _finish_chain,
    _kind,
    _open,
    _say,
    model,
    no_ingest,
    sent,
)

from brain.interview import converse
from brain.interview.converse import find_person, run_interview_reply
from brain.interview.strings import strings
from brain.interview.tick import run_interview_tick

JEN_A = "00000000-0000-4000-8000-0000000000c1"
JEN_B = "00000000-0000-4000-8000-0000000000c2"


@pytest.fixture()
def jens(db: Any) -> None:
    db.execute("DELETE FROM public.employees WHERE id = ANY(%s::uuid[])", ([JEN_A, JEN_B],))
    db.execute(
        "INSERT INTO public.employees (id, email, name, role) VALUES "
        "(%s, 'jen.a@test.invalid', 'Jennifer Chaffier', 'Sales'), "
        "(%s, 'jen.b@test.invalid', 'Jen Chaffier', NULL)",
        (JEN_A, JEN_B),
    )
    db.commit()


def _target(db: Any, qid: str) -> tuple[str | None, list[str], str]:
    row = db.execute(
        "SELECT target_employee_id::text, skipped_by::text[], why "
        "FROM cmap.open_question WHERE id = %s",
        (qid,),
    ).fetchone()
    return row[0], list(row[1] or []), str(row[2] or "")


def test_find_person_returns_both_duplicate_names(db: Any, jens: None) -> None:
    found = {p["employee_id"]: p["name"] for p in find_person(db, "Chaffier")}
    assert found == {JEN_A: "Jennifer Chaffier", JEN_B: "Jen Chaffier"}
    assert {p["employee_id"] for p in find_person(db, "Jen")} == {JEN_A, JEN_B}
    assert find_person(db, "Jennifer")[0]["employee_id"] == JEN_A
    assert find_person(db, "Chaffier", exclude=JEN_A)[0]["employee_id"] == JEN_B
    assert find_person(db, "") == []


def test_agent_looks_up_then_refers(
    db: Any, enabled: None, jens: None, sent: list[dict[str, Any]],
    model: list[dict[str, Any]], no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Ask Jen, she handles that.")
    model.extend([
        {"tool": "find_person", "query": "Jen"},
        {"reflect": "", "action": "refer", "employee_id": JEN_B,
         "text": "Thanks, I'll ask Jen Chaffier."},
    ])
    _finish_chain(db)
    result = run_interview_reply(_conv(db)[0])
    assert result["action"] == "refer"
    target, skipped, why = _target(db, ids[0])
    assert target == JEN_B and EMPLOYEE_ID in skipped and "[referred by" in why
    assert _states(db)[ids[0]] == "open"
    assert sent[-1]["text"].startswith("Thanks, I'll ask Jen Chaffier.")
    assert "Who signs off step 1?" in sent[-1]["text"]


def test_refer_reopens_a_question_already_marked_answered(
    db: Any, enabled: None, jens: None, sent: list[dict[str, Any]],
    model: list[dict[str, Any]], no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Live case (#604): "not sure, ask Adam or Jack" after a partial answer;
    # the answer step had already marked the question answered.
    ids = _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("The salesman. Not sure where it's recorded, ask Jennifer.")
    db.execute("UPDATE cmap.open_question SET state = 'answered' WHERE id = %s", (ids[0],))
    db.commit()
    model.extend([
        {"tool": "find_person", "query": "Jennifer"},
        {"reflect": "", "action": "refer", "employee_id": JEN_A,
         "text": "Thanks, I'll ask Jennifer Chaffier."},
    ])
    _finish_chain(db)
    db.execute("UPDATE cmap.open_question SET state = 'answered' WHERE id = %s", (ids[0],))
    db.commit()
    result = run_interview_reply(_conv(db)[0])
    assert result["action"] == "refer"
    target, skipped, why = _target(db, ids[0])
    assert target == JEN_A and skipped.count(EMPLOYEE_ID) == 1 and "[referred by" in why
    assert _states(db)[ids[0]] == "open"


def test_refer_to_unlooked_up_id_is_rejected(
    db: Any, enabled: None, jens: None, sent: list[dict[str, Any]],
    model: list[dict[str, Any]], no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Ask Jen.")
    bad = {"reflect": "", "action": "refer", "employee_id": JEN_A, "text": "I'll ask Jen."}
    model.extend([bad, bad])
    _finish_chain(db)
    result = run_interview_reply(_conv(db)[0])
    assert result["path"] == "fallback"
    assert _target(db, ids[0])[0] != JEN_A


def test_dont_know_naming_a_colleague_refers(
    db: Any, enabled: None, jens: None, sent: list[dict[str, Any]],
    model: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    ids = _open(db, sent)
    _kind(monkeypatch, "dont_know")
    reply = _say("No idea, Jennifer would know.")
    model.extend([
        {"tool": "find_person", "query": "Jennifer"},
        {"reflect": "", "action": "refer", "employee_id": JEN_A,
         "text": "Thanks, I'll ask Jennifer Chaffier."},
    ])
    run_interview_reply(reply["conversation_id"])
    assert _target(db, ids[0])[0] == JEN_A
    assert sent[-1]["text"] != strings("en").who_would_know


def test_dont_know_without_a_name_still_asks_who_would_know(
    db: Any, enabled: None, sent: list[dict[str, Any]],
    model: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "dont_know")
    reply = _say("No idea.")
    model.append({"reflect": "", "action": "next_question", "text": "x", "question_index": 1})
    run_interview_reply(reply["conversation_id"])
    assert sent[-1]["text"] == strings("en").who_would_know


def test_referred_question_opens_with_referrer(
    db: Any, enabled: None, jens: None, sent: list[dict[str, Any]],
    model: list[dict[str, Any]], no_ingest: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _open(db, sent)
    _kind(monkeypatch, "answer")
    _say("Ask Jen.")
    model.extend([
        {"tool": "find_person", "query": "Jen"},
        {"reflect": "", "action": "refer", "employee_id": JEN_B, "text": "I'll ask Jen Chaffier."},
    ])
    _finish_chain(db)
    run_interview_reply(_conv(db)[0])
    monkeypatch.setattr(converse, "_call", lambda *a, **k: {})
    run_interview_tick()
    to_jen = [c for c in sent if c["employee_id"] == JEN_B]
    assert to_jen, sent
    assert to_jen[0]["text"].endswith("") and "suggested you would know" in to_jen[0]["text"]
    assert "Who signs off step 0?" in to_jen[0]["text"]
