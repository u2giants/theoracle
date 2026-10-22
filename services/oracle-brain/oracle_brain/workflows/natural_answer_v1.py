"""Closed natural question planning over the SAME permitted qualified model.

Pure planning is descriptive, never authentication or model/source authority.
The protected answer owner obtains and rechecks actual SQL/SDK context before
and after calling this module. No provider, invented identity, or history cache.
"""
from dataclasses import dataclass
from datetime import datetime
import re
from typing import Literal
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from oracle_brain.operating_model.consolidation_contracts_v1 import AssertionScopeV1,ConsolidationCoreV1
from oracle_brain.retrieval.planner import _signals
from oracle_brain.operating_model.protected_inputs_v1 import parse_canonical_object_v1

Mode=Literal['local','connected','historical','global']

class NaturalQuestionRequestV1(StrictRecord):
    protocol:Literal['qualified-natural-question-v1']='qualified-natural-question-v1'
    caller_deadline:AwareDatetime
    question:str=Field(min_length=1,max_length=4096)
    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_schema(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact natural question schema required')
        return value
    @model_validator(mode='after')
    def exact_original_question(self):
        if not self.question.strip() or '\x00' in self.question or len(self.question.encode('utf-8'))>16384:
            raise ValueError('bounded exact original Unicode question required')
        return self
    @property
    def expires_at(self):return self.caller_deadline

def parse_natural_question_request_v1(raw):
    obj=parse_canonical_object_v1(raw,limit=65536)
    if (set(obj)!=set(NaturalQuestionRequestV1.model_fields)
            or type(obj.get('schema_version')) is not int or obj['schema_version']!=1
            or obj.get('protocol')!='qualified-natural-question-v1'):
        raise ValueError('complete closed natural question envelope required')
    return NaturalQuestionRequestV1.model_validate_json(raw)

class NaturalResolvedPlanV1(StrictRecord):
    """Server-derived selectors only; NEVER accepted as a public request."""
    question:str=Field(min_length=1,max_length=4096)
    mode:Mode
    scope:AssertionScopeV1
    process_ids:tuple[str,...]=Field(min_length=1,max_length=32)
    valid_at:AwareDatetime|None=None
    known_at:AwareDatetime|None=None
    expected_version:int=Field(ge=1)
    max_records:Literal[32]=32
    max_bytes:Literal[65536]=65536
    page:Literal[0]=0
    @field_validator('schema_version','max_records','max_bytes','page',mode='before')
    @classmethod
    def exact_bounds(cls,value):
        if type(value) is not int:raise ValueError('exact natural plan integer bounds required')
        return value
    @model_validator(mode='after')
    def closed_server_plan(self):
        if (not self.question.strip() or '\x00' in self.question or len(self.question.encode('utf-8'))>16384
                or len(set(self.process_ids))!=len(self.process_ids)
                or any(not p or len(p)>200 or p.strip()!=p or '\x00' in p for p in self.process_ids)
                or (self.mode=='historical')!=(self.valid_at is not None and self.known_at is not None)
                or self.mode!='historical' and (self.valid_at is not None or self.known_at is not None)):
            raise ValueError('closed source-derived bounded natural plan required')
        return self

@dataclass(frozen=True)
class NaturalIntentV1:
    mode:Mode
    valid_at:datetime|None=None
    known_at:datetime|None=None
    clarification:str|None=None

_ISO=r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})'
_DATED=re.compile(r'\b(?:valid\s+at|business\s+(?:date|time)\s*:?|at)\s*('+_ISO+r').*?\b(?:as\s+known\s+(?:at|by)|known\s+(?:at|by)|knowledge\s+(?:date|time)\s*:?)\s*('+_ISO+r')',re.I|re.S)

def natural_intent_v1(question,*,now):
    historical,connected,global_scope,_=_signals(question)
    dates=_DATED.search(question)
    if historical or dates is not None:
        if dates is None or len(re.findall(_ISO,question))!=2:
            return NaturalIntentV1('historical',clarification='Which business date and knowledge date should I use? Please give both exact times with their time zones.')
        try:
            valid=datetime.fromisoformat(dates[1]);known=datetime.fromisoformat(dates[2])
            if known>now:raise ValueError('future knowledge time')
        except (ValueError,OverflowError):
            return NaturalIntentV1('historical',clarification='Which past knowledge time and business time should I use, with their time zones?')
        return NaturalIntentV1('historical',valid,known)
    if global_scope:return NaturalIntentV1('global')
    return NaturalIntentV1('connected' if connected else 'local')


