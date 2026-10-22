"""Pure fixed adapter orchestration only; dependency is an invented owner stub.

No SQL, real mTLS, installed profile, provider, employee or admission proof.
"""
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4,UUID
import base64,hashlib
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.hosting.meeting_worker_service_v1 import _ParticipationWorkerAdapter
from oracle_brain.meetings.worker_contracts import MeetingWorkerPacketV1
ID=uuid4();CLAIM=uuid4();BOT=uuid4();HASH='a'*64;BODY=canonical_bytes({'to':'everyone','message':'先确认。'})
@pytest.fixture
def case():
 now=datetime.now(timezone.utc);end=now+timedelta(seconds=20)
 metadata=dict(intent_id=str(ID),claim_event_id=None,request_sha256=hashlib.sha256(BODY).hexdigest(),state='intent',delivery_revision=1,claim_current=False,valid_until=end.isoformat())
 calls=[]
 class Stub:
  operation_policy_sha256=HASH
  def prepare_latest_v1(self,**kw):calls.append(('prepare',kw));return dict(metadata)
  def status_v1(self,wanted,**kw):calls.append(('status',wanted,kw));assert wanted==ID;return dict(metadata)
  def status_latest_v1(self,**kw):return dict(metadata)
  def claim_v1(self,wanted,**kw):
   calls.append(('claim',wanted,kw));assert wanted==ID
   repeated=metadata['claim_event_id'] is not None
   metadata.update(state='inflight',claim_event_id=str(CLAIM),claim_current=True,delivery_revision=2)
   return SimpleNamespace(metadata=dict(metadata),body=None if repeated else BODY,bot_id=BOT,valid_until=end-timedelta(seconds=2))
  def receipt_identity_v1(self,wanted,claim,**kw):
   calls.append(('identity',wanted,claim));assert (wanted,claim)==(ID,CLAIM);return BOT,dict(metadata)
  def current_claim_v1(self,wanted,claim,sha,**kw):calls.append(('current',wanted,claim,sha));assert (wanted,claim,sha)==(ID,CLAIM,metadata['request_sha256']);return dict(metadata)
  def receipt_v1(self,wanted,**kw):calls.append(('observe',wanted,kw));metadata.update(state='provider-response-observed',claim_current=False);return dict(metadata)
 f=Stub();adapter=object.__new__(_ParticipationWorkerAdapter)
 adapter.settings=SimpleNamespace(factory=f,profile=SimpleNamespace(worker_id=ID,provider_account='invented'),participation=SimpleNamespace(config=SimpleNamespace(principal_id=ID,workspace_id=ID,meeting_id=ID,composer_sha256=HASH)))
 adapter._check=lambda deadline:end
 def run(operation_name,**changes):
  value=dict(schema_version=1,operation=operation_name,operation_id=None,claim_event_id=None,wire_base64=None,error=None,caller_deadline=end.isoformat().replace('+00:00','Z'))|changes
  return adapter.execute_v1(canonical_bytes(value))
 return run,metadata,calls,end

def test_only_actual_first_claim_returns_body_with_narrower_actual_lease(case):
 run,m,calls,end=case;prepared=run('prepare');assert prepared['state']=='prepared' and prepared['body_base64'] is None
 claimed=run('claim',operation_id=str(ID));assert claimed['state']=='claimed' and claimed['bot_id']==str(BOT)
 assert base64.b64decode(claimed['body_base64'])==BODY
 assert datetime.fromisoformat(claimed['valid_until'].replace('Z','+00:00'))==end-timedelta(seconds=2)
 repeated=run('claim',operation_id=str(ID));assert repeated['state']=='UNKNOWN' and repeated['body_base64'] is None and repeated['executable'] is False
 assert all(v['caller_deadline']==end for _,*rest in calls if rest and isinstance((v:=rest[-1]),dict))

def test_current_uses_actual_own_forensic_identity_and_status_never_serves_bytes(case):
 run,m,calls,_=case;run('claim',operation_id=str(ID));current=run('current',operation_id=str(ID),claim_event_id=str(CLAIM))
 assert current['state']=='inflight' and current['body_base64'] is None and current['bot_id']==str(BOT)
 assert [c[0] for c in calls].count('current')==1
 m['claim_current']=False
 status=run('status',operation_id=str(ID),claim_event_id=str(CLAIM));assert status['state']=='UNKNOWN' and status['bot_id']==str(BOT) and status['executable'] is False

def test_actual_response_wire_only_closed_error_mapping_and_no_caller_status(case):
 run,m,calls,_=case;run('claim',operation_id=str(ID));wire=b'HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n'
 result=run('observe',operation_id=str(ID),claim_event_id=str(CLAIM),wire_base64=base64.b64encode(wire).decode(),error='invalid_response')
 assert result['body_base64'] is None and result['qualification'] is False and result['remote_stop_proven'] is False
 observed=next(c for c in calls if c[0]=='observe');assert observed[2]['raw_wire']==wire and observed[2]['error']=='framing'

@pytest.mark.parametrize('patch',[{'actor_id':str(ID)},{'operation':['claim']},{'operation_id':str(ID)},{'wire_base64':''},{'schema_version':True}])
def test_unknown_or_malformed_before_any_owner_call(case,patch):
 run,_,calls,_=case
 with pytest.raises(ValueError):run('prepare',**patch)
 assert calls==[]

def test_production_constructor_refuses_injected_settings_or_factory():
 with pytest.raises(PermissionError):_ParticipationWorkerAdapter(SimpleNamespace())
