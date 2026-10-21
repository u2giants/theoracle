"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.meetings.participation is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.meetings.participation'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        'S08 meeting participation implementation absent on main (not built; no merged building block). Named offline gate test retained with the s08-meeting-participation branch assertions; activates when meetings.participation lands.',
        allow_module_level=True,
    )

"""Host-gated participation, proactive budget, and durable receipts. No meeting joined."""
import pytest

from oracle_brain.meetings.participation import (
    ENABLE_PROOF_PURPOSE, InterventionBudget, decide_addressed,
    can_intervene_proactively, record_proactive_intervention, record_settings,
)


from meeting_testkit import SETTINGS_EXPIRY, host_current
from oracle_brain.meetings.participation import record_settings as _raw_record_settings


def record_settings(**fields):
    if fields.get('enabled'):
        fields.setdefault('generation', 1)
        fields.setdefault('valid_until', SETTINGS_EXPIRY)
    return _raw_record_settings(**fields)


from oracle_brain.meetings.participation import (
    decide_addressed as _raw_decide, can_intervene_proactively as _raw_proactive,
)


def decide_addressed(settings, **fields):
    fields.setdefault('current_state_reader', host_current)
    return _raw_decide(settings, **fields)


def can_intervene_proactively(settings, budget, **fields):
    fields.setdefault('current_state_reader', host_current)
    return _raw_proactive(settings, budget, **fields)


def _test_mac(purpose, *fields):
    """Produce a purpose-tagged seal via the signer CLI (test host stand-in)."""
    from seal_testkit import sign_seal
    return sign_seal(purpose, *fields)


def _enable_mac(meeting_id, **configuration):
    from oracle_brain.meetings.participation import settings_authority_payload
    return _test_mac(ENABLE_PROOF_PURPOSE, settings_authority_payload(
        meeting_id=meeting_id, recorded_at='2026-10-16T12:00:00Z',
        generation=1, valid_until=SETTINGS_EXPIRY, **configuration))


def _settings(**kw):
    base = dict(meeting_id='m-1', enabled=True, recorded_at='2026-10-16T12:00:00Z',
                generation=1, valid_until=SETTINGS_EXPIRY)
    base.update(kw)
    if base.get('enabled') and 'enable_proof_mac' not in base:
        from oracle_brain.meetings.participation import settings_authority_payload
        base['enable_proof_mac'] = _test_mac(ENABLE_PROOF_PURPOSE, settings_authority_payload(**base))
    return record_settings(**base)


def test_participation_is_off_until_host_explicitly_enables():
    default = record_settings(meeting_id='m-1')
    assert default.enabled is False and default.channel == 'meeting_text'
    receipt = decide_addressed(default, turn_id='t-1', receipt_id='r-1',
                               recorded_at='2026-10-16T12:00:00Z')
    assert receipt.status == 'suppressed' and receipt.reason == 'participation_disabled'


def test_enabling_requires_recorded_settings_and_addressed_turn_records_intent():
    try:
        record_settings(meeting_id='m-1', enabled=True)
    except ValueError:
        pass
    else:
        raise AssertionError('enabling without recorded_at must fail')
    settings = _settings()
    receipt = decide_addressed(settings, turn_id='t-1', receipt_id='r-1',
                               recorded_at='2026-10-16T12:00:00Z')
    assert receipt.status == 'recorded' and receipt.channel == 'meeting_text'


def test_proactive_clarification_is_off_by_default_with_cooldown_and_cap():
    settings = _settings(proactive_enabled=True, cooldown_seconds=120, max_interventions=3)
    assert _settings().proactive_enabled is False
    empty = InterventionBudget()
    assert can_intervene_proactively(settings, empty, now_seconds=0.0) is True
    spent = InterventionBudget(count=3, last_at_seconds=1000.0)
    assert can_intervene_proactively(settings, spent, now_seconds=1120.0) is False
    cooling = InterventionBudget(count=1, last_at_seconds=1000.0)
    assert can_intervene_proactively(settings, cooling, now_seconds=1050.0) is False
    assert can_intervene_proactively(settings, cooling, now_seconds=1120.0) is True
    advanced = record_proactive_intervention(cooling)
    assert advanced.count == 2


def test_channel_is_configurable_and_invalid_channel_rejected():
    chat = _settings(channel='meeting_chat')
    assert chat.channel == 'meeting_chat'
    try:
        _settings(channel='voice')
    except ValueError:
        pass
    else:
        raise AssertionError('unsupported channel must fail')


def test_silence_when_disabled_still_returns_a_durable_receipt():
    settings = record_settings(meeting_id='m-1', recorded_at='2026-10-16T12:00:00Z')
    receipt = decide_addressed(settings, turn_id='t-9', receipt_id='r-9',
                               recorded_at='2026-10-16T12:00:01Z')
    assert receipt.status == 'suppressed' and receipt.turn_id == 't-9'


