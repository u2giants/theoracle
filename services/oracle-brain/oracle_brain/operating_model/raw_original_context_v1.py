"""Fixed byte-only paid PDF phase context, not a source or spend appointment."""
from typing import Literal
from uuid import UUID
from pydantic import Field,AwareDatetime,field_validator,model_validator
from .contracts import StrictRecord,digest
from .native_factory import RawOriginalDispatchJobV1
from .original_qualification_v1 import RawOriginalPopulationV1
HASH=r'^[0-9a-f]{64}$'

class RawOriginalPhaseContextV1(StrictRecord):
    schema_version:Literal[1]=1
    context_schema:Literal['raw-original-phase-context-v1']='raw-original-phase-context-v1'
    actor_id:UUID
    expected_session_role:str=Field(pattern=r'^[a-z_][a-z0-9_]{0,62}$')
    population:RawOriginalPopulationV1
    job:RawOriginalDispatchJobV1
    original_allocation_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    pricing_quote_hash:str=Field(pattern=HASH)
    view_policy_hash:str=Field(pattern=HASH)
    vision_token_policy_hash:str=Field(pattern=HASH)
    phase_expires_at:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact raw original context version required')
        return v

    @model_validator(mode='after')
    def complete_original_phase_binding(self):
        p,j=self.population,self.job;q=j.pricing
        if (self.actor_id in {p.issuer_actor,p.reviewer_actor}
                or j.workspace_id!=p.workspace_id or j.raw_ref not in p.raw_refs
                or j.population_id!=p.population_id or j.operation_registry_hash!=p.operation_registry_hash
                or q.original_root_hash!=p.original_root_hash or q.original_allocation_hash!=self.original_allocation_hash
                or q.original_horizon!=self.original_horizon or q.population_id!=p.population_id
                or self.pricing_quote_hash!=digest(q.model_dump(mode='json'))
                or self.vision_token_policy_hash!=q.vision_token_policy_sha256
                or not q.valid_from<self.phase_expires_at<=min(p.expires_at,q.expires_at,self.original_horizon)):
            raise ValueError('complete exact independently appointed raw phase context required')
        return self
