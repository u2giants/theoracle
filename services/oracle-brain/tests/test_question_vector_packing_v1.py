"""Pure exact/vector union packing; not current SQL/paid receipt authority."""
from uuid import uuid4
import copy
import pytest
from test_natural_business_question_v1 import business,case
from test_assembly_context import context
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.consolidation_contracts_v1 import ConsolidationCoreV1
from oracle_brain.operating_model.qualified_answer_v1 import AnswerQueryV1,_pack_answer_v1,_pack_vector_answer_v1,DocumentaryAnswerV1,QualifiedVectorAnswerV1

def pack(business,scores,*,records=32):
 core,payload,now,scope=business
 q=AnswerQueryV1(question='unmatchedlexeme',mode='local',scope=scope,process_ids=(core.model.processes[0].process_id,),max_records=records)
 return _pack_vector_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now,vector_scores=scores)

def test_vector_adds_real_qualified_candidates_and_old_mode_remains_exact_false(business):
 core,payload,now,scope=business
 scores={a.assertion_id:float(i+1)/len(core.assertions) for i,a in enumerate(core.assertions)}
 result=pack(business,scores)
 assert type(result) is QualifiedVectorAnswerV1 and result.records and result.query_embedding_used is True and result.provider_generation_used is False
 q=AnswerQueryV1(question='unmatchedlexeme',mode='local',scope=scope,process_ids=(core.model.processes[0].process_id,))
 old=_pack_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now)
 assert type(old) is DocumentaryAnswerV1 and old.state=='missing' and not old.records and old.query_embedding_used is False
 assert any('not semantic entailment' in text for text in result.caveats)

@pytest.mark.parametrize('damage',['missing','foreign','nan','bool','infinity','above-cosine'])
def test_vector_requires_complete_exact_finite_census(business,damage):
 scores={a.assertion_id:.2 for a in business[0].assertions};key=next(iter(scores))
 if damage=='missing':scores.pop(key)
 elif damage=='foreign':scores[uuid4()]=scores.pop(key)
 else:scores[key]={'nan':float('nan'),'bool':True,'infinity':float('inf'),'above-cosine':2.}[damage]
 with pytest.raises(ValueError):pack(business,scores)

def test_vector_selected_opposition_group_is_not_cut_by_page_bound(business):
 core,payload,now,scope=business;raw=core.model_dump(mode='json');left,right=raw['assertions']
 right['subject_id']=left['subject_id'];right['predicate']=left['predicate'];left['opposing_observations']=right['supporting_observations']
 core=ConsolidationCoreV1.model_validate_json(canonical_bytes(raw));payload=payload|{'consolidation_core':core.model_dump(mode='json')}
 q=AnswerQueryV1(question='unmatchedlexeme',mode='global',scope=scope,max_records=1)
 result=_pack_vector_answer_v1(core,payload,{'manifest':{'content_hash':digest(payload)}},q,observed_at=now,vector_scores={core.assertions[0].assertion_id:.9,core.assertions[1].assertion_id:-.9})
 assert result.state=='coverage_incomplete' and result.coverage.selected_assertion_count==2 and not result.records
