"""Host-gated in-meeting participation policy and durable receipts.

Participation is off until the host explicitly enables it. Settings are recorded
per meeting, never hard-coded in prompts. Outbound words are never employee
evidence. This module never contacts a provider.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

DEFAULT_COOLDOWN_SECONDS = 120
DEFAULT_MAX_INTERVENTIONS = 3
DEFAULT_CHANNEL: Literal['meeting_text', 'meeting_chat'] = 'meeting_text'
CHANNELS = frozenset({'meeting_text', 'meeting_chat'})
RECEIPT_STATUSES = frozenset({'recorded', 'sent', 'failed', 'suppressed'})


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
                    recorded_at: str = '') -> ParticipationSettings:
    """Record host settings for a meeting. Enabling participation is explicit."""
    return ParticipationSettings(
        meeting_id=meeting_id, enabled=enabled, channel=channel,
        proactive_enabled=proactive_enabled, cooldown_seconds=cooldown_seconds,
        max_interventions=max_interventions, recorded_at=recorded_at)


def decide_addressed(settings: ParticipationSettings, *, turn_id: str,
                     receipt_id: str, recorded_at: str) -> ParticipationReceipt:
    """Addressed turns respond only while the host has participation enabled.
    Silence is a recorded outcome, not a missing receipt."""
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
                              *, now_seconds: float) -> bool:
    """Proactive clarification is off by default, rate-limited by cooldown and
    capped at max_interventions per meeting."""
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
