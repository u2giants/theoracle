"""Offline summary cache invalidated when a fact it depends on is corrected."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from dataclasses import dataclass, field
from uuid import UUID

if TYPE_CHECKING:
    from .temporal import Fact


@dataclass
class Summary:
    key: str
    text: str
    depends_on: frozenset[UUID]
    stale: bool = False


@dataclass
class SummaryCache:
    summaries: dict[str, Summary] = field(default_factory=dict)

    def build(self, key: str, facts: list[Fact], render: Callable[[list[Fact]], str]) -> Summary:
        summary = Summary(key, render(facts), frozenset(f.fact_id for f in facts))
        self.summaries[key] = summary
        return summary

    def invalidate_fact(self, fact_id: UUID) -> list[str]:
        hit = []
        for s in self.summaries.values():
            if fact_id in s.depends_on and not s.stale:
                s.stale = True
                hit.append(s.key)
        return hit

    def get(self, key: str) -> Summary | None:
        s = self.summaries.get(key)
        return None if s is None or s.stale else s
