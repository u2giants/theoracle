"""Legacy reservation arithmetic and raw-purpose refusal before external IO."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from oracle_brain.operating_model.provider_adapter import AdmittedProvider, Pricing
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest


def provider(purpose):
    now=datetime.now(timezone.utc)
    request=ProcessingRequest(provider='openai',account='invented',endpoint='https://api.openai.com/v1',
        data_classes=frozenset({'synthetic'}),purpose=purpose,terms_hash='a'*64)
    approval=ProcessingApproval(**request.model_dump(),expires_at=now+timedelta(minutes=1),register_ref='invented')
    pricing=Pricing(provider='openai',model='openai/gpt-6.1-sol',input_per_million_usd=Decimal('2'),
        output_per_million_usd=Decimal('3'),max_output_tokens=100,expires_at=now+timedelta(minutes=1),
        admitted_register_hash='b'*64)
    class NoIO:
        def reserve(self,**kwargs):raise AssertionError('unexpected reservation')
    def no_io(*args,**kwargs):raise AssertionError('unexpected provider or allowance read')
    return AdmittedProvider(request=request,approvals=[approval],pricing=pricing,budget=NoIO(),
        sender=no_io,remaining_daily_allowance=no_io,admitted_register_hash='b'*64)


@pytest.mark.parametrize('purpose',['source-original-reading','source-original-review'])
def test_legacy_broker_refuses_raw_before_allowance_reservation_or_post(purpose):
    p=provider(purpose)
    with pytest.raises(PermissionError,match='protected raw original provider required'):
        p.extract(workspace_id=uuid4(),artifact_id=uuid4(),batch_id=uuid4(),purpose=purpose,attempt=1,
            input_tokens_upper_bound=10000,messages=[{'role':'user','content':'invented'}])


def test_text_reservation_arithmetic_and_byte_bound_remain_exact():
    p=provider('source-extraction')
    assert p._reservation_maximum(input_tokens_upper_bound=12345)==Decimal('0.02499')
    messages=[{'role':'user','content':'invented'}]
    import json
    exact=len(json.dumps(messages,ensure_ascii=False).encode())+1024
    p._validate_reservation_input(purpose='source-extraction',input_tokens_upper_bound=exact,messages=messages)
    with pytest.raises(ValueError,match='complete dispatch payload'):
        p._validate_reservation_input(purpose='source-extraction',input_tokens_upper_bound=exact-1,messages=messages)
