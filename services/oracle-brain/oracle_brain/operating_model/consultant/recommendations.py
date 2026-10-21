"""Pure recommendation and feedback proposals; no ledger, actor or write authority.

Actual serving and feedback effects require the existing authoritative ledger.
DTO identity and arithmetic never attest truth or causal realized savings.
"""
from dataclasses import asdict, dataclass, replace
from decimal import Decimal
from uuid import UUID
from .calculations import Measurement, Forecast, _canonical_token
from .experiments import ExperimentObservation
from ..contracts import digest

LENSES = ("handoff_rework", "approval_exception", "information_duplication")
DECISIONS = ("accept", "reject", "defer")
MEASURE_KINDS = ("actual_cost", "capacity_estimate", "forecast_scenario", "missing")
MAX_REPAIRS = 1
MAX_TEXT = 4000
MAX_ID = 256
MAX_REFS = 256
MAX_OPTIONS = 16
MAX_MEASURES = 32
MAX_FEEDBACK = 128


def _natural(value: object) -> bool:
    return type(value) is str and bool(value.strip()) and len(value) <= MAX_TEXT


def _identity(value: object) -> bool:
    return type(value) is str and len(value) <= MAX_ID and _canonical_token(value)


def _hash(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _refs(value, *, allow_empty=False):
    if type(value) is not tuple or len(value) > MAX_REFS or (not value and not allow_empty):
        raise ValueError('bounded evidence reference tuple required')
    if any(not _identity(ref) for ref in value):
        raise ValueError('canonical evidence references required')
    if len(value) != len(set(value)):
        raise ValueError('duplicate evidence references rejected')


def _wire(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_wire(item) for item in value]
    return value


@dataclass(frozen=True)
class CostedMeasure:
    """A number labeled by epistemic kind; missing values stay explicit."""
    kind: str
    measure: Measurement | None = None

    def __post_init__(self):
        if type(self.kind) is not str or self.kind not in MEASURE_KINDS:
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
    evidence_seal: str | None = None

    def __post_init__(self):
        if not _identity(self.revision_id):
            raise ValueError("canonical evidence revision id required")
        _refs(self.evidence_refs)
        if self.evidence_seal is not None and not _hash(self.evidence_seal):
            raise ValueError('evidence seal must be a sha256 identity')

    def content_hash(self) -> str:
        return digest(_wire(asdict(self)))

    def covers(self, refs: tuple[str, ...]) -> bool:
        _refs(refs, allow_empty=True)
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
        if not _identity(self.option_id):
            raise ValueError("canonical option id required")
        if not _natural(self.title):
            raise ValueError("option title required")
        if type(self.is_no_change) is not bool:
            raise ValueError("no-change flag must be boolean")
        _refs(self.evidence_refs)
        if self.forecast is not None and not isinstance(self.forecast, Forecast):
            raise ValueError("forecast must be a validated Forecast")
        for costs in (self.downstream_costs, self.measured_basis):
            if type(costs) is not tuple or len(costs) > MAX_MEASURES or any(type(c) is not CostedMeasure for c in costs):
                raise ValueError("costed measure tuples required")
        if not self.downstream_costs:
            object.__setattr__(self, 'downstream_costs', (CostedMeasure('missing'),))
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
        if not _identity(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if type(self.lens) is not str or self.lens not in LENSES:
            raise ValueError("unsupported consulting lens")
        if not isinstance(self.evidence, EvidenceRevision):
            raise ValueError("evidence revision required")
        if type(self.options) is not tuple or not 2 <= len(self.options) <= MAX_OPTIONS:
            raise ValueError("at least no-change plus one alternative required")
        if any(type(o) is not Alternative for o in self.options):
            raise ValueError("validated alternatives required")
        ids = [o.option_id for o in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate option ids rejected")
        no_change = [o for o in self.options if o.is_no_change]
        if len(no_change) != 1:
            raise ValueError("exactly one no-change option required")
        for option in self.options:
            if not self.evidence.covers(option.evidence_refs):
                raise ValueError("option evidence outside revision")
        _refs(self.opposing_evidence, allow_empty=True)
        if type(self.opposing_unknown) is not bool:
            raise ValueError("opposing unknown must be boolean")
        if not self.opposing_unknown and not self.opposing_evidence:
            raise ValueError("opposing evidence or explicit unknown required")
        if self.opposing_unknown and self.opposing_evidence:
            raise ValueError("opposing unknown cannot hide cited opposing evidence")
        if not self.evidence.covers(self.opposing_evidence):
            raise ValueError("opposing evidence outside revision")
        if not _natural(self.scope_note):
            raise ValueError('bounded nonblank scope note required')

    def content_hash(self) -> str:
        return digest(_wire(asdict(self)))

    @property
    def no_change_option(self) -> Alternative:
        return next(o for o in self.options if o.is_no_change)

    def is_stale(self, current: EvidenceRevision) -> bool:
        if not isinstance(current, EvidenceRevision):
            raise ValueError("current evidence revision required")
        return self.evidence != current or self.evidence.content_hash() != current.content_hash()


@dataclass(frozen=True)
class ImprovementClaim:
    """Descriptive observed-difference proposal, never causal realized savings."""
    claim_id: str
    recommendation_id: str
    option_id: str
    evidence: EvidenceRevision
    observation: ExperimentObservation
    recommendation_hash: str | None = None

    def __post_init__(self):
        if not _identity(self.claim_id):
            raise ValueError("canonical claim id required")
        if not _identity(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if not _identity(self.option_id):
            raise ValueError("canonical option id required")
        if not isinstance(self.evidence, EvidenceRevision):
            raise ValueError("evidence revision required")
        if not isinstance(self.observation, ExperimentObservation):
            raise ValueError("experiment observation required")
        if not self.evidence.covers(self.observation.evidence_refs):
            raise ValueError("observation evidence outside revision")
        if self.recommendation_hash is not None and not _hash(self.recommendation_hash):
            raise ValueError('recommendation hash must be a sha256 identity')

    def measured_reduction(self, *, now):
        """Unattached arithmetic only; not evidence of causality or actual savings."""
        return self.observation.observed_reduction(now=now)

    def checked_observed_difference(self, recommendation: Recommendation, current: EvidenceRevision, *, now):
        if type(recommendation) is not Recommendation or type(current) is not EvidenceRevision:
            raise ValueError('exact current recommendation and evidence required')
        if (self.recommendation_id != recommendation.recommendation_id or
                self.recommendation_hash != recommendation.content_hash()):
            raise ValueError('observation does not bind exact recommendation')
        if self.option_id not in {option.option_id for option in recommendation.options}:
            raise ValueError('observation option is absent from recommendation')
        if self.evidence != current or recommendation.is_stale(current):
            raise ValueError('observation or recommendation evidence is stale')
        return self.measured_reduction(now=now)

    def is_stale(self, current: EvidenceRevision) -> bool:
        if not isinstance(current, EvidenceRevision):
            raise ValueError("current evidence revision required")
        return self.evidence != current or self.evidence.content_hash() != current.content_hash()


@dataclass(frozen=True)
class DecisionFeedback:
    """Descriptive decision payload; envelope fields never establish actor authority."""
    recommendation_id: str
    decision: str
    reason: str
    falsifies_facts: bool = False
    event_id: str | None = None
    workspace_id: UUID | None = None
    actor_id: UUID | None = None
    recommendation_hash: str | None = None

    def __post_init__(self):
        if not _identity(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if type(self.decision) is not str or self.decision not in DECISIONS:
            raise ValueError("unsupported decision")
        if not _natural(self.reason):
            raise ValueError("decision reason required")
        if self.falsifies_facts is not False:
            raise ValueError("decision feedback cannot falsify source facts")
        if self.event_id is not None and not _identity(self.event_id):
            raise ValueError('canonical explicit event id required')
        supplied = (self.workspace_id, self.actor_id, self.recommendation_hash)
        if any(item is not None for item in supplied):
            if (type(self.workspace_id) is not UUID or type(self.actor_id) is not UUID or
                    not _hash(self.recommendation_hash)):
                raise ValueError('complete explicit workspace actor and recommendation hash required')


@dataclass(frozen=True)
class FeedbackLoop:
    """Immutable nondurable proposal view; no user, event, time or authority minting."""
    recommendation_id: str
    history: tuple[DecisionFeedback, ...] = ()
    repairs_used: int = 0
    expected_workspace_id: UUID | None = None
    expected_actor_id: UUID | None = None
    current_recommendation: Recommendation | None = None

    def __post_init__(self):
        if not _identity(self.recommendation_id):
            raise ValueError("canonical recommendation id required")
        if type(self.history) is not tuple or len(self.history) > MAX_FEEDBACK or any(type(h) is not DecisionFeedback for h in self.history):
            raise ValueError("decision feedback history required")
        unique = []
        for feedback in self.history:
            if feedback not in unique:
                unique.append(feedback)
        object.__setattr__(self, 'history', tuple(unique))
        if any(h.recommendation_id != self.recommendation_id for h in self.history):
            raise ValueError("history must belong to this recommendation")
        if not isinstance(self.repairs_used, int) or isinstance(self.repairs_used, bool) or not 0 <= self.repairs_used <= MAX_REPAIRS:
            raise ValueError("repairs used out of range")
        supplied = (self.expected_workspace_id, self.expected_actor_id, self.current_recommendation)
        if any(item is not None for item in supplied):
            if (type(self.expected_workspace_id) is not UUID or type(self.expected_actor_id) is not UUID or
                    type(self.current_recommendation) is not Recommendation or
                    self.current_recommendation.recommendation_id != self.recommendation_id):
                raise ValueError('complete expected server scope and current recommendation required')
        seen_ids = {}
        for feedback in self.history:
            self._check_envelope(feedback)
            if feedback.event_id is not None:
                if feedback.event_id in seen_ids and seen_ids[feedback.event_id] != feedback:
                    raise ValueError('feedback event id collision')
                seen_ids[feedback.event_id] = feedback
        rejects = sum(1 for h in self.history if h.decision == 'reject' and self._matches_current(h))
        if self.repairs_used > rejects:
            raise ValueError("repair without a rejecting decision")

    def _matches_current(self, feedback):
        return (self.current_recommendation is not None and
                feedback.workspace_id == self.expected_workspace_id and
                feedback.actor_id == self.expected_actor_id and
                feedback.recommendation_hash == self.current_recommendation.content_hash())

    def _check_envelope(self, feedback):
        if feedback.workspace_id is not None and not self._matches_current(feedback):
            raise ValueError('feedback envelope differs from expected current server scope')

    def record(self, feedback: DecisionFeedback) -> "FeedbackLoop":
        if not isinstance(feedback, DecisionFeedback):
            raise ValueError("decision feedback required")
        if feedback.recommendation_id != self.recommendation_id:
            raise ValueError("feedback for a different recommendation")
        self._check_envelope(feedback)
        for prior in self.history:
            if feedback.event_id is not None and prior.event_id == feedback.event_id and prior != feedback:
                raise ValueError('feedback event id collision')
        if feedback in self.history:
            return self
        return replace(self, history=self.history + (feedback,))

    def can_repair(self) -> bool:
        if self.repairs_used >= MAX_REPAIRS:
            return False
        return bool(self.history and self.history[-1].decision == 'reject' and
                    self._matches_current(self.history[-1]))

    def repaired(self) -> "FeedbackLoop":
        if not self.can_repair():
            raise ValueError("no repair remaining")
        return replace(self, repairs_used=self.repairs_used + 1)


def _payload_object(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError('exact recommendation payload fields required')
    return value


def _payload_array(value, *, maximum, minimum=0):
    if type(value) is not list or not minimum <= len(value) <= maximum:
        raise ValueError('bounded recommendation payload array required')
    return value


def evidence_revision_from_payload(value) -> EvidenceRevision:
    data = _payload_object(value, ('revision_id', 'evidence_refs', 'evidence_seal'))
    refs = _payload_array(data['evidence_refs'], maximum=MAX_REFS, minimum=1)
    return EvidenceRevision(data['revision_id'], tuple(refs), data['evidence_seal'])


def evidence_revision_to_payload(value: EvidenceRevision) -> dict:
    if type(value) is not EvidenceRevision:
        raise ValueError('exact evidence revision required')
    payload = _wire(asdict(value))
    if evidence_revision_from_payload(payload) != value:
        raise ValueError('evidence revision wire mismatch')
    return payload


def _measurement_from_payload(value) -> Measurement:
    data = _payload_object(value, ('amount', 'unit', 'period', 'currency'))
    if type(data['amount']) is not str or not 1 <= len(data['amount']) <= 96:
        raise ValueError('exact Decimal string required')
    from decimal import InvalidOperation
    try:
        amount = Decimal(data['amount'])
    except InvalidOperation as error:
        raise ValueError('exact Decimal string required') from error
    if str(amount) != data['amount']:
        raise ValueError('canonical Decimal string required')
    return Measurement(amount, data['unit'], data['period'], data['currency'])


def _forecast_from_payload(value):
    if value is None:
        return None
    data = _payload_object(value, ('baseline', 'alternative', 'assumptions', 'kind'))
    assumptions = _payload_array(data['assumptions'], maximum=MAX_MEASURES, minimum=1)
    if any(not _natural(item) for item in assumptions):
        raise ValueError('bounded forecast assumption text required')
    return Forecast(_measurement_from_payload(data['baseline']), _measurement_from_payload(data['alternative']),
                    tuple(assumptions), data['kind'])


def _cost_from_payload(value):
    data = _payload_object(value, ('kind', 'measure'))
    return CostedMeasure(data['kind'], None if data['measure'] is None else _measurement_from_payload(data['measure']))


def recommendation_from_payload(value) -> Recommendation:
    """Strict explicit JSON wire; no dropped fields, inferred identities or effects."""
    data = _payload_object(value, ('recommendation_id', 'lens', 'evidence', 'options',
                                  'opposing_evidence', 'opposing_unknown', 'scope_note'))
    options = []
    for raw in _payload_array(data['options'], maximum=MAX_OPTIONS, minimum=2):
        row = _payload_object(raw, ('option_id', 'title', 'is_no_change', 'evidence_refs',
                                   'forecast', 'downstream_costs', 'measured_basis'))
        refs = _payload_array(row['evidence_refs'], maximum=MAX_REFS, minimum=1)
        downstream = _payload_array(row['downstream_costs'], maximum=MAX_MEASURES, minimum=1)
        basis = _payload_array(row['measured_basis'], maximum=MAX_MEASURES)
        options.append(Alternative(row['option_id'], row['title'], row['is_no_change'], tuple(refs),
            _forecast_from_payload(row['forecast']), tuple(_cost_from_payload(item) for item in downstream),
            tuple(_cost_from_payload(item) for item in basis)))
    opposing = _payload_array(data['opposing_evidence'], maximum=MAX_REFS)
    return Recommendation(data['recommendation_id'], data['lens'], evidence_revision_from_payload(data['evidence']),
                          tuple(options), tuple(opposing), data['opposing_unknown'], data['scope_note'])


def recommendation_to_payload(value: Recommendation) -> dict:
    if type(value) is not Recommendation:
        raise ValueError('exact recommendation required')
    payload = _wire(asdict(value))
    if recommendation_from_payload(payload) != value:
        raise ValueError('recommendation wire mismatch')
    return payload
