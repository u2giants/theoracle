"""Actual SQL019 self scope and independently appointed SQL017/022 answer scope."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4,UUID
import hashlib
import psycopg
from psycopg import sql
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.operating_model.conversation_control_v1 import ConversationConfigV1,ConversationAppointmentV1,load_conversation_settings_v1,ConversationControlV1
from oracle_brain.hosting.conversation_answer_v1 import ConversationAnswerV1

def installed_conversation(admin,state,h,settings,directory):
 directory.mkdir(mode=0o700);f=state['f'];login='answer_conversation_'+uuid4().hex[:12];until=settings.config.original_horizon
 leaf=uuid4()
 with psycopg.connect(admin) as c:
  owner=c.execute('SELECT actor_id FROM oracle2.appointments WHERE appointment_id=%s',(f['root'],)).fetchone()[0]
  c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS').format(sql.Identifier(login),sql.Literal('invented-conversation-answer-only')))
  c.execute(sql.SQL('GRANT oracle2_replacement_requester TO {}').format(sql.Identifier(login)))
  c.execute('INSERT INTO oracle2.hosting_role_runtime_admissions VALUES(%s,%s,%s,%s)',(login,settings.config.history.runtime_hash,settings.config.history.registry_hash,until))
  c.execute('INSERT INTO oracle2.hosting_request_principal_admissions VALUES(%s,%s,%s,%s,%s,%s)',(login,h['actor'],f['workspace'],settings.config.history.runtime_hash,settings.config.history.registry_hash,until))
  c.execute("INSERT INTO oracle2.appointments(appointment_id,workspace_id,actor_id,scope,granted_by,parent_id,expires_at) VALUES(%s,%s,%s,'conversation-self',%s,%s,%s)",(leaf,f['workspace'],h['actor'],owner,f['root'],until))
 url=psycopg.conninfo.make_conninfo(admin,user=login,password='invented-conversation-answer-only')
 def protected(name,raw):
  p=directory/name;p.write_bytes(raw);p.chmod(0o600);return dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest())
 ca=settings.config.history.ca_path
 c=ConversationConfigV1.model_validate(dict(schema_version=1,purpose='employee-conversation-control-v1',auth_issuer='https://invented-conversation.supabase.co/auth/v1',auth_project_id='invented-conversation',auth_user_id=uuid4(),employee_id=uuid4(),principal_id=h['actor'],workspace_id=f['workspace'],expected_session_role=login,expected_owner_role=settings.config.history.expected_owner,
  runtime_hash=settings.config.history.runtime_hash,registry_hash=settings.config.history.registry_hash,database_url=protected('database-url',url.encode()),database_ca=dict(path=ca,sha256=settings.config.history.ca_sha256),original_horizon=until,expires_at=until))
 cp=protected('config.json',canonical_bytes(c.model_dump(mode='json')))
 a=ConversationAppointmentV1(schema_version=1,purpose=c.purpose,config_sha256=cp['sha256'],principal_id=c.principal_id,workspace_id=c.workspace_id,expected_session_role=login,runtime_hash=c.runtime_hash,registry_hash=c.registry_hash,issuer_actor=settings.peer.issuer_actor,reviewer_actor=settings.peer.reviewer_actor,valid_from=datetime.now(timezone.utc)-timedelta(seconds=1),original_horizon=until,expires_at=until)
 ap=protected('appointment.json',canonical_bytes(a.model_dump(mode='json')))
 configured=load_conversation_settings_v1(cp['path'],cp['sha256'],ap['path'],ap['sha256'],settings.peer.issuer_actor,settings.peer.reviewer_actor)
 return ConversationControlV1(configured)

def exercise_actual_interview_answer(admin,state,h,settings,directory):
 control=installed_conversation(admin,state,h,settings,directory)
 deadline=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat()
 q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=deadline,mode='interview',topic='Invented packing handoff',language='en')
 initial=control.execute_v1(canonical_bytes(q));assert initial['question_count']==1
 turn=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=deadline,thread_id=initial['thread_id'],expected_revision=initial['revision'],operation='employee_turn',turn_id=str(uuid4()),text='What is reported in '+state['q']['payload']['consolidation_core']['model']['processes'][0]['label']+'?',language='en')
 committed=control.execute_v1(canonical_bytes(turn));pending=committed['pending_question_id']
 assert committed['question_count']==initial['question_count']==1 and pending==initial['pending_question_id']
 owner=ConversationAnswerV1(control,settings)
 try:
  shown=owner.present_turn_v1(committed,turn['turn_id'])
  assert shown['qualified_answer']['answer']['records'] and shown['question_count']==committed['question_count']
  assert shown['question_id']==pending and shown['company_policy_confirmed'] is False
  assert shown['answer_first']=='Current qualified evidence is shown below.'
  unchanged=control.snapshot_v1(UUID(initial['thread_id']))
  assert unchanged['revision']==committed['revision'] and unchanged['events']==committed['events']
  return owner,control,committed,turn['turn_id']
 except BaseException:
  owner.close();raise


def test_uninstalled_question_adapter_refuses_before_thread_or_SQL(monkeypatch):
 import pytest
 import oracle_brain.hosting.conversation_answer_v1 as owner
 monkeypatch.setattr(owner,'_ResultOwnedLoopV1',lambda *a:pytest.fail('uninstalled answer started a loop'))
 with pytest.raises(TypeError):ConversationAnswerV1(object(),object())
