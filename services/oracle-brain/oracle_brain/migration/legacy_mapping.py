"""Pure legacy mapping eligibility proposals with original attribution.

The accepted_original label is legacy mapping eligibility only. It grants no
qualified SourceRef, current permission, company truth, serving or write access.
"""
from __future__ import annotations

import re
from typing import Literal
from uuid import UUID

from pydantic import field_validator, model_validator

from oracle_brain.migration.inventory import LegacyInventory, LegacySourceRecord
from oracle_brain.operating_model.contracts import StrictRecord, digest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


MappingDecision = Literal[
    "accepted_original",
    "excluded_ai_summary",
    "excluded_unconfirmed",
    "legacy_unverified",
    "quarantined",
]

TargetKind = Literal["source", "claim", "excluded", "quarantine"]


class MappingTarget(StrictRecord):
    """Replacement contract identity that preserves original attribution."""
    target_kind: TargetKind
    attribution_legacy_id: str
    redirect_legacy_id: str | None = None

    @field_validator("attribution_legacy_id")
    @classmethod
    def _attribution(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("original attribution is required")
        return value

    @model_validator(mode="after")
    def _redirect_identity(self) -> "MappingTarget":
        if self.redirect_legacy_id is not None and not self.redirect_legacy_id.strip():
            raise ValueError("redirect identity must be nonempty when present")
        return self


class LegacyMappingEntry(StrictRecord):
    legacy_id: str
    decision: MappingDecision
    reason: str
    target: MappingTarget | None = None

    @field_validator("legacy_id", "reason")
    @classmethod
    def _required(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("mapping entry requires identity and reason")
        return value

    @model_validator(mode="after")
    def _decision_target(self) -> "LegacyMappingEntry":
        if self.target is not None and self.target.attribution_legacy_id != self.legacy_id:
            raise ValueError('mapping must keep original attribution')
        if self.decision == "accepted_original":
            if self.target is None:
                raise ValueError("accepted mapping requires a target")
            if self.target.target_kind not in ("source", "claim"):
                raise ValueError("accepted mapping target must be source or claim")
            if self.target.attribution_legacy_id != self.legacy_id:
                raise ValueError("accepted mapping must keep original attribution")
            if self.target.redirect_legacy_id not in (None, self.legacy_id):
                raise ValueError("redirect must preserve the legacy id")
        elif self.target is not None and self.target.target_kind != {
            "excluded_ai_summary": "excluded",
            "excluded_unconfirmed": "excluded",
            "legacy_unverified": "excluded",
            "quarantined": "quarantine",
        }[self.decision]:
            raise ValueError("non-accepted mapping target kind does not match decision")
        return self


class MappingManifest(StrictRecord):
    """Complete mapping of one inventory revision; never a serving artifact."""
    mapping_id: UUID
    inventory_digest: str
    entries: tuple[LegacyMappingEntry, ...]

    @field_validator("inventory_digest")
    @classmethod
    def _digest(cls, value: str) -> str:
        if not _HEX64.fullmatch(value):
            raise ValueError("inventory digest must be lowercase hexadecimal")
        return value

    @model_validator(mode="after")
    def _unique_entries(self) -> "MappingManifest":
        ids = [entry.legacy_id for entry in self.entries]
        if len(ids) != len(set(ids)):
            raise ValueError("mapping entries must be unique per legacy id")
        return self

    def counts(self) -> dict[str, int]:
        tallies = {
            "accepted": 0,
            "quarantined": 0,
            "intentionally_excluded": 0,
            "failed": 0,
        }
        for entry in self.entries:
            if entry.decision == "accepted_original":
                tallies["accepted"] += 1
            elif entry.decision == "quarantined":
                tallies["quarantined"] += 1
            elif entry.decision in ("excluded_ai_summary", "excluded_unconfirmed", "legacy_unverified"):
                tallies["intentionally_excluded"] += 1
            else:  # pragma: no cover - closed Literal
                tallies["failed"] += 1
        return tallies

    def content_digest(self) -> str:
        return digest(
            {
                "mapping_id": str(self.mapping_id),
                "inventory_digest": self.inventory_digest,
                "entries": [entry.model_dump(mode="json") for entry in self.entries],
            }
        )


def map_record(record: LegacySourceRecord) -> LegacyMappingEntry:
    """Propose legacy mapping eligibility; never admit source or truth authority."""
    if record.is_ai_summary:
        return LegacyMappingEntry(
            legacy_id=record.legacy_id,
            decision="excluded_ai_summary",
            reason="ai summary is never a primary source",
            target=MappingTarget(
                target_kind="excluded",
                attribution_legacy_id=record.legacy_id,
            ),
        )
    if not record.has_original:
        return LegacyMappingEntry(
            legacy_id=record.legacy_id,
            decision="legacy_unverified",
            reason="missing original support; excluded from confirmed policy answers",
            target=MappingTarget(
                target_kind="excluded",
                attribution_legacy_id=record.legacy_id,
            ),
        )
    if record.review_state != "confirmed":
        return LegacyMappingEntry(
            legacy_id=record.legacy_id,
            decision="excluded_unconfirmed",
            reason="unconfirmed legacy claim remains unconfirmed",
            target=MappingTarget(
                target_kind="excluded",
                attribution_legacy_id=record.legacy_id,
            ),
        )
    target_kind: TargetKind = "claim" if record.kind == "claim" else "source"
    return LegacyMappingEntry(
        legacy_id=record.legacy_id,
        decision="accepted_original",
        reason="accepted original evidence with preserved attribution",
        target=MappingTarget(
            target_kind=target_kind,
            attribution_legacy_id=record.legacy_id,
            redirect_legacy_id=record.legacy_id,
        ),
    )


def quarantine_record(record: LegacySourceRecord, reason: str) -> LegacyMappingEntry:
    """Explicit quarantine when the mapper cannot map confidently."""
    if not reason.strip():
        raise ValueError("quarantine requires a reason")
    return LegacyMappingEntry(
        legacy_id=record.legacy_id,
        decision="quarantined",
        reason=reason,
        target=MappingTarget(
            target_kind="quarantine",
            attribution_legacy_id=record.legacy_id,
        ),
    )


def build_manifest(
    inventory: LegacyInventory,
    *,
    mapping_id: UUID,
    quarantine: dict[str, str] | None = None,
) -> MappingManifest:
    """Map every inventory row exactly once; overrides may only quarantine."""
    overrides = quarantine or {}
    unknown = set(overrides) - {record.legacy_id for record in inventory.records}
    if unknown:
        raise ValueError("quarantine override is not present in inventory")
    entries = []
    for record in inventory.records:
        if record.legacy_id in overrides:
            entries.append(quarantine_record(record, overrides[record.legacy_id]))
        else:
            entries.append(map_record(record))
    return MappingManifest(
        mapping_id=mapping_id,
        inventory_digest=inventory.content_digest(),
        entries=tuple(entries),
    )
