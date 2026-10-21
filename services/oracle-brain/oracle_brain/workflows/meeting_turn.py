"""One bounded in-meeting turn: address detection, access bound, decision, intent.

Membership that cannot be determined never widens access: the answer uses
meeting-only evidence or declines. Oracle outbound words are never employee
evidence. Capture is independent of participation and survives silence or a
failed answer. No provider is contacted from this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from secrets import token_hex
import time
from typing import Callable, Literal, Optional

from oracle_brain.seal import verify_mac

from oracle_brain.meetings.delivery import DeliveryLedger, OutboundIntent, create_intent
from oracle_brain.meetings.participation import (
    ParticipationReceipt, ParticipationSettings, CurrentSettingsReader, decide_addressed, verify_settings_authority,
)

Decision = Literal['respond', 'silence', 'decline']
EvidenceScope = Literal['meeting_only', 'shared_access', 'none']


@dataclass(frozen=True)
class InboundTurn:
    """A meeting turn offered to the participation path. Oracle-origin turns
    must never be presented here as employee evidence."""
    turn_id: str
    meeting_id: str
    speaker_id: str
    text: str
    origin: Literal['participant', 'oracle'] = 'participant'
    addresses_oracle: bool = False

    def __post_init__(self) -> None:
        if not self.turn_id or not self.meeting_id or not self.speaker_id:
            raise ValueError('inbound turn identity required')
        if not self.text.strip():
            raise ValueError('inbound turn text required')
        if self.origin not in ('participant', 'oracle'):
            raise ValueError('unsupported turn origin')
        if self.origin == 'oracle':
            raise ValueError('oracle outbound words are never inbound evidence')


@dataclass(frozen=True)
class MembershipView:
    """What the host channel can prove about who shares the answer's access."""
    determined: bool
    shared_access: Optional[frozenset] = None

    def __post_init__(self) -> None:
        if self.determined and self.shared_access is None:
            raise ValueError('determined membership requires shared_access')


AUDIENCE_PURPOSE = 'meeting-audience:v1'

@dataclass(frozen=True)
class CurrentAudienceProof:
    """Independent host's complete current recipients and exact-answer access."""
    meeting_id: str
    channel: str
    settings_generation: int
    answer_sha256: str
    recipient_ids: frozenset[str]
    authorized_audience: frozenset[str]
    complete: bool
    challenge: str
    valid_until: float
    mac: str


def audience_payload(proof: CurrentAudienceProof) -> str:
    return json.dumps(['current-meeting-audience:v1', proof.meeting_id,
                      proof.channel, proof.settings_generation, proof.answer_sha256,
                      sorted(proof.recipient_ids), sorted(proof.authorized_audience),
                      proof.complete, proof.challenge, proof.valid_until],
                     separators=(',', ':'), allow_nan=False)


AudienceReader = Callable[[str, str, int, str, str], CurrentAudienceProof]


def _current_audience(settings, turn, answer_body, reader):
    if reader is None:
        raise PermissionError('independent complete current recipients required')
    challenge = token_hex(32)
    body_hash = sha256(answer_body.encode('utf-8')).hexdigest()
    proof = reader(settings.meeting_id, settings.channel, settings.generation, body_hash, challenge)
    if type(proof) is not CurrentAudienceProof:
        raise PermissionError('host-signed current audience required')
    if (proof.meeting_id != settings.meeting_id or proof.channel != settings.channel
            or type(proof.settings_generation) is not int
            or proof.settings_generation != settings.generation
            or proof.answer_sha256 != body_hash or proof.challenge != challenge
            or proof.complete is not True or type(proof.recipient_ids) is not frozenset
            or type(proof.authorized_audience) is not frozenset
            or not 0 < len(proof.recipient_ids) <= 1000
            or not all(type(v) is str and v for v in proof.recipient_ids | proof.authorized_audience)
            or type(proof.valid_until) not in (int, float)
            or not math.isfinite(proof.valid_until)
            or not time.time() < proof.valid_until <= time.time() + 60):
        raise PermissionError('complete current audience binding invalid or expired')
    verify_mac(AUDIENCE_PURPOSE, proof.mac, audience_payload(proof))
    if (turn.speaker_id not in proof.recipient_ids
            or not proof.recipient_ids <= proof.authorized_audience):
        raise PermissionError('all current meeting recipients must have answer access')
    return proof


