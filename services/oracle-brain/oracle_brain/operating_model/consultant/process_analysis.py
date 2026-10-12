"""Sealed documentary/measurement report contract, never normative policy."""
from typing import Literal
from pydantic import Field
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
