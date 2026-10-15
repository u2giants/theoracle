"""Offline contradiction detection between overlapping live facts in the same scope."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .temporal import Fact


@dataclass(frozen=True)
class Contradiction:
    left: Fact
    right: Fact


def _end(f: Fact) -> datetime:
    return f.valid_to or datetime.max.replace(tzinfo=f.valid_from.tzinfo)


def _overlap(a: Fact, b: Fact) -> bool:
    return a.valid_from < _end(b) and b.valid_from < _end(a)


def find_contradictions(facts: list[Fact]) -> list[Contradiction]:
    live = [f for f in facts if f.superseded_at is None]
    out: list[Contradiction] = []
    for i, a in enumerate(live):
        for b in live[i + 1 :]:
            if (
                (a.subject, a.attribute, a.scope) == (b.subject, b.attribute, b.scope)
                and a.value != b.value
                and _overlap(a, b)
            ):
                out.append(Contradiction(a, b))
    return out
