"""Offline gate test retained from the building-block branch. Invented/synthetic only.

Import guard: oracle_brain.ingest.meeting is required; skip with reason when absent.
"""
from __future__ import annotations

import importlib.util

import pytest

_REQUIRED = 'oracle_brain.ingest.meeting'
try:
    _spec = importlib.util.find_spec(_REQUIRED)
except ModuleNotFoundError:
    _spec = None
if _spec is None:
    pytest.skip(
        "S07 meeting dedup implementation absent on main (held PR #143 / branch claude/s07-invited-meeting). Named offline gate test retained with the branch's real assertions; activates when ingest.meeting lands.",
        allow_module_level=True,
    )

import pytest
from oracle_brain.ingest.meeting import Transcript, Turn, reconcile, reported_candidates
from oracle_brain.ingest.speakers import Speaker


def transcript(revision, *, final=False, text='reported instruction', origin='participant', tenant='tenant'):
    return Transcript(tenant, 'meeting', revision, (Turn('turn', revision, Speaker('p', 'Name'), text, origin),), final)


def test_duplicate_and_delayed_delivery_cannot_revert_final_correction():
    live = transcript(0)
    final = transcript(2, final=True, text='corrected instruction')
    accepted = reconcile(live, final)
    assert reconcile(accepted, final) is accepted
    assert reconcile(accepted, live) is accepted
    assert reported_candidates(accepted)[0].text == 'corrected instruction'


def test_conflicting_same_revision_and_cross_tenant_fail_visibly():
    current = transcript(1, final=True)
    with pytest.raises(ValueError, match='conflicting'):
        reconcile(current, transcript(1, final=True, text='different'))
    with pytest.raises(ValueError, match='cross-meeting'):
        reconcile(current, transcript(2, tenant='other'))
    with pytest.raises(ValueError, match='live transcript'):
        reconcile(current, transcript(2))


def test_live_and_oracle_words_never_become_employee_evidence():
    assert reported_candidates(transcript(0)) == ()
    assert reported_candidates(transcript(1, final=True, origin='oracle')) == ()


def test_final_snapshot_removes_live_turns_missing_from_final():
    final = Transcript('tenant', 'meeting', 2, (), True)
    assert reconcile(transcript(1), final).turns == ()


def test_duplicate_turn_and_invalid_origin_rejected():
    turn = transcript(0).turns[0]
    with pytest.raises(ValueError, match='duplicate turn'):
        Transcript('tenant', 'meeting', 0, (turn, turn))
    with pytest.raises(ValueError, match='unsupported'):
        transcript(0, origin='model')
