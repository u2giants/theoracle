"""Whole-final transcript interpretation, never a speaker or source grant.

The exact raw artifact is retained separately. Provider names, emails and
metadata never establish employee identity. Only separately installed scoped
speaker links affect attribution; unmatched turns remain visible and unknown.
"""
from decimal import Decimal
import hashlib,json
from uuid import UUID
from typing import Literal
from pydantic import AwareDatetime,Field,model_validator
from oracle_brain.operating_model.contracts import StrictRecord
from oracle_brain.hosting.gateway import unique_object
from .capture_contracts import (HASH,TEXT,MAX_RAW,MAX_TURNS,RawMeetingArtifactV1,
    MeetingRevisionV1,MeetingTurnV1,MeetingWordV1)

class InstalledSpeakerLinkV1(StrictRecord):
    provider_speaker_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    attribution:Literal['verified_employee','verified_external','oracle']
    employee_id:UUID|None=None
    @model_validator(mode='after')
    def exact(self):
        if self.provider_speaker_id!=self.provider_speaker_id.strip():raise ValueError('canonical speaker identifier required')
        if (self.attribution=='verified_employee')!=(self.employee_id is not None):raise ValueError('independent employee identity required')
        return self

class InstalledSpeakerMappingV1(StrictRecord):
    purpose:Literal['meeting-speaker-mapping-v1']
    workspace_id:UUID
    meeting_id:UUID
    provider:Literal['recall','graph']
    provider_account:str=Field(min_length=1,max_length=256,pattern=TEXT)
    tenant_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_meeting_id:str=Field(min_length=1,max_length=2048,pattern=TEXT)
    raw_sha256:str=Field(pattern=HASH)
    links:tuple[InstalledSpeakerLinkV1,...]=Field(max_length=MAX_TURNS)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        if len({x.provider_speaker_id for x in self.links})!=len(self.links):raise ValueError('duplicate speaker identity')
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent finite mapping required')
        return self

def _relative(value):
    if type(value) is not dict or 'relative' not in value:raise ValueError('actual relative timestamp required')
    n=value['relative']
    if type(n) not in (int,Decimal) or not Decimal(n).is_finite() or n<0:raise ValueError('finite nonnegative relative timestamp required')
    return format(Decimal(n),'f')

def _final_mapping_links_v1(descriptor,mapping,observed_at):
    links={}
    if mapping is not None:
        if type(mapping) is not InstalledSpeakerMappingV1:raise TypeError('exact installed mapping required')
        mapping=InstalledSpeakerMappingV1.model_validate(mapping.model_dump(mode='python'))
        for key in ('workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id'):
            if getattr(mapping,key)!=getattr(descriptor,key):raise ValueError('foreign meeting speaker mapping')
        if mapping.raw_sha256!=descriptor.original_sha256 or not mapping.valid_from<=observed_at<min(mapping.expires_at,mapping.original_horizon):raise ValueError('stale speaker mapping')
        links={x.provider_speaker_id:x for x in mapping.links}
    return links

def parse_final_recall_v1(raw:bytes,descriptor:RawMeetingArtifactV1,*,revision:int,mapping:InstalledSpeakerMappingV1|None=None,observed_at):
    """Pure exact-byte parser. Mapping consumption still requires fresh admission.

    No mapping means unknown attribution; raw participant labels are display
    only. This function cannot fetch, qualify, persist or expose an original.
    """
    if type(raw) is not bytes or type(descriptor) is not RawMeetingArtifactV1 or descriptor.provider!='recall' or descriptor.media_type!='application/json' or descriptor.final is not True:raise ValueError('exact whole-final Recall original required')
    descriptor=RawMeetingArtifactV1.model_validate(descriptor.model_dump(mode='python'))
    if not 0<len(raw)<=MAX_RAW or len(raw)!=descriptor.byte_count or hashlib.sha256(raw).hexdigest()!=descriptor.original_sha256:raise ValueError('raw original identity differs')
    links=_final_mapping_links_v1(descriptor,mapping,observed_at)
    try:
        value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique_object,parse_float=Decimal,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite provider value')))
    except (UnicodeError,ValueError):raise ValueError('strict UTF8 final JSON required') from None
    if type(value) is not list or not 0<len(value)<=MAX_TURNS:raise ValueError('bounded whole-final turn array required')
    turns=_recall_turns_v1(value,links)
    return MeetingRevisionV1(raw=descriptor,revision=revision,turns=tuple(turns))


