"""Host-gated in-meeting participation policy and durable receipts.

Participation is off until the host explicitly enables it. Settings are recorded
per meeting, never hard-coded in prompts. Outbound words are never employee
evidence. This module never contacts a provider.
"""
from __future__ import annotations

import json
import math
import time
from secrets import token_hex
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from oracle_brain.seal import verify_mac

DEFAULT_COOLDOWN_SECONDS = 120
DEFAULT_MAX_INTERVENTIONS = 3
DEFAULT_CHANNEL: Literal['meeting_text', 'meeting_chat'] = 'meeting_text'
CHANNELS = frozenset({'meeting_text', 'meeting_chat'})
RECEIPT_STATUSES = frozenset({'recorded', 'sent', 'failed', 'suppressed'})
# Purpose tag for the host-authorized enable seal. Enabling participation
# for a meeting requires an Ed25519 signature over all configuration fields issued
# under this purpose. The signature is the authority — there is no
# in-process enable registry to mutate.
ENABLE_PROOF_PURPOSE = 'participation-enable:v1'
CURRENT_PROOF_PURPOSE = 'participation-current:v1'


@dataclass(frozen=True)
class ParticipationSettings:
    """Recorded per-meeting host configuration. Proactive clarification is off
    by default and must be explicitly enabled."""
    meeting_id: str
    enabled: bool = False
    channel: str = DEFAULT_CHANNEL
    proactive_enabled: bool = False
    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS
    max_interventions: int = DEFAULT_MAX_INTERVENTIONS
    recorded_at: str = ''
    enable_proof_mac: str = ''
    generation: int = 0
    valid_until: float = 0.0

    def __post_init__(self) -> None:
        if not self.meeting_id:
            raise ValueError('meeting_id required')
        if self.channel not in CHANNELS:
            raise ValueError('unsupported participation channel')
        if self.cooldown_seconds < 0:
            raise ValueError('cooldown must be nonnegative')
        if self.max_interventions < 0:
            raise ValueError('max_interventions must be nonnegative')
        if self.enabled and not self.recorded_at:
            raise ValueError('enabling participation requires recorded_at')
        verify_settings_signature(self)


@dataclass(frozen=True)
class ParticipationReceipt:
    """Durable record of one participation outcome. A suppressed receipt still
    proves the turn was considered, so capture is never confused with silence."""
    receipt_id: str
    meeting_id: str
    turn_id: str
    status: str
    channel: Optional[str] = None
    reason: Optional[str] = None
    recorded_at: str = ''

    def __post_init__(self) -> None:
        if not self.receipt_id or not self.meeting_id or not self.turn_id:
            raise ValueError('receipt identity required')
        if self.status not in RECEIPT_STATUSES:
            raise ValueError('unsupported receipt status')


@dataclass(frozen=True)
class InterventionBudget:
    """Proactive interventions already spent in one meeting."""
    count: int = 0
    last_at_seconds: Optional[float] = None

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError('intervention count must be nonnegative')
        if self.last_at_seconds is not None and self.last_at_seconds < 0:
            raise ValueError('last intervention time must be nonnegative')


def record_settings(*, meeting_id: str, enabled: bool = False,
                    channel: str = DEFAULT_CHANNEL, proactive_enabled: bool = False,
                    cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
                    max_interventions: int = DEFAULT_MAX_INTERVENTIONS,
                    recorded_at: str = '',
                    enable_proof_mac: str = '', generation: int = 0,
                    valid_until: float = 0.0) -> ParticipationSettings:
    """Record host settings for a meeting. Enabling participation is explicit.

    When ``enabled`` is true, ``enable_proof_mac`` must be a
    host-authorized Ed25519 seal over all configuration fields under
    ``ENABLE_PROOF_PURPOSE``. A bare settings object without that proof
    cannot enable participation.
    """
    return ParticipationSettings(
        meeting_id=meeting_id, enabled=enabled, channel=channel,
        proactive_enabled=proactive_enabled, cooldown_seconds=cooldown_seconds,
        max_interventions=max_interventions, recorded_at=recorded_at,
        enable_proof_mac=enable_proof_mac, generation=generation, valid_until=valid_until)


def settings_authority_payload(*, meeting_id: str, enabled: bool = True,
                               channel: str = DEFAULT_CHANNEL,
                               proactive_enabled: bool = False,
                               cooldown_seconds: int = DEFAULT_COOLDOWN_SECONDS,
                               max_interventions: int = DEFAULT_MAX_INTERVENTIONS,
                               recorded_at: str = '', generation: int = 0,
                               valid_until: float = 0.0) -> str:
    """Unambiguous, complete host-authorized configuration for the signer."""
    return json.dumps([meeting_id, enabled, channel, proactive_enabled,
                       cooldown_seconds, max_interventions, recorded_at, generation, valid_until],
                      separators=(',', ':'), ensure_ascii=True)


