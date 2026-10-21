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

import inspect

import pytest

from oracle_brain.meetings.delivery import (
    DELIVERY_ACTION_PURPOSE, DeliveryLedger, SenderCredentialProof,
    SENDER_CREDENTIAL_PURPOSE, create_intent,
    issue_sender_credential_proof, provider_idempotency_key,
    verify_sender_principal,
)
from oracle_brain.meetings.participation import (
    ENABLE_PROOF_PURPOSE, record_settings,
)
from oracle_brain.workflows.meeting_turn import (
    InboundTurn, MembershipView, evaluate_turn,
)

# Far-future expiry for legitimate fixture credentials.
_FUTURE = datetime(2030, 1, 1, tzinfo=timezone.utc)
_PAST = datetime(2020, 1, 1, tzinfo=timezone.utc)


from meeting_testkit import SETTINGS_EXPIRY, host_current
from oracle_brain.meetings.participation import record_settings as _raw_record_settings


def record_settings(**fields):
    if fields.get('enabled'):
        fields.setdefault('generation', 1)
        fields.setdefault('valid_until', SETTINGS_EXPIRY)
    return _raw_record_settings(**fields)


from oracle_brain.workflows.meeting_turn import evaluate_turn as _raw_evaluate


def evaluate_turn(settings, *args, **fields):
    fields.setdefault('current_state_reader', host_current)
    from meeting_testkit import host_audience
    fields.setdefault('current_audience_reader', host_audience)
    return _raw_evaluate(settings, *args, **fields)


def _test_mac(purpose, *fields):
    """Produce a purpose-tagged seal via the signer CLI (test host stand-in).

    Stands in for the host/identity service. The private key is loaded
    only inside the signer child process, never by the test process.
    """
    from seal_testkit import sign_seal
    return sign_seal(purpose, *fields)


def _credential_mac(principal_id, role, expires_at):
    """Host-identity-service MAC over (principal, role, expiry, purpose)."""
    return _test_mac(SENDER_CREDENTIAL_PURPOSE, principal_id, role, expires_at)


def _enable_mac(meeting_id, **configuration):
    """Host-authorized participation enable proof."""
    from oracle_brain.meetings.participation import settings_authority_payload
    return _test_mac(ENABLE_PROOF_PURPOSE, settings_authority_payload(
        meeting_id=meeting_id, recorded_at='2026-10-16T12:00:00Z',
        generation=1, valid_until=SETTINGS_EXPIRY, **configuration))


def _action_mac(intent_id, status, timestamp, *, ledger=None, receipt_id='',
                provider_message_id=''):
    """Synthetic host authorizes the full immutable action and bounded nonce."""
    import time
    from uuid import uuid4
    from oracle_brain.meetings.delivery import DeliveryActionProof, delivery_action_payload
    expiry, nonce = time.time() + 60, uuid4().hex
    if ledger is None:
        # Intentionally legacy/incomplete proof used only by denied-case tests.
        payload = intent_id
    else:
        intent = next(value for value in ledger._intents_by_key.values()
                      if value.intent_id == intent_id)
        payload = delivery_action_payload(
            ledger_id=ledger.ledger_id, intent=intent, status=status, timestamp=timestamp,
            receipt_id=receipt_id, channel=intent.channel,
            provider_message_id=provider_message_id, expires_at=expiry, nonce=nonce)
    return DeliveryActionProof(expiry, nonce, _test_mac(DELIVERY_ACTION_PURPOSE, payload))


def _credential(*, role='delivery_sender', expires_at=None, principal_id='principal-1'):
    """Real verified signed credential fixture from the authz boundary."""
    exp = expires_at if expires_at is not None else _FUTURE
    proof = issue_sender_credential_proof(
        principal_id=principal_id, role=role, expires_at=exp,
        mac=_credential_mac(principal_id, role, exp))
    return verify_sender_principal(proof)


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
                            provider_message_id='m-1',
                            action_mac=_action_mac(intent.intent_id, 'sent',
                                                   '2026-10-16T12:05:00Z', ledger=ledger, receipt_id='dr-2', provider_message_id='m-1'))
    again = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-3',
                             channel='meeting_text', sent_at='2026-10-16T12:06:00Z',
                             provider_message_id='m-2',
                             action_mac=_action_mac(intent.intent_id, 'sent',
                                                    '2026-10-16T12:06:00Z'))
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
                         action_mac=_action_mac(intent.intent_id, 'sent', ''))
    except ValueError:
        pass
    else:
        raise AssertionError('incomplete sent receipt must fail')
    try:
        ledger.mark_sent('nope', receipt_id='dr-y', channel='meeting_text',
                         sent_at='2026-10-16T12:05:00Z', provider_message_id='m',
                         action_mac=_action_mac('oi-1', 'sent', '2026-10-16T12:05:00Z'))
    except ValueError:
        pass
    else:
        raise AssertionError('unknown key must fail')


