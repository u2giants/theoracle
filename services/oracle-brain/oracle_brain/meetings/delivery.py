"""Meeting outbound intents, provider idempotency keys and durable receipts.

Recording an intent never sends. Only a separate authorized send actor may
attach a delivery receipt. Replay of an existing idempotency key returns the
prior receipt and must not produce a second provider call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Optional

INTENT_STATUSES = frozenset({'recorded', 'sent', 'failed'})
RECEIPT_STATUSES = frozenset({'recorded', 'sent', 'failed'})


@dataclass(frozen=True)
class OutboundIntent:
    """What Oracle intends to say in a meeting. Creating one is not a send."""
    intent_id: str
    meeting_id: str
    turn_id: str
    channel: str
    body: str
    idempotency_key: str
    created_at: str

    def __post_init__(self) -> None:
        if not all((self.intent_id, self.meeting_id, self.turn_id, self.channel,
                    self.body.strip(), self.idempotency_key, self.created_at)):
            raise ValueError('outbound intent requires complete identity and body')
        if self.channel not in ('meeting_text', 'meeting_chat'):
            raise ValueError('unsupported outbound channel')


@dataclass(frozen=True)
class DeliveryReceipt:
    """Durable delivery outcome bound to one provider idempotency key."""
    receipt_id: str
    intent_id: str
    idempotency_key: str
    status: str
    channel: Optional[str] = None
    sent_at: Optional[str] = None
    provider_message_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.receipt_id or not self.intent_id or not self.idempotency_key:
            raise ValueError('delivery receipt identity required')
        if self.status not in RECEIPT_STATUSES:
            raise ValueError('unsupported delivery receipt status')


@dataclass
class DeliveryLedger:
    """Append-only map from provider idempotency key to the single receipt.

    A replay under an existing key returns the stored receipt. Conflicting
    content under the same key fails visibly rather than silently re-sending.
    """
    _by_key: dict = field(default_factory=dict)
    _body_by_key: dict = field(default_factory=dict)

    def record_intent(self, intent: OutboundIntent) -> DeliveryReceipt:
        """Record intent only. Status stays 'recorded' until a separate send."""
        existing = self._by_key.get(intent.idempotency_key)
        if existing is not None:
            prior_body = self._body_by_key.get(intent.idempotency_key)
            if prior_body != intent.body:
                raise ValueError('conflicting outbound body under idempotency key')
            return existing
        receipt = DeliveryReceipt(
            receipt_id=f'dr-{intent.intent_id}', intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key, status='recorded')
        self._by_key[intent.idempotency_key] = receipt
        self._body_by_key[intent.idempotency_key] = intent.body
        return receipt

    def mark_sent(self, idempotency_key: str, *, receipt_id: str, channel: str,
                  sent_at: str, provider_message_id: str) -> DeliveryReceipt:
        """Attach a delivery receipt for a send a separate authorized actor performed."""
        if not all((channel, sent_at, provider_message_id)):
            raise ValueError('sent receipt requires channel, sent_at and provider_message_id')
        prior = self._by_key.get(idempotency_key)
        if prior is None:
            raise ValueError('unknown idempotency key')
        if prior.status == 'sent':
            return prior
        receipt = DeliveryReceipt(
            receipt_id, prior.intent_id, idempotency_key, 'sent',
            channel=channel, sent_at=sent_at, provider_message_id=provider_message_id)
        self._by_key[idempotency_key] = receipt
        return receipt

    def mark_failed(self, idempotency_key: str, *, receipt_id: str, channel: str) -> DeliveryReceipt:
        if not channel:
            raise ValueError('failed receipt requires channel')
        prior = self._by_key.get(idempotency_key)
        if prior is None:
            raise ValueError('unknown idempotency key')
        if prior.status == 'sent':
            return prior
        receipt = DeliveryReceipt(
            receipt_id, prior.intent_id, idempotency_key, 'failed', channel=channel)
        self._by_key[idempotency_key] = receipt
        return receipt

    def replay(self, idempotency_key: str) -> Optional[DeliveryReceipt]:
        """Return the durable receipt for a key, or None when never recorded."""
        return self._by_key.get(idempotency_key)


def provider_idempotency_key(*, meeting_id: str, intent_id: str, channel: str) -> str:
    """Deterministic provider key for one logical send. Retries reuse the key;
    the body is payload and a different body under the same key conflicts."""
    if not all((meeting_id, intent_id, channel)):
        raise ValueError('idempotency key requires meeting, intent and channel')
    value = (meeting_id, intent_id, channel)
    return sha256(repr(value).encode()).hexdigest()


def create_intent(*, intent_id: str, meeting_id: str, turn_id: str, channel: str,
                  body: str, created_at: str) -> OutboundIntent:
    """Build an outbound intent. This function never sends anything."""
    key = provider_idempotency_key(
        meeting_id=meeting_id, intent_id=intent_id, channel=channel)
    return OutboundIntent(
        intent_id=intent_id, meeting_id=meeting_id, turn_id=turn_id,
        channel=channel, body=body, idempotency_key=key, created_at=created_at)


def intent_recorded(ledger: DeliveryLedger, intent: OutboundIntent) -> DeliveryReceipt:
    """The only receipt produced by deciding to speak. Delivery is separate."""
    return ledger.record_intent(intent)
