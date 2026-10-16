"""Offline identity resolution: same-name people stay distinct unless evidence links them."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4


def _norm(name: str) -> str:
    return " ".join(name.casefold().split())


@dataclass(frozen=True)
class Person:
    person_id: UUID
    display_name: str
    discriminators: frozenset[tuple[str, str]]


@dataclass(frozen=True)
class Resolution:
    person_id: UUID | None
    candidates: tuple[UUID, ...]
    ambiguous: bool


@dataclass
class IdentityRegistry:
    """Resolve mentions by strong discriminators (email, employee id, team), never by name alone."""

    people: dict[UUID, Person] = field(default_factory=dict)

    def register(self, display_name: str, **discriminators: str) -> Person:
        if not discriminators:
            raise ValueError("a person needs at least one discriminator besides the name")
        person = Person(
            uuid4(),
            display_name,
            frozenset((k, v.casefold()) for k, v in discriminators.items()),
        )
        self.people[person.person_id] = person
        return person

    def resolve(self, name: str, **hints: str) -> Resolution:
        named = [p for p in self.people.values() if _norm(p.display_name) == _norm(name)]
        wanted = {(k, v.casefold()) for k, v in hints.items()}
        if wanted:
            named = [p for p in named if wanted <= p.discriminators]
        ids = tuple(p.person_id for p in named)
        if len(ids) == 1:
            return Resolution(ids[0], ids, False)
        return Resolution(None, ids, len(ids) > 1)
