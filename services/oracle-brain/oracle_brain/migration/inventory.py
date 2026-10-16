"""Read-only legacy source inventory and ordered change deltas; no live store."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from oracle_brain.operating_model.contracts import canonical_bytes, digest

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[1] = 1


def _nonempty(value: str) -> str:
    if not value:
        raise ValueError("identity must be nonempty")
    return value


def _sha256(value: str) -> str:
    if not _HEX64.fullmatch(value):
        raise ValueError("sha256 must be lowercase hexadecimal")
    return value


LegacyPermissionKind = Literal["read", "write", "approve", "admin"]
LegacyReviewState = Literal["unreviewed", "pending", "confirmed", "rejected", "withdrawn"]
LegacyRecordKind = Literal["document", "message", "claim", "translation", "summary"]
LegacyRelation = Literal["cites", "translates", "supersedes", "derived_from", "attached_to"]
LegacyChangeKind = Literal["insert", "update", "delete", "permission", "approval"]


class LegacyPermission(_StrictModel):
    principal_id: str
    kind: LegacyPermissionKind

    @field_validator("principal_id")
    @classmethod
    def _principal(cls, value: str) -> str:
        return _nonempty(value)


class LegacyRelationship(_StrictModel):
    relation: LegacyRelation
    target_legacy_id: str

    @field_validator("target_legacy_id")
    @classmethod
    def _target(cls, value: str) -> str:
        return _nonempty(value)


class TranslationLineage(_StrictModel):
    source_legacy_id: str
    source_language: str
    target_language: str

    @field_validator("source_legacy_id", "source_language", "target_language")
    @classmethod
    def _required(cls, value: str) -> str:
        return _nonempty(value)

    @model_validator(mode="after")
    def _distinct_languages(self) -> "TranslationLineage":
        if self.source_language == self.target_language:
            raise ValueError("translation lineage requires distinct languages")
        return self


class LegacySourceRecord(_StrictModel):
    """One inventoried legacy object; content bytes live outside this DTO."""
    legacy_id: str
    kind: LegacyRecordKind
    content_sha256: str
    permissions: tuple[LegacyPermission, ...]
    review_state: LegacyReviewState
    relationships: tuple[LegacyRelationship, ...]
    translation_lineage: tuple[TranslationLineage, ...]
    is_ai_summary: bool = False
    has_original: bool = False

    @field_validator("legacy_id")
    @classmethod
    def _legacy_id(cls, value: str) -> str:
        return _nonempty(value)

    @field_validator("content_sha256")
    @classmethod
    def _content(cls, value: str) -> str:
        return _sha256(value)

    @model_validator(mode="after")
    def _kind_flags(self) -> "LegacySourceRecord":
        if self.is_ai_summary and self.kind != "summary":
            raise ValueError("ai summary flag requires summary kind")
        if self.kind == "summary" and not self.is_ai_summary:
            raise ValueError("summary kind requires ai summary flag")
        return self


class LegacyInventory(_StrictModel):
    """Consistent initial snapshot of the old source corpus."""
    inventory_id: UUID
    captured_at: datetime
    records: tuple[LegacySourceRecord, ...]

    @field_validator("captured_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("inventory capture time requires a timezone")
        return value

    @model_validator(mode="after")
    def _unique_ids(self) -> "LegacyInventory":
        ids = [record.legacy_id for record in self.records]
        if len(ids) != len(set(ids)):
            raise ValueError("inventory legacy ids must be unique")
        return self

    def record_count(self) -> int:
        return len(self.records)

    def by_id(self, legacy_id: str) -> LegacySourceRecord:
        for record in self.records:
            if record.legacy_id == legacy_id:
                return record
        raise KeyError(legacy_id)

    def content_digest(self) -> str:
        payload = {
            "inventory_id": str(self.inventory_id),
            "records": [record.model_dump(mode="json") for record in self.records],
        }
        return digest(payload)

    def snapshot_checksum(self) -> str:
        return digest(
            {
                "content_digest": self.content_digest(),
                "captured_at": self.captured_at.isoformat(),
                "record_count": self.record_count(),
            }
        )


class LegacyChange(_StrictModel):
    """One ordered change-feed event, including deletions and permission updates."""
    watermark: int = Field(ge=0)
    change_id: str
    kind: LegacyChangeKind
    legacy_id: str
    record: LegacySourceRecord | None = None

    @field_validator("change_id", "legacy_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        return _nonempty(value)

    @model_validator(mode="after")
    def _payload_shape(self) -> "LegacyChange":
        if self.kind == "delete":
            if self.record is not None:
                raise ValueError("delete change carries no record payload")
        elif self.record is None:
            raise ValueError("non-delete change requires a record payload")
        elif self.record.legacy_id != self.legacy_id:
            raise ValueError("change record identity must match legacy_id")
        return self


def inventory_digest(records: tuple[LegacySourceRecord, ...]) -> str:
    return digest([record.model_dump(mode="json") for record in records])


def canonical_inventory_bytes(inventory: LegacyInventory) -> bytes:
    return canonical_bytes(
        {
            "inventory_id": str(inventory.inventory_id),
            "captured_at": inventory.captured_at.isoformat(),
            "records": [record.model_dump(mode="json") for record in inventory.records],
        }
    )
