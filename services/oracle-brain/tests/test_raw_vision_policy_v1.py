"""Invented explicitly conservative vision policy; no model capability claim."""
from datetime import timedelta
from uuid import uuid4
import pytest
from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.raw_vision_policy_v1 import RawVisionTokenPolicyV1,verify_raw_vision_quote_v1
from test_raw_multimodal_pricing_v1 import quote

def packet():
    q,now=quote();p=RawVisionTokenPolicyV1(model=q.model,max_width=4000,max_height=4000,max_images=10,
        max_image_bytes=1000,max_total_image_bytes=10000,tokens_per_complete_view_upper_bound=250,
        provider_evidence_sha256='a'*64,issuer_actor=uuid4(),reviewer_actor=uuid4(),
        valid_from=now,expires_at=q.expires_at)
    h=digest(p.model_dump(mode='json'));q=q.model_copy(update={'vision_token_policy_sha256':h})
    return q,p,tuple((4000,4000,100) for _ in range(7)),h,now

def check(q,p,views,h,now):return verify_raw_vision_quote_v1(q,p,views,expected_policy_sha256=h,now=now)

def test_complete_actual_view_bound_uses_model_policy_not_base64_length():
    q,p,v,h,now=packet();assert check(q,p,v,h,now)==q.expires_at

@pytest.mark.parametrize('damage',['width','height','bytes','count','missing','hash','model','vision-tokens','expiry','bool'])
def test_incomplete_or_unproven_vision_capacity_refuses(damage):
    q,p,v,h,now=packet()
    if damage=='width':v=((4001,4000,100),*v[1:])
    elif damage=='height':v=((4000,4001,100),*v[1:])
    elif damage=='bytes':v=((4000,4000,1001),*v[1:])
    elif damage=='count':v=(*v,*v)
    elif damage=='missing':v=v[:-1]
    elif damage=='hash':h='0'*64
    elif damage=='model':q=q.model_copy(update={'model':'openai/gpt-6-astra'})
    elif damage=='vision-tokens':q=q.model_copy(update={'vision_input_tokens_upper_bound':1749})
    elif damage=='expiry':now=p.expires_at
    else:v=((True,4000,100),*v[1:])
    with pytest.raises(PermissionError):check(q,p,v,h,now)

@pytest.mark.parametrize('bad',[True,1.0,'1'])
def test_vision_policy_does_not_coerce_version(bad):
    _,p,_,_,_=packet()
    with pytest.raises(ValueError):RawVisionTokenPolicyV1.model_validate({**p.model_dump(),'schema_version':bad})