def resolve_natural_question_v1(question,core,*,observed_at):
    if type(core) is not ConsolidationCoreV1:raise TypeError('exact permitted qualified core required')
    # Revalidate text WITHOUT replacing, translating or normalizing its bytes.
    NaturalQuestionRequestV1(caller_deadline=observed_at,question=question)
    intent=natural_intent_v1(question,now=observed_at)
    if intent.clarification:return None,intent.clarification
    if re.search(r'\b(customer|product|region)\b',question,re.I):
        return None,'Which qualified customer, product or region scope should I use? Those business names are not yet established by this model.'
    text=question.casefold();matches=[];matched_labels={}
    for process in core.model.processes:
        label=process.label.casefold()
        if re.search(r'(?<!\w)'+re.escape(label)+r'(?!\w)',text):
            matches.append(process.process_id);matched_labels.setdefault(label,[]).append(process.process_id)
    if any(len(ids)>1 for ids in matched_labels.values()):
        return None,'Which business process do you mean? More than one permitted process has that name.'
    if not matches and re.search(r'\b(it|they|them|that|this|those|next)\b',text):
        return None,'Which process or reported action do you mean in this question?'
    if intent.mode=='global':selected=tuple(p.process_id for p in core.model.processes)
    elif matches:selected=tuple(matches)
    elif len(core.model.processes)==1:selected=(core.model.processes[0].process_id,)
    else:return None,'Which business process should this question cover?'
    if len(selected)>32:return None,'Which smaller group of business processes should this question cover?'
    if len(selected)>1 and intent.mode=='local':
        return None,'Should I compare those processes or follow their supported handoffs?'
    # UUID-only scope metadata cannot prove a customer/product/region name.
    # Multiple differing scopes ask for clarification instead of silently
    # choosing a value or claiming a name-resolution capability that is absent.
    process_observations={o for p in core.model.processes if p.process_id in selected for o in p.observation_ids}
    relevant=[a for a in core.assertions if process_observations&(set(a.supporting_observations)|set(a.opposing_observations)|set(a.temporal_observations))]
    for dimension in ('customer','product','region'):
        scopes={getattr(a.scope,dimension).identities for a in relevant if getattr(a.scope,dimension).mode=='exact'}
        if len(scopes)>1:return None,'Which customer, product and region should this question cover? The recorded scopes differ.'
    scope=AssertionScopeV1.model_validate_json(canonical_bytes({k:{'mode':'all','identities':[]} for k in ('process','customer','product','region')}))
    return NaturalResolvedPlanV1(question=question,mode=intent.mode,scope=scope,process_ids=selected,
        valid_at=intent.valid_at,known_at=intent.known_at,expected_version=core.model.version),None


async def answer_natural_from_projection_v1(projection,request):
    from oracle_brain.operating_model.sdk_projection import ConsolidatedMetadataSDKProjectionV1
    from oracle_brain.operating_model.request_deadline_v1 import request_remaining_v1
    from .answer import _pack_answer_v1,DocumentaryAnswerV1
    if type(projection) is not ConsolidatedMetadataSDKProjectionV1 or type(request) is not NaturalQuestionRequestV1:
        raise PermissionError('actual same qualified readonly SDK and exact natural question required')
    request_remaining_v1();packet=await projection.load()
    plan,clarification=resolve_natural_question_v1(request.question,packet[0],observed_at=packet[3].checked_at)
    answer=None
    if plan is not None:
        answer=_pack_answer_v1(packet[0],packet[2],packet[1],plan,observed_at=packet[3].checked_at)
        if answer.state=='clarification':clarification=answer.answer_text;answer=None;plan=None
        elif plan.mode=='historical':
            answer=DocumentaryAnswerV1.model_validate_json(canonical_bytes(answer.model_dump(mode='json')|{
                'business_decisions_as_of':[d.model_dump(mode='json') for d in packet[3].business_decisions_as_of]}))
    # Clarification has the SAME actual current complete recipient/source/ACK
    # checks; no answer, mode or invented evidence is fabricated for it.
    await projection.verify(packet[2]);request_remaining_v1()
    return answer,clarification,plan.mode if plan else None,packet
