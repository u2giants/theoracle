from hashlib import sha256
from uuid import UUID
import pytest
from oracle_brain.operating_model.source_receipts import SourceRef
from oracle_brain.operating_model.observations import Observation
from oracle_brain.operating_model.workflows.process_model import *
from oracle_brain.operating_model.workflows.process_validate import formal_eligible, validate_workflow

W=UUID(int=1); S=UUID(int=2); REF=SourceRef(workspace_id=W,source_id=S,revision=1,original_sha256='a'*64,reading_sha256='b'*64,parser_id='p')
def sp(i='o'): return Support(observation_ids=(i,))
def model(**kw):
    base=dict(workflow_id='w',version=1,workspace_id=W,process_id='p',scope='s',source_refs=(REF,),completeness='complete',coverage_digest='c'*64,
      steps=(Step(step_id='start',label='Same',kind='start',support=sp()),Step(step_id='end',label='Same',kind='end',support=sp())),transitions=(Transition(transition_id='t',from_id='start',to_id='end',support=sp()),))
    base.update(kw); return WorkflowModel(**base)
def obs(): return {'o': Observation(observation_id='o',ref=REF,occurrence_key='x',kind='step',scope='s',value='v',evidence=())}
def test_repeated_labels_and_literal_parallel_gateway():
    m=model(steps=(Step(step_id='a',label='Same',kind='start',support=sp()),Step(step_id='b',label='Same',kind='end',support=sp())),transitions=(Transition(transition_id='t',from_id='a',to_id='b',support=sp()),),gateways=(Gateway(gateway_id='g',kind='parallel_split',support=sp()),))
    assert m.steps[0].label == m.steps[1].label and m.gateways[0].kind == 'parallel_split'
def test_rework_preserved_and_dangling_or_reused_ids_rejected():
    assert model(transitions=(Transition(transition_id='t',from_id='start',to_id='end',support=sp(),rework=True),)).transitions[0].rework
    with pytest.raises(ValueError): model(transitions=(Transition(transition_id='t',from_id='x',to_id='end',support=sp()),))
    with pytest.raises(ValueError): model(steps=(Step(step_id='start',label='a',kind='start',support=sp()),Step(step_id='start',label='b',kind='end',support=sp())))
def test_unknown_gateway_and_partial_model_denied():
    assert not formal_eligible(model(completeness='partial'))
    assert not formal_eligible(model(gateways=(Gateway(gateway_id='g',kind='unsupported',support=sp()),)))
def test_missing_support_rejected_and_explicit_start_end_required():
    with pytest.raises(ValueError): validate_workflow(model(), {})
    with pytest.raises(ValueError): model(steps=(Step(step_id='x',label='x',kind='activity',support=sp()),))
def test_complete_explicit_start_end_is_eligible():
    assert formal_eligible(model())
