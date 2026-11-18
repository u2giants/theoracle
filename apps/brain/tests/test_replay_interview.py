"""The Step 6 replay script is a check: it fails on old, fallback or invented replies."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from brain.config import Settings
from brain.interview import converse, followup

_SPEC = importlib.util.spec_from_file_location(
    "replay_interview",
    Path(__file__).resolve().parents[1] / "scripts" / "replay_interview.py",
)
replay_interview = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(replay_interview)  # type: ignore[union-attr]


@pytest.fixture
def no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converse, "_employee", lambda conn, eid: ("Albert", "en"))
    monkeypatch.setattr(followup, "map_context", lambda conn, text: [])
    monkeypatch.setattr(converse, "_clarified", lambda *a: "Who signs off the concept?")


def _run(monkeypatch: pytest.MonkeyPatch, out: dict[str, Any]) -> int:
    monkeypatch.setattr(converse, "_call", lambda *a, **k: out)
    return replay_interview.replay(None, Settings())


def test_good_replies_pass(monkeypatch: pytest.MonkeyPatch, no_db: None) -> None:
    out = {
        "reflect": "So it lives in the item library.",
        "action": "next_question",
        "text": "Thanks.",
        "question_index": 1,
    }
    assert _run(monkeypatch, out) == 0


def test_fallback_fails(monkeypatch: pytest.MonkeyPatch, no_db: None) -> None:
    assert _run(monkeypatch, {}) == 1


def test_invented_name_fails(monkeypatch: pytest.MonkeyPatch, no_db: None) -> None:
    out = {
        "reflect": "Got it.",
        "action": "followup",
        "text": "Does Maria Gonzalez in Shipwell handle that?",
    }
    assert _run(monkeypatch, out) == 1


def test_old_fixed_string_fails() -> None:
    bad = replay_interview.problems(
        {"text": replay_interview.OLD_REPLY, "action": "close", "path": "model"},
        "q",
        "a",
        "answer",
    )
    assert bad
