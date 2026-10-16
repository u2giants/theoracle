"""Fixture-only S12 product-experience completeness gate tests. Pure offline."""

from uuid import uuid4

import pytest

from oracle_brain.knowledge.product_experience_gate_v1 import (
    REQUIRED_UPSTREAM_STAGES,
    CompletenessDecisionV1,
    ProductExperienceCompletenessRequestV1,
    UpstreamJourneyStateV1,
    evaluate_product_experience_completeness,
)


def state(workspace_id, stage, *, accepted=True, evidence_ref=None, **overrides):
    if accepted and evidence_ref is None and "evidence_ref" not in overrides:
        evidence_ref = f"evidence-{stage.lower()}"
    base = dict(
        workspace_id=workspace_id,
        stage=stage,
        accepted=accepted,
        evidence_ref=evidence_ref,
    )
    base.update(overrides)
    return UpstreamJourneyStateV1(**base)


def request(workspace_id=None, stages=None, **overrides):
    workspace_id = workspace_id or uuid4()
    if stages is None:
        stages = [
            state(workspace_id, stage) for stage in REQUIRED_UPSTREAM_STAGES
        ]
    base = dict(workspace_id=workspace_id, upstream=tuple(stages))
    base.update(overrides)
    return ProductExperienceCompletenessRequestV1(**base)


def test_all_accepted_stages_with_evidence_yield_ready():
    decision = evaluate_product_experience_completeness(request())
    assert decision.ready is True
    assert decision.missing_stages == ()
    assert decision.incomplete_stages == ()
    assert decision.refusal_reason == ""


def test_missing_stage_refuses_ready():
    workspace_id = uuid4()
    stages = [
        state(workspace_id, stage)
        for stage in REQUIRED_UPSTREAM_STAGES
        if stage != "S07"
    ]
    decision = evaluate_product_experience_completeness(
        request(workspace_id, stages)
    )
    assert decision.ready is False
    assert decision.missing_stages == ("S07",)
    assert "S07" in decision.refusal_reason


def test_incomplete_stage_refuses_ready():
    workspace_id = uuid4()
    stages = [
        state(workspace_id, stage, accepted=(stage != "S05"), evidence_ref="evidence-s05")
        for stage in REQUIRED_UPSTREAM_STAGES
    ]
    decision = evaluate_product_experience_completeness(
        request(workspace_id, stages)
    )
    assert decision.ready is False
    assert decision.incomplete_stages == ("S05",)
    assert "S05" in decision.refusal_reason


def test_multiple_missing_and_incomplete_stages_reported():
    workspace_id = uuid4()
    stages = [
        state(
            workspace_id,
            stage,
            accepted=stage not in ("S04", "S10"),
            evidence_ref=f"evidence-{stage.lower()}",
        )
        for stage in REQUIRED_UPSTREAM_STAGES
        if stage not in ("S06", "S09")
    ]
    decision = evaluate_product_experience_completeness(
        request(workspace_id, stages)
    )
    assert decision.ready is False
    assert decision.missing_stages == ("S06", "S09")
    assert decision.incomplete_stages == ("S04", "S10")
    assert "S06" in decision.refusal_reason
    assert "S10" in decision.refusal_reason


def test_accepted_stage_without_evidence_ref_is_refused_at_construction():
    with pytest.raises(ValueError, match="metadata alone never equals ready"):
        UpstreamJourneyStateV1(
            workspace_id=uuid4(),
            stage="S03",
            accepted=True,
            evidence_ref=None,
        )


def test_duplicate_upstream_stage_is_refused():
    workspace_id = uuid4()
    stages = [state(workspace_id, "S03"), state(workspace_id, "S03")]
    with pytest.raises(ValueError, match="duplicate upstream stage"):
        request(workspace_id, stages)


def test_upstream_workspace_mismatch_is_refused():
    workspace_id = uuid4()
    foreign = state(uuid4(), "S03")
    with pytest.raises(ValueError, match="belong to the request workspace"):
        request(workspace_id, [foreign])


def test_empty_upstream_is_refused_at_construction():
    with pytest.raises(ValueError):
        request(uuid4(), [])


def test_never_synthesizes_ready_from_metadata_only():
    # Every stage present and accepted=False with evidence is still refused.
    workspace_id = uuid4()
    stages = [
        state(workspace_id, stage, accepted=False, evidence_ref=f"evidence-{stage.lower()}")
        for stage in REQUIRED_UPSTREAM_STAGES
    ]
    decision = evaluate_product_experience_completeness(
        request(workspace_id, stages)
    )
    assert decision.ready is False
    assert decision.incomplete_stages == REQUIRED_UPSTREAM_STAGES
    assert decision.missing_stages == ()


def test_decision_is_frozen_strict_record():
    decision = evaluate_product_experience_completeness(request())
    assert isinstance(decision, CompletenessDecisionV1)
    with pytest.raises(Exception):
        decision.ready = False
