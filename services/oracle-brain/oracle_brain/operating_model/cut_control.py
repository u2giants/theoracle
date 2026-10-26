"""Stage 1–8 durable writer-cut control state machine.

Extends the SAME durable release-selector CAS concept with exact release/workspace/
controller admission/old+new ingestion generation/complete writer-census digest.

Phases: legacy-active -> pausing -> drained -> snapshot-reconciled -> replacement-active,
plus ABORTED / UNKNOWN / rolling-back.

Every transition is CAS on exact prior generation. Enforcement is local at each
actual write owner; this control coordinates, it does not replace local barriers.
No POP shared-db writes. No advisory-only / GUC / self-stamp grant.
"""
from __future__ import annotations

import time
from enum import Enum
from typing import Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from .contracts import canonical_bytes, digest


class CutPhase(str, Enum):
    LEGACY_ACTIVE = 'legacy-active'
    PAUSING = 'pausing'
    DRAINED = 'drained'
    SNAPSHOT_RECONCILED = 'snapshot-reconciled'
    REPLACEMENT_ACTIVE = 'replacement-active'
    ABORTED = 'aborted'
    UNKNOWN = 'unknown'
    ROLLING_BACK = 'rolling-back'


_ALLOWED_TRANSITIONS: dict[CutPhase, frozenset[CutPhase]] = {
    CutPhase.LEGACY_ACTIVE: frozenset({CutPhase.PAUSING, CutPhase.ABORTED}),
    CutPhase.PAUSING: frozenset({CutPhase.DRAINED, CutPhase.ABORTED, CutPhase.ROLLING_BACK}),
    CutPhase.DRAINED: frozenset({CutPhase.SNAPSHOT_RECONCILED, CutPhase.ABORTED, CutPhase.ROLLING_BACK}),
    CutPhase.SNAPSHOT_RECONCILED: frozenset({CutPhase.REPLACEMENT_ACTIVE, CutPhase.ABORTED, CutPhase.ROLLING_BACK}),
    CutPhase.REPLACEMENT_ACTIVE: frozenset({CutPhase.ROLLING_BACK, CutPhase.ABORTED}),
    CutPhase.ROLLING_BACK: frozenset({CutPhase.LEGACY_ACTIVE, CutPhase.ABORTED}),
    CutPhase.ABORTED: frozenset(),
    CutPhase.UNKNOWN: frozenset(),
}


