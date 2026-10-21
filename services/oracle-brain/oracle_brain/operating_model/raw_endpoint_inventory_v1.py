"""Versioned raw-only safety projection of official OpenRouter metadata.

Pure parsing, not endpoint admission. Full input hashes stay separate from the
canonical safety inventory; no provider request or credential exists here.
Primary schema: https://openrouter.ai/docs/api/api-reference/endpoints/list-all-endpoints-for-a-model
and https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties
"""
from dataclasses import dataclass
from datetime import datetime,timedelta
from typing import Literal
from pydantic import AwareDatetime,Field,field_validator,model_validator
from .contracts import StrictRecord
from .raw_multimodal_pricing_v1 import RawMultimodalPricingQuoteV1
from decimal import Decimal
import hashlib
from .contracts import canonical_bytes,digest

_MODELS=frozenset({'openai/gpt-6.1-sol','openai/gpt-6-astra'})
_MODEL_KEYS=frozenset({'id','canonical_slug','created','name','description','architecture','context_length',
    'pricing','top_provider','per_request_limits','supported_parameters','default_parameters','expiration_date',
    'knowledge_cutoff','links','supported_voices','hugging_face_id'})
_ARCH_KEYS=frozenset({'input_modalities','output_modalities','instruct_type','modality','tokenizer'})
_TOP_KEYS=frozenset({'context_length','max_completion_tokens','is_moderated'})
_DATA_KEYS=frozenset({'id','name','description','created','architecture','endpoints'})
_ENDPOINT_KEYS=frozenset({'name','model_name','model_id','provider_name','tag','status','context_length',
    'max_prompt_tokens','max_completion_tokens','pricing','quantization','supported_parameters',
    'supports_diarization','supports_implicit_caching','latency_last_30m','throughput_last_30m',
    'uptime_last_1d','uptime_last_30m','uptime_last_5m'})
_EXCLUDED_MODEL=frozenset({'name','description'})
_EXCLUDED_ENDPOINT=frozenset({'name','model_name','latency_last_30m','throughput_last_30m',
    'uptime_last_1d','uptime_last_30m','uptime_last_5m'})
_PRICES=frozenset({'prompt','completion','image','request','input_cache_write','input_cache_read'})
_CONDITIONS=frozenset({'min_prompt_tokens','utc_start','utc_end','utc_days'})
_WEEKDAYS=frozenset({'monday','tuesday','wednesday','thursday','friday','saturday','sunday'})


def _require(ok):
    if not ok:raise PermissionError('unproven raw endpoint safety/pricing inventory')


def _object(value,allowed):
    _require(type(value) is dict and set(value)<=allowed)


def _pricing(value,*,required=True):
    _object(value,_PRICES|{'overrides'})
    if required:_require({'prompt','completion','image','request','input_cache_write'}<=set(value))
    for key,amount in value.items():
        if key=='overrides':continue
        _require(type(amount) is str)
        try:n=Decimal(amount)
        except Exception:raise PermissionError('unproven raw endpoint safety/pricing inventory') from None
        _require(n.is_finite() and n>=0)
    overrides=value.get('overrides',[]);_require(type(overrides) is list)
    for row in overrides:
        _object(row,_PRICES|_CONDITIONS)
        _pricing({k:v for k,v in row.items() if k in _PRICES},required=False)
        # Official flat API schema + provider integration time-window contract:
        # https://github.com/OpenRouterTeam/terraform-provider-openrouter/blob/main/docs/data-sources/model.md
        # https://openrouter.ai/docs/guides/providers/integration#time-of-day-pricing
        if 'min_prompt_tokens' in row:
            _require(type(row['min_prompt_tokens']) is int and row['min_prompt_tokens']>=0)
        _require(('utc_start' in row)==('utc_end' in row))
        if 'utc_start' in row:
            for key in ('utc_start','utc_end'):
                time=row[key]
                _require(type(time) is int and 0<=time<=2359 and time%100<60)
            _require(row['utc_start']!=row['utc_end'])
        if 'utc_days' in row:
            days=row['utc_days']
            _require(type(days) is list and bool(days) and all(type(day) is str and day in _WEEKDAYS for day in days)
                and len(set(days))==len(days))



@dataclass(frozen=True)
class RawEndpointSafetyInventoryV1:
    canonical_inventory:bytes
    catalogue_sha256:str
    model_capability_sha256:str
    models_wire_sha256:str
    endpoints_wire_sha256:str


