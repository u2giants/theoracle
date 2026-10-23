"""Pure strict display DTO tests; hashes/typed records are NOT runtime authority."""
from datetime import timedelta
from uuid import uuid4
import hashlib,copy
import pytest
from test_assembly_context import context
from test_natural_business_question_v1 import business,case
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.question_effect_public_v1 import QuestionEffectPacketV1,validate_question_effect_scope_v1,nonobserved_question_effect_v1,OBSERVED_FIELDS,_scope_fields_v1
from oracle_brain.operating_model.qualified_answer_v1 import AnswerQueryV1,_pack_vector_answer_v1

@pytest.fixture
def packet(business):
 core,payload,now,scope=business;identifier=str(uuid4());original=' 不允许未经复核就发货。仅限样品。 '
 snapshot=dict(principal_id=identifier,workspace_id=str(core.model.workspace_id),thread_id=identifier,revision=2,mode='ordinary',recap=dict(events=[dict(origin='employee',event_id=identifier,original_text=original,original_sha256=hashlib.sha256(original.encode()).hexdigest())]))
 q=AnswerQueryV1(question='reported action',mode='global',scope=scope)
 body=_pack_vector_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now,vector_scores={a.assertion_id:.5 for a in core.assertions})
 value={k:None for k in OBSERVED_FIELDS}|_scope_fields_v1(snapshot)|dict(schema_version=1,protocol='question-effect-result-v1',state='observed',channel='web',checked_at=now.isoformat(),expires_at=(now+timedelta(seconds=20)).isoformat(),purpose='qualified-query-embedding-v1',operation_id=identifier,model_id=str(core.model.model_id),model_version=body.model_version,model_content_hash=body.model_content_hash,accepted_projection_event_id=identifier,accepted_receipt_body_sha256='a'*64,native_receipt_sha256='b'*64,wire_sha256='c'*64,settled_response_sha256='d'*64,answer=body.model_dump(mode='json'),synthesis=None,clarification=None,provider_dispatched=True,automatic_retry_allowed=False,semantic_entailment_verified=False,business_accepted=False)
 return value,snapshot,now

def test_closed_observed_display_binds_exact_original_and_independent_recipient_scope(packet):
 value,snapshot,_=packet;p=QuestionEffectPacketV1.model_validate_json(canonical_bytes(value))
 assert validate_question_effect_scope_v1(p,snapshot) is p and p.answer.query_embedding_used is True
 assert p.business_accepted is p.semantic_entailment_verified is p.automatic_retry_allowed is False
 for key in('principal_id','workspace_id','thread_id'):
  with pytest.raises(PermissionError):validate_question_effect_scope_v1(p,snapshot|{key:str(uuid4())})
 with pytest.raises(PermissionError):validate_question_effect_scope_v1(p,snapshot|{'revision':3})
 tampered=copy.deepcopy(snapshot);tampered['recap']['events'][0]['original_text']='允许未经复核就发货。'
 with pytest.raises(PermissionError):validate_question_effect_scope_v1(p,tampered)

@pytest.mark.parametrize('field,value',[('schema_version',True),('automatic_retry_allowed',True),('automatic_retry_allowed',0),('semantic_entailment_verified',True),('business_accepted',True),('provider_dispatched',False),('native_receipt_sha256',None),('settled_response_sha256','wrong'),('accepted_projection_event_id',None),('model_version',True),('model_content_hash','f'*64)])
def test_closed_effect_refuses_missing_forged_or_coerced_observations(packet,field,value):
 original=packet[0]
 with pytest.raises(ValueError):QuestionEffectPacketV1.model_validate_json(canonical_bytes(original|{field:value}))

