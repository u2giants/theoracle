"""Named invented workflow variant, captured before qualification; no provider proof."""
import copy
import pytest
from oracle_brain.operating_model.contracts import digest,canonical_bytes
from oracle_brain.operating_model.model import BusinessOperatingModel,BusinessRecord
from oracle_brain.operating_model.workflows.process_model import (WorkflowModel,Step,Gateway,Condition,Transition,RoleAssignment,Artifact,Handoff,Support)

VARIANT='workspace-artwork-rework-v1'
SCOPE='Invented ART review only; Supplier internals and company-wide coverage unrecorded'
QUOTE=('Start artwork review, then Design performs Prepare ART. Design hands ART from Prepare ART to Supplier at Review ART. '
       'After Review ART an exclusive decision checks ART approved or ART needs changes. '
       'If ART approved, Release ART ends this review. If ART needs changes, Design performs Revise ART and rework returns to Review ART. '
       'This complete reported workflow covers only this invented ART review, not Supplier internals or company-wide activity.')


def workflow_inputs_v1():
    from test_business_operating_model import observation
    values=(observation(4,QUOTE,scope=SCOPE),observation(5,'Supplier receives packet; its internal workflow is not recorded.',scope=SCOPE))
    return values,tuple({'source_refs':[o.ref.model_dump(mode='json')],'observations':[o.model_dump(mode='json')],'findings':[]}for o in values)


def workflow_model_v1(observations):
    from test_business_operating_model import model
    base=model(observations);a=observations[0];support=Support(observation_ids=(a.observation_id,))
    workflow=WorkflowModel(workflow_id='art-review',version=1,workspace_id=base.workspace_id,process_id='p1',scope=a.scope,source_refs=(a.ref,),status='reported',completeness='complete',
        steps=tuple(Step(step_id=i,label=label,kind=kind,role_id=role,support=support)for i,label,kind,role in (
            ('art-start','Start artwork review','start',None),('art-prepare','Prepare ART','activity','design-role'),('art-review-step','Review ART','activity','supplier-role'),('art-revise','Revise ART','activity','design-role'),('art-release','Release ART','end',None))),
        gateways=(Gateway(gateway_id='art-decision',kind='exclusive_split',support=support),),
        conditions=(Condition(condition_id='art-approved',wording='ART approved',applicability='known',support=support),Condition(condition_id='art-needs-changes',wording='ART needs changes',applicability='known',support=support)),
        transitions=tuple(Transition(transition_id=i,from_id=start,to_id=end,condition_id=condition,rework=rework,support=support)for i,start,end,condition,rework in (
            ('art-t1','art-start','art-prepare',None,False),('art-t2','art-prepare','art-review-step',None,False),('art-t3','art-review-step','art-decision',None,False),('art-t4','art-decision','art-release','art-approved',False),('art-t5','art-decision','art-revise','art-needs-changes',False),('art-t6','art-revise','art-review-step',None,True))),
        roles=(RoleAssignment(assignment_id='art-design-prepare',step_id='art-prepare',role_id='design-role',support=support),RoleAssignment(assignment_id='art-supplier-review',step_id='art-review-step',role_id='supplier-role',support=support),RoleAssignment(assignment_id='art-design-revise',step_id='art-revise',role_id='design-role',support=support)),
        artifacts=(Artifact(artifact_id='art-workflow-packet',label='ART',support=support),),
        handoffs=(Handoff(handoff_id='art-design-to-supplier',from_step='art-prepare',to_step='art-review-step',artifact_id='art-workflow-packet',support=support),),
        coverage_digest=digest({'fixture':VARIANT,'scope':a.scope,'support':support.model_dump(mode='json')}))
    raw=base.model_dump(mode='json');raw.update(declared_population='Two invented processes; one explicit ART review workflow; Supplier internal workflow unrecorded',workflows=[workflow.model_dump(mode='json')])
    raw['processes'][0].update(workflow_ids=['art-review'],completeness='complete')
    raw['objects'] += [BusinessRecord(object_id=i,kind='role',label=label,scope=a.scope,support=support).model_dump(mode='json')for i,label in (('design-role','Design'),('supplier-role','Supplier'))]
    return BusinessOperatingModel.model_validate_json(canonical_bytes(raw))


