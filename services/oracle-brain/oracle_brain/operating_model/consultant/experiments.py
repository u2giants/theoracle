"""Offline experiment observations; measured differences do not establish causality."""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from .calculations import Measurement, difference, _canonical_token


def _aware(value: datetime):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware observation dates required")


@dataclass(frozen=True)
class ExperimentObservation:
    baseline: Measurement
    followup: Measurement
    starts_at: datetime
    ends_at: datetime
    observed_through: datetime
    evidence_refs: tuple[str, ...]

    def observed_reduction(self, *, now: datetime) -> Decimal:
        for date in (self.starts_at, self.ends_at, self.observed_through, now):
            _aware(date)
        if self.starts_at >= self.ends_at:
            raise ValueError("positive observation window required")
        if now < self.ends_at or self.observed_through < self.ends_at:
            raise ValueError("observation window incomplete")
        if self.observed_through > now:
            raise ValueError("future observations rejected")
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs or any(not _canonical_token(ref) for ref in self.evidence_refs):
            raise ValueError("baseline and followup evidence references required")
        if len(set(self.evidence_refs)) < 2:
            raise ValueError("distinct baseline and followup evidence required")
        return difference(self.baseline, self.followup)
