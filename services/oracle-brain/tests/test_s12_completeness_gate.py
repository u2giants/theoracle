"""S12 offline completeness gate. Invented/synthetic only.

Asserts the gate refuses completeness when upstream stages are missing or
incomplete (REQUIRED_UPSTREAM_STAGES S03-S11 pattern). No employees, no
company data. Does not close #36.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from oracle_brain.knowledge.product_experience_gate_v1 import (
    REQUIRED_UPSTREAM_STAGES,
    CompletenessDecisionV1,
    ProductExperienceCompletenessRequestV1,
    UpstreamJourneyStateV1,
    evaluate_product_experience_completeness,
)


def _state(workspace_id, stage, *, accepted=True, evidence_ref=None):
    if accepted and evidence_ref is None:
        evidence_ref = f"evidence-{stage.lower()}"
    return UpstreamJourneyStateV1(
        workspace_id=workspace_id,
        stage=stage,
        accepted=accepted,
        evidence_ref=evidence_ref,
    )


def _request(workspace_id=None, stages=None):
    workspace_id = workspace_id or uuid4()
    if stages is None:
        stages = [_state(workspace_id, stage) for stage in REQUIRED_UPSTREAM_STAGES]
    return ProductExperienceCompletenessRequestV1(
        workspace_id=workspace_id, upstream=tuple(stages)
    )


def test_required_upstream_stages_are_s03_through_s11():
    assert REQUIRED_UPSTREAM_STAGES == (
        "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11",
    )


def test_gate_refuses_completeness_when_upstream_stages_missing():
    workspace_id = uuid4()
    stages = [
        _state(workspace_id, stage)
        for stage in REQUIRED_UPSTREAM_STAGES
        if stage != "S07"
    ]
    decision = evaluate_product_experience_completeness(_request(workspace_id, stages))
    assert decision.ready is False
    assert decision.missing_stages == ("S07",)
    assert "S07" in decision.refusal_reason


def test_gate_refuses_completeness_when_multiple_stages_missing():
    workspace_id = uuid4()
    stages = [
        _state(workspace_id, stage)
        for stage in REQUIRED_UPSTREAM_STAGES
        if stage not in ("S06", "S09")
    ]
    decision = evaluate_product_experience_completeness(_request(workspace_id, stages))
    assert decision.ready is False
    assert decision.missing_stages == ("S06", "S09")
    assert "S06" in decision.refusal_reason
    assert "S09" in decision.refusal_reason


def test_gate_refuses_completeness_when_upstream_stage_incomplete():
    workspace_id = uuid4()
    stages = [
        _state(workspace_id, stage, accepted=(stage != "S05"),
               evidence_ref=f"evidence-{stage.lower()}")
        for stage in REQUIRED_UPSTREAM_STAGES
    ]
    decision = evaluate_product_experience_completeness(_request(workspace_id, stages))
    assert decision.ready is False
    assert decision.incomplete_stages == ("S05",)
    assert "S05" in decision.refusal_reason


def test_gate_ready_only_with_all_stages_accepted_and_evidence():
    decision = evaluate_product_experience_completeness(_request())
    assert isinstance(decision, CompletenessDecisionV1)
    assert decision.ready is True
    assert decision.missing_stages == ()
    assert decision.incomplete_stages == ()
    assert decision.refusal_reason == ""


def test_gate_never_synthesizes_ready_from_metadata_only():
    workspace_id = uuid4()
    stages = [
        _state(workspace_id, stage, accepted=False,
               evidence_ref=f"evidence-{stage.lower()}")
        for stage in REQUIRED_UPSTREAM_STAGES
    ]
    decision = evaluate_product_experience_completeness(_request(workspace_id, stages))
    assert decision.ready is False
    assert decision.incomplete_stages == REQUIRED_UPSTREAM_STAGES


def test_accepted_upstream_without_evidence_ref_refused_at_construction():
    with pytest.raises(ValueError, match="metadata alone never equals ready"):
        UpstreamJourneyStateV1(
            workspace_id=uuid4(), stage="S03", accepted=True, evidence_ref=None,
        )
