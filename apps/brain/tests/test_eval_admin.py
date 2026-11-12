"""Repair plan B1 gate: owner-approved eval questions.

Only approved, not-retired questions count toward the eval bar; the admin
actions are approve, edit and retire; the B1 draft batch loads as unapproved
drafts and meets the owner's coverage requirements (two per business
function, five cross-function, five "the documents do not say" questions).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from brain.config import get_settings
from brain.eval import run as eval_mod
from brain.eval.run import B1_SEED_PATH, load_questions, load_seed

SEED_PATH = Path(__file__).resolve().parents[1] / "eval" / "questions.seed.json"

FUNCTIONS = [
    "Sales & Customer Accounts",
    "Licensing",
    "Product Design & Development",
    "Sourcing & Vendor Management",
    "Sampling",
    "Production & Quality",
    "Logistics & Shipping",
    "Compliance & Testing",
    "Finance & Accounting",
    "IT & Systems",
    "HR & Administration",
    "China Office Operations",
    "Executive/Company-wide",
]


@pytest.fixture()
def eval_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("BRAIN_SCALEDOWN_ENABLED", "true")
    monkeypatch.setenv("SCALEDOWN_API_KEY", "test-scaledown-key")
    monkeypatch.setenv("BRAIN_FRONTIER_MODEL", "test/frontier-model")
    monkeypatch.setenv("BRAIN_CHAT_MODEL", "test/chat-model")
    monkeypatch.setenv("BRAIN_EVAL_MODEL", "test/eval-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_only_approved_count(
    eval_env: None, monkeypatch: pytest.MonkeyPatch, db: Any
) -> None:
    """run_eval scores only approved questions; drafts and retired ones are
    never evaluated (the plan B1 bar)."""
    del eval_env
    seen: list[str] = []

    def fake_evaluate(item: dict[str, Any], settings: Any, usage: dict[str, int]):
        del settings, usage
        seen.append(item["question"])
        return {
            "question_id": item["id"],
            "question": item["question"],
            "score": 1.0,
            "score_legacy": 1.0,
            "error": None,
        }

    monkeypatch.setattr(eval_mod, "evaluate_question", fake_evaluate)
    db.execute(
        "INSERT INTO cmap.eval_question (question, expected_points, "
        "expected_source_titles, author, approved_at) VALUES (%s, %s, %s, "
        "'seed', now())",
        ("Approved question?", ["a", "b", "c"], ["t.pdf"]),
    )
    db.execute(
        "INSERT INTO cmap.eval_question (question, expected_points, "
        "expected_source_titles, author) VALUES (%s, %s, %s, 'seed')",
        ("Draft question?", ["a", "b", "c"], ["t.pdf"]),
    )
    db.execute(
        "INSERT INTO cmap.eval_question (question, expected_points, "
        "expected_source_titles, author, approved_at, retired_at) VALUES "
        "(%s, %s, %s, 'seed', now(), now())",
        ("Retired question?", ["a", "b", "c"], ["t.pdf"]),
    )
    db.commit()
    run = eval_mod.run_eval()
    assert seen == ["Approved question?"]
    assert [item["question"] for item in run["results"]] == ["Approved question?"]
    assert run["mean_score"] == 1.0
    assert [item["question"] for item in load_questions()] == ["Approved question?"]


def test_admin_approve_edit_retire_actions(
    eval_env: None,
    db: Any,
    client: Any,
    admin_headers: dict[str, str],
    user_headers: dict[str, str],
) -> None:
    """Approve stamps approved_at, edit rewrites the wording, retire stamps
    retired_at and drops the question from the scored set."""
    del eval_env, db
    body = {
        "question": "Who signs the artwork log?",
        "expected_points": ["The licensing manager", "The artwork log", "Before the PO"],
        "expected_source_titles": ["licensing-approval-procedure.pdf"],
        "recommendation": "Approve as written.",
    }
    assert (
        client.post("/eval/questions", json=body, headers=user_headers).status_code
        == 403
    )
    question_id = client.post(
        "/eval/questions", json=body, headers=admin_headers
    ).json()["id"]
    listed = client.get("/eval/questions", headers=user_headers).json()["questions"]
    row = next(item for item in listed if item["id"] == question_id)
    assert row["approved_at"] is None
    assert row["retired_at"] is None
    assert row["abstention"] is False
    assert row["recommendation"] == "Approve as written."

    assert (
        client.post(
            f"/eval/questions/{question_id}/approve", headers=user_headers
        ).status_code
        == 403
    )
    approved = client.post(
        f"/eval/questions/{question_id}/approve", headers=admin_headers
    ).json()
    assert approved["approved_at"] is not None
    first_stamp = approved["approved_at"]
    again = client.post(
        f"/eval/questions/{question_id}/approve", headers=admin_headers
    ).json()
    assert again["approved_at"] == first_stamp  # idempotent: first stamp wins

    edited = client.put(
        f"/eval/questions/{question_id}",
        json=dict(body, question="Who signs the artwork log each week?"),
        headers=admin_headers,
    )
    assert edited.status_code == 200
    listed = client.get("/eval/questions", headers=user_headers).json()["questions"]
    row = next(item for item in listed if item["id"] == question_id)
    assert row["question"] == "Who signs the artwork log each week?"

    retired = client.post(
        f"/eval/questions/{question_id}/retire", headers=admin_headers
    ).json()
    assert retired["retired_at"] is not None
    assert [item["question"] for item in load_questions()] == []


def test_b1_drafts_load_as_unapproved_drafts(eval_env: None, db: Any) -> None:
    """The B1 batch loads 30 drafts: unapproved, 5 abstention, 3-6 points
    each, recommendations present, and no duplicate of the seed set."""
    del eval_env
    assert load_seed(B1_SEED_PATH) == 30
    assert load_seed(B1_SEED_PATH) == 0
    rows = db.execute(
        "SELECT question, expected_points, abstention, recommendation, "
        "approved_at, retired_at FROM cmap.eval_question"
    ).fetchall()
    assert len(rows) == 30
    for question, points, abstention, recommendation, approved_at, retired_at in rows:
        assert 3 <= len(points) <= 6, question
        assert abstention is False or abstention is True
        assert approved_at is None and retired_at is None
        assert recommendation, question
    assert sum(1 for row in rows if row[2]) == 5
    seed_questions = {
        item["question"]
        for item in json.loads(SEED_PATH.read_text(encoding="utf-8"))["questions"]
    }
    b1_questions = {row[0] for row in rows}
    assert b1_questions & seed_questions == set()
    assert load_questions() == []


def test_b1_drafts_meet_function_coverage(eval_env: None) -> None:
    """Coverage (documented per the plan): at least two questions per
    business function, five cross-function, five abstention, total 30."""
    del eval_env
    items = json.loads(B1_SEED_PATH.read_text(encoding="utf-8"))["questions"]
    assert len(items) <= 30
    covered: dict[str, int] = {name: 0 for name in FUNCTIONS}
    cross = 0
    abstention = 0
    for item in items:
        tags = item["functions"]
        assert tags, item["question"]
        assert set(tags) <= set(FUNCTIONS), item["question"]
        for tag in tags:
            covered[tag] += 1
        if len(tags) >= 2:
            cross += 1
        if item.get("abstention"):
            abstention += 1
    for name in FUNCTIONS:
        assert covered[name] >= 2, f"{name} covered only {covered[name]} times"
    assert cross >= 5
    assert abstention == 5