def raw_endpoint_safety_inventory_v1(models_wire,endpoints_wire,*,model):
    import json
    def decode(raw):
        _require(type(raw) is bytes and len(raw)<=16*1024*1024)
        def unique(pairs):
            d={}
            for k,v in pairs:
                _require(k not in d);d[k]=v
            return d
        try:return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        except (ValueError,TypeError,RecursionError):raise PermissionError('unproven raw endpoint safety/pricing inventory') from None
    _require(type(model) is str and model in _MODELS)
    models=decode(models_wire);endpoints=decode(endpoints_wire)
    _object(models,{'data'});_require(type(models.get('data')) is list)
    selected=[m for m in models['data'] if type(m) is dict and m.get('id')==model];_require(len(selected)==1)
    m=selected[0];_object(m,_MODEL_KEYS)
    _object(m.get('architecture'),_ARCH_KEYS);_object(m.get('top_provider'),_TOP_KEYS)
    modes=m['architecture'].get('input_modalities')
    _require(type(modes) is list and all(type(x) is str for x in modes) and {'text','image'}<=set(modes))
    for k in ('context_length','max_completion_tokens'):_require(type(m['top_provider'].get(k)) is int and m['top_provider'][k]>0)
    _require(type(m.get('supported_parameters')) is list and all(type(x) is str for x in m['supported_parameters']))
    _require(type(m.get('context_length')) is int and m['context_length']>0)
    _pricing(m.get('pricing'))
    _object(endpoints,{'data'});d=endpoints.get('data');_object(d,_DATA_KEYS)
    _require(d.get('id')==model and d.get('architecture')==m['architecture'] and type(d.get('endpoints')) is list)
    chosen=[]
    for e in d['endpoints']:
        _require(type(e) is dict and type(e.get('provider_name')) is str)
        if e['provider_name']!='OpenAI':continue
        _object(e,_ENDPOINT_KEYS)
        _require(e.get('model_id')==model and e.get('tag')=='openai' and type(e.get('status')) is int and e['status']==0)
        for k in ('context_length','max_prompt_tokens','max_completion_tokens'):_require(type(e.get(k)) is int and e[k]>0)
        _require(type(e.get('supported_parameters')) is list and all(type(x) is str for x in e['supported_parameters']))
        _pricing(e.get('pricing'))
        chosen.append({k:v for k,v in e.items() if k not in _EXCLUDED_ENDPOINT})
    _require(bool(chosen));chosen.sort(key=canonical_bytes)  # Duplicate records remain present.
    kept={k:v for k,v in m.items() if k not in _EXCLUDED_MODEL}
    inventory={'schema_version':1,'purpose':'raw-openrouter-endpoint-safety-inventory-v1',
        'model':kept,'provider_endpoints':chosen}
    capability={'schema_version':1,'purpose':'raw-openrouter-endpoint-capability-v1',
        'model_id':model,'architecture':m['architecture'],'context_length':m['context_length'],
        'top_provider':m['top_provider'],'supported_parameters':m.get('supported_parameters'),
        'provider_endpoints':[{k:v for k,v in e.items() if k!='pricing'} for e in chosen]}
    body=canonical_bytes(inventory)
    return RawEndpointSafetyInventoryV1(body,hashlib.sha256(body).hexdigest(),digest(capability),
        hashlib.sha256(models_wire).hexdigest(),hashlib.sha256(endpoints_wire).hexdigest())


# Owner-selected schema1 raw-worst-case-v1, not a pricing/route appointment.
# Prices use official USD/token, USD/input-image and USD/request units:
# https://github.com/OpenRouterTeam/terraform-provider-openrouter/blob/main/docs/data-sources/model.md
# image_token is deliberately unsupported; it is NOT USD/input-image.
# Every known override contributes to the bound, regardless of its condition.
def raw_worst_case_policy_v1():
    return canonical_bytes({'schema_version':1,'purpose':'raw-worst-case-v1',
        'provider_selection':'all-eligible-openai-endpoints',
        'price_rule':'maximum-of-every-endpoint-base-and-known-override',
        'capacity_rule':'minimum-model-top-provider-and-all-endpoints',
        'required_parameters':['max_tokens','response_format'],
        'required_input_modalities':['text','image'],'required_output_modalities':['text'],
        'units':{'prompt':'USD/token','input_cache_write':'USD/token','completion':'USD/token',
            'image':'USD/input-image','request':'USD/request'},
        'quote_token_rate_unit':'USD/million-tokens','token_rate_multiplier':1000000,
        'cache_read_rule':'refuse-above-global-prompt-or-cache-write-maximum',
        'override_conditions':['min_prompt_tokens','utc_start','utc_end','utc_days'],
        'time_rule':'paired-distinct-integer-HHMM-0000-2359-minute-00-59',
        'weekdays':sorted(_WEEKDAYS),'condition_discounts':False,
        'unsupported_fees':'refuse-including-image_token','billing_evidence':'external-exact-pin-required',
        'metadata_max_age_seconds':120})


