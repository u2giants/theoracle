"""Closed optional conversation display; a parsed record grants no authority.

Only the actual SQL019→SQL024/native/Budget/SDK consumer may publish observed
results. These pure records preserve current recipient display scope separately
from the immutable spent-operation deadline and independent original cost scope.
"""
from datetime import timedelta
import hashlib
from typing import Literal,Any
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator,model_validator
from .contracts import StrictRecord,digest
from .qualified_answer_v1 import QualifiedVectorAnswerV1,QualifiedSynthesisAnswerV1
HASH=r'^[0-9a-f]{64}$'
OBSERVED_FIELDS=('purpose','operation_id','model_id','model_version','model_content_hash','accepted_projection_event_id','accepted_receipt_body_sha256','native_receipt_sha256','wire_sha256','settled_response_sha256','answer','synthesis')

class QuestionEffectPacketV1(StrictRecord):
    protocol:Literal['question-effect-result-v1']='question-effect-result-v1'
    state:Literal['observed','clarification','unknown','unavailable']
    principal_id:UUID
    workspace_id:UUID
    thread_id:UUID
    thread_revision:int=Field(strict=True,ge=1)
    employee_event_id:UUID
    original_sha256:str=Field(pattern=HASH)
    query_sha256:str=Field(pattern=HASH)
    channel:Literal['web']='web'
    checked_at:AwareDatetime
    expires_at:AwareDatetime
    purpose:Literal['qualified-query-embedding-v1','qualified-answer-synthesis-v1']|None
    operation_id:UUID|None
    model_id:UUID|None
    model_version:int|None=Field(ge=1)
    model_content_hash:str|None=Field(pattern=HASH)
    accepted_projection_event_id:UUID|None
    accepted_receipt_body_sha256:str|None=Field(pattern=HASH)
    native_receipt_sha256:str|None=Field(pattern=HASH)
    wire_sha256:str|None=Field(pattern=HASH)
    settled_response_sha256:str|None=Field(pattern=HASH)
    answer:QualifiedVectorAnswerV1|QualifiedSynthesisAnswerV1|None
    synthesis:dict[str,Any]|None
    clarification:str|None=Field(max_length=2000)
    provider_dispatched:bool|None
    automatic_retry_allowed:Literal[False]=False
    semantic_entailment_verified:Literal[False]=False
    business_accepted:Literal[False]=False
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact effect schema required')
        return value
    @field_validator('automatic_retry_allowed','semantic_entailment_verified','business_accepted',mode='before')
    @classmethod
    def exact_false(cls,value):
        if value is not False:raise ValueError('effect display grants no retry/semantic/business acceptance')
        return value
    @model_validator(mode='after')
    def closed_outcome(self):
        if not self.checked_at<self.expires_at<=self.checked_at+timedelta(seconds=30):raise ValueError('current recipient display window only')
        if self.state!='observed':
            if any(getattr(self,k) is not None for k in OBSERVED_FIELDS):raise ValueError('unobserved effect has no model/receipt/answer')
            if self.provider_dispatched is not(None if self.state=='unknown' else False):raise ValueError('unobserved dispatch truth differs')
            if self.state=='clarification':
                if self.clarification is None or not self.clarification.strip() or '\0' in self.clarification or len(self.clarification.encode('utf8'))>8000:raise ValueError('bounded honest clarification required')
            elif self.clarification is not None:raise ValueError('no fabricated clarification')
            return self
        required=tuple(k for k in OBSERVED_FIELDS if k!='synthesis')
        if any(getattr(self,k) is None for k in required) or self.provider_dispatched is not True or self.clarification is not None:raise ValueError('complete observed actual effect bindings required')
        if(self.answer.model_version,self.answer.model_content_hash)!=(self.model_version,self.model_content_hash):raise ValueError('exact observed model/answer differs')
        if self.purpose=='qualified-query-embedding-v1':
            if type(self.answer) is not QualifiedVectorAnswerV1 or self.synthesis is not None:raise ValueError('closed actual vector result required')
        elif self.purpose=='qualified-answer-synthesis-v1':
            if type(self.answer) is not QualifiedSynthesisAnswerV1 or self.answer.query_embedding_used is not False or self.synthesis is None:raise ValueError('distinct text synthesis; no borrowed query receipt')
            from .qualified_synthesis_v1 import validate_synthesis_references_v1
            validate_synthesis_references_v1(self.synthesis,self.answer,interview=False)
        else:raise ValueError('independently appointed effect purpose required')
        return self

def _scope_fields_v1(snapshot):
    events=[e for e in snapshot['recap']['events'] if e['origin']=='employee']
    if not events:raise PermissionError('actual employee original required')
    event=events[-1];original=event['original_text']
    if type(original) is not str or not original.strip() or '\0' in original or len(original.encode('utf8'))>32768 or hashlib.sha256(original.encode('utf8')).hexdigest()!=event['original_sha256']:raise PermissionError('immutable original hash differs')
    return dict(principal_id=snapshot['principal_id'],workspace_id=snapshot['workspace_id'],thread_id=snapshot['thread_id'],thread_revision=snapshot['revision'],employee_event_id=event['event_id'],original_sha256=event['original_sha256'],query_sha256=digest({'schema_version':1,'protocol':'qualified-natural-question-v1','question':original}))

def validate_question_effect_scope_v1(packet,snapshot):
    if type(packet) is not QuestionEffectPacketV1:raise TypeError('exact closed display packet required')
    actual=packet.model_dump(mode='json');expected=_scope_fields_v1(snapshot)
    if any(actual[k]!=v for k,v in expected.items()):raise PermissionError('actual current employee/thread/original display binding differs')
    if packet.state=='clarification' and snapshot['mode']=='interview':raise PermissionError('no extra scope question around SQL interview cap')
    if packet.synthesis is not None:
        from .qualified_synthesis_v1 import validate_synthesis_references_v1
        validate_synthesis_references_v1(packet.synthesis,packet.answer,interview=snapshot['mode']=='interview')
    return packet

def nonobserved_question_effect_v1(snapshot,*,state,checked_at,expires_at,clarification=None):
    """Descriptive display only; actual caller supplies its own SQL019 snapshot."""
    from .contracts import canonical_bytes
    value={k:None for k in OBSERVED_FIELDS}|_scope_fields_v1(snapshot)|dict(schema_version=1,protocol='question-effect-result-v1',state=state,channel='web',checked_at=checked_at.isoformat(),expires_at=expires_at.isoformat(),clarification=clarification,provider_dispatched=None if state=='unknown' else False,automatic_retry_allowed=False,semantic_entailment_verified=False,business_accepted=False)
    return validate_question_effect_scope_v1(QuestionEffectPacketV1.model_validate_json(canonical_bytes(value)),snapshot)