def _recall_turns_v1(value,links):
    turns=[];total=0
    for index,item in enumerate(value):
        if type(item) is not dict or type(item.get('participant')) is not dict or type(item.get('words')) is not list:raise ValueError('actual final transcript turn required')
        participant=item['participant'];speaker=participant.get('id')
        if type(speaker) is not int or speaker<0:raise ValueError('actual meeting-local participant identifier required')
        speaker=str(speaker);link=links.get(speaker);name=participant.get('name')
        if name is not None and (type(name) is not str or len(name)>512 or '\x00' in name):raise ValueError('bounded participant display label required')
        words=[];total+=len(item['words'])
        if not item['words'] or total>MAX_TURNS:raise ValueError('bounded original words required')
        for word in item['words']:
            if type(word) is not dict or type(word.get('text')) is not str:raise ValueError('actual original word required')
            end=word.get('end_timestamp')
            words.append(MeetingWordV1(text=word['text'],start_relative_seconds=_relative(word.get('start_timestamp')),end_relative_seconds=None if end is None else _relative(end)))
        turns.append(MeetingTurnV1(turn_id=f'raw-turn:{index}',provider_speaker_id=speaker,display_name=name,employee_id=link.employee_id if link else None,attribution=link.attribution if link else 'unknown',language=item.get('language_code'),words=tuple(words)))
    # Unknown mapping entries are refused; accidental cross-artifact links may
    # never silently disappear from the accounted population.
    if set(links)-{x.provider_speaker_id for x in turns}:raise ValueError('dangling installed speaker identity')
    return tuple(turns)


