"""Closed service worker wire. Descriptive bytes never issue an admission.

The fixed startup owner chooses the actual factory and installed peer purpose;
HTTP input cannot choose an actor, role, account, profile, URL or provider body.
"""
import base64,binascii,hashlib
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord
HASH=r'^[a-f0-9]{64}$'
MAX_RESPONSE_WIRE=1064960
MAX_REQUEST_BYTES=2097152
WorkerPurpose=Literal['capture-create','capture-leave','capture-retrieve','participation-send']
class _WorkerRecord(StrictRecord):
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact worker wire version required')
        return value

class MeetingWorkerRequestV1(_WorkerRecord):
    operation:Literal['prepare','claim','current','observe','status']
    operation_id:UUID|None
    claim_event_id:UUID|None
    wire_base64:str|None=Field(max_length=1419948)
    error:Literal['transport_uncertain','invalid_response','expired','cancelled','local_failure']|None
    caller_deadline:AwareDatetime
    @model_validator(mode='after')
    def closed_operation(self):
        if self.operation in ('claim','current','observe') and self.operation_id is None:raise ValueError('actual prepared identity required')
        if self.operation in ('prepare','claim') and self.claim_event_id is not None:raise ValueError('claim identity is server-derived')
        if self.operation=='prepare' and self.operation_id is not None:raise ValueError('latest operation is server-derived')
        if self.operation in ('current','observe') and self.claim_event_id is None:raise ValueError('exact actual claim identity required')
        if self.operation!='observe':
            if self.wire_base64 is not None or self.error is not None:raise ValueError('wire only belongs to actual observation')
        else:self.observed_wire()
        return self
    def observed_wire(self):
        if self.operation!='observe' or type(self.wire_base64) is not str:raise ValueError('exact observed wire required')
        try:raw=base64.b64decode(self.wire_base64,validate=True)
        except (ValueError,binascii.Error):raise ValueError('canonical observed wire required') from None
        if len(raw)>MAX_RESPONSE_WIRE or base64.b64encode(raw).decode()!=self.wire_base64:raise ValueError('bounded canonical observed wire required')
        return raw

class MeetingWorkerPacketV1(_WorkerRecord):
    state:Literal['prepared','claimed','inflight','observed','UNKNOWN','DENIED','idle','terminal_observed']
    effect_purpose:WorkerPurpose
    principal_id:UUID
    worker_id:UUID
    workspace_id:UUID
    meeting_id:UUID
    provider_account:str=Field(min_length=1,max_length=256)
    operation_id:UUID|None
    claim_event_id:UUID|None
    request_sha256:str|None=Field(pattern=HASH)
    bot_id:UUID|None
    body_base64:str|None=Field(max_length=87384)
    operation_policy_sha256:str=Field(pattern=HASH)
    composer_program_sha256:str|None=Field(pattern=HASH)
    valid_until:AwareDatetime
    executable:bool
    qualification:Literal[False]
    remote_stop_proven:Literal[False]
    observation_only:Literal[True]
    resend_authorized:Literal[False]
    @field_validator('executable','qualification','remote_stop_proven','observation_only','resend_authorized',mode='before')
    @classmethod
    def exact_flags(cls,value):
        if type(value) is not bool:raise ValueError('actual worker observation flags required')
        return value
    @model_validator(mode='after')
    def exact_claim(self):
        if self.provider_account!=self.provider_account.strip() or any(ord(c)<32 or ord(c)==127 for c in self.provider_account):raise ValueError('canonical installed provider account required')
        if self.state=='claimed':
            if not self.executable or self.operation_id is None or self.claim_event_id is None or self.request_sha256 is None or type(self.body_base64) is not str:raise ValueError('first exact committed claim required')
            try:body=base64.b64decode(self.body_base64,validate=True)
            except (ValueError,binascii.Error):raise ValueError('canonical claimed body required') from None
            if base64.b64encode(body).decode()!=self.body_base64 or hashlib.sha256(body).hexdigest()!=self.request_sha256:raise ValueError('actual claimed body digest differs')
            if self.effect_purpose=='capture-create':
                if not 0<len(body)<=65536 or self.bot_id is not None:raise ValueError('exact create body without fabricated bot required')
            elif self.bot_id is None or (len(body)!=0 if self.effect_purpose in ('capture-leave','capture-retrieve') else not 0<len(body)<=32768):raise ValueError('exact current bot and closed operation body required')
        elif self.executable or self.body_base64 is not None:raise ValueError('only first committed claim may carry executable bytes')
        return self
