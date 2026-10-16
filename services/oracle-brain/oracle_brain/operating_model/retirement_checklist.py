"""Pure S16 retirement checklist DTOs and fail-closed gates. No I/O, no deletion."""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .contracts import StrictRecord, digest

DEFAULT_RETENTION_WINDOW_DAYS = 30


def _check_path(path: str) -> None:
    if path.startswith('/') or '..' in path.split('/') or '\\' in path:
        raise ValueError('retirement path must be repository relative')


class LegacyRouteEntry(StrictRecord):
    """One legacy route with the runtime consumers that must already be gone."""
    path: str = Field(min_length=1)
    replaced: bool
    active_callers: tuple[str, ...] = ()
    active_schedules: tuple[str, ...] = ()
    active_queues: tuple[str, ...] = ()

    @model_validator(mode='after')
    def _relative(self):
        _check_path(self.path)
        return self


class NoActiveConsumerCensus(StrictRecord):
    """Audited call/schedule/queue census against one accepted release."""
    release_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    routes: tuple[LegacyRouteEntry, ...] = Field(min_length=1)


class NoActiveConsumerProof(StrictRecord):
    release_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    paths: tuple[str, ...] = Field(min_length=1)
    census_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    deletion_authorized: Literal[False] = False
    reviewed_retirement_pr_required: Literal[True] = True


class CitationRedirect(StrictRecord):
    """Permanently resolvable old citation identity."""
    legacy_id: str = Field(min_length=1)
    current_id: str = Field(min_length=1)

    @model_validator(mode='after')
    def _changes_identity(self):
        if self.legacy_id == self.current_id:
            raise ValueError('citation redirect must change identity')
        return self


class CitationRestoreContract(StrictRecord):
    """Legacy citations that must resolve after a backup restore."""
    release_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    legacy_ids: tuple[str, ...] = Field(min_length=1)
    redirects: tuple[CitationRedirect, ...] = Field(min_length=1)


class CitationRestoreProof(StrictRecord):
    release_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    resolved_legacy_ids: tuple[str, ...] = Field(min_length=1)
    redirect_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    deletion_authorized: Literal[False] = False
    reviewed_retirement_pr_required: Literal[True] = True


class WriterOwnership(StrictRecord):
    """Current writer ownership generation for one workspace."""
    workspace_id: UUID
    active_generation: int = Field(strict=True, ge=1)
    revoked_generations: tuple[int, ...] = ()

    @model_validator(mode='after')
    def _coherent(self):
        if len(set(self.revoked_generations)) != len(self.revoked_generations):
            raise ValueError('duplicate revoked generations')
        if self.active_generation in self.revoked_generations:
            raise ValueError('active generation cannot be revoked')
        return self


class RetentionPlan(StrictRecord):
    """Approved retention window that must pass before irreversible deletion."""
    retention_window_days: int = Field(strict=True, ge=DEFAULT_RETENTION_WINDOW_DAYS)
    restorable_state_exported: bool
    stable_adoption_reached: bool


class RollbackConditions(StrictRecord):
    """Rollback prerequisites; legacy writer fencing is mandatory."""
    final_watermark: int = Field(strict=True, ge=0)
    legacy_writer_fencing_proved: bool
    rollback_rehearsal_hash: str = Field(pattern=r'^[0-9a-f]{64}$')


class GovernedRetirement(StrictRecord):
    """What a retirement checklist may never grant on its own."""
    reviewed_retirement_pr_required: Literal[True] = True
    deletion_authorized: Literal[False] = False
    live_deployed_smoke_required: Literal[True] = True


class RetirementChecklist(StrictRecord):
    """S16 #40 offline gate shape: retention, rollback, consumers, citations, governance."""
    release_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    retention: RetentionPlan
    rollback: RollbackConditions
    no_active_consumers: NoActiveConsumerProof
    citation_restore: CitationRestoreProof
    governed: GovernedRetirement


