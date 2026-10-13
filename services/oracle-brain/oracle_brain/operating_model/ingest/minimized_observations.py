"""Pure lossless observation conversion preparation. No access or intake authority.

Inputs are the existing canonical minimized export and original-reference bytes,
never original bodies. Production/private use requires distinct exact admission.
This module opens no files, contacts no services and issues no SourceRef/receipt.
"""
import csv
from datetime import datetime,timezone
import hashlib
import io
import json
import re

FIELDS=('event_id','case_id','activity','timestamp','timestamp_ms','before_status',
        'before_state','before_status_field','after_status','actor_id','process_id',
        'original_capture_id','original_sha256')
REFERENCE_FIELDS={'capture_id','received_at','sha256'}
COLUMNS=FIELDS+('lifecycle','status','received_at')
PROCESS='clickup-workspace-2298436-task-status-observation'
ROWS=816
CASES=360
OBSERVED=531
UNOBSERVED=285
MAX_BYTES=4*1024*1024

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')

def sha(value):return hashlib.sha256(value).hexdigest()

def _pairs(items):
    value={}
    for key,item in items:
        if key in value:raise ValueError('duplicate JSON field')
        value[key]=item
    return value

def _load(raw,expected_hash):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
        raise ValueError('bounded exact export bytes required')
    if not isinstance(expected_hash,str) or not re.fullmatch('[0-9a-f]{64}',expected_hash) or sha(raw)!=expected_hash:
        raise ValueError('existing export hash mismatch')
    value=json.loads(raw.decode('utf-8'),object_pairs_hook=_pairs)
    if not isinstance(value,list) or canonical(value)!=raw:
        raise ValueError('existing canonical export required')
    return value

def _validate(events,references):
    if len(events)!=ROWS or len(references)!=ROWS:
        raise ValueError('exact observation population required')
    ids=set();cases=set();previous=-1;observed=0;unobserved=0
    for event,reference in zip(events,references):
        if not isinstance(event,dict) or set(event)!=set(FIELDS):
            raise ValueError('exact thirteen minimized fields required')
        if not isinstance(reference,dict) or set(reference)!=REFERENCE_FIELDS:
            raise ValueError('exact external original-reference fields required')
        capture=event['original_capture_id']
        if type(capture) is not int or capture<=previous or type(reference['capture_id']) is not int or reference['capture_id']!=capture:
            raise ValueError('original capture order or identity changed')
        previous=capture
        for key in FIELDS:
            if key in {'original_capture_id','before_status'}:continue
            if type(event[key]) is not str or len(event[key])>100000:
                raise ValueError('native scalar type or bound changed')
        if (not event['event_id'] or ':' not in event['event_id'] or event['event_id'] in ids
                or not event['case_id'] or not event['actor_id'].isdigit()):
            raise ValueError('native event/case/actor identity changed')
        if event['process_id']!=PROCESS or event['activity']!=event['after_status']:
            raise ValueError('observation scope or activity changed')
        if not re.fullmatch('[0-9a-f]{64}',event['original_sha256']) or reference['sha256']!=event['original_sha256']:
            raise ValueError('original capture hash association changed')
        if type(reference['received_at']) is not str or not reference['received_at'] or len(reference['received_at'])>100:
            raise ValueError('external original receipt time unavailable')
        millis=event['timestamp_ms']
        if not re.fullmatch('[0-9]{13}',millis):raise ValueError('native millisecond timestamp changed')
        native=datetime.fromtimestamp(int(millis)/1000,timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
        if event['timestamp']!=native:raise ValueError('native timestamp association changed')
        if event['before_state']=='observed':
            if type(event['before_status']) is not str or len(event['before_status'])>100000 or event['before_status_field']!='value':
                raise ValueError('observed predecessor changed')
            observed+=1
        elif event['before_state']=='unobserved':
            if event['before_status'] is not None or event['before_status_field'] not in {'missing','null'}:
                raise ValueError('unknown predecessor changed')
            unobserved+=1
        else:raise ValueError('predecessor evidence state changed')
        ids.add(event['event_id']);cases.add(event['case_id'])
    if len(cases)!=CASES or observed!=OBSERVED or unobserved!=UNOBSERVED:
        raise ValueError('case or predecessor population changed')

def prepare_csv(minimized_bytes,reference_bytes,*,minimized_sha256,reference_sha256):
    """Conversion only; hashes are custody inputs, never authentication/admission."""
    if not isinstance(minimized_bytes,bytes) or not isinstance(reference_bytes,bytes):
        raise ValueError('exact export bytes required')
    if len(minimized_bytes)+len(reference_bytes)>MAX_BYTES:
        raise ValueError('aggregate export bound exceeded')
    events=_load(minimized_bytes,minimized_sha256)
    references=_load(reference_bytes,reference_sha256)
    _validate(events,references)
    output=io.StringIO(newline='')
    writer=csv.DictWriter(output,fieldnames=COLUMNS,lineterminator='\n')
    writer.writeheader()
    for event,reference in zip(events,references):
        writer.writerow({**event,'lifecycle':'point','status':'unknown','received_at':reference['received_at']})
    data=output.getvalue().encode('utf-8')
    if len(data)>MAX_BYTES:raise ValueError('derived CSV bound exceeded')
    if reconstruct_csv(data)!=(minimized_bytes,reference_bytes):
        raise ValueError('lossless native roundtrip failed')
    diagnostic={'schema_version':1,'scope':PROCESS,'row_count':ROWS,'case_count':CASES,
        'observed_predecessors':OBSERVED,'unobserved_predecessors':UNOBSERVED,
        'minimized_export_sha256':minimized_sha256,'original_references_sha256':reference_sha256,
        'derived_csv_sha256':sha(data),'capture_authenticity':'unavailable',
        'documentary_mapping':'unavailable','rights':{'ledger_intake':False,
        'analytical_acceptance':False,'company_generation':False,'grading':False}}
    return data,diagnostic

def reconstruct_csv(raw):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
        raise ValueError('bounded derived CSV required')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8'),newline=''))
    if reader.fieldnames!=list(COLUMNS):raise ValueError('exact derived CSV columns required')
    events=[];references=[]
    for row in reader:
        if len(events)>=ROWS or None in row or any(value is None for value in row.values()):
            raise ValueError('derived observation population changed')
        if row['lifecycle']!='point' or row['status']!='unknown':
            raise ValueError('derived CSV cannot invent completion')
        capture_text=row['original_capture_id']
        if not re.fullmatch('[0-9]+',capture_text):raise ValueError('capture scalar changed')
        capture=int(capture_text)
        if str(capture)!=capture_text:raise ValueError('capture scalar changed')
        event={key:row[key] for key in FIELDS}
        event['original_capture_id']=capture
        if event['before_state']=='unobserved':
            if row['before_status']!='':raise ValueError('unknown predecessor cannot gain text')
            event['before_status']=None
        events.append(event)
        references.append({'capture_id':capture,'received_at':row['received_at'],'sha256':row['original_sha256']})
    _validate(events,references)
    return canonical(events),canonical(references)
