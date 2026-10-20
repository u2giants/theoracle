"""Withdrawal tombstones that block serving and propagate to derived stores.

A tombstone blocks serving immediately, then each registered derived store
(graph, embeddings, summaries, recommendations, caches, checkpoints) purges.
Restoring from a backup reapplies every tombstone before serving resumes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Protocol

DERIVED_STORES = ("graph", "embeddings", "summaries", "recommendations", "caches", "checkpoints")


class DerivedStore(Protocol):
    def purge(self, source_id: str, revision: int | None) -> None: ...


@dataclass(frozen=True)
class Tombstone:
    source_id: str
    revision: int | None  # None withdraws every revision of the source


def _require_all(stores: dict[str, DerivedStore]) -> None:
    missing = set(DERIVED_STORES) - set(stores)
    if missing:
        raise ValueError(f"withdrawal must reach every derived store: {sorted(missing)}")


class WithdrawalRegistry:
    def __init__(self, stores: dict[str, DerivedStore]):
        _require_all(stores)
        self._stores = stores
        self._tombstones: list[Tombstone] = []

    def withdraw(self, source_id: str, revision: int | None = None) -> Tombstone:
        tomb = Tombstone(source_id, revision)
        self._tombstones.append(tomb)  # serving is blocked before any purge runs
        for name in DERIVED_STORES:
            self._stores[name].purge(source_id, revision)
        return tomb

    def is_servable(self, source_id: str, revision: int) -> bool:
        return not any(t.source_id == source_id and t.revision in (None, revision)
                       for t in self._tombstones)

    def tombstones(self) -> list[Tombstone]:
        return list(self._tombstones)

    def restore(self, stores: dict[str, DerivedStore], tombstones: Iterable[Tombstone],
                ready: Callable[[], None]) -> None:
        """Reapply durable tombstones to restored stores, then allow serving."""
        _require_all(stores)
        self._stores = stores
        self._tombstones = list(tombstones)
        for tomb in self._tombstones:
            for name in DERIVED_STORES:
                stores[name].purge(tomb.source_id, tomb.revision)
        ready()
