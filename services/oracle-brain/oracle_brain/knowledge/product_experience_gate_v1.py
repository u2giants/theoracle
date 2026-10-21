"""S12 product-experience completeness gate. Pure offline; fixture-only.

Refuses to declare the working product experience complete when any required
upstream journey is missing or incomplete. Never synthesizes ready or success
from metadata alone: an upstream journey counts only with an explicit accepted
state and a concrete evidence reference. No database, provider call, or live
proof is performed or implied here.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..operating_model.contracts import StrictRecord

# Upstream stages that must be accepted before S12 can declare completeness.
# S12 depends on S11; S11 on S10; ... S03 on the accepted S02 foundation.
REQUIRED_UPSTREAM_STAGES: tuple[str, ...] = (
    "S03",
    "S04",
    "S05",
    "S06",
    "S07",
    "S08",
    "S09",
    "S10",
    "S11",
)

StageName = Literal[
    "S03", "S04", "S05", "S06", "S07", "S08", "S09", "S10", "S11"
]


class UpstreamJourneyStateV1(StrictRecord):
    """Explicit state of one upstream journey. Metadata alone never equals ready."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    stage: StageName
    accepted: bool
    evidence_ref: str | None = None

    @model_validator(mode="after")
    def _evidence_required(self) -> "UpstreamJourneyStateV1":
        if self.accepted and not self.evidence_ref:
            raise ValueError(
                "accepted upstream journey requires an evidence_ref; "
                "metadata alone never equals ready"
            )
        return self


class ProductExperienceCompletenessRequestV1(StrictRecord):
    """S12 completeness declaration request. Refuses incomplete upstream."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    request_kind: Literal["product_experience_complete"] = "product_experience_complete"
    upstream: tuple[UpstreamJourneyStateV1, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _upstream(self) -> "ProductExperienceCompletenessRequestV1":
        seen: set[str] = set()
        for item in self.upstream:
            if item.workspace_id != self.workspace_id:
                raise ValueError(
                    "every upstream journey must belong to the request workspace"
                )
            if item.stage in seen:
                raise ValueError("duplicate upstream stage")
            seen.add(item.stage)
        return self


class CompletenessDecisionV1(StrictRecord):
    """Gate outcome. ready is never synthesized from missing or partial metadata."""

    schema_version: Literal[1] = 1
    workspace_id: UUID
    ready: bool
    missing_stages: tuple[str, ...] = ()
    incomplete_stages: tuple[str, ...] = ()
    refusal_reason: str = ""


def evaluate_product_experience_completeness(
    request: ProductExperienceCompletenessRequestV1,
) -> CompletenessDecisionV1:
    """Refuse incomplete upstream; never synthesize ready from metadata alone.

    A stage is missing when absent from the request, and incomplete when present
    but not accepted. Both conditions refuse the declaration. Only a complete
    set of accepted stages with evidence references yields ready.
    """
    provided = {item.stage: item for item in request.upstream}
    missing = tuple(
        stage for stage in REQUIRED_UPSTREAM_STAGES if stage not in provided
    )
    incomplete = tuple(
        stage
        for stage in REQUIRED_UPSTREAM_STAGES
        if stage in provided and not provided[stage].accepted
    )
    if missing or incomplete:
        parts: list[str] = []
        if missing:
            parts.append(f"missing upstream journeys: {', '.join(missing)}")
        if incomplete:
            parts.append(f"incomplete upstream journeys: {', '.join(incomplete)}")
        return CompletenessDecisionV1(
            workspace_id=request.workspace_id,
            ready=False,
            missing_stages=missing,
            incomplete_stages=incomplete,
            refusal_reason="; ".join(parts),
        )
    return CompletenessDecisionV1(workspace_id=request.workspace_id, ready=True)
