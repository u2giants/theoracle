"""Invented official-shaped endpoint catalogue; never contacts OpenRouter."""
import copy,json
import pytest
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import raw_endpoint_safety_inventory_v1
MODEL='openai/gpt-6.1-sol'

def catalogue():
    arch=dict(input_modalities=['text','image'],output_modalities=['text'],instruct_type=None,modality='text+image->text',tokenizer='GPT')
    price=dict(prompt='0.000001',completion='0.000002',image='0.001',request='0.002',input_cache_write='0.000003',
        input_cache_read='0.000001',overrides=[dict(min_prompt_tokens=10000,prompt='0.000004')])
    model=dict(id=MODEL,architecture=arch,context_length=100000,pricing=price,
        top_provider=dict(context_length=100000,max_completion_tokens=8192,is_moderated=True),
        supported_parameters=['max_tokens','response_format'],name='Invented model',description='Invented only')
    endpoint=dict(model_id=MODEL,provider_name='OpenAI',tag='openai',status=0,context_length=100000,
        max_prompt_tokens=90000,max_completion_tokens=8192,pricing=copy.deepcopy(price),quantization='fp16',
        supported_parameters=['max_tokens','response_format'],name='Invented endpoint',model_name='Invented',
        latency_last_30m={'p50':1},throughput_last_30m={'p50':10},uptime_last_1d=99,
        uptime_last_30m=99,uptime_last_5m=99,supports_implicit_caching=True,supports_diarization=False)
    return {'data':[model]},{'data':dict(id=MODEL,architecture=copy.deepcopy(arch),endpoints=[endpoint])}

def parse(m,e):return raw_endpoint_safety_inventory_v1(json.dumps(m).encode(),json.dumps(e).encode(),model=MODEL)

def test_documented_metrics_only_changes_keep_safety_hash_and_retain_wire_identity():
    m,e=catalogue();a=parse(m,e);e['data']['endpoints'][0]['latency_last_30m']['p50']=2
    m['data'][0]['name']='Another display name';b=parse(m,e)
    assert a.catalogue_sha256==b.catalogue_sha256 and a.model_capability_sha256==b.model_capability_sha256
    assert a.models_wire_sha256!=b.models_wire_sha256 and a.endpoints_wire_sha256!=b.endpoints_wire_sha256

@pytest.mark.parametrize('field,value',[('model_id','openai/gpt-6-astra'),('provider_name','Foreign'),
    ('tag','foreign'),('status',1),('status',True),('context_length',None),('max_prompt_tokens',True),
    ('max_completion_tokens',0),('unknown_capability',1)])
def test_foreign_or_unknown_endpoint_identity_and_capability_refuses(field,value):
    m,e=catalogue();e['data']['endpoints'][0][field]=value
    with pytest.raises(PermissionError):parse(m,e)

@pytest.mark.parametrize('field',['pricing','architecture','context_length','top_provider','supported_parameters'])
def test_each_model_safety_mutation_changes_bound_inventory(field):
    m,e=catalogue();a=parse(m,e)
    if field=='pricing':m['data'][0][field]['prompt']='0.000009'
    elif field=='architecture':m['data'][0][field]['tokenizer']='different';e['data']['architecture']['tokenizer']='different'
    elif field=='context_length':m['data'][0][field]-=1
    elif field=='top_provider':m['data'][0][field]['context_length']-=1
    else:m['data'][0][field].append('another')
    assert parse(m,e).catalogue_sha256!=a.catalogue_sha256

@pytest.mark.parametrize('damage',['unknown-fee','unknown-condition','negative','nonfinite','number','duplicate-key','bad-modality','unknown-model-field'])
def test_pricing_unknowns_and_malformed_schema_never_become_zero(damage):
    m,e=catalogue();p=e['data']['endpoints'][0]['pricing']
    if damage=='unknown-fee':p['surprise_fee']='0'
    elif damage=='unknown-condition':p['overrides'][0]['surprise_condition']=True
    elif damage=='negative':p['image']='-1'
    elif damage=='nonfinite':p['request']='NaN'
    elif damage=='number':p['image']=0
    elif damage=='bad-modality':m['data'][0]['architecture']['input_modalities']=[{}]
    elif damage=='unknown-model-field':m['data'][0]['unknown_safety']=1
    else:
        with pytest.raises(PermissionError):raw_endpoint_safety_inventory_v1(b'{"data":[],"data":[]}',b'{}',model=MODEL)
        return
    with pytest.raises(PermissionError):parse(m,e)


def test_endpoint_order_is_canonical_but_duplicates_are_never_dropped():
    m,e=catalogue();a=parse(m,e);e['data']['endpoints'].append(copy.deepcopy(e['data']['endpoints'][0]));b=parse(m,e)
    assert a.catalogue_sha256!=b.catalogue_sha256
    assert b.canonical_inventory.count(b'"provider_name":"OpenAI"')==2
