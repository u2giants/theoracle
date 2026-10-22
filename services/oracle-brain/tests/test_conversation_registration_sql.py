"""Actual employee event→existing intake→same immutable owner→native SQL014.

Metadata link grants no source read. Only the invented installer later appoints
separate actual byte reader/reviewer roles; no fake qualified SourceRef exists.
"""
from pathlib import Path
from uuid import UUID,uuid4,uuid5
from types import SimpleNamespace
import hashlib
import psycopg
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.original_intake_v1 import OriginalIntakeFactoryV1,OriginalIntakeRequestV1,load_original_intake_settings_v1
from oracle_brain.hosting.conversation_control_v1 import ConversationControlV1,ConversationDenied,ConversationUnknown,ConversationConflict
from oracle_brain.workflows.interview import InterviewWorkflowV1
from test_durable_interview_sql import conversation,create,command
from test_replacement_source_intake_sql import requester,call
from test_replacement_requester_sql import owned_admin,configured_settings
from test_conversation_original_sql import write,appointed_native_original_phases_v1,reading_then_review

def text_intake(x):
 s=x['intake_settings'];a=s.appointment.model_copy(update={'media_types':('application/pdf','text/plain')});ah=write(s.appointment_path,a)
 return OriginalIntakeFactoryV1(load_original_intake_settings_v1(s.config_path,s.config_sha256,s.appointment_path,ah,s.expected_issuer_actor,s.expected_reviewer_actor))
def initial(x):
 _,s=create(x);_,s=command(x,s);return s,s['events'][-1]
def claim(x,s,event):
 q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=x['until'].isoformat(),thread_id=s['thread_id'],expected_revision=s['revision'],operation='claim_original',event_id=event['event_id'])
 return x['control']._call('apply',(canonical_bytes(q),))
def link(x,s,event,source):
 q=dict(schema_version=1,command_id=str(uuid4()),caller_deadline=x['until'].isoformat(),thread_id=s['thread_id'],expected_revision=s['revision'],operation='link_original',event_id=event['event_id'],source_id=str(source.sourceId),source_revision=source.revision)
 return x['control']._call('apply',(canonical_bytes(q),))
def intake_event(intake,event,*,data=None,filename=None):
 data=event['original_text'].encode() if data is None else data
 return intake.intake_text_v1(source_id=None,expected_head=0,idempotency_key=uuid4(),filename=filename or event['event_id']+'.txt',original_sha256=hashlib.sha256(data).hexdigest(),data=data)

def test_actual_composed_registration_restart_no_resend_and_distinct_native_qualification(conversation,tmp_path):
 x=conversation;s,event=initial(x);intake=text_intake(x);workflow=InterviewWorkflowV1(x['control'])
 saved=workflow.register_original_v1(UUID(s['thread_id']),UUID(event['event_id']),intake)
 linkage=saved['events'][-1]['payload'];assert saved['events'][-1]['operation']=='link_original'
 assert linkage['source_read_granted'] is False and linkage['qualification_authorized'] is False
 assert saved['source_qualified'] is False and saved['company_policy_confirmed'] is False
 with owned_admin(x) as c:
  assert c.execute('SELECT count(*) FROM oracle2.appointments WHERE workspace_id=%s AND actor_id=%s AND scope=%s',(x['workspace'],x['actor'],'source-read:'+linkage['source_id'])).fetchone()==(0,)
  assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
 # Own metadata link does not unlock the retained ordinary source head/read cap.
 with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'replacement_source_head_v1',UUID(linkage['source_id']))
 restored=InterviewWorkflowV1(ConversationControlV1(x['control'].settings))
 assert restored.register_original_v1(UUID(s['thread_id']),UUID(event['event_id']),intake)['events']==saved['events']
 with owned_admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)
 snapshot=SimpleNamespace(sourceId=UUID(linkage['source_id']),originalSha256=event['original_sha256'],filename=event['event_id']+'.txt')
 with appointed_native_original_phases_v1(x,snapshot,event['original_text'].encode(),intake.settings,tmp_path) as native:
  _,qualified=reading_then_review(native,expire_reader=True)
  assert qualified.source_ref.source_id==snapshot.sourceId and qualified.source_ref.original_sha256==event['original_sha256']
 # Reader/reviewer appointments are for their distinct principals, not employee.
 with pytest.raises(psycopg.errors.InsufficientPrivilege):call(x,'replacement_source_head_v1',snapshot.sourceId)

