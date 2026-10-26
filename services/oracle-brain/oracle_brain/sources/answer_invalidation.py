"""S04 offline: current answers become unservable when their sources change.

A source revision or withdrawal invalidates every dependent answer immediately.
The answer record is retained for audit but is never served again until it is
recomputed against the current revision. Invented/synthetic only. Does not
close #28.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable
from uuid import UUID, uuid4


class AnswerStaleReason(str, Enum):
    SOURCE_REVISED = "source_revised"
    SOURCE_WITHDRAWN = "source_withdrawn"


@dataclass(frozen=True)
class AnswerSourceRef:
    source_id: str
    revision: int


@dataclass(frozen=True)
class AnswerRecord:
    answer_id: UUID
    source_refs: tuple[AnswerSourceRef, ...]


@dataclass
class AnswerInvalidationRegistry:
    """Track answer→source dependencies and enforce current-source serving."""

    _answers: dict[UUID, AnswerRecord] = field(default_factory=dict)
    _stale: dict[UUID, AnswerStaleReason] = field(default_factory=dict)
    _current_revision: dict[str, int] = field(default_factory=dict)

    def record(
        self,
        source_refs: Iterable[AnswerSourceRef],
        *,
        answer_id: UUID | None = None,
    ) -> AnswerRecord:
        refs = tuple(source_refs)
        if not refs:
            raise ValueError("an answer must cite at least one source")
        record = AnswerRecord(answer_id or uuid4(), refs)
        self._answers[record.answer_id] = record
        for ref in refs:
            known = self._current_revision.get(ref.source_id)
            if known is None or ref.revision > known:
                self._current_revision[ref.source_id] = ref.revision
        return record

    def on_revision(self, source_id: str, new_revision: int) -> list[UUID]:
        """Mark answers that cite an older revision of this source as stale."""
        if new_revision < self._current_revision.get(source_id, 0):
            raise ValueError("revision cannot move backwards")
        self._current_revision[source_id] = new_revision
        hit: list[UUID] = []
        for answer in self._answers.values():
            if answer.answer_id in self._stale:
                continue
            if any(
                ref.source_id == source_id and ref.revision < new_revision
                for ref in answer.source_refs
            ):
                self._stale[answer.answer_id] = AnswerStaleReason.SOURCE_REVISED
                hit.append(answer.answer_id)
        return hit

    def on_withdrawal(self, source_id: str, revision: int | None = None) -> list[UUID]:
        """Mark answers that cite a withdrawn source (any or one revision) stale."""
        hit: list[UUID] = []
        for answer in self._answers.values():
            if answer.answer_id in self._stale:
                continue
            if any(
                ref.source_id == source_id
                and (revision is None or ref.revision == revision)
                for ref in answer.source_refs
            ):
                self._stale[answer.answer_id] = AnswerStaleReason.SOURCE_WITHDRAWN
                hit.append(answer.answer_id)
        return hit

    def is_servable(self, answer_id: UUID) -> bool:
        if answer_id not in self._answers:
            raise KeyError(answer_id)
        return answer_id not in self._stale

    def stale_reason(self, answer_id: UUID) -> AnswerStaleReason | None:
        return self._stale.get(answer_id)

    def dependents(self, source_id: str) -> list[UUID]:
        return [
            a.answer_id
            for a in self._answers.values()
            if any(ref.source_id == source_id for ref in a.source_refs)
        ]
