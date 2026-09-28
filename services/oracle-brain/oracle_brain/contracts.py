"""Wire contracts. These stay in parity with packages/brain-contracts/schema."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpan(StrictModel):
    source_id: UUID
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
    assertion_id: UUID
    subject: str = Field(min_length=1)
    predicate: str = Field(min_length=1)
    object: str = Field(min_length=1)
    span: SourceSpan
    confidence: float = Field(ge=0, le=1)


class CandidateBundle(StrictModel):
    contract_version: Literal[1] = 1
    workspace_id: UUID
    run_id: UUID
    source_id: UUID
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
    contract_version: Literal[1] = 1
    workspace_id: UUID
    assertion_id: UUID
    revision: int = Field(ge=1)
    operation: Literal["project", "withdraw"]
    projector_id: str = Field(min_length=1)
    applied_at: datetime
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")


class RunRequest(StrictModel):
    contract_version: Literal[1] = 1
    run_id: UUID
    workspace_id: UUID
    actor_id: UUID
    source_id: UUID
    source_revision: int = Field(ge=1)
    mode: Literal["synthetic", "approved_real"] = "synthetic"
