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


def _test_mac(purpose, *fields):
    """Produce a purpose-tagged seal via the signer CLI (test host stand-in)."""
    from seal_testkit import sign_seal
    return sign_seal(purpose, *fields)


def _enable_mac(meeting_id):
    return _test_mac(ENABLE_PROOF_PURPOSE, meeting_id)


def _settings(**kw):
    base = dict(meeting_id='m-1', enabled=True, recorded_at='2026-10-16T12:00:00Z')
    base.update(kw)
    if base.get('enabled') and 'enable_proof_mac' not in base:
        base['enable_proof_mac'] = _enable_mac(base['meeting_id'])
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
