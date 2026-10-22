"""Invented pure workspace packing; no runtime identity, source or serving grant."""
from datetime import timedelta
from types import SimpleNamespace
import copy
import pytest
from test_assembly_context import context
from test_connected_answer_contract_v1 import case
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.hosting.qualified_workspace_v1 import WorkspaceRequestV1,parse_workspace_request_v1,_workspace_view_v1
from oracle_brain.hosting.connected_answer_service_v1 import parse_answer_request_v1
from oracle_brain.operating_model.consolidation_contracts_v1 import ConsolidationCoreV1


@pytest.fixture
def workflow_case(case):
    # New invented pure body, never relabel an admitted runtime/capture result.
    core,payload,now,scope=case
    raw=core.model_dump(mode='json');process=raw['model']['processes'][0]
    support={'observation_ids':[process['observation_ids'][0]]}
    raw['model']['workflows']=[dict(schema_version=1,workflow_id='invented-map',version=1,
        workspace_id=str(core.model.workspace_id),process_id=process['process_id'],scope=process['scope'],
        source_refs=raw['model']['source_refs'],completeness='partial',coverage_digest='c'*64,
        steps=[dict(step_id='start',label='Begin',kind='start',support=support),
               dict(step_id='end',label='Finish',kind='end',support=support)],
        transitions=[dict(transition_id='next',from_id='start',to_id='end',condition_id='condition',rework=True,support=support)],
        conditions=[dict(condition_id='condition',wording='Only after review',applicability='unknown',support=support)],
        gateways=[],roles=[dict(assignment_id='owner',step_id='start',role_id='reviewer',support=support)],
        artifacts=[dict(artifact_id='report',label='Review report',support=support)],
        handoffs=[dict(handoff_id='handoff',from_step='start',to_step='end',artifact_id='report',support=support)],finding_ids=[])]
    process['workflow_ids']=['invented-map']
    model=ConsolidationCoreV1.model_validate_json(canonical_bytes(raw))
    return model,payload|{'consolidation_core':model.model_dump(mode='json'),'operating_models':[model.model.model_dump(mode='json')]},now,scope


def request(case,**changes):
    return WorkspaceRequestV1(operation='overview',protocol='qualified-workspace-question-v1',
        process_id=None,page=0,caller_deadline=case[2]+timedelta(seconds=10)).model_copy(update=changes)


def packet(case):
    core,payload,now,_=case
    return core,{'manifest':{'content_hash':digest(payload)}},payload,SimpleNamespace(checked_at=now+timedelta(seconds=1))


def test_complete_overview_retains_exact_accounts_quotes_and_coverage(case):
    result=_workspace_view_v1(packet(case),request(case))
    assert result['process_count']==result['returned_process_count']==len(case[0].model.processes)
    assert result['process_list_complete'] and not result['company_wide_completeness_verified']
    assert not result['company_policy_confirmed'] and not result['source_health_observed']
    assert not result['workflows'] and result['answer']['records']
    assert result['answer']['records'][0]['assertion']==case[0].assertions[0].model_dump(mode='json')
    assert all(p['evidence'] for p in result['processes'])


def test_selected_process_keeps_all_workflow_items_and_every_original_quote(workflow_case):
    case=workflow_case
    process=next(p for p in case[0].model.processes if p.workflow_ids)
    result=_workspace_view_v1(packet(case),request(case,operation='process',process_id=process.process_id))
    expected=[w for w in case[0].model.workflows if w.process_id==process.process_id]
    assert len(result['workflows'])==len(expected)>0
    for shown,workflow in zip(result['workflows'],expected):
        assert len(shown['items'])==sum(len(getattr(workflow,k)) for k in ('steps','gateways','transitions','conditions','roles','artifacts','handoffs'))
        assert all(item['evidence'] for item in shown['items'])
        assert shown['reported_status']==workflow.status


@pytest.mark.parametrize('changes',[{'actor_id':'spoof'},{'page':True},{'page':-1},{'page':2048},
    {'operation':'export-all'},{'operation':'process','process_id':None},{'process_id':'foreign'},
    {'operation':'process','process_id':'x\x00'},{'schema_version':True}])
def test_closed_wire_never_accepts_authority_or_coerced_bounds(case,changes):
    raw=request(case).model_dump(mode='json')|changes
    with pytest.raises((ValueError,PermissionError)):
        parse_workspace_request_v1(canonical_bytes(raw))


def test_same_actual_listener_parser_selects_the_closed_workspace_protocol(case):
    raw=canonical_bytes(request(case).model_dump(mode='json'))
    assert type(parse_answer_request_v1(raw)) is WorkspaceRequestV1
    with pytest.raises((ValueError,PermissionError)):
        parse_workspace_request_v1(raw+b' ')


def test_foreign_process_and_modified_retained_body_are_not_partial_success(case):
    with pytest.raises(PermissionError):_workspace_view_v1(packet(case),request(case,operation='process',process_id='foreign'))
    core,metadata,payload,delivery=packet(case)
    changed=copy.deepcopy(payload);changed['consolidation_core']['assertions'][0]['value']='changed'
    with pytest.raises(PermissionError):_workspace_view_v1((core,metadata,changed,delivery),request(case))


def test_process_map_does_not_silently_omit_a_missing_quote(workflow_case):
    case=workflow_case
    core,metadata,payload,delivery=packet(case)
    process=next(p for p in core.model.processes if p.workflow_ids)
    changed=copy.deepcopy(payload);changed['observations']=[]
    with pytest.raises((ValueError,PermissionError)):
        _workspace_view_v1((core,{'manifest':{'content_hash':digest(changed)}},changed,delivery),request(case,operation='process',process_id=process.process_id))
