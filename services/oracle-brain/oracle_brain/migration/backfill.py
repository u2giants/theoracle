"""Bounded resumable backfill cursor and idempotent change-delta replay."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from oracle_brain.migration.inventory import LegacyChange, LegacyChangeKind, LegacySourceRecord

_NO_WATERMARK = -1


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1] = 1


class ReplayState(_StrictModel):
    """Durable ordered cursor: last applied watermark and applied change ids."""
    last_watermark: int = Field(ge=_NO_WATERMARK)
    applied_change_ids: tuple[str, ...] = ()

    @field_validator("applied_change_ids")
    @classmethod
    def _unique(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("applied change ids must be unique")
        for change_id in value:
            if not change_id:
                raise ValueError("applied change ids must be nonempty")
        return value

    def has_applied(self, change_id: str) -> bool:
        return change_id in self.applied_change_ids


class AppliedChange(_StrictModel):
    change_id: str
    watermark: int = Field(ge=0)
    kind: LegacyChangeKind
    legacy_id: str

    @field_validator("change_id", "legacy_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        if not value:
            raise ValueError("applied change requires identity")
        return value


class ReplayOutcome(_StrictModel):
    """Result of one idempotent replay step; never mutates a live store."""
    state: ReplayState
    action: Literal["applied", "duplicate", "rejected"]
    change_id: str
    kind: LegacyChangeKind | None = None
    legacy_id: str | None = None

    @model_validator(mode="after")
    def _action_shape(self) -> "ReplayOutcome":
        if self.action == "applied":
            if self.kind is None or self.legacy_id is None:
                raise ValueError("applied outcome requires kind and legacy id")
        elif self.kind is not None or self.legacy_id is not None:
            raise ValueError("non-applied outcome carries no applied identity")
        return self


class ChangeApplication(_StrictModel):
    """What a replayed change does to the replacement view of one legacy row."""
    legacy_id: str
    kind: LegacyChangeKind
    record: LegacySourceRecord | None = None

    @model_validator(mode="after")
    def _shape(self) -> "ChangeApplication":
        if self.kind == "delete":
            if self.record is not None:
                raise ValueError("delete application carries no record")
        elif self.record is None:
            raise ValueError("non-delete application requires a record")
        elif self.record.legacy_id != self.legacy_id:
            raise ValueError("application record identity must match legacy id")
        return self


def apply_delta(state: ReplayState, change: LegacyChange) -> ReplayOutcome:
    """Idempotent replay: duplicates are no-ops; new changes need a higher watermark."""
    if state.has_applied(change.change_id):
        return ReplayOutcome(state=state, action="duplicate", change_id=change.change_id)
    if change.watermark <= state.last_watermark:
        return ReplayOutcome(state=state, action="rejected", change_id=change.change_id)
    next_state = ReplayState(
        last_watermark=change.watermark,
        applied_change_ids=state.applied_change_ids + (change.change_id,),
    )
    return ReplayOutcome(
        state=next_state,
        action="applied",
        change_id=change.change_id,
        kind=change.kind,
        legacy_id=change.legacy_id,
    )


def application_for(change: LegacyChange) -> ChangeApplication:
    return ChangeApplication(
        legacy_id=change.legacy_id,
        kind=change.kind,
        record=change.record,
    )


def replay_batch(
    state: ReplayState,
    changes: tuple[LegacyChange, ...],
) -> tuple[ReplayState, tuple[ChangeApplication, ...], tuple[ReplayOutcome, ...]]:
    """Replay an ordered batch; duplicate change ids never re-apply."""
    current = state
    applications: list[ChangeApplication] = []
    outcomes: list[ReplayOutcome] = []
    for change in changes:
        outcome = apply_delta(current, change)
        outcomes.append(outcome)
        current = outcome.state
        if outcome.action == "applied":
            applications.append(application_for(change))
    return current, tuple(applications), tuple(outcomes)


class BackfillBatch(_StrictModel):
    """Bounded batch descriptor with resumable cursor and failure quarantine."""
    batch_index: int = Field(ge=0)
    cursor_before: ReplayState
    cursor_after: ReplayState
    applied: tuple[AppliedChange, ...]
    quarantined_change_ids: tuple[str, ...] = ()
    failed_change_ids: tuple[str, ...] = ()

    @field_validator("quarantined_change_ids", "failed_change_ids")
    @classmethod
    def _nonempty_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for change_id in value:
            if not change_id:
                raise ValueError("quarantine and failure ids must be nonempty")
        return value

    @model_validator(mode="after")
    def _disjoint(self) -> "BackfillBatch":
        applied_ids = {item.change_id for item in self.applied}
        overlap = applied_ids & set(self.quarantined_change_ids)
        overlap |= applied_ids & set(self.failed_change_ids)
        overlap |= set(self.quarantined_change_ids) & set(self.failed_change_ids)
        if overlap:
            raise ValueError("applied, quarantined and failed change ids must be disjoint")
        return self


def build_batch(
    *,
    batch_index: int,
    cursor_before: ReplayState,
    changes: tuple[LegacyChange, ...],
    quarantined_change_ids: tuple[str, ...] = (),
    failed_change_ids: tuple[str, ...] = (),
) -> BackfillBatch:
    batch_ids = {change.change_id for change in changes}
    skip = set(quarantined_change_ids) | set(failed_change_ids)
    if not skip <= batch_ids:
        raise ValueError("quarantine and failure ids must come from this batch")
    to_apply = tuple(change for change in changes if change.change_id not in skip)
    cursor_after, _applications, outcomes = replay_batch(cursor_before, to_apply)
    applied = tuple(
        AppliedChange(
            change_id=outcome.change_id,
            watermark=change.watermark,
            kind=outcome.kind,  # type: ignore[arg-type]
            legacy_id=outcome.legacy_id,  # type: ignore[arg-type]
        )
        for change, outcome in zip(to_apply, outcomes)
        if outcome.action == "applied"
    )
    return BackfillBatch(
        batch_index=batch_index,
        cursor_before=cursor_before,
        cursor_after=cursor_after,
        applied=applied,
        quarantined_change_ids=quarantined_change_ids,
        failed_change_ids=failed_change_ids,
    )


class DeltaAdapter(_StrictModel):
    """Pure snapshot of the chosen change-feed mechanism; pause metadata is recorded."""
    mechanism: Literal["change_feed", "write_pause_snapshot"]
    pause_seconds: float | None = None

    @model_validator(mode="after")
    def _mechanism(self) -> "DeltaAdapter":
        if self.mechanism == "change_feed":
            if self.pause_seconds is not None:
                raise ValueError("change feed records no write pause")
        else:
            if self.pause_seconds is None or self.pause_seconds < 0:
                raise ValueError("write pause snapshot requires measured pause duration")
        return self
