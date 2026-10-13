from datetime import datetime, timezone
from uuid import UUID
import pytest
from oracle_brain.operating_model.ingest.operational_export import Mapping, parse_export

W=UUID(int=1); START=datetime(2026,1,1,tzinfo=timezone.utc); END=datetime(2026,1,2,tzinfo=timezone.utc)
def mapping(**kw):
 d=dict(columns={'event_id':'id','case_id':'case','activity_id':'activity','timestamp':'time'},source_system='fixture',process_id='p',scope='s',activity_map={'A':'act-a'}); d.update(kw); return Mapping(**d)
def test_csv_exact_mapping_and_original_offset():
 r,q=parse_export(b'id,case,activity,time\n1,c1,A,2026-01-01T05:00:00-05:00\n', 'csv', W,mapping(),START,END); assert not q and r.events[0].timestamp==datetime(2026,1,1,10,tzinfo=timezone.utc) and r.events[0].original_zone=='UTC-05:00'
def test_exact_replay_import_id_and_unknown_quarantine():
 data=b'id,case,activity,time\n1,c1,A,2026-01-01T00:00:00Z\n2,c1,X,2026-01-01T00:00:00Z\n'; a,_=parse_export(data,'csv',W,mapping(),START,END); b,_=parse_export(data,'csv',W,mapping(),START,END); assert a.import_id==b.import_id and len(a.events)==1
def test_limits_missing_columns_duplicate_ids_and_invalid_time():
 with pytest.raises(ValueError): parse_export(b'id,id\n','csv',W,mapping(),START,END)
 r,q=parse_export(b'id,case,activity,time\n1,c,A,2026-01-01T00:00:00\n2,c,A,2026-01-01T00:00:00Z\n2,c,A,2026-01-01T00:00:00Z\n','csv',W,mapping(),START,END); assert len(q)==3
def test_object_centric_and_external_entity_rejected():
 with pytest.raises(ValueError): mapping(correlation='object_centric')
 with pytest.raises(ValueError): parse_export(b'<!DOCTYPE x [<!ENTITY e "x">]><log/>','xes',W,mapping(),START,END)
def test_no_sop_date_inference_and_supplied_mapping_labels_only():
 r,q=parse_export(b'id,case,activity,time\n1,c,A,2026-01-01T00:00:00Z\n','csv',W,mapping(),START,END); assert r.events[0].activity_id=='act-a'

def test_trace_case_inheritance_and_original_z_timestamp():
    mapping=Mapping(columns={'event_id':'id','case_id':'case','activity_id':'concept:name','timestamp':'time:timestamp'},source_system='erp',process_id='p',scope='s',activity_map={'Review':'r'})
    from datetime import datetime,timezone
    start=datetime(2026,1,1,tzinfo=timezone.utc);end=datetime(2026,2,1,tzinfo=timezone.utc)
    raw=b'<log><trace><string key="concept:name" value="C1"/><event><string key="id" value="E1"/><string key="concept:name" value="Review"/><date key="time:timestamp" value="2026-01-02T00:00:00Z"/></event></trace></log>'
    receipt,q=parse_export(raw,'xes',UUID(int=1),mapping,start,end)
    assert not q and receipt.events[0].case_id=='C1' and receipt.events[0].original_timestamp.endswith('Z')

@pytest.mark.parametrize('stamp',['2026-03-08T02:30:00','2026-11-01T01:30:00'])
def test_dst_gap_and_fold_quarantine_censors_case(stamp):
    mapping=Mapping(columns={'event_id':'id','case_id':'case','activity_id':'a','timestamp':'t'},source_system='erp',process_id='p',scope='s',activity_map={'Review':'r'},timezone_name='America/New_York')
    from datetime import datetime,timezone
    receipt,q=parse_export(f'id,case,a,t\nE,C,Review,{stamp}\n'.encode(),'csv',UUID(int=1),mapping,datetime(2026,1,1,tzinfo=timezone.utc),datetime(2027,1,1,tzinfo=timezone.utc))
    assert not receipt.events and len(q)==1 and 'C' in receipt.case_censoring

