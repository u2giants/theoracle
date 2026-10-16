"""Deterministic comparison; forecasts never imply realized business benefits."""
from dataclasses import dataclass
from decimal import Decimal, localcontext


@dataclass(frozen=True)
class Measurement:
    amount: Decimal
    unit: str
    period: str
    currency: str | None = None

    def __post_init__(self):
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise ValueError("finite Decimal amount required")
        if len(self.amount.as_tuple().digits) > 36 or not -18 <= self.amount.as_tuple().exponent <= 18:
            raise ValueError("measurement exceeds computational precision bounds")
        if not isinstance(self.unit, str) or not isinstance(self.period, str):
            raise ValueError("string unit and period required")
        if self.amount < 0 or not self.unit.strip() or not self.period.strip():
            raise ValueError("nonnegative amount and explicit unit/period required")
        if self.unit == "money":
            if not isinstance(self.currency, str) or len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
                raise ValueError("explicit uppercase currency required")
        elif self.currency is not None:
            raise ValueError("currency applies only to monetary measurements")


def difference(baseline: Measurement, alternative: Measurement) -> Decimal:
    if not isinstance(baseline, Measurement) or not isinstance(alternative, Measurement):
        raise ValueError("two validated measurements required")
    if (baseline.unit, baseline.period, baseline.currency) != (alternative.unit, alternative.period, alternative.currency):
        raise ValueError("incompatible units, currencies or time periods")
    with localcontext() as context:
        context.prec = 80
        return baseline.amount - alternative.amount


@dataclass(frozen=True)
class Forecast:
    baseline: Measurement
    alternative: Measurement
    assumptions: tuple[str, ...]
    kind: str = "forecast"

    def __post_init__(self):
        if self.kind != "forecast" or not isinstance(self.assumptions, tuple) or not self.assumptions or any(not isinstance(a, str) or not a.strip() for a in self.assumptions):
            raise ValueError("forecast requires explicit assumptions")
        difference(self.baseline, self.alternative)

    @property
    def estimated_reduction(self) -> Decimal:
        return difference(self.baseline, self.alternative)