def parse_live_recall_utterance_v1(raw,descriptor,*,revision,epoch,observed_at,expected_bot_id):
    """Finalized utterance only; independently current SQL epoch is still required."""
    from .participant_epoch import LiveParticipantEpochV1
    if type(raw) is not bytes or type(descriptor) is not RawMeetingArtifactV1 or descriptor.provider!='recall' or descriptor.final is not False or descriptor.media_type!='application/json':raise ValueError('exact live utterance original required')
    descriptor=RawMeetingArtifactV1.model_validate(descriptor.model_dump(mode='python'))
    if len(raw)!=descriptor.byte_count or hashlib.sha256(raw).hexdigest()!=descriptor.original_sha256:raise ValueError('actual live raw identity differs')
    if type(epoch) is not LiveParticipantEpochV1:raise ValueError('independent live participant epoch required')
    epoch=LiveParticipantEpochV1.model_validate(epoch.model_dump(mode='python'))
    for key in ('workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id'):
        if getattr(epoch,key)!=getattr(descriptor,key):raise ValueError('foreign live participant epoch')
    if epoch.bot_id!=expected_bot_id or not epoch.valid_from<=observed_at<min(epoch.expires_at,epoch.capture_until,epoch.original_horizon):raise ValueError('stale live participant epoch')
    value=json.loads(raw.decode('utf-8'),object_pairs_hook=unique_object,parse_float=Decimal,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite provider value')))
    if type(value) is not dict or value.get('event')!='transcript.data' or type(value.get('data')) is not dict or type(value['data'].get('data')) is not dict:raise ValueError('finalized current utterance required')
    if type(value['data'].get('bot')) is not dict or value['data']['bot'].get('id')!=expected_bot_id:raise ValueError('actual installed bot identity differs')
    item=value['data']['data'];participant=item.get('participant')
    if type(participant) is not dict or type(participant.get('id')) is not int or str(participant['id']) not in epoch.provider_participant_ids:raise ValueError('stable participant absent from current epoch')
    link=next(x for x in epoch.links if x.provider_participant_id==str(participant['id']))
    # Workspace actor membership is not employee identity. This structural
    # leaf's external label never asserts an employee or company access fact.
    structural={} if link.attribution=='unknown' else {link.provider_participant_id:InstalledSpeakerLinkV1(provider_speaker_id=link.provider_participant_id,attribution='verified_external' if link.attribution=='workspace_actor' else link.attribution)}
    turns=_recall_turns_v1([item],structural)
    return MeetingRevisionV1(raw=descriptor,revision=revision,turns=turns)


def parse_final_graph_v1(raw:bytes,descriptor:RawMeetingArtifactV1,*,revision:int,language:str,mapping:InstalledSpeakerMappingV1|None=None,observed_at):
    """Exact selected Graph WebVTT; cue labels are display-only.

    The independent mapping binds exact raw bytes and positional cue selectors.
    No displayed voice name, email, cue UUID or timing creates an actor.
    Legacy normalization and pure employee mapping APIs remain unchanged.
    """
    import re,html
    if (type(raw) is not bytes or type(descriptor) is not RawMeetingArtifactV1
        or descriptor.provider!='graph' or descriptor.media_type!='text/vtt' or descriptor.final is not True):raise ValueError('exact whole-final Graph WebVTT required')
    descriptor=RawMeetingArtifactV1.model_validate(descriptor.model_dump(mode='python'))
    if not 0<len(raw)<=MAX_RAW or len(raw)!=descriptor.byte_count or hashlib.sha256(raw).hexdigest()!=descriptor.original_sha256:raise ValueError('raw original identity differs')
    if type(language) is not str or re.fullmatch(r'[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*',language) is None:raise ValueError('independently selected transcript language required')
    text=raw.decode('utf-8',errors='strict')
    if '\x00' in text or '\r' in text.replace('\r\n',''):raise ValueError('strict original VTT lines required')
    text=text.replace('\r\n','\n').removesuffix('\n');blocks=text.split('\n\n')
    if blocks[0]!='WEBVTT':raise ValueError('exact WEBVTT header required')
    links=_final_mapping_links_v1(descriptor,mapping,observed_at);turns=[];seen_ids=set()
    timestamp=r'(\d{2,6}):([0-5][0-9]):([0-5][0-9])\.([0-9]{3})'
    def relative(parts):
        h,m,sec,ms=map(int,parts);return format(Decimal(h*3600+m*60+sec)+Decimal(ms)/1000,'f')
    for block in blocks[1:]:
        if not block.strip():continue
        lines=block.split('\n');cue_id=None
        if '-->' not in lines[0]:
            cue_id=lines.pop(0)
            if not cue_id or len(cue_id)>256 or cue_id in seen_ids or any(ord(c)<32 or ord(c)==127 for c in cue_id):raise ValueError('unique bounded VTT cue identity required')
            seen_ids.add(cue_id)
        if not lines:raise ValueError('complete VTT cue required')
        match=re.fullmatch(timestamp+r' --> '+timestamp,lines.pop(0))
        if match is None:raise ValueError('exact bounded VTT cue timestamps required')
        start=relative(match.groups()[:4]);end=relative(match.groups()[4:])
        cue='\n'.join(lines);voice=re.fullmatch(r'<v ([^<>\n]{1,512})>([\s\S]*)</v>',cue)
        name=voice.group(1) if voice else None;words=voice.group(2) if voice else cue
        if '<' in words or '>' in words:raise ValueError('unsupported VTT markup cannot be silently removed')
        words=html.unescape(words)
        selector=f'raw-cue:{len(turns)}';link=links.get(selector)
        if len(turns)>=MAX_TURNS:raise ValueError('bounded complete Graph cues required')
        turns.append(MeetingTurnV1(turn_id=selector,provider_speaker_id=selector,display_name=name,
            employee_id=link.employee_id if link else None,attribution=link.attribution if link else 'unknown',language=language,
            words=(MeetingWordV1(text=words,start_relative_seconds=start,end_relative_seconds=end),)))
    if not turns or set(links)-{t.provider_speaker_id for t in turns}:raise ValueError('complete nonempty Graph cue mapping required')
    if any(Decimal(b.words[0].start_relative_seconds)<Decimal(a.words[0].start_relative_seconds) for a,b in zip(turns,turns[1:])):raise ValueError('ordered Graph cue population required')
    return MeetingRevisionV1(raw=descriptor,revision=revision,turns=tuple(turns))
