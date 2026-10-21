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


# Serialization remains a pure legacy helper. This named phase suite now also
# proves the operational owner survives a new controller with exact SQL history.
from test_durable_interview_sql import conversation,create,command
from test_replacement_source_intake_sql import requester
from oracle_brain.hosting.conversation_control_v1 import ConversationControlV1
from uuid import UUID

def test_actual_owned_store_resume_uses_same_pending_question_and_original(conversation):
    x=conversation;_,s=create(x);_,s=command(x,s);_,s=command(x,s,'pause')
    new=ConversationControlV1(x['control'].settings)
    saved=new.snapshot_v1(UUID(s['thread_id']))
    assert saved['events']==s['events'] and saved['state']=='paused'
    assert saved['events'][1]['original_text']=='不允许未经复核就发货。仅限样品。'
    x['control']=new;_,resumed=command(x,saved,'resume')
    assert resumed['pending_question_id']==saved['pending_question_id'] and resumed['question_count']==2
