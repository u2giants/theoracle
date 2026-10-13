"""Bounded untrusted CSV/XES input. Quarantine retains rows, never guessed events."""
from __future__ import annotations
import csv, hashlib, io, uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET
from pydantic import Field, model_validator
from ..contracts import StrictRecord, digest
from ..process_analysis.event_contracts import LogReceipt, PydanticEvent

MAX_BYTES=25*1024*1024
MAX_EVENTS=100000
MAX_COLUMNS=100
MAX_CELL=100000
# Interpretation changes get a distinct immutable import identity; old receipts
# are preserved rather than overwritten or replayed as current evidence.
PARSER_CONTRACT='operational-event-v2-explicit-completion'

class Mapping(StrictRecord):
    columns: dict[str,str]
    source_system: str = Field(min_length=1)
    process_id: str = Field(min_length=1)
    scope: str = Field(min_length=1)
    activity_map: dict[str,str]
    delimiter: Literal[',',';','\t'] = ','
    correlation: Literal['single_case','object_centric'] = 'single_case'
    timezone_name: str|None = None
    @model_validator(mode='after')
    def valid(self):
        required={'event_id','case_id','activity_id','timestamp'}
        if not required <= set(self.columns):raise ValueError('required mapping columns missing')
        if self.correlation!='single_case':raise ValueError('object-centric exports require qualified correlation')
        allowed=required|{'lifecycle','status','tie_order','resource','cost','process_id','scope'}
        if set(self.columns)-allowed or len(set(self.columns.values()))!=len(self.columns):raise ValueError('invalid mapping keys or overlapping columns')
        if not self.activity_map or any(not k or not v for k,v in self.activity_map.items()):raise ValueError('activity mappings must be explicit')
        if self.timezone_name:ZoneInfo(self.timezone_name)
        return self

def _dt(value:str, timezone_name:str|None):
    original=value
    d=datetime.fromisoformat(value[:-1]+'+00:00' if value.endswith('Z') else value)
    if d.tzinfo is None:
        if not timezone_name:raise ValueError('timestamp requires offset or mapped timezone')
        zone=ZoneInfo(timezone_name)
        candidates={d.replace(tzinfo=zone,fold=f).astimezone(timezone.utc) for f in (0,1)
                    if d.replace(tzinfo=zone,fold=f).astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)==d}
        if len(candidates)!=1:raise ValueError('ambiguous or nonexistent local timestamp')
        return next(iter(candidates)),original,timezone_name
    return d.astimezone(timezone.utc),original,str(d.tzinfo)

def _bounded(row):
    if len(row)>MAX_COLUMNS or any(not isinstance(v,str) or len(v)>MAX_CELL for v in row.values()):raise ValueError('column or cell limits exceeded')

def _rows(data,format,mapping):
    if len(data)>MAX_BYTES:raise ValueError('input exceeds byte limit')
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError as e:raise ValueError('export must be UTF-8') from e
    rows=[]
    if format=='csv':
        # csv's own bound also prevents an oversized cell allocation.
        reader=csv.DictReader(io.StringIO(text),delimiter=mapping.delimiter)
        fields=reader.fieldnames
        if not fields or len(fields)>MAX_COLUMNS or len(fields)!=len(set(fields)):raise ValueError('invalid or duplicate headers')
        if not set(mapping.columns.values())<=set(fields):raise ValueError('missing mapped columns')
        try:
            for row in reader:
                _bounded(row);rows.append(row)
                if len(rows)>MAX_EVENTS:raise ValueError('event limit exceeded')
        except csv.Error as e:raise ValueError('CSV cell limit or syntax failure') from e
    elif format=='xes':
        if '<!DOCTYPE' in text.upper() or '<!ENTITY' in text.upper():raise ValueError('external entities forbidden')
        case=None;inside_event=False
        try:
            for action,element in ET.iterparse(io.StringIO(text),events=('start','end')):
                tag=element.tag.rsplit('}',1)[-1]
                if action=='start':
                    if tag=='trace':case=None
                    elif tag=='event':inside_event=True
                    continue
                if tag=='string' and not inside_event and element.attrib.get('key')=='concept:name':case=element.attrib.get('value')
                if tag=='event':
                    row={}
                    for child in element:
                        key,value=child.attrib.get('key'),child.attrib.get('value')
                        if not key or value is None or key in row:raise ValueError('invalid or duplicate XES attribute')
                        row[key]=value
                    case_column=mapping.columns['case_id']
                    if case_column not in row and case is not None:row[case_column]=case
                    _bounded(row);rows.append(row)
                    if len(rows)>MAX_EVENTS:raise ValueError('event limit exceeded')
                    element.clear();inside_event=False
                elif tag=='trace':element.clear()
        except ET.ParseError as e:raise ValueError('invalid XES') from e
    else:raise ValueError('unsupported event format')
    return rows

