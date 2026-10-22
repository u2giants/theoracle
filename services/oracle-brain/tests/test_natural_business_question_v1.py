"""Invented pure question tests; no reader, provider or runtime authority."""
from datetime import timedelta
from uuid import uuid4
import copy
import pytest
from test_assembly_context import context
from test_connected_answer_contract_v1 import case
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.consolidation_contracts_v1 import ConsolidationCoreV1
from oracle_brain.workflows.answer import AnswerQueryV1,_pack_answer_v1,_unicode_terms_v1
from oracle_brain.workflows.natural_answer_v1 import NaturalQuestionRequestV1,resolve_natural_question_v1

@pytest.fixture
def business(case):
 core,payload,now,scope=case;raw=core.model_dump(mode='json');observations={o['observation_id']:o for o in payload['observations']}
 records=[]
 for process in core.model.processes:
  observation=observations[process.observation_ids[0]]
  a=copy.deepcopy(raw['assertions'][0]);a.update(assertion_id=str(uuid4()),subject_id=str(uuid4()),predicate='reported_action',
   value=observation['value'],supporting_observations=[observation['observation_id']],temporal_observations=[observation['observation_id']])
  records.append(a)
 raw['assertions']=records;core=ConsolidationCoreV1.model_validate_json(canonical_bytes(raw))
 return core,payload|{'consolidation_core':core.model_dump(mode='json')},now,scope

def natural(case,question):
 core,payload,now,_=case;plan,clarification=resolve_natural_question_v1(question,core,observed_at=now+timedelta(seconds=1))
 if plan is None:return None,clarification
 return _pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},plan,observed_at=now+timedelta(seconds=1)),None

def test_natural_employee_question_then_unrelated_followup_resolves_independently(business):
 core=business[0];assert len(core.model.processes)==2
 first=core.model.processes[0];second=core.model.processes[1]
 answer,clarification=natural(business,f'Who performs the reported action in {first.label}?')
 assert clarification is None and answer.records and answer.coverage.represented_process_ids==(first.process_id,)
 followup,clarification=natural(business,f'What does {second.label} receive?')
 assert clarification is None and followup.records and followup.coverage.represented_process_ids==(second.process_id,)
 assert {a.assertion.assertion_id for a in followup.records}.isdisjoint(a.assertion.assertion_id for a in answer.records)
 assert followup.provider_generation_used is False and followup.query_embedding_used is False

def test_pronoun_only_followup_does_not_borrow_previous_scope_or_quote(business):
 assert natural(business,f'Who acts in {business[0].model.processes[0].label}?')[0].records
 answer,clarification=natural(business,'What happens to it next?')
 assert answer is None and clarification.count('?')==1

def test_ambiguous_natural_question_returns_one_clarification(business):
 answer,clarification=natural(business,'Who is responsible?')
 assert answer is None and clarification.count('?')==1

def test_connected_natural_question_uses_only_bounded_supported_relation(business):
 core=business[0];answer,clarification=natural(business,f'What handoff connects {core.model.processes[0].label} and {core.model.processes[1].label}?')
 assert clarification is None and answer.mode=='connected'
 assert set(answer.coverage.represented_process_ids)=={p.process_id for p in core.model.processes}

def test_global_natural_question_discloses_exact_model_population_not_company_totals(business):
 answer,clarification=natural(business,'What is reported across all processes?')
 assert clarification is None and answer.mode=='global'
 assert answer.coverage.declared_assertion_count==len(business[0].assertions)
 assert answer.coverage.entire_company_verified is False
 assert any('company-wide completeness is not verified' in c for c in answer.caveats)

def test_dates_need_two_exact_zoned_times_and_do_not_invent_history(business):
 answer,clarification=natural(business,'What previously happened in Design?')
 assert answer is None and clarification.count('?')==1
 core,payload,now,_=business
 question=f'What happened in {core.model.processes[0].label} at {now.isoformat()}, as known at {now.isoformat()}?'
 answer,clarification=natural(business,question)
 assert clarification is None and answer.mode=='historical' and answer.valid_at==answer.known_at==now

def test_same_subject_exception_group_is_never_split_at_topk_or_page_limit(business):
 core,payload,now,scope=business;raw=core.model_dump(mode='json')
 raw['assertions'][1]['subject_id']=raw['assertions'][0]['subject_id'];raw['assertions'][1]['predicate']=raw['assertions'][0]['predicate']
 raw['assertions'][0]['opposing_observations']=raw['assertions'][1]['supporting_observations']
 core=ConsolidationCoreV1.model_validate_json(canonical_bytes(raw));payload=payload|{'consolidation_core':core.model_dump(mode='json')}
 q=AnswerQueryV1(question=str(core.assertions[0].assertion_id),mode='global',scope=scope,max_records=1)
 result=_pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now)
 assert result.state=='coverage_incomplete' and not result.records and result.coverage.selected_assertion_count==2
 q=AnswerQueryV1(question=str(core.assertions[0].assertion_id),mode='global',scope=scope,max_records=2)
 result=_pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now)
 assert len(result.records)==2 and any(r.evidence.opposing for r in result.records)

def test_unicode_ranking_keeps_negation_without_changing_original(business):
 text='不允许未经复核就发货。仅限样品。'
 assert '不允' in _unicode_terms_v1(text) and '发货' in _unicode_terms_v1(text)
 assert 'not' in _unicode_terms_v1('Do not ship samples')
 core,payload,now,_=business
 question='中'*4096
 original=NaturalQuestionRequestV1(caller_deadline=now,question=question)
 assert original.question==question and len(original.question.encode())==12288
 with pytest.raises(ValueError):AnswerQueryV1(question=question)

@pytest.mark.parametrize('question',[' ','x\x00','中'*4097,'😀'*4097])
def test_natural_original_bounds_are_strict(question,business):
 with pytest.raises(ValueError):NaturalQuestionRequestV1(caller_deadline=business[2],question=question)

@pytest.mark.parametrize('question',['What happens for customer Acme?','Who handles product Blue?','What applies in region North?'])
def test_business_scope_names_are_never_guessed_from_UUID_metadata(question,business):
 answer,clarification=natural(business,question)
 assert answer is None and 'not yet established' in clarification

def test_natural_flat_wire_preserves_original_deadline_and_rejects_authority(business):
 from oracle_brain.hosting.connected_answer_service_v1 import parse_answer_request_v1
 raw=dict(schema_version=1,protocol='qualified-natural-question-v1',question=' 不发货。 ',caller_deadline='2026-10-21T20:00:00.123Z')
 parsed=parse_answer_request_v1(canonical_bytes(raw))
 assert parsed.question==raw['question'] and parsed.caller_deadline.microsecond==123000
 for patch in ({'actor_id':str(uuid4())},{'schema_version':True},{'protocol':'unknown'},{'question':'x\x00'}):
  with pytest.raises(ValueError):parse_answer_request_v1(canonical_bytes(raw|patch))
 with pytest.raises(ValueError):parse_answer_request_v1(canonical_bytes(raw)+b' ')