def validate_no_active_consumers(census: NoActiveConsumerCensus, *, proposed_paths: tuple[str, ...],
                                 admitted_release_hashes: frozenset[str]) -> NoActiveConsumerProof:
    """Fail closed unless every proposed-retired path is replaced and has no live consumer."""
    if census.release_hash not in admitted_release_hashes:
        raise PermissionError('retirement census is not bound to an admitted release')
    if not proposed_paths or len(set(proposed_paths)) != len(proposed_paths):
        raise ValueError('nonempty unique retirement paths required')
    for path in proposed_paths:
        _check_path(path)
    entries = {entry.path: entry for entry in census.routes}
    if len(entries) != len(census.routes):
        raise ValueError('duplicate legacy route census entries')
    for path in proposed_paths:
        entry = entries.get(path)
        if entry is None:
            raise PermissionError('retirement target is absent from the active-consumer census')
        if entry.replaced is not True:
            raise PermissionError('retirement target is not replaced')
        if entry.active_callers or entry.active_schedules or entry.active_queues:
            raise PermissionError('active caller, schedule or queue still depends on retirement target')
    return NoActiveConsumerProof(release_hash=census.release_hash, paths=tuple(proposed_paths),
                                 census_hash=digest(census.model_dump(mode='json')))


def validate_citation_restore(contract: CitationRestoreContract, *, restored_current_ids: frozenset[str],
                              admitted_release_hashes: frozenset[str]) -> CitationRestoreProof:
    """Fail closed unless every registered legacy citation resolves in the restore."""
    if contract.release_hash not in admitted_release_hashes:
        raise PermissionError('citation restore contract is not bound to an admitted release')
    if not restored_current_ids:
        raise ValueError('restored citation population is required')
    if len(set(contract.legacy_ids)) != len(contract.legacy_ids):
        raise ValueError('duplicate legacy citation ids')
    mapping: dict[str, str] = {}
    for redirect in contract.redirects:
        if redirect.legacy_id in mapping:
            raise ValueError('duplicate legacy citation redirect')
        mapping[redirect.legacy_id] = redirect.current_id
    for legacy_id in contract.legacy_ids:
        if legacy_id not in mapping:
            raise PermissionError('legacy citation has no redirect')
        if mapping[legacy_id] not in restored_current_ids:
            raise PermissionError('legacy citation redirect target is missing from the restore')
    return CitationRestoreProof(release_hash=contract.release_hash,
                                resolved_legacy_ids=tuple(contract.legacy_ids),
                                redirect_hash=digest(contract.model_dump(mode='json')))


def authorize_write(ownership: WriterOwnership, *, presented_generation: int,
                    operation: str) -> dict:
    """Deny a write from a revoked or non-current ownership generation."""
    if not operation or not operation.strip():
        raise ValueError('write operation name is required')
    if presented_generation in ownership.revoked_generations or presented_generation != ownership.active_generation:
        raise PermissionError('revoked writer generation cannot write')
    return {'workspace_id': str(ownership.workspace_id), 'generation': presented_generation,
            'operation': operation, 'write_authorized': True}


def validate_retirement_checklist(checklist: RetirementChecklist) -> dict:
    """Structural coherence of a retirement checklist; never authorizes deletion."""
    release = checklist.release_hash
    if checklist.no_active_consumers.release_hash != release:
        raise ValueError('consumer proof binds a different release')
    if checklist.citation_restore.release_hash != release:
        raise ValueError('citation proof binds a different release')
    if not checklist.retention.restorable_state_exported:
        raise PermissionError('retention plan has no restorable state export')
    if not checklist.retention.stable_adoption_reached:
        raise PermissionError('retention window has not started from stable primary adoption')
    if not checklist.rollback.legacy_writer_fencing_proved:
        raise PermissionError('rollback conditions lack legacy writer fencing')
    return {'release_hash': release, 'checklist_hash': digest(checklist.model_dump(mode='json')),
            'retention_window_days': checklist.retention.retention_window_days,
            'final_watermark': checklist.rollback.final_watermark,
            'deletion_authorized': False, 'reviewed_retirement_pr_required': True,
            'live_deployed_smoke_required': True, 'live_proof_still_required': True}