@dataclass(frozen=True)
class TurnOutcome:
    decision: Decision
    evidence_scope: EvidenceScope
    receipt: ParticipationReceipt
    intent: Optional[OutboundIntent] = None

    @property
    def capture_continues(self) -> bool:
        """Capture never stops because participation is off or an answer failed."""
        return True


def evaluate_turn(settings: ParticipationSettings, turn: InboundTurn,
                  membership: MembershipView, ledger: DeliveryLedger, *,
                  receipt_id: str, intent_id: Optional[str] = None,
                  answer_body: str = '', recorded_at: str = '',
                  current_state_reader: Optional[CurrentSettingsReader] = None,
                  current_audience_reader: Optional[AudienceReader] = None) -> TurnOutcome:
    """Decide one bounded turn and, when responding, record an outbound intent.

    The ledger only records the intent; sending is a separate authorized act
    with its own provider idempotency receipt.
    """
    verify_settings_authority(settings, current_state_reader)
    if turn.meeting_id != settings.meeting_id:
        raise ValueError('turn does not belong to this meeting')
    if turn.origin != 'participant':
        raise ValueError('only participant turns may be evaluated')
    if not turn.addresses_oracle:
        return TurnOutcome(
            'silence', 'none', _quiet(settings, turn, receipt_id, recorded_at))
    receipt = decide_addressed(
        settings, turn_id=turn.turn_id, receipt_id=receipt_id, recorded_at=recorded_at,
        current_state_reader=current_state_reader)
    if receipt.status == 'suppressed':
        return TurnOutcome('silence', 'none', receipt)
    if not membership.determined:
        # Membership unknown never widens access and never produces an
        # outbound intent — decline regardless of answer body.
        return TurnOutcome(
            'decline', 'meeting_only',
            _decline(settings, turn, receipt_id, recorded_at,
                     reason='membership_undetermined'))
    # Membership determined: shared_access answers require the speaker to
    # be in the proven shared_access set. Otherwise refuse.
    if turn.speaker_id not in (membership.shared_access or frozenset()):
        return TurnOutcome(
            'decline', 'none',
            _decline(settings, turn, receipt_id, recorded_at,
                     reason='shared_access_unauthorized'))
    scope: EvidenceScope = 'shared_access'
    if not answer_body.strip():
        return TurnOutcome(
            'decline', scope,
            _decline(settings, turn, receipt_id, recorded_at, reason='no_answer'))
    if intent_id is None:
        raise ValueError('responding requires intent_id')
    audience = _current_audience(settings, turn, answer_body, current_audience_reader)
    intent = create_intent(
        intent_id=intent_id, meeting_id=settings.meeting_id, turn_id=turn.turn_id,
        channel=settings.channel, body=answer_body, created_at=recorded_at,
        recipient_ids=tuple(sorted(audience.recipient_ids)),
        audience_sha256=sha256(audience_payload(audience).encode()).hexdigest())
    ledger.record_intent(intent)
    return TurnOutcome('respond', scope, receipt, intent)


def _quiet(settings: ParticipationSettings, turn: InboundTurn,
           receipt_id: str, recorded_at: str) -> ParticipationReceipt:
    return ParticipationReceipt(
        receipt_id, settings.meeting_id, turn.turn_id, 'suppressed',
        reason='not_addressed', recorded_at=recorded_at)


def _decline(settings: ParticipationSettings, turn: InboundTurn,
             receipt_id: str, recorded_at: str, *, reason: str) -> ParticipationReceipt:
    return ParticipationReceipt(
        receipt_id, settings.meeting_id, turn.turn_id, 'suppressed',
        reason=reason, recorded_at=recorded_at)
