"""No provider/store IO: exact request contracts, original text and paid-wire guards."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal
from uuid import uuid4
import hashlib,json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.native_factory import EmployeeConversationDispatchJobV1
from oracle_brain.hosting.conversation_native_v1 import validate_conversation_wire_v1,ConversationWireLiabilityUnknown,conversation_request_v1
from oracle_brain.hosting.conversation_service_v1 import parse_conversation_request_v1
from oracle_brain.interviews.utf8_reader_v1 import read_exact_utf8_v1
from oracle_brain.interviews.utf8_reviewer_v1 import review_exact_utf8_v1
from test_native_factory import job as existing_job

def conversation_job():
 base=existing_job();from test_conversation_text_pricing_v1 import scenario
 base=base.model_copy(update={'pricing':scenario()[2]});operation=uuid4();p=base.processing_request.model_copy(update={'purpose':'employee-conversation'})
 data=base.model_dump(mode='python')|dict(dispatch_id=operation,artifact_id=operation,purpose='employee-conversation',processing_request=p,
   pricing=base.pricing,schema_version=1,job_schema='employee-conversation-dispatch-v1',thread_id=uuid4(),thread_revision=2,employee_event_id=uuid4(),
   original_sha256='a'*64,billing_bounds_sha256='b'*64,pending_question_id=uuid4(),qualified_population=(),qualified_population_sha256=digest({'source_refs':[]}))
 return EmployeeConversationDispatchJobV1(**data)

def actual_wire(j,**usage):
 return canonical_bytes(dict(model=j.pricing.model,choices=[dict(finish_reason='stop',message=dict(role='assistant',content='{"display_text":"Missing qualified evidence."}'))],usage=dict(cost='0.001',is_byok=False)|usage)).decode()

def test_utf8_original_negation_and_scope_survive_independent_byte_programs():
 raw='不允许未经复核就发货。仅限样品。\n原文保留。'.encode()
 text=read_exact_utf8_v1(raw);assert text.encode()==raw
 assert review_exact_utf8_v1(raw,text)==text
 with pytest.raises(ValueError):review_exact_utf8_v1(raw,text.replace('不允许','允许'))
@pytest.mark.parametrize('data',[b'',b'\xff',b'\x00',b' '*4,b'x'*32769])
def test_native_byte_programs_refuse_bad_originals(data):
 with pytest.raises((ValueError,UnicodeError)):read_exact_utf8_v1(data)
 with pytest.raises((ValueError,UnicodeError)):review_exact_utf8_v1(data,'anything')

def test_explicit_shared_wire_accepted_and_content_only_invalid_is_known_cost():
 j=conversation_job();assert validate_conversation_wire_v1(actual_wire(j),j)['usage']['is_byok'] is False
 q=json.loads(actual_wire(j));q['choices'][0]['finish_reason']='length'
 with pytest.raises(ValueError):validate_conversation_wire_v1(canonical_bytes(q).decode(),j)
@pytest.mark.parametrize('route',[True,None,'false',0])
def test_route_unknown_keeps_full_observed_upstream_liability(route):
 j=conversation_job()
 with pytest.raises(ConversationWireLiabilityUnknown) as e:validate_conversation_wire_v1(actual_wire(j,is_byok=route,cost_details={'upstream_inference_cost':'2'}),j)
 assert e.value.observed_actual_usd==Decimal('2.001')
@pytest.mark.parametrize('cost',[True,-1,'NaN','Infinity',None])
def test_bad_usage_cost_cannot_be_known_success(cost):
 j=conversation_job()
 with pytest.raises((PermissionError,ValueError)):validate_conversation_wire_v1(actual_wire(j,cost=cost),j)

def test_duplicate_nonfinite_paid_wire_never_known_success():
 j=conversation_job()
 with pytest.raises(PermissionError):validate_conversation_wire_v1('{"usage":{},"usage":{}}',j)
 with pytest.raises(PermissionError):validate_conversation_wire_v1('{"usage":{"cost":NaN}}',j)

@pytest.mark.parametrize('operation',['link_original','claim_response','complete_response','respond','fixture-start'])
def test_browser_cannot_supply_internal_original_or_model_operation(operation):
 q=dict(schema_version=1,operation=operation,caller_deadline=(datetime.now(timezone.utc)+timedelta(seconds=20)).isoformat())
 with pytest.raises(PermissionError):parse_conversation_request_v1(canonical_bytes(q))

def test_duplicate_canonical_request_and_naive_clock_refused():
 with pytest.raises(ValueError):parse_conversation_request_v1(b'{"schema_version":1,"schema_version":1}')
 with pytest.raises(ValueError):parse_conversation_request_v1(canonical_bytes(dict(schema_version=1,caller_deadline='2026-10-21T12:00:00',operation='list')))

@pytest.mark.parametrize('attempt',[True,2,0,'1'])
def test_no_second_conversation_attempt_or_coercion(attempt):
 j=conversation_job();data=j.model_dump(mode='python')|dict(attempt=attempt)
 with pytest.raises(ValueError):EmployeeConversationDispatchJobV1(**data)
