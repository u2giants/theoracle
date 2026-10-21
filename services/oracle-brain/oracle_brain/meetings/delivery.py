"""Meeting outbound intents, provider idempotency keys and durable receipts.

Recording an intent never sends. Only a separate authorized send action may
attach a delivery receipt. Replay of an existing idempotency key returns the
prior receipt and must not produce a second provider call.

Authority is the Ed25519 signature alone. ``mark_sent``/``mark_failed``
verify a host-issued signature over ledger identity, the complete immutable
intent, receipt/provider outcome, expiry and a single-use nonce. There is no mutable in-process mint registry:
forged capability objects and ``__closure__`` registry mutation attempts
are irrelevant because no registry exists to mutate.
"""
from __future__ import annotations

import json
import math
import time
from uuid import uuid4
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Optional

from oracle_brain.seal import verify_mac

INTENT_STATUSES = frozenset({'recorded', 'sent', 'failed'})
RECEIPT_STATUSES = frozenset({'recorded', 'sent', 'failed'})
# Only these sender roles may be named in a sealed sender credential.
# Recording an intent is open to the ledger; attaching a delivery receipt
# requires a host-issued action signature, never a role string.
AUTHORIZED_SENDER_ROLES = frozenset({'delivery_sender', 'oracle_sender'})
# Purpose pin on sender credentials. The credential's authority is its
# Ed25519 signature over (principal_id, role, expires_at) — never a
# registry membership.
SENDER_CREDENTIAL_PURPOSE = 'sender-credential:v1'
# Purpose pin on delivery actions. ``mark_sent``/``mark_failed`` verify a
# signature over the exact action payload under this purpose.
DELIVERY_ACTION_PURPOSE = 'delivery-action:v1'


class SenderCredentialProof:
    """Signed credential material presented by the authz/authority layer.

    Authority is the Ed25519 ``mac`` over (principal_id, role, expires_at)
    issued by the isolated signer under ``SENDER_CREDENTIAL_PURPOSE``.
    Instances are built by ``issue_sender_credential_proof`` after the mac
    verifies; direct construction is refused. A look-alike built with
    ``object.__new__`` carries no valid signature and is denied at verify
    time. Holding this record is not send authority by itself: delivery
    actions are separately signed.
    """
    __slots__ = ('_principal_id', '_role', '_expires_at', '_purpose', '_mac',
                 '__weakref__')

    def __init__(self, *args, **kwargs) -> None:
        raise PermissionError('sender credential proof cannot be forged')

    @property
    def principal_id(self) -> str:
        return self._principal_id

    @property
    def role(self) -> str:
        return self._role

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    @property
    def purpose(self) -> str:
        return self._purpose

    @property
    def mac(self) -> str:
        return self._mac


def issue_sender_credential_proof(*, principal_id: str, role: str,
                                  expires_at: datetime,
                                  mac: str) -> SenderCredentialProof:
    """Sealed authz/authority boundary: present signed credential material.

    ``mac`` must be a host-identity-service Ed25519 seal over
    (principal_id, role, expires_at, purpose) issued by the isolated
    signer. Without a valid seal the call is denied — caller-chosen
    fields alone never mint a proof. The proof carries the signature;
    there is no registry membership to forge or mutate.
    """
    if not principal_id or not role:
        raise ValueError('sender credential identity and role required')
    if (not isinstance(expires_at, datetime)
            or expires_at.tzinfo is None
            or expires_at.utcoffset() is None):
        raise ValueError('sender credential expiry must be timezone-aware')
    verify_mac(SENDER_CREDENTIAL_PURPOSE, mac,
               principal_id, role, expires_at)
    proof = object.__new__(SenderCredentialProof)
    proof._principal_id = principal_id
    proof._role = role
    proof._expires_at = expires_at
    proof._purpose = SENDER_CREDENTIAL_PURPOSE
    proof._mac = mac
    return proof


