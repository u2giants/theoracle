"""Byte-only paid phase lineage. Records never authorize their own consumption."""
from typing import Literal
from uuid import UUID
from pydantic import Field,AwareDatetime,field_validator,model_validator
from .contracts import StrictRecord
from .original_qualification_v1 import RawOriginalRefV1
HASH=r'^[0-9a-f]{64}$'

class RawOriginalPaidResponseCommitV1(StrictRecord):
    schema_version:Literal[1]=1
    record_schema:Literal['raw-original-paid-response-v1']='raw-original-paid-response-v1'
    transport:Literal['paid-native-v1']='paid-native-v1'
    purpose:Literal['source-original-reading','source-original-review']
    dispatch_id:UUID
    raw_ref:RawOriginalRefV1
    native_job_hash:str=Field(pattern=HASH)
    context_hash:str=Field(pattern=HASH)
    request_hash:str=Field(pattern=HASH)
    permission_hash:str=Field(pattern=HASH)
    population_id:UUID
    operation_registry_hash:str=Field(pattern=HASH)
    original_root_hash:str=Field(pattern=HASH)
    population_digest:str=Field(pattern=HASH)
    source_registry_hash:str=Field(pattern=HASH)
    allocation_hash:str=Field(pattern=HASH)
    view_manifest_hash:str=Field(pattern=HASH)
    locator_map_hash:str=Field(pattern=HASH)
    pricing_quote_hash:str=Field(pattern=HASH)
    reservation_id:UUID
    native_custody_receipt_hash:str=Field(pattern=HASH)
    raw_wire_hash:str=Field(pattern=HASH)
    model_content_hash:str=Field(pattern=HASH)
    model_id:Literal['openai/gpt-6.1-sol','openai/gpt-6-astra']
    current_sql_receipt_hash:str=Field(pattern=HASH)
    observer_witness_hash:str=Field(pattern=HASH)
    native_failed:Literal[False]
    wire_complete:Literal[True]
    committed_at:AwareDatetime
    original_horizon:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact raw paid response version required')
        return v

    @field_validator('native_failed','wire_complete',mode='before')
    @classmethod
    def actual_bool(cls,v):
        if type(v) is not bool:raise ValueError('actual native wire status required')
        return v

    @model_validator(mode='after')
    def paid_pdf_original_window(self):
        if self.raw_ref.media_type!='application/pdf' or self.committed_at>=self.original_horizon:
            raise ValueError('complete actual PDF paid response within original horizon required')
        return self