def verify_settings_signature(settings: ParticipationSettings) -> None:
    """Recheck authority at each consumption; frozen objects are not a boundary."""
    if type(settings) is not ParticipationSettings:
        raise PermissionError('exact participation settings required')
    if not settings.enabled:
        return
    if not settings.enable_proof_mac:
        raise PermissionError('host-authorized enable proof required to enable participation')
    verify_mac(ENABLE_PROOF_PURPOSE, settings.enable_proof_mac,
               settings_authority_payload(
                   meeting_id=settings.meeting_id, enabled=settings.enabled,
                   channel=settings.channel, proactive_enabled=settings.proactive_enabled,
                   cooldown_seconds=settings.cooldown_seconds,
                   max_interventions=settings.max_interventions,
                   recorded_at=settings.recorded_at, generation=settings.generation,
                   valid_until=settings.valid_until))
    if (type(settings.generation) is not int or settings.generation < 1
            or type(settings.valid_until) not in (int, float)
            or not math.isfinite(settings.valid_until)
            or settings.valid_until <= time.time()):
        raise PermissionError('participation settings expired or invalid generation')


@dataclass(frozen=True)
class CurrentSettingsProof:
    """Independent host's current state, bound to a fresh verifier challenge."""
    meeting_id: str
    generation: int
    enabled: bool
    challenge: str
    valid_until: float
    mac: str


def current_settings_payload(proof: CurrentSettingsProof) -> str:
    return json.dumps(['current-meeting-settings:v1', proof.meeting_id,
                      proof.generation, proof.enabled, proof.challenge,
                      proof.valid_until], separators=(',', ':'), allow_nan=False)


CurrentSettingsReader = Callable[[str, str], CurrentSettingsProof]


def verify_settings_authority(settings: ParticipationSettings,
                              current_state_reader: Optional[CurrentSettingsReader] = None) -> None:
    """Require a fresh host response, never a caller integer or old attestation."""
    verify_settings_signature(settings)
    if not settings.enabled:
        return
    if current_state_reader is None:
        raise PermissionError('independent current meeting settings required')
    challenge = token_hex(32)
    current = current_state_reader(settings.meeting_id, challenge)
    if type(current) is not CurrentSettingsProof:
        raise PermissionError('host-signed current meeting settings required')
    if (current.meeting_id != settings.meeting_id or current.challenge != challenge
            or type(current.generation) is not int
            or current.generation != settings.generation or current.enabled is not True
            or type(current.valid_until) not in (int, float)
            or not math.isfinite(current.valid_until)
            or not time.time() < current.valid_until <= time.time() + 60):
        raise PermissionError('meeting settings superseded, disabled or expired')
    verify_mac(CURRENT_PROOF_PURPOSE, current.mac, current_settings_payload(current))


def decide_addressed(settings: ParticipationSettings, *, turn_id: str,
                     receipt_id: str, recorded_at: str,
                     current_state_reader: Optional[CurrentSettingsReader] = None) -> ParticipationReceipt:
    """Addressed turns respond only while the host has participation enabled.
    Silence is a recorded outcome, not a missing receipt."""
    verify_settings_authority(settings, current_state_reader)
    if not turn_id or not receipt_id:
        raise ValueError('turn and receipt identity required')
    if not settings.enabled:
        return ParticipationReceipt(
            receipt_id, settings.meeting_id, turn_id, 'suppressed',
            reason='participation_disabled', recorded_at=recorded_at)
    return ParticipationReceipt(
        receipt_id, settings.meeting_id, turn_id, 'recorded',
        channel=settings.channel, reason='addressed', recorded_at=recorded_at)


def can_intervene_proactively(settings: ParticipationSettings, budget: InterventionBudget,
                              *, now_seconds: float,
                              current_state_reader: Optional[CurrentSettingsReader] = None) -> bool:
    """Proactive clarification is off by default, rate-limited by cooldown and
    capped at max_interventions per meeting."""
    verify_settings_authority(settings, current_state_reader)
    if not settings.enabled or not settings.proactive_enabled:
        return False
    if budget.count >= settings.max_interventions:
        return False
    if budget.last_at_seconds is None:
        return True
    return (now_seconds - budget.last_at_seconds) >= settings.cooldown_seconds


def record_proactive_intervention(budget: InterventionBudget) -> InterventionBudget:
    """Advance the budget after a proactive intervention was actually performed."""
    return InterventionBudget(count=budget.count + 1, last_at_seconds=None)


def receipt_recorded(*, receipt_id: str, meeting_id: str, turn_id: str,
                     recorded_at: str, channel: Optional[str] = None) -> ParticipationReceipt:
    """The only receipt produced by deciding to answer. Delivery is a separate act."""
    return ParticipationReceipt(
        receipt_id, meeting_id, turn_id, 'recorded', channel=channel,
        reason='addressed', recorded_at=recorded_at)


def receipt_failed(*, receipt_id: str, meeting_id: str, turn_id: str,
                   channel: str, reason: str) -> ParticipationReceipt:
    if not all((channel, reason)):
        raise ValueError('failed receipt requires channel and reason')
    return ParticipationReceipt(
        receipt_id, meeting_id, turn_id, 'failed', channel=channel, reason=reason)