def verify_sender_principal(proof) -> SenderCredentialProof:
    """Authz boundary: verify the signed credential material.

    ``proof`` must carry a valid ``SENDER_CREDENTIAL_PURPOSE`` signature
    over its own fields. Real checks (signature, purpose, authorized role,
    unexpired window) follow; a field echo is never proof. A look-alike
    built with ``object.__new__`` has no valid signature and is refused.
    No registry is consulted — the signature is the authority.
    """
    if not isinstance(proof, SenderCredentialProof):
        raise PermissionError('sender credential proof required')
    if proof.purpose != SENDER_CREDENTIAL_PURPOSE:
        raise PermissionError('sender credential purpose mismatch')
    verify_mac(SENDER_CREDENTIAL_PURPOSE, proof.mac,
               proof.principal_id, proof.role, proof.expires_at)
    if proof.role not in AUTHORIZED_SENDER_ROLES:
        raise PermissionError('sender role not authorized')
    at = datetime.now(timezone.utc)
    if proof.expires_at <= at:
        raise PermissionError('sender credential expired')
    return proof


def _deny_role_claim(sender_role: str) -> None:
    """A caller-supplied role claim is never proof of who sent."""
    if sender_role:
        raise PermissionError('sender role claim is not proof; present an action signature')




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
    recipient_ids: tuple[str, ...] = ()
    audience_sha256: str = ''

    def __post_init__(self) -> None:
        if not all((self.intent_id, self.meeting_id, self.turn_id, self.channel,
                    self.body.strip(), self.idempotency_key, self.created_at)):
            raise ValueError('outbound intent requires complete identity and body')
        if self.channel not in ('meeting_text', 'meeting_chat'):
            raise ValueError('unsupported outbound channel')


@dataclass(frozen=True)
class DeliveryActionProof:
    """Short-lived exact-action seal; nonce is consumed by one ledger only."""
    expires_at: float
    nonce: str
    mac: str


