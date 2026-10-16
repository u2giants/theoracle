"""Meeting invitation and capture-consent gate. Pure fixture decisions only.

A bot is never created and no transcript is accepted for learning without a
meeting-specific explicit invitation and current capture consent. Public
meetings are never joined. Missing transcript permission, rejected lobby
admission and transcription failure are visible refusals, never silent success.
Persistence, provider signatures and dispatch live outside this module.
"""
from dataclasses import dataclass
from typing import Literal

from .meeting import Transcript


@dataclass(frozen=True)
class Invitation:
    """Meeting-specific invitation/capture permission recorded before any bot."""
    tenant_id: str
    meeting_id: str
    explicitly_invited: bool
    capture_permission: bool
    transcript_permission: bool
    consent_current: bool

    def __post_init__(self):
        if not self.tenant_id or not self.meeting_id:
            raise ValueError('tenant and meeting required')


@dataclass(frozen=True)
class GateDecision:
    admitted: bool
    stage: Literal['capture', 'intake', 'learning']
    reason: str


def _refuse(stage, reason: str) -> GateDecision:
    return GateDecision(False, stage, reason)


def _allow(stage) -> GateDecision:
    return GateDecision(True, stage, '')


def authorize_capture(invitation: Invitation) -> GateDecision:
    """Explicit invitation, capture permission and current consent before a bot."""
    if not invitation.explicitly_invited:
        return _refuse('capture', 'no explicit invitation; public meetings are never joined')
    if not invitation.capture_permission:
        return _refuse('capture', 'missing capture permission')
    if not invitation.consent_current:
        return _refuse('capture', 'capture consent is not current')
    return _allow('capture')


def evaluate_intake(invitation: Invitation, *, lobby_admitted: bool,
                    transcription_succeeded: bool) -> GateDecision:
    """Missing permission, rejected lobby and transcription failure stay visible."""
    base = authorize_capture(invitation)
    if not base.admitted:
        return _refuse('intake', base.reason)
    if not lobby_admitted:
        return _refuse('intake', 'rejected lobby admission')
    if not transcription_succeeded:
        return _refuse('intake', 'transcription failure')
    return _allow('intake')


def authorize_learning(invitation: Invitation, transcript: Transcript | None) -> GateDecision:
    """Current consent and the matching final transcript before accepting learning."""
    base = authorize_capture(invitation)
    if not base.admitted:
        return _refuse('learning', base.reason)
    if not invitation.transcript_permission:
        return _refuse('learning', 'missing transcript permission')
    if transcript is None:
        return _refuse('learning', 'missing transcript')
    if (transcript.tenant_id, transcript.meeting_id) != (invitation.tenant_id, invitation.meeting_id):
        return _refuse('learning', 'cross-meeting transcript')
    if not transcript.final:
        return _refuse('learning', 'only final transcripts may be learned from')
    return _allow('learning')
