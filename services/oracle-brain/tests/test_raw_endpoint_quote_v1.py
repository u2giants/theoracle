"""Descriptive pure current comparisons, never authenticated billing/admission."""
import copy,json
from datetime import timedelta
from decimal import Decimal,localcontext
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import (RawBillingBoundsV1,
    compare_raw_endpoint_quote_v1,raw_endpoint_safety_inventory_v1,
    raw_worst_case_policy_v1,raw_worst_case_policy_hash_v1)
from test_raw_endpoint_inventory_v1 import catalogue,MODEL
from test_raw_multimodal_pricing_v1 import quote as old_quote


def scenario(*,byok=True):
    m,e=catalogue();q,now=old_quote()
    inv=raw_endpoint_safety_inventory_v1(canonical_bytes(m),canonical_bytes(e),model=MODEL)
    q=q.model_copy(update={'account':'key-sha256:'+q.key_fingerprint,
        'pricing_policy_sha256':raw_worst_case_policy_hash_v1(),'catalogue_sha256':inv.catalogue_sha256,
        'model_capability_sha256':inv.model_capability_sha256,'input_per_million_usd':Decimal('4'),
        'input_cache_write_per_million_usd':Decimal('3'),'output_per_million_usd':Decimal('2'),
        'is_byok':byok,**({} if byok else {k:Decimal(0) for k in
            ('upstream_input_per_million_usd','upstream_output_per_million_usd',
             'upstream_per_image_fee_usd','upstream_per_request_fee_usd')})})
    b=RawBillingBoundsV1(model=q.model,route='byok' if byok else 'shared-only',account=q.account,
        key_fingerprint=q.key_fingerprint,ledger_registry_hash=q.ledger_registry_hash,terms_hash=q.terms_hash,
        provider_evidence_sha256='7'*64,valid_from=now-timedelta(seconds=1),expires_at=q.expires_at,
        **{key:getattr(q,key) for key in ('upstream_input_per_million_usd','upstream_output_per_million_usd',
            'upstream_per_image_fee_usd','upstream_per_request_fee_usd')})
    return m,e,q,b,now


def compare(s,**changes):
    m,e,q,b,now=s
    args=dict(quote=q,expected_quote_sha256=digest(q.model_dump(mode='json')),billing_bounds=b,
        expected_billing_evidence_sha256=digest(b.model_dump(mode='json')),current_account=q.account,
        current_key_fingerprint=q.key_fingerprint,current_ledger_registry_hash=q.ledger_registry_hash,
        current_terms_hash=q.terms_hash,current_register_hash=q.admitted_register_hash,
        models_observed_at=now,endpoints_observed_at=now,now=now)
    args.update(changes)
    return compare_raw_endpoint_quote_v1(canonical_bytes(m),canonical_bytes(e),**args)


def repin(s,**quote_changes):
    m,e,q,b,now=s;inv=raw_endpoint_safety_inventory_v1(canonical_bytes(m),canonical_bytes(e),model=MODEL)
    q=q.model_copy(update={'catalogue_sha256':inv.catalogue_sha256,
        'model_capability_sha256':inv.model_capability_sha256,**quote_changes})
    return m,e,q,b,now

@pytest.mark.parametrize('byok',[True,False])
def test_complete_comparison_retains_raw_wires_but_grants_nothing(byok):
    s=scenario(byok=byok);m,e,q,b,now=s;body=json.loads(compare(s))
    assert body['comparison_only'] is True
    assert body['dispatch_authorized'] is False and body['billing_route_authenticated'] is False
    assert body['models_wire_sha256']==digest(m) and body['endpoints_wire_sha256']==digest(e)
    assert body['billing_evidence_sha256']==digest(b.model_dump(mode='json'))
    assert body['quote_sha256']==digest(q.model_dump(mode='json'))
    assert json.loads(raw_worst_case_policy_v1())['units']['image']=='USD/input-image'


def test_all_endpoint_base_override_maxima_never_first_or_condition_discount():
    s=scenario();m,e,q,b,now=s
    other=copy.deepcopy(e['data']['endpoints'][0]);other['pricing'].update(prompt='.000009',
        completion='.000006',input_cache_write='.000011',image='.05',request='.7')
    # Even a cheap present-day base and a future/night/weekend override must
    # contribute fully: we never select a currently cheap condition.
    other['pricing']['overrides']=[{'utc_start':2300,'utc_end':100,'utc_days':['sunday'],
        'prompt':'.000020','completion':'.000030','input_cache_write':'.000040',
        'image':'.08','request':'.9'}]
    e['data']['endpoints'].append(other)
    with pytest.raises(PermissionError):compare(repin(s))
    compare(repin(s,input_per_million_usd=Decimal(20),output_per_million_usd=Decimal(30),
        input_cache_write_per_million_usd=Decimal(40),per_image_fee_usd=Decimal('.08'),
        per_request_fee_usd=Decimal('.9')))
    e['data']['endpoints'].reverse()
    compare(repin(s,input_per_million_usd=Decimal(20),output_per_million_usd=Decimal(30),
        input_cache_write_per_million_usd=Decimal(40),per_image_fee_usd=Decimal('.08'),
        per_request_fee_usd=Decimal('.9')))


