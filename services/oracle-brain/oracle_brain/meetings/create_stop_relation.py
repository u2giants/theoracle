"""Independently installed exact-operation STOP relation; never a bot issuer."""
from datetime import timezone
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,digest
from .capture_contracts import HASH,TEXT

class CreateOperationStopRelationV1(StrictRecord):
    purpose:Literal['meeting-create-operation-stop-relation-v1']
    mapping_id:UUID
    workspace_id:UUID
    meeting_id:UUID
    provider:Literal['recall']
    provider_account:str=Field(min_length=1,max_length=256,pattern=TEXT)
    tenant_id:str=Field(min_length=1,max_length=256,pattern=TEXT)
    provider_meeting_id:str=Field(min_length=1,max_length=2048,pattern=TEXT)
    create_operation_id:UUID
    create_request_sha256:str=Field(pattern=HASH)
    supervision_scope_sha256:str=Field(pattern=HASH)
    scheduler_id:UUID
    stop_owner_id:UUID
    scheduler_runtime_sha256:str=Field(pattern=HASH)
    scheduler_config_sha256:str=Field(pattern=HASH)
    stop_runtime_sha256:str=Field(pattern=HASH)
    stop_config_sha256:str=Field(pattern=HASH)
    capture_until:AwareDatetime
    stop_valid_from:AwareDatetime
    stop_until:AwareDatetime
    original_horizon:AwareDatetime
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime
    @field_validator('schema_version',mode='before')
    @classmethod
    def actual_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('actual integer relation version required')
        return value
    @model_validator(mode='after')
    def exact(self):
        if len({self.scheduler_id,self.stop_owner_id,self.issuer_actor,self.reviewer_actor})!=4:raise ValueError('independently appointed scheduler and STOP owners required')
        if not self.valid_from<=self.stop_valid_from<self.capture_until<=self.stop_until<=self.original_horizon or not self.stop_valid_from<self.expires_at<=self.stop_until:raise ValueError('immutable original STOP relation window required')
        for name in ('provider_account','tenant_id','provider_meeting_id'):
            if getattr(self,name)!=getattr(self,name).strip():raise ValueError('canonical installed provider relation required')
        return self
    @property
    def sha256(self):return digest(self.model_dump(mode='json'))