def test_failed_send_is_visible_and_silence_is_not_a_send():
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    failed = ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                                channel='meeting_text', failed_at='2026-10-16T12:05:00Z',
                                action_mac=_action_mac(intent.intent_id, 'failed',
                                                       '2026-10-16T12:05:00Z', ledger=ledger, receipt_id='dr-f'))
    assert failed.status == 'failed' and failed.sent_at is None
    assert ledger.replay(intent.idempotency_key).status == 'failed'


def test_forged_action_signature_denied_for_mark_sent():
    """Unsigned, forged, wrong-purpose and wrong-key action signatures are denied."""
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    sent_at = '2026-10-16T12:05:00Z'
    # No action signature: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at=sent_at,
                         provider_message_id='m-1')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent without action signature must be denied')
    # Forged sender_role claim of an authorized role name: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at=sent_at,
                         provider_message_id='m-1', sender_role='delivery_sender',
                         action_mac=_action_mac(intent.intent_id, 'sent', sent_at))
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with forged sender_role must be denied')
    # Garbage signature: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at=sent_at,
                         provider_message_id='m-1', action_mac='0' * 64)
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with forged action signature must be denied')
    # Wrong purpose (credential mac presented as action mac): denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at=sent_at,
                         provider_message_id='m-1',
                         action_mac=_credential_mac(intent.intent_id, 'sent', sent_at))
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with wrong-purpose signature must be denied')
    # Signature over a different timestamp: denied.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at=sent_at,
                         provider_message_id='m-1',
                         action_mac=_action_mac(intent.intent_id, 'sent',
                                                '2026-10-16T12:06:00Z'))
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-sent with signature for other fields must be denied')
    assert ledger.replay(intent.idempotency_key).status == 'recorded'
    # Legitimate signed action: allowed and idempotent.
    sent = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-s',
                            channel='meeting_text', sent_at=sent_at,
                            provider_message_id='m-1',
                            action_mac=_action_mac(intent.intent_id, 'sent', sent_at, ledger=ledger,
                                                   receipt_id='dr-s', provider_message_id='m-1'))
    assert sent.status == 'sent'
    again = ledger.mark_sent(intent.idempotency_key, receipt_id='dr-s2',
                             channel='meeting_text', sent_at='2026-10-16T12:06:00Z',
                             provider_message_id='m-2',
                             action_mac=_action_mac(intent.intent_id, 'sent',
                                                    '2026-10-16T12:06:00Z'))
    assert again is sent and again.provider_message_id == 'm-1'


def test_unauthorized_mark_failed_denied():
    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    failed_at = '2026-10-16T12:05:00Z'
    # No action signature: denied.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                           channel='meeting_text')
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-failed without action signature must be denied')
    # Forged sender_role claim: denied.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                           channel='meeting_text', sender_role='delivery_sender',
                           action_mac=_action_mac(intent.intent_id, 'failed', failed_at))
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-failed with forged sender_role must be denied')
    # Garbage signature: denied.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f',
                           channel='meeting_text', action_mac='0' * 64)
    except PermissionError:
        pass
    else:
        raise AssertionError('mark-failed with forged action signature must be denied')
    assert ledger.replay(intent.idempotency_key).status == 'recorded'
    # Legitimate signed action: allowed.
    failed = ledger.mark_failed(intent.idempotency_key, receipt_id='dr-f2',
                                channel='meeting_text', failed_at=failed_at,
                                action_mac=_action_mac(intent.intent_id, 'failed', failed_at, ledger=ledger,
                                                     receipt_id='dr-f2'))
    assert failed.status == 'failed'


