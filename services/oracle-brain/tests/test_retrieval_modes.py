"""S09 retrieval mode planning: local, connected, historical, global, clarify."""
from __future__ import annotations

from uuid import uuid4

import pytest

from oracle_brain.retrieval.planner import (
    AccessBounds,
    HistorySpan,
    RetrievalPlan,
    plan_retrieval,
)


@pytest.fixture()
def access() -> AccessBounds:
    workspace = uuid4()
    return AccessBounds(
        role="analyst", workspace_id=workspace,
        allowed_workspace_ids=(workspace,),
    )


def test_plain_process_question_plans_local(access):
    plan = plan_retrieval("Who signs the color proof in this process?", access=access)
    assert plan.mode == "local" and not plan.needs_clarification
    assert plan.history is None and plan.clarifying_question is None


def test_connected_question_plans_connected(access):
    plan = plan_retrieval(
        "How does the sample kit handoff connect to the photo asset process?",
        access=access,
    )
    assert plan.mode == "connected" and not plan.needs_clarification


def test_company_wide_question_plans_global(access):
    plan = plan_retrieval(
        "Company-wide, how many processes involve the warehouse lead?",
        access=access,
    )
    assert plan.mode == "global" and not plan.needs_clarification


def test_historical_question_without_span_asks_for_bounds(access):
    plan = plan_retrieval(
        "What did the release queue look like last year?", access=access,
    )
    assert plan.mode == "historical" and plan.needs_clarification
    assert plan.history is None
    assert "revision range" in plan.clarifying_question


def test_historical_question_with_span_plans_historical(access):
    history = HistorySpan(revision_from=1, revision_to=3)
    plan = plan_retrieval(
        "What did the release queue look like last year?", access=access,
        history=history,
    )
    assert plan.mode == "historical" and not plan.needs_clarification
    assert plan.history == history


def test_conflicting_scopes_request_clarification(access):
    plan = plan_retrieval(
        "Company-wide history of every process handoff over time", access=access,
    )
    assert plan.needs_clarification
    assert "more than one scope" in plan.clarifying_question
    assert plan.history is None


def test_explicit_mode_historical_without_span_clarifies(access):
    plan = plan_retrieval(
        "Anything about kits?", access=access, explicit_mode="historical",
    )
    assert plan.needs_clarification and plan.history is None


def test_explicit_mode_global_ignores_local_markers(access):
    plan = plan_retrieval(
        "Overall posture in this process", access=access, explicit_mode="global",
    )
    assert plan.mode == "global" and not plan.needs_clarification


def test_empty_question_rejected(access):
    with pytest.raises(ValueError):
        plan_retrieval("   ", access=access)


def test_history_span_rejects_inverted_window():
    with pytest.raises(ValueError):
        HistorySpan(revision_from=4, revision_to=2)


def test_history_span_contains_bounded_revisions():
    history = HistorySpan(revision_from=2, revision_to=4)
    assert not history.contains(1)
    assert history.contains(2) and history.contains(4)
    assert not history.contains(5)


def test_access_bounds_require_workspace_membership():
    with pytest.raises(ValueError):
        AccessBounds(
            role="analyst", workspace_id=uuid4(),
            allowed_workspace_ids=(uuid4(),),
        )


def test_plan_rejects_history_on_non_historical_mode(access):
    with pytest.raises(ValueError):
        RetrievalPlan(
            mode="local", question="q", access=access,
            history=HistorySpan(revision_from=1, revision_to=1),
        )


def test_plan_rejects_historical_without_history(access):
    with pytest.raises(ValueError):
        RetrievalPlan(mode="historical", question="q", access=access)