@pytest.mark.parametrize('state',['unknown','unavailable','clarification'])
def test_unobserved_has_no_model_receipt_or_answer_and_never_authorizes_retry(packet,state):
 _,snapshot,now=packet;p=nonobserved_question_effect_v1(snapshot,state=state,checked_at=now,expires_at=now+timedelta(seconds=10),clarification='Which process?' if state=='clarification' else None)
 assert all(getattr(p,k) is None for k in OBSERVED_FIELDS) and p.automatic_retry_allowed is False
 assert p.provider_dispatched is (None if state=='unknown' else False)
 with pytest.raises(ValueError):QuestionEffectPacketV1.model_validate_json(canonical_bytes(p.model_dump(mode='json')|{'native_receipt_sha256':'a'*64}))
 if state=='clarification':
  with pytest.raises(PermissionError):validate_question_effect_scope_v1(p,snapshot|{'mode':'interview'})

def test_current_display_window_is_not_new_operation_or_financial_authority(packet):
 value,snapshot,now=packet
 for expiry in(now,now+timedelta(seconds=31)):
  with pytest.raises(ValueError):QuestionEffectPacketV1.model_validate_json(canonical_bytes(value|{'expires_at':expiry.isoformat()}))
 with pytest.raises(ValueError):QuestionEffectPacketV1.model_validate_json(canonical_bytes(value|{'operation_deadline':(now+timedelta(hours=1)).isoformat()}))


def test_public_synthesis_references_resolve_all_nonempty_facts_once_and_refuse_tampering(packet):
 from oracle_brain.operating_model.qualified_answer_v1 import QualifiedSynthesisAnswerV1
 from oracle_brain.operating_model.qualified_synthesis_v1 import synthesis_groups_v1,synthesis_gap_codes_v1,validate_qualified_synthesis_v1,synthesis_references_v1,validate_synthesis_references_v1
 value,_,_=packet
 body=QualifiedSynthesisAnswerV1.model_validate_json(canonical_bytes(value['answer']|{'selection':'qualified-retained-facts-synthesis-v1','provider_generation_used':True,'query_embedding_used':False}))
 assert body.records
 groups=[]
 for records in synthesis_groups_v1(body):
  classification='opposed' if any(r.evidence.opposing for r in records) else 'unknown' if any(r.applicability=='unknown' or r.evidence.unknown or not r.evidence.supporting for r in records) else 'reported'
  groups.append(dict(schema_version=1,classification=classification,assertion_ids=[str(r.assertion.assertion_id) for r in records]))
 parsed=validate_qualified_synthesis_v1(canonical_bytes(dict(schema_version=1,protocol='qualified-answer-synthesis-output-v1',factual_groups=groups,gap_codes=list(synthesis_gap_codes_v1(body)),unverified_interpretation=None)),body,interview=False)
 refs=synthesis_references_v1(parsed,body,interview=False)
 assert all(set(g)=={'classification','assertion_ids'} for g in refs['factual_groups'])
 assert validate_synthesis_references_v1(refs,body,interview=False)==parsed
 complete=value|dict(purpose='qualified-answer-synthesis-v1',answer=body.model_dump(mode='json'),synthesis=refs)
 assert QuestionEffectPacketV1.model_validate_json(canonical_bytes(complete)).answer.records
 variants=[]
 for kind in ('nested','foreign','missing','duplicate','classification','coverage','gaps'):
  bad=copy.deepcopy(refs)
  if kind=='nested':bad['factual_groups'][0]['records']=body.records[0].model_dump(mode='json')
  elif kind=='foreign':bad['factual_groups'][0]['assertion_ids'][0]=str(uuid4())
  elif kind=='missing':bad['factual_groups']=bad['factual_groups'][1:]
  elif kind=='duplicate':bad['factual_groups'][0]['assertion_ids'].append(bad['factual_groups'][0]['assertion_ids'][0])
  elif kind=='classification':bad['factual_groups'][0]['classification']='opposed' if bad['factual_groups'][0]['classification']!='opposed' else 'reported'
  elif kind=='coverage':bad['coverage']['entire_company_verified']=True
  else:bad['gap_codes']=[]
  variants.append(bad)
 for bad in variants:
  with pytest.raises(ValueError):QuestionEffectPacketV1.model_validate_json(canonical_bytes(complete|{'synthesis':bad}))