def test_direct_enabled_settings_without_host_proof_rejected():
    from oracle_brain.meetings.participation import ParticipationSettings
    with pytest.raises(PermissionError, match='host-authorized'):
        ParticipationSettings(meeting_id='m-1', enabled=True,
                              recorded_at='2026-10-16T12:00:00Z')


@pytest.mark.parametrize(('field', 'value'), [
    ('meeting_id', 'm-other'), ('channel', 'meeting_chat'),
    ('proactive_enabled', True), ('cooldown_seconds', 0),
    ('max_interventions', 999), ('recorded_at', '2026-10-17T12:00:00Z'),
    ('enable_proof_mac', '0' * 128),
])
def test_consumers_reject_mutated_signed_settings(field, value):
    settings = _settings()
    # Deliberately bypass frozen dataclass protection as hostile same-process code.
    object.__setattr__(settings, field, value)
    with pytest.raises(PermissionError):
        decide_addressed(settings, turn_id='t-1', receipt_id='r-1', recorded_at='now')
    with pytest.raises(PermissionError):
        can_intervene_proactively(settings, InterventionBudget(), now_seconds=0)


def test_enabled_bit_cannot_be_forged_after_disabled_construction():
    settings = record_settings(meeting_id='m-1', recorded_at='now')
    object.__setattr__(settings, 'enabled', True)
    with pytest.raises(PermissionError, match='host-authorized'):
        decide_addressed(settings, turn_id='t-1', receipt_id='r-1', recorded_at='now')


def test_valid_host_proof_retained_and_consumed_for_both_actions():
    settings = _settings(proactive_enabled=True)
    assert settings.enable_proof_mac
    assert decide_addressed(settings, turn_id='t-1', receipt_id='r-1',
                            recorded_at='now').status == 'recorded'
    assert can_intervene_proactively(settings, InterventionBudget(), now_seconds=0)


def test_enabled_settings_need_fresh_independent_current_state():
    settings = _settings()
    with pytest.raises(PermissionError, match='independent current'):
        _raw_decide(settings, turn_id='t', receipt_id='r', recorded_at='now')


@pytest.mark.parametrize('damage', ['disabled', 'new_generation', 'caller_integer',
                                    'forged_signature', 'old_challenge', 'expired_current'])
def test_old_enabled_settings_cannot_outlive_host_current_state(damage):
    from dataclasses import replace
    import time
    settings = _settings(proactive_enabled=True)
    def reader(meeting_id, challenge):
        if damage == 'disabled':
            return host_current(meeting_id, challenge, generation=2, enabled=False)
        if damage == 'new_generation':
            return host_current(meeting_id, challenge, generation=2)
        if damage == 'caller_integer':
            return 1
        current = host_current(meeting_id, challenge)
        if damage == 'forged_signature':
            return replace(current, mac='00' * 64)
        if damage == 'old_challenge':
            return host_current(meeting_id, 'old-verifier-challenge')
        return replace(current, valid_until=time.time() - 1)
    with pytest.raises(PermissionError):
        _raw_decide(settings, turn_id='t', receipt_id='r', recorded_at='now',
                    current_state_reader=reader)
    with pytest.raises(PermissionError):
        _raw_proactive(settings, InterventionBudget(), now_seconds=0,
                       current_state_reader=reader)


def test_expiry_is_enforced_again_at_consumption(monkeypatch):
    import oracle_brain.meetings.participation as policy
    settings = _settings()
    monkeypatch.setattr(policy.time, 'time', lambda: SETTINGS_EXPIRY + 1)
    with pytest.raises(PermissionError, match='expired'):
        decide_addressed(settings, turn_id='t', receipt_id='r', recorded_at='now')


def test_current_attestation_cannot_be_replayed_for_second_challenge():
    settings = _settings()
    held = []
    def reader(meeting_id, challenge):
        if not held:
            held.append(host_current(meeting_id, challenge))
        return held[0]
    assert _raw_decide(settings, turn_id='t1', receipt_id='r1', recorded_at='now',
                       current_state_reader=reader).status == 'recorded'
    with pytest.raises(PermissionError, match='superseded'):
        _raw_decide(settings, turn_id='t2', receipt_id='r2', recorded_at='now',
                    current_state_reader=reader)


def test_new_host_generation_can_enable_with_new_configuration_and_proof():
    settings = _settings(generation=2, channel='meeting_chat')
    receipt = _raw_decide(settings, turn_id='t', receipt_id='r', recorded_at='now',
                          current_state_reader=lambda meeting, challenge:
                          host_current(meeting, challenge, generation=2))
    assert receipt.status == 'recorded' and receipt.channel == 'meeting_chat'
