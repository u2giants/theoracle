"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.meetings.delivery is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.meetings.delivery'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        'S08 outbound replay/delivery implementation absent on main (not built). Named offline gate test retained with the s08-meeting-participation branch assertions; activates when meetings.delivery lands.',
        allow_module_level=True,
    )

"""Outbound never auto-sends; provider idempotency makes replay safe. No meeting joined."""
import pytest

from oracle_brain.meetings.delivery import (
    DeliveryLedger, create_intent, provider_idempotency_key,
)
from oracle_brain.meetings.participation import record_settings
from oracle_brain.workflows.meeting_turn import (
    InboundTurn, MembershipView, evaluate_turn,
)


def _intent(**kw):
    base = dict(intent_id='oi-1', meeting_id='m-1', turn_id='t-1',
                channel='meeting_text', body='the answer',
                created_at='2026-10-16T12:00:00Z')
    base.update(kw)
    return create_intent(**base)


def test_create_intent_records_only_and_never_sends():
    ledger = DeliveryLedger()
    intent = _intent()
    receipt = ledger.record_intent(intent)
    assert receipt.status == 'recorded' and receipt.sent_at is None
    assert receipt.provider_message_id is None


def test_provider_idempotency_key_is_stable_for_one_logical_send():
    a = provider_idempotency_key(meeting_id='m-1', intent_id='oi-1', channel='meeting_text')
    b = provider_idempotency_key(meeting_id='m-1', intent_id='oi-1', channel='meeting_text')
    c = provider_idempotency_key(meeting_id='m-1', intent_id='oi-2', channel='meeting_text')
    d = provider_idempotency_key(meeting_id='m-1', intent_id='oi-1', channel='meeting_chat')
    assert a == b and a != c and a != d


def test_replay_returns_prior_receipt_and_never_second_send():
    ledger = DeliveryLedger()
    intent = _intent()
    first = ledger.record_intent(intent)
    replayed = ledger.record_intent(intent)
    assert replayed is first
    sent = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-2',
                            channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                            provider_message_id='m-1')
    again = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-3',
                             channel='meeting_text', sent_at='2026-10-16T12:06:00Z',
                             provider_message_id='m-2')
    assert again is sent and again.provider_message_id == 'm-1'
    assert ledger.replay(intent.idempotency_key).status == 'sent'


def test_conflicting_body_under_same_key_fails_visibly():
    ledger = DeliveryLedger()
    ledger.record_intent(_intent())
    try:
        ledger.record_intent(_intent(body='different words'))
    except ValueError:
        pass
    else:
        raise AssertionError('conflicting body must fail, not re-send')


def test_sent_receipt_requires_complete_fields_and_unknown_key_denied():
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='', provider_message_id='m')
    except ValueError:
        pass
    else:
        raise AssertionError('incomplete sent receipt must fail')
    try:
        ledger.mark_sent('nope', receipt_id='dr-y', channel='meeting_text',
                         sent_at='2026-10-16T12:05:00Z', provider_message_id='m')
    except ValueError:
        pass
    else:
        raise AssertionError('unknown key must fail')


def test_failed_send_is_visible_and_silence_is_not_a_send():
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    failed = ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                                channel='meeting_text')
    assert failed.status == 'failed' and failed.sent_at is None
    assert ledger.replay(intent.idempotency_key).status == 'failed'


def test_turn_silence_when_disabled_records_no_outbound_intent():
    ledger = DeliveryLedger()
    settings = record_settings(meeting_id='m-1', recorded_at='2026-10-16T12:00:00Z')
    turn = InboundTurn(turn_id='t-1', meeting_id='m-1', speaker_id='p-1',
                       text='Oracle, what is the policy?', addresses_oracle=True)
    outcome = evaluate_turn(settings, turn, MembershipView(determined=False),
                            ledger, receipt_id='r-1', recorded_at='2026-10-16T12:00:00Z')
    assert outcome.decision == 'silence' and outcome.intent is None
    assert outcome.capture_continues is True


def test_turn_respond_records_intent_but_never_sends():
    ledger = DeliveryLedger()
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z')
    turn = InboundTurn(turn_id='t-1', meeting_id='m-1', speaker_id='p-1',
                       text='Oracle, what is the policy?', addresses_oracle=True)
    outcome = evaluate_turn(
        settings, turn, MembershipView(determined=True, shared_access=frozenset({'p-1'})),
        ledger, receipt_id='r-1', intent_id='oi-1', answer_body='the policy is X',
        recorded_at='2026-10-16T12:00:00Z')
    assert outcome.decision == 'respond' and outcome.evidence_scope == 'shared_access'
    assert outcome.intent is not None
    assert ledger.replay(outcome.intent.idempotency_key).status == 'recorded'


def test_undetermined_membership_never_widens_access():
    ledger = DeliveryLedger()
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z')
    turn = InboundTurn(turn_id='t-1', meeting_id='m-1', speaker_id='p-1',
                       text='Oracle, share the company total', addresses_oracle=True)
    unknown = evaluate_turn(
        settings, turn, MembershipView(determined=False), ledger,
        receipt_id='r-1', intent_id='oi-1', answer_body='meeting-only note',
        recorded_at='2026-10-16T12:00:00Z')
    assert unknown.decision == 'respond' and unknown.evidence_scope == 'meeting_only'
    declined = evaluate_turn(
        settings, turn, MembershipView(determined=False), ledger,
        receipt_id='r-2', answer_body='  ', recorded_at='2026-10-16T12:00:01Z')
    assert declined.decision == 'decline' and declined.evidence_scope == 'meeting_only'


def test_oracle_outbound_words_are_never_inbound_evidence():
    try:
        InboundTurn(turn_id='t-1', meeting_id='m-1', speaker_id='oracle',
                    text='my own earlier answer', origin='oracle')
    except ValueError:
        pass
    else:
        raise AssertionError('oracle-origin turns must not enter as evidence')


def test_cross_meeting_turn_rejected_and_capture_survives_failed_answer():
    ledger = DeliveryLedger()
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z')
    other = InboundTurn(turn_id='t-1', meeting_id='m-2', speaker_id='p-1',
                        text='hello', addresses_oracle=True)
    try:
        evaluate_turn(settings, other, MembershipView(determined=False), ledger,
                      receipt_id='r-1', recorded_at='2026-10-16T12:00:00Z')
    except ValueError:
        pass
    else:
        raise AssertionError('cross-meeting turn must fail')
    turn = InboundTurn(turn_id='t-2', meeting_id='m-1', speaker_id='p-1',
                       text='Oracle?', addresses_oracle=True)
    outcome = evaluate_turn(settings, turn, MembershipView(determined=False),
                            ledger, receipt_id='r-2', answer_body='   ',
                            recorded_at='2026-10-16T12:00:00Z')
    assert outcome.decision == 'decline' and outcome.capture_continues is True
