"""Invented pure packing only; this test never grants runtime/source authority."""
from datetime import timedelta
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.consolidation_contracts_v1 import AssertionScopeV1,ConsolidationCoreV1
from oracle_brain.operating_model.pipeline import assembly_candidate_payload,assembly_inputs
from oracle_brain.workflows.answer import AnswerQueryV1,_pack_answer_v1
from test_consolidation_contracts_v1 import core_fixture
from test_assembly_context import context

@pytest.fixture
def case(context):
 ctx,core,now=core_fixture(context)
 refs,observations,findings=assembly_inputs(tuple(e.payload for e in ctx.extractions))
 payload,_=assembly_candidate_payload(core.model_dump_json(),workspace_id=core.model.workspace_id,refs=refs,
     observations=observations,findings=findings,candidate_contract=core.contract)
 scope=AssertionScopeV1.model_validate_json(canonical_bytes({k:{'mode':'all','identities':[]} for k in ('process','customer','product','region')}))
 return core,payload,now,scope

def pack(case,**changes):
 core,payload,now,scope=case
 q=AnswerQueryV1(question='reported_step',mode='global',scope=scope,**changes)
 return _pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now+timedelta(seconds=1))

def test_exact_records_cite_every_support_and_never_claim_policy_or_generation(case):
 result=pack(case)
 assert result.records and result.records[0].evidence.supporting
 assert result.records[0].assertion==case[0].assertions[0]
 assert result.records[0].company_policy_confirmed is False
 assert result.provider_generation_used is False and result.query_embedding_used is False
 assert result.coverage.entire_company_verified is False

@pytest.mark.parametrize('change',[{'schema_version':True},{'max_bytes':True},{'max_records':0},{'page':-1},{'question':' '},{'question':'x\x00'},{'question':'中'*2000},{'process_ids':('same','same')},{'actor_id':str(uuid4())},{'source_refs':[]}])
def test_query_cannot_coerce_bounds_or_supply_authority(change):
 with pytest.raises(ValueError):AnswerQueryV1.model_validate_json(canonical_bytes(dict(question='question')|change))

def test_ambiguous_scope_asks_one_clarification_without_revealing_records(case):
 core,payload,now,_=case
 result=_pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},AnswerQueryV1(question='who?',mode='global'),observed_at=now)
 assert result.state=='clarification' and not result.records and result.answer_text.count('?')==1


def test_unrelated_followup_cannot_inherit_previous_records(case):
 core,payload,now,scope=case
 assert pack(case).records
 q=AnswerQueryV1(question='unrelated banana topic',mode='local',scope=scope,process_ids=(core.model.processes[0].process_id,))
 result=_pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now)
 assert result.state=='missing' and result.records==()


def test_unknown_time_is_visible_report_not_current_policy(case):
 core,payload,now,scope=case;raw=core.model_dump(mode='json');a=raw['assertions'][0]
 a.update(valid_time='unknown',valid_from=None,valid_to=None,temporal_observations=[])
 core=ConsolidationCoreV1.model_validate_json(canonical_bytes(raw));payload=payload|{'consolidation_core':core.model_dump(mode='json')}
 result=pack((core,payload,now,scope))
 assert result.state=='partial' and result.records[0].applicability=='unknown'
 assert 'applicability unknown' in result.answer_text and result.business_accepted is False


def test_chinese_negation_and_scope_are_never_paraphrased(case):
 core,payload,now,scope=case;raw=core.model_dump(mode='json')
 raw['assertions'][0]['value']='不允许未经复核就发货。仅限样品。'
 core=ConsolidationCoreV1.model_validate_json(canonical_bytes(raw));payload=payload|{'consolidation_core':core.model_dump(mode='json')}
 result=pack((core,payload,now,scope))
 assert result.records[0].assertion.value=='不允许未经复核就发货。仅限样品。'
 assert result.answer_text.endswith('不允许未经复核就发货。仅限样品。')


def test_changed_model_and_future_known_time_refuse(case):
 with pytest.raises(ValueError):pack(case,expected_version=case[0].model.version+1)
 core,payload,now,scope=case
 q=AnswerQueryV1(question='x',mode='historical',scope=scope,valid_at=now,known_at=now+timedelta(days=1))
 with pytest.raises(ValueError):_pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now)


def test_changed_private_body_identity_is_not_used(case):
 core,payload,now,scope=case
 with pytest.raises(PermissionError):_pack_answer_v1(core,payload,{'manifest':{'content_hash':'0'*64}},AnswerQueryV1(question='x',mode='global',scope=scope),observed_at=now)
