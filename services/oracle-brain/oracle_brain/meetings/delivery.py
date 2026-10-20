"""Meeting outbound intents, provider idempotency keys and durable receipts.

Recording an intent never sends. Only a separate authorized send actor may
attach a delivery receipt. Replay of an existing idempotency key returns the
prior receipt and must not produce a second provider call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Optional
from weakref import WeakSet

INTENT_STATUSES = frozenset({'recorded', 'sent', 'failed'})
RECEIPT_STATUSES = frozenset({'recorded', 'sent', 'failed'})
# Only these sender roles may mark an intent sent or failed. Recording an
# intent is open to the ledger; attaching a delivery receipt is a separate
# authorized act. A role name is never believed on its own — the caller must
# present a sealed SenderAuthority capability.
AUTHORIZED_SENDER_ROLES = frozenset({'delivery_sender', 'oracle_sender'})

# Constructor-private mint token: the proof held by the authenticated delivery
# boundary. Ordinary callers never see it, so they cannot mint an authority.
_MINT_TOKEN = object()
# Instances minted under that token. Membership is the use-site proof, so a
# look-alike built with object.__new__ (even with copied attributes) is denied.
_MINTED: WeakSet = WeakSet()


class SenderAuthority:
    """Capability proving the holder is an authorized delivery sender.

    Construction is sealed by the constructor-private mint token; only
    ``issue_sender_authority`` (which holds that token) mints instances. A
    claimed role string or a forged instance is not an authority.
    """
    __slots__ = ('_role', '__weakref__')

    def __init__(self, role: str = '', mint_token: object = None) -> None:
        if mint_token is not _MINT_TOKEN:
            raise PermissionError('sender authority cannot be forged')
        if role not in AUTHORIZED_SENDER_ROLES:
            raise PermissionError('sender role not authorized')
        self._role = role
        _MINTED.add(self)


def issue_sender_authority(role: str, *, mint_token: object = None) -> SenderAuthority:
    """Sealed authorizer: mint a sender capability for an authenticated principal.

    Call only after the principal's credential has been proven. The mint token
    is constructor-private proof; a bare role claim is never accepted.
    """
    return SenderAuthority(role, mint_token=mint_token)


def _require_proven_sender(sender) -> SenderAuthority:
    """Deny unless the caller presents a minted SenderAuthority.

    Unproven claims — None, a role string, a forged instance — are refused.
    """
    if not isinstance(sender, SenderAuthority) or sender not in _MINTED:
        raise PermissionError('sender authority required to mark delivery')
    return sender


def _deny_role_claim(sender_role: str) -> None:
    """A caller-supplied role claim is never proof of who sent."""
    if sender_role:
        raise PermissionError('sender role claim is not proof; present a sender authority')


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
                  sent_at: str, provider_message_id: str,
                  sender=None, sender_role: str = '') -> DeliveryReceipt:
        """Attach a delivery receipt for a send a separate authorized actor performed.

        Only the holder of a sealed SenderAuthority may mark sent. A claimed
        ``sender_role`` is never proof and is denied. Replay by an authorized
        sender is idempotent: a prior sent receipt is returned unchanged.
        """
        _deny_role_claim(sender_role)
        _require_proven_sender(sender)
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

    def mark_failed(self, idempotency_key: str, *, receipt_id: str, channel: str,
                    sender=None, sender_role: str = '') -> DeliveryReceipt:
        """Attach a failure receipt. Same authorized-sender boundary as mark_sent."""
        _deny_role_claim(sender_role)
        _require_proven_sender(sender)
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
