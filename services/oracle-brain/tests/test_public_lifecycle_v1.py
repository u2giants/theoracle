"""Fixture-only U6 public lifecycle tests. Pure offline; no DB, no browser."""
from oracle_brain.operating_model.public_lifecycle_v1 import (
    COMPLETED,
    IndependentFacts,
    RecoveryAppointment,
    UserRetryIntent,
    assert_no_stale_answer,
    confirm_cancel,
    derive_public_state,
    public_view,
    recover_existing_attempt,
    request_cancel,
    user_retry,
)


def test_pending_when_no_observations():
    assert derive_public_state(IndependentFacts()) == 'pending'


def test_metadata_done_alone_is_never_ready_or_completed():
    facts = IndependentFacts(metadata_done=True)
    assert derive_public_state(facts) == 'UNKNOWN'
    view = public_view('UNKNOWN', facts)
    assert not view.current_answer_allowed
    assert not view.current_map_allowed
    assert not view.current_badge_allowed
    assert_no_stale_answer(view)


def test_completion_requires_independent_proof_not_sql_metadata():
    assert derive_public_state(IndependentFacts(completion_proof=True)) == COMPLETED
    assert derive_public_state(IndependentFacts(metadata_done=True)) != COMPLETED
    both = IndependentFacts(completion_proof=True, metadata_done=True)
    assert derive_public_state(both) == COMPLETED


def test_cancel_request_is_not_cancelled():
    facts = IndependentFacts(dispatch_spent=True)
    assert request_cancel(facts) == 'cancel-requested'
    assert confirm_cancel(IndependentFacts(dispatch_spent=True, provider_stop_proof=True)) == 'cancelled'
    try:
        confirm_cancel(IndependentFacts(dispatch_spent=True))
    except ValueError as exc:
        assert 'not proof' in str(exc)
    else:
        raise AssertionError('cancel without stop proof must refuse')


def test_cancel_requested_never_infers_stop():
    facts = IndependentFacts(dispatch_spent=True, provider_stop_proof=False)
    state = request_cancel(facts)
    assert state == 'cancel-requested'
    view = public_view(state, facts)
    assert not view.cancel_stop_proven
    assert_no_stale_answer(view)


def test_missing_evidence_abstains_and_clears_stale_answer():
    facts = IndependentFacts(dispatch_spent=True, completion_proof=True, evidence_missing=True)
    state = derive_public_state(facts)
    assert state == 'missing-evidence'
    view = public_view(state, facts)
    assert view.answer_policy == 'abstain-missing-evidence'
    assert not view.current_answer_allowed
    assert not view.current_map_allowed
    assert not view.current_badge_allowed
    assert_no_stale_answer(view)


def test_revision_pending_clears_current_answer_map_badge():
    facts = IndependentFacts(dispatch_spent=True, completion_proof=True, revision_pending=True)
    view = public_view(derive_public_state(facts), facts)
    assert view.state == 'revision_pending'
    assert not view.current_answer_allowed
    assert_no_stale_answer(view)


def test_lost_reply_preserves_unknown_liability():
    facts = IndependentFacts(dispatch_spent=True, lost_reply=True)
    view = public_view(derive_public_state(facts), facts)
    assert view.state == 'UNKNOWN'
    assert view.liability == 'completed-unknown'
    assert_no_stale_answer(view)


def test_failure_wire_retained_reports_failed():
    facts = IndependentFacts(dispatch_spent=True, failure_wire_retained=True)
    view = public_view(derive_public_state(facts), facts)
    assert view.state == 'failed'
    assert view.liability == 'retained-failure-wire'
    assert_no_stale_answer(view)


def test_external_custody_awaits():
    assert derive_public_state(IndependentFacts(external_phase_or_custody_open=True)) == (
        'awaiting-external-phase-or-custody'
    )


def test_spent_dispatch_without_completion_is_processing():
    facts = IndependentFacts(dispatch_spent=True, nonce_consumed=True)
    assert derive_public_state(facts) == 'processing'


def test_no_automatic_paid_retry_and_spent_dispatch_not_disguised():
    spent = IndependentFacts(dispatch_spent=True, nonce_consumed=True)
    assert user_retry(spent, UserRetryIntent(request_new_dispatch=True)) == 'refused'
    assert user_retry(spent, UserRetryIntent()) == 'refused'
    assert user_retry(spent, UserRetryIntent(admitted_metadata_reread=True)) == 'metadata-reread-only'
    view = public_view('failed', IndependentFacts(dispatch_spent=True, failure_wire_retained=True))
    assert not view.paid_retry_allowed
    assert_no_stale_answer(view)


def test_recovery_consumes_existing_appointed_attempt_without_post():
    facts = IndependentFacts(dispatch_spent=True, nonce_consumed=True)
    ok = RecoveryAppointment(attempt_id='a' * 8, appointed=True, same_nonce=True)
    assert recover_existing_attempt(facts, ok) == 'processing'
    for bad in (
        RecoveryAppointment(attempt_id='a' * 8, appointed=False, same_nonce=True),
        RecoveryAppointment(attempt_id='a' * 8, appointed=True, same_nonce=False),
    ):
        try:
            recover_existing_attempt(facts, bad)
        except ValueError:
            pass
        else:
            raise AssertionError('unappointed or changed-nonce recovery must refuse')
    try:
        recover_existing_attempt(IndependentFacts(), ok)
    except ValueError:
        pass
    else:
        raise AssertionError('recovery without a spent dispatch must refuse')


def test_late_completion_after_cancel_request_keeps_exact_completion_liability():
    facts = IndependentFacts(
        dispatch_spent=True,
        late_completion_after_cancel_request=True,
        completion_proof=True,
    )
    assert derive_public_state(facts) == COMPLETED
    view = public_view(COMPLETED, facts)
    assert view.current_answer_allowed
    assert not view.paid_retry_allowed


def test_all_public_states_are_the_ledger_set_plus_proven_completed():
    from oracle_brain.operating_model.public_lifecycle_v1 import PUBLIC_STATES
    assert PUBLIC_STATES == frozenset({
        'pending', 'processing', 'awaiting-external-phase-or-custody',
        'missing-evidence', 'revision_pending', 'cancel-requested',
        'cancelled', 'failed', 'UNKNOWN',
    })