class WriterCensusDigest(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    value: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmed_count: int = Field(ge=0)


class CutControlState(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    workspace_id: UUID
    release_id: UUID
    phase: CutPhase
    old_generation: int = Field(ge=0)
    new_generation: int = Field(ge=1)
    census: WriterCensusDigest
    controller_id: str
    controller_generation: int = Field(ge=0)
    transition_count: int = Field(ge=0)
    pause_started_monotonic: float | None = None
    pause_started_wall: float | None = None
    drained_ack: bool = False
    snapshot_digest: str | None = None
    comparison_digest: str | None = None
    consistent_boundary_proven: bool = False
    external_participants_controlled: bool = False
    stop_or_privacy_or_security_invalidated: bool = False
    rolling_back_note: str = ''


class CutControlError(RuntimeError):
    pass


class CasConflict(CutControlError):
    pass


class TransitionRefused(CutControlError):
    pass


class CutControl:
    """In-memory CAS control owner. A real deployment binds the same contract to
    a durable row with SELECT ... FOR UPDATE. Offline tests exercise this owner."""

    def __init__(self, initial: CutControlState):
        self._state = initial

    @property
    def state(self) -> CutControlState:
        return self._state

    def _cas(self, expect: CutControlState, update: dict) -> CutControlState:
        if self._state.transition_count != expect.transition_count:
            raise CasConflict('cut control moved concurrently')
        if self._state != expect:
            raise CasConflict('cut control state changed concurrently')
        next_state = expect.model_copy(update={
            **update,
            'transition_count': expect.transition_count + 1,
        })
        self._state = next_state
        return next_state

    def _require_controller(self, controller_id: str, controller_generation: int) -> None:
        if controller_id != self._state.controller_id:
            raise TransitionRefused('controller identity is not the admitted controller')
        if controller_generation != self._state.controller_generation:
            raise TransitionRefused('controller generation is stale; re-admit before transition')

    def begin_pause(self, controller_id: str, controller_generation: int) -> CutControlState:
        self._require_controller(controller_id, controller_generation)
        expect = self._state
        if expect.phase is not CutPhase.LEGACY_ACTIVE:
            raise TransitionRefused(f'cannot pause from {expect.phase.value}')
        if expect.stop_or_privacy_or_security_invalidated:
            raise TransitionRefused('STOP/privacy/security already invalidates the candidate cut')
        now_mono = time.monotonic()
        now_wall = time.time()
        return self._cas(expect, {
            'phase': CutPhase.PAUSING,
            'pause_started_monotonic': now_mono,
            'pause_started_wall': now_wall,
        })

    def record_opaque_arrival(self, arrival_id: str, body_hash: str) -> dict:
        """Stage 4: finite opaque arrival during pausing. Queueing is not source
        qualification, viewer permission, or an automatic right to replay."""
        if self._state.phase is not CutPhase.PAUSING:
            raise TransitionRefused('opaque arrivals are only accepted during pausing')
        return {
            'arrival_id': arrival_id,
            'body_hash': body_hash,
            'status': 'accepted-opaque',
            'replay_authorized': False,
        }

    def mark_drained(self, controller_id: str, controller_generation: int,
                     unknown_open: int = 0) -> CutControlState:
        """Stage 5: UNKNOWN never equals drained."""
        self._require_controller(controller_id, controller_generation)
        expect = self._state
        if expect.phase is not CutPhase.PAUSING:
            raise TransitionRefused(f'cannot mark drained from {expect.phase.value}')
        if unknown_open > 0:
            raise TransitionRefused('UNKNOWN blocks a positive drained claim')
        return self._cas(expect, {'phase': CutPhase.DRAINED, 'drained_ack': True})

    def record_snapshot(self, controller_id: str, controller_generation: int,
                        snapshot_digest: str, comparison_digest: str,
                        overflow: bool = False) -> CutControlState:
        self._require_controller(controller_id, controller_generation)
        expect = self._state
        if expect.phase is not CutPhase.DRAINED:
            raise TransitionRefused(f'cannot snapshot-reconcile from {expect.phase.value}')
        if overflow:
            raise TransitionRefused('snapshot overflow denies completion')
        if snapshot_digest != comparison_digest:
            raise TransitionRefused('snapshot and comparison digests differ; reconciliation incomplete')
        return self._cas(expect, {
            'phase': CutPhase.SNAPSHOT_RECONCILED,
            'snapshot_digest': snapshot_digest,
            'comparison_digest': comparison_digest,
        })

    def require_complete_participants(self, missing_families: list[str],
                                      external_controlled: bool) -> None:
        if missing_families:
            raise TransitionRefused(
                'missing participant families: ' + ','.join(missing_families))
        if not external_controlled:
            raise TransitionRefused('uncontrolled external writer means incomplete cut')

    def activate_replacement(self, controller_id: str, controller_generation: int,
                             missing_families: list[str] | None = None,
                             external_controlled: bool | None = None) -> CutControlState:
        self._require_controller(controller_id, controller_generation)
        expect = self._state
        if expect.phase is not CutPhase.SNAPSHOT_RECONCILED:
            raise TransitionRefused(f'cannot activate replacement from {expect.phase.value}')
        self.require_complete_participants(
            missing_families or [], expect.external_participants_controlled if external_controlled is None else external_controlled)
        return self._cas(expect, {
            'phase': CutPhase.REPLACEMENT_ACTIVE,
            'consistent_boundary_proven': True,
        })

    def invalidate_candidate(self, reason: str) -> CutControlState:
        """STOP / privacy-withdrawal / security denial must remain operational and
        invalidate the candidate cut. Immutable fact is retained."""
        expect = self._state
        return self._cas(expect, {
            'phase': CutPhase.UNKNOWN,
            'stop_or_privacy_or_security_invalidated': True,
            'consistent_boundary_proven': False,
            'rolling_back_note': reason,
        })

    def begin_rollback(self, controller_id: str, controller_generation: int,
                       note: str = '') -> CutControlState:
        self._require_controller(controller_id, controller_generation)
        expect = self._state
        if expect.phase in (CutPhase.ABORTED, CutPhase.UNKNOWN):
            raise TransitionRefused(f'cannot rollback from {expect.phase.value}')
        return self._cas(expect, {
            'phase': CutPhase.ROLLING_BACK,
            'rolling_back_note': note,
            'consistent_boundary_proven': False,
        })

    def complete_rollback(self, controller_id: str, controller_generation: int) -> CutControlState:
        self._require_controller(controller_id, controller_generation)
        expect = self._state
        if expect.phase is not CutPhase.ROLLING_BACK:
            raise TransitionRefused(f'cannot complete rollback from {expect.phase.value}')
        return self._cas(expect, {'phase': CutPhase.LEGACY_ACTIVE})

    def abort(self, controller_id: str, controller_generation: int) -> CutControlState:
        self._require_controller(controller_id, controller_generation)
        expect = self._state
        return self._cas(expect, {'phase': CutPhase.ABORTED})


def new_control(workspace_id: UUID, release_id: UUID, census: WriterCensusDigest,
                controller_id: str, old_generation: int = 0,
                new_generation: int = 1, external_controlled: bool = False) -> CutControl:
    state = CutControlState(
        workspace_id=workspace_id,
        release_id=release_id,
        phase=CutPhase.LEGACY_ACTIVE,
        old_generation=old_generation,
        new_generation=new_generation,
        census=census,
        controller_id=controller_id,
        controller_generation=0,
        transition_count=0,
        external_participants_controlled=external_controlled,
    )
    return CutControl(state)
