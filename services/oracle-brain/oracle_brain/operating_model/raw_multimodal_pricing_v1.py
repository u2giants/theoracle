"""Raw-only price arithmetic. Quote records/hash arguments confer no authority."""
from decimal import Decimal,ROUND_CEILING
from typing import Literal
from uuid import UUID
from pydantic import AwareDatetime,Field,field_validator,model_validator
from .provider_adapter import Pricing
from .contracts import digest
HASH=r'^[a-f0-9]{64}$'

class RawMultimodalPricingQuoteV1(Pricing):
    schema_version:Literal[1]=1
    quote_purpose:Literal['raw-original-multimodal-pricing-v1']='raw-original-multimodal-pricing-v1'
    provider:Literal['openrouter']='openrouter'
    model:Literal['openai/gpt-6.1-sol','openai/gpt-6-astra']
    account:str=Field(min_length=1,max_length=200)
    endpoint:Literal['https://openrouter.ai/api/v1']='https://openrouter.ai/api/v1'
    terms_hash:str=Field(pattern=HASH)
    key_fingerprint:str=Field(pattern=HASH)
    ledger_registry_hash:str=Field(pattern=HASH)
    catalogue_sha256:str=Field(pattern=HASH)
    pricing_policy_sha256:str=Field(pattern=HASH)
    vision_token_policy_sha256:str=Field(pattern=HASH)
    model_capability_sha256:str=Field(pattern=HASH)
    dispatch_id:UUID
    request_hash:str=Field(pattern=HASH)
    view_manifest_hash:str=Field(pattern=HASH)
    population_id:UUID
    original_root_hash:str=Field(pattern=HASH)
    original_allocation_hash:str=Field(pattern=HASH)
    original_horizon:AwareDatetime
    view_count:int=Field(gt=0)
    total_image_bytes:int=Field(gt=0,le=25*1024*1024)
    largest_image_bytes:int=Field(gt=0,le=25*1024*1024)
    model_max_images:int=Field(gt=0)
    model_max_image_bytes:int=Field(gt=0)
    model_context_tokens:int=Field(gt=0)
    text_input_tokens_upper_bound:int=Field(gt=0)
    vision_input_tokens_upper_bound:int=Field(gt=0)
    input_per_million_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    input_cache_write_per_million_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    output_per_million_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    per_image_fee_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    per_request_fee_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    is_byok:bool
    upstream_input_per_million_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    upstream_output_per_million_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    upstream_per_image_fee_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    upstream_per_request_fee_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    valid_from:AwareDatetime
    issuer_actor:UUID
    reviewer_actor:UUID

    @field_validator('schema_version',mode='before')
    @classmethod
    def exact_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact raw quote version required')
        return v

    @model_validator(mode='after')
    def complete_current_capacity(self):
        if (self.issuer_actor==self.reviewer_actor or not self.valid_from<self.expires_at<=self.original_horizon
                or self.view_count>self.model_max_images or self.largest_image_bytes>self.model_max_image_bytes
                or self.largest_image_bytes>self.total_image_bytes
                or self.total_image_bytes>self.view_count*self.largest_image_bytes
                or not 1<=self.max_output_tokens<=8192
                or self.text_input_tokens_upper_bound+self.vision_input_tokens_upper_bound+self.max_output_tokens>self.model_context_tokens):
            raise ValueError('complete finite model-specific raw capability required')
        if not self.is_byok and any(getattr(self,n)!=0 for n in ('upstream_input_per_million_usd',
                'upstream_output_per_million_usd','upstream_per_image_fee_usd','upstream_per_request_fee_usd')):
            raise ValueError('non-BYOK quote cannot invent upstream charges')
        return self


def raw_multimodal_reservation_maximum_v1(quote,*,expected_quote_sha256,input_tokens_upper_bound,purpose,now):
    """Pure cost bound; trusted native startup must authenticate ALL quote pins.

    Same Budget.reserve(maximum,pricing_hash) consumes this bound. This function
    performs no IO, account admission, model-capability issuance or reservation.
    """
    if type(quote) is not RawMultimodalPricingQuoteV1:
        raise PermissionError('exact independently admitted raw quote required')
    quote=RawMultimodalPricingQuoteV1.model_validate(quote.model_dump(mode='python'))
    if (digest(quote.model_dump(mode='json'))!=expected_quote_sha256
            or type(input_tokens_upper_bound) is not int
            or input_tokens_upper_bound!=quote.text_input_tokens_upper_bound+quote.vision_input_tokens_upper_bound
            or purpose not in {'source-original-reading','source-original-review'}
            or now.tzinfo is None or not quote.valid_from<=now<quote.expires_at):
        raise PermissionError('current exact raw cost/context quote required')
    input_rate=max(quote.input_per_million_usd,quote.input_cache_write_per_million_usd)+quote.upstream_input_per_million_usd
    output_rate=quote.output_per_million_usd+quote.upstream_output_per_million_usd
    maximum=(Decimal(input_tokens_upper_bound)*input_rate/Decimal(1_000_000)
        +Decimal(quote.max_output_tokens)*output_rate/Decimal(1_000_000)
        +Decimal(quote.view_count)*(quote.per_image_fee_usd+quote.upstream_per_image_fee_usd)
        +quote.per_request_fee_usd+quote.upstream_per_request_fee_usd)
    if maximum<=0:raise PermissionError('positive conservative raw reservation required')
    return maximum.quantize(Decimal('0.000001'),rounding=ROUND_CEILING)
