"""Meeting outbound intents, provider idempotency keys and durable receipts.

Recording an intent never sends. Only a separate authorized send actor may
attach a delivery receipt. Replay of an existing idempotency key returns the
prior receipt and must not produce a second provider call.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
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
# Purpose pin on sender credentials, matching the appointment/admission
# records used by processing authority proofs and original intake.
SENDER_CREDENTIAL_PURPOSE = 'meeting-delivery-sender'

class SenderAuthority:
    """Capability proving the holder is an authorized delivery sender.

    Instances exist only via ``issue_sender_authority``. Direct construction
    is refused, and a look-alike built with ``object.__new__`` is denied at
    the use site because it is not in the sealed mint registry.
    """
    __slots__ = ('_role', '__weakref__')

    def __init__(self, *args, **kwargs) -> None:
        raise PermissionError('sender authority cannot be forged')


class SenderPrincipal:
    """Verified principal credential for an authenticated delivery sender.

    Instances exist only via ``verify_sender_principal``. Direct construction
    is refused, and a look-alike built with ``object.__new__`` is denied at
    the use site because it is not in the sealed verified-principal registry.
    """
    __slots__ = ('_principal_id', '_role', '_expires_at', '__weakref__')

    def __init__(self, *args, **kwargs) -> None:
        raise PermissionError('sender principal cannot be forged')

    @property
    def principal_id(self) -> str:
        return self._principal_id

    @property
    def role(self) -> str:
        return self._role

    @property
    def expires_at(self) -> datetime:
        return self._expires_at


@dataclass(frozen=True)
class SenderCredentialProof:
    """Credential material presented by the authz/authority layer.

    Same admission shape as processing authority proofs and original-intake
    appointments: principal identity, expected role, and a finite validity
    window. Holding this record is not authority; it is input to
    ``verify_sender_principal`` only.
    """
    principal_id: str
    role: str
    expires_at: datetime
    purpose: str = SENDER_CREDENTIAL_PURPOSE

    def __post_init__(self) -> None:
        if not self.principal_id or not self.role:
            raise ValueError('sender credential identity and role required')
        if (not isinstance(self.expires_at, datetime)
                or self.expires_at.tzinfo is None
                or self.expires_at.utcoffset() is None):
            raise ValueError('sender credential expiry must be timezone-aware')


def _install_sealed_authority_api():
    """Create the mint path with closure-local secrets and registries.

    The mint secret, principal secret and both registries are locals of this
    factory, captured only inside the returned callables. None is a module
    attribute, so no import or getattr can reach a mint credential.
    """
    mint_secret = object()
    minted: WeakSet = WeakSet()
    principal_secret = object()
    verified: WeakSet = WeakSet()

    def _mint(role: str, secret: object) -> SenderAuthority:
        if secret is not mint_secret:
            raise PermissionError('sender authority cannot be forged')
        authority = object.__new__(SenderAuthority)
        authority._role = role
        minted.add(authority)
        return authority

    def _mint_principal(proof: SenderCredentialProof,
                        secret: object) -> SenderPrincipal:
        if secret is not principal_secret:
            raise PermissionError('sender principal cannot be forged')
        principal = object.__new__(SenderPrincipal)
        principal._principal_id = proof.principal_id
        principal._role = proof.role
        principal._expires_at = proof.expires_at
        verified.add(principal)
        return principal

    def verify_sender_principal(proof) -> SenderPrincipal:
        """Authz boundary: verify credential material, mint a sealed principal.

        ``proof`` must be a real ``SenderCredentialProof`` (appointment-shaped
        identity + role + validity window). A bare role string, a look-alike,
        or a credential for another purpose is refused. Expiry is enforced
        again at capability mint time.
        """
        if not isinstance(proof, SenderCredentialProof):
            raise PermissionError('sender credential proof required')
        if proof.purpose != SENDER_CREDENTIAL_PURPOSE:
            raise PermissionError('sender credential purpose mismatch')
        if proof.role not in AUTHORIZED_SENDER_ROLES:
            raise PermissionError('sender role not authorized')
        return _mint_principal(proof, principal_secret)

    def issue_sender_authority(role: str, principal=None,
                               *, now: Optional[datetime] = None) -> SenderAuthority:
        """Sealed authorizer: mint a sender capability for a verified principal.

        Requires a sealed ``SenderPrincipal`` whose role matches and whose
        validity window is still open. Missing credentials, bare role strings,
        forged principals, expired principals, and role mismatches are all
        refused. The mint secret lives only in this closure and is never a
        parameter.
        """
        if not isinstance(principal, SenderPrincipal) or principal not in verified:
            raise PermissionError('verified sender principal required')
        if role not in AUTHORIZED_SENDER_ROLES:
            raise PermissionError('sender role not authorized')
        if principal.role != role:
            raise PermissionError('sender principal role mismatch')
        at = now or datetime.now(timezone.utc)
        if at.tzinfo is None or at.utcoffset() is None:
            raise ValueError('mint time must be timezone-aware')
        if principal.expires_at <= at:
            raise PermissionError('sender principal expired')
        return _mint(role, mint_secret)

    def require_proven_sender(sender) -> SenderAuthority:
        """Deny unless the caller presents a minted SenderAuthority.

        Unproven claims — None, a role string, a forged instance — are refused.
        """
        if not isinstance(sender, SenderAuthority) or sender not in minted:
            raise PermissionError('sender authority required to mark delivery')
        return sender

    return verify_sender_principal, issue_sender_authority, require_proven_sender


verify_sender_principal, issue_sender_authority, _require_proven_sender = (
    _install_sealed_authority_api())


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
