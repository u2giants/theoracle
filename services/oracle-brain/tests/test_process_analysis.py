from datetime import datetime, timedelta, timezone
from uuid import uuid4
from decimal import Decimal
import pytest
from oracle_brain.operating_model.process_analysis import PydanticEvent, LogReceipt, measured_metrics

W=datetime(2026,1,1,tzinfo=timezone.utc); IMP=uuid4()
def ev(case, n, sec, activity='A', lifecycle='complete', status='completed', tie_order=None, cost=None):
    t=W+timedelta(seconds=sec)
    return PydanticEvent(event_id=f'e{n}',row_index=n,case_id=case,activity_id=activity,timestamp=t,original_timestamp=t.isoformat(),original_zone='UTC',lifecycle=lifecycle,tie_order=tie_order,status=status,resource=None,cost=cost,source_import_id=IMP)
def log(events, censor=None):
    return LogReceipt(workspace_id=uuid4(),import_id=IMP,input_hash='a'*64,mapping_hash='b'*64,window_start=W,window_end=W+timedelta(hours=1),events=tuple(events),case_censoring=censor or {})

def test_elapsed_median_p90_and_provenance():
    r=measured_metrics(log([ev('c1',1,0),ev('c1',2,10),ev('c2',3,0),ev('c2',4,20),ev('c3',5,0),ev('c3',6,40)]))
    assert r['elapsed_seconds']['median']=='20.0' and r['elapsed_seconds']['p90_nearest_rank']=='40.0'
    assert r['cases']['retained_completed']==3 and len(r['event_ids']['c1'])==2

def test_repeats_count_complete_and_point_only():
    r=measured_metrics(log([ev('c',1,0),ev('c',2,1),ev('c',3,2,activity='B',lifecycle='point')]))
    assert r['repeat_counts']['c']['A']==1

def test_point_only_has_no_lifecycle_worktime():
    assert measured_metrics(log([ev('c',1,0,lifecycle='point')]))['worktime_seconds']['c']=={}

def test_equal_time_without_tie_order_is_unordered():
    assert measured_metrics(log([ev('c',1,0,tie_order=None),ev('c',2,0,activity='B',tie_order=None)]))['variants']['c']=='unordered'

def test_censored_is_shown_and_explicit_exclusion_changes_denominator():
    r=measured_metrics(log([ev('done',1,0),ev('open',2,0,status='ongoing')], {'open':'window ended'}), frozenset({'done'}))
    assert r['cases']=={'total':2,'completed':1,'retained_completed':0,'excluded':1,'censored':1}

def test_strict_receipt_rejects_duplicate_ids_and_out_of_window():
    with pytest.raises(ValueError, match='duplicate'): log([ev('c',1,0),ev('c',1,1)])
    with pytest.raises(ValueError, match='outside'): log([ev('c',1,3601)])

def test_unique_lifecycle_pair_has_duration():
    r=measured_metrics(log([ev('c',1,0,lifecycle='start'),ev('c',2,5,lifecycle='complete')]))
    assert r['worktime_seconds']['c']['A']==5.0

def test_unknown_terminal_status_cannot_be_counted_as_completed_without_censor_flag():
    receipt=log([ev('unknown',1,0,status='unknown'),ev('unknown',2,5),ev('done',3,0)])
    restored=LogReceipt.model_validate_json(receipt.model_dump_json())
    result=measured_metrics(restored)
    assert result['cases']=={'total':2,'completed':1,'retained_completed':1,'excluded':0,'censored':1}
    assert result['event_ids']['unknown']==['e1','e2']
    assert 'unknown' not in result['worktime_seconds'] and 'unknown' not in result['observed_activity_paths']
