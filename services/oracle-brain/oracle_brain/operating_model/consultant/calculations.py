"""Deterministic comparison; forecasts never imply realized business benefits."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class Measurement:
    amount: Decimal
    unit: str
    period: str
    currency: str | None = None

    def __post_init__(self):
        if not isinstance(self.amount, Decimal) or not self.amount.is_finite():
            raise ValueError("finite Decimal amount required")
        if self.amount < 0 or not self.unit.strip() or not self.period.strip():
            raise ValueError("nonnegative amount and explicit unit/period required")
        if self.unit == "money":
            if self.currency is None or len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
                raise ValueError("explicit uppercase currency required")
        elif self.currency is not None:
            raise ValueError("currency applies only to monetary measurements")


def difference(baseline: Measurement, alternative: Measurement) -> Decimal:
    if (baseline.unit, baseline.period, baseline.currency) != (alternative.unit, alternative.period, alternative.currency):
        raise ValueError("incompatible units, currencies or time periods")
    return baseline.amount - alternative.amount


@dataclass(frozen=True)
class Forecast:
    baseline: Measurement
    alternative: Measurement
    assumptions: tuple[str, ...]
    kind: str = "forecast"

    def __post_init__(self):
        if self.kind != "forecast" or not self.assumptions or any(not a.strip() for a in self.assumptions):
            raise ValueError("forecast requires explicit assumptions")
        difference(self.baseline, self.alternative)

    @property
    def estimated_reduction(self) -> Decimal:
        return difference(self.baseline, self.alternative)
