"""Existing modules and callers retain the SAME canonical class/API objects."""
from oracle_brain.workflows import answer,natural_answer_v1,qualified_synthesis_v1
from oracle_brain.operating_model import qualified_answer_v1,natural_question_v1
from oracle_brain.operating_model import qualified_synthesis_v1 as core_synthesis,question_signals_v1
from oracle_brain.retrieval import planner

def test_existing_answer_module_and_pure_types_are_same_objects():
 assert answer is qualified_answer_v1 and answer.AnswerQueryV1 is qualified_answer_v1.AnswerQueryV1
 assert answer.DocumentaryAnswerV1 is qualified_answer_v1.DocumentaryAnswerV1
 assert answer._pack_answer_v1 is qualified_answer_v1._pack_answer_v1

def test_natural_and_synthesis_existing_modules_preserve_same_objects():
 assert natural_answer_v1 is natural_question_v1
 assert qualified_synthesis_v1 is core_synthesis

def test_legacy_fixture_retrieval_keeps_authority_local_and_only_shares_immutable_signals():
 assert planner._signals is question_signals_v1._signals
 assert planner._GLOBAL_MARKERS is question_signals_v1._GLOBAL_MARKERS
 assert planner._signals('What historically passed between all processes?')==(True,True,True,False)
 assert not hasattr(question_signals_v1,'AccessBounds') and not hasattr(question_signals_v1,'RetrievalPlan')
