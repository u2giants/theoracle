"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.operating_model.consultant.recommendations is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.operating_model.consultant.recommendations'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        'S11 recommendation contract implementation absent on main (held PR #142 / branch s11-recommendation-feedback). Named offline gate test retained with the branch assertions; activates when consultant.recommendations lands.',
        allow_module_level=True,
    )

"""Fixture-only recommendation contract tests; no live data or providers."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from oracle_brain.operating_model.consultant.calculations import Forecast, Measurement
from oracle_brain.operating_model.consultant.experiments import ExperimentObservation
from oracle_brain.operating_model.consultant.recommendations import (
    MAX_REPAIRS,
    Alternative,
    CostedMeasure,
    DecisionFeedback,
    EvidenceRevision,
    FeedbackLoop,
    ImprovementClaim,
    Recommendation,
)


def money(amount, currency="USD", period="per_week"):
    return Measurement(Decimal(amount), "money", period, currency)


def hours(amount, period="per_week"):
    return Measurement(Decimal(amount), "hours", period)


def revision(*refs, revision_id="rev:1"):
    return EvidenceRevision(revision_id, refs)


def forecast(base="10", alt="4"):
    return Forecast(money(base), money(alt), ("same workload",))


def alternative(option_id="opt:1", *, is_no_change=False, evidence_refs=("ev:a",), **kwargs):
    args = dict(
        option_id=option_id,
        title="Split approval into one named owner",
        is_no_change=is_no_change,
        evidence_refs=evidence_refs,
    )
    args.update(kwargs)
    return Alternative(**args)


def recommendation(*, lens="approval_exception", options=None, opposing_evidence=("ev:b",), opposing_unknown=False, evidence=None):
    if options is None:
        options = (
            alternative("opt:keep", is_no_change=True, title="Keep current approval path"),
            alternative("opt:1", forecast=forecast()),
        )
    return Recommendation(
        recommendation_id="rec:1",
        lens=lens,
        evidence=evidence or revision("ev:a", "ev:b"),
        options=options,
        opposing_evidence=opposing_evidence,
        opposing_unknown=opposing_unknown,
        scope_note="Scoped to the cited evidence revision only",
    )


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(days=7)


def observation(evidence_refs=("ev:a", "ev:c")):
    return ExperimentObservation(
        baseline=money("10"),
        followup=money("8"),
        starts_at=START,
        ends_at=END,
        observed_through=END,
        evidence_refs=evidence_refs,
    )


def test_no_change_option_is_required_and_identified():
    rec = recommendation()
    assert rec.no_change_option.is_no_change is True
    assert rec.no_change_option.option_id == "opt:keep"


def test_missing_no_change_option_rejected():
    with pytest.raises(ValueError, match="no-change"):
        recommendation(options=(alternative("opt:1", forecast=forecast()), alternative("opt:2", forecast=forecast("10", "2"))))


def test_duplicate_no_change_options_rejected():
    with pytest.raises(ValueError, match="no-change"):
        recommendation(options=(
            alternative("opt:keep", is_no_change=True),
            alternative("opt:keep2", is_no_change=True, title="Also keep"),
            alternative("opt:1", forecast=forecast()),
        ))


def test_no_change_cannot_carry_change_forecast():
    with pytest.raises(ValueError, match="no-change"):
        alternative("opt:keep", is_no_change=True, forecast=forecast())


def test_supported_lenses_accepted():
    for lens in ("handoff_rework", "approval_exception", "information_duplication"):
        assert recommendation(lens=lens).lens == lens


def test_unsupported_lens_rejected():
    with pytest.raises(ValueError, match="lens"):
        recommendation(lens="cost_savings")


def test_opposing_evidence_or_explicit_unknown_required():
    with pytest.raises(ValueError, match="opposing"):
        recommendation(opposing_evidence=(), opposing_unknown=False)


def test_opposing_unknown_and_cited_opposing_evidence_conflict():
    with pytest.raises(ValueError, match="opposing"):
        recommendation(opposing_evidence=("ev:b",), opposing_unknown=True)


def test_explicit_opposing_unknown_is_accepted():
    rec = recommendation(opposing_evidence=(), opposing_unknown=True)
    assert rec.opposing_unknown is True
    assert rec.opposing_evidence == ()


def test_option_evidence_outside_revision_rejected():
    with pytest.raises(ValueError, match="outside revision"):
        recommendation(options=(
            alternative("opt:keep", is_no_change=True),
            alternative("opt:1", forecast=forecast(), evidence_refs=("ev:z",)),
        ))


def test_opposing_evidence_outside_revision_rejected():
    with pytest.raises(ValueError, match="outside revision"):
        recommendation(opposing_evidence=("ev:z",))


def test_recommendation_is_stale_when_evidence_revision_changes():
    rec = recommendation(evidence=revision("ev:a", "ev:b", revision_id="rev:1"))
    assert rec.is_stale(revision("ev:a", "ev:b", revision_id="rev:2")) is True
    assert rec.is_stale(revision("ev:a", "ev:b", revision_id="rev:1")) is False


def test_duplicate_option_ids_rejected():
    with pytest.raises(ValueError, match="duplicate option"):
        recommendation(options=(
            alternative("opt:keep", is_no_change=True),
            alternative("opt:1", forecast=forecast()),
            alternative("opt:1", forecast=forecast("10", "2")),
        ))


def test_measure_kinds_distinguish_actual_capacity_forecast_and_missing():
    assert CostedMeasure("missing").measure is None
    assert CostedMeasure("actual_cost", money("3")).kind == "actual_cost"
    assert CostedMeasure("capacity_estimate", hours("2")).kind == "capacity_estimate"
    assert CostedMeasure("forecast_scenario", money("1")).kind == "forecast_scenario"


def test_missing_measure_cannot_carry_a_number():
    with pytest.raises(ValueError, match="missing"):
        CostedMeasure("missing", money("1"))


def test_non_missing_measure_requires_a_validated_measurement():
    with pytest.raises(ValueError, match="measurement"):
        CostedMeasure("actual_cost", None)


def test_unknown_measure_kind_rejected():
    with pytest.raises(ValueError, match="kind"):
        CostedMeasure("savings", money("1"))


def test_downstream_costs_and_measured_basis_attach_to_alternative():
    option = alternative(
        "opt:1",
        forecast=forecast(),
        downstream_costs=(CostedMeasure("capacity_estimate", hours("4")), CostedMeasure("missing")),
        measured_basis=(CostedMeasure("actual_cost", money("2")),),
    )
    assert option.downstream_costs[0].kind == "capacity_estimate"
    assert option.measured_basis[0].kind == "actual_cost"


def test_improvement_claim_requires_observation_evidence_inside_revision():
    with pytest.raises(ValueError, match="outside revision"):
        ImprovementClaim(
            claim_id="claim:1",
            recommendation_id="rec:1",
            option_id="opt:1",
            evidence=revision("ev:a", revision_id="rev:1"),
            observation=observation(evidence_refs=("ev:a", "ev:z")),
        )


def test_improvement_claim_measures_only_after_window_closes():
    claim = ImprovementClaim(
        claim_id="claim:1",
        recommendation_id="rec:1",
        option_id="opt:1",
        evidence=revision("ev:a", "ev:c", revision_id="rev:1"),
        observation=observation(),
    )
    assert claim.measured_reduction(now=END) == Decimal("2")
    with pytest.raises(ValueError, match="incomplete"):
        claim.measured_reduction(now=END - timedelta(seconds=1))


def test_improvement_claim_is_stale_on_evidence_revision_change():
    claim = ImprovementClaim(
        claim_id="claim:1",
        recommendation_id="rec:1",
        option_id="opt:1",
        evidence=revision("ev:a", "ev:c", revision_id="rev:1"),
        observation=observation(),
    )
    assert claim.is_stale(revision("ev:a", "ev:c", revision_id="rev:2")) is True
    assert claim.is_stale(revision("ev:a", "ev:c", revision_id="rev:1")) is False


def test_reject_requires_reason_and_is_decision_feedback_not_fact_falsification():
    feedback = DecisionFeedback("rec:1", "reject", "We cannot staff the change this quarter")
    assert feedback.falsifies_facts is False


def test_decision_feedback_cannot_falsify_source_facts():
    with pytest.raises(ValueError, match="falsify"):
        DecisionFeedback("rec:1", "reject", "Wrong facts", falsifies_facts=True)


def test_accept_and_defer_also_require_reason():
    assert DecisionFeedback("rec:1", "accept", "Proceed").decision == "accept"
    assert DecisionFeedback("rec:1", "defer", "Revisit next month").decision == "defer"


def test_unknown_decision_rejected():
    with pytest.raises(ValueError, match="decision"):
        DecisionFeedback("rec:1", "ignore", "No opinion")


def test_blank_decision_reason_rejected():
    with pytest.raises(ValueError, match="reason"):
        DecisionFeedback("rec:1", "reject", "   ")


def test_repair_allowed_once_after_reject_then_bounded():
    loop = FeedbackLoop("rec:1")
    assert loop.can_repair() is False
    rejected = loop.record(DecisionFeedback("rec:1", "reject", "Not now"))
    assert rejected.can_repair() is True
    repaired = rejected.repaired()
    assert repaired.repairs_used == MAX_REPAIRS
    assert repaired.can_repair() is False
    with pytest.raises(ValueError, match="repair"):
        repaired.repaired()


def test_accept_does_not_open_a_repair():
    accepted = FeedbackLoop("rec:1").record(DecisionFeedback("rec:1", "accept", "Proceed"))
    assert accepted.can_repair() is False


def test_feedback_for_another_recommendation_rejected():
    with pytest.raises(ValueError, match="different"):
        FeedbackLoop("rec:1").record(DecisionFeedback("rec:2", "reject", "Wrong card"))


def test_loop_history_binds_to_one_recommendation():
    with pytest.raises(ValueError, match="belong"):
        FeedbackLoop("rec:1", history=(DecisionFeedback("rec:2", "defer", "Later"),))


def test_repairs_cannot_exceed_rejects():
    with pytest.raises(ValueError, match="repair without"):
        FeedbackLoop("rec:1", repairs_used=1)


def test_evidence_revision_requires_unique_canonical_refs():
    with pytest.raises(ValueError):
        EvidenceRevision("rev:1", ())
    with pytest.raises(ValueError, match="duplicate"):
        EvidenceRevision("rev:1", ("ev:a", "ev:a"))
    with pytest.raises(ValueError, match="canonical"):
        EvidenceRevision("rev:1", ("ev a",))


def test_canonical_revision_id_required():
    with pytest.raises(ValueError, match="canonical"):
        EvidenceRevision("rev 1", ("ev:a",))


def test_naive_and_noncanonical_identifiers_rejected_end_to_end():
    with pytest.raises(ValueError):
        Alternative(option_id="opt 1", title="x", is_no_change=False, evidence_refs=("ev:a",))
    with pytest.raises(ValueError):
        Recommendation(
            recommendation_id="rec:1",
            lens="approval_exception",
            evidence=revision("ev:a", "ev:b"),
            options=(
                alternative("opt:keep", is_no_change=True),
                alternative("opt:1", forecast=forecast()),
            ),
            opposing_evidence=("ev b",),
        )
