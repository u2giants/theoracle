"""Pure scoped migration replay proposals. No feed execution, writes or authority.

Payload seals and cursor checks describe complete immutable state transitions;
they do not qualify originals or admit migration, serving or company truth.
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import Field, field_validator, model_validator

from oracle_brain.migration.inventory import LegacyChange, ReplayScope
from oracle_brain.operating_model.contracts import StrictRecord, digest

MAX_BATCH_LIMIT = 1000
DEFAULT_BATCH_LIMIT = 100
_SCOPE_FIELDS = ('workspace_id', 'inventory_id', 'inventory_digest', 'feed_id')


def _same_scope(left: ReplayScope, right: ReplayScope) -> bool:
    return all(getattr(left, key) == getattr(right, key) for key in _SCOPE_FIELDS)


def _scope_values(scope: ReplayScope) -> dict:
    return {key: getattr(scope, key) for key in _SCOPE_FIELDS}


class SealedChange(StrictRecord):
    change: LegacyChange
    payload_digest: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def _exact_payload(self) -> 'SealedChange':
        if self.payload_digest != digest(self.change.model_dump(mode='json')):
            raise ValueError('event payload digest mismatch')
        return self


def seal_change(change: LegacyChange) -> SealedChange:
    return SealedChange(change=change, payload_digest=digest(change.model_dump(mode='json')))


class PendingChange(StrictRecord):
    event: SealedChange
    reason: Literal['failed', 'quarantined', 'blocked']


class FailureRecord(StrictRecord):
    event: SealedChange
    reason: Literal['failed', 'quarantined']


class ReplayState(ReplayScope):
    read_watermark: int = Field(strict=True, ge=-1, default=-1)
    applied_watermark: int = Field(strict=True, ge=-1, default=-1)
    applied_events: tuple[SealedChange, ...] = ()
    pending_events: tuple[PendingChange, ...] = ()
    failure_history: tuple[FailureRecord, ...] = ()
    resolved_change_ids: tuple[str, ...] = ()

    @model_validator(mode='after')
    def _complete_history(self) -> 'ReplayState':
        events = list(self.applied_events) + [pending.event for pending in self.pending_events]
        ids = [item.change.change_id for item in events]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate event identity in replay state')
        marks = [item.change.watermark for item in events]
        if marks != sorted(set(marks)):
            raise ValueError('replay history must have strictly ascending watermarks')
        if any(not _same_scope(self, item.change) for item in events):
            raise ValueError('foreign replay event scope')
        expected_read = marks[-1] if marks else -1
        expected_applied = self.applied_events[-1].change.watermark if self.applied_events else -1
        if self.read_watermark != expected_read or self.applied_watermark != expected_applied:
            raise ValueError('cursor watermark does not match exact event history')
        if self.pending_events and self.pending_events[0].reason == 'blocked':
            raise ValueError('pending history requires an unresolved failed or quarantined event')
        known = {event.change.change_id: event for event in events}
        issues = {(failure.event.change.change_id, failure.reason) for failure in self.failure_history}
        if len(issues) != len(self.failure_history):
            raise ValueError('duplicate failure history')
        for failure in self.failure_history:
            if known.get(failure.event.change.change_id) != failure.event:
                raise ValueError('failure history does not bind exact retained event')
        resolved = set(self.resolved_change_ids)
        issue_ids = {key for key, _ in issues}
        if len(resolved) != len(self.resolved_change_ids) or not resolved <= issue_ids:
            raise ValueError('resolution history must identify unique retained failures')
        pending = {item.event.change.change_id: item for item in self.pending_events}
        applied_ids = {item.change.change_id for item in self.applied_events}
        for key in issue_ids - resolved:
            if key not in pending or pending[key].reason == 'blocked':
                raise ValueError('unresolved failure cannot be applied or silently unblocked')
        for key, item in pending.items():
            if item.reason != 'blocked' and ((key, item.reason) not in issues or key in resolved):
                raise ValueError('pending failure must retain its unresolved history')
        if issue_ids & applied_ids - resolved:
            raise ValueError('applied failure requires exact recorded resolution')
        return self


class ReplayOutcome(StrictRecord):
    change_id: str = Field(min_length=1)
    action: Literal['applied', 'duplicate', 'pending', 'resolved']


def _validate_ids(value: tuple[str, ...]) -> tuple[str, ...]:
    if len(value) != len(set(value)) or any(not key.strip() for key in value):
        raise ValueError('operation event ids must be unique and nonblank')
    return value


def _transition(state, changes, failed_ids, quarantine_ids, resolve_ids, batch_limit):
    # Pydantic copy/update helpers intentionally skip validation. Revalidate
    # nested snapshots so caller-constructed objects cannot bypass these rules.
    state = ReplayState.model_validate_json(state.model_dump_json())
    changes = tuple(LegacyChange.model_validate_json(item.model_dump_json()) for item in changes)
    if type(batch_limit) is not int or not 1 <= batch_limit <= MAX_BATCH_LIMIT:
        raise ValueError('batch limit must be a positive bounded integer')
    if len(changes) > batch_limit:
        raise ValueError('supplied batch exceeds its limit')
    failed, quarantine, resolve = set(failed_ids), set(quarantine_ids), set(resolve_ids)
    if failed & quarantine or (failed | quarantine) & resolve:
        raise ValueError('failure, quarantine and resolution ids must be disjoint')
    old = {item.change.change_id: item for item in state.applied_events}
    old.update({item.event.change.change_id: item.event for item in state.pending_events})
    supplied = {}
    unseen = []
    last_unseen_watermark = state.read_watermark
    # Validate the entire input before computing any proposed application.
    for change in changes:
        if not _same_scope(state, change):
            raise ValueError('foreign replay event scope')
        sealed = seal_change(change)
        key = change.change_id
        prior = supplied.get(key) or old.get(key)
        if prior is not None:
            if prior != sealed:
                raise ValueError('event identity collision with changed payload')
        else:
            if change.watermark <= last_unseen_watermark:
                raise ValueError('unseen event watermarks must be strictly ascending beyond read cursor')
            last_unseen_watermark = change.watermark
            unseen.append(sealed)
        supplied[key] = sealed
    if not (failed | quarantine | resolve) <= set(supplied):
        raise ValueError('operation ids must appear with exact payload in supplied batch')
    applied_ids = {event.change.change_id for event in state.applied_events}
    if (failed | quarantine) & applied_ids:
        raise ValueError('an applied event cannot be relabeled as pending')
    pending = {item.event.change.change_id: item for item in state.pending_events}
    for key in resolve:
        if key not in pending or pending[key].reason == 'blocked':
            raise ValueError('resolution requires an independently failed or quarantined pending event')
    issue_history = list(state.failure_history)
    known_issues = {(item.event.change.change_id, item.reason) for item in issue_history}
    resolved = set(state.resolved_change_ids)
    staged = list(state.pending_events) + [PendingChange(event=event, reason='blocked') for event in unseen]
    updated = []
    for item in staged:
        key = item.event.change.change_id
        reason = 'failed' if key in failed else 'quarantined' if key in quarantine else item.reason
        if key in failed | quarantine:
            resolved.discard(key)
            if (key, reason) not in known_issues:
                issue_history.append(FailureRecord(event=item.event, reason=reason))
                known_issues.add((key, reason))
        if key in resolve:
            resolved.add(key)
            reason = 'blocked'
        updated.append(PendingChange(event=item.event, reason=reason))
    applications = []
    remaining = []
    stopped = False
    for item in updated:
        if item.reason in ('failed', 'quarantined'):
            stopped = True
        if stopped:
            remaining.append(item)
        else:
            applications.append(item.event)
    applied = state.applied_events + tuple(applications)
    all_events = list(applied) + [item.event for item in remaining]
    next_state = ReplayState(**_scope_values(state),
        read_watermark=all_events[-1].change.watermark if all_events else -1,
        applied_watermark=applied[-1].change.watermark if applied else -1,
        applied_events=applied, pending_events=tuple(remaining),
        failure_history=tuple(issue_history), resolved_change_ids=tuple(sorted(resolved)))
    newly_applied = {event.change.change_id for event in applications}
    outcomes = []
    for change in changes:
        key = change.change_id
        action = ('resolved' if key in resolve else
                  'applied' if key in newly_applied else
                  'pending' if key not in old or key in failed | quarantine else 'duplicate')
        outcomes.append(ReplayOutcome(change_id=key, action=action))
    return next_state, tuple(applications), tuple(outcomes)


class BackfillBatch(StrictRecord):
    """Exact atomic proposal, never evidence that target effects were executed.

    Before applying any descriptor, actual integration must independently check
    current authority and resolution evidence in its existing transaction.
    """
    batch_index: int = Field(strict=True, ge=0, default=0)
    batch_limit: int = Field(strict=True, ge=1, le=MAX_BATCH_LIMIT, default=DEFAULT_BATCH_LIMIT)
    cursor_before: ReplayState
    changes: tuple[LegacyChange, ...]
    failed_change_ids: tuple[str, ...] = ()
    quarantined_change_ids: tuple[str, ...] = ()
    resolve_pending_change_ids: tuple[str, ...] = ()
    cursor_after: ReplayState
    applications: tuple[SealedChange, ...]
    pending: tuple[PendingChange, ...]
    outcomes: tuple[ReplayOutcome, ...]

    @field_validator('failed_change_ids', 'quarantined_change_ids', 'resolve_pending_change_ids')
    @classmethod
    def _operation_ids(cls, value):
        return _validate_ids(value)

    @model_validator(mode='after')
    def _exact_transition(self) -> 'BackfillBatch':
        expected, applications, outcomes = _transition(self.cursor_before, self.changes,
            self.failed_change_ids, self.quarantined_change_ids,
            self.resolve_pending_change_ids, self.batch_limit)
        if self.cursor_after != expected or self.applications != applications:
            raise ValueError('batch cursor or application population is not the exact transition')
        if self.pending != expected.pending_events or self.outcomes != outcomes:
            raise ValueError('batch pending or outcome population is not the exact transition')
        return self


def replay_batch(state: ReplayState, changes: tuple[LegacyChange, ...], *,
                 failed_change_ids: tuple[str, ...] = (),
                 quarantined_change_ids: tuple[str, ...] = (),
                 resolve_pending_change_ids: tuple[str, ...] = (),
                 batch_index: int = 0, batch_limit: int = DEFAULT_BATCH_LIMIT) -> BackfillBatch:
    """Propose a sealed complete replay; duplicate delivery never resolves failure."""
    for ids in (failed_change_ids, quarantined_change_ids, resolve_pending_change_ids):
        _validate_ids(ids)
    after, applications, outcomes = _transition(state, changes, failed_change_ids,
        quarantined_change_ids, resolve_pending_change_ids, batch_limit)
    return BackfillBatch(batch_index=batch_index, batch_limit=batch_limit,
        cursor_before=state, changes=changes, failed_change_ids=failed_change_ids,
        quarantined_change_ids=quarantined_change_ids,
        resolve_pending_change_ids=resolve_pending_change_ids,
        cursor_after=after, applications=applications, pending=after.pending_events, outcomes=outcomes)


def build_batch(*, cursor_before: ReplayState, changes: tuple[LegacyChange, ...], **kwargs) -> BackfillBatch:
    return replay_batch(cursor_before, changes, **kwargs)


class DeltaAdapter(StrictRecord):
    mechanism: Literal['change_feed', 'write_pause_snapshot']
    pause_seconds: float | None = None

    @field_validator('pause_seconds', mode='before')
    @classmethod
    def _finite_duration(cls, value):
        if value is None:
            return None
        try:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError('pause duration must be finite and nonnegative')
            return float(value)
        except OverflowError as error:
            raise ValueError('pause duration must be finite and nonnegative') from error

    @model_validator(mode='after')
    def _mechanism(self) -> 'DeltaAdapter':
        if self.mechanism == 'change_feed' and self.pause_seconds is not None:
            raise ValueError('change feed records no write pause')
        if self.mechanism == 'write_pause_snapshot' and self.pause_seconds is None:
            raise ValueError('write pause snapshot requires measured pause duration')
        return self
