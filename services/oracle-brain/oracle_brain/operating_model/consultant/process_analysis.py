"""Sealed documentary/measurement report contract, never normative policy."""
from typing import Literal
from pydantic import Field, field_validator
from ..contracts import canonical_bytes
from ..source_receipts import _StrictModel

class SupportedClause(_StrictModel):
    text:str=Field(min_length=1)
    citation_ids:tuple[str,...]=Field(min_length=1)

class Experiment(_StrictModel):
    hypothesis:str=Field(min_length=1)
    measurement:str=Field(min_length=1)
    uncertainty:str=Field(min_length=1)

class Report(_StrictModel):
    schema_version:Literal[1]=1
    variant:Literal['documentary','measured']
    state:Literal['ready','limited','failed']
    model_artifact_hash:str=Field(pattern=r'^[0-9a-f]{64}$')
    event_artifact_hash:str|None=None
    clauses:tuple[SupportedClause,...]
    finding_ids:tuple[str,...]
    measurements:dict|None=None
    experiments:tuple[Experiment,...]=()
    established_policy:Literal[False]=False
    actual_data_acceptance:Literal['unavailable','synthetic','accepted']
    limitations:tuple[str,...]=()


class ReportV2(Report):
    """Explicit recommendation-bearing report under the existing report kind."""
    schema_version:Literal[2]=2
    recommendations:tuple[dict,...]=Field(min_length=1,max_length=16)

    @field_validator('schema_version',mode='before')
    @classmethod
    def _exact_version(cls,value):
        if type(value) is not int or value!=2:
            raise ValueError('exact report schema version two required')
        return value

    @field_validator('recommendations')
    @classmethod
    def _recommendations(cls, value):
        from .recommendations import recommendation_from_payload
        ids=[]
        for payload in value:
            recommendation=recommendation_from_payload(payload)
            ids.append(recommendation.recommendation_id)
        if len(ids)!=len(set(ids)):
            raise ValueError('duplicate recommendation identity')
        return value


def parse_report(payload:dict, *, expected_schema_version:int|None=None):
    """Explicit supported version dispatch. V1 remains unchanged."""
    import json
    if type(payload) is not dict:
        raise ValueError('report payload must be an object')
    if expected_schema_version is not None and (type(expected_schema_version) is not int
            or expected_schema_version not in (1,2)):
        raise ValueError('unsupported expected report schema version')
    version=payload.get('schema_version',1)
    if type(version) is not int or version not in (1,2):
        raise ValueError('unsupported report schema version')
    if expected_schema_version is not None and version!=expected_schema_version:
        raise ValueError('writer changed expected report schema version')
    try:
        if version==2 and len(canonical_bytes(payload))>128*1024:
            raise ValueError('bounded recommendation report size exceeded')
        wire=json.dumps(payload,allow_nan=False)
    except (TypeError,ValueError) as error:
        raise ValueError('invalid or unbounded report JSON wire') from error
    return (Report if version==1 else ReportV2).model_validate_json(wire)
