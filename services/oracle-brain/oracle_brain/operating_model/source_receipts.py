"""Immutable source and evidence receipts for the operating model."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SourceRef(_StrictModel):
    schema_version: Literal[1] = 1
    workspace_id: UUID
    source_id: UUID
    revision: Annotated[int, Field(ge=1)]
    original_sha256: str
    reading_sha256: str
    parser_id: str

    @field_validator("original_sha256", "reading_sha256")
    @classmethod
    def _sha256(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("sha256 must be lowercase hexadecimal")
        return value

    @field_validator("parser_id")
    @classmethod
    def _parser_id(cls, value: str) -> str:
        if not value:
            raise ValueError("parser_id must be nonempty")
        return value


class SourceReceipt(_StrictModel):
    schema_version: Literal[1] = 1
    ref: SourceRef
    reading: str
    display_revision: str
    aliases: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_receipt(self) -> "SourceReceipt":
        if self.display_revision != f"r{self.ref.revision}":
            raise ValueError("display_revision must match ref.revision")
        digest = hashlib.sha256(self.reading.encode("utf-8")).hexdigest()
        if digest != self.ref.reading_sha256:
            raise ValueError("reading_sha256 does not match reading")
        return self


class EvidenceRef(_StrictModel):
    schema_version: Literal[1] = 1
    ref: SourceRef
    start: Annotated[int, Field(ge=0)]
    end: Annotated[int, Field(gt=0)]
    quote: str

    @model_validator(mode="after")
    def _valid_span(self) -> "EvidenceRef":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


def validate_evidence(receipt: SourceReceipt, evidence: EvidenceRef) -> EvidenceRef:
    if evidence.ref != receipt.ref:
        raise ValueError("evidence references a different source revision")
    if evidence.end > len(receipt.reading):
        raise ValueError("evidence span is outside the reading")
    if receipt.reading[evidence.start : evidence.end] != evidence.quote:
        raise ValueError("evidence quote does not match the reading")
    return evidence


def resolve_receipt(
    ref: SourceRef,
    display_revision: str,
    current_record: Callable[[UUID, UUID], SourceReceipt],
) -> SourceReceipt:
    if display_revision != f"r{ref.revision}":
        raise ValueError("display_revision is not authoritative")
    receipt = current_record(ref.workspace_id, ref.source_id)
    if not isinstance(receipt, SourceReceipt) or receipt.ref != ref or receipt.display_revision != f"r{ref.revision}":
        raise ValueError("source receipt is stale or forged")
    return receipt


def canonical_receipts(receipts: tuple[SourceReceipt,...]) -> tuple[SourceReceipt,...]:
    """Collapse admitted upload aliases only for identical original/parser/readings.

    Callers must authorize every receipt before grouping. All alias source IDs remain
    manifest dependencies; grouping does not delegate or expand access.
    """
    groups={}
    for receipt in receipts:
        key=(receipt.ref.workspace_id,receipt.ref.original_sha256,receipt.ref.reading_sha256,receipt.ref.parser_id)
        groups.setdefault(key,[]).append(receipt)
    result=[]
    for group in groups.values():
        canonical=min(group,key=lambda r:r.ref.source_id.int)
        if any(r.reading!=canonical.reading for r in group):raise ValueError('alias reading seal collision')
        aliases=tuple(sorted(set(canonical.aliases)|{str(r.ref.source_id) for r in group if r.ref.source_id!=canonical.ref.source_id}))
        result.append(canonical.model_copy(update={'aliases':aliases}))
    return tuple(sorted(result,key=lambda r:r.ref.source_id.int))
