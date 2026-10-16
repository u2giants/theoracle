"""Referral intents and outbound receipts. Referral never contacts anyone."""
from oracle_brain.interviews.outbound import (
    receipt_failed, receipt_recorded, receipt_sent, record_referral,
)


def _intent(**kw):
    base = dict(intent_id='ri-1', interview_id='iv-1', referred_role='approver',
                reason='cutoff owner', created_at='2026-10-16T12:00:00Z')
    base.update(kw)
    return record_referral(**base)


def test_record_referral_creates_intent_only_never_sends():
    intent = _intent()
    receipt = receipt_recorded(intent, receipt_id='ob-1')
    assert receipt.status == 'recorded' and receipt.channel is None and receipt.sent_at is None
    assert intent.referred_role == 'approver'


def test_sent_receipt_needs_complete_delivery_fields():
    intent = _intent()
    ok = receipt_sent(intent.intent_id, receipt_id='ob-2', channel='teams',
                      sent_at='2026-10-16T12:05:00Z', provider_message_id='m-1')
    assert ok.status == 'sent' and ok.provider_message_id == 'm-1'
    try:
        receipt_sent(intent.intent_id, receipt_id='ob-3', channel='teams',
                     sent_at='', provider_message_id='m-2')
    except ValueError:
        pass
    else:
        raise AssertionError('incomplete sent receipt must fail')


def test_failed_receipt_is_visible_not_silent():
    r = receipt_failed('ri-1', receipt_id='ob-4', channel='teams')
    assert r.status == 'failed' and r.sent_at is None
