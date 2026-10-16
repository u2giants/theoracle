"""Source revision versioning: same bytes never re-ingest; genuine edits advance.

Pure decision logic only. No provider, database, network or runtime is
constructed here. Callers own authorization and persistence.
"""
from __future__ import annotations

import hashlib
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SourceRevision(_StrictModel):
    schema_version: Literal[1] = 1
    source_id: str = Field(min_length=1, max_length=128)
    revision: Annotated[int, Field(ge=1)]
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_type: str = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def _consistent(self) -> "SourceRevision":
        if not _SHA256.fullmatch(self.original_sha256):
            raise ValueError("original_sha256 must be lowercase hexadecimal")
        return self


class RevisionDecision(_StrictModel):
    """Outcome of an admission attempt; `created` is False on same-bytes idempotent."""

    schema_version: Literal[1] = 1
    revision: SourceRevision
    created: bool


def original_sha256(data: bytes) -> str:
    if type(data) is not bytes:
        raise TypeError("original bytes must be exact bytes")
    return hashlib.sha256(data).hexdigest()


def admit_revision(
    *,
    source_id: str,
    data: bytes,
    content_type: str,
    current: SourceRevision | None,
) -> RevisionDecision:
    """Same bytes/identity return the existing revision without re-ingest.

    A genuine byte change creates the next revision. A different content_type
    for identical bytes is a forged identity and is refused.
    """
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("source_id must be a nonempty string")
    if not isinstance(content_type, str) or not content_type:
        raise ValueError("content_type must be a nonempty string")
    digest = original_sha256(data)
    if current is not None:
        if type(current) is not SourceRevision:
            raise TypeError("current must be an exact SourceRevision")
        if current.source_id != source_id:
            raise ValueError("current revision belongs to a different source_id")
        if current.original_sha256 == digest:
            if current.content_type != content_type:
                raise ValueError("identical bytes cannot change content_type")
            return RevisionDecision(revision=current, created=False)
        revision = current.revision + 1
    else:
        revision = 1
    return RevisionDecision(
        revision=SourceRevision(
            source_id=source_id,
            revision=revision,
            original_sha256=digest,
            content_type=content_type,
        ),
        created=True,
    )


def is_current(head: SourceRevision, candidate: SourceRevision) -> bool:
    """True only when the candidate is exactly the current head revision."""
    if type(head) is not SourceRevision or type(candidate) is not SourceRevision:
        raise TypeError("exact SourceRevision values required")
    return head == candidate
