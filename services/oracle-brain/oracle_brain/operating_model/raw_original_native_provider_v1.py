"""Protected exact raw multimodal native constructor. Confers no admission.

The default AdmittedProvider keeps refusing raw purposes before
allowance/reserve/POST. This closed constructor is the separately appointed
raw path: exact current selected-endpoint quote, genuine complete PNG parts,
independently pinned vision policy, and the same central Budget reserve/finish
before any private POST. Source-only invented keys/provider. No model
catalogue price is used as the selected endpoint price.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
from typing import Literal
from uuid import UUID

from oracle_brain.provider_transport import transport_options
from oracle_brain.provider_policy import ProcessingRequest

from .contracts import digest
from .native_provider import NativeOpenRouter
from .provider_adapter import Budget, ProviderQuotaError
from .raw_multimodal_pricing_v1 import (
    RawMultimodalPricingQuoteV1,
    raw_multimodal_reservation_maximum_v1,
)
from .raw_vision_policy_v1 import RawVisionTokenPolicyV1, verify_raw_vision_quote_v1

RAW_PURPOSES = frozenset({'source-original-reading', 'source-original-review'})
_DATA_PNG_PREFIX = 'data:image/png;base64,'


def verify_raw_png_parts_v1(messages, quote):
    """Pure complete-PNG shape control. Omission/substitution/remote/text-base64 deny.

    Byte sizes come only from actual decoded PNG payloads. Image tokens remain
    the independently appointed quote/vision bound, never base64 text length.
    """
    if type(quote) is not RawMultimodalPricingQuoteV1:
        raise PermissionError('exact independently admitted raw quote required')
    if type(messages) is not list or len(messages) != 2:
        raise PermissionError('exact system and user raw multimodal messages required')
    system, user = messages
    if (not isinstance(system, dict) or system.get('role') != 'system'
            or not isinstance(system.get('content'), str) or not system['content']
            or not isinstance(user, dict) or user.get('role') != 'user'
            or type(user.get('content')) is not list or not user['content']):
        raise PermissionError('exact fixed raw multimodal message shape required')
    sizes = []
    for part in user['content']:
        if not isinstance(part, dict):
            raise PermissionError('exact raw multimodal content parts required')
        kind = part.get('type')
        if kind == 'text':
            text = part.get('text')
            if not isinstance(text, str) or not text:
                raise PermissionError('nonempty raw text part required')
            if text.startswith(_DATA_PNG_PREFIX) or text.startswith('data:image/') or text.startswith('http'):
                raise PermissionError('genuine image parts only; never text-base64 or remote URL')
        elif kind == 'image_url':
            image = part.get('image_url')
            if not isinstance(image, dict) or set(image) != {'url', 'detail'} or image.get('detail') != 'high':
                raise PermissionError('exact high-detail genuine PNG image part required')
            url = image.get('url')
            if not isinstance(url, str) or not url.startswith(_DATA_PNG_PREFIX):
                raise PermissionError('genuine inline PNG image parts only; never remote URL or foreign type')
            try:
                png = base64.b64decode(url[len(_DATA_PNG_PREFIX):], validate=True)
            except (binascii.Error, ValueError):
                raise PermissionError('actual complete PNG payload required') from None
            if not png or png[:8] != b'\x89PNG\r\n\x1a\n':
                raise PermissionError('actual complete PNG payload required')
            sizes.append(len(png))
        else:
            raise PermissionError('exact text or genuine PNG image parts only')
    if (len(sizes) != quote.view_count
            or sum(sizes) != quote.total_image_bytes
            or (sizes and max(sizes) != quote.largest_image_bytes)
            or any(size <= 0 or size > quote.model_max_image_bytes for size in sizes)):
        raise PermissionError('actual complete all-view PNG population differs from the admitted quote')
    return tuple(sizes)


class RawOriginalNativeProviderV1:
    """Exact closed raw constructor; only the factory function builds it."""

    operation: Literal['chat'] = 'chat'

    def __init__(self, *, quote, expected_quote_sha256, budget, sender,
                 remaining_daily_allowance, admitted_register_hash,
                 processing_request, expected_vision_policy_sha256=None,
                 vision_policy=None):
        if type(quote) is not RawMultimodalPricingQuoteV1:
            raise PermissionError('exact independently admitted raw quote required')
        quote = RawMultimodalPricingQuoteV1.model_validate(quote.model_dump(mode='python'))
        if (digest(quote.model_dump(mode='json')) != expected_quote_sha256
                or quote.admitted_register_hash != admitted_register_hash
                or quote.issuer_actor == quote.reviewer_actor):
            raise PermissionError('current exact raw quote binding required')
        if type(budget) is not Budget:
            raise PermissionError('exact central Budget required')
        native = getattr(sender, '__self__', None)
        if (not isinstance(native, NativeOpenRouter)
                or getattr(sender, '__func__', None) is not NativeOpenRouter.send):
            raise PermissionError('protected raw native sender required')
        if (type(processing_request) is not ProcessingRequest
                or processing_request.account != 'key-sha256:' + native.key_fingerprint
                or processing_request.provider != 'openrouter'
                or processing_request.endpoint != 'https://openrouter.ai/api/v1'
                or processing_request.fallback
                or processing_request.purpose not in RAW_PURPOSES
                or quote.account != processing_request.account):
            raise PermissionError('exact existing key and source-only raw processing admission required')
        if getattr(remaining_daily_allowance, '__func__', None) is not NativeOpenRouter.allowance:
            raise PermissionError('native admitted key allowance required')
        if getattr(remaining_daily_allowance, '__self__', None) is not native:
            raise PermissionError('native sender, admitted key allowance and central ledger must share one binding')
        if budget.ledger_identity_hash != native.ledger_identity_hash:
            raise PermissionError('native sender, admitted key allowance and central ledger must share one binding')
        if vision_policy is not None or expected_vision_policy_sha256 is not None:
            if (type(vision_policy) is not RawVisionTokenPolicyV1
                    or expected_vision_policy_sha256 is None
                    or digest(vision_policy.model_dump(mode='json')) != expected_vision_policy_sha256
                    or vision_policy.model != quote.model
                    or quote.vision_token_policy_sha256 != expected_vision_policy_sha256):
                raise PermissionError('independently pinned model-specific vision policy required')
        self.quote = quote
        self.expected_quote_sha256 = expected_quote_sha256
        self.budget = budget
        self.sender = sender
        self.remaining_daily_allowance = remaining_daily_allowance
        self.admitted_register_hash = admitted_register_hash
        self.processing_request = processing_request
        self.vision_policy = vision_policy
        self.expected_vision_policy_sha256 = expected_vision_policy_sha256
        self.last_reservation_id = None

    def correction_contract(self, *, workspace_id, artifact_id, batch_id, purpose,
                            input_tokens_upper_bound, messages):
        return digest({'workspace_id': str(workspace_id), 'artifact_id': str(artifact_id),
                       'batch_id': str(batch_id), 'purpose': purpose, 'messages': messages,
                       'processing_request': self.processing_request.model_dump(mode='json'),
                       'pricing': self.quote.model_dump(mode='json'),
                       'register_hash': self.admitted_register_hash,
                       'input_tokens_upper_bound': input_tokens_upper_bound})

    def extract_raw(self, *, workspace_id: UUID, artifact_id: UUID, batch_id: UUID,
                    purpose: str, attempt: int, messages: list, input_tokens_upper_bound: int,
                    now, response_validator=None, view_dimensions=None):
        if purpose not in RAW_PURPOSES or purpose != self.processing_request.purpose:
            raise PermissionError('exact raw original phase required')
        if attempt not in (1, 2) or type(attempt) is not int:
            raise ValueError('bounded raw attempt required')
        if type(input_tokens_upper_bound) is not int or isinstance(input_tokens_upper_bound, bool):
            raise ValueError('bounded input token count required')
        if (input_tokens_upper_bound
                != self.quote.text_input_tokens_upper_bound + self.quote.vision_input_tokens_upper_bound):
            raise PermissionError('exact quote-bound input reservation required')
        if now.tzinfo is None:
            raise PermissionError('aware raw dispatch time required')
        if self.quote.expires_at <= now or self.quote.valid_from > now:
            raise PermissionError('current exact raw cost/context quote required')
        sizes = verify_raw_png_parts_v1(messages, self.quote)
        if view_dimensions is not None or self.vision_policy is not None:
            if view_dimensions is None or self.vision_policy is None:
                raise PermissionError('independently pinned model-specific vision policy required')
            verify_raw_vision_quote_v1(
                self.quote, self.vision_policy, view_dimensions,
                expected_policy_sha256=self.expected_vision_policy_sha256, now=now)
        maximum = raw_multimodal_reservation_maximum_v1(
            self.quote, expected_quote_sha256=self.expected_quote_sha256,
            input_tokens_upper_bound=input_tokens_upper_bound, purpose=purpose, now=now)
        if self.remaining_daily_allowance is None:
            raise PermissionError('authoritative remaining daily allowance unavailable')
        allowance = self.remaining_daily_allowance()
        if maximum > allowance:
            raise PermissionError('current remaining daily allowance cannot fund dispatch')
        opts = transport_options(self.processing_request, self.quote.model, operation='chat')
        rid = self.budget.reserve(
            workspace_id=workspace_id, artifact_id=artifact_id, batch_id=batch_id,
            purpose=purpose, attempt=attempt, maximum=maximum,
            pricing_hash=digest(self.quote.model_dump(mode='json')),
            account_remaining=allowance,
            correction_hash=self.correction_contract(
                workspace_id=workspace_id, artifact_id=artifact_id, batch_id=batch_id,
                purpose=purpose, input_tokens_upper_bound=input_tokens_upper_bound,
                messages=messages))
        self.last_reservation_id = rid
        try:
            response, actual = self.sender(
                messages=messages, model=self.quote.model,
                max_output_tokens=self.quote.max_output_tokens, store=False, **opts)
        except Exception as error:
            # Unknown liability retains the full conservative reservation.
            self.budget.finish(
                rid, actual_usd=maximum, failed=True, response_hash=None,
                failure_kind='quota_exhausted' if isinstance(error, ProviderQuotaError)
                else 'transport_failure')
            raise RuntimeError('admitted raw extraction dispatch failed; private response not logged') from None
        valid = True
        if response_validator is not None:
            try:
                response_validator(response)
            except (ValueError, TypeError, KeyError):
                valid = False
        if isinstance(response, str):
            response_hash = hashlib.sha256(response.encode()).hexdigest()
        else:
            response_hash = digest({'response': response}) if response is not None else None
        self.budget.finish(
            rid, actual_usd=actual, failed=not valid, response_hash=response_hash,
            failure_kind=None if valid else 'invalid_output')
        return response, actual, sizes


def open_raw_original_native_v1(*, quote, expected_quote_sha256, budget, sender,
                                remaining_daily_allowance, admitted_register_hash,
                                processing_request, expected_vision_policy_sha256=None,
                                vision_policy=None):
    """Factory for the exact closed raw constructor. No authority is issued here."""
    return RawOriginalNativeProviderV1(
        quote=quote, expected_quote_sha256=expected_quote_sha256, budget=budget,
        sender=sender, remaining_daily_allowance=remaining_daily_allowance,
        admitted_register_hash=admitted_register_hash,
        processing_request=processing_request,
        expected_vision_policy_sha256=expected_vision_policy_sha256,
        vision_policy=vision_policy)