def test_no_mutable_registry_and_lookalikes_cannot_mark():
    """No in-process mint registry exists; closure mutation is irrelevant.

    Authority is the Ed25519 signature alone. Forged credential
    look-alikes carry no valid signature and are denied. There is no
    WeakSet or id-registry anywhere in the delivery module for a caller
    to mutate through ``func.__closure__``.
    """
    import oracle_brain.meetings.delivery as delivery_mod

    # No mint secret or mutable registry may be a module attribute.
    for name in ('_MINT_TOKEN', 'MINT_TOKEN', '_mint_token', 'mint_token',
                 '_MINTED', 'minted', '_VERIFIED', 'verified',
                 '_PROOF_TOKEN', 'proof_token', '_PROOFS', 'proofs',
                 'require_proven_sender', 'issue_sender_authority',
                 'SenderAuthority', 'SenderPrincipal'):
        try:
            getattr(delivery_mod, name)
        except AttributeError:
            pass
        else:
            raise AssertionError(
                f'mint credential/registry/capability must not be module attribute {name}')
    # WeakSet / identity-registry patterns are gone from the source.
    source = inspect.getsource(delivery_mod)
    assert 'WeakSet' not in source
    assert 'from weakref' not in source
    # Exported functions must not close over a mutable add-able registry.
    for fn in (issue_sender_credential_proof, verify_sender_principal):
        for cell in (fn.__closure__ or ()):
            obj = getattr(cell, 'cell_contents', None)
            if isinstance(obj, (set, dict, list)):
                try:
                    obj.add(object())
                except AttributeError:
                    try:
                        obj[object()] = object()
                    except Exception:
                        continue
                    else:
                        raise AssertionError(
                            f'{fn.__name__} closes over a mutable registry')
                else:
                    raise AssertionError(
                        f'{fn.__name__} closes over a mutable registry')
    # Direct construction of a credential proof is sealed: denied.
    for attempt in (
        lambda: SenderCredentialProof(
            principal_id='p-1', role='delivery_sender', expires_at=_FUTURE),
        lambda: SenderCredentialProof(),
    ):
        try:
            attempt()
        except PermissionError:
            pass
        else:
            raise AssertionError('SenderCredentialProof direct construction must be denied')
    # object.__new__ look-alike has no valid signature: denied at verify.
    forged_proof = object.__new__(SenderCredentialProof)
    forged_proof._principal_id = 'p-1'
    forged_proof._role = 'delivery_sender'
    forged_proof._expires_at = _FUTURE
    forged_proof._purpose = SENDER_CREDENTIAL_PURPOSE
    forged_proof._mac = ''
    try:
        verify_sender_principal(forged_proof)
    except PermissionError:
        pass
    else:
        raise AssertionError('forged sender credential proof look-alike must be denied')
    # Unauthorized role in a real sealed proof: denied at verify.
    bad_role_proof = issue_sender_credential_proof(
        principal_id='p-1', role='not_a_sender', expires_at=_FUTURE,
        mac=_credential_mac('p-1', 'not_a_sender', _FUTURE))
    try:
        verify_sender_principal(bad_role_proof)
    except PermissionError:
        pass
    else:
        raise AssertionError('unauthorized role credential must be denied')
    # Expired sealed credential: denied at verify (real expiry check).
    expired_proof = issue_sender_credential_proof(
        principal_id='p-expired', role='delivery_sender', expires_at=_PAST,
        mac=_credential_mac('p-expired', 'delivery_sender', _PAST))
    try:
        verify_sender_principal(expired_proof)
    except PermissionError:
        pass
    else:
        raise AssertionError('expired sender credential must be denied at verify')
    # Credential for a different role cannot pass as this role.
    other = _credential(role='oracle_sender')
    assert other.role == 'oracle_sender'
    # Legitimate verified credential fixture still verifies.
    proven = _credential()
    assert isinstance(proven, SenderCredentialProof)
    assert proven.role == 'delivery_sender'

    ledger = DeliveryLedger()
    intent = _intent()
    ledger.record_intent(intent)
    # Look-alike credential is not an action signature: cannot mark sent.
    try:
        ledger.mark_sent(intent.idempotency_key, receipt_id='dr-x',
                         channel='meeting_text', sent_at='2026-10-16T12:05:00Z',
                         provider_message_id='m-1', action_mac=forged_proof.mac)
    except PermissionError:
        pass
    else:
        raise AssertionError('look-alike must not mark sent')
    # Look-alike cannot mark failed either.
    try:
        ledger.mark_failed(intent.idempotency_key, receipt_id='dr-x',
                           channel='meeting_text', action_mac=forged_proof.mac)
    except PermissionError:
        pass
    else:
        raise AssertionError('look-alike must not mark failed')
    assert ledger.replay(intent.idempotency_key).status == 'recorded'