def raw_worst_case_policy_hash_v1():
    return hashlib.sha256(raw_worst_case_policy_v1()).hexdigest()



_HASH=r'^[0-9a-f]{64}$'


class RawBillingBoundsV1(StrictRecord):
    """Descriptive bounds only; external expected hash does not authenticate IO.

    A protected existing appointment must authenticate this record before an
    operational consumer may use it. This pure module issues no appointment.
    Every upstream dimension is required, even explicit zero on shared-only.
    """
    purpose:Literal['raw-billing-bounds-v1']='raw-billing-bounds-v1'
    model:Literal['openai/gpt-6.1-sol','openai/gpt-6-astra']
    route:Literal['shared-only','byok']
    account:str=Field(min_length=1,max_length=200)
    key_fingerprint:str=Field(pattern=_HASH)
    ledger_registry_hash:str=Field(pattern=_HASH)
    terms_hash:str=Field(pattern=_HASH)
    provider_evidence_sha256:str=Field(pattern=_HASH)
    upstream_input_per_million_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    upstream_output_per_million_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    upstream_per_image_fee_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    upstream_per_request_fee_usd:Decimal=Field(ge=0,allow_inf_nan=False)
    valid_from:AwareDatetime
    expires_at:AwareDatetime

    @field_validator('schema_version',mode='before')
    @classmethod
    def integer_version(cls,v):
        if type(v) is not int or v!=1:raise ValueError('exact billing bounds version required')
        return v

    @model_validator(mode='after')
    def explicit_bounded_route(self):
        if (not self.valid_from<self.expires_at or self.account!='key-sha256:'+self.key_fingerprint
                or (self.route=='shared-only' and any(getattr(self,key)!=0 for key in
                    ('upstream_input_per_million_usd','upstream_output_per_million_usd',
                     'upstream_per_image_fee_usd','upstream_per_request_fee_usd')))):
            raise ValueError('explicit finite exact-key billing bounds required')
        return self


def _per_million_exact(value):
    # Decimal multiplication under a short caller context could round DOWN.
    # Changing the decimal exponent converts USD/token exactly, at any precision.
    parts=value.as_tuple()
    return Decimal((parts.sign,parts.digits,parts.exponent+6))


