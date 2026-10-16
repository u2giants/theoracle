"""U6 public lifecycle/error/recovery states. Pure offline validation only.

No I/O, no database, no network, no provider call. This module never infers
ready or completed from SQL metadata alone: callers supply independently
observed facts, and missing facts abstain (UNKNOWN / missing-evidence) rather
than fabricate success. A cancel request is never proof the paid provider or
remote writer stopped. There is no automatic paid retry/rePOST, and no new
budget/horizon/epoch/reset. A spent dispatch is never disguised as retry;
recovery only consumes an independently appointed existing attempt without
another POST. Pure DTOs and state rules are offline pieces of U6; the real
browser journey proof remains separate and open.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contracts import StrictRecord

PUBLIC_STATES = frozenset({
    'pending',
    'processing',
    'awaiting-external-phase-or-custody',
    'missing-evidence',
    'revision_pending',
    'cancel-requested',
    'cancelled',
    'failed',
    'UNKNOWN',
})

# Positive completion is outside the public error/recovery set and is only
# reachable with independent completion proof, never from metadata alone.
COMPLETED = 'completed'

ANSWER_PRESENT = 'present'
ANSWER_ABSTAIN_MISSING_EVIDENCE = 'abstain-missing-evidence'
ANSWER_CLEARED_INVALID = 'clear-invalid'

AnswerPolicy = Literal['present', 'abstain-missing-evidence', 'clear-invalid']
PublicState = Literal[
    'pending', 'processing', 'awaiting-external-phase-or-custody',
    'missing-evidence', 'revision_pending', 'cancel-requested',
    'cancelled', 'failed', 'UNKNOWN', 'completed',
]

_INVARIANT_STATES = frozenset({
    'missing-evidence', 'revision_pending', 'cancel-requested',
    'cancelled', 'failed', 'UNKNOWN',
})


def _require(value: bool, message: str) -> None:
    if not value:
        raise ValueError(message)


class IndependentFacts(StrictRecord):
    """Facts an independent observer actually holds.

    Every field is an observation, not a SQL metadata claim. `metadata_done`
    exists only to be refused: when it is the sole completion signal the public
    state stays UNKNOWN, never completed/ready.
    """

    dispatch_spent: bool = False
    provider_stop_proof: bool = False
    completion_proof: bool = False
    metadata_done: bool = False
    external_phase_or_custody_open: bool = False
    evidence_missing: bool = False
    revision_pending: bool = False
    failure_wire_retained: bool = False
    nonce_consumed: bool = False
    late_completion_after_cancel_request: bool = False
    lost_reply: bool = False


class PublicView(StrictRecord):
    """Truthful public presentation for one attempt/journey slice."""

    state: PublicState
    answer_policy: AnswerPolicy
    current_answer_allowed: bool
    current_map_allowed: bool
    current_badge_allowed: bool
    cancel_stop_proven: bool
    paid_retry_allowed: bool
    recovery_mode: Literal['none', 'consume-existing-attempt', 'metadata-reread-only']
    liability: Literal['none', 'completed-unknown', 'retained-failure-wire', 'spent-dispatch']


class UserRetryIntent(StrictRecord):
    """User-facing retry request. Never a new paid POST by itself."""

    admitted_metadata_reread: bool = False
    request_new_dispatch: bool = False


class RecoveryAppointment(StrictRecord):
    """Independently appointed existing attempt for recovery without POST."""

    attempt_id: str = Field(min_length=1)
    appointed: bool
    same_nonce: bool = True


def derive_public_state(facts: IndependentFacts) -> PublicState:
    """Map independently observed facts to one truthful public state.

    Precedence is deliberate: missing evidence and revision invalidation are
    presented first so a stale answer is never shown; a cancel request is
    distinct from a proven cancel; a spent dispatch that only looks done in
    SQL metadata stays UNKNOWN.
    """
    if facts.evidence_missing:
        return 'missing-evidence'
    if facts.revision_pending:
        return 'revision_pending'
    if facts.provider_stop_proof and facts.dispatch_spent:
        return 'cancelled'
    if facts.late_completion_after_cancel_request and facts.completion_proof:
        # Late completion after a cancel request is preserved as its exact
        # liability, never silently relabelled cancelled or ready.
        return COMPLETED
    if facts.lost_reply and facts.dispatch_spent and not facts.completion_proof:
        return 'UNKNOWN'
    if facts.dispatch_spent and not facts.completion_proof and facts.provider_stop_proof:
        return 'cancelled'
    if facts.completion_proof:
        return COMPLETED
    if facts.failure_wire_retained and not facts.completion_proof:
        return 'failed'
    if facts.external_phase_or_custody_open:
        return 'awaiting-external-phase-or-custody'
    if facts.dispatch_spent:
        return 'processing'
    if facts.metadata_done and not facts.completion_proof:
        # Never infer ready/completed from SQL metadata alone.
        return 'UNKNOWN'
    return 'pending'


def answer_policy_for(state: PublicState) -> AnswerPolicy:
    if state == 'missing-evidence':
        return ANSWER_ABSTAIN_MISSING_EVIDENCE
    if state in _INVARIANT_STATES:
        return ANSWER_CLEARED_INVALID
    if state == COMPLETED:
        return ANSWER_PRESENT
    return ANSWER_CLEARED_INVALID


def public_view(state: PublicState, facts: IndependentFacts) -> PublicView:
    """Build the public presentation. Invalid states clear map/answer/badge."""
    _require(state in PUBLIC_STATES or state == COMPLETED, 'unknown public state')
    policy = answer_policy_for(state)
    invalid = policy != ANSWER_PRESENT
    stop_proven = facts.provider_stop_proof
    liability: Literal['none', 'completed-unknown', 'retained-failure-wire', 'spent-dispatch']
    if facts.lost_reply and facts.dispatch_spent and not facts.completion_proof:
        liability = 'completed-unknown'
    elif facts.failure_wire_retained:
        liability = 'retained-failure-wire'
    elif facts.dispatch_spent and not facts.completion_proof:
        liability = 'spent-dispatch'
    else:
        liability = 'none'
    if state == COMPLETED:
        recovery: Literal['none', 'consume-existing-attempt', 'metadata-reread-only'] = 'none'
        paid_retry = False
    elif state in ('failed', 'UNKNOWN', 'cancelled', 'cancel-requested'):
        recovery = 'consume-existing-attempt' if facts.dispatch_spent else 'none'
        paid_retry = False
    else:
        recovery = 'none'
        paid_retry = False
    return PublicView(
        state=state,
        answer_policy=policy,
        current_answer_allowed=not invalid,
        current_map_allowed=not invalid,
        current_badge_allowed=not invalid,
        cancel_stop_proven=stop_proven,
        paid_retry_allowed=paid_retry,
        recovery_mode=recovery,
        liability=liability,
    )


def request_cancel(facts: IndependentFacts) -> PublicState:
    """Record cancel intent. Never returns cancelled; intent is not stop proof."""
    if facts.provider_stop_proof:
        return 'cancelled'
    return 'cancel-requested'


def confirm_cancel(facts: IndependentFacts) -> PublicState:
    """Only an independently observed provider stop proof yields cancelled."""
    _require(facts.provider_stop_proof, 'cancel request is not proof the paid provider stopped')
    return 'cancelled'


def user_retry(facts: IndependentFacts, intent: UserRetryIntent) -> Literal['refused', 'metadata-reread-only']:
    """A spent dispatch is never disguised as retry; no automatic paid rePOST."""
    if not facts.dispatch_spent:
        return 'refused' if intent.request_new_dispatch else 'metadata-reread-only'
    if intent.request_new_dispatch:
        return 'refused'
    if intent.admitted_metadata_reread:
        return 'metadata-reread-only'
    return 'refused'


def recover_existing_attempt(
    facts: IndependentFacts,
    appointment: RecoveryAppointment,
) -> PublicState:
    """Recovery consumes an independently appointed existing attempt, no POST."""
    _require(facts.dispatch_spent, 'recovery requires a spent dispatch attempt')
    _require(appointment.appointed, 'recovery requires an independently appointed existing attempt')
    _require(appointment.same_nonce, 'recovery must retain the consumed nonce')
    _require(not facts.completion_proof, 'completed attempt is not recovered')
    # Recovery never issues a new POST, budget, horizon, epoch or reset.
    if facts.failure_wire_retained:
        return 'failed'
    if facts.lost_reply:
        return 'UNKNOWN'
    return 'processing'


def assert_no_stale_answer(view: PublicView) -> None:
    """Invariant: an invalid state never presents a current answer/map/badge."""
    if view.answer_policy != ANSWER_PRESENT:
        _require(not view.current_answer_allowed, 'stale answer after invalidation')
        _require(not view.current_map_allowed, 'stale map after invalidation')
        _require(not view.current_badge_allowed, 'stale badge after invalidation')
    _require(not view.paid_retry_allowed, 'public view must not allow automatic paid retry')
