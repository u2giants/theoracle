"""Evidence-backed recommendation contract; decision feedback never falsifies facts."""
from dataclasses import dataclass, replace
from .calculations import Measurement, Forecast, _canonical_token
from .experiments import ExperimentObservation

LENSES = ("handoff_rework", "approval_exception", "information_duplication")
DECISIONS = ("accept", "reject", "defer")
MEASURE_KINDS = ("actual_cost", "capacity_estimate", "forecast_scenario", "missing")
MAX_REPAIRS = 1


def _natural(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class CostedMeasure:
    """A number labeled by epistemic kind; missing values stay explicit."""
    kind: str
    measure: Measurement | None = None

    def __post_init__(self):
        if self.kind not in MEASURE_KINDS:
            raise ValueError("unknown measure kind")
        if self.kind == "missing":
            if self.measure is not None:
                raise ValueError("missing measure carries no number")
        elif not isinstance(self.measure, Measurement):
            raise ValueError("non-missing measure requires a validated measurement")


@dataclass(frozen=True)
class EvidenceRevision:
    """Immutable snapshot of the evidence advice was built from."""
    revision_id: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self):
        if not _canonical_token(self.revision_id):
            raise ValueError("canonical evidence revision id required")
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs:
            raise ValueError("evidence revision requires evidence references")
        if any(not _canonical_token(ref) for ref in self.evidence_refs):
            raise ValueError("canonical evidence references required")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("duplicate evidence references rejected")

    def covers(self, refs: tuple[str, ...]) -> bool:
        return set(refs) <= set(self.evidence_refs)


@dataclass(frozen=True)
class Alternative:
    """One compared option, including the mandatory no-change option."""
    option_id: str
    title: str
    is_no_change: bool
    evidence_refs: tuple[str, ...]
    forecast: Forecast | None = None
    downstream_costs: tuple[CostedMeasure, ...] = ()
    measured_basis: tuple[CostedMeasure, ...] = ()

    def __post_init__(self):
        if not _canonical_token(self.option_id):
            raise ValueError("canonical option id required")
        if not _natural(self.title):
            raise ValueError("option title required")
        if not isinstance(self.is_no_change, bool):
            raise ValueError("no-change flag must be boolean")
        if not isinstance(self.evidence_refs, tuple) or not self.evidence_refs:
            raise ValueError("option evidence references required")
        if any(not _canonical_token(ref) for ref in self.evidence_refs):
            raise ValueError("canonical option evidence references required")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("duplicate option evidence references rejected")
        if self.forecast is not None and not isinstance(self.forecast, Forecast):
            raise ValueError("forecast must be a validated Forecast")
        for costs in (self.downstream_costs, self.measured_basis):
            if not isinstance(costs, tuple) or any(not isinstance(c, CostedMeasure) for c in costs):
                raise ValueError("costed measure tuples required")
        if self.is_no_change and self.forecast is not None:
            raise ValueError("no-change option cannot carry a change forecast")


