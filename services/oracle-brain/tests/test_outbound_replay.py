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
from datetime import datetime, timezone

import pytest

from oracle_brain.meetings.delivery import (
    DeliveryLedger, SenderAuthority, SenderCredentialProof, SenderPrincipal,
    create_intent, issue_sender_authority, provider_idempotency_key,
    verify_sender_principal,
)
from oracle_brain.meetings.participation import record_settings
from oracle_brain.workflows.meeting_turn import (
    InboundTurn, MembershipView, evaluate_turn,
)

# Far-future expiry for legitimate fixture credentials.
_FUTURE = datetime(2030, 1, 1, tzinfo=timezone.utc)
_PAST = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _credential(*, role='delivery_sender', expires_at=None, principal_id='principal-1'):
    """Real verified principal fixture from the authz credential boundary."""
    proof = SenderCredentialProof(
        principal_id=principal_id, role=role,
        expires_at=expires_at if expires_at is not None else _FUTURE)
    return verify_sender_principal(proof)


def _sender(role='delivery_sender', principal=None):
    """Stand in for the authenticated delivery boundary allowed to mint."""
    return issue_sender_authority(
        role, principal if principal is not None else _credential(role=role))


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
                            provider_message_id='m-1', sender=_sender())
    again = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-3',
                             channel='meeting_text', sent_at='2026-10-16T12:06:00Z',
                             provider_message_id='m-2', sender=_sender())
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
                         channel='meeting_text', sent_at='', provider_message_id='m',
                         sender=_sender())
    except ValueError:
        pass
    else:
        raise AssertionError('incomplete sent receipt must fail')
    try:
        ledger.mark_sent('nope', receipt_id='dr-y', channel='meeting_text',
                         sent_at='2026-10-16T12:05:00Z', provider_message_id='m',
                         sender=_sender())
    except ValueError:
        pass
    else:
        raise AssertionError('unknown key must fail')


def test_failed_send_is_visible_and_silence_is_not_a_send():
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    failed = ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                                channel='meeting_text', sender=_sender())
    assert failed.status == 'failed' and failed.sent_at is None
    assert ledger.replay(intent.idempotency_key).status == 'failed'


def test_forged_sender_role_denied_for_mark_sent():
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    # No sender capability: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                         provider_message_id='m-1')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent without sender authority must be denied')
    # Forged sender_role claim of an authorized role name: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                         provider_message_id='m-1', sender_role='delivery_sender')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with forged sender_role must be denied')
    # Forged sender string claiming a role: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                         provider_message_id='m-1', sender='delivery_sender')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with forged sender role string must be denied')
    # Unknown/rogue role name: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                         provider_message_id='m-1', sender_role='random_caller')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with unauthorized role must be denied')
    # Forged capability instance (direct construction is sealed): denied.
    try:
        SenderAuthority('delivery_sender')
    except PermissionError:
        pass
    else:
        raise AssertionError('SenderAuthority direct construction must be denied')
    forged = object.__new__(SenderAuthority)
    forged._role = 'delivery_sender'
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                         provider_message_id='m-1', sender=forged)
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with forged SenderAuthority must be denied')
    assert ledger.replay(intent.idempotency_key).status == 'recorded'
    # Minted capability: allowed and idempotent.
    sent = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-s',
                            channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                            provider_message_id='m-1', sender=_sender())
    assert sent.status == 'sent'
    again = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-s2',
                             channel='meeting_text', sent_at='2026-10-16T12:06:00Z',
                             provider_message_id='m-2', sender=_sender())
    assert again is sent and again.provider_message_id == 'm-1'


def test_unauthorized_mark_failed_denied():
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    # No sender capability: denied.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                           channel='meeting_text')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-failed without sender authority must be denied')
    # Forged sender_role claim of an authorized role name: denied.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                           channel='meeting_text', sender_role='delivery_sender')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-failed with forged sender_role must be denied')
    # Forged sender string claiming a role: denied.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                           channel='meeting_text', sender='oracle_sender')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-failed with forged sender role string must be denied')
    assert ledger.replay(intent.idempotency_key).status == 'recorded'
    # Minted capability: allowed.
    failed = ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f2',
                                channel='meeting_text', sender=_sender())
    assert failed.status == 'failed'


