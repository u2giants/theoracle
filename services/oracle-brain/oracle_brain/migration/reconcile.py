"""Shadow migration reconciliation; counts must sum to inventory, no serving switch."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from oracle_brain.migration.inventory import LegacyInventory, LegacySourceRecord
from oracle_brain.migration.legacy_mapping import MappingManifest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1] = 1


class ShadowMigrationCounts(_StrictModel):
    """Complete accounting of one shadow migration run."""
    accepted: int = Field(ge=0)
    quarantined: int = Field(ge=0)
    intentionally_excluded: int = Field(ge=0)
    failed: int = Field(ge=0)

    def total(self) -> int:
        return self.accepted + self.quarantined + self.intentionally_excluded + self.failed


class ShadowManifest(_StrictModel):
    """Shadow migration manifest bound to one inventory and mapping revision."""
    manifest_id: str
    inventory_digest: str
    mapping_digest: str
    counts: ShadowMigrationCounts
    accepted_legacy_ids: tuple[str, ...] = ()
    quarantined_legacy_ids: tuple[str, ...] = ()
    intentionally_excluded_legacy_ids: tuple[str, ...] = ()
    failed_legacy_ids: tuple[str, ...] = ()

    @field_validator("manifest_id")
    @classmethod
    def _manifest(cls, value: str) -> str:
        if not value:
            raise ValueError("manifest id must be nonempty")
        return value

    @field_validator("inventory_digest", "mapping_digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        if not _HEX64.fullmatch(value):
            raise ValueError("manifest digests must be lowercase hexadecimal")
        return value

    @field_validator(
        "accepted_legacy_ids",
        "quarantined_legacy_ids",
        "intentionally_excluded_legacy_ids",
        "failed_legacy_ids",
    )
    @classmethod
    def _ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            if not item:
                raise ValueError("manifest legacy ids must be nonempty")
        if len(value) != len(set(value)):
            raise ValueError("manifest legacy ids must be unique within a bucket")
        return value

    @model_validator(mode="after")
    def _counts_match_ids(self) -> "ShadowManifest":
        buckets = {
            "accepted": self.accepted_legacy_ids,
            "quarantined": self.quarantined_legacy_ids,
            "intentionally_excluded": self.intentionally_excluded_legacy_ids,
            "failed": self.failed_legacy_ids,
        }
        for name, ids in buckets.items():
            if getattr(self.counts, name) != len(ids):
                raise ValueError(f"counts.{name} does not match id bucket")
        all_ids: list[str] = []
        for ids in buckets.values():
            all_ids.extend(ids)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("manifest legacy ids must be unique across buckets")
        return self


class ReconcileResult(_StrictModel):
    inventory_size: int = Field(ge=0)
    manifest_total: int = Field(ge=0)
    complete: bool


class FidelityCheck(_StrictModel):
    """Permission and source attribution fidelity comparison for one legacy id."""
    legacy_id: str
    before_permission_digest: str
    after_permission_digest: str
    before_attribution: str
    after_attribution: str

    @field_validator("legacy_id", "before_attribution", "after_attribution")
    @classmethod
    def _required(cls, value: str) -> str:
        if not value:
            raise ValueError("fidelity check requires identity and attribution")
        return value

    @field_validator("before_permission_digest", "after_permission_digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        if not _HEX64.fullmatch(value):
            raise ValueError("permission digests must be lowercase hexadecimal")
        return value

    @model_validator(mode="after")
    def _no_degradation(self) -> "FidelityCheck":
        if self.before_permission_digest != self.after_permission_digest:
            raise ValueError("permission fidelity degraded")
        if self.before_attribution != self.after_attribution:
            raise ValueError("source attribution fidelity degraded")
        return self


def permission_digest(record: LegacySourceRecord) -> str:
    from oracle_brain.operating_model.contracts import digest

    payload = sorted(
        (permission.principal_id, permission.kind)
        for permission in record.permissions
    )
    return digest({"permissions": payload})


def reconcile_counts(inventory_size: int, counts: ShadowMigrationCounts) -> ReconcileResult:
    if inventory_size < 0:
        raise ValueError("inventory size must be nonnegative")
    total = counts.total()
    return ReconcileResult(
        inventory_size=inventory_size,
        manifest_total=total,
        complete=total == inventory_size,
    )


def reconcile_manifest(
    inventory: LegacyInventory,
    mapping: MappingManifest,
    manifest: ShadowManifest,
) -> ReconcileResult:
    """Counts must sum to inventory and match the mapping; never accept partial."""
    if manifest.inventory_digest != inventory.content_digest():
        raise ValueError("shadow manifest is not bound to this inventory")
    if manifest.mapping_digest != mapping.content_digest():
        raise ValueError("shadow manifest is not bound to this mapping")
    mapped = mapping.counts()
    if (
        manifest.counts.accepted != mapped["accepted"]
        or manifest.counts.quarantined != mapped["quarantined"]
        or manifest.counts.intentionally_excluded != mapped["intentionally_excluded"]
        or manifest.counts.failed != mapped["failed"]
    ):
        raise ValueError("shadow counts do not match mapping decisions")
    result = reconcile_counts(inventory.record_count(), manifest.counts)
    if not result.complete:
        raise ValueError("shadow migration counts do not sum to inventory")
    return result


def check_fidelity(
    *,
    legacy_id: str,
    before: LegacySourceRecord,
    after_attribution: str,
    after_permission_digest: str,
) -> FidelityCheck:
    return FidelityCheck(
        legacy_id=legacy_id,
        before_permission_digest=permission_digest(before),
        after_permission_digest=after_permission_digest,
        before_attribution=legacy_id,
        after_attribution=after_attribution,
    )
