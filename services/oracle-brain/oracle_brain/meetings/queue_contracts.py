"""Official closed task API: https://trigger.dev/docs/management/tasks/trigger .

Once enqueue observations in the existing capture owner; never task proof."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.hosting.original_intake_v1 import RequesterContextV1
from oracle_brain.meetings.participation_wire_v1 import observed_participation_wire_v1
from oracle_brain.hosting.gateway import unique_object
import hashlib,json,re
HASH=r'^[a-f0-9]{64}$'
TASK='oracle2-meeting-ingress-normalize-v1'
MAX_QUEUE_BODY_V1=4096
MAX_QUEUE_HEADERS_V1=16384
MAX_QUEUE_WIRE_V1=MAX_QUEUE_BODY_V1+MAX_QUEUE_HEADERS_V1
QUEUE_PIN_FIELDS_V1=('queue_project_ref','queue_environment_id','queue_account_id','queue_task_id','queue_credential_sha256','queue_installation_receipt_sha256','queue_target_descriptor_sha256')

def observe_queue_wire_v1(raw,*,error=None):
    if type(raw) is not bytes or len(raw)>MAX_QUEUE_WIRE_V1:raise ValueError('bounded private queue response wire required')
    # SAME existing complete framing owner, not another HTTP parser.
    facts=observed_participation_wire_v1(raw,error=error)
    result=dict(kind='UNKNOWN',complete=facts['complete'],run_id=None,body_sha256=None)
    if not facts['complete'] or facts['http_status']!=200:return result
    try:
        split=raw.index(b'\r\n\r\n');body=raw[split+4:]
        headers={k.lower():v.strip().lower() for k,v in (line.split(b':',1) for line in raw[:split].split(b'\r\n')[1:])}
        if headers.get(b'connection')!=b'close' or headers.get(b'content-type') not in (b'application/json',b'application/json; charset=utf-8') or split+4>MAX_QUEUE_HEADERS_V1 or len(body)>MAX_QUEUE_BODY_V1:return result
        value=json.loads(body.decode('utf-8'),object_pairs_hook=unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if type(value) is not dict or set(value)!={'id'} or type(value['id']) is not str or re.fullmatch(r'[A-Za-z0-9_-]{1,256}',value['id']) is None:return result
        result.update(kind='enqueue-observed',run_id=value['id'],body_sha256=hashlib.sha256(body).hexdigest());return result
    except (ValueError,TypeError,UnicodeError):return result

class MeetingEnqueueSQLV1(StrictRecord):
    context:RequesterContextV1
    meeting_id:UUID
    capture_until:AwareDatetime
    valid_until:AwareDatetime
    ingress_event_id:UUID|None
    claim_id:UUID|None
    state:Literal['idle','claimed','inflight','observed','UNKNOWN']
    fresh_claim:bool
    request_sha256:str|None=Field(pattern=HASH)
    body:dict|None
    queue_pins:dict
    original_effect_deadline:AwareDatetime|None
    original_processing_horizon:AwareDatetime
    run_id:str|None=Field(min_length=1,max_length=256)
    pending_count:int=Field(ge=0,le=4096)
    unresolved_count:int=Field(ge=0,le=4096)
    observation_only:Literal[True]
    remote_stop_proven:Literal[False]
    @field_validator('fresh_claim','observation_only','remote_stop_proven',mode='before')
    @classmethod
    def flags(cls,value):
        if type(value) is not bool:raise ValueError('literal queue observation flags required')
        return value
    @model_validator(mode='after')
    def once_body(self):
        if self.fresh_claim!=(self.state=='claimed') or self.fresh_claim!=(self.body is not None):raise ValueError('only fresh actual SQL claim returns executable body')
        if self.fresh_claim and any(x is None for x in (self.claim_id,self.ingress_event_id,self.request_sha256,self.original_effect_deadline)):raise ValueError('actual original once claim required')
        if set(self.queue_pins)!=set(QUEUE_PIN_FIELDS_V1) or self.queue_pins['queue_task_id']!=TASK:raise ValueError('closed installed queue commitment required')
        return self
