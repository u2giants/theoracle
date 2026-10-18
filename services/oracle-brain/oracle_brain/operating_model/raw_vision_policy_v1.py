"""Consumes an independently appointed model-specific conservative vision bound.

This record does not establish model capability or appoint its own issuer. The
protected startup must authenticate the exact policy hash and its external pins.
"""
from typing import Literal
from uuid import UUID
from pydantic import Field,AwareDatetime,field_validator,model_validator
from .contracts import StrictRecord,digest
from .raw_multimodal_pricing_v1 import RawMultimodalPricingQuoteV1

class RawVisionTokenPolicyV1(StrictRecord):
    schema_version:Literal[1]=1
    purpose:Literal['raw-original-vision-token-policy-v1']='raw-original-vision-token-policy-v1'
    model:Literal['openai/gpt-6.1-sol','openai/gpt-6-astra']
    provider_tag:Literal['openai']='openai'
    detail:Literal['high']='high'
    bound_rule:Literal['constant-per-complete-view-upper-bound-v1']='constant-per-complete-view-upper-bound-v1'
    max_width:int=Field(gt=0)
    max_height:int=Field(gt=0)
    max_images:int=Field(gt=0)
    max_image_bytes:int=Field(gt=0)
    max_total_image_bytes:int=Field(gt=0)
    tokens_per_complete_view_upper_bound:int=Field(gt=0)
    provider_evidence_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    issuer_actor:UUID
    reviewer_actor:UUID
    valid_from:AwareDatetime
    expires_at:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact vision policy version required')
        return v

    @model_validator(mode='after')
    def finite_independent_window(self):
        if self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at:
            raise ValueError('independently appointed finite vision policy required')
        return self


def verify_raw_vision_quote_v1(quote,policy,view_dimensions,*,expected_policy_sha256,now):
    """Pure complete-view arithmetic, never a source/account/provider grant."""
    if type(quote) is not RawMultimodalPricingQuoteV1 or type(policy) is not RawVisionTokenPolicyV1:
        raise PermissionError('exact raw quote and independently pinned vision policy required')
    quote=RawMultimodalPricingQuoteV1.model_validate(quote.model_dump())
    policy=RawVisionTokenPolicyV1.model_validate(policy.model_dump())
    if (digest(policy.model_dump(mode='json'))!=expected_policy_sha256
            or quote.vision_token_policy_sha256!=expected_policy_sha256 or policy.model!=quote.model
            or now.tzinfo is None or not policy.valid_from<=now<min(policy.expires_at,quote.expires_at)
            or type(view_dimensions) is not tuple or not view_dimensions):
        raise PermissionError('current complete model-specific vision policy required')
    for row in view_dimensions:
        if (type(row) is not tuple or len(row)!=3 or any(type(v) is not int or v<=0 for v in row)
                or row[0]>policy.max_width or row[1]>policy.max_height or row[2]>policy.max_image_bytes):
            raise PermissionError('actual view exceeds independently admitted native capability')
    total=sum(row[2] for row in view_dimensions)
    if (len(view_dimensions)!=quote.view_count or len(view_dimensions)>policy.max_images
            or total!=quote.total_image_bytes or total>policy.max_total_image_bytes
            or max(row[2] for row in view_dimensions)!=quote.largest_image_bytes
            or quote.model_max_images>policy.max_images or quote.model_max_image_bytes>policy.max_image_bytes
            or quote.vision_input_tokens_upper_bound<len(view_dimensions)*policy.tokens_per_complete_view_upper_bound):
        raise PermissionError('actual complete vision token/capability bound differs')
    return min(policy.expires_at,quote.expires_at,quote.original_horizon)
