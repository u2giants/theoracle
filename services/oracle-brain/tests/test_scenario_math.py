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
