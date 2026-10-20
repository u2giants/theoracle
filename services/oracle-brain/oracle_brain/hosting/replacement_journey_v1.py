"""Fixed U2 journey control plane: opaque request, CAS, cancel, native1..N.

Pure/offline state machine. No database, no provider, no fcntl, no network.
Server identity only: request bodies never carry actor/workspace/provider fields.
Cancelling preserves paid liability and never replays a spent attempt.
Cancel is not remote-stop proof. No automatic rePOST, paid retry, new budget,
horizon or epoch. Consumed nonces are retained; only an independently admitted
same-attempt consume may recover one.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, Field, model_validator

from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes, digest

HASH = r'^[a-f0-9]{64}$'

JourneyControlState = Literal[
    'pending', 'processing', 'delivered', 'awaiting-external-authority',
    'missing-evidence', 'revision_pending', 'cancel-requested',
    'cancelled', 'failed', 'UNKNOWN',
]

_TERMINAL = frozenset({'cancelled', 'failed', 'UNKNOWN'})

# CAS-legal transitions. Absent edges are denied.
_TRANSITIONS: dict[str, frozenset[str]] = {
    'pending': frozenset({
        'processing', 'awaiting-external-authority', 'missing-evidence',
        'revision_pending', 'cancel-requested', 'failed'}),
    'processing': frozenset({
        'delivered', 'awaiting-external-authority', 'missing-evidence',
        'revision_pending', 'cancel-requested', 'failed'}),
    'delivered': frozenset({
        'revision_pending', 'cancel-requested', 'failed'}),
    'awaiting-external-authority': frozenset({
        'processing', 'missing-evidence', 'revision_pending',
        'cancel-requested', 'failed'}),
    'missing-evidence': frozenset({
        'processing', 'awaiting-external-authority', 'revision_pending',
        'cancel-requested', 'failed'}),
    'revision_pending': frozenset({
        'processing', 'awaiting-external-authority', 'missing-evidence',
        'cancel-requested', 'failed'}),
    'cancel-requested': frozenset({'cancelled', 'failed'}),
    'cancelled': frozenset(),
    'failed': frozenset(),
    'UNKNOWN': frozenset(),
}

# Promotion targets that are confirmed/answer-ready. Never intake-only.
_PROMOTION_TARGETS = frozenset({'delivered'})
_CONFIRMATION_SCOPE = 'process-confirm'


class JourneyConflict(ValueError):
    """CAS conflict, idempotency conflict, replay or illegal transition."""


class JourneyDenied(PermissionError):
    """Forged actor, expired authority or cancel-semantic denial."""


class JourneyActorContextV1(StrictRecord):
    """Server-held identity. Never accepted from a request body."""
    principal_id: UUID
    workspace_id: UUID
    session_role: str = Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    runtime_hash: str = Field(pattern=HASH)
    registry_hash: str = Field(pattern=HASH)
    # Appointment scopes proven at admission. Intake-only cannot promote.
    scopes: tuple[str, ...] = ()
    checked_at: AwareDatetime
    valid_until: AwareDatetime

    @model_validator(mode='after')
    def finite(self):
        if self.checked_at >= self.valid_until:
            raise ValueError('finite journey authority required')
        return self


class JourneySourceSelectorV1(StrictRecord):
    """One ordered source reference the server resolves; no raw identity fields."""
    source_id: UUID
    revision: int = Field(strict=True, ge=1)


class JourneyReserveRequestV1(StrictRecord):
    """Opaque request identity only. Actor/workspace/provider are forbidden."""
    source_selectors: tuple[JourneySourceSelectorV1, ...] = Field(min_length=1, max_length=100)
    population_sha256: str = Field(pattern=HASH)
    idempotency_key: UUID
    caller_deadline: AwareDatetime

    @model_validator(mode='after')
    def shape(self):
        keys = [(s.source_id, s.revision) for s in self.source_selectors]
        if len(set(keys)) != len(keys) or len({s.source_id for s in self.source_selectors}) != len(self.source_selectors):
            raise ValueError('ordered complete journey source selectors required')
        return self


class NativeAttemptV1(StrictRecord):
    """One native attempt in a journey. Spent attempts are never replayed."""
    attempt_id: UUID
    sequence: int = Field(strict=True, ge=1, le=4096)
    nonce: str = Field(pattern=HASH)
    purpose: str = Field(min_length=1, max_length=200)
    admitted: bool
    spent: bool
    spent_at: AwareDatetime | None
    cost_retained: bool
    recovery_admitted: bool

    @model_validator(mode='after')
    def spend_shape(self):
        if self.spent and self.spent_at is None:
            raise ValueError('spent native attempt requires spent_at')
        if not self.spent and self.spent_at is not None:
            raise ValueError('unspent native attempt cannot carry spent_at')
        if self.spent and not self.cost_retained:
            raise ValueError('spent attempt retains paid liability')
        return self


class JourneyControlRecordV1(StrictRecord):
    """Immutable-identity journey with mutable CAS control fields."""
    run_id: UUID
    workspace_id: UUID
    actor_id: UUID
    journey_revision: int = Field(strict=True, ge=1)
    state: JourneyControlState
    population_sha256: str = Field(pattern=HASH)
    source_selectors: tuple[JourneySourceSelectorV1, ...] = Field(min_length=1, max_length=100)
    cancel_requested: bool
    cancel_requested_at: AwareDatetime | None
    cancel_reason: str | None
    native_attempts: tuple[NativeAttemptV1, ...] = Field(max_length=4096)
    delivered_event_id: UUID | None
    paid_cost_retained: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode='after')
    def control_shape(self):
        if self.cancel_requested != (self.cancel_requested_at is not None):
            raise ValueError('cancel marker consistency required')
        if self.state == 'cancelled' and not self.cancel_requested:
            raise ValueError('cancelled journey requires prior cancel request')
        if self.state == 'cancelled' and self.delivered_event_id is not None:
            raise ValueError('cancelled journey cannot deliver')
        sequences = [a.sequence for a in self.native_attempts]
        if sequences != sorted(sequences) or len(set(sequences)) != len(sequences):
            raise ValueError('native attempts are an ordered unique sequence')
        nonces = [a.nonce for a in self.native_attempts]
        if len(set(nonces)) != len(nonces):
            raise ValueError('native attempt nonces are unique')
        if self.updated_at < self.created_at:
            raise ValueError('journey clock order required')
        return self

    @property
    def spent_attempts(self) -> tuple[NativeAttemptV1, ...]:
        return tuple(a for a in self.native_attempts if a.spent)

    @property
    def open_attempts(self) -> tuple[NativeAttemptV1, ...]:
        return tuple(a for a in self.native_attempts if a.admitted and not a.spent)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_current(context: JourneyActorContextV1, journey: JourneyControlRecordV1) -> datetime:
    """Refresh/advance requires the exact pinned server identity, still finite."""
    if type(context) is not JourneyActorContextV1 or type(journey) is not JourneyControlRecordV1:
        raise TypeError('exact journey records required')
    now = _now()
    if context.checked_at > now or now >= context.valid_until:
        raise JourneyDenied('journey authority expired')
    if (context.principal_id, context.workspace_id) != (journey.actor_id, journey.workspace_id):
        raise JourneyDenied('forged journey actor')
    return context.valid_until


def _cas(journey: JourneyControlRecordV1, expected_revision: int) -> None:
    if type(expected_revision) is not int:
        raise JourneyConflict('journey CAS conflict')
    if expected_revision != journey.journey_revision:
        raise JourneyConflict('journey CAS conflict')


def _advance(journey: JourneyControlRecordV1, new_state: JourneyControlState) -> JourneyControlRecordV1:
    if new_state not in _TRANSITIONS[journey.state]:
        raise JourneyConflict(f'illegal journey transition {journey.state}->{new_state}')
    return journey.model_copy(update={
        'state': new_state,
        'journey_revision': journey.journey_revision + 1,
        'updated_at': _now(),
    })


class JourneyControlPlaneV1:
    """In-memory authoritative store for offline journey control tests.

    Mirrors the SQL functions reserve_replacement_journey,
    current_replacement_journey_metadata, compare_and_advance_replacement_journey
    and request_replacement_cancel. The SQL layer is the durable projection;
    this class is the pure control semantics those functions implement.
    """

    def __init__(self) -> None:
        self._journeys: dict[UUID, JourneyControlRecordV1] = {}
        self._idempotency: dict[tuple[UUID, UUID], tuple[UUID, str]] = {}
        self._attempts: dict[UUID, NativeAttemptV1] = {}

    # -- reserve ------------------------------------------------------------

    def reserve_replacement_journey(
        self,
        context: JourneyActorContextV1,
        request: JourneyReserveRequestV1,
    ) -> JourneyControlRecordV1:
        if type(context) is not JourneyActorContextV1 or type(request) is not JourneyReserveRequestV1:
            raise TypeError('exact journey records required')
        now = _now()
        if context.checked_at > now or now >= context.valid_until or now >= request.caller_deadline:
            raise JourneyDenied('journey authority expired')
        request_hash = digest({
            'source_selectors': [s.model_dump(mode='json') for s in request.source_selectors],
            'population_sha256': request.population_sha256,
            'caller_deadline': request.caller_deadline.isoformat(),
        })
        key = (context.workspace_id, request.idempotency_key)
        prior = self._idempotency.get(key)
        if prior is not None:
            prior_run, prior_hash = prior
            if prior_hash != request_hash:
                raise JourneyConflict('journey idempotency conflict')
            existing = self._journeys[prior_run]
            _require_current(context, existing)
            return existing
        run_id = uuid4()
        record = JourneyControlRecordV1(
            run_id=run_id,
            workspace_id=context.workspace_id,
            actor_id=context.principal_id,
            journey_revision=1,
            state='pending',
            population_sha256=request.population_sha256,
            source_selectors=request.source_selectors,
            cancel_requested=False,
            cancel_requested_at=None,
            cancel_reason=None,
            native_attempts=(),
            delivered_event_id=None,
            paid_cost_retained=False,
            created_at=now,
            updated_at=now,
        )
        self._journeys[run_id] = record
        self._idempotency[key] = (run_id, request_hash)
        return record

    # -- read ---------------------------------------------------------------

    def current_replacement_journey_metadata(
        self,
        context: JourneyActorContextV1,
        run_id: UUID,
    ) -> JourneyControlRecordV1:
        journey = self._journeys.get(run_id)
        if journey is None:
            raise JourneyDenied('journey unavailable')
        _require_current(context, journey)
        return journey

    # -- CAS advance --------------------------------------------------------

    def compare_and_advance_replacement_journey(
        self,
        context: JourneyActorContextV1,
        run_id: UUID,
        expected_revision: int,
        new_state: JourneyControlState,
        *,
        binding: dict | None = None,
        idempotency_key: UUID | None = None,
    ) -> JourneyControlRecordV1:
        journey = self._journeys.get(run_id)
        if journey is None:
            raise JourneyDenied('journey unavailable')
        _require_current(context, journey)
        _cas(journey, expected_revision)
        if journey.state in _TERMINAL:
            raise JourneyConflict('terminal journey cannot advance')
        if new_state == 'cancel-requested':
            raise JourneyConflict('cancel uses request_replacement_cancel')
        if new_state in _PROMOTION_TARGETS:
            # Delivered (confirmed/answer-ready) is never intake-only and
            # never fires without bound qualification/review commits.
            if _CONFIRMATION_SCOPE not in context.scopes:
                raise JourneyDenied(
                    'confirmation authority required for delivered promotion')
            evidence = None if binding is None else binding.get('evidence')
            if not isinstance(evidence, dict):
                raise JourneyDenied(
                    'qualification and review commits required for delivered promotion')
            reader = evidence.get('reader_commit')
            reviewer = evidence.get('reviewer_commit')
            import re as _re
            if (not isinstance(reader, str) or not isinstance(reviewer, str)
                    or not _re.fullmatch(HASH, reader)
                    or not _re.fullmatch(HASH, reviewer)):
                raise JourneyDenied(
                    'qualification and review commits required for delivered promotion')
        if binding is not None and idempotency_key is not None:
            key = (context.workspace_id, idempotency_key)
            prior = self._idempotency.get(key)
            if prior is not None:
                prior_run, prior_hash = prior
                if prior_run != run_id or prior_hash != digest(binding):
                    raise JourneyConflict('journey idempotency conflict')
                return journey
            self._idempotency[key] = (run_id, digest(binding))
        updated = _advance(journey, new_state)
        if binding is not None:
            delivered = binding.get('delivered_event_id')
            if delivered is not None:
                updated = updated.model_copy(update={'delivered_event_id': UUID(str(delivered))})
        self._journeys[run_id] = updated
        return updated

    # -- cancel -------------------------------------------------------------

    def request_replacement_cancel(
        self,
        context: JourneyActorContextV1,
        run_id: UUID,
        expected_revision: int,
        *,
        reason: str = 'user cancel',
        idempotency_key: UUID | None = None,
    ) -> dict:
        """Request cancel. Preserves paid liability. Not remote-stop proof.

        A spent or open native attempt means the in-flight attempt is retained:
        the result says so and never claims 'not sent' or a refund.
        """
        journey = self._journeys.get(run_id)
        if journey is None:
            raise JourneyDenied('journey unavailable')
        _require_current(context, journey)
        _cas(journey, expected_revision)
        if idempotency_key is not None:
            key = (context.workspace_id, idempotency_key)
            prior = self._idempotency.get(key)
            if prior is not None and prior[0] == run_id:
                # Idempotent replay of the same cancel request.
                current = self._journeys[run_id]
                return self._cancel_envelope(current, retained=bool(current.spent_attempts or current.open_attempts))
        if journey.state == 'cancelled':
            raise JourneyConflict('journey already cancelled')
        if journey.state == 'cancel-requested':
            raise JourneyConflict('journey already cancel-requested')
        if journey.state in _TERMINAL:
            raise JourneyConflict('terminal journey cannot cancel')
        now = _now()
        retained = bool(journey.spent_attempts or journey.open_attempts)
        requested = journey.model_copy(update={
            'state': 'cancel-requested',
            'journey_revision': journey.journey_revision + 1,
            'cancel_requested': True,
            'cancel_requested_at': now,
            'cancel_reason': reason,
            'paid_cost_retained': journey.paid_cost_retained or retained,
            'updated_at': now,
        })
        self._journeys[run_id] = requested
        if idempotency_key is not None:
            self._idempotency[(context.workspace_id, idempotency_key)] = (run_id, digest({'cancel': run_id.hex}))
        # Complete the cancel. Spent liability is preserved on the record.
        completed = requested.model_copy(update={
            'state': 'cancelled',
            'journey_revision': requested.journey_revision + 1,
            'updated_at': _now(),
        })
        self._journeys[run_id] = completed
        return self._cancel_envelope(completed, retained=retained)

    def _cancel_envelope(self, journey: JourneyControlRecordV1, *, retained: bool) -> dict:
        return {
            'schema_version': 1,
            'run_id': str(journey.run_id),
            'journey_revision': journey.journey_revision,
            'state': journey.state,
            'cancel_requested': journey.cancel_requested,
            'paid_cost_retained': journey.paid_cost_retained,
            'in_flight_attempt_retained': retained,
            'remote_stop_proof': False,
            'message': (
                'cancellation requested; in-flight attempt retained' if retained
                else 'cancellation completed; no in-flight attempt'
            ),
            'spent_attempts': [a.attempt_id for a in journey.spent_attempts],
        }

    # -- native1..N ---------------------------------------------------------

    def admit_native_attempt(
        self,
        context: JourneyActorContextV1,
        run_id: UUID,
        *,
        purpose: str,
        nonce: str,
        idempotency_key: UUID | None = None,
    ) -> NativeAttemptV1:
        """Admit the next native attempt (native1..N). Spent attempts stay."""
        journey = self._journeys.get(run_id)
        if journey is None:
            raise JourneyDenied('journey unavailable')
        _require_current(context, journey)
        if journey.state in _TERMINAL or journey.cancel_requested:
            raise JourneyDenied('journey cannot admit native attempts')
        if not purpose or len(purpose) > 200:
            raise ValueError('exact native attempt purpose required')
        import re as _re
        if not _re.fullmatch(HASH, nonce):
            raise ValueError('exact native attempt nonce required')
        if any(a.nonce == nonce for a in journey.native_attempts):
            raise JourneyConflict('native attempt nonce already used')
        if idempotency_key is not None:
            key = (context.workspace_id, idempotency_key)
            prior = self._idempotency.get(key)
            if prior is not None:
                prior_run, _ = prior
                if prior_run != run_id:
                    raise JourneyConflict('journey idempotency conflict')
                for attempt in journey.native_attempts:
                    if attempt.nonce == nonce:
                        return attempt
        now = _now()
        attempt = NativeAttemptV1(
            attempt_id=uuid4(),
            sequence=len(journey.native_attempts) + 1,
            nonce=nonce,
            purpose=purpose,
            admitted=True,
            spent=False,
            spent_at=None,
            cost_retained=False,
            recovery_admitted=False,
        )
        self._attempts[attempt.attempt_id] = attempt
        updated = journey.model_copy(update={
            'native_attempts': journey.native_attempts + (attempt,),
            'updated_at': now,
        })
        self._journeys[run_id] = updated
        return attempt

    def consume_native_attempt(
        self,
        context: JourneyActorContextV1,
        run_id: UUID,
        attempt_id: UUID,
        *,
        recovery_admitted: bool = False,
    ) -> NativeAttemptV1:
        """Consume (spend) one native attempt nonce exactly once.

        A spent attempt is never replayed. An independently admitted
        same-attempt consume is permitted for recovery only and still
        cannot un-spend or re-dispatch the attempt.
        """
        journey = self._journeys.get(run_id)
        if journey is None:
            raise JourneyDenied('journey unavailable')
        _require_current(context, journey)
        target = None
        for attempt in journey.native_attempts:
            if attempt.attempt_id == attempt_id:
                target = attempt
                break
        if target is None:
            raise JourneyConflict('native attempt absent')
        if target.spent:
            if recovery_admitted and target.recovery_admitted:
                # Independently admitted same-attempt consume for recovery only.
                return target
            raise JourneyConflict('native attempt already spent')
        now = _now()
        spent = target.model_copy(update={
            'spent': True,
            'spent_at': now,
            'cost_retained': True,
            'recovery_admitted': recovery_admitted,
        })
        self._attempts[attempt_id] = spent
        replaced = tuple(spent if a.attempt_id == attempt_id else a for a in journey.native_attempts)
        updated = journey.model_copy(update={
            'native_attempts': replaced,
            'paid_cost_retained': True,
            'updated_at': now,
        })
        self._journeys[run_id] = updated
        return spent

    # -- refresh ------------------------------------------------------------

    def refresh_replacement_journey(
        self,
        context: JourneyActorContextV1,
        run_id: UUID,
    ) -> JourneyControlRecordV1:
        """Poll/reload. Requires current authority; never serves stale identity."""
        return self.current_replacement_journey_metadata(context, run_id)