def test_forged_mac_denied_for_credential_proof():
    """A credential proof without a valid host MAC is refused."""
    # Garbage MAC: denied.
    try:
        issue_sender_credential_proof(
            principal_id='p-1', role='delivery_sender', expires_at=_FUTURE,
            mac='0' * 64)
    except PermissionError:
        pass
    else:
        raise AssertionError('forged MAC must be denied')
    # Empty MAC: denied.
    try:
        issue_sender_credential_proof(
            principal_id='p-1', role='delivery_sender', expires_at=_FUTURE,
            mac='')
    except PermissionError:
        pass
    else:
        raise AssertionError('empty MAC must be denied')
    # MAC for different fields: denied.
    wrong_fields_mac = _credential_mac('p-2', 'delivery_sender', _FUTURE)
    try:
        issue_sender_credential_proof(
            principal_id='p-1', role='delivery_sender', expires_at=_FUTURE,
            mac=wrong_fields_mac)
    except PermissionError:
        pass
    else:
        raise AssertionError('MAC for different fields must be denied')
    # Allowed: real test-secret MAC over the exact fields.
    proof = issue_sender_credential_proof(
        principal_id='p-1', role='delivery_sender', expires_at=_FUTURE,
        mac=_credential_mac('p-1', 'delivery_sender', _FUTURE))
    assert verify_sender_principal(proof).role == 'delivery_sender'


