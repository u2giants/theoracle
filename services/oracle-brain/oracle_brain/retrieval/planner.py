"""Retrieval mode planning with role/workspace/access bounds; pure, fixture-only.

Chooses local, connected, historical or global retrieval from the question and
explicit scope. Ambiguous scope yields a clarifying question instead of a plan.
Historical retrieval always carries a bounded HistorySpan — never unbounded.
No provider calls, no company question generation.
"""
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from ..operating_model.source_receipts import _StrictModel

RetrievalMode = Literal["local", "connected", "historical", "global"]

from ..operating_model.question_signals_v1 import (_HISTORICAL_MARKERS,_CONNECTED_MARKERS,_GLOBAL_MARKERS,_LOCAL_MARKERS,_signals)

class AccessBounds(_StrictModel):
    """Role and workspace bounds every candidate span must satisfy."""
    role: str = Field(min_length=1, max_length=200)
    actor_id: UUID | None = None
    workspace_id: UUID
    allowed_workspace_ids: tuple[UUID, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _workspace_included(self) -> "AccessBounds":
        if self.workspace_id not in self.allowed_workspace_ids:
            raise ValueError("workspace_id must appear in allowed_workspace_ids")
        return self


class HistorySpan(_StrictModel):
    """Closed revision window for historical retrieval; never open-ended."""
    revision_from: int = Field(strict=True, ge=1)
    revision_to: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> "HistorySpan":
        if self.revision_to < self.revision_from:
            raise ValueError("revision_to must be >= revision_from")
        return self

    def contains(self, revision: int) -> bool:
        return self.revision_from <= revision <= self.revision_to


class RetrievalPlan(_StrictModel):
    schema_version: Literal[1] = 1
    mode: RetrievalMode
    question: str = Field(min_length=1, max_length=4000)
    access: AccessBounds
    history: HistorySpan | None = None
    process_ids: tuple[str, ...] = ()
    needs_clarification: bool = False
    clarifying_question: str | None = None

    @model_validator(mode="after")
    def _mode_consistency(self) -> "RetrievalPlan":
        if self.needs_clarification:
            if not self.clarifying_question:
                raise ValueError("clarifying_question required when needs_clarification")
            return self
        if self.clarifying_question:
            raise ValueError("clarifying_question only valid when needs_clarification")
        if self.mode == "historical" and self.history is None:
            raise ValueError("historical retrieval requires an explicit HistorySpan")
        if self.mode != "historical" and self.history is not None:
            raise ValueError("HistorySpan only applies to historical retrieval")
        return self




def plan_retrieval(
    question: str,
    *,
    access: AccessBounds,
    history: HistorySpan | None = None,
    process_ids: tuple[str, ...] = (),
    explicit_mode: RetrievalMode | None = None,
) -> RetrievalPlan:
    """Choose a retrieval mode, or ask one clarifying question when scope is ambiguous.

    Conflicting mode signals (for example a historical company-wide ask with no
    supplied HistorySpan) do not silently widen scope: they request clarification.
    """
    if not question.strip():
        raise ValueError("question must be non-empty")
    if explicit_mode is not None:
        if explicit_mode == "historical" and history is None:
            return RetrievalPlan(
                mode="historical", question=question, access=access,
                process_ids=process_ids, needs_clarification=True,
                clarifying_question=(
                    "Which revision range should the historical answer cover? "
                    "Provide revision_from and revision_to."
                ),
            )
        return RetrievalPlan(
            mode=explicit_mode, question=question, access=access,
            history=history if explicit_mode == "historical" else None,
            process_ids=process_ids,
        )

    historical, connected, global_scope, local = _signals(question)
    modes = [m for m, on in (
        ("historical", historical), ("connected", connected),
        ("global", global_scope), ("local", local),
    ) if on]
    if len(modes) > 1:
        return RetrievalPlan(
            mode="local", question=question, access=access, process_ids=process_ids,
            needs_clarification=True,
            clarifying_question=(
                "This question spans more than one scope "
                f"({', '.join(modes)}). Should the answer cover one process, "
                "connected processes, a bounded history span, or the company "
                "with explicit coverage bounds?"
            ),
        )
    if historical:
        if history is None:
            return RetrievalPlan(
                mode="historical", question=question, access=access,
                process_ids=process_ids, needs_clarification=True,
                clarifying_question=(
                    "Which revision range should the historical answer cover? "
                    "Provide revision_from and revision_to."
                ),
            )
        return RetrievalPlan(
            mode="historical", question=question, access=access,
            history=history, process_ids=process_ids,
        )
    if global_scope:
        return RetrievalPlan(
            mode="global", question=question, access=access, process_ids=process_ids,
        )
    if connected:
        return RetrievalPlan(
            mode="connected", question=question, access=access, process_ids=process_ids,
        )
    return RetrievalPlan(
        mode="local", question=question, access=access, process_ids=process_ids,
    )
