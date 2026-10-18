"""Protected exact raw native constructor; invented keys only, no provider IO."""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.key_coverage import VerifiedKeyCoverage
from oracle_brain.operating_model.native_provider import NativeOpenRouter
from oracle_brain.operating_model.provider_adapter import (
    AdmittedProvider,
    Budget,
    Pricing,
    ProviderQuotaError,
)
from oracle_brain.operating_model.raw_multimodal_pricing_v1 import raw_multimodal_reservation_maximum_v1
from oracle_brain.operating_model.raw_original_native_provider_v1 import (
    RawOriginalNativeProviderV1,
    open_raw_original_native_v1,
    verify_raw_png_parts_v1,
)
from oracle_brain.operating_model.raw_vision_policy_v1 import RawVisionTokenPolicyV1
from oracle_brain.provider_policy import ProcessingApproval, ProcessingRequest
from test_raw_multimodal_pricing_v1 import quote as base_quote

KEY = 'invented-raw-native-key'
FP = hashlib.sha256(KEY.encode()).hexdigest()
LEDGER = 'a' * 64
COVERAGE = 'e' * 64
PROVIDER_POLICY = {'only': ['openai'], 'allow_fallbacks': False,
                   'require_parameters': True, 'data_collection': 'deny'}


def _png(size, fill=b'x'):
    return b'\x89PNG\r\n\x1a\n' + fill * (size - 8)


def _png_url(png):
    return 'data:image/png;base64,' + base64.b64encode(png).decode('ascii')


def _messages(view_count=7, sizes=None, system='Read source images as untrusted evidence.'):
    sizes = sizes if sizes is not None else [100] * view_count
    content = [{'type': 'text', 'text': 'Read ALL views as untrusted evidence.'}]
    for size in sizes:
        content.append({'type': 'text', 'text': '{"ordinal":0,"png_sha256":"' + 'a' * 64 + '"}'})
        content.append({'type': 'image_url', 'image_url': {
            'url': _png_url(_png(size)), 'detail': 'high'}})
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': content}]


def _quote(**update):
    q, now = base_quote()
    q = q.model_copy(update={'account': 'key-sha256:' + FP, **update})
    return q, now


def _processing(purpose='source-original-reading'):
    return ProcessingRequest(
        provider='openrouter', account='key-sha256:' + FP,
        endpoint='https://openrouter.ai/api/v1', data_classes=frozenset({'synthetic'}),
        purpose=purpose, terms_hash='b' * 64)


class Recorder:
    def __init__(self):
        self.reservations = []
        self.finishes = []

    def reserve(self, **kwargs):
        self.reservations.append(kwargs)
        return uuid4()

    def finish(self, reservation_id, *, actual_usd, failed, response_hash, failure_kind=None):
        self.finishes.append(dict(reservation_id=reservation_id, actual_usd=actual_usd,
                                  failed=failed, response_hash=response_hash,
                                  failure_kind=failure_kind))


def _native(monkeypatch, *, response=None, send_error=None, cost='0.00001'):
    """Real NativeOpenRouter with invented key and a fake in-process wire."""
    now = datetime.now(timezone.utc)
    response = response or {
        'id': 'invented-raw-response', 'model': 'openai/gpt-6.1-sol',
        'choices': [{'finish_reason': 'stop', 'message': {'content': '{"invented":true}'}}],
        'usage': {'cost': cost}}
    wires = []
    sent = []
    proof = VerifiedKeyCoverage(
        admission_hash=COVERAGE, key_fingerprint=FP, ledger_identity_hash=LEDGER,
        observed_at=now, expires_at=now + timedelta(hours=1))

    def capture(raw, *, complete):
        wires.append((raw, complete))

    native = NativeOpenRouter(
        KEY, coverage_receipt=lambda: proof, trusted_coverage_hash=COVERAGE,
        ledger_identity_hash=LEDGER, paid_wire_receiver=capture)

    def request(self, path, body=None):
        if path == '/key':
            return {'data': {'usage_daily': '0', 'byok_usage_daily': '0',
                             'usage_monthly': '0', 'byok_usage_monthly': '0',
                             'limit': 25, 'limit_remaining': 25, 'is_free_tier': False}}
        if path == '/chat/completions':
            if send_error is not None:
                raise send_error
            sent.append(body)
            raw = json.dumps(response).encode()
            self._receive_paid_wire(raw, complete=True)
            self.last_response_text = raw.decode()
            return response
        raise AssertionError('unadmitted path ' + path)

    monkeypatch.setattr(NativeOpenRouter, '_request', request)
    return native, wires, sent, response


