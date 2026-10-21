"""Qualification runtime unit contracts; invented metadata only, no custody."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from oracle_brain.operating_model.contracts import digest
from oracle_brain.operating_model.original_qualification_runtime import (
    PhaseCommitRecordV1,
    QualificationCustodyStoreV1,
    QualificationConflict,
    QualificationDenied,
    SourceReadingQualificationV1,
    build_paid_response_body_v1,
    seal_response_body_v1,
    synthesize_raw_png_messages_v1,
    verify_raw_png_parts_v1,
)
from oracle_brain.operating_model.raw_multimodal_pricing_v1 import RawMultimodalPricingQuoteV1


def _now():
    return datetime.now(timezone.utc)


def _hashes():
    return {k: f'{i:x}' * 64 for i, k in enumerate([
        'operation_registry_hash', 'original_root_hash', 'allocation_hash',
        'population_hash', 'source_registry_hash', 'context_hash',
        'view_manifest_hash', 'locator_map_hash', 'reading_body_hash',
        'native_job_hash', 'request_hash', 'raw_wire_hash', 'model_content_hash',
        'native_custody_receipt_hash', 'authorized_phase_commit_hash',
        'reading_population_id', 'reading_operation_registry_hash', 'review_body_hash'], 0)}


def _raw_ref(**over):
    from oracle_brain.operating_model.original_qualification_v1 import RawOriginalRefV1
    from uuid import uuid4
    base = dict(workspace_id=uuid4(), source_id=uuid4(), revision=1,
                original_sha256='a' * 64, byte_count=10, media_type='application/pdf',
                filename='invented.pdf', custody_locator_seal_sha256='b' * 64)
    base.update(over)
    return RawOriginalRefV1(**base)


def _commit_record(*, purpose='source-original-reading', principal=None, role='reader_login',
                   model='openai/gpt-6.1-sol', commit='c' * 64, reading_commit_hash=None):
    return PhaseCommitRecordV1(
        commit_sha256=commit, purpose=purpose,
        principal_id=principal or uuid4(), session_role=role,
        workspace_id=uuid4(), source_id=uuid4(), revision=1,
        original_sha256='a' * 64, reading_sha256='d' * 64, parser_id='e' * 64,
        view_manifest_sha256='f' * 64, locator_map_sha256='1' * 64,
        reading_commit_hash=reading_commit_hash, model_id=model,
        canonical_body=b'{}')


def test_finalize_requires_both_commits_and_denies_partial():
    store = QualificationCustodyStoreV1()
    reading = _commit_record()
    store.commit_phase(reading)
    with pytest.raises(QualificationDenied, match='complete reading and review'):
        store.finalize_qualification(
            reading_commit_hash=reading.commit_sha256,
            review_commit_hash='9' * 64, parser_id='e' * 64)


def test_finalize_denies_same_reviewer_as_reader():
    store = QualificationCustodyStoreV1()
    shared = uuid4()
    reading = _commit_record(principal=shared, role='reader_login', model='openai/gpt-6.1-sol')
    review = _commit_record(purpose='source-original-review', principal=shared,
                            role='reader_login', model='openai/gpt-6-astra',
                            commit='d' * 64, reading_commit_hash=reading.commit_sha256)
    # Force the same workspace/source so the identity check is the one that fires.
    review = review.model_copy(update={
        'workspace_id': reading.workspace_id, 'source_id': reading.source_id})
    store.commit_phase(reading)
    store.commit_phase(review)
    with pytest.raises(QualificationDenied, match='late distinct reviewer'):
        store.finalize_qualification(
            reading_commit_hash=reading.commit_sha256,
            review_commit_hash=review.commit_sha256, parser_id='e' * 64)


def test_finalize_denies_same_reviewer_model():
    store = QualificationCustodyStoreV1()
    reading = _commit_record(model='openai/gpt-6.1-sol')
    review = _commit_record(purpose='source-original-review', role='reviewer_login',
                            model='openai/gpt-6.1-sol', commit='d' * 64,
                            reading_commit_hash=reading.commit_sha256)
    review = review.model_copy(update={
        'workspace_id': reading.workspace_id, 'source_id': reading.source_id})
    store.commit_phase(reading)
    store.commit_phase(review)
    with pytest.raises(QualificationDenied, match='distinct reviewer model'):
        store.finalize_qualification(
            reading_commit_hash=reading.commit_sha256,
            review_commit_hash=review.commit_sha256, parser_id='e' * 64)


def test_finalize_denies_review_that_does_not_name_the_reading():
    store = QualificationCustodyStoreV1()
    reading = _commit_record()
    review = _commit_record(purpose='source-original-review', role='reviewer_login',
                            model='openai/gpt-6-astra', commit='d' * 64,
                            reading_commit_hash='0' * 64)
    review = review.model_copy(update={
        'workspace_id': reading.workspace_id, 'source_id': reading.source_id})
    store.commit_phase(reading)
    store.commit_phase(review)
    with pytest.raises(QualificationDenied, match='independent historical original reading'):
        store.finalize_qualification(
            reading_commit_hash=reading.commit_sha256,
            review_commit_hash=review.commit_sha256, parser_id='e' * 64)


def test_finalize_inserts_once_then_second_insert_is_denied():
    store = QualificationCustodyStoreV1()
    reading = _commit_record()
    review = _commit_record(purpose='source-original-review', role='reviewer_login',
                            model='openai/gpt-6-astra', commit='d' * 64,
                            reading_commit_hash=reading.commit_sha256)
    review = review.model_copy(update={
        'workspace_id': reading.workspace_id, 'source_id': reading.source_id})
    store.commit_phase(reading)
    store.commit_phase(review)
    row = store.finalize_qualification(
        reading_commit_hash=reading.commit_sha256,
        review_commit_hash=review.commit_sha256, parser_id='e' * 64)
    assert row.reader_principal_id != row.reviewer_principal_id
    ref = store.source_ref(row.workspace_id, row.source_id, row.revision)
    assert ref is not None and ref.reading_sha256 == 'd' * 64
    with pytest.raises(QualificationConflict, match='already finalized'):
        store.finalize_qualification(
            reading_commit_hash=reading.commit_sha256,
            review_commit_hash=review.commit_sha256, parser_id='e' * 64)


def test_no_source_ref_before_finalize():
    store = QualificationCustodyStoreV1()
    reading = _commit_record()
    store.commit_phase(reading)
    assert store.source_ref(reading.workspace_id, reading.source_id, reading.revision) is None
    assert store.qualification(reading.workspace_id, reading.source_id, reading.revision) is None


def test_qualification_row_enforces_distinct_principals():
    shared = uuid4()
    with pytest.raises(ValueError, match='distinct from the reader'):
        SourceReadingQualificationV1(
            workspace_id=uuid4(), source_id=uuid4(), revision=1,
            original_sha256='a' * 64, reading_sha256='b' * 64, parser_id='p',
            view_manifest_sha256='c' * 64, locator_map_sha256='d' * 64,
            reader_native_commit_sha256='e' * 64, reviewer_native_commit_sha256='f' * 64,
            reader_principal_id=shared, reviewer_principal_id=shared)


def test_build_paid_response_body_reading_and_review_shapes():
    ref = _raw_ref()
    hashes = _hashes()
    now = _now()
    reading = build_paid_response_body_v1(
        raw_ref=ref, population_id=uuid4(), hashes=hashes, purpose='reading',
        reading_sha256='d' * 64, parser_id='e' * 64,
        committed_at=now, original_horizon=now + timedelta(seconds=40))
    assert reading['purpose'] == 'observed-authorized-original-reading-response-v1'
    assert 'qualification_pass' not in reading
    review = build_paid_response_body_v1(
        raw_ref=ref, population_id=uuid4(), hashes=hashes, purpose='review',
        reading_commit_hash='a' * 64, reading_sha256='d' * 64, parser_id='e' * 64,
        committed_at=now, original_horizon=now + timedelta(seconds=40),
        qualification_pass=True)
    assert review['purpose'] == 'observed-authorized-original-review-response-v1'
    assert review['qualification_pass'] is True
    assert review['reading_commit_hash'] == 'a' * 64


def test_seal_response_body_round_trips_closed_parser():
    ref = _raw_ref()
    hashes = _hashes()
    now = _now()
    body = build_paid_response_body_v1(
        raw_ref=ref, population_id=uuid4(), hashes=hashes, purpose='reading',
        reading_sha256='d' * 64, parser_id='e' * 64,
        committed_at=now, original_horizon=now + timedelta(seconds=40))
    raw = seal_response_body_v1(body)
    assert isinstance(raw, bytes) and raw
    from oracle_brain.operating_model.original_qualification_v1 import parse_original_response_commit_v1
    parsed = parse_original_response_commit_v1(raw, phase='reading')
    assert parsed.reading_sha256 == 'd' * 64


def test_seal_response_body_rejects_open_transport():
    body = {'schema_version': 1, 'transport': 'caller-selected', 'purpose': 'x'}
    with pytest.raises(ValueError):
        seal_response_body_v1(body)


def test_synthesized_png_messages_bind_exact_quote_sizes():
    sizes = (100,) * 7
    messages = synthesize_raw_png_messages_v1(
        prompt='Fixed invented reading task', view_count=7, image_sizes=sizes)
    q = RawMultimodalPricingQuoteV1(
        model='openai/gpt-6.1-sol', account='invented-only', terms_hash='a' * 64,
        key_fingerprint='b' * 64, ledger_registry_hash='c' * 64, catalogue_sha256='d' * 64,
        pricing_policy_sha256='e' * 64, vision_token_policy_sha256='f' * 64,
        model_capability_sha256='1' * 64, dispatch_id=uuid4(), request_hash='2' * 64,
        view_manifest_hash='3' * 64, population_id=uuid4(), original_root_hash='4' * 64,
        original_allocation_hash='5' * 64, original_horizon=_now() + timedelta(seconds=90),
        view_count=7, total_image_bytes=700, largest_image_bytes=100,
        model_max_images=10, model_max_image_bytes=1000, model_context_tokens=100000,
        text_input_tokens_upper_bound=1000, vision_input_tokens_upper_bound=2000,
        input_per_million_usd=__import__('decimal').Decimal('1'),
        input_cache_write_per_million_usd=__import__('decimal').Decimal('2'),
        output_per_million_usd=__import__('decimal').Decimal('4'), max_output_tokens=100,
        per_image_fee_usd=__import__('decimal').Decimal('.001'),
        per_request_fee_usd=__import__('decimal').Decimal('.002'), is_byok=True,
        upstream_input_per_million_usd=__import__('decimal').Decimal('3'),
        upstream_output_per_million_usd=__import__('decimal').Decimal('5'),
        upstream_per_image_fee_usd=__import__('decimal').Decimal('.003'),
        upstream_per_request_fee_usd=__import__('decimal').Decimal('.004'),
        admitted_register_hash='6' * 64, valid_from=_now(),
        expires_at=_now() + timedelta(seconds=60), issuer_actor=uuid4(), reviewer_actor=uuid4())
    assert verify_raw_png_parts_v1(messages, q) == sizes
    # Omission is denied.
    truncated = [messages[0], {'role': 'user', 'content': messages[1]['content'][:-2]}]
    with pytest.raises(PermissionError):
        verify_raw_png_parts_v1(truncated, q)