def compare_raw_endpoint_quote_v1(models_wire,endpoints_wire,*,quote,expected_quote_sha256,
        billing_bounds,expected_billing_evidence_sha256,current_account,current_key_fingerprint,
        current_ledger_registry_hash,current_terms_hash,current_register_hash,
        models_observed_at,endpoints_observed_at,now):
    """Pure strict comparison only; NO source, route, spend or dispatch authority.

    Observed times/bytes must later come from the protected actual metadata
    transport and billing bounds from its existing independently appointed owner.
    A caller-constructed DTO or matching caller-chosen digest proves neither.
    """
    import re,json
    try:
        _require(type(quote) is RawMultimodalPricingQuoteV1 and type(billing_bounds) is RawBillingBoundsV1)
        q=RawMultimodalPricingQuoteV1.model_validate_json(quote.model_dump_json())
        b=RawBillingBoundsV1.model_validate_json(billing_bounds.model_dump_json())
        for pin in (expected_quote_sha256,expected_billing_evidence_sha256,current_key_fingerprint,
                current_ledger_registry_hash,current_terms_hash,current_register_hash):
            _require(type(pin) is str and re.fullmatch(_HASH,pin) is not None)
        _require(type(current_account) is str and current_account=='key-sha256:'+current_key_fingerprint)
        _require(digest(q.model_dump(mode='json'))==expected_quote_sha256
            and digest(b.model_dump(mode='json'))==expected_billing_evidence_sha256
            and q.pricing_policy_sha256==raw_worst_case_policy_hash_v1())
        for value in (now,models_observed_at,endpoints_observed_at):
            _require(type(value) is datetime and value.tzinfo is not None and value.utcoffset() is not None)
        _require(q.valid_from<=now<q.expires_at<=b.expires_at and b.valid_from<=now)
        for observed in (models_observed_at,endpoints_observed_at):
            _require(q.valid_from<=observed<=now and timedelta(0)<=now-observed<=timedelta(seconds=120))
        expected=(current_account,current_key_fingerprint,current_ledger_registry_hash,current_terms_hash)
        _require((q.account,q.key_fingerprint,q.ledger_registry_hash,q.terms_hash)==expected
            and (b.account,b.key_fingerprint,b.ledger_registry_hash,b.terms_hash)==expected
            and q.admitted_register_hash==current_register_hash and b.model==q.model
            and q.is_byok==(b.route=='byok'))
        for key in ('upstream_input_per_million_usd','upstream_output_per_million_usd',
                'upstream_per_image_fee_usd','upstream_per_request_fee_usd'):
            _require(getattr(q,key)==getattr(b,key))
        inventory=raw_endpoint_safety_inventory_v1(models_wire,endpoints_wire,model=q.model)
        _require(q.catalogue_sha256==inventory.catalogue_sha256
            and q.model_capability_sha256==inventory.model_capability_sha256)
        data=json.loads(inventory.canonical_inventory);m=data['model'];endpoints=data['provider_endpoints']
        outputs=m['architecture'].get('output_modalities')
        _require(type(outputs) is list and outputs==['text'])
        for item in (m,*endpoints):
            params=item['supported_parameters']
            _require({'max_tokens','response_format'}<=set(params))
        context=min(m['context_length'],m['top_provider']['context_length'],*(e['context_length'] for e in endpoints))
        prompt=min(e['max_prompt_tokens'] for e in endpoints)
        completion=min(m['top_provider']['max_completion_tokens'],*(e['max_completion_tokens'] for e in endpoints))
        limits=m.get('per_request_limits')
        if limits is not None:
            _object(limits,{'prompt_tokens','completion_tokens'})
            for key,value in limits.items():
                _require(type(value) is int and value>0)
                if key=='prompt_tokens':prompt=min(prompt,value)
                else:completion=min(completion,value)
        total_input=q.text_input_tokens_upper_bound+q.vision_input_tokens_upper_bound
        _require(q.model_context_tokens==context and total_input+q.max_output_tokens<=context
            and total_input<=prompt and q.max_output_tokens<=completion)
        prices=[]
        for endpoint in endpoints:
            price=endpoint['pricing'];prices.append(price);prices.extend(price.get('overrides',[]))
        maxima={key:max(Decimal(p[key]) for p in prices if key in p)
            for key in ('prompt','input_cache_write','completion','image','request')}
        cache_ceiling=max(maxima['prompt'],maxima['input_cache_write'])
        _require(all(Decimal(price['input_cache_read'])<=cache_ceiling for price in prices
            if 'input_cache_read' in price))
        _require(q.input_per_million_usd==_per_million_exact(maxima['prompt'])
            and q.input_cache_write_per_million_usd==_per_million_exact(maxima['input_cache_write'])
            and q.output_per_million_usd==_per_million_exact(maxima['completion'])
            and q.per_image_fee_usd==maxima['image'] and q.per_request_fee_usd==maxima['request'])
        return canonical_bytes({'schema_version':1,'purpose':'raw-endpoint-quote-comparison-v1',
            'comparison_only':True,'dispatch_authorized':False,'billing_route_authenticated':False,
            'quote_sha256':expected_quote_sha256,'billing_evidence_sha256':expected_billing_evidence_sha256,
            'pricing_policy_sha256':q.pricing_policy_sha256,'catalogue_sha256':inventory.catalogue_sha256,
            'model_capability_sha256':inventory.model_capability_sha256,
            'models_wire_sha256':inventory.models_wire_sha256,'endpoints_wire_sha256':inventory.endpoints_wire_sha256})
    except (ValueError,TypeError,KeyError,ArithmeticError):
        raise PermissionError('unproven raw endpoint quote/billing comparison') from None
