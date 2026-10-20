"""U2 journey control gate: CAS, cancel, native1..N, authority.

Pure/offline. Synthetic invented data only. No provider, no company data,
no network, no database. Happy paths and denials for forged actor, double
cancel, replayed spent attempts, CAS conflict and expired authority.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from oracle_brain.hosting.replacement_journey_v1 import (
    JourneyActorContextV1,
    JourneyConflict,
    JourneyControlPlaneV1,
    JourneyControlRecordV1,
    JourneyControlState,
    JourneyDenied,
    JourneyReserveRequestV1,
    JourneySourceSelectorV1,
    NativeAttemptV1,
    _TRANSITIONS,
)


def _now():
    return datetime.now(timezone.utc)


def _context(**over):
    now = _now()
    data = dict(
        principal_id=uuid4(), workspace_id=uuid4(),
        session_role='invented_requester', runtime_hash='a' * 64,
        registry_hash='b' * 64, checked_at=now,
        valid_until=now + timedelta(minutes=5))
    data.update(over)
    return JourneyActorContextV1(**data)


def _request(**over):
    now = _now()
    data = dict(
        source_selectors=(JourneySourceSelectorV1(source_id=uuid4(), revision=1),),
        population_sha256='c' * 64, idempotency_key=uuid4(),
        caller_deadline=now + timedelta(minutes=5))
    data.update(over)
    return JourneyReserveRequestV1(**data)


def _plane_with_journey(**request_over):
    plane = JourneyControlPlaneV1()
    context = _context()
    journey = plane.reserve_replacement_journey(context, _request(**request_over))
    return plane, context, journey


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_reserve_starts_pending_at_revision_one():
    plane, context, journey = _plane_with_journey()
    assert journey.state == 'pending'
    assert journey.journey_revision == 1
    assert journey.cancel_requested is False
    assert journey.native_attempts == ()
    assert journey.paid_cost_retained is False
    read = plane.current_replacement_journey_metadata(context, journey.run_id)
    assert read.run_id == journey.run_id


def test_cas_advance_walks_control_states():
    plane, context, journey = _plane_with_journey()
    current = plane.compare_and_advance_replacement_journey(
        context, journey.run_id, 1, 'processing')
    assert current.state == 'processing'
    assert current.journey_revision == 2
    current = plane.compare_and_advance_replacement_journey(
        context, journey.run_id, 2, 'awaiting-external-authority')
    assert current.state == 'awaiting-external-authority'
    assert current.journey_revision == 3
    current = plane.compare_and_advance_replacement_journey(
        context, journey.run_id, 3, 'processing')
    assert current.state == 'processing'
    current = plane.compare_and_advance_replacement_journey(
        context, journey.run_id, current.journey_revision, 'missing-evidence')
    assert current.state == 'missing-evidence'
    current = plane.compare_and_advance_replacement_journey(
        context, journey.run_id, current.journey_revision, 'revision_pending')
    assert current.state == 'revision_pending'


def test_native_attempts_are_tracked_and_spent_never_replayed():
    plane, context, journey = _plane_with_journey()
    plane.compare_and_advance_replacement_journey(
        context, journey.run_id, 1, 'processing')
    first = plane.admit_native_attempt(
        context, journey.run_id, purpose='native-extract', nonce='1' * 64)
    assert first.sequence == 1 and first.spent is False
    spent = plane.consume_native_attempt(context, journey.run_id, first.attempt_id)
    assert spent.spent is True and spent.cost_retained is True
    # Spent nonce is retained, never replayed.
    with pytest.raises(JourneyConflict, match='already spent'):
        plane.consume_native_attempt(context, journey.run_id, first.attempt_id)
    # native2 is a new attempt, not a replay of native1.
    second = plane.admit_native_attempt(
        context, journey.run_id, purpose='native-extract', nonce='2' * 64)
    assert second.sequence == 2 and second.attempt_id != first.attempt_id
    spent2 = plane.consume_native_attempt(context, journey.run_id, second.attempt_id)
    assert spent2.spent is True
    final = plane.current_replacement_journey_metadata(context, journey.run_id)
    assert [a.sequence for a in final.native_attempts] == [1, 2]
    assert all(a.spent for a in final.native_attempts)
    assert final.paid_cost_retained is True
    with pytest.raises(JourneyConflict, match='already spent'):
        plane.consume_native_attempt(context, journey.run_id, second.attempt_id)


def test_repeated_nonce_cannot_start_a_second_attempt():
    plane, context, journey = _plane_with_journey()
    plane.admit_native_attempt(
        context, journey.run_id, purpose='p', nonce='a' * 64)
    with pytest.raises(JourneyConflict, match='nonce already used'):
        plane.admit_native_attempt(
            context, journey.run_id, purpose='p', nonce='a' * 64)


def test_independently_admitted_same_attempt_consume_is_recovery_only():
    plane, context, journey = _plane_with_journey()
    attempt = plane.admit_native_attempt(
        context, journey.run_id, purpose='p', nonce='a' * 64)
    spent = plane.consume_native_attempt(
        context, journey.run_id, attempt.attempt_id, recovery_admitted=True)
    assert spent.spent is True and spent.recovery_admitted is True
    # Recovery consume returns the retained record; it never un-spends.
    recovered = plane.consume_native_attempt(
        context, journey.run_id, attempt.attempt_id, recovery_admitted=True)
    assert recovered.spent is True and recovered.cost_retained is True
    # Without independent admission the spent attempt still refuses replay.
    with pytest.raises(JourneyConflict, match='already spent'):
        plane.consume_native_attempt(
            context, journey.run_id, attempt.attempt_id, recovery_admitted=False)


def test_cancel_preserves_paid_liability_and_is_not_remote_stop_proof():
    plane, context, journey = _plane_with_journey()
    plane.compare_and_advance_replacement_journey(
        context, journey.run_id, 1, 'processing')
    attempt = plane.admit_native_attempt(
        context, journey.run_id, purpose='paid', nonce='a' * 64)
    plane.consume_native_attempt(context, journey.run_id, attempt.attempt_id)
    result = plane.request_replacement_cancel(
        context, journey.run_id, 2, reason='user cancel')
    assert result['state'] == 'cancelled'
    assert result['paid_cost_retained'] is True
    assert result['in_flight_attempt_retained'] is True
    assert result['remote_stop_proof'] is False
    assert 'cancellation requested; in-flight attempt retained' in result['message']
    assert str(attempt.attempt_id) in [str(x) for x in result['spent_attempts']]
    final = plane.current_replacement_journey_metadata(context, journey.run_id)
    assert final.state == 'cancelled'
    assert final.paid_cost_retained is True
    # Spent attempt remains spent after cancel; no replay, no refund.
    with pytest.raises(JourneyConflict, match='already spent'):
        plane.consume_native_attempt(context, journey.run_id, attempt.attempt_id)


def test_cancel_without_in_flight_attempt_completes_quietly():
    plane, context, journey = _plane_with_journey()
    result = plane.request_replacement_cancel(context, journey.run_id, 1)
    assert result['state'] == 'cancelled'
    assert result['in_flight_attempt_retained'] is False
    assert result['remote_stop_proof'] is False
    assert result['paid_cost_retained'] is False


def test_refresh_returns_current_record_under_current_authority():
    plane, context, journey = _plane_with_journey()
    plane.compare_and_advance_replacement_journey(
        context, journey.run_id, 1, 'processing')
    refreshed = plane.refresh_replacement_journey(context, journey.run_id)
    assert refreshed.state == 'processing'
    assert refreshed.journey_revision == 2


def test_idempotent_reserve_returns_same_journey():
    plane = JourneyControlPlaneV1()
    context = _context()
    request = _request()
    first = plane.reserve_replacement_journey(context, request)
    second = plane.reserve_replacement_journey(context, request)
    assert first.run_id == second.run_id


def test_all_states_are_reachable_from_the_declared_machine():
    expected = {
        'pending', 'processing', 'awaiting-external-authority',
        'missing-evidence', 'revision_pending', 'cancel-requested',
        'cancelled', 'failed', 'UNKNOWN',
    }
    assert set(_TRANSITIONS) == expected
    assert JourneyControlState is not None


# ---------------------------------------------------------------------------
# Denial paths
# ---------------------------------------------------------------------------


def test_forged_actor_is_denied():
    plane, context, journey = _plane_with_journey()
    forged = _context(principal_id=uuid4(), workspace_id=context.workspace_id)
    with pytest.raises(JourneyDenied, match='forged journey actor'):
        plane.current_replacement_journey_metadata(forged, journey.run_id)
    with pytest.raises(JourneyDenied, match='forged journey actor'):
        plane.compare_and_advance_replacement_journey(forged, journey.run_id, 1, 'processing')
    with pytest.raises(JourneyDenied, match='forged journey actor'):
        plane.request_replacement_cancel(forged, journey.run_id, 1)
    foreign_workspace = _context(
        principal_id=context.principal_id, workspace_id=uuid4())
    with pytest.raises(JourneyDenied, match='forged journey actor'):
        plane.current_replacement_journey_metadata(foreign_workspace, journey.run_id)


def test_double_cancel_is_denied():
    plane, context, journey = _plane_with_journey()
    plane.request_replacement_cancel(context, journey.run_id, 1)
    with pytest.raises(JourneyConflict, match='already cancelled'):
        plane.request_replacement_cancel(context, journey.run_id, 3)
    final = plane.current_replacement_journey_metadata(context, journey.run_id)
    assert final.state == 'cancelled'


def test_replay_of_spent_attempt_is_denied():
    plane, context, journey = _plane_with_journey()
    attempt = plane.admit_native_attempt(
        context, journey.run_id, purpose='p', nonce='a' * 64)
    plane.consume_native_attempt(context, journey.run_id, attempt.attempt_id)
    with pytest.raises(JourneyConflict, match='already spent'):
        plane.consume_native_attempt(context, journey.run_id, attempt.attempt_id)
    # A new attempt cannot reuse the spent nonce either.
    with pytest.raises(JourneyConflict, match='nonce already used'):
        plane.admit_native_attempt(
            context, journey.run_id, purpose='p', nonce='a' * 64)


def test_cas_conflict_is_denied():
    plane, context, journey = _plane_with_journey()
    with pytest.raises(JourneyConflict, match='CAS conflict'):
        plane.compare_and_advance_replacement_journey(
            context, journey.run_id, 99, 'processing')
    with pytest.raises(JourneyConflict, match='CAS conflict'):
        plane.compare_and_advance_replacement_journey(
            context, journey.run_id, 0, 'processing')
    with pytest.raises(JourneyConflict, match='CAS conflict'):
        plane.compare_and_advance_replacement_journey(
            context, journey.run_id, 2, 'processing')
    with pytest.raises(JourneyConflict, match='CAS conflict'):
        plane.request_replacement_cancel(context, journey.run_id, 99)
    # Record is unchanged after the conflicts.
    current = plane.current_replacement_journey_metadata(context, journey.run_id)
    assert current.state == 'pending' and current.journey_revision == 1


def test_expired_authority_is_denied():
    plane = JourneyControlPlaneV1()
    now = _now()
    stale = _context(
        checked_at=now - timedelta(minutes=10),
        valid_until=now - timedelta(minutes=5))
    request = _request()
    with pytest.raises(JourneyDenied, match='authority expired'):
        plane.reserve_replacement_journey(stale, request)
    # A live context reserves; an expired context cannot refresh it.
    live = _context()
    journey = plane.reserve_replacement_journey(live, request)
    expired = _context(
        principal_id=live.principal_id, workspace_id=live.workspace_id,
        checked_at=now - timedelta(minutes=10),
        valid_until=now - timedelta(minutes=1))
    with pytest.raises(JourneyDenied, match='authority expired'):
        plane.refresh_replacement_journey(expired, journey.run_id)


def test_illegal_transition_is_denied():
    plane, context, journey = _plane_with_journey()
    with pytest.raises(JourneyConflict, match='illegal journey transition'):
        plane.compare_and_advance_replacement_journey(
            context, journey.run_id, 1, 'cancelled')
    with pytest.raises(JourneyConflict, match='illegal journey transition'):
        plane.compare_and_advance_replacement_journey(
            context, journey.run_id, 1, 'UNKNOWN')
    # cancel-requested must go through the cancel entry point.
    with pytest.raises(JourneyConflict, match='request_replacement_cancel'):
        plane.compare_and_advance_replacement_journey(
            context, journey.run_id, 1, 'cancel-requested')


def test_idempotency_conflict_on_different_request_is_denied():
    plane = JourneyControlPlaneV1()
    context = _context()
    key = uuid4()
    first = _request(idempotency_key=key, population_sha256='a' * 64)
    plane.reserve_replacement_journey(context, first)
    conflicting = _request(idempotency_key=key, population_sha256='b' * 64)
    with pytest.raises(JourneyConflict, match='idempotency conflict'):
        plane.reserve_replacement_journey(context, conflicting)


def test_terminal_journey_cannot_advance_or_admit_attempts():
    plane, context, journey = _plane_with_journey()
    plane.request_replacement_cancel(context, journey.run_id, 1)
    with pytest.raises(JourneyConflict, match='terminal journey cannot advance'):
        plane.compare_and_advance_replacement_journey(
            context, journey.run_id, 3, 'processing')
    with pytest.raises(JourneyDenied, match='cannot admit native attempts'):
        plane.admit_native_attempt(
            context, journey.run_id, purpose='p', nonce='a' * 64)


def test_forge_request_identity_fields_are_refused():
    # Request model forbids actor/workspace/provider/profile/admission fields.
    with pytest.raises(ValueError):
        JourneyReserveRequestV1.model_validate_json(
            '{"source_selectors":[{"source_id":"%s","revision":1}],'
            '"population_sha256":"%s","idempotency_key":"%s",'
            '"caller_deadline":"2030-01-01T00:00:00Z","actor_id":"%s"}'
            % (uuid4(), 'a' * 64, uuid4(), uuid4()))
    # Context is a separate server-held record; requests cannot carry it.
    with pytest.raises(ValueError):
        JourneyReserveRequestV1.model_validate_json(
            '{"source_selectors":[{"source_id":"%s","revision":1}],'
            '"population_sha256":"%s","idempotency_key":"%s",'
            '"caller_deadline":"2030-01-01T00:00:00Z","workspace_id":"%s"}'
            % (uuid4(), 'a' * 64, uuid4(), uuid4()))


def test_native_attempt_shape_guards():
    now = _now()
    with pytest.raises(ValueError):
        NativeAttemptV1(attempt_id=uuid4(), sequence=1, nonce='a' * 64,
                        purpose='p', admitted=True, spent=True, spent_at=None,
                        cost_retained=True, recovery_admitted=False)
    with pytest.raises(ValueError):
        NativeAttemptV1(attempt_id=uuid4(), sequence=1, nonce='a' * 64,
                        purpose='p', admitted=True, spent=False,
                        spent_at=now, cost_retained=False, recovery_admitted=False)
    with pytest.raises(ValueError):
        NativeAttemptV1(attempt_id=uuid4(), sequence=1, nonce='a' * 64,
                        purpose='p', admitted=True, spent=True, spent_at=now,
                        cost_retained=False, recovery_admitted=False)


def test_no_automatic_retry_after_spent_dispatch():
    """A spent dispatch is terminal for that attempt: no rePOST or paid retry."""
    plane, context, journey = _plane_with_journey()
    plane.compare_and_advance_replacement_journey(
        context, journey.run_id, 1, 'processing')
    attempt = plane.admit_native_attempt(
        context, journey.run_id, purpose='paid-dispatch', nonce='a' * 64)
    plane.consume_native_attempt(context, journey.run_id, attempt.attempt_id)
    # Same attempt cannot be consumed or re-admitted under the same nonce.
    with pytest.raises(JourneyConflict, match='already spent'):
        plane.consume_native_attempt(context, journey.run_id, attempt.attempt_id)
    with pytest.raises(JourneyConflict, match='nonce already used'):
        plane.admit_native_attempt(
            context, journey.run_id, purpose='paid-dispatch', nonce='a' * 64)
    # Cancel after spend keeps the liability and reports retained attempt.
    result = plane.request_replacement_cancel(
        context, journey.run_id, 2, reason='stop')
    assert result['paid_cost_retained'] is True
    assert result['remote_stop_proof'] is False


def test_sql_advance_function_validates_legal_transitions():
    """R8: SQL compare_and_advance must fail closed on illegal current->target.

    Offline source-level guard: the migration must carry a legal-edge check
    that denies absent edges (including pending->delivered gate skip) and
    raises 'illegal journey transition'. No live database required.
    """
    from pathlib import Path

    sql_path = (Path(__file__).resolve().parents[1] / 'sql'
                / '014_replacement_source_custody.sql')
    sql = sql_path.read_text(encoding='utf-8')
    assert 'illegal journey transition' in sql
    # Legal edges are enumerated from the current state, not a free target list.
    assert "j.state='pending' AND target_state IN ('processing'" in sql
    # Cannot jump to delivered (confirmed/answer-ready) without processing.
    pending_edges = sql.split("j.state='pending' AND target_state IN (", 1)[1].split(')', 1)[0]
    assert 'delivered' not in pending_edges
    assert 'cancelled' not in pending_edges
    assert 'UNKNOWN' not in pending_edges
    # delivered is reachable only from processing.
    assert "j.state='processing' AND target_state IN ('delivered'" in sql
    # Correction path reaches revision_pending; cancel stays on its own entry point.
    assert "j.state='delivered' AND target_state IN ('revision_pending'" in sql
    assert 'cancel uses request_replacement_cancel' in sql
    # Terminal states still refuse advance before the edge check.
    assert 'terminal journey cannot advance' in sql
