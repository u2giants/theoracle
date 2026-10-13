import csv
from datetime import datetime,timedelta,timezone
import io
from uuid import UUID
import pytest
from oracle_brain.operating_model.ingest import minimized_observations as converter
from oracle_brain.operating_model.ingest.operational_export import Mapping,parse_export
from oracle_brain.operating_model.process_analysis.metrics import measured_metrics

def invented():
    events=[];references=[];start=datetime(2026,1,1,tzinfo=timezone.utc)
    for index in range(816):
        stamp=start+timedelta(milliseconds=index)
        known=index<531;capture=index+1;seal=converter.sha(f'invented-original-{index}'.encode())
        activity='Invented, "Unicode 雪"\nstatus' if index==0 else 'Invented review'
        event={'event_id':f'invented-webhook:history-{index}','case_id':f'invented-case-{index%360}',
            'activity':activity,'timestamp':stamp.isoformat(timespec='milliseconds').replace('+00:00','Z'),
            'timestamp_ms':str(int(stamp.timestamp()*1000)),
            'before_status':('' if index==0 else 'Invented, "prior"\n雪') if known else None,
            'before_state':'observed' if known else 'unobserved',
            'before_status_field':'value' if known else ('null' if index%2 else 'missing'),
            'after_status':activity,'actor_id':str(index+100),'process_id':converter.PROCESS,
            'original_capture_id':capture,'original_sha256':seal}
        events.append(event)
        references.append({'capture_id':capture,'received_at':'2026-01-01 00:00:00','sha256':seal})
    return events,references

def convert(events,references):
    raw=converter.canonical(events);refs=converter.canonical(references)
    return converter.prepare_csv(raw,refs,minimized_sha256=converter.sha(raw),reference_sha256=converter.sha(refs))

def test_full_invented_population_roundtrips_types_nulls_quotes_newlines_and_unicode():
    events,references=invented();raw,diagnostic=convert(events,references)
    assert converter.reconstruct_csv(raw)==(converter.canonical(events),converter.canonical(references))
    rows=list(csv.DictReader(io.StringIO(raw.decode(),newline='')))
    assert len(rows)==816 and rows[0]['activity']==events[0]['activity']
    assert all(row['lifecycle']=='point' and row['status']=='unknown' for row in rows)
    assert diagnostic['observed_predecessors']==531 and diagnostic['unobserved_predecessors']==285
    assert diagnostic['minimized_export_sha256']==converter.sha(converter.canonical(events))
    assert diagnostic['original_references_sha256']==converter.sha(converter.canonical(references))
    assert diagnostic['derived_csv_sha256']==converter.sha(raw)
    assert len(set((diagnostic['minimized_export_sha256'],diagnostic['original_references_sha256'],diagnostic['derived_csv_sha256'])))==3
    assert all(value is False for value in diagnostic['rights'].values())
    assert diagnostic['capture_authenticity']==diagnostic['documentary_mapping']=='unavailable'

def test_all_observations_retained_but_no_invented_completed_case_or_worktime():
    events,references=invented();raw,_=convert(events,references)
    # Explicit invented mapping only; it grants no real documentary mapping.
    mapping=Mapping(columns={'event_id':'event_id','case_id':'case_id','activity_id':'activity','timestamp':'timestamp','status':'status','lifecycle':'lifecycle'},
        source_system='invented',process_id=converter.PROCESS,scope='invented',
        activity_map={event['activity']:event['activity'] for event in events})
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    receipt,quarantine=parse_export(raw,'csv',UUID(int=1),mapping,start,start+timedelta(days=1))
    result=measured_metrics(receipt)
    assert not quarantine and len(receipt.events)==816
    assert result['cases']=={'total':360,'completed':0,'retained_completed':0,'excluded':0,'censored':360}
    assert sum(len(ids) for ids in result['event_ids'].values())==816
    assert result['elapsed_seconds']['values']==[] and result['worktime_seconds']=={}

@pytest.mark.parametrize('fault',['count','case_count','predecessor_count','extra','type','null_state','order','duplicate','capture_hash','timestamp_type','timestamp_drift','reference_extra'])
def test_changed_population_native_evidence_or_shape_is_denied(fault):
    events,references=invented()
    if fault=='count':events.pop()
    elif fault=='case_count':
        for event in events:
            if event['case_id']=='invented-case-359':event['case_id']='invented-case-0'
    elif fault=='predecessor_count':events[-1].update(before_state='observed',before_status='Invented',before_status_field='value')
    elif fault=='extra':events[0]['title']='Not a minimized field'
    elif fault=='type':events[0]['original_capture_id']=True
    elif fault=='null_state':events[-1]['before_status']='Invented predecessor'
    elif fault=='order':events[0],events[1]=events[1],events[0];references[0],references[1]=references[1],references[0]
    elif fault=='duplicate':events[1]['event_id']=events[0]['event_id']
    elif fault=='capture_hash':references[0]['sha256']='a'*64
    elif fault=='timestamp_type':events[0]['timestamp_ms']=int(events[0]['timestamp_ms'])
    elif fault=='timestamp_drift':events[0]['timestamp_ms']=str(int(events[0]['timestamp_ms'])+1)
    else:references[0]['extra']='Not an original reference'
    with pytest.raises(ValueError):convert(events,references)

def test_existing_hash_canonical_form_and_duplicate_json_fields_are_checked():
    events,references=invented();raw=converter.canonical(events);refs=converter.canonical(references)
    with pytest.raises(ValueError,match='hash mismatch'):
        converter.prepare_csv(raw,refs,minimized_sha256='a'*64,reference_sha256=converter.sha(refs))
    spaced=b' '+raw
    with pytest.raises(ValueError,match='canonical'):
        converter.prepare_csv(spaced,refs,minimized_sha256=converter.sha(spaced),reference_sha256=converter.sha(refs))
    duplicate=raw.replace(b'"case_id":',b'"case_id":"duplicate","case_id":',1)
    with pytest.raises(ValueError,match='duplicate JSON'):
        converter.prepare_csv(duplicate,refs,minimized_sha256=converter.sha(duplicate),reference_sha256=converter.sha(refs))

def test_reverse_conversion_refuses_added_completion_or_lost_columns():
    events,references=invented();raw,_=convert(events,references)
    rows=list(csv.DictReader(io.StringIO(raw.decode(),newline='')))
    rows[0]['status']='completed';out=io.StringIO(newline='')
    writer=csv.DictWriter(out,fieldnames=converter.COLUMNS,lineterminator='\n');writer.writeheader();writer.writerows(rows)
    with pytest.raises(ValueError,match='invent completion'):converter.reconstruct_csv(out.getvalue().encode())
    with pytest.raises(ValueError,match='columns'):converter.reconstruct_csv(raw.replace(b'before_status_field,',b'',1))
