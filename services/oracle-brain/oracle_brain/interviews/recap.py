"""Visible recap: what was learned, what remains unconfirmed, how to correct it."""
from dataclasses import dataclass

from .state import InterviewState


@dataclass(frozen=True)
class Recap:
    learned: tuple[tuple[str, str], ...]
    unconfirmed: tuple[str, ...]
    how_to_correct: str = 'Reply with the corrected value for any item; it replaces the earlier answer.'


def build_recap(state: InterviewState, required_fields) -> Recap:
    learned = tuple(sorted(state.known.items()))
    unconfirmed = tuple(sorted(f for f in required_fields if state.known.get(f) in (None, '')))
    return Recap(learned, unconfirmed)
