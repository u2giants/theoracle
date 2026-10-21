"""Text-only uses the shared strict endpoint parser and conservative fee owner."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal,localcontext
import copy,json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.provider_adapter import ConversationTextPricingV1,AdmittedProvider
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import (RawBillingBoundsV1,text_endpoint_safety_inventory_v1,
 compare_conversation_text_quote_v1,text_worst_case_policy_hash_v1)
from test_raw_endpoint_inventory_v1 import catalogue,MODEL

def scenario(*,key='a'*64,ledger='b'*64,terms='c'*64,register='d'*64,input_tokens=3000):
 m,e=catalogue();now=datetime.now(timezone.utc)
 for target in (m['data'][0],e['data']['endpoints'][0]):target['pricing'].pop('image',None)
 m['data'][0]['architecture']['input_modalities']=['text'];e['data']['architecture']=copy.deepcopy(m['data'][0]['architecture'])
 inv=text_endpoint_safety_inventory_v1(canonical_bytes(m),canonical_bytes(e),model=MODEL)
 q=ConversationTextPricingV1(model=MODEL,input_per_million_usd=Decimal(4),input_cache_write_per_million_usd=Decimal(3),output_per_million_usd=Decimal(2),per_request_fee_usd=Decimal('.002'),max_output_tokens=100,input_tokens_upper_bound=input_tokens,model_context_tokens=100000,pricing_policy_sha256=text_worst_case_policy_hash_v1(),catalogue_sha256=inv.catalogue_sha256,model_capability_sha256=inv.model_capability_sha256,account='key-sha256:'+key,key_fingerprint=key,ledger_registry_hash=ledger,terms_hash=terms,admitted_register_hash=register,valid_from=now-timedelta(seconds=2),expires_at=now+timedelta(minutes=5))
 b=RawBillingBoundsV1(model=MODEL,route='shared-only',account=q.account,key_fingerprint=key,ledger_registry_hash=ledger,terms_hash=terms,provider_evidence_sha256='e'*64,upstream_input_per_million_usd=Decimal(0),upstream_output_per_million_usd=Decimal(0),upstream_per_image_fee_usd=Decimal(0),upstream_per_request_fee_usd=Decimal(0),valid_from=q.valid_from,expires_at=q.expires_at)
 return m,e,q,b,now

def compare(s):
 m,e,q,b,now=s
 return compare_conversation_text_quote_v1(canonical_bytes(m),canonical_bytes(e),quote=q,billing_bounds=b,expected_quote_sha256=digest(q.model_dump(mode='json')),expected_billing_evidence_sha256=digest(b.model_dump(mode='json')),current_account=q.account,current_key_fingerprint=q.key_fingerprint,current_ledger_registry_hash=q.ledger_registry_hash,current_terms_hash=q.terms_hash,current_register_hash=q.admitted_register_hash,models_observed_at=now,endpoints_observed_at=now,now=now)

def test_text_bound_has_zero_images_and_no_fabricated_raw_fields():
 s=scenario();q=s[2];body=json.loads(compare(s));assert body['comparison_only'] and not body['dispatch_authorized']
 assert not {'views','vision_input_tokens_upper_bound','per_image_fee_usd','raw_population_hash'}&set(type(q).model_fields)

@pytest.mark.parametrize('damage',['request','cache-write','prompt','completion','context','max-prompt','max-completion','unknown-fee','unknown-condition','route','upstream','stale','model-text','model-output'])
def test_endpoint_or_route_drift_never_qualifies_old_text_quote(damage):
 m,e,q,b,now=s=scenario();p=e['data']['endpoints'][0]
 if damage in ('request','prompt','completion'):p['pricing'][damage]='.7'
 elif damage=='cache-write':p['pricing']['input_cache_write']='.8'
 elif damage=='context':p['context_length']=3000
 elif damage=='max-prompt':p['max_prompt_tokens']=2000
 elif damage=='max-completion':p['max_completion_tokens']=99
 elif damage=='unknown-fee':p['pricing']['image_token']='.1'
 elif damage=='unknown-condition':p['pricing']['overrides']=[{'unknown':'yes','prompt':'.1'}]
 elif damage=='route':b=b.model_copy(update={'route':'byok'})
 elif damage=='upstream':b=b.model_copy(update={'upstream_input_per_million_usd':Decimal(1)})
 elif damage=='stale':now=now+timedelta(minutes=10)
 elif damage=='model-text':m['data'][0]['architecture']['input_modalities']=['image']
 else:m['data'][0]['architecture']['output_modalities']=['image']
 with pytest.raises((PermissionError,ValueError)):compare((m,e,q,b,now))

def test_conservative_cache_write_request_and_all_overrides_charge_same_budget():
 m,e,q,b,now=scenario();p=e['data']['endpoints'][0]['pricing'];p['overrides']=[{'utc_start':2300,'utc_end':100,'prompt':'.000005','input_cache_write':'.000008','request':'.02'}]
 inv=text_endpoint_safety_inventory_v1(canonical_bytes(m),canonical_bytes(e),model=MODEL)
 q=q.model_copy(update={'catalogue_sha256':inv.catalogue_sha256,'model_capability_sha256':inv.model_capability_sha256,'input_per_million_usd':Decimal(5),'input_cache_write_per_million_usd':Decimal(8),'per_request_fee_usd':Decimal('.02')})
 compare((m,e,q,b,now))
 from types import SimpleNamespace
 holder=SimpleNamespace(pricing=q,request=SimpleNamespace(purpose='employee-conversation'))
 with localcontext() as ctx:
  ctx.prec=3
  assert AdmittedProvider._reservation_maximum(holder,input_tokens_upper_bound=3000)==Decimal('.0442')


@pytest.mark.parametrize('field,value',[('schema_version',True),('input_tokens_upper_bound',True),('input_per_million_usd',Decimal('Infinity')),('output_per_million_usd',Decimal('NaN')),('per_request_fee_usd',Decimal('-1')),('input_cache_write_per_million_usd',Decimal('Infinity'))])
def test_direct_text_dto_construction_cannot_bypass_strict_complete_bound(field,value):
 q=scenario()[2]
 with pytest.raises(ValueError):ConversationTextPricingV1.model_validate(q.model_dump(mode='python')|{field:value})
