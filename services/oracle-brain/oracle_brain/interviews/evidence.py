"""Current-evidence binding for interview turns. Superseded evidence never binds."""
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class EvidenceRef:
    evidence_id: str
    source_id: str
    revision: int
    superseded: bool = False
    withdrawn: bool = False

    @property
    def current(self) -> bool:
        return not self.superseded and not self.withdrawn


@dataclass(frozen=True)
class TurnEvidenceBinding:
    turn_id: str
    evidence_ids: tuple
    bound_at: str


def bind_turn_evidence(turn_id: str, evidence: Iterable[EvidenceRef], *,
                       bound_at: str, speaker: str = 'employee') -> TurnEvidenceBinding:
    """Bind a turn to the current evidence only.

    Assistant turns never bind. Superseded or withdrawn evidence is refused,
    not silently dropped: the caller must supply current refs.
    """
    if speaker != 'employee':
        raise ValueError('assistant statements are never evidence')
    if not turn_id or not bound_at:
        raise ValueError('binding requires turn_id and bound_at')
    refs = tuple(evidence)
    stale = [e for e in refs if not e.current]
    if stale:
        raise ValueError('superseded or withdrawn evidence cannot bind')
    seen = set()
    ordered = []
    for e in refs:
        if e.evidence_id in seen:
            raise ValueError('duplicate evidence_id in one binding')
        seen.add(e.evidence_id)
        ordered.append(e.evidence_id)
    return TurnEvidenceBinding(turn_id, tuple(ordered), bound_at)


def filter_current(evidence: Sequence[EvidenceRef]) -> tuple:
    """Current refs only, in input order. For display/recap, never for silent binding."""
    return tuple(e for e in evidence if e.current)
