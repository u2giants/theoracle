"""Invented exact embedding metadata/fees; no native/API or spend authority."""
from datetime import datetime,timezone,timedelta
from decimal import Decimal,localcontext
from types import SimpleNamespace
import copy,json
import pytest
from oracle_brain.operating_model.contracts import canonical_bytes,digest
from oracle_brain.operating_model.raw_endpoint_inventory_v1 import(query_embedding_safety_inventory_v1,query_embedding_policy_hash_v1,
 QueryEmbeddingBillingBoundsV1,compare_query_embedding_quote_v1)
from oracle_brain.operating_model.provider_adapter import QualifiedQueryEmbeddingPricingV1,AdmittedProvider
from test_raw_endpoint_inventory_v1 import catalogue
MODEL='openai/text-embedding-3-small'

def scenario():
 m,e=catalogue();model=m['data'][0];endpoint=e['data']['endpoints'][0];arch=dict(input_modalities=['text'],output_modalities=['embeddings'],modality='text->text',tokenizer='GPT',instruct_type=None)
 model.update(id=MODEL,architecture=arch,context_length=8192,supported_parameters=[]);model['top_provider'].update(context_length=8192,max_completion_tokens=None)
 e['data'].update(id=MODEL,architecture=copy.deepcopy(arch));endpoint.update(model_id=MODEL,context_length=8192,max_prompt_tokens=8192,max_completion_tokens=None,supported_parameters=[])
 for item in(model,endpoint):item['pricing']=dict(prompt='.00000002',input_cache_write='.00000003',input_cache_read='.00000001',request='.000001',completion='0',image='0',overrides=[dict(utc_start=2300,utc_end=100,prompt='.00000004')])
 inv=query_embedding_safety_inventory_v1(canonical_bytes(m),canonical_bytes(e));now=datetime.now(timezone.utc)
 q=QualifiedQueryEmbeddingPricingV1(input_per_million_usd=Decimal('.04'),input_cache_write_per_million_usd=Decimal('.03'),per_request_fee_usd=Decimal('.000001'),input_tokens_upper_bound=3000,model_context_tokens=8192,pricing_policy_sha256=query_embedding_policy_hash_v1(),catalogue_sha256=inv.catalogue_sha256,model_capability_sha256=inv.model_capability_sha256,account='key-sha256:'+'a'*64,key_fingerprint='a'*64,ledger_registry_hash='b'*64,terms_hash='c'*64,admitted_register_hash='d'*64,valid_from=now-timedelta(seconds=1),expires_at=now+timedelta(minutes=5))
 b=QueryEmbeddingBillingBoundsV1(route='shared-only',account=q.account,key_fingerprint=q.key_fingerprint,ledger_registry_hash=q.ledger_registry_hash,terms_hash=q.terms_hash,provider_evidence_sha256='e'*64,upstream_input_per_million_usd=Decimal(0),upstream_output_per_million_usd=Decimal(0),upstream_per_image_fee_usd=Decimal(0),upstream_per_request_fee_usd=Decimal(0),valid_from=q.valid_from,expires_at=q.expires_at)
 return m,e,q,b,now

def compare(s):
 m,e,q,b,now=s
 return compare_query_embedding_quote_v1(canonical_bytes(m),canonical_bytes(e),quote=q,billing_bounds=b,expected_quote_sha256=digest(q.model_dump(mode='json')),expected_billing_evidence_sha256=digest(b.model_dump(mode='json')),current_account=q.account,current_key_fingerprint=q.key_fingerprint,current_ledger_registry_hash=q.ledger_registry_hash,current_terms_hash=q.terms_hash,current_register_hash=q.admitted_register_hash,models_observed_at=now,endpoints_observed_at=now,now=now)

def test_embedding_schema_is_not_chat_and_has_no_fake_output_image_or_views():
 s=scenario();body=json.loads(compare(s));assert body['comparison_only'] and not body['dispatch_authorized']
 assert not {'output_per_million_usd','max_output_tokens','per_image_fee_usd','views'}&set(type(s[2]).model_fields)
 holder=SimpleNamespace(request=SimpleNamespace(purpose='qualified-query-embedding-v1'),pricing=s[2])
 with localcontext() as context:
  context.prec=2
  assert AdmittedProvider._reservation_maximum(holder,input_tokens_upper_bound=3000)==Decimal('.000121')

@pytest.mark.parametrize('damage',['missing-cachewrite','unknown-fee','prompt','request','cachewrite','context','prompt-cap','model-base','cache-read','chat-output','model-id','byok','upstream','future','stale'])
def test_embedding_unknown_fees_route_or_changed_inventory_refuses_before_spend(damage):
 m,e,q,b,now=scenario();model=m['data'][0];endpoint=e['data']['endpoints'][0]
 if damage=='missing-cachewrite':endpoint['pricing'].pop('input_cache_write')
 elif damage=='unknown-fee':endpoint['pricing']['image_token']='.1'
 elif damage=='prompt':endpoint['pricing']['prompt']='1'
 elif damage=='request':endpoint['pricing']['request']='1'
 elif damage=='cachewrite':endpoint['pricing']['input_cache_write']='1'
 elif damage=='context':endpoint['context_length']=2000
 elif damage=='prompt-cap':endpoint['max_prompt_tokens']=2000
 elif damage=='model-base':model['pricing']['prompt']='1'
 elif damage=='cache-read':endpoint['pricing']['input_cache_read']='1'
 elif damage=='chat-output':model['architecture']['output_modalities']=['text'];e['data']['architecture']=model['architecture']
 elif damage=='model-id':model['id']='foreign'
 elif damage=='byok':b=b.model_copy(update={'route':'byok'})
 elif damage=='upstream':b=b.model_copy(update={'upstream_input_per_million_usd':Decimal('1')})
 elif damage=='future':now=q.valid_from-timedelta(seconds=1)
 elif damage=='stale':now=q.expires_at+timedelta(seconds=1)
 with pytest.raises((PermissionError,ValueError)):compare((m,e,q,b,now))

@pytest.mark.parametrize('field,value',[('input_tokens_upper_bound',True),('model_context_tokens',True),('schema_version',True),('input_per_million_usd',Decimal('NaN')),('input_cache_write_per_million_usd',Decimal('-1')),('per_request_fee_usd',Decimal('Infinity')),('model','openai/gpt-6.1-sol')])
def test_direct_embedding_quote_cannot_bypass_types_or_finite_bounds(field,value):
 with pytest.raises(ValueError):QualifiedQueryEmbeddingPricingV1.model_validate(scenario()[2].model_dump(mode='python')|{field:value})
