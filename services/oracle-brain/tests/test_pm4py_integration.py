"""Explicit isolated analytical extra; no product qualification flags are enabled."""
from datetime import datetime,timedelta,timezone
from uuid import uuid4
from importlib.metadata import version
from scripts.oracle2.measure_pm4py import fixture
from oracle_brain.operating_model.process_analysis.runtime import _execute_bounded,_execute_operation,run_bounded
from oracle_brain.operating_model.process_analysis.event_contracts import LogReceipt,PydanticEvent


def execute(model,operation='structural',log=None):
    assert version('pm4py')=='2.7.22'
    return _execute_bounded(model.model_dump(mode='json'),_execute_operation,(model.model_dump_json(),operation,log.model_dump_json() if log else None),30)


def test_integrated_xor_and_rework_and_deadlock_keep_identity():
    for kind in ('xor','and','loop','deadlock'):
        model=fixture(kind);result=execute(model)
        assert result['state']=='analyzed',result
        assert result['structural_soundness']==(kind!='deadlock')
        assert set(result['step_map'])=={s.step_id for s in model.steps}
        assert set(result['transition_map'])=={t.transition_id for t in model.transitions}
        assert result['model']==model.model_dump(mode='json') and result['company_truth_accepted'] is False


def test_integrated_bounds_exhaustion_keeps_full_original_map():
    model=fixture('bounds');result=execute(model)
    assert result['state'] in {'analyzed','incomplete'}
    assert result['model']==model.model_dump(mode='json') and result['company_truth_accepted'] is False
    assert result['resource_bounds']=={'seconds':30,'memory_bytes':512*1024*1024}


def log_for(model):
    import_id=uuid4();start=datetime(2026,10,11,tzinfo=timezone.utc);events=[]
    for case,trace in (('z-fit',('start','x','end')),('a-deviation',('start','x','y','end'))):
        for i,activity in enumerate(trace):
            stamp=start+timedelta(seconds=i);events.append(PydanticEvent(event_id=f'{case}-{i}',row_index=len(events)+1,case_id=case,activity_id=activity,timestamp=stamp,original_timestamp=stamp.isoformat(),original_zone='UTC',lifecycle='point',status='completed',source_import_id=import_id))
    return LogReceipt(workspace_id=model.workspace_id,import_id=import_id,input_hash='a'*64,mapping_hash='b'*64,window_start=start,window_end=start+timedelta(days=1),events=tuple(events))


def test_integrated_discovery_and_conformance_are_observations_not_policy():
    model=fixture('xor');log=log_for(model)
    discovered=execute(model,'discovery',log);assert discovered['state']=='analyzed',discovered
    assert discovered['observed_is_documented_policy'] is False
    assert set(discovered['observed_model']['transitions'])=={'start','end','x','y'}
    compared=execute(model,'conformance',log);assert compared['state']=='analyzed',compared
    assert {case['case_id']:case['fits'] for case in compared['case_diagnostics']}=={'z-fit':True,'a-deviation':False}
    assert compared['deviations_are_policy_failures'] is False and compared['actual_data_acceptance']=='unavailable'
    assert compared['event_ids']==discovered['event_ids']


def test_installed_extra_cannot_enable_product_analytics():
    result=run_bounded(fixture('xor'),operation='structural',qualification=None)
    assert result['state']=='unavailable'