@dataclass(frozen=True)
class Recommendation:
    """Conclusions stay scoped to the evidence revision they cite."""
    recommendation_id: str
    lens: str
    evidence: EvidenceRevision
    options: tuple[Alternative, ...]
    opposing_evidence: tuple[str, ...]
    opposing_unknown: bool = False
    scope_note: str = ""

    def __post_init__(self):
        if not _canonical_token(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if self.lens not in LENSES:
            raise ValueError("unsupported consulting lens")
        if not isinstance(self.evidence, EvidenceRevision):
            raise ValueError("evidence revision required")
        if not isinstance(self.options, tuple) or len(self.options) < 2:
            raise ValueError("at least no-change plus one alternative required")
        ids = [o.option_id for o in self.options]
        if any(not isinstance(o, Alternative) for o in self.options):
            raise ValueError("validated alternatives required")
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate option ids rejected")
        no_change = [o for o in self.options if o.is_no_change]
        if len(no_change) != 1:
            raise ValueError("exactly one no-change option required")
        for option in self.options:
            if not self.evidence.covers(option.evidence_refs):
                raise ValueError("option evidence outside revision")
        if not isinstance(self.opposing_evidence, tuple):
            raise ValueError("opposing evidence tuple required")
        if any(not _canonical_token(ref) for ref in self.opposing_evidence):
            raise ValueError("canonical opposing evidence references required")
        if len(set(self.opposing_evidence)) != len(self.opposing_evidence):
            raise ValueError("duplicate opposing evidence rejected")
        if not isinstance(self.opposing_unknown, bool):
            raise ValueError("opposing unknown must be boolean")
        if not self.opposing_unknown and not self.opposing_evidence:
            raise ValueError("opposing evidence or explicit unknown required")
        if self.opposing_unknown and self.opposing_evidence:
            raise ValueError("opposing unknown cannot hide cited opposing evidence")
        if not self.evidence.covers(self.opposing_evidence):
            raise ValueError("opposing evidence outside revision")
        if self.scope_note is not None and not isinstance(self.scope_note, str):
            raise ValueError("scope note must be text")

    @property
    def no_change_option(self) -> Alternative:
        return next(o for o in self.options if o.is_no_change)

    def is_stale(self, current: EvidenceRevision) -> bool:
        if not isinstance(current, EvidenceRevision):
            raise ValueError("current evidence revision required")
        return self.evidence.revision_id != current.revision_id


@dataclass(frozen=True)
class ImprovementClaim:
    """Measured improvement bound to the evidence revision that produced it."""
    claim_id: str
    recommendation_id: str
    option_id: str
    evidence: EvidenceRevision
    observation: ExperimentObservation

    def __post_init__(self):
        if not _canonical_token(self.claim_id):
            raise ValueError("canonical claim id required")
        if not _canonical_token(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if not _canonical_token(self.option_id):
            raise ValueError("canonical option id required")
        if not isinstance(self.evidence, EvidenceRevision):
            raise ValueError("evidence revision required")
        if not isinstance(self.observation, ExperimentObservation):
            raise ValueError("experiment observation required")
        if not self.evidence.covers(self.observation.evidence_refs):
            raise ValueError("observation evidence outside revision")

    def measured_reduction(self, *, now):
        return self.observation.observed_reduction(now=now)

    def is_stale(self, current: EvidenceRevision) -> bool:
        if not isinstance(current, EvidenceRevision):
            raise ValueError("current evidence revision required")
        return self.evidence.revision_id != current.revision_id


@dataclass(frozen=True)
class DecisionFeedback:
    """Employee decision feedback; rejection is not proof that facts are false."""
    recommendation_id: str
    decision: str
    reason: str
    falsifies_facts: bool = False

    def __post_init__(self):
        if not _canonical_token(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if self.decision not in DECISIONS:
            raise ValueError("unsupported decision")
        if not _natural(self.reason):
            raise ValueError("decision reason required")
        if self.falsifies_facts is not False:
            raise ValueError("decision feedback cannot falsify source facts")


@dataclass(frozen=True)
class FeedbackLoop:
    """At most one repair after a reject; then bounded findings only."""
    recommendation_id: str
    history: tuple[DecisionFeedback, ...] = ()
    repairs_used: int = 0

    def __post_init__(self):
        if not _canonical_token(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if not isinstance(self.history, tuple) or any(not isinstance(h, DecisionFeedback) for h in self.history):
            raise ValueError("decision feedback history required")
        if any(h.recommendation_id != self.recommendation_id for h in self.history):
            raise ValueError("history must belong to this recommendation")
        if not isinstance(self.repairs_used, int) or isinstance(self.repairs_used, bool) or not 0 <= self.repairs_used <= MAX_REPAIRS:
            raise ValueError("repairs used out of range")
        rejects = sum(1 for h in self.history if h.decision == "reject")
        if self.repairs_used > rejects:
            raise ValueError("repair without a rejecting decision")

    def record(self, feedback: DecisionFeedback) -> "FeedbackLoop":
        if not isinstance(feedback, DecisionFeedback):
            raise ValueError("decision feedback required")
        if feedback.recommendation_id != self.recommendation_id:
            raise ValueError("feedback for a different recommendation")
        return replace(self, history=self.history + (feedback,))

    def can_repair(self) -> bool:
        if self.repairs_used >= MAX_REPAIRS:
            return False
        return any(h.decision == "reject" for h in self.history)

    def repaired(self) -> "FeedbackLoop":
        if not self.can_repair():
            raise ValueError("no repair remaining")
        return replace(self, repairs_used=self.repairs_used + 1)
