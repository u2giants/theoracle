"""Real owned TLS SQL conversations; invented identities are not installation authority."""
from datetime import datetime,timezone,timedelta
from uuid import uuid4,UUID
import json
import os
import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.conversation_control_v1 import (
 ConversationConfigV1,ConversationAppointmentV1,load_conversation_settings_v1,ConversationControlV1,ConversationUnknown,ConversationConflict,ConversationDenied)
from oracle_brain.workflows.interview import InterviewWorkflowV1
from test_replacement_source_intake_sql import requester,call
from test_replacement_requester_sql import owned_admin,configured_settings

@pytest.fixture
def conversation(requester,tmp_path):
 x=requester;s=configured_settings(tmp_path,x)
 with owned_admin(x) as c:
  leaf=uuid4();c.execute('INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s)',(leaf,x['workspace'],x['actor'],'conversation-self',x['owner'],x['root'],x['until']))
 fields=('auth_issuer','auth_project_id','auth_user_id','employee_id','principal_id','workspace_id','expected_session_role','expected_owner_role','runtime_hash','registry_hash','database_url','database_ca','original_horizon','expires_at')
 config=ConversationConfigV1(schema_version=1,purpose='employee-conversation-control-v1',**{k:getattr(s.config,k) for k in fields})
 raw=canonical_bytes(config.model_dump(mode='json'));p=tmp_path/'conversation-config';p.write_bytes(raw);p.chmod(0o600)
 import hashlib
 seal=hashlib.sha256(raw).hexdigest()
 appointment=ConversationAppointmentV1(schema_version=1,purpose='employee-conversation-control-v1',config_sha256=seal,
  **{k:getattr(config,k) for k in ('principal_id','workspace_id','expected_session_role','runtime_hash','registry_hash','original_horizon','expires_at')},
  issuer_actor=s.expected_issuer_actor,reviewer_actor=s.expected_reviewer_actor,valid_from=s.appointment.valid_from)
 ar=canonical_bytes(appointment.model_dump(mode='json'));ap=tmp_path/'conversation-appointment';ap.write_bytes(ar);ap.chmod(0o600)
 settings=load_conversation_settings_v1(p,seal,ap,hashlib.sha256(ar).hexdigest(),s.expected_issuer_actor,s.expected_reviewer_actor)
 from oracle_brain.hosting._protected_control_listener_v1 import _request_fence_v1
 import time
 with _request_fence_v1(float(time.monotonic()+30)):
  yield x|dict(control=ConversationControlV1(settings),conversation_leaf=leaf,intake_settings=s)

def create(x,**changes):
 q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=x['until'].isoformat(),mode='interview',topic='Invented packing handoff',language='zh-Hans')|changes
 return q,x['control'].execute_v1(canonical_bytes(q))
def command(x,s,op='employee_turn',**changes):
 q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=x['until'].isoformat(),thread_id=s['thread_id'],expected_revision=s['revision'],operation=op)
 if op in ('employee_turn','correct','skip','unknown','referral'):q.update(turn_id=str(uuid4()),text='不允许未经复核就发货。仅限样品。',language='zh-Hans')
 q.update(changes);return q,x['control'].execute_v1(canonical_bytes(q))

def test_real_restart_original_chinese_correction_and_exact_recap(conversation):
 x=conversation;q,s=create(x);assert s['question_count']==1
 first=s['pending_question_id'];q,s=command(x,s);e=s['events'][-1]
 assert e['original_text']=='不允许未经复核就发货。仅限样品。' and e['payload']['confirmed'] is False
 x['control']=ConversationControlV1(x['control'].settings)
 assert x['control'].snapshot_v1(UUID(s['thread_id']))['pending_question_id']==s['pending_question_id']!=first
 q,s=command(x,s,'correct',corrects_event_id=e['event_id'],corrects_original_sha256=e['original_sha256'],text='样品也必须复核。')
 assert s['events'][-1]['corrects_event_id']==e['event_id'] and s['events'][-2]['original_text']==e['original_text']
 q,s=command(x,s,'review_recap',recap_revision=s['revision'],recap_sha256=s['recap_sha256'])
 assert s['reviewed_revision']==s['revision']-1 and s['company_policy_confirmed'] is False
 last=s['events'][-2]
 q,s=command(x,s,'correct',corrects_event_id=last['event_id'],corrects_original_sha256=last['original_sha256'])
 assert s['reviewed_revision'] is None and len(s['events'])==5

def test_maximum_eight_total_no_repeat_after_pause_resume(conversation):
 x=conversation;_,s=create(x);seen={s['pending_question_id']}
 for _ in range(7):
  _,s=command(x,s);assert s['pending_question_id'] not in seen;seen.add(s['pending_question_id'])
 assert s['question_count']==8
 _,s=command(x,s,'pause');pending=s['pending_question_id'];_,s=command(x,s,'resume')
 assert s['question_count']==8 and s['pending_question_id']==pending
 _,s=command(x,s);assert s['state']=='recap' and s['pending_question_id'] is None and s['question_count']==8

def test_direct_question_answer_first_preserves_pending_and_unknown_no_fact(conversation):
 from oracle_brain.workflows.interview import present
 x=conversation;_,s=create(x);pending=s['pending_question_id']
 _,s=command(x,s,text='What is the shipping rule?')
 shown=present(s);assert shown['answer_first'] and shown['question_id']==pending and s['question_count']==1
 _,s=command(x,s,'unknown',text='不知道')
 assert s['events'][-1]['payload']['proposal_text'] is None and s['events'][-1]['payload']['missing_reason']=='unknown'