def parse_export(data:bytes,format:Literal['csv','xes'],workspace_id:UUID,mapping:Mapping,window_start:datetime,window_end:datetime):
    if window_start.tzinfo is None or window_end.tzinfo is None or window_end<=window_start:raise ValueError('aware ordered window required')
    window_start,window_end=window_start.astimezone(timezone.utc),window_end.astimezone(timezone.utc)
    rows=_rows(data,format,mapping)
    input_hash=hashlib.sha256(data).hexdigest();mapping_hash=digest(mapping.model_dump(mode='json'))
    import_id=uuid.uuid5(workspace_id,PARSER_CONTRACT+':'+input_hash+mapping_hash+window_start.isoformat()+window_end.isoformat())
    ids=Counter(row.get(mapping.columns['event_id']) for row in rows)
    events=[];quarantine=[];censor={};notes=[]
    for index,row in enumerate(rows,1):
        def val(key,default=None):return row.get(mapping.columns[key],default) if key in mapping.columns else default
        case=val('case_id')
        try:
            if any(val(k) in (None,'') for k in ('event_id','case_id','activity_id','timestamp')):raise ValueError('blank required field')
            if ids[val('event_id')]>1:raise ValueError('duplicate event id')
            if val('activity_id') not in mapping.activity_map:raise ValueError('unmapped activity')
            if val('process_id',mapping.process_id)!=mapping.process_id or val('scope',mapping.scope)!=mapping.scope:raise ValueError('process or scope mismatch')
            dt,original,zone=_dt(val('timestamp'),mapping.timezone_name)
            if not window_start<=dt<=window_end:raise ValueError('outside event window')
            tie=val('tie_order');cost=val('cost')
            events.append(PydanticEvent(event_id=val('event_id'),row_index=index,case_id=case,
                activity_id=mapping.activity_map[val('activity_id')],timestamp=dt,original_timestamp=original,
                original_zone=zone,lifecycle=val('lifecycle','point'),status=val('status','unknown') or 'unknown',
                resource=val('resource') or None,cost=Decimal(cost) if cost not in (None,'') else None,
                tie_order=int(tie) if tie not in (None,'') else None,source_import_id=import_id))
            if events[-1].status=='unknown':
                censor.setdefault(case,'completion-evidence-unavailable')
        except (ValueError,TypeError) as error:
            quarantine.append({'row_index':index,'reason':str(error),'raw_fields':row})
            if case:censor[case]='quarantined-event-incomplete'
    ties=defaultdict(list)
    for event in events:ties[(event.case_id,event.timestamp)].append(event)
    for (case,_),group in ties.items():
        if len(group)>1 and (any(e.tie_order is None for e in group) or len({e.tie_order for e in group})!=len(group)):
            notes.append('unordered-timestamp-tie:'+case)
    receipt=LogReceipt(workspace_id=workspace_id,import_id=import_id,input_hash=input_hash,mapping_hash=mapping_hash,
        window_start=window_start,window_end=window_end,events=tuple(events),quarantined_rows=tuple(q['row_index'] for q in quarantine),
        quality_notes=tuple(sorted(set(notes))),case_censoring=censor)
    return receipt,tuple(quarantine)
