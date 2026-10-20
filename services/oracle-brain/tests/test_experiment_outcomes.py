"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.operating_model.consultant.experiments is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.operating_model.consultant.experiments'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        'S11 experiment outcomes implementation absent on main (held PR #142 / branch s11-recommendation-feedback). Named offline gate test retained with the branch assertions; activates when consultant.experiments lands.',
        allow_module_level=True,
    )

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


@pytest.mark.parametrize("refs", ["baseline-only", None, ("baseline-only",), (1, "followup")])
def test_single_string_or_wrong_type_cannot_prove_two_observations(refs):
    with pytest.raises(ValueError):
        observation(evidence_refs=refs).observed_reduction(now=END)


def test_naive_current_clock_is_rejected():
    with pytest.raises(ValueError, match="timezone"):
        observation().observed_reduction(now=END.replace(tzinfo=None))


def test_acceptance_is_not_realized_benefit():
    # A decision to try a scenario cannot replace completed followup evidence.
    with pytest.raises(ValueError, match="incomplete"):
        observation(observed_through=START).observed_reduction(now=START)


@pytest.mark.parametrize("whitespace", [" ", "\t", "\n", "\u00a0", "\u2003"])
@pytest.mark.parametrize("placement", ["prefix", "suffix"])
def test_noncanonical_evidence_cannot_make_one_reference_distinct(whitespace, placement):
    altered = whitespace + "ref" if placement == "prefix" else "ref" + whitespace
    with pytest.raises(ValueError):
        observation(evidence_refs=("ref", altered)).observed_reduction(now=END)


@pytest.mark.parametrize("bad", tuple(chr(code) for code in range(33)) + ("\x7f", "\u0085", "\u00a0", "\u200b", "\ufeff", "\u2060", "\u202e", "\u0301", "中"))
def test_evidence_identifier_rejects_control_format_combining_nonascii(bad):
    with pytest.raises(ValueError):
        observation(evidence_refs=("ref", "ref" + bad + "x")).observed_reduction(now=END)
