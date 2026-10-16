from decimal import Decimal
import pytest
from oracle_brain.operating_model.consultant.calculations import Measurement, Forecast


def money(amount, currency="USD", period="per_week"):
    return Measurement(Decimal(amount), "money", period, currency)


def test_forecast_explicit_assumptions_and_exact_decimal_math():
    forecast = Forecast(money("12.10"), money("2.05"), ("same workload",))
    assert forecast.kind == "forecast"
    assert forecast.estimated_reduction == Decimal("10.05")


@pytest.mark.parametrize("alternative", [money("2", "EUR"), money("2", period="per_month"), Measurement(Decimal("2"), "hours", "per_week")])
def test_incompatible_currency_period_or_unit_rejected(alternative):
    with pytest.raises(ValueError, match="incompatible"):
        Forecast(money("10"), alternative, ("same workload",))


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-1"])
def test_invalid_amount_rejected(amount):
    with pytest.raises(ValueError):
        money(amount)


def test_missing_assumptions_and_actual_label_rejected():
    with pytest.raises(ValueError):
        Forecast(money("10"), money("2"), ())
    with pytest.raises(ValueError):
        Forecast(money("10"), money("2"), ("same workload",), kind="realized")


def test_no_change_and_increased_cost_are_retained():
    assert Forecast(money("10"), money("10"), ("same workload",)).estimated_reduction == 0
    assert Forecast(money("10"), money("12"), ("same workload",)).estimated_reduction == -2


@pytest.mark.parametrize("assumptions", ["single-assumption", None, (None,), ("",)])
def test_missing_or_incompatible_inputs_abstain(assumptions):
    with pytest.raises(ValueError):
        Forecast(money("10"), money("2"), assumptions)


@pytest.mark.parametrize("changes", [{"unit": 5}, {"period": None}, {"currency": 123}, {"currency": "usd"}, {"currency": "US"}, {"currency": None}])
def test_invalid_measurement_metadata_rejected(changes):
    args = dict(amount=Decimal("1"), unit="money", period="per_week", currency="USD")
    args.update(changes)
    with pytest.raises(ValueError):
        Measurement(**args)


@pytest.mark.parametrize("amount", ["1e1000000", "1e-1000000", "1234567890123456789012345678901234567"])
def test_computational_precision_bounds(amount):
    with pytest.raises(ValueError, match="precision"):
        money(amount)


def test_missing_baseline_is_not_fabricated():
    with pytest.raises(ValueError):
        Forecast(None, money("2"), ("same workload",))


@pytest.mark.parametrize("field", ["unit", "period"])
@pytest.mark.parametrize("whitespace", [" ", "\t", "\n", "\u00a0", "\u2003"])
@pytest.mark.parametrize("placement", ["prefix", "suffix"])
def test_noncanonical_units_periods_fail_closed(field, whitespace, placement):
    args = dict(amount=Decimal("5"), unit="money", period="per_week", currency="USD")
    args[field] = whitespace + args[field] if placement == "prefix" else args[field] + whitespace
    if field == "unit":
        args["currency"] = None
    with pytest.raises(ValueError, match="canonical"):
        Measurement(**args)
