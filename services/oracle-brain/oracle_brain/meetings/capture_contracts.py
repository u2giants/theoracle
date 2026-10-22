"""Strict operational meeting descriptors. None is capture or truth authority."""
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime, Field, field_validator, model_validator
from oracle_brain.operating_model.contracts import StrictRecord, digest
HASH=r'^[a-f0-9]{64}$'
TEXT=r'^[^\x00-\x1f\x7f]+$'
MAX_RAW=1024*1024
MAX_TURNS=4096
class RawMeetingArtifactV1(StrictRecord):
    workspace_id:UUID
    meeting_id:UUID
    provider:Literal['recall','graph']
    provider_account:str=Field(min_length=1,max_length=256,pattern=TEXT)
    tenant_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_meeting_id:str=Field(min_length=1,max_length=2048,pattern=TEXT)
    provider_artifact_id:str=Field(min_length=1,max_length=1024,pattern=TEXT)
    provider_revision:str=Field(min_length=1,max_length=256,pattern=TEXT)
    original_sha256:str=Field(pattern=HASH)
    byte_count:int=Field(ge=1,le=MAX_RAW)
    media_type:Literal['application/json','text/vtt']
    final:bool
    @field_validator('provider_account','tenant_id','provider_meeting_id','provider_artifact_id','provider_revision')
    @classmethod
    def nonblank(cls,v):
        if v!=v.strip():raise ValueError('canonical meeting identity required')
        return v
class MeetingWordV1(StrictRecord):
    text:str=Field(min_length=1,max_length=16384)
    start_relative_seconds:str=Field(pattern=r'^(0|[1-9][0-9]{0,8})(\.[0-9]{1,9})?$',max_length=20)
    end_relative_seconds:str|None=Field(default=None,pattern=r'^(0|[1-9][0-9]{0,8})(\.[0-9]{1,9})?$',max_length=20)
    @model_validator(mode='after')
    def finite_order(self):
        try:
            a=Decimal(self.start_relative_seconds);b=Decimal(self.end_relative_seconds) if self.end_relative_seconds is not None else a
        except InvalidOperation:raise ValueError('finite relative time required')
        if not a.is_finite() or not b.is_finite() or b<a:raise ValueError('ordered relative time required')
        if not self.text.strip() or '\x00' in self.text:raise ValueError('nonblank original word required')
        return self
class MeetingTurnV1(StrictRecord):
    turn_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_speaker_id:str|None=Field(default=None,min_length=1,max_length=256,pattern=TEXT)
    display_name:str|None=Field(default=None,max_length=512)
    employee_id:UUID|None=None
    attribution:Literal['verified_employee','verified_external','oracle','unknown']
    language:str=Field(min_length=1,max_length=40,pattern=r'^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$')
    words:tuple[MeetingWordV1,...]=Field(min_length=1,max_length=MAX_TURNS)
    @model_validator(mode='after')
    def attribution_matches(self):
        if (self.attribution=='verified_employee')!=(self.employee_id is not None):raise ValueError('exact independent employee link required')
        if self.attribution!='unknown' and self.provider_speaker_id is None:raise ValueError('verified provider speaker required')
        if any(Decimal(b.start_relative_seconds)<Decimal(a.start_relative_seconds) for a,b in zip(self.words,self.words[1:])):raise ValueError('ordered original word timestamps required')
        return self
class MeetingRevisionV1(StrictRecord):
    raw:RawMeetingArtifactV1
    revision:int=Field(ge=1,le=2147483647)
    turns:tuple[MeetingTurnV1,...]=Field(max_length=MAX_TURNS)
    @model_validator(mode='after')
    def bounded(self):
        if len({t.turn_id for t in self.turns})!=len(self.turns) or sum(len(t.words) for t in self.turns)>MAX_TURNS:raise ValueError('bounded unique meeting turns required')
        return self
    @property
    def sha256(self):return digest(self.model_dump(mode='json'))
def reconcile_revision_v1(prior:MeetingRevisionV1|None,incoming:MeetingRevisionV1):
    if type(incoming) is not MeetingRevisionV1:raise TypeError('exact meeting revision required')
    incoming=MeetingRevisionV1.model_validate(incoming.model_dump(mode='python'))
    if prior is None:return incoming
    if type(prior) is not MeetingRevisionV1:raise TypeError('exact prior meeting revision required')
    prior=MeetingRevisionV1.model_validate(prior.model_dump(mode='python'))
    for key in ('workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id'):
        if getattr(prior.raw,key)!=getattr(incoming.raw,key):raise ValueError('cross-meeting revision')
    from oracle_brain.ingest.meeting import Transcript,Turn,reconcile
    from oracle_brain.ingest.speakers import Speaker
    def leaf(v):
        return Transcript(v.raw.tenant_id,str(v.raw.meeting_id),v.revision,tuple(Turn(t.turn_id,v.revision,Speaker(t.provider_speaker_id or 'unknown',t.display_name or '',str(t.employee_id) if t.employee_id else None),' '.join(w.text for w in t.words),'oracle' if t.attribution=='oracle' else 'participant') for t in v.turns),v.raw.final)
    reconcile(leaf(prior),leaf(incoming))
    if incoming.revision<prior.revision:return prior
    if incoming.revision==prior.revision:
        if incoming!=prior:raise ValueError('same revision conflicts')
        return prior
    if prior.raw.final and not incoming.raw.final:raise ValueError('final transcript cannot regress to live')
    return incoming
