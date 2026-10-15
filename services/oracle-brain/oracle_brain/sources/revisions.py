"""Content-addressed source revisions.

Same identity and bytes never re-ingest; a genuine edit creates a new revision.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..ingest.normalize import content_hash


@dataclass(frozen=True)
class Revision:
    source_id: str
    number: int
    digest: str


class RevisionLedger:
    def __init__(self) -> None:
        self._by_source: dict[str, list[Revision]] = {}

    def record(self, source_id: str, data: bytes) -> tuple[Revision, bool]:
        """Return (revision, created). created=False means an exact duplicate."""
        digest = content_hash(data)
        history = self._by_source.setdefault(source_id, [])
        # Only a repeat of the current bytes is a duplicate; reverting to an
        # older revision's bytes is a genuine edit and becomes current.
        if history and history[-1].digest == digest:
            return history[-1], False
        revision = Revision(source_id, len(history) + 1, digest)
        history.append(revision)
        return revision, True

    def current(self, source_id: str) -> Revision | None:
        history = self._by_source.get(source_id)
        return history[-1] if history else None

    def history(self, source_id: str) -> list[Revision]:
        return list(self._by_source.get(source_id, []))