def test_mint_secret_unreachable_and_lookalikes_cannot_mark():
    """No importable mint credential; look-alikes and unverified claims are denied."""
    import oracle_brain.meetings.delivery as delivery_mod

    # A mint secret must not be reachable as any module attribute.
    for name in ('_MINT_TOKEN', 'MINT_TOKEN', '_mint_token', 'mint_token',
                 '_MINTED', 'minted', '_VERIFIED', 'verified'):
        try:
            getattr(delivery_mod, name)
        except AttributeError:
            pass
        else:
            raise AssertionError(
                f'mint credential/registry must not be module attribute {name}')
    # Direct import of a mint token must fail.
    try:
        from oracle_brain.meetings.delivery import _MINT_TOKEN  # noqa: F401
    except ImportError:
        pass
    else:
        raise AssertionError('importing a mint token must fail')
    # The authorizer takes no mint-token argument at all.
    try:
        issue_sender_authority('delivery_sender', mint_token=object())
    except TypeError:
        pass
    else:
        raise AssertionError('issue_sender_authority must not accept a mint token')
    # Bare role string, with or without a role-as-credential: denied.
    try:
        issue_sender_authority('delivery_sender')
    except PermissionError:
        pass
    else:
        raise AssertionError('bare role string mint must be denied')
    try:
        issue_sender_authority('delivery_sender', 'delivery_sender')
    except PermissionError:
        pass
    else:
        raise AssertionError('role string is not a verified credential')
    # Forged/absent credential material at the authz boundary: denied.
    for bad in (None, 'delivery_sender', {'role': 'delivery_sender'},
                object.__new__(SenderPrincipal)):
        try:
            verify_sender_principal(bad)
        except PermissionError:
            pass
        else:
            raise AssertionError('forged sender credential proof must be denied')
    try:
        verify_sender_principal(SenderCredentialProof(
            principal_id='p-1', role='not_a_sender', expires_at=_FUTURE))
    except PermissionError:
        pass
    else:
        raise AssertionError('unauthorized role credential must be denied')
    # Forged principal (direct construction is sealed): denied.
    try:
        SenderPrincipal()
    except PermissionError:
        pass
    else:
        raise AssertionError('SenderPrincipal direct construction must be denied')
    forged_principal = object.__new__(SenderPrincipal)
    forged_principal._principal_id = 'principal-1'
    forged_principal._role = 'delivery_sender'
    forged_principal._expires_at = _FUTURE
    try:
        issue_sender_authority('delivery_sender', forged_principal)
    except PermissionError:
        pass
    else:
        raise AssertionError('forged sender principal must not mint authority')
    # Expired verified credential: denied at mint.
    try:
        issue_sender_authority(
            'delivery_sender', _credential(expires_at=_PAST))
    except PermissionError:
        pass
    else:
        raise AssertionError('expired sender principal must not mint authority')
    # Credential for a different role cannot mint this role.
    try:
        issue_sender_authority(
            'oracle_sender', _credential(role='delivery_sender'))
    except PermissionError:
        pass
    else:
        raise AssertionError('sender principal role mismatch must be denied')
    # Legitimate verified credential fixture still mints.
    proven = _sender()
    assert isinstance(proven, SenderAuthority)

    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    forged = object.__new__(SenderAuthority)
    forged._role = 'delivery_sender'
    # Look-alike cannot mark sent.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                         provider_message_id='m-1', sender=forged)
    except PermissionError:
        pass
    else:
        raise AssertionError('look-alike must not mark sent')
    # Look-alike cannot mark failed.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-x',
                           channel='meeting_text', sender=forged)
    except PermissionError:
        pass
    else:
        raise AssertionError('look-alike must not mark failed')
    assert ledger.replay(intent.idempotency_key).status == 'recorded'


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
    # Undetermined membership never produces an outbound intent, even with
    # a non-empty answer body: access is never widened.
    unknown = evaluate_turn(
        settings, turn, MembershipView(determined=False), ledger,
        receipt_id='r-1', intent_id='oi-1', answer_body='meeting-only note',
        recorded_at='2026-10-16T12:00:00Z')
    assert unknown.decision == 'decline' and unknown.intent is None
    assert unknown.evidence_scope == 'meeting_only'
    assert ledger.replay('unused-key') is None  # nothing recorded
    declined = evaluate_turn(
        settings, turn, MembershipView(determined=False), ledger,
        receipt_id='r-2', answer_body='  ', recorded_at='2026-10-16T12:00:01Z')
    assert declined.decision == 'decline' and declined.evidence_scope == 'meeting_only'


def test_shared_access_unauthorized_is_refused():
    ledger = DeliveryLedger()
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z')
    turn = InboundTurn(turn_id='t-1', meeting_id='m-1', speaker_id='p-1',
                       text='Oracle, what is the restricted total?', addresses_oracle=True)
    # Membership determined but speaker not in shared_access: refuse.
    outcome = evaluate_turn(
        settings, turn,
        MembershipView(determined=True, shared_access=frozenset({'other'})),
        ledger, receipt_id='r-1', intent_id='oi-1',
        answer_body='restricted answer', recorded_at='2026-10-16T12:00:00Z')
    assert outcome.decision == 'decline' and outcome.intent is None
    assert outcome.evidence_scope == 'none'
    # Empty shared_access set is also unauthorized.
    empty = evaluate_turn(
        settings, turn,
        MembershipView(determined=True, shared_access=frozenset()),
        ledger, receipt_id='r-2', intent_id='oi-2',
        answer_body='restricted answer', recorded_at='2026-10-16T12:00:01Z')
    assert empty.decision == 'decline' and empty.intent is None


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
