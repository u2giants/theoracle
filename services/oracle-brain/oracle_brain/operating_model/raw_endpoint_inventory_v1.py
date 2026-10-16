"""Versioned raw-only safety projection of official OpenRouter metadata.

Pure parsing, not endpoint admission. Full input hashes stay separate from the
canonical safety inventory; no provider request or credential exists here.
Primary schema: https://openrouter.ai/docs/api/api-reference/endpoints/list-all-endpoints-for-a-model
and https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties
"""
from dataclasses import dataclass
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
_CONDITIONS=frozenset({'min_prompt_tokens','max_prompt_tokens','utc_start','utc_end','utc_days'})


def _require(ok):
    if not ok:raise PermissionError('unproven raw endpoint safety/pricing inventory')


def _object(value,allowed):
    _require(type(value) is dict and set(value)<=allowed)


def _pricing(value):
    _object(value,_PRICES|{'overrides'})
    for key,amount in value.items():
        if key=='overrides':continue
        _require(type(amount) is str)
        try:n=Decimal(amount)
        except Exception:raise PermissionError('unproven raw endpoint safety/pricing inventory') from None
        _require(n.is_finite() and n>=0)
    overrides=value.get('overrides',[]);_require(type(overrides) is list)
    for row in overrides:
        _object(row,_PRICES|_CONDITIONS)
        _pricing({k:v for k,v in row.items() if k in _PRICES})
        for k,v in row.items():
            if k in {'min_prompt_tokens','max_prompt_tokens'}:_require(type(v) is int and v>=0)
            elif k in {'utc_start','utc_end'}:_require(type(v) is str and len(v)<=16)
            elif k=='utc_days':_require(type(v) is list and all(type(x) is int and 0<=x<=6 for x in v))


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