def test_wrong_secret_mac_denied_for_credential_proof():
    """A signature computed under a different seal key is refused."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
    )
    from oracle_brain.seal import seal_payload
    wrong = Ed25519PrivateKey.generate().sign(
        seal_payload(SENDER_CREDENTIAL_PURPOSE, 'p-1', 'delivery_sender', _FUTURE)
    ).hex()
    try:
        issue_sender_credential_proof(
            principal_id='p-1', role='delivery_sender', expires_at=_FUTURE,
            mac=wrong)
    except PermissionError:
        pass
    else:
        raise AssertionError('wrong-key signature must be denied')


def test_caller_built_settings_enable_denied():
    """Enabling participation without a host-authorized MAC is refused."""
    rs = record_settings
    try:
        rs(meeting_id='m-1', enabled=True,
           recorded_at='2026-10-16T12:00:00Z')
    except PermissionError:
        pass
    else:
        raise AssertionError('caller-built enabled settings must be denied')
    try:
        rs(meeting_id='m-1', enabled=True,
           recorded_at='2026-10-16T12:00:00Z', enable_proof_mac='0' * 64)
    except PermissionError:
        pass
    else:
        raise AssertionError('forged enable MAC must be denied')
    # Allowed: real test-secret enable MAC.
    settings = rs(meeting_id='m-1', enabled=True,
                  recorded_at='2026-10-16T12:00:00Z',
                  enable_proof_mac=_enable_mac('m-1'))
    assert settings.enabled is True


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
                               recorded_at='2026-10-16T12:00:00Z',
                               enable_proof_mac=_enable_mac('m-1'))
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
                               recorded_at='2026-10-16T12:00:00Z',
                               enable_proof_mac=_enable_mac('m-1'))
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
                               recorded_at='2026-10-16T12:00:00Z',
                               enable_proof_mac=_enable_mac('m-1'))
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
                               recorded_at='2026-10-16T12:00:00Z',
                               enable_proof_mac=_enable_mac('m-1'))
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


def test_evaluate_turn_rechecks_host_settings_before_recording_intent():
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z',
                               enable_proof_mac=_enable_mac('m-1'))
    object.__setattr__(settings, 'channel', 'meeting_chat')
    turn = InboundTurn(turn_id='t-1', meeting_id='m-1', speaker_id='p-1',
                       text='Oracle?', addresses_oracle=True)
    import pytest
    with pytest.raises(PermissionError):
        evaluate_turn(settings, turn,
                      MembershipView(determined=True, shared_access=frozenset({'p-1'})),
                      DeliveryLedger(), receipt_id='r-1', intent_id='i-1',
                      answer_body='invented answer', recorded_at='now')


@pytest.mark.parametrize(('field', 'changed'), [
    ('receipt_id', 'other-receipt'), ('channel', 'meeting_chat'),
    ('provider_message_id', 'other-provider'), ('sent_at', 'different-timestamp'),
])
def test_delivery_signature_binds_complete_receipt(field, changed):
    ledger, intent = DeliveryLedger(), _intent()
    ledger.record_intent(intent)
    args = dict(receipt_id='r', channel='meeting_text', sent_at='now',
                provider_message_id='provider')
    proof = _action_mac(intent.intent_id, 'sent', 'now', ledger=ledger,
                        receipt_id='r', provider_message_id='provider')
    args[field] = changed
    with pytest.raises(PermissionError):
        ledger.mark_sent(intent.idempotency_key, action_mac=proof, **args)
    assert ledger.replay(intent.idempotency_key).status == 'recorded'


@pytest.mark.parametrize('other', [dict(), dict(meeting_id='other-meeting'),
                                  dict(turn_id='other-turn'), dict(body='other answer')])
def test_delivery_signature_never_crosses_ledger_or_intent_identity(other):
    source, target = DeliveryLedger(), DeliveryLedger()
    original, different = _intent(), _intent(**other)
    source.record_intent(original)
    target.record_intent(different)
    proof = _action_mac(original.intent_id, 'sent', 'now', ledger=source,
                        receipt_id='r', provider_message_id='provider')
    with pytest.raises(PermissionError):
        target.mark_sent(different.idempotency_key, receipt_id='r', channel='meeting_text',
                         sent_at='now', provider_message_id='provider', action_mac=proof)
    assert target.replay(different.idempotency_key).status == 'recorded'


def test_delivery_action_expiry_checked_at_consumption(monkeypatch):
    import oracle_brain.meetings.delivery as delivery
    ledger, intent = DeliveryLedger(), _intent()
    ledger.record_intent(intent)
    proof = _action_mac(intent.intent_id, 'sent', 'now', ledger=ledger,
                        receipt_id='r', provider_message_id='provider')
    monkeypatch.setattr(delivery.time, 'time', lambda: proof.expires_at + 1)
    with pytest.raises(PermissionError, match='expired'):
        ledger.mark_sent(intent.idempotency_key, receipt_id='r', channel='meeting_text',
                         sent_at='now', provider_message_id='provider', action_mac=proof)


def test_delivery_nonce_cannot_be_consumed_twice():
    ledger, intent = DeliveryLedger(), _intent()
    ledger.record_intent(intent)
    proof = _action_mac(intent.intent_id, 'failed', 'now', ledger=ledger, receipt_id='r')
    assert ledger.mark_failed(intent.idempotency_key, receipt_id='r',
                              channel='meeting_text', failed_at='now', action_mac=proof).status == 'failed'
    with pytest.raises(PermissionError, match='nonce reused'):
        ledger.mark_failed(intent.idempotency_key, receipt_id='r', channel='meeting_text',
                           failed_at='now', action_mac=proof)


def test_host_disable_stops_old_enabled_turn_without_intent():
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z',
                               enable_proof_mac=_enable_mac('m-1'))
    turn = InboundTurn(turn_id='t', meeting_id='m-1', speaker_id='p',
                       text='Oracle?', addresses_oracle=True)
    ledger = DeliveryLedger()
    with pytest.raises(PermissionError):
        _raw_evaluate(settings, turn, MembershipView(True, frozenset({'p'})), ledger,
                      receipt_id='r', intent_id='i', answer_body='invented answer',
                      recorded_at='now', current_state_reader=lambda meeting, nonce:
                      host_current(meeting, nonce, generation=2, enabled=False))
    assert not ledger._by_key


@pytest.mark.parametrize(('field', 'changed'), [
    ('meeting_id', 'other-meeting'), ('turn_id', 'other-turn'),
    ('intent_id', 'other-intent'), ('body', 'other answer'),
    ('idempotency_key', 'other-key'), ('created_at', 'other-created-at'),
])
def test_delivery_signature_rechecks_every_immutable_intent_field(field, changed):
    ledger, intent = DeliveryLedger(), _intent()
    key = intent.idempotency_key
    ledger.record_intent(intent)
    proof = _action_mac(intent.intent_id, 'sent', 'now', ledger=ledger,
                        receipt_id='r', provider_message_id='provider')
    object.__setattr__(intent, field, changed)
    with pytest.raises(PermissionError):
        ledger.mark_sent(key, receipt_id='r', channel='meeting_text', sent_at='now',
                         provider_message_id='provider', action_mac=proof)
    assert ledger.replay(key).status == 'recorded'


def test_broadcast_requires_fresh_complete_authorized_recipient_set():
    from meeting_testkit import host_audience
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z', enable_proof_mac=_enable_mac('m-1'))
    turn = InboundTurn('turn-audience', 'm-1', 'p-1', 'Oracle?', addresses_oracle=True)
    membership = MembershipView(True, frozenset({'p-1', 'p-2'}))
    def decide(reader):
        ledger = DeliveryLedger()
        result = _raw_evaluate(settings, turn, membership, ledger, receipt_id='audience-r',
            intent_id='audience-i', answer_body='permitted quoted answer', recorded_at='now',
            current_state_reader=host_current, current_audience_reader=reader)
        return result, ledger
    def all_allowed(*args):
        return host_audience(*args, recipients=frozenset({'p-1', 'p-2'}), authorized=frozenset({'p-1', 'p-2'}))
    result, ledger = decide(all_allowed)
    assert result.decision == 'respond' and result.intent.recipient_ids == ('p-1', 'p-2')
    assert result.intent.audience_sha256 and ledger.replay(result.intent.idempotency_key).status == 'recorded'
    for reader in (None,
            lambda *args: host_audience(*args, complete=False),
            lambda *args: host_audience(*args, recipients=frozenset({'p-1', 'denied'})),
            lambda *args: host_audience(*args, recipients=frozenset()),
            lambda *args: host_audience(*args, recipients=frozenset({'other'}), authorized=frozenset({'other'}))):
        with pytest.raises(PermissionError):
            decide(reader)
    # A new denied attendee invalidates subsequent broadcast even with the same speaker.
    current = {'recipients': frozenset({'p-1'})}
    def changing(*args):
        return host_audience(*args, recipients=current['recipients'])
    assert decide(changing)[0].decision == 'respond'
    current['recipients'] = frozenset({'p-1', 'new-denied-attendee'})
    with pytest.raises(PermissionError):
        decide(changing)


def test_broadcast_rejects_replayed_or_tampered_host_audience():
    from dataclasses import replace
    from meeting_testkit import host_audience
    settings = record_settings(meeting_id='m-1', enabled=True,
                               recorded_at='2026-10-16T12:00:00Z', enable_proof_mac=_enable_mac('m-1'))
    turn = InboundTurn('turn-audience', 'm-1', 'p-1', 'Oracle?', addresses_oracle=True)
    membership = MembershipView(True, frozenset({'p-1'}))
    cached = []
    def stale(*args):
        if not cached: cached.append(host_audience(*args))
        return cached[0]
    def decide(reader):
        ledger = DeliveryLedger()
        return _raw_evaluate(settings, turn, membership, ledger, receipt_id='r', intent_id='i',
            answer_body='allowed', recorded_at='now', current_state_reader=host_current,
            current_audience_reader=reader)
    assert decide(stale).decision == 'respond'
    with pytest.raises(PermissionError): decide(stale)
    for field in ({'answer_sha256': 'f'*64}, {'channel': 'other'}, {'settings_generation': 9},
                  {'valid_until': 0.0}, {'mac': '0'*128}):
        with pytest.raises(PermissionError):
            decide(lambda *args: replace(host_audience(*args), **field))
