"""Deterministic information-need selection. The model only phrases the chosen need."""
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence


@dataclass(frozen=True)
class FieldSpec:
    name: str
    priority: int = 100


@dataclass(frozen=True)
class Conflict:
    field: str
    values: tuple[str, ...]
    source_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class InformationNeed:
    kind: str  # 'conflict' | 'missing' | 'example'
    field: str
    detail: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f'{self.kind}:{self.field}'


def _empty(value) -> bool:
    return value is None or value == ''


def select_need(fields: Sequence[FieldSpec], known: Mapping[str, object],
                conflicts: Iterable[Conflict] = (), asked: Iterable[str] = (),
                declined: Iterable[str] = ()) -> Optional[InformationNeed]:
    """Conflicts first, then missing fields by (priority, name), then example requests.
    Needs already asked or answered "I don't know" are never re-selected."""
    skip = set(asked) | set(declined)
    for c in sorted(conflicts, key=lambda c: c.field):
        need = InformationNeed('conflict', c.field, tuple(sorted(set(c.values))))
        if need.key not in skip:
            return need
    ordered = sorted(fields, key=lambda f: (f.priority, f.name))
    for f in ordered:
        need = InformationNeed('missing', f.name)
        if _empty(known.get(f.name)) and need.key not in skip:
            return need
    for f in ordered:
        need = InformationNeed('example', f.name)
        if not _empty(known.get(f.name)) and need.key not in skip:
            return need
    return None
