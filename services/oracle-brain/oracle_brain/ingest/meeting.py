"""Offline meeting transcript reconciliation. This module admits no webhooks.

Callers must authenticate provider deliveries and check capture authorization at
an ingress boundary before persisting an input. No provider adapter is installed
here; candidates are always reported, never accepted company truth.
"""
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from .speakers import Speaker


@dataclass(frozen=True)
class Turn:
    turn_id: str
    revision: int
    speaker: Speaker
    text: str
    origin: Literal['participant', 'oracle'] = 'participant'

    def __post_init__(self):
        if not self.turn_id or self.revision < 0 or not self.text.strip():
            raise ValueError('turn identity, nonnegative revision and text required')
        if self.origin not in ('participant', 'oracle'):
            raise ValueError('unsupported turn origin')


@dataclass(frozen=True)
class Transcript:
    tenant_id: str
    meeting_id: str
    revision: int
    turns: tuple[Turn, ...]
    final: bool = False

    def __post_init__(self):
        if not self.tenant_id or not self.meeting_id or self.revision < 0:
            raise ValueError('tenant, meeting and nonnegative revision required')
        if len({t.turn_id for t in self.turns}) != len(self.turns):
            raise ValueError('duplicate turn identity')

    def fingerprint(self) -> str:
        # repr of these immutable scalar tuples is deterministic and preserves
        # distinctions between field boundaries and unknown employee links.
        value = (self.tenant_id, self.meeting_id, self.revision, self.final,
                 tuple((t.turn_id, t.revision, t.speaker.provider_id,
                        t.speaker.display_name, t.speaker.employee_id,
                        t.text, t.origin) for t in self.turns))
        return sha256(repr(value).encode()).hexdigest()


def reconcile(current: Transcript | None, incoming: Transcript) -> Transcript:
    """Final snapshots replace live turns; stale replays cannot revert them.

    Equal-version disagreements fail visibly rather than silently selecting a
    contradictory delivery. A final snapshot may intentionally omit live turns.
    """
    if current is None:
        return incoming
    if (current.tenant_id, current.meeting_id) != (incoming.tenant_id, incoming.meeting_id):
        raise ValueError('cross-meeting transcript')
    if incoming.revision < current.revision:
        return current
    if incoming.revision == current.revision:
        if incoming.fingerprint() != current.fingerprint():
            raise ValueError('conflicting transcript revision')
        return current
    if current.final and not incoming.final:
        raise ValueError('live transcript cannot replace final transcript')
    return incoming


def reported_candidates(transcript: Transcript) -> tuple[Turn, ...]:
    """Only final participant words may be offered for a separate review."""
    if not transcript.final:
        return ()
    return tuple(turn for turn in transcript.turns if turn.origin == 'participant')