@pytest.mark.parametrize('op',['skip','referral'])
def test_skip_referral_missing_never_contacts(conversation,op):
 x=conversation;_,s=create(x);_,s=command(x,s,op)
 assert s['events'][-1]['payload']['reported'] is False and s['events'][-1]['payload']['proposal_text'] is None

def test_exact_idempotency_collision_cas_and_status(conversation):
 x=conversation;q,s=create(x);assert x['control'].execute_v1(canonical_bytes(q))['thread_id']==s['thread_id']
 with pytest.raises(ConversationConflict):x['control'].execute_v1(canonical_bytes(q|dict(topic='changed')))
 q2,s2=command(x,s)
 assert x['control'].execute_v1(canonical_bytes(q2))['revision']==2
 with pytest.raises(ConversationConflict):command(x,s)
 state=x['control'].command_status_v1(UUID(q2['command_id']))
 assert state['state']=='committed' and state['resend_authorized'] is False
 assert x['control'].command_status_v1(uuid4())['state']=='UNKNOWN'

@pytest.mark.parametrize('change',[{'role':'assistant'},{'actor_id':str(uuid4())},{'qualifiedSourceRef':{}},{'question_count':0}])
def test_spoofed_client_authority_denied_without_mutation(conversation,change):
 x=conversation;_,s=create(x)
 with pytest.raises(ConversationDenied):command(x,s,**change)
 assert x['control'].snapshot_v1(UUID(s['thread_id']))['revision']==1

def test_scope_revocation_denies_read_and_write_even_intake_admitted(conversation):
 x=conversation;_,s=create(x)
 with owned_admin(x) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['conversation_leaf'],))
 with pytest.raises(ConversationDenied):x['control'].snapshot_v1(UUID(s['thread_id']))
 with pytest.raises(ConversationDenied):command(x,s)

def test_foreign_thread_and_stale_correction_refused(conversation):
 x=conversation;_,a=create(x);_,a=command(x,a);e=a['events'][-1];_,b=create(x)
 with pytest.raises(ConversationConflict):command(x,b,'correct',corrects_event_id=e['event_id'],corrects_original_sha256=e['original_sha256'])
 _,a=command(x,a,'correct',corrects_event_id=e['event_id'],corrects_original_sha256=e['original_sha256'])
 with pytest.raises(ConversationConflict):command(x,a,'correct',corrects_event_id=e['event_id'],corrects_original_sha256=e['original_sha256'])

def test_ordinary_chat_does_not_start_interview(conversation):
 x=conversation;_,s=create(x,mode='ordinary');assert s['question_count']==0 and s['pending_question_id'] is None
 _,s=command(x,s);assert s['question_count']==0 and s['events'][-1]['payload']['confirmed'] is False

def test_lost_commit_ack_remains_observable_no_auto_resend(conversation,monkeypatch):
 x=conversation;_,s=create(x);q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=x['until'].isoformat(),thread_id=s['thread_id'],expected_revision=1,operation='pause')
 settings=x['control'].settings;original=settings.current;count=[]
 def fail_after():
  count.append(1)
  if len(count)==4:raise PermissionError('synthetic postcommit currentness loss')
  return original()
 monkeypatch.setattr(type(settings),'current',lambda self: fail_after())
 with pytest.raises(ConversationUnknown):x['control'].execute_v1(canonical_bytes(q))
 monkeypatch.setattr(type(settings),'current',lambda self: original())
 assert x['control'].command_status_v1(UUID(q['command_id']))['state']=='committed'
 assert x['control'].snapshot_v1(UUID(s['thread_id']))['revision']==2

def test_direct_fixed_sql_capability_appends_original(conversation):
 x=conversation;_,s=create(x)
 q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=x['until'].isoformat(),thread_id=s['thread_id'],expected_revision=1,operation='employee_turn',turn_id=str(uuid4()),text='Invented answer',language='en')
 observed=call(x,'apply_conversation_command_v1',canonical_bytes(q))
 assert observed['revision']==2 and observed['events'][-1]['original_text']=='Invented answer'


def test_pause_retained_across_invented_days_resumes_same_question_without_reset(conversation):
 x=conversation;_,s=create(x);_,s=command(x,s);_,s=command(x,s,'pause')
 with owned_admin(x) as c:
  c.execute("UPDATE oracle2.conversation_threads_v1 SET segment_started_at=segment_started_at-interval '4 days',segment_deadline=segment_deadline-interval '4 days' WHERE thread_id=%s",(s['thread_id'],))
 saved=ConversationControlV1(x['control'].settings).snapshot_v1(UUID(s['thread_id']))
 _,resumed=command(x,saved,'resume')
 assert resumed['pending_question_id']==s['pending_question_id'] and resumed['question_count']==2


def test_public_employee_turn_stays_32k_despite_generic_text_intake_extension(conversation):
 x=conversation;_,s=create(x)
 with pytest.raises(ConversationDenied):command(x,s,text='x'*32769)
 assert x['control'].snapshot_v1(UUID(s['thread_id']))['revision']==s['revision']