@pytest.fixture
def sql_qualified_workspace_workflow_v3(monkeypatch):
    """Named120/115 variant selected BEFORE context/census/raw capture/seals."""
    import test_assembly_context as foundation
    from test_consolidation_sql_v1 import original_sql_qualified_fixture_v3
    monkeypatch.setattr(foundation,'invented_inputs',workflow_inputs_v1)
    monkeypatch.setattr(foundation,'model',workflow_model_v1)
    return original_sql_qualified_fixture_v3(monkeypatch,lifetime_seconds=120)


def test_named_workflow_passes_real_canonical_capture_qualification(sql_qualified_workspace_workflow_v3):
    from test_consolidation_contracts_v1 import temporal_qualified_fixture
    from test_purpose_qualification_v3 import serving
    from oracle_brain.operating_model.purpose_qualification_v3 import verify_purpose_final_assembly_v3
    from oracle_brain.operating_model.assembly import validate_assembly
    from oracle_brain.operating_model.workflows.process_validate import formal_eligible
    from oracle_brain.operating_model.workflows.process_model import canonical_workflow_items
    q=temporal_qualified_fixture(sql_qualified_workspace_workflow_v3)
    assert verify_purpose_final_assembly_v3(**serving(q)) is None
    model=BusinessOperatingModel.model_validate_json(canonical_bytes(q['payload']['consolidation_core']['model']));ctx=q['wire']['context']
    from oracle_brain.operating_model.observations import Observation
    observations={v['observation_id']:Observation.model_validate_json(canonical_bytes(v))for x in ctx.extractions for v in x.payload['observations']}
    assert validate_assembly(model,observations)==model
    workflow,=model.workflows;assert formal_eligible(workflow)
    assert len(workflow.steps)==5 and len(workflow.transitions)==6 and len(workflow.handoffs)==1
    assert model.completeness=='partial' and model.processes[1].completeness=='partial'
    for _,_,item in canonical_workflow_items(workflow):
        assert item.support.observation_ids and all(observations[oid].evidence[0].quote==QUOTE for oid in item.support.observation_ids)
    assert all(step.label in QUOTE for step in workflow.steps)
    assert all(c.wording in QUOTE for c in workflow.conditions)
    assert workflow.transitions[-1].rework and workflow.transitions[-1].to_id=='art-review-step'
    assert 'ART review' in model.declared_population and 'company-wide' in workflow.scope


@pytest.mark.parametrize('damage',('quote','branch','rework','completeness'))
def test_captured_workflow_cannot_be_retrofitted(sql_qualified_workspace_workflow_v3,damage):
    from test_consolidation_contracts_v1 import temporal_qualified_fixture
    from test_purpose_qualification_v3 import serving
    from oracle_brain.operating_model.purpose_qualification_v3 import verify_purpose_final_assembly_v3
    q=serving(temporal_qualified_fixture(sql_qualified_workspace_workflow_v3));q['payload']=copy.deepcopy(q['payload'])
    workflow=q['payload']['consolidation_core']['model']['workflows'][0]
    if damage=='quote':workflow['steps'][0]['support']['observation_ids']=['invented-unsupported']
    elif damage=='branch':workflow['transitions'][3]['condition_id']='art-needs-changes'
    elif damage=='rework':workflow['transitions'][-1]['rework']=False
    else:workflow['completeness']='partial'
    with pytest.raises((ValueError,PermissionError)):verify_purpose_final_assembly_v3(**q)


def test_retained_default_remains_two_partial_processes_without_workflows():
    from test_assembly_context import original_context_v1
    context,model,now=original_context_v1(lifetime_seconds=30)
    assert model.workflows==() and all(p.completeness=='partial'for p in model.processes)
    assert (context.expires_at-now).total_seconds()==30