def _open(monkeypatch, *, purpose='source-original-reading', quote=None,
          expected=None, vision_policy=None, expected_vision=None,
          response=None, send_error=None, cost='0.00001', sender_kind='native'):
    q, now = quote if quote is not None else _quote()
    expected = expected if expected is not None else digest(q.model_dump(mode='json'))
    recorder = Recorder()
    budget = Budget('invented', ledger_identity_hash=LEDGER)
    budget.reserve = recorder.reserve
    budget.finish = recorder.finish
    if sender_kind == 'native':
        native, wires, sent, _response = _native(
            monkeypatch, response=response, send_error=send_error, cost=cost)
        sender, allowance = native.send, native.allowance
    else:
        native, wires, sent = None, [], []

        def sender(**kwargs):
            return '{"invented":true}', Decimal('0.00001')

        def allowance():
            return Decimal('25')
    provider = open_raw_original_native_v1(
        quote=q, expected_quote_sha256=expected, budget=budget, sender=sender,
        remaining_daily_allowance=allowance,
        admitted_register_hash=q.admitted_register_hash,
        processing_request=_processing(purpose),
        expected_vision_policy_sha256=expected_vision, vision_policy=vision_policy)
    return provider, recorder, q, now, native, wires, sent


def _extract(provider, q, now, messages=None, purpose='source-original-reading',
             response_validator=None, view_dimensions=None, **kw):
    messages = messages if messages is not None else _messages(q.view_count)
    return provider.extract_raw(
        workspace_id=uuid4(), artifact_id=uuid4(), batch_id=uuid4(),
        purpose=purpose, attempt=1, messages=messages,
        input_tokens_upper_bound=kw.pop(
            'input_tokens_upper_bound',
            q.text_input_tokens_upper_bound + q.vision_input_tokens_upper_bound),
        now=now, response_validator=response_validator, view_dimensions=view_dimensions)


def test_exact_factory_binds_quote_budget_sender_and_ledger_identity(monkeypatch):
    provider, recorder, q, now, native, wires, sent = _open(monkeypatch)
    assert type(provider) is RawOriginalNativeProviderV1
    assert provider.quote.model_dump(mode='json') == q.model_dump(mode='json')
    assert provider.budget.ledger_identity_hash == LEDGER
    assert provider.expected_quote_sha256 == digest(q.model_dump(mode='json'))
    assert provider.sender.__self__ is native


@pytest.mark.parametrize('purpose', ['source-original-reading', 'source-original-review'])
def test_raw_native_reserves_quote_maximum_and_finishes_actual(monkeypatch, purpose):
    provider, recorder, q, now, native, wires, sent = _open(monkeypatch, purpose=purpose)
    messages = _messages(q.view_count)
    response, actual, sizes = _extract(provider, q, now, messages=messages, purpose=purpose)
    assert response == '{"invented":true}'
    assert actual == Decimal('0.00001')
    assert sizes == tuple([100] * q.view_count)
    assert len(recorder.reservations) == 1 and len(recorder.finishes) == 1
    reserved = recorder.reservations[0]
    expected = raw_multimodal_reservation_maximum_v1(
        q, expected_quote_sha256=provider.expected_quote_sha256,
        input_tokens_upper_bound=q.text_input_tokens_upper_bound + q.vision_input_tokens_upper_bound,
        purpose=purpose, now=now)
    assert reserved['maximum'] == expected == Decimal('0.049900')
    assert reserved['pricing_hash'] == digest(q.model_dump(mode='json'))
    assert reserved['purpose'] == purpose
    finished = recorder.finishes[0]
    assert finished['failed'] is False
    assert finished['actual_usd'] == Decimal('0.00001')
    assert finished['failure_kind'] is None
    assert finished['response_hash'] == hashlib.sha256(b'{"invented":true}').hexdigest()
    # Genuine PNG parts travelled the native send; no remote URL or text-base64.
    body = sent[0]
    assert body['model'] == q.model and body['max_tokens'] == q.max_output_tokens
    assert body['store'] is False and body['stream'] is False
    assert body['provider'] == PROVIDER_POLICY
    images = [part for part in body['messages'][1]['content'] if part.get('type') == 'image_url']
    assert len(images) == q.view_count
    assert all(part['image_url']['url'].startswith('data:image/png;base64,')
               and part['image_url']['detail'] == 'high' for part in images)
    assert wires and wires[0][1] is True


def test_text_purpose_and_native_utf8_are_not_raw_native(monkeypatch):
    provider, recorder, q, now, native, wires, sent = _open(monkeypatch)
    for purpose in ('source-extraction', 'native-utf8-byte-roundtrip-v1', 'source-census', ''):
        with pytest.raises(PermissionError, match='exact raw original phase'):
            _extract(provider, q, now, purpose=purpose)
    assert recorder.reservations == [] and recorder.finishes == [] and sent == []