def test_catalogue_price_is_not_selected_endpoint_price():
    s=scenario();s[0]['data'][0]['pricing']['prompt']='1'
    compare(repin(s))  # Existing endpoint maxima remain4/million, not1/token.

@pytest.mark.parametrize('where,field,value',[
    ('model','context_length',3099),('top','context_length',3099),('endpoint','context_length',3099),
    ('endpoint','max_prompt_tokens',2999),('top','max_completion_tokens',99),
    ('endpoint','max_completion_tokens',99)])
def test_every_current_capacity_dimension_is_enforced(where,field,value):
    s=scenario();m,e,q,b,now=s
    target=m['data'][0] if where=='model' else m['data'][0]['top_provider'] if where=='top' else e['data']['endpoints'][0]
    target[field]=value
    # Repinning observations is descriptive; it cannot make impossible capacity pass.
    with pytest.raises(PermissionError):compare(repin(s))


def test_all_endpoint_capacity_minimum_and_model_per_request_limits_apply():
    s=scenario();e=s[1];other=copy.deepcopy(e['data']['endpoints'][0]);other['max_prompt_tokens']=2999
    e['data']['endpoints'].append(other)
    with pytest.raises(PermissionError):compare(repin(s))
    s=scenario();s[0]['data'][0]['per_request_limits']={'prompt_tokens':2999}
    with pytest.raises(PermissionError):compare(repin(s))
    s=scenario();s[0]['data'][0]['per_request_limits']={'completion_tokens':99}
    with pytest.raises(PermissionError):compare(repin(s))

@pytest.mark.parametrize('damage',['model-parameter','endpoint-parameter','output-modality','image_token',
    'fee-unit','missing-fee','unknown-condition','bad-time','bad-day','max-prompt-override'])
def test_unknown_incomplete_or_wrong_units_capabilities_conditions_refuse(damage):
    s=scenario();m,e,*_=s;p=e['data']['endpoints'][0]['pricing']
    if damage=='model-parameter':m['data'][0]['supported_parameters']=['max_tokens']
    elif damage=='endpoint-parameter':e['data']['endpoints'][0]['supported_parameters']=['response_format']
    elif damage=='output-modality':
        m['data'][0]['architecture']['output_modalities']=['image']
        e['data']['architecture']['output_modalities']=['image']
    elif damage=='image_token':p['image_token']='.000001'
    elif damage=='fee-unit':p['unit']='USD/million-tokens'
    elif damage=='missing-fee':del p['request']
    elif damage=='unknown-condition':p['overrides']=[{'location':'cheap','prompt':'.1'}]
    elif damage=='bad-time':p['overrides']=[{'utc_start':1260,'utc_end':1300,'prompt':'.1'}]
    elif damage=='bad-day':p['overrides']=[{'utc_days':['Monday'],'prompt':'.1'}]
    else:p['overrides']=[{'max_prompt_tokens':1000,'prompt':'.1'}]
    with pytest.raises(PermissionError):
        compare(repin(s) if damage in {'model-parameter','endpoint-parameter','output-modality'} else s)

@pytest.mark.parametrize('key,value',[
    ('expected_billing_evidence_sha256',None),('expected_billing_evidence_sha256','0'*64),
    ('billing_bounds',None),('current_terms_hash','0'*64),('current_account','foreign-account'),
    ('current_key_fingerprint','0'*64),('current_ledger_registry_hash','0'*64),
    ('current_register_hash','0'*64),('expected_quote_sha256','0'*64)])
def test_no_billing_route_or_current_binding_is_defaulted_or_self_authenticated(key,value):
    with pytest.raises(PermissionError):compare(scenario(),**{key:value})

@pytest.mark.parametrize('field',['upstream_input_per_million_usd','upstream_output_per_million_usd',
    'upstream_per_image_fee_usd','upstream_per_request_fee_usd'])
def test_every_upstream_dimension_is_explicit_and_quote_matched(field):
    s=scenario();m,e,q,b,now=s
    with pytest.raises(PermissionError):compare((m,e,q,b.model_copy(update={field:Decimal(99)}),now))
    body=b.model_dump();del body[field]
    with pytest.raises(ValueError):RawBillingBoundsV1.model_validate(body)

@pytest.mark.parametrize('damage',['route','model','key','account','terms','ledger','expiry','future','nonfinite','version'])
def test_billing_bounds_and_quotes_cannot_cross_current_route_scope_or_window(damage):
    s=scenario();m,e,q,b,now=s
    changes={'route':'shared-only'} if damage=='route' else {'model':'openai/gpt-6-astra'} if damage=='model' else \
        {'key_fingerprint':'0'*64} if damage=='key' else {'account':'foreign'} if damage=='account' else \
        {'terms_hash':'0'*64} if damage=='terms' else {'ledger_registry_hash':'0'*64} if damage=='ledger' else \
        {'expires_at':now} if damage=='expiry' else {'valid_from':now+timedelta(seconds=1)} if damage=='future' else \
        {'upstream_input_per_million_usd':Decimal('NaN')} if damage=='nonfinite' else {'schema_version':True}
    with pytest.raises((PermissionError,ValueError)):compare((m,e,q,b.model_copy(update=changes),now))