@pytest.mark.parametrize('attack',['no-claim','wrong-hash','wrong-count','not-finalized','corrected','control-origin','intake-revoked'])
def test_metadata_link_exact_current_original_and_finalized_own_intake_only(conversation,attack):
 x=conversation;s,event=initial(x);intake=text_intake(x)
 if attack=='control-origin':
  with pytest.raises((ConversationDenied,ConversationUnknown,ConversationConflict,Exception)):
   # Public control event cannot become employee original evidence.
   claim(x,s,s['events'][0])
  return
 if attack!='no-claim':s=claim(x,s,event)
 data=event['original_text'].encode()
 if attack=='wrong-hash':data='只'.encode()+data[len('不'.encode()):]
 if attack=='wrong-count':data+=b' extra'
 if attack=='not-finalized':
  q=OriginalIntakeRequestV1(source_id=None,expected_head=0,idempotency_key=uuid4(),filename=event['event_id']+'.txt',original_sha256=hashlib.sha256(data).hexdigest(),byte_count=len(data),media_type='text/plain')
  r=intake._reserve_original_v1(q,caller_deadline=intake.settings.current())
  source=SimpleNamespace(sourceId=r.reservation.source_id,revision=r.reservation.revision)
 else:source=intake_event(intake,event,data=data)
 if attack=='corrected':_,s=command(x,s,'correct',corrects_event_id=event['event_id'],corrects_original_sha256=event['original_sha256'],text='Correction retained separately.')
 if attack=='intake-revoked':
  with owned_admin(x) as c:c.execute('UPDATE oracle2.appointments SET revoked_at=clock_timestamp() WHERE appointment_id=%s',(x['leaf'],))
 with pytest.raises(ConversationDenied):link(x,s,event,source)
 assert x['control'].snapshot_v1(UUID(s['thread_id']))['revision']==s['revision']

def test_registration_uncertain_intake_never_repeats_original_effect(conversation,monkeypatch):
 x=conversation;s,event=initial(x);intake=text_intake(x);original=OriginalIntakeFactoryV1.intake_text_v1;calls=[]
 def lose(self,**kw):calls.append(1);original(self,**kw);raise RuntimeError('invented acknowledgement lost after actual finalization')
 monkeypatch.setattr(OriginalIntakeFactoryV1,'intake_text_v1',lose)
 workflow=InterviewWorkflowV1(x['control'])
 with pytest.raises(RuntimeError):workflow.register_original_v1(UUID(s['thread_id']),UUID(event['event_id']),intake)
 with pytest.raises(ConversationUnknown):workflow.register_original_v1(UUID(s['thread_id']),UUID(event['event_id']),intake)
 assert calls==[1]
 with owned_admin(x) as c:assert c.execute('SELECT count(*) FROM oracle2.source_intake_reservations_v1 WHERE workspace_id=%s',(x['workspace'],)).fetchone()==(1,)


@pytest.mark.parametrize('same_workspace',[True,False])
def test_other_actual_actor_or_workspace_cannot_supply_employee_original_link(conversation,admin_url,tmp_path,same_workspace):
 x=conversation;s,event=initial(x);s=claim(x,s,event)
 gen=requester.__wrapped__(admin_url);other=next(gen)
 try:
  if same_workspace:
   old=other['workspace']
   with owned_admin(x) as c:
    c.execute('UPDATE oracle2.hosting_request_principal_admissions SET workspace_id=%s WHERE role_name=%s',(x['workspace'],other['login']))
    c.execute('UPDATE oracle2.appointments SET workspace_id=%s WHERE workspace_id=%s',(x['workspace'],old))
   other=other|dict(workspace=x['workspace'])
  folder=tmp_path/'other-actual-intake';folder.mkdir(mode=0o700)
  other['intake_settings']=configured_settings(folder,other)
  source=intake_event(text_intake(other),event)
  with pytest.raises(ConversationDenied):link(x,s,event,source)
 finally:
  try:next(gen)
  except StopIteration:pass
