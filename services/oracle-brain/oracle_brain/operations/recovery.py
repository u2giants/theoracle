"""Pure restore/replay reconciliation: receipts, idempotent replay, tombstones.

Offline building block for S13. Validates supplied restore evidence and a
durable accepted-event ledger against a projection snapshot. This module never
performs a capture, restore, database write, or platform action, and never
claims hosted disaster-recovery acceptance or measured RPO/RTO.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal, Mapping

HEX = "0123456789abcdef"
TombstoneReason = Literal["deleted", "denied", "revoked"]


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(ch in HEX for ch in value)


@dataclass(frozen=True)
class AcceptedEvent:
    """One durable accepted ledger event that must be replayed or accounted."""

    event_id: str
    subject_id: str
    payload_digest: str
    acknowledged: bool = True

    def __post_init__(self) -> None:
        if not self.event_id:
            raise ValueError("event_id required")
        if not self.subject_id:
            raise ValueError("subject_id required")
        if not _is_digest(self.payload_digest):
            raise ValueError("payload_digest must be sha256 hex")


@dataclass(frozen=True)
class Tombstone:
    """A reinstated deletion, denial or revocation that outranks restored data."""

    subject_id: str
    reason: TombstoneReason

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise ValueError("subject_id required")


@dataclass(frozen=True)
class BlobCopy:
    """One private blob restored from backup; digest binds content, never path."""

    digest: str
    size: int

    def __post_init__(self) -> None:
        if not _is_digest(self.digest):
            raise ValueError("blob digest must be sha256 hex")
        if self.size < 0:
            raise ValueError("blob size must be non-negative")


@dataclass(frozen=True)
class RestoreReceipt:
    """What a restore claims to have landed; checked, never trusted alone."""

    target_id: str
    source_metadata_restored: bool
    blobs: tuple[BlobCopy, ...]
    tombstone_count: int
    accepted_event_count: int
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not self.target_id:
            raise ValueError("target_id required")
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        if self.tombstone_count < 0 or self.accepted_event_count < 0:
            raise ValueError("counts must be non-negative")


@dataclass(frozen=True)
class ProjectionState:
    """Snapshot of the rebuilt projection after restore and/or replay."""

    applied_event_ids: frozenset[str] = frozenset()
    readable_subject_ids: frozenset[str] = frozenset()
    pending_effect_nonces: frozenset[str] = frozenset()
    sent_effect_nonces: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ReplayResult:
    state: ProjectionState
    applied: tuple[str, ...]
    duplicates: tuple[str, ...]
    blocked: tuple[str, ...]


def replay(
    events: tuple[AcceptedEvent, ...] | list[AcceptedEvent],
    state: ProjectionState,
) -> ReplayResult:
    """Apply accepted events idempotently; a second apply is a no-op.

    Events whose subject is tombstoned (absent from readable_subject_ids once
    enforcement has run) are blocked, never applied. Sent effect nonces are
    never re-dispatched, so a crash resume cannot duplicate a send.
    """
    applied: list[str] = []
    duplicates: list[str] = []
    blocked: list[str] = []
    applied_ids = set(state.applied_event_ids)
    readable = set(state.readable_subject_ids)
    for event in events:
        if event.event_id in applied_ids:
            duplicates.append(event.event_id)
            continue
        if event.subject_id not in readable:
            blocked.append(event.event_id)
            continue
        applied_ids.add(event.event_id)
        readable.add(event.subject_id)
        applied.append(event.event_id)
    return ReplayResult(
        state=replace(
            state,
            applied_event_ids=frozenset(applied_ids),
            readable_subject_ids=frozenset(readable),
        ),
        applied=tuple(applied),
        duplicates=tuple(duplicates),
        blocked=tuple(blocked),
    )


def enforce_tombstones(
    state: ProjectionState,
    tombstones: tuple[Tombstone, ...] | list[Tombstone],
) -> ProjectionState:
    """Reinstate deletions/denials/revocations before any read is accepted."""
    dead = {t.subject_id for t in tombstones}
    return replace(
        state,
        readable_subject_ids=frozenset(
            subject for subject in state.readable_subject_ids if subject not in dead
        ),
    )


def resume_effects(state: ProjectionState) -> tuple[str, ...]:
    """Nonces safe to redispatch after a controlled host failure.

    An already-sent nonce is never returned, so recovery cannot produce a
    duplicate write or send; pending nonces remain for the appointed attempt.
    """
    return tuple(sorted(state.pending_effect_nonces - state.sent_effect_nonces))


def reconcile(
    receipt: RestoreReceipt,
    events: tuple[AcceptedEvent, ...] | list[AcceptedEvent],
    tombstones: tuple[Tombstone, ...] | list[Tombstone],
    state: ProjectionState,
) -> list[str]:
    """Return consistency problems; empty list means the restore checks out.

    Enforces the S13 offline invariants: acknowledged events are accounted for
    (applied or duplicate, never dropped), denied/deleted subjects stay
    unreadable, and receipt counts match the supplied evidence.
    """
    problems: list[str] = []
    applied = state.applied_event_ids
    seen: set[str] = set()
    for event in events:
        if event.event_id in seen:
            problems.append(f"duplicate ledger event {event.event_id}")
            continue
        seen.add(event.event_id)
        if event.acknowledged and event.event_id not in applied:
            problems.append(f"acknowledged event unaccounted {event.event_id}")
    dead = {t.subject_id for t in tombstones}
    leaked = sorted(dead & set(state.readable_subject_ids))
    for subject in leaked:
        problems.append(f"tombstoned subject readable {subject}")
    if receipt.accepted_event_count != len(events):
        problems.append("receipt accepted_event_count differs from ledger")
    if receipt.tombstone_count != len(tombstones):
        problems.append("receipt tombstone_count differs from tombstones")
    if not receipt.source_metadata_restored:
        problems.append("source metadata not restored")
    digests = [blob.digest for blob in receipt.blobs]
    if len(digests) != len(set(digests)):
        problems.append("duplicate blob digest in receipt")
    return problems
