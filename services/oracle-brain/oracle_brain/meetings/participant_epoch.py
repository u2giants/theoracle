"""Immutable installed LIVE participant epoch; no employee/directory grant.

Whole-final artifacts retain their separate exact-raw attribution mapping.
Only the dedicated SQL capture owner decides which epoch is current.
"""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,digest
from .capture_contracts import HASH,TEXT,MAX_TURNS
class _EpochRecordV1(StrictRecord):
    @field_validator('schema_version',mode='before')
    @classmethod
    def actual_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('actual integer epoch version required')
        return v
class LiveParticipantLinkV1(_EpochRecordV1):
    provider_participant_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    attribution:Literal['workspace_actor','oracle','unknown']
    actor_id:UUID|None
    employee_uuid_metadata:UUID|None=None
    mapping_evidence_sha256:str=Field(pattern=HASH)
    @model_validator(mode='after')
    def exact(self):
        if self.provider_participant_id!=self.provider_participant_id.strip():raise ValueError('canonical stable provider participant required')
        if (self.attribution=='workspace_actor')!=(self.actor_id is not None):raise ValueError('independently mapped workspace actor required')
        return self
class LiveParticipantEpochV1(_EpochRecordV1):
    purpose:Literal['meeting-live-participant-epoch-v1']
    epoch_id:UUID
    epoch_revision:int=Field(ge=1,le=2147483647)
    workspace_id:UUID
    meeting_id:UUID
    provider:Literal['recall','graph']
    provider_account:str=Field(min_length=1,max_length=256,pattern=TEXT)
    tenant_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_meeting_id:str=Field(min_length=1,max_length=2048,pattern=TEXT)
    bot_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_participant_ids:tuple[str,...]=Field(min_length=1,max_length=MAX_TURNS)
    participant_set_sha256:str=Field(pattern=HASH)
    links:tuple[LiveParticipantLinkV1,...]=Field(min_length=1,max_length=MAX_TURNS)
    issuer_actor:UUID
    reviewer_actor:UUID
    capture_until:AwareDatetime
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    original_horizon:AwareDatetime
    @model_validator(mode='after')
    def exact(self):
        ids=self.provider_participant_ids
        if tuple(sorted(set(ids)))!=ids or any(not v or len(v)>256 or v!=v.strip() or any(ord(c)<32 or ord(c)==127 for c in v) for v in ids):raise ValueError('canonical complete stable participant population required')
        if tuple(x.provider_participant_id for x in self.links)!=ids:raise ValueError('exact ordered participant mapping population required')
        if self.participant_set_sha256!=digest({'provider_participant_ids':list(ids)}):raise ValueError('exact participant population digest required')
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.capture_until<=self.original_horizon:raise ValueError('independent finite original participant epoch required')
        if any(getattr(self,key)!=getattr(self,key).strip() for key in ('provider_account','tenant_id','provider_meeting_id','bot_id')):raise ValueError('canonical participant scope required')
        return self
    @property
    def sha256(self):return digest(self.model_dump(mode='json'))
