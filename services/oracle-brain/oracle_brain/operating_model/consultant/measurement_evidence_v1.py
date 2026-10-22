"""Closed measured-report interpretation INSIDE a qualified assertion value.

Parsing does not qualify evidence, appoint an observer, or establish causality.
The actual captured assertion and all its citations remain canonical-owner input.
"""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from ..contracts import StrictRecord, canonical_bytes
from .calculations import Measurement

PREDICATE = 'measurement:observation:v1'
ASSERTION_UNIT = 'canonical-measurement-v1'


def _decimal(value: str) -> Decimal:
    if type(value) is not str or not value or len(value) > 80:
        raise ValueError('bounded canonical Decimal string required')
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError('finite canonical Decimal required') from None
    if (not number.is_finite() or number < 0 or number.is_signed()
            or len(number.as_tuple().digits) > 36
            or not -18 <= number.as_tuple().exponent <= 18):
        raise ValueError('nonnegative finite bounded Decimal required')
    normalized = format(number, 'f')
    if '.' in normalized:
        normalized = normalized.rstrip('0').rstrip('.')
    if value != normalized:
        raise ValueError('canonical Decimal spelling required')
    return number


class MeasurementEvidenceV1(StrictRecord):
    contract: Literal['qualified-measurement-evidence-v1'] = 'qualified-measurement-evidence-v1'
    amount: str = Field(min_length=1, max_length=80)
    unit: str = Field(min_length=1, max_length=100)
    currency: str | None = Field(default=None, max_length=3)
    period: str = Field(min_length=1, max_length=100)
    population_id: UUID
    window_start: AwareDatetime
    window_end: AwareDatetime
    observed_through: AwareDatetime
    complete: bool
    censored: bool

    @model_validator(mode='after')
    def coherent_report(self):
        # Currency syntax is not ISO qualification and performs no conversion.
        Measurement(_decimal(self.amount), self.unit, self.period, self.currency)
        dates = (self.window_start, self.window_end, self.observed_through)
        if (any(date.utcoffset().total_seconds() != 0 for date in dates)
                or self.window_start >= self.window_end
                or self.observed_through < self.window_start
                or self.complete and (self.censored or self.observed_through < self.window_end)):
            raise ValueError('coherent UTC observation window and completeness required')
        return self

    def measurement(self) -> Measurement:
        return Measurement(_decimal(self.amount), self.unit, self.period, self.currency)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate measurement field')
        result[key] = value
    return result


def measurement_from_assertion_v1(assertion, *, now: datetime | None = None):
    """Ordinary assertions are unchanged; a recognized malformed one REFUSES."""
    from ..consolidation_contracts_v1 import AssertionRevisionV1
    if type(assertion) is not AssertionRevisionV1:
        raise TypeError('exact qualified assertion required')
    if assertion.predicate != PREDICATE and assertion.unit != ASSERTION_UNIT:
        return None
    if assertion.predicate != PREDICATE or assertion.unit != ASSERTION_UNIT:
        raise ValueError('exact measurement assertion discriminator required')
    decoded = json.loads(assertion.value, object_pairs_hook=_unique)
    if canonical_bytes(decoded).decode('utf8') != assertion.value:
        raise ValueError('exact canonical measurement JSON required')
    record = MeasurementEvidenceV1.model_validate_json(assertion.value)
    if canonical_bytes(record.model_dump(mode='json')).decode('utf8') != assertion.value:
        raise ValueError('complete explicit canonical measurement fields required')
    selected_now = now if now is not None else datetime.now(timezone.utc)
    if (not isinstance(selected_now, datetime) or selected_now.tzinfo is None
            or selected_now.utcoffset() is None or record.observed_through > selected_now):
        raise ValueError('nonfuture observed-through and aware current time required')
    if (assertion.valid_time != 'evidenced'
            or assertion.valid_from != record.window_start
            or assertion.valid_to != record.window_end
            or not assertion.supporting_observations or not assertion.temporal_observations):
        raise ValueError('measurement window/value requires actual supporting and temporal source evidence')
    return record
