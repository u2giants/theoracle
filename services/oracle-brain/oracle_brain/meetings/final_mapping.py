"""Exact-raw whole-final workspace attribution, consumed only by SQL020.

This independent installed descriptor does not establish employee membership,
source access or permission. Legacy pure speaker mapping remains separate.
"""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,digest
from .capture_contracts import HASH,TEXT,MAX_TURNS
class _Record(StrictRecord):
    @field_validator('schema_version',mode='before')
    @classmethod
    def actual_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('actual final mapping version required')
        return v
class FinalWorkspaceSpeakerLinkV1(_Record):
    provider_speaker_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    attribution:Literal['workspace_actor','oracle','unknown']
    actor_id:UUID|None
    mapping_evidence_sha256:str=Field(pattern=HASH)
    @model_validator(mode='after')
    def exact(self):
        if self.provider_speaker_id!=self.provider_speaker_id.strip() or (self.attribution=='workspace_actor')!=(self.actor_id is not None):raise ValueError('independent exact workspace attribution required')
        return self
class FinalWorkspaceSpeakerMappingV1(_Record):
    purpose:Literal['meeting-final-workspace-mapping-v1']
    mapping_id:UUID
    mapping_revision:int=Field(ge=1,le=2147483647)
    workspace_id:UUID
    meeting_id:UUID
    provider:Literal['recall','graph']
    provider_account:str=Field(min_length=1,max_length=256,pattern=TEXT)
    tenant_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_meeting_id:str=Field(min_length=1,max_length=2048,pattern=TEXT)
    raw_sha256:str=Field(pattern=HASH)
    language:str=Field(pattern=r'^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$',max_length=40)
    links:tuple[FinalWorkspaceSpeakerLinkV1,...]=Field(min_length=1,max_length=MAX_TURNS)
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        if len({x.provider_speaker_id for x in self.links})!=len(self.links):raise ValueError('unique complete final cue mapping required')
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.original_horizon:raise ValueError('independent original final processing window required')
        for key in ('provider_account','tenant_id','provider_meeting_id'):
            if getattr(self,key)!=getattr(self,key).strip():raise ValueError('canonical final mapping scope required')
        return self
    @property
    def sha256(self):return digest(self.model_dump(mode='json'))
    def structural_mapping_v1(self):
        """Only current SQL owner may use this projection for actual processing."""
        from .final_transcript import InstalledSpeakerMappingV1,InstalledSpeakerLinkV1
        return InstalledSpeakerMappingV1(purpose='meeting-speaker-mapping-v1',
            **{k:getattr(self,k) for k in ('workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id','raw_sha256','issuer_actor','reviewer_actor','valid_from','expires_at','original_horizon')},
            links=tuple(InstalledSpeakerLinkV1(provider_speaker_id=x.provider_speaker_id,attribution='verified_external' if x.attribution=='workspace_actor' else 'oracle') for x in self.links if x.attribution!='unknown'))
