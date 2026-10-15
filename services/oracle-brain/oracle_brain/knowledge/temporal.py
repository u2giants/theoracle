"""Offline bitemporal facts: valid time (true in business) and recorded time (when known)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID, uuid4

COMPANY_SCOPE = "company"


@dataclass(frozen=True)
class Fact:
    fact_id: UUID
    subject: str
    attribute: str
    value: str
    scope: str
    valid_from: datetime
    valid_to: datetime | None
    recorded_at: datetime
    superseded_at: datetime | None = None
    supersedes: UUID | None = None


@dataclass
class FactStore:
    facts: list[Fact] = field(default_factory=list)

    def assert_fact(
        self,
        subject: str,
        attribute: str,
        value: str,
        *,
        valid_from: datetime,
        recorded_at: datetime,
        valid_to: datetime | None = None,
        scope: str = COMPANY_SCOPE,
    ) -> Fact:
        fact = Fact(uuid4(), subject, attribute, value, scope, valid_from, valid_to, recorded_at)
        self.facts.append(fact)
        return fact

    def correct(self, fact_id: UUID, value: str, *, recorded_at: datetime) -> Fact:
        """Supersede a fact; the old version stays visible to as-of-recorded queries."""
        idx = next(i for i, f in enumerate(self.facts) if f.fact_id == fact_id)
        old = self.facts[idx]
        if old.superseded_at is not None:
            raise ValueError("fact already superseded")
        self.facts[idx] = replace(old, superseded_at=recorded_at)
        new = replace(
            old, fact_id=uuid4(), value=value, recorded_at=recorded_at, supersedes=old.fact_id
        )
        self.facts.append(new)
        return new

    def as_of(
        self,
        subject: str,
        attribute: str,
        *,
        valid_at: datetime,
        known_at: datetime,
        scope: str = COMPANY_SCOPE,
    ) -> Fact | None:
        """Fact true at valid_at as known at known_at; a specific scope beats the company rule."""

        def visible(f: Fact, s: str) -> bool:
            return (
                (f.subject, f.attribute, f.scope) == (subject, attribute, s)
                and f.valid_from <= valid_at
                and (f.valid_to is None or valid_at < f.valid_to)
                and f.recorded_at <= known_at
                and (f.superseded_at is None or known_at < f.superseded_at)
            )

        hits = [f for f in self.facts if visible(f, scope)]
        if not hits and scope != COMPANY_SCOPE:
            hits = [f for f in self.facts if visible(f, COMPANY_SCOPE)]
        return max(hits, key=lambda f: f.valid_from) if hits else None

    def current(
        self, subject: str, attribute: str, *, now: datetime, scope: str = COMPANY_SCOPE
    ) -> Fact | None:
        return self.as_of(subject, attribute, valid_at=now, known_at=now, scope=scope)
