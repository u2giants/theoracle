"""Source withdrawal tombstones: deletion blocks serving and re-applies after restore.

Pure decision logic only. Callers own authorization, persistence and the
actual invalidation of dependent artifacts. Backup restoration must re-apply
every tombstone before any source is served again.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .revisions import SourceRevision

# Dependent artifact kinds that must be invalidated when a source is withdrawn.
# Order is the propagation order callers must follow.
DEPENDENT_ARTIFACT_KINDS: tuple[str, ...] = (
    "graph",
    "embeddings",
    "summaries",
    "recommendations",
    "caches",
    "recoverable_checkpoints",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class WithdrawalTombstone(_StrictModel):
    schema_version: Literal[1] = 1
    source_id: str = Field(min_length=1, max_length=128)
    revision: Annotated[int, Field(ge=1)]
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    withdrawn_at: datetime
    reason: str = Field(min_length=1, max_length=1024)

    @model_validator(mode="after")
    def _aware(self) -> "WithdrawalTombstone":
        if self.withdrawn_at.tzinfo is None or self.withdrawn_at.utcoffset() is None:
            raise ValueError("withdrawn_at must be timezone-aware")
        return self


class WithdrawalRecord(_StrictModel):
    tombstone: WithdrawalTombstone
    blocked_serving: bool
    invalidation_targets: tuple[str, ...]


def withdraw_revision(
    *,
    revision: SourceRevision,
    reason: str,
    existing: tuple[WithdrawalTombstone, ...] = (),
    withdrawn_at: datetime | None = None,
) -> WithdrawalRecord:
    """Record a tombstone and compute immediate serving block and propagation.

    A second withdrawal of the same source/revision is refused so that a
    withdrawal is never silently replaced or replayed.
    """
    if type(revision) is not SourceRevision:
        raise TypeError("exact SourceRevision required")
    if not isinstance(reason, str) or not reason:
        raise ValueError("reason must be a nonempty string")
    for tombstone in existing:
        if type(tombstone) is not WithdrawalTombstone:
            raise TypeError("existing must contain exact WithdrawalTombstone values")
        if tombstone.source_id == revision.source_id and tombstone.revision == revision.revision:
            raise ValueError("source revision is already withdrawn")
    moment = withdrawn_at or datetime.now(timezone.utc)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("withdrawn_at must be timezone-aware")
    tombstone = WithdrawalTombstone(
        source_id=revision.source_id,
        revision=revision.revision,
        original_sha256=revision.original_sha256,
        withdrawn_at=moment,
        reason=reason,
    )
    return WithdrawalRecord(
        tombstone=tombstone,
        blocked_serving=True,
        invalidation_targets=DEPENDENT_ARTIFACT_KINDS,
    )


def is_serveable(
    *,
    revision: SourceRevision,
    tombstones: tuple[WithdrawalTombstone, ...],
) -> bool:
    """A withdrawn source revision is never serveable; history is preserved."""
    if type(revision) is not SourceRevision:
        raise TypeError("exact SourceRevision required")
    for tombstone in tombstones:
        if type(tombstone) is not WithdrawalTombstone:
            raise TypeError("tombstones must contain exact WithdrawalTombstone values")
        if tombstone.source_id == revision.source_id and tombstone.revision == revision.revision:
            return False
    return True


def reapply_tombstones_after_restore(
    *,
    restored: tuple[SourceRevision, ...],
    tombstones: tuple[WithdrawalTombstone, ...],
) -> tuple[SourceRevision, ...]:
    """Backup restoration must drop every tombstoned revision before serving.

    Returns only the restored revisions that are still serveable. Restoring a
    withdrawn revision never resurrects it; the tombstone wins.
    """
    for item in restored:
        if type(item) is not SourceRevision:
            raise TypeError("restored must contain exact SourceRevision values")
    for tombstone in tombstones:
        if type(tombstone) is not WithdrawalTombstone:
            raise TypeError("tombstones must contain exact WithdrawalTombstone values")
    return tuple(
        item
        for item in restored
        if all(
            tombstone.source_id != item.source_id or tombstone.revision != item.revision
            for tombstone in tombstones
        )
    )


def invalidation_targets_for(
    *,
    revision: SourceRevision,
    tombstones: tuple[WithdrawalTombstone, ...],
) -> tuple[str, ...]:
    """Propagation targets when a source revision is withdrawn; empty if live."""
    if not is_serveable(revision=revision, tombstones=tombstones):
        return DEPENDENT_ARTIFACT_KINDS
    return ()
