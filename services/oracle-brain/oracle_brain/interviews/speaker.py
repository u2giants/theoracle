"""Conservative speaker identity for interview and ordinary chat turns."""
from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class SpeakerCandidate:
    speaker_id: str
    display_name: str
    email: Optional[str] = None


@dataclass(frozen=True)
class ResolvedSpeaker:
    speaker_id: str
    display_name: str
    resolution: str  # 'exact_id' | 'exact_email' | 'unique_name'


def resolve_speaker(candidates: Sequence[SpeakerCandidate], *,
                    speaker_id: Optional[str] = None,
                    email: Optional[str] = None,
                    display_name: Optional[str] = None) -> Optional[ResolvedSpeaker]:
    """Resolve a chat/interview speaker conservatively.

    Exact stable ID wins. Otherwise exact email if unique. Otherwise a display
    name matches only when exactly one candidate has it. Ambiguous or unknown
    input abstains (None) so the caller can raise a review question — shared
    names never merge identities.
    """
    if speaker_id:
        hits = [c for c in candidates if c.speaker_id == speaker_id]
        if len(hits) == 1:
            return ResolvedSpeaker(hits[0].speaker_id, hits[0].display_name, 'exact_id')
        return None
    if email:
        hits = [c for c in candidates if c.email == email]
        if len(hits) == 1:
            return ResolvedSpeaker(hits[0].speaker_id, hits[0].display_name, 'exact_email')
        return None
    if display_name:
        hits = [c for c in candidates if c.display_name == display_name]
        if len(hits) == 1:
            return ResolvedSpeaker(hits[0].speaker_id, hits[0].display_name, 'unique_name')
        return None
    return None
