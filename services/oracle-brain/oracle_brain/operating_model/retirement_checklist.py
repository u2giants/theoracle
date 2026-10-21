"""Descriptive citation/restore/retention extension to the canonical W12 gate.

No reads, deletion, serving or writer authority. Independent callers must admit
the exact evidence packets and supply their trusted current observation time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from .contracts import StrictRecord, digest
from .release_manifest import ReleaseManifest
from .retirement import verify_retirement
from .source_receipts import SourceRef

Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class CitationBinding(StrictRecord):
    legacy_citation_id: str
    target_id: str
    source_ref: SourceRef
    permission_digest: Hash
    tombstoned: bool

    @field_validator('legacy_citation_id', 'target_id')
    @classmethod
    def _identity(cls, value):
        if not value.strip():
            raise ValueError('citation and target identities must be nonblank')
        return value


class CitationInventoryPacket(StrictRecord):
    release_hash: Hash
    source_inventory_hash: Hash
    permission_digest: Hash
    citations: tuple[CitationBinding, ...] = Field(min_length=1)

    @model_validator(mode='after')
    def _unique_citations(self):
        keys = [item.legacy_citation_id for item in self.citations]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate legacy citation identity')
        targets = {}
        for item in self.citations:
            identity = (item.source_ref, item.permission_digest, item.tombstoned)
            if item.target_id in targets and targets[item.target_id] != identity:
                raise ValueError('citation target conflates distinct original identities or permissions')
            targets[item.target_id] = identity
        return self


class RestoredCitation(CitationBinding):
    resolution_state: Literal['available', 'withdrawn']

    @model_validator(mode='after')
    def _withdrawal_state(self):
        expected = 'withdrawn' if self.tombstoned else 'available'
        if self.resolution_state != expected:
            raise ValueError('citation resolution contradicts tombstone state')
        return self


class FreshRestorePacket(StrictRecord):
    release_hash: Hash
    source_inventory_hash: Hash
    permission_digest: Hash
    citation_inventory_hash: Hash
    fresh_instance_id: str
    backup_hash: Hash
    completed_at: AwareDatetime
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    citations: tuple[RestoredCitation, ...] = Field(min_length=1)
    available_target_ids: tuple[str, ...]

    @field_validator('fresh_instance_id')
    @classmethod
    def _instance(cls, value):
        if not value.strip():
            raise ValueError('fresh restore instance identity is required')
        return value

    @field_validator('available_target_ids')
    @classmethod
    def _target_ids(cls, value):
        if any(not key.strip() for key in value) or len(value) != len(set(value)):
            raise ValueError('available target ids must be unique and nonblank')
        return value

    @model_validator(mode='after')
    def _coherent(self):
        keys = [item.legacy_citation_id for item in self.citations]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate restored citation identity')
        if not self.completed_at <= self.observed_at < self.expires_at:
            raise ValueError('restore timestamps are incoherent')
        return self


class RetentionClearancePacket(StrictRecord):
    """Exact independently admitted duration and observed interval, never booleans."""
    release_hash: Hash
    census_hash: Hash
    equivalence_hash: Hash
    citation_inventory_hash: Hash
    restore_packet_hash: Hash
    rollback_rehearsal_hash: Hash
    required_window_seconds: int = Field(strict=True, gt=0)
    stable_primary_at: AwareDatetime
    observed_at: AwareDatetime

    @model_validator(mode='after')
    def _observed_window(self):
        if self.observed_at < self.stable_primary_at:
            raise ValueError('retention observation precedes stable primary adoption')
        if (self.observed_at - self.stable_primary_at).total_seconds() < self.required_window_seconds:
            raise ValueError('required retention window has not elapsed')
        return self


def _revalidate(packet, expected_type):
    # Unvalidated model_copy/update objects confer no bypass of the DTO checks.
    if type(packet) is not expected_type:
        raise ValueError('exact checklist packet type required')
    return expected_type.model_validate_json(packet.model_dump_json())


def verify_retirement_checklist(manifest: ReleaseManifest, census: dict, *,
    proposed_paths: tuple[str, ...], preserved_capabilities: dict,
    accepted_release_hashes: frozenset[str], admitted_census_hashes: frozenset[str],
    admitted_equivalence_hashes: frozenset[str],
    citation_inventory: CitationInventoryPacket, restore_packet: FreshRestorePacket,
    retention_packet: RetentionClearancePacket,
    admitted_citation_inventory_hashes: frozenset[str], admitted_restore_hashes: frozenset[str],
    admitted_retention_hashes: frozenset[str], observed_at: datetime) -> dict:
    """Extend, never replace, canonical admission; never authorize an operation."""
    canonical = verify_retirement(manifest, census, proposed_paths=proposed_paths,
        preserved_capabilities=preserved_capabilities,
        accepted_release_hashes=accepted_release_hashes,
        admitted_census_hashes=admitted_census_hashes,
        admitted_equivalence_hashes=admitted_equivalence_hashes)
    if type(observed_at) is not datetime or observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError('trusted current observation must be an aware datetime')
    citation_inventory = _revalidate(citation_inventory, CitationInventoryPacket)
    restore_packet = _revalidate(restore_packet, FreshRestorePacket)
    retention_packet = _revalidate(retention_packet, RetentionClearancePacket)
    citation_hash = digest(citation_inventory.model_dump(mode='json'))
    restore_hash = digest(restore_packet.model_dump(mode='json'))
    retention_hash = digest(retention_packet.model_dump(mode='json'))
    if citation_hash not in admitted_citation_inventory_hashes:
        raise PermissionError('exact citation inventory is not independently admitted')
    if restore_hash not in admitted_restore_hashes:
        raise PermissionError('exact fresh restore packet is not independently admitted')
    if retention_hash not in admitted_retention_hashes:
        raise PermissionError('exact retention packet is not independently admitted')
    release_hash = manifest.content_hash()
    if any(packet.release_hash != release_hash for packet in (citation_inventory, restore_packet, retention_packet)):
        raise PermissionError('checklist evidence binds a different accepted release')
    for packet in (citation_inventory, restore_packet):
        if packet.source_inventory_hash != manifest.source_inventory_hash or packet.permission_digest != manifest.permission_digest:
            raise PermissionError('checklist source inventory or permission snapshot differs from release')
    if (restore_packet.citation_inventory_hash != citation_hash or
            retention_packet.citation_inventory_hash != citation_hash or
            retention_packet.restore_packet_hash != restore_hash or
            retention_packet.census_hash != canonical['census_hash'] or
            retention_packet.equivalence_hash != canonical['equivalents_hash']):
        raise PermissionError('checklist evidence does not bind the exact canonical inputs')
    if restore_packet.observed_at != observed_at or not restore_packet.completed_at <= observed_at < restore_packet.expires_at:
        raise PermissionError('fresh restore evidence is stale or outside its admitted observation')
    if retention_packet.observed_at != observed_at:
        raise PermissionError('retention clearance is not the current admitted observation')
    expected = {item.legacy_citation_id: item for item in citation_inventory.citations}
    restored = {item.legacy_citation_id: item for item in restore_packet.citations}
    if set(expected) != set(restored):
        raise PermissionError('restored citation population is missing or contains unknown identities')
    expected_available_targets = set()
    for key, binding in expected.items():
        if binding.source_ref not in manifest.source_refs:
            raise PermissionError('citation original source revision is not in accepted release')
        observation = restored[key]
        # Compare every original, target, source revision, permission and tombstone.
        if observation.model_dump(exclude={'resolution_state'}) != binding.model_dump():
            raise PermissionError('restored original target revision permission or tombstone mismatch')
        if not binding.tombstoned:
            expected_available_targets.add(binding.target_id)
    if set(restore_packet.available_target_ids) != expected_available_targets:
        raise PermissionError('restored citation target population is dangling or contains unknown targets')
    return {**canonical, 'citation_inventory_hash': citation_hash, 'fresh_restore_hash': restore_hash,
            'retention_clearance_hash': retention_hash,
            'observed_retention_seconds': (retention_packet.observed_at - retention_packet.stable_primary_at).total_seconds(),
            'deletion_authorized': False, 'reviewed_retirement_pr_required': True,
            'live_deployed_smoke_required': True, 'live_proof_still_required': True}
