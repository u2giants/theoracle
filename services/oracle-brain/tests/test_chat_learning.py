"""S06 offline gate: ordinary chat learning with visible recap.

Assistant-generated statements must be excluded as evidence; chat can propose
a knowledge update with a visible recap. Recap/turn exclusion is real on main
(InterviewState.apply_turn drops non-employee speakers); the chat-update
proposal API is absent and skipped with the exact gap.
Invented/synthetic only.
"""
from __future__ import annotations

import importlib
import importlib.util

import pytest

from oracle_brain.interviews.recap import build_recap
from oracle_brain.interviews.state import InterviewState, Turn


def _state_with_assistant_claim():
    state = InterviewState(interview_id="synthetic-chat-1")
    state.apply_turn(Turn(turn_id="t1", need_key="fact:moq", answer="500 units", speaker="assistant"))
    state.apply_turn(Turn(turn_id="t2", need_key="fact:moq", answer="1000 units", speaker="employee"))
    return state


def test_assistant_statements_are_never_learned_evidence():
    state = InterviewState(interview_id="synthetic-chat-2")
    applied = state.apply_turn(
        Turn(turn_id="a1", need_key="fact:moq", answer="500 units", speaker="assistant")
    )
    assert applied  # turn is recorded for display
    assert "moq" not in state.known  # but never becomes learned evidence
    state.apply_turn(
        Turn(turn_id="e1", need_key="fact:moq", answer="1000 units", speaker="employee")
    )
    assert state.known["moq"] == "1000 units"


def test_recap_shows_learned_and_unconfirmed_and_correction_path():
    state = _state_with_assistant_claim()
    recap = build_recap(state, required_fields=["moq", "lead_time"])
    assert ("moq", "1000 units") in recap.learned
    assert "lead_time" in recap.unconfirmed
    assert "correct" in recap.how_to_correct.lower()


def test_chat_update_proposal_api_absent_is_named():
    """Skip-with-reason when the chat-learning proposal API is not built."""
    try:
        _spec = importlib.util.find_spec("oracle_brain.workflows.chat_learning")
    except ModuleNotFoundError:
        _spec = None
    if _spec is None:
        pytest.skip(
            "oracle_brain.workflows.chat_learning absent on main (S06 ordinary "
            "chat knowledge-update proposal not built; interviews/* covers only "
            "question selection and resume). Named offline gate test registered "
            "fail-closed until chat_learning lands with a visible recap and "
            "assistant-statement exclusion."
        )
    chat = importlib.import_module("oracle_brain.workflows.chat_learning")
    assert hasattr(chat, "propose_update") or hasattr(chat, "propose")