def delivery_action_payload(*, ledger_id: str, intent: OutboundIntent,
                            status: str, timestamp: str, receipt_id: str,
                            channel: str, provider_message_id: str,
                            expires_at: float, nonce: str) -> str:
    return json.dumps(['delivery-action:v2', ledger_id, asdict(intent), status,
                      timestamp, receipt_id, channel, provider_message_id,
                      expires_at, nonce], sort_keys=True, separators=(',', ':'),
                      allow_nan=False)


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
    _intents_by_key: dict = field(default_factory=dict)
    _used_nonces: set = field(default_factory=set)
    _ledger_id: str = field(default_factory=lambda: uuid4().hex, init=False)

    @property
    def ledger_id(self) -> str:
        return self._ledger_id

    def _verify_action(self, proof, *, intent: OutboundIntent, status: str,
                       timestamp: str, receipt_id: str, channel: str,
                       provider_message_id: str = '') -> None:
        if type(proof) is not DeliveryActionProof:
            raise PermissionError('exact delivery action proof required')
        if (type(proof.expires_at) not in (int, float)
                or not math.isfinite(proof.expires_at)
                or not time.time() < proof.expires_at <= time.time() + 300
                or not isinstance(proof.nonce, str) or len(proof.nonce) < 32
                or proof.nonce in self._used_nonces):
            raise PermissionError('delivery action expired or nonce reused')
        if not timestamp or not receipt_id:
            raise PermissionError('complete delivery receipt identity required')
        if channel != intent.channel:
            raise PermissionError('delivery channel differs from immutable intent')
        verify_mac(DELIVERY_ACTION_PURPOSE, proof.mac,
                   delivery_action_payload(
                       ledger_id=self.ledger_id, intent=intent, status=status,
                       timestamp=timestamp, receipt_id=receipt_id, channel=channel,
                       provider_message_id=provider_message_id,
                       expires_at=proof.expires_at, nonce=proof.nonce))
        self._used_nonces.add(proof.nonce)

    def record_intent(self, intent: OutboundIntent) -> DeliveryReceipt:
        """Record intent only. Status stays 'recorded' until a separate send."""
        existing = self._by_key.get(intent.idempotency_key)
        if existing is not None:
            prior_body = self._body_by_key.get(intent.idempotency_key)
            if prior_body != intent.body or self._intents_by_key.get(intent.idempotency_key) != intent:
                raise ValueError('conflicting outbound body under idempotency key')
            return existing
        receipt = DeliveryReceipt(
            receipt_id=f'dr-{intent.intent_id}', intent_id=intent.intent_id,
            idempotency_key=intent.idempotency_key, status='recorded')
        self._by_key[intent.idempotency_key] = receipt
        self._body_by_key[intent.idempotency_key] = intent.body
        self._intents_by_key[intent.idempotency_key] = intent
        return receipt

    def mark_sent(self, idempotency_key: str, *, receipt_id: str, channel: str,
                  sent_at: str, provider_message_id: str,
                  action_mac: Optional[DeliveryActionProof] = None, sender_role: str = '') -> DeliveryReceipt:
        """Attach a delivery receipt for a send a separate authorized actor performed.

        Authority is ``action_mac``: a short-lived host-issued signature over
        the ledger, immutable intent, complete receipt and single-use nonce.
        A claimed ``sender_role`` is never proof and is denied. Replay is
        idempotent: a prior sent receipt is returned unchanged.
        """
        _deny_role_claim(sender_role)
        if not all((channel, sent_at, provider_message_id)):
            raise ValueError('sent receipt requires channel, sent_at and provider_message_id')
        prior = self._by_key.get(idempotency_key)
        if prior is None:
            raise ValueError('unknown idempotency key')
        if prior.status == 'sent':
            return prior
        self._verify_action(action_mac, intent=self._intents_by_key[idempotency_key],
                            status='sent', timestamp=sent_at, receipt_id=receipt_id,
                            channel=channel, provider_message_id=provider_message_id)
        receipt = DeliveryReceipt(
            receipt_id, prior.intent_id, idempotency_key, 'sent',
            channel=channel, sent_at=sent_at, provider_message_id=provider_message_id)
        self._by_key[idempotency_key] = receipt
        return receipt

    def mark_failed(self, idempotency_key: str, *, receipt_id: str, channel: str,
                    failed_at: str = '', action_mac: Optional[DeliveryActionProof] = None,
                    sender_role: str = '') -> DeliveryReceipt:
        """Attach a failure receipt. Same signed-action boundary as mark_sent.

        Authority is ``action_mac`` over the ledger, immutable intent,
        complete failed receipt, enforced expiry and single-use nonce.
        """
        _deny_role_claim(sender_role)
        if not channel:
            raise ValueError('failed receipt requires channel')
        prior = self._by_key.get(idempotency_key)
        if prior is None:
            raise ValueError('unknown idempotency key')
        if prior.status == 'sent':
            return prior
        self._verify_action(action_mac, intent=self._intents_by_key[idempotency_key],
                            status='failed', timestamp=failed_at, receipt_id=receipt_id,
                            channel=channel)
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
                  body: str, created_at: str, recipient_ids: tuple[str, ...] = (),
                  audience_sha256: str = '') -> OutboundIntent:
    """Build an outbound intent. This function never sends anything."""
    key = provider_idempotency_key(
        meeting_id=meeting_id, intent_id=intent_id, channel=channel)
    return OutboundIntent(
        intent_id=intent_id, meeting_id=meeting_id, turn_id=turn_id,
        channel=channel, body=body, idempotency_key=key, created_at=created_at,
        recipient_ids=recipient_ids, audience_sha256=audience_sha256)


def intent_recorded(ledger: DeliveryLedger, intent: OutboundIntent) -> DeliveryReceipt:
    """The only receipt produced by deciding to speak. Delivery is separate."""
    return ledger.record_intent(intent)
