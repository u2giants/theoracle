"""Stage 2–3 local writer barrier + ingestion-generation admission.

Every confirmed SQL writer must check barrier+generation in the SAME transaction
as the mutation. A stale generation cannot publish. Independent role/generation
admission: the writer's DB role and generation must both be admitted.

Storage/external writers require a fixed effect owner that participates in the
same logical cut. No advisory-only lock, GUC, or self-stamp grant is sufficient.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BarrierPhase(str, Enum):
    OPEN = 'open'
    PAUSING = 'pausing'
    CLOSED = 'closed'
    UNKNOWN = 'unknown'


class AdmittedRole(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    role: str
    generation: int = Field(ge=0)
    family_id: str


class BarrierRow(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    workspace_id: UUID
    phase: BarrierPhase
    current_generation: int = Field(ge=0)
    admitted_roles: tuple[AdmittedRole, ...] = ()


class BarrierViolation(RuntimeError):
    pass


class StaleGeneration(BarrierViolation):
    pass


class RoleNotAdmitted(BarrierViolation):
    pass


class BarrierClosed(BarrierViolation):
    pass


@dataclass
class LocalBarrier:
    """One local barrier row per workspace. Real deployment binds to a SQL row
    locked FOR UPDATE inside the writer's own transaction."""

    row: BarrierRow
    _lock: Callable[[], None] = field(default=lambda: None)
    _unlock: Callable[[], None] = field(default=lambda: None)

    def transition(self, phase: BarrierPhase, generation: int | None = None) -> BarrierRow:
        self._lock()
        try:
            next_gen = self.row.current_generation if generation is None else generation
            self.row = self.row.model_copy(update={
                'phase': phase,
                'current_generation': next_gen,
            })
            return self.row
        finally:
            self._unlock()

    def admit_role(self, role: str, generation: int, family_id: str) -> BarrierRow:
        self._lock()
        try:
            existing = [r for r in self.row.admitted_roles
                        if not (r.role == role and r.family_id == family_id)]
            admitted = AdmittedRole(role=role, generation=generation, family_id=family_id)
            self.row = self.row.model_copy(update={
                'admitted_roles': tuple(existing) + (admitted,),
            })
            return self.row
        finally:
            self._unlock()

    def assert_admitted(self, role: str, generation: int, family_id: str) -> None:
        """Stage 2 guard: run INSIDE the same transaction as the mutation.

        Order of refusal (all fail-closed):
        1. barrier closed / unknown -> refuse
        2. stale generation -> refuse
        3. role not admitted for that generation -> refuse
        """
        row = self.row
        if row.phase in (BarrierPhase.CLOSED, BarrierPhase.UNKNOWN):
            raise BarrierClosed(f'barrier phase {row.phase.value} refuses new writes')
        if row.phase is BarrierPhase.PAUSING:
            raise BarrierClosed('barrier is pausing; new effect claims are rejected')
        if generation != row.current_generation:
            raise StaleGeneration(
                f'stale generation {generation} != admitted {row.current_generation}')
        match = next((r for r in row.admitted_roles
                      if r.role == role and r.generation == generation
                      and r.family_id == family_id), None)
        if match is None:
            raise RoleNotAdmitted(
                f'role {role} is not admitted for family {family_id} at generation {generation}')


class EffectStatus(str, Enum):
    IN_FLIGHT = 'in-flight'
    ACCEPTED = 'accepted'
    UNKNOWN = 'unknown'
    ORPHAN = 'orphan'
    DROPPED = 'dropped'


class EffectReceipt(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    effect_id: str
    family_id: str
    status: EffectStatus
    body_hash: str = ''
    receipt_hash: str = ''


class FixedEffectOwner:
    """Stage 3 storage/external effect owner. Records an outbound intent before
    the call and a receipt after. Lost ACK stays UNKNOWN; no resend."""

    def __init__(self, barrier: LocalBarrier):
        self._barrier = barrier
        self._effects: dict[str, EffectReceipt] = {}

    def begin_effect(self, effect_id: str, family_id: str, role: str,
                     generation: int, body_hash: str = '') -> EffectReceipt:
        self._barrier.assert_admitted(role, generation, family_id)
        receipt = EffectReceipt(
            effect_id=effect_id,
            family_id=family_id,
            status=EffectStatus.IN_FLIGHT,
            body_hash=body_hash,
        )
        self._effects[effect_id] = receipt
        return receipt

    def complete_effect(self, effect_id: str, success: bool) -> EffectReceipt:
        prior = self._effects.get(effect_id)
        if prior is None:
            raise BarrierViolation(f'unknown effect {effect_id}')
        if prior.status is not EffectStatus.IN_FLIGHT:
            return prior
        status = EffectStatus.ACCEPTED if success else EffectStatus.ORPHAN
        receipt = prior.model_copy(update={'status': status})
        self._effects[effect_id] = receipt
        return receipt

    def lost_ack(self, effect_id: str) -> EffectReceipt:
        prior = self._effects.get(effect_id)
        if prior is None:
            raise BarrierViolation(f'unknown effect {effect_id}')
        receipt = prior.model_copy(update={'status': EffectStatus.UNKNOWN})
        self._effects[effect_id] = receipt
        return receipt

    def orphan_removal(self, effect_id: str) -> EffectReceipt:
        prior = self._effects.get(effect_id)
        if prior is None:
            raise BarrierViolation(f'unknown effect {effect_id}')
        receipt = prior.model_copy(update={'status': EffectStatus.DROPPED})
        self._effects[effect_id] = receipt
        return receipt

    def open_effects(self) -> list[EffectReceipt]:
        return [e for e in self._effects.values()
                if e.status in (EffectStatus.IN_FLIGHT, EffectStatus.UNKNOWN)]


# Named writer families requiring actual consistent-cut participation.
WRITER_FAMILIES: tuple[str, ...] = (
    'F1_chat_messages_modelusage_contextpacks_typing',
    'F2_storage_bytes_sql_metadata_orphans',
    'F3_imports_teams_discovery_transcripts',
    'F4_extraction_paid_batches_late_drain',
    'F5_admin_approvals_corrections_taxonomy_gaps_identity_membership_auth',
    'F6_synthesis_translation_contradiction_lull_outbound_cached_clients',
    'F8_python_oracle_brain_legacy',
)


def build_default_barrier(workspace_id: UUID, generation: int = 1) -> LocalBarrier:
    row = BarrierRow(
        workspace_id=workspace_id,
        phase=BarrierPhase.OPEN,
        current_generation=generation,
        admitted_roles=tuple(
            AdmittedRole(role='writer', generation=generation, family_id=family)
            for family in WRITER_FAMILIES
        ),
    )
    return LocalBarrier(row=row)