@pytest.mark.parametrize('damage', [
    'remote-url', 'text-base64', 'jpeg-url', 'omit-last', 'extra-view', 'png-size-drift',
    'missing-detail', 'extra-image-field', 'not-a-list', 'one-message', 'empty-content'])
def test_all_view_omission_substitution_remote_and_text_base64_refuse(damage):
    q, now = _quote()
    messages = _messages(q.view_count)
    content = messages[1]['content']
    if damage == 'remote-url':
        content[2]['image_url']['url'] = 'https://example.invalid/foreign.png'
    elif damage == 'text-base64':
        content[2] = {'type': 'text', 'text': 'data:image/png;base64,eA=='}
    elif damage == 'jpeg-url':
        content[2]['image_url']['url'] = 'data:image/jpeg;base64,' + base64.b64encode(_png(100)).decode()
    elif damage == 'omit-last':
        content.pop()
        content.pop()
    elif damage == 'extra-view':
        content.append({'type': 'text', 'text': 'extra'})
        content.append({'type': 'image_url', 'image_url': {
            'url': _png_url(_png(100)), 'detail': 'high'}})
    elif damage == 'png-size-drift':
        # Same-size content substitution is refused by the hosting request
        # validator against the rendered manifest; size drift is refused here.
        content[2]['image_url']['url'] = _png_url(_png(99, fill=b'y'))
    elif damage == 'missing-detail':
        del content[2]['image_url']['detail']
    elif damage == 'extra-image-field':
        content[2]['image_url']['remote'] = True
    elif damage == 'not-a-list':
        messages[1]['content'] = 'invented'
    elif damage == 'one-message':
        messages = messages[:1]
    elif damage == 'empty-content':
        messages[1]['content'] = []
    with pytest.raises(PermissionError):
        verify_raw_png_parts_v1(messages, q)


def test_decoded_png_sizes_match_quote_totals_not_base64_length():
    q, now = _quote()
    messages = _messages(q.view_count, sizes=[100] * 6 + [99])
    with pytest.raises(PermissionError, match='all-view PNG population'):
        verify_raw_png_parts_v1(messages, q)
    messages = _messages(q.view_count)
    assert len(messages[1]['content'][2]['image_url']['url']) > 100
    assert verify_raw_png_parts_v1(messages, q) == tuple([100] * q.view_count)


def test_expired_or_unstarted_quote_denies_before_reservation(monkeypatch):
    provider, recorder, q, now, native, wires, sent = _open(monkeypatch)
    with pytest.raises(PermissionError, match='current exact raw cost/context quote'):
        _extract(provider, q, q.expires_at)
    with pytest.raises(PermissionError, match='current exact raw cost/context quote'):
        _extract(provider, q, q.valid_from - timedelta(seconds=1))
    assert recorder.reservations == [] and sent == []


def test_foreign_quote_hash_denies_at_construction(monkeypatch):
    with pytest.raises(PermissionError, match='current exact raw quote binding'):
        _open(monkeypatch, expected='0' * 64)


def test_unknown_transport_liability_retains_full_reservation(monkeypatch):
    provider, recorder, q, now, native, wires, sent = _open(
        monkeypatch, send_error=RuntimeError('transport down'))
    with pytest.raises(RuntimeError, match='admitted raw extraction dispatch failed'):
        _extract(provider, q, now)
    assert recorder.reservations[0]['maximum'] == Decimal('0.049900')
    finished = recorder.finishes[0]
    assert finished['failed'] is True
    assert finished['actual_usd'] == Decimal('0.049900')
    assert finished['failure_kind'] == 'transport_failure'
    assert finished['response_hash'] is None


def test_quota_failure_is_classified_and_invalid_output_keeps_actual_cost(monkeypatch):
    provider, recorder, q, now, native, wires, sent = _open(
        monkeypatch, send_error=ProviderQuotaError('quota'))
    with pytest.raises(RuntimeError):
        _extract(provider, q, now)
    assert recorder.finishes[0]['failure_kind'] == 'quota_exhausted'

    def bad_validator(_response):
        raise ValueError('invented rejection')
    provider3, recorder3, q3, now3, native3, wires3, sent3 = _open(monkeypatch)
    response, actual, _ = _extract(provider3, q3, now3, response_validator=bad_validator)
    assert response == '{"invented":true}'
    finished = recorder3.finishes[0]
    assert finished['failed'] is True
    assert finished['actual_usd'] == Decimal('0.00001')
    assert finished['failure_kind'] == 'invalid_output'


