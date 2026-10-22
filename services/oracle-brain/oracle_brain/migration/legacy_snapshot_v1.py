"""Bounded metadata preparation. No SQL, private bytes or permission producer.

The existing inventory is reused unchanged. Its hashes and eligibility labels
are descriptions, never custody/access proof. No production positive access
path exists while the actual legacy permission producer is unavailable.
"""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from oracle_brain.operating_model.contracts import StrictRecord, canonical_bytes, digest
from .inventory import LegacyInventory, LegacySourceRecord


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
        raise ValueError('aware UTC observation required')
    return value


def _raw(value):
    # Preserve strict Python types AND copied unknown keys; model_dump_json can
    # normalize an invalid copied integer/bool or omit copied extra fields.
    if isinstance(value, BaseModel):
        return {key: _raw(item) for key, item in
            {**value.__dict__, **(value.__pydantic_extra__ or {})}.items()}
    if isinstance(value, tuple):
        return tuple(_raw(item) for item in value)
    if isinstance(value, list):
        return [_raw(item) for item in value]
    if isinstance(value, dict):
        return {key: _raw(item) for key, item in value.items()}
    return value


def _validated(cls, value):
    if type(value) is not cls:
        raise ValueError('exact closed metadata type required')
    return cls.model_validate(_raw(value))


class LegacySnapshotDescriptorV1(StrictRecord):
    """Descriptive finite installation contract; it issues no authority."""
    purpose: Literal['legacy-metadata-snapshot-preparation-v1']
    origin_system: str = Field(min_length=1, max_length=128, pattern=r'^[a-z][a-z0-9_-]*$')
    workspace_id: UUID
    principal_id: UUID
    source_database_identity: UUID
    snapshot_program_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    source_profile_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    permission_producer_kind: Literal['unavailable']
    max_records: int = Field(strict=True, ge=1, le=10000)
    max_metadata_bytes: int = Field(strict=True, ge=1, le=64 * 1024 * 1024)
    valid_from: AwareDatetime
    expires_at: AwareDatetime
    original_horizon: AwareDatetime

    @model_validator(mode='after')
    def _window(self):
        for value in (self.valid_from, self.expires_at, self.original_horizon):
            _utc(value)
        if not self.valid_from < self.expires_at <= self.original_horizon:
            raise ValueError('original finite descriptor window required')
        return self


class LegacyMetadataSnapshotV1(StrictRecord):
    """Exact finite metadata shape, explicitly not an observed SQL snapshot."""
    descriptor: LegacySnapshotDescriptorV1
    inventory: LegacyInventory
    metadata_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    metadata_bytes: int = Field(strict=True, ge=1, le=64 * 1024 * 1024)
    declared_source_count: int = Field(strict=True, ge=0, le=10000)
    quarantine_legacy_ids: tuple[str, ...]
    quarantine_reason: Literal['legacy-permission-producer-unavailable']
    actual_source_snapshot_proven: Literal[False] = False
    current_source_permission_proven: Literal[False] = False
    original_bytes_observed: Literal[False] = False
    target_import_authorized: Literal[False] = False
    consistent_boundary_proven: Literal[False] = False
    company_acceptance: Literal[False] = False

    @model_validator(mode='after')
    def _exact_metadata(self):
        if self.inventory.records != tuple(sorted(self.inventory.records, key=lambda r: r.legacy_id)):
            raise ValueError('canonical deterministic metadata order required')
        if len(self.inventory.records) != self.declared_source_count:
            raise ValueError('declared finite source count differs from complete metadata population')
        if len(self.inventory.records) > self.descriptor.max_records:
            raise ValueError('metadata record bound exceeded; no complete snapshot')
        if tuple(sorted(r.legacy_id for r in self.inventory.records)) != self.quarantine_legacy_ids:
            raise ValueError('every metadata record requires exact quarantine')
        payload = _payload(self.descriptor, self.inventory)
        if len(payload) > self.descriptor.max_metadata_bytes:
            raise ValueError('metadata byte bound exceeded; no complete snapshot')
        if len(payload) != self.metadata_bytes or digest_payload(payload) != self.metadata_sha256:
            raise ValueError('exact immutable metadata seal required')
        return self


def digest_payload(payload: bytes) -> str:
    from hashlib import sha256
    return sha256(payload).hexdigest()


def _payload(descriptor, inventory):
    return canonical_bytes({'descriptor': descriptor.model_dump(mode='json'),
        'inventory': inventory.model_dump(mode='json')})


def _current(descriptor, inventory, now):
    _utc(now)
    if not descriptor.valid_from <= inventory.captured_at <= now < descriptor.expires_at:
        raise PermissionError('original descriptor/metadata observation window unavailable')
    _utc(inventory.captured_at)


def build_metadata_snapshot_v1(descriptor: LegacySnapshotDescriptorV1,
        inventory: LegacyInventory, *, declared_source_count: int, now: datetime) -> LegacyMetadataSnapshotV1:
    # Revalidate copied/constructed Pydantic objects before any interpretation.
    descriptor = _validated(LegacySnapshotDescriptorV1, descriptor)
    inventory = _validated(LegacyInventory, inventory)
    inventory = LegacyInventory.model_validate({**_raw(inventory),
        'records': tuple(_raw(r) for r in sorted(inventory.records, key=lambda r: r.legacy_id))})
    _current(descriptor, inventory, now)
    payload = _payload(descriptor, inventory)
    return LegacyMetadataSnapshotV1(descriptor=descriptor, inventory=inventory,
        declared_source_count=declared_source_count, metadata_sha256=digest_payload(payload),
        metadata_bytes=len(payload), quarantine_legacy_ids=tuple(sorted(r.legacy_id for r in inventory.records)),
        quarantine_reason='legacy-permission-producer-unavailable')


def stable_origin_key_v1(descriptor: LegacySnapshotDescriptorV1, record: LegacySourceRecord) -> str:
    descriptor = _validated(LegacySnapshotDescriptorV1, descriptor)
    record = _validated(LegacySourceRecord, record)
    return digest({'origin_system': descriptor.origin_system, 'workspace_id': str(descriptor.workspace_id),
        'legacy_kind': record.kind, 'legacy_id': record.legacy_id})


def observed_metadata_version_v1(record: LegacySourceRecord) -> str:
    """Observed metadata version digest, NOT fabricated legacy integer or byte proof."""
    record = _validated(LegacySourceRecord, record)
    return digest(record.model_dump(mode='json'))


def recheck_metadata_snapshot_v1(before: LegacyMetadataSnapshotV1,
        current: LegacyMetadataSnapshotV1, *, now: datetime) -> None:
    before = _validated(LegacyMetadataSnapshotV1, before)
    current = _validated(LegacyMetadataSnapshotV1, current)
    _current(before.descriptor, before.inventory, now)
    _current(current.descriptor, current.inventory, now)
    if before.descriptor != current.descriptor:
        raise PermissionError('installed source/identity/window changed')
    # A separately observed current capture may have a different capture UUID
    # and time. Every exact record/permission/review/lineage/membership remains.
    if sorted(before.inventory.records, key=lambda r: r.legacy_id) != sorted(current.inventory.records, key=lambda r: r.legacy_id):
        raise PermissionError('source membership/metadata/permission changed')


def require_original_access_v1(snapshot: LegacyMetadataSnapshotV1) -> None:
    _validated(LegacyMetadataSnapshotV1, snapshot)
    raise PermissionError('actual legacy permission producer unavailable; no original access or intake')
