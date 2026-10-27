"""S05 offline: current/historical badges, source-rights revocation, ACK lifecycle.

Approval longevity is separate from current source-read rights: a settled
confirmation stays until it is withdrawn, while a revoked source right denies
every future body read. Invented/synthetic only. Does not close #29.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from .temporal import Fact

FactBadge = Literal["current", "historical", "future", "superseded"]


def badge_facts(facts: list[Fact], *, now: datetime) -> list[tuple[Fact, FactBadge]]:
    """Label each fact for display: current, historical, future-dated or superseded.

    A fact is current when it is true at `now` and was known at `now`; it is
    historical when it was true earlier (or was known earlier and has since been
    superseded); it is future when its valid_from is still ahead of `now`; an
    explicitly superseded fact is never current.
    """
    out: list[tuple[Fact, FactBadge]] = []
    for f in facts:
        if f.superseded_at is not None and f.superseded_at <= now:
            out.append((f, "superseded"))
        elif f.valid_from > now:
            out.append((f, "future"))
        elif f.valid_to is not None and now >= f.valid_to:
            out.append((f, "historical"))
        elif f.recorded_at > now:
            out.append((f, "future"))
        elif f.valid_from <= now and (f.valid_to is None or now < f.valid_to):
            out.append((f, "current"))
        else:
            out.append((f, "historical"))
    return out


@dataclass
class SourceRightsRegistry:
    """Current source-body read rights, independent of approval longevity."""

    _granted: dict[tuple[str, str], bool] = field(default_factory=dict)

    def grant(self, source_id: str, subject: str) -> None:
        self._granted[(source_id, subject)] = True

    def revoke(self, source_id: str, subject: str) -> None:
        self._granted[(source_id, subject)] = False

    def can_read(self, source_id: str, subject: str) -> bool:
        return self._granted.get((source_id, subject), False)


AckState = Literal["pending", "acknowledged", "withdrawn"]


@dataclass(frozen=True)
class ConfirmationAck:
    confirmation_id: UUID
    subject: str
    source_ids: tuple[str, ...]
    state: AckState
    acknowledged_at: datetime | None = None
    withdrawn_at: datetime | None = None


@dataclass
class AckRegistry:
    """Scoped confirmation ACK lifecycle under current source-read rights."""

    rights: SourceRightsRegistry
    _acks: dict[UUID, ConfirmationAck] = field(default_factory=dict)

    def open(self, confirmation_id: UUID, *, subject: str, source_ids: tuple[str, ...]) -> ConfirmationAck:
        if confirmation_id in self._acks:
            raise ValueError("confirmation already opened")
        ack = ConfirmationAck(confirmation_id, subject, tuple(source_ids), "pending")
        self._acks[confirmation_id] = ack
        return ack

    def acknowledge(self, confirmation_id: UUID, *, at: datetime) -> ConfirmationAck:
        ack = self._acks[confirmation_id]
        if ack.state != "pending":
            raise ValueError(f"cannot acknowledge from state {ack.state}")
        for source_id in ack.source_ids:
            if not self.rights.can_read(source_id, ack.subject):
                raise PermissionError("current source-read right required to acknowledge")
        updated = ConfirmationAck(
            ack.confirmation_id, ack.subject, ack.source_ids, "acknowledged", acknowledged_at=at
        )
        self._acks[confirmation_id] = updated
        return updated

    def withdraw(self, confirmation_id: UUID, *, subject: str, at: datetime) -> ConfirmationAck:
        ack = self._acks[confirmation_id]
        if ack.subject != subject:
            raise PermissionError("only the confirming subject may withdraw")
        if ack.state == "withdrawn":
            raise ValueError("already withdrawn")
        updated = ConfirmationAck(
            ack.confirmation_id,
            ack.subject,
            ack.source_ids,
            "withdrawn",
            acknowledged_at=ack.acknowledged_at,
            withdrawn_at=at,
        )
        self._acks[confirmation_id] = updated
        return updated

    def status(self, confirmation_id: UUID) -> ConfirmationAck:
        return self._acks[confirmation_id]

    def settled(self, confirmation_id: UUID, *, now: datetime) -> bool:
        """True while the exact approved assertion remains in force (longevity).

        Revocation of source rights does NOT settle or erase an ACK; only an
        explicit withdrawal does. `now` bounds the settled window for callers
        that require a current witness.
        """
        ack = self._acks[confirmation_id]
        if ack.state == "withdrawn":
            return False
        if ack.state == "acknowledged":
            return ack.acknowledged_at is not None and ack.acknowledged_at <= now
        return False
