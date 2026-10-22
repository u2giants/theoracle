"""Closed operational whole-final population; never a source/identity grant."""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator,field_validator
from oracle_brain.operating_model.contracts import StrictRecord,digest
from oracle_brain.hosting.original_intake_v1 import RequesterContextV1
from .capture_contracts import InstalledFinalArtifactV1
HASH=r'^[a-f0-9]{64}$'
# URL, CA, issuer/reviewer and dates are installation metadata, not a new
# population. Their replacement must collide with the existing spent fence.
FINAL_POPULATION_FIELDS_V1=('workspace_id','meeting_id','provider','provider_account','tenant_id','provider_meeting_id','bot_id','recording_id','transcript_id','provider_revision','provider_finality_receipt_sha256','original_sha256','byte_count','media_type')

def final_population_sha256_v1(descriptor):
    if type(descriptor) is not InstalledFinalArtifactV1:raise TypeError('exact independently installed final descriptor required')
    descriptor=InstalledFinalArtifactV1.model_validate(descriptor.model_dump(mode='python'))
    value=descriptor.model_dump(mode='json')
    return digest({field:value[field] for field in FINAL_POPULATION_FIELDS_V1})

class MeetingProcessIngressSQLV1(StrictRecord):
    context:RequesterContextV1
    meeting_id:UUID
    capture_until:AwareDatetime
    valid_until:AwareDatetime
    original_ingress_event_id:UUID
    descriptor_sha256:str|None=Field(pattern=HASH)
    population_sha256:str|None=Field(pattern=HASH)
    final_operation_id:UUID|None
    fetch_claim_id:UUID|None
    state:Literal['final_artifact_pending','fresh_fetch','UNKNOWN','final_linked']
    fresh_fetch_claim:bool
    final_event_id:UUID|None
    original_effect_deadline:AwareDatetime|None
    original_processing_horizon:AwareDatetime
    observation_only:bool
    @field_validator('fresh_fetch_claim','observation_only',mode='before')
    @classmethod
    def flags(cls,value):
        if type(value) is not bool:raise ValueError('actual operational boolean required')
        return value
    @model_validator(mode='after')
    def exact(self):
        if self.fresh_fetch_claim!=(self.state=='fresh_fetch'):raise ValueError('only actual fresh global fetch claim may fetch')
        if self.state=='final_linked' and self.final_event_id is None:raise ValueError('actual retained final event required')
        if self.state=='final_artifact_pending' and any(x is not None for x in (self.fetch_claim_id,self.final_event_id,self.original_effect_deadline)):raise ValueError('missing descriptor cannot consume an effect')
        if self.fresh_fetch_claim and (self.observation_only or self.fetch_claim_id is None or self.original_effect_deadline is None):raise ValueError('observation never executes fetch')
        return self
