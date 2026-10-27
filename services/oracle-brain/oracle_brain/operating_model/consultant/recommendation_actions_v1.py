"""Closed recommendation actions. Contracts and math never issue authority."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, model_validator
from ..contracts import StrictRecord, canonical_bytes, digest
from ..consolidation_contracts_v1 import AssertionScopeV1
from .recommendations import recommendation_from_payload, recommendation_to_payload
from .calculations import Measurement, difference
from .measurement_evidence_v1 import measurement_from_assertion_v1

HASH = r'^[0-9a-f]{64}$'


class ExperimentPlanV1(StrictRecord):
    experiment_id: UUID
    option_id: str = Field(min_length=1, max_length=256)
    metric_id: UUID
    unit: str = Field(min_length=1, max_length=100)
    currency: str | None = Field(default=None, max_length=3)
    period: str = Field(min_length=1, max_length=100)
    population_id: UUID
    baseline_start: AwareDatetime
    baseline_end: AwareDatetime
    followup_start: AwareDatetime
    followup_end: AwareDatetime
    success_metric: str = Field(min_length=1, max_length=1000)
    reversible_step: str = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def exact_plan(self):
        Measurement(Decimal('0'), self.unit, self.period, self.currency)
        dates = (self.baseline_start, self.baseline_end, self.followup_start, self.followup_end)
        if (any(d.utcoffset().total_seconds() != 0 for d in dates)
                or not self.baseline_start < self.baseline_end <= self.followup_start < self.followup_end
                or not self.success_metric.strip() or not self.reversible_step.strip()):
            raise ValueError('explicit UTC disjoint experiment windows and reversible plan required')
        return self


class ConsultingRecommendationV2(StrictRecord):
    recommendation_id: UUID
    # The existing strict comparison parser remains the sole owner of lenses,
    # no-change, opposition, unit/currency math and actual/forecast/missing kinds.
    advice: dict
    scope: AssertionScopeV1
    problem: str = Field(min_length=1, max_length=4000)
    competing_explanations: tuple[str, ...] = Field(min_length=1, max_length=8)
    effort: str = Field(min_length=1, max_length=2000)
    risks: tuple[str, ...] = Field(min_length=1, max_length=16)
    owner_role_description: str = Field(min_length=1, max_length=500)
    review_due: AwareDatetime
    experiments: tuple[ExperimentPlanV1, ...] = Field(min_length=1, max_length=16)
    expected_benefit: Literal['unknown'] = 'unknown'
    policy_accepted: Literal[False] = False
    effect_executed: Literal[False] = False
    realized_savings_verified: Literal[False] = False

    @model_validator(mode='after')
    def closed_comparison(self):
        advice = recommendation_from_payload(self.advice)
        if (advice.recommendation_id != str(self.recommendation_id)
                or recommendation_to_payload(advice) != self.advice
                or len({p.experiment_id for p in self.experiments}) != len(self.experiments)
                or len({p.option_id for p in self.experiments}) != len(self.experiments)
                or not {p.option_id for p in self.experiments} <= {o.option_id for o in advice.options if not o.is_no_change}
                or self.review_due.utcoffset().total_seconds() != 0
                or any(p.followup_end > self.review_due for p in self.experiments)
                or any(not text.strip() or len(text) > 2000 for text in (*self.competing_explanations, *self.risks))):
            raise ValueError('exact recommendation identity, alternatives and bounded experiment plan required')
        return self


class QualifiedConsultingRecommendationsV2(StrictRecord):
    contract: Literal['qualified-consulting-recommendations-v2'] = 'qualified-consulting-recommendations-v2'
    parent_model_id: UUID
    parent_version: int = Field(strict=True, ge=1)
    parent_content_hash: str = Field(pattern=HASH)
    repair_of_event: UUID | None = None
    recommendations: tuple[ConsultingRecommendationV2, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def unique_recommendations(self):
        if len({r.recommendation_id for r in self.recommendations}) != len(self.recommendations):
            raise ValueError('unique immutable recommendation identities required')
        return self


class RecommendationSelectorV1(StrictRecord):
    artifact_id: UUID
    artifact_version: int = Field(strict=True, ge=1)
    artifact_sha256: str = Field(pattern=HASH)
    recommendation_id: UUID


class FeedbackCommandV1(StrictRecord):
    operation: Literal['feedback'] = 'feedback'
    selector: RecommendationSelectorV1
    expected_head: int = Field(strict=True, ge=0, le=16383)
    command_id: UUID
    decision: Literal['accept', 'reject', 'defer']
    option_id: str | None = Field(default=None, min_length=1, max_length=256)
    reason: str = Field(min_length=1, max_length=1600)
    caller_deadline: AwareDatetime

    @model_validator(mode='after')
    def closed_decision(self):
        if (self.decision == 'accept') != (self.option_id is not None) or not self.reason.strip():
            raise ValueError('accepted exact option or reasoned reject/defer required')
        return self


class MeasurementCommandV1(StrictRecord):
    operation: Literal['measurement'] = 'measurement'
    selector: RecommendationSelectorV1
    expected_head: int = Field(strict=True, ge=0, le=16383)
    command_id: UUID
    experiment_id: UUID
    phase: Literal['baseline', 'followup']
    assertion_id: UUID
    assertion_revision: int = Field(strict=True, ge=1)
    caller_deadline: AwareDatetime


def source_bound_measurement_v1(core, recommendation, command, *, now: datetime):
    """Derive ONLY exact qualified parent bytes; caller never supplies a number."""
    from ..consolidation_contracts_v1 import ConsolidationCoreV1
    if (type(core) is not ConsolidationCoreV1 or type(recommendation) is not ConsultingRecommendationV2
            or type(command) is not MeasurementCommandV1
            or command.selector.recommendation_id != recommendation.recommendation_id):
        raise PermissionError('exact qualified parent, recommendation and measurement selector required')
    return _planned_source_measurement_v1(core,recommendation,
        experiment_id=command.experiment_id,phase=command.phase,
        assertion_id=command.assertion_id,assertion_revision=command.assertion_revision,now=now)


def _planned_source_measurement_v1(core,recommendation,*,experiment_id,phase,assertion_id,assertion_revision,now):
    plan = next((p for p in recommendation.experiments if p.experiment_id == experiment_id), None)
    assertion = next((a for a in core.assertions if (a.assertion_id, a.revision) == (assertion_id, assertion_revision)), None)
    if plan is None or assertion is None or assertion.subject_id != plan.metric_id or assertion.scope != recommendation.scope:
        raise PermissionError('actual planned metric and exact scoped assertion required')
    measured = measurement_from_assertion_v1(assertion, now=now)
    window = ((plan.baseline_start, plan.baseline_end) if phase == 'baseline'
              else (plan.followup_start, plan.followup_end))
    if (measured is None or (measured.unit, measured.currency, measured.period, measured.population_id)
            != (plan.unit, plan.currency, plan.period, plan.population_id)
            or (measured.window_start, measured.window_end) != window):
        raise PermissionError('complete explicit source unit/currency/period/population/window binding required')
    return {'assertion': assertion.model_dump(mode='json'), 'assertion_sha256': digest(assertion.model_dump(mode='json')),
            'measurement': measured.model_dump(mode='json'), 'phase': phase,
            'reported_only': True, 'causal_savings': False, 'realized_savings_verified': False}


def observed_difference_v1(baseline, followup, *, now: datetime):
    """Descriptive difference only; caller must first recheck BOTH permissions."""
    from .measurement_evidence_v1 import MeasurementEvidenceV1
    if type(baseline) is not MeasurementEvidenceV1 or type(followup) is not MeasurementEvidenceV1:
        raise TypeError('exact source-bound measurement values required')
    if (not baseline.complete or not followup.complete or baseline.censored or followup.censored
            or baseline.window_end > followup.window_start
            or max(baseline.window_end, followup.window_end, baseline.observed_through, followup.observed_through) > now
            or baseline.population_id != followup.population_id):
        return {'state': 'incomplete', 'observed_difference': None, 'causal_savings': False, 'realized_savings_verified': False}
    value = difference(baseline.measurement(), followup.measurement())
    return {'state': 'reported-difference', 'observed_difference': str(value), 'unit': baseline.unit,
            'currency': baseline.currency, 'period': baseline.period,
            'causal_savings': False, 'realized_savings_verified': False}
