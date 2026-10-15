"""Restart/resume on synthetic transcripts; accepted effects are never replayed."""
from oracle_brain.interviews.questions import FieldSpec, select_need
from oracle_brain.interviews.recap import build_recap
from oracle_brain.interviews.state import InterviewState, Turn

FIELDS = [FieldSpec('approver', 1), FieldSpec('cutoff_day', 2)]


def test_resume_after_restart_does_not_replay_or_reask():
    s = InterviewState('iv-1')
    need = select_need(FIELDS, s.known, asked=s.asked, declined=s.declined)
    assert s.record_question(need.key)
    assert s.apply_turn(Turn('t1', need.key, '发布经理', language='zh'))
    restored = InterviewState.loads(s.dumps())
    assert restored.apply_turn(Turn('t1', need.key, '发布经理', language='zh')) is False
    assert restored.record_question('missing:approver') is False
    assert len(restored.turns) == 1 and restored.known['approver'] == '发布经理'
    assert select_need(FIELDS, restored.known, asked=restored.asked).key == 'missing:cutoff_day'


def test_dont_know_correction_and_assistant_exclusion_in_recap():
    s = InterviewState('iv-2')
    s.apply_turn(Turn('t1', 'missing:approver', 'Old Lead'))
    s.apply_turn(Turn('t2', 'missing:approver', 'New Lead', corrects='t1'))
    s.apply_turn(Turn('t3', 'missing:cutoff_day', 'Friday', speaker='assistant'))
    s.apply_turn(Turn('t4', 'missing:cutoff_day', None))
    assert select_need(FIELDS, s.known, asked=s.asked, declined=s.declined).key == 'example:approver'
    r = build_recap(s, [f.name for f in FIELDS])
    assert r.learned == (('approver', 'New Lead'),) and r.unconfirmed == ('cutoff_day',)
