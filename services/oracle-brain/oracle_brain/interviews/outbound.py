"""Referral intents and outbound receipts. Referral never auto-contacts anyone."""
from dataclasses import dataclass
from typing import Optional

STATUSES = frozenset({'recorded', 'sent', 'failed'})


@dataclass(frozen=True)
class ReferralIntent:
    intent_id: str
    interview_id: str
    referred_role: str
    reason: str
    created_at: str


@dataclass(frozen=True)
class OutboundReceipt:
    receipt_id: str
    intent_id: str
    status: str
    channel: Optional[str] = None
    sent_at: Optional[str] = None
    provider_message_id: Optional[str] = None


def record_referral(*, intent_id: str, interview_id: str, referred_role: str,
                    reason: str, created_at: str) -> ReferralIntent:
    """Record a referral the employee made. This function never sends anything."""
    if not intent_id or not interview_id or not referred_role or not reason:
        raise ValueError('referral intent requires id, interview, role and reason')
    return ReferralIntent(intent_id, interview_id, referred_role, reason, created_at)


def receipt_recorded(intent: ReferralIntent, *, receipt_id: str) -> OutboundReceipt:
    """The only receipt produced by asking. Status stays 'recorded' until a separate
    authorized send action attaches a real delivery receipt."""
    return OutboundReceipt(receipt_id, intent.intent_id, 'recorded')


def receipt_sent(intent_id: str, *, receipt_id: str, channel: str,
                 sent_at: str, provider_message_id: str) -> OutboundReceipt:
    """Attach a delivery receipt for a send that a separate actor performed."""
    if not all((intent_id, receipt_id, channel, sent_at, provider_message_id)):
        raise ValueError('sent receipt requires complete delivery fields')
    return OutboundReceipt(receipt_id, intent_id, 'sent', channel, sent_at, provider_message_id)


def receipt_failed(intent_id: str, *, receipt_id: str, channel: str) -> OutboundReceipt:
    if not all((intent_id, receipt_id, channel)):
        raise ValueError('failed receipt requires intent, receipt and channel')
    return OutboundReceipt(receipt_id, intent_id, 'failed', channel)