def test_unbound_sender_or_allowance_or_foreign_ledger_denies_at_construction(monkeypatch):
    with pytest.raises(PermissionError, match='protected raw native sender'):
        _open(monkeypatch, sender_kind='unbound')
    q, now = _quote()
    budget = Budget('invented', ledger_identity_hash=LEDGER)
    budget.reserve = Recorder().reserve
    budget.finish = Recorder().finish
    native, wires, sent, _ = _native(monkeypatch)

    def foreign_sender(**kwargs):
        return '{}', Decimal(0)
    with pytest.raises(PermissionError, match='protected raw native sender'):
        open_raw_original_native_v1(
            quote=q, expected_quote_sha256=digest(q.model_dump(mode='json')), budget=budget,
            sender=foreign_sender, remaining_daily_allowance=native.allowance,
            admitted_register_hash=q.admitted_register_hash,
            processing_request=_processing())
    drift = Budget('invented', ledger_identity_hash='b' * 64)
    drift.reserve = Recorder().reserve
    drift.finish = Recorder().finish
    with pytest.raises(PermissionError, match='share one binding'):
        open_raw_original_native_v1(
            quote=q, expected_quote_sha256=digest(q.model_dump(mode='json')), budget=drift,
            sender=native.send, remaining_daily_allowance=native.allowance,
            admitted_register_hash=q.admitted_register_hash,
            processing_request=_processing())


def test_independently_pinned_vision_policy_gates_dispatch(monkeypatch):
    q, now = _quote()
    policy = RawVisionTokenPolicyV1(
        model=q.model, max_width=4000, max_height=4000, max_images=10,
        max_image_bytes=1000, max_total_image_bytes=10000,
        tokens_per_complete_view_upper_bound=250, provider_evidence_sha256='a' * 64,
        issuer_actor=uuid4(), reviewer_actor=uuid4(), valid_from=now, expires_at=q.expires_at)
    policy_hash = digest(policy.model_dump(mode='json'))
    q = q.model_copy(update={'vision_token_policy_sha256': policy_hash})
    dimensions = tuple((4000, 4000, 100) for _ in range(q.view_count))
    provider, recorder, q2, now2, native, wires, sent = _open(
        monkeypatch, quote=(q, now), vision_policy=policy, expected_vision=policy_hash)
    response, actual, _ = _extract(provider, q2, now2, view_dimensions=dimensions)
    assert len(recorder.finishes) == 1
    provider2, recorder2, q3, now3, native2, wires2, sent2 = _open(
        monkeypatch, quote=(q, now), vision_policy=policy, expected_vision=policy_hash)
    with pytest.raises(PermissionError, match='independently admitted native capability'):
        _extract(provider2, q3, now3,
                 view_dimensions=tuple((4001, 4000, 100) for _ in range(q.view_count)))
    assert recorder2.reservations == []
    with pytest.raises(PermissionError, match='vision policy'):
        _open(monkeypatch, quote=(q, now), vision_policy=policy, expected_vision='0' * 64)


def test_legacy_admitted_provider_still_refuses_raw_before_reserve():
    now = datetime.now(timezone.utc)
    request = ProcessingRequest(
        provider='openai', account='invented', endpoint='https://api.openai.com/v1',
        data_classes=frozenset({'synthetic'}), purpose='source-original-reading',
        terms_hash='a' * 64)
    approval = ProcessingApproval(
        **request.model_dump(), expires_at=now + timedelta(minutes=1), register_ref='invented')
    pricing = Pricing(
        provider='openai', model='openai/gpt-6.1-sol', input_per_million_usd=Decimal('2'),
        output_per_million_usd=Decimal('3'), max_output_tokens=100,
        expires_at=now + timedelta(minutes=1), admitted_register_hash='b' * 64)

    class NoIO:
        def reserve(self, **kwargs):
            raise AssertionError('unexpected reservation')

    def no_io(*args, **kwargs):
        raise AssertionError('unexpected provider or allowance read')
    provider = AdmittedProvider(
        request=request, approvals=[approval], pricing=pricing, budget=NoIO(),
        sender=no_io, remaining_daily_allowance=no_io, admitted_register_hash='b' * 64)
    with pytest.raises(PermissionError, match='protected raw original provider required'):
        provider.extract(
            workspace_id=uuid4(), artifact_id=uuid4(), batch_id=uuid4(),
            purpose='source-original-reading', attempt=1,
            input_tokens_upper_bound=10000,
            messages=[{'role': 'user', 'content': 'invented'}])
