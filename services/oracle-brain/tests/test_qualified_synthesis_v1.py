"""Invented syntax/reference proof only; never semantic entailment or acceptance."""
from datetime import timedelta
import json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.workflows.answer import AnswerQueryV1,_pack_answer_v1
from oracle_brain.workflows.qualified_synthesis_v1 import validate_qualified_synthesis_v1,render_qualified_synthesis_v1,synthesis_groups_v1,synthesis_gap_codes_v1
from test_connected_answer_contract_v1 import case
from test_assembly_context import context

def packet(case):
 core,payload,now,scope=case
 answer=_pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},AnswerQueryV1(question='reported_step',mode='global',scope=scope),observed_at=now+timedelta(seconds=1))
 groups=[dict(schema_version=1,assertion_ids=[str(r.assertion.assertion_id) for r in group],classification='opposed' if any(r.evidence.opposing for r in group) else 'unknown' if any(r.applicability=='unknown' or r.evidence.unknown or not r.evidence.supporting for r in group) else 'reported') for group in synthesis_groups_v1(answer)]
 body=dict(schema_version=1,protocol='qualified-answer-synthesis-output-v1',factual_groups=groups,gap_codes=list(synthesis_gap_codes_v1(answer)),unverified_interpretation=None)
 return answer,body

def test_structured_model_output_only_orders_exact_facts_and_citations(case):
 answer,body=packet(case)
 # Real JSON mode may format whitespace; original wire custody stays raw.
 parsed=validate_qualified_synthesis_v1(json.dumps(body,indent=2).encode(),answer,interview=False)
 rendered=render_qualified_synthesis_v1(parsed,answer,interview=False)
 assert rendered['factual_groups'][0]['records'][0]==answer.records[0].model_dump(mode='json')
 assert rendered['semantic_entailment_verified'] is False and rendered['business_accepted'] is False

@pytest.mark.parametrize('attack',['omitted-group','foreign-reference','duplicate-reference','misclassified','missing-gap','new-fact','coerced-version','duplicate-key','nonfinite'])
def test_model_cannot_invent_or_drop_facts_exceptions_or_scope_gaps(case,attack):
 answer,body=packet(case)
 if attack=='omitted-group':body['factual_groups']=[]
 elif attack=='foreign-reference':body['factual_groups'][0]['assertion_ids']=['11111111-1111-4111-8111-111111111111']
 elif attack=='duplicate-reference':body['factual_groups'][0]['assertion_ids']*=2
 elif attack=='misclassified':body['factual_groups'][0]['classification']='reported' if body['factual_groups'][0]['classification']!='reported' else 'unknown'
 elif attack=='missing-gap':body['gap_codes']=[]
 elif attack=='new-fact':body['factual_groups'][0]['fact']='Invented company policy'
 elif attack=='coerced-version':body['factual_groups'][0]['schema_version']=True
 raw=canonical_bytes(body)
 if attack=='duplicate-key':raw=b'{"schema_version":1,'+raw[1:]
 if attack=='nonfinite':raw=raw.replace(b'null',b'NaN')
 with pytest.raises((ValueError,PermissionError)):validate_qualified_synthesis_v1(raw,answer,interview=False)

def test_optional_interpretation_is_explicitly_unverified_and_never_extra_interview_question(case):
 answer,body=packet(case);body['unverified_interpretation']='A possible interpretation, pending review.'
 parsed=validate_qualified_synthesis_v1(canonical_bytes(body),answer,interview=False)
 assert render_qualified_synthesis_v1(parsed,answer,interview=False)['interpretation']['classification']=='inference/unverified interpretation'
 with pytest.raises(PermissionError):validate_qualified_synthesis_v1(canonical_bytes(body),answer,interview=True)
