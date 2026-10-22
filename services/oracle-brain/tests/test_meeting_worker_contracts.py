"""Pure closed wire validation; no admitted worker or actual SQL proof."""
import base64,hashlib
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes
from oracle_brain.meetings.worker_contracts import MeetingWorkerRequestV1,MeetingWorkerPacketV1,MAX_RESPONSE_WIRE
ID=str(uuid4());HASH='a'*64
request=dict(schema_version=1,operation='prepare',operation_id=None,claim_event_id=None,wire_base64=None,error=None,caller_deadline='2099-01-01T00:00:00Z')
def parse(value):return MeetingWorkerRequestV1.model_validate_json(canonical_bytes(value))
@pytest.mark.parametrize('change',[{'schema_version':True},{'actor_id':ID},{'url':'https://foreign.example.test'},{'operation':['claim']},{'operation_id':ID},{'wire_base64':''},{'error':'retry'}])
def test_no_http_authority_or_coercion(change):
 with pytest.raises(ValueError):parse(request|change)
def test_exact_observed_partial_empty_and_full_wire_are_closed_bounded_bytes():
 for raw in (b'',b'HTTP/1.1 200 OK\r\n',bytes(MAX_RESPONSE_WIRE)):
  q=parse(request|dict(operation='observe',operation_id=ID,claim_event_id=ID,wire_base64=base64.b64encode(raw).decode(),error='transport_uncertain'))
  assert q.observed_wire()==raw
 for body in ('Zg', 'Zh==',base64.b64encode(bytes(MAX_RESPONSE_WIRE+1)).decode()):
  with pytest.raises(ValueError):parse(request|dict(operation='observe',operation_id=ID,claim_event_id=ID,wire_base64=body,error='transport_uncertain'))
def packet():
 raw=b'{}'
 return dict(schema_version=1,state='claimed',effect_purpose='capture-create',principal_id=ID,worker_id=ID,workspace_id=ID,meeting_id=ID,provider_account='invented',operation_id=ID,claim_event_id=ID,request_sha256=hashlib.sha256(raw).hexdigest(),bot_id=None,body_base64=base64.b64encode(raw).decode(),operation_policy_sha256=HASH,composer_program_sha256=None,valid_until='2099-01-01T00:00:00Z',executable=True,qualification=False,remote_stop_proven=False,observation_only=True,resend_authorized=False)
def test_only_first_claim_exposes_exact_digest_bound_body():
 p=packet();assert MeetingWorkerPacketV1.model_validate_json(canonical_bytes(p)).executable is True
 for change in ({'state':'UNKNOWN'},{'executable':False},{'request_sha256':HASH},{'bot_id':ID},{'schema_version':True},{'qualification':0},{'remote_stop_proven':1},{'provider_account':' invented'}):
  with pytest.raises(ValueError):MeetingWorkerPacketV1.model_validate_json(canonical_bytes(p|change))
