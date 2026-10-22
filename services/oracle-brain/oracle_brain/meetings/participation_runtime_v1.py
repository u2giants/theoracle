"""Deterministic current-turn content transform. Content is NEVER send authority.

Only the fixed hosting consumer supplies actual S07 protected current bytes.
No model, provider, user role, database, dispatch or in-memory receipt lives here.
"""
from dataclasses import dataclass
from hashlib import sha256
import re
import string

COMPOSER_PURPOSE = 'meeting-current-turn-quote-v1'
_BOUNDARY = r'[\s'+re.escape(string.punctuation)+r']'
_ADDRESSED = re.compile(r'^@?oracle(?:'+_BOUNDARY+r'|$)', re.IGNORECASE | re.ASCII)


class ParticipationDeclined(PermissionError):
    """A declined reply cannot be converted into another channel or permission."""


def is_addressed_current_turn_v1(text: str) -> bool:
    """Content predicate only, never sender/employee/company permission."""
    return type(text) is str and _ADDRESSED.match(text) is not None


@dataclass(frozen=True)
class ComposedMeetingReplyV1:
    message: str
    normalized_sha256: str
    body_sha256: str
    evidence_scope: str = 'meeting_only'
    reported_only: bool = True
    qualification: bool = False
    employee_identity_verified: bool = False
    shared_source_permission: bool = False


def compose_current_turn_v1(text: str, *, proactive: bool = False) -> ComposedMeetingReplyV1:
    """Exact leading address or separately permitted proactive clarification.

    This pure result does not prove host enable, current source/recipient access,
    an appointment, a budget, provider chat capability or delivery permission.
    """
    if type(text) is not str or not text.strip() or '\0' in text or type(proactive) is not bool:
        raise ParticipationDeclined('exact bounded current participant text required')
    if not proactive and not is_addressed_current_turn_v1(text):
        raise ParticipationDeclined('explicit leading Oracle address absent')
    # Recall Teams accepts HTML. Escape only presentation; source text/hash is
    # still the exact protected normalizer output and is never reinterpreted.
    escaped = text.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')
    message = ('Could you clarify: ' if proactive else 'You asked: ') + escaped
    if len(message) > 4096 or len(message.encode('utf8')) > 16384:
        raise ParticipationDeclined('complete same-turn reply exceeds provider bound; no truncation')
    return ComposedMeetingReplyV1(message,sha256(text.encode('utf8')).hexdigest(),sha256(message.encode('utf8')).hexdigest())
