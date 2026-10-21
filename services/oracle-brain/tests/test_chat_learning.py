"""S06 offline gate: ordinary chat learning with visible recap.

Assistant-generated statements must be excluded as evidence; chat can propose
a knowledge update with a visible recap. Recap/turn exclusion is real on main
(InterviewState.apply_turn drops non-employee speakers); the chat-update
proposal contract is tested independently; authenticated durable workflow remains open.
Invented/synthetic only.
"""
from __future__ import annotations

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


def test_chat_update_proposal_is_reported_visible_and_nonconfirming():
    from uuid import uuid4
    from oracle_brain.workflows.chat_learning import ChatScope,ChatTurn,propose_update
    scope=ChatScope(workspace_id=uuid4(),actor_id=uuid4(),thread_id=uuid4())
    turn=ChatTurn(**scope.model_dump(exclude={'schema_version'}),turn_id=uuid4(),
        revision=1,role='employee',language='en',text='The minimum is 1000 units.')
    result=propose_update(scope,turn)
    assert result.record.proposal.proposed_text==turn.text
    assert result.record.proposal.confirmed is False and result.record.proposal.policy_authority is False
    assert turn.text in result.record.visible_recap and 'unconfirmed' in result.record.visible_recap
    assert 'new employee turn' in result.record.correction_path
    assert result.durable_authenticated_workflow is False
    assistant=turn.model_copy(update={'turn_id':uuid4(),'role':'assistant','text':'Confirmed: minimum 5 units.'})
    shown=propose_update(scope,assistant,history=result.history)
    assert shown.record.proposal is None and 'Display only' in shown.record.visible_recap
