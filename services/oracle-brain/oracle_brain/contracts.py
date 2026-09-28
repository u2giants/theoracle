"""Wire contracts. These stay in parity with packages/brain-contracts/schema."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal
from uuid import RFC_4122, UUID

from pydantic import (AwareDatetime, BaseModel, ConfigDict, Field,
                      ValidationInfo, field_validator, model_validator)


WIRE_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)
WIRE_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("*", mode="before")
    @classmethod
    def canonical_wire_uuid(cls, value: object, info: ValidationInfo) -> object:
        if cls.model_fields[info.field_name].annotation is UUID:
            if isinstance(value, str) and not WIRE_UUID.fullmatch(value):
                raise ValueError("UUID must use an RFC variant hyphenated wire form")
            if isinstance(value, UUID) and (value.version not in range(1, 9)
                                            or value.variant != RFC_4122):
                raise ValueError("UUID must use a supported RFC variant")
        return value


class SourceSpan(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={
        "$comment": "Structural schema only: Oracle runtime enforces end > start.",
        "x-oracle-runtime-validation-required": ["end > start"],
    })

    source_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    source_revision: int = Field(ge=1)
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_range(self) -> "SourceSpan":
        if self.end <= self.start:
            raise ValueError("end must follow start")
        return self


class CandidateAssertion(StrictModel):
    assertion_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    span: SourceSpan
    confidence: float = Field(ge=0, le=1)


class CandidateBundle(StrictModel):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={
        "$comment": "Structural schema only: Oracle runtime enforces matching source IDs and revisions.",
        "x-oracle-runtime-validation-required": [
            "assertions[*].span.source_id == source_id",
            "assertions[*].span.source_revision == source_revision",
        ],
    })

    contract_version: Literal[1]
    workspace_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    run_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    source_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    source_revision: int = Field(ge=1)
    assertions: list[CandidateAssertion]

    @model_validator(mode="after")
    def matching_sources(self) -> "CandidateBundle":
        for assertion in self.assertions:
            if (assertion.span.source_id, assertion.span.source_revision) != (
                self.source_id, self.source_revision
            ):
                raise ValueError("candidate span must match bundle source revision")
        return self


class ProjectionReceipt(StrictModel):
    contract_version: Literal[1]
    workspace_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    assertion_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    revision: int = Field(ge=1)
    operation: Literal["project", "withdraw"]
    projector_id: str = Field(min_length=1)
    applied_at: AwareDatetime = Field(json_schema_extra={"pattern": WIRE_DATETIME.pattern})
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("applied_at", mode="before")
    @classmethod
    def canonical_wire_datetime(cls, value: object) -> object:
        if isinstance(value, str):
            if not WIRE_DATETIME.fullmatch(value):
                raise ValueError("timestamp must use ISO T and colonized offset")
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, (str, datetime)):
            raise ValueError("timestamp must be an aware ISO datetime")
        return value


class RunRequest(StrictModel):
    contract_version: Literal[1]
    run_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    workspace_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    actor_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    source_id: UUID = Field(json_schema_extra={"pattern": WIRE_UUID.pattern})
    source_revision: int = Field(ge=1)
    mode: Literal["synthetic", "approved_real"]
