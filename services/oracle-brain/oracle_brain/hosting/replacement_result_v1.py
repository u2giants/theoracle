"""Fixed protected-result wire. Records are selectors, never serving authority."""
from datetime import datetime,timedelta
from typing import Literal
from uuid import UUID
import json
from pydantic import AwareDatetime,Field,field_validator,model_validator
from oracle_brain.operating_model.contracts import StrictRecord,canonical_bytes
from .replacement_public_view_v1 import ReplacementSnapshotV1

PROTOCOL='replacement-protected-result-v1'
HASH=r'^[a-f0-9]{64}$'
MAX_RESULT_BYTES=2*1024*1024

class _ResultWireV1(StrictRecord):
    schema_version:Literal[1]
    protocol:Literal['replacement-protected-result-v1']

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,value):
        if type(value) is not int or value!=1:raise ValueError('exact result wire version required')
        return value

class ProtectedReplacementResultRequestV1(_ResultWireV1):
    journey_id:UUID
    expected_journey_revision:int=Field(ge=1,le=9007199254740991)
    model_id:UUID
    model_version:int=Field(ge=1,le=9007199254740991)
    content_hash:str=Field(pattern=HASH)
    projection_digest:str=Field(pattern=HASH)
    ack_event_id:UUID
    summary_artifact_id:UUID
    summary_version:int=Field(ge=1,le=9007199254740991)
    summary_content_hash:str=Field(pattern=HASH)
    nonce:str=Field(pattern=HASH)
    expires_at:AwareDatetime

class ProtectedReplacementResultResponseV1(_ResultWireV1):
    nonce:str=Field(pattern=HASH)
    request_sha256:str=Field(pattern=HASH)
    checked_at:AwareDatetime
    expires_at:AwareDatetime
    snapshot:ReplacementSnapshotV1

    @model_validator(mode='after')
    def bounded_window(self):
        if not self.checked_at<self.expires_at<=self.checked_at+timedelta(seconds=30):
            raise ValueError('bounded original result window required')
        return self

def _unique_object(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate result field')
        value[key]=item
    return value

def parse_result_request_v1(raw:bytes,*,now:datetime)->ProtectedReplacementResultRequestV1:
    """Strict canonical request, no key/role/path selection or clock renewal."""
    if type(raw) is not bytes or not 0<len(raw)<=8192 or now.tzinfo is None:
        raise PermissionError('bounded canonical result request required')
    try:
        body=json.loads(raw,object_pairs_hook=_unique_object,
            parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite result field')))
        if type(body) is not dict or canonical_bytes(body)!=raw:
            raise ValueError('canonical result object required')
        request=ProtectedReplacementResultRequestV1.model_validate_json(raw)
        if not now<request.expires_at<=now+timedelta(seconds=30):
            raise ValueError('original result deadline expired or excessive')
        return request
    except (ValueError,UnicodeError,RecursionError,TypeError):
        raise PermissionError('invalid protected result request') from None

def encode_result_response_v1(response:ProtectedReplacementResultResponseV1)->bytes:
    if type(response) is not ProtectedReplacementResultResponseV1:
        raise PermissionError('actual strict result response required')
    # Revalidate frozen model_copy/model_construct input instead of treating type as authority.
    checked=ProtectedReplacementResultResponseV1.model_validate_json(
        canonical_bytes(response.model_dump(mode='json')))
    raw=canonical_bytes(checked.model_dump(mode='json'))
    if len(raw)>MAX_RESULT_BYTES:raise PermissionError('bounded public result required')
    return raw