class MeetingTextDerivationV1(StrictRecord):
    purpose:Literal['meeting-reported-text-derivation-v1']
    raw:RawMeetingArtifactV1
    revision_sha256:str=Field(pattern=HASH)
    normalized_sha256:str=Field(pattern=HASH)
    byte_count:int=Field(ge=1,le=MAX_RAW)
    included_turn_ids:tuple[str,...]=Field(min_length=1,max_length=MAX_TURNS)
    excluded_turn_ids:tuple[str,...]=Field(max_length=MAX_TURNS)
    reported_only:Literal[True]=True
    qualification:Literal[False]=False
    @field_validator('reported_only','qualification',mode='before')
    @classmethod
    def literal_bool(cls,v):
        if type(v) is not bool:raise ValueError('actual boolean observation flags required')
        return v
    @model_validator(mode='after')
    def exact_population(self):
        all_ids=self.included_turn_ids+self.excluded_turn_ids
        if len(set(all_ids))!=len(all_ids) or any(not v or v!=v.strip() for v in all_ids):raise ValueError('unique complete turn population required')
        if not self.raw.final:raise ValueError('whole-final raw transcript required')
        return self

def derive_reported_text_v1(revision:MeetingRevisionV1):
    """Pure proposal: exact original-language words, never a SourceRef/grant.

    Raw bytes remain separately retained. Unknown attribution and Oracle turns
    stay visible in the revision, excluded from a participant-learning proposal.
    Only an actual independently installed speaker mapping may label verified.
    """
    import hashlib
    if type(revision) is not MeetingRevisionV1:raise TypeError('exact meeting revision required')
    revision=MeetingRevisionV1.model_validate(revision.model_dump(mode='python'))
    if not revision.raw.final:raise ValueError('whole-final raw transcript required')
    included=tuple(t for t in revision.turns if t.attribution in ('verified_employee','verified_external'))
    if not included:raise ValueError('no independently attributable participant text')
    # No translation, paraphrase, display-name identity, or invented timestamps.
    text='\n'.join(' '.join(w.text for w in t.words) for t in included).encode('utf-8')
    if not text or len(text)>MAX_RAW:raise ValueError('bounded participant text required')
    descriptor=MeetingTextDerivationV1(purpose='meeting-reported-text-derivation-v1',raw=revision.raw,revision_sha256=revision.sha256,normalized_sha256=hashlib.sha256(text).hexdigest(),byte_count=len(text),included_turn_ids=tuple(t.turn_id for t in included),excluded_turn_ids=tuple(t.turn_id for t in revision.turns if t not in included))
    return text,descriptor

class InstalledFinalArtifactV1(StrictRecord):
    """Independently installed exact selection, not a caller URL or grant."""
    purpose:Literal['meeting-final-artifact-selection-v1']
    workspace_id:UUID
    meeting_id:UUID
    provider:Literal['recall','graph']
    provider_account:str=Field(min_length=1,max_length=256,pattern=TEXT)
    tenant_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_meeting_id:str=Field(min_length=1,max_length=2048,pattern=TEXT)
    bot_id:str|None=Field(default=None,min_length=1,max_length=256,pattern=TEXT)
    recording_id:str=Field(min_length=1,max_length=1024,pattern=TEXT)
    transcript_id:str=Field(min_length=1,max_length=1024,pattern=TEXT)
    provider_revision:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_finality_receipt_sha256:str=Field(pattern=HASH)
    original_sha256:str=Field(pattern=HASH)
    byte_count:int=Field(ge=1,le=MAX_RAW)
    media_type:Literal['application/json','text/vtt']
    download_url:str=Field(min_length=1,max_length=8192)
    ca_file:str=Field(min_length=1,max_length=2048)
    ca_sha256:str=Field(pattern=HASH)
    server_der_sha256:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime
    @model_validator(mode='after')
    def bounded_selection(self):
        from urllib.parse import urlsplit,unquote
        from pathlib import Path
        u=urlsplit(self.download_url)
        if u.scheme!='https' or not u.hostname or u.port not in (None,443) or u.username or u.password or u.fragment or not u.path.startswith('/') or any(p in ('.','..') for p in unquote(u.path).split('/')) or any(ord(c)<=32 or ord(c)==127 for c in self.download_url):raise ValueError('exact fixed HTTPS artifact selection required')
        if not Path(self.ca_file).is_absolute() or Path(self.ca_file).resolve()!=Path(self.ca_file):raise ValueError('canonical private artifact CA required')
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent finite final selection required')
        if self.provider=='recall' and self.bot_id is None:raise ValueError('exact capture bot required')
        return self
