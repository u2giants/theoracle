from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from oracle_brain.operating_model.consultant.calculations import Measurement
from oracle_brain.operating_model.consultant.experiments import ExperimentObservation

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
END = START + timedelta(days=7)


def observation(**changes):
    args = dict(baseline=Measurement(Decimal("10"), "money", "per_week", "USD"), followup=Measurement(Decimal("8"), "money", "per_week", "USD"), starts_at=START, ends_at=END, observed_through=END, evidence_refs=("baseline:1", "followup:2"))
    args.update(changes)
    return ExperimentObservation(**args)


def test_completed_observation_reports_difference_without_causality_claim():
    assert observation().observed_reduction(now=END) == Decimal("2")


@pytest.mark.parametrize("changes,now", [({}, END-timedelta(seconds=1)), ({"observed_through": END-timedelta(seconds=1)}, END), ({"observed_through": END+timedelta(seconds=1)}, END), ({"ends_at": START}, END), ({"starts_at": START.replace(tzinfo=None)}, END)])
def test_incomplete_future_invalid_or_naive_observations_rejected(changes, now):
    with pytest.raises(ValueError):
        observation(**changes).observed_reduction(now=now)


@pytest.mark.parametrize("refs", [(), ("same", "same"), ("", "followup")])
def test_missing_distinct_evidence_rejected(refs):
    with pytest.raises(ValueError):
        observation(evidence_refs=refs).observed_reduction(now=END)


def test_mixed_period_cannot_be_reported_as_observed_savings():
    with pytest.raises(ValueError, match="incompatible"):
        observation(followup=Measurement(Decimal("8"), "money", "per_month", "USD")).observed_reduction(now=END)