def test_duplicate_ids_quarantine_every_row_and_censor():
    from datetime import datetime,timezone
    mapping=Mapping(columns={'event_id':'id','case_id':'case','activity_id':'a','timestamp':'t'},source_system='erp',process_id='p',scope='s',activity_map={'Review':'r'})
    raw=b'id,case,a,t\nE,C,Review,2026-01-02T00:00:00Z\nE,C,Review,2026-01-02T00:01:00Z\n'
    r,q=parse_export(raw,'csv',UUID(int=1),mapping,datetime(2026,1,1,tzinfo=timezone.utc),datetime(2027,1,1,tzinfo=timezone.utc))
    assert not r.events and len(q)==2 and r.case_censoring

@pytest.mark.parametrize('format', ['csv', 'xes'])
def test_missing_terminal_evidence_retains_observation_without_completed_case(format):
    from oracle_brain.operating_model.process_analysis.metrics import measured_metrics
    if format=='csv':
        raw=b'id,case,activity,time\nE,C,A,2026-01-01T00:00:00Z\n'
    else:
        raw=b'<log><trace><string key="concept:name" value="C"/><event><string key="id" value="E"/><string key="activity" value="A"/><date key="time" value="2026-01-01T00:00:00Z"/></event></trace></log>'
    receipt,quarantine=parse_export(raw,format,W,mapping(),START,END)
    assert not quarantine and len(receipt.events)==1
    assert receipt.events[0].lifecycle=='point' and receipt.events[0].status=='unknown'
    assert receipt.case_censoring=={'C':'completion-evidence-unavailable'}
    metrics=measured_metrics(receipt)
    assert metrics['event_ids']=={'C':['E']} and metrics['cases']['completed']==0
    assert metrics['elapsed_seconds']['values']==[] and metrics['worktime_seconds']=={}

def test_explicit_completed_status_retains_existing_measurement_contract():
    from oracle_brain.operating_model.process_analysis.metrics import measured_metrics
    columns={**mapping().columns,'status':'status'}
    raw=b'id,case,activity,time,status\nE1,C,A,2026-01-01T00:00:00Z,completed\nE2,C,A,2026-01-01T00:00:05Z,completed\n'
    receipt,quarantine=parse_export(raw,'csv',W,mapping(columns=columns),START,END)
    assert not quarantine and not receipt.case_censoring
    metrics=measured_metrics(receipt)
    assert metrics['cases']['completed']==1 and metrics['elapsed_seconds']['values']==[5.0]
    assert metrics['worktime_seconds']=={'C':{}}

def test_blank_mapped_status_is_unknown_and_preserves_prior_fields():
    columns={**mapping().columns,'status':'status'}
    raw=b'id,case,activity,time,status,before_state,before_status\nE,C,A,2026-01-01T00:00:00Z,,unobserved,\n'
    receipt,quarantine=parse_export(raw,'csv',W,mapping(columns=columns),START,END)
    assert not quarantine and receipt.events[0].status=='unknown'
    assert receipt.input_hash==__import__('hashlib').sha256(raw).hexdigest()
    assert receipt.case_censoring=={'C':'completion-evidence-unavailable'}

def test_current_parser_import_is_idempotent_and_distinct_from_legacy_interpretation():
    from uuid import uuid5
    raw=b'id,case,activity,time\nE,C,A,2026-01-01T00:00:00Z\n'
    first,_=parse_export(raw,'csv',W,mapping(),START,END)
    again,_=parse_export(raw,'csv',W,mapping(),START,END)
    legacy=uuid5(W,first.input_hash+first.mapping_hash+START.isoformat()+END.isoformat())
    assert first==again and first.import_id!=legacy