@pytest.mark.parametrize('key,offset',[('models_observed_at',-121),('endpoints_observed_at',-121),
    ('models_observed_at',1),('endpoints_observed_at',1),('now',61)])
def test_old_future_or_expired_observations_refuse(key,offset):
    s=scenario();now=s[-1]
    with pytest.raises(PermissionError):compare(s,**{key:now+timedelta(seconds=offset)})


def test_exact_decimal_conversion_cannot_round_down_under_small_decimal_context():
    s=scenario();p=s[1]['data']['endpoints'][0]['pricing'];price='0.000123456789123456789123456789123456789'
    p['prompt']=price;p['overrides']=[]
    exact=Decimal('123.456789123456789123456789123456789')
    s=repin(s,input_per_million_usd=exact)
    with localcontext() as ctx:
        ctx.prec=6
        compare(s)
    with pytest.raises(PermissionError):compare(repin(s,input_per_million_usd=Decimal('123.456789')))


def test_stable_display_metrics_preserve_safety_but_complete_raw_wire_changes():
    s=scenario();first=json.loads(compare(s));s[0]['data'][0]['name']='New display only'
    s[1]['data']['endpoints'][0]['latency_last_30m']['p50']=99
    other=json.loads(compare(s))
    assert other['catalogue_sha256']==first['catalogue_sha256']
    assert other['models_wire_sha256']!=first['models_wire_sha256']
    assert other['endpoints_wire_sha256']!=first['endpoints_wire_sha256']


def test_policy_hash_and_each_price_dimension_cannot_be_reinterpreted():
    s=scenario()
    for field in ('input_per_million_usd','input_cache_write_per_million_usd','output_per_million_usd',
            'per_image_fee_usd','per_request_fee_usd'):
        with pytest.raises(PermissionError):compare(repin(s,**{field:Decimal(0)}))
    with pytest.raises(PermissionError):compare(repin(s,pricing_policy_sha256='0'*64))
    policy=json.loads(raw_worst_case_policy_v1())
    assert policy['purpose']=='raw-worst-case-v1' and policy['schema_version']==1
    assert digest(policy)==raw_worst_case_policy_hash_v1()
    assert policy['condition_discounts'] is False


def test_naive_observations_and_incomplete_model_limit_units_never_qualify():
    s=scenario()
    with pytest.raises(PermissionError):compare(s,models_observed_at=s[-1].replace(tzinfo=None))
    for limits in ({'prompt_tokens':True},{'prompt_tokens':None},{'prompt_tokens':{'unit':'token','value':90000}},
            {'unknown_limit':1}):
        m,e,q,b,now=scenario();m['data'][0]['per_request_limits']=limits
        with pytest.raises(PermissionError):compare(repin((m,e,q,b,now)))


@pytest.mark.parametrize('position',['base','override'])
@pytest.mark.parametrize('rate,accepted',[('0',True),('.000003',True),('.000004',True),('.000004000001',False)])
def test_cache_read_lower_equal_or_above_global_prompt_cache_write_bound(position,rate,accepted):
    s=scenario();p=s[1]['data']['endpoints'][0]['pricing']
    if position=='base':p['input_cache_read']=rate
    else:p['overrides'].append({'min_prompt_tokens':99999,'input_cache_read':rate})
    s=repin(s)
    if accepted:compare(s)
    else:
        with pytest.raises(PermissionError):compare(s)

@pytest.mark.parametrize('position',['base','override'])
@pytest.mark.parametrize('value',['-0.1','NaN','Infinity',None,True,0,{'unknown':'rate'}])
def test_cache_read_unknown_negative_nonfinite_and_coerced_values_refuse(position,value):
    s=scenario();p=s[1]['data']['endpoints'][0]['pricing']
    if position=='base':p['input_cache_read']=value
    else:p['overrides'].append({'min_prompt_tokens':1,'input_cache_read':value})
    with pytest.raises(PermissionError):compare(s)


def test_cache_read_comparison_uses_global_maxima_across_all_endpoints():
    s=scenario();e=s[1];p=e['data']['endpoints'][0]['pricing'];p['input_cache_read']='.000009'
    other=copy.deepcopy(e['data']['endpoints'][0]);other['pricing']['input_cache_write']='.000009'
    e['data']['endpoints'].append(other)
    compare(repin(s,input_cache_write_per_million_usd=Decimal(9)))
    other['pricing']['input_cache_write']='.000008'
    with pytest.raises(PermissionError):compare(repin(s,input_cache_write_per_million_usd=Decimal(8)))
