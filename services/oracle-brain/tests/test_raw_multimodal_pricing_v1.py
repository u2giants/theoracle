from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.provider_adapter import Pricing
from oracle_brain.operating_model.raw_multimodal_pricing_v1 import RawMultimodalPricingQuoteV1,raw_multimodal_reservation_maximum_v1

def quote():
    now=datetime.now(timezone.utc)
    q=RawMultimodalPricingQuoteV1(model='openai/gpt-6.1-sol',account='invented-only',terms_hash='a'*64,
        key_fingerprint='b'*64,ledger_registry_hash='c'*64,catalogue_sha256='d'*64,pricing_policy_sha256='e'*64,
        vision_token_policy_sha256='f'*64,model_capability_sha256='1'*64,dispatch_id=uuid4(),request_hash='2'*64,
        view_manifest_hash='3'*64,population_id=uuid4(),original_root_hash='4'*64,original_allocation_hash='5'*64,
        original_horizon=now+timedelta(seconds=90),view_count=7,total_image_bytes=700,largest_image_bytes=100,
        model_max_images=10,model_max_image_bytes=1000,model_context_tokens=100000,
        text_input_tokens_upper_bound=1000,vision_input_tokens_upper_bound=2000,input_per_million_usd=Decimal('1'),
        input_cache_write_per_million_usd=Decimal('2'),output_per_million_usd=Decimal('4'),max_output_tokens=100,
        per_image_fee_usd=Decimal('.001'),per_request_fee_usd=Decimal('.002'),is_byok=True,
        upstream_input_per_million_usd=Decimal('3'),upstream_output_per_million_usd=Decimal('5'),
        upstream_per_image_fee_usd=Decimal('.003'),upstream_per_request_fee_usd=Decimal('.004'),
        admitted_register_hash='6'*64,valid_from=now,expires_at=now+timedelta(seconds=60),issuer_actor=uuid4(),reviewer_actor=uuid4())
    return q,now

def cost(q,now,**kw):
    args=dict(expected_quote_sha256=digest(q.model_dump(mode='json')),input_tokens_upper_bound=3000,
        purpose='source-original-reading',now=now);args.update(kw)
    return raw_multimodal_reservation_maximum_v1(q,**args)

def test_raw_cost_counts_vision_worst_cache_and_each_platform_upstream_fee():
    q,now=quote();assert cost(q,now)==Decimal('.049900')
    assert cost(q,now,purpose='source-original-review')==Decimal('.049900')

@pytest.mark.parametrize('update',[{'schema_version':True},{'schema_version':1.0},{'view_count':True},
    {'view_count':11},{'largest_image_bytes':1001},{'model_context_tokens':3099},{'max_output_tokens':8193},
    {'is_byok':False},{'per_image_fee_usd':Decimal('NaN')},{'per_request_fee_usd':Decimal('Infinity')},
    {'vision_input_tokens_upper_bound':0}])
def test_raw_unknown_or_impossible_capacity_fee_and_version_denies(update):
    q,_=quote()
    with pytest.raises(Exception):RawMultimodalPricingQuoteV1.model_validate({**q.model_dump(),**update})

@pytest.mark.parametrize('changes',[{'expected_quote_sha256':'0'*64},{'input_tokens_upper_bound':3001},
    {'input_tokens_upper_bound':True},{'purpose':'source-extraction'}])
def test_quote_hash_context_or_phase_cannot_be_reinterpreted(changes):
    q,now=quote()
    with pytest.raises(PermissionError):cost(q,now,**changes)

def test_zero_is_explicit_not_missing_and_original_window_not_refreshed():
    q,now=quote();body=q.model_dump();body['per_image_fee_usd']=Decimal(0)
    zero=RawMultimodalPricingQuoteV1.model_validate(body);assert cost(zero,now)<cost(q,now)
    del body['per_image_fee_usd']
    with pytest.raises(Exception):RawMultimodalPricingQuoteV1.model_validate(body)
    with pytest.raises(PermissionError):cost(q,q.expires_at)

def test_raw_quote_revalidation_denies_constructed_subclass_or_nonfinite_mutation():
    q,now=quote()
    class Foreign(RawMultimodalPricingQuoteV1):pass
    with pytest.raises(PermissionError):cost(Foreign.model_validate(q.model_dump()),now)
    with pytest.raises(Exception):cost(q.model_copy(update={'per_image_fee_usd':Decimal('NaN')}),now)

def test_existing_text_pricing_bytes_and_fields_remain_unextended():
    q,_=quote();p=Pricing(provider='openrouter',model=q.model,input_per_million_usd=Decimal(1),
        output_per_million_usd=Decimal(4),max_output_tokens=100,expires_at=q.expires_at,admitted_register_hash='6'*64)
    assert set(p.model_dump())=={'schema_version','provider','model','input_per_million_usd','output_per_million_usd',
        'max_output_tokens','expires_at','admitted_register_hash'}
    assert Pricing.model_validate_json(p.model_dump_json()).model_dump_json()==p.model_dump_json()
