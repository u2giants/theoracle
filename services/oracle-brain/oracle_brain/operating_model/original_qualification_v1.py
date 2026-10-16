"""Byte-only original contracts; no source receipt, grant or issuer is minted.

Reading-byte hashes and canonical provider-body hashes are deliberately distinct.
Only protected consumers and actual SQL role appointments can qualify a source.
"""
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,model_validator
from .contracts import StrictRecord,digest

HASH=r'^[0-9a-f]{64}$'

class RawOriginalRefV1(StrictRecord):
    schema_version:Literal[1]=1
    workspace_id:UUID
    source_id:UUID
    revision:int=Field(strict=True,ge=1)
    original_sha256:str=Field(pattern=HASH)
    byte_count:int=Field(strict=True,ge=1,le=25*1024*1024)
    media_type:Literal['application/pdf','text/plain']
    filename:str=Field(min_length=1,max_length=255)
    custody_locator_seal_sha256:str=Field(pattern=HASH)

    @model_validator(mode='after')
    def display_name_only(self):
        if any(ord(c)<32 or c in '/\\' for c in self.filename):
            raise ValueError('original filename is a display name, never a locator')
        return self

class RawOriginalPopulationV1(StrictRecord):
    """Externally pinned COMPLETE raw phase population; fields confer no scope."""
    schema_version:Literal[1]=1
    purpose:Literal['raw-original-population-v1']='raw-original-population-v1'
    population_id:UUID
    workspace_id:UUID
    original_root_hash:str=Field(pattern=HASH)
    operation_registry_hash:str=Field(pattern=HASH)
    runtime_hash:str=Field(pattern=HASH)
    source_registry_hash:str=Field(pattern=HASH)
    raw_refs:tuple[RawOriginalRefV1,...]=Field(min_length=1,max_length=4096)
    population_digest:str=Field(pattern=HASH)
    issuer_actor:UUID
    reviewer_actor:UUID
    expires_at:AwareDatetime

    @model_validator(mode='after')
    def complete_raw_population(self):
        if (self.issuer_actor==self.reviewer_actor
                or len({r.source_id for r in self.raw_refs})!=len(self.raw_refs)
                or any(r.workspace_id!=self.workspace_id for r in self.raw_refs)
                or self.population_digest!=digest({'raw_refs':[r.model_dump(mode='json') for r in self.raw_refs]})):
            raise ValueError('complete independently pinned ordered raw population required')
        return self


class OriginalResponseCommitBaseV1(StrictRecord):
    schema_version:Literal[1]=1
    raw_ref:RawOriginalRefV1
    population_id:UUID
    operation_registry_hash:str=Field(pattern=HASH)
    original_root_hash:str=Field(pattern=HASH)
    allocation_hash:str=Field(pattern=HASH)
    population_hash:str=Field(pattern=HASH)
    source_registry_hash:str=Field(pattern=HASH)
    context_hash:str=Field(pattern=HASH)
    view_manifest_hash:str=Field(pattern=HASH)
    locator_map_hash:str=Field(pattern=HASH)
    reading_sha256:str=Field(pattern=HASH)
    parser_id:str=Field(pattern=HASH)
    committed_at:AwareDatetime
    original_horizon:AwareDatetime

    @model_validator(mode='after')
    def finite_original_window(self):
        if self.committed_at>=self.original_horizon:
            raise ValueError('response commitment cannot extend original horizon')
        return self

class PaidOriginalResponseCommitBaseV1(OriginalResponseCommitBaseV1):
    transport:Literal['paid-native-v1']='paid-native-v1'
    native_dispatch_id:UUID
    native_job_hash:str=Field(pattern=HASH)
    request_hash:str=Field(pattern=HASH)
    raw_wire_hash:str=Field(pattern=HASH)
    model_content_hash:str=Field(pattern=HASH)
    native_custody_receipt_hash:str=Field(pattern=HASH)
    authorized_phase_commit_hash:str=Field(pattern=HASH)

    @model_validator(mode='after')
    def paid_pdf_only(self):
        if self.raw_ref.media_type!='application/pdf':
            raise ValueError('paid original qualification is fixed to PDF')
        return self

class OriginalReadingCommitV1(PaidOriginalResponseCommitBaseV1):
    purpose:Literal['observed-authorized-original-reading-response-v1']='observed-authorized-original-reading-response-v1'
    reading_body_hash:str=Field(pattern=HASH)

class OriginalReviewCommitV1(PaidOriginalResponseCommitBaseV1):
    purpose:Literal['observed-authorized-original-review-response-v1']='observed-authorized-original-review-response-v1'
    reading_commit_hash:str=Field(pattern=HASH)
    reading_population_id:UUID
    reading_operation_registry_hash:str=Field(pattern=HASH)
    reading_body_hash:str=Field(pattern=HASH)
    review_body_hash:str=Field(pattern=HASH)
    qualification_pass:Literal[True]

class NativeUTF8ResponseCommitBaseV1(OriginalResponseCommitBaseV1):
    transport:Literal['native-utf8-byte-roundtrip-v1']='native-utf8-byte-roundtrip-v1'

    @model_validator(mode='after')
    def exact_native_reading(self):
        if self.raw_ref.media_type!='text/plain' or self.reading_sha256!=self.raw_ref.original_sha256:
            raise ValueError('native UTF8 must preserve exact original reading bytes')
        return self

class NativeUTF8ReadingCommitV1(NativeUTF8ResponseCommitBaseV1):
    purpose:Literal['observed-authorized-original-reading-response-v1']='observed-authorized-original-reading-response-v1'
    reading_body_hash:str=Field(pattern=HASH)

class NativeUTF8ReviewCommitV1(NativeUTF8ResponseCommitBaseV1):
    purpose:Literal['observed-authorized-original-review-response-v1']='observed-authorized-original-review-response-v1'
    reading_commit_hash:str=Field(pattern=HASH)
    reading_population_id:UUID
    reading_operation_registry_hash:str=Field(pattern=HASH)
    reading_body_hash:str=Field(pattern=HASH)
    review_body_hash:str=Field(pattern=HASH)
    qualification_pass:Literal[True]


def parse_original_response_commit_v1(raw:bytes,*,phase:Literal['reading','review']):
    """Closed JSON transport union only; this parser grants no authority."""
    import json
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('duplicate original commitment field')
            result[k]=v
        return result
    value=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(value,dict):raise ValueError('original commitment must be object')
    models={('reading','paid-native-v1'):OriginalReadingCommitV1,
        ('review','paid-native-v1'):OriginalReviewCommitV1,
        ('reading','native-utf8-byte-roundtrip-v1'):NativeUTF8ReadingCommitV1,
        ('review','native-utf8-byte-roundtrip-v1'):NativeUTF8ReviewCommitV1}
    model=models.get((phase,value.get('transport')))
    if model is None:raise ValueError('fixed original phase/transport required')
    # Strict JSON UUID/datetime interpretation; no Python-dict coercion.
    return model.model_validate_json(raw)
